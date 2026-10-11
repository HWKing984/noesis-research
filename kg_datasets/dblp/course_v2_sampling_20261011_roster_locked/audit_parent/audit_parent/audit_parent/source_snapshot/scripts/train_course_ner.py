"""Strict SciBERT NER preflight, train-only smoke and train/dev candidate fitting.

Uses reviewed AI receipts, the existing BIO/metric contract and a pinned local
checkpoint. Test titles are read only by the explicit locked evaluate-test mode. Missing
labels, drift and tokenizer boundary cuts fail instead of silently filtering.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
import time
import shutil
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from functools import lru_cache, partial

import course_weak as c
from import_course_ai import assess_readiness
from prepare_course_weak import verify_dataset


@dataclass(frozen=True)
class TrainingConfig:
    seed: int = 20261006
    samples: int = 24
    steps: int = 120
    batch_size: int = 8
    learning_rate: float = 5e-5
    max_length: int = 128
    epochs: int = 6


def verify_files(folder: Path) -> dict:
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if not manifest.get('filesSha256'):
        raise ValueError('Manifest must bind nonempty artifact files')
    for name, digest in manifest['filesSha256'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or not (folder / relative).resolve().is_relative_to(folder.resolve()):
            raise ValueError('Unsafe artifact manifest path')
        if not isinstance(digest, str) or not c.HASH_PATTERN.fullmatch(digest) or c.file_sha256(folder / relative) != digest:
            raise ValueError('Artifact changed: ' + name)
    return manifest


def load_snapshot(dataset: Path, snapshot: Path, *, include_test: bool = False) -> tuple[dict, dict]:
    """Rebind all train/dev inputs to eligible canonical receipts, never trust names alone."""
    before = c.file_sha256(snapshot / 'manifest.json')
    manifest = verify_files(snapshot)
    if manifest.get('sourceDatasetManifestSha256') != c.file_sha256(dataset / 'manifest.json'):
        raise ValueError('Snapshot is bound to another dataset')
    references = verify_dataset(dataset)
    lookup = {r['sampleId']: r for r in references}
    receipts = c.read_jsonl(snapshot / 'receipts.jsonl')
    summary = assess_readiness(receipts, references)
    if summary != json.loads((snapshot / 'summary.json').read_text(encoding='utf-8')):
        raise ValueError('Snapshot summary differs from validated receipts')
    by_id = {r['reference']['sampleId']: r for r in receipts}
    if include_test:
        test_ids = {r['sampleId'] for r in references if r['split'] == 'test'}
        if any(sid not in by_id or by_id[sid]['review'] is None for sid in test_ids):
            raise ValueError('Review the entire test queue before final test evaluation')
    splits = {}
    for split in (('train', 'dev', 'test') if include_test else ('train', 'dev')):
        rows = c.read_jsonl(snapshot / f'ner_inputs_{split}.jsonl')
        expected_ids = {r['reference']['sampleId'] for r in receipts
                        if r['reference']['split'] == split and c.eligible_tasks(r, r['reference'])['ner']}
        if not rows or len({r['sampleId'] for r in rows}) != len(rows) or {r['sampleId'] for r in rows} != expected_ids:
            raise ValueError('Missing, duplicate or ineligible NER rows in ' + split)
        for row in rows:
            ref, receipt = lookup[row['sampleId']], by_id[row['sampleId']]
            expected = {'sampleId': ref['sampleId'], 'text': ref['text'], 'textSha256': ref['textSha256'],
                        'referenceSha256': c.canonical_sha256(ref), 'annotationSha256': receipt['contentSha256'],
                        'labelSource': 'ai_pseudo', 'entities': receipt['annotation']['entities']}
            if row != expected or ref['split'] != split:
                raise ValueError('NER row differs from reviewed receipt: ' + row['sampleId'])
        splits[split] = rows
    if c.file_sha256(snapshot / 'manifest.json') != before:
        raise ValueError('Snapshot manifest changed during loading')
    verify_files(snapshot)
    return splits, summary


def decode_bio(labels: list[int], offsets: list[tuple[int, int]], text: str) -> dict:
    """Reject orphan I transitions rather than silently repairing them into B spans."""
    if len(labels) != len(offsets):
        raise ValueError('Token labels and Unicode offsets differ in length')
    entities, active, invalid, last_end = [], None, 0, 0

    def finish() -> None:
        nonlocal active
        if active is not None:
            start, end, label = active
            entities.append({'start': start, 'end': end, 'text': text[start:end], 'label': label})
            active = None

    for index, (start, end) in zip(labels, offsets):
        if type(index) is not int or not 0 <= index < len(c.CONFIG['bioLabels']):
            raise ValueError('Unknown BIO class index')
        if (start, end) == (0, 0):
            finish()
            continue
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text) or start < last_end:
            raise ValueError('Invalid decoder Unicode offsets')
        last_end = end
        tag = c.CONFIG['bioLabels'][index]
        if tag == 'O':
            finish()
        elif tag.startswith('B-'):
            finish()
            active = (start, end, tag[2:])
        elif active is not None and active[2] == tag[2:] and not text[active[1]:start].strip():
            active = (active[0], end, active[2])
        else:
            finish()
            invalid += 1
    finish()
    return {'entities': entities, 'invalidTransitions': invalid}


def make_dictionary(rows: list[dict]) -> list[tuple[str, str]]:
    phrases = {}
    for row in rows:
        for entity in row['entities']:
            phrases.setdefault(entity['text'].casefold(), set()).add(entity['label'])
    return sorted((phrase, next(iter(labels))) for phrase, labels in phrases.items() if len(labels) == 1)


@lru_cache(maxsize=2048)
def phrase_pattern(phrase: str):
    return re.compile(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', re.IGNORECASE)


def dictionary_predict(text: str, lexicon: list[tuple[str, str]]) -> list[dict]:
    candidates = []
    for phrase, label in lexicon:
        for match in phrase_pattern(phrase).finditer(text):
            candidates.append({'start': match.start(), 'end': match.end(), 'text': match.group(), 'label': label})
    selected = []
    for entity in sorted(candidates, key=lambda e: (-(e['end'] - e['start']), e['start'], e['label'])):
        if not any(entity['start'] < e['end'] and e['start'] < entity['end'] for e in selected):
            selected.append(entity)
    return sorted(selected, key=lambda e: e['start'])


def score_rows(rows: list[dict], predictions: list[list[dict]], *,
               evaluation_target: str = c.CONFIG['evaluationTarget']) -> dict:
    if (not rows or len(rows) != len(predictions) or len({r['sampleId'] for r in rows})!=len(rows)
            or any(not isinstance(r['sampleId'],str) or not r['sampleId'] for r in rows)):
        raise ValueError('Predictions must cover every document exactly once')
    for row, predicted_entities in zip(rows,predictions):
        for entities in (row['entities'],predicted_entities):
            if (any(e['label'] not in c.CONFIG['entityLabels'] or c.span_errors(e,row['text']) for e in entities)
                    or any(a['end']>b['start'] for a,b in zip(entities,entities[1:]))):
                raise ValueError('Entity scoring requires valid sorted nonoverlapping original spans')
    expected = [(r['sampleId'], e['start'], e['end'], e['label']) for r in rows for e in r['entities']]
    predicted = [(r['sampleId'], e['start'], e['end'], e['label']) for r, entities in zip(rows, predictions) for e in entities]
    return {'micro': c.entity_agreement(predicted, expected) | {'evaluationTarget': evaluation_target},
            'perClass': {label: c.entity_agreement([e for e in predicted if e[-1] == label],
                                                  [e for e in expected if e[-1] == label])
                         | {'evaluationTarget': evaluation_target}
                         for label in c.CONFIG['entityLabels']}}


def select_smoke(rows: list[dict], count: int, seed: int) -> list[dict]:
    if type(count) is not int or not 0 < count <= len(rows):
        raise ValueError('Smoke count must be positive and within eligible train rows')
    selected = []
    for label in c.CONFIG['entityLabels']:
        if any(e['label'] == label for r in selected for e in r['entities']):
            continue
        candidate = next((r for r in rows if any(e['label'] == label for e in r['entities'])), None)
        if candidate is not None and len(selected) < count:
            selected.append(candidate)
    shuffled = list(rows)
    random.Random(seed).shuffle(shuffled)
    for row in shuffled:
        if len(selected) == count:
            break
        if row['sampleId'] not in {r['sampleId'] for r in selected}:
            selected.append(row)
    return selected


def encode_row(tokenizer, row: dict, max_length: int) -> dict:
    encoded = dict(tokenizer(row['text'], return_offsets_mapping=True, truncation=False))
    if len(encoded['input_ids']) > max_length:
        raise ValueError('Title exceeds token limit; truncation forbidden: ' + row['sampleId'])
    offsets = encoded.pop('offset_mapping')
    encoded['labels'] = c.align_bio(offsets, row['entities'], row['text'])
    return {'sampleId': row['sampleId'], 'offsets': offsets, 'features': encoded}


def smoke_passed(initial_loss: float, final_loss: float, f1: float | None, changed: bool, reloaded: bool) -> bool:
    return bool(initial_loss > 0 and math.isfinite(final_loss) and final_loss <= initial_loss * 0.5
                and f1 is not None and f1 >= 0.9 and changed and reloaded)


def dev_checkpoint_improved(score: float | None, best: float | None) -> bool:
    """Strict entity micro F1 selects the earliest checkpoint on ties, never test."""
    if score is None or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError('Dev checkpoint selection requires a finite supported F1')
    return best is None or score > best


def evaluate_model(current_model, rows, records, target, *, collator, device, batch_size):
    """Shared dev/smoke/test inference; no gradients and the same strict decoder."""
    import torch
    current_model.eval()
    total_loss, tokens, predictions, invalid = 0.0, 0, [], 0
    texts = {r['sampleId']: r['text'] for r in rows}
    if [r['sampleId'] for r in records] != [r['sampleId'] for r in rows]:
        raise ValueError('Encoded records must match evaluation rows in order')
    with torch.no_grad():
        for start in range(0, len(records), batch_size):
            chunk = records[start:start + batch_size]
            batch = {k: v.to(device) for k, v in collator([r['features'] for r in chunk]).items()}
            outputs = current_model(**batch)
            if not torch.isfinite(outputs.loss) or not torch.isfinite(outputs.logits).all():
                raise ValueError('Nonfinite evaluation output')
            count = int((batch['labels'] != -100).sum())
            total_loss += float(outputs.loss) * count
            tokens += count
            labels = outputs.logits.argmax(-1).cpu().tolist()
            for record, token_labels in zip(chunk, labels):
                decoded = decode_bio(token_labels[:len(record['offsets'])], record['offsets'], texts[record['sampleId']])
                predictions.append(decoded['entities'])
                invalid += decoded['invalidTransitions']
    if not tokens:
        raise ValueError('No supported tokens for evaluation')
    return {'loss': total_loss / tokens, 'invalidTransitions': invalid,
            'metrics': score_rows(rows, predictions, evaluation_target=target), 'predictions': predictions}


def load_test_checkpoint(development: Path, selection: Path) -> tuple[Path, dict]:
    lock = json.loads(selection.read_text(encoding='utf-8'))
    manifest = verify_files(development)
    result = json.loads((development / 'development_result.json').read_text(encoding='utf-8'))
    state = json.loads((development / 'status.json').read_text(encoding='utf-8'))
    epochs = json.loads((development / 'epochs.json').read_text(encoding='utf-8'))
    best = max(epochs, key=lambda e: e['dev']['metrics']['micro']['f1'])
    checkpoint = f'checkpoint_epoch_{best["epoch"]:02d}'
    root = Path(__file__).resolve().parents[1]
    if (c.file_sha256(development / 'manifest.json') != lock['developmentManifestSha256']
            or (root / lock['developmentRun']).resolve() != development.resolve()
            or lock['checkpoint'] != checkpoint or result['bestCheckpoint'] != checkpoint
            or result['bestDev'] != best['dev'] or not result['passed'] or state['status'] != 'completed'
            or state['mode'] != 'fit-dev' or result['devUsedForGradient'] or result['testEvaluated']
            or lock['testMetricsUsedForSelection'] or lock['humanGold']
            or manifest['filesSha256'][checkpoint + '/model.safetensors'] != lock['weightsSha256']):
        raise ValueError('Frozen test checkpoint differs from declared dev selection')
    return development / checkpoint, manifest


def load_final_inputs(dataset: Path, snapshot: Path, development: Path, selection: Path):
    checkpoint, manifest = load_test_checkpoint(development, selection)
    lock = json.loads(selection.read_text(encoding='utf-8'))
    training_snapshot = Path(__file__).resolve().parents[1] / lock['trainingSnapshot']
    old_path = str((training_snapshot / 'manifest.json').resolve())
    if (manifest['inputSha256'].get(old_path) != lock['trainingSnapshotManifestSha256']
            or c.file_sha256(training_snapshot / 'manifest.json') != lock['trainingSnapshotManifestSha256']):
        raise ValueError('Frozen training snapshot differs from selection')
    for path in (c.CONFIG_PATH, c.SCHEMA_PATH, Path(c.__file__)):
        if manifest['inputSha256'].get(str(path.resolve())) != c.file_sha256(path):
            raise ValueError('Frozen extraction contract changed')
    old, _ = load_snapshot(dataset, training_snapshot)
    splits, summary = load_snapshot(dataset, snapshot, include_test=True)
    if any(splits[s] != old[s] for s in ('train', 'dev')):
        raise ValueError('Final test must preserve original train/dev inputs')
    receipts = [r for r in c.read_jsonl(snapshot / 'receipts.jsonl') if r['reference']['split'] == 'test']
    locked = datetime.fromisoformat(lock['lockedAtUTC'].replace('Z', '+00:00'))
    finished = datetime.fromisoformat(json.loads((development / 'status.json').read_text())['finishedAt'])
    if (len(receipts) != lock['testQueueDocuments'] or finished >= locked
            or any(not locked < datetime.fromisoformat(r['generation']['createdAt'])
                   <= datetime.fromisoformat(r['review']['provenance']['createdAt']) for r in receipts)):
        raise ValueError('Test queue or recorded selection chronology differs')
    return checkpoint, manifest, splits, summary, lock


def evaluate_test(dataset: Path, snapshot: Path, development: Path, selection: Path,
                  output: Path, device_name: str = 'auto') -> dict:
    """One frozen-checkpoint test pass; unchanged dev predictions gate serving parity first."""
    if output.exists():
        raise FileExistsError('Preserve final test artifacts; no overwrite or automatic retry')
    if device_name not in {'auto', 'cpu', 'cuda'}:
        raise ValueError('Unsupported evaluation device')
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    state = {'status': 'running', 'mode': 'evaluate-test', 'trainingStarted': False,
             'testEvaluated': False, 'humanGold': False, 'createdAt': datetime.now(UTC).isoformat(),
             'evaluationTarget': c.CONFIG['evaluationTarget']}
    c.write_json(output / 'status.json', state)
    try:
        paths = [dataset / 'manifest.json', snapshot / 'manifest.json', development / 'manifest.json',
                 selection, Path(__file__), c.CONFIG_PATH, c.SCHEMA_PATH, Path(c.__file__)]
        hashes = {str(p.resolve()): c.file_sha256(p) for p in paths}
        checkpoint, dm, splits, summary, lock = load_final_inputs(dataset, snapshot, development, selection)
        config = TrainingConfig(**dm['config'])
        (output / 'inputs').mkdir()
        archived = {}
        for index, path in enumerate(paths):
            dest = output / 'inputs' / f'{index:02d}_{path.name}'
            shutil.copyfile(path, dest)
            if c.file_sha256(dest) != hashes[str(path.resolve())]:
                raise ValueError('Final test input changed during archival')
            archived[str(path.resolve())] = dest.relative_to(output).as_posix()
        os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
        import numpy as np
        import torch
        from transformers import BertTokenizerFast, BertForTokenClassification, DataCollatorForTokenClassification
        random.seed(config.seed)
        np.random.seed(config.seed)
        torch.manual_seed(config.seed)
        torch.cuda.manual_seed_all(config.seed)
        torch.set_num_threads(4)
        torch.use_deterministic_algorithms(True)
        torch.backends.cudnn.benchmark = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        device = torch.device(('cuda' if torch.cuda.is_available() else 'cpu') if device_name == 'auto' else device_name)
        if device.type == 'cuda' and not torch.cuda.is_available():
            raise ValueError('CUDA requested but unavailable; no silent fallback')
        tokenizer = BertTokenizerFast.from_pretrained(checkpoint, local_files_only=True, do_lower_case=True)
        encoded, rejected = {}, []
        for split in ('dev', 'test'):
            encoded[split] = []
            for row in splits[split]:
                try:
                    encoded[split].append(encode_row(tokenizer, row, config.max_length))
                except ValueError as error:
                    rejected.append({'sampleId': row['sampleId'], 'split': split, 'reason': str(error)})
        c.write_json(output / 'preflight.json', {'valid': not rejected, 'rejected': rejected,
                     'tokenized': {s: len(r) for s, r in encoded.items()},
                     'maxTokens': {s: max((len(r['features']['input_ids']) for r in rows), default=0) for s, rows in encoded.items()},
                     'classSupport': summary['entitySupport']['test'], 'testQueueReviewed': lock['testQueueDocuments']})
        if rejected:
            raise ValueError('Test tokenizer alignment failed; no silent filtering')
        model = BertForTokenClassification.from_pretrained(checkpoint, local_files_only=True,
                    use_safetensors=True, attn_implementation='eager').to(device)
        if [model.config.id2label[i] for i in range(len(c.CONFIG['bioLabels']))] != c.CONFIG['bioLabels']:
            raise ValueError('Checkpoint BIO label order differs from contract')
        model.requires_grad_(False)
        evaluate = partial(evaluate_model, collator=DataCollatorForTokenClassification(tokenizer, padding=True,
                           return_tensors='pt'), device=device, batch_size=config.batch_size)
        dev = evaluate(model, splits['dev'], encoded['dev'], c.CONFIG['evaluationTarget'])
        old_predictions = c.read_jsonl(development / 'dev_predictions.jsonl')
        if dev['predictions'] != [p['predictedEntities'] for p in old_predictions]:
            raise ValueError('Frozen dev reload predictions changed; refuse test inference')
        c.write_json(output / 'dev_reload_check.json', {'predictionsIdentical': True, 'documents': len(splits['dev']),
                      'metrics': dev['metrics'], 'checkpointSelectionRepeated': False})
        print(json.dumps({'devReloadIdentical': True, 'testDocuments': len(splits['test'])}), flush=True)
        state.update(testInferenceStarted=True, device=str(device), cudaVersion=torch.version.cuda,
                     gpu=torch.cuda.get_device_name(device) if device.type == 'cuda' else None)
        c.write_json(output / 'status.json', state)
        test = evaluate(model, splits['test'], encoded['test'], c.CONFIG['evaluationTarget'])
        predictions = [{'sampleId': r['sampleId'], 'referenceEntities': r['entities'], 'predictedEntities': p}
                       for r, p in zip(splits['test'], test['predictions'])]
        c.write_jsonl(output / 'test_inputs.jsonl', splits['test'])
        c.write_jsonl(output / 'test_predictions.jsonl', predictions)
        spans = lambda items: {(e['start'], e['end'], e['label']) for e in items}
        errors = [p for p in predictions if spans(p['referenceEntities']) != spans(p['predictedEntities'])]
        c.write_jsonl(output / 'test_errors.jsonl', errors)
        receipts = [r for r in c.read_jsonl(snapshot / 'receipts.jsonl') if r['reference']['split'] == 'test']
        eligible = {r['sampleId'] for r in splits['test']}
        excluded = [{'sampleId': r['reference']['sampleId'], 'text': r['reference']['text'],
                     'entityStatus': r['annotation']['entityStatus'], 'reason': r['annotation']['entityReason'],
                     'groupMentions': r['annotation']['groupMentions'], 'annotationSha256': r['contentSha256']}
                    for r in receipts if r['reference']['sampleId'] not in eligible]
        c.write_jsonl(output / 'excluded_test_titles.jsonl', excluded)
        lexicon = make_dictionary(splits['train'])
        baseline = [dictionary_predict(r['text'], lexicon) for r in splits['test']]
        c.write_jsonl(output / 'dictionary_test_predictions.jsonl', [
            {'sampleId': r['sampleId'], 'entities': p} for r, p in zip(splits['test'], baseline)])
        baseline_metrics = score_rows(splits['test'], baseline)
        c.write_json(output / 'dictionary_test_metrics.json', baseline_metrics | {
            'lexiconPhrases': len(lexicon), 'source': 'unchanged_frozen_train_spans_only', 'humanGold': False})
        weights_unchanged = c.file_sha256(checkpoint / 'model.safetensors') == lock['weightsSha256']
        if not weights_unchanged or any(p.grad is not None or p.requires_grad for p in model.parameters()):
            raise ValueError('Final test must not alter weights or enable gradients')
        if any(c.file_sha256(Path(p)) != h for p, h in hashes.items()):
            raise ValueError('Final test input changed during evaluation')
        verify_files(snapshot)
        verify_files(development)
        result = {'evaluationScope': 'locked_final_test_ai_reference_agreement_not_human_gold',
                  'checkpoint': lock['checkpoint'], 'weightsSha256': lock['weightsSha256'],
                  'queueReviewed': len(receipts), 'documents': len(splits['test']), 'excludedDocuments': len(excluded),
                  'eligibleCoverage': len(splits['test']) / len(receipts), 'errorDocuments': len(errors),
                  'test': {k: v for k, v in test.items() if k != 'predictions'}, 'dictionaryTest': baseline_metrics,
                  'trainDevUnchanged': True, 'devReloadPredictionsIdentical': True, 'weightsUnchanged': weights_unchanged,
                  'testEvaluated': True, 'humanGold': False, 'independentAnnotator': False, 'testUsedForSelection': False,
                  'notice': 'AI self-reviewed references; conditional on eligible titles, not all 200. Rare support is not reliability. This model version is closed to test-informed tuning.'}
        c.write_json(output / 'test_result.json', result)
        state.update(status='completed', testEvaluated=True, finishedAt=datetime.now(UTC).isoformat(),
                     elapsedSeconds=time.perf_counter() - started, config=asdict(config))
        c.write_json(output / 'status.json', state)
        c.write_json(output / 'manifest.json', {'inputSha256': hashes, 'archivedInputs': archived,
                     'config': asdict(config), 'decoderPolicy': dm['decoderPolicy'], 'python': sys.version,
                     'packages': {name: version(name) for name in dm['packages']},
                     'filesSha256': {p.relative_to(output).as_posix(): c.file_sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}})
        return state
    except Exception as error:
        state.update(status='failed', errorType=type(error).__name__, error=str(error), elapsedSeconds=time.perf_counter() - started)
        c.write_json(output / 'status.json', state)
        raise


def run(dataset: Path, snapshot: Path, model_path: Path, output: Path, mode: str,
        config: TrainingConfig, device_name: str = 'auto') -> dict:
    if output.exists():
        raise FileExistsError('Preserve experiment artifacts: choose a new output directory')
    if mode not in {'preflight', 'smoke', 'fit-dev'} or device_name not in {'auto', 'cpu', 'cuda'}:
        raise ValueError('Unsupported experiment mode or device')
    if (config.steps <= 0 or config.batch_size <= 0 or config.max_length < 2
            or not math.isfinite(config.learning_rate) or config.learning_rate <= 0
            or type(config.epochs) is not int or config.epochs <= 0):
        raise ValueError('Invalid training configuration')
    output.mkdir(parents=True, exist_ok=False)
    state = {'status': 'running', 'mode': mode, 'trainingStarted': False, 'formalTrainingStarted': False,
             'testEvaluated': False, 'developmentTrainingStarted': False,
             'evaluationTarget': ('in_sample_ai_reference_agreement_not_generalization' if mode == 'smoke'
                                  else c.CONFIG['evaluationTarget']),
             'createdAt': datetime.now(UTC).isoformat(), 'config': asdict(config)}
    c.write_json(output / 'status.json', state)
    started = time.perf_counter()
    try:
        input_paths = [dataset / 'manifest.json', snapshot / 'manifest.json', model_path / 'manifest.json',
                       Path(__file__), c.CONFIG_PATH, c.SCHEMA_PATH, Path(c.__file__),
                       Path(sys.modules['import_course_ai'].__file__), Path(sys.modules['prepare_course_weak'].__file__)]
        hashes = {str(p.resolve()): c.file_sha256(p) for p in input_paths}
        # Keep the small source/config/manifest inputs; do not duplicate the full dataset or base weights.
        (output / 'inputs').mkdir()
        archived_inputs = {}
        for index, path in enumerate(input_paths):
            archive = output / 'inputs' / f'{index:02d}_{path.name}'
            shutil.copyfile(path, archive)
            if c.file_sha256(archive) != hashes[str(path.resolve())]:
                raise ValueError('Input changed during provenance archival: ' + str(path))
            archived_inputs[str(path.resolve())] = archive.relative_to(output).as_posix()
        splits, summary = load_snapshot(dataset, snapshot)
        model_manifest = verify_files(model_path)
        required = {'config.json', 'vocab.txt', 'pytorch_model.bin'}
        if (model_manifest.get('modelId') != 'allenai/scibert_scivocab_uncased'
                or model_manifest.get('revision') != '24f92d32b1bfb0bcaf9ab193ff3ad01e87732fc1'
                or not required <= set(model_manifest['filesSha256'])
                or model_manifest['filesSha256']['pytorch_model.bin'] != 'e492944d88ac97dee6baa547671d3c526a3d067676883efb058311f4e5882e1a'):
            raise ValueError('Model checkpoint is not the declared pinned SciBERT artifact')
        from transformers import BertTokenizerFast
        tokenizer = BertTokenizerFast.from_pretrained(model_path, local_files_only=True, do_lower_case=True)
        encoded, rejected = {}, []
        for split, rows in splits.items():
            encoded[split] = []
            for row in rows:
                try:
                    encoded[split].append(encode_row(tokenizer, row, config.max_length))
                except ValueError as error:
                    rejected.append({'sampleId': row['sampleId'], 'split': split, 'reason': str(error)})
        preflight = {'valid': not rejected, 'documents': {s: len(r) for s, r in splits.items()},
                     'tokenized': {s: len(r) for s, r in encoded.items()}, 'rejected': rejected,
                     'maxTokens': {s: max(len(r['features']['input_ids']) for r in rows) if rows else 0
                                   for s, rows in encoded.items()},
                     'classSupport': summary['entitySupport'], 'formalReadiness': summary['nerTrainingReady'],
                     'testTokenized': False, 'notice': 'Preflight is not model accuracy or formal experiment readiness.'}
        c.write_json(output / 'preflight.json', preflight)
        if rejected:
            raise ValueError('Tokenizer preflight rejected rows; inspect preflight.json, no silent filtering')
        lexicon = make_dictionary(splits['train'])
        baseline = [dictionary_predict(r['text'], lexicon) for r in splits['dev']]
        c.write_json(output / 'dictionary_dev_metrics.json', score_rows(splits['dev'], baseline) | {
            'method': 'train_span_dictionary_longest_match', 'split': 'dev', 'lexiconPhrases': len(lexicon),
            'testEvaluated': False, 'humanGold': False})
        c.write_jsonl(output / 'dictionary_dev_predictions.jsonl', [
            {'sampleId': r['sampleId'], 'entities': prediction} for r, prediction in zip(splits['dev'], baseline)])
        result = None
        if mode in {'smoke', 'fit-dev'}:
            os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
            import numpy as np
            import torch
            from transformers import BertForTokenClassification, DataCollatorForTokenClassification
            random.seed(config.seed)
            np.random.seed(config.seed)
            torch.manual_seed(config.seed)
            torch.cuda.manual_seed_all(config.seed)
            torch.set_num_threads(4)
            torch.use_deterministic_algorithms(True)
            torch.backends.cudnn.benchmark = False
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            device = torch.device(('cuda' if torch.cuda.is_available() else 'cpu') if device_name == 'auto' else device_name)
            if device.type == 'cuda' and not torch.cuda.is_available():
                raise ValueError('CUDA requested but unavailable; no silent CPU fallback')
            rows = select_smoke(splits['train'], config.samples, config.seed) if mode == 'smoke' else splits['train']
            selection = {r['sampleId'] for r in rows}
            lookup = {r['sampleId']: r for r in encoded['train']}
            records = [lookup[r['sampleId']] for r in rows]
            collator = DataCollatorForTokenClassification(tokenizer, padding=True, return_tensors='pt')
            model = BertForTokenClassification.from_pretrained(
                model_path, local_files_only=True, weights_only=True, num_labels=len(c.CONFIG['bioLabels']),
                id2label=dict(enumerate(c.CONFIG['bioLabels'])),
                label2id={name: i for i, name in enumerate(c.CONFIG['bioLabels'])}, attn_implementation='eager').to(device)
            before_head = model.classifier.weight.detach().cpu().clone()
            before_encoder = model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu().clone()

            evaluate = partial(evaluate_model, collator=collator, device=device, batch_size=config.batch_size)

            eval_rows = rows if mode == 'smoke' else splits['dev']
            eval_records = records if mode == 'smoke' else encoded['dev']
            target = ('in_sample_ai_reference_agreement_not_generalization' if mode == 'smoke'
                      else c.CONFIG['evaluationTarget'])
            initial = evaluate(model, eval_rows, eval_records, target)
            optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=0.01)
            state.update(trainingStarted=True, device=str(device), cudaVersion=torch.version.cuda,
                         developmentTrainingStarted=mode == 'fit-dev',
                         gpu=torch.cuda.get_device_name(device) if device.type == 'cuda' else None)
            c.write_json(output / 'status.json', state)
            c.write_jsonl(output / ('smoke_train_inputs.jsonl' if mode == 'smoke' else 'development_train_inputs.jsonl'), rows)
            generator = random.Random(config.seed)
            order = []
            batches_per_epoch = math.ceil(len(records) / config.batch_size)
            total_steps = config.steps if mode == 'smoke' else config.epochs * batches_per_epoch
            best_f1, best_path, best_evaluation, epochs = None, None, None, []
            with (output / 'steps.jsonl').open('x', encoding='utf-8') as stream:
                for step in range(1, total_steps + 1):
                    if not order:
                        order = list(range(len(records)))
                        generator.shuffle(order)
                    indices, order = order[:config.batch_size], order[config.batch_size:]
                    batch = {k: v.to(device) for k, v in collator([records[i]['features'] for i in indices]).items()}
                    model.train()
                    optimizer.zero_grad(set_to_none=True)
                    loss = model(**batch).loss
                    if not torch.isfinite(loss):
                        raise ValueError('Nonfinite training loss')
                    loss.backward()
                    norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    if not torch.isfinite(norm):
                        raise ValueError('Nonfinite training gradient')
                    optimizer.step()
                    record = {'step': step, 'loss': float(loss.detach()), 'gradientNorm': float(norm),
                              'sampleIds': [records[i]['sampleId'] for i in indices]}
                    stream.write(json.dumps(record, allow_nan=False) + '\n')
                    stream.flush()
                    if step == 1 or step % 20 == 0:
                        print(json.dumps({'step': step, 'loss': record['loss']}, allow_nan=False), flush=True)
                    if mode == 'fit-dev' and not order:
                        epoch = step // batches_per_epoch
                        validation = evaluate(model, eval_rows, eval_records, target)
                        improved = dev_checkpoint_improved(validation['metrics']['micro']['f1'], best_f1)
                        if improved:
                            best_f1, best_path, best_evaluation = validation['metrics']['micro']['f1'], output / f'checkpoint_epoch_{epoch:02d}', validation
                            model.save_pretrained(best_path, safe_serialization=True)
                            tokenizer.save_pretrained(best_path)
                        epoch_record = {'epoch': epoch, 'step': step,
                                        'trainDocuments': len(records), 'devDocuments': len(eval_rows),
                                        'dev': {k: v for k, v in validation.items() if k != 'predictions'},
                                        'checkpointImproved': improved}
                        epochs.append(epoch_record)
                        c.write_json(output / 'epochs.json', epochs)
                        print(json.dumps(epoch_record, allow_nan=False), flush=True)
            final = evaluate(model, eval_rows, eval_records, target) if mode == 'smoke' else best_evaluation
            head_changed = not torch.equal(before_head, model.classifier.weight.detach().cpu())
            encoder_changed = not torch.equal(before_encoder, model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu())
            if mode == 'smoke':
                best_path = output / 'model'
                model.save_pretrained(best_path, safe_serialization=True)
                tokenizer.save_pretrained(best_path)
            del optimizer, model
            if device.type == 'cuda':
                torch.cuda.empty_cache()
            reloaded = BertForTokenClassification.from_pretrained(best_path, local_files_only=True,
                                                                  use_safetensors=True, attn_implementation='eager').to(device)
            recheck = evaluate(reloaded, eval_rows, eval_records, target)
            reload_equal = recheck['predictions'] == final['predictions']
            head_changed = head_changed and not torch.equal(before_head, reloaded.classifier.weight.detach().cpu())
            encoder_changed = encoder_changed and not torch.equal(before_encoder, reloaded.bert.encoder.layer[0].attention.self.query.weight.detach().cpu())
            predictions = [
                {'sampleId': r['sampleId'], 'referenceEntities': r['entities'], 'predictedEntities': p}
                for r, p in zip(eval_rows, final['predictions'])]
            c.write_jsonl(output / ('smoke_predictions.jsonl' if mode == 'smoke' else 'dev_predictions.jsonl'), predictions)
            result = {'evaluationScope': 'in_sample_overfit_smoke_not_generalization', 'documents': len(selection),
                      'support': dict(Counter(e['label'] for r in rows for e in r['entities'])),
                      'initial': {k: v for k, v in initial.items() if k != 'predictions'},
                      'final': {k: v for k, v in final.items() if k != 'predictions'},
                      'classifierChanged': head_changed, 'encoderChanged': encoder_changed,
                      'reloadPredictionsIdentical': reload_equal,
                      'passed': smoke_passed(initial['loss'], final['loss'], final['metrics']['micro']['f1'],
                                            head_changed and encoder_changed, reload_equal),
                      'gates': {'maxFinalInitialLossRatio': 0.5, 'minInSampleStrictEntityF1': 0.9},
                      'devUsedForGradient': False, 'testEvaluated': False, 'humanGold': False,
                      'notice': 'Memorizing reviewed AI train labels does not establish generalization or semantic accuracy.'}
            if mode == 'fit-dev':
                result = {'evaluationScope': 'dev_selected_ai_reference_agreement_not_final_test',
                          'trainDocuments': len(rows), 'devDocuments': len(eval_rows), 'epochs': config.epochs,
                          'steps': total_steps, 'initialDev': {k: v for k, v in initial.items() if k != 'predictions'},
                          'bestDev': {k: v for k, v in final.items() if k != 'predictions'},
                          'bestCheckpoint': best_path.relative_to(output).as_posix(),
                          'selection': 'strict_dev_entity_micro_f1_earliest_tie',
                          'classifierChanged': head_changed, 'encoderChanged': encoder_changed,
                          'reloadPredictionsIdentical': reload_equal,
                          'passed': head_changed and encoder_changed and reload_equal,
                          'dictionaryDevF1': score_rows(splits['dev'], baseline)['micro']['f1'],
                          'devUsedForGradient': False, 'testEvaluated': False, 'testTokenized': False,
                          'humanGold': False, 'formalReadiness': summary['nerTrainingReady'],
                          'notice': 'Dev selects checkpoint and is not an untouched final test; AI self-reviewed labels are not human gold.'}
                def spans(items):
                    return {(e['start'], e['end'], e['label']) for e in items}
                c.write_jsonl(output / 'dev_errors.jsonl', [p for p in predictions
                    if spans(p['referenceEntities']) != spans(p['predictedEntities'])])
            c.write_json(output / ('smoke_result.json' if mode == 'smoke' else 'development_result.json'), result)
        for name, digest in hashes.items():
            if c.file_sha256(Path(name)) != digest:
                raise ValueError('Experiment input changed: ' + name)
        verify_files(snapshot)
        verify_files(model_path)
        state.update(status='completed' if result is None or result['passed'] else 'training_gate_failed',
                     elapsedSeconds=time.perf_counter() - started, testTokenized=False,
                     finishedAt=datetime.now(UTC).isoformat())
        c.write_json(output / 'status.json', state)
        packages = {name: version(name) for name in ('torch', 'transformers', 'tokenizers', 'huggingface-hub',
                                                     'safetensors', 'numpy', 'jsonschema')}
        c.write_json(output / 'manifest.json', {'inputSha256': hashes, 'archivedInputs': archived_inputs,
                     'modelProvenance': model_manifest,
                     'packages': packages, 'python': sys.version, 'config': asdict(config),
                     'decoderPolicy': 'drop_orphan_I_no_B_repair',
                     'reproducibility': 'Fixed seeds and deterministic eager FP32; hardware/library changes may still alter results.',
                     'resumeSupported': False,
                     'filesSha256': {p.relative_to(output).as_posix(): c.file_sha256(p)
                                     for p in sorted(output.rglob('*')) if p.is_file()}})
        return state
    except Exception as error:
        state.update(status='failed', errorType=type(error).__name__, error=str(error),
                     elapsedSeconds=time.perf_counter() - started)
        c.write_json(output / 'status.json', state)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('mode', choices=('preflight', 'smoke', 'fit-dev', 'evaluate-test'))
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device', choices=('auto', 'cpu', 'cuda'), default='auto')
    parser.add_argument('--selection', type=Path, help='Required frozen selection JSON for evaluate-test; --model is the sealed development run')
    for name, default in asdict(TrainingConfig()).items():
        parser.add_argument('--' + name.replace('_', '-'), type=type(default), default=default)
    args = parser.parse_args()
    config = TrainingConfig(**{key: getattr(args, key) for key in asdict(TrainingConfig())})
    if args.mode == 'evaluate-test':
        if args.selection is None or any('--' + name.replace('_', '-') in {arg.split('=',1)[0] for arg in sys.argv[1:]} for name in asdict(config)):
            parser.error('evaluate-test requires --selection and inherits frozen config; no test tuning arguments')
        state = evaluate_test(args.dataset, args.snapshot, args.model, args.selection, args.output, args.device)
    else:
        state = run(args.dataset, args.snapshot, args.model, args.output, args.mode, config, args.device)
    print(json.dumps(state, ensure_ascii=False, indent=2), flush=True)
    if state['status'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
