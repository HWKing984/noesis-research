"""Simulated orchestration only; real hardware evidence remains in the sealed60 run."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import train_pair_window_relation as training


@pytest.fixture(scope='module')
def loaded():
    return training.load_inputs()


@pytest.mark.parametrize('drift', [False, True])
def test_completed_or_drifted_orchestration_preserves_every_original_candidate(loaded, drift):
    data = loaded[5]; baseline, candidates, refs, by_id = training.cached_baseline(data)
    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True,
        mem_get_info=lambda: (8_000_000_000, 8_000_000_000), get_device_name=lambda _: 'mock_not_real_GPU', empty_cache=lambda: None),
        __version__='mock', version=SimpleNamespace(cuda='mock'))
    transformers = SimpleNamespace(__version__='mock', DataCollatorWithPadding=lambda *a, **k: None)
    model = SimpleNamespace(); model.to = lambda _: model; model.requires_grad_ = lambda _: model
    changed = False; digest = training.c.file_sha256
    def checked_digest(path):
        return '0'*64 if changed and path == training.CONTRACT else digest(path)
    def simulated_fit(transformed, settings, config, output):
        nonlocal changed
        assert [p['label'] for p in transformed['train']['relation']] == [p['label'] for p in data['train']['relation']]
        assert transformed['dev']['relation'] == [training.window_pair(r) for r in data['dev']['relation']]
        output.mkdir(); checkpoint = output/'checkpoint_epoch_06'; checkpoint.mkdir()
        changed = drift
        return checkpoint, {'steps': 612, 'bestDev': {'metrics': baseline['module']}}
    cache = [training.c.read_jsonl(training.BASELINE/(name+'.jsonl')) for name in ('new_module_dev_predictions', 'new_pipeline_predictions')]
    calls = []
    def simulated_predict(model, tokenizer, cropped, max_length, collator, device, batch_size):
        old = cache[len(calls)]; calls.append(len(cropped))
        assert len(cropped) == len(old) and all('evidence' not in r and 'reason' not in r for r in cropped)
        return [{k: v for k, v in row.items() if k != 'label'} | {'label': p['label'],
                 'probabilities': p['probabilities'], 'pairId': training.re_model.pair_id(row)} for row, p in zip(cropped, old)]
    with TemporaryDirectory(prefix='pytest_window60_normal_', dir=training.c.ROOT/'kg_datasets/dblp/course_v4_runs') as folder:
        output = Path(folder)/'run'
        with patch.object(training, 'load_inputs', return_value=loaded), patch.object(training, 'cached_baseline', return_value=(baseline, candidates, refs, by_id)), \
                patch.object(training.c, 'file_sha256', side_effect=checked_digest), patch.object(training.shutil, 'disk_usage', return_value=SimpleNamespace(free=8_000_000_000)), \
                patch.object(training.source.old.boundary, 'memory_available', return_value=8_000_000_000), patch.dict(sys.modules, torch=torch, transformers=transformers), \
                patch.object(training.source.old, 'fit', side_effect=simulated_fit), patch.object(training.prior, 'setup', return_value='mock'), \
                patch.object(training.re_model, 'prepare_tokenizer', return_value=None), patch.object(training.re_model, 'load_relation_model', return_value=model), \
                patch.object(training.prior, 'predict', side_effect=simulated_predict):
            if drift:
                with pytest.raises(ValueError, match='drift'): training.run(output)
            else: training.run(output)
        assert calls == [333, 183]
        assert training.read(output/'status.json')['status'] == ('failed_no_synthetic_fallback' if drift else 'completed')
        assert (output/'manifest.json').exists() is not drift
        if not drift:
            result = training.read(output/'comparison.json')
            assert result['pipeline']['new'] == baseline['pipeline']
            assert result['allPipelineCandidates'] == 183 and result['documentCoverage'] == 7/19
            assert not result['modelPromoted'] and not result['testEvaluated']
        assert not (output/'sources/test_references.jsonl').exists()
