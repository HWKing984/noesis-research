"""Recompute TRAIN role diagnostics and seal actual browser artifact captures."""
import argparse
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT/'scripts'))
import diagnose_train_roles as diagnostic
from course_abstract_v1 import read
from export_course_evidence import page, table

c, g, role, prior = diagnostic.c, diagnostic.g, diagnostic.role, diagnostic.prior
SOURCE = diagnostic.SOURCE
RUNS = ROOT/'kg_datasets/dblp/course_v4_runs'
RUN = RUNS/'role_diagnostic_20261009_53'
EVIDENCE = ROOT/'docs/evidence/20261009_round53'
JUNIT = RUNS/'tests_20261009_round53.xml'


def checked():
    added, original, _ = diagnostic.load_inputs(); config, _, refs, old = role.load_sources()
    manifest = g.verified_files(RUN)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    assert read(RUN/'status.json')['status'] == 'completed'
    receipts = c.read_jsonl(SOURCE/'reviewed_receipts.jsonl'); docs, pairs, full, excluded, unknown, total = role.rows_for(refs, receipts)
    assert pairs == c.read_jsonl(SOURCE/'relation_train.jsonl') and full == c.read_jsonl(SOURCE/'full_relation_train.jsonl') and excluded == c.read_jsonl(SOURCE/'excluded_ner_train.jsonl')
    assert refs == c.read_jsonl(SOURCE/'references.jsonl') and len(refs) == len(receipts) == 70
    assert all(receipt == parent for ref, receipt, parent in zip(refs, receipts, old) if ref['arxivId'] not in config['revisionCohort'])
    old_by_key = {role.re_model.pair_key(p): p for p in original}
    assert all(p == old_by_key[role.re_model.pair_key(p)] for p in pairs if role.re_model.pair_key(p) in old_by_key)
    assert len(old_by_key) == 271 and len(pairs) == 386
    assert [p for p in pairs if role.re_model.pair_key(p) in old_by_key] == original
    assert [p for p in pairs if role.re_model.pair_key(p) not in old_by_key] == added
    assert (len(docs), sum(len(d['entities']) for d in docs), len(excluded), unknown, total) == (65, 787, 5, 1971, 2357)
    parent = ROOT/config['snapshot']; frozen = c.read_jsonl(SOURCE/'ner_train_frozen.jsonl')
    assert c.file_sha256(parent/'ner_train.jsonl') == c.file_sha256(SOURCE/'ner_train_frozen.jsonl')
    assert [(d['sampleId'], d['textSha256'], d['entities']) for d in docs] == [(d['sampleId'], d['textSha256'], d['entities']) for d in frozen]
    dev = [p for p in parent.iterdir() if p.is_file() and 'dev' in p.stem]
    assert len(dev) == 9 and all(c.file_sha256(p) == c.file_sha256(SOURCE/p.name) for p in dev)
    result = read(RUN/'diagnostic_result.json'); predictions = c.read_jsonl(RUN/'predictions.jsonl')
    assert added == c.read_jsonl(RUN/'inputs.jsonl') and diagnostic.scored(added, predictions) == result['model']
    mapping = role.re_model.type_majority(original)
    assert prior.dev_scope(role.re_model.score_relations(added, [mapping[r['tail']['label']] for r in added]), diagnostic.TARGET) == result['typeMajorityBaselineFromOld271']
    errors = c.read_jsonl(RUN/'errors.jsonl'); wrong = [(r, p) for r, p in zip(added, predictions) if r['label'] != p['label']]
    assert len(errors) == len(wrong) == result['modelErrors'] == 12
    for error, (ref, pred) in zip(errors, wrong):
        assert all(error[k] == ref[k] for k in ('sampleId', 'publicationId', 'textSha256', 'head', 'tail', 'evidence'))
        assert error['pairId'] == pred['pairId'] and error['referenceLabel'] == ref['label'] and error['referenceReason'] == ref['reason'] and error['predictedLabel'] == pred['label'] and error['modelScores'] == pred['probabilities']
    assert result['newReferenceSupport'] == dict(Counter(r['label'] for r in added)) == {'USED_FOR': 104, 'EVALUATED_ON': 3, 'NO_RELATION': 8}
    assert result['negativeContrastCorrect'] == sum(r['label'] == p['label'] == 'NO_RELATION' for r, p in zip(added, predictions)) == 0
    assert result['pipelineMetrics'] is None and all(result[k] is False for k in ('trainingExecuted', 'devContentAccessed', 'testContentConsumed', 'independentHumanGold', 'modelPromoted', 'qualityPromotionPassed'))
    support = {label: len({r['sampleId'] for r in added if r['label'] == label}) for label in role.re_model.LABELS}
    assert support['NO_RELATION'] == 3 and support['EVALUATED_ON'] == 1
    suites = ET.parse(JUNIT).getroot().findall('testsuite'); totals = {k: sum(int(s.get(k, '0')) for s in suites) for k in ('tests', 'errors', 'failures', 'skipped')}
    assert totals == {'tests': 390, 'errors': 0, 'failures': 0, 'skipped': 0}
    audit = {'passed': True, 'newKnownRelations': 115, 'trainKnown': 386, 'unknown': unknown, 'eligibleTrainPairs': total, 'knownTrainCoverage': 386/total,
        'NERtrainPreserved': 65, 'NERentitiesPreserved': 787, 'NERquarantinesPreserved': 5, 'inheritedKnownRelationsUnchanged': 271, 'opaqueDevFilesPreserved': 9, 'inheritedReceiptsPreserved': 59,
        'newClassSourceDocuments': support, 'diagnostic': result, 'dataManifestSha256': c.file_sha256(SOURCE/'manifest.json'), 'runManifestSha256': c.file_sha256(RUN/'manifest.json'),
        'engineeringTests': totals, 'regressionSeconds': sum(float(s.get('time', '0')) for s in suites), 'trainingExecuted': False, 'testContentConsumed': False, 'modelPromoted': False, 'qualityPromotionPassed': False,
        'authorWorkPerformed': False, 'conceptWorkPerformed': False, 'onlineAcceptancePerformed': False, 'reportExpansionPaused': True}
    return audit, errors, added


