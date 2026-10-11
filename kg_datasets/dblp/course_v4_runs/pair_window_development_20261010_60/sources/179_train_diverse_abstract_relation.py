"""One408-pair RE experiment; reuse sealed trainers without editing historical inputs."""
import argparse
import os
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import train_role_abstract_relation as old
import diagnose_diverse_train_roles as diverse

c, g, prior, re_model, read, seal = old.c, old.g, old.prior, old.re_model, old.read, old.seal
CONTRACT = c.ROOT/'resources/course_diverse_role_training_v1.json'


def load_inputs():
    config = read(CONTRACT)
    if config['version'] != 'abstract_diverse_role_training_v1' or config['expectedSteps'] != 612 or any(config[k] is not False for k in ('NERTrainingAllowed', 'automaticPromotionAllowed')) or config['reserveBytes'] != 1_000_000_000 or config['optimizer'] != {'weightDecay': 0.01, 'clipGradientNorm': 1.0}: raise ValueError('Diverse fit contract drift')
    if c.ROOT/config['evaluationRecipe'] != old.CONTRACT or c.file_sha256(old.CONTRACT) != config['evaluationRecipeSha256']: raise ValueError('Evaluation recipe drift')
    recipe, parent, parent_re, data, old_re, legacy = old.load_inputs(); added, original, _ = diverse.load_inputs()
    if c.ROOT/config['snapshot'] != diverse.SOURCE or config['snapshotManifestSha256'] != diverse.SOURCE_SHA or original != data['train']['relation']: raise ValueError('Training scope drift')
    manifest = g.verified_files(diverse.SOURCE, diverse.SOURCE_SHA)
    refs = c.read_jsonl(diverse.SOURCE/'references.jsonl'); receipts = c.read_jsonl(diverse.SOURCE/'reviewed_receipts.jsonl')
    docs, pairs, full, excluded, unknown, total = diverse.diverse.role.rows_for(refs, receipts)
    if full != c.read_jsonl(diverse.SOURCE/'full_relation_train.jsonl') or excluded != c.read_jsonl(diverse.SOURCE/'excluded_ner_train.jsonl') or Counter(p['label'] for p in pairs) != {'USED_FOR': 307, 'EVALUATED_ON': 64, 'NO_RELATION': 37}: raise ValueError('Train inventory drift')
    if c.read_jsonl(diverse.SOURCE/'ner_train_frozen.jsonl') != data['train']['ner'] or [(d['sampleId'], d['textSha256'], d['entities']) for d in docs] != [(d['sampleId'], d['textSha256'], d['entities']) for d in data['train']['ner']]: raise ValueError('Frozen NER drift')
    previous = c.ROOT/recipe['snapshot']; dev = [p for p in previous.iterdir() if p.is_file() and 'dev' in p.stem]
    dev_refs = c.read_jsonl(previous/'dev_references.jsonl')
    if len(dev) != 9 or any(c.file_sha256(p) != manifest['filesSha256'][p.name] for p in dev) or {r['groupId'] for r in refs} & {r['groupId'] for r in dev_refs}: raise ValueError('Dev bytes or group isolation drift')
    ids = {d['sampleId'] for d in data['dev']['full_relation']}; complete = [p for p in data['dev']['relation'] if p['sampleId'] in ids]
    dev_receipts = c.read_jsonl(previous/'dev_reviewed_receipts.jsonl')
    _, _, _, _, _, eligible = diverse.diverse.role.rows_for(dev_refs, dev_receipts)
    actual = {'trainKnown': len(pairs), 'newKnown': len(added), 'trainUnknown': unknown, 'trainEligible': total, 'NERTrainFrozen': len(docs), 'devKnown': len(data['dev']['relation']), 'devEligible': eligible, 'completeDev': len(ids), 'lockedDev': len(dev_refs), 'completeDevPairs': len(complete), 'completeDevPositive': sum(p['label'] != 'NO_RELATION' for p in complete), 'completeDevEVALUATED_ON': sum(p['label'] == 'EVALUATED_ON' for p in complete), 'zeroReferenceDocuments': sum(not any(p['sampleId'] == d['sampleId'] for p in complete) for d in data['dev']['full_relation'])}
    if actual != config['expected'] or 6*((len(pairs)+3)//4) != config['expectedSteps']: raise ValueError('Locked expected inventory drift')
    for key in ('artifactMarginBytes', 'CPUReserveBytes', 'GPUFreeMinimumBytes'):
        if config[key] != recipe[key]: raise ValueError('Historical resource budget lowered or changed')
    for folder, sha in ((diverse.RUN54, diverse.RUN54_SHA), (c.ROOT/config['diagnosticRun'], config['diagnosticManifestSha256'])):
        mf = g.verified_files(folder, sha)
        if any(c.file_sha256(c.ROOT/p) != h for p, h in mf['inputSha256'].items()): raise ValueError('Frozen comparison inputs drift')
    data['train'].update(relation=pairs, full_relation=full, excluded_ner=excluded)
    return config, recipe, parent, parent_re, data, old_re, legacy, added


def cached54(data, recipe):
    folder = diverse.RUN54; g.verified_files(folder, diverse.RUN54_SHA)
    full = data['dev']['full_relation']; ids = {d['sampleId'] for d in full}; refs = [p for p in data['dev']['relation'] if p['sampleId'] in ids]
    known = c.read_jsonl(folder/'new_module_dev_predictions.jsonl'); diagnostic = old.diagnostic.scored(data['dev']['relation'], known)
    module = prior.dev_scope(diagnostic)
    frozen = c.read_jsonl(folder/'frozen_ner_dev_predictions.jsonl')
    if c.read_jsonl(folder/'re/dev_inputs.jsonl') != data['dev']['relation'] or c.read_jsonl(folder/'pipeline_dev_documents.jsonl') != full or c.read_jsonl(folder/'pipeline_dev_reference_pairs.jsonl') != refs or [(d['sampleId'], d['entities']) for d in data['dev']['ner']] != [(p['sampleId'], p['referenceEntities']) for p in frozen]: raise ValueError('Cached54 reference scope drift')
    expected_ner = c.read_jsonl(c.ROOT/recipe['frozenNERRun']/'new_ner_dev_predictions.jsonl')
    if [p['predictedEntities'] for p in frozen] != [p['predictedEntities'] for p in expected_ner]: raise ValueError('Cached54 NER drift')
    by_id = {p['sampleId']: p['predictedEntities'] for p in frozen}; candidates = [p for d in full for p in prior.candidate_rows(d, by_id[d['sampleId']])]
    scored = c.read_jsonl(folder/'new_pipeline_predictions.jsonl'); old.diagnostic.scored([p | {'label': 'NO_RELATION'} for p in candidates], scored)
    pipeline = prior.dev_scope(prior.score_pipeline(full, refs, scored), 'complete_document_exposed_dev_AI_reference_not_final_test')
    causes, false = old.error_summary(full, refs, scored); missed = [e for d in full for e in prior.diagnose(d, by_id[d['sampleId']], [p for p in refs if p['sampleId'] == d['sampleId']], [p for p in scored if p['sampleId'] == d['sampleId']])]
    pipeline.update(entityScope='fixed52_predicted_NER_entities', endpointMismatch=causes, missedReferencePrimaryCauses=dict(Counter(e['primaryCause'] for e in missed)))
    original = read(folder/'comparison.json')
    if module != original['module']['new'] or pipeline != original['pipeline']['new'] or false != c.read_jsonl(folder/'new_false_relations.jsonl') or missed != c.read_jsonl(folder/'new_missed_relations.jsonl'): raise ValueError('Cached54 metrics/errors recount drift')
    return {'kind': 'sealed54_prediction_cache_recount_not_new_inference', 'sourceManifestSha256': diverse.RUN54_SHA, 'module': module, 'pipeline': pipeline, 'falsePositives': len(false), 'falseNegatives': len(missed)}


def run(output):
    output = output.resolve()
    if output.exists(): raise FileExistsError('Preserve training run and failures')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp/course_v4_runs').resolve()): raise ValueError('Output outside runs')
    config, recipe, parent, parent_re, data, old_re, legacy, added = load_inputs(); cache = cached54(data, recipe)
    inherited = read(diverse.RUN54/'manifest.json')['inputSha256'] | read(diverse.SOURCE/'manifest.json')['inputSha256'] | read(c.ROOT/config['diagnosticRun']/'manifest.json')['inputSha256']
    paths = [c.ROOT/p for p in sorted(inherited)] + [CONTRACT, Path(__file__), Path(diverse.__file__), c.ROOT/'tests/test_diverse_role_training.py', diverse.SOURCE/'manifest.json', diverse.RUN54/'manifest.json', c.ROOT/config['diagnosticRun']/'manifest.json']
    hashes = {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in paths}; output.mkdir(parents=True); started = time.perf_counter()
    c.write_json(output/'selection_lock.json', {'createdAtUTC': datetime.now(UTC).isoformat(), 'config': config, 'evaluationRecipe': recipe, 'inputSha256': hashes})
    try:
        os.environ.setdefault('HF_HUB_OFFLINE', '1'); os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        import torch
        import transformers
        from transformers import DataCollatorWithPadding
        initial = c.ROOT/parent_re['RETraining']['initialization']; size = (initial/'model.safetensors').stat().st_size
        free = shutil.disk_usage(output).free; cpu = old.boundary.memory_available(); gpu = torch.cuda.mem_get_info()[0] if torch.cuda.is_available() else 0
        required = size+config['reserveBytes']+config['artifactMarginBytes']; cpu_required = 2*size+config['CPUReserveBytes']
        c.write_json(output/'preflight.json', {'freeDiskBytes': free, 'requiredBytes': required, 'availableCPUBytes': cpu, 'requiredCPUBytes': cpu_required, 'GPUFreeBytes': gpu, 'GPUFreeRequiredBytes': config['GPUFreeMinimumBytes'], 'historicalDeletion': False, 'testContentConsumed': False})
        if free < required or cpu < cpu_required or gpu < config['GPUFreeMinimumBytes']: raise ValueError('Insufficient checked memory/storage; no deletion or lowered reserve')
        c.write_json(output/'environment.json', {'torch': torch.__version__, 'transformers': transformers.__version__, 'gpu': torch.cuda.get_device_name(0), 'cuda': torch.version.cuda})
        archive = output/'sources'; archive.mkdir()
        for i, p in enumerate(paths):
            if p.suffix != '.safetensors' and p.name != 'test_references.jsonl': shutil.copy2(p, archive/(str(i)+'_'+p.name))
        checkpoint, training = old.fit(data, parent_re['RETraining'], config, output/'re')
        comparison = old.compare(recipe, parent, parent_re, data, old_re, legacy, checkpoint, output)
        comparison.update(candidateRE='new57', cached54=cache, trainingKnownPairs=408, stepsComparison='same6epochs_not_equal_steps')
        comparison['legacy115TrainDiagnostic'] = comparison.pop('newTrainDiagnostic')
        device = prior.setup(parent_re['RETraining']); tokenizer = re_model.prepare_tokenizer(checkpoint); collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
        model = re_model.load_relation_model(checkpoint, tokenizer, 'entity_markers').to(device).requires_grad_(False)
        predictions = prior.predict(model, tokenizer, added, 512, collator, device, 4); metrics = old.diagnostic.scored(added, predictions)
        errors = [{'reference': r, 'prediction': p} for r, p in zip(added, predictions) if r['label'] != p['label']]
        baseline = read(c.ROOT/config['diagnosticRun']/'diagnostic_result.json')
        if c.read_jsonl(c.ROOT/config['diagnosticRun']/'inputs.jsonl') != added: raise ValueError('New22 diagnostic input drift')
        comparison['new22TrainDiagnostic'] = {'scope': 'TRAIN_fit_agreement_not_generalization', 'frozen46_54Cache': baseline['models'], 'new57': metrics, 'errors': len(errors)}
        c.write_jsonl(output/'new22_train_predictions.jsonl', predictions); c.write_jsonl(output/'new22_train_errors.jsonl', errors); c.write_jsonl(output/'new22_train_inputs.jsonl', added)
        del model; torch.cuda.empty_cache(); c.write_json(output/'comparison.json', comparison)
        if training['steps'] != config['expectedSteps'] or len(list((output/'re').glob('checkpoint_*'))) != 1 or any(c.file_sha256(c.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Checkpoint/input/source drift')
        load_inputs(); c.write_json(output/'development_result.json', {'passed': True, 'RE': training, 'comparison': comparison, 'qualityPromotionPassed': False, 'modelPromoted': False, 'testEvaluated': False})
        c.write_json(output/'status.json', {'status': 'completed', 'elapsedSeconds': time.perf_counter()-started, 'trainingExecuted': True, 'NERTrained': False, 'testEvaluated': False, 'modelPromoted': False}); seal(output, paths)
        print({'completed': True, 'REsteps': training['steps'], 'pipeline': comparison['pipeline']['new']['positiveMicro'], 'blockedBy': comparison['gates']['blockedBy'], 'modelPromoted': False}, flush=True)
    except Exception as error:
        c.write_json(output/'status.json', {'status': 'failed_no_synthetic_fallback', 'errorType': type(error).__name__, 'error': str(error), 'testEvaluated': False, 'modelPromoted': False})
        if (output/'re').exists() and not (output/'re/development_result.json').exists(): c.write_json(output/'re/status.json', {'status': 'failed_no_synthetic_fallback', 'error': str(error)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('preflight', 'train')); parser.add_argument('--output', type=Path); args = parser.parse_args()
    if args.action == 'preflight':
        config, recipe, _, _, data, _, _, _ = load_inputs(); cached54(data, recipe); print({'trainKnown': len(data['train']['relation']), 'steps': config['expectedSteps'], 'testConsumed': False})
    elif args.output is None: parser.error('New output required')
    else: run(args.output)
