"""Verify real round46 outputs and render two evidence pages for course use."""
import argparse
import json
import math
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_graph as g
import course_weak as c
import train_benchmark_abstract_models as training
from course_abstract_v1 import read
from export_course_evidence import loss_curve, page, table

ROOT = c.ROOT
RUN = ROOT/'kg_datasets/dblp/course_v4_runs/abstract_benchmark_development_20261008_46'
EVIDENCE = ROOT/'docs/evidence/20261008_round46'
REGRESSION = ROOT/'kg_datasets/dblp/course_v4_runs/tests_20261008_round46_workspace_temp_final.xml'
VERIFICATION = ROOT/'kg_datasets/dblp/course_v4_runs/verification_20261008_round46.json'


def checked():
    manifest = g.verified_files(RUN)
    if any(c.file_sha256(ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Training source/input drift')
    config, parent, _, data = training.load_inputs(); state = read(RUN/'status.json'); result = read(RUN/'development_result.json'); comparison = read(RUN/'pipeline_development_result.json')
    if state['status'] != 'completed' or result['version'] != config['version'] or not result['passed'] or result['testEvaluated'] or result['modelPromoted'] or result['qualityPromotionPassed'] or comparison['gates']['developmentGatesPassed']: raise ValueError('Experiment completion/gate drift')
    expected = {'NER': (58, 16, 174, 'checkpoint_epoch_04'), 'RE': (271, 333, 408, 'checkpoint_epoch_06')}
    for task, (train, dev, steps, checkpoint) in expected.items():
        entry = result[task]; folder = RUN/task.lower(); logs = c.read_jsonl(folder/'steps.jsonl'); epochs = read(folder/'epochs.json')
        if (entry['trainInputs'], entry['devInputs'], entry['steps'], entry['bestCheckpoint']) != (train, dev, steps, checkpoint) or len(logs) != steps or [s['step'] for s in logs] != list(range(1, steps+1)) or len(epochs) != 6 or not entry['classifierAndEncoderChanged'] or not entry['reloadPredictionsIdentical'] or entry['devUsedForGradient'] or not (folder/checkpoint/'model.safetensors').exists(): raise ValueError('Actual fit/checkpoint trace drift')
    queue = data['dev']['ner']; full = data['dev']['full_relation']; refs = c.read_jsonl(RUN/'pipeline_dev_reference_pairs.jsonl')
    if full != c.read_jsonl(RUN/'pipeline_dev_documents.jsonl') or len(refs) != 107 or len(full) != 7: raise ValueError('Full dev scope drift')
    for name in ('old', 'new'):
        rows = c.read_jsonl(RUN/(name+'_ner_dev_predictions.jsonl'))
        if [r['sampleId'] for r in rows] != [r['sampleId'] for r in queue] or [r['referenceEntities'] for r in rows] != [r['entities'] for r in queue]: raise ValueError('NER reference binding drift')
        score = training.ner.score_rows(queue, [r['predictedEntities'] for r in rows], evaluation_target=training.prior.TARGET)
        if score != comparison['nerDevMetrics'][name]['metrics']: raise ValueError('NER metrics differ from predictions')
        module = c.read_jsonl(RUN/(name+'_module_dev_predictions.jsonl'))
        metric = training.prior.dev_scope(training.re_model.score_relations(data['dev']['relation'], [r['label'] for r in module])) | {'evaluationTarget': training.prior.TARGET}
        if len(module) != 333 or metric != comparison['moduleMetrics'][name]: raise ValueError('RE module metric drift')
    gold = {(r['sampleId'], training.re_model.pair_key(r), r['label']) for r in refs if r['label'] != 'NO_RELATION'}
    fp = {}
    for ner_name in ('old', 'new'):
        for re_name in ('old', 'new'):
            name = ner_name+'_NER_'+re_name+'_RE'; predictions = c.read_jsonl(RUN/(name+'_predictions.jsonl'))
            score = training.prior.dev_scope(training.prior.score_pipeline(full, refs, predictions), 'complete_document_exposed_dev_AI_reference_not_final_test')['positiveMicro']
            if score != comparison['pipelineMetrics'][name]['positiveMicro']: raise ValueError('Pipeline metric drift: '+name)
            positives = [r for r in predictions if r['label'] != 'NO_RELATION']
            fp[name] = Counter(r['sampleId'] for r in positives if (r['sampleId'], training.re_model.pair_key(r), r['label']) not in gold)
            if sum(fp[name].values()) != score['predicted']-score['truePositive']: raise ValueError('False-positive accounting drift')
    if comparison['pipelineMetrics']['old_NER_old_RE']['positiveMicro']['f1'] <= comparison['pipelineMetrics']['new_NER_new_RE']['positiveMicro']['f1']: raise ValueError('Recorded non-promotion reason changed')
    junit = ET.parse(REGRESSION).getroot().find('testsuite').attrib
    if (junit['tests'], junit['errors'], junit['failures'], junit['skipped']) != ('374', '0', '0', '0'): raise ValueError('Regression failed/partial')
    return {'runManifestSha256': c.file_sha256(RUN/'manifest.json'), 'trainingContractSha256': c.file_sha256(training.CONTRACT), 'regressionSha256': c.file_sha256(REGRESSION), 'engineeringTests': 374,
        'regressionSeconds': float(junit['time']), 'baselinePipeline': comparison['pipelineMetrics']['old_NER_old_RE']['positiveMicro'], 'candidatePipeline': comparison['pipelineMetrics']['new_NER_new_RE']['positiveMicro'],
        'falsePositivesByDocument': {k: dict(v) for k, v in fp.items()}, 'gates': comparison['gates']['checks'], 'testEvaluated': False, 'independentHumanGold': False, 'modelPromoted': False}, result, comparison


def prepare():
    state, result, comparison = checked()
    if EVIDENCE.exists(): raise FileExistsError('Preserve evidence; no overwrite')
    EVIDENCE.mkdir(parents=True)
    sources = [Path(__file__), training.CONTRACT, Path(training.__file__), RUN/'manifest.json', RUN/'status.json', RUN/'preflight.json', RUN/'development_result.json', RUN/'pipeline_development_result.json', REGRESSION, ROOT/'kg_datasets/dblp/course_v4_runs/round46_preflight_failure.json']
    sources += [RUN/task.lower()/name for task in ('NER', 'RE') for name in ('status.json', 'development_result.json', 'epochs.json', 'steps.jsonl')]
    for source in sources:
        target = EVIDENCE/'sources'/source.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
    c.write_json(EVIDENCE/'audit_state.json', state)
    stamp = datetime.now(UTC).isoformat(); ner_old = comparison['nerDevMetrics']['old']['metrics']; ner_new = comparison['nerDevMetrics']['new']['metrics']
    rows = []
    for label in ('micro', 'METHOD', 'TASK', 'DATASET'):
        a = ner_old['micro'] if label == 'micro' else ner_old['perClass'][label]; b = ner_new['micro'] if label == 'micro' else ner_new['perClass'][label]
        rows.append([label, a['reference'], f"{a['precision']:.2%} / {a['recall']:.2%} / {a['f1']:.2%}", f"{b['precision']:.2%} / {b['recall']:.2%} / {b['f1']:.2%}"])
    body = '<p>使用第45轮已封存训练输入，同一16篇开发摘要重新推理旧42模型和新46模型。训练从原始08/15权重各启动一次；开发集仅选epoch，不调参。AI参考标签与同会话自复核，非独立人工gold。</p>'
    body += table(['实体类别', '开发集参考数', '旧42 P/R/F1', '新46 P/R/F1'], rows)
    body += '<h2>真实训练步与选择</h2>' + table(['任务', '训练/开发输入', '真实步数', '选择epoch', '权重变化/重载'], [['NER','58篇 / 16篇','174','4','分类头与编码器变化；重载预测一致'], ['RE','271对 / 333对','408','6','分类头与编码器变化；重载预测一致']])
    body += '<h2>NER 逐步实际训练损失（对数纵轴）</h2>'+loss_curve(c.read_jsonl(RUN/'ner/steps.jsonl'))
    body += '<p>开发集已暴露且DATASET仅15个参考跨度；66.67%召回不代表新模型泛化可靠。完整流程结果见第二张图。</p>'
    (EVIDENCE/'02_training.html').write_text(page('新版摘要实体训练与稀有类召回 · 第46轮', body, stamp, ['sources/kg_datasets/dblp/course_v4_runs/abstract_benchmark_development_20261008_46/ner/steps.jsonl', 'sources/kg_datasets/dblp/course_v4_runs/abstract_benchmark_development_20261008_46/development_result.json']), encoding='utf-8')
    names = [('旧NER＋旧RE','old_NER_old_RE'),('新NER＋旧RE','new_NER_old_RE'),('旧NER＋新RE','old_NER_new_RE'),('新NER＋新RE','new_NER_new_RE')]
    matrix = [[display, *[f'{m[k]:.2%}' for k in ('precision','recall','f1')], m['truePositive'], m['predicted']-m['truePositive']] for display, key in names for m in [comparison['pipelineMetrics'][key]['positiveMicro']]]
    module = [[n, f"{comparison['moduleMetrics'][k]['positiveMicro']['f1']:.2%}", f"{comparison['moduleMetrics'][k]['perClass']['NO_RELATION']['recall']:.2%}"] for n, k in [('旧42','old'),('新46','new')]]
    body = '<p>同7篇完整开发摘要、84条正关系参考重新推理四种组合。完整流程按文献、方向、实体边界/类型和关系标签精确匹配，负关系不计为真阴性。</p>'
    body += table(['组合', 'P', 'R', 'F1', '正确正边', '错报正边'], matrix)
    body += '<h2>条件关系模块（输入参考实体，333个已判对）</h2>'+table(['模型','正关系F1','NO_RELATION召回'],module)
    body += '<p>旧NER配新RE仍为54.35%；新NER配旧RE为39.22%。当前退化主要随新NER进入完整流程，不能拿条件模块94.18%代替完整流程39.53%。新NER更常给出边界不同的实体，漏边原因从missing26/boundary8变为missing11/boundary23；多出约69条错报正边。</p>'
    body += '<h2>晋级约束</h2>'+table(['条件','结果'],[[k,'通过' if v else '未通过'] for k,v in comparison['gates']['checks'].items()])
    body += '<p>完整EVALUATED_ON正例0，完整开发文档7/19，既有测试未运行；两模型与生产图谱均未替换。首次入口文件绑定错误在训练前失败，已保存失败记录并修复；374项回归通过。</p>'
    (EVIDENCE/'07_relation_development.html').write_text(page('同范围完整抽取对照与晋级门槛 · 第46轮', body, stamp, ['sources/kg_datasets/dblp/course_v4_runs/abstract_benchmark_development_20261008_46/pipeline_development_result.json', 'sources/kg_datasets/dblp/course_v4_runs/tests_20261008_round46_workspace_temp_final.xml']), encoding='utf-8')
    c.write_json(EVIDENCE/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'filesSha256': {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})
    print({'prepared': True, 'falsePositiveOld': sum(state['falsePositivesByDocument']['old_NER_old_RE'].values()), 'falsePositiveNew': sum(state['falsePositivesByDocument']['new_NER_new_RE'].values())})


def finish():
    state, _, _ = checked()
    if VERIFICATION.exists(): raise FileExistsError('Preserve verification; no overwrite')
    g.verified_files(EVIDENCE)
    if read(EVIDENCE/'audit_state.json') != state: raise ValueError('Evidence audit changed')
    captures = json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig'))
    if captures['status'] != 'completed' or {(r['sourcePage'], r['image']) for r in captures['captures']} != {('02_training.html','02_training.png'),('07_relation_development.html','07_relation_development.png')}: raise ValueError('Screenshots incomplete')
    for item in captures['captures']:
        if c.file_sha256(EVIDENCE/item['image']) != item['sha256'] or c.file_sha256(EVIDENCE/item['sourcePage']) != item['sourcePageSha256']: raise ValueError('Capture drift')
    c.write_json(VERIFICATION, {'passed': True, 'checkedAtUTC': datetime.now(UTC).isoformat(), 'audit': state, 'evidenceManifestSha256': c.file_sha256(EVIDENCE/'manifest.json'), 'capturesSha256': c.file_sha256(EVIDENCE/'captures.json'), 'previousVerificationSha256': c.file_sha256(ROOT/'kg_datasets/dblp/course_v4_runs/verification_20261008_round45.json'), 'modelPromoted': False, 'qualityPromotionPassed': False})
    print({'passed': True, 'engineeringTests': 374, 'pipelineF1': state['candidatePipeline']['f1'], 'modelPromoted': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('prepare','seal')); args = parser.parse_args()
    prepare() if args.action == 'prepare' else finish()
