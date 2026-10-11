"""Recompute the fixed-NER RE experiment and seal actual artifact captures."""
import argparse
import json
import math
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT/'scripts'))
import train_role_abstract_relation as training
from course_abstract_v1 import read
from export_course_evidence import page, table

c, g, prior = training.c, training.g, training.prior
RUNS = ROOT/'kg_datasets/dblp/course_v4_runs'
RUN = RUNS/'abstract_role_development_20261009_54'
EVIDENCE = ROOT/'docs/evidence/20261009_round54_complete'
JUNIT = RUNS/'tests_20261009_round54.xml'


def loss_curve(steps):
    values = [s['loss'] for s in steps]
    if len(values) < 2 or [s['step'] for s in steps] != list(range(1, len(values)+1)) or any(not math.isfinite(v) or v < 0 for v in values): raise ValueError('Linear chart requires ordered finite nonnegative actual losses')
    upper = max(1.0, max(values)); y = lambda v: 40+230*(1-v/upper)
    points = ' '.join(f'{70+810*i/(len(values)-1):.2f},{y(v):.2f}' for i, v in enumerate(values))
    return (f'<svg viewBox="0 0 940 315" role="img" aria-label="实际逐步训练损失，线性刻度保留零值">'
            f'<line x1="70" y1="270" x2="880" y2="270" stroke="#dae3ef"/><text x="12" y="275">0</text>'
            f'<text x="12" y="45">{upper:.2f}</text><polyline fill="none" stroke="#2463bc" stroke-width="2.5" points="{points}"/>'
            f'<text x="70" y="300">step 1</text><text x="790" y="300">step {len(values)}</text></svg>')


