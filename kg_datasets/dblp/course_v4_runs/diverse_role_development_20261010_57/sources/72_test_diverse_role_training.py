"""Data-only57 fit boundaries and sealed54 comparison recipe; no model fit here."""
import copy
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import train_diverse_abstract_relation as training


@pytest.fixture(scope='module')
def loaded():
    with patch.object(training.c, 'read_jsonl', wraps=training.c.read_jsonl) as reads:
        inputs = training.load_inputs()
    assert not any('test' in p.args[0].name for p in reads.call_args_list)
    return inputs


def test_only408_train_pairs_change_and612_steps_are_data_derived(loaded):
    config, recipe, parent, parent_re, data, _, legacy, added = loaded
    assert len(data['train']['relation']) == 408 and len(legacy) == 115 and len(added) == 22
    assert len(data['train']['ner']) == 65 and len(data['dev']['relation']) == 333
    assert 6*((len(data['train']['relation'])+3)//4) == 612
    assert recipe['snapshotManifestSha256'] != config['snapshotManifestSha256']
    assert config['automaticPromotionAllowed'] is False and config['NERTrainingAllowed'] is False
    assert parent_re['RETraining']['initialization'].endswith('re_entity_development_20261006_15/checkpoint_epoch_03')
    assert training.c.file_sha256(training.old.CONTRACT) == config['evaluationRecipeSha256']
    previous = training.read(training.c.ROOT/recipe['frozenNERRun']/'comparison.json')
    metrics = training.read(training.c.ROOT/'kg_datasets/dblp/course_v4_runs/abstract_benchmark_development_20261008_46/re/development_result.json')['bestDev']['metrics']
    gates = training.old.gates(parent, data, {k: copy.deepcopy(previous['historicalPipeline']['new']) for k in ('old', 'new')}, {k: copy.deepcopy(metrics) for k in ('old', 'new')}, previous['historicalNER']['new']['metrics'])
    assert {'completeReferenceEVALUATED_ONSupport', 'completeDocumentCoverage'} <= set(gates['blockedBy'])
    assert gates['qualityPromotionPassed'] is False


@pytest.mark.parametrize(('key', 'value'), [('NERTrainingAllowed', True), ('automaticPromotionAllowed', True), ('reserveBytes', 999_999_999), ('evaluationRecipeSha256', '0'*64), ('expectedSteps', 611), ('expected', {})])
def test_scope_drift_rejected_before_any_fit(key, value):
    config = training.read(training.CONTRACT); config[key] = value
    with patch.object(training, 'read', return_value=config), pytest.raises(ValueError):
        training.load_inputs()


def test_existing_and_outside_run_paths_rejected_before_reads(tmp_path):
    with patch.object(training, 'load_inputs', side_effect=AssertionError('No reads permitted')):
        with pytest.raises(FileExistsError): training.run(tmp_path)
        with pytest.raises(ValueError): training.run(tmp_path/'new')


def test_cached54_is_recounted_not_inferred_and_keeps_full_candidate_scope(loaded):
    _, recipe, _, _, data, _, _, _ = loaded
    result = training.cached54(data, recipe)
    assert result['kind'] == 'sealed54_prediction_cache_recount_not_new_inference'
    assert result['pipeline']['positiveMicro']['predicted'] == 182
    assert result['pipeline']['positiveMicro']['truePositive'] == 59
    assert result['falsePositives'] == 123 and result['falseNegatives'] == 25
    assert result['module']['perClass']['NO_RELATION']['reference'] == 66


def test_expected_keys_order_does_not_change_inventory(loaded):
    config = copy.deepcopy(loaded[0]); config['expected'] = dict(reversed(list(config['expected'].items())))
    original = training.read
    with patch.object(training, 'read', side_effect=lambda p: config if p == training.CONTRACT else original(p)):
        assert len(training.load_inputs()[4]['train']['relation']) == 408


@pytest.mark.parametrize('fit_fails', [False, True])
def test_resource_refusal_and_partial_fit_failure_leave_honest_states(loaded, fit_fails):
    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True, mem_get_info=lambda: (8_000_000_000, 8_000_000_000), get_device_name=lambda _: 'mock_not_real_GPU'), __version__='mock', version=SimpleNamespace(cuda='mock'))
    transformers = SimpleNamespace(__version__='mock', DataCollatorWithPadding=None)
    def failed_fit(data, settings, config, output):
        output.mkdir(); training.c.write_json(output/'status.json', {'status': 'running'})
        raise RuntimeError('simulated fit interruption')
    with TemporaryDirectory(prefix='pytest_diverse57_', dir=training.c.ROOT/'kg_datasets/dblp/course_v4_runs') as folder:
        output = Path(folder)/'run'
        with patch.object(training, 'load_inputs', return_value=loaded), patch.object(training, 'cached54', return_value={}), patch.object(training, 'read', return_value={'inputSha256': {}}), patch.object(training.shutil, 'disk_usage', return_value=SimpleNamespace(free=8_000_000_000 if fit_fails else 0)), patch.object(training.old.boundary, 'memory_available', return_value=8_000_000_000), patch.dict(sys.modules, torch=torch, transformers=transformers), patch.object(training.old, 'fit', side_effect=failed_fit) as fit:
            with pytest.raises(RuntimeError if fit_fails else ValueError): training.run(output)
        assert training.old.read(output/'status.json')['status'] == 'failed_no_synthetic_fallback'
        assert fit.call_count == int(fit_fails)
        if fit_fails:
            assert training.old.read(output/'re/status.json')['status'] == 'failed_no_synthetic_fallback'
        else:
            assert not (output/'re').exists()
