"""One authorized Train65/Dev20 SciBERT experiment; no test or production writes."""
from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import json
import os
import random
import sys
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import course_weak as c
import course_v2_textscope_metrics as partial_metrics
import train_course_ner as ner
import train_course_relation as re_model

SEED = 20261011
EPOCHS = 6
BATCH = 4
MAX_LENGTH = 512
TARGET = 'v2_abstract_dev_selected_AI_weak_reference_not_final_test'


def read(path):
    return c.read_jsonl(path)


def save(path, obj):
    c.write_json(path, obj)


def log(obj):
    print(json.dumps(obj, ensure_ascii=True, allow_nan=False), flush=True)


def seed_all():
    import numpy as np
    import torch
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(4)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False


def clean_eval(value):
    result = {k: v for k, v in value.items() if k not in ('predictions', 'probabilities')}
    def rename(item):
        if isinstance(item, dict):
            return {k: TARGET if k == 'evaluationTarget' else rename(v) for k, v in item.items()}
        if isinstance(item, list):
            return [rename(x) for x in item]
        return item
    return rename(result)


def freeze_groups(rows):
    """Explicit supportGroup is provenance, never an input feature or fact count."""
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        if row['label'] not in re_model.LABELS or row.get('masked'):
            raise ValueError('Unknown or masked training pair')
        if not row.get('supportGroup'):
            raise ValueError('Missing evidence group')
        groups[(row['arxivId'], row['label'], row['supportGroup'])].append(i)
    rng = random.Random(SEED)
    ordered = []
    for key in sorted(groups):
        indices = sorted(groups[key], key=lambda i: rows[i]['pairId'])
        rng.shuffle(indices)
        ordered.append((key, indices))
    plans = []
    for epoch in range(EPOCHS):
        indices = [members[epoch % len(members)] for _, members in ordered]
        random.Random(SEED + epoch).shuffle(indices)
        plans.append(indices)
    return ordered, plans


def step(model, optimizer, loss):
    import torch
    if not torch.isfinite(loss):
        raise ValueError('Nonfinite training loss')
    loss.backward()
    norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
    if not torch.isfinite(norm):
        raise ValueError('Nonfinite gradient')
    optimizer.step()
    return float(loss.detach()), float(norm)


