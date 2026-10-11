"""Isolated abstract-source cohort; preserve raw responses, old splits and failures."""
import argparse
import csv
import hashlib
import json
import re
import time
from collections import Counter
from datetime import UTC,datetime
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from urllib.request import Request,urlopen

import course_weak as c
from fetch_abstract_pilot import normalize_title,parse_feed,POLICY

ROOT=c.ROOT
CACHED=ROOT/'kg_datasets/dblp/ner_v3_1'

def plan_sources():
    corpus=ROOT/'kg_datasets/dblp/processed_ai/publications.csv'
    split_file=ROOT/'kg_datasets/dblp/course_v4_weak/corpus_split_manifest.jsonl'
    refs=[ROOT/'kg_datasets/dblp'/p/'references.jsonl' for p in ('course_v4_weak','course_v4_holdout_20261007_29')]
    splits={r['publicationId']:r for r in c.read_jsonl(split_file)}
    excluded={splits[r['publicationId']]['groupId'] for p in refs for r in c.read_jsonl(p)}
    cached=[];inputs=[corpus,split_file,*refs,Path(__file__),ROOT/'scripts/fetch_abstract_pilot.py']
    for name in ('abstract_sources','benchmark_abstract_sources'):
        folder=CACHED/name;inputs += [folder/'abstracts.jsonl',folder/'response.atom',folder/'request.json']
        rows=c.read_jsonl(folder/'abstracts.jsonl')
        raw_sha=c.file_sha256(folder/'response.atom')
        for row in rows:
            if row['raw_response_sha256']!=raw_sha or row['content_hash']!=hashlib.sha256(row['abstract'].encode()).hexdigest():
                raise ValueError('Cached abstract source drifted')
            cached.append(row)
    cached_ids={r['arxivId'] for r in cached}
    cached_titles={normalize_title(r['title']) for r in cached}
    with corpus.open(encoding='utf-8-sig',newline='') as stream:publications=list(csv.DictReader(stream))
    title_groups={}
    for row in publications:
        title_groups.setdefault(normalize_title(row['title']),set()).add(splits[row['publicationId:ID(Publication)']]['groupId'])
    excluded |= {group for title in cached_titles for group in title_groups.get(title,())}
    eligible=[]
    for row in publications:
        pid=row['publicationId:ID(Publication)'];match=re.fullmatch(r'journals/corr/abs-(\d{4})-(\d{4,5})',pid)
        group=splits[pid]
        if not match or group['groupId'] in excluded:continue
        arxiv_id=match[1]+'.'+match[2]
        if arxiv_id in cached_ids:continue
        eligible.append({'publicationId':pid,'arxivId':arxiv_id,'title':row['title'],
            'groupId':group['groupId'],'split':group['split']})
    selected=[];seen=set()
    for split,target in (('train',60),('dev',20),('test',20)):
        candidates=sorted((r for r in eligible if r['split']==split),key=lambda r:c.canonical_sha256(['abstract32',r['groupId'],r['arxivId']]))
        for row in candidates:
            if row['groupId'] in seen:continue
            seen.add(row['groupId']);selected.append(row)
            if sum(r['split']==split for r in selected)==target:break
    return selected,cached,inputs,{'eligibleCounts':dict(Counter(r['split'] for r in eligible)),
        'selectedCounts':dict(Counter(r['split'] for r in selected)),
        'selection':'Prior paper-group split fixed; no new title keyword or model-score targeting. Prior labelled and cached exposed groups excluded from new cohort.'}

