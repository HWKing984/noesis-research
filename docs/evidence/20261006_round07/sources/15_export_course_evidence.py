"""Render verified real experiment artifacts into offline report pages, not fake UI screenshots."""
from __future__ import annotations

import argparse
import html
import json
import math
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_weak as c
from train_course_ner import load_snapshot, verify_files


def escaped(value) -> str:
    return html.escape(str(value), quote=True)


def table(headers, rows) -> str:
    return '<table><thead><tr>' + ''.join(f'<th>{escaped(x)}</th>' for x in headers) + '</tr></thead><tbody>' + ''.join(
        '<tr>' + ''.join(f'<td>{escaped(x)}</td>' for x in row) + '</tr>' for row in rows) + '</tbody></table>'


def highlight(text: str, entities: list[dict]) -> str:
    result, position = [], 0
    for entity in sorted(entities, key=lambda x: x['start']):
        start, end, label = entity['start'], entity['end'], entity['label']
        if not 0 <= position <= start < end <= len(text) or label not in c.CONFIG['entityLabels'] or text[start:end] != entity['text']:
            raise ValueError('Invalid literal entity for evidence display')
        result.extend([escaped(text[position:start]), f'<mark class="{label}">{escaped(text[start:end])}<small>{label}</small></mark>'])
        position = end
    return ''.join(result) + escaped(text[position:])


def loss_curve(steps: list[dict]) -> str:
    if len(steps) < 2 or [s['step'] for s in steps] != list(range(1, len(steps) + 1)):
        raise ValueError('Evidence requires complete consecutive step logs')
    values = [s['loss'] for s in steps]
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError('Logarithmic loss plot requires finite positive actual losses')
    lower, upper = math.floor(math.log10(min(values))), math.ceil(math.log10(max(values)))
    upper = max(upper, lower + 1)
    y = lambda value: 40 + 230 * (upper - value) / (upper - lower)
    points = ' '.join(f'{70 + 810 * i / (len(values)-1):.2f},{y(math.log10(v)):.2f}' for i, v in enumerate(values))
    grid = ''.join(f'<line x1="70" y1="{y(v):.2f}" x2="880" y2="{y(v):.2f}" stroke="#dae3ef"/>'
                   f'<text x="12" y="{y(v)+5:.2f}">1e{v}</text>' for v in range(lower, upper + 1))
    return (f'<svg viewBox="0 0 940 315" role="img" aria-label="实际逐步训练损失，纵轴为对数刻度">{grid}'
            f'<polyline fill="none" stroke="#2463bc" stroke-width="2.5" points="{points}"/>'
            f'<text x="70" y="300">step 1</text><text x="790" y="300">step {len(values)}</text></svg>')


