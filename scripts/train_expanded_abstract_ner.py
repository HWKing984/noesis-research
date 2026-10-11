"""Data-only abstract NER experiment with frozen dev labels and old RE; never reads held-out content."""
import argparse
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
from collect_train_abstracts import CONTRACT,protocol,selection
from course_abstract_v1 import read,seal
from train_abstract_ner import load_inputs as old_inputs
from course_abstract_relation import load_inputs as relation_inputs
from evaluate_course_relation import candidate_rows,predict,score_pipeline
from infer_course_corpus import encode_title
from train_abstract_relation import diagnose

BASE_SNAPSHOT=c.ROOT/'kg_datasets/dblp/course_abstract_v1_inputs_20261008_35'
RE_SNAPSHOT=c.ROOT/'kg_datasets/dblp/course_abstract_relation_inputs_20261008_36'
RE_RUN=c.ROOT/'kg_datasets/dblp/course_v4_runs/abstract_relation_development_20261008_36'

def additions(source,reviewed):
    source_manifest=g.verified_files(source);mf=g.verified_files(reviewed)
    for key,sha in source_manifest['inputSha256'].items():
        if c.file_sha256(c.ROOT/key)!=sha:raise ValueError('Expansion collection input drift: '+key)
    if read(source/'selection_lock.json')['selected']!=selection()[2]:raise ValueError('Source selection differs from pre-locked train policy')
    for key,sha in mf['inputSha256'].items():
        if c.file_sha256(c.ROOT/key)!=sha:raise ValueError('New train annotation input drift: '+key)
    refs=c.read_jsonl(source/'train_references.jsonl');receipts=c.read_jsonl(reviewed/'reviewed_receipts.jsonl')
    if refs!=c.read_jsonl(reviewed/'references.jsonl') or len(receipts)!=len(refs) or len({r['sampleId'] for r in refs})!=len(refs):raise ValueError('Incomplete expansion annotation cohort')
    _,parent=protocol();records={r['arxivId']:r for r in c.read_jsonl(source/'abstracts.jsonl')};locked={r['arxivId']:r for r in read(source/'selection_lock.json')['selected']}
    for ref,receipt in zip(refs,receipts):
        raw=records[ref['arxivId']];selected_row=locked[ref['arxivId']]
        if ref['split']!='train' or ref['textKind']!='abstract' or ref['tokens']>parent['maxTokens'] or not raw['title_match'] or ref['text']!=raw['abstract'] or ref['textSha256']!=raw['content_hash'] or any(ref[k]!=selected_row[k] for k in ('publicationId','groupId','split')):raise ValueError('Expansion source identity, split or text mismatch')
        if c.validate_receipt(receipt,ref) or receipt['review'] is None:raise ValueError('Invalid or unreviewed expansion receipt')
    return list(zip(refs,receipts))

def new_row(ref,receipt,parent):
    if not c.eligible_tasks(receipt,ref)['ner']:return None
    row={k:ref[k] for k in ('sampleId','publicationId','groupId','split','textKind','text','textSha256')}
    row.update(referenceSha256=c.canonical_sha256(ref),receiptSha256=receipt['contentSha256'],labelSource='ai_pseudo',contractSha256=c.file_sha256(parent),entities=receipt['annotation']['entities'])
    return row

