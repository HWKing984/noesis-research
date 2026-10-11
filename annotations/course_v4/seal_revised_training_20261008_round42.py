"""Recompute saved development predictions and seal actual browser captures; never runs test."""
import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import course_graph as g
import course_weak as c
import train_course_ner as ner
import train_course_relation as re_model
import train_revised_abstract_models as revised
from course_abstract_v1 import read
from evaluate_course_relation import candidate_rows, score_pipeline
from export_course_evidence import page, table
import seal_eval_attribution_20261008_round41 as previous_round

RUNS = ROOT/'kg_datasets/dblp/course_v4_runs'
RUN = RUNS/'abstract_revised_development_20261008_42'
EVIDENCE = ROOT/'docs/evidence/20261008_round42'
TESTS = RUNS/'tests_20261008_round42_workspace_temp.xml'


def checked():
    _, _, _, immutable = previous_round.checked()
    old_seal = read(RUNS/'verification_20261008_round41.json'); assert old_seal['passed']
    old_evidence = ROOT/'docs/evidence/20261008_round41'; g.verified_files(old_evidence, old_seal['evidenceManifestSha256'])
    assert c.file_sha256(old_evidence/'captures.json') == old_seal['capturesSha256']
    for capture in json.loads((old_evidence/'captures.json').read_text(encoding='utf-8-sig'))['captures']: assert c.file_sha256(old_evidence/capture['image']) == capture['sha256']
    config, parent, parent_re, data = revised.load_inputs(); manifest = g.verified_files(RUN)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items()) and read(RUN/'contract.json') == config
    state = read(RUN/'status.json'); result = read(RUN/'development_result.json'); comparison = read(RUN/'pipeline_development_result.json')
    assert state['status'] == 'completed' and result['passed'] and not state['testEvaluated'] and not state['modelPromoted']
    selections = {}; model_hashes = {}
    for task, settings, steps_count in (('NER', parent['NERTraining'], 150), ('RE', parent_re['RETraining'], 402)):
        folder = RUN/task.lower(); fit = read(folder/'development_result.json'); status = read(folder/'status.json'); epochs = read(folder/'epochs.json'); steps = c.read_jsonl(folder/'steps.jsonl')
        assert fit == result[task] and status['status'] == 'completed' and status['settings'] == settings and status['trainingStarted']
        assert fit['epochs'] == len(epochs) == 6 and fit['steps'] == len(steps) == steps_count
        assert fit['classifierAndEncoderChanged'] and fit['reloadPredictionsIdentical'] and not any(fit[k] for k in ('devUsedForGradient', 'testEvaluated', 'testTokenized', 'modelPromoted', 'qualityPromotionPassed'))
        for split in ('train', 'dev'): assert c.read_jsonl(folder/(split+'_inputs.jsonl')) == data[split]['ner' if task == 'NER' else 'relation']
        inputs = data['train']['ner' if task == 'NER' else 'relation']; ids = [p['sampleId'] if task == 'NER' else re_model.pair_id(p) for p in inputs]
        assert [s['step'] for s in steps] == list(range(1, steps_count+1))
        for epoch in range(1, 7): assert Counter(i for s in steps if s['epoch'] == epoch for i in s['inputIds']) == Counter(ids)
        score = lambda e: e['dev']['metrics']['micro']['f1'] if task == 'NER' else re_model.selection_score(e['dev']['metrics'], 'all_class_macro')
        best = max(epochs, key=score); assert fit['bestCheckpoint'] == f'checkpoint_epoch_{best["epoch"]:02d}' and fit['bestDev'] == best['dev']
        model = folder/fit['bestCheckpoint']/'model.safetensors'; assert c.file_sha256(model) != settings['initialWeightsSha256']
        model_hashes[task] = c.file_sha256(model); selections[task] = {'epochs': 6, 'steps': steps_count, 'selectedEpoch': best['epoch']}
    docs = data['dev']['ner']; entity_predictions = {}
    for name in ('old', 'new'):
        saved = c.read_jsonl(RUN/(name+'_ner_dev_predictions.jsonl')); assert [p['sampleId'] for p in saved] == [d['sampleId'] for d in docs]
        assert all(p['referenceEntities'] == d['entities'] for p, d in zip(saved, docs))
        predictions = [p['predictedEntities'] for p in saved]; metrics = ner.score_rows(docs, predictions, evaluation_target=revised.TARGET)
        assert comparison['nerDevMetrics'][name]['metrics'] == metrics and comparison['nerDevMetrics'][name]['inferenceFeaturesContainLabels'] is False
        entity_predictions[name] = {d['sampleId']: p for d, p in zip(docs, predictions)}
        if name == 'new':
            assert saved == c.read_jsonl(RUN/'ner/dev_predictions.jsonl') and result['NER']['bestDev']['metrics'] == metrics | {'evaluationTarget': revised.TARGET}
    for name in ('old', 'new'):
        saved = c.read_jsonl(RUN/(name+'_module_dev_predictions.jsonl')); refs = data['dev']['relation']
        assert [p['pairId'] for p in saved] == [re_model.pair_id(p) for p in refs]
        assert all(all(pred[k] == ref[k] for k in ('sampleId', 'text', 'head', 'tail')) for pred, ref in zip(saved, refs))
        metrics = revised.dev_scope(re_model.score_relations(refs, [p['label'] for p in saved])) | {'evaluationTarget': revised.TARGET}
        assert metrics == comparison['moduleMetrics'][name] == result['RE']['baselineDev' if name == 'old' else 'bestDev']['metrics']
    full = data['dev']['full_relation']; full_ids = {d['sampleId'] for d in full}; refs = [p for p in data['dev']['relation'] if p['sampleId'] in full_ids]
    assert full == c.read_jsonl(RUN/'pipeline_dev_documents.jsonl') and refs == c.read_jsonl(RUN/'pipeline_dev_reference_pairs.jsonl')
    for name, metrics in comparison['pipelineMetrics'].items():
        ner_name = name.split('_')[0]; candidates = [p for d in full for p in candidate_rows(d, entity_predictions[ner_name][d['sampleId']])]
        saved = c.read_jsonl(RUN/(name+'_predictions.jsonl')); assert len(saved) == len(candidates)
        assert all(all(pred[k] == ref[k] for k in ('sampleId', 'text', 'head', 'tail')) for pred, ref in zip(saved, candidates))
        recomputed = revised.dev_scope(score_pipeline(full, refs, saved), 'complete_document_exposed_dev_AI_reference_not_final_test'); recomputed['entityScope'] = 'predicted_NER_entities'
        errors = c.read_jsonl(RUN/(name+'_missed_relations.jsonl')); recomputed['missedReferencePrimaryCauses'] = dict(Counter(e['primaryCause'] for e in errors))
        assert errors == [e for d in full for e in revised.diagnose(d, entity_predictions[ner_name][d['sampleId']], [p for p in refs if p['sampleId'] == d['sampleId']], [p for p in saved if p['sampleId'] == d['sampleId']])]
        assert recomputed == metrics and len(errors) == metrics['positiveMicro']['reference']-metrics['positiveMicro']['truePositive']
    gates = revised.gate_results(parent, data, comparison, comparison['nerDevMetrics']['new']['metrics']); assert gates == comparison['gates'] == result['gates']
    assert not gates['developmentGatesPassed'] and not gates['qualityPromotionPassed'] and not gates['modelPromoted'] and not comparison['testEvaluated']
    assert comparison['pipelineReferenceEVALUATED_ON'] == 0 and comparison['pipelineDocumentCoverage'] == 7/19 and comparison['modulePairCoverage'] == 333/432
    suite = ElementTree.parse(TESTS).getroot().find('testsuite'); assert suite.get('tests') == '370' and all(suite.get(k) == '0' for k in ('errors', 'failures', 'skipped'))
    failed = ElementTree.parse(RUNS/'tests_20261008_round42.xml').getroot().find('testsuite')
    assert failed.get('tests') == '370' and failed.get('failures') == '1' and failed.get('skipped') == '0' and 'WinError 5' in ElementTree.tostring(failed, encoding='unicode')
    isolated = ElementTree.parse(RUNS/'tests_20261008_round42_rename_D_check.xml').getroot().find('testsuite'); assert isolated.get('tests') == '1' and isolated.get('failures') == '0'
    audit = {'passed': True, 'engineeringTests': 370, 'trainingActuallyExecuted': True, 'selections': selections, 'selectedWeightsSha256': model_hashes,
        'trainOnlyGradientInputInventoryVerified': True, 'selectedNERModuleAndFourPipelineScoresRecomputedFromSavedPredictions': True, 'freshSameScopeFourWayPipelineComparison': True,
        'labelFreeInferenceParityCheckedDuringRun': True, 'pipelineUsesEveryPredictedCandidate': True, 'revisedSnapshotManifestSha256': config['snapshotManifestSha256'],
        'runManifestSha256': c.file_sha256(RUN/'manifest.json'), 'gates': gates, 'reservedTestContentConsumed': False, 'oldTestReinferred': False,
        'developmentPreviouslyExposed': True, 'independentHumanGold': False, 'modelPromoted': False, 'qualityPromotionPassed': False, 'databaseWritten': False,
        'serviceRestarted': False, 'liveApplicationReaccepted': False, 'reportExpansionPaused': True,
        'regressionInitialFailurePreserved': True, 'regressionTemporaryDirectory': 'isolated_workspace_D_drive',
        'CDefaultTempRenameFailureRootCauseResolved': False, 'regressionTestsSkipped': 0,
        'notice': 'Real fixed-setting training and exposed AI-dev diagnostics. Historical 5-document scores are not this 7-document baseline. Zero full EVAL support blocks reliability promotion.'}
    return audit, result, comparison, immutable


