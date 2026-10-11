"""Recount the actual fixed60 run and render saved results, not a fake training UI."""
import json
import math
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import train_pair_window_relation as training
from export_course_evidence import page, table, loss_curve

c, g, read = training.c, training.g, training.read
RUN = ROOT/'kg_datasets/dblp/course_v4_runs/pair_window_development_20261010_60'
TESTS = ROOT/'kg_datasets/dblp/course_v4_runs/tests_pair_window60_related.xml'
OUTPUT = ROOT/'docs/evidence/20261010_round60_pair_window'


def main():
    if OUTPUT.exists(): raise FileExistsError('Preserve evidence and captures')
    manifest = g.verified_files(RUN)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    config, inherited, recipe, parent, parent_re, data, _ = training.load_inputs()
    baseline, candidates, refs, by_id = training.cached_baseline(data)
    result = read(RUN/'development_result.json'); comparison = read(RUN/'comparison.json'); fit = result['RE']
    assert read(RUN/'status.json')['status'] == 'completed' and result['passed'] and result['comparison'] == comparison
    assert fit['steps'] == 612 and fit['epochs'] == 6 and fit['savedCheckpoints'] == 1
    assert fit['classifierAndEncoderChanged'] and fit['reloadPredictionsIdentical'] and not fit['devUsedForGradient']
    assert not any(result[k] for k in ('qualityPromotionPassed', 'modelPromoted', 'testEvaluated'))
    assert comparison['baseline'] == baseline
    steps = c.read_jsonl(RUN/'re/steps.jsonl'); epochs = read(RUN/'re/epochs.json')
    assert len(steps) == 612 and [s['step'] for s in steps] == list(range(1, 613))
    assert all(math.isfinite(s['loss']) and s['loss'] >= 0 for s in steps)
    for split in ('train', 'dev'):
        local = [training.window_pair(r) for r in data[split]['relation']]
        assert local == c.read_jsonl(RUN/('re/'+split+'_inputs.jsonl'))
        assert len({training.re_model.pair_id(r) for r in local}) == len(local), 'Ambiguous cropped step identifiers'
        if split == 'train':
            expected = Counter(training.re_model.pair_id(r) for r in local)
            for epoch in range(1, 7):
                values = [s for s in steps if s['epoch'] == epoch]
                assert len(values) == 102 and Counter(p for s in values for p in s['inputIds']) == expected
    selected = max(epochs, key=lambda e: training.re_model.selection_score(e['dev']['metrics'], 'all_class_macro'))
    assert fit['bestCheckpoint'] == f'checkpoint_epoch_{selected["epoch"]:02d}' and fit['bestDev'] == selected['dev']
    known = c.read_jsonl(RUN/'new_module_predictions.jsonl')
    module = training.prior.dev_scope(training.re_model.score_relations(data['dev']['relation'], [p['label'] for p in known]))
    assert module == comparison['module']['new'] == fit['bestDev']['metrics']
    full = data['dev']['full_relation']; predicted = c.read_jsonl(RUN/'new_pipeline_predictions.jsonl')
    assert c.read_jsonl(RUN/'pipeline_dev_documents.jsonl') == full and c.read_jsonl(RUN/'pipeline_dev_reference_pairs.jsonl') == refs
    for name, rows, predictions in (('module', data['dev']['relation'], known), ('pipeline', candidates, predicted)):
        local = [training.window_pair(r) for r in rows]
        assert len({training.re_model.pair_id(r) for r in local}) == len(local)
        assert c.read_jsonl(RUN/(name+'_window_inputs.jsonl')) == [{k: v for k, v in r.items() if k != 'label'} for r in local]
        reconstructed = [{k: v for k, v in w.items() if k != 'label'} | {'label': p['label'], 'probabilities': p['probabilities'],
                          'pairId': training.re_model.pair_id(w)} for w, p in zip(local, predictions)]
        assert training.restore_predictions(rows, reconstructed) == predictions
    pipeline, false, missed = training.pipeline_scores(full, refs, predicted, by_id)
    assert pipeline == comparison['pipeline']['new']
    assert false == c.read_jsonl(RUN/'new_false_relations.jsonl') and missed == c.read_jsonl(RUN/'new_missed_relations.jsonl')
    assert training.source.old.gates(parent, data, comparison['pipeline'], comparison['module'], baseline['NER']['metrics']) == comparison['gates']
    suites = list(ET.parse(TESTS).getroot().iter('testsuite'))
    counts = {k: sum(int(s.get(k, 0)) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
    assert counts['tests'] >= 24 and not any(counts[k] for k in ('failures', 'errors', 'skipped'))
    with urlopen('http://127.0.0.1:8765/api/health', timeout=15) as response: health = json.load(response)['data']
    assert health['status'] == 'ready' and health['graphId'] == 'ai-literature-63686318d85cccb07afb'
    assert health['scope']['bibliographyTitles'] == 20000 and health['liveImportCompleted']
    assert not health['conceptVocabulary']['modelReliabilityPromoted']
    runtime = ROOT/'resources/course_graph_quality_v3_runtime.json'
    assert c.file_sha256(runtime) == manifest['inputSha256'][runtime.relative_to(ROOT).as_posix()]
    reserved = ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl'
    assert c.file_sha256(reserved) == '716b5cba5779d7c3b6e4bc404dba9579447b5c93768d56b0da28a70edc0bb3c1'
    before = c.read_jsonl(training.BASELINE/'new_pipeline_predictions.jsonl')
    assert [p['pairId'] for p in before] == [p['pairId'] for p in predicted]
    changes = [{'sampleId': p['sampleId'], 'pairId': p['pairId'], 'beforeLabel': b['label'], 'afterLabel': p['label']}
               for b, p in zip(before, predicted) if b['label'] != p['label']]
    state = {'status': 'passed', 'RE': fit, 'comparison': comparison, 'tests': counts,
             'changedPredictions': changes, 'changedSourceDocuments': len({p['sampleId'] for p in changes}),
             'liveStatus': health['status'], 'livePapers': 20000, 'liveGraphId': health['graphId'],
             'reservedTestParsedOrCopied': False, 'modelPromoted': False, 'full503SuiteRepeated': False}
    sources = [RUN/'manifest.json', TESTS, Path(__file__), ROOT/'scripts/export_course_evidence.py',
               ROOT/'scripts/capture_course_evidence.ps1', ROOT/'resources/course_pair_window_training_v1.json', runtime]
    hashes = {p.relative_to(ROOT).as_posix(): c.file_sha256(p) for p in sources}
    rows = [(name, *(f'{metrics["positiveMicro"][k]:.2%}' for k in ('precision', 'recall', 'f1')),
             metrics['positiveMicro']['predicted']-metrics['positiveMicro']['truePositive'],
             metrics['positiveMicro']['reference']-metrics['positiveMicro']['truePositive']) for name, metrics in comparison['pipeline'].items()]
    body = ('<p>复用408已判训练对、333开发对、固定52 NER与原15 RE初始化。仅改变关系输入为实体对所在句范围及左右各一句；窗口选择不读取关系标签或参考证据，原完整文档评分分母不变。</p>'
            + table(['真实训练', '记录'], [('epochs / steps', '6 / 612'), ('单检查点', fit['bestCheckpoint']), ('编码器/分类头更新与重载一致', True), ('每轮408对均消费一次', True), ('保留测试/自动上线', '未读取 / 未晋级')])
            + '<h2>同7篇 / 84正参考 / 183预测候选：整篇开发对比</h2>'
            + table(['版本', 'Precision', 'Recall', 'F1', 'FP', 'FN'], rows)
            + f'<p>57对照是封存预测重算，不是新推理。预测变化来自{state["changedSourceDocuments"]}篇；不是多来源泛化证明。完整评测关系支持0、覆盖7/19仍阻断晋级。</p>'
            + '<h2>输入缩短与限制</h2>' + table(['split', '对数', '缩短输入', '原证据片段未完整覆盖'], [(s, v['pairs'], v['shorterInputs'], v['quotedEvidenceOutsideWindow']) for s, v in comparison['inventory'].items()])
            + '<p>保留原整篇标签与证据，不能把局部共现当事实；窗口可能遗漏远处配置/共指信息。未决1949训练对不填负例。AI参考仍非独立人工金标准；本轮没有生产准确率结论。</p>'
            + '<h2>实际612步损失</h2>' + (loss_curve(steps) if all(s['loss'] > 0 for s in steps) else '<p>保留日志中的精确零损失，不删点画对数图。</p>')
            + table(['检查', '结果'], [('新增与相关回归', counts['tests']), ('failed / errors / skipped', '0 / 0 / 0'), ('现有应用', 'ready / 20000篇'), ('生产模型 / 图配置', '保持不变'), ('全503项重跑', '本轮未重跑，上一轮503通过仅作历史记录')]))
    OUTPUT.mkdir(parents=True)
    c.write_json(OUTPUT/'check.json', state)
    (OUTPUT/'07_relation_development.html').write_text(page('第60轮 · 局部上下文真实训练与整篇开发评测', body, datetime.now(UTC).isoformat(), [str(RUN/'manifest.json'), str(OUTPUT/'check.json')]), encoding='utf-8')
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in hashes.items())
    c.write_json(OUTPUT/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui',
        'inputSha256': hashes, 'filesSha256': {p.name: c.file_sha256(p) for p in OUTPUT.iterdir()}})
    print({'verified': True, 'steps': 612, 'pipeline': pipeline['positiveMicro'], 'relatedTests': counts,
           'changedSourceDocuments': state['changedSourceDocuments'], 'livePapers': 20000, 'modelPromoted': False})


if __name__ == '__main__': main()
