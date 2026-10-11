import copy
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import course_weak as c


def corpus_row(pid, text, doi='', group=None):
    return {'publicationId':pid, 'text':text, 'doi':doi, 'groupId':group or pid,
            'year':2025, 'type':'article', 'topics':['hidden-topic'],
            'ambiguityFlags':['hidden-answer-hint']}


@pytest.fixture
def reference():
    return c.make_reference(corpus_row('test/1', 'BERT for Sentiment Analysis on IMDb'), 'g1', 'train', 'a'*64)


@pytest.fixture
def response(reference):
    text=reference['text']
    entities=[]
    for name,label in [('BERT','METHOD'),('Sentiment Analysis','TASK'),('IMDb','DATASET')]:
        start=text.index(name)
        entities.append({'entityId':f'e{len(entities)+1}','start':start,'end':start+len(name),'text':name,'label':label})
    evidence={'start':0,'end':len(text),'text':text}
    return {'sampleId':reference['sampleId'],'textSha256':reference['textSha256'],
            'reviewOfSha256':None,'entityStatus':'complete','entityReason':'',
            'entities':entities,'groupMentions':[], 'relationStatus':'unresolved',
            'relationReason':'Title does not establish evaluation on IMDb.',
            'relations':[{'head':'e1','tail':'e2','label':'USED_FOR','evidence':evidence,'reason':'Explicit task phrase.'},
                         {'head':'e1','tail':'e3','label':'UNRESOLVED','evidence':None,'reason':'Mention does not establish evaluation.'}],
            'notes':'Synthetic unit test only.'}


def metadata():
    return {'provider':'synthetic_test','model':'not_a_real_model','promptSha256':'b'*64,
            'sourceArtifactSha256':'c'*64,'createdAt':'2026-10-05T00:00:00+00:00'}


def reviewed_receipt(reference, response):
    first=c.make_receipt(response,reference,metadata())
    checked=copy.deepcopy(response)
    checked['reviewOfSha256']=first['contentSha256']
    return c.make_receipt(checked,reference,metadata(),previous=first)


def test_grouping_is_transitive_and_does_not_merge_identities():
    rows=[corpus_row('a','Same, title.','10/x'),corpus_row('b','Same title','10/y'),
          corpus_row('c','Different title','10/y'),corpus_row('d','Unrelated')]
    groups=c.group_corpus(rows,[('c','d')])
    assert len(groups)==4 and len(set(groups.values()))==1
    assert groups==c.group_corpus(list(reversed(rows)),[('d','c')])


@pytest.mark.parametrize('rows,pairs', [([corpus_row('a','x'),corpus_row('a','y')],[]),
                                       ([corpus_row('a','x')],[('a','missing')])])
def test_bad_group_inputs_rejected(rows,pairs):
    with pytest.raises(ValueError):c.group_corpus(rows,pairs)


def test_train_exposure_propagates_to_group_and_split_is_order_invariant():
    rows=[corpus_row(str(i),f'Title {i}') for i in range(100)]
    groups=c.group_corpus(rows,[('0','1')])
    splits=c.assign_splits(rows,groups,{'0'},seed=42)
    assert splits['0']==splits['1']=='train'
    assert splits==c.assign_splits(list(reversed(rows)),groups,{'0'},seed=42)
    for group in set(groups.values()):
        assert len({splits[pid] for pid in groups if groups[pid]==group})==1
    with pytest.raises(ValueError):c.assign_splits(rows,groups,{'missing'})


def test_selection_preserves_all_exposed_and_never_fills_shortage():
    rows=[corpus_row(str(i),f'Title {i}') for i in range(8)]
    splits={str(i):'train' if i<4 else 'dev' if i<6 else 'test' for i in range(8)}
    selected=c.select_cohort(rows,splits,{'0','1'},counts={'train':3,'dev':1,'test':1},seed=42)
    assert {'0','1'} <= {r['publicationId'] for r in selected}
    assert selected==c.select_cohort(list(reversed(rows)),splits,{'0','1'},counts={'train':3,'dev':1,'test':1},seed=42)
    with pytest.raises(ValueError):c.select_cohort(rows,splits,{'0','1'},counts={'train':1,'dev':1,'test':1})
    with pytest.raises(ValueError):c.select_cohort(rows,splits,set(),counts={'train':5,'dev':1,'test':1})


