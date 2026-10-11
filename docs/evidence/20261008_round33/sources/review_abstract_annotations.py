"""Review whole train abstracts without accessing held-out texts or fitting a model."""
import argparse
import copy
import json
import os
from collections import Counter
from datetime import UTC,datetime
from pathlib import Path

import course_graph as g
import course_weak as c
import train_course_ner as ner
from compile_abstract_annotations import annotate

def review(folder,decisions_path,judgments_path,output):
    if output.exists():raise FileExistsError('Preserve reviewed batch')
    g.verified_files(folder)
    for name,digest in json.loads((folder/'manifest.json').read_text(encoding='utf-8'))['inputSha256'].items():
        if c.file_sha256(c.ROOT/name)!=digest:raise ValueError('Generation input drift: '+name)
    refs=c.read_jsonl(folder/'references.jsonl');initial=c.read_jsonl(folder/'generation_receipts.jsonl')
    decisions=json.loads(decisions_path.read_text(encoding='utf-8'))['documents']
    judgments=json.loads(judgments_path.read_text(encoding='utf-8'))
    if judgments['independent'] is not False:raise ValueError('Cannot certify independent review')
    if [j['index'] for j in judgments['reviews']]!=list(range(len(refs))) or len(decisions)!=len(refs) or len(initial)!=len(refs):raise ValueError('Incomplete review')
    if any(r['split']!='train' or r['textKind']!='abstract' for r in refs):raise ValueError('Only whole train abstracts allowed')
    output.mkdir(parents=True)
    c.write_json(output/'review_prompt.json',{'instruction':'Same-session AI review against whole original train abstract: boundaries, scope, method families, named datasets, context-specific homonyms, direct evidence and conservative quarantines. Not independent human gold.'})
    metadata={'provider':judgments['provider'],'model':judgments['model'],'promptSha256':c.file_sha256(output/'review_prompt.json'),
        'sourceArtifactSha256':c.file_sha256(judgments_path),'createdAt':datetime.now(UTC).isoformat()}
    receipts=[]
    for ref,prior,decision,judgment in zip(refs,initial,decisions,judgments['reviews']):
        if c.validate_receipt(prior,ref) or decision['arxivId']!=ref['arxivId']:raise ValueError('Initial receipt or order invalid')
        if not judgment['reason'].strip() or set(judgment)-{'index','reason','addMentions','excludedLiterals','entityStatus'}:raise ValueError('Invalid review amendment')
        amended=copy.deepcopy(decision)
        for label,names in judgment.get('addMentions',{}).items():amended['mentions'].setdefault(label,[]).extend(names)
        amended['excludedLiterals']=amended.get('excludedLiterals',[])+judgment.get('excludedLiterals',[])
        if 'entityStatus' in judgment:amended.update(entityStatus=judgment['entityStatus'],reason=judgment['reason'])
        response=annotate(amended,ref);response['reviewOfSha256']=prior['contentSha256'];response['notes']+=' Self-review: '+judgment['reason']
        receipt=c.make_receipt(response,ref,metadata,previous=prior)
        if c.validate_receipt(receipt,ref):raise ValueError('Reviewed receipt invalid')
        receipts.append(receipt)
    c.write_jsonl(output/'references.jsonl',refs);c.write_jsonl(output/'reviewed_receipts.jsonl',receipts)
    os.environ.setdefault('HF_HUB_OFFLINE','1')
    from transformers import BertTokenizerFast
    tokenizer=BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32',local_files_only=True,do_lower_case=True)
    preflight=[];training=[];positives=[]
    for ref,receipt in zip(refs,receipts):
        annotation=receipt['annotation'];eligible=c.eligible_tasks(receipt,ref)
        entry={'sampleId':ref['sampleId'],'eligibility':eligible,'strictAlignmentPassed':False}
        if eligible['ner']:
            offsets=tokenizer(ref['text'],return_offsets_mapping=True,add_special_tokens=True,truncation=False)['offset_mapping']
            try:
                if len(offsets)>512:raise ValueError('Over 512 tokens; no silent truncation')
                labels=c.align_bio(offsets,annotation['entities'],ref['text'])
                decoded=ner.decode_bio([0 if offset==(0,0) else label for label,offset in zip(labels,offsets)],offsets,ref['text'])
                expected=[{k:v for k,v in e.items() if k!='entityId'} for e in annotation['entities']]
                if decoded['invalidTransitions'] or decoded['entities']!=expected:raise ValueError('BIO round-trip mismatch')
                entry.update(tokens=len(offsets),BIOLabels=labels,offsets=offsets,strictAlignmentPassed=True)
                training.append({'sampleId':ref['sampleId'],'text':ref['text'],'textSha256':ref['textSha256'],'entities':annotation['entities'],
                    'groupId':ref['groupId'],'split':'train','textKind':'abstract','receiptSha256':receipt['contentSha256'],'labelSource':'ai_pseudo'})
            except ValueError as error:entry['exclusionReason']=str(error)
        else:entry['exclusionReason']=annotation['entityReason'] or 'Coordinated group quarantined'
        preflight.append(entry)
        for relation in annotation['relations']:
            if relation['label']!='UNRESOLVED':positives.append({'sampleId':ref['sampleId'],'receiptSha256':receipt['contentSha256'],'relation':relation,'fullRelationTrainingEligible':eligible['relation']})
    c.write_jsonl(output/'token_alignment.jsonl',preflight);c.write_jsonl(output/'ner_train_candidates.jsonl',training)
    c.write_jsonl(output/'positive_relation_candidates.jsonl',positives)
    summary={'documents':len(refs),'selfReviewed':len(receipts),'nerCandidates':len(training),'excludedNER':len(refs)-len(training),
        'eligibleNEREntityCounts':dict(Counter(e['label'] for r in training for e in r['entities'])),
        'relationCounts':dict(Counter(r['label'] for a in receipts for r in a['annotation']['relations'])),
        'completeRelationDocuments':sum(e['eligibility']['relation'] for e in preflight),
        'positiveRelationCandidates':len(positives),'maxNERtokens':max((e.get('tokens',0) for e in preflight),default=0),
        'independentHumanGold':False,'devAccessed':False,'testAccessed':False,'trainingExecuted':False,'modelPromoted':False,
        'notice':'AI pseudo labels only. NER candidates are not automatically admitted to the title-only model contract. Unresolved pairs are not negative examples; positive candidates are not a complete RE training dataset.'}
    c.write_json(output/'summary.json',summary)
    inputs=[folder/'manifest.json',decisions_path,judgments_path,Path(__file__),c.ROOT/'scripts/compile_abstract_annotations.py',c.ROOT/'scripts/course_weak.py',c.ROOT/'scripts/train_course_ner.py',c.SCHEMA_PATH,c.ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt',c.ROOT/'kg_datasets/models/scibert_24f92d32/config.json']
    c.write_json(output/'manifest.json',{'inputSha256':{p.relative_to(c.ROOT).as_posix():c.file_sha256(p) for p in inputs},'filesSha256':{p.name:c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('generation','decisions','judgments','output'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    try:review(args.generation.resolve(),args.decisions.resolve(),args.judgments.resolve(),args.output.resolve())
    except Exception as error:
        if args.output.exists() and not (args.output/'manifest.json').exists():c.write_json(args.output/'failure.json',{'status':'failed_no_synthetic_fallback','errorType':type(error).__name__,'error':str(error)})
        raise
