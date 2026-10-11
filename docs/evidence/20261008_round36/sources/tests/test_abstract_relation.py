"""One runnable partial-label/source-role/diagnostic check; no model fitting or test-text access."""
import copy
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import course_weak as c
from course_abstract_relation import load_inputs,revise,read
from train_abstract_relation import diagnose

def test_partial_relation_contract_keeps_unknown_masked_and_attributes_endpoint_errors():
    config,data=load_inputs(ROOT/'kg_datasets/dblp/course_abstract_relation_inputs_20261008_36')
    assert len(data['train']['relation'])==195 and len(data['dev']['relation'])==242
    assert sum(p['label']=='NO_RELATION' for p in data['train']['relation'])==7 and sum(p['label']=='NO_RELATION' for p in data['dev']['relation'])==30
    assert len(data['dev']['full_relation'])==5 and not config['automaticPromotionAllowed']
    assert all(p['label']!='UNRESOLVED' for split in data.values() for p in split['relation'])
    source=ROOT/'kg_datasets/dblp/course_abstract_dev_reviewed_20261008_35';refs=c.read_jsonl(source/'references.jsonl');receipts=c.read_jsonl(source/'reviewed_receipts.jsonl')
    decision=next(d for d in read(ROOT/'annotations/course_v4/abstract_relation_decisions_20261008_36.json')['documents'] if d['split']=='dev' and d['arxivId']=='2411.06463')
    revised=revise(receipts[1]['annotation'],refs[1],decision,config)
    assert revised['relations'][0]['label']=='NO_RELATION' and any(p['label']=='UNRESOLVED' for p in revised['relations'])
    invalid=copy.deepcopy(decision);invalid['groups'][0].pop('negativeBasis')
    with pytest.raises(ValueError):revise(receipts[1]['annotation'],refs[1],invalid,config)
    row=next(p for p in data['dev']['relation'] if p['label']=='USED_FOR');doc=next(d for d in data['dev']['ner'] if d['sampleId']==row['sampleId'])
    entities=[row['head'],row['tail']]
    assert diagnose(doc,entities,[row],[row])==[]
    assert diagnose(doc,[],[row],[])[0]['primaryCause']=='missing'
    assert diagnose(doc,entities,[row],[row|{'label':'NO_RELATION'}])[0]['primaryCause']=='RE_decision'
    changed=copy.deepcopy(entities);changed[0]['label']='DATASET'
    assert diagnose(doc,changed,[row],[])[0]['primaryCause']=='type'