def checked():
    config, parent, _, data, _, added = training.load_inputs(); manifest = g.verified_files(RUN)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    assert read(RUN/'status.json')['status'] == 'completed'
    result = read(RUN/'development_result.json'); fit = result['RE']; comparison = read(RUN/'comparison.json')
    assert result['comparison'] == comparison and fit['steps'] == 582 and fit['epochs'] == 6 and fit['savedCheckpoints'] == 1
    assert fit['classifierAndEncoderChanged'] and fit['reloadPredictionsIdentical'] and not fit['devUsedForGradient'] and not fit['NERTrained']
    assert all(result[k] is False for k in ('modelPromoted', 'qualityPromotionPassed', 'testEvaluated'))
    assert '270.00' in loss_curve([{'step': 1, 'loss': 0.0}, {'step': 2, 'loss': 1.0}])
    for invalid in (-1.0, float('nan'), float('inf')):
        try: loss_curve([{'step': 1, 'loss': 0.0}, {'step': 2, 'loss': invalid}])
        except ValueError: pass
        else: raise AssertionError('Invalid chart loss accepted')
    steps = c.read_jsonl(RUN/'re/steps.jsonl'); epochs = read(RUN/'re/epochs.json'); ids = {training.re_model.pair_id(r) for r in data['train']['relation']}
    assert [s['step'] for s in steps] == list(range(1, 583)) and len(list((RUN/'re').glob('checkpoint_*'))) == 1
    for epoch in range(1, 7):
        inputs = [i for s in steps if s['epoch'] == epoch for i in s['inputIds']]
        assert len(inputs) == len(set(inputs)) == 386 and set(inputs) == ids and len([s for s in steps if s['epoch'] == epoch]) == 97
    selected = max(epochs, key=lambda e: training.re_model.selection_score(e['dev']['metrics'], 'all_class_macro'))
    assert fit['bestCheckpoint'] == f"checkpoint_epoch_{selected['epoch']:02d}" and fit['bestDev'] == selected['dev']
    assert all(c.read_jsonl(RUN/f're/{split}_inputs.jsonl') == data[split]['relation'] for split in ('train', 'dev'))
    ner_predictions = c.read_jsonl(RUN/'frozen_ner_dev_predictions.jsonl')
    assert [p['sampleId'] for p in ner_predictions] == [r['sampleId'] for r in data['dev']['ner']]
    assert training.ner.score_rows(data['dev']['ner'], [p['predictedEntities'] for p in ner_predictions], evaluation_target=prior.TARGET) == comparison['NER']['metrics']
    full = data['dev']['full_relation']; full_ids = {d['sampleId'] for d in full}; refs = [p for p in data['dev']['relation'] if p['sampleId'] in full_ids]
    assert full == c.read_jsonl(RUN/'pipeline_dev_documents.jsonl') and refs == c.read_jsonl(RUN/'pipeline_dev_reference_pairs.jsonl')
    by_id = {p['sampleId']: p['predictedEntities'] for p in ner_predictions}; candidates = [p for d in full for p in prior.candidate_rows(d, by_id[d['sampleId']])]
    for name in ('old', 'new'):
        module = c.read_jsonl(RUN/(name+'_module_dev_predictions.jsonl'))
        assert [p['pairId'] for p in module] == [training.re_model.pair_id(r) for r in data['dev']['relation']]
        assert prior.dev_scope(training.re_model.score_relations(data['dev']['relation'], [p['label'] for p in module])) == comparison['module'][name]
        predictions = c.read_jsonl(RUN/(name+'_pipeline_predictions.jsonl'))
        assert [p['pairId'] for p in predictions] == [training.re_model.pair_id(r) for r in candidates]
        metrics = prior.dev_scope(prior.score_pipeline(full, refs, predictions), 'complete_document_exposed_dev_AI_reference_not_final_test')
        causes, false = training.error_summary(full, refs, predictions)
        missed = [e for d in full for e in prior.diagnose(d, by_id[d['sampleId']], [p for p in refs if p['sampleId'] == d['sampleId']], [p for p in predictions if p['sampleId'] == d['sampleId']])]
        metrics.update(entityScope='fixed52_predicted_NER_entities', endpointMismatch=causes, missedReferencePrimaryCauses=dict(Counter(e['primaryCause'] for e in missed)))
        assert metrics == comparison['pipeline'][name] and false == c.read_jsonl(RUN/(name+'_false_relations.jsonl')) and missed == c.read_jsonl(RUN/(name+'_missed_relations.jsonl'))
        assert len(false) == metrics['positiveMicro']['predicted']-metrics['positiveMicro']['truePositive'] and len(missed) == 84-metrics['positiveMicro']['truePositive']
        train_predictions = c.read_jsonl(RUN/(name+'_new_train_predictions.jsonl'))
        assert training.diagnostic.scored(added, train_predictions) == comparison['newTrainDiagnostic'][name]
        assert [{'reference': r, 'prediction': p} for r, p in zip(added, train_predictions) if r['label'] != p['label']] == c.read_jsonl(RUN/(name+'_new_train_errors.jsonl'))
    transitions = {}
    for scope, rows in (('module', data['dev']['relation']), ('pipeline', candidates)):
        old = c.read_jsonl(RUN/('old_'+('module_dev' if scope == 'module' else 'pipeline')+'_predictions.jsonl'))
        new = c.read_jsonl(RUN/('new_'+('module_dev' if scope == 'module' else 'pipeline')+'_predictions.jsonl'))
        transitions[scope] = [{'pairId': o['pairId'], 'sampleId': r['sampleId'], 'head': r['head'], 'tail': r['tail'], 'old': o['label'], 'new': n['label']} | ({'referenceLabel': r['label']} if scope == 'module' else {}) for r, o, n in zip(rows, old, new) if o['label'] != n['label']]
    assert len(transitions['module']) == 9 and len(transitions['pipeline']) == 4
    assert training.gates(parent, data, comparison['pipeline'], comparison['module'], comparison['NER']['metrics']) == comparison['gates']
    suites = ET.parse(JUNIT).getroot().findall('testsuite'); totals = {k: sum(int(s.get(k, '0')) for s in suites) for k in ('tests', 'errors', 'failures', 'skipped')}
    assert totals == {'tests': 391, 'errors': 0, 'failures': 0, 'skipped': 0}
    audit = {'passed': True, 'trainingExecuted': True, 'NERTrained': False, 'REtrain': 386, 'REsteps': 582, 'REepochs': 6, 'selectedEpoch': selected['epoch'], 'savedCheckpoints': 1,
        'preflight': read(RUN/'preflight.json'), 'module': comparison['module'], 'pipeline': comparison['pipeline'], 'newTrainDiagnostic': comparison['newTrainDiagnostic'], 'gates': comparison['gates'],
        'frozenNER': comparison['NER'], 'allLabelTransitions': transitions, 'originalTrainNERAndDevUnchanged': True, 'unresolvedTrainPairsExcluded': 1971, 'testContentConsumed': False, 'modelPromoted': False, 'qualityPromotionPassed': False,
        'runManifestSha256': c.file_sha256(RUN/'manifest.json'), 'engineeringTests': totals, 'regressionSeconds': sum(float(s.get('time', '0')) for s in suites),
        'authorWorkPerformed': False, 'conceptWorkPerformed': False, 'onlineAcceptancePerformed': False, 'reportExpansionPaused': True}
    return audit, steps, epochs


