"""Partial-label RE development and complete-document NER x RE diagnostics; no test or automatic promotion."""
import argparse
import math
import os
import random
import shutil
import time
from collections import Counter
from datetime import UTC,datetime
from pathlib import Path

import course_graph as g
import course_weak as c
import train_course_ner as ner
import train_course_relation as re_model
from course_abstract_v1 import read,seal
from course_abstract_relation import CONTRACT,load_inputs
from evaluate_course_relation import candidate_rows,predict,score_pipeline
from infer_course_corpus import encode_title

def diagnose(document,entities,reference,predicted):
    positives={re_model.pair_key(p)+(p['label'],) for p in predicted if p['label']!='NO_RELATION'};errors=[]
    for row in reference:
        if row['label']=='NO_RELATION' or re_model.pair_key(row)+(row['label'],) in positives:continue
        flags=[]
        for role in ('head','tail'):
            expected=row[role];overlap=[e for e in entities if e['start']<expected['end'] and expected['start']<e['end']]
            exact=[e for e in overlap if (e['start'],e['end'],e['label'])==(expected['start'],expected['end'],expected['label'])]
            if exact:continue
            if not overlap:flags.append(role+'_missing')
            else:
                if not any(e['label']==expected['label'] for e in overlap):flags.append(role+'_type')
                if not any((e['start'],e['end'])==(expected['start'],expected['end']) for e in overlap):flags.append(role+'_boundary')
        if flags:primary=next(kind for kind in ('missing','type','boundary') if any(f.endswith('_'+kind) for f in flags))
        else:
            primary='RE_decision' if any(re_model.pair_key(p)==re_model.pair_key(row) for p in predicted) else 'candidate_generation'
            flags=[primary]
        errors.append({'sampleId':document['sampleId'],'referencePair':row,'flags':flags,'primaryCause':primary})
    return errors