def prepare():
    audit, errors, added = checked()
    if EVIDENCE.exists(): raise FileExistsError('Preserve evidence')
    EVIDENCE.mkdir(parents=True); c.write_json(EVIDENCE/'audit_state.json', audit); c.write_jsonl(EVIDENCE/'all_diagnostic_errors.jsonl', errors)
    stamp = datetime.now(UTC).isoformat()
    body = '<p>11篇训练摘要先锁来源、实际源文初判与同会话AI复核，再封存数据并运行旧RE；没有修改标签来适配模型输出。复用部分标注/收据/编码器，未知不填负，组件不继承整体模型评测。</p>'
    body += table(['库存', '实际'], [['明确训练关系', '271→386：用途288 / 评测64 / 负例34'], ['本轮新增', '115：用途104 / 评测3 / 角色负例8'], ['未决与覆盖', '1,971 / 2,357候选仍未知；已判16.38%'], ['冻结库存', '65篇NER / 787提及 / 5隔离；旧271关系完整行不变'], ['来源支持', '新增评测3条仅1论文；8负例来自3论文，重复跨度非独立样本'], ['范围保护', '9开发文件原字节保留；19篇保留测试只二进制哈希，不解析']])
    refs = c.read_jsonl(SOURCE/'references.jsonl'); counts = {ref['arxivId']: Counter(r['label'] for r in added if r['sampleId'] == ref['sampleId']) for ref in refs}
    body += '<h2>固定11来源的新增判断</h2>'+table(['arXiv ID', '用途', '评测', '负例'], [[arxiv, counts[arxiv]['USED_FOR'], counts[arxiv]['EVALUATED_ON'], counts[arxiv]['NO_RELATION']] for arxiv in read(role.CONTRACT)['revisionCohort']])
    body += '<p>LUKE没有明确具名的被评测整体方法，不把架构组件或标题名称自动补为摘要实体/评测边；DocRED无方法实体，是零候选文档，不制造负例。训练/预训练提及、背景共现、较差性能不自动判NO_RELATION。角色负例只是本篇明确阶段/操作对象的局部对照，不是通用“不可能”断言。</p>'
    body += '<p>旧NER收据独立绑定52输入，53只新增RE收据。390项工程回归通过（0失败/错误/跳过），不是390项语义正确性证明。没有新模型训练、开发指标或图谱导入。</p>'
    (EVIDENCE/'09_annotation_expansion.html').write_text(page('训练关系证据与未决库存 · 第53轮', body, stamp, [str(SOURCE/'summary.json'), str(SOURCE/'role_ledger.jsonl'), str(JUNIT)]), encoding='utf-8')
    result = audit['diagnostic']; body = '<p>全115对新增训练参考，使用冻结46 RE和参考实体；不是未见开发/最终测试、NER→RE完整Pipeline或生产准确率。无拟合、阈值搜索或模型选择。</p>'
    body += table(['TRAIN条件诊断', '一致率', '正Precision', '正Recall', '正F1', '负例正确'], [[name, f"{m['accuracy']:.2%}", f"{m['positiveMicro']['precision']:.2%}", f"{m['positiveMicro']['recall']:.2%}", f"{m['positiveMicro']['f1']:.2%}", '0/8'] for name, m in (('冻结46 RE', result['model']), ('旧271对类型多数基线', result['typeMajorityBaselineFromOld271']))])
    body += '<h2>混淆矩阵：行是参考，列是预测</h2>'+table(['参考/预测']+result['model']['confusionLabels'], [[label]+row for label, row in zip(result['model']['confusionLabels'], result['model']['confusionMatrix'])])
    body += '<p>8角色负例全部误报用途；另4用途漏判。正例占107/115且类型限制较强，总体94.50%不能证明语义理解，简单类型基线96.40%反而更高；3评测全部正确但仅1源论文、基线也全对，不能证明稀有关系泛化。</p>'
    body += '<h2>完整12条错例（原文证据与分数另存JSONL）</h2>'+table(['论文', '方法提及', '任务提及', '参考→预测'], [[e['publicationId'].replace('journals/corr/abs-', ''), e['head']['text'], e['tail']['text'], e['referenceLabel']+' → '+e['predictedLabel']] for e in errors])
    body += '<p>AWD为蒸馏操作方法，源神经网络/输出小波变换不是本篇蒸馏操作者；模型仍将操作对象连成用途关系。另一流水线中关系阶段的实体信息融合被错误连到实体识别任务，softmax接近1仍是错例，分数不是事实正确概率。</p>'
    body += '<p>没有新完整Pipeline成绩。52的119错报中108涉及端点错配，RE不是唯一问题；当前历史完整EVAL参考0、覆盖7/19，补充完整0/8仍不足。拒绝模型晋级，旧线上模型/图/8765/8766不改；作者与概念保持51状态，报告暂停。</p>'
    (EVIDENCE/'07_relation_development.html').write_text(page('冻结RE角色诊断：8负例全部错判 · 第53轮', body, stamp, [str(RUN/'diagnostic_result.json'), str(RUN/'predictions.jsonl'), 'all_diagnostic_errors.jsonl']), encoding='utf-8')
    paths = [Path(__file__), ROOT/'scripts/capture_course_evidence.ps1', ROOT/'scripts/export_course_evidence.py', JUNIT, ROOT/'README.md']
    paths += [ROOT/'docs'/n for n in ('quality_iteration_round53.md', 'system_status_round53.md', 'course_v4_plan.md', 'course_v4_runbook.md', 'status_log.md', 'model_optimization_abstract_v1.md')]
    for folder in (SOURCE, RUN):
        paths += [p for p in folder.rglob('*') if p.is_file()]
        paths += [ROOT/p for p in g.verified_files(folder)['inputSha256'] if not p.endswith('.safetensors') and not p.endswith('/test_references.jsonl')]
    paths = list(dict.fromkeys(paths))
    for p in paths:
        target = EVIDENCE/'sources'/p.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, target)
    c.write_json(EVIDENCE/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'inputSha256': {p.relative_to(ROOT).as_posix(): c.file_sha256(p) for p in paths}, 'filesSha256': {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})


