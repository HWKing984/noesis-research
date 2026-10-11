"""One fixed NER/RE experiment on the revised abstract snapshot; no test or deployment."""
import argparse
import hashlib
import json
import os
import random
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_graph as g
import course_weak as c
import train_course_ner as ner
import train_course_relation as re_model
from course_abstract_v1 import read, seal
from course_abstract_relation import NER_FIELDS, rows_for
from review_eval_attribution import source_cohorts
from evaluate_course_relation import candidate_rows, predict, score_pipeline
from infer_course_corpus import encode_title
from train_abstract_relation import diagnose

CONTRACT = c.ROOT/'resources/course_abstract_revised_training_v1.json'
TARGET = 'dev_ai_reference_agreement_not_human_gold'


def load_inputs():
    config = read(CONTRACT)
    if config['version'] != 'abstract_revised_training_v1' or config['maxTokens'] != 512 or config['textKind'] != 'abstract' or config['automaticPromotionAllowed'] is not False:
        raise ValueError('Revised experiment contract drift')
    for key in ('NERParent', 'REParent', 'revisionContract'):
        if c.file_sha256(c.ROOT/config[key]) != config[key+'Sha256']: raise ValueError('Parent/revision contract drift')
    parent_ner = read(c.ROOT/config['NERParent']); parent_re = read(c.ROOT/config['REParent'])
    revision, old_sources = source_cohorts(); folder = c.ROOT/config['snapshot']; manifest = g.verified_files(folder, config['snapshotManifestSha256'])
    if read(folder/'contract.json') != revision or any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Revised snapshot input drift')
    data = {}; groups = {}
    for split in ('train', 'dev'):
        refs = c.read_jsonl(folder/(split+'_references.jsonl')); receipts = c.read_jsonl(folder/(split+'_reviewed_receipts.jsonl')); original_refs, original_receipts = old_sources[split]
        expected = config['expected'][split]
        if refs != original_refs or len(refs) != len(receipts) or len(refs) != expected['queue'] or len({r['sampleId'] for r in refs}) != len(refs) or len({r['groupId'] for r in refs}) != len(refs): raise ValueError('Locked cohort incomplete/duplicate/replaced')
        for ref, receipt, original in zip(refs, receipts, original_receipts):
            if ref['split'] != split or ref['textKind'] != 'abstract' or hashlib.sha256(ref['text'].encode('utf-8')).hexdigest() != ref['textSha256'] or c.validate_receipt(receipt, ref) or receipt['review'] is None or any(receipt['annotation'][k] != original['annotation'][k] for k in NER_FIELDS): raise ValueError('Unreviewed source, wrong split/text or altered NER')
        rows = rows_for(refs, receipts); names = ('ner', 'relation', 'full_relation', 'excluded_ner')
        for name, generated in zip(names, rows[:4]):
            if len(generated) != expected[name] or generated != c.read_jsonl(folder/(name+'_'+split+'.jsonl')): raise ValueError('Serialized revised rows differ from receipts: '+name)
        if rows[4:] != (expected['unknown'], expected['eligiblePairs']) or Counter(p['label'] for p in rows[1]) != expected['support'] or len({re_model.pair_key(p) for p in rows[1]}) != len(rows[1]): raise ValueError('Known/unknown support or pair inventory drift')
        data[split] = dict(zip(names, rows[:4])); groups[split] = {r['groupId'] for r in refs}
    if groups['train'] & groups['dev']: raise ValueError('Cross-split paper group leakage')
    full_ids = {d['sampleId'] for d in data['dev']['full_relation']}; full_pairs = [p for p in data['dev']['relation'] if p['sampleId'] in full_ids]
    if len(full_pairs) != 107 or Counter(p['label'] for p in full_pairs) != {'USED_FOR': 84, 'NO_RELATION': 23} or sum(not any(p['sampleId'] == d['sampleId'] for p in full_pairs) for d in data['dev']['full_relation']) != 1: raise ValueError('Complete dev reference/zero-document drift')
    baseline = config['baselineNER']; path = c.ROOT/baseline['path']; g.verified_files(path.parent, baseline['runManifestSha256'])
    if c.file_sha256(path/'model.safetensors') != baseline['weightsSha256']: raise ValueError('Baseline NER changed')
    for task, settings in (('NER', parent_ner['NERTraining']), ('RE', parent_re['RETraining'])):
        initial = c.ROOT/settings['initialization']; g.verified_files(initial.parent, config['initialRunManifests'][task])
        if c.file_sha256(initial/'model.safetensors') != settings['initialWeightsSha256']: raise ValueError('Frozen initialization weights changed')
    return config, parent_ner, parent_re, data