def snapshot(source,reviewed,output):
    if output.exists():raise FileExistsError('Preserve expanded input snapshot')
    config,parent=protocol();_,base=old_inputs(BASE_SNAPSHOT,c.ROOT/config['dev']);pairs=additions(source,reviewed)
    old_groups={r['groupId'] for split in base.values() for r in split};all_groups=[ref['groupId'] for ref,_ in pairs]
    if set(all_groups)&old_groups or len(set(all_groups))!=len(all_groups):raise ValueError('Duplicate or conflicting source paper group')
    os.environ.setdefault('HF_HUB_OFFLINE','1')
    from transformers import BertTokenizerFast
    tokenizer=BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32',local_files_only=True,do_lower_case=True)
    added=[];excluded=[];alignment=[]
    for ref,receipt in pairs:
        row=new_row(ref,receipt,c.ROOT/config['parentContract'])
        if row is None:
            excluded.append({'sampleId':ref['sampleId'],'reason':receipt['annotation']['entityReason'] or 'Coordinated group unresolved'});continue
        try:
            encoded=ner.encode_row(tokenizer,row,parent['maxTokens']);offsets=encoded['offsets'];labels=encoded['features']['labels']
            decoded=ner.decode_bio([0 if tuple(o)==(0,0) else label for o,label in zip(offsets,labels)],offsets,row['text'])
            if decoded['invalidTransitions'] or decoded['entities']!=[{k:e[k] for k in ('start','end','text','label')} for e in row['entities']]:raise ValueError('BIO strict round-trip mismatch')
        except ValueError as error:
            excluded.append({'sampleId':ref['sampleId'],'reason':str(error)});continue
        added.append(row);alignment.append({'sampleId':ref['sampleId'],'offsets':offsets,'labels':labels,'tokens':len(offsets)})
    if not added:raise ValueError('No strictly aligned additional train documents')
    output.mkdir(parents=True)
    c.write_jsonl(output/'ner_train.jsonl',base['train']+added);c.write_jsonl(output/'ner_dev.jsonl',base['dev']);c.write_jsonl(output/'additional_train.jsonl',added)
    c.write_jsonl(output/'excluded_additional_train.jsonl',excluded);c.write_jsonl(output/'additional_alignment.jsonl',alignment)
    summary={'version':config['version'],'previousTrain':len(base['train']),'additionalQueue':len(pairs),'additionalEligible':len(added),'additionalExcluded':len(excluded),
        'trainDocuments':len(base['train'])+len(added),'devDocuments':len(base['dev']),'trainEntitySupport':dict(Counter(e['label'] for row in base['train']+added for e in row['entities'])),
        'devRowsUnchanged':True,'devRowsSha256':c.canonical_sha256(base['dev']),'testConsumed':False,'trainingExecuted':False,'modelPromoted':False}
    c.write_json(output/'summary.json',summary)
    seal(output,[CONTRACT,c.ROOT/config['parentContract'],BASE_SNAPSHOT/'manifest.json',source/'manifest.json',reviewed/'manifest.json',Path(__file__),
        c.ROOT/'scripts/collect_train_abstracts.py',c.ROOT/'scripts/train_abstract_ner.py',c.ROOT/'scripts/train_course_ner.py'])
    print(__import__('json').dumps(summary),flush=True)

def load_inputs(folder,source,reviewed):
    config,parent=protocol();manifest=g.verified_files(folder)
    paths=[CONTRACT,c.ROOT/config['parentContract'],BASE_SNAPSHOT/'manifest.json',source/'manifest.json',reviewed/'manifest.json']
    if any(manifest['inputSha256'].get(p.relative_to(c.ROOT).as_posix())!=c.file_sha256(p) for p in paths):raise ValueError('Expansion snapshot source differs')
    for key,sha in manifest['inputSha256'].items():
        if c.file_sha256(c.ROOT/key)!=sha:raise ValueError('Expansion snapshot input drift: '+key)
    _,base=old_inputs(BASE_SNAPSHOT,c.ROOT/config['dev']);pairs=additions(source,reviewed);lookup={r['sampleId']:(r,a) for r,a in pairs}
    rows={s:c.read_jsonl(folder/('ner_'+s+'.jsonl')) for s in ('train','dev')};added=c.read_jsonl(folder/'additional_train.jsonl');excluded=c.read_jsonl(folder/'excluded_additional_train.jsonl')
    ids={r['sampleId'] for r in added};excluded_ids={r['sampleId'] for r in excluded}
    if not added or len(ids)!=len(added) or len(excluded_ids)!=len(excluded) or ids&excluded_ids or ids|excluded_ids!=set(lookup):raise ValueError('Missing or duplicated additional cohort')
    preflight=c.read_jsonl(reviewed/'token_alignment.jsonl')
    if {r['sampleId'] for r in preflight if r['strictAlignmentPassed']}!=ids:raise ValueError('Expansion eligibility differs from reviewed token preflight')
    failed={r['sampleId']:r['exclusionReason'] for r in preflight if not r['strictAlignmentPassed']}
    if {r['sampleId']:r['reason'] for r in excluded}!=failed:raise ValueError('Expansion exclusion evidence changed')
    if rows['train']!=base['train']+added or rows['dev']!=base['dev']:raise ValueError('Old train/dev rows changed')
    for row in added:
        ref,receipt=lookup[row['sampleId']]
        if row!=new_row(ref,receipt,c.ROOT/config['parentContract']):raise ValueError('Additional row differs from canonical receipt')
    groups=[r['groupId'] for r in rows['train']+rows['dev']]
    if len(set(groups))!=len(groups):raise ValueError('Paper-group leakage or duplicates')
    return config,parent,rows

