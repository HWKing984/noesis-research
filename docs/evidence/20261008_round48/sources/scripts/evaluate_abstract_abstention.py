"""Replay one fixed conservative decoder rule against sealed47 logits and exact RE cache."""
import argparse
import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

import evaluate_abstract_decoder as decoder
from course_abstract_v1 import read,seal
from course_bio_abstention import decode_with_abstention

c,g,ner,relation,prior=decoder.c,decoder.g,decoder.ner,decoder.relation,decoder.prior
CONTRACT=c.ROOT/'resources/course_abstract_abstention_v1.json'


def load_inputs():
    config=read(CONTRACT)
    if config['version']!='abstract_structural_abstention_v1' or any(config[k] is not False for k in ('trainingAllowed','labelMutationAllowed','testContentAccessAllowed','automaticPromotionAllowed')): raise ValueError('Abstention contract drift')
    source=c.ROOT/config['source']; manifest=g.verified_files(source,config['sourceManifestSha256'])
    if any(c.file_sha256(c.ROOT/p)!=sha for p,sha in manifest['inputSha256'].items()): raise ValueError('Replay source drift')
    _,data_config,parent,data=decoder.load_inputs()
    train=data['train']['ner']; alignments=c.read_jsonl(c.ROOT/data_config['snapshot']/'token_alignment_train.jsonl')
    if [a['sampleId'] for a in alignments]!=[d['sampleId'] for d in train]: raise ValueError('Training alignment order drift')
    for d,a in zip(train,alignments):
        tags=[0 if tuple(o)==(0,0) else tag for o,tag in zip(a['offsets'],a['labels'])]; expected=[{k:e[k] for k in ('start','end','text','label')} for e in d['entities']]; decoded=decode_with_abstention(tags,a['offsets'],d['text'])
        if decoded['entities']!=expected or decoded['abstainedEntities'] or decoded['rawInvalidTransitions']: raise ValueError('Rule rejects a reviewed training reference span: '+d['sampleId'])
    return config,source,parent,data


