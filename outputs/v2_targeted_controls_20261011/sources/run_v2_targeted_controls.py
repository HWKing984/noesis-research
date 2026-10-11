"""Frozen-weight BIO contrast, one weighted RE fit, and four fixed pipeline cells."""
from __future__ import annotations

import argparse
import gc
import json
import os
import time
import traceback
from collections import Counter
from pathlib import Path

import course_weak as c
import course_bio_constraints as bio
import course_v2_textscope_metrics as metrics
import run_v2_textscope_once as prior
import train_course_ner as ner
import train_course_relation as rel


def ner_contrast(data, previous, out, device):
    import torch
    from transformers import BertTokenizerFast, BertForTokenClassification, DataCollatorWithPadding
    folder = previous / 'ner/best_model'
    tokenizer = BertTokenizerFast.from_pretrained(folder, local_files_only=True)
    model = BertForTokenClassification.from_pretrained(folder, local_files_only=True,
                         use_safetensors=True, attn_implementation='eager').to(device).eval().requires_grad_(False)
    collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
    result, predictions, logits_rows, errors = {}, {}, [], []
    for split in ('train', 'dev'):
        rows = c.read_jsonl(data / f'{split}_ner.jsonl')
        predictions[split] = {'argmax': [], 'legal': []}
        invalid = Counter()
        with torch.inference_mode():
            for start in range(0, len(rows), prior.BATCH):
                chunk = rows[start:start+prior.BATCH]
                records = [ner.encode_row(tokenizer, r, prior.MAX_LENGTH) for r in chunk]
                for record, row in zip(records, chunk):
                    # Roundtrip the supplied labels separately; neither labels nor offsets enter the model.
                    gold = ner.decode_bio([max(0, t) for t in record['features']['labels']], record['offsets'], row['text'])
                    key = lambda e: (e['start'], e['end'], e['label'])
                    if {key(e) for e in gold['entities']} != {key(e) for e in row['entities']} or gold['invalidTransitions']:
                        raise ValueError('Training/reference BIO roundtrip failed')
                features = [{k: v for k, v in r['features'].items() if k != 'labels'} for r in records]
                batch = {k: v.to(device) for k, v in collator(features).items()}
                scores = model(**batch).logits.cpu().tolist()
                for row, record, padded in zip(chunk, records, scores):
                    logits = padded[:len(record['offsets'])]
                    paths = {'argmax': [max(range(len(v)), key=v.__getitem__) for v in logits],
                             'legal': bio.legal_bio_labels(logits, record['offsets'])}
                    logits_rows.append({'split': split, 'sampleId': row['sampleId'], 'offsets': record['offsets'], 'logits': logits})
                    for mode, path in paths.items():
                        decoded = ner.decode_bio(path, record['offsets'], row['text'])
                        invalid[mode] += decoded['invalidTransitions']
                        if mode == 'legal' and decoded['invalidTransitions']:
                            raise ValueError('Constrained path incompatible with source offsets')
                        predictions[split][mode].append({**{k: row[k] for k in ('arxivId', 'sampleId', 'text', 'textSha256')},
                                                         'referenceEntities': row['entities'], 'predictedEntities': decoded['entities']})
        result[split] = {'metrics': {mode: prior.clean_eval({'metrics': ner.score_rows(rows, [p['predictedEntities'] for p in ps], evaluation_target=prior.TARGET)})['metrics']
                                    for mode, ps in predictions[split].items()}, 'invalidTransitions': dict(invalid),
                         'evaluationScope': 'in_sample_training_label_diagnostic' if split == 'train' else 'exposed_dev_decoder_comparison',
                         'referenceEncodingRoundtripPassed': len(rows)}
        for mode, ps in predictions[split].items():
            c.write_jsonl(out / f'{split}_ner_{mode}_predictions.jsonl', ps)
        if split == 'train':
            for row in predictions[split]['argmax']:
                key = lambda e: (e['start'], e['end'], e['label'])
                gold = {key(e): e for e in row['referenceEntities']}
                pred = {key(e): e for e in row['predictedEntities']}
                for kind, source, other in [('FN', gold, pred), ('FP', pred, gold)]:
                    for k in sorted(source.keys()-other.keys()):
                        entity = source[k]
                        overlaps = [e for e in other.values() if max(e['start'], entity['start']) < min(e['end'], entity['end'])]
                        errors.append({'arxivId': row['arxivId'], 'kind': kind, 'entity': entity,
                                       'overlaps': overlaps, 'text': row['text'], 'labelMutation': False})
    old = c.read_jsonl(previous / 'ner/dev_predictions.jsonl')
    if [p['predictedEntities'] for p in predictions['dev']['argmax']] != [p['predictedEntities'] for p in old]:
        raise ValueError('Original NER predictions not reproduced')
    c.write_jsonl(out / 'ner_logits.jsonl', logits_rows)
    c.write_jsonl(out / 'train_ner_error_review.jsonl', errors)
    c.write_json(out / 'ner_decoder_result.json', result)
    del model
    gc.collect()
    torch.cuda.empty_cache()
    prior.log({'stage': 'NER_contrast_complete', 'devF1': {k: v['micro']['f1'] for k, v in result['dev']['metrics'].items()},
               'invalid': result['dev']['invalidTransitions']})
    return result, predictions


