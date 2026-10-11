"""Recompute sealed exposed-dev comparison; no model calls and no reserved-test parsing."""
import math
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_graph as g
import course_weak as c
import compare_pretrained_ner as comparison
from course_abstract_v1 import read
from evaluate_course_relation import candidate_rows, score_pipeline
from export_course_evidence import page, table
from train_course_ner import score_rows

READY = ROOT / 'kg_datasets/dblp/course_v4_runs/pretrained_ner_comparison_20261010_58_ready'
REPLAY = ROOT / 'kg_datasets/dblp/course_v4_runs/pretrained_ner_comparison_20261010_58_replay'
OUTPUT = ROOT / 'docs/evidence/20261010_round58_model'
LOCKS = ('c6a24649a82784efd6960fc5c857cd15c431900ed874824879d613a50c6ec4aa',
         '8846abec60560fa791709ee1196d4da5828d89056df9428631d272c77015e8ae')
ARTIFACTS = ('gliner_raw_predictions.jsonl', 'gliner_ner_predictions.jsonl',
             'gliner_relation_predictions.jsonl', 'scibert52_relation_predictions.jsonl', 'token_lengths.json')


def check():
    config, rows, full, refs, cache = comparison.load_inputs()
    inputs = {Path(__file__).resolve(), comparison.CONTRACT}
    inputs.update(ROOT / 'scripts' / name for name in (
        'course_graph.py', 'course_weak.py', 'course_abstract_v1.py', 'compare_pretrained_ner.py',
        'train_course_ner.py', 'train_course_relation.py', 'evaluate_course_relation.py', 'export_course_evidence.py'))
    inputs.update((c.CONFIG_PATH, c.SCHEMA_PATH))
    manifests = []
    for folder, lock in zip((READY, REPLAY), LOCKS):
        manifest = g.verified_files(folder, lock)
        assert read(folder / 'status.json')['status'] == 'completed'
        for name, sha in manifest['inputSha256'].items():
            path = (ROOT / name).resolve()
            assert path.is_relative_to(ROOT.resolve()) and c.file_sha256(path) == sha, name
            inputs.add(path)  # Reserved test is bound by binary SHA only, never decoded.
        manifests.append(manifest)
        inputs.update((folder / 'manifest.json', folder / 'status.json', folder / 'comparison.json'))
        inputs.update(folder / name for name in ARTIFACTS)
    assert manifests[0]['inputSha256'] == manifests[1]['inputSha256']
    replay_sha = {name: c.file_sha256(READY / name) for name in ARTIFACTS}
    assert all(replay_sha[name] == c.file_sha256(REPLAY / name) for name in ARTIFACTS)
    hashes = {str(p.relative_to(ROOT)): c.file_sha256(p) for p in sorted(inputs)}
    result = read(READY / 'comparison.json')
    rerun = read(REPLAY / 'comparison.json')
    for name in ('NER', 'pipeline', 'NERDocuments', 'completeDocuments', 'lockedQueue', 'documentCoverage',
                 'testEvaluated', 'trainingExecuted', 'modelPromoted', 'thresholdSearch', 'inferenceFeatures',
                 'externalPretrainingOverlapUnknown', 'notice', 'versions'):
        assert result[name] == rerun[name], name
    assert all(result[k] is False for k in ('testEvaluated', 'trainingExecuted', 'modelPromoted', 'thresholdSearch'))
    assert result['externalPretrainingOverlapUnknown'] is True
    assert result['inferenceFeatures'] == 'original_text_and_fixed_label_descriptions_only'
    assert 'exposed dev' in result['notice'] and result['versions']['gliner'] == config['runtimeVersion']
    assert result['NERDocuments'] == len(rows) == 16 and result['completeDocuments'] == len(full) == 7
    assert result['lockedQueue'] == 19 and result['documentCoverage'] == 7 / 19
    raw = c.read_jsonl(READY / ARTIFACTS[0]); mapped = c.read_jsonl(READY / ARTIFACTS[1])
    assert [p['sampleId'] for p in raw] == [p['sampleId'] for p in mapped] == [r['sampleId'] for r in rows]
    assert all(r['entities'] == p['referenceEntities'] for r, p in zip(rows, mapped))
    assert all(comparison.checked_entities(r, p['predictions']) == m['predictedEntities']
               for r, p, m in zip(rows, raw, mapped))
    predictions = {'scibert52': cache, 'gliner': mapped}
    scores, endpoint_coverage = {}, {}
    for name, values in predictions.items():
        score = score_rows(rows, [p['predictedEntities'] for p in values], evaluation_target='exposed_dev_AI_reference')
        assert score == result['NER'][name]
        by_id = {p['sampleId']: p['predictedEntities'] for p in values}
        edges = c.read_jsonl(READY / (name + '_relation_predictions.jsonl'))
        candidates = [p for doc in full for p in candidate_rows(doc, by_id[doc['sampleId']])]
        assert len(candidates) == len(edges)
        for candidate, edge in zip(candidates, edges):
            assert all(candidate[k] == edge[k] for k in candidate), name
            probabilities = edge['probabilities']
            assert all(math.isfinite(v) and 0 <= v <= 1 for v in probabilities.values())
            assert math.isclose(sum(probabilities.values()), 1, abs_tol=1e-5)
            assert edge['label'] == max(probabilities, key=probabilities.get)
        pipeline = score_pipeline(full, refs, edges)
        pipeline['evaluationTarget'] = 'complete_document_exposed_dev_AI_reference_not_final_test'
        assert pipeline == result['pipeline'][name]
        coverage = Counter()
        for pair in (p for p in refs if p['label'] != 'NO_RELATION'):
            entities = by_id[pair['sampleId']]
            keys = {(e['start'], e['end'], e['label']) for e in entities}
            spans = {(e['start'], e['end']) for e in entities}
            head, tail = (pair[k] for k in ('head', 'tail'))
            h = (head['start'], head['end'], head['label']) in keys
            t = (tail['start'], tail['end'], tail['label']) in keys
            coverage['both' if h and t else 'headOnly' if h else 'tailOnly' if t else 'neither'] += 1
            coverage['bothBoundariesIgnoringType'] += int(all((e['start'], e['end']) in spans for e in (head, tail)))
        scores[name] = {'NER': score, 'pipeline': pipeline, 'candidateLabels': dict(Counter(e['label'] for e in edges))}
        endpoint_coverage[name] = {k: coverage[k] for k in ('both', 'headOnly', 'tailOnly', 'neither', 'bothBoundariesIgnoringType')}
    assert endpoint_coverage['gliner'] == dict(both=0, headOnly=45, tailOnly=0, neither=39, bothBoundariesIgnoringType=0)
    assert scores['gliner']['pipeline']['positiveMicro']['truePositive'] == 0
    lengths = read(READY / 'token_lengths.json'); model_config = read(ROOT / config['modelDirectory'] / 'gliner_config.json')
    backbone_config = read(ROOT / config['tokenizerDirectory'] / 'config.json')
    assert [p['sampleId'] for p in lengths] == [r['sampleId'] for r in rows]
    width_issues = []
    for row, length in zip(rows, lengths):
        words = list(re.finditer(r'\w+(?:[-_]\w+)*|\S', row['text']))
        assert len(words) == length['words'] <= model_config['max_len']
        assert 0 < length['subtokensWithLabels'] <= backbone_config['max_position_embeddings']
        for entity in row['entities']:
            aligned = [w for w in words if entity['start'] <= w.start() and w.end() <= entity['end']]
            if not aligned or aligned[0].start() != entity['start'] or aligned[-1].end() != entity['end'] or len(aligned) > model_config['max_width']:
                width_issues.append((row['sampleId'], entity))
    assert not width_issues
    examples = []
    for publication, predicted, reference in (
            ('abs-2403.13872', 'future state prediction task', 'future state prediction'),
            ('abs-1904.04163', 'speech recognition N-bestrescoring task', 'speech recognition N-bestrescoring'),
            ('abs-2404.09802', 'Temporal Convolutional Network (TCN)', 'Temporal Convolutional Network'),
            ('abs-2411.06463', 'ResNet', 'ResNet')):
        row = next(r for r in rows if r['publicationId'].endswith(publication))
        p = next(e for e in predictions['gliner'][[r['sampleId'] for r in rows].index(row['sampleId'])]['predictedEntities'] if e['text'] == predicted)
        r = next(e for e in row['entities'] if e['text'] == reference)
        assert (p['start'], p['end'], p['label']) != (r['start'], r['end'], r['label'])
        examples.append({'publicationId': row['publicationId'], 'predicted': p, 'reference': r})
    assert all(c.file_sha256(ROOT / path) == sha for path, sha in hashes.items())
    return {'status': 'passed', 'qualityPromotionPassed': False, 'testParsedOrEvaluated': False, 'modelCalled': False,
            'evaluationTarget': 'exposed_dev_AI_reference_not_final_test', 'independentHumanGold': False,
            'externalPretrainingOverlapUnknown': True, 'scores': scores, 'endpointCoverage': endpoint_coverage,
            'byteIdenticalReplaySha256': replay_sha, 'inputSha256': hashes, 'examples': examples,
            'NERDocuments': len(rows), 'NERQueue': 19, 'completeDocuments': len(full), 'relationQueue': 19,
            'positiveSupport': dict(Counter(r['label'] for r in refs if r['label'] != 'NO_RELATION')),
            'maximumWords': max(p['words'] for p in lengths), 'maximumSubtokensWithLabels': max(p['subtokensWithLabels'] for p in lengths),
            'spanWidthIssues': width_issues, 'versionsRecordedByRun': result['versions'],
            'legacyNestedEvaluationTarget': result['pipeline']['gliner']['positiveMicro']['evaluationTarget']}