def collect(output):
    if output.exists():raise FileExistsError('Preserve source run; use a new output')
    selected,cached,inputs,selection=plan_sources()
    output.mkdir(parents=True)
    policy=POLICY|{'policy_checked_on':'2026-10-08'}
    contract={'version':'course-abstract-1','textKind':'abstract','offsetUnit':'unicode_codepoint',
        'entityLabels':c.CONFIG['entityLabels'],'relationPairs':c.CONFIG['relationPairs'],
        'splitPolicy':'Same paper group across titles and abstracts; cached/exposed external benchmarks train-only. Test sources reserved before annotation.',
        'annotationSource':'ai_pseudo_not_independent_human_gold','titleLabelsReusable':False,
        'normalization':'none: source abstract Unicode text retained exactly','overlengthPolicy':'reject, never silent truncation',
        'promotion':'No automatic promotion; require rare-class support and independent evaluation. No closed title test tuning.',
        'relationScope':'Only explicitly supported METHOD->TASK or METHOD->DATASET; unresolved coreference is not a negative.',
        'iterationCompact':{'goal':'Add real abstract evidence for missing DATASET/EVALUATED_ON support',
            'successMetric':'usable source-matched abstracts and explicit rare labels, not inflated F1',
            'mistakeBudget':'zero fabricated abstracts, source joins, copied title labels or cross-split paper groups',
            'baseline':'Title production unchanged; preceding dev constrained decoder rejected',
            'nextExperiment':'Source availability, then AI-labelled pilot and strict token/offset preflight',
            'fallback':'Keep old model and graph; preserve failed acquisition without synthetic substitute'}}
    hashes={p.relative_to(ROOT).as_posix():c.file_sha256(p) for p in inputs}
    c.write_json(output/'contract.json',contract)
    c.write_json(output/'selection_lock.json',selection|{'lockedAtUTC':datetime.now(UTC).isoformat(),'selected':selected,'inputSha256':hashes,'policy':policy})
    records=[];quarantine=[];requests=[]
    # ponytail: bounded serial metadata batches; use arXiv bulk metadata only if corpus-scale collection is needed.
    for row in cached:
        enriched=row|{'split':'train','groupId':'abstract-paper-'+row['arxivId'],'sourceOrigin':'cached_exposed_train_only'}
        (records if row['title_match'] else quarantine).append(enriched)
    previous=0
    for start in range(0,len(selected),20):
        batch=selected[start:start+20];requested={r['arxivId']:r for r in batch}
        url='https://export.arxiv.org/api/query?'+urlencode({'id_list':','.join(requested),'max_results':len(batch)})
        time.sleep(max(0,3.1-(time.monotonic()-previous)));previous=time.monotonic()
        request={'url':url,'startedAtUTC':datetime.now(UTC).isoformat(),'arxivIds':list(requested),'concurrency':1}
        try:
            with urlopen(Request(url,headers={'User-Agent':'AI-Literature-KG/abstract32 (bounded course metadata research)','Accept':'application/atom+xml'}),timeout=25) as response:
                if urlsplit(response.url).hostname not in ('export.arxiv.org','arxiv.org'):raise ValueError('Unexpected source redirect')
                payload=response.read(4*1024*1024+1)
                if len(payload)>4*1024*1024:raise ValueError('Response too large')
            filename=f'response_{start//20+1:02d}.atom';(output/filename).write_bytes(payload)
            parsed=parse_feed(payload,requested,url,request['startedAtUTC'])
            for row in parsed:
                source=requested[row['arxivId']]
                row |= {'split':source['split'],'groupId':source['groupId'],'policy':policy,'sourceOrigin':'fresh_locked_dblp_cohort','rawResponseFile':filename}
                (records if row['title_match'] else quarantine).append(row)
            request.update(status='completed',received=len(parsed),missingIds=sorted(set(requested)-{r['arxivId'] for r in parsed}))
        except Exception as error:request.update(status='failed_no_synthetic_fallback',errorType=type(error).__name__,error=str(error))
        requests.append(request);c.write_json(output/'requests.json',requests)
        print(json.dumps({'batch':start//20+1,'status':request['status'],'received':request.get('received',0)}),flush=True)
    if any(c.file_sha256(ROOT/p)!=sha for p,sha in hashes.items()):raise ValueError('Source drift during collection')
    c.write_jsonl(output/'abstracts.jsonl',records);c.write_jsonl(output/'quarantine.jsonl',quarantine)
    summary={'status':'completed' if all(r['status']=='completed' and not r['missingIds'] for r in requests) else 'partial',
        'selected':len(selected),'usableAbstracts':len(records),'bySplit':dict(Counter(r['split'] for r in records)),
        'quarantinedTitleMismatches':len(quarantine),'failedRequests':sum(r['status']!='completed' for r in requests),
        'annotated':False,'trainingExecuted':False,'modelPromoted':False,'policy':policy}
    c.write_json(output/'summary.json',summary)
    c.write_json(output/'manifest.json',{'inputSha256':hashes,'filesSha256':{p.name:c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    collect(parser.parse_args().output.resolve())
