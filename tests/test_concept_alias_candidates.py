import copy
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import propose_course_concept_aliases as candidates


def fixture_rows():
    text = 'LoRA: Low-Rank Adaptation of Large Language Models.'
    config = {'groups': [{'canonical': 'low-rank adaptation', 'members': ['lora', 'low-rank adaptation'],
        'type': 'METHOD', 'status': 'candidate_local_definition', 'basis': 'explicit_local_definition',
        'anchorPublicationId': 'paper1', 'supportQuote': 'LoRA: Low-Rank Adaptation',
        'reviewReason': '题名明确展开缩写，两次发生点保留原始文字。',
        'reviewedPublicationIds': ['paper1', 'paper2'], 'primaryUrls': ['https://arxiv.org/abs/2106.09685']}],
        'expected': {'concepts': 2, 'mentions': 2, 'potentialNodeReductions': 1}}
    docs = [{'sampleId': 's1', 'publicationId': 'paper1', 'text': text, 'textSha256': hashlib.sha256(text.encode()).hexdigest()},
        {'sampleId': 's2', 'publicationId': 'paper2', 'text': 'Low-Rank Adaptation.', 'textSha256': hashlib.sha256(b'Low-Rank Adaptation.').hexdigest()}]
    predictions = [{'sampleId': 's1', 'predictedEntities': [{'start': 0, 'end': 4, 'text': 'LoRA', 'label': 'METHOD'}]},
        {'sampleId': 's2', 'predictedEntities': [{'start': 0, 'end': 19, 'text': 'Low-Rank Adaptation', 'label': 'METHOD'}]}]
    mapping = [{'oldName': name, 'entityType': 'METHOD', 'newConceptId': f'c{i}', 'policy': 'casefold_only_no_semantic_merge'}
        for i, name in enumerate(config['groups'][0]['members'])]
    return config, mapping, docs, predictions


def test_candidate_evidence_keeps_literal_offsets_and_uncertainty():
    groups, mentions, summary = candidates.audit(*fixture_rows())
    assert groups[0]['anchorEvidence']['quote'] == 'LoRA: Low-Rank Adaptation'
    assert groups[0]['anchorEvidence']['start'] == 0
    assert mentions[0]['evidenceQuote'] == fixture_rows()[2][0]['text']
    assert mentions[0]['mention']['text'] == 'LoRA'
    assert mentions[1]['mention']['text'] == 'Low-Rank Adaptation'
    assert summary['potentialNodeReductions'] == 1 and summary['actualNodeReductions'] == 0
    assert summary['kind'] == 'candidate_not_graph_migration'
    assert summary['abstractSourcesUsed'] is False and summary['modelPromoted'] is False


@pytest.mark.parametrize('failure', ['type', 'duplicate', 'anchor', 'offset', 'hash', 'review', 'false_approval'])
def test_invalid_type_evidence_or_unreviewed_occurrence_is_rejected(failure):
    config, mapping, docs, predictions = copy.deepcopy(fixture_rows())
    if failure == 'type': config['groups'][0]['type'] = 'DATASET'
    if failure == 'duplicate': config['groups'].append(copy.deepcopy(config['groups'][0]))
    if failure == 'anchor': config['groups'][0]['supportQuote'] = 'Not in source'
    if failure == 'offset': predictions[0]['predictedEntities'][0]['end'] = 5
    if failure == 'hash': docs[0]['textSha256'] = '0' * 64
    if failure == 'review': config['groups'][0]['reviewedPublicationIds'] = ['paper1']
    if failure == 'false_approval': config['groups'][0]['supportQuote'] = 'Large Language Models'
    with pytest.raises(ValueError): candidates.audit(config, mapping, docs, predictions)


def test_existing_output_is_never_overwritten(tmp_path):
    with pytest.raises(FileExistsError): candidates.run(tmp_path)


def test_output_cannot_target_source_or_runtime():
    with pytest.raises(ValueError): candidates.run(candidates.g.ROOT / 'resources/new_concept_candidates')


@pytest.mark.parametrize('failure', ['source_hash', 'forbidden_source'])
def test_frozen_source_drift_or_unapproved_source_read_is_rejected(tmp_path, monkeypatch, failure):
    config = candidates.json.loads(candidates.CONFIG.read_text(encoding='utf-8'))
    if failure == 'source_hash': config['sources'][candidates.MAPPING] = '0' * 64
    else: config['sources']['forbidden_reserved_test.jsonl'] = '0' * 64
    monkeypatch.setattr(candidates.json, 'loads', lambda text: config)
    monkeypatch.setattr(candidates, 'vocabulary', lambda: None)
    with pytest.raises(ValueError): candidates.run(candidates.g.ROOT / 'kg_datasets/dblp/course_v4_runs' / tmp_path.name)
