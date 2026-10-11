"""Acquire official metadata, lock a real finite sample, retain negative-review candidates."""
import argparse
import csv
import hashlib
import json
import platform
import shutil
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import course_v2_admission as admission
import course_v2_sampling as sampling
import course_v2_training_roster as roster

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'resources/course_v2_sampling_v2.json'
DECISIONS = ROOT/'annotations/course_v4/v2_negative_screening_20261011.json'
OUTPUT = ROOT/'kg_datasets/dblp/course_v2_sampling_20261011_roster_locked'
ADJUDICATION = ROOT/'annotations/course_v4/v2_negative_adjudication_20261011.json'
CORE = ('references.jsonl','generation_receipts.jsonl','reviewed_receipts.jsonl','relation_ledger.jsonl','ner_candidates.jsonl','re_candidates.jsonl')
SOURCES = ('scripts/prepare_v2_sampling.py','scripts/course_v2_sampling.py','scripts/course_v2_admission.py',
    'scripts/course_v2_identity.py','resources/course_v2_sampling_v2.json','annotations/course_v4/v2_negative_screening_20261011.json',
    'tests/test_v2_sampling.py', 'scripts/course_v2_training_roster.py',
    'tests/test_v2_training_roster.py', 'annotations/course_v4/v2_negative_adjudication_20261011.json',
    'scripts/collect_v2_dev.py', 'tests/test_v2_dev_collection.py',
    'scripts/run_v2_roster_checks.py', 'scripts/run_v2_admission_checks.py', 'scripts/harden_v2_identity.py',
    'tests/test_v2_admission.py')
FLAGS = ('trainingAllowed','inferenceAllowed','testContentAccessAllowed','productionMutationAllowed','automaticPromotionAllowed','independentHumanGold')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def jsonl(path, values):
    path.write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in values),encoding='utf-8')


def negatives(old, decisions):
    references = sampling.rows(old/'references.jsonl'); ledger = sampling.rows(old/'relation_ledger.jsonl')
    review_ids = [r['arxivId'] for r in decisions['reviews']]
    if sorted(review_ids) != sorted(r['arxivId'] for r in references): raise ValueError('Twelve-paper screening incomplete')
    review = []
    for r in decisions['reviews']:
        source = next(s for s in references if s['arxivId']==r['arxivId'])
        review.append(r | {'sampleId':source['sampleId'],'textSha256':source['textSha256'],
            'sourceURL':source['sourceURL'],'labelSource':decisions['labelSource'],'trainingAuthorized':False})
    c = decisions['candidate']; source = next(r for r in references if r['arxivId']==c['arxivId'])
    pair = next(r for r in ledger if r['arxivId']==c['arxivId'] and r['head']['entityId']==c['headId'] and r['tail']['entityId']==c['tailId'])
    if pair['label']!=c['priorLabel'] or c['candidateEligible'] is not False or c['trainingAuthorized'] is not False:
        raise ValueError('Do not change or authorize legacy relation')
    spans = {}
    for field in ('negativeQuote','architectureQuote','evaluationQuote'):
        phrase = c[field]
        if source['text'].count(phrase)!=1: raise ValueError('Unambiguous literal negative evidence required')
        start = source['text'].index(phrase); spans[field]={'start':start,'end':start+len(phrase),'text':phrase}
    return review, c | {'sampleId':source['sampleId'],'sourceURL':source['sourceURL'],'textSha256':source['textSha256'],
        'head':pair['head'],'tail':pair['tail'],'evidenceSpans':spans,'sourceLedgerRecordSha256':admission.digest(pair),
        'labelSource':decisions['labelSource'],'independentHumanGold':False}