def finish():
    audit, _, _ = checked(); manifest = g.verified_files(EVIDENCE)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    captures = json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig'))
    assert captures['status'] == 'completed' and {x['sourcePage'] for x in captures['captures']} == {'09_annotation_expansion.html', '07_relation_development.html'} and len(captures['captures']) == 2 and captures['originalConsoleScreenshot'] is False
    for item in captures['captures']:
        assert c.file_sha256(EVIDENCE/item['image']) == item['sha256'] and manifest['filesSha256'][item['sourcePage']] == item['sourcePageSha256']
    c.write_json(EVIDENCE/'capture_verification.json', {'passed': True, 'actualBrowserCaptures': 2, 'originalConsoleScreenshot': False, 'roleInventoryAndDiagnosticRecomputed': True, 'qualityPromotionPassed': False})
    manifest['filesSha256'] = {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file() and p != EVIDENCE/'manifest.json'}
    c.write_json(EVIDENCE/'manifest.json', manifest)
    c.write_json(RUNS/'verification_20261009_round53.json', audit | {'evidenceManifestSha256': c.file_sha256(EVIDENCE/'manifest.json'), 'actualBrowserCaptures': 2})
    print({'verified': True, 'engineeringTests': 390, 'newKnownRelations': 115, 'negativeContrastCorrect': 0, 'modelPromoted': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('prepare', 'finish')); args = parser.parse_args()
    (prepare if args.action == 'prepare' else finish)()
