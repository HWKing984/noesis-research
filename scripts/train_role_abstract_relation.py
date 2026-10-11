"""One RE data experiment with frozen52 NER; no final test or deployment."""
import argparse
import os
import random
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import train_boundary_abstract_ner as boundary
import diagnose_train_roles as diagnostic
from course_abstract_v1 import read, seal
from evaluate_abstract_decoder import error_summary

prior, c, g, ner, re_model = boundary.prior, boundary.c, boundary.g, boundary.ner, boundary.re_model
CONTRACT = c.ROOT/'resources/course_abstract_role_training_v1.json'


def load_inputs():
    config = read(CONTRACT)
    if config['version'] != 'abstract_role_training_v1' or config['automaticPromotionAllowed'] is not False or config['NERTrainingAllowed'] is not False or config['reserveBytes'] != 1_000_000_000 or config['optimizer'] != {'weightDecay': 0.01, 'clipGradientNorm': 1.0}: raise ValueError('Role training contract drift')
    old_config, parent, parent_re, data = boundary.load_inputs(); added, original, old_re = diagnostic.load_inputs()
    folder = c.ROOT/config['snapshot']; manifest = g.verified_files(folder, config['snapshotManifestSha256'])
    if folder != diagnostic.SOURCE or original != data['train']['relation']: raise ValueError('Role input/baseline scope drift')
    _, _, refs, _ = diagnostic.role.load_sources(); receipts = c.read_jsonl(folder/'reviewed_receipts.jsonl')
    docs, pairs, full, excluded, unknown, total = diagnostic.role.rows_for(refs, receipts)
    if pairs != c.read_jsonl(folder/'relation_train.jsonl') or full != c.read_jsonl(folder/'full_relation_train.jsonl') or excluded != c.read_jsonl(folder/'excluded_ner_train.jsonl'): raise ValueError('Role rows differ from reviewed references')
    if (len(pairs), len(added), unknown, total, len(docs)) != (386, 115, 1971, 2357, 65) or Counter(p['label'] for p in pairs) != {'USED_FOR': 288, 'EVALUATED_ON': 64, 'NO_RELATION': 34}: raise ValueError('Role inventory drift')
    old_keys = {re_model.pair_key(p) for p in original}
    if [p for p in pairs if re_model.pair_key(p) in old_keys] != original or [p for p in pairs if re_model.pair_key(p) not in old_keys] != added: raise ValueError('Known training rows changed')
    if c.read_jsonl(folder/'ner_train_frozen.jsonl') != data['train']['ner'] or [(d['sampleId'], d['textSha256'], d['entities']) for d in docs] != [(d['sampleId'], d['textSha256'], d['entities']) for d in data['train']['ner']]: raise ValueError('Frozen NER changed')
    dev_folder = c.ROOT/old_config['snapshot']; dev = [p for p in dev_folder.iterdir() if p.is_file() and 'dev' in p.stem]
    dev_refs = c.read_jsonl(dev_folder/'dev_references.jsonl')
    if len(dev) != 9 or any(c.file_sha256(p) != manifest['filesSha256'][p.name] for p in dev) or {r['groupId'] for r in refs} & {r['groupId'] for r in dev_refs}: raise ValueError('Dev bytes or split isolation changed')
    frozen = c.ROOT/config['frozenNERRun']; frozen_manifest = g.verified_files(frozen, config['frozenNERManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in frozen_manifest['inputSha256'].items()) or c.file_sha256(frozen/config['frozenNER']/'model.safetensors') != config['frozenNERWeightsSha256']: raise ValueError('Frozen52 NER/input drift')
    full_ids = {d['sampleId'] for d in data['dev']['full_relation']}; full_pairs = [p for p in data['dev']['relation'] if p['sampleId'] in full_ids]
    expected = config['expected']; actual = {'trainKnown': len(pairs), 'newKnown': len(added), 'trainUnknown': unknown, 'trainEligible': total, 'NERTrainFrozen': len(docs), 'devKnown': len(data['dev']['relation']), 'completeDev': len(full_ids), 'completeDevPairs': len(full_pairs), 'completeDevPositive': sum(p['label'] != 'NO_RELATION' for p in full_pairs)}
    if actual != expected: raise ValueError('Locked expected inventory differs')
    data['train'].update(relation=pairs, full_relation=full, excluded_ner=excluded)
    return config, parent, parent_re, data, old_re, added


def fit(data, settings, config, output):
    import torch
    from transformers import DataCollatorWithPadding
    device = prior.setup(settings); torch.cuda.reset_peak_memory_stats(device); started = time.perf_counter(); output.mkdir()
    rows = {s: data[s]['relation'] for s in ('train', 'dev')}; initial = c.ROOT/settings['initialization']
    tokenizer = re_model.prepare_tokenizer(initial); collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
    encoded = {s: [re_model.encode_pair(tokenizer, r, 512) for r in values] for s, values in rows.items()}
    model = re_model.load_relation_model(initial, tokenizer, 'entity_markers').to(device)
    head = model.classifier.weight.detach().cpu().clone(); encoder = model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu().clone()
    evaluate = lambda current: re_model.evaluate_model(current, rows['dev'], encoded['dev'], collator, device, settings['batchSize'])
    initial_dev = evaluate(model); mapping = re_model.type_majority(rows['train'])
    simple = prior.dev_scope(re_model.score_relations(rows['dev'], [mapping[r['tail']['label']] for r in rows['dev']]))
    c.write_json(output/'baseline_dev.json', prior.clean(initial_dev)); c.write_json(output/'simple_baseline_dev.json', simple)
    for split in rows: c.write_jsonl(output/(split+'_inputs.jsonl'), rows[split])
    weights = torch.tensor(re_model.class_weights(rows['train'], settings['balancedLoss']), dtype=torch.float32, device=device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings['learningRate'], weight_decay=config['optimizer']['weightDecay'])
    best_score = None; best = None; best_state = None; best_epoch = None; epochs = []; steps = []; rng = random.Random(settings['seed'])
    c.write_json(output/'status.json', {'status': 'running', 'trainingStarted': True, 'settings': settings, 'classWeights': dict(zip(re_model.LABELS, weights.cpu().tolist())), 'testEvaluated': False, 'modelPromoted': False})
    for epoch in range(1, settings['epochs']+1):
        order = list(range(len(rows['train']))); rng.shuffle(order)
        for start in range(0, len(order), settings['batchSize']):
            indices = order[start:start+settings['batchSize']]; model.train(); optimizer.zero_grad(set_to_none=True)
            logits, targets = re_model.forward_batch(model, [encoded['train'][i] for i in indices], collator, device)
            loss = torch.nn.functional.cross_entropy(logits, targets, weight=weights)
            if not torch.isfinite(loss): raise ValueError('Nonfinite training loss')
            loss.backward(); norm = torch.nn.utils.clip_grad_norm_(model.parameters(), config['optimizer']['clipGradientNorm'])
            if not torch.isfinite(norm): raise ValueError('Nonfinite gradient')
            optimizer.step(); steps.append({'step': len(steps)+1, 'epoch': epoch, 'loss': float(loss.detach()), 'gradientNorm': float(norm), 'inputIds': [re_model.pair_id(rows['train'][i]) for i in indices]})
        validation = evaluate(model); score = re_model.selection_score(validation['metrics'], 'all_class_macro'); improved = ner.dev_checkpoint_improved(score, best_score)
        if improved:
            best_state = None; best_state = boundary.clone_best(model); best_score = score; best = validation; best_epoch = epoch
        epochs.append({'epoch': epoch, 'steps': len(steps), 'dev': prior.clean(validation), 'checkpointImproved': improved, 'checkpointWritten': False})
        c.write_jsonl(output/'steps.jsonl', steps); c.write_json(output/'epochs.json', epochs)
        print({'task': 'RE', 'epoch': epoch, 'steps': len(steps), 'allClassDevMacroF1': score}, flush=True)
    checkpoint = output/f'checkpoint_epoch_{best_epoch:02d}'; model.load_state_dict(best_state, strict=True); best_state = None
    model.save_pretrained(checkpoint, safe_serialization=True); tokenizer.save_pretrained(checkpoint)
    del model, optimizer; torch.cuda.empty_cache(); restored = re_model.load_relation_model(checkpoint, tokenizer, 'entity_markers').to(device)
    if evaluate(restored)['predictions'] != best['predictions'] or torch.equal(head, restored.classifier.weight.detach().cpu()) or torch.equal(encoder, restored.bert.encoder.layer[0].attention.self.query.weight.detach().cpu()): raise ValueError('Reload mismatch or unchanged encoder/head')
    c.write_jsonl(output/'dev_predictions.jsonl', [{'pairId': re_model.pair_id(r), 'sampleId': r['sampleId'], 'referenceLabel': r['label'], 'predictedLabel': p} for r, p in zip(rows['dev'], best['predictions'])])
    result = {'passed': True, 'task': 'RE', 'trainInputs': len(rows['train']), 'devInputs': len(rows['dev']), 'epochs': len(epochs), 'steps': len(steps), 'bestCheckpoint': checkpoint.name, 'baselineDev': prior.clean(initial_dev), 'bestDev': prior.clean(best), 'simpleBaselineDev': simple,
        'savedCheckpoints': 1, 'classifierAndEncoderChanged': True, 'reloadPredictionsIdentical': True, 'NERTrained': False, 'devUsedForGradient': False, 'testEvaluated': False, 'modelPromoted': False}
    c.write_json(output/'development_result.json', result); c.write_json(output/'status.json', {'status': 'completed', 'elapsedSeconds': time.perf_counter()-started, 'peakCUDAbytes': torch.cuda.max_memory_allocated(device), 'steps': len(steps), 'trainingStarted': True, 'testEvaluated': False, 'modelPromoted': False})
    del restored; torch.cuda.empty_cache(); return checkpoint, result


def gates(parent, data, pipeline, module, ner_metrics):
    result = prior.gate_results(parent, data, {'pipelineMetrics': {'old_NER_old_RE': pipeline['old'], 'new_NER_new_RE': pipeline['new']}}, ner_metrics)
    checks = result['checks']
    checks['completeDevFalsePositiveNonRegression'] = pipeline['new']['positiveMicro']['predicted']-pipeline['new']['positiveMicro']['truePositive'] <= pipeline['old']['positiveMicro']['predicted']-pipeline['old']['positiveMicro']['truePositive']
    checks['knownDevNegativeRecallNonRegression'] = module['new']['perClass']['NO_RELATION']['recall'] >= module['old']['perClass']['NO_RELATION']['recall']
    result.update(developmentGatesPassed=all(checks.values()), blockedBy=[k for k, ok in checks.items() if not ok])
    return result


def compare(config, parent, parent_re, data, old_re, added, checkpoint, output):
    import torch
    from transformers import BertTokenizerFast, DataCollatorWithPadding
    device = prior.setup(parent_re['RETraining']); frozen = c.ROOT/config['frozenNERRun']
    tokenizer = BertTokenizerFast.from_pretrained(frozen/config['frozenNER'], local_files_only=True, do_lower_case=True)
    predictions, ner_metrics = prior.infer_ner(frozen/config['frozenNER'], data['dev']['ner'], tokenizer, parent, device)
    if predictions != [p['predictedEntities'] for p in c.read_jsonl(frozen/'new_ner_dev_predictions.jsonl')] or ner_metrics != read(frozen/'comparison.json')['historicalNER']['new']: raise ValueError('Frozen52 label-free NER parity failed')
    c.write_jsonl(output/'frozen_ner_dev_predictions.jsonl', [{'sampleId': d['sampleId'], 'referenceEntities': d['entities'], 'predictedEntities': p} for d, p in zip(data['dev']['ner'], predictions)])
    by_id = dict(zip([d['sampleId'] for d in data['dev']['ner']], predictions)); full = data['dev']['full_relation']; ids = {d['sampleId'] for d in full}; refs = [p for p in data['dev']['relation'] if p['sampleId'] in ids]
    candidates = [p for d in full for p in prior.candidate_rows(d, by_id[d['sampleId']])]
    tokenizer = re_model.prepare_tokenizer(old_re); collator = DataCollatorWithPadding(tokenizer, return_tensors='pt'); pipeline = {}; module = {}; train = {}
    for name, path in (('old', old_re), ('new', checkpoint)):
        model = re_model.load_relation_model(path, tokenizer, 'entity_markers').to(device).requires_grad_(False)
        known = prior.predict(model, tokenizer, data['dev']['relation'], 512, collator, device, 4)
        module[name] = prior.dev_scope(re_model.score_relations(data['dev']['relation'], [p['label'] for p in known]))
        expected = read(old_re.parent/'development_result.json') if name == 'old' else read(output/'re/development_result.json')
        if module[name] != expected['bestDev']['metrics']: raise ValueError('Label-free RE reload parity failed')
        c.write_jsonl(output/(name+'_module_dev_predictions.jsonl'), known)
        scored = prior.predict(model, tokenizer, candidates, 512, collator, device, 4)
        metrics = prior.dev_scope(prior.score_pipeline(full, refs, scored), 'complete_document_exposed_dev_AI_reference_not_final_test')
        causes, false = error_summary(full, refs, scored)
        missed = [e for d in full for e in prior.diagnose(d, by_id[d['sampleId']], [p for p in refs if p['sampleId'] == d['sampleId']], [p for p in scored if p['sampleId'] == d['sampleId']])]
        if len(false) != metrics['positiveMicro']['predicted']-metrics['positiveMicro']['truePositive'] or len(missed) != metrics['positiveMicro']['reference']-metrics['positiveMicro']['truePositive']: raise ValueError('FP/FN accounting drift')
        metrics.update(entityScope='fixed52_predicted_NER_entities', endpointMismatch=causes, missedReferencePrimaryCauses=dict(Counter(e['primaryCause'] for e in missed))); pipeline[name] = metrics
        if name == 'old' and metrics['positiveMicro'] != read(frozen/'comparison.json')['historicalPipeline']['new']['positiveMicro']: raise ValueError('Old52+46 pipeline replay drift')
        c.write_jsonl(output/(name+'_pipeline_predictions.jsonl'), scored); c.write_jsonl(output/(name+'_false_relations.jsonl'), false); c.write_jsonl(output/(name+'_missed_relations.jsonl'), missed)
        train_predictions = prior.predict(model, tokenizer, added, 512, collator, device, 4); train[name] = diagnostic.scored(added, train_predictions)
        if name == 'old':
            old_run = c.ROOT/'kg_datasets/dblp/course_v4_runs/role_diagnostic_20261009_53'; manifest = g.verified_files(old_run)
            if manifest['inputSha256'].get('kg_datasets/dblp/course_abstract_role_enriched_20261009_53/manifest.json') != config['snapshotManifestSha256'] or train[name] != read(old_run/'diagnostic_result.json')['model']: raise ValueError('Old TRAIN diagnostic replay drift')
        c.write_jsonl(output/(name+'_new_train_predictions.jsonl'), train_predictions)
        c.write_jsonl(output/(name+'_new_train_errors.jsonl'), [{'reference': r, 'prediction': p} for r, p in zip(added, train_predictions) if r['label'] != p['label']])
        del model; torch.cuda.empty_cache()
    result = {'evaluationTarget': prior.TARGET, 'fixedNER': 'frozen52_not_production', 'baselineRE': 'frozen46_not_production', 'candidateRE': 'new54', 'NER': ner_metrics, 'module': module, 'pipeline': pipeline, 'newTrainDiagnostic': train,
        'moduleKnownPairs': 333, 'modulePairCoverage': 333/432, 'completeDocuments': 7, 'lockedQueue': 19, 'documentCoverage': 7/19, 'positiveReference': 84, 'completeReferenceEVALUATED_ON': 0, 'zeroReferencePairDocuments': 1,
        'NERTrained': False, 'testEvaluated': False, 'independentHumanGold': False, 'qualityPromotionPassed': False, 'modelPromoted': False, 'notice': 'Previously exposed AI dev, not final test. New TRAIN role agreement is fit diagnostic only; correlated mentions are not independent evidence. No supplemental pipeline or automatic deployment.'}
    result['gates'] = gates(parent, data, pipeline, module, ner_metrics['metrics']); c.write_json(output/'comparison.json', result)
    c.write_jsonl(output/'pipeline_dev_documents.jsonl', full); c.write_jsonl(output/'pipeline_dev_reference_pairs.jsonl', refs)
    return result


def run(output):
    if output.exists(): raise FileExistsError('Preserve training run and failures')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp/course_v4_runs').resolve()): raise ValueError('Output outside runs')
    config, parent, parent_re, data, old_re, added = load_inputs(); initial = c.ROOT/parent_re['RETraining']['initialization']; frozen = c.ROOT/config['frozenNERRun']
    paths = [CONTRACT, Path(__file__), Path(boundary.__file__), Path(diagnostic.__file__), Path(diagnostic.role.__file__), Path(prior.__file__), boundary.CONTRACT, boundary.baseline.CONTRACT, Path(boundary.baseline.__file__), diagnostic.role.CONTRACT,
        c.ROOT/config['snapshot']/'manifest.json', frozen/'manifest.json', old_re.parent.parent/'manifest.json', initial.parent/'manifest.json', c.ROOT/'tests/test_role_relation_training.py', c.CONFIG_PATH, c.SCHEMA_PATH]
    paths += [c.ROOT/'resources'/n for n in ('course_abstract_v1.json', 'course_abstract_relation_v1.json', 'course_graph_runtime.json', 'course_graph_quality_runtime.json')]
    paths += [c.ROOT/'scripts'/n for n in ('course_abstract_v1.py', 'course_abstract_relation.py', 'course_weak.py', 'course_graph.py', 'train_course_ner.py', 'train_course_relation.py', 'course_relation_model.py', 'evaluate_course_relation.py', 'evaluate_abstract_decoder.py', 'infer_course_corpus.py', 'train_abstract_relation.py', 'review_eval_attribution.py')]
    paths += [c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl']
    for folder in (initial, old_re, frozen/config['frozenNER']): paths += [folder/n for n in ('model.safetensors', 'config.json', 'vocab.txt', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json')]
    hashes = {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in paths}; output.mkdir(parents=True)
    c.write_json(output/'selection_lock.json', {'createdAtUTC': datetime.now(UTC).isoformat(), 'config': config, 'inputSha256': hashes}); started = time.perf_counter()
    try:
        os.environ.setdefault('HF_HUB_OFFLINE', '1'); os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        import torch
        import transformers
        size = (initial/'model.safetensors').stat().st_size; free = shutil.disk_usage(output).free; cpu = boundary.memory_available(); gpu = torch.cuda.mem_get_info()[0] if torch.cuda.is_available() else 0
        required = size+config['reserveBytes']+config['artifactMarginBytes']; cpu_required = 2*size+config['CPUReserveBytes']
        c.write_json(output/'preflight.json', {'freeDiskBytes': free, 'requiredBytes': required, 'availableCPUBytes': cpu, 'requiredCPUBytes': cpu_required, 'GPUFreeBytes': gpu, 'GPUFreeRequiredBytes': config['GPUFreeMinimumBytes'], 'historicalDeletion': False, 'testContentConsumed': False})
        if free < required or cpu < cpu_required or gpu < config['GPUFreeMinimumBytes']: raise ValueError('Insufficient checked memory/storage; no deletion or lowered reserve')
        c.write_json(output/'environment.json', {'torch': torch.__version__, 'transformers': transformers.__version__, 'gpu': torch.cuda.get_device_name(0), 'cuda': torch.version.cuda})
        archive = output/'sources'; archive.mkdir()
        for i, p in enumerate(paths):
            if p.suffix != '.safetensors' and p.name != 'test_references.jsonl': shutil.copy2(p, archive/(str(i)+'_'+p.name))
        checkpoint, training = fit(data, parent_re['RETraining'], config, output/'re'); comparison = compare(config, parent, parent_re, data, old_re, added, checkpoint, output)
        if len(list((output/'re').glob('checkpoint_*'))) != 1 or any(c.file_sha256(c.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Checkpoint/input/source drift')
        load_inputs(); c.write_json(output/'development_result.json', {'passed': True, 'RE': training, 'comparison': comparison, 'qualityPromotionPassed': False, 'modelPromoted': False, 'testEvaluated': False})
        c.write_json(output/'status.json', {'status': 'completed', 'elapsedSeconds': time.perf_counter()-started, 'trainingExecuted': True, 'NERTrained': False, 'testEvaluated': False, 'modelPromoted': False}); seal(output, paths)
        print({'completed': True, 'REsteps': training['steps'], 'gates': comparison['gates']['checks'], 'modelPromoted': False}, flush=True)
    except Exception as error:
        c.write_json(output/'status.json', {'status': 'failed_no_synthetic_fallback', 'errorType': type(error).__name__, 'error': str(error), 'testEvaluated': False, 'modelPromoted': False})
        if (output/'re').exists() and not (output/'re/development_result.json').exists(): c.write_json(output/'re/status.json', {'status': 'failed_no_synthetic_fallback', 'error': str(error)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('preflight', 'train')); parser.add_argument('--output', type=Path); args = parser.parse_args()
    if args.action == 'preflight':
        _, _, _, data, _, added = load_inputs(); print({'REtrain': len(data['train']['relation']), 'addedKnown': len(added), 'NERtrainFrozen': len(data['train']['ner']), 'devKnown': len(data['dev']['relation']), 'testConsumed': False})
    elif args.output is None: parser.error('New output required')
    else: run(args.output.resolve())
