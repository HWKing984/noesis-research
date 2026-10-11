"""One fixed experiment on reviewed45 data, reusing frozen42 training and evaluators."""
import argparse
import hashlib
import json
import os
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import train_revised_abstract_models as prior
from course_abstract_v1 import read, seal
from course_abstract_relation import rows_for

c, g, ner, re_model = prior.c, prior.g, prior.ner, prior.re_model
CONTRACT = c.ROOT/'resources/course_abstract_benchmark_training_v1.json'


def load_inputs():
    config = read(CONTRACT)
    if config['version'] != 'abstract_benchmark_training_v1' or config['maxTokens'] != 512 or config['textKind'] != 'abstract' or config['automaticPromotionAllowed'] is not False:
        raise ValueError('Benchmark experiment contract drift')
    for key in ('NERParent', 'REParent', 'revisionContract'):
        if c.file_sha256(c.ROOT/config[key]) != config[key+'Sha256']: raise ValueError('Bound contract drift')
    parent = read(c.ROOT/config['NERParent']); parent_re = read(c.ROOT/config['REParent']); folder = c.ROOT/config['snapshot']
    manifest = g.verified_files(folder, config['snapshotManifestSha256'])
    if read(folder/'contract.json') != read(c.ROOT/config['revisionContract']) or any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Reviewed input/source drift')
    data = {}; groups = {}; names = ('ner', 'relation', 'full_relation', 'excluded_ner')
    for split in ('train', 'dev'):
        refs = c.read_jsonl(folder/(split+'_references.jsonl')); receipts = c.read_jsonl(folder/(split+'_reviewed_receipts.jsonl')); expected = config['expected'][split]
        if len(refs) != len(receipts) or len(refs) != expected['queue'] or any(len({r[k] for r in refs}) != len(refs) for k in ('sampleId', 'groupId', 'arxivId', 'publicationId')): raise ValueError('Missing/duplicate cohort')
        if any(r['split'] != split or r['textKind'] != 'abstract' or hashlib.sha256(r['text'].encode()).hexdigest() != r['textSha256'] or c.validate_receipt(a, r) or a['review'] is None for r, a in zip(refs, receipts)): raise ValueError('Unreviewed/wrong source or split')
        rows = rows_for(refs, receipts)
        for name, values in zip(names, rows[:4]):
            if len(values) != expected[name] or values != c.read_jsonl(folder/(name+'_'+split+'.jsonl')): raise ValueError('Rows differ from reviewed receipts: '+name)
        if rows[4:] != (expected['unknown'], expected['eligiblePairs']) or Counter(p['label'] for p in rows[1]) != expected['support'] or len({re_model.pair_key(p) for p in rows[1]}) != len(rows[1]): raise ValueError('Known/unknown inventory drift')
        data[split] = dict(zip(names, rows[:4])); groups[split] = {r['groupId'] for r in refs}
    if groups['train'] & groups['dev']: raise ValueError('Cross-split paper leakage')
    baseline = c.ROOT/config['baselineRun']; baseline_manifest = g.verified_files(baseline, config['baselineManifestSha256'])
    baseline_config = read(baseline/'contract.json'); old_dev = c.ROOT/baseline_config['snapshot']; old_manifest = g.verified_files(old_dev, baseline_config['snapshotManifestSha256'])
    dev_files = [name for name in manifest['filesSha256'] if 'dev' in Path(name).stem]
    if len(dev_files) != 9 or any(manifest['filesSha256'][name] != old_manifest['filesSha256'][name] for name in dev_files): raise ValueError('Dev is not byte-identical to frozen42 scope')
    full_ids = {d['sampleId'] for d in data['dev']['full_relation']}; full_pairs = [p for p in data['dev']['relation'] if p['sampleId'] in full_ids]
    if len(full_pairs) != 107 or Counter(p['label'] for p in full_pairs) != {'USED_FOR': 84, 'NO_RELATION': 23}: raise ValueError('Complete dev reference drift')
    for task, settings in (('NER', parent['NERTraining']), ('RE', parent_re['RETraining'])):
        weight = task.lower()+'/checkpoint_epoch_06/model.safetensors'
        if baseline_manifest['filesSha256'][weight] != config['baselineWeightsSha256'][task]: raise ValueError('Frozen42 baseline changed')
        initial = c.ROOT/settings['initialization']; g.verified_files(initial.parent, config['initialRunManifests'][task])
        if c.file_sha256(initial/'model.safetensors') != settings['initialWeightsSha256']: raise ValueError('Initialization changed')
    return config, parent, parent_re, data


def gates(config, parent, data, comparison):
    result = prior.gate_results(parent, data, comparison, comparison['nerDevMetrics']['new']['metrics'])
    metrics = comparison['nerDevMetrics']
    result['checks']['DATASETRecallRegressionWithinGuard'] = metrics['old']['metrics']['perClass']['DATASET']['recall']-metrics['new']['metrics']['perClass']['DATASET']['recall'] <= config['maxAbsoluteDATASETRecallRegression']
    result['developmentGatesPassed'] = all(result['checks'].values()); result['blockedBy'] = [k for k, ok in result['checks'].items() if not ok]
    result['DATASETBaseline'] = 'frozen42_same_dev'; result['independentHumanGoldRequired'] = False
    return result


