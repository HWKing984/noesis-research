"""One data-only title refresh; fixed dev selection, no test inference or deployment."""
from __future__ import annotations

import json
import math
import shutil
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_weak as c
import evaluate_course_relation as evaluation
import export_course_evidence as evidence
import train_course_ner as ner
import train_course_relation as relation

OUTPUT = c.ROOT / 'outputs/title_expansion_once_20261010'
DATASET = c.ROOT / 'kg_datasets/dblp/course_v4_weak'
SNAPSHOT = c.ROOT / 'kg_datasets/dblp/course_v4_training_inputs_17'
BASE = c.ROOT / 'kg_datasets/models/scibert_24f92d32'
BASELINES = {
    'ner': c.ROOT / 'kg_datasets/dblp/course_v4_runs/ner_development_20261006_08',
    're': c.ROOT / 'kg_datasets/dblp/course_v4_runs/re_entity_development_20261006_15',
}


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def audit_inputs():
    ner_data, summary = ner.load_snapshot(DATASET, SNAPSHOT)
    re_data, _ = relation.load_relation_snapshot(DATASET, SNAPSHOT)
    receipts = c.read_jsonl(SNAPSHOT / 'receipts.jsonl')
    references = {r['reference']['sampleId']: r['reference'] for r in receipts}
    holds = [r for r in references.values() if r['split'] in ('dev', 'test')]
    report = {}
    for task, data, expected in [('ner', ner_data, 1219), ('re', re_data, 975)]:
        old = BASELINES[task]
        manifest = ner.verify_files(old)
        prefix = 'ner' if task == 'ner' else 'relation'
        old_snapshot = Path(next(p for p in manifest['inputSha256']
                                 if 'course_v4_training_inputs_' in p)).parent
        if (len(data['train']) != expected
                or c.file_sha256(SNAPSHOT / f'{prefix}_inputs_dev.jsonl')
                != c.file_sha256(old_snapshot / f'{prefix}_inputs_dev.jsonl')):
            raise ValueError('Unexpected expanded support or changed fixed dev bytes')
        normal = lambda text: ' '.join(unicodedata.normalize('NFKC', text).casefold().split())
        train_refs = [references[r['sampleId']] for r in data['train']]
        if any(r['split'] != 'train' or r['textKind'] != 'title' for r in train_refs):
            raise ValueError('Non-title or held-out training record')
        overlaps = {key: len({r[key] for r in train_refs} & {r[key] for r in holds})
                    for key in ('sampleId', 'groupId', 'publicationId', 'textSha256')}
        overlaps['normalizedText'] = len({normal(r['text']) for r in train_refs}
                                        & {normal(r['text']) for r in holds})
        if any(overlaps.values()):
            raise ValueError('Training/held-out overlap')
        support, source_ids = Counter(), {}
        for row in data['train']:
            for entity in row['entities'] if task == 'ner' else [row]:
                label = entity['label']
                support[label] += 1
                source_ids.setdefault(label, set()).add(row['sampleId'])
        report[task] = {'trainRows': len(data['train']), 'devRows': len(data['dev']),
                        'support': dict(support), 'sourcePapers': {k: len(v) for k, v in source_ids.items()},
                        'heldoutOverlap': overlaps, 'devBytesUnchanged': True}
    documents = [r for r in ner_data['dev']
                 if c.eligible_tasks(next(a for a in receipts if a['reference']['sampleId'] == r['sampleId']),
                                     references[r['sampleId']])['relation']]
    if len(documents) != summary['relationEligibleSplits']['dev'] or len(documents) != 158:
        raise ValueError('Incomplete fixed dev document denominator')
    return ner_data, re_data, documents, report


