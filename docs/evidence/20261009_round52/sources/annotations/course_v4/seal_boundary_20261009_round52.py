"""Recompute saved development results, archive sources and seal actual artifact captures."""
import argparse
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT/'scripts'))
import train_boundary_abstract_ner as training
from course_abstract_v1 import read
from evaluate_abstract_decoder import error_summary
from export_course_evidence import page, table, loss_curve

c, g, prior = training.c, training.g, training.prior
RUNS = ROOT/'kg_datasets/dblp/course_v4_runs'
RUN = RUNS/'abstract_boundary_development_20261009_52'
EVIDENCE = ROOT/'docs/evidence/20261009_round52'
JUNIT = RUNS/'tests_20261009_round52.xml'


def checked():
    config, _, _, data = training.load_inputs(); manifest = g.verified_files(RUN)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    result = read(RUN/'development_result.json'); comparison = result['comparison']; fit = result['NER']
    assert read(RUN/'status.json')['status'] == 'completed' and fit['steps'] == 198 and fit['epochs'] == 6
    assert fit['bestCheckpoint'] == 'checkpoint_epoch_06' and fit['savedCheckpoints'] == 1 and fit['reloadPredictionsIdentical'] and fit['classifierAndEncoderChanged']
    assert not result['testEvaluated'] and not result['modelPromoted'] and not comparison['RETrained'] and not result['qualityPromotionPassed']
    steps = c.read_jsonl(RUN/'ner/steps.jsonl'); epochs = read(RUN/'ner/epochs.json'); ids = {r['sampleId'] for r in data['train']['ner']}
    assert [r['step'] for r in steps] == list(range(1, 199)) and all(set(r['inputIds']) <= ids for r in steps)
    assert all(len([s for s in steps if s['epoch'] == e]) == 33 for e in range(1, 7))
    assert max(epochs, key=lambda e: e['dev']['metrics']['micro']['f1'])['epoch'] == 6
    full = data['dev']['full_relation']; full_ids = {d['sampleId'] for d in full}; refs = [p for p in data['dev']['relation'] if p['sampleId'] in full_ids]
    supp = c.read_jsonl(ROOT/read(ROOT/'resources/course_abstract_boundary_expansion_v1.json')['supplement']/'ner_dev.jsonl')
    false = {}; endpoints = {}
    for name in ('old', 'new'):
        for scope, rows, filename in (('historicalNER', data['dev']['ner'], name+'_ner_dev_predictions.jsonl'), ('supplementNER', supp, name+'_supplement_ner_predictions.jsonl')):
            predictions = c.read_jsonl(RUN/filename)
            assert [p['sampleId'] for p in predictions] == [r['sampleId'] for r in rows]
            assert prior.ner.score_rows(rows, [p['predictedEntities'] for p in predictions], evaluation_target=prior.TARGET) == comparison[scope][name]['metrics']
        predictions = c.read_jsonl(RUN/(name+'_pipeline_predictions.jsonl'))
        scored = prior.score_pipeline(full, refs, predictions)
        assert scored['positiveMicro']['truePositive'] == comparison['historicalPipeline'][name]['positiveMicro']['truePositive']
        assert prior.dev_scope(scored['positiveMicro'], 'complete_document_exposed_dev_AI_reference_not_final_test') == comparison['historicalPipeline'][name]['positiveMicro']
        endpoints[name], false[name] = error_summary(full, refs, predictions)
        assert len(false[name]) == scored['positiveMicro']['predicted']-scored['positiveMicro']['truePositive'] == 119
    additional = c.read_jsonl(ROOT/config['snapshot']/'additional_references.jsonl')
    decisions = read(ROOT/'annotations/course_v4/abstract_boundary_decisions_20261009_52.json')['documents']
    assert [(d['arxivId'], d['textSha256']) for d in decisions] == [(r['arxivId'], r['textSha256']) for r in additional]
    initial = ROOT/'kg_datasets/dblp/course_abstract_boundary_sources_20261009_52'; retry = ROOT/'kg_datasets/dblp/course_abstract_boundary_sources_20261009_52_retry'
    assert read(initial/'summary.json')['usable'] == 7 and read(retry/'summary.json')['usable'] == 8
    old_text = {r['arxivId']: r['textSha256'] for r in c.read_jsonl(initial/'train_references.jsonl')}
    assert all(r['textSha256'] == old_text[r['arxivId']] for r in additional if r['arxivId'] in old_text)
    suites = ET.parse(JUNIT).getroot().findall('testsuite'); totals = {k: sum(int(s.get(k, '0')) for s in suites) for k in ('tests', 'errors', 'failures', 'skipped')}
    assert totals == {'tests': 388, 'errors': 0, 'failures': 0, 'skipped': 0}
    audit = {'passed': True, 'trainingExecuted': True, 'NERtrain': 65, 'NERsteps': 198, 'NERepochs': 6, 'selectedEpoch': 6, 'RETrained': False, 'addedNERDocuments': 7, 'newNERExcluded': 1,
        'entitySupport': {'METHOD': 458, 'TASK': 260, 'DATASET': 69}, 'frozenREFilesAndDevPreserved': 11,
        'runManifestSha256': c.file_sha256(RUN/'manifest.json'), 'engineeringTests': totals, 'regressionSeconds': sum(float(s.get('time', '0')) for s in suites),
        'historicalNER': comparison['historicalNER'], 'pipeline': comparison['historicalPipeline'], 'supplementNER': comparison['supplementNER'], 'endpointMismatch': endpoints,
        'gates': comparison['gates'], 'originalDevAndReservedTestUnchanged': True, 'testContentConsumed': False, 'modelPromoted': False, 'qualityPromotionPassed': False,
        'authorWorkPerformed': False, 'conceptWorkPerformed': False, 'reportExpansionPaused': True}
    return audit, false, steps, epochs