def compare(config, parent, parent_re, data, checkpoints, output):
    import torch
    from transformers import BertTokenizerFast, DataCollatorWithPadding
    device = torch.device('cuda'); tokenizer = re_model.prepare_tokenizer(c.ROOT/parent_re['RETraining']['initialization']); collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
    ner_tokenizer = BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32', local_files_only=True, do_lower_case=True)
    baseline = c.ROOT/config['baselineRun']; full = data['dev']['full_relation']; ids = {d['sampleId'] for d in full}; refs = [p for p in data['dev']['relation'] if p['sampleId'] in ids]
    entities = {}; ner_metrics = {}; module = {}; pipeline = {}
    for name, path in (('old', baseline/'ner/checkpoint_epoch_06'), ('new', checkpoints['NER'])):
        predictions, metrics = prior.infer_ner(path, data['dev']['ner'], ner_tokenizer, parent, device)
        saved = baseline/'ner/dev_predictions.jsonl' if name == 'old' else output/'ner/dev_predictions.jsonl'
        if predictions != [p['predictedEntities'] for p in c.read_jsonl(saved)]: raise ValueError('Label-free NER reload differs from selected predictions')
        entities[name] = {d['sampleId']: p for d, p in zip(data['dev']['ner'], predictions)}; ner_metrics[name] = metrics
        c.write_jsonl(output/(name+'_ner_dev_predictions.jsonl'), [{'sampleId': d['sampleId'], 'referenceEntities': d['entities'], 'predictedEntities': p} for d, p in zip(data['dev']['ner'], predictions)])
    # ponytail: four diagnostic combinations, not a search; reuse frozen inference/scoring.
    for re_name, path in (('old', baseline/'re/checkpoint_epoch_06'), ('new', checkpoints['RE'])):
        model = re_model.load_relation_model(path, tokenizer, 'entity_markers').to(device)
        known = prior.predict(model, tokenizer, data['dev']['relation'], 512, collator, device, 4)
        module[re_name] = prior.dev_scope(re_model.score_relations(data['dev']['relation'], [p['label'] for p in known])) | {'evaluationTarget': prior.TARGET}
        expected = read(baseline/'re/development_result.json') if re_name == 'old' else read(output/'re/development_result.json')
        if module[re_name] != expected['bestDev']['metrics']: raise ValueError('Label-free RE reload mismatch')
        c.write_jsonl(output/(re_name+'_module_dev_predictions.jsonl'), known)
        for ner_name in ('old', 'new'):
            name = ner_name+'_NER_'+re_name+'_RE'; candidates = [p for d in full for p in prior.candidate_rows(d, entities[ner_name][d['sampleId']])]
            predicted = prior.predict(model, tokenizer, candidates, 512, collator, device, 4)
            metrics = prior.dev_scope(prior.score_pipeline(full, refs, predicted), 'complete_document_exposed_dev_AI_reference_not_final_test')
            metrics.update(evaluationTarget='complete_document_exposed_dev_AI_reference_not_final_test', entityScope='predicted_NER_entities')
            errors = [e for d in full for e in prior.diagnose(d, entities[ner_name][d['sampleId']], [p for p in refs if p['sampleId'] == d['sampleId']], [p for p in predicted if p['sampleId'] == d['sampleId']])]
            metrics['missedReferencePrimaryCauses'] = dict(Counter(e['primaryCause'] for e in errors))
            if len(errors) != metrics['positiveMicro']['reference']-metrics['positiveMicro']['truePositive']: raise ValueError('Missed-reference accounting mismatch')
            c.write_jsonl(output/(name+'_predictions.jsonl'), predicted); c.write_jsonl(output/(name+'_missed_relations.jsonl'), errors); pipeline[name] = metrics
        del model; torch.cuda.empty_cache()
    if pipeline['old_NER_old_RE'] != read(baseline/'pipeline_development_result.json')['pipelineMetrics']['new_NER_new_RE']: raise ValueError('Re-inferred frozen42 pipeline differs')
    c.write_jsonl(output/'pipeline_dev_documents.jsonl', full); c.write_jsonl(output/'pipeline_dev_reference_pairs.jsonl', refs)
    result = {'evaluationTarget': prior.TARGET, 'baselineNER': 'frozen42_not_production', 'baselineRE': 'frozen42_not_production', 'candidate': 'new46',
        'nerDevMetrics': ner_metrics, 'moduleMetrics': module, 'pipelineMetrics': pipeline, 'moduleKnownPairs': len(data['dev']['relation']), 'modulePairCoverage': len(data['dev']['relation'])/config['expected']['dev']['eligiblePairs'],
        'pipelineDocuments': len(full), 'queueDocuments': config['expected']['dev']['queue'], 'pipelineDocumentCoverage': len(full)/config['expected']['dev']['queue'], 'pipelineReferencePairs': len(refs),
        'pipelinePositiveReference': sum(p['label'] != 'NO_RELATION' for p in refs), 'pipelineReferenceEVALUATED_ON': sum(p['label'] == 'EVALUATED_ON' for p in refs),
        'testEvaluated': False, 'independentHumanGold': False, 'qualityPromotionPassed': False, 'modelPromoted': False}
    result['gates'] = gates(config, parent, data, result); c.write_json(output/'pipeline_development_result.json', result)
    return result