def test_model_payload_excludes_hints_and_ids(reference):
    payload=c.model_payload(reference)
    assert set(payload)=={'sampleId','text','textSha256'}
    assert 'test/1' not in json.dumps(payload) and 'hidden' not in json.dumps(payload)


def test_response_requires_complete_relation_scope_and_separate_status(reference,response):
    assert c.validate_response(response,reference)==[]
    broken=copy.deepcopy(response);broken['relations'].pop()
    assert c.validate_response(broken,reference)
    broken=copy.deepcopy(response);broken['relationStatus']='complete';broken['relationReason']=''
    assert c.validate_response(broken,reference)
    broken=copy.deepcopy(response);broken['entityStatus']='unresolved';broken['entityReason']=''
    assert c.validate_response(broken,reference)


@pytest.mark.parametrize('mutation', ['offset','text','overlap','label','id','duplicate_pair','wrong_pair','evidence','unknown_field','human_claim','hash','reason','sample'])
def test_invalid_ai_output_fails_closed(reference,response,mutation):
    r=copy.deepcopy(response)
    if mutation=='offset':r['entities'][0]['start']=-1
    elif mutation=='text':r['entities'][0]['text']='not BERT'
    elif mutation=='overlap':r['entities'][1]['start']=0
    elif mutation=='label':r['entities'][0]['label']='DOMAIN'
    elif mutation=='id':r['entities'][0]['entityId']='e9'
    elif mutation=='duplicate_pair':r['relations'].append(copy.deepcopy(r['relations'][0]))
    elif mutation=='wrong_pair':r['relations'][0]['head']='e2'
    elif mutation=='evidence':r['relations'][0]['evidence']={'start':0,'end':4,'text':'BERT'}
    elif mutation=='unknown_field':r['topics']=['hidden']
    elif mutation=='human_claim':r['reviewer']='Human'
    elif mutation=='hash':r['textSha256']='0'*64
    elif mutation=='reason':r['relations'][1]['reason']=''
    elif mutation=='sample':r['sampleId']='sample-0000000000000000'
    assert c.validate_response(r,reference)


def test_receipt_review_hash_detects_all_post_review_content_changes(reference,response):
    receipt=reviewed_receipt(reference,response)
    assert c.validate_receipt(receipt,reference)==[]
    assert c.eligible_tasks(receipt,reference)=={'ner':True,'relation':False}
    for key in ('notes','entityReason','relationReason'):
        changed=copy.deepcopy(receipt);changed['annotation'][key]+=' changed'
        assert c.validate_receipt(changed,reference)
    changed=copy.deepcopy(receipt);changed['annotation']['entities'][0]['label']='TASK'
    assert c.validate_receipt(changed,reference)
    changed=copy.deepcopy(receipt);changed['labelSource']='human'
    assert c.validate_receipt(changed,reference)
    changed=copy.deepcopy(receipt);changed['reference']['split']='test'
    assert c.validate_receipt(changed,reference)


def test_generation_is_not_reviewed_and_review_must_bind_previous(reference,response):
    receipt=c.make_receipt(response,reference,metadata())
    assert c.eligible_tasks(receipt,reference)=={'ner':False,'relation':False}
    with pytest.raises(ValueError):c.make_receipt(response,reference,metadata(),previous=receipt)
    changed=copy.deepcopy(response);changed['reviewOfSha256']='0'*64
    with pytest.raises(ValueError):c.make_receipt(changed,reference,metadata(),previous=receipt)


