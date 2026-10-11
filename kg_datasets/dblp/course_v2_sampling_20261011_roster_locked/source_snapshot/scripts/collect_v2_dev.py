"""Collect only fixed dev abstracts; never fetch/annotate test or replace failures."""
import argparse
import csv
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

import course_v2_sampling as s
import prepare_v2_sampling as p

MAX_BYTES=1024*1024
RATE_SECONDS=3.2


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.values={}

    def handle_starttag(self,tag,attrs):
        if tag!='meta': return
        attrs=dict(attrs);name=attrs.get('name')
        if name not in ('citation_title','citation_arxiv_id','citation_abstract'):return
        if name in self.values: raise ValueError('Duplicate official citation metadata')
        self.values[name]=attrs.get('content','')


def parse(payload,member,title):
    parser=Metadata();parser.feed(payload.decode('utf-8'));parser.close();v=parser.values
    if set(v)!={'citation_title','citation_arxiv_id','citation_abstract'} or any(not x.strip() for x in v.values()):
        raise ValueError('Missing official abstract metadata; no snippet fallback')
    if s.identity.canonical_arxiv(v['citation_arxiv_id'])!=member['arxivId']:
        raise ValueError('Official source paper identity mismatch')
    if s.title_key(v['citation_title'])!=s.title_key(title):
        raise ValueError('Official source title differs from fixed listing; quarantine, no replacement')
    return {'sourceTitle':v['citation_title'],'sourceArxivVersion':v['citation_arxiv_id'],
            'text':v['citation_abstract'],
            'textSha256':hashlib.sha256(v['citation_abstract'].encode('utf-8')).hexdigest()}


def members(bundle):
    # Metadata only; never touches any test abstract/reference file.
    p.verify(bundle)
    chosen=s.read(bundle/'selected_members.json')
    dev=[r for r in chosen if r['split']=='dev']
    if len(dev)!=20 or sum(r['split']=='test' for r in chosen)!=20:
        raise ValueError('Fixed dev20/test20 cohort required')
    return dev


