"""Fixed cached pipeline replay and supplemental dev inference, never training/test."""
import argparse
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_graph as g
import train_benchmark_abstract_models as models
from course_abstract_v1 import read, seal
from course_relation_evidence import apply_gate

CONTRACT = g.ROOT/'resources/course_relation_evidence_v1.json'


def positive_agreement(reference, emitted):
    key = lambda p: models.re_model.pair_key(p)+(p['label'],)
    return g.c.entity_agreement([key(p) for p in emitted], [key(p) for p in reference if p['label'] != 'NO_RELATION'])


def run(output):
    if output.exists(): raise FileExistsError('Preserve fixed experiment')
    config = read(CONTRACT)
    if config['version'] != 'local_relation_evidence_gate_v1' or any(config[k] is not False for k in ('trainingAllowed', 'labelMutationAllowed', 'testContentAccessAllowed', 'automaticPromotionAllowed')): raise ValueError('Evidence contract drift')
    source = g.ROOT/config['baseline']; g.verified_files(source, config['baselineManifestSha256'])
    supplement = g.ROOT/config['supplement']; g.verified_files(supplement, config['supplementManifestSha256'])
    training_config, parent, parent_re, data = models.load_inputs()
    run46 = g.ROOT/'kg_datasets/dblp/course_v4_runs/abstract_benchmark_development_20261008_46'; run_manifest = g.verified_files(run46)
    result46 = read(run46/'development_result.json')
    ner_path = run46/'ner'/result46['NER']['bestCheckpoint']; re_path = run46/'re'/result46['RE']['bestCheckpoint']
    refs = g.c.read_jsonl(run46/'pipeline_dev_reference_pairs.jsonl'); docs = g.c.read_jsonl(run46/'pipeline_dev_documents.jsonl')
    rows = g.c.read_jsonl(source/'pipeline_predictions.jsonl'); supp_ner = g.c.read_jsonl(supplement/'ner_dev.jsonl'); supp_re = g.c.read_jsonl(supplement/'relation_dev.jsonl')
    if len(supp_ner) != 7 or len(supp_re) != 88 or len(docs) != 7: raise ValueError('Fixed dev scope drift')
    if {r['groupId'] for r in supp_ner} & {r['groupId'] for r in data['train']['ner']+data['dev']['ner']}: raise ValueError('Supplement paper leakage')
    paths = [CONTRACT, Path(__file__), g.ROOT/'scripts/course_relation_evidence.py', g.ROOT/'tests/test_relation_evidence.py',
        source/'manifest.json', supplement/'manifest.json', run46/'manifest.json', g.ROOT/'resources/course_graph_runtime.json',
        g.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl',
        ner_path/'model.safetensors', re_path/'model.safetensors', g.ROOT/'resources/course_abstract_benchmark_training_v1.json']
    hashes = {p.relative_to(g.ROOT).as_posix(): g.c.file_sha256(p) for p in paths}
    output.mkdir(parents=True); g.c.write_json(output/'selection_lock.json', {'lockedAtUTC': datetime.now(UTC).isoformat(), 'contract': config, 'inputSha256': hashes})
    state = {'status': 'running', 'trainingExecuted': False, 'testEvaluated': False, 'modelPromoted': False}; g.c.write_json(output/'status.json', state)
    try:
        emitted, ledger = apply_gate(rows)
        original = models.prior.score_pipeline(docs, refs, rows); guarded = models.prior.score_pipeline(docs, refs, emitted)
        train_positive = [r for r in data['train']['relation'] if r['label'] != 'NO_RELATION']
        train_emitted, train_ledger = apply_gate(train_positive)
        g.c.write_jsonl(output/'historical_dev_evidence_ledger.jsonl', ledger); g.c.write_jsonl(output/'historical_dev_emitted.jsonl', emitted)
        g.c.write_jsonl(output/'train_positive_evidence_ledger.jsonl', train_ledger)
        os.environ.setdefault('HF_HUB_OFFLINE', '1'); os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        from transformers import BertTokenizerFast, DataCollatorWithPadding
        import torch
        device = models.prior.setup(parent['NERTraining'])
        tokenizer = BertTokenizerFast.from_pretrained(g.ROOT/'kg_datasets/models/scibert_24f92d32', local_files_only=True, do_lower_case=True)
        predictions, ner_metric = models.prior.infer_ner(ner_path, supp_ner, tokenizer, parent, device)
        g.c.write_jsonl(output/'supplement_ner_predictions.jsonl', [{'sampleId': r['sampleId'], 'textSha256': r['textSha256'], 'referenceEntities': r['entities'], 'predictedEntities': p} for r, p in zip(supp_ner, predictions)])
        tokenizer = models.re_model.prepare_tokenizer(re_path); collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
        model = models.re_model.load_relation_model(re_path, tokenizer, 'entity_markers').to(device)
        known = models.prior.predict(model, tokenizer, supp_re, 512, collator, device, 4)
        supp_emit, supp_ledger = apply_gate(known)
        g.c.write_jsonl(output/'supplement_known_pair_predictions.jsonl', known); g.c.write_jsonl(output/'supplement_evidence_ledger.jsonl', supp_ledger)
        report = {'version': config['version'], 'trainingExecuted': False, 'testEvaluated': False, 'modelPromoted': False, 'qualityPromotionPassed': False,
            'historicalDev': {'documents': 7, 'queueDocuments': 19, 'documentCoverage': 7/19,
                'baselinePositiveMicro': original['positiveMicro'], 'guardedPositiveMicro': guarded['positiveMicro'],
                'baselinePerClass': original['perClass'], 'guardedPerClass': guarded['perClass'],
                'decisions': dict(Counter(p['evidenceGate']['decision'] for p in ledger)),
                'emittedPositiveCoverage': len(emitted)/original['positiveMicro']['predicted'], 'evidenceLedgerComplete': len(ledger) == len(rows)},
            'trainReferenceEvidenceCoverage': {'positivePairs': len(train_positive), 'emitted': len(train_emitted), 'coverage': len(train_emitted)/len(train_positive)},
            'supplementDev': {'NER': ner_metric, 'queueDocuments': 8, 'NERDocuments': 7, 'NERDocumentCoverage': 7/8,
                'resolvedPairs': 88, 'eligiblePairs': 478, 'knownPairCoverage': 88/478, 'unknownPairs': 390, 'completePipelineDocuments': 0,
                'conditionalReferenceEntityModule': models.re_model.score_relations(supp_re, [p['label'] for p in known]),
                'conditionalGuardedPositiveMicro': positive_agreement(supp_re, supp_emit),
                'guardedPerClass': {label: positive_agreement([r for r in supp_re if r['label'] in (label, 'NO_RELATION')], [r for r in supp_emit if r['label'] == label]) for label in ('USED_FOR', 'EVALUATED_ON')},
                'decisions': dict(Counter(p['evidenceGate']['decision'] for p in supp_ledger)), 'completePipelineMetrics': None},
            'notice': 'Fixed lexical abstention diagnostic; AI-reference agreement, not semantic correctness. Unknown pairs not negative. Recall retains every positive reference. Historical dev is exposed and supplement has partial relations; no final test or promotion.'}
        old = report['historicalDev']['baselinePositiveMicro']; new = report['historicalDev']['guardedPositiveMicro']
        report['diagnosticChecks'] = {'precisionNonRegression': new['precision'] >= old['precision'], 'F1NonRegression': new['f1'] >= old['f1'],
            'recallRegressionWithinOriginalGuard': old['recall']-new['recall'] <= parent['promotionGates']['maxAbsoluteRecallRegression']}
        report['blockedBy'] = [k for k, passed in report['diagnosticChecks'].items() if not passed]+['insufficient_complete_EVALUATED_ON_and_document_coverage', 'final_test_not_executed']
        if any(g.c.file_sha256(g.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Fixed experiment input drift')
        g.c.write_json(output/'development_result.json', report); state.update(status='completed', finishedAtUTC=datetime.now(UTC).isoformat()); g.c.write_json(output/'status.json', state)
        seal(output, paths); print(json.dumps({'historical': report['historicalDev'], 'supplementNER': ner_metric, 'blockedBy': report['blockedBy']}), flush=True)
    except Exception as error:
        g.c.write_json(output/'status.json', state | {'status': 'failed_no_synthetic_fallback', 'error': str(error)}); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); run(args.output.resolve())