def pipeline_dev(model,predictions,rows,device,output):
    import torch
    from transformers import DataCollatorWithPadding
    config,data=relation_inputs(RE_SNAPSHOT);g.verified_files(RE_RUN)
    full=data['dev']['full_relation'];ids={r['sampleId'] for r in full};refs=[p for p in data['dev']['relation'] if p['sampleId'] in ids]
    fields=('sampleId','publicationId','groupId','split','textKind','text','textSha256','entities')
    if [{k:r[k] for k in fields} for r in rows]!=[{k:r[k] for k in fields} for r in data['dev']['ner']]:raise ValueError('Pipeline NER development cohort or entities changed')
    tokenizer=re_model.prepare_tokenizer(c.ROOT/config['RETraining']['initialization']);collator=DataCollatorWithPadding(tokenizer,return_tensors='pt')
    # Re-infer without labels; reference entities never enter candidate generation.
    encoded=[encode_title(tokenizer,{k:r[k] for k in ('sampleId','text','textSha256')},512)[0] for r in rows];inferred=[];model.eval()
    if any(r is None for r in encoded):raise ValueError('Pipeline abstract overlength; no truncation')
    with torch.inference_mode():
        for start in range(0,len(encoded),2):
            chunk=encoded[start:start+2];batch={k:v.to(device) for k,v in collator([r['features'] for r in chunk]).items()};logits=model(**batch).logits
            if not torch.isfinite(logits).all():raise ValueError('Nonfinite label-free NER logits')
            for doc,record,tags in zip(rows[start:start+2],chunk,logits.argmax(-1).cpu().tolist()):inferred.append(ner.decode_bio(tags[:len(record['offsets'])],record['offsets'],doc['text'])['entities'])
    if inferred!=predictions:raise ValueError('Label-free NER inference differs from saved development predictions')
    by_id={r['sampleId']:p for r,p in zip(rows,inferred)};pairs=[p for doc in full for p in candidate_rows(doc,by_id[doc['sampleId']])]
    old_re=c.ROOT/config['RETraining']['initialization']
    if c.file_sha256(old_re/'model.safetensors')!=config['RETraining']['initialWeightsSha256']:raise ValueError('Fixed old RE changed')
    relation_model=re_model.load_relation_model(old_re,tokenizer,'entity_markers').to(device);predicted=predict(relation_model,tokenizer,pairs,512,collator,device,4)
    metric=score_pipeline(full,refs,predicted);errors=[e for d in full for e in diagnose(d,by_id[d['sampleId']],[p for p in refs if p['sampleId']==d['sampleId']],[p for p in predicted if p['sampleId']==d['sampleId']])]
    metric['missedReferencePrimaryCauses']=dict(Counter(e['primaryCause'] for e in errors))
    baseline={}
    for name in ('old_NER_old_RE','new_NER_old_RE'):
        saved=c.read_jsonl(RE_RUN/(name+'_predictions.jsonl'));baseline[name]=score_pipeline(full,refs,saved)
    result={'pipelineDocuments':len(full),'queueDocuments':19,'pipelineDocumentCoverage':len(full)/19,'referenceEVALUATED_ON':sum(p['label']=='EVALUATED_ON' for p in refs),
        'zeroReferencePairDocuments':sum(not any(p['sampleId']==d['sampleId'] for p in refs) for d in full),'previous':baseline,'expandedNER_oldRE':metric,
        'labelFreeInferenceMatchesNERDev':True,'fixedOldRE':True,'testEvaluated':False,'modelPromoted':False,'qualityPromotionPassed':False,
        'notice':'Same exposed AI-reference dev diagnostics, not a blind or final evaluation. Low complete-document coverage and zero rare relation support preclude promotion.'}
    c.write_jsonl(output/'pipeline_dev_documents.jsonl',full);c.write_jsonl(output/'pipeline_dev_reference_pairs.jsonl',refs)
    c.write_jsonl(output/'expanded_NER_old_RE_predictions.jsonl',predicted);c.write_jsonl(output/'expanded_NER_old_RE_missed_relations.jsonl',errors)
    c.write_json(output/'pipeline_development_result.json',result);del relation_model;torch.cuda.empty_cache()
    return result