def compare(config,data,new_checkpoint,tokenizer,collator,device,batch_size,output):
    import torch
    from transformers import BertForTokenClassification,DataCollatorWithPadding
    full=data['dev']['full_relation'];full_ids={d['sampleId'] for d in full};refs=[p for p in data['dev']['relation'] if p['sampleId'] in full_ids]
    if not full or not refs:raise ValueError('No complete-document positive/negative references for pipeline diagnostics')
    ner_predictions={};all_dev=data['dev']['ner'];ner_collator=DataCollatorWithPadding(tokenizer,return_tensors='pt')
    comparison=config['NERComparison'];candidate_run=c.ROOT/Path(comparison['candidateCheckpoint']).parent
    g.verified_files(candidate_run,comparison['candidateRunManifestSha256']);old_result=read(candidate_run/'development_result.json')
    for name,key in (('old','oldCheckpoint'),('new','candidateCheckpoint')):
        path=c.ROOT/comparison[key]
        if c.file_sha256(path/'model.safetensors')!=comparison['oldWeightsSha256' if name=='old' else 'candidateWeightsSha256']:raise ValueError('Frozen NER comparison weights changed')
        model,info=BertForTokenClassification.from_pretrained(path,local_files_only=True,use_safetensors=True,attn_implementation='eager',output_loading_info=True)
        if any(info[k] for k in ('missing_keys','unexpected_keys','mismatched_keys','error_msgs')) or model.config.id2label!=dict(enumerate(c.CONFIG['bioLabels'])):raise ValueError('Invalid NER checkpoint')
        model.to(device).eval();predictions=[];invalid=0
        encoded=[encode_title(tokenizer,{k:doc[k] for k in ('sampleId','text','textSha256')},config['maxTokens'])[0] for doc in all_dev]
        if any(r is None for r in encoded):raise ValueError('NER comparison overlength; no silent truncation')
        with torch.inference_mode():
            for offset in range(0,len(encoded),2):
                chunk=encoded[offset:offset+2];features={k:v.to(device) for k,v in ner_collator([e['features'] for e in chunk]).items()}
                logits=model(**features).logits
                if not torch.isfinite(logits).all():raise ValueError('Nonfinite NER comparison logits')
                for doc,record,labels in zip(all_dev[offset:offset+2],chunk,logits.argmax(-1).cpu().tolist()):
                    decoded=ner.decode_bio(labels[:len(record['offsets'])],record['offsets'],doc['text']);predictions.append(decoded['entities']);invalid+=decoded['invalidTransitions']
        ner_predictions[name]={d['sampleId']:e for d,e in zip(all_dev,predictions)}
        metrics=ner.score_rows(all_dev,predictions,evaluation_target='dev_ai_reference_agreement_not_human_gold')
        if metrics!=(old_result['baselineDev'] if name=='old' else old_result['bestDev'])['metrics']:raise ValueError('Round35 NER dev score differs on identical entity references')
        if name=='new' and predictions!=[p['predictedEntities'] for p in c.read_jsonl(candidate_run/'dev_predictions.jsonl')]:raise ValueError('Frozen candidate NER dev predictions differ')
        c.write_jsonl(output/(name+'_ner_dev_predictions.jsonl'),[{'sampleId':d['sampleId'],'referenceEntities':d['entities'],'predictedEntities':e} for d,e in zip(all_dev,predictions)])
        c.write_json(output/(name+'_ner_dev_metrics.json'),{'metrics':metrics,'invalidTransitions':invalid,'inferenceFeaturesContainLabels':False})
        del model;torch.cuda.empty_cache()
    results={};errors={};module={}
    for re_name,path in (('old',c.ROOT/config['RETraining']['initialization']),('new',new_checkpoint)):
        model=re_model.load_relation_model(path,tokenizer,'entity_markers').to(device)
        known=predict(model,tokenizer,data['dev']['relation'],config['maxTokens'],collator,device,batch_size)
        module[re_name]=re_model.score_relations(data['dev']['relation'],[p['label'] for p in known])
        c.write_jsonl(output/(re_name+'_module_dev_predictions.jsonl'),known)
        for ner_name in ('old','new'):
            name=ner_name+'_NER_'+re_name+'_RE';rows=[p for d in full for p in candidate_rows(d,ner_predictions[ner_name][d['sampleId']])]
            predicted=predict(model,tokenizer,rows,config['maxTokens'],collator,device,batch_size)
            metrics=score_pipeline(full,refs,predicted);metrics['evaluationTarget']='complete_document_dev_AI_reference_not_final_test';metrics['entityScope']='predicted_NER_entities'
            failures=[e for d in full for e in diagnose(d,ner_predictions[ner_name][d['sampleId']],[p for p in refs if p['sampleId']==d['sampleId']],[p for p in predicted if p['sampleId']==d['sampleId']])]
            metrics['missedReferencePrimaryCauses']=dict(Counter(e['primaryCause'] for e in failures))
            assert len(failures)==metrics['positiveMicro']['reference']-metrics['positiveMicro']['truePositive']
            c.write_jsonl(output/(name+'_predictions.jsonl'),predicted);c.write_jsonl(output/(name+'_missed_relations.jsonl'),failures)
            results[name]=metrics;errors[name]=len(failures)
        del model;torch.cuda.empty_cache()
    c.write_jsonl(output/'pipeline_dev_documents.jsonl',full);c.write_jsonl(output/'pipeline_dev_reference_pairs.jsonl',refs)
    result={'evaluationTarget':'AI_reference_dev_diagnostics_not_human_gold','pipelineDocuments':len(full),'queueDocuments':19,'pipelineDocumentCoverage':len(full)/19,
        'zeroReferencePairDocuments':sum(not any(p['sampleId']==d['sampleId'] for p in refs) for d in full),'moduleKnownPairs':len(data['dev']['relation']),
        'moduleScoresConditionalOnKnownPairs':True,'moduleMetrics':module,'pipelineMetrics':results,'endToEndDevEvaluated':True,
        'candidateNERNotRetrained':True,'testEvaluated':False,'modelPromoted':False,'qualityPromotionPassed':False,
        'notice':'Module dev covers explicitly resolved pairs only; pipeline dev covers complete documents including zero pairs. Different denominators. Low full-document coverage and repeated aliases prevent reliability claims; no final-test or production title accuracy.'}
    c.write_json(output/'pipeline_development_result.json',result)
    return result