def collect(bundle,output):
    bundle=Path(bundle).resolve();output=Path(output).resolve()
    if output.exists():raise FileExistsError('Preserve prior acquisition; use an explicit new attempt directory')
    selected=members(bundle)
    population={r['arxivId']:r for r in s.rows(bundle/'population.jsonl')}
    manifest_sha=p.sha(bundle/'manifest.json');members_sha=p.sha(bundle/'selected_members.json')
    sources={str(Path(__file__).name):p.sha(Path(__file__)),
             'course_v2_sampling.py':p.sha(Path(s.__file__))}
    old=bundle/'audit_parent'
    forbidden={r.get('textSha256') for r in s.rows(old/'historical_exclusions.jsonl') if r.get('textSha256')}
    forbidden.update(r['textSha256'] for r in s.read(old/'split_lock.json')['assignments'])
    output.mkdir(parents=True);(output/'sources').mkdir()
    p.write(output/'dev_selection_lock.json',{'selected':selected,'samplingManifestSha256':manifest_sha,
        'selectedMembersFileSha256':members_sha,'sourceSha256':sources,
        'testContentAccessAllowed':False,'resamplingAllowed':False,'trainingAuthorized':False})
    records=[];requests=[];last=0;seen=set()
    try:
        for index,member in enumerate(selected,1):
            # Serial public-source requests; bounded to the selected dev identities.
            time.sleep(max(0,RATE_SECONDS-(time.monotonic()-last)));last=time.monotonic()
            url='https://arxiv.org/abs/'+member['arxivId']
            request={'arxivId':member['arxivId'],'split':'dev','requestedURL':url,'startedAtUTC':datetime.now(UTC).isoformat()}
            try:
                with urlopen(Request(url,headers={'User-Agent':'AI-Literature-KG/2.0 bounded academic dev metadata collection',
                    'Accept':'text/html'}),timeout=15) as response:
                    payload=response.read(MAX_BYTES+1);final_url=response.geturl()
                    if response.status!=200 or final_url!=url or len(payload)>MAX_BYTES:
                        raise ValueError('Unexpected source response/redirect/size')
                path=output/'sources'/('dev_'+member['arxivId']+'.html');path.write_bytes(payload)
                request.update(rawResponseFile=path.relative_to(output).as_posix(),rawResponseSha256=p.sha(path),finalURL=final_url)
                extracted=parse(payload,member,population[member['arxivId']]['title'])
                if extracted['textSha256'] in forbidden or extracted['textSha256'] in seen:
                    raise ValueError('Exact abstract text exposure/duplicate; quarantine, do not resample')
                seen.add(extracted['textSha256'])
                record=member|extracted|{'title':population[member['arxivId']]['title'],'sourceURL':url,
                    'retrievedAtUTC':request['startedAtUTC'],'rawResponseFile':request['rawResponseFile'],
                    'rawResponseSha256':request['rawResponseSha256'],
                    'sourceIdentityVerified':True,'semanticIndependenceProven':False,
                    'annotationStatus':'not_annotated','referenceComplete':False,
                    'status':'source_collected_pending_near_duplicate_review_and_annotation',
                    'trainingAuthorized':False,'evaluationAuthorized':False,'independentHumanGold':False}
                records.append(record);request['status']='completed_source_identity_only'
            except Exception as error:
                request.update(status='failed_no_fallback_or_replacement',errorType=type(error).__name__,error=str(error))
            request['endedAtUTC']=datetime.now(UTC).isoformat();requests.append(request)
            p.write(output/'requests.json',requests);p.jsonl(output/'references.jsonl',records)
            print(json.dumps({'devRequests':index,'collected':len(records),'failed':index-len(records),'testRequests':0}),flush=True)
        if p.sha(bundle/'manifest.json')!=manifest_sha or p.sha(bundle/'selected_members.json')!=members_sha:
            raise ValueError('Fixed source cohort drifted during acquisition')
        members(bundle)
        summary={'status':'dev_sources_collected_pending_annotation' if len(records)==20 else 'partial_dev_sources',
            'requestedDevDocuments':20,'collectedDevDocuments':len(records),'failedDevRequests':20-len(records),
            'testRequests':0,'testContentParsed':False,'annotatedDocuments':0,
            'sourceIdentityVerifiedDocuments':len(records),'semanticIndependenceProven':False,
            'trainingAuthorized':False,'evaluationAuthorized':False,'trainingExecuted':False}
        p.write(output/'summary.json',summary)
        with (output/'dev_review.csv').open('w',encoding='utf-8-sig',newline='') as handle:
            fields=['arxivId','title','sourceArxivVersion','sourceURL','textSha256','text','annotationStatus']
            writer=csv.DictWriter(handle,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(records)
        p.write(output/'manifest.json',{'samplingManifestSha256':manifest_sha,'sourceSha256':sources,
            'filesSha256':{x.relative_to(output).as_posix():p.sha(x) for x in output.rglob('*') if x.is_file()}})
        verify(output,bundle);return summary
    except Exception as error:
        p.write(output/'failure_receipt.json',{'status':'failed','errorType':type(error).__name__,
            'error':str(error),'trainingAuthorized':False,'testRequests':0});raise


def verify(folder,bundle):
    folder=Path(folder).resolve();bundle=Path(bundle).resolve()
    manifest=s.read(folder/'manifest.json')
    if manifest['samplingManifestSha256']!=p.sha(bundle/'manifest.json'):raise ValueError('Sampling version drift')
    for name,value in manifest['filesSha256'].items():s.admission.artifact(folder,{'file':name,'sha256':value})
    selected=members(bundle)
    if s.read(folder/'dev_selection_lock.json')['selected']!=selected:raise ValueError('Dev identities changed')
    requests=s.read(folder/'requests.json');rows=s.rows(folder/'references.jsonl')
    if [r['arxivId'] for r in requests]!=[r['arxivId'] for r in selected]:raise ValueError('Request cohort mismatch')
    if any(r['split']!='dev' or r['requestedURL']!='https://arxiv.org/abs/'+r['arxivId'] for r in requests):
        raise ValueError('Forbidden non-dev source request')
    expected=[]
    population={r['arxivId']:r for r in s.rows(bundle/'population.jsonl')}
    for request,member in zip(requests,selected):
        if request['status']!='completed_source_identity_only':continue
        payload=s.admission.artifact(folder,{'file':request['rawResponseFile'],'sha256':request['rawResponseSha256']})
        extracted=parse(payload,member,population[member['arxivId']]['title'])
        expected.append((member['arxivId'],extracted['textSha256'],extracted['text']))
    if expected!=[(r['arxivId'],r['textSha256'],r['text']) for r in rows]:raise ValueError('Dev text/source mismatch')
    if any(r['split']!='dev' or r['annotationStatus']!='not_annotated' or r['referenceComplete'] is not False
           or r['trainingAuthorized'] is not False or r['evaluationAuthorized'] is not False for r in rows):
        raise ValueError('Unreviewed data cannot be promoted')
    summary=s.read(folder/'summary.json')
    expected_summary={'status':'dev_sources_collected_pending_annotation' if len(rows)==20 else 'partial_dev_sources',
        'requestedDevDocuments':20,'collectedDevDocuments':len(rows),'failedDevRequests':20-len(rows),
        'testRequests':0,'testContentParsed':False,'annotatedDocuments':0,'sourceIdentityVerifiedDocuments':len(rows),
        'semanticIndependenceProven':False,'trainingAuthorized':False,'evaluationAuthorized':False,'trainingExecuted':False}
    if summary!=expected_summary:raise ValueError('Collection summary mismatch')
    return summary|{'verification':'passed'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--output',type=Path)
    parser.add_argument('--verify',type=Path)
    args=parser.parse_args()
    if not args.verify and not args.output:parser.error('--output or --verify is required')
    print(json.dumps(verify(args.verify,args.bundle) if args.verify else collect(args.bundle,args.output),ensure_ascii=False,indent=2))
