"""Package actual fixed-run results for review; do not include weight binaries."""
from __future__ import annotations

import argparse
import csv
import html
import json
import zipfile
from pathlib import Path

import course_weak as c


def h(value):
    return html.escape(str(value))


def spans(text, entities):
    pieces, previous = [], 0
    for entity in entities:
        pieces.extend([h(text[previous:entity['start']]),
                       '<mark class="' + h(entity['label']) + '" title="' + h(entity['label']) + '">',
                       h(text[entity['start']:entity['end']]), '</mark>'])
        previous = entity['end']
    pieces.append(h(text[previous:]))
    return ''.join(pieces)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--zip', type=Path, required=True)
    args = parser.parse_args()
    run = args.run.resolve()
    if json.loads((run / 'status.json').read_text(encoding='utf-8'))['status'] != 'completed':
        raise ValueError('Cannot package incomplete experiment as completed')
    contract = json.loads((run / 'execution_contract.json').read_text(encoding='utf-8'))
    data = Path(contract['data'])
    bound_files = json.loads((run / 'artifacts_manifest.json').read_text(encoding='utf-8'))['filesSha256']
    for name, digest in bound_files.items():
        if c.file_sha256(run / name) != digest:
            raise ValueError('Run artifact changed: ' + name)
    entities = c.read_jsonl(run / 'ner/dev_predictions.jsonl')
    relation_errors = c.read_jsonl(run / 're/dev_errors.jsonl')
    pipeline = c.read_jsonl(run / 'pipeline_error_attribution.jsonl')
    result = json.loads((run / 'results.json').read_text(encoding='utf-8'))
    metrics = [('NER', result['NER']['bestDev']['metrics']['micro']),
               *[('NER ' + k, v) for k, v in result['NER']['bestDev']['metrics']['perClass'].items()],
               *[('RE conditional ' + k, v) for k, v in result['RE']['bestDev']['metrics']['perClass'].items()]]
    pct = lambda v: 'N/A' if v is None else f'{v * 100:.2f}%'
    metric_rows = ''.join('<tr>' + ''.join('<td>' + h(x) + '</td>' for x in
                         (name, pct(m['precision']), pct(m['recall']), pct(m['f1']), m['reference'])) + '</tr>'
                         for name, m in metrics)
    pages = []
    for row in entities:
        paper = row['arxivId']
        errors = [e for e in relation_errors if e['arxivId'] == paper]
        pe = [e for e in pipeline if e['arxivId'] == paper]
        rel_rows = ''.join('<tr>' + ''.join('<td>' + h(x) + '</td>' for x in
                           (e['head']['text'], e['tail']['text'], e['referenceLabel'], e['predictedLabel'], e['evidence']['text'])) + '</tr>'
                           for e in errors)
        pipe_rows = ''.join('<tr>' + ''.join('<td>' + h(x) + '</td>' for x in
                            (e['kind'], e['category'], e['head']['text'], e['tail']['text'], e['label'])) + '</tr>' for e in pe)
        pages.append(f'<details><summary>{h(paper)} — NER reference {len(row["referenceEntities"])}, predicted {len(row["predictedEntities"])}; RE classified errors {len(errors)}</summary>'
                     f'<h3>参考实体（AI 弱参考）</h3><p>{spans(row["text"], row["referenceEntities"])}</p>'
                     f'<h3>模型实体</h3><p>{spans(row["text"], row["predictedEntities"])}</p>'
                     '<h3>给定参考实体的 RE 错误</h3><table><tr><th>方法</th><th>目标</th><th>参考</th><th>预测</th><th>参考证据</th></tr>' + rel_rows + '</table>'
                     '<h3>实际 Pipeline 归因（MASKED 不是误报）</h3><table><tr><th>状态</th><th>归因</th><th>方法</th><th>目标</th><th>关系</th></tr>' + pipe_rows + '</table></details>')
    page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>V2 单次 SciBERT 实验审核</title>'
            '<style>body{font:16px/1.7 system-ui;max-width:1400px;margin:30px auto;padding:0 20px;background:#f6f8fa}'
            'table{border-collapse:collapse;width:100%;background:white}td,th{padding:7px;border:1px solid #ccc;text-align:left}'
            'details{background:white;padding:16px;margin:20px 0;border:1px solid #ddd}summary{cursor:pointer;font-weight:600}'
            'mark{padding:2px;border-radius:3px}.METHOD{background:#badbff}.TASK{background:#c8efcf}.DATASET{background:#f9dbaf}</style>'
            '<h1>V2 Train65 / Dev20 — 真实单次训练结果</h1><p>固定 seed=20261011；两模型各 6 轮；test20 正文未读取；生产不变。</p>'
            '<p>这是 dev 选点后的 AI 弱参考匹配，不是正式测试成绩。RE 已裁决 361/974 对，覆盖 37.06%；613 对未决，完整端到端 F1 不计算。</p>'
            '<p>METHOD 蓝、TASK 绿、DATASET 橙；展开论文查看完整原文与真实预测。概率未校准，不能当作正确率。</p>'
            '<table><tr><th>类别</th><th>P</th><th>R</th><th>F1</th><th>参考数</th></tr>' + metric_rows + '</table>' + ''.join(pages) + '</html>')
    page_path = run / 'dev20_model_review.html'
    if page_path.exists():
        raise ValueError('Refuse to overwrite existing review')
    page_path.write_text(page, encoding='utf-8')
    with (run / 'ner_error_review.csv').open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['arxivId', 'kind', 'category', 'entityText', 'label', 'start', 'end', 'overlaps', 'text'])
        writer.writeheader()
        for row in c.read_jsonl(run / 'ner_error_spans.jsonl'):
            e = row['entity']
            writer.writerow({**{k: row[k] for k in ('arxivId', 'kind', 'category', 'text')},
                             'entityText': e['text'], 'label': e['label'], 'start': e['start'], 'end': e['end'],
                             'overlaps': json.dumps(row['overlaps'], ensure_ascii=False)})
    archive = args.zip.resolve()
    if archive.exists():
        raise ValueError('Refuse to overwrite review archive')
    entries = [(p, 'results/' + p.relative_to(run).as_posix()) for p in sorted(run.rglob('*'))
               if p.is_file() and p.suffix not in ('.safetensors', '.bin')]
    entries += [(p, 'snapshot/' + p.name) for p in sorted(data.iterdir()) if p.is_file()]
    scripts = set(Path(p) for p in contract['codeSha256']) | {
        Path(__file__), c.ROOT / 'scripts/import_course_ai.py', c.ROOT / 'scripts/prepare_course_weak.py',
        c.CONFIG_PATH, c.SCHEMA_PATH}
    entries += [(p, p.relative_to(c.ROOT).as_posix()) for p in sorted(scripts)]
    bootstrap_abort = c.ROOT / 'outputs/v2_textscope_once_20261011'
    if bootstrap_abort.exists():
        entries += [(bootstrap_abort / name, 'bootstrap_abort/' + name)
                    for name in ('failure.json', 'status.json', 'execution_contract.json')
                    if (bootstrap_abort / name).is_file()]
    note = ('真实训练审核包：包含冻结 Train65/Dev20、实际指标/预测/错误、采样计划与运行代码。\n'
            '不含 test20 正文，不含大型模型权重；两模型权重在原 run/ner/best_model 和 run/re/best_model。\n'
            '原 snapshot 中 trainingAuthorized=false 是冻结时状态；本次用户授权单独记录在 execution_contract.json，未回写快照。\n'
            '原本首次启动在梯度更新前因 NER 未使用 pooler 的检查过严而失败；修正后仅完成此一实际训练，不是多轮调参。\n'
            '复现需要本地 pinned SciBERT 基础权重、execution_contract 指定的软件依赖。\n'
            '在当前项目运行：.venv-training/Scripts/python.exe -B scripts/run_v2_textscope_once.py '
            '--data kg_datasets/dblp/course_v2_train65_dev20_textscope_20261011_final '
            '--base kg_datasets/models/scibert_24f92d32 --output outputs/v2_textscope_once_reproduction\n'
            '这是复现说明，不建议在未审核前追加运行或解封测试。\n')
    digests = {name: c.file_sha256(p) for p, name in entries}
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for path, name in entries:
            z.write(path, name)
        z.writestr('PACKAGE_README.txt', note)
        z.writestr('PACKAGE_SHA256.json', json.dumps(digests, indent=2, ensure_ascii=False))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('Review archive CRC error')
    c.write_json(run / 'review_package_receipt.json', {'archive': str(archive), 'sha256': c.file_sha256(archive),
                 'bytes': archive.stat().st_size, 'entries': len(entries) + 2,
                 'weightBinariesIncluded': False, 'testBodyIncluded': False})
    print(json.dumps({'archive': str(archive), 'sha256': c.file_sha256(archive), 'bytes': archive.stat().st_size}))


if __name__ == '__main__':
    main()
