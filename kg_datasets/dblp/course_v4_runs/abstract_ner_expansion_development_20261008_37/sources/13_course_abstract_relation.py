"""Compile explicit relation revisions on fixed NER labels; unknown pairs remain masked, never negative."""
import argparse
import copy
from collections import Counter
from datetime import UTC,datetime
from pathlib import Path

import course_graph as g
import course_weak as c
import train_course_ner as ner
import train_course_relation as re_model
from course_abstract_v1 import CONTRACT as PARENT,TRAIN,protocol,read,seal

CONTRACT=c.ROOT/'resources/course_abstract_relation_v1.json'
DEV=c.ROOT/'kg_datasets/dblp/course_abstract_dev_reviewed_20261008_35'
NER_FIELDS=('entities','entityStatus','entityReason','groupMentions')

def checked_contract():
    config=read(CONTRACT);_,queue=protocol()
    if (config['version']!='abstract_relation_partial_v1' or config['parentContractSha256']!=c.file_sha256(PARENT)
            or config['maxTokens']!=512 or config['textKind']!='abstract' or config['automaticPromotionAllowed'] is not False):raise ValueError('Relation contract drift')
    return config,queue

def revise(annotation,reference,decision,config):
    result=copy.deepcopy(annotation);entities={e['entityId']:e for e in result['entities']};candidates=c.candidate_pairs(result['entities'])
    pairs={(p['head'],p['tail']):p for p in result['relations']};seen=set();text=reference['text']
    if result['entityStatus']!='complete' or result['groupMentions']:raise ValueError('Cannot resolve pairs in a quarantined NER document')
    for group in decision['groups']:
        quote=group['supportExcerpt'];position=text.find(quote)
        if not quote.strip() or position<0 or text.count(quote)!=1 or not group['reason'].strip():raise ValueError('Relation excerpt absent/ambiguous or reason empty')
        if group['label']=='NO_RELATION' and group.get('negativeBasis') not in config['negativeEvidence']:raise ValueError('Negative requires explicit contrast, not absence')
        if not group['heads'] or not group['tails']:raise ValueError('Empty explicit group')
        for head in group['heads']:
            for tail in group['tails']:
                key=(head,tail)
                if key not in candidates or key in seen or group['label'] not in (candidates[key],'NO_RELATION'):raise ValueError('Duplicate or incompatible explicit pair')
                if pairs[key]['label'] not in ('UNRESOLVED',group['label']):raise ValueError('A conflicting resolved judgment needs a separate explicit retraction')
                seen.add(key);start=min(entities[head]['start'],entities[tail]['start'],position);end=max(entities[head]['end'],entities[tail]['end'],position+len(quote))
                pairs[key]={'head':head,'tail':tail,'label':group['label'],'evidence':{'start':start,'end':end,'text':text[start:end]},'reason':group['reason']}
    result['relations']=[pairs[key] for key in candidates]
    result['relationStatus']='unresolved' if any(p['label']=='UNRESOLVED' for p in result['relations']) else 'complete'
    result['relationReason']='Explicitly unjudged pairs retain UNRESOLVED; no negative filling.' if result['relationStatus']=='unresolved' else ''
    result['reviewOfSha256']=None;result['notes']+=' Relation revision: immutable source NER, explicit source-role decisions only.'
    if c.validate_response(result,reference):raise ValueError('; '.join(c.validate_response(result,reference)))
    return result

def rows_for(refs,receipts):
    docs=[];resolved=[];full=[];excluded=[];unknown=0;all_pairs=0
    for ref,receipt in zip(refs,receipts):
        if c.validate_receipt(receipt,ref):raise ValueError('Invalid source-bound receipt')
        annotation=receipt['annotation'];eligible=c.eligible_tasks(receipt,ref)
        if not eligible['ner']:
            excluded.append({'sampleId':ref['sampleId'],'reason':annotation['entityReason'] or 'Group quarantine'});continue
        common={k:ref[k] for k in ('sampleId','publicationId','groupId','split','textKind','text','textSha256')}
        common.update(referenceSha256=c.canonical_sha256(ref),receiptSha256=receipt['contentSha256'],labelSource='ai_pseudo',contractSha256=c.file_sha256(CONTRACT))
        docs.append(common|{'entities':annotation['entities']});entities={e['entityId']:e for e in annotation['entities']}
        if eligible['relation']:full.append(docs[-1])
        for pair in annotation['relations']:
            all_pairs+=1
            if pair['label']=='UNRESOLVED':unknown+=1;continue
            resolved.append(common|{'head':entities[pair['head']],'tail':entities[pair['tail']],'label':pair['label'],'evidence':pair['evidence'],'reason':pair['reason']})
    return docs,resolved,full,excluded,unknown,all_pairs

