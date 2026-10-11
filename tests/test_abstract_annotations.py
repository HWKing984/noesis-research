"""One runnable check for literal boundaries, unknown-pair policy and reviewed artifacts."""
import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import course_graph as g
import course_weak as c
from compile_abstract_annotations import annotate,mention_spans
from train_course_ner import decode_bio

def test_abstract_annotations_never_fill_unknown_pairs_or_split_compound_names():
    text='GLUE SuperGLUE MNIST Fashion-MNIST GPT GPT-3 algorithms--MAX-Flow https://example.com/GLUE'
    spans=mention_spans(text,{'DATASET':['GLUE','SuperGLUE','MNIST','Fashion-MNIST'],'METHOD':['GPT','GPT-3','MAX-Flow']})
    assert [e['text'] for e in spans]==['GLUE','SuperGLUE','MNIST','Fashion-MNIST','GPT','GPT-3','MAX-Flow']
    assert not mention_spans('PDE diffusion models',{'METHOD':['diffusion models']},['PDE diffusion models'])
    with pytest.raises(ValueError):mention_spans('GPT-3',{'METHOD':['GPT']})
    with pytest.raises(ValueError):mention_spans('CNN model',{'METHOD':['CNN model'],'TASK':['CNN']})
    folder=ROOT/'kg_datasets/dblp/course_abstract_train_reviewed_20261008_33'
    g.verified_files(folder)
    refs=c.read_jsonl(folder/'references.jsonl');receipts=c.read_jsonl(folder/'reviewed_receipts.jsonl');aligned=c.read_jsonl(folder/'token_alignment.jsonl')
    rows=c.read_jsonl(folder/'ner_train_candidates.jsonl')
    assert len(refs)==len(receipts)==len(aligned)==37 and len(rows)==29
    assert all(r['split']=='train' and r['textKind']=='abstract' for r in refs)
    for ref,receipt,encoded in zip(refs,receipts,aligned):
        assert not c.validate_receipt(receipt,ref) and encoded['eligibility']==c.eligible_tasks(receipt,ref)
        if encoded['strictAlignmentPassed']:
            tags=[0 if tuple(offset)==(0,0) else label for label,offset in zip(encoded['BIOLabels'],encoded['offsets'])]
            expected=[{k:e[k] for k in ('start','end','text','label')} for e in receipt['annotation']['entities']]
            assert decode_bio(tags,encoded['offsets'],ref['text'])=={'entities':expected,'invalidTransitions':0}
    ref=copy.deepcopy(refs[0]);ref['text']='CNN is evaluated on MNIST.';ref['textSha256']=hashlib.sha256(ref['text'].encode()).hexdigest()
    decision={'mentions':{'METHOD':['CNN'],'DATASET':['MNIST']}}
    assert annotate(decision,ref)['relations'][0]['label']=='UNRESOLVED'
    decision['positives']=[{'head':'CNN','tail':'MNIST','label':'EVALUATED_ON','evidence':ref['text']}]
    assert annotate(decision,ref)['relations'][0]['label']=='EVALUATED_ON'
    decision['positives'][0]['evidence']='Invented evidence'
    with pytest.raises(ValueError):annotate(decision,ref)
    summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    assert summary['relationCounts']=={'UNRESOLVED':1119,'EVALUATED_ON':11,'USED_FOR':6}
    assert summary['eligibleNEREntityCounts']['DATASET']==35 and not summary['trainingExecuted']
