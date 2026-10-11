"""A local expression benchmark must not manufacture document negatives."""
import copy
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import evaluate_evidence_blocks as blocks


def source(text='Model solves task. Results on Data. Empty sentence.'):
    entities = []
    for label, literal in [('METHOD', 'Model'), ('TASK', 'task'), ('DATASET', 'Data')]:
        if literal in text:
            start = text.index(literal)
            entities.append({'entityId': 'e'+str(len(entities)+1), 'label': label,
                             'text': literal, 'start': start, 'end': start+len(literal)})
    entities.sort(key=lambda e: e['start'])
    ref = {'sampleId': 'sample-'+'0'*20, 'arxivId': '1', 'groupId': 'paper-1',
           'sourceURL': 'https://example.org/1', 'referenceTitle': 'Never prepend title',
           'split': 'dev', 'textKind': 'abstract', 'text': text,
           'textSha256': hashlib.sha256(text.encode()).hexdigest()}
    return ref, {'reference': ref, 'annotation': {'entities': entities, 'groupMentions': []}}


def judgment(unit):
    return {'arxivId': unit['arxivId'], 'block': unit['block'],
            'entityReview': 'Reviewed every local entity and the empty regions.',
            'pairReview': 'All local typed pairs reviewed; remaining pairs express no predicate.',
            'positives': [['e1', 'e2', 'USED_FOR', 'Explicit task predicate.']], 'unresolved': []}


def test_all_nonoverlapping_blocks_conserve_original_unicode_and_empty_regions():
    ref, receipt = source('Model solves task. Results on Data. 中文😀 remains. End.')
    original = copy.deepcopy((ref, receipt)); units = blocks.build_units([ref], [receipt])
    assert ''.join(u['text'] for u in units) == ref['text'] and len(units) == 2
    assert units[0]['sourceStart'] == 0 and units[-1]['sourceEnd'] == len(ref['text'])
    assert units[1]['entities'] == [] and (ref, receipt) == original
    assert all(ref['text'][u['sourceStart']:u['sourceEnd']] == u['text'] for u in units)
    assert all('Never prepend title' not in u['text'] for u in units)


def test_decimal_and_vs_numeric_scores_do_not_split_sentences():
    ref, receipt = source('Model gets 1.5 (90.2% vs. 91.1%) on Data. Next task. Third.')
    units = blocks.build_units([ref], [receipt])
    assert len(units) == 2 and 'vs. 91.1%' in units[0]['text']


@pytest.mark.parametrize('mutation', ['hash', 'identity', 'span', 'duplicate', 'missing', 'label', 'empty_text'])
def test_source_trust_boundary_rejects_drift(mutation):
    ref, receipt = source(); refs, receipts = [ref], [receipt]
    if mutation == 'hash': ref['textSha256'] = 'bad'
    if mutation == 'identity': receipt['reference'] = ref | {'sampleId': 'other'}
    if mutation == 'span': receipt['annotation']['entities'][0]['text'] = 'wrong'
    if mutation == 'duplicate': refs = refs*2; receipts = receipts*2
    if mutation == 'missing': receipts = []
    if mutation == 'label': receipt['annotation']['entities'][0]['label'] = 'VENUE'
    if mutation == 'empty_text': ref['text'] = ''; ref['textSha256'] = hashlib.sha256(b'').hexdigest()
    with pytest.raises(ValueError): blocks.build_units(refs, receipts)


def test_shared_head_and_cross_boundary_entities_are_quarantined_not_dropped():
    ref, receipt = source()
    receipt['annotation']['groupMentions'] = [{'start': 0, 'end': 5, 'text': 'Model', 'label': 'METHOD'}]
    assert blocks.build_units([ref], [receipt])[0]['entityStatus'] == 'unresolved'
    receipt['annotation']['groupMentions'] = []
    start = ref['text'].index('Data')
    receipt['annotation']['entities'] = [{'entityId': 'e1', 'label': 'METHOD', 'start': start,
        'end': len(ref['text']), 'text': ref['text'][start:]}]
    units = blocks.build_units([ref], [receipt])
    assert len(units) == 2 and all(u['entityStatus'] == 'unresolved' for u in units)


def test_not_expressed_is_sidecar_only_never_a_training_negative():
    unit = blocks.build_units(*([x] for x in source()))[0]
    result = blocks.compile_units([unit], [judgment(unit)])
    assert {p['state'] for p in result['pairStates']} == {'USED_FOR', 'NOT_EXPRESSED'}
    assert [p['label'] for p in result['positives']] == ['USED_FOR']
    assert len(result['complete']) == 1 and result['trainableNegativePairs'] == 0
    assert all('label' not in p for p in result['pairStates'])


@pytest.mark.parametrize('mutation', ['negative', 'duplicate', 'illegal', 'missing', 'order', 'no_review'])
def test_explicit_exhaustive_judgment_contract(mutation):
    unit = blocks.build_units(*([x] for x in source()))[0]; decision = judgment(unit)
    if mutation == 'negative': decision['positives'][0][2] = 'NO_RELATION'
    if mutation == 'duplicate': decision['positives'] *= 2
    if mutation == 'illegal': decision['positives'][0][1] = 'e1'
    if mutation == 'missing': decision = None
    if mutation == 'order': decision['block'] = 2
    if mutation == 'no_review': decision['pairReview'] = ''
    with pytest.raises(ValueError): blocks.compile_units([unit], [] if decision is None else [decision])


def test_one_unresolved_pair_excludes_entire_block_but_keeps_ner_and_positive_records():
    unit = blocks.build_units(*([x] for x in source()))[0]; decision = judgment(unit)
    decision['unresolved'] = [['e1', 'e3', 'Configuration attachment ambiguous.']]
    result = blocks.compile_units([unit], [decision])
    assert result['complete'] == [] and len(result['ner']) == 1
    assert len(result['positives']) == 1 and len(result['excluded']) == 1


def test_pair_projection_preserves_offsets_and_explicit_zero_reference_blocks():
    ref, receipt = source(); units = blocks.build_units([ref], [receipt])
    decisions = [judgment(units[0]), judgment(units[1]) | {'positives': []}]
    result = blocks.compile_units(units, decisions)
    assert len(result['complete']) == 2
    p = result['positives'][0]; offset = units[0]['sourceStart']
    for role in ('head', 'tail'):
        e = p[role]; assert ref['text'][offset+e['start']:offset+e['end']] == e['text']


def test_actual_fixed_queue_and_judgments_align_without_test_semantic_access():
    config, refs, receipts, _ = blocks.load_sources()
    units = blocks.build_units(refs, receipts)
    assert len(units) == 31 and {u['arxivId'] for u in units} == set(config['papers'])
    assert sum(u['entityStatus'] == 'unresolved' for u in units) == 1


def test_existing_output_refused_before_source_or_model_access(tmp_path, monkeypatch):
    monkeypatch.setattr(blocks, 'load_sources', lambda: pytest.fail('source access'))
    with pytest.raises(FileExistsError): blocks.new_output(tmp_path)