def run(snapshot,output):
    if output.exists():raise FileExistsError('Preserve relation development run')
    config,data=load_inputs(snapshot);settings=config['RETraining'];initial=c.ROOT/settings['initialization'];weight=initial/'model.safetensors'
    if c.file_sha256(weight)!=settings['initialWeightsSha256']:raise ValueError('Frozen RE initialization weights changed')
    if any(not any(p['label']==label for p in data[s]['relation']) for s in ('train','dev') for label in re_model.LABELS):raise ValueError('Partial three-class development support missing')
    paths=[CONTRACT,snapshot/'manifest.json',weight,initial/'config.json',Path(__file__),c.ROOT/'scripts/course_abstract_relation.py',c.ROOT/'scripts/train_course_relation.py',
        c.ROOT/'scripts/course_relation_model.py',c.ROOT/'scripts/train_course_ner.py',c.ROOT/'scripts/evaluate_course_relation.py',c.ROOT/'scripts/infer_course_corpus.py',c.ROOT/'scripts/course_weak.py']
    paths += [c.ROOT/config['NERComparison'][key]/'model.safetensors' for key in ('oldCheckpoint','candidateCheckpoint')]
    hashes={p.relative_to(c.ROOT).as_posix():c.file_sha256(p) for p in paths};output.mkdir(parents=True);sources=output/'sources';sources.mkdir()
    for i,p in enumerate(paths):
        if p.suffix!='.safetensors':shutil.copy2(p,sources/(str(i)+'_'+p.name))
    state={'status':'running','trainingStarted':False,'testEvaluated':False,'testTokenized':False,'modelPromoted':False,'createdAtUTC':datetime.now(UTC).isoformat(),'settings':settings};c.write_json(output/'status.json',state);started=time.perf_counter()
    try:
        os.environ.setdefault('HF_HUB_OFFLINE','1');os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
        import numpy as np
        import torch
        from transformers import DataCollatorWithPadding
        random.seed(settings['seed']);np.random.seed(settings['seed']);torch.manual_seed(settings['seed']);torch.cuda.manual_seed_all(settings['seed'])
        torch.set_num_threads(4);torch.use_deterministic_algorithms(True);torch.backends.cudnn.benchmark=False;torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        if not torch.cuda.is_available():raise ValueError('CUDA required; no fallback')
        device=torch.device('cuda');tokenizer=re_model.prepare_tokenizer(initial);collator=DataCollatorWithPadding(tokenizer,return_tensors='pt')
        rows={s:data[s]['relation'] for s in ('train','dev')};encoded={s:[re_model.encode_pair(tokenizer,p,config['maxTokens']) for p in pairs] for s,pairs in rows.items()}
        model=re_model.load_relation_model(initial,tokenizer,settings['representation']).to(device);head_before=model.classifier.weight.detach().cpu().clone();encoder_before=model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu().clone()
        evaluate=lambda current:re_model.evaluate_model(current,rows['dev'],encoded['dev'],collator,device,settings['batchSize'])
        baseline=evaluate(model);mapping=re_model.type_majority(rows['train']);majority=re_model.score_relations(rows['dev'],[mapping[p['tail']['label']] for p in rows['dev']])
        clean=lambda evaluation:{k:v for k,v in evaluation.items() if k not in ('predictions','probabilities')}
        c.write_json(output/'baseline_dev.json',clean(baseline));c.write_json(output/'type_majority_dev.json',majority)
        weights=re_model.class_weights(rows['train'],settings['balancedLoss']);loss_weights=torch.tensor(weights,dtype=torch.float32,device=device)
        optimizer=torch.optim.AdamW(model.parameters(),lr=settings['learningRate'],weight_decay=0.01);best_score=None;best=None;best_path=None;steps=[];epochs=[];rng=random.Random(settings['seed'])
        state.update(trainingStarted=True,device='cuda',gpu=torch.cuda.get_device_name(device),classWeights=dict(zip(re_model.LABELS,weights)));c.write_json(output/'status.json',state)
        for epoch in range(1,settings['epochs']+1):
            order=list(range(len(encoded['train'])));rng.shuffle(order)
            for offset in range(0,len(order),settings['batchSize']):
                indices=order[offset:offset+settings['batchSize']];model.train();optimizer.zero_grad(set_to_none=True)
                logits,targets=re_model.forward_batch(model,[encoded['train'][i] for i in indices],collator,device);loss=torch.nn.functional.cross_entropy(logits,targets,weight=loss_weights)
                if not torch.isfinite(loss):raise ValueError('Nonfinite training loss')
                loss.backward();norm=torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
                if not torch.isfinite(norm):raise ValueError('Nonfinite gradient')
                optimizer.step();steps.append({'step':len(steps)+1,'epoch':epoch,'loss':float(loss.detach()),'gradientNorm':float(norm),'pairIds':[re_model.pair_id(rows['train'][i]) for i in indices]})
            c.write_jsonl(output/'steps.jsonl',steps);validation=evaluate(model);score=re_model.selection_score(validation['metrics'],'all_class_macro')
            if ner.dev_checkpoint_improved(score,best_score):
                best_score=score;best=validation;best_path=output/f'checkpoint_epoch_{epoch:02d}';model.save_pretrained(best_path,safe_serialization=True);tokenizer.save_pretrained(best_path)
            record={'epoch':epoch,'steps':len(steps),'dev':clean(validation)};epochs.append(record);c.write_json(output/'epochs.json',epochs);print(__import__('json').dumps({'epoch':epoch,'steps':len(steps),'devMacro':score}),flush=True)
        del model,optimizer;torch.cuda.empty_cache();restored=re_model.load_relation_model(best_path,tokenizer,'entity_markers').to(device);check=evaluate(restored)
        changed=not torch.equal(head_before,restored.classifier.weight.detach().cpu()) and not torch.equal(encoder_before,restored.bert.encoder.layer[0].attention.self.query.weight.detach().cpu())
        if not changed or check['predictions']!=best['predictions']:raise ValueError('Weights unchanged or reload mismatch')
        c.write_jsonl(output/'dev_predictions.jsonl',[{'pairId':re_model.pair_id(p),'sampleId':p['sampleId'],'referenceLabel':p['label'],'predictedLabel':label} for p,label in zip(rows['dev'],best['predictions'])])
        result={'passed':True,'version':config['version'],'steps':len(steps),'epochs':len(epochs),'bestCheckpoint':best_path.name,'baselineDev':clean(baseline),'bestDev':clean(best),'typeMajorityDev':majority,
            'trainPairs':len(rows['train']),'devPairs':len(rows['dev']),'classifierAndEncoderChanged':changed,'reloadPredictionsIdentical':True,'devUsedForGradient':False,
            'selection':'conditional_dev_all_class_macro_f1_earliest_tie','testEvaluated':False,'testTokenized':False,'modelPromoted':False,'qualityPromotionPassed':False,
            'notice':'Warm-started candidate on explicit resolved pairs only; conditional dev metrics, not all-pair accuracy, final test or complete pipeline quality.'}
        c.write_json(output/'development_result.json',result);del restored;torch.cuda.empty_cache()
        comparison=compare(config,data,best_path,tokenizer,collator,device,settings['batchSize'],output)
        assert comparison['moduleMetrics']['new']==best['metrics'] and comparison['moduleMetrics']['old']==baseline['metrics']
        if any(c.file_sha256(c.ROOT/p)!=sha for p,sha in hashes.items()):raise ValueError('Training/inference source drift')
        load_inputs(snapshot);state.update(status='completed',finishedAtUTC=datetime.now(UTC).isoformat(),elapsedSeconds=time.perf_counter()-started,steps=len(steps),endToEndDevEvaluated=True);c.write_json(output/'status.json',state);seal(output,paths)
        print(__import__('json').dumps({'completed':True,'steps':len(steps),'bestCheckpoint':best_path.name,'pipelineDevDocuments':comparison['pipelineDocuments'],'testEvaluated':False}))
    except Exception as error:
        state.update(status='failed_no_synthetic_fallback',errorType=type(error).__name__,error=str(error),elapsedSeconds=time.perf_counter()-started);c.write_json(output/'status.json',state);raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();run(args.snapshot.resolve(),args.output.resolve())
