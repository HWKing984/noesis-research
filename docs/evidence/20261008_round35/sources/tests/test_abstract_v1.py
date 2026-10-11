"""Small contract/source/partial-relation check; no model or held-out test inference."""
import copy
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import course_weak as c
from course_abstract_v1 import TRAIN,read
from train_abstract_ner import bind_row,load_inputs

def test_abstract_v1_binds_rows_to_review_and_never_converts_unknown_to_negative():
    folder=ROOT/'kg_datasets/dblp/course_abstract_v1_inputs_20261008_35';dev=ROOT/'kg_datasets/dblp/course_abstract_dev_reviewed_20261008_35'
    config,rows=load_inputs(folder,dev);summary=read(folder/'summary.json')
    assert {s:len(r) for s,r in rows.items()}=={'train':29,'dev':16}
    assert summary['entitySupport']['dev']['DATASET']==15 and summary['excludedNER']=={'train':8,'dev':3}
    assert not summary['relationTrainingReady'] and not summary['testConsumed']
    assert len(c.read_jsonl(folder/'relation_train.jsonl'))==17 and not c.read_jsonl(folder/'relation_dev.jsonl')
    assert all(r['label'] in ('USED_FOR','EVALUATED_ON') for r in c.read_jsonl(folder/'relation_train.jsonl'))
    assert not {r['groupId'] for r in rows['train']}&{r['groupId'] for r in rows['dev']}
    assert config['maxTokens']==512 and not config['promotionGates']['automaticPromotionAllowed']
    refs=c.read_jsonl(TRAIN/'references.jsonl');receipts=c.read_jsonl(TRAIN/'reviewed_receipts.jsonl');lookup={r['sampleId']:(r,a) for r,a in zip(refs,receipts)}
    row=copy.deepcopy(rows['train'][0]);ref,receipt=lookup[row['sampleId']]
    bind_row(row,ref,receipt);row['entities'][0]['label']='DATASET'
    with pytest.raises(ValueError):bind_row(row,ref,receipt)