def prepare():
    audit, steps, epochs = checked()
    if EVIDENCE.exists(): raise FileExistsError('Preserve evidence')
    EVIDENCE.mkdir(parents=True); c.write_json(EVIDENCE/'audit_state.json', audit); stamp = datetime.now(UTC).isoformat()
    for scope, rows in audit['allLabelTransitions'].items(): c.write_jsonl(EVIDENCE/('all_'+scope+'_label_transitions.jsonl'), rows)
    body = '<style>svg{max-height:240px}td,th{padding:6px 10px}</style><p>只改变RE训练数据271→386；冻结52 NER和46 RE基线，原15初始化，固定六轮/batch4/lr2e-5/seed20261008。未知1,971对不进损失，开发无梯度，保留测试只二进制哈希。</p>'
    body += table(['实际训练', '记录'], [['训练/开发', '386训练对 / 333已判开发对；原开发字节不改'], ['步数', '6轮 × 97批 = 582步；旧46为408步，数据量引起步数/类别权重变化'], ['检查点', f"三类开发宏F1选第{audit['selectedEpoch']}轮、最早平分；只保存1个，重载一致，编码器/分类头已更新"], ['资源储备', '磁盘/CPU/GPU预检通过，1GB磁盘储备不变，历史不删除'], ['限制', '无中间恢复；Pipeline和新增训练115对不选检查点，无调参/阈值搜索']])
    body += f"<p>损失曲线使用线性刻度，保留{sum(s['loss'] == 0 for s in steps)}个真实FP32零值，不设epsilon、不改日志。首次对数图拒绝零值的失败目录另存。</p><h2>真实逐步损失</h2>"+loss_curve(steps)
    body += table(['Epoch', '累计步数', '开发三类宏F1', '改善'], [[e['epoch'], e['steps'], f"{training.re_model.selection_score(e['dev']['metrics'], 'all_class_macro'):.2%}", e['checkpointImproved']] for e in epochs])
    body += '<p>391项工程回归通过，0失败/错误/跳过；不是391项语义正确性证明。AI同会话自复核不是独立人工gold，开发集已暴露，不能当盲测。没有生产模型/图谱/服务变更。</p>'
    (EVIDENCE/'02_training.html').write_text(page('固定NER的一次真实RE训练 · 第54轮', body, stamp, [str(RUN/'re/steps.jsonl'), str(RUN/'re/epochs.json'), str(RUN/'preflight.json')]), encoding='utf-8')
    body = '<p>同一冻结52 NER、同7篇完整开发、同84条参考正关系。所有预测对都计入评分，不过滤参考端点；完整零候选文档也保留。新旧RE各一次重新推理，基线重现52结果。</p>'
    body += table(['同范围Pipeline', 'Precision', 'Recall', 'F1', 'TP/预测/参考', 'FP/FN'], [[name, f"{m['positiveMicro']['precision']:.2%}", f"{m['positiveMicro']['recall']:.2%}", f"{m['positiveMicro']['f1']:.2%}", f"{m['positiveMicro']['truePositive']}/{m['positiveMicro']['predicted']}/84", f"{m['positiveMicro']['predicted']-m['positiveMicro']['truePositive']}/{84-m['positiveMicro']['truePositive']}"] for name, m in audit['pipeline'].items()])
    body += '<h2>参考实体条件模块：不能替代Pipeline</h2>'+table(['333已判开发对', '正P', '正R', '正F1', '三类宏F1', '负例Recall'], [[name, f"{m['positiveMicro']['precision']:.2%}", f"{m['positiveMicro']['recall']:.2%}", f"{m['positiveMicro']['f1']:.2%}", f"{training.re_model.selection_score(m, 'all_class_macro'):.2%}", f"{m['perClass']['NO_RELATION']['recall']:.2%}"] for name, m in audit['module'].items()])
    body += '<h2>新增115对的训练侧拟合诊断</h2>'+table(['TRAIN参考实体', '正F1', '8角色负例正确', '3评测正确'], [[name, f"{m['positiveMicro']['f1']:.2%}", f"{m['perClass']['NO_RELATION']['truePositive']}/8", f"{m['perClass']['EVALUATED_ON']['truePositive']}/3"] for name, m in audit['newTrainDiagnostic'].items()])
    body += '<p>训练反例来自3论文，新增评测来自1论文；重复提及相关。训练侧学会与未见泛化严格分开，不能拿它作最终准确率。未决1971不填负例，开发模块仅333/432已判对，不能推断全部候选正确率。</p>'
    body += '<p>本轮实际未改善：Pipeline F1 45.04%→44.36%、错报119→123，开发负例Recall50.00%→39.39%。条件模块9对标签改变（8新错/1纠正），Pipeline4对改变均成为额外错报、集中同一篇AI4Science摘要；全部变化账本另存，不挑例、不按开发词汇补规则或回改标签。</p>'
    body += '<h2>护栏与未晋级</h2>'+table(['护栏', '通过'], list(audit['gates']['checks'].items()))
    body += '<p>完整开发EVALUATED_ON参考0、覆盖7/19=36.84%，补充49完整0/8，仍不足以质量晋级；没有新的最终测试。NER冻结，边界/类别错配仍可能传递，保留全部错报/漏报，不按已见开发改规则。</p>'
    body += table(['Pipeline', '错报端点原因', '漏报主因'], [[name, json.dumps(m['endpointMismatch'], ensure_ascii=False), json.dumps(m['missedReferencePrimaryCauses'], ensure_ascii=False)] for name, m in audit['pipeline'].items()])
    (EVIDENCE/'07_relation_development.html').write_text(page('固定实体模型的新旧RE端到端对照 · 第54轮', body, stamp, [str(RUN/'comparison.json'), str(RUN/'new_false_relations.jsonl'), str(RUN/'new_missed_relations.jsonl')]), encoding='utf-8')
    paths = [Path(__file__), ROOT/'scripts/capture_course_evidence.ps1', ROOT/'scripts/export_course_evidence.py', JUNIT, ROOT/'README.md']
    paths += [p for p in (ROOT/'docs/evidence/20261009_round54').iterdir() if p.is_file()]
    paths += [ROOT/'docs/evidence/20261009_round54_final'/n for n in ('visual_review.json', 'captures.json', '02_training.png', '07_relation_development.png')]
    paths += [ROOT/'docs'/n for n in ('quality_iteration_round54.md', 'system_status_round54.md', 'course_v4_plan.md', 'course_v4_runbook.md', 'status_log.md', 'model_optimization_abstract_v1.md')]
    paths += [p for p in RUN.rglob('*') if p.is_file() and p.suffix != '.safetensors']
    paths += [ROOT/p for p in g.verified_files(RUN)['inputSha256'] if not p.endswith('.safetensors') and not p.endswith('/test_references.jsonl')]
    paths = list(dict.fromkeys(paths))
    for p in paths:
        target = EVIDENCE/'sources'/p.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, target)
    c.write_json(EVIDENCE/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'inputSha256': {p.relative_to(ROOT).as_posix(): c.file_sha256(p) for p in paths}, 'filesSha256': {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})