def dev_scope(value, target=TARGET):
    if not isinstance(value, dict): return value
    return {k: target if k == 'evaluationTarget' else dev_scope(v, target) for k, v in value.items()}


def clean(evaluation):
    result = {k: v for k, v in evaluation.items() if k not in ('predictions', 'probabilities')}
    result['metrics'] = dev_scope(result['metrics']) | {'evaluationTarget': TARGET}
    return result


def setup(settings):
    import numpy as np
    import torch
    random.seed(settings['seed']); np.random.seed(settings['seed']); torch.manual_seed(settings['seed']); torch.cuda.manual_seed_all(settings['seed'])
    torch.set_num_threads(4); torch.use_deterministic_algorithms(True); torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
    if not torch.cuda.is_available(): raise ValueError('CUDA required; no silent fallback')
    return torch.device('cuda')


def load_ner(path, bio_labels, device):
    from transformers import BertForTokenClassification
    model, info = BertForTokenClassification.from_pretrained(path, local_files_only=True, use_safetensors=True, attn_implementation='eager', output_loading_info=True)
    if any(info[k] for k in ('missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs')) or model.config.id2label != dict(enumerate(bio_labels)): raise ValueError('Incomplete/incompatible NER weights')
    return model.to(device)


def fit(task, data, settings, parent_ner, config, output):
    import torch
    from transformers import BertTokenizerFast, DataCollatorForTokenClassification, DataCollatorWithPadding
    device = setup(settings); torch.cuda.reset_peak_memory_stats(device); started = time.perf_counter(); initial = c.ROOT/settings['initialization']; output.mkdir()
    rows = {s: data[s]['ner' if task == 'NER' else 'relation'] for s in ('train', 'dev')}
    tokenizer = BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32', local_files_only=True, do_lower_case=True) if task == 'NER' else re_model.prepare_tokenizer(initial)
    collator = DataCollatorForTokenClassification(tokenizer, return_tensors='pt') if task == 'NER' else DataCollatorWithPadding(tokenizer, return_tensors='pt')
    encoded = {s: [(ner.encode_row if task == 'NER' else re_model.encode_pair)(tokenizer, row, 512) for row in split] for s, split in rows.items()}
    if task == 'NER':
        for split in rows:
            for row, record in zip(rows[split], encoded[split]):
                offsets = record['offsets']; labels = record['features']['labels']
                decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else label for o, label in zip(offsets, labels)], offsets, row['text'])
                if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]: raise ValueError('Strict BIO round-trip failed before fit')
    model = load_ner(initial, parent_ner['bioLabels'], device) if task == 'NER' else re_model.load_relation_model(initial, tokenizer, 'entity_markers').to(device)
    head = model.classifier.weight.detach().cpu().clone(); encoder = model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu().clone()
    def evaluate(current):
        return ner.evaluate_model(current, rows['dev'], encoded['dev'], TARGET, collator=collator, device=device, batch_size=settings['batchSize']) if task == 'NER' else re_model.evaluate_model(current, rows['dev'], encoded['dev'], collator, device, settings['batchSize'])
    baseline = evaluate(model)
    if task == 'NER':
        lexicon = ner.make_dictionary(rows['train']); simple = ner.score_rows(rows['dev'], [ner.dictionary_predict(r['text'], lexicon) for r in rows['dev']], evaluation_target=TARGET)
    else:
        mapping = re_model.type_majority(rows['train']); simple = dev_scope(re_model.score_relations(rows['dev'], [mapping[p['tail']['label']] for p in rows['dev']])) | {'evaluationTarget': TARGET}
    c.write_json(output/'baseline_dev.json', clean(baseline)); c.write_json(output/'simple_baseline_dev.json', simple)
    for split in rows: c.write_jsonl(output/(split+'_inputs.jsonl'), rows[split])
    weights = torch.tensor(re_model.class_weights(rows['train'], settings['balancedLoss']), dtype=torch.float32, device=device) if task == 'RE' else None
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings['learningRate'], weight_decay=config['optimizer']['weightDecay'])
    best_score = None; best = None; checkpoint = None; epochs = []; steps = []; rng = random.Random(settings['seed'])
    state = {'status': 'running', 'trainingStarted': True, 'task': task, 'settings': settings, 'createdAtUTC': datetime.now(UTC).isoformat(), 'device': 'cuda', 'gpu': torch.cuda.get_device_name(device), 'testEvaluated': False, 'modelPromoted': False}
    if weights is not None: state['classWeights'] = dict(zip(re_model.LABELS, weights.cpu().tolist()))
    c.write_json(output/'status.json', state)
    for epoch in range(1, settings['epochs']+1):
        order = list(range(len(rows['train']))); rng.shuffle(order)
        for start in range(0, len(order), settings['batchSize']):
            indices = order[start:start+settings['batchSize']]; records = [encoded['train'][i] for i in indices]
            model.train(); optimizer.zero_grad(set_to_none=True)
            if task == 'NER':
                batch = {k: v.to(device) for k, v in collator([r['features'] for r in records]).items()}; loss = model(**batch).loss
            else:
                logits, targets = re_model.forward_batch(model, records, collator, device); loss = torch.nn.functional.cross_entropy(logits, targets, weight=weights)
            if not torch.isfinite(loss): raise ValueError('Nonfinite training loss')
            loss.backward(); norm = torch.nn.utils.clip_grad_norm_(model.parameters(), config['optimizer']['clipGradientNorm'])
            if not torch.isfinite(norm): raise ValueError('Nonfinite gradient')
            optimizer.step(); steps.append({'step': len(steps)+1, 'epoch': epoch, 'loss': float(loss.detach()), 'gradientNorm': float(norm), 'inputIds': [rows['train'][i]['sampleId'] if task == 'NER' else re_model.pair_id(rows['train'][i]) for i in indices]})
        c.write_jsonl(output/'steps.jsonl', steps); validation = evaluate(model)
        score = validation['metrics']['micro']['f1'] if task == 'NER' else re_model.selection_score(validation['metrics'], 'all_class_macro')
        improved = ner.dev_checkpoint_improved(score, best_score)
        if improved:
            best_score = score; best = validation; checkpoint = output/f'checkpoint_epoch_{epoch:02d}'
            model.save_pretrained(checkpoint, safe_serialization=True); tokenizer.save_pretrained(checkpoint)
        epochs.append({'epoch': epoch, 'steps': len(steps), 'dev': clean(validation), 'checkpointImproved': improved}); c.write_json(output/'epochs.json', epochs)
        print(json.dumps({'task': task, 'epoch': epoch, 'steps': len(steps), 'selectionScore': score}), flush=True)
    del model, optimizer; torch.cuda.empty_cache()
    restored = load_ner(checkpoint, parent_ner['bioLabels'], device) if task == 'NER' else re_model.load_relation_model(checkpoint, tokenizer, 'entity_markers').to(device)
    if evaluate(restored)['predictions'] != best['predictions'] or torch.equal(head, restored.classifier.weight.detach().cpu()) or torch.equal(encoder, restored.bert.encoder.layer[0].attention.self.query.weight.detach().cpu()): raise ValueError('Reload mismatch or unchanged classifier/encoder')
    predictions = [{'sampleId': r['sampleId'], 'referenceEntities': r['entities'], 'predictedEntities': p} if task == 'NER' else {'pairId': re_model.pair_id(r), 'sampleId': r['sampleId'], 'referenceLabel': r['label'], 'predictedLabel': p} for r, p in zip(rows['dev'], best['predictions'])]
    c.write_jsonl(output/'dev_predictions.jsonl', predictions)
    result = {'passed': True, 'task': task, 'trainInputs': len(rows['train']), 'devInputs': len(rows['dev']), 'epochs': len(epochs), 'steps': len(steps), 'bestCheckpoint': checkpoint.name,
        'baselineDev': clean(baseline), 'bestDev': clean(best), 'simpleBaselineDev': simple, 'classifierAndEncoderChanged': True, 'reloadPredictionsIdentical': True,
        'devUsedForGradient': False, 'testEvaluated': False, 'testTokenized': False, 'modelPromoted': False, 'qualityPromotionPassed': False, 'notice': 'Exposed AI-reference dev selection, not independent gold or final-test accuracy.'}
    c.write_json(output/'development_result.json', result); state.update(status='completed', steps=len(steps), elapsedSeconds=time.perf_counter()-started, finishedAtUTC=datetime.now(UTC).isoformat(), peakCUDAbytes=torch.cuda.max_memory_allocated(device)); c.write_json(output/'status.json', state)
    del restored; torch.cuda.empty_cache(); return checkpoint, result


