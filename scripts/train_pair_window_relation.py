"""One label-independent pair-context experiment; score original whole documents."""
import argparse
import os
import re
import shutil
import time
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import train_diverse_abstract_relation as source

c, g, prior, re_model, read, seal = source.c, source.g, source.prior, source.re_model, source.read, source.seal
CONTRACT = c.ROOT/'resources/course_pair_window_training_v1.json'
BOUNDARY = r'(?<=[.!?])\s+(?=[A-Z0-9])'
BASELINE = c.ROOT/'kg_datasets/dblp/course_v4_runs/diverse_role_development_20261010_57'
BASELINE_SHA = '716c5cd973681636bfef1bf08be94165f8bc8d6d8f339b618758f2015688ed1a'


def window_pair(row):
    re_model.mark_pair(row)
    if 'contextWindow' in row: raise ValueError('Do not crop an already cropped pair')
    text = row['text']; bounds = [0]+[m.end() for m in re.finditer(BOUNDARY, text)]+[len(text)]
    left = bisect_right(bounds, min(row[r]['start'] for r in ('head', 'tail')))-1
    right = bisect_left(bounds, max(row[r]['end'] for r in ('head', 'tail')))
    start, end = bounds[max(0, left-1)], bounds[min(len(bounds)-1, right+1)]
    local = {k: v for k, v in row.items() if k not in ('evidence', 'reason')}
    local.update(text=text[start:end], textSha256=c.canonical_sha256(text[start:end]),
                 contextWindow={'version': 'pair_window_v1', 'sourceStart': start, 'sourceEnd': end,
                                'sourceTextSha256': row['textSha256'], 'sourcePairId': re_model.pair_id(row)})
    for role in ('head', 'tail'):
        local[role] = row[role] | {'start': row[role]['start']-start, 'end': row[role]['end']-start}
    re_model.mark_pair(local)
    return local


def restore_predictions(rows, predictions):
    if len(rows) != len(predictions): raise ValueError('Cropped prediction candidate loss')
    result = []
    for row, prediction in zip(rows, predictions):
        local = window_pair(row)
        if (any(prediction.get(k) != local[k] for k in ('sampleId', 'text', 'textSha256', 'head', 'tail', 'contextWindow'))
                or prediction.get('pairId') != re_model.pair_id(local)
                or prediction.get('label') not in re_model.allowed_labels(row['tail']['label'])):
            raise ValueError('Cropped prediction/source identity drift or illegal label')
        result.append({k: v for k, v in row.items() if k not in ('label', 'evidence', 'reason')} | {
            'label': prediction['label'], 'probabilities': prediction['probabilities'],
            'pairId': re_model.pair_id(row), 'contextWindow': local['contextWindow']})
    return result


def load_inputs():
    config = read(CONTRACT)
    if (config['version'] != 'abstract_pair_window_training_v1' or config['neighborSentences'] != 1
            or config['boundaryPattern'] != BOUNDARY or config['expectedSteps'] != 612
            or c.ROOT/config['parent'] != source.CONTRACT or c.ROOT/config['baselineRun'] != BASELINE
            or config['baselineManifestSha256'] != BASELINE_SHA
            or any(config[k] is not False for k in ('NERTrainingAllowed', 'testContentAccessAllowed', 'automaticPromotionAllowed'))):
        raise ValueError('Fixed pair-window protocol drift')
    manifest = g.verified_files(BASELINE, BASELINE_SHA)
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()):
        raise ValueError('Frozen57 source inputs drift')
    inherited, recipe, parent, parent_re, data, _, _, _ = source.load_inputs()
    return config, inherited, recipe, parent, parent_re, data, manifest


def cached_baseline(data):
    frozen = c.read_jsonl(BASELINE/'frozen_ner_dev_predictions.jsonl')
    if [(d['sampleId'], d['entities']) for d in data['dev']['ner']] != [(d['sampleId'], d['referenceEntities']) for d in frozen]:
        raise ValueError('Frozen57 reference NER scope drift')
    full = data['dev']['full_relation']; ids = {d['sampleId'] for d in full}
    refs = [p for p in data['dev']['relation'] if p['sampleId'] in ids]
    if (c.read_jsonl(BASELINE/'re/dev_inputs.jsonl') != data['dev']['relation']
            or c.read_jsonl(BASELINE/'pipeline_dev_documents.jsonl') != full
            or c.read_jsonl(BASELINE/'pipeline_dev_reference_pairs.jsonl') != refs):
        raise ValueError('Frozen57 evaluation denominator drift')
    by_id = {d['sampleId']: d['predictedEntities'] for d in frozen}
    candidates = [p for d in full for p in prior.candidate_rows(d, by_id[d['sampleId']])]
    known = c.read_jsonl(BASELINE/'new_module_dev_predictions.jsonl')
    source.old.diagnostic.scored(data['dev']['relation'], known)
    module = prior.dev_scope(re_model.score_relations(data['dev']['relation'], [p['label'] for p in known]))
    predicted = c.read_jsonl(BASELINE/'new_pipeline_predictions.jsonl')
    source.old.diagnostic.scored([p | {'label': 'NO_RELATION'} for p in candidates], predicted)
    pipeline, false, missed = pipeline_scores(full, refs, predicted, by_id)
    original = read(BASELINE/'comparison.json')
    if (module != original['module']['new'] or pipeline != original['pipeline']['new']
            or false != c.read_jsonl(BASELINE/'new_false_relations.jsonl')
            or missed != c.read_jsonl(BASELINE/'new_missed_relations.jsonl')):
        raise ValueError('Frozen57 metrics or errors recount drift')
    return {'kind': 'sealed57_predictions_recount_not_new_inference', 'module': module,
            'pipeline': pipeline, 'NER': original['NER']}, candidates, refs, by_id


