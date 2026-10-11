"""Independent whole-abstract train/dev contract; never consumes held-out test text."""
import argparse
import copy
import json
from collections import Counter
from datetime import UTC,datetime
from pathlib import Path

import course_graph as g
import course_weak as c
import train_course_ner as ner
import train_course_relation as re_model
from compile_abstract_annotations import annotate

CONTRACT=c.ROOT/'resources/course_abstract_v1.json'
TRAIN=c.ROOT/'kg_datasets/dblp/course_abstract_train_reviewed_20261008_33'

def read(path):return json.loads(path.read_text(encoding='utf-8'))

def protocol():
    config=read(CONTRACT);queue=c.ROOT/config['queue']
    if config['version']!='abstract_v1' or config['textKind']!='abstract' or config['entityLabels']!=c.CONFIG['entityLabels'] or config['bioLabels']!=c.CONFIG['bioLabels'] or config['maxTokens']!=512:raise ValueError('Incompatible abstract contract')
    g.verified_files(queue,config['queueManifestSha256'])
    return config,queue

def seal(output,inputs):
    c.write_json(output/'manifest.json',{'inputSha256':{p.relative_to(c.ROOT).as_posix():c.file_sha256(p) for p in inputs},
        'filesSha256':{p.relative_to(output).as_posix():c.file_sha256(p) for p in output.rglob('*') if p.is_file()}})

def compile_dev(decisions_path,reviews_path,output):
    if output.exists():raise FileExistsError('Preserve dev annotations')
    _,queue=protocol();refs=c.read_jsonl(queue/'dev_references.jsonl')
    source=read(decisions_path);reviews=read(reviews_path);decisions=source['documents']
    if [d['arxivId'] for d in decisions]!=[r['arxivId'] for r in refs] or [j['index'] for j in reviews['reviews']]!=list(range(len(refs))) or reviews['independent'] is not False:raise ValueError('Dev review coverage/order invalid')
    if any(r['split']!='dev' or r['textKind']!='abstract' for r in refs):raise ValueError('Only locked whole dev abstracts allowed')
    initial=[];reviewed=[]
    def metadata(document,path):return {'provider':document['provider'],'model':document['model'],'promptSha256':c.file_sha256(CONTRACT),'sourceArtifactSha256':c.file_sha256(path),'createdAt':datetime.now(UTC).isoformat()}
    for ref,decision,judgment in zip(refs,decisions,reviews['reviews']):
        prior=c.make_receipt(annotate(decision,ref),ref,metadata(source,decisions_path));initial.append(prior)
        if not judgment['reason'].strip() or set(judgment)-{'index','reason','addMentions'}:raise ValueError('Invalid explicit dev review')
        amended=copy.deepcopy(decision)
        for label,names in judgment.get('addMentions',{}).items():amended['mentions'].setdefault(label,[]).extend(names)
        response=annotate(amended,ref);response['reviewOfSha256']=prior['contentSha256'];response['notes']+=' Self-review: '+judgment['reason']
        reviewed.append(c.make_receipt(response,ref,metadata(reviews,reviews_path),previous=prior))
    output.mkdir(parents=True)
    c.write_jsonl(output/'references.jsonl',refs);c.write_jsonl(output/'generation_receipts.jsonl',initial);c.write_jsonl(output/'reviewed_receipts.jsonl',reviewed)
    summary={'documents':len(refs),'selfReviewed':len(reviewed),'nerEligibleClaims':sum(c.eligible_tasks(r,f)['ner'] for r,f in zip(reviewed,refs)),
        'relationCounts':dict(Counter(p['label'] for r in reviewed for p in r['annotation']['relations'])),
        'devAccessed':True,'testAccessed':False,'modelPredictionsSeenForAnnotation':False,'independentHumanGold':False,'trainingExecuted':False}
    c.write_json(output/'summary.json',summary)
    seal(output,[CONTRACT,queue/'manifest.json',decisions_path,reviews_path,Path(__file__),c.ROOT/'scripts/compile_abstract_annotations.py',c.ROOT/'scripts/course_weak.py',c.SCHEMA_PATH])
    print(json.dumps(summary))