def infer_ner(path, rows, tokenizer, parent, device):
    import torch
    from transformers import DataCollatorWithPadding
    model = load_ner(path, parent['bioLabels'], device).eval(); collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
    encoded = [encode_title(tokenizer, {k: d[k] for k in ('sampleId', 'text', 'textSha256')}, 512)[0] for d in rows]
    if any(r is None or 'labels' in r['features'] for r in encoded): raise ValueError('Label-free NER overlength/label leak')
    predictions = []; invalid = 0
    with torch.inference_mode():
        for start in range(0, len(rows), 2):
            chunk = encoded[start:start+2]; batch = {k: v.to(device) for k, v in collator([r['features'] for r in chunk]).items()}; logits = model(**batch).logits
            if not torch.isfinite(logits).all(): raise ValueError('Nonfinite NER inference logits')
            for row, record, labels in zip(rows[start:start+2], chunk, logits.argmax(-1).cpu().tolist()):
                decoded = ner.decode_bio(labels[:len(record['offsets'])], record['offsets'], row['text']); predictions.append(decoded['entities']); invalid += decoded['invalidTransitions']
    del model; torch.cuda.empty_cache()
    return predictions, {'metrics': ner.score_rows(rows, predictions, evaluation_target=TARGET), 'invalidTransitions': invalid, 'inferenceFeaturesContainLabels': False}


