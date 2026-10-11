import copy
import csv
import json
import runpy
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import prepare_revision_v3 as prepare
import annotation_v3 as contract


@pytest.fixture
def source(tmp_path):
    data=prepare.ROOT/'kg_datasets/dblp/ner_v3'
    shutil.copytree(data/'source_review',tmp_path/'source')
    shutil.copytree(data/'legacy_reference',tmp_path/'previous')
    return tmp_path/'source',tmp_path/'previous'


def rewrite(source, previous, monkeypatch, mutate):
    review=json.loads((source/'pilot20_boundary_review.json').read_text(encoding='utf-8'))
    with (source/'pilot20_boundary_review.csv').open(encoding='utf-8-sig',newline='') as stream:
        rows=list(csv.DictReader(stream))
    mutate(review,rows)
    (source/'pilot20_boundary_review.json').write_text(json.dumps(review,ensure_ascii=False),encoding='utf-8')
    with (source/'pilot20_boundary_review.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    rules=copy.deepcopy(prepare.RULES)
    for name,key in prepare.SOURCE_FILES.items():
        rules[key]=prepare.digest(source/name)
    monkeypatch.setattr(prepare,'RULES',rules)


def test_source_hashes_are_checked_before_import(source):
    review,previous=source
    with (review/'pilot20_boundary_review.json').open('ab') as stream: stream.write(b' ')
    with pytest.raises(ValueError,match='source hash'):
        prepare.import_stress_review(review,previous)


def test_independent_reference_hash_checked(source):
    review,previous=source
    with (previous/'blind_50_reference.jsonl').open('ab') as stream:stream.write(b' ')
    with pytest.raises(ValueError,match='reference hash'):
        prepare.import_stress_review(review,previous)


@pytest.mark.parametrize('case,message',[
    ('status','AI-not-human'),('csv_count','IDs/count'),('duplicate','Duplicate'),('index','index'),
    ('source_title','source differs'),('baseline','baseline differs'),('csv_basic','basic review'),
    ('csv_spans','entity views'),('invalid_span','proposal span'),('order','proposal span'),('label','proposal span')])
def test_import_rejects_semantic_and_view_drift(source,monkeypatch,case,message):
    review,previous=source
    def mutate(value,rows):
        item=value['items'][0]
        if case=='status': value['status']='human_reviewed'
        elif case=='csv_count':rows.pop()
        elif case=='duplicate':value['items'][1]['publicationId']=item['publicationId']
        elif case=='index':item['blind_index']=51
        elif case=='source_title':item['title']+='tampered'
        elif case=='baseline':item['current_draft_entities']=[]
        elif case=='csv_basic':rows[0]['title']+='tampered'
        elif case=='csv_spans':rows[0]['proposed_entities']='tampered'
        else:
            if case=='invalid_span':item['proposed_entities'][0]['end']=999
            elif case=='order':item['proposed_entities'].reverse()
            elif case=='label':item['proposed_entities'][0]['label']='DOMAIN'
            rows[0]['proposed_entities']='; '.join(f"{e['label']}[{e['start']},{e['end']}): {e['text']} ({e['confidence']})" for e in item['proposed_entities'])
    rewrite(review,previous,monkeypatch,mutate)
    with pytest.raises(ValueError,match=message):prepare.import_stress_review(review,previous)


def test_case_set_is_policy_bound(source,monkeypatch):
    review,previous=source
    rules=copy.deepcopy(prepare.RULES);rules['case_decisions'].pop();monkeypatch.setattr(prepare,'RULES',rules)
    with pytest.raises(ValueError,match='case set'):prepare.import_stress_review(review,previous)


def test_migration_refuses_human_progress_and_invalid_decisions(source):
    old=contract.read_jsonl(source[1]/'pilot_200.jsonl')[0]
    old['entity_review']['status']='reviewed'
    with pytest.raises(ValueError,match='reviewed progress'):prepare.convert_record(old,'a'*64)
    old['entity_review']['status']='draft';old['notes']='actual edit'
    with pytest.raises(ValueError,match='Human edits'):prepare.convert_record(old,'a'*64)
    old['notes']='';row=prepare.convert_record(old,'a'*64)
    item={'proposed_entities':[{'start':0,'end':1,'text':row['text'][0],'label':'METHOD'}],'boundary_review':'fixture'}
    with pytest.raises(ValueError,match='forms'):prepare.apply_case_decision(row,item,{'forms':[]})
    item['proposed_entities'][0]['text']='wrong'
    with pytest.raises(ValueError,match='Invalid adopted'):prepare.apply_case_decision(row,item,{'forms':['single']})


def test_new_provenance_semantics_fail_closed(source):
    row=prepare.convert_record(contract.read_jsonl(source[1]/'pilot_200.jsonl')[0],'a'*64)
    row['boundaryRulesSha256']='0'*64
    assert not contract.validate_records([row])['valid']
    row['boundaryRulesSha256']=contract.RULES_SHA256
    row['initialDraftProvenance']['kind']='ai_rule_stress_test'
    assert not contract.validate_records([row])['valid']
    row['initialDraftProvenance']['aiReviewSha256']='b'*64
    assert not contract.validate_records([row])['valid']


def test_main_and_entrypoint_generate_isolated_packages(source,tmp_path,monkeypatch):
    review,previous=source
    destination=tmp_path/'generated'
    monkeypatch.setattr(sys,'argv',['prepare_revision_v3.py','--review-dir',str(review),'--previous-data',str(previous),'--output',str(destination)])
    runpy.run_path(str(prepare.ROOT/'scripts/prepare_revision_v3.py'),run_name='__main__')
    assert json.loads((destination/'summary.json').read_text(encoding='utf-8'))['adopted_candidates']['entity_counts']=={'METHOD':23,'TASK':21,'DATASET':1}
    with pytest.raises(FileExistsError):prepare.main()
    monkeypatch.setattr(sys,'argv',['prepare_revision_v3.py','--review-dir',str(review),'--previous-data',str(previous),'--output',str(tmp_path/'invalid')])
    monkeypatch.setattr(prepare,'apply_case_decision',lambda original,*args:original)
    monkeypatch.setattr(prepare,'validate_records',lambda *a,**k:{'valid':False})
    with pytest.raises(ValueError):prepare.main()