def build(decisions_path,reviews_path,output):
    if output.exists():raise FileExistsError('Preserve relation snapshot')
    config,queue=checked_contract();source=read(decisions_path);judgments=read(reviews_path)
    key=lambda item:(item['split'],item['arxivId'])
    decisions={key(d):d for d in source['documents']};reviews={key(j):j for j in judgments['reviews']}
    if (len(decisions)!=len(source['documents']) or len(reviews)!=len(judgments['reviews']) or set(decisions)!=set(reviews)
            or judgments['independent'] is not False or any(s not in ('train','dev') for s,_ in decisions)):raise ValueError('Invalid explicit revision/review cohort')
    output.mkdir(parents=True);collections={};matched=set();summary={'version':config['version'],'documents':{},'relationSupport':{},'unresolvedPairs':{},'knownPairCoverage':{},'completeRelationDocuments':{},'NERExcluded':{},'rejudgedDocuments':{},'testConsumed':False,'trainingExecuted':False,'modelPromoted':False,'qualityPromotionPassed':False}
    def metadata(document,path):return {'provider':document['provider'],'model':document['model'],'promptSha256':c.file_sha256(CONTRACT),'sourceArtifactSha256':c.file_sha256(path),'createdAt':datetime.now(UTC).isoformat()}
    for split,folder in (('train',TRAIN),('dev',DEV)):
        manifest=g.verified_files(folder)
        if any(c.file_sha256(c.ROOT/p)!=sha for p,sha in manifest['inputSha256'].items()):raise ValueError('Upstream annotation source drift')
        refs=c.read_jsonl(folder/'references.jsonl');old=c.read_jsonl(folder/'reviewed_receipts.jsonl');receipts=[];generation=[];origins=[]
        if refs!=c.read_jsonl(queue/(split+'_references.jsonl')) or len(old)!=len(refs):raise ValueError('Locked source cohort changed')
        for ref,prior in zip(refs,old):
            if c.validate_receipt(prior,ref):raise ValueError('Upstream receipt invalid')
            identity=(split,ref['arxivId']);receipt=prior
            if identity in decisions:
                matched.add(identity);response=revise(prior['annotation'],ref,decisions[identity],config)
                initial=c.make_receipt(response,ref,metadata(source,decisions_path));generation.append(initial)
                judgment=reviews[identity]
                if not judgment['reason'].strip() or set(judgment)!={'split','arxivId','reason'}:raise ValueError('Missing actual self-review judgment')
                reviewed=copy.deepcopy(response);reviewed['reviewOfSha256']=initial['contentSha256'];reviewed['notes']+=' Self-review: '+judgment['reason']
                receipt=c.make_receipt(reviewed,ref,metadata(judgments,reviews_path),previous=initial)
            if any(receipt['annotation'][name]!=prior['annotation'][name] for name in NER_FIELDS):raise ValueError('Source NER annotation changed')
            receipts.append(receipt);origins.append({'sampleId':ref['sampleId'],'upstreamReceiptSha256':prior['contentSha256'],'relationRejudged':identity in decisions,'NERReannotated':False})
        collections[split]=(refs,receipts)
        c.write_jsonl(output/(split+'_references.jsonl'),refs);c.write_jsonl(output/(split+'_generation_receipts.jsonl'),generation)
        c.write_jsonl(output/(split+'_reviewed_receipts.jsonl'),receipts);c.write_jsonl(output/(split+'_origins.jsonl'),origins)
        docs,pairs,full,excluded,unknown,total=rows_for(refs,receipts)
        for name,rows in (('ner',docs),('relation',pairs),('full_relation',full),('excluded_ner',excluded)):c.write_jsonl(output/(name+'_'+split+'.jsonl'),rows)
        summary['documents'][split]={'queue':len(refs),'ner':len(docs),'knownPairDocuments':len({p['sampleId'] for p in pairs}),'knownPairs':len(pairs),'allEligiblePairs':total}
        summary['relationSupport'][split]=dict(Counter(p['label'] for p in pairs));summary['unresolvedPairs'][split]=unknown
        summary['knownPairCoverage'][split]=len(pairs)/total;summary['completeRelationDocuments'][split]=len(full);summary['NERExcluded'][split]=len(excluded)
        summary['rejudgedDocuments'][split]=sum(o['relationRejudged'] for o in origins)
    if matched!=set(decisions):raise ValueError('Explicit revision document not found')
    if {r['groupId'] for r in collections['train'][0]}&{r['groupId'] for r in collections['dev'][0]}:raise ValueError('Paper group leakage')
    import os
    os.environ.setdefault('HF_HUB_OFFLINE','1');tokenizer=re_model.prepare_tokenizer(c.ROOT/'kg_datasets/models/scibert_24f92d32')
    for split in ('train','dev'):
        docs=c.read_jsonl(output/('ner_'+split+'.jsonl'));pairs=c.read_jsonl(output/('relation_'+split+'.jsonl'))
        for doc in docs:ner.encode_row(tokenizer,doc,config['maxTokens'])
        encoded=[re_model.encode_pair(tokenizer,p,config['maxTokens']) for p in pairs]
        summary.setdefault('maxMarkedTokens',{})[split]=max(len(e['features']['input_ids']) for e in encoded)
    summary['partialModuleDevelopmentReady']=all(summary['relationSupport'][s].get(label,0)>0 for s in ('train','dev') for label in re_model.LABELS)
    summary['fullDevDocumentCoverage']=summary['completeRelationDocuments']['dev']/summary['documents']['dev']['queue']
    summary['labelIndependence']='same_session_AI_not_human_gold; NER entities frozen; relation decisions made without RE predictions, not an independent blind NER evaluation'
    c.write_json(output/'summary.json',summary);c.write_json(output/'contract.json',config)
    seal(output,[CONTRACT,PARENT,queue/'manifest.json',TRAIN/'manifest.json',DEV/'manifest.json',decisions_path,reviews_path,Path(__file__),c.ROOT/'scripts/course_abstract_v1.py',c.ROOT/'scripts/train_course_ner.py',c.ROOT/'scripts/train_course_relation.py',c.ROOT/'scripts/course_weak.py',c.SCHEMA_PATH,c.ROOT/'kg_datasets/models/scibert_24f92d32/manifest.json'])
    print(__import__('json').dumps(summary))

