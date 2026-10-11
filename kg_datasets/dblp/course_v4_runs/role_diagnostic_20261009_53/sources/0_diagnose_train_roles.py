"""Frozen46 RE on new known TRAIN references; no fitting or dev/test consumption."""
import argparse
import math
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import enrich_train_roles as role
import train_revised_abstract_models as prior
from course_abstract_v1 import read, seal

c, g, re_model = role.c, role.g, role.re_model
SOURCE = c.ROOT/'kg_datasets/dblp/course_abstract_role_enriched_20261009_53'
SOURCE_SHA = '862621313f1a1a0591f237ef9e9146952367d384a78587b10f3b5bed4692cb59'
TARGET = 'new_training_reference_role_diagnostic_not_dev_or_final_test'


def load_inputs():
    config, _, _, _ = role.load_sources(); manifest = g.verified_files(SOURCE, SOURCE_SHA)
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Role source drift')
    rows = c.read_jsonl(SOURCE/'additional_relation_train.jsonl'); original = c.read_jsonl(c.ROOT/config['snapshot']/'relation_train.jsonl')
    if len(rows) != 115 or len(original) != 271 or len({re_model.pair_key(r) for r in rows}) != 115 or any(r['split'] != 'train' or r['label'] == 'UNRESOLVED' for r in rows): raise ValueError('New training diagnostic inventory changed')
    frozen = read(c.ROOT/'resources/course_abstract_boundary_training_v1.json'); run = c.ROOT/frozen['baselineRun']; g.verified_files(run, frozen['baselineManifestSha256'])
    checkpoint = run/frozen['frozenRE']
    if c.file_sha256(checkpoint/'model.safetensors') != frozen['frozenREWeightsSha256']: raise ValueError('Frozen RE weights changed')
    return rows, original, checkpoint


def scored(rows, predictions):
    if len(rows) != len(predictions) or [re_model.pair_id(r) for r in rows] != [p['pairId'] for p in predictions] or any(re_model.pair_key(r) != re_model.pair_key(p) or r['head'] != p['head'] or r['tail'] != p['tail'] or r['textSha256'] != p['textSha256'] for r, p in zip(rows, predictions)): raise ValueError('Inference pair/source order or endpoints changed')
    for p in predictions:
        values = p['probabilities']
        if set(values) != set(re_model.LABELS) or any(not math.isfinite(v) or not 0 <= v <= 1 for v in values.values()) or abs(sum(values.values())-1) > 1e-5 or p['label'] != max(values, key=values.__getitem__): raise ValueError('Invalid model scores')
    return prior.dev_scope(re_model.score_relations(rows, [p['label'] for p in predictions]), TARGET)


