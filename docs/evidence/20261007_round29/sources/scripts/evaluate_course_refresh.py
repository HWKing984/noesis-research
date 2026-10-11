"""One locked expanded-model test versus unchanged production caches; no fitting or deployment."""
import argparse
import json
import math
import os
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

import course_weak as c
import train_course_ner as ner
import train_course_relation as relation
from prepare_course_weak import verify_dataset
from import_course_ai import assess_readiness, save_training_inputs
from infer_course_corpus import encode_title
from evaluate_course_relation import candidate_rows, predict, score_pipeline

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / 'kg_datasets/dblp/course_v4_runs'
DATASET = ROOT / 'kg_datasets/dblp/course_v4_holdout_20261007_29'
SNAPSHOT = ROOT / 'kg_datasets/dblp/course_v4_holdout_inputs_20261007_29'
SELECTION = RUNS / 'refresh_selection_20261007_29.json'
SEAL = RUNS / 'refresh_test_data_seal_20261007_29.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def promotion_decision(new, old, support, gates):
    for metrics in (new, old):
        if any(type(metrics[k]) not in (int,float) or not math.isfinite(metrics[k]) or not 0 <= metrics[k] <= 1
               for k in ('f1','precision')): raise ValueError('Supported finite metrics required')
    checks = {'pipelineF1NonRegression': new['f1'] >= old['f1'],
              'pipelinePrecisionNonRegression': new['precision'] >= old['precision'],
              'rareNERDevNonRegression': gates['rareNERDevNonRegression'],
              'rareEntitySupport': support['DATASET'] >= gates['minimumReferenceRareEntitySupport'],
              'rareRelationSupport': support['EVALUATED_ON'] >= gates['minimumReferenceRareRelationSupport']}
    return {'passed': all(value is True for value in checks.values()), 'checks': checks,
            'failedChecks': [name for name,value in checks.items() if value is not True]}


def load_reviewed():
    selection = read(SELECTION)
    if (c.file_sha256(DATASET / 'manifest.json') != selection['datasetManifestSha256'] or
        c.file_sha256(c.SCHEMA_PATH) != selection['annotationSchemaSha256'] or
        c.file_sha256(c.CONFIG_PATH) != selection['annotationConfigSha256']):
        raise ValueError('Frozen queue or annotation contract changed')
    refs = verify_dataset(DATASET); manifest = ner.verify_files(SNAPSHOT)
    if (c.canonical_sha256(refs) != selection['referenceSha256'] or len(refs) != 200 or
        len({r['groupId'] for r in refs}) != 200 or any(r['split'] != 'test' for r in refs) or
        manifest['sourceDatasetManifestSha256'] != c.file_sha256(DATASET / 'manifest.json')):
        raise ValueError('Reserved holdout identity or snapshot binding changed')
    existing = verify_dataset(ROOT / 'kg_datasets/dblp/course_v4_weak')
    if {r['groupId'] for r in refs} & {r['groupId'] for r in existing}: raise ValueError('Holdout group overlap')
    receipts = c.read_jsonl(SNAPSHOT / 'receipts.jsonl')
    summary = assess_readiness(receipts, refs)
    if summary != read(SNAPSHOT / 'summary.json') or summary['aiReviewedDocuments'] != 200:
        raise ValueError('Entire queue must have validated reviews')
    locked = datetime.fromisoformat(selection['lockedAtUTC'])
    for r in receipts:
        if not (locked < datetime.fromisoformat(r['generation']['createdAt']) <=
                datetime.fromisoformat(r['review']['provenance']['createdAt'])):
            raise ValueError('Labels must follow checkpoint selection')
    with tempfile.TemporaryDirectory(prefix='course-refresh-binding-') as name:
        folder = Path(name); save_training_inputs(folder, receipts, refs)
        for path in folder.iterdir():
            if path.read_bytes() != (SNAPSHOT / path.name).read_bytes(): raise ValueError('Test exports differ from reviewed receipts')
    paths = [DATASET / 'manifest.json', SNAPSHOT / 'manifest.json', SELECTION, c.CONFIG_PATH, c.SCHEMA_PATH]
    paths += [ROOT / 'scripts' / p for p in ('evaluate_course_refresh.py','course_weak.py','train_course_ner.py',
        'train_course_relation.py','course_relation_model.py','infer_course_corpus.py','evaluate_course_relation.py')]
    for kind,saved in selection['models'].items():
        folder = ROOT / saved['developmentRun']; dev = ner.verify_files(folder)
        result = read(folder / 'development_result.json')
        if (c.file_sha256(folder / 'manifest.json') != saved['developmentManifestSha256'] or
            dev['config'] != saved['config'] or result['bestCheckpoint'] != saved['checkpoint'] or
            result['testEvaluated'] or not result['passed']): raise ValueError('Frozen candidate selection changed')
        epochs = read(folder / 'epochs.json')
        score = (lambda e:e['dev']['metrics']['micro']['f1']) if kind == 'ner' else (
            lambda e:relation.selection_score(e['dev']['metrics'],saved['config']['selection_metric']))
        if saved['checkpoint'] != f'checkpoint_epoch_{max(epochs,key=score)["epoch"]:02d}':
            raise ValueError('Checkpoint is not the earliest declared dev optimum')
        weights = folder / saved['checkpoint'] / 'model.safetensors'
        if c.file_sha256(weights) != saved['weightsSha256']: raise ValueError('Frozen weights changed')
        paths += [folder / 'manifest.json', weights]
    hashes = {p.relative_to(ROOT).as_posix():c.file_sha256(p) for p in paths}
    return selection, receipts, summary, hashes


