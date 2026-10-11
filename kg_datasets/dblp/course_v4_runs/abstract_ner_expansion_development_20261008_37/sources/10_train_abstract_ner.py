"""Train a separate abstract NER candidate with existing strict scoring; never reads test text."""
import argparse
import json
import math
import os
import random
import shutil
import time
from collections import Counter
from datetime import UTC,datetime
from functools import partial
from pathlib import Path

import course_graph as g
import course_weak as c
import train_course_ner as ner
from course_abstract_v1 import CONTRACT,TRAIN,protocol,read,seal

def bind_row(row,ref,receipt):
    expected={k:ref[k] for k in ('sampleId','publicationId','groupId','split','textKind','text','textSha256')}
    expected.update(referenceSha256=c.canonical_sha256(ref),receiptSha256=receipt['contentSha256'],labelSource='ai_pseudo',contractSha256=c.file_sha256(CONTRACT),entities=receipt['annotation']['entities'])
    if row!=expected or c.validate_receipt(receipt,ref) or not c.eligible_tasks(receipt,ref)['ner']:raise ValueError('Abstract NER row differs from eligible reviewed receipt')

def load_inputs(snapshot,dev):
    config,queue=protocol();manifest=g.verified_files(snapshot)
    required=[CONTRACT,TRAIN/'manifest.json',dev/'manifest.json',queue/'manifest.json']
    if any(manifest['inputSha256'].get(p.relative_to(c.ROOT).as_posix())!=c.file_sha256(p) for p in required):raise ValueError('Abstract source contract or annotation source differs')
    for name,digest in manifest['inputSha256'].items():
        if c.file_sha256(c.ROOT/name)!=digest:raise ValueError('Abstract snapshot input drift: '+name)
    splits={};groups={}
    for split,folder in (('train',TRAIN),('dev',dev)):
        g.verified_files(folder);refs=c.read_jsonl(folder/'references.jsonl');receipts=c.read_jsonl(folder/'reviewed_receipts.jsonl')
        if refs!=c.read_jsonl(queue/(split+'_references.jsonl')) or len(refs)!=len(receipts):raise ValueError('Locked abstract annotation cohort differs')
        lookup={r['sampleId']:(r,a) for r,a in zip(refs,receipts)};rows=c.read_jsonl(snapshot/('ner_'+split+'.jsonl'))
        excluded=c.read_jsonl(snapshot/('excluded_ner_'+split+'.jsonl'));selected={r['sampleId'] for r in rows};excluded_ids={r['sampleId'] for r in excluded}
        if not rows or len(selected)!=len(rows) or len(excluded_ids)!=len(excluded) or selected&excluded_ids or selected|excluded_ids!=set(lookup):raise ValueError('Missing or duplicate cohort/exclusion record')
        for row in rows:bind_row(row,*lookup[row['sampleId']])
        groups[split]={r['groupId'] for r in refs};splits[split]=rows
    if groups['train']&groups['dev']:raise ValueError('Train/dev paper group leakage')
    return config,splits