def pipeline_scores(full, refs, predicted, by_id):
    metrics = prior.dev_scope(prior.score_pipeline(full, refs, predicted), 'complete_document_exposed_dev_AI_reference_not_final_test')
    causes, false = source.old.error_summary(full, refs, predicted)
    missed = [e for d in full for e in prior.diagnose(d, by_id[d['sampleId']],
              [p for p in refs if p['sampleId'] == d['sampleId']], [p for p in predicted if p['sampleId'] == d['sampleId']])]
    if (len(false) != metrics['positiveMicro']['predicted']-metrics['positiveMicro']['truePositive']
            or len(missed) != metrics['positiveMicro']['reference']-metrics['positiveMicro']['truePositive']):
        raise ValueError('Whole-document FP/FN accounting drift')
    metrics.update(entityScope='fixed52_predicted_NER_entities', endpointMismatch=causes,
                   missedReferencePrimaryCauses=dict(Counter(e['primaryCause'] for e in missed)))
    return metrics, false, missed


def run(output):
    output = output.resolve()
    if output.exists(): raise FileExistsError('Preserve training run and failures')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp/course_v4_runs').resolve()): raise ValueError('Output outside runs')
    config, inherited, recipe, parent, parent_re, data, manifest = load_inputs()
    baseline, candidates, refs, by_id = cached_baseline(data)
    paths = {c.ROOT/p for p in manifest['inputSha256']}
    paths.update(BASELINE/p for p in manifest['filesSha256'])
    paths.update((CONTRACT, Path(__file__), Path(source.__file__), BASELINE/'manifest.json',
                  c.ROOT/'tests/test_pair_window_training.py', c.ROOT/'resources/course_graph_quality_v3_runtime.json'))
    paths = sorted(paths); hashes = {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in paths}
    transformed = {s: data[s] | {'relation': [window_pair(r) for r in data[s]['relation']]} for s in ('train', 'dev')}
    if any(len(transformed[s]['relation']) != len(data[s]['relation']) for s in transformed): raise ValueError('Pair inventory drift')
    inventory = {s: {'pairs': len(data[s]['relation']),
                    'shorterInputs': sum(len(w['text']) < len(r['text']) for r, w in zip(data[s]['relation'], transformed[s]['relation'])),
                    'originalCharacters': sum(len(r['text']) for r in data[s]['relation']),
                    'windowCharacters': sum(len(r['text']) for r in transformed[s]['relation']),
                    'quotedEvidenceOutsideWindow': sum(not (w['contextWindow']['sourceStart'] <= r['evidence']['start'] and
                        r['evidence']['end'] <= w['contextWindow']['sourceEnd']) for r, w in zip(data[s]['relation'], transformed[s]['relation']))}
                 for s in transformed}
    output.mkdir(parents=True); started = time.perf_counter()
    c.write_json(output/'selection_lock.json', {'createdAtUTC': datetime.now(UTC).isoformat(), 'config': config,
                 'trainingRecipe': inherited, 'inputSha256': hashes, 'inventory': inventory, 'testContentConsumed': False})
    try:
        os.environ.setdefault('HF_HUB_OFFLINE', '1'); os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        import torch
        import transformers
        from transformers import DataCollatorWithPadding
        initial = c.ROOT/parent_re['RETraining']['initialization']; size = (initial/'model.safetensors').stat().st_size
        free = shutil.disk_usage(output).free; cpu = source.old.boundary.memory_available()
        gpu = torch.cuda.mem_get_info()[0] if torch.cuda.is_available() else 0
        required = size+inherited['reserveBytes']+inherited['artifactMarginBytes']; cpu_required = 2*size+inherited['CPUReserveBytes']
        c.write_json(output/'preflight.json', {'freeDiskBytes': free, 'requiredBytes': required,
                     'availableCPUBytes': cpu, 'requiredCPUBytes': cpu_required, 'GPUFreeBytes': gpu,
                     'GPUFreeRequiredBytes': inherited['GPUFreeMinimumBytes'], 'historicalDeletion': False, 'testContentConsumed': False})
        if free < required or cpu < cpu_required or gpu < inherited['GPUFreeMinimumBytes']:
            raise ValueError('Insufficient checked resources; no deletion or lowered reserve')
        archive = output/'sources'; archive.mkdir()
        for i, p in enumerate(paths):
            if p.suffix == '.py' or p == CONTRACT: shutil.copy2(p, archive/(str(i)+'_'+p.name))
        c.write_json(output/'environment.json', {'torch': torch.__version__, 'transformers': transformers.__version__,
                     'gpu': torch.cuda.get_device_name(0), 'cuda': torch.version.cuda})
        checkpoint, training = source.old.fit(transformed, parent_re['RETraining'], inherited, output/'re')
        device = prior.setup(parent_re['RETraining']); tokenizer = re_model.prepare_tokenizer(checkpoint)
        collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
        model = re_model.load_relation_model(checkpoint, tokenizer, 'entity_markers').to(device).requires_grad_(False)
        results = {}
        for name, rows in (('module', data['dev']['relation']), ('pipeline', candidates)):
            cropped = [window_pair(r) for r in rows]
            local_predictions = prior.predict(model, tokenizer, cropped, 512, collator, device, 4)
            results[name] = restore_predictions(rows, local_predictions)
            c.write_jsonl(output/(name+'_window_inputs.jsonl'), [{k: v for k, v in r.items() if k != 'label'} for r in cropped])
            c.write_jsonl(output/('new_'+name+'_predictions.jsonl'), results[name])
        del model; torch.cuda.empty_cache()
        module = prior.dev_scope(re_model.score_relations(data['dev']['relation'], [p['label'] for p in results['module']]))
        if module != training['bestDev']['metrics']: raise ValueError('Label-free cropped module reload mismatch')
        full = data['dev']['full_relation']; pipeline, false, missed = pipeline_scores(full, refs, results['pipeline'], by_id)
        gates = source.old.gates(parent, data, {'old': baseline['pipeline'], 'new': pipeline},
                                 {'old': baseline['module'], 'new': module}, baseline['NER']['metrics'])
        comparison = {'evaluationTarget': prior.TARGET, 'baseline': baseline,
                      'module': {'old': baseline['module'], 'new': module}, 'pipeline': {'old': baseline['pipeline'], 'new': pipeline},
                      'gates': gates, 'fixedNER': 'frozen52_not_production', 'moduleKnownPairs': 333,
                      'modulePairCoverage': 333/432, 'completeDocuments': 7, 'lockedQueue': 19,
                      'documentCoverage': 7/19, 'positiveReference': 84, 'completeReferenceEVALUATED_ON': 0,
                      'allPipelineCandidates': len(candidates), 'inventory': inventory,
                      'testEvaluated': False, 'independentHumanGold': False, 'qualityPromotionPassed': False, 'modelPromoted': False,
                      'notice': 'Fixed cropped input feature with unchanged whole-document references. No gold-evidence sentence selection, candidate filtering or unknown-negative filling. Exposed AI dev, not final test or production accuracy.'}
        c.write_json(output/'comparison.json', comparison)
        c.write_jsonl(output/'new_false_relations.jsonl', false); c.write_jsonl(output/'new_missed_relations.jsonl', missed)
        c.write_jsonl(output/'pipeline_dev_documents.jsonl', full); c.write_jsonl(output/'pipeline_dev_reference_pairs.jsonl', refs)
        if (training['steps'] != config['expectedSteps'] or len(list((output/'re').glob('checkpoint_*'))) != 1
                or any(c.file_sha256(c.ROOT/p) != sha for p, sha in hashes.items())):
            raise ValueError('Step/checkpoint/source drift')
        load_inputs()
        c.write_json(output/'development_result.json', {'passed': True, 'RE': training, 'comparison': comparison,
                     'qualityPromotionPassed': False, 'modelPromoted': False, 'testEvaluated': False})
        c.write_json(output/'status.json', {'status': 'completed', 'elapsedSeconds': time.perf_counter()-started,
                     'trainingExecuted': True, 'NERTrained': False, 'testEvaluated': False, 'modelPromoted': False})
        seal(output, paths)
        print({'completed': True, 'REsteps': training['steps'], 'pipeline': pipeline['positiveMicro'],
               'blockedBy': gates['blockedBy'], 'modelPromoted': False}, flush=True)
    except Exception as error:
        c.write_json(output/'status.json', {'status': 'failed_no_synthetic_fallback', 'errorType': type(error).__name__,
                     'error': str(error), 'testEvaluated': False, 'modelPromoted': False})
        if (output/'re').exists() and not (output/'re/development_result.json').exists():
            c.write_json(output/'re/status.json', {'status': 'failed_no_synthetic_fallback', 'error': str(error)})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'train')); parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.action == 'preflight':
        config, inherited, recipe, parent, parent_re, data, manifest = load_inputs(); baseline, candidates, _, _ = cached_baseline(data)
        print({'trainKnown': len(data['train']['relation']), 'devKnown': len(data['dev']['relation']),
               'pipelineCandidates': len(candidates), 'steps': config['expectedSteps'], 'testConsumed': False})
    elif args.output is None: parser.error('New output required')
    else: run(args.output)
