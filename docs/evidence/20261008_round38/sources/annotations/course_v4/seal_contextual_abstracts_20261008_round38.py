"""Audit occurrence repair and unchanged artifacts; archive actual browser-renderable evidence."""
import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import course_graph as g
import course_weak as c
import train_course_ner as ner
from course_abstract_v1 import read
from course_abstract_relation import rows_for
from revise_contextual_abstracts import CONTRACT, source_cohort, response_for
from export_course_evidence import page, table, highlight

RUNS = ROOT/'kg_datasets/dblp/course_v4_runs'
DATA = ROOT/'kg_datasets/dblp/course_abstract_occurrence_reviewed_20261008_38'
GENERATION = ROOT/'kg_datasets/dblp/course_abstract_occurrence_generated_20261008_38'
EVIDENCE = ROOT/'docs/evidence/20261008_round38'
TESTS = RUNS/'tests_20261008_round38_scoped.xml'
DECISIONS = ROOT/'annotations/course_v4/abstract_occurrence_decisions_20261008_38.json'
REVIEWS = ROOT/'annotations/course_v4/abstract_occurrence_reviews_20261008_38.json'


def checked():
    config, refs, old = source_cohort()
    for folder in (DATA, GENERATION):
        manifest = g.verified_files(folder)
        assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    receipts = c.read_jsonl(DATA/'reviewed_receipts.jsonl'); origins = c.read_jsonl(DATA/'origins.jsonl')
    assert c.read_jsonl(DATA/'references.jsonl') == refs and len(receipts) == len(origins) == len(refs) == 58
    selected = set(config['revisionCohort']); cases = []
    initial = {r['reference']['arxivId']: r for r in c.read_jsonl(GENERATION/'generation_receipts.jsonl')}
    decisions = {d['arxivId']: d for d in read(DECISIONS)['documents']}
    for ref, before, after, origin in zip(refs, old, receipts, origins):
        revised = ref['arxivId'] in selected
        assert not c.validate_receipt(after, ref) and origin == {'sampleId': ref['sampleId'], 'upstreamReceiptSha256': before['contentSha256'], 'NERReannotated': revised, 'inheritedRelationsInvalidated': revised}
        if not revised:
            assert before == after; continue
        assert before['annotation']['entityStatus'] == 'unresolved' and after['annotation']['entityStatus'] == 'complete'
        generated = initial[ref['arxivId']]
        assert generated['annotation'] == response_for(decisions[ref['arxivId']], ref)
        assert after['initialContentSha256'] == generated['contentSha256'] and after['review']['provenance']['sourceArtifactSha256'] == c.file_sha256(REVIEWS)
        cases.append({'arxivId': ref['arxivId'], 'source': ref, 'before': before['annotation'], 'after': after['annotation'], 'upstreamReceiptSha256': before['contentSha256'], 'reviewedReceiptSha256': after['contentSha256']})
    assert len(cases) == 2 and all(not c.eligible_tasks(r, r['reference'])['ner'] for r in initial.values())
    rows = c.read_jsonl(DATA/'ner_train.jsonl'); alignment = c.read_jsonl(DATA/'token_alignment.jsonl')
    prior_rows = c.read_jsonl(ROOT/'kg_datasets/dblp/course_abstract_expansion_inputs_20261008_37/ner_train.jsonl')
    old_rows = {r['sampleId']: r for r in prior_rows}; new_rows = {r['sampleId']: r for r in rows}
    fields = ('sampleId', 'publicationId', 'groupId', 'split', 'textKind', 'text', 'textSha256', 'entities')
    assert len(rows) == len(new_rows) == len(alignment) == 50 and len(old_rows) == 48
    assert all({k: row[k] for k in fields} == {k: new_rows[sid][k] for k in fields} for sid, row in old_rows.items())
    assert set(new_rows)-set(old_rows) == {p['source']['sampleId'] for p in cases}
    assert [r['sampleId'] for r in rows] == [a['sampleId'] for a in alignment]
    for row, entry in zip(rows, alignment):
        assert entry['tokens'] == len(entry['offsets']) <= 512 and c.align_bio(entry['offsets'], row['entities'], row['text']) == entry['labels']
        decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else label for o, label in zip(entry['offsets'], entry['labels'])], entry['offsets'], row['text'])
        assert not decoded['invalidTransitions'] and decoded['entities'] == [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]
    _, pairs, full, excluded, unknown, total = rows_for(refs, receipts)
    assert pairs == c.read_jsonl(DATA/'relation_train.jsonl') and full == c.read_jsonl(DATA/'full_relation_train.jsonl') and excluded == c.read_jsonl(DATA/'excluded_ner.jsonl')
    summary = read(DATA/'summary.json'); assert summary['nerCandidates'] == 50 and summary['excludedNER'] == 8 and summary['unresolvedPairs'] == unknown == 1644 and total == 1845
    assert len(pairs) == 201 and len(full) == 6 and not summary['trainingExecuted'] and not summary['qualityPromotionPassed']
    suite = ElementTree.parse(TESTS).getroot().find('testsuite')
    assert suite.get('tests') == '366' and all(suite.get(k) == '0' for k in ('errors', 'failures', 'skipped'))
    failed = RUNS/'tests_20261008_round38_all.xml'; assert ElementTree.parse(failed).getroot().find('testsuite').get('errors') == '20'
    assert (ROOT/'pytest.ini').read_text(encoding='utf-8').strip() == '[pytest]\ntestpaths = tests'
    previous = read(RUNS/'verification_20261008_round37.json'); assert previous['passed']
    unchanged = dict(previous['immutableSourceSha256'])
    for p, sha in unchanged.items(): assert c.file_sha256(ROOT/p) == sha
    g.verified_files(ROOT/'docs/evidence/20261008_round37', previous['evidenceManifestSha256'])
    assert c.file_sha256(ROOT/'docs/evidence/20261008_round37/captures.json') == previous['capturesSha256']
    for name, sha in [('abstract_ner_development_20261008_35', '95a3c250100aa89452af0381f142f4a6b9df3e1336a1c4ed956b386e01f5a269'),
        ('abstract_relation_development_20261008_36', 'd59d94922a8b87c220a893fa949f5aaf91f721de2bd56675219802f6c21fd5fb'),
        ('abstract_ner_expansion_development_20261008_37', '05689e39fa2c75be563eafceb2b684e9578563fe254b05edbf3364526af273e6')]:
        g.verified_files(RUNS/name, sha); unchanged[(RUNS/name/'manifest.json').relative_to(ROOT).as_posix()] = sha
    parent = read(ROOT/config['parentContract']); g.verified_files(ROOT/parent['queue'], parent['queueManifestSha256'])
    expansion = read(ROOT/'resources/course_abstract_expansion_v1.json'); g.verified_files(ROOT/expansion['dev'], expansion['devManifestSha256'])
    bundle = g.configured_bundle(); assert bundle.name == 'course_v4_graph_resolved_20261007_31_ready'
    audit = {'passed': True, 'engineeringTests': 366, 'failedCollectionPreserved': True, 'previousTrainingCohort': 48, 'nerCandidates': 50,
        'wholeTrainCohort': 58, 'freshlyRejudged': 2, 'unchangedReceipts': 56, 'remainingNERQuarantines': 8, 'strictBIORoundTripDocuments': 50,
        'explicitAdditionalRelations': 6, 'resolvedRelationPairs': 201, 'unknownEligiblePairs': 1644, 'completeTrainRelationDocuments': 6,
        'old48NERTextEntitiesGroupsUnchanged': True, 'old48RowProvenanceByteIdentical': False,
        'devLabelsAndSourceUnchanged': True, 'testContentConsumed': False, 'modelTrainingExecuted': False, 'inferenceExecuted': False,
        'previousModelsVerifiedUnchanged': True, 'modelPromoted': False, 'qualityPromotionPassed': False, 'databaseWritten': False,
        'serviceRestarted': False, 'liveApplicationReaccepted': False, 'reportExpansionPaused': True,
        'dataManifestSha256': c.file_sha256(DATA/'manifest.json'), 'graphId': read(bundle/'manifest.json')['graphId'],
        'labelIndependence': 'same_session_AI_reference_not_human_gold',
        'notice': 'Representation repair and engineering preflight only, not model-performance or global semantic-quality acceptance. Remaining task-boundary consistency, rare relation support and blind evaluation still required.'}
    return audit, summary, cases, unchanged