def run(output):
    if output.exists(): raise FileExistsError('Preserve diagnostic run')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp/course_v4_runs').resolve()): raise ValueError('Output outside runs')
    rows, original, checkpoint = load_inputs(); summary = read(SOURCE/'summary.json')
    paths = [Path(__file__), role.CONTRACT, Path(role.__file__), SOURCE/'manifest.json', c.ROOT/'resources/course_abstract_boundary_training_v1.json', checkpoint.parent.parent/'manifest.json', c.ROOT/'tests/test_train_role_diagnostic.py',
        c.ROOT/'resources/course_graph_runtime.json', c.ROOT/'resources/course_graph_quality_runtime.json', c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl', Path(prior.__file__)]
    paths += [c.ROOT/'scripts'/n for n in ('course_abstract_v1.py', 'course_abstract_relation.py', 'course_weak.py', 'course_graph.py', 'train_course_ner.py', 'train_course_relation.py', 'course_relation_model.py', 'evaluate_course_relation.py')]
    paths += [checkpoint/n for n in ('model.safetensors', 'config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'vocab.txt')]
    hashes = {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in paths}; output.mkdir(parents=True)
    c.write_json(output/'selection_lock.json', {'createdAtUTC': datetime.now(UTC).isoformat(), 'inputSha256': hashes, 'evaluationTarget': TARGET, 'scope': 'all115 added known TRAIN pairs, fixed reference entities; eight negatives kept', 'trainingAllowed': False, 'testContentAccessAllowed': False})
    try:
        os.environ.setdefault('HF_HUB_OFFLINE', '1'); os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        import torch
        import transformers
        from transformers import DataCollatorWithPadding
        device = prior.setup(read(c.ROOT/'resources/course_abstract_v1.json')['NERTraining']); tokenizer = re_model.prepare_tokenizer(checkpoint); collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
        model = re_model.load_relation_model(checkpoint, tokenizer, 'entity_markers').to(device).requires_grad_(False)
        predictions = prior.predict(model, tokenizer, rows, 512, collator, device, 4); metrics = scored(rows, predictions); mapping = re_model.type_majority(original)
        simple_labels = [mapping[r['tail']['label']] for r in rows]; simple = prior.dev_scope(re_model.score_relations(rows, simple_labels), TARGET)
        errors = [{'pairId': p['pairId'], 'sampleId': r['sampleId'], 'publicationId': r['publicationId'], 'textSha256': r['textSha256'], 'head': r['head'], 'tail': r['tail'], 'referenceLabel': r['label'], 'predictedLabel': p['label'], 'evidence': r['evidence'], 'referenceReason': r['reason'], 'modelScores': p['probabilities']} for r, p in zip(rows, predictions) if r['label'] != p['label']]
        result = {'evaluationTarget': TARGET, 'referenceEntities': True, 'knownPairs': 115, 'newReferenceSupport': summary['addedSupport'], 'knownTotalTrainPairs': summary['knownPairs'], 'eligibleTotalTrainPairs': summary['eligiblePairs'], 'knownPairCoverage': summary['knownPairCoverage'], 'unknownPairs': 1971, 'model': metrics, 'typeMajorityBaselineFromOld271': simple,
            'modelErrors': len(errors), 'negativeContrastCorrect': sum(r['label'] == 'NO_RELATION' and p['label'] == 'NO_RELATION' for r, p in zip(rows, predictions)), 'negativeContrastSupport': 8, 'positiveBenchmarkSupport': 3, 'positiveBenchmarkSourceDocuments': 1,
            'pipelineMetrics': None, 'trainingExecuted': False, 'devContentAccessed': False, 'testContentConsumed': False, 'independentHumanGold': False, 'modelPromoted': False, 'qualityPromotionPassed': False,
            'notice': 'Training-side reference-entity diagnostic, not held-out accuracy. Unknowns not negatives; correlated spans not independent trials. Scores uncalibrated, AI judgments not human gold. No threshold/model selection or production change.'}
        if len(errors) != 115-sum(metrics['confusionMatrix'][i][i] for i in range(len(re_model.LABELS))): raise ValueError('Error/confusion accounting mismatch')
        c.write_jsonl(output/'inputs.jsonl', rows); c.write_jsonl(output/'predictions.jsonl', predictions); c.write_jsonl(output/'errors.jsonl', errors)
        c.write_json(output/'diagnostic_result.json', result); c.write_json(output/'environment.json', {'torch': torch.__version__, 'transformers': transformers.__version__, 'gpu': torch.cuda.get_device_name(0), 'cuda': torch.version.cuda})
        if any(c.file_sha256(c.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Diagnostic input/code drift')
        c.write_json(output/'status.json', {'status': 'completed', 'trainingExecuted': False, 'inferenceExecuted': True, 'testEvaluated': False, 'modelPromoted': False})
        archive = output/'sources'; archive.mkdir()
        for i, p in enumerate(paths):
            if p.suffix != '.safetensors' and p.name != 'test_references.jsonl': shutil.copy2(p, archive/(str(i)+'_'+p.name))
        seal(output, paths); print({'diagnosed': True, 'errors': len(errors), 'negativeContrastCorrect': result['negativeContrastCorrect'], 'trainingExecuted': False, 'modelPromoted': False})
    except Exception as error:
        c.write_json(output/'status.json', {'status': 'failed_no_synthetic_fallback', 'errorType': type(error).__name__, 'error': str(error), 'trainingExecuted': False, 'modelPromoted': False}); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True); args = parser.parse_args(); run(args.output.resolve())
