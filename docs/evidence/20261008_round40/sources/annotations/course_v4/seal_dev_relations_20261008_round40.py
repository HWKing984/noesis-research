"""Recompute development revision and seal real artifact captures; no models are executed."""
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
from course_abstract_v1 import read
from course_abstract_relation import NER_FIELDS, revise, rows_for
from complete_dev_relations import CONTRACT, source_cohort
from export_course_evidence import page, table, highlight
import seal_relation_enrichment_20261008_round39 as previous_round

RUNS = ROOT/'kg_datasets/dblp/course_v4_runs'
DATA = ROOT/'kg_datasets/dblp/course_abstract_dev_relation_reviewed_20261008_40'
EVIDENCE = ROOT/'docs/evidence/20261008_round40'
DECISIONS = ROOT/'annotations/course_v4/abstract_dev_relation_decisions_20261008_40.json'
REVIEWS = ROOT/'annotations/course_v4/abstract_dev_relation_reviews_20261008_40.json'
TESTS = RUNS/'tests_20261008_round40.xml'


def checked():
    _, _, _, unchanged = previous_round.checked()
    prior_seal = read(RUNS/'verification_20261008_round39.json'); assert prior_seal['passed']
    g.verified_files(ROOT/'docs/evidence/20261008_round39', prior_seal['evidenceManifestSha256'])
    assert c.file_sha256(ROOT/'docs/evidence/20261008_round39/captures.json') == prior_seal['capturesSha256']
    for capture in json.loads((ROOT/'docs/evidence/20261008_round39/captures.json').read_text(encoding='utf-8-sig'))['captures']:
        assert c.file_sha256(ROOT/'docs/evidence/20261008_round39'/capture['image']) == capture['sha256']
    config, parent, refs, old = source_cohort(); manifest = g.verified_files(DATA)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    assert refs == c.read_jsonl(DATA/'references.jsonl') and read(DATA/'contract.json') == config
    receipts = c.read_jsonl(DATA/'reviewed_receipts.jsonl'); origins = c.read_jsonl(DATA/'origins.jsonl')
    initial = {r['reference']['arxivId']: r for r in c.read_jsonl(DATA/'generation_receipts.jsonl')}
    decisions = {d['arxivId']: d for d in read(DECISIONS)['documents']}
    judgments = {d['arxivId']: d for d in read(REVIEWS)['reviews']}
    assert read(REVIEWS)['independent'] is False and set(initial) == set(decisions) == set(judgments) == set(config['revisionCohort']) and len(initial) == 11
    assert len(refs) == len(old) == len(receipts) == len(origins) == 19
    cases = []
    for ref, before, after, origin in zip(refs, old, receipts, origins):
        rejudged = ref['arxivId'] in decisions
        assert not c.validate_receipt(after, ref) and all(before['annotation'][k] == after['annotation'][k] for k in NER_FIELDS)
        assert origin == {'sampleId': ref['sampleId'], 'upstreamReceiptSha256': before['contentSha256'], 'relationRejudged': rejudged, 'NERReannotated': False}
        if not rejudged: assert before == after; continue
        generated = initial[ref['arxivId']]; decision = decisions[ref['arxivId']]
        assert decision['textSha256'] == ref['textSha256'] and generated['annotation'] == revise(before['annotation'], ref, decision, parent)
        assert after['initialContentSha256'] == generated['contentSha256'] and after['review']['provenance']['sourceArtifactSha256'] == c.file_sha256(REVIEWS)
        assert after['annotation']['notes'].endswith('Self-review: '+judgments[ref['arxivId']]['reason'])
        cases.append({'arxivId': ref['arxivId'], 'source': ref, 'before': before['annotation'], 'after': after['annotation'],
            'unresolvedReason': decision['unresolvedReason'], 'legacyReviewConcern': decision.get('legacyReviewConcern'), 'reviewedReceiptSha256': after['contentSha256']})
    assert all(not c.eligible_tasks(r, r['reference'])['ner'] for r in initial.values())
    docs, pairs, full, excluded, unknown, total = rows_for(refs, receipts); previous = rows_for(refs, old)
    assert docs == c.read_jsonl(DATA/'ner_dev.jsonl') and pairs == c.read_jsonl(DATA/'relation_dev.jsonl') and full == c.read_jsonl(DATA/'full_relation_dev.jsonl') and excluded == c.read_jsonl(DATA/'excluded_ner.jsonl')
    assert excluded == previous[3] and len(docs) == 16 and len(excluded) == 3 and len(full) == 7 and len(previous[2]) == 5
    key = lambda p: (p['sampleId'], p['head']['entityId'], p['tail']['entityId'])
    prior_pairs = {key(p): p for p in previous[1]}; current = {key(p): p for p in pairs}
    assert len(prior_pairs) == 242 and len(current) == len(pairs) == 335 and set(prior_pairs) <= set(current)
    assert all(all(row[k] == current[pid][k] for k in ('head', 'tail', 'label', 'evidence', 'reason')) for pid, row in prior_pairs.items())
    added = [p for p in pairs if key(p) not in prior_pairs]
    assert added == c.read_jsonl(DATA/'additional_relation_dev.jsonl') and len(added) == 93 and Counter(p['label'] for p in added) == {'USED_FOR': 57, 'NO_RELATION': 36}
    assert len({p['sampleId'] for p in added}) == 6 and unknown == 97 and total == 432
    assert Counter(p['label'] for p in pairs) == {'USED_FOR': 259, 'NO_RELATION': 66, 'EVALUATED_ON': 10}
    full_ids = {d['sampleId'] for d in full}; full_pairs = [p for p in pairs if p['sampleId'] in full_ids]
    assert len(full_pairs) == 107 and Counter(p['label'] for p in full_pairs) == {'USED_FOR': 84, 'NO_RELATION': 23}
    assert sum(not any(p['sampleId'] == d['sampleId'] for p in full_pairs) for d in full) == 1
    parking = next(p for p in cases if p['arxivId'] == '2001.11639')
    assert next(p for p in parking['after']['relations'] if (p['head'], p['tail']) == ('e10', 'e3'))['label'] == 'UNRESOLVED'
    legacy = next(p for p in cases if p['arxivId'] == '1904.04163'); assert legacy['legacyReviewConcern']
    assert all(next(p for p in legacy['after']['relations'] if (p['head'], p['tail']) == pair)['label'] == 'EVALUATED_ON' for pair in [('e14', 'e16'), ('e15', 'e16')])
    alignment = c.read_jsonl(DATA/'token_alignment.jsonl'); assert [a['sampleId'] for a in alignment] == [d['sampleId'] for d in docs]
    for doc, entry in zip(docs, alignment):
        assert c.align_bio(entry['offsets'], doc['entities'], doc['text']) == entry['labels'] and entry['tokens'] == len(entry['offsets']) <= 512
        decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else label for o, label in zip(entry['offsets'], entry['labels'])], entry['offsets'], doc['text'])
        assert not decoded['invalidTransitions'] and decoded['entities'] == [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in doc['entities']]
    suite = ElementTree.parse(TESTS).getroot().find('testsuite'); assert suite.get('tests') == '368' and all(suite.get(k) == '0' for k in ('errors', 'failures', 'skipped'))
    summary = read(DATA/'summary.json')
    assert summary['knownPairs'] == 335 and summary['maxMarkedTokens'] == 306 and summary['knownPairCoverage'] == 335/432 and summary['fullDevDocumentCoverage'] == 7/19
    assert summary['completeDocumentEVALSupport'] == 0 and summary['developmentPreviouslyExposed'] and not any(summary[k] for k in ('trainingExecuted', 'inferenceExecuted', 'newMetricsProduced', 'testContentAccessed', 'modelPromoted', 'qualityPromotionPassed'))
    audit = {'passed': True, 'engineeringTests': 368, 'wholeDevCohort': 19, 'nerCandidates': 16, 'remainingNERQuarantines': 3, 'freshReviews': 11,
        'inheritedReceipts': 8, 'documentsWithAdditionalLabels': 6, 'previousKnownPairs': 242, 'knownPairs': 335, 'additionalKnownPairs': 93,
        'additionalSupport': dict(Counter(p['label'] for p in added)), 'eligiblePairs': 432, 'unresolvedPairs': 97, 'knownPairCoverage': 335/432,
        'completeRelationDevDocuments': 7, 'fullDevDocumentCoverage': 7/19, 'fullReferencePairs': 107, 'fullReferenceSupport': dict(Counter(p['label'] for p in full_pairs)),
        'completeDocumentEVALSupport': 0, 'zeroCandidateDocuments': 1, 'oldNERFieldsAndKnownPairLabelsUnchanged': True, 'sourceReferencesUnchanged': True,
        'backgroundBenchmarkPairStillUnresolved': True, 'historicalComponentEvaluationRiskRetainedAndFlagged': True, 'legacyRetractionsExecuted': False,
        'strictBIORoundTripDocuments': 16, 'knownPairMarkedEncodingPreflightPassed': True, 'maxMarkedTokens': 306,
        'historicalDevSnapshotsUnchanged': True, 'newVersionContainsDevLabelRevisions': True, 'developmentPreviouslyExposed': True,
        'train39Unchanged': True, 'reservedTestContentConsumed': False, 'modelTrainingExecuted': False, 'inferenceExecuted': False,
        'newMetricsProduced': False, 'modelPromoted': False, 'qualityPromotionPassed': False, 'databaseWritten': False, 'serviceRestarted': False,
        'liveApplicationReaccepted': False, 'reportExpansionPaused': True, 'dataManifestSha256': c.file_sha256(DATA/'manifest.json'),
        'labelIndependence': 'same_session_AI_reference_not_human_gold', 'notice': 'Label coverage, not new model accuracy; incomplete benchmarks and legacy attribution concerns still block reliability claims.'}
    return audit, summary, cases, unchanged


