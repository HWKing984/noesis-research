"""One bounded external development slice; reuse parsing, receipts, relation rules and BIO."""
import argparse
import copy
import hashlib
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.robotparser import RobotFileParser

import collect_train_abstracts as transport
import course_graph as g
import course_weak as c
import train_course_ner as ner
import train_course_relation as relation
from collect_course_abstract_pages import parse_page
from compile_abstract_annotations import annotate
from course_abstract_relation import revise, rows_for
from course_abstract_v1 import read, seal
from expand_train_benchmarks import CORPUS, reject_identity_overlap, title_key

CONTRACT = c.ROOT/'resources/course_abstract_dev_supplement_v1.json'
RELATION_CONTRACT = c.ROOT/'resources/course_abstract_relation_v1.json'


def locked():
    config = read(CONTRACT); source = c.ROOT/config['snapshot']; metadata = c.ROOT/config['metadataLock']
    if config['version'] != 'abstract_dev_supplement_v1' or len(config['seeds']) != 8 or config['maxTokens'] != 512 or config['crawlDelaySeconds'] < 15.1 or any(config[k] is not False for k in ('trainingAllowed','inferenceAllowed','automaticPromotionAllowed','independentHumanGold')):
        raise ValueError('Supplement contract drift')
    manifest = g.verified_files(source, config['snapshotManifestSha256'])
    if c.file_sha256(CORPUS) != config['corpusSha256'] or c.file_sha256(metadata) != config['metadataLockSha256'] or any(c.file_sha256(c.ROOT/p) != sha for p,sha in manifest['inputSha256'].items()):
        raise ValueError('Source identity/hash drift')
    existing = c.read_jsonl(source/'train_references.jsonl')+c.read_jsonl(source/'dev_references.jsonl')
    identities = [{k:r.get(k,'') for k in ('publicationId','arxivId')} | {'title':r.get('referenceTitle','')} for r in existing]
    reject_identity_overlap(config['seeds'], c.read_jsonl(CORPUS), identities+read(metadata)['selected'])
    return config


def checked_new(output):
    if output.exists(): raise FileExistsError('Preserve supplementary source/annotation evidence')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Output outside dataset directory')