def finish():
    audit, _, _ = checked(); manifest = g.verified_files(EVIDENCE)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    captures = json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig'))
    assert captures['status'] == 'completed' and {x['sourcePage'] for x in captures['captures']} == {'02_training.html', '07_relation_development.html'} and len(captures['captures']) == 2 and captures['originalConsoleScreenshot'] is False
    for item in captures['captures']:
        assert c.file_sha256(EVIDENCE/item['image']) == item['sha256'] and manifest['filesSha256'][item['sourcePage']] == item['sourcePageSha256']
    c.write_json(EVIDENCE/'capture_verification.json', {'passed': True, 'actualBrowserCaptures': 2, 'originalConsoleScreenshot': False, 'trainingAndComparisonsRecomputed': True, 'qualityPromotionPassed': False})
    manifest['filesSha256'] = {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file() and p != EVIDENCE/'manifest.json'}
    c.write_json(EVIDENCE/'manifest.json', manifest)
    c.write_json(RUNS/'verification_20261009_round54.json', audit | {'evidenceManifestSha256': c.file_sha256(EVIDENCE/'manifest.json'), 'actualBrowserCaptures': 2})
    print({'verified': True, 'engineeringTests': 391, 'REsteps': 582, 'selectedEpoch': audit['selectedEpoch'], 'modelPromoted': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('prepare', 'finish')); args = parser.parse_args()
    (prepare if args.action == 'prepare' else finish)()
