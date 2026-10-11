import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import course_weak as c
import compile_course_ai as compiler
from compile_course_ai import compile_decisions
from test_course_preparation import prepared,source_root
from test_course_weak import corpus_row,metadata


def example():
    reference=c.make_reference(corpus_row('sample','BERT for Classification'),'g','train','a'*64)
    decision={'sampleId':reference['sampleId'],'entityStatus':'complete','entityReason':'',
              'entities':[{'text':'BERT','label':'METHOD'},{'text':'Classification','label':'TASK'}],
              'groupMentions':[],'relationStatus':'complete','relationReason':'',
              'relations':[{'head':'e1','tail':'e2','label':'USED_FOR','reason':'Explicit for in the title.'}],
              'notes':'Synthetic test only.'}
    return reference,decision


def test_literal_ai_boundaries_compile_without_creating_new_labels():
    reference,decision=example()
    response=compile_decisions([decision],[reference])[0]
    assert response['entities'][0]['start']==0
    assert response['entities'][1]['start']==9
    assert response['relations'][0]['evidence']['text']==reference['text']
    assert not c.validate_response(response,reference)
    assert response['reviewOfSha256'] is None


@pytest.mark.parametrize('case',['missing_sample','duplicate_sample','invented_text','missing_relation','unknown_field','nonunique_literal'])
def test_compiler_never_invents_bounds_or_missing_decisions(case):
    reference,decision=example()
    decisions=[decision]
    if case=='missing_sample':decision['sampleId']='sample-'+'0'*20
    elif case=='duplicate_sample':decisions.append(copy.deepcopy(decision))
    elif case=='invented_text':decision['entities'][0]['text']='GPT'
    elif case=='missing_relation':decision['relations']=[]
    elif case=='unknown_field':decision['human_reviewed']=True
    elif case=='nonunique_literal':
        reference=c.make_reference(corpus_row('sample','BERT BERT for Classification'),'g','train','a'*64)
    with pytest.raises(ValueError):compile_decisions(decisions,[reference])


def test_review_binding_does_not_mean_the_compiler_executed_ai_review():
    reference,decision=example()
    response=compile_decisions([decision],[reference])[0]
    previous=c.make_receipt(response,reference,metadata())
    reviewed=compile_decisions([decision],[reference],previous=[previous])[0]
    assert reviewed['reviewOfSha256']==previous['contentSha256']


def test_repeated_surface_requires_explicit_occurrence():
    reference,decision=example()
    reference=c.make_reference(corpus_row('sample','BERT BERT for Classification'),'g','train','a'*64)
    decision['entities'][0]['occurrence']=2
    assert compile_decisions([decision],[reference])[0]['entities'][0]['start']==5
    decision['entities'][0]['occurrence']=3
    with pytest.raises(ValueError):compile_decisions([decision],[reference])


def artifact_inputs(prepared,tmp_path):
    reference=c.read_jsonl(prepared/'references.jsonl')[0]
    _,decision=example()
    decision['sampleId']=reference['sampleId']
    decision['entities'][1]['text']=reference['text'][9:]
    jobs=tmp_path/'jobs.jsonl';c.write_jsonl(jobs,[c.model_payload(reference)])
    source=tmp_path/'decisions.json'
    c.write_json(source,{'provider':'synthetic_test','model':'not_a_real_model','round':'generation','decisions':[decision]})
    return reference,jobs,source


def test_artifact_cli_generation_review_and_nonempty_relation_export(prepared,tmp_path,monkeypatch,capsys):
    import import_course_ai as importer
    reference,jobs,source=artifact_inputs(prepared,tmp_path)
    output=tmp_path/'compiled'
    monkeypatch.setattr(sys,'argv',['compile_course_ai','--dataset',str(prepared),'--jobs',str(jobs),'--decisions',str(source),'--output',str(output)])
    compiler.main()
    assert json.loads(capsys.readouterr().out)['modelCallExecutedByCompiler'] is False
    manifest=json.loads((output/'manifest.json').read_text(encoding='utf-8'))
    assert manifest['inputSha256'][str(source.resolve())]==c.file_sha256(output/'ai_decisions.json')
    first=tmp_path/'first'
    importer.import_results(prepared,output/'responses.jsonl',first,provider='synthetic_test',model='not_a_real_model')
    review_source=tmp_path/'review.json'
    c.write_json(review_source,json.loads(source.read_text(encoding='utf-8'))|{'round':'candidate_aware_ai_review'})
    reviewed=tmp_path/'reviewed'
    compiler.compile_artifact(prepared,jobs,review_source,reviewed,previous=first/'receipts.jsonl')
    imported=tmp_path/'imported'
    importer.import_results(prepared,reviewed/'responses.jsonl',imported,provider='synthetic_test',model='not_a_real_model',previous=first/'receipts.jsonl')
    pair=c.read_jsonl(imported/f"relation_inputs_{reference['split']}.jsonl")[0]
    assert pair['label']=='USED_FOR' and pair['labelSource']=='ai_pseudo'
    with pytest.raises(FileExistsError):compiler.compile_artifact(prepared,jobs,source,output)


def test_compiler_detects_jobs_changed_during_initial_read(prepared,tmp_path,monkeypatch):
    _,jobs,source=artifact_inputs(prepared,tmp_path)
    original=c.read_jsonl
    def changed(path):
        rows=original(path)
        if path==jobs:path.write_text(path.read_text(encoding='utf-8')+'\n',encoding='utf-8')
        return rows
    monkeypatch.setattr(c,'read_jsonl',changed)
    with pytest.raises(ValueError,match='changed'):compiler.compile_artifact(prepared,jobs,source,tmp_path/'must_not_exist')
    assert not (tmp_path/'must_not_exist').exists()
