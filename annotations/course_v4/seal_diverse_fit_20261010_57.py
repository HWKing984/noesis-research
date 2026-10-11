"""Verify actual57 artifacts and render honest evidence pages; no fit or held-out reads."""
import argparse
import math
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
import train_diverse_abstract_relation as training
from export_course_evidence import escaped, loss_curve, page, table

c, g, read = training.c, training.g, training.read
RUN = c.ROOT/'kg_datasets/dblp/course_v4_runs/diverse_role_development_20261010_57'
AUTHOR = c.ROOT/'kg_datasets/dblp/course_v4_identity_alias_audit_20261010_57'
CONCEPT = c.ROOT/'kg_datasets/dblp/course_v4_runs/concept_alias_candidates_20261010_57'
TESTS = c.ROOT/'kg_datasets/dblp/course_v4_runs/tests_quality57_final_fixed.xml'
COVERAGE = c.ROOT/'kg_datasets/dblp/course_v4_runs/coverage_quality57_combined.json'
OUTPUT = c.ROOT/'docs/evidence/20261010_round57'


def checked():
    mf = g.verified_files(RUN)
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in mf['inputSha256'].items()): raise ValueError('Training sources drifted')
    config, recipe, _, _, data, _, _, added = training.load_inputs(); cached = training.cached54(data, recipe)
    result = read(RUN/'development_result.json'); comparison = read(RUN/'comparison.json'); fit = result['RE']; steps = c.read_jsonl(RUN/'re/steps.jsonl'); epochs = read(RUN/'re/epochs.json')
    if read(RUN/'status.json')['status'] != 'completed' or not result['passed'] or result['comparison'] != comparison or any(result[k] for k in ('qualityPromotionPassed', 'modelPromoted', 'testEvaluated')) or fit['steps'] != 612 or fit['epochs'] != 6 or fit['savedCheckpoints'] != 1 or not fit['classifierAndEncoderChanged'] or not fit['reloadPredictionsIdentical']: raise ValueError('Actual training/result scope drift')
    if comparison['candidateRE'] != 'new57' or comparison['cached54'] != cached or c.read_jsonl(RUN/'re/train_inputs.jsonl') != data['train']['relation'] or c.read_jsonl(RUN/'re/dev_inputs.jsonl') != data['dev']['relation'] or c.read_jsonl(RUN/'new22_train_inputs.jsonl') != added: raise ValueError('Model/data binding drift')
    if len(steps) != 612 or [s['step'] for s in steps] != list(range(1, 613)) or any(not math.isfinite(s['loss']) or s['loss'] < 0 for s in steps): raise ValueError('Incomplete/nonfinite real loss trace')
    expected = Counter(training.re_model.pair_id(p) for p in data['train']['relation'])
    for epoch in range(1, 7):
        values = [s for s in steps if s['epoch'] == epoch]
        if len(values) != 102 or Counter(i for s in values for i in s['inputIds']) != expected: raise ValueError('Epoch did not consume each408 TRAIN pair exactly once')
    selected = max(epochs, key=lambda e: training.re_model.selection_score(e['dev']['metrics'], 'all_class_macro'))
    if fit['bestCheckpoint'] != f'checkpoint_epoch_{selected["epoch"]:02d}' or fit['bestDev'] != selected['dev']: raise ValueError('Dev selection changed')
    for name in ('old', 'new'):
        known = c.read_jsonl(RUN/(name+'_module_dev_predictions.jsonl'))
        if training.prior.dev_scope(training.old.diagnostic.scored(data['dev']['relation'], known)) != comparison['module'][name]: raise ValueError('Module prediction recount drift')
        full = c.read_jsonl(RUN/'pipeline_dev_documents.jsonl'); refs = c.read_jsonl(RUN/'pipeline_dev_reference_pairs.jsonl'); preds = c.read_jsonl(RUN/(name+'_pipeline_predictions.jsonl'))
        metric = training.prior.score_pipeline(full, refs, preds)['positiveMicro']; saved = comparison['pipeline'][name]['positiveMicro']
        if any(metric[k] != saved[k] for k in ('truePositive', 'predicted', 'reference', 'precision', 'recall', 'f1')) or len(c.read_jsonl(RUN/(name+'_false_relations.jsonl'))) != saved['predicted']-saved['truePositive'] or len(c.read_jsonl(RUN/(name+'_missed_relations.jsonl'))) != saved['reference']-saved['truePositive']: raise ValueError('Pipeline FP/FN recount drift')
    train_predictions = c.read_jsonl(RUN/'new22_train_predictions.jsonl')
    if training.old.diagnostic.scored(added, train_predictions) != comparison['new22TrainDiagnostic']['new57'] or len(c.read_jsonl(RUN/'new22_train_errors.jsonl')) != sum(r['label'] != p['label'] for r, p in zip(added, train_predictions)): raise ValueError('TRAIN22 accounting drift')
    summaries = []
    for folder in (AUTHOR, CONCEPT):
        manifest = g.verified_files(folder)
        if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Identity/concept provenance drift')
        summaries.append(read(folder/'summary.json'))
    author, concept = summaries
    if (author['signaturesExamined'], author['identityLinksChanged'], author['remainingUnresolved'], author['changedRejectionReasons']) != (88762, 0, 9062, 4) or concept['kind'] != 'candidate_not_graph_migration' or concept['actualNodeReductions'] != 0 or concept['graphMigrated']: raise ValueError('Candidate audit scope drift')
    suites = list(ET.parse(TESTS).getroot().iter('testsuite')); counts = {k: sum(int(s.get(k, 0)) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
    if not counts['tests'] or any(counts[k] for k in ('failures', 'errors', 'skipped')): raise ValueError('Regression not clean')
    coverage = read(COVERAGE)
    changes = []
    for kind in ('module_dev', 'pipeline'):
        before = c.read_jsonl(RUN/('old_'+kind+'_predictions.jsonl')); after = c.read_jsonl(RUN/('new_'+kind+'_predictions.jsonl'))
        if [p['pairId'] for p in before] != [p['pairId'] for p in after]: raise ValueError('Same-scope prediction comparison drift')
        source_ids = {d['sampleId']: d['publicationId'] for d in data['dev']['ner']}
        changes += [a | {'scope': kind, 'sourcePublicationId': source_ids[a['sampleId']], 'beforeLabel': b['label'], 'afterLabel': a['label']} for b, a in zip(before, after) if b['label'] != a['label']]
    pipeline_changes = [p for p in changes if p['scope'] == 'pipeline']
    state = {'training': {'pairs': 408, 'epochs': 6, 'steps': 612, 'bestCheckpoint': fit['bestCheckpoint'], 'checkpointSha256': c.file_sha256(RUN/'re'/fit['bestCheckpoint']/'model.safetensors')}, 'comparison': comparison, 'author': author, 'concept': concept, 'tests': counts, 'coveragePercent': coverage['totals']['percent_covered'], 'predictionChanges46To57': changes, 'changedPipelineSourceDocuments': len({p['sampleId'] for p in pipeline_changes}), 'testContentConsumed': False, 'modelPromoted': False, 'liveApplicationChecked': False}
    return state, steps, epochs


def prepare():
    if OUTPUT.exists(): raise FileExistsError('Preserve57 evidence and captures')
    state, steps, epochs = checked(); comparison = state['comparison']; now = datetime.now(UTC).isoformat()
    sources = [RUN/'manifest.json', AUTHOR/'manifest.json', CONCEPT/'manifest.json', TESTS, COVERAGE, Path(__file__), c.ROOT/'scripts/export_course_evidence.py', c.ROOT/'tests/conftest.py', c.ROOT/'kg_datasets/dblp/course_v4_runs/tests_quality57_final.xml']
    paths = [p.relative_to(c.ROOT).as_posix() for p in sources]; hashes = {p.relative_to(c.ROOT).as_posix(): c.file_sha256(p) for p in sources}
    body = '<p>固定52 NER、原15 RE初始化；仅训练标签386→408，未知1,949对不填负例。旧开发数据原字节保持，预留19篇最终测试只校验二进制哈希。</p>'
    body += table(['实际训练', '记录'], [('训练对/轮/步', '408 / 6 / 612'), ('选定单检查点', state['training']['bestCheckpoint']), ('选型', '原333已知dev对，all-class macro，最早并列'), ('权重重载/编码器与分类头', '预测一致 / 两者已更新'), ('步数解释', '582→612随数据增加，不是等步数对照'), ('最终测试/上线', '未消费 / 未晋级')])
    body += '<h2>工程检查不是语义金标准</h2>' + table(['相关回归', '计数'], list(state['tests'].items()))
    body += f'<p>新三个入口联合单元+实际运行行覆盖：{state["coveragePercent"]:.2f}%。不等于模型正确率、全面故障注入或线上验收。</p>'
    pages = {'01_data.html': page('第57轮 · 真实训练与隔离记录', body, now, paths)}
    body = table(['epoch', '累计步数', 'dev宏F1', '更新最佳'], [(e['epoch'], e['steps'], f'{training.re_model.selection_score(e["dev"]["metrics"], "all_class_macro"):.2%}', e['checkpointImproved']) for e in epochs])
    body += '<h2>实际612步损失</h2>' + (loss_curve(steps) if all(s['loss'] > 0 for s in steps) else '<p>存在精确零损失，保留原日志；不静默删点绘制对数图。</p>')
    body += '<p class="notice">训练损失和训练侧标签吻合不能证明泛化；开发集已暴露且选择过多个历史版本，不能当独立最终测试。</p>'
    pages['02_training.html'] = page('第57轮 · 六轮GPU训练记录', body, now, paths)
    models = [('固定52NER+46RE重推理', comparison['pipeline']['old'], comparison['module']['old']), ('54封存预测重算', comparison['cached54']['pipeline'], comparison['cached54']['module']), ('固定52NER+57RE重推理', comparison['pipeline']['new'], comparison['module']['new'])]
    body = table(['同7篇/84正参考', 'TP/预测', 'P', 'R', 'F1', 'FP/FN', '模块负例召回'], [(name, f'{m["positiveMicro"]["truePositive"]}/{m["positiveMicro"]["predicted"]}', *(f'{m["positiveMicro"][k]:.2%}' for k in ('precision', 'recall', 'f1')), f'{m["positiveMicro"]["predicted"]-m["positiveMicro"]["truePositive"]}/{84-m["positiveMicro"]["truePositive"]}', f'{module["perClass"]["NO_RELATION"]["recall"]:.2%}') for name, m, module in models])
    diagnostic = comparison['new22TrainDiagnostic']; body += '<h2>新增22对：TRAIN拟合诊断</h2>'
    body += table(['模型', '用途正确/19', '角色负例正确/3'], [(name, v['positiveTaskCorrect'], v['negativeContrastCorrect']) for name, v in diagnostic['frozen46_54Cache'].items()] + [('57', diagnostic['new57']['perClass']['USED_FOR']['truePositive'], diagnostic['new57']['perClass']['NO_RELATION']['truePositive'])])
    body += f'<p>相对46版仅2条Pipeline预测改变，来自{state["changedPipelineSourceDocuments"]}篇；正确检出仍59、漏检仍25，不是普遍跨论文泛化提升。模块6条预测改变，纠正3条但新增3条错判，总分相同不代表逐条相同。</p>'
    body += '<p class="notice">完整开发评测关系支持0、文档覆盖7/19仍阻断晋级。三个新负例来自同一训练论文；AI参考不是独立人工金标准。全量FP/FN、所有预测与概率保留，未自动升级。</p>'
    pages['03_predictions.html'] = page('第57轮 · 同范围端到端对比', body, now, paths)
    body = '<p>作者诊断读取既有库存，没有联网或扫描XML，没有更改身份链接。</p>' + table(['署名复核', '拒绝原因修正', 'ORCID冲突', '未决署名', '新增链接'], [(88762, 4, '2→1', 9062, 0)])
    groups = c.read_jsonl(CONCEPT/'groups.jsonl'); body += '<h2>类型受控概念候选，不是已迁移图</h2>' + table(['候选组', '本文证据状态', '原概念', '提及'], [(r['canonical'], r['status'], len(r['sourceConcepts']), r['mentionCount']) for r in groups])
    body += '<p class="notice">11概念/30提及，6是潜在节点减少，实际减少0。GRU/CRF需本文展开证据；未使用摘要，不跨METHOD/TASK合并，不合并具体模型变体。当前v2、作者身份、图谱和应用配置原字节保持。本轮未重验Neo4j/HTTP。</p>'
    pages['04_traceability.html'] = page('第57轮 · 作者拒绝账目与概念候选', body, now, paths)
    OUTPUT.mkdir(parents=True)
    for name, content in pages.items(): (OUTPUT/name).write_text(content, encoding='utf-8')
    c.write_json(OUTPUT/'audit_state.json', state)
    c.write_jsonl(OUTPUT/'prediction_changes_46_to57.jsonl', state['predictionChanges46To57'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Evidence source drift')
    c.write_json(OUTPUT/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'inputSha256': hashes, 'filesSha256': {p.name: c.file_sha256(p) for p in OUTPUT.iterdir()}})
    print({'prepared': True, 'tests': state['tests'], 'steps': 612, 'modelPromoted': False}, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('check', 'prepare')); args = parser.parse_args()
    if args.action == 'prepare': prepare()
    else: print({'checked': True, 'steps': checked()[0]['training']['steps'], 'modelPromoted': False}, flush=True)