def main():
    if sys.flags.optimize: raise RuntimeError('Assertions must remain enabled')
    targets = [OUTPUT / name for name in ('03_predictions.html', 'prediction_check.json', 'manifest.json')]
    if any(p.exists() for p in targets): raise FileExistsError('Preserve previous audit; do not overwrite')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).isoformat()
    try:
        audit = check(); audit['checkedAtUTC'] = stamp
        c.write_json(targets[1], audit)
        metrics = []
        for name, scores in audit['scores'].items():
            for task, metric in (('NER', scores['NER']['micro']), ('Pipeline', scores['pipeline']['positiveMicro'])):
                metrics.append((name, task, f"{metric['truePositive']}/{metric['predicted']}/{metric['reference']}",
                    f"{metric['precision']:.2%}", f"{metric['recall']:.2%}", f"{metric['f1']:.2%}",
                    metric['predicted'] - metric['truePositive'], metric['reference'] - metric['truePositive']))
        example_rows = [(e['publicationId'], f"{e['predicted']['text']} [{e['predicted']['start']}:{e['predicted']['end']}] {e['predicted']['label']}",
                         f"{e['reference']['text']} [{e['reference']['start']}:{e['reference']['end']}] {e['reference']['label']}") for e in audit['examples']]
        body = ('<p>同范围固定对照：SciBERT52 / GLiNER medium-v2.1，均接同一个冻结的57轮RE。'
                '未重训、未搜索阈值、未读保留测试、未部署；AI参考标签并非独立人工金标准。</p>'
                '<p>NER：16/19篇开发队列；完整Pipeline：7/19篇、84条正参考关系（全为USED_FOR，EVALUATED_ON支持为0）。'
                '这是已暴露开发集，不是最终测试成绩。GLiNER外部预训练与本数据是否重叠未知。</p>'
                '<h2>保存预测独立复算</h2>' + table(('模型', '任务', 'TP/预测/参考', 'Precision', 'Recall', 'F1', 'FP', 'FN'), metrics)
                + '<h2>为什么完整流程为0</h2><p>84条正参考关系中，GLiNER严格端点覆盖：两端0、仅头45、仅尾0、两端都无39。'
                '忽略类别、仅要求两端原字符边界相同仍为0。TASK：0/53参考实体严格命中。'
                '关系分类器无法恢复未被NER正确找到的端点；不是把全部真实关系判为无关系。</p>'
                + table(('论文', 'GLiNER预测原字符跨度 / 类别', 'AI参考原字符跨度 / 类别'), example_rows)
                + '<h2>完整性与局限</h2><p>ready与固定配置replay的raw NER、映射NER、两组关系预测及长度记录5项SHA完全相同。'
                f"本队列最大词数{audit['maximumWords']}、含标签子词数{audit['maximumSubtokensWithLabels']}，均低于模型上限；184个参考实体无超12词或分词边界不齐问题。</p>"
                '<p>历史评分函数的嵌套字段仍写held_out_ai_reference_agreement_not_human_gold；外层已声明exposed-dev。'
                '嵌套旧名称不证明使用了未暴露测试，本页明确按开发集解释，原封存产物未改。</p>'
                '<p>仅检验这一固定标签说明/.5阈值/flatNER配置，不能推广为所有预训练模型的表现。'
                '实际权重、输入及保存源码SHA已核验；官方revision声明与下载来源链、Python/protobuf/CUDA驱动等完整运行环境未由本run直接绑定。'
                '当前环境补记不能冒充推理当时环境。qualityPromotionPassed仍为false。</p>')
        targets[0].write_text(page('第58轮：保存预测复核与零分端点诊断', body, stamp,
            [str(READY / 'manifest.json'), str(REPLAY / 'manifest.json'), str(targets[1])]), encoding='utf-8')
        c.write_json(targets[2], {'kind': 'real_artifact_visualization_not_original_console_ui', 'status': 'passed',
            'generatedAtUTC': stamp, 'inputSha256': audit['inputSha256'],
            'filesSha256': {str(p.relative_to(OUTPUT)): c.file_sha256(p) for p in targets[:2]}})
        print({'status': 'passed', 'replayFilesByteIdentical': len(ARTIFACTS), 'output': str(OUTPUT), 'qualityPromotionPassed': False})
    except Exception as error:
        c.write_json(targets[1], {'status': 'failed_no_synthetic_fallback', 'checkedAtUTC': stamp,
            'errorType': type(error).__name__, 'error': str(error), 'qualityPromotionPassed': False})
        c.write_json(targets[2], {'kind': 'failed_readonly_prediction_audit', 'status': 'failed_no_synthetic_fallback',
            'checkerSha256': c.file_sha256(Path(__file__)), 'filesSha256': {targets[1].name: c.file_sha256(targets[1])}})
        raise


if __name__ == '__main__': main()
