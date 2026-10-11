"""One check for source identity, literal evidence, unknowns and output preservation."""
import hashlib
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import prepare_supplementary_dev as preparation


def test_supplementary_development_contract_and_labels():
    assert len(preparation.locked()['seeds'])==8
    text='Alpha performs tagging. Bench is a named benchmark.'
    ref={'sampleId':'sample-'+'a'*20,'arxivId':'9999.12345','text':text,'textSha256':hashlib.sha256(text.encode()).hexdigest()}
    decision={'arxivId':ref['arxivId'],'textSha256':ref['textSha256'],'mentions':{'METHOD':['Alpha'],'TASK':['tagging'],'DATASET':['Bench']},'groups':[{'heads':['e1'],'tails':['e2'],'label':'USED_FOR','supportExcerpt':'Alpha performs tagging.','reason':'Explicit performer/task, not benchmark evaluation.'}]}
    result=preparation.compile_decision(decision,ref)
    assert [r['label'] for r in result['relations']]==['USED_FOR','UNRESOLVED'] and result['relationStatus']=='unresolved'
    decision['groups'][0]['label']='NO_RELATION'
    with pytest.raises(ValueError,match='explicit contrast'): preparation.compile_decision(decision,ref)
    seed=preparation.locked()['seeds'][0]
    with pytest.raises(ValueError): preparation.reject_identity_overlap(preparation.locked()['seeds'],[],[seed | {'publicationId':'arxiv:'+seed['arxivId']}])
    with pytest.raises(FileExistsError): preparation.checked_new(Path(__file__).parent.resolve())