def prepare():
    audit, false, steps, epochs = checked()
    if EVIDENCE.exists(): raise FileExistsError('Preserve evidence')
    EVIDENCE.mkdir(parents=True); c.write_json(EVIDENCE/'audit_state.json', audit)
    for name, rows in false.items(): c.write_jsonl(EVIDENCE/(name+'_false_relations.jsonl'), rows)
    stamp = datetime.now(UTC).isoformat()
    body = '<p>只增加7篇训练NER摘要，58→65；关系271对、原开发数据及46关系权重冻结。六轮198步，原08初始化；不按开发错误选词，不搜索参数，不读取19篇保留测试。</p>'
    body += table(['训练项', '实际'], [['实体支持', 'METHOD458 / TASK260 / DATASET69，共787提及'], ['采集', '首次7/8，SSL失败保存；同名单一次重试8/8成功'], ['标注', 'AI整篇初标和同会话复核；7通过BIO，SQuAD共享版本名1隔离'], ['最优模型', '第6轮；仅保存一个检查点，重载预测一致且编码器/分类头发生变化']])
    body += '<h2>真实逐步训练损失</h2>'+loss_curve(steps)
    body += table(['Epoch', '累计训练步', '原16篇NER dev F1', '是否改善'], [[e['epoch'], e['steps'], f"{e['dev']['metrics']['micro']['f1']:.2%}", e['checkpointImproved']] for e in epochs])
    body += '<p>CPU最优权重克隆与恢复实际自检通过；训练前磁盘/CPU/GPU检查通过，1GB磁盘储备不变。没有中间检查点的恢复能力，失败不会冒充已保存。</p>'
    (EVIDENCE/'02_training.html').write_text(page('真实NER训练与数据量单因素对照 · 第52轮', body, stamp, [str(RUN/'ner/steps.jsonl'), str(RUN/'ner/epochs.json'), str(RUN/'preflight.json')]), encoding='utf-8')
    body = '<p>同一冻结46 RE、同一7篇完整开发文档、84参考正关系，包括真实零候选文档；没有过滤参考端点或缩小召回分母。</p>'
    body += table(['同范围Pipeline', 'Precision', 'Recall', 'F1', 'TP/预测/参考', '错报'], [[name, f"{m['positiveMicro']['precision']:.2%}", f"{m['positiveMicro']['recall']:.2%}", f"{m['positiveMicro']['f1']:.2%}", f"{m['positiveMicro']['truePositive']}/{m['positiveMicro']['predicted']}/84", 119] for name, m in audit['pipeline'].items()])
    body += '<h2>两个不同开发队列单独比较</h2>'+table(['队列', '模型', 'NER F1', 'TASK F1', 'DATASET recall', '非法BIO'], [[scope, name, f"{m['metrics']['micro']['f1']:.2%}", f"{m['metrics']['perClass']['TASK']['f1']:.2%}", f"{m['metrics']['perClass']['DATASET']['recall']:.2%}", m['invalidTransitions']] for scope in ('historicalNER', 'supplementNER') for name, m in audit[scope].items()])
    body += '<h2>仍不升级</h2><p>历史NER precision71.04%→70.41%；补充METHOD F1 66.67%→66.10%，非法BIO7→11。正关系错报仍119，改进主要是多召回9条，不是消除语义错误。52完整F1 45.04%仍低于同范围42的54.35%，不拿不同范围题名测试60.07%作比较。</p>'
    body += table(['护栏', '通过'], list(audit['gates']['checks'].items()))
    body += '<p>完整开发EVALUATED_ON参考0，覆盖7/19=36.84%，低于80%；补充49完整文档0/8，故没有补充Pipeline成绩。两个队列均为已暴露AI参考，非盲测、人类金标或实际准确率。新训练全部487候选关系保持未知，没有RE负例填充。旧线上模型/图谱/服务不变。</p>'
    body += '<h2>错报端点库存</h2>'+table(['模型', '错报主因计数'], [[name, json.dumps(counts, ensure_ascii=False)] for name, counts in audit['endpointMismatch'].items()])
    (EVIDENCE/'07_relation_development.html').write_text(page('端到端实际改善、残留错误与未晋级 · 第52轮', body, stamp, [str(RUN/'comparison.json'), 'audit_state.json', 'new_false_relations.jsonl']), encoding='utf-8')
    paths = [Path(__file__), ROOT/'scripts/capture_course_evidence.ps1', ROOT/'scripts/export_course_evidence.py', ROOT/'scripts/evaluate_abstract_decoder.py', JUNIT]
    paths += [ROOT/'scripts'/n for n in ('expand_boundary_abstracts.py', 'train_boundary_abstract_ner.py')]
    paths += [ROOT/'resources'/n for n in ('course_abstract_boundary_expansion_v1.json', 'course_abstract_boundary_training_v1.json', 'course_graph_runtime.json', 'course_graph_quality_runtime.json')]
    paths += [ROOT/'tests'/n for n in ('test_boundary_expansion.py', 'test_boundary_ner_training.py')]
    paths += [ROOT/'annotations/course_v4'/n for n in ('abstract_boundary_decisions_20261009_52.json', 'abstract_boundary_reviews_20261009_52.json')]
    paths += [ROOT/'docs'/n for n in ('quality_iteration_round52.md', 'system_status_round52.md', 'course_v4_plan.md', 'course_v4_runbook.md', 'status_log.md', 'model_optimization_abstract_v1.md')]+[ROOT/'README.md']
    paths += [p for p in RUN.rglob('*') if p.is_file() and p.suffix != '.safetensors']
    for folder in ('course_abstract_boundary_sources_20261009_52', 'course_abstract_boundary_sources_20261009_52_retry', 'course_abstract_boundary_generation_20261009_52', 'course_abstract_boundary_reviewed_20261009_52', 'course_abstract_boundary_inputs_20261009_52'):
        parent = ROOT/'kg_datasets/dblp'/folder; manifest = g.verified_files(parent)
        assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
        paths += [p for p in parent.iterdir() if p.is_file()]
    for p in paths:
        target = EVIDENCE/'sources'/p.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, target)
    c.write_json(EVIDENCE/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'inputSha256': {p.relative_to(ROOT).as_posix(): c.file_sha256(p) for p in paths}, 'filesSha256': {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})


def finish():
    audit, _, _, _ = checked(); manifest = g.verified_files(EVIDENCE); assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    captures = json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig'))
    assert captures['status'] == 'completed' and len(captures['captures']) == 2 and captures['originalConsoleScreenshot'] is False
    for item in captures['captures']:
        assert c.file_sha256(EVIDENCE/item['image']) == item['sha256'] and manifest['filesSha256'][item['sourcePage']] == item['sourcePageSha256']
    c.write_json(EVIDENCE/'capture_verification.json', {'passed': True, 'actualBrowserCaptures': 2, 'originalConsoleScreenshot': False, 'trainingRecomputed': True, 'qualityPromotionPassed': False})
    manifest['filesSha256'] = {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file() and p != EVIDENCE/'manifest.json'}
    c.write_json(EVIDENCE/'manifest.json', manifest)
    c.write_json(RUNS/'verification_20261009_round52.json', audit | {'evidenceManifestSha256': c.file_sha256(EVIDENCE/'manifest.json'), 'actualBrowserCaptures': 2})
    print({'verified': True, 'engineeringTests': 388, 'NERsteps': 198, 'modelPromoted': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('prepare', 'finish')); args = parser.parse_args()
    (prepare if args.action == 'prepare' else finish)()
