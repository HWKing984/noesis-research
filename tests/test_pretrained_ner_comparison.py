import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import compare_pretrained_ner as app
from compare_pretrained_ner import checked_dev, checked_entities


def row(text='BERT用于分类'):
    return {'sampleId': 'dev-1', 'split': 'dev', 'textKind': 'abstract', 'text': text,
            'textSha256': hashlib.sha256(text.encode()).hexdigest(), 'entities': []}


def test_original_unicode_offsets_and_class_mapping():
    prediction = [{'start': 0, 'end': 4, 'text': 'BERT', 'label': 'machine learning method', 'score': .8}]
    assert checked_entities(row(), prediction) == [{'start': 0, 'end': 4, 'text': 'BERT', 'label': 'METHOD'}]


@pytest.mark.parametrize('patch', [{'label': 'person'}, {'text': 'bert'}, {'end': 30}, {'score': float('nan')}])
def test_invalid_model_output_is_rejected(patch):
    prediction = {'start': 0, 'end': 4, 'text': 'BERT', 'label': 'machine learning method', 'score': .8} | patch
    with pytest.raises(ValueError): checked_entities(row(), [prediction])


def test_overlapping_or_duplicate_predictions_are_rejected():
    prediction = {'start': 0, 'end': 4, 'text': 'BERT', 'label': 'machine learning method', 'score': .8}
    with pytest.raises(ValueError): checked_entities(row(), [prediction, prediction])


@pytest.mark.parametrize('patch', [{'split': 'test'}, {'textSha256': '0' * 64}, {'textKind': 'title'}])
def test_only_integrity_checked_dev_abstracts_are_accepted(patch):
    with pytest.raises(ValueError): checked_dev([row() | patch])


def test_complete_unique_cohort_required():
    assert checked_dev([row()]) == [row()]
    for rows in ([], [row(), row()]):
        with pytest.raises(ValueError): checked_dev(rows)


@pytest.fixture
def inputs(monkeypatch):
    config = {'version': 'pretrained_ner_comparison_v1', 'labelMap': app.LABELS, 'threshold': .5,
              'flatNER': True, 'automaticPromotionAllowed': False, 'snapshot': 'snapshot',
              'baselineNER': 'ner', 'frozenRE': 're', 'snapshotManifestSha256': 'a',
              'baselineNERManifestSha256': 'b', 'frozenREManifestSha256': 'c',
              'expected': {'NERdev': 1, 'completeDev': 1, 'knownPairs': 0, 'completePairs': 0}}
    records = {'ner_dev.jsonl': [row()], 'full_relation_dev.jsonl': [row()], 'relation_dev.jsonl': [],
               'new_ner_dev_predictions.jsonl': [{'sampleId': 'dev-1', 'referenceEntities': [], 'predictedEntities': []}]}
    monkeypatch.setattr(app, 'read', lambda path: config)
    monkeypatch.setattr(app.g, 'verified_files', lambda *args: {})
    monkeypatch.setattr(app.g.c, 'read_jsonl', lambda path: records[path.name])
    return config, records


def test_locked_cohort_and_reference_cache_are_verified(inputs):
    _, rows, full, refs, cache = app.load_inputs()
    assert len(rows) == len(full) == len(cache) == 1 and refs == []


@pytest.mark.parametrize('field,value', [('threshold', .7), ('automaticPromotionAllowed', True), ('flatNER', False)])
def test_parameter_search_and_auto_promotion_are_rejected(inputs, field, value):
    config, _ = inputs; config[field] = value
    with pytest.raises(ValueError, match='experiment drift'): app.load_inputs()


def test_cache_reference_mismatch_is_rejected(inputs):
    _, records = inputs; records['new_ner_dev_predictions.jsonl'][0]['referenceEntities'] = [{'text': 'other'}]
    with pytest.raises(ValueError, match='cohort'): app.load_inputs()


def test_no_overwrite_or_output_escape(tmp_path):
    with pytest.raises(FileExistsError): app.run(tmp_path)
    with pytest.raises(ValueError, match='outside runs'): app.run(tmp_path / 'new')