def seal():
    if SEAL.exists(): raise FileExistsError('Preserve test data seal')
    _, _, summary, hashes = load_reviewed()
    c.write_json(SEAL, {'sealedAtUTC':datetime.now(UTC).isoformat(), 'inputSha256':hashes,
        'NERDocuments':summary['nerEligibleDocuments'], 'pipelineDocuments':summary['relationEligibleDocuments'],
        'testInferenceExecuted':False, 'humanGold':False, 'independentAnnotator':False})
    print(json.dumps({'sealed':True,'NERDocuments':summary['nerEligibleDocuments'],'pipelineDocuments':summary['relationEligibleDocuments']}))


def infer_ner(model, tokenizer, docs, config, collator, device):
    import torch
    records = []
    for doc in docs:
        encoded, _ = encode_title(tokenizer,c.model_payload(doc),config['max_length'])
        if encoded is None: raise ValueError('Title over frozen limit; no silent evaluation filtering')
        records.append(encoded)
    results = []
    with torch.inference_mode():
        for start in range(0,len(records),config['batch_size']):
            chunk = records[start:start+config['batch_size']]
            features = {k:v.to(device) for k,v in collator([r['features'] for r in chunk]).items()}
            if 'labels' in features: raise ValueError('Labels leaked into NER inference')
            logits = model(**features).logits
            if not torch.isfinite(logits).all() or logits.shape[-1] != len(c.CONFIG['bioLabels']): raise ValueError('Invalid NER logits')
            for record,doc,tags in zip(chunk,docs[start:start+len(chunk)],logits.argmax(-1).cpu().tolist()):
                decoded = ner.decode_bio(tags[:len(record['offsets'])],record['offsets'],doc['text'])
                results.append({'sampleId':doc['sampleId'],'predictedEntities':decoded['entities'],'invalidTransitions':decoded['invalidTransitions']})
    return results