def gate_results(parent, data, comparison, ner_metrics):
    gates = parent['promotionGates']; results = comparison['pipelineMetrics']; baseline = results['old_NER_old_RE']['positiveMicro']; candidate = results['new_NER_new_RE']['positiveMicro']
    full_ids = {d['sampleId'] for d in data['dev']['full_relation']}; refs = [p for p in data['dev']['relation'] if p['sampleId'] in full_ids]
    checks = {'pipelinePrecisionNonRegression': candidate['precision'] >= baseline['precision'], 'pipelineF1NonRegression': candidate['f1'] >= baseline['f1'],
        'pipelineRecallRegressionWithinGuard': baseline['recall']-candidate['recall'] <= gates['maxAbsoluteRecallRegression'],
        'referenceDATASETSupport': ner_metrics['perClass']['DATASET']['reference'] >= gates['minimumReferenceDATASETDev'],
        'completeReferenceEVALUATED_ONSupport': sum(p['label'] == 'EVALUATED_ON' for p in refs) >= gates['minimumReferenceEVALUATED_ONDev'],
        'completeDocumentCoverage': len(full_ids)/19 >= gates['minimumDocumentCoverage']}
    return {'checks': checks, 'developmentGatesPassed': all(checks.values()), 'blockedBy': [k for k, passed in checks.items() if not passed], 'parentGates': gates,
        'finalTestExecuted': False, 'finalRareSupportKnown': False, 'qualityPromotionPassed': False, 'modelPromoted': False,
        'notice': 'Development guards are not final promotion. No final test, independent gold or automatic deployment.'}