def gates(comparison):
    old, new = comparison['ner']['old'], comparison['ner']['new']
    baseline = comparison['pipeline']['old_ner_old_re']
    candidate = comparison['pipeline']['new_ner_new_re']
    b, n = baseline['positiveMicro'], candidate['positiveMicro']
    old_re, new_re = comparison['module']['old'], comparison['module']['new']
    for metric in [old['micro'], new['micro'], b, n, *old['perClass'].values(),
                   *new['perClass'].values(), *old_re['perClass'].values(), *new_re['perClass'].values()]:
        if (metric['reference'] <= 0 or any(metric[k] is None or not math.isfinite(metric[k])
                                          or not 0 <= metric[k] <= 1 for k in ('recall', 'f1'))):
            raise ValueError('Missing supported finite guardrail metric')
    checks = {
        'NEROverallImproved': new['micro']['f1'] > old['micro']['f1'],
        'METHODAndTASKNotWorse': all(new['perClass'][k]['f1'] >= old['perClass'][k]['f1']
                                   for k in ('METHOD', 'TASK')),
        'PipelineF1GainAtLeastTwoPoints': n['f1'] - b['f1'] >= 0.02 - 1e-12,
        'PipelineFalsePositivesNotIncreased': n['predicted'] - n['truePositive'] <= b['predicted'] - b['truePositive'],
        'PipelineUSED_FORNotWorse': candidate['perClass']['USED_FOR']['f1'] >= baseline['perClass']['USED_FOR']['f1'],
        'ModuleNegativeRecallNotWorse': new_re['perClass']['NO_RELATION']['recall'] >= old_re['perClass']['NO_RELATION']['recall'],
        'NERDATASETTruePositivesNotLost': new['perClass']['DATASET']['truePositive'] >= old['perClass']['DATASET']['truePositive'],
        'ModuleEVALUATED_ONTruePositivesNotLost': new_re['perClass']['EVALUATED_ON']['truePositive'] >= old_re['perClass']['EVALUATED_ON']['truePositive'],
        'PipelineEVALUATED_ONTruePositivesNotLost': candidate['perClass']['EVALUATED_ON']['truePositive'] >= baseline['perClass']['EVALUATED_ON']['truePositive'],
    }
    return {'checks': checks, 'failed': [k for k, v in checks.items() if not v],
            'candidateAccepted': all(checks.values()), 'productionReplacementAllowed': False,
            'optimizationStopped': True, 'statisticalSignificanceEstablished': False,
            'notice': 'Single seeded dev experiment against AI references; no new final test or stable rare-class claim.'}


def compare(ner_data, re_data, documents, output):
    import torch
    from transformers import DataCollatorWithPadding

    ner_runs = {'old': BASELINES['ner'], 'new': output / 'ner'}
    re_runs = {'old': BASELINES['re'], 'new': output / 're'}
    predicted_entities, ner_metrics, module = {}, {}, {}
    for name, run in ner_runs.items():
        ner.verify_files(run)
        predictions = c.read_jsonl(run / 'dev_predictions.jsonl')
        if ([p['sampleId'] for p in predictions] != [r['sampleId'] for r in ner_data['dev']]
                or any(p['referenceEntities'] != r['entities'] for p, r in zip(predictions, ner_data['dev']))):
            raise ValueError('Fixed NER dev prediction binding drift')
        predicted_entities[name] = {p['sampleId']: p['predictedEntities'] for p in predictions}
        ner_metrics[name] = ner.score_rows(ner_data['dev'], [p['predictedEntities'] for p in predictions])
        if ner_metrics[name] != read(run / 'development_result.json')['bestDev']['metrics']:
            raise ValueError('NER dev machine recomputation mismatch')
    pipelines, errors = {}, []
    device = torch.device('cuda')
    for re_name, run in re_runs.items():
        ner.verify_files(run)
        result = read(run / 'development_result.json')
        checkpoint = run / result['bestCheckpoint']
        tokenizer = relation.prepare_tokenizer(checkpoint)
        model = relation.load_relation_model(checkpoint, tokenizer).to(device)
        model.requires_grad_(False)
        collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
        infer = lambda rows: evaluation.predict(model, tokenizer, rows, 128, collator, device, 8)
        module_predictions = infer(re_data['dev'])
        original = c.read_jsonl(run / 'dev_predictions.jsonl')
        if [p['label'] for p in module_predictions] != [p['predictedLabel'] for p in original]:
            raise ValueError('RE serving reload differs from selected dev predictions')
        module[re_name] = relation.score_relations(re_data['dev'], [p['label'] for p in module_predictions])
        if module[re_name] != result['bestDev']['metrics']:
            raise ValueError('RE dev machine recomputation mismatch')
        c.write_jsonl(output / f'{re_name}_module_predictions.jsonl', module_predictions)
        for ner_name in ner_runs:
            key = f'{ner_name}_ner_{re_name}_re'
            rows = [pair for doc in documents for pair in evaluation.candidate_rows(
                doc, predicted_entities[ner_name][doc['sampleId']])]
            predictions = infer(rows)
            c.write_jsonl(output / f'{key}_predictions.jsonl', predictions)
            pipelines[key] = evaluation.score_pipeline(documents, re_data['dev'], predictions)
            for doc in documents:
                ref = [p for p in re_data['dev'] if p['sampleId'] == doc['sampleId']]
                pred = [p for p in predictions if p['sampleId'] == doc['sampleId']]
                score = evaluation.score_pipeline([doc], ref, pred)['positiveMicro']
                if score['truePositive'] != score['reference'] or score['truePositive'] != score['predicted']:
                    errors.append({'combination': key, 'sampleId': doc['sampleId'], 'text': doc['text'],
                                   'metrics': score, 'referencePairs': ref, 'predictedPairs': pred})
        del model
        torch.cuda.empty_cache()
    c.write_jsonl(output / 'pipeline_errors.jsonl', errors)
    return {'scope': 'fixed_title_dev_ai_reference_not_final_test', 'ner': ner_metrics,
            'module': module, 'pipeline': pipelines, 'coverage': {'queue': 200, 'NER': len(ner_data['dev']),
            'completeRelationDocuments': len(documents), 'referencePairs': len(re_data['dev']),
            'zeroReferencePairDocuments': sum(not any(r['sampleId'] == d['sampleId'] for r in re_data['dev']) for d in documents)},
            'hybridCombinationsDiagnosticOnly': True, 'testEvaluated': False, 'humanGold': False}


