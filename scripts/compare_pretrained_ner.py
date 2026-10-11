"""Fixed zero-shot NER comparison on exposed dev, with the same frozen relation model."""
import argparse
import hashlib
import math
import os
import shutil
import sys
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import course_graph as g
import train_course_ner as ner
import train_course_relation as re_model
from course_abstract_v1 import read, seal
from evaluate_course_relation import candidate_rows, predict, score_pipeline

CONTRACT = g.ROOT / 'resources/course_pretrained_ner_comparison_v1.json'
LABELS = {'machine learning method': 'METHOD', 'research task': 'TASK', 'dataset': 'DATASET'}


def checked_dev(rows):
    if not rows or len({r['sampleId'] for r in rows}) != len(rows): raise ValueError('Missing or duplicate dev documents')
    for row in rows:
        if (row['split'] != 'dev' or row['textKind'] != 'abstract'
                or hashlib.sha256(row['text'].encode()).hexdigest() != row['textSha256']):
            raise ValueError('Only integrity-checked dev abstracts allowed')
    ner.score_rows(rows, [r['entities'] for r in rows])
    return rows


def checked_entities(row, predictions):
    entities = []
    for p in predictions:
        if p['label'] not in LABELS or not math.isfinite(p['score']) or not 0 <= p['score'] <= 1:
            raise ValueError('Invalid pretrained label or score')
        entities.append({k: p[k] for k in ('start', 'end', 'text')} | {'label': LABELS[p['label']]})
    entities.sort(key=lambda e: (e['start'], e['end'], e['label']))
    ner.score_rows([row], [entities])
    return entities


def load_inputs():
    config = read(CONTRACT)
    if (config['version'] != 'pretrained_ner_comparison_v1' or config['labelMap'] != LABELS
            or config['threshold'] != .5 or config['flatNER'] is not True or config['automaticPromotionAllowed'] is not False):
        raise ValueError('Frozen experiment drift')
    for name in ('snapshot', 'baselineNER', 'frozenRE'):
        g.verified_files(g.ROOT / config[name], config[name + 'ManifestSha256'])
    folder = g.ROOT / config['snapshot']
    rows = checked_dev(g.c.read_jsonl(folder / 'ner_dev.jsonl'))
    full = checked_dev(g.c.read_jsonl(folder / 'full_relation_dev.jsonl'))
    refs = g.c.read_jsonl(folder / 'relation_dev.jsonl'); ids = {r['sampleId'] for r in full}
    cache = g.c.read_jsonl(g.ROOT / config['baselineNER'] / 'new_ner_dev_predictions.jsonl')
    expected = config['expected']
    if (len(rows) != expected['NERdev'] or len(full) != expected['completeDev'] or len(refs) != expected['knownPairs']
            or len([r for r in refs if r['sampleId'] in ids]) != expected['completePairs']
            or [r['sampleId'] for r in cache] != [r['sampleId'] for r in rows]
            or any(r['entities'] != p['referenceEntities'] for r, p in zip(rows, cache))):
        raise ValueError('Comparison cohort or cached reference drift')
    return config, rows, full, [r for r in refs if r['sampleId'] in ids], cache


