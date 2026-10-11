"""Source-bound supplementary dev receipts; reuse occurrence-aware labeling and original rules."""
import argparse
import copy
import sys
from collections import Counter
from datetime import UTC,datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'scripts'))
import prepare_supplementary_dev as p
from revise_contextual_abstracts import response_for


def response(decision,ref):
    if 'occurrenceMentions' not in decision: return p.compile_decision(decision,ref)
    return response_for(decision | {'mentions':decision['occurrenceMentions'],'entityStatus':decision.get('entityStatus','complete'),'reason':decision['notes'],'relationGroups':decision['groups']},ref)


def run(source,decisions_path,output,reviews_path=None):
    p.checked_new(output); config=p.locked(); manifest=p.g.verified_files(source)
    if any(p.c.file_sha256(ROOT/name)!=sha for name,sha in manifest['inputSha256'].items()): raise ValueError('Supplementary source drift')
    refs=p.c.read_jsonl(source/'references.jsonl'); decisions=p.read(decisions_path); docs=decisions['documents']
    if [d['arxivId'] for d in docs]!=[r['arxivId'] for r in refs] or any(r['split']!='dev' or r['textKind']!='abstract' for r in refs) or not refs: raise ValueError('Wrong development decision scope')
    reviews=p.read(reviews_path) if reviews_path else None; initial=p.c.read_jsonl(source/'generation_receipts.jsonl') if reviews else []
    if reviews and (reviews['independent'] is not False or [r['arxivId'] for r in reviews['reviews']]!=[r['arxivId'] for r in refs] or len(initial)!=len(refs)): raise ValueError('Review does not cover fixed generation')
    def metadata(document,path): return {'provider':document['provider'],'model':document['model'],'promptSha256':p.c.file_sha256(p.CONTRACT),'sourceArtifactSha256':p.c.file_sha256(path),'createdAt':datetime.now(UTC).isoformat()}
    receipts=[]
    for i,(ref,decision) in enumerate(zip(refs,docs)):
        annotation=response(decision,ref)
        if reviews:
            reason=reviews['reviews'][i]['reason']
            if annotation!=initial[i]['annotation'] or not reason.strip(): raise ValueError('Review confirmation or generation changed')
            annotation=copy.deepcopy(annotation); annotation['reviewOfSha256']=initial[i]['contentSha256']; annotation['notes']+=' Actual same-session source review: '+reason
            receipts.append(p.c.make_receipt(annotation,ref,metadata(reviews,reviews_path),previous=initial[i]))
        else: receipts.append(p.c.make_receipt(annotation,ref,metadata(decisions,decisions_path)))
    output.mkdir(parents=True)
    try:
        p.c.write_jsonl(output/'references.jsonl',refs); p.c.write_jsonl(output/('reviewed_receipts.jsonl' if reviews else 'generation_receipts.jsonl'),receipts)
        summary={'lockedQueue':len(config['seeds']),'annotated':len(refs),'selfReviewed':bool(reviews),'independentHumanGold':False,'trainingExecuted':False,'inferenceExecuted':False,'testEvaluated':False,'modelPromoted':False,'qualityPromotionPassed':False,'selectionBias':config['selection'],'oldDevUnchanged':True}
        paths=p.inputs()+[Path(__file__),ROOT/'scripts/revise_contextual_abstracts.py',source/'manifest.json',decisions_path,ROOT/'tests/test_supplementary_occurrences.py']
        if reviews:
            paths.append(reviews_path); rows,pairs,full,excluded,unknown,total=p.rows_for(refs,receipts); tokenizer=p.relation.prepare_tokenizer(ROOT/'kg_datasets/models/scibert_24f92d32'); alignment=[]
            for row in rows:
                encoded=p.ner.encode_row(tokenizer,row,512); offsets=encoded['offsets']; labels=encoded['features']['labels']; decoded=p.ner.decode_bio([0 if tuple(o)==(0,0) else t for t,o in zip(labels,offsets)],offsets,row['text'])
                if decoded['invalidTransitions'] or decoded['entities']!=[{k:e[k] for k in ('start','end','text','label')} for e in row['entities']]: raise ValueError('Strict BIO failed')
                alignment.append({'sampleId':row['sampleId'],'offsets':offsets,'labels':labels})
            for pair in pairs: p.relation.encode_pair(tokenizer,pair,512)
            for name,values in [('ner_dev',rows),('relation_dev',pairs),('full_relation_dev',full),('excluded_ner',excluded),('token_alignment',alignment)]: p.c.write_jsonl(output/(name+'.jsonl'),values)
            full_ids={r['sampleId'] for r in full}; evals=[r for r in pairs if r['label']=='EVALUATED_ON']; full_evals=[r for r in evals if r['sampleId'] in full_ids]
            summary.update(NER=len(rows),entities=dict(Counter(e['label'] for r in rows for e in r['entities'])),knownPairs=len(pairs),eligiblePairs=total,unknownPairs=unknown,relationSupport=dict(Counter(r['label'] for r in pairs)),completeDocuments=len(full),completeCoverage=len(full)/len(config['seeds']),EVALSourcePapers=len({r['sampleId'] for r in evals}),completeEVALSupport=len(full_evals),completeEVALPapers=len({r['sampleId'] for r in full_evals}),quarantinedNER=len(excluded),strictBIOPassed=True)
        p.c.write_json(output/'summary.json',summary); p.c.write_json(output/'contract.json',config); p.seal(output,paths); print(summary,flush=True)
    except Exception as error:
        p.c.write_json(output/'failure.json',{'status':'failed_no_synthetic_fallback','errorType':type(error).__name__,'error':str(error)}); raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('source','decisions','output'): parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--reviews',type=Path); args=parser.parse_args(); run(args.source.resolve(),args.decisions.resolve(),args.output.resolve(),args.reviews.resolve() if args.reviews else None)