def run(output):
    if output.exists(): raise FileExistsError('Preserve run; no automatic retry')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp/course_v4_runs').resolve()): raise ValueError('Output outside run directory')
    config, parent, parent_re, data = load_inputs()
    settings = {'NER': parent['NERTraining'], 'RE': parent_re['RETraining']}
    required = 6*sum((c.ROOT/s['initialization']/'model.safetensors').stat().st_size for s in settings.values())+1_000_000_000
    storage = output.parent
    while not storage.exists(): storage = storage.parent
    free = shutil.disk_usage(storage).free
    if free < required: raise ValueError('Insufficient worst-case checkpoint space; no deletion')
    paths = [CONTRACT, Path(__file__), c.ROOT/'tests/test_benchmark_abstract_training.py', c.ROOT/config['snapshot']/'manifest.json', c.ROOT/config['baselineRun']/'manifest.json']
    paths += [c.ROOT/config[k] for k in ('NERParent', 'REParent', 'revisionContract')]
    paths += [Path(prior.__file__), c.CONFIG_PATH, c.SCHEMA_PATH, c.ROOT/'resources/course_graph_runtime.json', c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl']
    paths += [c.ROOT/'scripts'/name for name in ('course_abstract_v1.py', 'course_abstract_relation.py', 'course_weak.py', 'course_graph.py', 'train_course_ner.py', 'train_course_relation.py', 'course_relation_model.py', 'evaluate_course_relation.py', 'infer_course_corpus.py', 'train_abstract_relation.py', 'review_eval_attribution.py')]
    paths += [c.ROOT/'kg_datasets/models/scibert_24f92d32'/name for name in ('vocab.txt', 'config.json')]
    for task, initial in settings.items():
        folder = c.ROOT/initial['initialization']; paths += [folder/name for name in ('model.safetensors', 'config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'vocab.txt')]+[folder.parent/'manifest.json']
        folder = c.ROOT/config['baselineRun']/task.lower()/'checkpoint_epoch_06'; paths += [folder/name for name in ('model.safetensors', 'config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'vocab.txt')]
    hashes = {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in paths}
    output.mkdir(parents=True); archive = output/'sources'; archive.mkdir()
    for i, p in enumerate(paths):
        if p.suffix != '.safetensors' and p.name != 'test_references.jsonl': shutil.copy2(p, archive/(str(i)+'_'+p.name))
    c.write_json(output/'contract.json', config); c.write_json(output/'preflight.json', {'requiredWorstCaseBytes': required, 'freeBytesBeforeFit': free, 'testContentConsumed': False})
    state = {'status': 'running', 'startedAtUTC': datetime.now(UTC).isoformat(), 'testEvaluated': False, 'testTokenized': False, 'modelPromoted': False}; c.write_json(output/'status.json', state); started = time.perf_counter()
    try:
        os.environ.setdefault('HF_HUB_OFFLINE', '1'); os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        import torch
        import transformers
        c.write_json(output/'environment.json', {'torch': torch.__version__, 'transformers': transformers.__version__, 'gpu': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None, 'cuda': torch.version.cuda})
        checkpoints = {}; results = {}
        for task, initial in settings.items(): checkpoints[task], results[task] = prior.fit(task, data, initial, parent, config, output/task.lower())
        comparison = compare(config, parent, parent_re, data, checkpoints, output)
        if any(c.file_sha256(c.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Experiment input/source drift')
        load_inputs()
        c.write_json(output/'development_result.json', {'passed': True, 'version': config['version'], 'NER': results['NER'], 'RE': results['RE'], 'gates': comparison['gates'], 'testEvaluated': False, 'independentHumanGold': False, 'qualityPromotionPassed': False, 'modelPromoted': False})
        state.update(status='completed', finishedAtUTC=datetime.now(UTC).isoformat(), elapsedSeconds=time.perf_counter()-started); c.write_json(output/'status.json', state); seal(output, paths)
        print(json.dumps({'completed': True, 'NERsteps': results['NER']['steps'], 'REsteps': results['RE']['steps'], 'gates': comparison['gates']['checks'], 'modelPromoted': False}), flush=True)
    except Exception as error:
        for folder in (output, output/'ner', output/'re'):
            if folder.exists():
                status = folder/'status.json'; current = read(status) if status.exists() else {}
                if folder == output or current.get('status') != 'completed': c.write_json(status, current | {'status': 'failed_no_synthetic_fallback', 'errorType': type(error).__name__, 'error': str(error)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('preflight', 'train')); parser.add_argument('--output', type=Path); args = parser.parse_args()
    if args.action == 'preflight':
        _, _, _, data = load_inputs(); print({'NERtrain': len(data['train']['ner']), 'REtrain': len(data['train']['relation']), 'testConsumed': False})
    elif args.output is None: parser.error('New output required')
    else: run(args.output.resolve())
