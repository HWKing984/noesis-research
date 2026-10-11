"""Append a bounded pre-locked train-only abstract cohort; no held-out content or fabricated fallback."""
import argparse
import hashlib
import json
import os
import time
from datetime import UTC,datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request,urlopen
from urllib.robotparser import RobotFileParser

import course_graph as g
import course_weak as c
from course_abstract_v1 import read,seal
from collect_course_abstract_pages import parse_page
from fetch_abstract_pilot import normalize_title,POLICY

CONTRACT=c.ROOT/'resources/course_abstract_expansion_v1.json'
AGENT='AI-Literature-KG/abstract37 (bounded course metadata research)'

def protocol():
    config=read(CONTRACT);parent=c.ROOT/config['parentContract']
    if c.file_sha256(parent)!=config['parentContractSha256']:raise ValueError('Parent extraction contract drifted')
    for key in ('sourceSelection','previousPages','oldTraining','dev'):
        g.verified_files(c.ROOT/config[key],config[key+'ManifestSha256'])
    return config,read(parent)

def selection():
    config,parent=protocol();source=c.ROOT/config['sourceSelection'];pages=c.ROOT/config['previousPages']
    prior=read(pages/'selection_lock.json')['selected'];requested={r['arxivId'] for r in prior}
    # Cached sources were exposed before the new cohort and are train-only, but not new samples.
    requested|={r['arxivId'] for r in c.read_jsonl(source/'abstracts.jsonl')+c.read_jsonl(source/'quarantine.jsonl')}
    locked=read(source/'selection_lock.json')['selected']
    chosen=[r for r in locked if r['split']=='train' and r['arxivId'] not in requested][:config['additionalRequests']]
    splits={r['publicationId']:r for r in c.read_jsonl(c.ROOT/'kg_datasets/dblp/course_v4_weak/corpus_split_manifest.jsonl')}
    old_refs=c.read_jsonl(c.ROOT/config['oldTraining']/'references.jsonl');dev_refs=c.read_jsonl(c.ROOT/config['dev']/'references.jsonl')
    if len(chosen)!=config['additionalRequests'] or len({r['groupId'] for r in chosen})!=len(chosen):raise ValueError('Insufficient unique pre-locked train cohort')
    for row in chosen:
        if splits[row['publicationId']]['split']!='train' or splits[row['publicationId']]['groupId']!=row['groupId'] or row['groupId'] in {r['groupId'] for r in old_refs+dev_refs}:raise ValueError('Train source group conflicts')
    return config,parent,chosen

def get(url,limit):
    with urlopen(Request(url,headers={'User-Agent':AGENT,'Accept':'text/html,text/plain'}),timeout=20) as response:
        if urlsplit(response.url).hostname!='arxiv.org':raise ValueError('Unexpected source redirect')
        payload=response.read(limit+1)
        if len(payload)>limit:raise ValueError('Oversized source response')
        return payload

