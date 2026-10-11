"""Bounded official arXiv citation-metadata collection when export API is unavailable."""
import argparse
import hashlib
import json
import re
import time
from collections import Counter
from datetime import UTC,datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request,urlopen

import course_weak as c
import course_graph as g
from fetch_abstract_pilot import normalize_title,POLICY

class CitationMetadata(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.values={}
    def handle_starttag(self,tag,attrs):
        if tag!='meta':return
        attrs=dict(attrs);key=attrs.get('name','')
        if key not in ('citation_title','citation_arxiv_id','citation_abstract'):return
        if key in self.values:raise ValueError('Duplicate citation metadata')
        self.values[key]=attrs.get('content','')

def parse_page(payload,requested):
    parser=CitationMetadata();parser.feed(payload.decode('utf-8'));values=parser.values
    if set(values)!={'citation_title','citation_arxiv_id','citation_abstract'} or any(not v.strip() for v in values.values()):
        raise ValueError('Incomplete official citation metadata; no snippet substitute')
    if re.sub(r'v\d+$','',values['citation_arxiv_id'])!=requested['arxivId']:raise ValueError('arXiv identifier mismatch')
    return values['citation_title'],values['citation_abstract']

def collect(previous,output):
    if output.exists():raise FileExistsError('Preserve source evidence')
    g.verified_files(previous);lock=json.loads((previous/'selection_lock.json').read_text(encoding='utf-8'))
    selected=[]
    for split in ('train','dev','test'):selected += [r for r in lock['selected'] if r['split']==split][:20]
    if Counter(r['split'] for r in selected)!=Counter({'train':20,'dev':20,'test':20}):raise ValueError('Source cohort incomplete')
    inputs=[previous/'manifest.json',previous/'selection_lock.json',Path(__file__),c.ROOT/'scripts/fetch_abstract_pilot.py']
    hashes={p.relative_to(c.ROOT).as_posix():c.file_sha256(p) for p in inputs}
    policy=POLICY|{'policy_checked_on':'2026-10-08','extraction':'Official HTML citation_abstract/citation_title metadata; HTML character references decoded, no rewriting or snippets.'}
    output.mkdir(parents=True)
    c.write_json(output/'selection_lock.json',{'lockedAtUTC':datetime.now(UTC).isoformat(),'selected':selected,
        'selection':'First20 per split of prior locked uniform group cohort, chosen before page responses or labels. No score or rare-keyword test targeting.',
        'inputSha256':hashes,'policy':policy,'rate':'one serial request at least every3.1seconds','trainingExecuted':False})
    records=c.read_jsonl(previous/'abstracts.jsonl');quarantine=c.read_jsonl(previous/'quarantine.jsonl');requests=[];last=0
    for index,source in enumerate(selected,1):
        time.sleep(max(0,3.1-(time.monotonic()-last)));last=time.monotonic()
        url='https://arxiv.org/abs/'+source['arxivId'];request={'url':url,'arxivId':source['arxivId'],'startedAtUTC':datetime.now(UTC).isoformat()}
        try:
            with urlopen(Request(url,headers={'User-Agent':'AI-Literature-KG/abstract32 (bounded course metadata research)','Accept':'text/html'}),timeout=15) as response:
                if urlsplit(response.url).hostname!='arxiv.org':raise ValueError('Unexpected source redirect')
                payload=response.read(1024*1024+1)
                if len(payload)>1024*1024:raise ValueError('Source page too large')
            filename=f'page_{index:03d}.html';(output/filename).write_bytes(payload)
            title,abstract=parse_page(payload,source)
            matched=normalize_title(title)==normalize_title(source['title'])
            row={'publicationId':source['publicationId'],'arxivId':source['arxivId'],'title':title,'abstract':abstract,
                'dblp_title':source['title'],'reference_provider':'DBLP','split':source['split'],'groupId':source['groupId'],
                'source_url':url,'retrieved_at':request['startedAtUTC'],'content_hash':hashlib.sha256(abstract.encode()).hexdigest(),
                'raw_response_sha256':hashlib.sha256(payload).hexdigest(),'rawResponseFile':filename,'title_match':matched,
                'status':'source_verified_not_annotated' if matched else 'title_mismatch_needs_review',
                'sourceOrigin':'fresh_locked_dblp_html_metadata','policy':policy,'ner_annotations':None}
            (records if matched else quarantine).append(row)
            request.update(status='completed',matched=matched,rawResponseFile=filename)
        except Exception as error:request.update(status='failed_no_synthetic_fallback',errorType=type(error).__name__,error=str(error))
        requests.append(request);c.write_json(output/'requests.json',requests)
        if index%10==0:print(json.dumps({'completedRequests':index,'failures':sum(r['status']!='completed' for r in requests)}),flush=True)
    if any(c.file_sha256(c.ROOT/p)!=sha for p,sha in hashes.items()):raise ValueError('Source inputs drifted')
    c.write_jsonl(output/'abstracts.jsonl',records);c.write_jsonl(output/'quarantine.jsonl',quarantine)
    summary={'status':'completed' if all(r['status']=='completed' for r in requests) else 'partial',
        'requestedNew':len(selected),'freshMatched':sum(r['sourceOrigin']=='fresh_locked_dblp_html_metadata' for r in records),
        'usableAbstracts':len(records),'bySplit':dict(Counter(r['split'] for r in records)),
        'quarantinedTitleMismatches':len(quarantine),'failedRequests':sum(r['status']!='completed' for r in requests),
        'annotated':False,'trainingExecuted':False,'testEvaluated':False,'modelPromoted':False}
    c.write_json(output/'summary.json',summary)
    c.write_json(output/'manifest.json',{'inputSha256':hashes,'filesSha256':{p.name:c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
    print(json.dumps(summary))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--previous',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();collect(args.previous.resolve(),args.output.resolve())
