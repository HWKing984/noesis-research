import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import annotation_v3 as contract
from prepare_revision_v3 import apply_case_decision, convert_record, import_stress_review, make_blind, render_page

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def row():
    text = 'Graph Neural Networks for Node Classification'
    old = {'publicationId': 'test/1', 'title': text, 'text': text, 'textKind': 'title', 'year': 2020,
           'type': 'article', 'doi': '', 'topics': ['graph'], 'groupId': 'g1', 'sourceCsvSha256': 'a'*64,
           'schemaVersion': 'v2-candidate', 'schemaSha256': 'a'*64, 'intendedSplit': 'train',
           'samplingStratum': {}, 'ambiguityFlags': [],
           'textSource': {'provider':'DBLP','sourceRecordId':'test/1','snapshot':'2026-09-01',
             'sourceUrl':'https://dblp.org/rec/test/1','license':'CC0-1.0','textSha256':hashlib.sha256(text.encode()).hexdigest()},
           'entities': [{'start':0,'end':21,'text':'Graph Neural Networks','label':'METHOD','origin':'draft_dictionary_v2'},
                        {'start':26,'end':45,'text':'Node Classification','label':'TASK','origin':'draft_dictionary_v2'}],
           'relations': [], 'domains': [], 'notes':'', **{key:contract.new_review() for key in ('entity_review','relation_review','domain_review')}}
    return convert_record(old, 'b'*64)


def test_ai_suggestions_keep_provenance_and_draft(row):
    item = {'blind_index': 6, 'proposed_entities': [{'start':0,'end':21,'text':'Graph Neural Networks','label':'METHOD'}], 'boundary_review':'fixture'}
    result = apply_case_decision(row, item, {'forms':['composite'], 'note':'fixture'})
    assert result['entities'][0]['origin'] == 'ai_suggestion'
    assert result['initialDraftProvenance']['kind'] == 'ai_rule_stress_test'
    assert contract.validate_records([result], reference=[result])['valid']
    for scope in ('entity_gold','relation_gold','domain_gold'):
        assert not contract.validate_records([result], reference=[result], **{scope:True})['valid']
    assert not contract.validate_records([result])['training_ready']


def test_coordinated_mentions_are_not_individual_relation_pairs(row):
    row['entities'][0]['mentionForm'] = 'coordinated'
    assert not contract.candidate_pairs(row['entities'])
    assert contract.scope_exclusions(row['entities'])
    row['relations'] = [{'head':0,'tail':1,'label':'USED_FOR','reason':'fixture','evidence':{'start':0,'end':len(row['text']),'text':row['text']}}]
    assert not contract.validate_records([row])['valid']


def test_task_dependency_is_out_of_scope_not_negative(row):
    row['entities'][0]['label'] = 'TASK'
    assert not contract.candidate_pairs(row['entities'])
    assert any(item['reason'] == 'TASK_TO_TASK_OUT_OF_SCOPE' for item in contract.scope_exclusions(row['entities']))


def test_blank_package_has_no_answers_or_notes(row):
    row['notes'] = 'AI ANSWER SECRET'
    blank = make_blind(row, 'c'*64)
    assert not blank['entities'] and not blank['relations'] and not blank['domains'] and not blank['notes']
    assert blank['initialDraftProvenance']['kind'] == 'blind'
    assert blank['initialDraftProvenance']['aiReviewSha256'] is None
    assert 'AI ANSWER SECRET' not in render_page([blank], title='fixture', download='fixture.jsonl', blind=True)


@pytest.mark.parametrize('field', ['boundaryRulesSha256', 'initialDraftProvenance', 'intendedSplit', 'textSource'])
def test_new_and_old_provenance_immutable(row, field):
    changed = copy.deepcopy(row)
    changed[field] = 'tampered'
    assert not contract.validate_records([changed], reference=[row])['valid']


def test_new_shape_requires_form_and_ai_source(row):
    changed = copy.deepcopy(row)
    del changed['entities'][0]['mentionForm']
    assert not contract.validate_records([changed])['valid']
    row['entities'][0]['origin'] = 'ai_suggestion'
    assert not contract.validate_records([row])['valid']


def test_source_review_import_is_hash_and_reference_bound():
    data = ROOT / 'kg_datasets/dblp/ner_v3'
    if not data.exists():
        pytest.skip('Generated source package not yet available')
    result = import_stress_review(data / 'source_review', data / 'legacy_reference')
    assert len(result['items']) == 20
    assert result['stats'] == {'documents':20,'proposed_entities':46,'proposed_by_label':{'METHOD':24,'TASK':21,'DATASET':1},'baseline_entities':21,'strict_matches':10}


@pytest.mark.parametrize('blind_index', [1,2,3,4,5,6,7,9,13,15,16,18,20,21,22,24,25,29,31,41])
def test_twenty_cases_are_structural_policy_fixtures_not_gold(blind_index):
    data = ROOT / 'kg_datasets/dblp/ner_v3'
    if not data.exists():
        pytest.skip('Generated source package not yet available')
    rows = contract.read_jsonl(data / 'pilot20_ai_candidates.jsonl')
    source = json.loads((data / 'source_review/pilot20_boundary_review.json').read_text(encoding='utf-8'))
    item = next(i for i in source['items'] if i['blind_index'] == blind_index)
    row = next(r for r in rows if r['publicationId'] == item['publicationId'])
    decision = next(i for i in contract.RULES['case_decisions'] if i['blind_index'] == blind_index)
    expected = decision.get('replace_entities', item['proposed_entities'])
    assert [{k:e[k] for k in ('start','end','text','label')} for e in row['entities']] == [{k:e[k] for k in ('start','end','text','label')} for e in expected]
    assert [e['mentionForm'] for e in row['entities']] == decision['forms']
    assert all(e['origin']=='ai_suggestion' for e in row['entities'])
    assert row['entity_review']['status']=='draft' and row['intendedSplit']=='train'
    assert contract.validate_records([row], reference=[row])['valid']
    assert not contract.validate_records([row], reference=[row], entity_gold=True)['valid']