@pytest.mark.parametrize('key,value',[('provider',''),('model',''),('createdAt','2026-10-05'),('sourceArtifactSha256','broken')])
def test_bad_provenance_is_rejected(reference,response,key,value):
    m=metadata();m[key]=value
    with pytest.raises(ValueError):c.make_receipt(response,reference,m)


def test_group_mentions_quarantine_without_turning_into_negative(reference,response):
    r=copy.deepcopy(response)
    group=r['entities'].pop(0)
    r['groupMentions']=[{k:v for k,v in group.items() if k!='entityId'}|{'groupId':'g1'}]
    for i,e in enumerate(r['entities'],1):e['entityId']=f'e{i}'
    r['relations']=[];r['relationStatus']='complete';r['relationReason']=''
    receipt=reviewed_receipt(reference,r)
    assert c.validate_receipt(receipt,reference)==[]
    assert c.eligible_tasks(receipt,reference)=={'ner':False,'relation':False}


def test_empty_generation_is_not_a_true_negative(reference,response):
    r=copy.deepcopy(response)
    r.update(entities=[],relations=[],relationStatus='complete',relationReason='')
    receipt=c.make_receipt(r,reference,metadata())
    assert not c.eligible_tasks(receipt,reference)['ner']
    assert c.eligible_tasks(reviewed_receipt(reference,r),reference)['ner']


def test_bio_alignment_uses_unicode_and_rejects_partial_or_truncated_spans():
    text='😀 BERT works'
    entity={'start':2,'end':6,'text':'BERT','label':'METHOD'}
    assert c.align_bio([(0,0),(0,1),(2,4),(4,6),(7,12),(0,0)],[entity],text)==[-100,0,1,2,0,-100]
    with pytest.raises(ValueError):c.align_bio([(2,5)],[entity],text)
    with pytest.raises(ValueError):c.align_bio([(1,6)],[entity],text)


def test_metrics_are_strict_span_agreement_not_model_accuracy():
    truth=[('s1',0,4,'METHOD'),('s1',9,12,'TASK')]
    prediction=[('s1',0,4,'METHOD'),('s1',9,11,'TASK')]
    report=c.entity_agreement(prediction,truth)
    assert report['precision']==report['recall']==report['f1']==0.5
    assert report['evaluationTarget']==c.CONFIG['evaluationTarget']
    assert c.entity_agreement([],[])['f1'] is None


@pytest.mark.parametrize('mutation',['identity','snapshot','initial_hash','content_hash','generation_provenance','review_shape','review_hash','null_review_input','extra_field','invalid_annotation'])
def test_receipt_lineage_and_review_cannot_be_silently_rewritten(reference,response,mutation):
    receipt=reviewed_receipt(reference,response)
    if mutation=='identity':receipt['reference']['publicationId']='other'
    elif mutation=='snapshot':receipt['initialAnnotation']['notes']='rewritten history'
    elif mutation=='initial_hash':receipt['initialContentSha256']='0'*64
    elif mutation=='content_hash':receipt['contentSha256']='bad'
    elif mutation=='generation_provenance':receipt['generation']['model']=''
    elif mutation=='review_shape':receipt['review']={}
    elif mutation=='review_hash':receipt['review']['contentSha256']='0'*64
    elif mutation=='null_review_input':receipt['review']['inputContentSha256']=None
    elif mutation=='extra_field':receipt['human_reviewed']=True
    elif mutation=='invalid_annotation':receipt['annotation']=None
    assert c.validate_receipt(receipt,reference)
    assert not c.eligible_tasks(receipt,reference)['ner']


def test_bad_first_receipt_and_second_review_rejected(reference,response):
    bad=copy.deepcopy(response);bad['reviewOfSha256']='0'*64
    with pytest.raises(ValueError):c.make_receipt(bad,reference,metadata())
    first=c.make_receipt(response,reference,metadata())
    first['contentSha256']='0'*64
    with pytest.raises(ValueError):c.make_receipt(response,reference,metadata(),previous=first)
    first=c.make_receipt(response,reference,metadata())
    first['annotation']['reviewOfSha256']='0'*64
    first['contentSha256']=c.content_sha256(first['annotation'],reference)
    assert c.validate_receipt(first,reference)
    reviewed=reviewed_receipt(reference,response)
    r=copy.deepcopy(response);r['reviewOfSha256']=reviewed['contentSha256']
    with pytest.raises(ValueError):c.make_receipt(r,reference,metadata(),previous=reviewed)