def run(output=OUTPUT):
    if output.exists():
        raise FileExistsError('One-shot experiment already exists; no overwrite or automatic retry')
    ner_data, re_data, documents, audit = audit_inputs()
    configurations = {k: read(v / 'manifest.json')['config'] for k, v in BASELINES.items()}
    protected = [c.ROOT / p for p in ('resources/course_graph_runtime.json',
        'resources/course_graph_quality_v3_runtime.json', 'resources/course_literature.html',
        'scripts/course_quality_app.py', 'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl')]
    runtime = read(c.ROOT / 'resources/course_graph_quality_v3_runtime.json')
    graph = c.ROOT / runtime['bundle']
    gm = ner.verify_files(graph)
    protected += [graph / 'manifest.json'] + [graph / name for name in gm['filesSha256']]
    inputs = [Path(__file__), c.CONFIG_PATH, c.SCHEMA_PATH, BASE / 'manifest.json', SNAPSHOT / 'manifest.json',
              c.ROOT / 'tests/test_title_expansion_once.py', Path(ner.__file__), Path(relation.__file__),
              Path(evaluation.__file__), Path(evidence.__file__), Path(c.__file__)]
    inputs += [SNAPSHOT / name for name in read(SNAPSHOT / 'manifest.json')['filesSha256']]
    for folder in BASELINES.values():
        manifest = ner.verify_files(folder)
        inputs += [folder / 'manifest.json'] + [folder / name for name in manifest['filesSha256']]
    hashes = {str(p.resolve()): c.file_sha256(p) for p in inputs + protected}
    required = 6 * sum((folder / read(folder / 'development_result.json')['bestCheckpoint']
                        / 'model.safetensors').stat().st_size for folder in BASELINES.values()) + 300_000_000
    free = shutil.disk_usage(output.parent if output.parent.exists() else c.ROOT).free
    if free < required:
        raise ValueError(f'Insufficient space for original checkpoint policy: need {required}, free {free}; no historical deletion')
    lock = {'lockedAtUTC': datetime.now(UTC).isoformat(), 'kind': 'one_shot_title_data_expansion',
            'configs': configurations, 'dataAudit': audit, 'inputSha256': hashes,
            'originalGraphId': runtime['graphId'], 'diskRequiredBytes': required, 'diskFreeBytes': free,
            'stoppingPolicy': {'runsPerModel': 1, 'minimumPipelineF1Gain': 0.02, 'maximumExtraPipelineFP': 0,
                'commonClassF1RegressionAllowed': False, 'rareTruePositiveLossAllowed': False,
                'negativeRecallRegressionAllowed': False, 'deploymentAllowed': False, 'newLabelsAllowed': False},
            'lossPolicy': 'original inverse-frequency RE loss; derived weights change with train support',
            'comparisonPolicy': 'fixed original dev; hybrids diagnostic only; no pipeline-driven checkpoint reselection',
            'testPolicy': 'existing provenance validators may verify historical receipts/hashes; no test features, tokenization, scoring or selection; reserved abstract test is binary hash only',
            'trainingCodeChangesSinceBaseline': 'shared NER evaluator plus validation hardening; same optimizer, loss, decoder, architecture and scoring formula',
            'courseVersionFrozen': True}
    output.mkdir(parents=True, exist_ok=False)
    c.write_json(output / 'experiment_lock.json', lock)
    state = {'status': 'running', 'stage': 'locked', 'testEvaluated': False, 'productionReplaced': False}
    c.write_json(output / 'status.json', state)
    try:
        import torch
        if not torch.cuda.is_available():
            raise ValueError('CUDA required; no fallback or unplanned training change')
        for task, fit in [('ner', lambda: ner.run(DATASET, SNAPSHOT, BASE, output / 'ner', 'fit-dev',
                                                 ner.TrainingConfig(**configurations['ner']), 'cuda')),
                          ('re', lambda: relation.run(DATASET, SNAPSHOT, BASE, output / 're',
                                                      relation.RelationConfig(**configurations['re']), 'cuda'))]:
            state['stage'] = f'train_{task}'
            c.write_json(output / 'status.json', state)
            if fit()['status'] != 'completed':
                raise ValueError(f'{task} training gate failed; no automatic retry')
            torch.cuda.empty_cache()
        state['stage'] = 'fixed_dev_comparison'
        c.write_json(output / 'status.json', state)
        result = compare(ner_data, re_data, documents, output)
        result['decision'] = gates(result)
        if any(c.file_sha256(Path(p)) != sha for p, sha in hashes.items()):
            raise ValueError('Frozen experiment or production input changed')
        result['protectedFilesUnchanged'] = True
        c.write_json(output / 'comparison.json', result)
        rows = [(name, *(f'{metric[k]:.2%}' for k in ('precision', 'recall', 'f1')))
                for name, metric in [(f'NER {k}', v['micro']) for k, v in result['ner'].items()]
                + [(f'Pipeline {k}', v['positiveMicro']) for k, v in result['pipeline'].items()]]
        body = evidence.table(['固定验证范围', 'Precision', 'Recall', 'F1'], rows)
        body += evidence.table(['候选门槛', '结果'], result['decision']['checks'].items())
        body += '<p>仅一次随机种子；NER覆盖167/200，完整关系158/200。DATASET支持3、EVALUATED_ON支持2。旧测试不重评，线上图谱/模型不替换。混合组合仅用于诊断；结果不证明统计显著性或真实泛化。</p>'
        page = output / '07_relation_development.html'
        page.write_text(evidence.page('扩充题名数据：一次固定验证对照', body, datetime.now(UTC).isoformat(),
                                     ['experiment_lock.json', 'comparison.json', 'ner/epochs.json', 're/epochs.json']), encoding='utf-8')
        state.update(status='completed', stage='stopped', finishedAtUTC=datetime.now(UTC).isoformat(),
                     candidateAccepted=result['decision']['candidateAccepted'])
        c.write_json(output / 'status.json', state)
        c.write_json(output / 'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui',
            'inputSha256': hashes, 'filesSha256': {p.relative_to(output).as_posix(): c.file_sha256(p)
            for p in sorted(output.rglob('*')) if p.is_file()}})
        return result
    except Exception as error:
        state.update(status='failed', error=repr(error), finishedAtUTC=datetime.now(UTC).isoformat())
        c.write_json(output / 'status.json', state)
        raise


if __name__ == '__main__':
    result = run()
    print(json.dumps({'decision': result['decision'], 'coverage': result['coverage']}, ensure_ascii=False), flush=True)