def percent(value): return '无参考支持' if value is None else f'{value:.2%}'


def main(action):
    audit, result, comparison, immutable = checked()
    if action == 'prepare':
        if EVIDENCE.exists(): raise FileExistsError('Preserve evidence')
        EVIDENCE.mkdir(parents=True)
        paths = [Path(__file__), revised.CONTRACT, ROOT/'scripts/train_revised_abstract_models.py', ROOT/'tests/test_revised_abstract_training.py', ROOT/'README.md', ROOT/'docs/system_status_round42.md', TESTS]
        paths += [RUNS/name for name in ('tests_20261008_round42.xml', 'tests_20261008_round42_rename_check.xml', 'tests_20261008_round42_rename_D_check.xml')]
        paths += [p for p in RUN.rglob('*') if p.is_file() and 'checkpoint_' not in p.as_posix() and 'sources' not in p.relative_to(RUN).parts]
        for source in paths:
            target = EVIDENCE/'sources'/source.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        c.write_json(EVIDENCE/'audit_state.json', audit)
        rows = []
        for task in ('NER', 'RE'):
            fit = result[task]; baseline = fit['baselineDev']['metrics']; best = fit['bestDev']['metrics']
            b = baseline['micro']['f1'] if task == 'NER' else re_model.selection_score(baseline, 'all_class_macro'); p = best['micro']['f1'] if task == 'NER' else re_model.selection_score(best, 'all_class_macro')
            rows.append([task, f'{fit["trainInputs"]} / {fit["devInputs"]}', f'6轮 / {fit["steps"]}步，{fit["bestCheckpoint"]}', f'{percent(b)} → {percent(p)}'])
        body = '<h2>真实固定设置训练 · 新旧模型同一修订参考</h2>'+table(['任务', 'train / dev输入', '实际训练 / 选择', '初始化迁移基线 → 候选'], rows)
        body += '<p>NER微F1与条件性RE三类宏F1不是同一指标。NER从旧08、RE从旧15初始化；只使用train梯度，dev选earliest tie。两模型分类头/编码器实际变化、重载预测一致；无新超参搜索。NER词典、RE类型多数基线仅由train构造。</p>'
        body += '<h2>实体类型明细 · 16篇dev / 19篇队列</h2>'+table(['类别', 'Precision', 'Recall', 'F1', 'TP / 预测 / 参考'], [[label, percent(m['precision']), percent(m['recall']), percent(m['f1']), f'{m["truePositive"]} / {m["predicted"]} / {m["reference"]}'] for label, m in comparison['nerDevMetrics']['new']['metrics']['perClass'].items()])
        body += '<h2>不能拿训练完成当可靠性完成</h2><p>41轮train50篇NER / 267明确关系；dev16篇NER / 333明确关系。1578 / 99未决对不进RE损失或条件性模块评分。完整pipeline只评7/19文档，包括1篇零候选，107参考对中84用途、23负例、EVALUATED_ON正例0。</p><p>D盘隔离临时目录下370项正式工程回归通过，无跳过。首次C默认临时目录的重命名拒绝访问及单项失败XML保留，具体Windows触发原因未解决；未改源码或吞失败，不是语义正确率认证。</p><p>本轮有新dev成绩，没有最终测试；AI参考与已暴露开发集不是独立gold。所有原始输入、逐步loss、epoch选择、权重哈希、真实预测、逐对漏边原因可复查。没有改旧模型、31图或服务，也没有写库/晋级，报告继续暂停。</p>'
        (EVIDENCE/'02_training.html').write_text(page('修订摘要模型真实训练 · 第42轮', body, datetime.now(UTC).isoformat(), ['audit_state.json', 'sources/kg_datasets/dblp/course_v4_runs/abstract_revised_development_20261008_42/development_result.json']), encoding='utf-8')
        rows = []
        for name, metrics in comparison['pipelineMetrics'].items():
            m = metrics['positiveMicro']; rows.append([name, percent(m['precision']), percent(m['recall']), percent(m['f1']), f'{m["truePositive"]} / {m["predicted"]} / {m["reference"]}', str(metrics['missedReferencePrimaryCauses'])])
        body = '<p>旧NER=第35轮冻结摘要NER；旧RE=第15轮冻结题名RE。四组均重新推理同一7篇完整dev，不能和36/37轮旧5篇分数直接比较。</p><h2>严格端到端关系对照</h2>'+table(['组合', 'Precision', 'Recall', 'F1', 'TP / 预测 / 参考', '漏参考主因'], rows)
        body += '<h2>条件性模块 ≠ 完整pipeline</h2>'+table(['已判对模块（333 / 432）', '正关系Precision', 'Recall', 'F1', '三类宏F1'], [[name, percent(m['positiveMicro']['precision']), percent(m['positiveMicro']['recall']), percent(m['positiveMicro']['f1']), percent(re_model.selection_score(m, 'all_class_macro'))] for name, m in comparison['moduleMetrics'].items()])
        body += '<h2>事先声明护栏 · 不因结果放松</h2>'+table(['检查', '实际判断'], [[k, '通过' if passed else '未通过'] for k, passed in comparison['gates']['checks'].items()])
        body += '<p>所有预测候选都评分，没有用参考端点遮住错误。FP=预测正边数−TP，只针对当前可判定范围；F1不是错误比例。EVALUATED_ON零参考不能宣称准确；完整覆盖7/19=36.84%，不是模块333/432=77.08%。</p><p>qualityPromotionPassed=false，modelPromoted=false。训练与比较完成≠系统可靠性通过。下一步根据实际错误簇改善训练侧任务边界和局部角色，不回读test或用旧测试追分。</p>'
        (EVIDENCE/'04_traceability.html').write_text(page('同范围端到端对照与拒绝晋级 · 第42轮', body, datetime.now(UTC).isoformat(), ['sources/kg_datasets/dblp/course_v4_runs/abstract_revised_development_20261008_42/pipeline_development_result.json']), encoding='utf-8')
        c.write_json(EVIDENCE/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'filesSha256': {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})
        print(json.dumps({'prepared': True, 'engineeringTests': 370, 'trained': True}))
    else:
        target = RUNS/'verification_20261008_round42.json'
        if target.exists(): raise FileExistsError('Preserve verification seal')
        g.verified_files(EVIDENCE); assert read(EVIDENCE/'audit_state.json') == audit
        captures = json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig')); assert captures['status'] == 'completed' and len(captures['captures']) == 2
        assert {(p['sourcePage'], p['image']) for p in captures['captures']} == {('02_training.html', '02_training.png'), ('04_traceability.html', '04_traceability.png')}
        for capture in captures['captures']: assert c.file_sha256(EVIDENCE/capture['image']) == capture['sha256'] and c.file_sha256(EVIDENCE/capture['sourcePage']) == capture['sourcePageSha256']
        c.write_json(target, {'passed': True, 'checkedAtUTC': datetime.now(UTC).isoformat(), 'engineeringTests': 370, 'audit': audit, 'immutableHistoricalSha256': immutable,
            'previousVerificationSha256': c.file_sha256(RUNS/'verification_20261008_round41.json'), 'evidenceManifestSha256': c.file_sha256(EVIDENCE/'manifest.json'), 'capturesSha256': c.file_sha256(EVIDENCE/'captures.json'), 'qualityPromotionPassed': False})
        print(json.dumps({'passed': True, 'engineeringTests': 370, 'trained': True, 'modelPromoted': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('prepare', 'seal')); main(parser.parse_args().action)
