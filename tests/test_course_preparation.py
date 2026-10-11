import copy
import csv
import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import course_weak as c
import prepare_course_weak as p
import import_course_ai as importer
from test_course_weak import corpus_row,metadata,reviewed_receipt


@pytest.fixture
def source_root(tmp_path):
    root=tmp_path/'source'
    corpus=[corpus_row(str(i),f'BERT for Task {i}',group=f'old{i}') for i in range(120)]
    base=root/'kg_datasets/dblp'
    (base/'ner_v1').mkdir(parents=True)
    (base/'processed_ai').mkdir()
    (base/'ner_v3_1/near_duplicate_review').mkdir(parents=True)
    c.write_jsonl(base/'ner_v1/corpus_manifest.jsonl',corpus)
    c.write_jsonl(base/'ner_v1/pilot_200.jsonl',corpus[:3])
    fields=['publicationId:ID(Publication)','title','doi','year:int','type']
    with (base/'processed_ai/publications.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        writer.writerows({'publicationId:ID(Publication)':r['publicationId'],'title':r['text'],
                         'doi':r['doi'],'year:int':r['year'],'type':r['type']} for r in corpus)
    with (base/'ner_v3_1/near_duplicate_review/near_duplicate_pairs.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['leftId','rightId']);writer.writeheader();writer.writerow({'leftId':'0','rightId':'3'})
    legacy=[]
    for r in corpus[:3]:
        legacy.append(r|{'entities':[{'start':0,'end':4,'text':'BERT','label':'METHOD','origin':'ai_suggestion','mentionForm':'single'}],'notes':'AI fixture only'})
    c.write_jsonl(base/'ner_v3_1/pilot20_ai_candidates.jsonl',legacy)
    for name in ('docs/course_v4_ai_prompt.md','scripts/course_weak.py','scripts/prepare_course_weak.py'):
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(c.ROOT/name,target)
    return root


@pytest.fixture
def prepared(source_root,tmp_path):
    folder=tmp_path/'prepared'
    p.prepare(source_root,folder,counts={'train':10,'dev':2,'test':2},seed=42)
    return folder


def complete_empty_response(reference):
    return {'sampleId':reference['sampleId'],'textSha256':reference['textSha256'],'reviewOfSha256':None,
            'entityStatus':'complete','entityReason':'','entities':[],'groupMentions':[],
            'relationStatus':'complete','relationReason':'','relations':[],'notes':'Synthetic test, not real annotations.'}


def test_preparation_preserves_sources_and_seals_real_outputs(source_root,prepared):
    manifest=json.loads((prepared/'manifest.json').read_text(encoding='utf-8'))
    p.assert_input_hashes(source_root,manifest['inputSha256'])
    refs=p.verify_dataset(prepared)
    assert len(refs)==14
    assert {r['publicationId'] for r in refs if r['split']=='train'} >= {'0','1','2'}
    jobs=c.read_jsonl(prepared/'jobs/generation/batch-0001.jsonl')
    assert all(set(job)=={'sampleId','text','textSha256'} for job in jobs)
    assert all(not c.eligible_tasks(receipt,receipt['reference'])['ner'] for receipt in c.read_jsonl(prepared/'legacy/generation_receipts.jsonl'))
    summary=json.loads((prepared/'summary.json').read_text(encoding='utf-8'))
    assert summary['pendingGenerationJobs']==14 and not summary['trainingStarted']


def test_preparation_refuses_overwrite(source_root,prepared):
    with pytest.raises(FileExistsError):p.prepare(source_root,prepared)


@pytest.mark.parametrize('target',['references.jsonl','ai_prompt.md','response_schema.json'])
def test_changed_prepared_artifact_rejected(prepared,target):
    (prepared/target).write_text('tampered',encoding='utf-8')
    with pytest.raises(ValueError):p.verify_dataset(prepared)


def test_changed_original_input_is_rejected(source_root,prepared):
    manifest=json.loads((prepared/'manifest.json').read_text(encoding='utf-8'))
    (source_root/'kg_datasets/dblp/ner_v1/pilot_200.jsonl').write_text('changed',encoding='utf-8')
    with pytest.raises(ValueError):p.assert_input_hashes(source_root,manifest['inputSha256'])


def test_legacy_dictionary_cannot_be_called_ai(source_root):
    row=c.read_jsonl(source_root/'kg_datasets/dblp/ner_v3_1/pilot20_ai_candidates.jsonl')[0]
    row['entities'][0]['origin']='draft_dictionary_v3'
    ref=c.make_reference(row,'g','train','a'*64)
    with pytest.raises(ValueError):p.legacy_ai_response(row,ref)
    row['text']='changed'
    with pytest.raises(ValueError):p.legacy_ai_response(row,ref)


def test_generation_and_bound_review_import_are_distinct(prepared,tmp_path):
    reference=p.verify_dataset(prepared)[0]
    response=complete_empty_response(reference)
    first_file=tmp_path/'first.jsonl';c.write_jsonl(first_file,[response])
    first_output=tmp_path/'first_output'
    first=importer.import_results(prepared,first_file,first_output,provider='synthetic_test',model='not_a_real_model')
    assert first['nerEligibleDocuments']==0
    old=c.read_jsonl(first_output/'receipts.jsonl')[0]
    response['reviewOfSha256']=old['contentSha256']
    review_file=tmp_path/'review.jsonl';c.write_jsonl(review_file,[response])
    review_output=tmp_path/'review_output'
    result=importer.import_results(prepared,review_file,review_output,provider='synthetic_test',model='not_a_real_model',previous=first_output/'receipts.jsonl')
    assert result['nerEligibleDocuments']==1 and result['relationEligibleDocuments']==1
    assert not result['nerTrainingReady'] and not result['humanGoldAvailable']
    receipts=c.read_jsonl(review_output/'receipts.jsonl')
    assert c.validate_receipt(receipts[0],reference)==[]


def test_import_rejects_duplicate_unknown_and_invalid_outputs(prepared,tmp_path):
    reference=p.verify_dataset(prepared)[0]
    response=complete_empty_response(reference)
    for index,rows in enumerate(([response,response],[response|{'sampleId':'sample-'+'0'*20}],
                                [response|{'entityStatus':'unresolved','entityReason':''}])):
        source=tmp_path/f'bad{index}.jsonl';c.write_jsonl(source,rows)
        with pytest.raises(ValueError):importer.import_results(prepared,source,tmp_path/f'bad_output{index}',provider='test',model='test')
        assert not (tmp_path/f'bad_output{index}').exists()


def test_import_refuses_empty_input_and_overwrite(prepared,tmp_path):
    source=tmp_path/'empty.jsonl';c.write_jsonl(source,[])
    with pytest.raises(ValueError):importer.import_results(prepared,source,tmp_path/'none',provider='test',model='test')
    output=tmp_path/'exists';output.mkdir()
    with pytest.raises(FileExistsError):importer.import_results(prepared,source,output,provider='test',model='test')


def test_training_readiness_requires_each_split_and_label():
    report=importer.assess_readiness([],[])
    assert not report['nerTrainingReady'] and not report['relationTrainingReady']
    assert report['evaluationTarget']==c.CONFIG['evaluationTarget']


@pytest.mark.parametrize('case',['duplicate_csv','corpus_text','historical_text','input_race'])
def test_corrupt_or_changing_inputs_never_generate_output(source_root,tmp_path,monkeypatch,case):
    if case=='duplicate_csv':
        path=source_root/'kg_datasets/dblp/processed_ai/publications.csv'
        lines=path.read_text(encoding='utf-8').splitlines()
        path.write_text('\n'.join(lines+[lines[1]])+'\n',encoding='utf-8')
    elif case=='corpus_text':
        path=source_root/'kg_datasets/dblp/ner_v1/corpus_manifest.jsonl'
        rows=c.read_jsonl(path);rows[0]['text']='wrong';c.write_jsonl(path,rows)
    elif case=='historical_text':
        path=source_root/'kg_datasets/dblp/ner_v1/pilot_200.jsonl'
        rows=c.read_jsonl(path);rows[0]['text']='wrong';c.write_jsonl(path,rows)
    else:
        target=source_root/'kg_datasets/dblp/processed_ai/publications.csv'
        original=c.file_sha256;calls=0
        def changed(path):
            nonlocal calls
            if path==target:
                calls+=1
                if calls>1:return '0'*64
            return original(path)
        monkeypatch.setattr(c,'file_sha256',changed)
    with pytest.raises(ValueError):p.prepare(source_root,tmp_path/'must_not_exist',counts={'train':10,'dev':2,'test':2},seed=42)
    assert not (tmp_path/'must_not_exist').exists()


def test_legacy_group_conversion_preserves_original_span(source_root):
    row=c.read_jsonl(source_root/'kg_datasets/dblp/ner_v3_1/pilot20_ai_candidates.jsonl')[0]
    row['entities'][0]['mentionForm']='coordinated'
    ref=c.make_reference(row,'g','train','a'*64)
    converted=p.legacy_ai_response(row,ref)
    assert converted['entities']==[] and converted['groupMentions'][0]['text']=='BERT'
    row['entities'][0]['end']=1000
    with pytest.raises(ValueError):p.legacy_ai_response(row,ref)


@pytest.mark.parametrize('case',['missing_required','traversal','contract_drift','duplicate_reference'])
def test_manifest_must_bind_safe_complete_contract(prepared,case):
    path=prepared/'manifest.json';manifest=json.loads(path.read_text(encoding='utf-8'))
    if case=='missing_required':del manifest['filesSha256']['references.jsonl']
    elif case=='traversal':manifest['filesSha256']['../outside']='0'*64
    elif case=='contract_drift':manifest['schemaSha256']='0'*64
    else:
        references=c.read_jsonl(prepared/'references.jsonl');references[1]=references[0]
        c.write_jsonl(prepared/'references.jsonl',references)
        manifest['filesSha256']['references.jsonl']=c.file_sha256(prepared/'references.jsonl')
    c.write_json(path,manifest)
    with pytest.raises(ValueError):p.verify_dataset(prepared)


def test_readiness_reports_all_classes_but_is_not_semantic_certification():
    references,receipts=[],[]
    for split in ('train','dev','test'):
        row=corpus_row(split,'BERT for Sentiment Analysis on IMDb compared to RoBERTa.')
        ref=c.make_reference(row,split,split,'a'*64);references.append(ref)
        entities=[]
        for text,label in [('BERT','METHOD'),('Sentiment Analysis','TASK'),('IMDb','DATASET'),('RoBERTa','METHOD')]:
            start=ref['text'].index(text)
            entities.append({'entityId':f'e{len(entities)+1}','start':start,'end':start+len(text),'text':text,'label':label})
        evidence={'start':0,'end':len(ref['text']),'text':ref['text']}
        r=complete_empty_response(ref)
        r['entities']=entities
        r['relations']=[{'head':h,'tail':t,'label':label if h=='e1' else 'NO_RELATION','evidence':evidence,'reason':'Synthetic fixture only.'}
                        for (h,t),label in c.candidate_pairs(entities).items()]
        receipts.append(reviewed_receipt(ref,r))
    report=importer.assess_readiness(receipts,references)
    assert report['nerTrainingReady'] and report['relationTrainingReady']
    assert report['humanGoldAvailable'] is False and report['trainingStarted'] is False
    with pytest.raises(ValueError):importer.assess_readiness(receipts,references+[references[0]])
    with pytest.raises(ValueError):importer.assess_readiness(receipts+[receipts[0]],references)
    bad=copy.deepcopy(receipts);bad[0]['labelSource']='human'
    with pytest.raises(ValueError):importer.assess_readiness(bad,references)
    cross=copy.deepcopy(references);cross[1]['groupId']=cross[0]['groupId']
    with pytest.raises(ValueError):importer.assess_readiness([],cross)


def test_assembly_saves_task_specific_inputs_and_refuses_duplicate_samples(prepared,tmp_path):
    ref=p.verify_dataset(prepared)[0]
    receipt=reviewed_receipt(ref,complete_empty_response(ref))
    source=tmp_path/'actual_receipts.jsonl';c.write_jsonl(source,[receipt])
    output=tmp_path/'assembled';report=importer.assemble(prepared,[source],output)
    assert report['nerEligibleDocuments']==1 and not report['nerTrainingReady']
    assert len(c.read_jsonl(output/f"ner_inputs_{ref['split']}.jsonl"))==1
    pending=c.read_jsonl(output/'pending_generation.jsonl')
    assert len(pending)==report['pendingGenerationDocuments']==13
    assert {row['sampleId'] for row in pending}=={row['sampleId'] for row in p.verify_dataset(prepared)}-{ref['sampleId']}
    assert all(set(row)=={'sampleId','text','textSha256'} for row in pending)
    with pytest.raises(FileExistsError):importer.assemble(prepared,[source],output)
    with pytest.raises(ValueError):importer.assemble(prepared,[source,source],tmp_path/'duplicate_export')


@pytest.mark.parametrize('case',['duplicate_previous','missing_previous','partial_review','input_race'])
def test_review_import_is_exact_and_inputs_cannot_change(prepared,tmp_path,monkeypatch,case):
    refs=p.verify_dataset(prepared)[:2]
    first=[c.make_receipt(complete_empty_response(ref),ref,metadata()) for ref in refs]
    response=complete_empty_response(refs[0]);response['reviewOfSha256']=first[0]['contentSha256']
    if case=='duplicate_previous':first.append(first[0])
    elif case=='missing_previous':first=first[1:]
    elif case=='input_race':first=first[:1]
    previous=tmp_path/'first.jsonl';c.write_jsonl(previous,first)
    source=tmp_path/'review.jsonl';c.write_jsonl(source,[response])
    if case=='input_race':
        original=c.file_sha256;calls=0
        def changed(path):
            nonlocal calls
            if path==source:
                calls+=1
                if calls>1:return '0'*64
            return original(path)
        monkeypatch.setattr(c,'file_sha256',changed)
    with pytest.raises(ValueError):importer.import_results(prepared,source,tmp_path/'invalid_review',provider='test',model='test',previous=previous)
    assert not (tmp_path/'invalid_review').exists()


def test_assembly_detects_changing_input(prepared,tmp_path,monkeypatch):
    ref=p.verify_dataset(prepared)[0]
    source=tmp_path/'receipts.jsonl';c.write_jsonl(source,[reviewed_receipt(ref,complete_empty_response(ref))])
    original=c.file_sha256;calls=0
    def changed(path):
        nonlocal calls
        if path.resolve()==source.resolve():
            calls+=1
            if calls>1:return '0'*64
        return original(path)
    monkeypatch.setattr(c,'file_sha256',changed)
    with pytest.raises(ValueError):importer.assemble(prepared,[source],tmp_path/'not_generated')


def test_cli_verify_import_and_assemble(prepared,tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(sys,'argv',['prepare_course_weak','--verify-only',str(prepared)])
    p.main();assert json.loads(capsys.readouterr().out)['documents']==14
    ref=p.verify_dataset(prepared)[0]
    source=tmp_path/'response.jsonl';c.write_jsonl(source,[complete_empty_response(ref)])
    output=tmp_path/'cli_import'
    monkeypatch.setattr(sys,'argv',['import_course_ai','import','--dataset',str(prepared),'--responses',str(source),'--output',str(output),'--provider','synthetic_test','--model','not_a_real_model'])
    importer.main();assert json.loads(capsys.readouterr().out)['modelCallExecutedByImporter'] is False
    monkeypatch.setattr(sys,'argv',['import_course_ai','assemble','--dataset',str(prepared),'--receipts',str(output/'receipts.jsonl'),'--output',str(tmp_path/'cli_assemble')])
    importer.main();assert json.loads(capsys.readouterr().out)['nerTrainingReady'] is False


def test_review_import_detects_previous_changed_during_initial_read(prepared,tmp_path,monkeypatch):
    ref=p.verify_dataset(prepared)[0]
    first=c.make_receipt(complete_empty_response(ref),ref,metadata())
    previous=tmp_path/'first.jsonl';c.write_jsonl(previous,[first])
    response=complete_empty_response(ref)|{'reviewOfSha256':first['contentSha256']}
    source=tmp_path/'review.jsonl';c.write_jsonl(source,[response])
    original=c.read_jsonl
    def changed(path):
        rows=original(path)
        if path==previous:path.write_text(path.read_text(encoding='utf-8')+'\n',encoding='utf-8')
        return rows
    monkeypatch.setattr(c,'read_jsonl',changed)
    with pytest.raises(ValueError,match='changed'):
        importer.import_results(prepared,source,tmp_path/'must_not_exist',provider='synthetic_test',model='not_a_real_model',previous=previous)
    assert not (tmp_path/'must_not_exist').exists()
