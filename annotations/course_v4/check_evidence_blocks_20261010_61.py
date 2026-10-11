"""Recount the sealed local diagnostic and expose NER/RE error propagation."""
import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
import evaluate_evidence_blocks as b
from export_course_evidence import escaped, page, table
from course_abstract_v1 import read

ROOT = b.c.ROOT
SNAPSHOT = ROOT/'kg_datasets/dblp/course_evidence_blocks_20261010_61'
RUN = ROOT/'kg_datasets/dblp/course_v4_runs/evidence_blocks_development_20261010_61'
OUTPUT = ROOT/'docs/evidence/20261010_round61_evidence_blocks'
key = lambda p: b.relation.pair_key(p)+(p['head']['label'], p['tail']['label'])


def check():
    assert b.c.file_sha256(SNAPSHOT/'manifest.json') == '0085ae497cc00cf6a2e560f6ff437c83665a1437fe342fa5d8f4d242edf6dad6'
    assert b.c.file_sha256(RUN/'manifest.json') == '19ff55d3a170401f7f3e8cd836f129cf872aba038f417251d16243526677421e'
    inputs = []
    for folder in (SNAPSHOT, RUN):
        manifest = b.checked_snapshot(folder)
        inputs.extend([folder/'manifest.json']+[folder/p for p in manifest['filesSha256']])
    config, refs, receipts, source_paths = b.load_sources(); inputs += source_paths
    units = b.build_units(refs, receipts)
    decisions_path = ROOT/'annotations/course_v4/evidence_block_decisions_20261010_61.json'
    compiled = b.compile_units(units, read(decisions_path)['blocks'])
    assert units == b.c.read_jsonl(SNAPSHOT/'units.jsonl')
    for name in ('ner', 'complete', 'excluded', 'pairStates', 'positives'):
        assert compiled[name] == b.c.read_jsonl(SNAPSHOT/(name+'.jsonl'))
    docs = compiled['complete']; ids = {d['sampleId'] for d in docs}
    references = [p for p in compiled['positives'] if p['sampleId'] in ids]
    ner_rows = b.c.read_jsonl(RUN/'ner_predictions.jsonl')
    assert [r['sampleId'] for r in ner_rows] == [d['sampleId'] for d in compiled['ner']]
    ner_by_id = {r['sampleId']: r['predictedEntities'] for r in ner_rows}
    result = read(RUN/'comparison.json'); summary = read(SNAPSHOT/'summary.json')
    assert b.ner.score_rows(compiled['ner'], [r['predictedEntities'] for r in ner_rows], evaluation_target=b.TARGET) == result['NER52']['metrics']
    assert summary == result['coverage'] and summary['trainableNegativePairs'] == 0
    assert summary['lockedQueue'] == 31 and len(docs) == 27 and len(references) == 52
    assert summary['zeroPositiveCompleteBlocks'] == 12 and len(compiled['excluded']) == 4
    module = [p for d in docs for p in b.prior.candidate_rows(d, d['entities'])]
    pipeline = [p for d in docs for p in b.prior.candidate_rows(d, ner_by_id[d['sampleId']])]
    assert len(module) == result['allModuleCandidates'] == 100 and len(pipeline) == result['allPipelineCandidates'] == 90
    prediction_keys = {key(p) for p in pipeline}; ref_keys = {key(p) for p in references}
    reachable = [p for p in references if key(p) in prediction_keys]
    assert len(reachable) == 22
    baseline = {}
    for name, candidates in [('reference_entity_module', module), ('predicted_entity_pipeline', pipeline)]:
        positive = [p | {'label': 'USED_FOR' if p['tail']['label'] == 'TASK' else 'EVALUATED_ON'} for p in candidates]
        baseline[name] = b.prior.dev_scope(b.prior.score_pipeline(docs, references, positive), b.TARGET)
    states = {key(p): p['state'] for p in compiled['pairStates'] if p['sampleId'] in ids}
    errors = {}; artifacts = {}
    for model in ('RE57', 'RE60'):
        for scope, candidates in [('reference_entity_module', module), ('predicted_entity_pipeline', pipeline)]:
            predicted = b.c.read_jsonl(RUN/(model+'_'+scope+'_predictions.jsonl'))
            assert len(predicted) == len(candidates)
            for source, row in zip(candidates, predicted):
                assert all(row[k] == source[k] for k in ('sampleId', 'text', 'textSha256', 'head', 'tail'))
                assert row['pairId'] == b.relation.pair_id(source)
                values = list(row['probabilities'].values())
                assert all(math.isfinite(v) and 0 <= v <= 1 for v in values) and abs(sum(values)-1) < 1e-6
            metrics = b.prior.dev_scope(b.prior.score_pipeline(docs, references, predicted), b.TARGET)
            assert all(metrics[k] == result['comparison'][model][scope][k] for k in ('positiveMicro', 'perClass', 'negativeDecisions', 'documents', 'positiveMacroF1'))
            if scope != 'predicted_entity_pipeline': continue
            missed = [e for d in docs for e in b.prior.diagnose(d, ner_by_id[d['sampleId']],
                [p for p in references if p['sampleId'] == d['sampleId']], [p for p in predicted if p['sampleId'] == d['sampleId']])]
            false = [p | {'primaryCause': 'local_predicate_overreach' if key(p) in states else 'NER_endpoint_mismatch',
                     'referenceTextState': states.get(key(p), 'REFERENCE_ENDPOINTS_NOT_EXACTLY_MATCHED')}
                     for p in predicted if p['label'] != 'NO_RELATION' and key(p) not in ref_keys]
            m = metrics['positiveMicro']; assert len(missed) == m['reference']-m['truePositive'] == 30
            assert len(false) == m['predicted']-m['truePositive']
            assert all(p['referenceTextState'] == 'NOT_EXPRESSED' for p in false if p['primaryCause'] == 'local_predicate_overreach')
            causes = dict(Counter(e['primaryCause'] for e in missed)); assert causes == {'missing': 11, 'type': 11, 'boundary': 8}
            errors[model] = {'missedPrimaryCauses': causes, 'missedFlags': dict(Counter(f for e in missed for f in e['flags'])),
                'falsePrimaryCauses': dict(Counter(e['primaryCause'] for e in false)),
                'EVALUATED_ON_missedFlags': dict(Counter(f for e in missed if e['referencePair']['label'] == 'EVALUATED_ON' for f in e['flags']))}
            artifacts[model+'_missed.jsonl'] = missed; artifacts[model+'_false.jsonl'] = false
    assert result['support']['EVALUATED_ON'] == {'mentionPairs': 13, 'blocks': 4, 'independentSourcePapers': 3}
    xml = ROOT/'kg_datasets/dblp/course_v4_runs/tests_evidence_blocks61_related.xml'; suites = list(ET.parse(xml).getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == 46
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('failures', 'errors', 'skipped'))
    coverage_path = ROOT/'kg_datasets/dblp/course_v4_runs/coverage_evidence61_final.json'; coverage = read(coverage_path)['totals']
    assert coverage['covered_lines'] == 176 and coverage['num_statements'] == 193
    original = ROOT/'kg_datasets/dblp/course_v4_runs/pair_window_development_20261010_60/comparison.json'
    assert read(original)['completeReferenceEVALUATED_ON'] == 0
    assert b.c.file_sha256(ROOT/'resources/course_graph_quality_v3_runtime.json') == '8b772f5e84a53d8a71044e1909e76d06c00a0a16b6cd5d363da56745e19f5353'
    assert not any(result[k] for k in ('trained', 'testEvaluated', 'modelPromoted', 'qualityPromotionPassed', 'oldWholeAbstractMetricsReplaced'))
    status = read(RUN/'status.json'); assert status['status'] == 'completed' and status['inferenceExecuted'] and not status['trainingExecuted']
    checked = {'passed': True, 'originalWholeAbstractMetricsUnchanged': True, 'summary': summary,
        'support': result['support'], 'typedPositiveBaselines': baseline, 'errorAttribution': errors,
        'reachablePositivePairsWithFrozenNER': 22, 'totalPositiveReference': 52, 'reachableRecallCeiling': 22/52,
        'relatedTests': 46, 'testsSeconds': sum(float(s.attrib['time']) for s in suites), 'coverage': coverage,
        'coverageKind': 'combined_unit_tests_and_real_compile_GPU_inference_not_unit_only',
        'inferenceSeconds': status['elapsedSeconds'], 'testEvaluated': False, 'qualityPromotionPassed': False,
        'notice': 'Source-paper count means distinct arxiv IDs, not statistically independent samples. All scores concern this exposed local mention-expression target and AI references, not global relation truth or production accuracy.'}
    return checked, artifacts, result, inputs+[decisions_path, b.REVIEW, xml, coverage_path, original, Path(__file__)]


