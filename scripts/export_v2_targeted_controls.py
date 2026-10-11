"""Review the bounded contrasts and two train-only candidate omission corrections."""
import argparse
import copy
import html
import json
import zipfile
from pathlib import Path

import course_weak as c
import course_v2_textscope_metrics as metrics
from package_v2_textscope_once import spans


def candidate_revision(data, out):
    rows = c.read_jsonl(data / 'train_ner.jsonl')
    originals = c.read_jsonl(data / 'train_all_pairs.jsonl')
    lookup = {r['arxivId']: r for r in rows}
    patches = [
        {'arxivId': '1606.05250', 'text': 'answer the questions',
         'reason': 'The benchmark description explicitly names answering questions as an activity. Under the current broad task scope this is a candidate missing TASK mention; no method attribution is inherited.'},
        {'arxivId': '2506.16934', 'text': 'imaging', 'start': 97,
         'reason': 'The first sentence explicitly says the PET method is used for imaging. This is an expressed purpose, separate from the later multi-tracer PET imaging mention.'}
    ]
    for patch in patches:
        row = lookup[patch['arxivId']]
        patch['entityId'] = 'e' + str(1 + max(int(e['entityId'][1:]) for e in row['entities']))
        start = patch.get('start', row['text'].index(patch['text']))
        end = start + len(patch['text'])
        assert row['text'][start:end] == patch['text']
        assert not any(max(start, e['start']) < min(end, e['end']) for e in row['entities'])
        entity = {'entityId': patch['entityId'], 'text': patch['text'], 'label': 'TASK', 'start': start, 'end': end,
                  'provenance': 'AI_train_source_read_candidate_not_yet_accepted'}
        row['entities'].append(entity)
        row['entities'].sort(key=lambda e: e['start'])
        patch.update(start=start, end=end, label='TASK', textSha256=row['textSha256'],
                     evidence=row['text'], status='candidate_for_review', usedInExperiment=False)
    old = {metrics.endpoint_key(r): r for r in originals}
    rebuilt, added = [], []
    for row in rows:
        row.update(annotationStatus='candidate_train_revision_pending_review', trainingAuthorized=False)
        for head in row['entities']:
            if head['label'] != 'METHOD':
                continue
            for tail in row['entities']:
                if tail['label'] not in ('TASK', 'DATASET'):
                    continue
                bare = {**{k: row[k] for k in ('arxivId', 'sampleId', 'publicationId', 'groupId', 'sourceURL', 'text', 'textSha256')},
                        'split': 'train', 'textKind': 'abstract', 'head': head, 'tail': tail}
                key = metrics.endpoint_key(bare)
                if key in old:
                    pair = copy.deepcopy(old[key])
                else:
                    pair = {**bare, 'pairId': row['sampleId'] + ':' + head['entityId'] + ':' + tail['entityId'],
                            'label': 'UNRESOLVED', 'masked': True, 'adjudicated': False, 'trainingAuthorized': False,
                            'scopeVersion': 'whole_abstract_expressed_relation_v2', 'annotationStatus': 'new_candidate_unresolved',
                            'reason': 'New pair after candidate entity addition; no automatic negative or positive assignment.'}
                    added.append(pair)
                rebuilt.append(pair)
    assert len({metrics.endpoint_key(r) for r in rebuilt}) == len(rebuilt)
    assert set(old).issubset({metrics.endpoint_key(r) for r in rebuilt})
    c.write_jsonl(out / 'candidate_train_ner.jsonl', rows)
    c.write_jsonl(out / 'candidate_train_all_pairs.jsonl', rebuilt)
    c.write_jsonl(out / 'new_unresolved_train_pairs.jsonl', added)
    c.write_json(out / 'train_revision_candidates.json', {'status': 'candidate_pending_user_review', 'patches': patches,
                 'entities': sum(len(r['entities']) for r in rows), 'pairs': len(rebuilt), 'newUnknownPairs': len(added),
                 'adjudicatedPairsRemain': sum(r['label'] != 'UNRESOLVED' for r in rebuilt),
                 'newHardNegatives': 0, 'trainedOnThisRevision': False,
                 'otherFinding': 'entity and relation encoders is a coordination/scope ambiguity; no automatic METHOD addition.'})
    return patches, len(added)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', type=Path, required=True)
    ap.add_argument('--previous', type=Path, required=True)
    ap.add_argument('--data', type=Path, required=True)
    ap.add_argument('--zip', type=Path, required=True)
    a = ap.parse_args()
    out, previous, data = a.run.resolve(), a.previous.resolve(), a.data.resolve()
    assert json.loads((out / 'status.json').read_text(encoding='utf-8'))['status'] == 'completed'
    baseline = json.loads((previous / 'results.json').read_text(encoding='utf-8'))
    result = json.loads((out / 'results.json').read_text(encoding='utf-8'))
    patches, added_pairs = candidate_revision(data, out)
    pct = lambda x: 'N/A' if x is None else f'{x*100:.2f}%'
    n = result['NER']['dev']['metrics']
    re0, re1 = baseline['RE']['bestDev']['metrics'], result['weightedRE']['bestDev']['metrics']
    macro = lambda m: sum(x['f1'] for x in m['perClass'].values())/3
    lines = ['# V2 定向对照：实际结果', '',
        '完成冻结 NER 权重的解码对照、一次 RE 加权训练，以及预先指定的 2×2 Pipeline 对照。test20 正文未读取，生产未替换。', '',
        '本轮未重训 NER、未改实验用标签、未新增困难负例。另导出两项训练侧补标候选供审核，未用于本次结果。', '',
        '## NER', '', '| 指标 | 原 argmax | 合法 BIO |', '|---|---:|---:|']
    for name in ['micro', 'METHOD', 'TASK', 'DATASET']:
        get = lambda mode: n[mode]['micro'] if name == 'micro' else n[mode]['perClass'][name]
        lines.append(f'| {name} F1 | {pct(get("argmax")["f1"])} | {pct(get("legal")["f1"])} |')
    lines += ['| 非法 BIO 转移 | 177 | 0 |', '',
        '使用项目已有的最大得分合法 BIO 路径解码，没有根据 dev 实体答案编写修正规则。它只保证序列合法，不保证完整词边界或语义正确。',
        f'训练集原解码 F1={pct(result["NER"]["train"]["metrics"]["argmax"]["micro"]["f1"])}，这是训练内拟合结果。训练 65 篇和 dev 20 篇参考标签的 BIO 编码/还原均通过。',
        '训练与 dev 的差距支持当前泛化不足的判断；不能仅凭这一实验将原因全部归于标签噪声或样本数。', '',
        '## RE', '', '| 指标 | 原损失 | 加权损失 |', '|---|---:|---:|',
        f'| 三类别 macro F1 | {pct(macro(re0))} | {pct(macro(re1))} |']
    for label in ('USED_FOR', 'EVALUATED_ON', 'NO_RELATION'):
        for metric in ('precision', 'recall', 'f1'):
            lines.append(f'| {label} {metric} | {pct(re0["perClass"][label][metric])} | {pct(re1["perClass"][label][metric])} |')
    lines += ['', f'加权组固定训练 6 轮/378 步，按相同三类别 macro F1 规则选择第 {result["weightedRE"]["bestEpoch"]} 轮，重载预测一致。',
        '相同 seed=20261011、SciBERT 基座、学习率、批大小和采样顺序。权重来自训练组频次：USED_FOR 0.42687、EVALUATED_ON 2.88506、NO_RELATION 3.21795。',
        '每个样本交叉熵乘固定类别权重后取批均值。没有同时改变采样、补负例或调整置信度阈值。', '',
        '## Pipeline：同一 dev 的条件范围', '',
        '| 组合 | P | R | 条件 F1 | 候选对 | 输出正边 | 拒绝对 | 未决匹配掩码 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name, p in result['pipeline'].items():
        m = p['conditionalPositiveMetrics']
        lines.append(f'| {name} | {pct(m["precision"])} | {pct(m["recall"])} | {pct(m["f1"])} | {p["candidatePairs"]} | {p["allPositivePredictionCount"]} | {p["rejectedPairs"]} | {p["maskedPredictionCount"]} |')
    lines += ['', '关系参考覆盖率仍为 361/974=37.06%；613 对未决，完整端到端 F1 保持 null。精确匹配未决对的预测被掩码；非参考实体端点按严格 AI 参考跨度计错。',
        '所有分数都是已暴露 dev 的 AI 参考匹配，不能当作独立测试或与 V1 旧题名成绩直接比较。四个组合全部报告，未选最高数冒充正式成绩。', '',
        '## 训练侧定向复核', '',
        '原训练解码共有 28 条 FP/FN 跨度记录；大多是模型未学好的边界，不能反过来把标签改成模型预测。',
        '- 保留 `offline knowledge base construction` 的 offline 修饰语。',
        '- 保留 `fine-tune the model\'s responses` 整体跨度，拒绝拆成 fine- 与 tune…。',
        '- 保留 `identifies predictive features`，不把后面的 that 包入实体。',
        '- `cognitive` 出自 cognitive science 的片段，不能据此补成 METHOD。',
        '- SQuAD 的 `answer the questions` 与 PET 的 `imaging` 导出为 TASK 补标候选。',
        f'候选副本包含 65 篇、943 个实体；重建新增 {added_pairs} 个合法实体对，全部先标 UNRESOLVED。原 674 对已裁决标签保留。本轮训练没有使用该候选副本。',
        '- `entity and relation encoders` 涉及并列方法粒度，留待定向裁决，未强行补标。', '',
        '## 下一步边界', '',
        '合法 BIO 消除非法转移，但无法单独解决泛化与误配对；类别加权的实际作用见上表，不能假定它已经解决负例问题。',
        '后续数据工作应集中于训练侧有原文依据的困难负例和 TASK 表述覆盖。不能将 dev 错误答案直接回流训练，也不能批量把 UNRESOLVED 改成 NO_RELATION。',
        '本轮结果和权重封存。V1 同口径比较、NER 迁移初始化和 LLM 证据核验未在此轮执行。',
        '原始 ner_decoder_result 的 train 指标内部沿用通用 evaluationTarget 字符串；其外层 evaluationScope 明确为 in_sample_training_label_diagnostic，本报告按训练内诊断解释。']
    report = '\n'.join(lines) + '\n'
    (out / 'REVIEW.md').write_text(report, encoding='utf-8')
    sections = []
    for mode in ('argmax', 'legal'):
        for row in c.read_jsonl(out / f'dev_ner_{mode}_predictions.jsonl'):
            sections.append(f'<details><summary>{html.escape(row["arxivId"])} / {mode}</summary><h4>AI 参考实体</h4><p>'
                            + spans(row['text'], row['referenceEntities']) + '</p><h4>模型实体</h4><p>'
                            + spans(row['text'], row['predictedEntities']) + '</p></details>')
    page = ('<!doctype html><meta charset="utf-8"><title>V2 定向对照审核</title><style>'
            'body{font:16px/1.7 system-ui;max-width:1300px;margin:30px auto;padding:0 20px}'
            'pre{white-space:pre-wrap;background:#f4f6f8;padding:18px}details{padding:14px;border:1px solid #ccc;margin:12px 0}'
            '.METHOD{background:#bbdcff}.TASK{background:#cbefce}.DATASET{background:#ffdda9}</style>'
            '<h1>V2 定向对照审核</h1><pre>' + html.escape(report) + '</pre>' + ''.join(sections))
    (out / 'review.html').write_text(page, encoding='utf-8')
    sources = out / 'sources'
    sources.mkdir()
    plan = json.loads((out / 'experiment_plan.json').read_text(encoding='utf-8'))
    for path, digest in plan['inputSha256'].items():
        source = Path(path)
        if source.suffix == '.py':
            assert c.file_sha256(source) == digest
            (sources / source.name).write_bytes(source.read_bytes())
    (sources / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    files = [(p, p.relative_to(out).as_posix()) for p in sorted(out.rglob('*')) if p.is_file() and p.suffix != '.safetensors']
    with zipfile.ZipFile(a.zip, 'x', zipfile.ZIP_DEFLATED) as z:
        for p, name in files:
            z.write(p, name)
        z.writestr('PACKAGE_SHA256.json', json.dumps({name: c.file_sha256(p) for p, name in files}, indent=2))
        z.writestr('PACKAGE_NOTE.txt', 'Contains comparison results and untrained candidate train revision; no large weights or test20 text. Weights remain in weighted_re/best_model locally. Baseline checkpoints remain in the previous run.\n')
    print(json.dumps({'zip': str(a.zip.resolve()), 'bytes': a.zip.stat().st_size, 'sha256': c.file_sha256(a.zip), 'newUnknownPairs': added_pairs}))


if __name__ == '__main__':
    main()
