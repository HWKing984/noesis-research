"""Frozen46/54 RE on new TRAIN judgments; this is not held-out or pipeline evaluation."""
import argparse
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path

import diagnose_train_roles as diagnostic
import revise_diverse_train_roles as diverse
from course_abstract_v1 import read, seal

c, g, re_model, prior = diagnostic.c, diagnostic.g, diagnostic.re_model, diagnostic.prior
SOURCE = c.ROOT/'kg_datasets/dblp/course_diverse_train_roles_20261010_56_final'
SOURCE_SHA = 'b45ac3019819f67a56e33abc68b8d5a1115fe4b251b0f3d8d47d6dd5e77aa4e8'
RUN54 = c.ROOT/'kg_datasets/dblp/course_v4_runs/abstract_role_development_20261009_54'
RUN54_SHA = '25d872cdae05973ce3ff39de8ad072eb8ff78bda0ff2b2540a092b4c500ab919'
WEIGHTS54_SHA = '44470a364db2b4f5660a3808c821a70bcdf7fb48d055a43f766798c8b044c1cc'


def load_inputs():
    diverse.load_sources(); manifest = g.verified_files(SOURCE, SOURCE_SHA)
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('New evidence inputs drifted')
    refs = c.read_jsonl(SOURCE/'references.jsonl'); receipts = c.read_jsonl(SOURCE/'reviewed_receipts.jsonl')
    docs, pairs, full, excluded, unknown, total = diverse.role.rows_for(refs, receipts)
    if pairs != c.read_jsonl(SOURCE/'relation_train.jsonl') or (len(docs), len(pairs), len(full), len(excluded), unknown, total) != (65, 408, 12, 5, 1949, 2357): raise ValueError('Evidence snapshot inventory changed')
    rows = c.read_jsonl(SOURCE/'additional_relation_train.jsonl'); original = c.read_jsonl(diagnostic.SOURCE/'relation_train.jsonl')
    old_keys = {re_model.pair_key(r) for r in original}
    if [p for p in pairs if re_model.pair_key(p) in old_keys] != original or [p for p in pairs if re_model.pair_key(p) not in old_keys] != rows or diverse.Counter(r['label'] for r in rows) != {'USED_FOR': 19, 'NO_RELATION': 3}: raise ValueError('Diagnostic is not exactly the22 new TRAIN pairs')
    _, _, checkpoint46 = diagnostic.load_inputs(); g.verified_files(RUN54, RUN54_SHA)
    checkpoint54 = RUN54/'re/checkpoint_epoch_06'
    if c.file_sha256(checkpoint54/'model.safetensors') != WEIGHTS54_SHA: raise ValueError('Frozen54 checkpoint drift')
    return rows, original, {'frozen46': checkpoint46, 'frozen54': checkpoint54}