def main(action):
    audit, summary, cases, unchanged = checked()
    if action == 'prepare':
        if EVIDENCE.exists(): raise FileExistsError('Preserve evidence')
        EVIDENCE.mkdir(parents=True)
        paths = [Path(__file__), CONTRACT, DECISIONS, REVIEWS, ROOT/'scripts/complete_dev_relations.py', ROOT/'tests/test_dev_relation_revision.py', ROOT/'README.md', ROOT/'docs/system_status_round40.md', TESTS] + [p for p in DATA.iterdir() if p.is_file()]
        for source in paths:
            target = EVIDENCE/'sources'/source.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        c.write_json(EVIDENCE/'audit_state.json', audit); c.write_json(EVIDENCE/'relation_cases.json', cases)
        body = '<h2>固定19篇dev · 全部11篇不完整关系文档源文复核</h2>'+table(['项目', '实际结果', '不能推出'], [
            ['明确关系对', '242 → 335；新增57用途 / 36局部角色反例', '93跨度对来自6论文，不是93独立实验'],
            ['实体对覆盖', f'335 / 432 = {335/432:.2%}；97未决', '未决不作为NO_RELATION'],
            ['完整文档覆盖', f'5 → 7 / 19 = {7/19:.2%}；含1篇零候选', '不是77.55%的完整文档覆盖'],
            ['完整文档参考', '107对：USED_FOR84 / NO_RELATION23', 'EVALUATED_ON正例仍0，不能验证benchmark能力'],
            ['全部明确对支持', 'USED_FOR259 / EVALUATED_ON10 / NO_RELATION66', '部分模块的10个评测正例不能移到完整pipeline'],
            ['旧标签与NER', '原242标签/证据/理由、16篇NER/3隔离均不改', '覆盖增加不等于模型提高或独立gold']])
        body += '<h2>保留未知和历史风险，不用补负例凑完整</h2>'+table(['源文', '处理', '边界'], [
            ['ParkingSticker', 'YOLOv2 — PASCAL VOC保持UNRESOLVED', '背景比较＋未报告测量不证明负例'],
            ['sMoRe', '18个用途/局部角色判断，11对仍未决', '创建/放置/管理复合任务不强拆'],
            ['TaDaa / CBFL / SDG review', '检查后保留未知', '下游期望、背景任务、家族讨论不自动成为事实'],
            ['语言模型压缩', '旧组合评测向组件归属风险单列，未撤回', '原标签保持不等于组件独立测量已认证']])
        body += '<h2>编码、回归与未晋级状态</h2><p>16篇严格BIO往返；335个明确对实体标记编码通过，最大306 tokens，无截断。368项正式工程回归通过，不是语义正确性认证。11篇实际初判/自复核，其中仅6篇新增关系，其余5篇检查后仍保留未决。</p><p>本轮没有训练、模型推理、新Precision/Recall/F1、test内容读取、写库或重启。开发集此前已用于选择，不是新盲测。39轮train268关系/50篇NER、旧权重/成绩/31图哈希复检，qualityPromotionPassed=false。</p><p>按MLE先补证据和覆盖；下一步显式复核/撤回组合方法与组件归属，统一直接角色后锁定新训练对照。模型可靠性、独立参考和稀有评测支持仍未解决。</p>'
        (EVIDENCE/'09_annotation_expansion.html').write_text(page('开发关系覆盖与未决边界 · 第40轮', body, datetime.now(UTC).isoformat(), ['audit_state.json', 'sources/kg_datasets/dblp/course_abstract_dev_relation_reviewed_20261008_40/summary.json']), encoding='utf-8')
        case = next(p for p in cases if p['arxivId'] == '2001.11639')
        body = '<p>完整dev源文与冻结实体，非模型预测。颜色标METHOD/TASK/DATASET，不表示关系已核实：</p><div style="line-height:1.8">'+highlight(case['source']['text'], case['after']['entities'])+'</div>'
        body += table(['候选关系/状态', '源文证据与限制'], [['YOLOv2 → ParkingSticker（四个重复数据提及）', '原EVALUATED_ON不改；重复跨度不等于四次独立实验'], ['YOLOv2 → PASCAL VOC', 'UNRESOLVED：只作为背景比较，未明确排除评测'], ['完整关系文档准入', '该论文仍不准入，不能用一个假负例凑完整'], ['另一论文：distillation / regularization → Penn Treebank', '旧组合结果归属组件的风险另记；未静默改标签或认证独立测量']])
        body += '<p>97个未决对保留源文与理由，不训练成负例。完整文档虽增加到7/19，其EVALUATED_ON参考仍0；本轮没有模型成绩或可靠性晋级。AI初判与本会话自复核不是独立人工金标准。</p>'
        (EVIDENCE/'04_traceability.html').write_text(page('背景benchmark为什么不能补成负例 · 第40轮', body, datetime.now(UTC).isoformat(), ['relation_cases.json', 'sources/annotations/course_v4/abstract_dev_relation_reviews_20261008_40.json']), encoding='utf-8')
        c.write_json(EVIDENCE/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'filesSha256': {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})
        print(json.dumps({'prepared': True, 'engineeringTests': 368, 'trained': False}))
    else:
        target = RUNS/'verification_20261008_round40.json'
        if target.exists(): raise FileExistsError('Preserve verification seal')
        g.verified_files(EVIDENCE); assert read(EVIDENCE/'audit_state.json') == audit and read(EVIDENCE/'relation_cases.json') == cases
        captures = json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig')); assert captures['status'] == 'completed' and len(captures['captures']) == 2
        for capture in captures['captures']:
            assert c.file_sha256(EVIDENCE/capture['image']) == capture['sha256'] and c.file_sha256(EVIDENCE/capture['sourcePage']) == capture['sourcePageSha256']
        c.write_json(target, {'passed': True, 'checkedAtUTC': datetime.now(UTC).isoformat(), 'engineeringTests': 368, 'audit': audit, 'immutableSourceSha256': unchanged,
            'previousVerificationSha256': c.file_sha256(RUNS/'verification_20261008_round39.json'), 'evidenceManifestSha256': c.file_sha256(EVIDENCE/'manifest.json'), 'capturesSha256': c.file_sha256(EVIDENCE/'captures.json'), 'qualityPromotionPassed': False})
        print(json.dumps({'passed': True, 'engineeringTests': 368, 'trained': False, 'modelPromoted': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('prepare', 'seal')); main(parser.parse_args().action)