def compare(config, parent, parent_re, data, checkpoints, output):
    import torch
    from transformers import BertTokenizerFast, DataCollatorWithPadding
    device = torch.device('cuda'); tokenizer = re_model.prepare_tokenizer(c.ROOT/parent_re['RETraining']['initialization']); collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
    ner_tokenizer = BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32', local_files_only=True, do_lower_case=True)
    all_dev = data['dev']['ner']; full = data['dev']['full_relation']; ids = {d['sampleId'] for d in full}; refs = [p for p in data['dev']['relation'] if p['sampleId'] in ids]
    entities = {}; ner_metrics = {}
    for name, path in (('old', c.ROOT/config['baselineNER']['path']), ('new', checkpoints['NER'])):
        predictions, metrics = infer_ner(path, all_dev, ner_tokenizer, parent, device); entities[name] = {d['sampleId']: p for d, p in zip(all_dev, predictions)}; ner_metrics[name] = metrics
        if name == 'new' and predictions != [p['predictedEntities'] for p in c.read_jsonl(output/'ner/dev_predictions.jsonl')]: raise ValueError('Label-free NER differs from selected dev predictions')
        c.write_jsonl(output/(name+'_ner_dev_predictions.jsonl'), [{'sampleId': d['sampleId'], 'referenceEntities': d['entities'], 'predictedEntities': p} for d, p in zip(all_dev, predictions)])
    module = {}; pipeline = {}
    for re_name, path in (('old', c.ROOT/parent_re['RETraining']['initialization']), ('new', checkpoints['RE'])):
        model = re_model.load_relation_model(path, tokenizer, 'entity_markers').to(device)
        known = predict(model, tokenizer, data['dev']['relation'], 512, collator, device, 4); module[re_name] = dev_scope(re_model.score_relations(data['dev']['relation'], [p['label'] for p in known])) | {'evaluationTarget': TARGET}
        c.write_jsonl(output/(re_name+'_module_dev_predictions.jsonl'), known)
        for ner_name in ('old', 'new'):
            name = ner_name+'_NER_'+re_name+'_RE'; candidates = [p for d in full for p in candidate_rows(d, entities[ner_name][d['sampleId']])]
            predicted = predict(model, tokenizer, candidates, 512, collator, device, 4); metrics = dev_scope(score_pipeline(full, refs, predicted), 'complete_document_exposed_dev_AI_reference_not_final_test')
            metrics.update(evaluationTarget='complete_document_exposed_dev_AI_reference_not_final_test', entityScope='predicted_NER_entities')
            errors = [e for d in full for e in diagnose(d, entities[ner_name][d['sampleId']], [p for p in refs if p['sampleId'] == d['sampleId']], [p for p in predicted if p['sampleId'] == d['sampleId']])]
            metrics['missedReferencePrimaryCauses'] = dict(Counter(e['primaryCause'] for e in errors))
            if len(errors) != metrics['positiveMicro']['reference']-metrics['positiveMicro']['truePositive']: raise ValueError('Missed-reference accounting mismatch')
            c.write_jsonl(output/(name+'_predictions.jsonl'), predicted); c.write_jsonl(output/(name+'_missed_relations.jsonl'), errors); pipeline[name] = metrics
        del model; torch.cuda.empty_cache()
    c.write_jsonl(output/'pipeline_dev_documents.jsonl', full); c.write_jsonl(output/'pipeline_dev_reference_pairs.jsonl', refs)
    result = {'evaluationTarget': TARGET, 'baselineNER': 'frozen_round35_abstract_not_production_round08', 'baselineRE': 'frozen_round15_title_RE',
        'nerDevMetrics': ner_metrics, 'moduleMetrics': module, 'pipelineMetrics': pipeline, 'moduleKnownPairs': 333, 'modulePairCoverage': 333/432,
        'pipelineDocuments': 7, 'queueDocuments': 19, 'pipelineDocumentCoverage': 7/19, 'pipelineReferencePairs': 107, 'pipelinePositiveReference': 84,
        'pipelineReferenceEVALUATED_ON': 0, 'zeroReferencePairDocuments': 1, 'testEvaluated': False, 'qualityPromotionPassed': False, 'modelPromoted': False}
    result['gates'] = gate_results(parent, data, result, ner_metrics['new']['metrics']); c.write_json(output/'pipeline_development_result.json', result)
    return result