def run(output, device_name):
    if output.exists(): raise FileExistsError('Preserve final test; no overwrite or automatic retry')
    selection, receipts, summary, hashes = load_reviewed()
    data_seal = read(SEAL)
    if data_seal['inputSha256'] != hashes: raise ValueError('Sources changed after test seal')
    output.mkdir(parents=True)
    started = time.monotonic()
    state = {'status':'running','createdAtUTC':datetime.now(UTC).isoformat(),'trainingStarted':False,
             'testInferenceStarted':False,'databaseWritten':False}
    c.write_json(output / 'status.json',state)
    try:
        if datetime.fromisoformat(data_seal['sealedAtUTC']) >= datetime.fromisoformat(state['createdAtUTC']): raise ValueError('Seal must precede test')
        (output / 'inputs').mkdir()
        for i,name in enumerate(hashes): shutil.copyfile(ROOT / name, output / 'inputs' / f'{i:02d}_{Path(name).name}') if not name.endswith('.safetensors') else None
        shutil.copyfile(SEAL,output / 'inputs/data_seal.json')
        docs = c.read_jsonl(SNAPSHOT / 'ner_inputs_test.jsonl')
        pairs = c.read_jsonl(SNAPSHOT / 'relation_inputs_test.jsonl')
        relation_ids = {r['reference']['sampleId'] for r in receipts if c.eligible_tasks(r,r['reference'])['relation']}
        pipeline_docs = [d for d in docs if d['sampleId'] in relation_ids]
        c.write_jsonl(output / 'excluded_documents.jsonl',[{'sampleId':r['reference']['sampleId'],
            'text':r['reference']['text'],'eligible':c.eligible_tasks(r,r['reference']),
            'annotation':r['annotation']} for r in receipts if r['reference']['sampleId'] not in relation_ids])
        os.environ.setdefault('HF_HUB_OFFLINE','1'); os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
        os.environ.setdefault('TOKENIZERS_PARALLELISM','false')
        import torch
        from transformers import BertTokenizerFast, BertForTokenClassification, DataCollatorWithPadding
        torch.set_num_threads(4); torch.manual_seed(20261006); torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.benchmark=False; torch.backends.cuda.matmul.allow_tf32=False; torch.backends.cudnn.allow_tf32=False
        if device_name == 'cuda' and not torch.cuda.is_available(): raise ValueError('CUDA unavailable; no fallback')
        device = torch.device(device_name)
        saved = selection['models']['ner']; checkpoint = ROOT / saved['developmentRun'] / saved['checkpoint']
        tokenizer = BertTokenizerFast.from_pretrained(checkpoint,local_files_only=True,do_lower_case=True)
        model, info = BertForTokenClassification.from_pretrained(checkpoint,local_files_only=True,use_safetensors=True,
            attn_implementation='eager',output_loading_info=True)
        if any(info[k] for k in ('missing_keys','unexpected_keys','mismatched_keys','error_msgs')): raise ValueError('Incomplete NER checkpoint')
        if [model.config.id2label[i] for i in range(len(c.CONFIG['bioLabels']))] != c.CONFIG['bioLabels']: raise ValueError('NER class order changed')
        model.to(device).requires_grad_(False).eval(); collator = DataCollatorWithPadding(tokenizer,return_tensors='pt')
        dev_docs = c.read_jsonl(ROOT / 'kg_datasets/dblp/course_v4_training_inputs_17/ner_inputs_dev.jsonl')
        dev = infer_ner(model,tokenizer,dev_docs,saved['config'],collator,device)
        if [r['predictedEntities'] for r in dev] != [r['predictedEntities'] for r in c.read_jsonl(ROOT / saved['developmentRun'] / 'dev_predictions.jsonl')]:
            raise ValueError('NER dev serving parity failed before test')
        # Reuse sealed old production outputs by publication identity; never rerun the old test.
        old_folder = ROOT / selection['oldProductionRun']; ner.verify_files(old_folder)
        if c.file_sha256(old_folder / 'manifest.json') != selection['oldProductionManifestSha256']: raise ValueError('Old production cache changed')
        old_docs = {d['publicationId']:d for d in c.read_jsonl(old_folder / 'documents.jsonl')}
        by_pid = {r['reference']['sampleId']:r['reference']['publicationId'] for r in receipts}
        old_to_new = {old_docs[by_pid[d['sampleId']]]['sampleId']:d['sampleId'] for d in docs}
        old_predictions = {r['sampleId']:r for r in c.read_jsonl(old_folder / 'ner_predictions.jsonl')}
        old_ner = []
        for d in docs:
            old_doc = old_docs[by_pid[d['sampleId']]]; p = old_predictions[old_doc['sampleId']]
            if old_doc['text'] != d['text'] or p['status'] == 'rejected': raise ValueError('Old cache title/reject differs')
            old_ner.append(p | {'sampleId':d['sampleId']})
        old_pipeline = []
        for p in c.read_jsonl(old_folder / 'relation_predictions.jsonl'):
            sid = old_to_new.get(p['sampleId'])
            if sid in relation_ids:
                updated = p | {'sampleId':sid}; updated['pairId'] = relation.pair_id(updated); old_pipeline.append(updated)
        old_expected = [p for d,r in zip(docs,old_ner) if d['sampleId'] in relation_ids for p in candidate_rows(d,r['predictedEntities'])]
        if {p['pairId'] for p in old_pipeline} != {relation.pair_id(p) for p in old_expected} or len(old_pipeline) != len(old_expected):
            raise ValueError('Old cache must include every predicted pair, including negatives')
        state.update(testInferenceStarted=True,device=str(device),gpu=torch.cuda.get_device_name(device) if device.type == 'cuda' else None)
        c.write_json(output / 'status.json',state)
        predictions = infer_ner(model,tokenizer,docs,saved['config'],collator,device)
        c.write_jsonl(output / 'new_ner_predictions.jsonl',predictions); c.write_jsonl(output / 'old_ner_cached.jsonl',old_ner)
        new_pipeline_rows = [p for d,r in zip(docs,predictions) if d['sampleId'] in relation_ids for p in candidate_rows(d,r['predictedEntities'])]
        outputs = {}
        for version in ('old','new'):
            saved_re = read(ROOT / 'annotations/course_v4/re_test_selection_20261006.json') if version == 'old' else selection['models']['re']
            folder = ROOT / saved_re['developmentRun']; ner.verify_files(folder)
            if c.file_sha256(folder / 'manifest.json') != saved_re['developmentManifestSha256']: raise ValueError('RE manifest changed')
            rp = folder / saved_re['checkpoint']
            if c.file_sha256(rp / 'model.safetensors') != saved_re['weightsSha256']: raise ValueError('RE weights changed')
            rt = relation.prepare_tokenizer(rp); rm = relation.load_relation_model(rp,rt).to(device).requires_grad_(False).eval()
            rc = DataCollatorWithPadding(rt,return_tensors='pt'); config = saved_re['config']
            infer = lambda rows:predict(rm,rt,rows,config['max_length'],rc,device,config['batch_size'])
            train_snapshot = 'course_v4_training_inputs_10' if version == 'old' else 'course_v4_training_inputs_17'
            dev_pairs = c.read_jsonl(ROOT / 'kg_datasets/dblp' / train_snapshot / 'relation_inputs_dev.jsonl')
            dev_predictions = infer(dev_pairs)
            if [p['label'] for p in dev_predictions] != [p['predictedLabel'] for p in c.read_jsonl(folder / 'dev_predictions.jsonl')]: raise ValueError('RE dev serving parity failed')
            module = infer(pairs); pipeline = old_pipeline if version == 'old' else infer(new_pipeline_rows)
            c.write_jsonl(output / f'{version}_module_predictions.jsonl',module)
            c.write_jsonl(output / f'{version}_pipeline_predictions.jsonl',pipeline)
            metrics = score_pipeline(pipeline_docs,pairs,pipeline)
            metrics['entityScope'] = 'sealed_production_NER_cache' if version == 'old' else 'frozen_expanded_NER_predictions'
            outputs[version] = {'module':relation.score_relations(pairs,[p['label'] for p in module]), 'pipeline':metrics}
        outputs['old']['NER'] = ner.score_rows(docs,[r['predictedEntities'] for r in old_ner])
        outputs['new']['NER'] = ner.score_rows(docs,[r['predictedEntities'] for r in predictions])
        gates = promotion_decision(outputs['new']['pipeline']['positiveMicro'],outputs['old']['pipeline']['positiveMicro'],
            {'DATASET':summary['entitySupport']['test']['DATASET'],'EVALUATED_ON':summary['relationSupport']['test']['EVALUATED_ON']},selection['promotionGates'])
        for name,sha in hashes.items():
            if c.file_sha256(ROOT / name) != sha: raise ValueError('Frozen input changed during evaluation')
        spans = lambda entities:{(e['start'],e['end'],e['label']) for e in entities}
        c.write_jsonl(output / 'new_ner_errors.jsonl',[{'document':d,'prediction':p} for d,p in zip(docs,predictions) if spans(d['entities']) != spans(p['predictedEntities'])])
        c.write_jsonl(output / 'test_documents.jsonl',docs); c.write_jsonl(output / 'test_reference_pairs.jsonl',pairs)
        result = {'engineeringPassed':True,'testEvaluated':True,'endToEndEvaluated':True,'queueDocuments':200,
            'NERDocuments':len(docs),'pipelineDocuments':len(pipeline_docs),'referencePairs':len(pairs),'support':summary,
            'scores':outputs,'promotion':gates,'modelPromoted':False,'qualityPromotionPassed':False,
            'oldNERInferenceRepeated':False,'oldPipelineInferenceRepeated':False,'trainingExecuted':False,
            'newInvalidBIOTransitions':sum(p['invalidTransitions'] for p in predictions),'humanGold':False,'independentAnnotator':False,
            'notice':'Same-session AI reference agreement on eligible new holdout titles, not independent gold. Zero-reference-pair titles included. Missing rare support is not a zero-F1 reliability claim. Closed to test-informed tuning.'}
        c.write_json(output / 'test_result.json',result)
        state.update(status='completed',finishedAtUTC=datetime.now(UTC).isoformat(),elapsedSeconds=time.monotonic()-started)
        print(json.dumps({'completed':True,'scores':{v:{'NER':r['NER']['micro'],'pipeline':r['pipeline']['positiveMicro']} for v,r in outputs.items()},'promotion':gates}),flush=True)
    except Exception as error:
        state.update(status='failed',error=repr(error),finishedAtUTC=datetime.now(UTC).isoformat()); raise
    finally:
        c.write_json(output / 'status.json',state)
        c.write_json(output / 'manifest.json',{'status':state['status'],'inputSha256':hashes,'dataSealSha256':c.file_sha256(SEAL),
            'filesSha256':{p.relative_to(output).as_posix():c.file_sha256(p) for p in output.rglob('*') if p.is_file()}})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('action',choices=('seal','run')); parser.add_argument('--output',type=Path)
    parser.add_argument('--device',choices=('cuda','cpu'),default='cuda')
    args = parser.parse_args()
    if args.action == 'seal': seal()
    elif args.output is None: parser.error('run requires a new --output')
    else: run(args.output,args.device)