def main(action):
    audit, summary, cases, unchanged = checked()
    if action == 'prepare':
        if EVIDENCE.exists(): raise FileExistsError('Preserve evidence')
        EVIDENCE.mkdir(parents=True)
        paths = [Path(__file__), CONTRACT, DECISIONS, REVIEWS, ROOT/'scripts/revise_contextual_abstracts.py', ROOT/'tests/test_contextual_abstracts.py',
            ROOT/'pytest.ini', ROOT/'README.md', ROOT/'docs/system_status_round38.md', TESTS, RUNS/'tests_20261008_round38_all.xml']
        paths += [p for folder in (DATA, GENERATION) for p in folder.iterdir() if p.is_file()]
        for source in paths:
            target = EVIDENCE/'sources'/source.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        c.write_json(EVIDENCE/'audit_state.json', audit); c.write_json(EVIDENCE/'contextual_cases.json', cases)
        body = '<h2>逐次出现的上下文判断 · 不修改旧标注器</h2>'+table(['项目', '实际结果', '边界'], [
            ['训练摘要', '48 → 50 / 58；隔离10 → 8', '只修订两篇已知train隔离；56篇原收据继承'],
            ['参考提及', 'METHOD378 / TASK189 / DATASET44', 'AI参考，不是人工gold或模型预测'],
            ['关系标签', '新增6条USED_FOR，明确对195 → 201', 'EVALUATED_ON43 / NO_RELATION7未增加'],
            ['未决关系', '可用NER文档中1644对仍UNRESOLVED', '不当负例；完整RE train6/58，dev仍5/19'],
            ['工程回归', '366项通过；50篇严格BIO往返', '不是366项语义验证或模型性能晋级']])
        body += '<h2>真实修复：同词不同角色，关系端点必须重建</h2>'+table(['原文位置', '本版明确判断'], [
            ['multi-LLM debiasing framework', '全名为METHOD；内部debiasing仅是词法修饰，不独立断言嵌套TASK'],
            ['for debiasing LLMs', '此处debiasing为TASK；旧e13为LLMs，新e13为debiasing，不能沿用旧边'],
            ['using machine learning (ML) methods / deploying ML', '技术方法/部署家族为METHOD'],
            ['ML Practitioners / ML community / ML development', '人群、领域、工作流不传播为METHOD']])
        body += '<h2>保留失败，不混淆新数据与新成绩</h2><p>首次根目录pytest误收集历史证据副本，20个重名收集错误原XML保留；新增pytest.ini默认只收集正式tests目录，重新执行366项通过。没有删除历史文件。</p><p>本轮没有训练、推理、改dev/test、写库、重启或新线上验收。37轮NER71.28%与pipeline26.49%仍是原先的已暴露dev诊断，不是本轮新成绩。两篇解隔离不证明模型可靠性已经解决。</p><h2>仍需完成</h2><p>其余8篇语义/共用中心词歧义不强制放行；继续核对训练任务跨度/家族与研究对象，补完整dev关系证据和稀有关系支持，锁定新pipeline后再使用未暴露测试。独立核验、长尾概念/作者身份仍有限，暂不扩大图谱或自动晋级。</p>'
        (EVIDENCE/'09_annotation_expansion.html').write_text(page('上下文标注修复与未晋级边界 · 第38轮', body, datetime.now(UTC).isoformat(), ['audit_state.json', 'contextual_cases.json', 'sources/kg_datasets/dblp/course_abstract_occurrence_reviewed_20261008_38/summary.json']), encoding='utf-8')
        case = next(p for p in cases if p['arxivId'] == '2409.13884')
        body = '<p>原文arXiv 2409.13884；训练侧AI参考标注修订，不是模型预测。下面为完整来源摘要：</p><div style="line-height:2">'+highlight(case['source']['text'], case['after']['entities'])+'</div>'
        body += table(['位置/检查', '真实结果'], [['字符621–630：debiasing', '包含在字符611–640的METHOD全名内'], ['字符771–780：debiasing', 'TASK，与后面的LLMs不重叠'], ['新增明确正对 / 仍未决', '6条有原文证据的USED_FOR / 46对UNRESOLVED'], ['源文本/分组/旧权重', '未改；50篇严格BIO往返，不是训练效果证明']])
        (EVIDENCE/'03_predictions.html').write_text(page('源文跨度与关系端点复核 · 非预测结果', body, datetime.now(UTC).isoformat(), ['contextual_cases.json', 'sources/annotations/course_v4/abstract_occurrence_reviews_20261008_38.json']), encoding='utf-8')
        c.write_json(EVIDENCE/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'filesSha256': {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})
        print(json.dumps({'prepared': True, 'engineeringTests': 366, 'trained': False}))
    else:
        target = RUNS/'verification_20261008_round38.json'
        if target.exists(): raise FileExistsError('Preserve verification seal')
        g.verified_files(EVIDENCE); assert read(EVIDENCE/'audit_state.json') == audit and read(EVIDENCE/'contextual_cases.json') == cases
        captures = json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig')); assert captures['status'] == 'completed' and len(captures['captures']) == 2
        for capture in captures['captures']:
            assert c.file_sha256(EVIDENCE/capture['image']) == capture['sha256'] and c.file_sha256(EVIDENCE/capture['sourcePage']) == capture['sourcePageSha256']
        c.write_json(target, {'passed': True, 'checkedAtUTC': datetime.now(UTC).isoformat(), 'engineeringTests': 366, 'audit': audit,
            'immutableSourceSha256': unchanged, 'previousVerificationSha256': c.file_sha256(RUNS/'verification_20261008_round37.json'),
            'evidenceManifestSha256': c.file_sha256(EVIDENCE/'manifest.json'), 'capturesSha256': c.file_sha256(EVIDENCE/'captures.json'), 'qualityPromotionPassed': False})
        print(json.dumps({'passed': True, 'engineeringTests': 366, 'trained': False, 'modelPromoted': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('prepare', 'seal')); main(parser.parse_args().action)
