"""Recompute source/inference evidence and render it; never reads the reserved test text."""
import argparse
import os
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT/'scripts'))
import diagnose_diverse_train_roles as diagnostic
from course_abstract_v1 import read
from course_bio_constraints import legal_bio_labels
from export_course_evidence import page, table

c, g, ner = diagnostic.c, diagnostic.g, diagnostic.diverse.ner
RUN = ROOT/'kg_datasets/dblp/course_v4_runs/diverse_role_diagnostic_20261010_56'
EVIDENCE = ROOT/'docs/evidence/20261010_round56'
JUNIT = ROOT/'kg_datasets/dblp/course_v4_runs/tests_role56_final.xml'


def checked():
    rows, original, _ = diagnostic.load_inputs(); manifest = g.verified_files(RUN)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    assert read(RUN/'status.json')['status'] == 'completed' and c.read_jsonl(RUN/'inputs.jsonl') == rows
    result = read(RUN/'diagnostic_result.json'); errors = []
    for name, model in result['models'].items():
        predictions = c.read_jsonl(RUN/(name+'_predictions.jsonl')); saved = c.read_jsonl(RUN/(name+'_errors.jsonl'))
        assert diagnostic.diagnostic.scored(rows, predictions) == model['metrics']
        expected = [r | {'pairId': p['pairId'], 'referenceLabel': r['label'], 'predictedLabel': p['label'], 'modelScores': p['probabilities']} for r, p in zip(rows, predictions) if r['label'] != p['label']]
        assert saved == expected and len(saved) == model['errors']
        assert model['negativeContrastCorrect'] == sum(r['label'] == p['label'] == 'NO_RELATION' for r, p in zip(rows, predictions))
        assert model['positiveTaskCorrect'] == sum(r['label'] == p['label'] == 'USED_FOR' for r, p in zip(rows, predictions))
        errors.extend({'model': name, **r} for r in saved)
    mapping = diagnostic.re_model.type_majority(original)
    assert diagnostic.prior.dev_scope(diagnostic.re_model.score_relations(rows, [mapping[r['tail']['label']] for r in rows]), diagnostic.diagnostic.TARGET) == result['typeMajorityFromOld386']
    assert all(result[k] is False for k in ('trainingExecuted', 'devContentAccessed', 'testContentConsumed', 'independentHumanGold', 'qualityPromotionPassed', 'modelPromoted'))
    os.environ.setdefault('HF_HUB_OFFLINE', '1'); tokenizer = diagnostic.re_model.prepare_tokenizer(ROOT/'kg_datasets/models/scibert_24f92d32')
    cohorts = {split: c.read_jsonl(diagnostic.SOURCE/filename) for split, filename in [('train', 'ner_train_frozen.jsonl'), ('dev', 'ner_dev.jsonl')]}; alignment = {}
    for split, docs in cohorts.items():
        sizes = []; gaps = []
        for doc in docs:
            record = ner.encode_row(tokenizer, doc, 512); offsets = record['offsets']; labels = record['features']['labels']; sizes.append(len(offsets))
            decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else label for o, label in zip(offsets, labels)], offsets, doc['text'])
            assert not decoded['invalidTransitions'] and decoded['entities'] == [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in doc['entities']]
            end = 0
            for start, stop in offsets:
                if start == stop: continue
                if doc['text'][end:start].strip(): gaps.append({'sampleId': doc['sampleId'], 'start': end, 'end': start})
                end = stop
            if doc['text'][end:].strip(): gaps.append({'sampleId': doc['sampleId'], 'start': end, 'end': len(doc['text'])})
        alignment[split] = {'documents': len(docs), 'minTokens': min(sizes), 'maxTokens': max(sizes), 'strictBIORoundTripPassed': True, 'nonWhitespaceGaps': gaps}
    assert (alignment['train']['documents'], alignment['dev']['documents']) == (65, 16) and not any(a['nonWhitespaceGaps'] for a in alignment.values())
    run52 = ROOT/'kg_datasets/dblp/course_v4_runs/abstract_boundary_development_20261009_52'; g.verified_files(run52)
    predictions52 = c.read_jsonl(run52/'new_ner_dev_predictions.jsonl'); dev = cohorts['dev']
    assert [r['sampleId'] for r in dev] == [p['sampleId'] for p in predictions52] and all(r['entities'] == p['referenceEntities'] for r, p in zip(dev, predictions52))
    metrics = ner.score_rows(dev, [p['predictedEntities'] for p in predictions52], evaluation_target='exposed_dev_ai_reference_not_new_inference')
    causes = {'missing': 0, 'classOnly': 0, 'boundaryOnly': 0, 'boundaryAndClass': 0}
    for item in predictions52:
        for gold in item['referenceEntities']:
            if any(all(p[k] == gold[k] for k in ('start', 'end', 'label')) for p in item['predictedEntities']): continue
            overlap = [p for p in item['predictedEntities'] if p['start'] < gold['end'] and gold['start'] < p['end']]
            cause = 'classOnly' if any((p['start'], p['end']) == (gold['start'], gold['end']) for p in overlap) else 'boundaryOnly' if any(p['label'] == gold['label'] for p in overlap) else 'boundaryAndClass' if overlap else 'missing'
            causes[cause] += 1
    assert sum(causes.values()) == metrics['micro']['reference']-metrics['micro']['truePositive']
    text = 'BERT\x01NER'; offsets = tokenizer(text, return_offsets_mapping=True)['offset_mapping']
    logits = [[0., -1., -1., -1., -1., -1., -1.] if s == e else [0., 10., 1., -1., -1., -1., -1.] if s == 0 else [0., 1., 10., -1., -1., -1., -1.] for s, e in offsets]
    gap = ner.decode_bio(legal_bio_labels(logits, offsets), offsets, text)
    assert gap['invalidTransitions'] == 1
    suites = ET.parse(JUNIT).getroot().findall('testsuite'); totals = {k: sum(int(s.get(k, '0')) for s in suites) for k in ('tests', 'errors', 'failures', 'skipped')}
    assert totals['tests'] >= 12 and not any(totals[k] for k in ('errors', 'failures', 'skipped'))
    audit = {'passed': True, 'dataSummary': read(diagnostic.SOURCE/'summary.json'), 'diagnostic': result, 'NERAlignment': alignment, 'historical52NERDevRecount': {'metrics': metrics, 'unmatchedReferenceCauses': causes, 'newNERInferenceExecuted': False}, 'rejectedExperimentalDecoderGap': {'textRepresentation': 'BERT\\u0001NER', 'offsets': offsets, 'invalidTransitions': gap['invalidTransitions'], 'productionUsesThisBranch': False, 'currentTrainDevTriggered': False, 'fixRequiredBeforeActivation': True}, 'engineeringTests': totals, 'regressionSeconds': sum(float(s.get('time', '0')) for s in suites), 'trainingDeferred': read(RUN/'training_deferred.json'), 'dataManifestSha256': c.file_sha256(diagnostic.SOURCE/'manifest.json'), 'runManifestSha256': c.file_sha256(RUN/'manifest.json'), 'testContentConsumed': False, 'qualityPromotionPassed': False, 'modelPromoted': False, 'authorWorkPerformed': False, 'conceptWorkPerformed': False, 'onlineAcceptancePerformed': False, 'reportExpansionPaused': True}
    return audit, errors