def page(title: str, body: str, generated_at: str, sources: list[str]) -> str:
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{escaped(title)}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#eef2f7;color:#18243a;font:17px/1.55 'Microsoft YaHei',sans-serif}}
main{{max-width:1120px;margin:28px auto;background:white;padding:30px 38px;border-top:6px solid #2463bc}}
h1{{font-size:28px;margin:10px 0 18px}}h2{{font-size:20px;margin:22px 0 10px}}p{{margin:8px 0}}.tag{{color:#315f9b;font-weight:bold}}
.notice{{background:#fff4d7;border-left:5px solid #ba7900;padding:12px 16px}}.cards{{display:flex;gap:16px;margin:18px 0}}
.card{{flex:1;background:#edf4fc;padding:14px 18px}}.card strong{{font-size:27px;display:block}}table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:15px}}
th,td{{border:1px solid #d9e2ed;padding:9px 12px;text-align:left;overflow-wrap:anywhere}}th{{background:#edf3fa}}
code,.path{{font-family:Consolas,monospace;font-size:13px;overflow-wrap:anywhere}}mark{{background:#d9eaff;padding:2px 4px;border-radius:3px}}
mark.TASK{{background:#dcf2e5}}mark.DATASET{{background:#f3e5fd}}small{{font-size:10px;padding-left:5px;color:#38495e}}
.title{{font-size:20px;line-height:2.1;margin:12px 0}}footer{{border-top:1px solid #d7e1ed;margin-top:22px;padding-top:14px;font-size:12px;color:#58677d}}
svg{{width:100%;max-height:315px}}svg text{{font:14px Consolas,monospace}}
</style><main><div class="tag">AI Literature KG · 课程实验真实结果留痕</div><h1>{escaped(title)}</h1>
<p class="notice">本页由保存的真实 JSON/JSONL/XML 结果生成，供浏览器截图；不是原始终端、训练现场或 Neo4j 应用画面的仿制。AI 参考标签不是人工 gold。</p>
{body}<footer>证据页生成时间：{escaped(generated_at)}<br>来源：{''.join(f'<div class="path">{escaped(x)}</div>' for x in sources)}
模型/标注的时间以来源文件为准；截图拍摄时间与哈希另存 captures.json。</footer></main></html>'''


def build(dataset: Path, snapshot: Path, preflight: Path, smoke: Path, smoke_snapshot: Path,
          tests: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError('Preserve report evidence; choose a new output directory')
    sources = [dataset / 'manifest.json', snapshot / 'manifest.json', snapshot / 'summary.json',
               snapshot / 'receipts.jsonl', preflight / 'manifest.json', preflight / 'preflight.json',
               preflight / 'dictionary_dev_metrics.json', smoke / 'manifest.json', smoke / 'status.json',
               smoke / 'smoke_result.json', smoke / 'steps.jsonl', smoke / 'smoke_train_inputs.jsonl',
               smoke / 'smoke_predictions.jsonl', smoke_snapshot / 'manifest.json', tests, Path(__file__)]
    hashes = {str(p.resolve()): c.file_sha256(p) for p in sources}
    splits, summary = load_snapshot(dataset, snapshot)
    old_splits, _ = load_snapshot(dataset, smoke_snapshot)
    pm, sm = verify_files(preflight), verify_files(smoke)
    if (pm['inputSha256'].get(str((snapshot / 'manifest.json').resolve())) != hashes[str((snapshot / 'manifest.json').resolve())]
            or sm['inputSha256'].get(str((smoke_snapshot / 'manifest.json').resolve())) != hashes[str((smoke_snapshot / 'manifest.json').resolve())]):
        raise ValueError('Display snapshots do not match actual preflight/smoke source versions')
    read = lambda folder, name: json.loads((folder / name).read_text(encoding='utf-8'))
    pf, baseline, status, result = read(preflight, 'preflight.json'), read(preflight, 'dictionary_dev_metrics.json'), read(smoke, 'status.json'), read(smoke, 'smoke_result.json')
    if not pf['valid'] or status['status'] != 'completed' or not result['passed'] or result['evaluationScope'] != 'in_sample_overfit_smoke_not_generalization':
        raise ValueError('Evidence export requires declared successful preflight and actual in-sample smoke')
    rows = c.read_jsonl(smoke / 'smoke_train_inputs.jsonl')
    old_lookup = {r['sampleId']: r for r in old_splits['train']}
    if len({r['sampleId'] for r in rows}) != len(rows) or any(old_lookup.get(r['sampleId']) != r for r in rows):
        raise ValueError('Smoke inputs differ from their actual eligible train references')
    steps, predictions = c.read_jsonl(smoke / 'steps.jsonl'), c.read_jsonl(smoke / 'smoke_predictions.jsonl')
    ids = {r['sampleId'] for r in rows}
    if (len(steps) != status['config']['steps'] or any(not set(s['sampleIds']) <= ids for s in steps)
            or len(predictions) != len(rows) or {p['sampleId'] for p in predictions} != ids):
        raise ValueError('Incomplete logs or predictions, or nontrain sample in gradients')
    suites = ET.parse(tests).getroot()
    suites = [suites] if suites.tag == 'testsuite' else list(suites.iter('testsuite'))
    counts = {key: sum(int(s.get(key, 0)) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
    receipts = c.read_jsonl(snapshot / 'receipts.jsonl')
    reviews = Counter(r['reference']['split'] for r in receipts)
    relations = {s: sum(summary['relationSupport'][s].values()) for s in c.CONFIG['splitRatios']}
    generated_at = datetime.now(UTC).isoformat()
    table_rows = [(s, reviews[s], summary['nerEligibleSplits'][s], relations[s], *summary['entitySupport'][s].values())
                  for s in c.CONFIG['splitRatios']]
    data = f'<p>当前数据快照：<code>{escaped(snapshot.name)}</code>；队列 1600/200/200 按论文组固定划分，未移动样本。</p>'
    data += f'<div class="cards"><div class="card">已完成两轮 AI 判断<strong>{summary["aiReviewedDocuments"]} 篇</strong></div><div class="card">NER 可用<strong>{summary["nerEligibleDocuments"]} 篇</strong></div><div class="card">尚未首轮<strong>{summary["pendingGenerationDocuments"]} 篇</strong></div></div>'
    data += table(['split', 'AI复核篇数', 'NER篇数', '关系样本条数', 'METHOD跨度', 'TASK跨度', 'DATASET跨度'], table_rows)
    data += f'<h2>真实 tokenizer 对齐检查</h2><p>train/dev 通过 {sum(pf["tokenized"].values())} 篇；拒绝 {len(pf["rejected"])}；最长 token：train {pf["maxTokens"]["train"]} / dev {pf["maxTokens"]["dev"]}。无截断、无静默丢样本。</p>'
    data += f'<p>此快照的训练词典 dev 严格实体 F1：{baseline["micro"]["f1"]:.2%}；这是 AI 留出参考一致性，不是神经网络成绩。</p><p>未决不作为空负例；测试尚无标签，正式训练准备状态仍为 false。</p>'
    train = f'<p>模型：固定 SciBERT → 七类 BIO token 分类；<code>{escaped(smoke.name)}</code> 基于 <code>{escaped(smoke_snapshot.name)}</code>，不是最新数据重新训练。</p>'
    train += f'<div class="cards"><div class="card">实际设备<strong>RTX 4060</strong>{escaped(status["device"])} / CUDA {escaped(status["cudaVersion"])}</div><div class="card">训练内小样本<strong>{len(rows)} 篇 / {len(steps)} 步</strong>batch {status["config"]["batch_size"]} · lr {status["config"]["learning_rate"]}</div><div class="card">训练内严格实体 F1<strong>{result["final"]["metrics"]["micro"]["f1"]:.2%}</strong>不能作为测试成绩</div></div>'
    train += '<h2>逐步实际 batch loss（未平滑，纵轴对数）</h2>' + loss_curve(steps)
    train += table(['检查项', '真实结果'], [('同一训练内样本评估态 loss', f'{result["initial"]["loss"]:.6f} → {result["final"]["loss"]:.9f}'), ('编码器 / 分类头确实更新', f'{result["encoderChanged"]} / {result["classifierChanged"]}'), ('保存重载后实体预测一致', result['reloadPredictionsIdentical']), ('运行完成时间', status['finishedAt']), ('正式训练 / 测试评估', f'{status["formalTrainingStarted"]} / {status["testEvaluated"]}')])
    train += '<p>曲线来自 steps.jsonl 的逐批训练损失，不是验证曲线；训练内高分仅证明小样本过拟合链路正常。</p>'
    lookup = {r['sampleId']: r for r in rows}
    examples = '<p>下列是已保存的真实模型预测回放，来自上述 24 篇训练内题名，未筛选未见测试文本。显示前两个已保存样本，不当泛化演示。</p>'
    for prediction in predictions[:2]:
        row = lookup[prediction['sampleId']]
        if prediction['referenceEntities'] != row['entities']:
            raise ValueError('Displayed prediction reference differs from actual smoke input')
        examples += f'<h2>{escaped(row["sampleId"])}</h2><div class="title">{highlight(row["text"], prediction["predictedEntities"])}</div>'
        examples += table(['类别', 'Unicode [start,end)', '模型预测原文', '匹配AI参考'], [(e['label'], f'[{e["start"]},{e["end"]})', e['text'], any((e['start'], e['end'], e['label']) == (r['start'], r['end'], r['label']) for r in row['entities'])) for e in prediction['predictedEntities']])
    examples += '<p>METHOD 蓝色 / TASK 绿色 / DATASET 紫色。DATASET 训练内仅 1 个跨度，不能声称已解决稀有类泛化。</p>'
    trace = table(['检查项', '来源与结果'], [('pytest (本轮真实回归)', f'{counts["tests"]} 项；失败 {counts["failures"]} / 错误 {counts["errors"]} / 跳过 {counts["skipped"]}'), ('新数据输入版本', snapshot.name), ('训练权重实际输入版本', smoke_snapshot.name), ('原始模型固定 revision', sm['modelProvenance']['revision']), ('模型本地权重 SHA-256', sm['modelProvenance']['filesSha256']['pytorch_model.bin']), ('训练后 safetensors SHA-256', sm['filesSha256']['model/model.safetensors']), ('标签来源', 'codex_session / unknown_session_model；candidate-aware AI自复核，不是人工gold或独立盲审')])
    selected = [r for r in receipts if r['reference']['sampleId'] in {'sample-1ae916a995bfd6c962e8', 'sample-8a13e8c69ef3c0126eb5'}]
    trace += '<h2>本轮保留的修订与未决案例</h2>'
    trace += table(['原题名', '为何隔离而不伪造答案'], [(r['reference']['text'], r['annotation']['entityReason']) for r in selected])
    pages = {'01_data.html': ('01 数据处理与固定划分', data, [str(snapshot), str(preflight)]),
             '02_training.html': ('02 SciBERT GPU 冒烟与真实训练曲线', train, [str(smoke)]),
             '03_predictions.html': ('03 原文实体跨度与真实模型预测', examples, [str(smoke / 'smoke_predictions.jsonl')]),
             '04_traceability.html': ('04 版本、校验与 AI 自复核证据', trace, [str(tests), str(snapshot / 'receipts.jsonl'), str(smoke / 'manifest.json')])}
    if any(c.file_sha256(Path(name)) != digest for name, digest in hashes.items()):
        raise ValueError('Evidence sources changed while rendering')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'sources').mkdir()
    archived = {}
    for index, source in enumerate(sources):
        dest = output / 'sources' / f'{index:02d}_{source.name}'
        shutil.copyfile(source, dest)
        if c.file_sha256(dest) != hashes[str(source.resolve())]:
            raise ValueError('Source changed during evidence archival')
        archived[str(source.resolve())] = dest.relative_to(output).as_posix()
    for name, (title, body, paths) in pages.items():
        (output / name).write_text(page(title, body, generated_at, paths), encoding='utf-8')
    report = '# 报告截图索引\n\n本包为真实结果文件的离线可视化，不是终端或 Neo4j 原始界面。截图完成情况以 captures.json 为准。\n\n'
    for name, (title, _, _) in pages.items():
        png = name.replace('.html', '.png')
        report += f'## {title}\n\n![{title}]({png})\n\n页面：[{name}]({name})。插图必须保留页内阶段、输入版本和局限说明；不能把训练内 100% 当测试成绩。\n\n'
    report += '正式 NER/test、关系模型、Neo4j 导入和检索应用尚未完成，未生成这些阶段的成功截图。原始来源文件副本见 sources/；页面与来源哈希见 manifest.json，图片与拍摄方式见 captures.json。\n'
    (output / 'report_figures.md').write_text(report, encoding='utf-8')
    manifest = {'generatedAt': generated_at, 'kind': 'real_artifact_visualization_not_original_console_ui',
                'snapshot': snapshot.name, 'smokeSnapshot': smoke_snapshot.name, 'inputSha256': hashes,
                'archivedInputs': archived, 'testCounts': counts, 'screenshotCapturePending': True,
                'filesSha256': {p.relative_to(output).as_posix(): c.file_sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    c.write_json(output / 'manifest.json', manifest)
    return {'output': str(output.resolve()), 'pages': list(pages), 'tests': counts, 'screenshotCapturePending': True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'snapshot', 'preflight', 'smoke', 'smoke-snapshot', 'tests', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.dataset, args.snapshot, args.preflight, args.smoke, args.smoke_snapshot,
                           args.tests, args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