def weighted_fit(data, base, out, device, plans, weights):
    import torch
    from transformers import DataCollatorWithPadding
    out.mkdir()
    prior.seed_all()
    train, dev = c.read_jsonl(data / 'train_re_scored.jsonl'), c.read_jsonl(data / 'dev_re_scored.jsonl')
    tokenizer = rel.prepare_tokenizer(base)
    encoded = {split: [rel.encode_pair(tokenizer, r, prior.MAX_LENGTH) for r in rows]
               for split, rows in [('train', train), ('dev', dev)]}
    model = rel.load_relation_model(base, tokenizer, 'entity_markers', initialize_from_base=True).to(device)
    before = model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu().clone()
    collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
    evaluate = lambda current: rel.evaluate_model(current, dev, encoded['dev'], collator, device, prior.BATCH)
    c.write_json(out / 'initial_dev.json', prior.clean_eval(evaluate(model)))
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5, weight_decay=0.01)
    weight = torch.tensor([weights[label] for label in rel.LABELS], dtype=torch.float32, device=device)
    best, best_epoch, best_eval, updates, history = None, None, None, 0, []
    with (out / 'steps.jsonl').open('x', encoding='utf-8') as stream:
        for epoch, indices in enumerate(plans, 1):
            loss_sum = 0.0
            for start in range(0, len(indices), prior.BATCH):
                chosen = indices[start:start+prior.BATCH]
                model.train()
                optimizer.zero_grad(set_to_none=True)
                logits, targets = rel.forward_batch(model, [encoded['train'][i] for i in chosen], collator, device)
                # Fixed global expected normalization, not a fluctuating minibatch weight sum.
                loss = (torch.nn.functional.cross_entropy(logits, targets, reduction='none') * weight[targets]).mean()
                loss_value, norm = prior.step(model, optimizer, loss)
                updates += 1
                loss_sum += loss_value * len(chosen)
                stream.write(json.dumps({'epoch': epoch, 'step': updates, 'loss': loss_value, 'gradientNorm': norm,
                                        'snapshotPairIds': [train[i]['pairId'] for i in chosen]}) + '\n')
                stream.flush()
                if updates == 1 or updates % 30 == 0:
                    prior.log({'stage': 'weighted_RE', 'step': updates, 'loss': loss_value})
            validation = evaluate(model)
            score = rel.selection_score(validation['metrics'], 'all_class_macro')
            improved = ner.dev_checkpoint_improved(score, best)
            if improved:
                best, best_epoch, best_eval = score, epoch, validation
                model.save_pretrained(out / 'best_model', safe_serialization=True)
                tokenizer.save_pretrained(out / 'best_model')
            history.append({'epoch': epoch, 'step': updates, 'trainWeightedLoss': loss_sum/len(indices),
                            'dev': prior.clean_eval(validation), 'allClassMacroF1': score, 'checkpointImproved': improved})
            c.write_json(out / 'epochs.json', history)
            prior.log({'stage': 'weighted_RE_epoch', **history[-1]})
    del optimizer, model, logits, loss
    gc.collect()
    torch.cuda.empty_cache()
    tokenizer = rel.prepare_tokenizer(out / 'best_model')
    model = rel.load_relation_model(out / 'best_model', tokenizer, 'entity_markers').to(device).eval()
    recheck = evaluate(model)
    if recheck['predictions'] != best_eval['predictions']:
        raise ValueError('Weighted checkpoint reload mismatch')
    result = {'bestEpoch': best_epoch, 'steps': updates, 'bestDev': prior.clean_eval(recheck),
              'weights': weights, 'reloadPredictionsIdentical': True,
              'encoderChanged': not torch.equal(before, model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu())}
    c.write_json(out / 'result.json', result)
    c.write_jsonl(out / 'dev_predictions.jsonl', [{**r, 'referenceLabel': r['label'], 'predictedLabel': p,
                   'probabilities': dict(zip(rel.LABELS, probs))} for r, p, probs in zip(dev, recheck['predictions'], recheck['probabilities'])])
    del model
    gc.collect()
    torch.cuda.empty_cache()
    return result