def fit_ner(data, base, output, device):
    import torch
    from transformers import BertTokenizerFast, BertForTokenClassification, DataCollatorForTokenClassification
    seed_all()
    output.mkdir()
    train, dev = read(data / 'train_ner.jsonl'), read(data / 'dev_ner.jsonl')
    tokenizer = BertTokenizerFast.from_pretrained(base, local_files_only=True)
    encoded = {name: [ner.encode_row(tokenizer, r, MAX_LENGTH) for r in rows]
               for name, rows in [('train', train), ('dev', dev)]}
    model, info = BertForTokenClassification.from_pretrained(
        base, local_files_only=True, weights_only=True, num_labels=len(c.CONFIG['bioLabels']),
        id2label=dict(enumerate(c.CONFIG['bioLabels'])),
        label2id={x: i for i, x in enumerate(c.CONFIG['bioLabels'])},
        attn_implementation='eager', output_loading_info=True)
    if (set(info['missing_keys']) != {'classifier.weight', 'classifier.bias'}
            or info['mismatched_keys'] or info['error_msgs']
            or any(not k.startswith('cls.') and k not in ('bert.pooler.dense.weight', 'bert.pooler.dense.bias')
                   for k in info['unexpected_keys'])):
        raise ValueError('Unexpected NER initialization keys: ' + str(info))
    model.to(device)
    head_before = model.classifier.weight.detach().cpu().clone()
    encoder_before = model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu().clone()
    collator = DataCollatorForTokenClassification(tokenizer, padding=True, return_tensors='pt')
    evaluate = lambda m: ner.evaluate_model(m, dev, encoded['dev'], TARGET,
                                           collator=collator, device=device, batch_size=BATCH)
    baseline = ner.score_rows(dev, [ner.dictionary_predict(r['text'], ner.make_dictionary(train)) for r in dev],
                              evaluation_target=TARGET)
    save(output / 'baseline.json', baseline)
    initial = evaluate(model)
    save(output / 'initial_dev.json', clean_eval(initial))
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5, weight_decay=0.01)
    best_score, best_eval, best_epoch = None, None, None
    history, updates = [], 0
    with (output / 'steps.jsonl').open('x', encoding='utf-8') as stream:
        for epoch in range(1, EPOCHS + 1):
            indices = list(range(len(train)))
            random.Random(SEED + epoch - 1).shuffle(indices)
            epoch_loss, tokens = 0.0, 0
            for start in range(0, len(indices), BATCH):
                chosen = indices[start:start+BATCH]
                batch = {k: v.to(device) for k, v in collator([encoded['train'][i]['features'] for i in chosen]).items()}
                model.train()
                optimizer.zero_grad(set_to_none=True)
                loss, norm = step(model, optimizer, model(**batch).loss)
                n = int((batch['labels'] != -100).sum())
                tokens += n
                epoch_loss += loss * n
                updates += 1
                record = {'epoch': epoch, 'step': updates, 'loss': loss, 'gradientNorm': norm,
                          'sampleIds': [train[i]['sampleId'] for i in chosen]}
                stream.write(json.dumps(record, allow_nan=False) + '\n')
                stream.flush()
                if updates == 1 or updates % 10 == 0:
                    log({'stage': 'NER', 'step': updates, 'loss': loss})
            validation = evaluate(model)
            value = validation['metrics']['micro']['f1']
            improved = ner.dev_checkpoint_improved(value, best_score)
            if improved:
                best_score, best_eval, best_epoch = value, validation, epoch
                model.save_pretrained(output / 'best_model', safe_serialization=True)
                tokenizer.save_pretrained(output / 'best_model')
            record = {'epoch': epoch, 'step': updates, 'trainLoss': epoch_loss/tokens,
                      'dev': clean_eval(validation), 'checkpointImproved': improved}
            history.append(record)
            save(output / 'epochs.json', history)
            log({'stage': 'NER', **record})
    del optimizer, model, batch
    gc.collect()
    torch.cuda.empty_cache()
    restored_tokenizer = BertTokenizerFast.from_pretrained(output / 'best_model', local_files_only=True)
    restored = BertForTokenClassification.from_pretrained(output / 'best_model', local_files_only=True,
                              use_safetensors=True, attn_implementation='eager').to(device)
    reload_encoded = [ner.encode_row(restored_tokenizer, r, MAX_LENGTH) for r in dev]
    recheck = ner.evaluate_model(restored, dev, reload_encoded, TARGET,
                                 collator=DataCollatorForTokenClassification(restored_tokenizer, return_tensors='pt'),
                                 device=device, batch_size=BATCH)
    if recheck['predictions'] != best_eval['predictions'] or reload_encoded != encoded['dev']:
        raise ValueError('NER checkpoint reload mismatch')
    result = {'bestEpoch': best_epoch, 'steps': updates, 'selection': 'strict_entity_micro_F1_earliest_tie',
              'bestDev': clean_eval(recheck), 'baseline': baseline, 'reloadPredictionsIdentical': True,
              'classifierChanged': not torch.equal(head_before, restored.classifier.weight.detach().cpu()),
              'encoderChanged': not torch.equal(encoder_before, restored.bert.encoder.layer[0].attention.self.query.weight.detach().cpu())}
    predictions = [{**{k: r[k] for k in ('arxivId', 'sampleId', 'text', 'textSha256')},
                    'referenceEntities': r['entities'], 'predictedEntities': p}
                   for r, p in zip(dev, recheck['predictions'])]
    c.write_jsonl(output / 'dev_predictions.jsonl', predictions)
    save(output / 'result.json', result)
    del restored
    gc.collect()
    torch.cuda.empty_cache()
    return result, predictions


