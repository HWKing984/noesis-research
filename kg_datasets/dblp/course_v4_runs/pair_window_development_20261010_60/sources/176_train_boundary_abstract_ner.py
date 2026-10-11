"""One NER-only data experiment, single final checkpoint, fixed RE and frozen test."""
import argparse
import ctypes
import hashlib
import os
import random
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import train_benchmark_abstract_models as baseline
from course_abstract_v1 import read, seal

prior, c, g, ner, re_model = baseline.prior, baseline.c, baseline.g, baseline.ner, baseline.re_model
CONTRACT = c.ROOT/'resources/course_abstract_boundary_training_v1.json'


def load_inputs():
    config = read(CONTRACT)
    if config['version'] != 'abstract_boundary_training_v1' or config['automaticPromotionAllowed'] is not False or config['RETrainingAllowed'] is not False or config['reserveBytes'] != 1_000_000_000: raise ValueError('Boundary fit contract drift')
    _, parent, parent_re, data = baseline.load_inputs()
    folder = c.ROOT/config['snapshot']; manifest = g.verified_files(folder, config['snapshotManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Boundary input drift')
    original = data['train']['ner']; combined = c.read_jsonl(folder/'ner_train.jsonl'); expected = config['expected']
    refs = c.read_jsonl(folder/'additional_references.jsonl'); receipts = c.read_jsonl(folder/'additional_receipts.jsonl')
    if len(refs) != 8 or len(receipts) != 8 or len({r['arxivId'] for r in refs}) != 8: raise ValueError('Incomplete additional source cohort')
    accepted = []
    for ref, receipt in zip(refs, receipts):
        if ref['split'] != 'train' or ref['textKind'] != 'abstract' or hashlib.sha256(ref['text'].encode()).hexdigest() != ref['textSha256'] or c.validate_receipt(receipt, ref) or receipt['review'] is None: raise ValueError('Invalid additional annotation')
        if any(p['label'] != 'UNRESOLVED' for p in receipt['annotation']['relations']): raise ValueError('NER-only experiment contains new known RE labels')
        if c.eligible_tasks(receipt, ref)['ner']:
            accepted.append({'sampleId': ref['sampleId'], 'text': ref['text'], 'textSha256': ref['textSha256'], 'entities': receipt['annotation']['entities'], 'groupId': ref['groupId'], 'split': 'train', 'textKind': 'abstract', 'receiptSha256': receipt['contentSha256'], 'labelSource': 'ai_pseudo'})
    support = Counter(e['label'] for row in combined for e in row['entities'])
    if combined != original+accepted or len(original) != expected['originalNER'] or len(accepted) != expected['addedNER'] or len(combined) != expected['NERtrain'] or len(data['dev']['ner']) != expected['NERdev'] or support != {k: expected[k] for k in c.CONFIG['entityLabels']}: raise ValueError('Expanded NER inventory drift')
    if any(len({r[k] for r in combined}) != len(combined) for k in ('sampleId', 'groupId')) or {r['groupId'] for r in combined} & {r['groupId'] for r in data['dev']['ner']}: raise ValueError('Duplicate/cross-split paper')
    old = c.ROOT/read(baseline.CONTRACT)['snapshot']
    frozen = [p for p in old.iterdir() if p.is_file() and ('dev' in p.stem or p.name.startswith(('relation_', 'full_relation_')))]
    if len(frozen) != 11 or any(c.file_sha256(p) != c.file_sha256(folder/p.name) for p in frozen): raise ValueError('Frozen RE/dev bytes changed')
    run = c.ROOT/config['baselineRun']; g.verified_files(run, config['baselineManifestSha256'])
    for key in ('baselineNER', 'frozenRE'):
        if c.file_sha256(run/config[key]/'model.safetensors') != config[key+'WeightsSha256']: raise ValueError('Frozen46 weights changed')
    data['train']['ner'] = combined
    return config, parent, parent_re, data


def memory_available():
    class Memory(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)]+[(k, ctypes.c_ulonglong) for k in ('totalPhys', 'availPhys', 'totalPage', 'availPage', 'totalVirtual', 'availVirtual', 'extended')]
    status = Memory(); status.length = ctypes.sizeof(status)
    if os.name != 'nt' or not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)): raise ValueError('Cannot verify physical memory on this Windows training host')
    return status.availPhys