def load_inputs(folder):
    config,queue=checked_contract();manifest=g.verified_files(folder)
    if read(folder/'contract.json')!=config or any(c.file_sha256(c.ROOT/p)!=sha for p,sha in manifest['inputSha256'].items()):raise ValueError('Relation snapshot input drift')
    data={}
    for split,upstream in (('train',TRAIN),('dev',DEV)):
        refs=c.read_jsonl(folder/(split+'_references.jsonl'));receipts=c.read_jsonl(folder/(split+'_reviewed_receipts.jsonl'));old=c.read_jsonl(upstream/'reviewed_receipts.jsonl')
        if refs!=c.read_jsonl(queue/(split+'_references.jsonl')) or len(refs)!=len(receipts) or len(old)!=len(receipts):raise ValueError('Incomplete locked cohort')
        if any(any(after['annotation'][k]!=before['annotation'][k] for k in NER_FIELDS) for before,after in zip(old,receipts)):raise ValueError('Inherited NER changed')
        expected=rows_for(refs,receipts);names=('ner','relation','full_relation','excluded_ner')
        if any(c.read_jsonl(folder/(name+'_'+split+'.jsonl'))!=rows for name,rows in zip(names,expected)):raise ValueError('Serialized rows differ from reviewed receipts')
        data[split]=dict(zip(names,expected[:4]))
    if {r['groupId'] for r in data['train']['ner']}&{r['groupId'] for r in data['dev']['ner']}:raise ValueError('Cross-split group leakage')
    return config,data

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('decisions','reviews','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    try:build(args.decisions.resolve(),args.reviews.resolve(),args.output.resolve())
    except Exception as error:
        if args.output.exists() and not (args.output/'manifest.json').exists():c.write_json(args.output/'failure.json',{'status':'failed_no_synthetic_fallback','errorType':type(error).__name__,'error':str(error)})
        raise