def predict_pairs(model, tokenizer, rows, device):
    import torch
    from transformers import DataCollatorWithPadding
    collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
    predictions = []
    model.eval()
    with torch.no_grad():
        for start in range(0, len(rows), BATCH):
            part = rows[start:start+BATCH]
            features = [re_model.encode_pair(tokenizer, {k: v for k, v in r.items() if k != 'label'}, MAX_LENGTH) for r in part]
            logits, _ = re_model.forward_batch(model, features, collator, device)
            labels, probs = logits.argmax(-1).cpu().tolist(), logits.softmax(-1).cpu().tolist()
            predictions.extend({**r, 'referenceLabel': r.get('label'), 'label': re_model.LABELS[i],
                                'probabilities': dict(zip(re_model.LABELS, prob))}
                               for r, i, prob in zip(part, labels, probs))
    return predictions


def fit_re(data, base, output, device, groups, plans, ner_predictions):
    import torch
    from transformers import DataCollatorWithPadding
    seed_all()
    output.mkdir()
    train, dev = read(data / 'train_re_scored.jsonl'), read(data / 'dev_re_scored.jsonl')
    tokenizer = re_model.prepare_tokenizer(base)
    encoded = {name: [re_model.encode_pair(tokenizer, r, MAX_LENGTH) for r in rows]
               for name, rows in [('train', train), ('dev', dev)]}
    model = re_model.load_relation_model(base, tokenizer, 'entity_markers', initialize_from_base=True).to(device)
    before_head = model.classifier.weight.detach().cpu().clone()
    before_encoder = model.bert.encoder.layer[0].attention.self.query.weight.detach().cpu().clone()
    collator = DataCollatorWithPadding(tokenizer, return_tensors='pt')
    evaluate = lambda m: re_model.evaluate_model(m, dev, encoded['dev'], collator, device, BATCH)
    baseline_types = re_model.type_majority([train[i] for i in plans[0]])
    baseline = clean_eval({'metrics': re_model.score_relations(dev, [baseline_types[r['tail']['label']] for r in dev])})
    save(output / 'baseline.json', baseline)
    save(output / 'initial_dev.json', clean_eval(evaluate(model)))
    optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5, weight_decay=0.01)
    best_score, best_eval, best_epoch = None, None, None
    history, updates, seen = [], 0, set()
    with (output / 'steps.jsonl').open('x', encoding='utf-8') as stream:
        for epoch, indices in enumerate(plans, 1):
            total_loss = 0.0
            for start in range(0, len(indices), BATCH):
                chosen = indices[start:start+BATCH]
                part = [encoded['train'][i] for i in chosen]
                model.train()
                optimizer.zero_grad(set_to_none=True)
                logits, targets = re_model.forward_batch(model, part, collator, device)
                loss, norm = step(model, optimizer, torch.nn.functional.cross_entropy(logits, targets))
                total_loss += loss * len(part)
                updates += 1
                seen.update(chosen)
                record = {'epoch': epoch, 'step': updates, 'loss': loss, 'gradientNorm': norm,
                          'snapshotPairIds': [train[i]['pairId'] for i in chosen]}
                stream.write(json.dumps(record, allow_nan=False) + '\n')
                stream.flush()
                if updates == 1 or updates % 20 == 0:
                    log({'stage': 'RE', 'step': updates, 'loss': loss})
            validation = evaluate(model)
            value = re_model.selection_score(validation['metrics'], 'all_class_macro')
            improved = ner.dev_checkpoint_improved(value, best_score)
            if improved:
                best_score, best_eval, best_epoch = value, validation, epoch
                model.save_pretrained(output / 'best_model', safe_serialization=True)
                tokenizer.save_pretrained(output / 'best_model')
            record = {'epoch': epoch, 'step': updates, 'trainLoss': total_loss/len(indices),
                      'sampledPairs': len(indices), 'sampledClassCounts': dict(Counter(train[i]['label'] for i in indices)),
                      'distinctPairsSeen': len(seen), 'allClassMacroF1': value,
                      'dev': clean_eval(validation), 'checkpointImproved': improved}
            history.append(record)
            save(output / 'epochs.json', history)
            log({'stage': 'RE', **record})
    del optimizer, model, logits
    gc.collect()
    torch.cuda.empty_cache()
    tokenizer = re_model.prepare_tokenizer(output / 'best_model')
    restored = re_model.load_relation_model(output / 'best_model', tokenizer, 'entity_markers').to(device)
    reload_encoded = [re_model.encode_pair(tokenizer, r, MAX_LENGTH) for r in dev]
    recheck = re_model.evaluate_model(restored, dev, reload_encoded, collator, device, BATCH)
    if recheck['predictions'] != best_eval['predictions'] or reload_encoded != encoded['dev']:
        raise ValueError('RE checkpoint reload mismatch')
    predictions = [{**{k: r[k] for k in ('arxivId', 'sampleId', 'head', 'tail', 'evidence', 'text', 'pairId')},
                    'referenceLabel': r['label'], 'predictedLabel': p,
                    'probabilities': dict(zip(re_model.LABELS, probs))}
                   for r, p, probs in zip(dev, recheck['predictions'], recheck['probabilities'])]
    c.write_jsonl(output / 'dev_predictions.jsonl', predictions)
    c.write_jsonl(output / 'dev_errors.jsonl', [p for p in predictions if p['referenceLabel'] != p['predictedLabel']])
    all_dev = read(data / 'dev_all_pairs.jsonl')
    reference_entity_predictions = predict_pairs(restored, tokenizer, all_dev, device)
    c.write_jsonl(output / 'dev_reference_entity_all_pairs_predictions.jsonl', reference_entity_predictions)
    pipeline_pairs = []
    for r in ner_predictions:
        for h in r['predictedEntities']:
            if h['label'] != 'METHOD':
                continue
            for t in r['predictedEntities']:
                if t['label'] in ('TASK', 'DATASET'):
                    pipeline_pairs.append({**{k: r[k] for k in ('arxivId', 'sampleId', 'text', 'textSha256')},
                                           'head': h, 'tail': t})
    pipeline = predict_pairs(restored, tokenizer, pipeline_pairs, device)
    c.write_jsonl(output / 'dev_pipeline_all_pairs_predictions.jsonl', pipeline)
    scope = partial_metrics.score(all_dev, pipeline)
    save(output / 'dev_pipeline_scope_metrics.json', scope)
    result = {'bestEpoch': best_epoch, 'steps': updates, 'selection': 'adjudicated_all_3_class_macro_F1_earliest_tie',
              'bestDev': clean_eval(recheck), 'baseline': baseline, 'reloadPredictionsIdentical': True,
              'classifierChanged': not torch.equal(before_head, restored.classifier.weight.detach().cpu()),
              'encoderChanged': not torch.equal(before_encoder, restored.bert.encoder.layer[0].attention.self.query.weight.detach().cpu()),
              'trainingPoolPairs': len(train), 'evidenceLabelGroups': len(groups), 'distinctPairsSeen': len(seen),
              'referenceEntityAllPairsScope': partial_metrics.score(all_dev, reference_entity_predictions),
              'pipelineScope': scope}
    save(output / 'result.json', result)
    del restored
    gc.collect()
    torch.cuda.empty_cache()
    return result, predictions, pipeline