def run(output):
    if output.exists(): raise FileExistsError('Preserve abstention experiment')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp/course_v4_runs').resolve()): raise ValueError('Output outside runs')
    config,source,parent,data=load_inputs(); logits=c.read_jsonl(source/'dev_logits.jsonl'); rows=data['dev']['ner']; original=c.read_jsonl(source/'argmax_ner_dev_predictions.jsonl'); cached=c.read_jsonl(source/'argmax_pipeline_predictions.jsonl')
    if [v['sampleId'] for v in logits]!=[d['sampleId'] for d in rows] or [v['sampleId'] for v in original]!=[d['sampleId'] for d in rows] or len({p['pairId'] for p in cached})!=len(cached): raise ValueError('Replay cohort/cache drift')
    paths=[CONTRACT,Path(__file__),c.ROOT/'scripts/course_bio_abstention.py',c.ROOT/'tests/test_abstract_abstention.py',source/'manifest.json',c.ROOT/'resources/course_graph_runtime.json',c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl']
    hashes={p.relative_to(c.ROOT).as_posix():c.file_sha256(p) for p in paths}; output.mkdir(parents=True); c.write_json(output/'selection_lock.json',{'lockedAtUTC':datetime.now(UTC).isoformat(),'contract':config,'inputSha256':hashes})
    state={'status':'running','trainingExecuted':False,'testEvaluated':False,'modelPromoted':False}; c.write_json(output/'status.json',state)
    try:
        predictions=[]; ledger=[]
        for d,v,old in zip(rows,logits,original):
            if v['textSha256']!=d['textSha256'] or hashlib.sha256(d['text'].encode()).hexdigest()!=d['textSha256']: raise ValueError('Replay text binding drift')
            tags=[max(range(len(token)),key=token.__getitem__) for token in v['logits']]; baseline=ner.decode_bio(tags,v['offsets'],d['text'])
            if baseline['entities']!=old['predictedEntities']: raise ValueError('Cached logits argmax parity failed')
            new=decode_with_abstention(tags,v['offsets'],d['text']); predictions.append(new['entities']); ledger.append({'sampleId':d['sampleId'],'textSha256':d['textSha256'],'rawInvalidTransitions':new['rawInvalidTransitions'],'abstainedEntities':new['abstainedEntities']})
        metrics=ner.score_rows(rows,predictions,evaluation_target=prior.TARGET); by_id={d['sampleId']:p for d,p in zip(rows,predictions)}; full=data['dev']['full_relation']; ids={d['sampleId'] for d in full}; refs=[p for p in data['dev']['relation'] if p['sampleId'] in ids]
        cache={p['pairId']:p for p in cached}; scored=[]
        for d in full:
            for p in prior.candidate_rows(d,by_id[d['sampleId']]):
                saved=cache.get(relation.pair_id(p))
                if saved is None or any(saved[k]!=p[k] for k in ('sampleId','text','textSha256','head','tail')): raise ValueError('RE cache input absent/changed')
                scored.append(saved)
        kept={p['pairId'] for p in scored}; dropped=[p for p in cached if p['pairId'] not in kept]; pipeline=prior.dev_scope(prior.score_pipeline(full,refs,scored),'complete_document_exposed_dev_AI_reference_not_final_test')
        fp_counts,false=decoder.error_summary(full,refs,scored); pipeline['endpointMismatch']=fp_counts
        old=read(source/'development_result.json'); compare={'pipelineMetrics':{'old_NER_old_RE':{'positiveMicro':old['frozen42Pipeline']},'new_NER_new_RE':pipeline}}
        gates=prior.gate_results(parent,data,compare,metrics); checks=gates['checks']; checks.update(NERMicroF1Against46=metrics['micro']['f1']>=old['metrics']['argmax']['micro']['f1'],DATASETRecallAgainst46=old['metrics']['argmax']['perClass']['DATASET']['recall']-metrics['perClass']['DATASET']['recall']<=parent['promotionGates']['maxAbsoluteRecallRegression'])
        gates.update(developmentGatesPassed=all(checks.values()),blockedBy=[k for k,v in checks.items() if not v])
        c.write_jsonl(output/'ner_predictions.jsonl',[{'sampleId':d['sampleId'],'referenceEntities':d['entities'],'predictedEntities':p} for d,p in zip(rows,predictions)]); c.write_jsonl(output/'abstention_ledger.jsonl',ledger)
        c.write_jsonl(output/'pipeline_predictions.jsonl',scored); c.write_jsonl(output/'abstained_pairs.jsonl',[p | {'decision':'abstained_structural_endpoint','notice':'Cached label is preserved for audit, not emitted as a relation or relabeled NO_RELATION.'} for p in dropped]); c.write_jsonl(output/'false_relations.jsonl',false)
        c.write_json(output/'development_result.json',{'passed':True,'version':config['version'],'trainReferencePreserved':58,'trainEntityPreserved':678,'devDocuments':len(rows),'metrics':metrics,'pipelineMetrics':pipeline,'baseline46':old['pipelineMetrics']['argmax']['positiveMicro'],'baseline42':old['frozen42Pipeline'],
            'abstainedEntities':sum(len(v['abstainedEntities']) for v in ledger),'abstainedPairs':len(dropped),'exactCacheReplay':True,'gates':gates,'trainingExecuted':False,'testEvaluated':False,'labelsChanged':False,'qualityPromotionPassed':False,'modelPromoted':False,'notice':'Exposed AI-reference dev diagnostic with structural abstention. No additional fit/inference, calibrated correctness or final test.'})
        archive=output/'sources'; archive.mkdir()
        for i,p in enumerate(paths):
            if p.name!='test_references.jsonl':shutil.copy2(p,archive/(str(i)+'_'+p.name))
        if any(c.file_sha256(c.ROOT/p)!=sha for p,sha in hashes.items()):raise ValueError('Replay source drift')
        state.update(status='completed',finishedAtUTC=datetime.now(UTC).isoformat());c.write_json(output/'status.json',state);seal(output,paths)
        print({'completed':True,'abstainedEntities':sum(len(v['abstainedEntities']) for v in ledger),'abstainedPairs':len(dropped),'NERf1':metrics['micro']['f1'],'pipeline':pipeline['positiveMicro'],'blockedBy':gates['blockedBy']})
    except Exception as error:
        c.write_json(output/'status.json',state | {'status':'failed_no_synthetic_fallback','errorType':type(error).__name__,'error':str(error)});raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('preflight','evaluate'));parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.action=='preflight':print({'trainingReferencesPreserved':len(load_inputs()[3]['train']['ner']),'testAccessed':False})
    elif args.output is None:parser.error('New output required')
    else:run(args.output.resolve())