def run(folder,source,reviewed,output):
    if output.exists():raise FileExistsError('Preserve expanded NER run')
    config,parent,rows=load_inputs(folder,source,reviewed);settings=parent['NERTraining'];initial=c.ROOT/settings['initialization'];weight=initial/'model.safetensors'
    if c.file_sha256(weight)!=settings['initialWeightsSha256']:raise ValueError('Frozen initialization changed')
    paths=[CONTRACT,c.ROOT/config['parentContract'],folder/'manifest.json',source/'manifest.json',reviewed/'manifest.json',Path(__file__),weight,initial/'config.json',
        c.ROOT/'scripts/train_course_ner.py',c.ROOT/'scripts/collect_train_abstracts.py',c.ROOT/'scripts/train_abstract_ner.py',RE_SNAPSHOT/'manifest.json',RE_RUN/'manifest.json',
        c.ROOT/'scripts/course_abstract_relation.py',c.ROOT/'scripts/train_course_relation.py',c.ROOT/'scripts/evaluate_course_relation.py',c.ROOT/'scripts/infer_course_corpus.py',
        c.ROOT/'scripts/train_abstract_relation.py',c.ROOT/'scripts/course_weak.py',c.ROOT/'resources/course_abstract_relation_v1.json',
        c.ROOT/'kg_datasets/dblp/course_v4_runs/abstract_ner_development_20261008_35/manifest.json']
    re_config=read(c.ROOT/'resources/course_abstract_relation_v1.json');paths.append(c.ROOT/re_config['RETraining']['initialization']/'model.safetensors')
    g.verified_files(c.ROOT/Path(re_config['NERComparison']['candidateCheckpoint']).parent,re_config['NERComparison']['candidateRunManifestSha256'])
    hashes={p.relative_to(c.ROOT).as_posix():c.file_sha256(p) for p in paths};output.mkdir(parents=True);archive=output/'sources';archive.mkdir()
    for i,p in enumerate(paths):
        if p.suffix!='.safetensors':shutil.copy2(p,archive/(str(i)+'_'+p.name))
    state={'status':'running','trainingStarted':False,'createdAtUTC':datetime.now(UTC).isoformat(),'settings':settings,'testEvaluated':False,'modelPromoted':False};c.write_json(output/'status.json',state);started=time.perf_counter()
    try:
        os.environ.setdefault('HF_HUB_OFFLINE','1');os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
        import numpy as np
        import torch
        from transformers import BertTokenizerFast,BertForTokenClassification,DataCollatorForTokenClassification
        random.seed(settings['seed']);np.random.seed(settings['seed']);torch.manual_seed(settings['seed']);torch.cuda.manual_seed_all(settings['seed'])
        torch.set_num_threads(4);torch.use_deterministic_algorithms(True);torch.backends.cudnn.benchmark=False;torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        if not torch.cuda.is_available():raise ValueError('CUDA required; no silent fallback')
        device=torch.device('cuda');tokenizer=BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32',local_files_only=True,do_lower_case=True)
        encoded={s:[ner.encode_row(tokenizer,r,512) for r in split] for s,split in rows.items()}
        model,info=BertForTokenClassification.from_pretrained(initial,local_files_only=True,use_safetensors=True,attn_implementation='eager',output_loading_info=True)
        if any(info[k] for k in ('missing_keys','unexpected_keys','mismatched_keys','error_msgs')) or model.config.id2label!=dict(enumerate(parent['bioLabels'])):raise ValueError('Incompatible initialization')
        model.to(device);head=model.classifier.weight.detach().cpu().clone();encoder=model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu().clone()
        collator=DataCollatorForTokenClassification(tokenizer,padding=True,return_tensors='pt')
        evaluate=lambda m:ner.evaluate_model(m,rows['dev'],encoded['dev'],'dev_ai_reference_agreement_not_human_gold',collator=collator,device=device,batch_size=2)
        clean=lambda r:{k:v for k,v in r.items() if k!='predictions'}
        baseline=evaluate(model);dictionary=ner.score_rows(rows['dev'],[ner.dictionary_predict(r['text'],ner.make_dictionary(rows['train'])) for r in rows['dev']])
        c.write_json(output/'baseline_dev.json',clean(baseline));c.write_json(output/'dictionary_dev.json',dictionary)
        optimizer=torch.optim.AdamW(model.parameters(),lr=settings['learningRate'],weight_decay=0.01);rng=random.Random(settings['seed']);best_score=None;best=None;best_path=None;steps=[];epochs=[]
        state.update(trainingStarted=True,gpu=torch.cuda.get_device_name(device),device='cuda');c.write_json(output/'status.json',state)
        for epoch in range(1,settings['epochs']+1):
            order=list(range(len(encoded['train'])));rng.shuffle(order)
            for start in range(0,len(order),settings['batchSize']):
                indices=order[start:start+settings['batchSize']];batch={k:v.to(device) for k,v in collator([encoded['train'][i]['features'] for i in indices]).items()}
                model.train();optimizer.zero_grad(set_to_none=True);loss=model(**batch).loss
                if not torch.isfinite(loss):raise ValueError('Nonfinite training loss')
                loss.backward();norm=torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
                if not torch.isfinite(norm):raise ValueError('Nonfinite training gradient')
                optimizer.step();steps.append({'step':len(steps)+1,'epoch':epoch,'loss':float(loss.detach()),'gradientNorm':float(norm),'sampleIds':[rows['train'][i]['sampleId'] for i in indices]})
            c.write_jsonl(output/'steps.jsonl',steps);validation=evaluate(model);score=validation['metrics']['micro']['f1'];improved=ner.dev_checkpoint_improved(score,best_score)
            if improved:
                best_score=score;best=validation;best_path=output/f'checkpoint_epoch_{epoch:02d}';model.save_pretrained(best_path,safe_serialization=True);tokenizer.save_pretrained(best_path)
            epochs.append({'epoch':epoch,'steps':len(steps),'dev':clean(validation),'checkpointImproved':improved});c.write_json(output/'epochs.json',epochs)
            print(__import__('json').dumps({'epoch':epoch,'steps':len(steps),'devF1':score}),flush=True)
        del model,optimizer;torch.cuda.empty_cache();restored=BertForTokenClassification.from_pretrained(best_path,local_files_only=True,use_safetensors=True,attn_implementation='eager').to(device)
        if evaluate(restored)['predictions']!=best['predictions'] or torch.equal(head,restored.classifier.weight.detach().cpu()) or torch.equal(encoder,restored.bert.encoder.layer[0].attention.self.query.weight.detach().cpu()):raise ValueError('Reload mismatch or unchanged weights')
        c.write_jsonl(output/'dev_predictions.jsonl',[{'sampleId':r['sampleId'],'referenceEntities':r['entities'],'predictedEntities':p} for r,p in zip(rows['dev'],best['predictions'])])
        prior=read(c.ROOT/'kg_datasets/dblp/course_v4_runs/abstract_ner_development_20261008_35/development_result.json')
        if clean(baseline)!=prior['baselineDev']:raise ValueError('Same initialization/dev baseline differs from round35')
        result={'passed':True,'version':config['version'],'trainDocuments':len(rows['train']),'devDocuments':len(rows['dev']),'epochs':settings['epochs'],'steps':len(steps),'bestCheckpoint':best_path.name,
            'baselineDev':clean(baseline),'previousAbstractNERDev':prior['bestDev'],'bestDev':clean(best),'dictionaryDev':dictionary,'devRowsUnchanged':True,'devUsedForGradient':False,
            'classifierAndEncoderChanged':True,'reloadPredictionsIdentical':True,'testEvaluated':False,'testTokenized':False,'modelPromoted':False,'qualityPromotionPassed':False,
            'notice':'Single fixed-hyperparameter train-data expansion on exposed AI-reference dev labels. Development agreement only, not independent model reliability or final-test accuracy.'}
        c.write_json(output/'development_result.json',result);pipeline_dev(restored,best['predictions'],rows['dev'],device,output)
        if any(c.file_sha256(c.ROOT/key)!=sha for key,sha in hashes.items()):raise ValueError('Training source drift')
        load_inputs(folder,source,reviewed);state.update(status='completed',steps=len(steps),elapsedSeconds=time.perf_counter()-started,finishedAtUTC=datetime.now(UTC).isoformat(),peakCUDAbytes=torch.cuda.max_memory_allocated(device))
        c.write_json(output/'status.json',state);seal(output,paths);print(__import__('json').dumps({'completed':True,'train':len(rows['train']),'steps':len(steps),'bestF1':best_score,'testEvaluated':False}),flush=True)
    except Exception as error:
        state.update(status='failed_no_synthetic_fallback',errorType=type(error).__name__,error=str(error));c.write_json(output/'status.json',state);raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('snapshot','train'))
    for key in ('source','reviewed','output'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--snapshot',type=Path);args=parser.parse_args()
    if args.action=='snapshot':snapshot(args.source.resolve(),args.reviewed.resolve(),args.output.resolve())
    else:run(args.snapshot.resolve(),args.source.resolve(),args.reviewed.resolve(),args.output.resolve())