def collect(output):
    if output.exists():raise FileExistsError('Preserve collection evidence; use a fresh output')
    config,parent,chosen=selection();queue=c.ROOT/parent['queue'];g.verified_files(queue,parent['queueManifestSha256'])
    paths=[CONTRACT,c.ROOT/config['parentContract'],Path(__file__),c.ROOT/'scripts/collect_course_abstract_pages.py',c.ROOT/'scripts/fetch_abstract_pilot.py',
           c.ROOT/'kg_datasets/dblp/course_v4_weak/corpus_split_manifest.jsonl',queue/'manifest.json']
    paths += [c.ROOT/config[key]/'manifest.json' for key in ('sourceSelection','previousPages','oldTraining','dev')]
    hashes={p.relative_to(c.ROOT).as_posix():c.file_sha256(p) for p in paths}
    output.mkdir(parents=True);c.write_json(output/'selection_lock.json',{'selected':chosen,'lockedAtUTC':datetime.now(UTC).isoformat(),'selection':config['selection'],'inputSha256':hashes})
    robots_payload=get('https://arxiv.org/robots.txt',64*1024);(output/'robots.txt').write_bytes(robots_payload)
    robots=RobotFileParser();robots.parse(robots_payload.decode('utf-8').splitlines());delay=max(config['crawlDelaySeconds'],robots.crawl_delay(AGENT) or 0)
    if any(not robots.can_fetch(AGENT,'https://arxiv.org/abs/'+r['arxivId']) for r in chosen):raise ValueError('Source prohibited by robots.txt')
    c.write_json(output/'policy.json',POLICY|{'policy_checked_on':'2026-10-08','robotsURL':'https://arxiv.org/robots.txt','robotsSha256':c.file_sha256(output/'robots.txt'),
        'crawlDelaySeconds':delay,'policyCorrection':'HTML crawl delay follows robots (15s), not legacy API minimum (3s); historical round32 source evidence retained unchanged.'})
    os.environ.setdefault('HF_HUB_OFFLINE','1')
    from transformers import BertTokenizerFast
    tokenizer=BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32',local_files_only=True,do_lower_case=True)
    contract=read(queue/'contract.json');c.write_json(output/'contract.json',contract)
    requests=[];records=[];refs=[];excluded=[];last=time.monotonic()
    # ponytail: one bounded serial cohort; bulk metadata access is needed before corpus-scale collection.
    for i,row in enumerate(chosen,1):
        time.sleep(max(0,delay-(time.monotonic()-last)));last=time.monotonic();url='https://arxiv.org/abs/'+row['arxivId']
        request={'arxivId':row['arxivId'],'url':url,'startedAtUTC':datetime.now(UTC).isoformat()}
        try:
            raw=get(url,1024*1024);filename=f'page_{i:03d}.html';(output/filename).write_bytes(raw)
            title,text=parse_page(raw,row);match=normalize_title(title)==normalize_title(row['title']);digest=hashlib.sha256(text.encode()).hexdigest()
            record=row|{'title':title,'dblp_title':row['title'],'abstract':text,'content_hash':digest,'title_match':match,'source_url':url,
                'sourceOrigin':'fresh_locked_train_expansion','retrieved_at':request['startedAtUTC'],'rawResponseFile':filename,'raw_response_sha256':hashlib.sha256(raw).hexdigest()}
            records.append(record);tokens=len(tokenizer(text,add_special_tokens=True,truncation=False)['input_ids'])
            request.update(status='completed',titleMatch=match,tokens=tokens,rawResponseFile=filename)
            if not match or tokens>parent['maxTokens']:
                excluded.append({'arxivId':row['arxivId'],'reason':'title_mismatch' if not match else 'overlength_no_truncation','tokens':tokens})
            else:
                refs.append({'sampleId':'sample-'+c.canonical_sha256(['whole_abstract',row['arxivId'],digest])[:20],
                    **{k:row[k] for k in ('publicationId','arxivId','groupId','split')},'text':text,'textKind':'abstract','textSha256':digest,
                    'sourceURL':url,'sourceOrigin':'fresh_locked_train_expansion','schemaVersion':contract['version'],'contractSha256':c.canonical_sha256(contract),
                    'tokens':tokens,'annotationStatus':'pending'})
        except Exception as error:
            request.update(status='failed_no_synthetic_fallback',errorType=type(error).__name__,error=str(error));excluded.append({'arxivId':row['arxivId'],'reason':'failed_request'})
        requests.append(request);c.write_json(output/'requests.json',requests);c.write_jsonl(output/'abstracts.jsonl',records);c.write_jsonl(output/'train_references.jsonl',refs)
        print(json.dumps({'requests':i,'usable':len(refs),'excluded':len(excluded)}),flush=True)
    if any(c.file_sha256(c.ROOT/key)!=value for key,value in hashes.items()):raise ValueError('Source inputs drifted during collection')
    c.write_jsonl(output/'excluded.jsonl',excluded);c.write_json(output/'summary.json',{'requested':len(chosen),'fetched':len(records),'usableTrainAbstracts':len(refs),
        'excluded':len(excluded),'testAccessed':False,'trainingExecuted':False,'modelPromoted':False})
    seal(output,paths);print(json.dumps(read(output/'summary.json')),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    try:collect(args.output.resolve())
    except Exception as error:
        if args.output.exists() and not (args.output/'manifest.json').exists():c.write_json(args.output/'failure.json',{'errorType':type(error).__name__,'error':str(error),'status':'failed_no_synthetic_fallback'})
        raise