def inputs():
    config = locked()
    return [CONTRACT, Path(__file__), CORPUS, c.ROOT/config['metadataLock'], c.ROOT/config['snapshot']/'manifest.json', RELATION_CONTRACT,
            c.ROOT/'scripts/collect_train_abstracts.py', c.ROOT/'scripts/collect_course_abstract_pages.py', c.ROOT/'scripts/expand_train_benchmarks.py',
            c.ROOT/'scripts/compile_abstract_annotations.py', c.ROOT/'scripts/course_abstract_relation.py', c.ROOT/'scripts/course_weak.py', c.SCHEMA_PATH,
            c.ROOT/'scripts/train_course_ner.py', c.ROOT/'scripts/train_course_relation.py', c.ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt',
            c.ROOT/'kg_datasets/models/scibert_24f92d32/config.json', c.ROOT/'resources/course_graph_runtime.json',
            c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl']


def collect(output):
    checked_new(output); config = locked(); paths = inputs(); hashes = {p:c.file_sha256(p) for p in paths}; output.mkdir(parents=True)
    try:
        c.write_json(output/'selection_lock.json', {'lockedAtUTC':datetime.now(UTC).isoformat(),'selected':config['seeds'],'selection':config['selection'],'identityOverlap':False})
        payload = transport.get('https://arxiv.org/robots.txt',64*1024); (output/'robots.txt').write_bytes(payload)
        robots = RobotFileParser(); robots.parse(payload.decode().splitlines()); delay = max(config['crawlDelaySeconds'],robots.crawl_delay(transport.AGENT) or 0)
        if any(not robots.can_fetch(transport.AGENT,'https://arxiv.org/abs/'+s['arxivId']) for s in config['seeds']): raise ValueError('Robots prohibits request')
        c.write_json(output/'policy.json',{'robotsSha256':c.file_sha256(output/'robots.txt'),'crawlDelaySeconds':delay,'source':'official citation metadata; no PDF','checkedAtUTC':datetime.now(UTC).isoformat()})
        tokenizer = relation.prepare_tokenizer(c.ROOT/'kg_datasets/models/scibert_24f92d32'); refs=[]; requests=[]; excluded=[]; last=time.monotonic()
        # ponytail: fixed eight serial requests; use bulk metadata before larger collection.
        for i,seed in enumerate(config['seeds'],1):
            time.sleep(max(0,delay-(time.monotonic()-last))); last=time.monotonic(); url='https://arxiv.org/abs/'+seed['arxivId']; request=seed | {'url':url,'startedAtUTC':datetime.now(UTC).isoformat()}
            try:
                raw=transport.get(url,1024*1024); filename=f'page_{i:03d}.html'; (output/filename).write_bytes(raw); title,text=parse_page(raw,seed)
                tokens=len(tokenizer(text,truncation=False)['input_ids']); digest=hashlib.sha256(text.encode()).hexdigest(); match=title_key(title)==title_key(seed['title'])
                request.update(status='completed',titleMatch=match,tokens=tokens,rawResponseFile=filename,rawResponseSha256=c.file_sha256(output/filename))
                if not match or tokens>512: excluded.append(seed | {'reason':'title_mismatch' if not match else 'overlength_no_truncation'})
                else: refs.append({'sampleId':'sample-'+c.canonical_sha256(['whole_abstract',seed['arxivId'],digest])[:20],'publicationId':'arxiv:'+seed['arxivId'],'arxivId':seed['arxivId'],'referenceTitle':title,'groupId':'abstract-paper-'+seed['arxivId'],'split':'dev','textKind':'abstract','text':text,'textSha256':digest,'sourceURL':url,'sourceOrigin':'external_targeted_supplementary_dev','tokens':tokens})
            except Exception as error:
                request.update(status='failed_no_synthetic_fallback',errorType=type(error).__name__,error=str(error)); excluded.append(seed | {'reason':'failed_request'})
            requests.append(request); c.write_json(output/'requests.json',requests); c.write_jsonl(output/'references.jsonl',refs); print({'requested':i,'usable':len(refs),'excluded':len(excluded)},flush=True)
        if any(c.file_sha256(p)!=sha for p,sha in hashes.items()): raise ValueError('Collection input drift')
        c.write_jsonl(output/'excluded.jsonl',excluded); c.write_json(output/'contract.json',config)
        c.write_json(output/'summary.json',{'requested':8,'usable':len(refs),'excluded':len(excluded),'status':'completed' if len(refs)==8 else 'partial','testEvaluated':False,'trainingExecuted':False,'inferenceExecuted':False,'modelPromoted':False})
        seal(output,paths)
    except Exception as error:
        c.write_json(output/'failure.json',{'status':'failed_no_synthetic_fallback','errorType':type(error).__name__,'error':str(error)}); raise


def compile_decision(decision, ref):
    if decision['arxivId']!=ref['arxivId'] or decision['textSha256']!=ref['textSha256']: raise ValueError('Decision source binding differs')
    response=annotate(decision,ref)
    if response['entityStatus']=='complete' and not response['groupMentions']:
        response=revise(response,ref,decision,read(RELATION_CONTRACT))
    elif decision.get('groups'): raise ValueError('Quarantined entities cannot gain resolved pairs')
    return response


def annotate_batch(source,decisions_path,output,reviews_path=None):
    checked_new(output); config=locked(); paths=inputs()+[source/'manifest.json',decisions_path]
    manifest=g.verified_files(source)
    if any(c.file_sha256(c.ROOT/p)!=sha for p,sha in manifest['inputSha256'].items()): raise ValueError('Annotation input drift')
    refs=c.read_jsonl(source/'references.jsonl'); decisions=read(decisions_path); documents=decisions['documents']
    if [d['arxivId'] for d in documents]!=[r['arxivId'] for r in refs] or not refs or any(r['split']!='dev' or r['textKind']!='abstract' or hashlib.sha256(r['text'].encode()).hexdigest()!=r['textSha256'] for r in refs): raise ValueError('Incomplete/invalid development annotation cohort')
    reviews=read(reviews_path) if reviews_path else None; old=c.read_jsonl(source/'generation_receipts.jsonl') if reviews else []
    if reviews and (reviews['independent'] is not False or [r['arxivId'] for r in reviews['reviews']]!=[r['arxivId'] for r in refs] or len(old)!=len(refs)): raise ValueError('Invalid actual self-review cohort')
    def metadata(document,path): return {'provider':document['provider'],'model':document['model'],'promptSha256':c.file_sha256(CONTRACT),'sourceArtifactSha256':c.file_sha256(path),'createdAt':datetime.now(UTC).isoformat()}
    receipts=[]
    for i,(decision,ref) in enumerate(zip(documents,refs)):
        response=compile_decision(decision,ref)
        if reviews:
            judgment=reviews['reviews'][i]
            if set(judgment)!={'arxivId','reason'} or not judgment['reason'].strip() or response!=old[i]['annotation']: raise ValueError('Review must confirm this fixed generation; amendments need separate source-bound decisions')
            response=copy.deepcopy(response); response['reviewOfSha256']=old[i]['contentSha256']; response['notes']+=' Actual same-session source review: '+judgment['reason']
            receipts.append(c.make_receipt(response,ref,metadata(reviews,reviews_path),previous=old[i]))
        else: receipts.append(c.make_receipt(response,ref,metadata(decisions,decisions_path)))
    output.mkdir(parents=True)
    try:
        c.write_jsonl(output/'references.jsonl',refs); c.write_jsonl(output/('reviewed_receipts.jsonl' if reviews else 'generation_receipts.jsonl'),receipts)
        summary={'lockedQueue':8,'annotated':len(refs),'selfReviewed':bool(reviews),'independentHumanGold':False,'trainingExecuted':False,'inferenceExecuted':False,'testEvaluated':False,'modelPromoted':False,'qualityPromotionPassed':False,'selectionBias':config['selection'],'originalDevUnchanged':True}
        if reviews:
            paths.append(reviews_path); rows,pairs,full,excluded,unknown,total=rows_for(refs,receipts); tokenizer=relation.prepare_tokenizer(c.ROOT/'kg_datasets/models/scibert_24f92d32'); alignment=[]
            for row in rows:
                encoded=ner.encode_row(tokenizer,row,512); offsets=encoded['offsets']; labels=encoded['features']['labels']; decoded=ner.decode_bio([0 if tuple(o)==(0,0) else t for t,o in zip(labels,offsets)],offsets,row['text'])
                if decoded['invalidTransitions'] or decoded['entities']!=[{k:e[k] for k in ('start','end','text','label')} for e in row['entities']]: raise ValueError('Strict BIO round-trip failed')
                alignment.append({'sampleId':row['sampleId'],'offsets':offsets,'labels':labels})
            for pair in pairs: relation.encode_pair(tokenizer,pair,512)
            for name,values in [('ner_dev',rows),('relation_dev',pairs),('full_relation_dev',full),('excluded_ner',excluded),('token_alignment',alignment)]: c.write_jsonl(output/(name+'.jsonl'),values)
            full_ids={r['sampleId'] for r in full}; full_eval=[p for p in pairs if p['sampleId'] in full_ids and p['label']=='EVALUATED_ON']
            summary.update(NER=len(rows),entities=dict(Counter(e['label'] for r in rows for e in r['entities'])),knownPairs=len(pairs),eligiblePairs=total,unknownPairs=unknown,relationSupport=dict(Counter(p['label'] for p in pairs)),completeDocuments=len(full),completeCoverage=len(full)/8,completeEVALSupport=len(full_eval),completeEVALPapers=len({p['sampleId'] for p in full_eval}))
        c.write_json(output/'summary.json',summary); c.write_json(output/'contract.json',config); seal(output,paths); print(summary,flush=True)
    except Exception as error:
        c.write_json(output/'failure.json',{'status':'failed_no_synthetic_fallback','errorType':type(error).__name__,'error':str(error)}); raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('action',choices=('preflight','collect','compile','review')); parser.add_argument('--source',type=Path); parser.add_argument('--decisions',type=Path); parser.add_argument('--reviews',type=Path); parser.add_argument('--output',type=Path); args=parser.parse_args()
    if args.action=='preflight': print({'lockedSeeds':len(locked()['seeds']),'identityOverlap':False,'testContentAccessed':False})
    elif args.output is None: parser.error('New output required')
    elif args.action=='collect': collect(args.output.resolve())
    elif args.source is None or args.decisions is None or (args.action=='review' and args.reviews is None): parser.error('source/decisions/reviews required')
    else: annotate_batch(args.source.resolve(),args.decisions.resolve(),args.output.resolve(),args.reviews.resolve() if args.action=='review' else None)
