"""Locked RE module and cached-frozen-NER pipeline test; never fit or tune."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

import course_weak as c
import train_course_ner as ner
import train_course_relation as re_model
from prepare_course_weak import verify_dataset

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def candidate_rows(document, entities):
    ner.score_rows([document|{'entities':entities}],[entities])
    common={k:document[k] for k in ('sampleId','text','textSha256') if k in document}
    result=[common|{'head':head,'tail':tail} for head in entities for tail in entities
            if head['label']=='METHOD' and tail['label'] in ('TASK','DATASET')]
    for row in result: re_model.mark_pair(row)
    return result


def score_pipeline(documents, reference, predictions):
    lookup={d['sampleId']:d for d in documents}
    if not lookup or len(lookup)!=len(documents): raise ValueError('Pipeline documents must be nonempty and unique')
    def keys(rows):
        seen=set()
        for row in rows:
            sid=row['sampleId']
            if sid not in lookup or row['text']!=lookup[sid]['text']: raise ValueError('Pipeline pair outside scored documents')
            re_model.mark_pair(row)
            if row['label'] not in re_model.allowed_labels(row['tail']['label']): raise ValueError('Pipeline unresolved or illegal relation label')
            key=re_model.pair_key(row)+(row['head']['label'],row['tail']['label'])
            if key in seen: raise ValueError('Duplicate pipeline candidate')
            seen.add(key)
            if row['label']!='NO_RELATION': yield key+(row['label'],)
    expected=list(keys(reference)); predicted=list(keys(predictions))
    per_class={label:c.entity_agreement([p for p in predicted if p[-1]==label],[p for p in expected if p[-1]==label])
               for label in c.CONFIG['relationPairs']}
    supported=[label for label in per_class if per_class[label]['reference']]
    return {'evaluationTarget':c.CONFIG['evaluationTarget'],'entityScope':'cached_frozen_NER_predicted_entities',
        'matching':'exact_document_directed_endpoint_spans_endpoint_types_and_relation_label',
        'documents':len(documents),'positiveMicro':c.entity_agreement(predicted,expected),'perClass':per_class,
        'positiveMacroF1':sum(per_class[label]['f1'] for label in supported)/len(supported) if supported else None,
        'supportedPositiveClasses':supported,'negativeDecisions':sum(p['label']=='NO_RELATION' for p in predictions),
        'notice':'All fully resolved documents including zero-reference-pair titles are scored. NO_RELATION is no edge, not pipeline true-negative accuracy. Incomplete documents are excluded and disclosed.'}


def load_inputs(dataset, snapshot, selection):
    lock=read(selection); development=ROOT/lock['developmentRun']; manifest=ner.verify_files(development)
    result=read(development/'development_result.json'); state=read(development/'status.json')
    epochs=read(development/'epochs.json')
    best=max(epochs,key=lambda e:re_model.selection_score(e['dev']['metrics'],lock['config']['selection_metric']))
    if (c.file_sha256(development/'manifest.json')!=lock['developmentManifestSha256']
        or lock['checkpoint']!=f'checkpoint_epoch_{best["epoch"]:02d}' or result['bestCheckpoint']!=lock['checkpoint']
        or result['bestDev']!=best['dev'] or state['config']!=lock['config'] or manifest['config']!=lock['config']
        or state['status']!='completed' or not result['passed'] or result['testEvaluated'] or result['devUsedForGradient']
        or lock['testMetricsUsedForSelection'] or lock['humanGold'] or not lock['declaredDevGatesPassed']):
        raise ValueError('RE dev selection or frozen configuration changed')
    checkpoint=development/lock['checkpoint']
    if c.file_sha256(checkpoint/'model.safetensors')!=lock['weightsSha256']: raise ValueError('RE frozen weights changed')
    for path,digest in ((c.SCHEMA_PATH,lock['annotationSchemaSha256']),(c.CONFIG_PATH,lock['annotationConfigSha256'])):
        if c.file_sha256(path)!=digest: raise ValueError('Frozen extraction contract changed')
    parent=ROOT/lock['trainingSnapshot']
    if c.file_sha256(parent/'manifest.json')!=lock['trainingSnapshotManifestSha256']: raise ValueError('RE training snapshot changed')
    old_splits,_=re_model.load_relation_snapshot(dataset,parent)
    splits,_=re_model.load_relation_snapshot(dataset,snapshot)
    if splits!=old_splits: raise ValueError('RE train/dev inputs changed for final test')
    ner_splits,_=ner.load_snapshot(dataset,snapshot,include_test=True)
    references=[r for r in verify_dataset(dataset) if r['split']=='test']
    if len(references)!=lock['testQueueDocuments'] or c.canonical_sha256(references)!=lock['testQueueReferenceSha256']:
        raise ValueError('Test queue differs from lock')
    old=c.read_jsonl(parent/'receipts.jsonl'); receipts=c.read_jsonl(snapshot/'receipts.jsonl')
    if [r['reference']['sampleId'] for r in receipts]!=[r['reference']['sampleId'] for r in old]: raise ValueError('Receipt cohort/order changed')
    locked=datetime.fromisoformat(lock['lockedAtUTC'].replace('Z','+00:00'))
    if datetime.fromisoformat(state['finishedAt'])>=locked: raise ValueError('Model was not selected before test labels')
    documents=[]; excluded=[]; expected=[]
    ner_by_id={row['sampleId']:row for row in ner_splits['test']}
    for before,after in zip(old,receipts):
        ref=after['reference']; annotation=after['annotation']
        if ref['split']!='test':
            if before!=after: raise ValueError('Non-test receipt changed')
            continue
        if any(annotation[k]!=before['annotation'][k] for k in ('entities','entityStatus','entityReason','groupMentions')):
            raise ValueError('Frozen NER entity annotation changed')
        if c.eligible_tasks(before,before['reference'])['ner']:
            if (after['review'] is None or not locked<datetime.fromisoformat(after['generation']['createdAt'])
                <=datetime.fromisoformat(after['review']['provenance']['createdAt'])):
                raise ValueError('RE judgments were not reviewed after model lock')
        elif before!=after: raise ValueError('Inherited NER quarantine changed')
        if not c.eligible_tasks(after,ref)['relation']:
            excluded.append({'sampleId':ref['sampleId'],'text':ref['text'],'entityStatus':annotation['entityStatus'],
                'relationStatus':annotation['relationStatus'],'reason':annotation['entityReason'] or annotation['relationReason'],
                'annotationSha256':after['contentSha256']})
            continue
        documents.append(ner_by_id[ref['sampleId']])
        entities={e['entityId']:e for e in annotation['entities']}
        common={k:ner_by_id[ref['sampleId']][k] for k in ('sampleId','text','textSha256','referenceSha256','annotationSha256','labelSource')}
        expected.extend(common|{'head':entities[p['head']],'tail':entities[p['tail']],'label':p['label'],
                               'evidence':p['evidence'],'reason':p['reason']} for p in annotation['relations'])
    relations=c.read_jsonl(snapshot/'relation_inputs_test.jsonl')
    if relations!=expected or not documents or not relations: raise ValueError('RE test rows differ from resolved reviewed receipts')
    cache=ROOT/'kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09'; cache_manifest=ner.verify_files(cache)
    ner_lock=ROOT/'annotations/course_v4/ner_test_selection_20261006.json'; nr=read(ner_lock)
    ner.load_test_checkpoint(ROOT/nr['developmentRun'],ner_lock)
    if (cache_manifest['inputSha256'].get(str(ner_lock.resolve()))!=c.file_sha256(ner_lock)
        or read(cache/'test_result.json')['weightsSha256']!=lock['pipelineNERWeightsSha256']
        or nr['weightsSha256']!=lock['pipelineNERWeightsSha256']): raise ValueError('Cached NER is not frozen pipeline model')
    cached=c.read_jsonl(cache/'test_predictions.jsonl')
    old_ner=c.read_jsonl(ROOT/'kg_datasets/dblp/course_v4_training_inputs_09/ner_inputs_test.jsonl')
    if ([p['sampleId'] for p in cached]!=[r['sampleId'] for r in old_ner]
        or any(p['referenceEntities']!=r['entities'] for p,r in zip(cached,old_ner))): raise ValueError('Cached NER reference binding changed')
    logical=lambda rows:[{k:r[k] for k in ('sampleId','text','textSha256','entities')} for r in rows]
    if logical(ner_splits['test'])!=logical(old_ner): raise ValueError('Cached NER input text or entities changed')
    ner.score_rows(old_ner,[p['predictedEntities'] for p in cached])
    lookup={p['sampleId']:p for p in cached}
    return {'checkpoint':checkpoint,'development':development,'lock':lock,'documents':documents,'relations':relations,
            'excluded':excluded,'cachedNERPredictions':[lookup[d['sampleId']] for d in documents],
            'cache':cache,'parent':parent,'dev':splits['dev'],'train':splits['train']}


def predict(model, tokenizer, rows, max_length, collator, device, batch_size):
    import torch
    records=[re_model.encode_pair(tokenizer,{k:v for k,v in row.items() if k!='label'},max_length) for row in rows]
    model.eval(); predictions=[]
    with torch.inference_mode():
        for offset in range(0,len(records),batch_size):
            logits,targets=re_model.forward_batch(model,records[offset:offset+batch_size],collator,device)
            if targets is not None: raise ValueError('Reference relation leaked into inference')
            for row,probabilities in zip(rows[offset:offset+batch_size],logits.softmax(-1).cpu().tolist()):
                label=re_model.LABELS[max(range(len(probabilities)),key=probabilities.__getitem__)]
                predictions.append({k:v for k,v in row.items() if k not in ('label','evidence','reason')}|
                    {'label':label,'probabilities':dict(zip(re_model.LABELS,probabilities)),'pairId':re_model.pair_id(row)})
    return predictions


def run(dataset, snapshot, selection, data_lock, output, device_name):
    if output.exists(): raise FileExistsError('Preserve final RE/pipeline results; no overwrite or automatic retry')
    if device_name not in ('cuda','cpu','auto'): raise ValueError('Invalid device')
    output.mkdir(exist_ok=False,parents=True)
    state={'status':'running','mode':'locked-RE-and-cached-NER-test','trainingStarted':False,
           'testInferenceStarted':False,'NERTestInferenceRepeated':False,'createdAt':datetime.now(UTC).isoformat()}
    c.write_json(output/'status.json',state)
    try:
        sealed=read(data_lock)
        if (sealed['snapshotManifestSha256']!=c.file_sha256(snapshot/'manifest.json')
            or sealed['selectionSha256']!=c.file_sha256(selection)
            or datetime.fromisoformat(sealed['sealedAtUTC'])>=datetime.fromisoformat(state['createdAt'])):
            raise ValueError('Test labels must be sealed before inference')
        inputs=load_inputs(dataset,snapshot,selection); lock=inputs['lock']; config=lock['config']
        if (sealed['frozenNERTestManifestSha256']!=c.file_sha256(inputs['cache']/'manifest.json')
            or sealed['relationLabelsManifestSha256']!=c.file_sha256(ROOT/'kg_datasets/dblp/course_v4_runs/test_relation_labels_20261006_17/manifest.json')):
            raise ValueError('Sealed NER cache or RE test labels changed')
        paths=[Path(__file__),Path(re_model.__file__),Path(ner.__file__),Path(c.__file__),
            Path(__file__).with_name('course_relation_model.py'),c.CONFIG_PATH,c.SCHEMA_PATH,
            dataset/'manifest.json',snapshot/'manifest.json',selection,data_lock,
            inputs['parent']/'manifest.json',inputs['development']/'manifest.json',inputs['cache']/'manifest.json',
            ROOT/'annotations/course_v4/ner_test_selection_20261006.json',
            ROOT/'kg_datasets/dblp/course_v4_runs/test_relation_labels_20261006_17/manifest.json']
        hashes={str(p.resolve()):c.file_sha256(p) for p in paths}; archived={}; (output/'inputs').mkdir()
        for i,path in enumerate(paths):
            target=output/'inputs'/f'{i:02d}_{path.name}'; shutil.copyfile(path,target)
            if c.file_sha256(target)!=hashes[str(path.resolve())]: raise ValueError('Input archival drift')
            archived[str(path.resolve())]=target.relative_to(output).as_posix()
        c.write_jsonl(output/'excluded_documents.jsonl',inputs['excluded'])
        c.write_jsonl(output/'test_documents.jsonl',inputs['documents'])
        c.write_jsonl(output/'test_reference_pairs.jsonl',inputs['relations'])
        c.write_jsonl(output/'cached_ner_predictions.jsonl',inputs['cachedNERPredictions'])
        os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
        import torch
        from importlib.metadata import version
        from transformers import DataCollatorWithPadding
        torch.set_num_threads(4); torch.manual_seed(config['seed']); torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.benchmark=False; torch.backends.cuda.matmul.allow_tf32=False; torch.backends.cudnn.allow_tf32=False
        device=torch.device(('cuda' if torch.cuda.is_available() else 'cpu') if device_name=='auto' else device_name)
        if device.type=='cuda' and not torch.cuda.is_available(): raise ValueError('CUDA unavailable; no fallback')
        tokenizer=re_model.prepare_tokenizer(inputs['checkpoint'])
        model=re_model.load_relation_model(inputs['checkpoint'],tokenizer).to(device); model.requires_grad_(False)
        collator=DataCollatorWithPadding(tokenizer,return_tensors='pt')
        infer=lambda rows:predict(model,tokenizer,rows,config['max_length'],collator,device,config['batch_size'])
        dev=infer(inputs['dev']); original=c.read_jsonl(inputs['development']/'dev_predictions.jsonl')
        if ([p['label'] for p in dev]!=[p['predictedLabel'] for p in original]
            or re_model.score_relations(inputs['dev'],[p['label'] for p in dev])!=read(inputs['development']/'development_result.json')['bestDev']['metrics']):
            raise ValueError('Dev serving parity failed; no test inference')
        c.write_json(output/'dev_reload_check.json',{'predictionsAndMetricsIdentical':True,'pairs':len(dev),'checkpointSelectionRepeated':False})
        pipeline_rows=[pair for doc,p in zip(inputs['documents'],inputs['cachedNERPredictions']) for pair in candidate_rows(doc,p['predictedEntities'])]
        for rows in (inputs['relations'],pipeline_rows):
            for row in rows: re_model.encode_pair(tokenizer,{k:v for k,v in row.items() if k!='label'},config['max_length'])
        c.write_json(output/'preflight.json',{'valid':True,'referencePairs':len(inputs['relations']),'pipelineCandidatePairs':len(pipeline_rows),
            'truncationOrRejectedPairs':0,'referenceLabelsAreModelFeatures':False,'cachedNERInferenceReused':True})
        state.update(testInferenceStarted=True,device=str(device),gpu=torch.cuda.get_device_name(device) if device.type=='cuda' else None)
        state['packages']={name:version(name) for name in ('torch','transformers','tokenizers','safetensors','numpy')}
        c.write_json(output/'status.json',state); print(json.dumps({'stage':'frozen_test','referencePairs':len(inputs['relations']),'pipelinePairs':len(pipeline_rows)}),flush=True)
        module=infer(inputs['relations']); pipeline=infer(pipeline_rows)
        module_metrics=re_model.score_relations(inputs['relations'],[p['label'] for p in module])
        pipeline_metrics=score_pipeline(inputs['documents'],inputs['relations'],pipeline)
        mapping=re_model.type_majority(inputs['train'])
        baseline=[mapping[row['tail']['label']] for row in inputs['relations']]
        c.write_jsonl(output/'module_predictions.jsonl',module); c.write_jsonl(output/'pipeline_predictions.jsonl',pipeline)
        c.write_jsonl(output/'baseline_module_predictions.jsonl',[{'pairId':re_model.pair_id(r),'predictedLabel':p} for r,p in zip(inputs['relations'],baseline)])
        c.write_jsonl(output/'module_errors.jsonl',[{'reference':r,'prediction':p} for r,p in zip(inputs['relations'],module) if r['label']!=p['label']])
        failures=[]
        for doc in inputs['documents']:
            ref=[r for r in inputs['relations'] if r['sampleId']==doc['sampleId']]
            pred=[r for r in pipeline if r['sampleId']==doc['sampleId']]
            metrics=score_pipeline([doc],ref,pred)
            if metrics['positiveMicro']['truePositive']!=metrics['positiveMicro']['reference'] or metrics['positiveMicro']['truePositive']!=metrics['positiveMicro']['predicted']:
                failures.append({'sampleId':doc['sampleId'],'text':doc['text'],'metrics':metrics,'referencePairs':ref,'predictedPairs':pred})
        c.write_jsonl(output/'pipeline_errors.jsonl',failures)
        if any(c.file_sha256(Path(path))!=digest for path,digest in hashes.items()) or c.file_sha256(inputs['checkpoint']/'model.safetensors')!=lock['weightsSha256']:
            raise ValueError('Frozen source or weights changed during inference')
        result={'engineeringPassed':True,'evaluationTarget':c.CONFIG['evaluationTarget'],'testEvaluated':True,'endToEndEvaluated':True,
            'trainingStarted':False,'NERTestInferenceRepeated':False,'weightsUnchanged':True,'humanGold':False,'independentAnnotator':False,
            'queueDocuments':lock['testQueueDocuments'],'evaluatedDocuments':len(inputs['documents']),'excludedDocuments':len(inputs['excluded']),
            'coverage':len(inputs['documents'])/lock['testQueueDocuments'],'zeroReferencePairDocuments':sum(not any(r['sampleId']==d['sampleId'] for r in inputs['relations']) for d in inputs['documents']),
            'referencePairs':len(module),'pipelineCandidatePairs':len(pipeline),'moduleMetrics':module_metrics,'pipelineMetrics':pipeline_metrics,
            'baselineModuleMetrics':re_model.score_relations(inputs['relations'],baseline),'moduleErrorPairs':sum(r['label']!=p['label'] for r,p in zip(inputs['relations'],module)),
            'pipelineErrorDocuments':len(failures),'REWeightsSha256':lock['weightsSha256'],'NERWeightsSha256':lock['pipelineNERWeightsSha256'],
            'notice':'One locked RE test pass; pipeline reuses prior frozen NER test predictions, no new NER test pass. Scores on fully resolved AI-reference subset, not human gold or complete-queue accuracy. No thresholds tuned; no application quality promotion.'}
        c.write_json(output/'test_result.json',result)
        state.update(status='completed',testEvaluated=True,endToEndEvaluated=True,finishedAt=datetime.now(UTC).isoformat()); c.write_json(output/'status.json',state)
        c.write_json(output/'manifest.json',{'inputSha256':hashes,'archivedInputs':archived,'config':config,
            'filesSha256':{p.relative_to(output).as_posix():c.file_sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}})
        return result
    except Exception as error:
        state.update(status='failed',error=repr(error),finishedAt=datetime.now(UTC).isoformat()); c.write_json(output/'status.json',state)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    for name in ('dataset','snapshot','selection','data-lock','output'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--device',choices=('cuda','cpu','auto'),default='auto')
    args=parser.parse_args()
    print(json.dumps(run(args.dataset,args.snapshot,args.selection,args.data_lock,args.output,args.device),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