def prepare():
    if EVIDENCE.exists(): raise FileExistsError('Preserve evidence pages')
    audit, errors = checked(); EVIDENCE.mkdir(parents=True); c.write_json(EVIDENCE/'audit_state.json', audit)
    stamp = datetime.now(UTC).isoformat(); run52 = ROOT/'kg_datasets/dblp/course_v4_runs/abstract_boundary_development_20261009_52'
    body = table(['库存', '核验结果'], [['训练来源', '70篇不换样；5篇局部关系源文判断/同会话AI复核'], ['明确关系', '386→408：用途307 / 评测64 / 负例37'], ['新增支持', '19用途来自5篇；3负例仅1篇；没有新增评测支持'], ['未决与覆盖', '1,949 / 2,357仍未知；已判17.31%'], ['保持不变', '65篇NER / 787实体 / 5隔离 / 旧386关系 / 9开发文件'], ['NER对齐检查', '65训练＋16开发BIO往返通过；最长350/302 token；无非空白gap'], ['工程回归', f"{audit['engineeringTests']['tests']}通过；不是语义准确率测试"], ['训练资源', f"D盘诊断时{audit['trainingDeferred']['freeDiskBytes']:,}字节；旧单检查点预算1,506,824,700字节，未重训"]])
    body += '<p>来源范围：2411.04637是教程文字；CelebAHQ-IDI只明确训练，评测关系保持未知。受约束BIO的特殊控制字符gap缺陷只在已拒绝实验分支，当前队列未触发；不启用该分支。</p><p>原始初次快照及失败测试保留，最终使用_final包；没有覆盖历史模型、图谱或测试文件。</p>'
    paths = [diagnostic.SOURCE, RUN, JUNIT]
    (EVIDENCE/'01_data.html').write_text(page('第56轮 · 跨论文训练证据与NER对齐核验', body, stamp, [str(p) for p in paths]), encoding='utf-8')
    body = table(['固定模型', '用途正确 / 19', '角色反例正确 / 3', '错例数'], [[name, data['positiveTaskCorrect'], data['negativeContrastCorrect'], data['errors']] for name, data in audit['diagnostic']['models'].items()]+[['旧386类型多数基线', 19, 0, 3]])
    body += '<p>全部22对来自训练侧，使用参考实体，不是Pipeline或留出集成绩。三个反例是同一论文的关联发生点；本轮没有EVALUATED_ON参考，不能据此估计总体准确率。</p>'
    body += table(['模型', '方法发生点', '任务', 'AI参考', '预测'], [[e['model'], e['head']['text'], e['tail']['text'], e['referenceLabel'], e['predictedLabel']] for e in errors])
    causes = audit['historical52NERDevRecount']['unmatchedReferenceCauses']
    body += f'<p>旧52版16篇已暴露开发预测重算：46个未匹配参考实体，缺失{causes["missing"]}、仅类别{causes["classOnly"]}、仅边界{causes["boundaryOnly"]}、二者兼有{causes["boundaryAndClass"]}。不是新NER推理，也不把所有Pipeline错误归为NER。</p><p>结论：54版局部角色诊断仍弱于46版；两者都未达到升级条件，不替换生产权重。AI自复核不是独立人工金标准。</p>'
    (EVIDENCE/'03_predictions.html').write_text(page('第56轮 · 冻结模型真实诊断与错误边界', body, stamp, [str(RUN/'diagnostic_result.json'), str(run52/'new_ner_dev_predictions.jsonl')]), encoding='utf-8')
    c.write_json(EVIDENCE/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'createdAtUTC': stamp, 'inputSha256': {p.relative_to(ROOT).as_posix(): c.file_sha256(p) for p in [Path(__file__), diagnostic.SOURCE/'manifest.json', RUN/'manifest.json', JUNIT, ROOT/'scripts/export_course_evidence.py', ROOT/'scripts/course_bio_constraints.py', run52/'new_ner_dev_predictions.jsonl']}, 'filesSha256': {p.name: c.file_sha256(p) for p in EVIDENCE.iterdir() if p.is_file()}})
    print({'prepared': True, 'tests': audit['engineeringTests'], 'NERUnmatchedCauses': causes, 'qualityPromotionPassed': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('check', 'prepare')); args = parser.parse_args()
    if args.action == 'prepare': prepare()
    else: print(checked()[0])