def clone_best(model):
    # shortcut: one best state on CPU, not resumable intermediate epochs; add resumption only if required.
    state = {name: value.detach().cpu().clone() for name, value in model.state_dict().items()}
    if any(t.device.type != 'cpu' or t.requires_grad for t in state.values()): raise ValueError('Best state must be detached CPU data')
    return state


def fit(data, parent, config, output):
    import torch
    from transformers import BertTokenizerFast, DataCollatorForTokenClassification
    settings = parent['NERTraining']; device = prior.setup(settings); torch.cuda.reset_peak_memory_stats(device); started = time.perf_counter()
    rows = {s: data[s]['ner'] for s in ('train', 'dev')}; output.mkdir()
    tokenizer = BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32', local_files_only=True, do_lower_case=True)
    collator = DataCollatorForTokenClassification(tokenizer, return_tensors='pt'); encoded = {s: [ner.encode_row(tokenizer, row, 512) for row in values] for s, values in rows.items()}
    for split in rows:
        for row, record in zip(rows[split], encoded[split]):
            decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else t for o, t in zip(record['offsets'], record['features']['labels'])], record['offsets'], row['text'])
            if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]: raise ValueError('BIO round-trip failed before fit')
    model = prior.load_ner(c.ROOT/settings['initialization'], parent['bioLabels'], device)
    head = model.classifier.weight.detach().cpu().clone(); encoder = model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu().clone()
    evaluate = lambda current: ner.evaluate_model(current, rows['dev'], encoded['dev'], prior.TARGET, collator=collator, device=device, batch_size=settings['batchSize'])
    initial = evaluate(model); lexicon = ner.make_dictionary(rows['train']); simple = ner.score_rows(rows['dev'], [ner.dictionary_predict(r['text'], lexicon) for r in rows['dev']], evaluation_target=prior.TARGET)
    c.write_json(output/'baseline_dev.json', prior.clean(initial)); c.write_json(output/'simple_baseline_dev.json', simple)
    for split in rows: c.write_jsonl(output/(split+'_inputs.jsonl'), rows[split])
    optimizer = torch.optim.AdamW(model.parameters(), lr=settings['learningRate'], weight_decay=0.01)
    best_score = None; best = None; best_state = None; best_epoch = None; epochs = []; steps = []; rng = random.Random(settings['seed'])
    c.write_json(output/'status.json', {'status': 'running', 'trainingStarted': True, 'settings': settings, 'device': 'cuda', 'testEvaluated': False, 'modelPromoted': False})
    for epoch in range(1, settings['epochs']+1):
        order = list(range(len(rows['train']))); rng.shuffle(order)
        for start in range(0, len(order), settings['batchSize']):
            indices = order[start:start+settings['batchSize']]; model.train(); optimizer.zero_grad(set_to_none=True)
            batch = {k: v.to(device) for k, v in collator([encoded['train'][i]['features'] for i in indices]).items()}; loss = model(**batch).loss
            if not torch.isfinite(loss): raise ValueError('Nonfinite training loss')
            loss.backward(); norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            if not torch.isfinite(norm): raise ValueError('Nonfinite gradient')
            optimizer.step(); steps.append({'step': len(steps)+1, 'epoch': epoch, 'loss': float(loss.detach()), 'gradientNorm': float(norm), 'inputIds': [rows['train'][i]['sampleId'] for i in indices]})
        validation = evaluate(model); score = validation['metrics']['micro']['f1']; improved = ner.dev_checkpoint_improved(score, best_score)
        if improved:
            best_state = None; best_state = clone_best(model); best_score = score; best = validation; best_epoch = epoch
        epochs.append({'epoch': epoch, 'steps': len(steps), 'dev': prior.clean(validation), 'checkpointImproved': improved, 'checkpointWritten': False})
        c.write_jsonl(output/'steps.jsonl', steps); c.write_json(output/'epochs.json', epochs)
        print({'epoch': epoch, 'steps': len(steps), 'strictDevNERF1': score}, flush=True)
    checkpoint = output/f'checkpoint_epoch_{best_epoch:02d}'; model.load_state_dict(best_state, strict=True); best_state = None
    model.save_pretrained(checkpoint, safe_serialization=True); tokenizer.save_pretrained(checkpoint)
    del model, optimizer; torch.cuda.empty_cache(); restored = prior.load_ner(checkpoint, parent['bioLabels'], device)
    if evaluate(restored)['predictions'] != best['predictions'] or torch.equal(head, restored.classifier.weight.detach().cpu()) or torch.equal(encoder, restored.bert.encoder.layer[0].attention.self.query.weight.detach().cpu()): raise ValueError('Reload mismatch or unchanged learned weights')
    c.write_jsonl(output/'dev_predictions.jsonl', [{'sampleId': r['sampleId'], 'referenceEntities': r['entities'], 'predictedEntities': p} for r, p in zip(rows['dev'], best['predictions'])])
    result = {'passed': True, 'trainInputs': len(rows['train']), 'devInputs': len(rows['dev']), 'epochs': len(epochs), 'steps': len(steps), 'bestCheckpoint': checkpoint.name, 'bestDev': prior.clean(best), 'initialDev': prior.clean(initial), 'simpleBaselineDev': simple, 'savedCheckpoints': 1, 'classifierAndEncoderChanged': True, 'reloadPredictionsIdentical': True, 'RETrained': False, 'devUsedForGradient': False, 'testEvaluated': False, 'modelPromoted': False}
    c.write_json(output/'development_result.json', result); c.write_json(output/'status.json', {'status': 'completed', 'elapsedSeconds': time.perf_counter()-started, 'peakCUDAbytes': torch.cuda.max_memory_allocated(device), 'steps': len(steps), 'trainingStarted': True, 'testEvaluated': False, 'modelPromoted': False})
    del restored; torch.cuda.empty_cache(); return checkpoint, result