def run(output):
    if output.exists(): raise FileExistsError('Preserve revised training run; no automatic retry')
    config, parent, parent_re, data = load_inputs()
    required_bytes = 6*sum((c.ROOT/s['initialization']/'model.safetensors').stat().st_size for s in (parent['NERTraining'], parent_re['RETraining']))+1_000_000_000
    storage = output.parent
    while not storage.exists(): storage = storage.parent
    if shutil.disk_usage(storage).free < required_bytes: raise ValueError('Insufficient free space for worst-case checkpoints plus reserve; no deletion')
    paths = [CONTRACT, c.ROOT/config['snapshot']/'manifest.json', c.ROOT/config['NERParent'], c.ROOT/config['REParent'], c.ROOT/config['revisionContract'], Path(__file__)]
    paths += [c.ROOT/'scripts'/name for name in ('review_eval_attribution.py', 'course_abstract_relation.py', 'course_abstract_v1.py', 'course_weak.py', 'course_graph.py', 'train_course_ner.py', 'train_course_relation.py', 'course_relation_model.py', 'train_abstract_relation.py', 'evaluate_course_relation.py', 'infer_course_corpus.py')]
    paths += [c.SCHEMA_PATH, c.CONFIG_PATH, c.ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt', c.ROOT/'kg_datasets/models/scibert_24f92d32/config.json', c.ROOT/config['baselineNER']['path']/'model.safetensors', (c.ROOT/config['baselineNER']['path']).parent/'manifest.json']
    for settings in (parent['NERTraining'], parent_re['RETraining']):
        initial = c.ROOT/settings['initialization']; paths += [initial/name for name in ('model.safetensors', 'config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'vocab.txt')] + [initial.parent/'manifest.json']
    hashes = {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in paths}; output.mkdir(parents=True); archive = output/'sources'; archive.mkdir()
    for i, p in enumerate(paths):
        if p.suffix != '.safetensors': shutil.copy2(p, archive/(str(i)+'_'+p.name))
    c.write_json(output/'contract.json', config)
    state = {'status': 'running', 'createdAtUTC': datetime.now(UTC).isoformat(), 'testEvaluated': False, 'testTokenized': False, 'modelPromoted': False}; c.write_json(output/'status.json', state); started = time.perf_counter()
    try:
        os.environ.setdefault('HF_HUB_OFFLINE', '1'); os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        import torch
        import transformers
        c.write_json(output/'environment.json', {'torch': torch.__version__, 'transformers': transformers.__version__, 'cuda': torch.version.cuda, 'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None})
        checkpoints = {}; results = {}
        for task, settings in (('NER', parent['NERTraining']), ('RE', parent_re['RETraining'])):
            checkpoints[task], results[task] = fit(task, data, settings, parent, config, output/task.lower())
        comparison = compare(config, parent, parent_re, data, checkpoints, output)
        for name, expected in (('old', results['RE']['baselineDev']['metrics']), ('new', results['RE']['bestDev']['metrics'])):
            if comparison['moduleMetrics'][name] != expected: raise ValueError('Label-free RE predictions differ from supervised dev evaluation')
        if any(c.file_sha256(c.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Experiment source/input drift')
        load_inputs(); c.write_json(output/'development_result.json', {'passed': True, 'version': config['version'], 'NER': results['NER'], 'RE': results['RE'], 'gates': comparison['gates'], 'testEvaluated': False, 'modelPromoted': False, 'qualityPromotionPassed': False})
        state.update(status='completed', finishedAtUTC=datetime.now(UTC).isoformat(), elapsedSeconds=time.perf_counter()-started); c.write_json(output/'status.json', state); seal(output, paths)
        print(json.dumps({'completed': True, 'NERsteps': results['NER']['steps'], 'REsteps': results['RE']['steps'], 'gates': comparison['gates']['checks'], 'modelPromoted': False}), flush=True)
    except Exception as error:
        for folder in (output, output/'ner', output/'re'):
            if folder.exists():
                state_path = folder/'status.json'; current = read(state_path) if state_path.exists() else {}
                if folder == output or current.get('status') != 'completed': c.write_json(state_path, current | {'status': 'failed_no_synthetic_fallback', 'errorType': type(error).__name__, 'error': str(error)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('preflight', 'train')); parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'preflight':
        _, _, _, data = load_inputs(); print(json.dumps({'loaded': True, 'NERtrain': len(data['train']['ner']), 'REtrain': len(data['train']['relation']), 'testConsumed': False}))
    else:
        if args.output is None: parser.error('train requires --output')
        run(args.output.resolve())