def run(snapshot,dev,output):
    if output.exists():raise FileExistsError('Preserve abstract training run')
    config,splits=load_inputs(snapshot,dev);settings=config['NERTraining'];initial=c.ROOT/settings['initialization'];weight=initial/'model.safetensors'
    if c.file_sha256(weight)!=settings['initialWeightsSha256']:raise ValueError('Frozen initialization weights changed')
    inputs=[CONTRACT,snapshot/'manifest.json',dev/'manifest.json',TRAIN/'manifest.json',weight,initial/'config.json',Path(__file__),c.ROOT/'scripts/course_abstract_v1.py',c.ROOT/'scripts/train_course_ner.py',c.ROOT/'scripts/course_weak.py',c.ROOT/'kg_datasets/models/scibert_24f92d32/manifest.json']
    hashes={p.relative_to(c.ROOT).as_posix():c.file_sha256(p) for p in inputs}
    output.mkdir(parents=True);archive=output/'sources';archive.mkdir()
    for index,path in enumerate(inputs):
        if path!=weight:shutil.copy2(path,archive/(str(index)+'_'+path.name))
    state={'status':'running','trainingStarted':False,'testEvaluated':False,'testTokenized':False,'modelPromoted':False,'createdAtUTC':datetime.now(UTC).isoformat(),'settings':settings}
    c.write_json(output/'status.json',state);started=time.perf_counter()
    try:
        os.environ.setdefault('HF_HUB_OFFLINE','1');os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
        import numpy as np
        import torch
        from transformers import BertTokenizerFast,BertForTokenClassification,DataCollatorForTokenClassification
        random.seed(settings['seed']);np.random.seed(settings['seed']);torch.manual_seed(settings['seed']);torch.cuda.manual_seed_all(settings['seed'])
        torch.set_num_threads(4);torch.use_deterministic_algorithms(True);torch.backends.cudnn.benchmark=False
        torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        if not torch.cuda.is_available():raise ValueError('CUDA required; no silent CPU fallback')
        device=torch.device('cuda');tokenizer=BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32',local_files_only=True,do_lower_case=True)
        encoded={s:[ner.encode_row(tokenizer,row,config['maxTokens']) for row in rows] for s,rows in splits.items()}
        model,info=BertForTokenClassification.from_pretrained(initial,local_files_only=True,use_safetensors=True,attn_implementation='eager',output_loading_info=True)
        if any(info[k] for k in ('missing_keys','unexpected_keys','mismatched_keys','error_msgs')) or model.config.id2label!=dict(enumerate(config['bioLabels'])):raise ValueError('Incomplete or incompatible initialization model')
        model.to(device);head_before=model.classifier.weight.detach().cpu().clone();encoder_before=model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu().clone()
        collator=DataCollatorForTokenClassification(tokenizer,padding=True,return_tensors='pt')
        evaluate=partial(ner.evaluate_model,rows=splits['dev'],records=encoded['dev'],target='dev_ai_reference_agreement_not_human_gold',collator=collator,device=device,batch_size=settings['batchSize'])
        baseline=evaluate(model);lexicon=ner.make_dictionary(splits['train']);dictionary=ner.score_rows(splits['dev'],[ner.dictionary_predict(r['text'],lexicon) for r in splits['dev']])
        c.write_json(output/'baseline_dev.json',{k:v for k,v in baseline.items() if k!='predictions'});c.write_json(output/'dictionary_dev.json',dictionary)
        optimizer=torch.optim.AdamW(model.parameters(),lr=settings['learningRate'],weight_decay=0.01)
        state.update(trainingStarted=True,device='cuda',gpu=torch.cuda.get_device_name(device),cudaVersion=torch.version.cuda);c.write_json(output/'status.json',state)
        best_score=None;best_path=None;best=None;epochs=[];steps=[];rng=random.Random(settings['seed'])
        for epoch in range(1,settings['epochs']+1):
            order=list(range(len(encoded['train'])));rng.shuffle(order)
            for start in range(0,len(order),settings['batchSize']):
                indices=order[start:start+settings['batchSize']];batch={k:v.to(device) for k,v in collator([encoded['train'][i]['features'] for i in indices]).items()}
                model.train();optimizer.zero_grad(set_to_none=True);loss=model(**batch).loss
                if not torch.isfinite(loss):raise ValueError('Nonfinite training loss')
                loss.backward();norm=torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
                if not torch.isfinite(norm):raise ValueError('Nonfinite training gradient')
                optimizer.step();steps.append({'step':len(steps)+1,'epoch':epoch,'loss':float(loss.detach()),'gradientNorm':float(norm),'sampleIds':[splits['train'][i]['sampleId'] for i in indices]})
            c.write_jsonl(output/'steps.jsonl',steps);validation=evaluate(model)
            improved=ner.dev_checkpoint_improved(validation['metrics']['micro']['f1'],best_score)
            if improved:
                best_score=validation['metrics']['micro']['f1'];best=validation;best_path=output/f'checkpoint_epoch_{epoch:02d}'
                model.save_pretrained(best_path,safe_serialization=True);tokenizer.save_pretrained(best_path)
            record={'epoch':epoch,'steps':len(steps),'dev':{k:v for k,v in validation.items() if k!='predictions'},'checkpointImproved':improved};epochs.append(record)
            c.write_json(output/'epochs.json',epochs);print(json.dumps(record),flush=True)
        del model,optimizer;torch.cuda.empty_cache()
        reloaded=BertForTokenClassification.from_pretrained(best_path,local_files_only=True,use_safetensors=True,attn_implementation='eager').to(device);recheck=evaluate(reloaded)
        changed=not torch.equal(head_before,reloaded.classifier.weight.detach().cpu()) and not torch.equal(encoder_before,reloaded.bert.encoder.layer[0].attention.self.query.weight.detach().cpu())
        reload_equal=recheck['predictions']==best['predictions']
        if not changed or not reload_equal:raise ValueError('Weights unchanged or checkpoint reload prediction mismatch')
        predictions=[{'sampleId':r['sampleId'],'referenceEntities':r['entities'],'predictedEntities':p} for r,p in zip(splits['dev'],best['predictions'])]
        spans=lambda items:{(e['start'],e['end'],e['label']) for e in items}
        c.write_jsonl(output/'dev_predictions.jsonl',predictions);c.write_jsonl(output/'dev_errors.jsonl',[p for p in predictions if spans(p['referenceEntities'])!=spans(p['predictedEntities'])])
        result={'passed':True,'version':'abstract_v1','trainDocuments':len(splits['train']),'devDocuments':len(splits['dev']),'steps':len(steps),'epochs':settings['epochs'],'bestCheckpoint':best_path.name,
            'baselineDev':{k:v for k,v in baseline.items() if k!='predictions'},'bestDev':{k:v for k,v in best.items() if k!='predictions'},'dictionaryDev':dictionary,
            'entitySupport':{s:dict(Counter(e['label'] for r in rows for e in r['entities'])) for s,rows in splits.items()},
            'classifierAndEncoderChanged':changed,'reloadPredictionsIdentical':reload_equal,'devUsedForGradient':False,'testEvaluated':False,'testTokenized':False,'modelPromoted':False,'qualityPromotionPassed':False,
            'notice':'Warm-started abstract NER development candidate, AI self-reviewed labels only; baseline is title-trained model transferred to this same abstract dev set, not production title accuracy. No complete RE/pipeline training or final-test result.'}
        c.write_json(output/'development_result.json',result)
        if any(c.file_sha256(c.ROOT/p)!=sha for p,sha in hashes.items()):raise ValueError('Training inputs drifted')
        load_inputs(snapshot,dev);state.update(status='completed',finishedAtUTC=datetime.now(UTC).isoformat(),elapsedSeconds=time.perf_counter()-started,peakCUDAbytes=torch.cuda.max_memory_allocated(device),steps=len(steps))
        c.write_json(output/'status.json',state);seal(output,inputs)
        print(json.dumps({'completed':True,'steps':len(steps),'baselineDevF1':baseline['metrics']['micro']['f1'],'candidateDevF1':best_score,'testEvaluated':False}),flush=True)
    except Exception as error:
        state.update(status='failed_no_synthetic_fallback',errorType=type(error).__name__,error=str(error),elapsedSeconds=time.perf_counter()-started);c.write_json(output/'status.json',state);raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('snapshot','dev','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();run(args.snapshot.resolve(),args.dev.resolve(),args.output.resolve())
