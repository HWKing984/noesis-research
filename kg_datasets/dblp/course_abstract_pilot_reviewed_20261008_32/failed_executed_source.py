"""Bind explicit same-session AI self-review and strict token alignment to the abstract pilot."""
import argparse
import copy
import json
import os
from collections import Counter
from datetime import UTC,datetime
from pathlib import Path

import course_graph as g
import course_weak as c
from compile_course_ai import literal_span

def review(folder,judgments_path,output):
    if output.exists():raise FileExistsError('Preserve reviewed pilot')
    g.verified_files(folder)
    refs=c.read_jsonl(folder/'references.jsonl');initial=c.read_jsonl(folder/'generation_receipts.jsonl')
    judgments=json.loads(judgments_path.read_text(encoding='utf-8'))
    if [r['index'] for r in judgments['reviews']]!=list(range(len(refs))):raise ValueError('Review coverage incomplete or reordered')
    if judgments['independent'] is not False:raise ValueError('Cannot certify independent review')
    output.mkdir(parents=True)
    c.write_json(output/'review_prompt.json',{'instruction':'Check all explicit mentions and directed typed relations against original excerpt only. Verify maximal distinctive name boundaries, generic-word exclusions, duplicate surfaces and parent offsets. This is same-session self-review, not human gold.'})
    metadata={'provider':judgments['provider'],'model':judgments['model'],
        'promptSha256':c.file_sha256(output/'review_prompt.json'),'sourceArtifactSha256':c.file_sha256(judgments_path),'createdAt':datetime.now(UTC).isoformat()}
    receipts=[]
    for ref,prior,judgment in zip(refs,initial,judgments['reviews']):
        if c.validate_receipt(prior,ref):raise ValueError('Initial receipt invalid')
        if judgment['verdict'] not in ('confirm','revise') or not judgment['reason'].strip():raise ValueError('Invalid semantic review')
        response=copy.deepcopy(prior['annotation']);response['reviewOfSha256']=prior['contentSha256']
        if judgment['verdict']=='revise':
            response['entities']=[{'entityId':f'e{i}',**literal_span(e,ref['text'])} for i,e in enumerate(judgment['entities'],1)]
        elif 'entities' in judgment:raise ValueError('Confirm cannot silently revise boundaries')
        response['notes']+=' Self-review: '+judgment['reason']
        receipts.append(c.make_receipt(response,ref,metadata,previous=prior))
    c.write_jsonl(output/'reviewed_receipts.jsonl',receipts);c.write_jsonl(output/'references.jsonl',refs)
    # Reuse the existing strict BIO aligner; there is no training, inference or synthetic fallback.
    os.environ.setdefault('HF_HUB_OFFLINE','1')
    from transformers import BertTokenizerFast
    tokenizer=BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32',local_files_only=True,do_lower_case=True)
    preflight=[];training=[]
    for ref,receipt in zip(refs,receipts):
        encoded=tokenizer(ref['text'],return_offsets_mapping=True,add_special_tokens=True,truncation=False)
        offsets=encoded['offset_mapping'];entities=receipt['annotation']['entities']
        if len(offsets)>128:raise ValueError('Pilot over token limit: no silent truncation')
        labels=c.align_bio(offsets,entities,ref['text'])
        parent=ref['sourceOffset']
        positions=[{'entityId':e['entityId'],'start':parent['start']+e['start'],'end':parent['start']+e['end']} for e in entities]
        preflight.append({'sampleId':ref['sampleId'],'tokens':len(offsets),'parentEntityOffsets':positions,
            'BIOLabels':labels,'offsets':offsets,'strictAlignmentPassed':True})
        training.append({'sampleId':ref['sampleId'],'text':ref['text'],'textSha256':ref['textSha256'],
            'entities':entities,'relations':receipt['annotation']['relations'],'groupId':ref['groupId'],
            'split':'train','textKind':'abstract_excerpt','receiptSha256':receipt['contentSha256'],'labelSource':'ai_pseudo'})
    assert all(all(c.eligible_tasks(r,f).values()) for r,f in zip(receipts,refs))
    c.write_jsonl(output/'token_alignment.jsonl',preflight);c.write_jsonl(output/'train_examples.jsonl',training)
    summary={'documents':len(refs),'paperGroups':len({r['groupId'] for r in refs}),
        'entityCounts':dict(Counter(e['label'] for r in receipts for e in r['annotation']['entities'])),
        'relationCounts':dict(Counter(e['label'] for r in receipts for e in r['annotation']['relations'])),
        'selfReviewed':len(refs),'revisedBoundaries':sum(r['verdict']=='revise' for r in judgments['reviews']),
        'strictTokenAlignmentPassed':True,'maxTokens':max(r['tokens'] for r in preflight),
        'independentHumanGold':False,'trainingExecuted':False,'testEvaluated':False,'modelPromoted':False,
        'notice':'Targeted train-only AI pilot. No independent dev/test abstracts acquired. Not automatically compatible with title-only training contracts.'}
    c.write_json(output/'summary.json',summary)
    inputs=[folder/'manifest.json',judgments_path,Path(__file__),c.ROOT/'scripts/course_weak.py',c.ROOT/'scripts/compile_course_ai.py',c.ROOT/'kg_datasets/models/scibert_24f92d32/tokenizer.json']
    c.write_json(output/'manifest.json',{'inputSha256':{p.relative_to(c.ROOT).as_posix():c.file_sha256(p) for p in inputs},
        'filesSha256':{p.name:c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot',type=Path,required=True);parser.add_argument('--judgments',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();review(args.pilot.resolve(),args.judgments.resolve(),args.output.resolve())
