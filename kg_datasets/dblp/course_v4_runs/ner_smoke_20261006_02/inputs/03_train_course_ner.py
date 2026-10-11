"""Strict SciBERT NER preflight and train-only overfit smoke, not formal test evaluation.

Uses reviewed AI receipts, the existing BIO/metric contract and a pinned local
checkpoint. No test titles enter tokenization, gradients or scoring. Missing
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


def load_snapshot(dataset: Path, snapshot: Path) -> tuple[dict, dict]:
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
    splits = {}
    for split in ('train', 'dev'):
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


def dictionary_predict(text: str, lexicon: list[tuple[str, str]]) -> list[dict]:
    candidates = []
    for phrase, label in lexicon:
        for match in re.finditer(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text, re.IGNORECASE):
            candidates.append({'start': match.start(), 'end': match.end(), 'text': match.group(), 'label': label})
    selected = []
    for entity in sorted(candidates, key=lambda e: (-(e['end'] - e['start']), e['start'], e['label'])):
        if not any(entity['start'] < e['end'] and e['start'] < entity['end'] for e in selected):
            selected.append(entity)
    return sorted(selected, key=lambda e: e['start'])


def score_rows(rows: list[dict], predictions: list[list[dict]], *,
               evaluation_target: str = c.CONFIG['evaluationTarget']) -> dict:
    if len(rows) != len(predictions):
        raise ValueError('Predictions must cover every document exactly once')
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


def run(dataset: Path, snapshot: Path, model_path: Path, output: Path, mode: str,
        config: TrainingConfig, device_name: str = 'auto') -> dict:
    if output.exists():
        raise FileExistsError('Preserve experiment artifacts: choose a new output directory')
    if mode not in {'preflight', 'smoke'} or device_name not in {'auto', 'cpu', 'cuda'}:
        raise ValueError('Unsupported experiment mode or device')
    if (config.steps <= 0 or config.batch_size <= 0 or config.max_length < 2
            or not math.isfinite(config.learning_rate) or config.learning_rate <= 0):
        raise ValueError('Invalid training configuration')
    output.mkdir(parents=True, exist_ok=False)
    state = {'status': 'running', 'mode': mode, 'trainingStarted': False, 'formalTrainingStarted': False,
             'testEvaluated': False,
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
        if mode == 'smoke':
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
            rows = select_smoke(splits['train'], config.samples, config.seed)
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

            def evaluate(current_model):
                current_model.eval()
                total_loss, tokens, predictions, invalid = 0.0, 0, [], 0
                with torch.no_grad():
                    for start in range(0, len(records), config.batch_size):
                        chunk = records[start:start + config.batch_size]
                        batch = {k: v.to(device) for k, v in collator([r['features'] for r in chunk]).items()}
                        outputs = current_model(**batch)
                        count = int((batch['labels'] != -100).sum())
                        total_loss += float(outputs.loss) * count
                        tokens += count
                        labels = outputs.logits.argmax(-1).cpu().tolist()
                        for record, token_labels in zip(chunk, labels):
                            text = next(r['text'] for r in rows if r['sampleId'] == record['sampleId'])
                            decoded = decode_bio(token_labels[:len(record['offsets'])], record['offsets'], text)
                            predictions.append(decoded['entities'])
                            invalid += decoded['invalidTransitions']
                return {'loss': total_loss / tokens, 'invalidTransitions': invalid,
                        'metrics': score_rows(rows, predictions,
                                              evaluation_target='in_sample_ai_reference_agreement_not_generalization'),
                        'predictions': predictions}

            initial = evaluate(model)
            optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=0.01)
            state.update(trainingStarted=True, device=str(device), cudaVersion=torch.version.cuda,
                         gpu=torch.cuda.get_device_name(device) if device.type == 'cuda' else None)
            c.write_json(output / 'status.json', state)
            c.write_jsonl(output / 'smoke_train_inputs.jsonl', rows)
            generator = random.Random(config.seed)
            order = []
            with (output / 'steps.jsonl').open('x', encoding='utf-8') as stream:
                for step in range(1, config.steps + 1):
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
            final = evaluate(model)
            head_changed = not torch.equal(before_head, model.classifier.weight.detach().cpu())
            encoder_changed = not torch.equal(before_encoder, model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu())
            model.save_pretrained(output / 'model', safe_serialization=True)
            tokenizer.save_pretrained(output / 'model')
            del optimizer, model
            if device.type == 'cuda':
                torch.cuda.empty_cache()
            reloaded = BertForTokenClassification.from_pretrained(output / 'model', local_files_only=True,
                                                                  use_safetensors=True, attn_implementation='eager').to(device)
            recheck = evaluate(reloaded)
            reload_equal = recheck['predictions'] == final['predictions']
            c.write_jsonl(output / 'smoke_predictions.jsonl', [
                {'sampleId': r['sampleId'], 'referenceEntities': r['entities'], 'predictedEntities': p}
                for r, p in zip(rows, final['predictions'])])
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
            c.write_json(output / 'smoke_result.json', result)
        for name, digest in hashes.items():
            if c.file_sha256(Path(name)) != digest:
                raise ValueError('Experiment input changed: ' + name)
        verify_files(snapshot)
        verify_files(model_path)
        state.update(status='completed' if result is None or result['passed'] else 'smoke_gate_failed',
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('preflight', 'smoke'))
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--device', choices=('auto', 'cpu', 'cuda'), default='auto')
    for name, default in asdict(TrainingConfig()).items():
        parser.add_argument('--' + name.replace('_', '-'), type=type(default), default=default)
    args = parser.parse_args()
    config = TrainingConfig(**{key: getattr(args, key) for key in asdict(TrainingConfig())})
    state = run(args.dataset, args.snapshot, args.model, args.output, args.mode, config, args.device)
    print(json.dumps(state, ensure_ascii=False, indent=2), flush=True)
    if state['status'] != 'completed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