def snapshot(dev,output):
    if output.exists():raise FileExistsError('Preserve abstract snapshot')
    config,queue=protocol();collections={};refs_by_split={s:c.read_jsonl(queue/(s+'_references.jsonl')) for s in ('train','dev')}
    if {r['groupId'] for r in refs_by_split['train']}&{r['groupId'] for r in refs_by_split['dev']}:raise ValueError('Cross-split paper-group leakage')
    for split,folder in (('train',TRAIN),('dev',dev)):
        g.verified_files(folder);refs=c.read_jsonl(folder/'references.jsonl');receipts=c.read_jsonl(folder/'reviewed_receipts.jsonl')
        if refs!=refs_by_split[split] or len(receipts)!=len(refs):raise ValueError('Annotation cohort differs from locked queue')
        if any(c.validate_receipt(r,f) or r['review'] is None for r,f in zip(receipts,refs)):raise ValueError('Unreviewed or invalid receipt')
        collections[split]=list(zip(refs,receipts))
    output.mkdir(parents=True)
    import os
    os.environ.setdefault('HF_HUB_OFFLINE','1')
    tokenizer=re_model.prepare_tokenizer(c.ROOT/'kg_datasets/models/scibert_24f92d32')
    summary={'version':'abstract_v1','documents':{},'entitySupport':{},'relationSupport':{},'unknownPairs':{},'fullRelationDocuments':{},'NERtokens':{},'excludedNER':{},'testConsumed':False,'trainingExecuted':False,'promotionAllowed':False}
    for split,pairs in collections.items():
        ner_rows=[];relation_rows=[];full_docs=[];excluded=[];alignment=[];unknown=0
        for ref,receipt in pairs:
            annotation=receipt['annotation'];eligible=c.eligible_tasks(receipt,ref)
            common={k:ref[k] for k in ('sampleId','publicationId','groupId','split','textKind','text','textSha256')}
            common.update(referenceSha256=c.canonical_sha256(ref),receiptSha256=receipt['contentSha256'],labelSource='ai_pseudo',contractSha256=c.file_sha256(CONTRACT))
            row=common|{'entities':annotation['entities']}
            if not eligible['ner']:
                excluded.append({'sampleId':ref['sampleId'],'reason':annotation['entityReason'] or 'Coordinated group quarantined'});continue
            try:encoded=ner.encode_row(tokenizer,row,config['maxTokens'])
            except ValueError as error:
                excluded.append({'sampleId':ref['sampleId'],'reason':str(error)});continue
            labels=encoded['features']['labels'];offsets=encoded['offsets']
            decoded=ner.decode_bio([0 if tuple(o)==(0,0) else label for o,label in zip(offsets,labels)],offsets,ref['text'])
            if decoded['entities']!=[{k:e[k] for k in ('start','end','text','label')} for e in row['entities']] or decoded['invalidTransitions']:raise ValueError('BIO round-trip mismatch')
            ner_rows.append(row);alignment.append({'sampleId':ref['sampleId'],'tokens':len(offsets),'offsets':offsets,'labels':labels})
            entities={e['entityId']:e for e in annotation['entities']}
            for p in annotation['relations']:
                if p['label']=='UNRESOLVED':unknown+=1;continue
                if split=='dev' and not eligible['relation']:continue
                candidate=common|{'head':entities[p['head']],'tail':entities[p['tail']],'label':p['label'],'evidence':p['evidence'],'reason':p['reason']}
                re_model.encode_pair(tokenizer,candidate,config['maxTokens']);relation_rows.append(candidate)
            if eligible['relation']:full_docs.append(row)
        if not ner_rows:raise ValueError('No eligible abstract NER documents: '+split)
        c.write_jsonl(output/('ner_'+split+'.jsonl'),ner_rows);c.write_jsonl(output/('relation_'+split+'.jsonl'),relation_rows)
        c.write_jsonl(output/('full_relation_'+split+'.jsonl'),full_docs);c.write_jsonl(output/('excluded_ner_'+split+'.jsonl'),excluded);c.write_jsonl(output/('alignment_'+split+'.jsonl'),alignment)
        summary['documents'][split]={'queue':len(pairs),'ner':len(ner_rows),'relations':len(relation_rows)}
        summary['entitySupport'][split]=dict(Counter(e['label'] for r in ner_rows for e in r['entities']))
        summary['relationSupport'][split]=dict(Counter(r['label'] for r in relation_rows));summary['unknownPairs'][split]=unknown
        summary['fullRelationDocuments'][split]=len(full_docs);summary['excludedNER'][split]=len(excluded);summary['NERtokens'][split]=max(a['tokens'] for a in alignment)
    summary['relationTrainingReady']=all(summary['relationSupport'][s].get(label,0)>0 for s in ('train','dev') for label in re_model.LABELS)
    summary['nerDevelopmentReady']=True
    c.write_json(output/'contract.json',config);c.write_json(output/'summary.json',summary)
    seal(output,[CONTRACT,queue/'manifest.json',TRAIN/'manifest.json',dev/'manifest.json',Path(__file__),c.ROOT/'scripts/train_course_ner.py',c.ROOT/'scripts/train_course_relation.py',c.ROOT/'scripts/course_weak.py',c.SCHEMA_PATH,c.ROOT/'kg_datasets/models/scibert_24f92d32/manifest.json'])
    print(json.dumps(summary))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('compile-dev','snapshot'));parser.add_argument('--decisions',type=Path);parser.add_argument('--reviews',type=Path);parser.add_argument('--dev',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    try:
        if args.action=='compile-dev':compile_dev(args.decisions.resolve(),args.reviews.resolve(),args.output.resolve())
        else:snapshot(args.dev.resolve(),args.output.resolve())
    except Exception as error:
        if args.output.exists() and not (args.output/'manifest.json').exists():c.write_json(args.output/'failure.json',{'status':'failed_no_synthetic_fallback','error':str(error),'errorType':type(error).__name__})
        raise
