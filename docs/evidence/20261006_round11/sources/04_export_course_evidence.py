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
from train_course_ner import load_snapshot, score_rows, verify_files


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


def build_test(dataset: Path, snapshot: Path, run: Path, tests: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError('Preserve final test evidence; choose a new output directory')
    manifest = verify_files(run)
    sources = [dataset / 'manifest.json', snapshot / 'manifest.json', snapshot / 'summary.json',
               snapshot / 'receipts.jsonl', tests, Path(__file__)]
    sources.extend(run / name for name in ('manifest.json', 'status.json', 'test_result.json', 'test_inputs.jsonl',
                  'test_predictions.jsonl', 'test_errors.jsonl', 'excluded_test_titles.jsonl', 'dictionary_test_metrics.json',
                  'dictionary_test_predictions.jsonl', 'dev_reload_check.json', 'preflight.json'))
    hashes = {str(p.resolve()): c.file_sha256(p) for p in sources}
    splits, summary = load_snapshot(dataset, snapshot, include_test=True)
    for p in (dataset / 'manifest.json', snapshot / 'manifest.json'):
        if manifest['inputSha256'].get(str(p.resolve())) != hashes[str(p.resolve())]:
            raise ValueError('Test evidence snapshot differs from actual evaluation inputs')
    result = json.loads((run / 'test_result.json').read_text(encoding='utf-8'))
    status = json.loads((run / 'status.json').read_text(encoding='utf-8'))
    predictions = c.read_jsonl(run / 'test_predictions.jsonl')
    excluded = c.read_jsonl(run / 'excluded_test_titles.jsonl')
    errors = c.read_jsonl(run / 'test_errors.jsonl')
    baseline = c.read_jsonl(run / 'dictionary_test_predictions.jsonl')
    spans = lambda items: {(e['start'], e['end'], e['label']) for e in items}
    receipts = [r for r in c.read_jsonl(snapshot / 'receipts.jsonl') if r['reference']['split'] == 'test']
    eligible = {r['sampleId'] for r in splits['test']}
    if (status['status'] != 'completed' or not status['testEvaluated'] or status['trainingStarted']
            or result['humanGold'] or result['testUsedForSelection']
            or result['evaluationScope'] != 'locked_final_test_ai_reference_agreement_not_human_gold'
            or c.read_jsonl(run / 'test_inputs.jsonl') != splits['test']
            or [p['sampleId'] for p in predictions] != [r['sampleId'] for r in splits['test']]
            or any(p['referenceEntities'] != r['entities'] for p, r in zip(predictions, splits['test']))
            or score_rows(splits['test'], [p['predictedEntities'] for p in predictions]) != result['test']['metrics']
            or not all(result[k] for k in ('weightsUnchanged', 'trainDevUnchanged', 'devReloadPredictionsIdentical'))
            or errors != [p for p in predictions if spans(p['referenceEntities']) != spans(p['predictedEntities'])]
            or {r['sampleId'] for r in excluded} != {r['reference']['sampleId'] for r in receipts if r['reference']['sampleId'] not in eligible}
            or [p['sampleId'] for p in baseline] != [r['sampleId'] for r in splits['test']]
            or score_rows(splits['test'], [p['entities'] for p in baseline]) != result['dictionaryTest']
            or len(excluded) != result['excludedDocuments'] or len(errors) != result['errorDocuments']):
        raise ValueError('Saved final test predictions or scope differ from evidence claims')
    for p, r in zip(predictions, splits['test']):
        highlight(r['text'], p['predictedEntities'])
    suites = ET.parse(tests).getroot()
    suites = [suites] if suites.tag == 'testsuite' else list(suites.iter('testsuite'))
    counts = {key: sum(int(s.get(key, 0)) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
    metric = result['test']['metrics']
    body = f'<p>输入：<code>{escaped(snapshot.name)}</code>；模型：冻结的 <code>{escaped(result["checkpoint"])}</code>。全部 200 篇先完成 AI 自复核，再评估完整可用子集；不重新训练。</p>'
    body += f'<div class="cards"><div class="card">固定测试队列<strong>{result["queueReviewed"]} 篇已复核</strong>同会话AI标注与自复核</div><div class="card">可用 / 排除<strong>{result["documents"]} / {result["excludedDocuments"]}</strong>覆盖 {result["eligibleCoverage"]:.0%}，未决不当负例</div><div class="card">严格实体 test F1<strong>{metric["micro"]["f1"]:.2%}</strong>AI参考一致性，不是人工gold</div></div>'
    body += table(['模型/类别', 'AI参考数', 'TP / 预测数', 'Precision', 'Recall', 'F1'],
                  [(name, m['reference'], f'{m["truePositive"]} / {m["predicted"]}', *(f'{m[x]:.2%}' if m[x] is not None else 'N/A' for x in ('precision', 'recall', 'f1')))
                   for name, m in [('SciBERT micro', metric['micro']), ('train词典 micro', result['dictionaryTest']['micro']), *metric['perClass'].items()]])
    body += table(['隔离与运行检查', '实际记录'], [('train/dev 输入未改', result['trainDevUnchanged']), ('旧dev预测重载完全一致', result['devReloadPredictionsIdentical']),
                  ('权重未更新 / test用于选型', f'{result["weightsUnchanged"]} / {result["testUsedForSelection"]}'), ('设备', status['gpu']),
                  ('真实回归', f'{counts["tests"]}项，失败/错误/跳过={counts["failures"]}/{counts["errors"]}/{counts["skipped"]}'), ('预测有差异题名', result['errorDocuments']),
                  ('冻结权重SHA-256', result['weightsSha256']), ('评估完成UTC', status['finishedAt'])])
    if errors:
        error = errors[0]
        row = next(r for r in splits['test'] if r['sampleId'] == error['sampleId'])
        body += f'<h2>保存顺序中的首个真实差异案例（未挑选好例）</h2><p><code>{escaped(row["sampleId"])}</code></p><p>AI参考：</p><div class="title">{highlight(row["text"], error["referenceEntities"])}</div><p>模型预测：</p><div class="title">{highlight(row["text"], error["predictedEntities"])}</div>'
    body += '<p class="notice">DATASET 只有 2 个参考跨度，不能声称稳定泛化；56 篇未决排除使指标仅适用于可判定子集。标签由同一 Codex 会话候选可见自复核，不是独立盲审。关系抽取/Neo4j应用尚未完成，测试结果不得回用于本版本调参。</p>'
    if any(c.file_sha256(Path(p)) != h for p, h in hashes.items()):
        raise ValueError('Final test evidence sources changed')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'sources').mkdir()
    archived = {}
    for i, source in enumerate(sources):
        dest = output / 'sources' / f'{i:02d}_{source.name}'
        shutil.copyfile(source, dest)
        if c.file_sha256(dest) != hashes[str(source.resolve())]:
            raise ValueError('Final test source changed during archival')
        archived[str(source.resolve())] = dest.relative_to(output).as_posix()
    generated = datetime.now(UTC).isoformat()
    (output / '06_final_test.html').write_text(page('06 冻结模型最终 NER 测试与局限', body, generated, [str(run), str(snapshot)]), encoding='utf-8')
    (output / 'report_figures.md').write_text('# 最终NER测试证据图\n\n![最终NER测试](06_final_test.png)\n\n图注：冻结dev所选epoch4，200篇测试题名全部AI自复核后，在144篇完整可用题名上一次性评估；56篇未决排除。严格实体指标为AI参考一致性，DATASET支持仅2，不是人工金标准。图为真实结果的浏览器可视化截图，不是原始终端或Neo4j界面。来源/页面哈希见manifest.json，实际拍摄状态见captures.json。旧08五图原样保留。\n', encoding='utf-8')
    c.write_json(output / 'manifest.json', {'kind':'real_artifact_visualization_not_original_console_ui', 'generatedAt':generated,
                 'snapshot':snapshot.name, 'inputSha256':hashes, 'archivedInputs':archived, 'testCounts':counts,
                 'screenshotCapturePending':True, 'filesSha256':{p.relative_to(output).as_posix():c.file_sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    return {'output':str(output.resolve()), 'pages':['06_final_test.html'], 'tests':counts}


def build_relation(dataset: Path, snapshot: Path, runs: list[Path], tests: Path, output: Path) -> dict:
    from train_course_relation import load_relation_snapshot, pair_id, score_relations, type_majority
    if output.exists():
        raise FileExistsError('Preserve relation evidence; choose a new output directory')
    if not runs:
        raise ValueError('Relation evidence requires nonempty real runs')
    manifests = [verify_files(run) for run in runs]
    sources = [dataset / 'manifest.json', snapshot / 'manifest.json', snapshot / 'summary.json', tests, Path(__file__)]
    for run in runs:
        sources.extend(run / name for name in ('manifest.json','status.json','development_result.json','preflight.json',
                       'epochs.json','steps.jsonl','train_inputs.jsonl','dev_inputs.jsonl','dev_predictions.jsonl','dev_errors.jsonl','baseline_dev_metrics.json'))
    hashes = {str(p.resolve()):c.file_sha256(p) for p in sources}
    splits, _ = load_relation_snapshot(dataset,snapshot)
    baseline = type_majority(splits['train'])
    baseline_metrics = score_relations(splits['dev'],[baseline[r['tail']['label']] for r in splits['dev']])
    reports = []
    for run, manifest in zip(runs,manifests):
        read = lambda name:json.loads((run / name).read_text(encoding='utf-8'))
        state, result, epochs = read('status.json'), read('development_result.json'), read('epochs.json')
        predictions, errors, steps = [c.read_jsonl(run / name) for name in ('dev_predictions.jsonl','dev_errors.jsonl','steps.jsonl')]
        if (manifest['inputSha256'].get(str((snapshot / 'manifest.json').resolve())) != hashes[str((snapshot / 'manifest.json').resolve())]
                or state['status']!='completed' or state['mode']!='fit-dev' or not result['passed']
                or result['testEvaluated'] or result['testTokenized'] or result['devUsedForGradient']
                or result['humanGold'] or result['endToEndEvaluated']
                or result['evaluationScope']!='reference_entities_dev_selected_ai_reference_not_final_test'
                or any(c.read_jsonl(run / f'{s}_inputs.jsonl')!=splits[s] for s in splits)
                or [p['pairId'] for p in predictions] != [pair_id(r) for r in splits['dev']]
                or any(p['head']!=r['head'] or p['tail']!=r['tail'] or p['referenceLabel']!=r['label'] for p,r in zip(predictions,splits['dev']))
                or score_relations(splits['dev'],[p['predictedLabel'] for p in predictions])!=result['bestDev']['metrics']
                or result['baselineDev']!=baseline_metrics or len(steps)!=result['steps']
                or errors!=[p for p in predictions if p['referenceLabel']!=p['predictedLabel']]):
            raise ValueError('Relation evidence differs from saved reference-entity development artifacts')
        expected = Counter(pair_id(r) for r in splits['train'])
        lookup = {pair_id(r):r['sampleId'] for r in splits['train']}
        if ([e['epoch'] for e in epochs]!=list(range(1,result['epochs']+1))
                or [s['step'] for s in steps]!=list(range(1,result['steps']+1))
                or any(Counter(pid for step in steps if step['epoch']==epoch for pid in step['pairIds'])!=expected for epoch in range(1,result['epochs']+1))
                or any(step['sampleIds']!=[lookup.get(pid) for pid in step['pairIds']] for step in steps)):
            raise ValueError('Relation gradients must use every train pair exactly once per epoch')
        best = max(epochs,key=lambda e:e['dev']['metrics']['positiveMacroF1'])
        if (result['bestCheckpoint']!=f'checkpoint_epoch_{best["epoch"]:02d}' or result['bestDev']!=best['dev']
                or result['bestCheckpoint']+'/model.safetensors' not in manifest['filesSha256']):
            raise ValueError('Relation checkpoint differs from earliest best dev macro F1')
        reports.append((run,state,result,epochs,errors,steps))
    chosen = max(reports,key=lambda x:(x[2]['bestDev']['metrics']['positiveMacroF1'],
                 x[2]['bestDev']['metrics']['perClass']['NO_RELATION']['recall'],not x[1]['config'].get('balanced_loss',False)))
    run, state, result, epochs, errors, steps = chosen
    metric = result['bestDev']['metrics']
    suites = ET.parse(tests).getroot()
    suites = [suites] if suites.tag=='testsuite' else list(suites.iter('testsuite'))
    counts = {key:sum(int(s.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
    body = '<p>315条train实体对来自247篇题名；162条dev实体对来自113篇题名。参考实体下关系分类，不是NER→RE端到端或最终test。</p>'
    body += f'<div class="cards"><div class="card">真实GPU开发实验<strong>{len(reports)} 组 × 6轮</strong>各240步，保存来源与权重</div><div class="card">正关系dev micro F1<strong>{metric["positiveMicro"]["f1"]:.2%}</strong>与类型多数基线比较</div><div class="card">NO_RELATION召回<strong>{metric["perClass"]["NO_RELATION"]["recall"]:.2%}</strong>支持仅5条，不能只展示高分</div></div>'
    comparison = [('类型多数基线','仅train计数',baseline_metrics['positiveMicro']['f1'],baseline_metrics['positiveMacroF1'],baseline_metrics['perClass']['NO_RELATION']['recall'])]
    comparison += [(p.name,'逆频率加权' if s['config'].get('balanced_loss',False) else '未加权',r['bestDev']['metrics']['positiveMicro']['f1'],r['bestDev']['metrics']['positiveMacroF1'],r['bestDev']['metrics']['perClass']['NO_RELATION']['recall']) for p,s,r,_,_,_ in reports]
    body += table(['实验','损失/基线','正关系micro F1','正关系macro F1','负例Recall'],[(name,method,*(f'{v:.2%}' for v in values)) for name,method,*values in comparison])
    body += f'<p>按dev正关系macro、负例召回、优先简单模型的既定顺序，候选为 <code>{escaped(run.name)}</code> / <code>{escaped(result["bestCheckpoint"])}</code>。仅为开发选择，不等于应用验收通过。</p>'
    body += '<h2>候选6轮完整验证记录</h2>' + table(['epoch','step','dev loss','正micro F1','正macro F1','负例Recall'],[(e['epoch'],e['step'],f'{e["dev"]["loss"]:.5f}',*(f'{e["dev"]["metrics"][key]:.2%}' if key=='positiveMacroF1' else f'{e["dev"]["metrics"][key]["f1"]:.2%}' for key in ('positiveMicro','positiveMacroF1')),f'{e["dev"]["metrics"]["perClass"]["NO_RELATION"]["recall"]:.2%}') for e in epochs])
    body += table(['类别','参考 / 预测','P','R','F1'],[(label,f'{m["reference"]} / {m["predicted"]}',*(f'{m[x]:.2%}' if m[x] is not None else 'N/A' for x in ('precision','recall','f1'))) for label,m in metric['perClass'].items()])
    body += '<h2>混淆矩阵：行=AI参考，列=模型预测</h2>' + table(['参考\\预测',*metric['confusionLabels']],[(label,*row) for label,row in zip(metric['confusionLabels'],metric['confusionMatrix'])])
    body += '<h2>选中候选实际逐批训练损失</h2>' + loss_curve(steps)
    if errors:
        error = errors[0]
        row = next(r for r in splits['dev'] if pair_id(r)==error['pairId'])
        body += '<h2>保存顺序中的首个误报（未挑选成功例）</h2>'
        body += f'<div class="title">{highlight(row["text"],sorted([row["head"],row["tail"]],key=lambda e:e["start"]))}</div><p>AI参考：{escaped(error["referenceLabel"])}；模型：{escaped(error["predictedLabel"])}。参考理由：{escaped(row["reason"])}</p>'
    body += f'<p>编码器/分类头更新：{result["encoderChanged"]}/{result["classifierChanged"]}；重载预测一致：{result["reloadPredictionsIdentical"]}；回归：{counts["tests"]}项，失败/错误/跳过={counts["failures"]}/{counts["errors"]}/{counts["skipped"]}。</p>'
    same_as_baseline = all([p['predictedLabel'] for p in c.read_jsonl(folder / 'dev_predictions.jsonl')] == [baseline[r['tail']['label']] for r in splits['dev']] for folder in runs)
    conclusion = f'{len(runs)}组模型选中轮预测均与类型多数基线相同；' if same_as_baseline else '选中轮预测与类型多数基线存在差异；'
    if metric['perClass']['NO_RELATION']['recall']==0:
        conclusion += f'{metric["perClass"]["NO_RELATION"]["reference"]}条负例全误报，未证明语义角色区分能力，下一步补训练侧角色区分/负例。'
    body += f'<p class="notice">{conclusion}未晋级为确证图谱事实。EVALUATED_ON dev仅{metric["perClass"]["EVALUATED_ON"]["reference"]}条，高分不代表可靠；RE最终test与端到端pipeline尚未完成，AI参考不是人工gold。</p>'
    if any(c.file_sha256(Path(p))!=h for p,h in hashes.items()):
        raise ValueError('Relation evidence sources changed during rendering')
    output.mkdir(parents=True,exist_ok=False)
    (output / 'sources').mkdir()
    archived = {}
    for i,source in enumerate(sources):
        dest = output / 'sources' / f'{i:02d}_{source.name}'
        shutil.copyfile(source,dest)
        if c.file_sha256(dest)!=hashes[str(source.resolve())]:
            raise ValueError('Relation source changed during evidence archival')
        archived[str(source.resolve())] = dest.relative_to(output).as_posix()
    generated = datetime.now(UTC).isoformat()
    (output / '07_relation_development.html').write_text(page('07 关系模型GPU训练、基线与误报分析',body,generated,[str(p) for p in runs]+[str(snapshot)]),encoding='utf-8')
    (output / 'report_figures.md').write_text(f'# 关系开发实验留痕\n\n![关系模型开发实验](07_relation_development.png)\n\n图注：固定{len(splits["train"])}/{len(splits["dev"])}条train/dev参考实体对上的{len(reports)}组SciBERT实际GPU训练。{conclusion}不能当最终test成绩。真实结果浏览器可视化，不是训练终端或Neo4j界面；来源/页面哈希见manifest.json，拍摄状态见captures.json。\n',encoding='utf-8')
    c.write_json(output / 'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui','generatedAt':generated,
                 'snapshot':snapshot.name,'inputSha256':hashes,'archivedInputs':archived,'testCounts':counts,'screenshotCapturePending':True,
                 'filesSha256':{p.relative_to(output).as_posix():c.file_sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}})
    return {'output':str(output.resolve()),'pages':['07_relation_development.html'],'tests':counts}


def build(dataset: Path, snapshot: Path, preflight: Path, smoke: Path, smoke_snapshot: Path,
          tests: Path, output: Path, development: Path | None = None) -> dict:
    if output.exists():
        raise FileExistsError('Preserve report evidence; choose a new output directory')
    sources = [dataset / 'manifest.json', snapshot / 'manifest.json', snapshot / 'summary.json',
               snapshot / 'receipts.jsonl', preflight / 'manifest.json', preflight / 'preflight.json',
               preflight / 'dictionary_dev_metrics.json', smoke / 'manifest.json', smoke / 'status.json',
               smoke / 'smoke_result.json', smoke / 'steps.jsonl', smoke / 'smoke_train_inputs.jsonl',
               smoke / 'smoke_predictions.jsonl', smoke_snapshot / 'manifest.json', tests, Path(__file__)]
    if development is not None:
        sources.extend(development / name for name in ('manifest.json', 'status.json', 'development_result.json',
                       'epochs.json', 'steps.jsonl', 'development_train_inputs.jsonl', 'dev_predictions.jsonl', 'dev_errors.jsonl'))
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
    if development is not None:
        dm = verify_files(development)
        ds, dr = read(development, 'status.json'), read(development, 'development_result.json')
        ep = read(development, 'epochs.json')
        dev_steps = c.read_jsonl(development / 'steps.jsonl')
        dev_predictions = c.read_jsonl(development / 'dev_predictions.jsonl')
        if (dm['inputSha256'].get(str((snapshot / 'manifest.json').resolve())) != hashes[str((snapshot / 'manifest.json').resolve())]
                or ds['mode'] != 'fit-dev' or ds['status'] != 'completed' or not dr['passed']
                or dr['evaluationScope'] != 'dev_selected_ai_reference_agreement_not_final_test'
                or dr['testEvaluated'] or dr['testTokenized'] or dr['devUsedForGradient'] or dr['humanGold']):
            raise ValueError('Development evidence must bind train/dev fitting, not final test')
        train_rows = c.read_jsonl(development / 'development_train_inputs.jsonl')
        if train_rows != splits['train'] or len(dev_steps) != dr['steps']:
            raise ValueError('Development train input or step coverage differs')
        batches = math.ceil(len(train_rows) / ds['config']['batch_size'])
        train_ids = Counter(r['sampleId'] for r in train_rows)
        for epoch in range(dr['epochs']):
            actual = Counter(sid for step in dev_steps[epoch*batches:(epoch+1)*batches] for sid in step['sampleIds'])
            if actual != train_ids:
                raise ValueError('Each development epoch must use exactly the train split once')
        if ([e['epoch'] for e in ep] != list(range(1, dr['epochs']+1))
                or [e['step'] for e in ep] != [batches*i for i in range(1, dr['epochs']+1)]
                or any(e['trainDocuments'] != len(train_rows) or e['devDocuments'] != len(splits['dev']) for e in ep)):
            raise ValueError('Development epoch logs incomplete')
        best = max(ep, key=lambda e: e['dev']['metrics']['micro']['f1'])
        if dr['bestCheckpoint'] != f'checkpoint_epoch_{best["epoch"]:02d}' or dr['bestDev'] != best['dev']:
            raise ValueError('Selected checkpoint does not match earliest best strict dev F1')
        if ([p['sampleId'] for p in dev_predictions] != [r['sampleId'] for r in splits['dev']]
                or any(p['referenceEntities'] != r['entities'] for p, r in zip(dev_predictions, splits['dev']))):
            raise ValueError('Development predictions differ from reviewed dev reference')
        for prediction, row in zip(dev_predictions, splits['dev']):
            highlight(row['text'], prediction['predictedEntities'])
        if score_rows(splits['dev'], [p['predictedEntities'] for p in dev_predictions]) != dr['bestDev']['metrics']:
            raise ValueError('Development metrics differ from actual saved predictions')
        if baseline['micro']['f1'] != dr['dictionaryDevF1']:
            raise ValueError('Dictionary baseline must use the same train/dev snapshot')
        errors = c.read_jsonl(development / 'dev_errors.jsonl')
        spans = lambda entities: {(e['start'], e['end'], e['label']) for e in entities}
        if errors != [p for p in dev_predictions if spans(p['referenceEntities']) != spans(p['predictedEntities'])]:
            raise ValueError('Development error inventory differs from saved predictions')
        body = f'<p>本轮真实训练：<code>{escaped(development.name)}</code>，输入 <code>{escaped(snapshot.name)}</code>。{len(train_rows)}/{len(splits["dev"])} 为实际可用 train/dev，不是完整 1600/200 队列。</p>'
        body += f'<div class="cards"><div class="card">GPU训练<strong>{dr["epochs"]} 轮 / {dr["steps"]} 步</strong>{escaped(ds["gpu"])}</div><div class="card">最佳验证实体 F1<strong>{dr["bestDev"]["metrics"]["micro"]["f1"]:.2%}</strong>epoch {best["epoch"]}，不是测试成绩</div><div class="card">同划分词典基线<strong>{baseline["micro"]["f1"]:.2%}</strong>AI参考一致性</div></div>'
        body += '<h2>验证集选择 checkpoint（严格跨度与类别完全匹配）</h2>'
        body += table(['epoch', 'step', 'dev token loss', 'dev Precision', 'dev Recall', 'dev F1', '保存改善权重'],
                      [(e['epoch'], e['step'], f'{e["dev"]["loss"]:.5f}', *(f'{e["dev"]["metrics"]["micro"][x]:.2%}' for x in ('precision', 'recall', 'f1')), e['checkpointImproved']) for e in ep])
        body += table(['类别', 'AI参考跨度数', 'Precision', 'Recall', 'F1'], [(label, m['reference'], *(f'{m[x]:.2%}' if m[x] is not None else 'N/A' for x in ('precision', 'recall', 'f1'))) for label, m in dr['bestDev']['metrics']['perClass'].items()])
        body += '<h2>真实训练逐批损失（对数，未平滑）</h2>' + loss_curve(dev_steps)
        body += f'<p>保存重载预测一致：{dr["reloadPredictionsIdentical"]}；编码器/分类头更新：{dr["encoderChanged"]}/{dr["classifierChanged"]}。train/dev 梯度隔离已按逐步样本 ID 核验。剩余 {len(errors)} 篇 dev 有至少一个漏检、错检或边界/类别差异。</p>'
        if errors:
            error = errors[0]
            row = next(r for r in splits['dev'] if r['sampleId'] == error['sampleId'])
            body += f'<h2>保存顺序中的首个错误案例（未挑选好例）</h2><p><code>{escaped(row["sampleId"])}</code></p><p>AI参考：</p><div class="title">{highlight(row["text"], error["referenceEntities"])}</div><p>模型预测：</p><div class="title">{highlight(row["text"], error["predictedEntities"])}</div>'
        body += '<p class="notice">这是 dev 选型成绩，dev 已用于选择 epoch；没有最终 test 成绩。DATASET 的 dev 支持仅 3 个，不能据此声称稀有类稳定泛化。AI 自复核并非独立人工核验。</p>'
        pages['05_development.html'] = ('05 全量可用 train/dev 候选训练与错误分析', body, [str(development), str(snapshot)])
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
    report += '最终 NER/test、关系模型、Neo4j 导入和检索应用尚未完成，未生成这些阶段的成功截图。原始来源文件副本见 sources/；页面与来源哈希见 manifest.json，图片与拍摄方式见 captures.json。\n'
    (output / 'report_figures.md').write_text(report, encoding='utf-8')
    manifest = {'generatedAt': generated_at, 'kind': 'real_artifact_visualization_not_original_console_ui',
                'snapshot': snapshot.name, 'smokeSnapshot': smoke_snapshot.name, 'inputSha256': hashes,
                'archivedInputs': archived, 'testCounts': counts, 'screenshotCapturePending': True,
                'filesSha256': {p.relative_to(output).as_posix(): c.file_sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}}
    c.write_json(output / 'manifest.json', manifest)
    return {'output': str(output.resolve()), 'pages': list(pages), 'tests': counts, 'screenshotCapturePending': True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('dataset', 'snapshot', 'tests', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('preflight', 'smoke', 'smoke-snapshot', 'final-test'):
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--development', type=Path)
    parser.add_argument('--relation-development', type=Path, nargs='+')
    args = parser.parse_args()
    if args.final_test is not None and args.relation_development is not None:
        parser.error('Choose final-test or relation-development evidence, not both')
    if args.relation_development is not None:
        result = build_relation(args.dataset,args.snapshot,args.relation_development,args.tests,args.output)
    elif args.final_test is not None:
        result = build_test(args.dataset, args.snapshot, args.final_test, args.tests, args.output)
    else:
        if any(x is None for x in (args.preflight, args.smoke, args.smoke_snapshot)):
            parser.error('Provide --final-test or all three --preflight/--smoke/--smoke-snapshot inputs')
        result = build(args.dataset, args.snapshot, args.preflight, args.smoke, args.smoke_snapshot,
                       args.tests, args.output, args.development)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
