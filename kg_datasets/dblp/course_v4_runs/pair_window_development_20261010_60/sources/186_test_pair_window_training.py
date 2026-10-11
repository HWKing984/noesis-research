"""Local context is an input feature, never a gold-evidence selector."""
import copy
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import train_pair_window_relation as training


def pair(text, head='Method', tail='task'):
    def entity(name, label):
        start = text.index(name)
        return {'start': start, 'end': start+len(name), 'text': name, 'label': label}
    return {'sampleId': 'sample-'+'0'*20, 'text': text,
            'textSha256': training.c.canonical_sha256(text),
            'head': entity(head, 'METHOD'), 'tail': entity(tail, 'TASK'),
            'label': 'USED_FOR'}


def test_window_retains_one_neighbor_each_side_and_original_is_unchanged():
    text = 'Far background. Left context. Method solves task. Right context. Far result.'
    row = pair(text); original = copy.deepcopy(row)
    local = training.window_pair(row)
    assert local['text'] == 'Left context. Method solves task. Right context. '
    assert row == original and 'contextWindow' not in row
    assert local['contextWindow']['sourceTextSha256'] == row['textSha256']
    assert local['contextWindow']['sourcePairId'] == training.re_model.pair_id(row)
    for role in ('head', 'tail'):
        assert local['text'][local[role]['start']:local[role]['end']] == row[role]['text']


def test_labels_and_evidence_never_choose_the_window():
    row = pair('Outside. Before. Method solves task. After. Elsewhere.')
    other = row | {'label': 'NO_RELATION', 'evidence': {'text': 'Elsewhere.'}, 'reason': 'different judgment'}
    a, b = training.window_pair(row), training.window_pair(other)
    assert {k: v for k, v in a.items() if k != 'label'} == {k: v for k, v in b.items() if k != 'label'}
    assert 'evidence' not in b and 'reason' not in b


@pytest.mark.parametrize('text', ['Method solves task', 'task uses Method.', '中文说明。 Method solves task.'])
def test_single_sentence_unicode_and_reversed_endpoints(text):
    row = pair(text)
    assert training.window_pair(row)['text'] == text


def test_cross_sentence_pairs_keep_all_intervening_text():
    row = pair('Far away. Neighbor. Method introduced. Intervening context. A task studied. Neighbor result. Far away.')
    local = training.window_pair(row)
    assert 'Intervening context.' in local['text']
    assert local['head']['start'] < local['tail']['start']
    assert not local['text'].startswith('Far away.') and not local['text'].endswith('Far away.')


def test_decimal_is_not_a_boundary_and_inside_entity_split_does_not_cut_entity():
    row = pair('Before. Method 3.5 tested task. After.', head='Method 3.5')
    assert training.window_pair(row)['head']['text'] == 'Method 3.5'
    row = pair('Outside. Before. Method. Variant solves task. After. Outside.', head='Method. Variant')
    local = training.window_pair(row)
    assert local['text'][local['head']['start']:local['head']['end']] == 'Method. Variant'


def test_invalid_source_spans_are_rejected():
    row = pair('Method solves task.'); row['head']['end'] += 1
    with pytest.raises(ValueError): training.window_pair(row)


def prediction(row):
    local = training.window_pair(row)
    return {k: v for k, v in local.items() if k != 'label'} | {
        'label': 'USED_FOR', 'probabilities': {'USED_FOR': .7, 'EVALUATED_ON': 0., 'NO_RELATION': .3},
        'pairId': training.re_model.pair_id(local)}


def test_predictions_restore_full_document_identity_without_gold_features():
    row = pair('Far background. Left context. Method solves task. Right context. Far result.')
    result = training.restore_predictions([row], [prediction(row)])[0]
    assert result['text'] == row['text'] and result['head'] == row['head'] and result['tail'] == row['tail']
    assert result['pairId'] == training.re_model.pair_id(row)
    assert result['probabilities']['USED_FOR'] == .7
    assert 'evidence' not in result and 'reason' not in result


@pytest.mark.parametrize('field', ['sampleId', 'text', 'head', 'pairId', 'contextWindow'])
def test_prediction_drift_cannot_be_restored_as_a_success(field):
    row = pair('Far background. Left context. Method solves task. Right context. Far result.')
    pred = prediction(row); pred[field] = 'changed'
    with pytest.raises(ValueError): training.restore_predictions([row], [pred])


def test_candidate_loss_or_illegal_relation_is_rejected():
    row = pair('Method solves task.')
    with pytest.raises(ValueError): training.restore_predictions([row], [])
    pred = prediction(row); pred['label'] = 'EVALUATED_ON'
    with pytest.raises(ValueError): training.restore_predictions([row], [pred])