def make_pairs(documents):
    return [{**{k: r[k] for k in ('arxivId', 'sampleId', 'text', 'textSha256')}, 'head': head, 'tail': tail}
            for r in documents for head in r['predictedEntities'] if head['label'] == 'METHOD'
            for tail in r['predictedEntities'] if tail['label'] in ('TASK', 'DATASET')]


def pipeline_contrast(data, previous, out, device, predictions):
    import torch
    refs = c.read_jsonl(data / 'dev_all_pairs.jsonl')
    result = {}
    for re_mode, checkpoint in [('original', previous / 're/best_model'), ('weighted', out / 'weighted_re/best_model')]:
        tokenizer = rel.prepare_tokenizer(checkpoint)
        model = rel.load_relation_model(checkpoint, tokenizer, 'entity_markers').to(device).eval().requires_grad_(False)
        if re_mode == 'weighted':
            reference_preds = prior.predict_pairs(model, tokenizer, refs, device)
            c.write_jsonl(out / 'weighted_reference_all_pairs_predictions.jsonl', reference_preds)
            c.write_json(out / 'weighted_reference_all_pairs_metrics.json', metrics.score(refs, reference_preds))
        for ner_mode in ('argmax', 'legal'):
            name = ner_mode + '_NER_' + re_mode + '_RE'
            if name == 'argmax_NER_original_RE':
                scored = c.read_jsonl(previous / 're/dev_pipeline_all_pairs_predictions.jsonl')
            else:
                scored = prior.predict_pairs(model, tokenizer, make_pairs(predictions['dev'][ner_mode]), device)
            score = metrics.score(refs, scored)
            score['candidatePairs'] = len(scored)
            score['rejectedPairs'] = sum(r['label'] == 'NO_RELATION' for r in scored)
            result[name] = score
            c.write_jsonl(out / (name + '_predictions.jsonl'), scored)
            prior.log({'stage': 'pipeline_cell', 'name': name, 'metrics': score})
        del model
        gc.collect()
        torch.cuda.empty_cache()
    c.write_json(out / 'pipeline_comparison.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--previous', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
    import torch
    data, previous, out = args.data.resolve(), args.previous.resolve(), args.output.resolve()
    old_contract = json.loads((previous / 'execution_contract.json').read_text(encoding='utf-8'))
    base = Path(old_contract['base'])
    for name, digest in old_contract['dataFilesSha256'].items():
        if c.file_sha256(data / name) != digest:
            raise ValueError('Input snapshot drift')
    prior.seed_all()
    train = c.read_jsonl(data / 'train_re_scored.jsonl')
    groups, plans = prior.freeze_groups(train)
    actual_plans = [{'epoch': i, 'pairIds': [train[k]['pairId'] for k in plan]} for i, plan in enumerate(plans, 1)]
    if actual_plans != json.loads((previous / 'sampling_plan.json').read_text(encoding='utf-8')):
        raise ValueError('Baseline sampling changed')
    counts = Counter(key[1] for key, _ in groups)
    weights = {label: len(groups)/(len(rel.LABELS)*counts[label]) for label in rel.LABELS}
    out.mkdir(parents=True, exist_ok=False)
    bound = {str(p): c.file_sha256(p) for p in [Path(__file__), Path(prior.__file__), Path(bio.__file__),
             Path(ner.__file__), Path(rel.__file__), Path(metrics.__file__), Path(c.__file__), c.CONFIG_PATH, c.SCHEMA_PATH,
             data / 'manifest.json', previous / 'execution_contract.json', previous / 'sampling_plan.json',
             previous / 'ner/best_model/model.safetensors', previous / 're/best_model/model.safetensors']}
    c.write_json(out / 'experiment_plan.json', {'seed': prior.SEED, 'NER': 'same frozen checkpoint; original argmax vs existing legal BIO Viterbi; no fitting',
        'RE': 'one 6-epoch fit from same pinned SciBERT; only training loss weighted by inverse evidence-group class frequency',
        'loss': 'mean(CE_per_example * class_weight); weights fixed before dev evaluation', 'classWeights': weights,
        'sampling': 'identical 251 group samples per epoch and order to original run', 'samplingClassCounts': dict(counts),
        'checkpointSelection': 'same adjudicated 3-class dev macro F1, earliest tie',
        'pipeline': 'predeclared full 2x2 decoder/loss comparison, fixed argmax label decision, no threshold tuning',
        'labelMutation': False, 'newHardNegatives': 0, 'NERretraining': False, 'testContentAccess': False,
        'productionPromotion': False, 'V1Comparison': 'deferred, no same-scope V1 claim',
        'baselineRun': str(previous), 'base': str(base), 'inputSha256': bound})
    c.write_json(out / 'sampling_plan.json', actual_plans)
    started = time.time()
    try:
        c.write_json(out / 'status.json', {'status': 'running'})
        n, predictions = ner_contrast(data, previous, out, torch.device('cuda'))
        r = weighted_fit(data, base, out / 'weighted_re', torch.device('cuda'), plans, weights)
        p = pipeline_contrast(data, previous, out, torch.device('cuda'), predictions)
        c.write_json(out / 'results.json', {'NER': n, 'weightedRE': r, 'pipeline': p,
                     'testContentRead': False, 'productionModified': False, 'labelsChanged': False})
        if any(c.file_sha256(Path(path)) != digest for path, digest in bound.items()):
            raise ValueError('Experiment inputs changed during execution')
        if any(c.file_sha256(data / name) != digest for name, digest in old_contract['dataFilesSha256'].items()):
            raise ValueError('Frozen snapshot changed')
        c.write_json(out / 'status.json', {'status': 'completed', 'elapsedSeconds': time.time()-started,
                                         'testContentRead': False, 'productionModified': False, 'snapshotUnchanged': True})
        c.write_json(out / 'artifacts_manifest.json', {'filesSha256': {p.relative_to(out).as_posix(): c.file_sha256(p)
                     for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'artifacts_manifest.json'}})
        prior.log({'completed': True, 'seconds': time.time()-started})
    except Exception:
        c.write_json(out / 'failure.json', {'traceback': traceback.format_exc()})
        c.write_json(out / 'status.json', {'status': 'failed', 'elapsedSeconds': time.time()-started})
        raise


if __name__ == '__main__':
    main()