def prepare(output=OUTPUT,cached_listing=None):
    output=Path(output).resolve()
    if output.exists(): raise FileExistsError('Preserve existing sampling attempt: '+str(output))
    protocol=sampling.read(CONFIG); old=ROOT/protocol['parent']; parent_manifest=sha(old/'manifest.json')
    if any(protocol[k] is not False for k in FLAGS): raise ValueError('Metadata-only authorization contract')
    if protocol['sourceURL']!='https://arxiv.org/list/'+protocol['category']+'/'+protocol['listingMonth']:
        raise ValueError('Month/category/source contract mismatch')
    inputs={p:sha(ROOT/p) for p in SOURCES}; exclusions=sampling.rows(old/'historical_exclusions.jsonl'); aliases=sampling.read(old/'identity_alias_index.json')
    protection=sampling.read(old/'production_protection.json')
    if any(sha(ROOT/p)!=h for p,h in protection.items()): raise ValueError('V1 protection hash changed')
    train=sampling.read(old/'split_lock.json')['assignments']
    title_path=old/'audit_parent/metadata_sources/publications.csv'
    with title_path.open(encoding='utf-8-sig',newline='') as handle:
        title_rows=[{'publicationId':r['publicationId:ID(Publication)'],'title':r['title']} for r in csv.DictReader(handle)]
    cached_receipt=None
    if cached_listing is not None:
        cached_listing=Path(cached_listing).resolve();cached_manifest=sampling.read(cached_listing/'manifest.json')
        cached_receipt=sampling.read(cached_listing/'acquisition_receipt.json')
        if cached_receipt['status']!='completed':raise ValueError('Cached acquisition is not completed')
        for record in cached_receipt['sourcePages']:
            if sha(cached_listing/record['file'])!=record['sha256'] or cached_manifest['filesSha256'][record['file']]!=record['sha256']:
                raise ValueError('Cached listing source changed')
    output.mkdir(parents=True); (output/'sources').mkdir()
    acquired=[]; receipt={'status':'running','startedAtUTC':datetime.now(UTC).isoformat(),'protocolSha256':admission.digest(protocol),
        'protocolFileSha256':inputs[CONFIG.relative_to(ROOT).as_posix()],'sourcePages':acquired,'abstractsFetched':0,
        'testContentParsed':False,'notice':'Metadata listing GET only; no /abs/, /pdf/, /html/ or API abstract retrieval.'}
    write(output/'acquisition_receipt.json',receipt)
    try:
        # The fixed parent is needed before constructing the formal prelock.
        shutil.copytree(old,output/'audit_parent')
        write(output/'training_roster_lock.json',roster.expected(output/'audit_parent'))
        pages=[]; offset=0; total=None
        while total is None or offset<total:
            url=protocol['sourceURL']+'?skip='+str(offset)+'&show='+str(protocol['pageSize'])
            if cached_receipt is not None:
                record=next(r for r in cached_receipt['sourcePages'] if r['sourceURL']==url)
                payload=(cached_listing/record['file']).read_bytes();fetched_at=record['fetchedAtUTC']
            else:
                request=urllib.request.Request(url,headers={'User-Agent':'AI-Literature-KG/2.0 metadata-only course sampling'})
                with urllib.request.urlopen(request,timeout=25) as response:
                    if response.status!=200 or response.geturl()!=url: raise ValueError('Unexpected metadata response/redirect')
                    payload=response.read()
                fetched_at=datetime.now(UTC).isoformat()
            reported, records=sampling.parse_listing(payload)
            if total is not None and reported!=total: raise ValueError('Listing changed; preserve failed acquisition')
            total=reported; path=output/'sources'/('listing_'+str(offset)+'.html'); path.write_bytes(payload)
            acquired.append({'file':path.relative_to(output).as_posix(),'sha256':sha(path),'sourceURL':url,'status':200,
                'fetchedAtUTC':fetched_at,'reusedRecordedAcquisition':cached_receipt is not None,'records':len(records),'bytes':len(payload)})
            write(output/'acquisition_receipt.json',receipt)
            pages.append({'sourceURL':url,'payload':payload}); offset+=len(records)
        eligible,rejected,total=sampling.population(pages,protocol,exclusions,aliases,title_rows); selected=sampling.draw(eligible,protocol)
        jsonl(output/'population.jsonl',eligible);jsonl(output/'excluded_population.jsonl',rejected)
        write(output/'selected_members.json',selected);write(output/'sampling_protocol.json',protocol)
        frame={'version':'sampling_frame_v1','samplingFrameLocked':True,'fullDBLPRepresentative':False,
            'protocolSha256':admission.digest(protocol),'exclusionsSha256':admission.digest(exclusions),'aliasIndexSha256':admission.digest(aliases),
            'sourcePages':acquired,'sourceListingCount':total,'eligiblePopulationCount':len(eligible),'excludedPopulationCount':len(rejected),
            'populationSha256':admission.digest(eligible),'selectedMembersSha256':admission.digest(selected),
            'seed':protocol['seed'],'samplingMethod':protocol['samplingMethod'],'samplingPython':platform.python_version(),
            'selectionCounts':{'dev':protocol['devSize'],'test':protocol['testSize'],'challenge':0},
            'inclusionProbabilities':{'dev':protocol['devSize']/len(eligible),'test':protocol['testSize']/len(eligible)},
            'contentBindingCompleted':False,'evaluationAuthorized':False,'scope':protocol['scope']}
        title_target=output/'sources/historical_publications.csv';shutil.copy2(title_path,title_target)
        frame['historicalTitleSource']={'file':title_target.relative_to(output).as_posix(),'sha256':sha(title_target)}
        frame['historicalTitleQuarantines']=sum('quarantineReason' in r for r in rejected)
        write(output/'sampling_frame.json',frame)
        lock=sampling.prelock(output,train,exclusions,aliases);write(output/'evaluation_lock.json',lock)
        screening,candidate=negatives(old,sampling.read(DECISIONS));jsonl(output/'negative_screening.jsonl',screening)
        jsonl(output/'negative_candidates.jsonl',[candidate])
        with (output/'negative_review_queue.csv').open('w',encoding='utf-8-sig',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=['arxivId','head','tail','priorLabel','proposedLabel','evidence','scopeQuestion','reviewStatus'])
            writer.writeheader();writer.writerow({'arxivId':candidate['arxivId'],'head':candidate['head']['text'],'tail':candidate['tail']['text'],
                'priorLabel':candidate['priorLabel'],'proposedLabel':candidate['proposedLabel'],'evidence':candidate['architectureQuote'],
                'scopeQuestion':candidate['counterargument'],'reviewStatus':candidate['reviewStatus']})
        # Parent is immutable; full historical replay remains available without local models.
        adjudication=sampling.read(ADJUDICATION)
        audit=Path('D:/Users/Y7000P/Downloads')/adjudication['auditFile']
        if sha(audit)!=adjudication['auditSha256']: raise ValueError('Independent audit source drift')
        shutil.copy2(audit,output/adjudication['auditFile'])
        write(output/'negative_adjudication.json',adjudication)
        for p in SOURCES:
            target=output/'source_snapshot'/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/p,target)
        summary={'status':'train_roster_locked_dev_content_and_negative_supervision_pending','trainDocuments':12,
            'sourceListingCount':total,'eligiblePopulationCount':len(eligible),'excludedPopulationCount':len(rejected),
            'devDocuments':protocol['devSize'],'testDocuments':protocol['testSize'],'challengeDocuments':0,
            'samplingFrameLocked':True,'evaluationInventoryLocked':True,'trainingRosterLocked':True,'finalContentBindingCompleted':False,
            'evaluationAuthorized':False,'trainingAuthorized':False,'trainingExecuted':False,'inferenceExecuted':False,
            'abstractsFetched':0,'testContentParsed':False,'screenedTrainDocuments':12,'proposedNegativePairs':1,'acceptedNegativePairs':0,
            'legacyCoreChanged':False,'activeMetadataGuard':'scripts/course_v2_sampling.py:prelock',
            'activeFinalGuard':'scripts/course_v2_sampling.py:finalize','independentHumanGold':False,'fullDBLPRepresentative':False}
        write(output/'summary.json',summary)
        if any(sha(ROOT/p)!=h for p,h in inputs.items()) or any(sha(ROOT/p)!=h for p,h in protection.items()) or sha(old/'manifest.json')!=parent_manifest:
            raise ValueError('Inputs/parent/V1 changed')
        receipt.update(status='completed',endedAtUTC=datetime.now(UTC).isoformat());write(output/'acquisition_receipt.json',receipt)
        write(output/'manifest.json',{'version':'sampling_bundle_v1','parentManifestSha256':parent_manifest,'inputSha256':inputs,
            'filesSha256':{p.relative_to(output).as_posix():sha(p) for p in output.rglob('*') if p.is_file()}})
        verify(output);return summary
    except Exception as error:
        receipt.update(status='failed',error=str(error),endedAtUTC=datetime.now(UTC).isoformat());write(output/'acquisition_receipt.json',receipt);raise