def test_existing_or_outside_outputs_rejected_before_loading(tmp_path):
    with patch.object(training, 'load_inputs', side_effect=AssertionError('No source read')):
        with pytest.raises(FileExistsError): training.run(tmp_path)
        with pytest.raises(ValueError): training.run(tmp_path/'outside')


@pytest.mark.parametrize(('key', 'value'), [('neighborSentences', 0), ('automaticPromotionAllowed', True), ('expectedSteps', 613), ('testContentAccessAllowed', True)])
def test_changed_protocol_rejected_before_parent_source_reads(key, value):
    config = training.read(training.CONTRACT); config[key] = value
    with patch.object(training, 'read', return_value=config), patch.object(training.source, 'load_inputs', side_effect=AssertionError('No source read')), pytest.raises(ValueError):
        training.load_inputs()


@pytest.fixture(scope='module')
def loaded():
    with patch.object(training.c, 'read_jsonl', wraps=training.c.read_jsonl) as reads:
        inputs = training.load_inputs()
    assert not any('test' in str(call.args[0].name) for call in reads.call_args_list)
    return inputs


def test_real_known_pairs_and_source_splits_are_preserved(loaded):
    config, inherited, recipe, parent, parent_re, data, manifest = loaded
    assert len(data['train']['relation']) == 408 and len(data['dev']['relation']) == 333
    assert inherited['expected']['trainUnknown'] == 1949
    assert parent_re['RETraining']['epochs'] == 6 and config['expectedSteps'] == 612
    for split in ('train', 'dev'):
        original = copy.deepcopy(data[split]['relation'])
        cropped = [training.window_pair(r) for r in original]
        assert [r['label'] for r in cropped] == [r['label'] for r in original]
        assert [r['contextWindow']['sourcePairId'] for r in cropped] == [training.re_model.pair_id(r) for r in original]
        assert data[split]['relation'] == original


def test_sealed57_recount_keeps_every_candidate_and_original_denominator(loaded):
    data = loaded[5]
    baseline, candidates, refs, by_id = training.cached_baseline(data)
    assert baseline['kind'] == 'sealed57_predictions_recount_not_new_inference'
    assert baseline['pipeline']['positiveMicro']['truePositive'] == 59
    assert baseline['pipeline']['positiveMicro']['predicted'] == 176
    assert baseline['pipeline']['positiveMicro']['reference'] == 84
    assert len(data['dev']['full_relation']) == 7 and len(refs) == 107
    assert baseline['module']['perClass']['NO_RELATION']['reference'] == 66
    cropped = [training.window_pair(r) for r in candidates]
    assert len(cropped) == len(candidates) and len(by_id) == 16


@pytest.mark.parametrize('fit_fails', [False, True])
def test_resource_refusal_or_interrupted_fit_never_seals_success(loaded, fit_fails):
    torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True,
        mem_get_info=lambda: (8_000_000_000, 8_000_000_000), get_device_name=lambda _: 'mock_not_real_GPU'),
        __version__='mock', version=SimpleNamespace(cuda='mock'))
    transformers = SimpleNamespace(__version__='mock', DataCollatorWithPadding=None)
    def fail_fit(data, settings, config, output):
        output.mkdir(); training.c.write_json(output/'status.json', {'status': 'running'})
        raise RuntimeError('simulated fit interruption')
    with TemporaryDirectory(prefix='pytest_window60_', dir=training.c.ROOT/'kg_datasets/dblp/course_v4_runs') as folder:
        output = Path(folder)/'run'
        with patch.object(training, 'load_inputs', return_value=loaded), patch.object(training, 'cached_baseline', return_value=({}, [], [], {})), \
                patch.object(training.shutil, 'disk_usage', return_value=SimpleNamespace(free=8_000_000_000 if fit_fails else 0)), \
                patch.object(training.source.old.boundary, 'memory_available', return_value=8_000_000_000), \
                patch.dict(sys.modules, torch=torch, transformers=transformers), patch.object(training.source.old, 'fit', side_effect=fail_fit) as fit:
            with pytest.raises(RuntimeError if fit_fails else ValueError): training.run(output)
        assert training.read(output/'status.json')['status'] == 'failed_no_synthetic_fallback'
        assert not (output/'manifest.json').exists() and fit.call_count == int(fit_fails)
        if fit_fails: assert training.read(output/'re/status.json')['status'] == 'failed_no_synthetic_fallback'