def run(output):
    if output.exists(): raise FileExistsError('Preserve previous comparison')
    if not output.resolve().is_relative_to((g.ROOT / 'kg_datasets/dblp/course_v4_runs').resolve()): raise ValueError('Output outside runs')
    config, rows, full, refs, cache = load_inputs()
    if shutil.disk_usage(g.ROOT).free < config['reserveBytes'] + 100_000_000: raise ValueError('Insufficient storage reserve')
    checkpoint = g.ROOT / config['frozenRE'] / 're/checkpoint_epoch_06'
    if g.c.file_sha256(checkpoint / 'model.safetensors') != config['REWeightsSha256']: raise ValueError('Relation weights drift')
    inputs = [CONTRACT, Path(__file__), g.ROOT / 'tests/test_pretrained_ner_comparison.py',
              checkpoint / 'model.safetensors', g.ROOT / config['baselineNER'] / 'new_ner_dev_predictions.jsonl',
              g.ROOT / 'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl']
    inputs += [g.ROOT / config[k] / 'manifest.json' for k in ('snapshot', 'baselineNER', 'frozenRE')]
    inputs += [g.ROOT / config['snapshot'] / name for name in ('ner_dev.jsonl', 'full_relation_dev.jsonl', 'relation_dev.jsonl')]
    inputs += [g.ROOT / 'scripts' / name for name in ('train_course_ner.py', 'train_course_relation.py', 'evaluate_course_relation.py', 'course_relation_model.py')]
    inputs += [g.ROOT / config['modelDirectory'] / name for name in ('gliner_config.json', 'model.safetensors')]
    inputs += [g.ROOT / config['tokenizerDirectory'] / name for name in ('config.json', 'spm.model', 'tokenizer_config.json')]
    inputs += list((g.ROOT / '.runtime-gliner/gliner').rglob('*.py'))
    hashes = {p: g.c.file_sha256(p) for p in inputs}
    output.mkdir(parents=True)
    state = {'status': 'running', 'startedAtUTC': datetime.now(UTC).isoformat(), 'trainingExecuted': False,
             'testEvaluated': False, 'modelPromoted': False, 'independentHumanGold': False}
    g.c.write_json(output / 'status.json', state); started = time.perf_counter()
    try:
        sys.path.insert(0, str(g.ROOT / '.runtime-gliner'))
        os.environ['HF_HUB_OFFLINE'] = '1'; os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'
        import torch
        from gliner import GLiNER
        from huggingface_hub import try_to_load_from_cache
        from transformers import DataCollatorWithPadding
        if version('gliner') != config['runtimeVersion'] or not torch.cuda.is_available(): raise ValueError('Runtime/GPU unavailable')
        for name in ('config.json', 'spm.model', 'tokenizer_config.json'):
            cached = try_to_load_from_cache(config['backboneId'], name, revision='main')
            if not isinstance(cached, str) or Path(cached).parent.name != config['backboneRevision'] or g.c.file_sha256(Path(cached)) != g.c.file_sha256(g.ROOT / config['tokenizerDirectory'] / name):
                raise ValueError('Offline tokenizer/backbone revision drift')
        torch.manual_seed(20261010); torch.use_deterministic_algorithms(True); torch.cuda.reset_peak_memory_stats()
        model = GLiNER.from_pretrained(str(g.ROOT / config['modelDirectory']), local_files_only=True, strict=True, _attn_implementation='eager').to('cuda').eval().requires_grad_(False)
        predictions = []; raw = []; lengths = []
        for row in rows:
            words = [item[0] for item in model.data_processor.words_splitter(row['text'])]
            prepared, _ = model.data_processor.prepare_inputs([words], list(LABELS))
            tokens = model.data_processor.transformer_tokenizer(prepared, is_split_into_words=True, truncation=False)['input_ids'][0]
            maximum = model.model.token_rep_layer.bert_layer.model.config.max_position_embeddings
            if len(words) > model.config.max_len or len(tokens) > maximum: raise ValueError('Would truncate complete dev abstract: ' + row['sampleId'])
            lengths.append({'sampleId': row['sampleId'], 'words': len(words), 'subtokensWithLabels': len(tokens)})
            with torch.inference_mode(): entities = model.predict_entities(row['text'], list(LABELS), threshold=config['threshold'], flat_ner=True)
            predictions.append(checked_entities(row, entities)); raw.append({'sampleId': row['sampleId'], 'predictions': entities})
            print({'NERdocument': len(predictions), 'entities': len(entities)}, flush=True)
        peak = torch.cuda.max_memory_allocated(); del model; torch.cuda.empty_cache()
        metrics = {'scibert52': ner.score_rows(rows, [r['predictedEntities'] for r in cache], evaluation_target='exposed_dev_AI_reference'),
                   'gliner': ner.score_rows(rows, predictions, evaluation_target='exposed_dev_AI_reference')}
        tokenizer = re_model.prepare_tokenizer(checkpoint); collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
        relation = re_model.load_relation_model(checkpoint, tokenizer, 'entity_markers').to('cuda').eval().requires_grad_(False)
        pipelines = {}
        for name, values in (('scibert52', [r['predictedEntities'] for r in cache]), ('gliner', predictions)):
            by_id = dict(zip([r['sampleId'] for r in rows], values))
            candidates = [p for doc in full for p in candidate_rows(doc, by_id[doc['sampleId']])]
            edges = predict(relation, tokenizer, candidates, 512, collator, 'cuda', 4)
            pipelines[name] = score_pipeline(full, refs, edges)
            pipelines[name]['evaluationTarget'] = 'complete_document_exposed_dev_AI_reference_not_final_test'
            g.c.write_jsonl(output / (name + '_relation_predictions.jsonl'), edges)
        expected_pipeline = read(g.ROOT / config['frozenRE'] / 'comparison.json')['pipeline']['new']['positiveMicro']
        if any(pipelines['scibert52']['positiveMicro'][k] != expected_pipeline[k] for k in ('truePositive', 'predicted', 'reference', 'precision', 'recall', 'f1')):
            raise ValueError('Frozen pipeline replay drift')
        if any(g.c.file_sha256(path) != sha for path, sha in hashes.items()): raise ValueError('Input changed during comparison')
        result = {'NER': metrics, 'pipeline': pipelines, 'NERDocuments': len(rows), 'completeDocuments': len(full),
                  'lockedQueue': config['expected']['lockedQueue'], 'documentCoverage': len(full) / config['expected']['lockedQueue'],
                  'testEvaluated': False, 'trainingExecuted': False, 'modelPromoted': False, 'thresholdSearch': False,
                  'inferenceFeatures': 'original_text_and_fixed_label_descriptions_only', 'peakNERGPUBytes': peak,
                  'versions': {n: version(n) for n in ('gliner', 'torch', 'transformers', 'sentencepiece')},
                  'externalPretrainingOverlapUnknown': True, 'notice': 'AI-reference exposed dev only; zero-shot baseline is not the required course training experiment or final test.'}
        g.c.write_jsonl(output / 'gliner_raw_predictions.jsonl', raw)
        g.c.write_jsonl(output / 'gliner_ner_predictions.jsonl', [{'sampleId': r['sampleId'], 'referenceEntities': r['entities'], 'predictedEntities': p} for r, p in zip(rows, predictions)])
        g.c.write_json(output / 'token_lengths.json', lengths); g.c.write_json(output / 'comparison.json', result)
        state.update(status='completed', elapsedSeconds=time.perf_counter() - started, finishedAtUTC=datetime.now(UTC).isoformat())
        g.c.write_json(output / 'status.json', state); seal(output, inputs)
        print({'completed': True, 'NER': {k: v['micro'] for k, v in metrics.items()}, 'pipeline': {k: v['positiveMicro'] for k, v in pipelines.items()}}, flush=True)
    except Exception as error:
        state.update(status='failed_no_synthetic_fallback', errorType=type(error).__name__, error=str(error))
        g.c.write_json(output / 'status.json', state); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