def run(output):
    output = output.resolve()
    if output.exists(): raise FileExistsError('Preserve diagnostic run')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp/course_v4_runs').resolve()): raise ValueError('Output outside runs')
    rows, original, checkpoints = load_inputs()
    paths = [Path(__file__), diverse.CONTRACT, Path(diverse.__file__), Path(diagnostic.__file__), Path(prior.__file__), SOURCE/'manifest.json', RUN54/'manifest.json', c.ROOT/'resources/course_abstract_role_training_v1.json', c.ROOT/'tests/test_diverse_train_role_diagnostic.py']
    paths += [c.ROOT/'scripts'/n for n in ('course_abstract_v1.py', 'course_abstract_relation.py', 'course_weak.py', 'course_graph.py', 'train_course_relation.py', 'course_relation_model.py', 'evaluate_course_relation.py')]
    paths += [path/n for path in checkpoints.values() for n in ('model.safetensors', 'config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'vocab.txt')]
    hashes = {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in paths}; output.mkdir(parents=True)
    c.write_json(output/'selection_lock.json', {'createdAtUTC': datetime.now(UTC).isoformat(), 'inputSha256': hashes, 'scope': 'all22 new TRAIN reference-entity pairs, both frozen models; no selection, thresholds, training or test', 'trainingAllowed': False, 'testContentAccessAllowed': False})
    try:
        os.environ.setdefault('HF_HUB_OFFLINE', '1'); os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        import torch
        import transformers
        from transformers import DataCollatorWithPadding
        settings = read(c.ROOT/'resources/course_abstract_role_training_v1.json'); parent = read(c.ROOT/'resources/course_abstract_relation_v1.json')
        size = (c.ROOT/parent['RETraining']['initialization']/'model.safetensors').stat().st_size; free = shutil.disk_usage(output).free
        c.write_json(output/'training_deferred.json', {'trainingExecuted': False, 'freeDiskBytes': free, 'requiredDiskBytesByExisting54Policy': size+settings['reserveBytes']+settings['artifactMarginBytes'], 'belowExisting54DiskBudget': free < size+settings['reserveBytes']+settings['artifactMarginBytes'], 'reason': 'No new training contract; existing one-checkpoint disk budget is also unmet. Source evidence/inference only; no lowered reserve or historical deletion.', 'historicalDeletion': False})
        if free < settings['reserveBytes']+10_000_000: raise ValueError('Insufficient diagnostic disk margin; keep1GB reserve')
        device = prior.setup(parent['RETraining']); results = {}
        for name, checkpoint in checkpoints.items():
            tokenizer = re_model.prepare_tokenizer(checkpoint); collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
            model = re_model.load_relation_model(checkpoint, tokenizer, 'entity_markers').to(device).requires_grad_(False)
            predictions = prior.predict(model, tokenizer, rows, 512, collator, device, 4); metrics = diagnostic.scored(rows, predictions)
            errors = [r | {'pairId': p['pairId'], 'referenceLabel': r['label'], 'predictedLabel': p['label'], 'modelScores': p['probabilities']} for r, p in zip(rows, predictions) if r['label'] != p['label']]
            if len(errors) != len(rows)-sum(metrics['confusionMatrix'][i][i] for i in range(len(re_model.LABELS))): raise ValueError('Error/confusion count mismatch')
            results[name] = {'metrics': metrics, 'errors': len(errors), 'negativeContrastCorrect': sum(r['label'] == 'NO_RELATION' and p['label'] == 'NO_RELATION' for r, p in zip(rows, predictions)), 'positiveTaskCorrect': sum(r['label'] == 'USED_FOR' and p['label'] == 'USED_FOR' for r, p in zip(rows, predictions))}
            c.write_jsonl(output/(name+'_predictions.jsonl'), predictions); c.write_jsonl(output/(name+'_errors.jsonl'), errors)
            del model; torch.cuda.empty_cache()
        mapping = re_model.type_majority(original); baseline = prior.dev_scope(re_model.score_relations(rows, [mapping[r['tail']['label']] for r in rows]), diagnostic.TARGET)
        result = {'evaluationTarget': diagnostic.TARGET, 'models': results, 'typeMajorityFromOld386': baseline, 'referencePairs': len(rows), 'referenceSourceDocuments': len({r['sampleId'] for r in rows}), 'negativeSupport': 3, 'negativeSourceDocuments': 1, 'EVALUATED_ONsupport': 0, 'referenceEntities': True, 'trainingExecuted': False, 'devContentAccessed': False, 'testContentConsumed': False, 'independentHumanGold': False, 'qualityPromotionPassed': False, 'modelPromoted': False, 'notice': 'New labels belong to TRAIN papers already seen by earlier NER/other stages. Not independent model accuracy, generalization, end-to-end evaluation, or calibrated confidence. Three negatives are correlated source occurrences; no EVALUATED_ON conclusions.'}
        c.write_jsonl(output/'inputs.jsonl', rows); c.write_json(output/'diagnostic_result.json', result)
        c.write_json(output/'environment.json', {'torch': torch.__version__, 'transformers': transformers.__version__, 'gpu': torch.cuda.get_device_name(0), 'cuda': torch.version.cuda})
        if any(c.file_sha256(c.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Inference input/code drift')
        c.write_json(output/'status.json', {'status': 'completed', 'inferenceExecuted': True, 'trainingExecuted': False, 'modelPromoted': False}); seal(output, paths)
        print({name: {k: v for k, v in value.items() if k != 'metrics'} for name, value in results.items()}, flush=True)
    except Exception as error:
        c.write_json(output/'status.json', {'status': 'failed_no_synthetic_fallback', 'errorType': type(error).__name__, 'error': str(error), 'trainingExecuted': False, 'modelPromoted': False}); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True); args = parser.parse_args(); run(args.output)