def main():
    if OUTPUT.exists(): raise FileExistsError('Preserve result visualization')
    checked, artifacts, result, inputs = check(); OUTPUT.mkdir(parents=True)
    b.c.write_json(OUTPUT/'check.json', checked)
    for name, rows in artifacts.items(): b.c.write_jsonl(OUTPUT/name, rows)
    percent = lambda x: f'{100*x:.2f}%'
    rows = []
    for name in ('RE57', 'RE60'):
        for scope in ('reference_entity_module', 'predicted_entity_pipeline'):
            m = result['comparison'][name][scope]['positiveMicro']
            rows.append([name, '给定参考实体' if scope == 'reference_entity_module' else '模型实体Pipeline',
                percent(m['precision']), percent(m['recall']), percent(m['f1']),
                f"{m['truePositive']}/{m['predicted']-m['truePositive']}/{m['reference']-m['truePositive']}"])
    body = '<h2>锁定文本单位与支持</h2><p>全部8篇外部开发摘要 → 31个不重叠连续双句块。NER 30块/125实体；完整关系27/31块（87.10%），其中12块无正关系。4块隔离仍保留分母。未表达不是事实负例，不进入训练。</p>'
    body += table(['关系', '提及对', '文本块', '去重来源论文'], [[k,v['mentionPairs'],v['blocks'],v['independentSourcePapers']] for k,v in result['support'].items()])
    body += '<h2>固定模型真实推理，没有新训练</h2>'+table(['模型', '范围', 'P', 'R', 'F1', 'TP/FP/FN'], rows)
    body += '<p>参考实体100候选、模型实体90候选，全数保留；关系头尾偏移恢复后评分。NER52与RE57/RE60权重预先锁定；未调阈值，未使用最终测试，未更新线上模型。</p>'
    body += '<h2>NER与误差传播</h2>'+table(['类别','P','R','F1','参考实体'], [[label,percent(m['precision']),percent(m['recall']),percent(m['f1']),m['reference']] for label,m in result['NER52']['metrics']['perClass'].items()])
    body += '<p>NER总体F1 69.32%，非法BIO转移15次，仍按原规则严格处理。52个正关系中，仅22个具备严格匹配的预测实体端点，召回上限42.31%。两模型各漏30条：缺实体11、错类别11、错边界8。稀有评测关系仅检出2/13，P20.00%/R15.38%/F1 17.39%。</p>'
    body += table(['模型','NER端点导致的局部误报','端点正确但局部谓词过度配对'], [[k,v['falsePrimaryCauses'].get('NER_endpoint_mismatch',0),v['falsePrimaryCauses'].get('local_predicate_overreach',0)] for k,v in checked['errorAttribution'].items()])
    body += '<h2>基线与结论边界</h2><p>参考实体按类型全预测正关系的F1为'+percent(checked['typedPositiveBaselines']['reference_entity_module']['positiveMicro']['f1'])+'；RE60为71.23%，优势有限。局部提及谓词是新诊断目标，不替代整篇摘要事实，不与旧45.74%或题名60.07%直接比较。原整篇开发完整EVAL支持仍为0。</p>'
    body += '<h2>机械验证与保留项</h2><p>46项新增/相关测试通过，0失败/错误/跳过。合并单元检查、真实标注编译和GPU推理的语句覆盖176/193（91.19%），不是单元覆盖或语义正确率。GPU推理'+f"{checked['inferenceSeconds']:.2f}"+'秒。完整FP/FN账本与来源SHA封存；未重跑503全套或应用UI全验收。</p><p>本次明确不晋级。下一步优先训练侧TASK/DATASET类别与方法边界，再用同一冻结开发口径比较；不把此开发切片转为训练数据或修改答案追分。</p>'
    html = page('第61轮 · 局部证据切片与模型误差传播', body, datetime.now(UTC).isoformat(),
                ['冻结运行manifest SHA256: '+b.c.file_sha256(RUN/'manifest.json'),
                 '标注snapshot manifest SHA256: '+b.c.file_sha256(SNAPSHOT/'manifest.json'),
                 str(RUN/'comparison.json'), str(SNAPSHOT/'summary.json')])
    (OUTPUT/'07_relation_development.html').write_text(html, encoding='utf-8')
    b.c.write_json(OUTPUT/'manifest.json', {'kind':'real_artifact_visualization_not_original_console_ui',
        'inputSha256': {p.relative_to(ROOT).as_posix(): b.c.file_sha256(p) for p in sorted(set(inputs))},
        'filesSha256': {p.name: b.c.file_sha256(p) for p in OUTPUT.iterdir() if p.is_file()}})
    print(json.dumps({'passed': True, 'errors': checked['errorAttribution'], 'relatedTests': 46}, ensure_ascii=False))


if __name__ == '__main__': main()