def compare(config, parent, data, checkpoint, output):
    import torch
    from transformers import BertTokenizerFast, DataCollatorWithPadding
    device = prior.setup(parent['NERTraining']); run = c.ROOT/config['baselineRun']; historical = read(run/'pipeline_development_result.json')
    full = data['dev']['full_relation']; ids = {d['sampleId'] for d in full}; refs = [p for p in data['dev']['relation'] if p['sampleId'] in ids]
    supplement = c.ROOT/read(c.ROOT/'resources/course_abstract_boundary_expansion_v1.json')['supplement']; supp = c.read_jsonl(supplement/'ner_dev.jsonl')
    if len(supp) != 7 or {r['groupId'] for r in supp} & {r['groupId'] for r in data['train']['ner']}: raise ValueError('Supplement scope/leakage')
    tokenizer = BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32', local_files_only=True, do_lower_case=True)
    entities = {}; metrics = {}; supplemental = {}
    for name, path in (('old', run/config['baselineNER']), ('new', checkpoint)):
        predictions, metric = prior.infer_ner(path, data['dev']['ner'], tokenizer, parent, device); entities[name] = dict(zip([r['sampleId'] for r in data['dev']['ner']], predictions)); metrics[name] = metric
        if name == 'new' and predictions != [r['predictedEntities'] for r in c.read_jsonl(output/'ner/dev_predictions.jsonl')]: raise ValueError('Label-free selected NER parity failed')
        if name == 'old' and metric['metrics'] != historical['nerDevMetrics']['new']['metrics']: raise ValueError('Frozen46 NER replay drift')
        c.write_jsonl(output/(name+'_ner_dev_predictions.jsonl'), [{'sampleId': r['sampleId'], 'referenceEntities': r['entities'], 'predictedEntities': p} for r, p in zip(data['dev']['ner'], predictions)])
        predictions, supplemental[name] = prior.infer_ner(path, supp, tokenizer, parent, device)
        c.write_jsonl(output/(name+'_supplement_ner_predictions.jsonl'), [{'sampleId': r['sampleId'], 'referenceEntities': r['entities'], 'predictedEntities': p} for r, p in zip(supp, predictions)])
    tokenizer = re_model.prepare_tokenizer(run/config['frozenRE']); collator = DataCollatorWithPadding(tokenizer, return_tensors='pt'); model = re_model.load_relation_model(run/config['frozenRE'], tokenizer, 'entity_markers').to(device)
    pipeline = {}
    for name in ('old', 'new'):
        candidates = [p for doc in full for p in prior.candidate_rows(doc, entities[name][doc['sampleId']])]; predictions = prior.predict(model, tokenizer, candidates, 512, collator, device, 4)
        result = prior.dev_scope(prior.score_pipeline(full, refs, predictions), 'complete_document_exposed_dev_AI_reference_not_final_test')
        result.update(evaluationTarget='complete_document_exposed_dev_AI_reference_not_final_test', entityScope='predicted_NER_entities')
        errors = [e for doc in full for e in prior.diagnose(doc, entities[name][doc['sampleId']], [p for p in refs if p['sampleId'] == doc['sampleId']], [p for p in predictions if p['sampleId'] == doc['sampleId']])]
        result['missedReferencePrimaryCauses'] = dict(Counter(e['primaryCause'] for e in errors)); pipeline[name] = result
        if len(errors) != result['positiveMicro']['reference']-result['positiveMicro']['truePositive']: raise ValueError('Missed-reference accounting mismatch')
        c.write_jsonl(output/(name+'_pipeline_predictions.jsonl'), predictions); c.write_jsonl(output/(name+'_missed_relations.jsonl'), errors)
    if pipeline['old'] != historical['pipelineMetrics']['new_NER_new_RE']: raise ValueError('Frozen46 pipeline replay drift')
    del model; torch.cuda.empty_cache()
    compatibility = {'pipelineMetrics': {'old_NER_old_RE': pipeline['old'], 'new_NER_new_RE': pipeline['new']}}
    gates = prior.gate_results(parent, data, compatibility, metrics['new']['metrics'])
    gates['checks']['DATASETRecallRegressionWithinGuard'] = metrics['old']['metrics']['perClass']['DATASET']['recall']-metrics['new']['metrics']['perClass']['DATASET']['recall'] <= config['maxAbsoluteDATASETRecallRegression']
    gates.update(developmentGatesPassed=all(gates['checks'].values()), blockedBy=[k for k, ok in gates['checks'].items() if not ok], independentHumanGoldRequired=False)
    result = {'historicalNER': metrics, 'historicalPipeline': pipeline, 'supplementNER': supplemental, 'gates': gates, 'completeDocuments': 7, 'lockedQueue': 19, 'documentCoverage': 7/19, 'positiveReference': 84, 'completeReferenceEVALUATED_ON': 0, 'supplementNERDocuments': 7, 'supplementQueue': 8, 'supplementCompletePipelineMetrics': None, 'supplementCompleteDocuments': 0, 'RETrained': False, 'testEvaluated': False, 'independentHumanGold': False, 'qualityPromotionPassed': False, 'modelPromoted': False, 'notice': 'Previously exposed AI dev agreement, not blind test or verified semantic correctness. Frozen46 RE on both arms; unknown pairs never negative.'}
    c.write_json(output/'comparison.json', result); return result