def errors_and_report(data, output, ner_result, ner_predictions, re_result, re_predictions, pipeline):
    entity_errors = []
    for r in ner_predictions:
        key = lambda e: (e['start'], e['end'], e['label'])
        gold = {key(e): e for e in r['referenceEntities']}
        pred = {key(e): e for e in r['predictedEntities']}
        for kind, source, other in [('FN', gold, pred), ('FP', pred, gold)]:
            for k in sorted(source.keys() - other.keys()):
                e = source[k]
                overlaps = [v for v in other.values() if max(e['start'], v['start']) < min(e['end'], v['end'])]
                category = ('boundary' if any(v['label'] == e['label'] for v in overlaps)
                            else 'type_or_type_and_boundary' if overlaps else 'missing' if kind == 'FN' else 'extra')
                entity_errors.append({'arxivId': r['arxivId'], 'kind': kind, 'category': category,
                                      'entity': e, 'overlaps': overlaps, 'text': r['text']})
    c.write_jsonl(output / 'ner_error_spans.jsonl', entity_errors)
    refs = read(data / 'dev_all_pairs.jsonl')
    gold = {(partial_metrics.endpoint_key(r), r['label']): r for r in refs if r['label'] in partial_metrics.POSITIVE}
    ref_keys = {partial_metrics.endpoint_key(r): r for r in refs}
    predicted = {(partial_metrics.endpoint_key(r), r['label']): r for r in pipeline if r['label'] in partial_metrics.POSITIVE}
    ner_spans = {r['arxivId']: {(e['start'], e['end'], e['label']) for e in r['predictedEntities']} for r in ner_predictions}
    rows = []
    for k in gold.keys() - predicted.keys():
        r = gold[k]
        both = all((r[which]['start'], r[which]['end'], r[which]['label']) in ner_spans[r['arxivId']] for which in ('head', 'tail'))
        rows.append({'kind': 'FN', 'category': 'RE_with_both_endpoints_recovered' if both else 'NER_endpoint_missing_or_wrong', **r})
    for k in predicted.keys() - gold.keys():
        r = predicted[k]
        ref = ref_keys.get(k[0])
        category = ('masked_unknown_not_error' if ref and ref['label'] == 'UNRESOLVED'
                    else 'known_negative' if ref and ref['label'] == 'NO_RELATION'
                    else 'wrong_relation' if ref else 'nonreference_endpoint')
        rows.append({'kind': 'MASKED' if category == 'masked_unknown_not_error' else 'FP',
                     'category': category, **r})
    rows.sort(key=lambda r: (r['arxivId'], r['kind'], r['head']['start'], r['tail']['start']))
    c.write_jsonl(output / 'pipeline_error_attribution.jsonl', rows)
    fields = ['arxivId', 'kind', 'category', 'label', 'headText', 'tailText', 'headStart', 'tailStart', 'text']
    with (output / 'pipeline_error_review.csv').open('x', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({**{k: r[k] for k in ('arxivId', 'kind', 'category', 'label', 'text')},
                         'headText': r['head']['text'], 'tailText': r['tail']['text'],
                         'headStart': r['head']['start'], 'tailStart': r['tail']['start']} for r in rows)
    summary = {'NER': ner_result, 'RE': re_result,
               'nerErrorSpanCategories': dict(Counter(r['kind'] + ':' + r['category'] for r in entity_errors)),
               'pipelineErrorCategories': dict(Counter(r['kind'] + ':' + r['category'] for r in rows)),
               'humanGold': False, 'testEvaluated': False, 'productionModified': False,
               'notice': 'Dev-selected exploratory AI-reference scores; RE unknowns masked, not complete pipeline quality.'}
    save(output / 'results.json', summary)
    def pct(value):
        return 'N/A' if value is None else f'{value*100:.2f}%'
    lines = ['# V2 Train65/Dev20 SciBERT 单次探索实验', '',
             '真实训练；seed=20261011；各 6 轮；未读取 test20 正文，未替换生产模型。', '',
             '全部成绩是固定 dev 上相对于 AI 弱参考标签的匹配，不是独立测试成绩或人工金标准。', '',
             '## 实验配置', '',
             '- NER：65 篇、941 个实体；AdamW 5e-5，batch=4，FP32，严格 BIO 解码。',
             '- RE：674 对作为训练池，排除 2693 个未决对；每轮 251 个论文/标签/证据组各选一对，轮换提及。',
             f'- 6 轮累计使用 {re_result["distinctPairsSeen"]} 个不同训练对；组不等于独立事实；未对稀有类过采样。',
             '- RE：原有 entity_markers 架构，AdamW 2e-5；原有类型掩码；无额外类别权重。',
             '- NER 按 dev 严格 micro F1 选点；RE 按已裁决 dev 三类别 macro F1 选点；平分取最早轮。',
             '- 仅输入原摘要与实体标记，不输入证据、角色、关系标签或测试文本；最长 512 token，禁止截断。', '',
             '## Dev 指标', '', '| 项目/类别 | Precision | Recall | F1 | 参考数 |', '|---|---:|---:|---:|---:|']
    n = ner_result['bestDev']['metrics']
    for label, m in [('NER overall', n['micro']), *n['perClass'].items()]:
        lines.append(f'| {label} | {pct(m["precision"])} | {pct(m["recall"])} | {pct(m["f1"])} | {m["reference"]} |')
    r = re_result['bestDev']['metrics']
    for label, m in [('RE positive micro (reference entities)', r['positiveMicro']), *r['perClass'].items()]:
        lines.append(f'| {label} | {pct(m["precision"])} | {pct(m["recall"])} | {pct(m["f1"])} | {m["reference"]} |')
    p = re_result['pipelineScope']
    m = p['conditionalPositiveMetrics']
    lines += ['', f'NER 选择第 {ner_result["bestEpoch"]} 轮（{ner_result["steps"]} 次更新）；RE 选择第 {re_result["bestEpoch"]} 轮（{re_result["steps"]} 次更新）。',
              '', f'模型抽实体→抽关系的已裁决范围条件指标：P={pct(m["precision"])}, R={pct(m["recall"])}, F1={pct(m["f1"])}。',
              f'关系参考覆盖 {361}/974={pct(p["referencePairCoverage"])}；613 对未决；预测正边 {p["allPositivePredictionCount"]}，其中 {p["maskedPredictionCount"]} 条精确匹配未决对被掩码。',
              '**完整端到端 F1 未计算（null），不能把条件成绩当成全部关系准确率。**', '',
              '## 实际错误与边界', '',
              'NER 错误类别（FP/FN 跨度记录，并非互斥独立原因）：', '',
              '```json', json.dumps(summary['nerErrorSpanCategories'], ensure_ascii=False, indent=2), '```', '',
              'Pipeline 错误归因（相对于 AI 标签；未知项不作为误报）：', '',
              '```json', json.dumps(summary['pipelineErrorCategories'], ensure_ascii=False, indent=2), '```', '',
              '逐条原文、参考/预测实体、关系、概率（未校准）、证据和错误位置见 JSONL 与 CSV。',
              '两套最佳权重已保存并重新载入，dev 预测一致；classifier/encoder 实际变化见 result.json。',
              '证据组采样只在训练使用；dev 为提及级，重复提及相关，分数不能视为独立事实正确率。',
              'DATASET 23 个参考实体；EVALUATED_ON 52 对来自 6 篇论文，负例 48 对来自 14 篇。',
              '与旧题名测试集输入/标注任务不同，不能直接声称相对旧测试提高。',
              '固定种子只保证此设备/软件路径可复现；单次种子不代表多种子稳定性或统计显著性。', '',
              '## 收尾', '', '本次训练结束；不自动追加训练、改标签、解封测试或上线。下一步由实际错误与用户复核决定。']
    (output / 'RESULTS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
    import torch
    data, base, output = args.data.resolve(), args.base.resolve(), args.output.resolve()
    manifest = json.loads((data / 'manifest.json').read_text(encoding='utf-8'))
    # Only this explicit frozen folder, base, and train/dev code paths are read.
    frozen_hashes = {name: c.file_sha256(data / name) for name in manifest['files']}
    if frozen_hashes != manifest['files']:
        raise ValueError('Frozen dataset changed')
    ner.verify_files(base)
    if not torch.cuda.is_available():
        raise ValueError('CUDA unavailable; no silent CPU fallback')
    train = read(data / 'train_re_scored.jsonl')
    if len(train) != 674 or len(read(data / 'train_ner.jsonl')) != 65 or len(read(data / 'dev_ner.jsonl')) != 20:
        raise ValueError('Unexpected authorized cohort counts')
    groups, plans = freeze_groups(train)
    output.mkdir(parents=True, exist_ok=False)
    started = time.time()
    contract = {'authorization': 'User explicitly authorized one fixed-seed exploratory NER+RE run on this frozen snapshot.',
                'createdUTC': datetime.now(timezone.utc).isoformat(), 'data': str(data),
                'dataManifestSha256': c.file_sha256(data / 'manifest.json'), 'dataFilesSha256': frozen_hashes,
                'base': str(base), 'baseManifestSha256': c.file_sha256(base / 'manifest.json'),
                'seed': SEED, 'epochs': EPOCHS, 'batch': BATCH, 'maxLength': MAX_LENGTH,
                'NERlearningRate': 5e-5, 'RElearningRate': 2e-5, 'weightDecay': 0.01, 'gradientClip': 1.0,
                'optimizer': 'AdamW; constant LR; no extra class weighting; eager FP32',
                'checkpointSelection': {'NER': 'strict_entity_micro_F1', 'RE': 'adjudicated_all_3_class_macro_F1'},
                'sampling': 'one per (arxivId,label,supportGroup) per epoch, fixed shuffled within-group rotation',
                'admittedREpairs': len(train), 'evidenceLabelGroups': len(groups),
                'groupClassCounts': dict(Counter(key[1] for key, _ in groups)),
                'groupSizeDistribution': dict(Counter(len(indices) for _, indices in groups)),
                'testBodyRead': False, 'testEvaluated': False, 'productionPromotionAuthorized': False,
                'humanGold': False, 'unknownReferencePairsMasked': True,
                'gpu': torch.cuda.get_device_name(0), 'cuda': torch.version.cuda,
                'versions': {name: version(name) for name in ('torch', 'transformers', 'numpy', 'safetensors')},
                'codeSha256': {str(Path(x).resolve()): c.file_sha256(Path(x)) for x in
                    (__file__, ner.__file__, re_model.__file__, partial_metrics.__file__, c.__file__,
                     str(Path(__file__).with_name('course_relation_model.py')))},
                'reproducibility': 'Strict deterministic eager FP32, fixed seeds; no cross-device or multi-seed claim.'}
    save(output / 'execution_contract.json', contract)
    save(output / 'sampling_plan.json', [{'epoch': e, 'pairIds': [train[i]['pairId'] for i in indices]} for e, indices in enumerate(plans, 1)])
    def status(stage):
        save(output / 'status.json', {'status': stage, 'elapsedSeconds': time.time()-started,
                                     'testBodyRead': False, 'productionModified': False})
        log({'stage': stage, 'elapsedSeconds': time.time()-started})
    try:
        status('training_NER')
        n, npred = fit_ner(data, base, output / 'ner', torch.device('cuda'))
        status('training_RE')
        r, rpred, ppred = fit_re(data, base, output / 're', torch.device('cuda'), groups, plans, npred)
        status('saving_results')
        errors_and_report(data, output, n, npred, r, rpred, ppred)
        if {name: c.file_sha256(data / name) for name in frozen_hashes} != frozen_hashes:
            raise ValueError('Frozen snapshot changed during experiment')
        if c.file_sha256(data / 'manifest.json') != contract['dataManifestSha256']:
            raise ValueError('Frozen manifest changed during experiment')
        save(output / 'artifacts_manifest.json', {'filesSha256': {p.relative_to(output).as_posix(): c.file_sha256(p)
               for p in sorted(output.rglob('*')) if p.is_file() and p.name not in ('status.json', 'artifacts_manifest.json')},
               'datasetUnchanged': True, 'testBodyRead': False, 'productionModified': False})
        status('completed')
    except Exception:
        save(output / 'failure.json', {'traceback': traceback.format_exc(), 'elapsedSeconds': time.time()-started})
        status('failed')
        raise


if __name__ == '__main__':
    main()