@pytest.mark.parametrize('provenance',[None,{}, {'provider':'x','model':'x','promptSha256':None,'sourceArtifactSha256':'a'*64,'createdAt':'bad'}])
def test_metadata_shape_invalid(provenance):
    assert c.metadata_errors(provenance)


def test_legacy_unknown_prompt_is_explicit_and_not_reconstructed():
    m=metadata();m.update(provider='legacy_ai_artifact',promptSha256=None)
    assert not c.metadata_errors(m)


def test_reference_and_selection_reject_bad_contract_inputs():
    with pytest.raises(ValueError):c.make_reference(corpus_row('x','x'),'g','other','a'*64)
    with pytest.raises(ValueError):c.make_reference(corpus_row('x','x'),'g','train','broken')
    with pytest.raises(ValueError):c.select_cohort([corpus_row('x','x')],{'x':'test'},{'x'},counts={'train':1,'dev':0,'test':0})


@pytest.mark.parametrize('case',['reverse','overlap','no_evidence','wrong_type','bad_evidence_text','blank_reason','unresolved_entity','bad_group_id','entity_group_overlap'])
def test_remaining_span_and_scope_failures(reference,response,case):
    r=copy.deepcopy(response)
    if case=='reverse':r['entities'].reverse()
    elif case=='overlap':r['entities'][1].update(start=0,end=4,text='BERT')
    elif case=='no_evidence':r['relations'][0]['evidence']=None
    elif case=='wrong_type':r['relations'][0]['label']='EVALUATED_ON'
    elif case=='bad_evidence_text':r['relations'][0]['evidence']['text']='wrong'
    elif case=='blank_reason':r['relations'][0]['reason']=' '
    elif case=='unresolved_entity':r.update(entityStatus='unresolved',entityReason='Ambiguous',relationStatus='complete',relationReason='')
    elif case=='bad_group_id':r['groupMentions']=[{'groupId':'g2','start':0,'end':4,'text':'BERT','label':'METHOD'}]
    elif case=='entity_group_overlap':r['groupMentions']=[{'groupId':'g1','start':0,'end':4,'text':'BERT','label':'METHOD'}]
    assert c.validate_response(r,reference)


def test_bio_invalid_spans_order_offsets_and_gaps():
    with pytest.raises(ValueError):c.align_bio([(0,1)],[{'start':0,'end':1,'text':'b','label':'METHOD'}],'a')
    entities=[{'start':0,'end':2,'text':'ab','label':'METHOD'}, {'start':1,'end':2,'text':'b','label':'TASK'}]
    with pytest.raises(ValueError):c.align_bio([(0,2)],entities,'ab')
    with pytest.raises(ValueError):c.align_bio([(1,2),(0,1)],[],'ab')
    with pytest.raises(ValueError):c.align_bio([(0,1),(2,3)],[{'start':0,'end':3,'text':'abc','label':'METHOD'}],'abc')
    assert c.span_errors({'start':0.0,'end':1,'text':'a'},'a')


def test_schema_configuration_drift_fails_at_import(monkeypatch):
    original_loads=json.loads
    def drifted_loads(text,*args,**kwargs):
        value=original_loads(text,*args,**kwargs)
        if isinstance(value,dict) and value.get('version')=='course-v4-weak-1':
            value['entityLabels']=['OTHER']
        return value
    try:
        with monkeypatch.context() as patch:
            patch.setattr(json,'loads',drifted_loads)
            with pytest.raises(ValueError,match='disagree'):importlib.reload(c)
    finally:
        importlib.reload(c)