def verify(bundle):
    bundle=Path(bundle).resolve(); manifest=sampling.read(bundle/'manifest.json');old=bundle/'audit_parent'
    for p,h in manifest['filesSha256'].items():
        target=(bundle/p).resolve()
        if not target.is_relative_to(bundle) or sha(target)!=h: raise ValueError('Sampling bundle file drift: '+p)
    if sha(old/'manifest.json')!=manifest['parentManifestSha256']: raise ValueError('Parent binding drift')
    protocol=sampling.read(bundle/'sampling_protocol.json')
    if protocol!=sampling.read(bundle/'source_snapshot/resources/course_v2_sampling_v2.json') or any(protocol[k] is not False for k in FLAGS):
        raise ValueError('Sampling protocol/authorization drift')
    for p,h in manifest['inputSha256'].items():
        if sha(bundle/'source_snapshot'/p)!=h: raise ValueError('Source snapshot drift')
    excluded=sampling.rows(old/'historical_exclusions.jsonl');aliases=sampling.read(old/'identity_alias_index.json')
    selected,frame=sampling.validate_frame(bundle,excluded,aliases)
    if frame['historicalTitleSource']['sha256'] != sha(old/'audit_parent/metadata_sources/publications.csv'):
        raise ValueError('Historical title source differs from frozen corpus')
    lock=sampling.prelock(bundle,sampling.read(old/'split_lock.json')['assignments'],excluded,aliases)
    if lock!=sampling.read(bundle/'evaluation_lock.json'): raise ValueError('Evaluation prelock drift')
    screening,candidate=negatives(old,sampling.read(bundle/'source_snapshot/annotations/course_v4/v2_negative_screening_20261011.json'))
    if sampling.rows(bundle/'negative_screening.jsonl')!=screening or sampling.rows(bundle/'negative_candidates.jsonl')!=[candidate]:
        raise ValueError('Negative screening/source drift')
    adjudication=sampling.read(bundle/'negative_adjudication.json')
    if (adjudication!=sampling.read(bundle/'source_snapshot'/ADJUDICATION.relative_to(ROOT))
            or sha(bundle/adjudication['auditFile'])!=adjudication['auditSha256']
            or adjudication['finalLabel']!='UNRESOLVED' or adjudication['candidateEligible'] is not False
            or adjudication['trainingAuthorized'] is not False):
        raise ValueError('Negative adjudication/source drift')
    summary=sampling.read(bundle/'summary.json')
    expected={'status':'train_roster_locked_dev_content_and_negative_supervision_pending','trainDocuments':12,
        'sourceListingCount':frame['sourceListingCount'],'eligiblePopulationCount':frame['eligiblePopulationCount'],
        'excludedPopulationCount':frame['excludedPopulationCount'],'devDocuments':protocol['devSize'],'testDocuments':protocol['testSize'],
        'challengeDocuments':0,'samplingFrameLocked':True,'evaluationInventoryLocked':True,'trainingRosterLocked':True,'finalContentBindingCompleted':False,
        'evaluationAuthorized':False,'trainingAuthorized':False,'trainingExecuted':False,'inferenceExecuted':False,
        'abstractsFetched':0,'testContentParsed':False,'screenedTrainDocuments':12,'proposedNegativePairs':1,'acceptedNegativePairs':0,
        'legacyCoreChanged':False,'activeMetadataGuard':'scripts/course_v2_sampling.py:prelock',
        'activeFinalGuard':'scripts/course_v2_sampling.py:finalize','independentHumanGold':False,'fullDBLPRepresentative':False}
    if summary != expected:
        raise ValueError('Incomplete status must remain explicit')
    return {'status':'passed','sourceListingCount':frame['sourceListingCount'],'eligiblePopulationCount':frame['eligiblePopulationCount'],
        'metadataMembers':len(selected),'counts':lock['counts'],'samplingFrameLocked':True,'trainingRosterLocked':True,'contentBindingCompleted':False,
        'acceptedNegativePairs':0,'trainingAuthorized':False,'evaluationAuthorized':False,'semanticIndependenceProven':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);parser.add_argument('--output',type=Path,default=OUTPUT);parser.add_argument('--verify',type=Path);parser.add_argument('--cached-listing',type=Path)
    args=parser.parse_args();print(json.dumps(verify(args.verify) if args.verify else prepare(args.output,args.cached_listing),ensure_ascii=False,indent=2))