def run(output):
    if output.exists(): raise FileExistsError('Preserve run and failed attempts')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp/course_v4_runs').resolve()): raise ValueError('Run output outside dataset runs')
    config, parent, _, data = load_inputs(); old_config = read(baseline.CONTRACT); initial = c.ROOT/parent['NERTraining']['initialization']; frozen = c.ROOT/config['baselineRun']
    paths = [CONTRACT, Path(__file__), c.ROOT/'tests/test_boundary_ner_training.py', c.ROOT/config['snapshot']/'manifest.json', frozen/'manifest.json', baseline.CONTRACT, Path(baseline.__file__), Path(prior.__file__)]
    paths += [c.ROOT/old_config[k] for k in ('NERParent', 'REParent', 'revisionContract')]
    paths += [c.ROOT/'scripts'/n for n in ('course_abstract_v1.py', 'course_weak.py', 'course_graph.py', 'train_course_ner.py', 'train_course_relation.py', 'course_relation_model.py', 'evaluate_course_relation.py', 'infer_course_corpus.py', 'train_abstract_relation.py', 'course_abstract_relation.py', 'review_eval_attribution.py')]
    paths += [c.CONFIG_PATH, c.SCHEMA_PATH, c.ROOT/'resources/course_graph_runtime.json', c.ROOT/'resources/course_graph_quality_runtime.json', c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl']
    for folder in (initial, frozen/config['baselineNER'], frozen/config['frozenRE']): paths += [folder/n for n in ('model.safetensors', 'config.json', 'vocab.txt', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json')]
    hashes = {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in paths}; output.mkdir(parents=True); c.write_json(output/'selection_lock.json', {'createdAtUTC': datetime.now(UTC).isoformat(), 'config': config, 'inputSha256': hashes}); started = time.perf_counter()
    try:
        os.environ.setdefault('HF_HUB_OFFLINE', '1'); os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        import torch
        import transformers
        probe = torch.nn.Linear(2, 1); probe_state = clone_best(probe); before = probe_state['weight'].clone()
        with torch.no_grad(): probe.weight.add_(1)
        if not torch.equal(before, probe_state['weight']) or torch.equal(probe.weight, before): raise ValueError('Best-state copy is not immutable')
        probe.load_state_dict(probe_state, strict=True)
        if not torch.equal(probe.weight, before): raise ValueError('Best-state restoration failed')
        del probe, probe_state, before
        size = (initial/'model.safetensors').stat().st_size; free = shutil.disk_usage(output).free; available = memory_available(); gpu_free = torch.cuda.mem_get_info()[0] if torch.cuda.is_available() else 0
        required = size+config['reserveBytes']+config['artifactMarginBytes']; cpu_required = 2*size+config['CPUReserveBytes']
        c.write_json(output/'preflight.json', {'freeDiskBytes': free, 'requiredBytes': required, 'availableCPUBytes': available, 'requiredCPUBytes': cpu_required, 'GPUFreeBytes': gpu_free, 'GPUFreeRequiredBytes': config['GPUFreeMinimumBytes'], 'historicalDeletion': False, 'testContentConsumed': False})
        if free < required or available < cpu_required or gpu_free < config['GPUFreeMinimumBytes']: raise ValueError('Insufficient checked memory/storage; no deletion, CPU fallback or lowered reserves')
        c.write_json(output/'environment.json', {'torch': torch.__version__, 'transformers': transformers.__version__, 'gpu': torch.cuda.get_device_name(0), 'cuda': torch.version.cuda})
        archive = output/'sources'; archive.mkdir()
        for i, p in enumerate(paths):
            if p.suffix != '.safetensors' and p.name != 'test_references.jsonl': shutil.copy2(p, archive/(str(i)+'_'+p.name))
        checkpoint, training = fit(data, parent, config, output/'ner'); comparison = compare(config, parent, data, checkpoint, output)
        if len(list((output/'ner').glob('checkpoint_*'))) != 1 or any(c.file_sha256(c.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Checkpoint count or input drift')
        load_inputs(); c.write_json(output/'development_result.json', {'passed': True, 'NER': training, 'comparison': comparison, 'qualityPromotionPassed': False, 'modelPromoted': False, 'testEvaluated': False})
        c.write_json(output/'status.json', {'status': 'completed', 'elapsedSeconds': time.perf_counter()-started, 'trainingExecuted': True, 'RETrained': False, 'testEvaluated': False, 'modelPromoted': False}); seal(output, paths)
        print({'completed': True, 'steps': training['steps'], 'gates': comparison['gates']['checks'], 'modelPromoted': False}, flush=True)
    except Exception as error:
        c.write_json(output/'status.json', {'status': 'failed_no_synthetic_fallback', 'errorType': type(error).__name__, 'error': str(error), 'testEvaluated': False, 'modelPromoted': False})
        if (output/'ner').exists() and not (output/'ner/development_result.json').exists(): c.write_json(output/'ner/status.json', {'status': 'failed_no_synthetic_fallback', 'error': str(error)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('preflight', 'train')); parser.add_argument('--output', type=Path); args = parser.parse_args()
    if args.action == 'preflight':
        _, _, _, data = load_inputs(); print({'NERtrain': len(data['train']['ner']), 'NERdev': len(data['dev']['ner']), 'RETrainUnchanged': len(data['train']['relation']), 'testConsumed': False})
    elif args.output is None: parser.error('New output required')
    else: run(args.output.resolve())
