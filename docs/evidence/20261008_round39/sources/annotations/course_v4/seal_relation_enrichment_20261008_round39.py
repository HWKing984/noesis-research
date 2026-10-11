"""Recompute enriched labels and preserve source/model evidence; no training or dev predictions."""
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
from enrich_abstract_relations import CONTRACT, source_cohort
from export_course_evidence import page, table, highlight
import seal_contextual_abstracts_20261008_round38 as previous_round

RUNS = ROOT/'kg_datasets/dblp/course_v4_runs'
DATA = ROOT/'kg_datasets/dblp/course_abstract_relation_enriched_20261008_39'
EVIDENCE = ROOT/'docs/evidence/20261008_round39'
DECISIONS = ROOT/'annotations/course_v4/abstract_relation_enrichment_decisions_20261008_39.json'
REVIEWS = ROOT/'annotations/course_v4/abstract_relation_enrichment_reviews_20261008_39.json'
TRIAGE = ROOT/'annotations/course_v4/abstract_quarantine_triage_20261008_39.json'
TESTS = RUNS/'tests_20261008_round39.xml'


def checked():
    _, _, _, unchanged = previous_round.checked()
    prior_seal = read(RUNS/'verification_20261008_round38.json'); assert prior_seal['passed']
    g.verified_files(ROOT/'docs/evidence/20261008_round38', prior_seal['evidenceManifestSha256'])
    assert c.file_sha256(ROOT/'docs/evidence/20261008_round38/captures.json') == prior_seal['capturesSha256']
    config, parent, refs, old = source_cohort(); manifest = g.verified_files(DATA)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    receipts = c.read_jsonl(DATA/'reviewed_receipts.jsonl'); origins = c.read_jsonl(DATA/'origins.jsonl')
    assert refs == c.read_jsonl(DATA/'references.jsonl') and len(receipts) == len(origins) == len(refs) == 58
    initial = {r['reference']['arxivId']: r for r in c.read_jsonl(DATA/'generation_receipts.jsonl')}
    decisions = {d['arxivId']: d for d in read(DECISIONS)['documents']}; cases = []
    assert set(initial) == set(decisions) == set(config['revisionCohort'])
    for ref, before, after, origin in zip(refs, old, receipts, origins):
        rejudged = ref['arxivId'] in decisions
        assert not c.validate_receipt(after, ref) and all(before['annotation'][k] == after['annotation'][k] for k in NER_FIELDS)
        assert origin == {'sampleId': ref['sampleId'], 'upstreamReceiptSha256': before['contentSha256'], 'relationRejudged': rejudged, 'NERReannotated': False}
        if not rejudged: assert before == after; continue
        generated = initial[ref['arxivId']]
        assert generated['annotation'] == revise(before['annotation'], ref, decisions[ref['arxivId']], parent)
        assert after['initialContentSha256'] == generated['contentSha256'] and after['review']['provenance']['sourceArtifactSha256'] == c.file_sha256(REVIEWS)
        cases.append({'arxivId': ref['arxivId'], 'source': ref, 'before': before['annotation'], 'after': after['annotation'],
            'upstreamReceiptSha256': before['contentSha256'], 'reviewedReceiptSha256': after['contentSha256']})
    assert all(not c.eligible_tasks(r, r['reference'])['ner'] for r in initial.values())
    docs, pairs, full, excluded, unknown, total = rows_for(refs, receipts); previous = rows_for(refs, old)
    assert docs == c.read_jsonl(DATA/'ner_train.jsonl') and pairs == c.read_jsonl(DATA/'relation_train.jsonl') and full == c.read_jsonl(DATA/'full_relation_train.jsonl') and excluded == c.read_jsonl(DATA/'excluded_ner.jsonl')
    assert excluded == previous[3] and len(docs) == 50 and len(excluded) == 8 and len(full) == len(previous[2]) == 6
    key = lambda p: (p['sampleId'], p['head']['entityId'], p['tail']['entityId'])
    old_pairs = {key(p): p for p in previous[1]}; known = {key(p): p for p in pairs}
    assert len(known) == len(pairs) == 268 and len(old_pairs) == 201 and set(old_pairs) <= set(known)
    assert all(all(p[k] == known[pid][k] for k in ('head', 'tail', 'label', 'evidence', 'reason')) for pid, p in old_pairs.items())
    added = [p for p in pairs if key(p) not in old_pairs]; assert added == c.read_jsonl(DATA/'additional_relation_train.jsonl')
    assert len(added) == 67 and Counter(p['label'] for p in added) == {'USED_FOR': 32, 'EVALUATED_ON': 16, 'NO_RELATION': 19}
    assert unknown == 1577 and total == 1845 and all(p['label'] != 'UNRESOLVED' for p in pairs)
    alignment = c.read_jsonl(DATA/'token_alignment.jsonl'); assert [a['sampleId'] for a in alignment] == [d['sampleId'] for d in docs]
    for doc, entry in zip(docs, alignment):
        assert c.align_bio(entry['offsets'], doc['entities'], doc['text']) == entry['labels'] and entry['tokens'] == len(entry['offsets']) <= 512
        decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else label for o, label in zip(entry['offsets'], entry['labels'])], entry['offsets'], doc['text'])
        assert not decoded['invalidTransitions'] and decoded['entities'] == [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in doc['entities']]
    eval_added = [p for p in added if p['label'] == 'EVALUATED_ON']
    distinct = {(p['sampleId'], p['head']['text'].casefold(), p['tail']['text'].casefold()) for p in eval_added}
    assert len(distinct) == 7 and len({p['sampleId'] for p in eval_added}) == 3
    scan = next(p for p in cases if p['arxivId'] == '2503.01309')['after']; entities = {e['entityId']: e for e in scan['entities']}
    assert all(p['label'] == 'UNRESOLVED' for p in scan['relations'] if entities[p['tail']]['label'] == 'DATASET')
    triage = read(TRIAGE); ids = {r['sampleId']: r['arxivId'] for r in refs}
    assert triage['kind'] == 'whole_source_inspection_not_annotation_revision' and {p['arxivId'] for p in triage['documents']} == {ids[e['sampleId']] for e in excluded}
    assert len(triage['documents']) == 8 and all(p['action'] == 'retain_quarantine' for p in triage['documents'])
    suite = ElementTree.parse(TESTS).getroot().find('testsuite'); assert suite.get('tests') == '367' and all(suite.get(k) == '0' for k in ('errors', 'failures', 'skipped'))
    summary = read(DATA/'summary.json'); assert summary['knownPairs'] == 268 and summary['maxMarkedTokens'] == 333 and summary['knownPairCoverage'] == 268/1845
    assert summary['relationSupport'] == dict(Counter(p['label'] for p in pairs)) and not summary['trainingExecuted'] and not summary['qualityPromotionPassed']
    audit = {'passed': True, 'engineeringTests': 367, 'wholeTrainCohort': 58, 'nerCandidates': 50, 'remainingNERQuarantines': 8,
        'freshRelationReviews': 4, 'inheritedReceipts': 54, 'previousKnownPairs': 201, 'knownPairs': 268, 'additionalKnownPairs': 67,
        'additionalSupport': dict(Counter(p['label'] for p in added)), 'unresolvedPairs': 1577, 'eligiblePairs': 1845, 'knownPairCoverage': 268/1845,
        'additionalEVALSpanPairs': 16, 'distinctSourceMethodBenchmarkTextPairs': 7, 'additionalEVALSourcePapers': 3,
        'NOReferencePapers': len({p['sampleId'] for p in pairs if p['label'] == 'NO_RELATION'}), 'completeRelationTrainDocuments': 6,
        'oldNERFieldsAndKnownPairLabelsUnchanged': True, 'sourceReferencesUnchanged': True, 'strictBIORoundTripDocuments': 50,
        'allKnownPairsMarkedEncodingPassed': True, 'maxMarkedTokens': 333, 'ambiguousComponentEvaluationsStillUnresolved': True,
        'quarantineInspectionIsNotRelabeling': True, 'devLabelsAndSourceUnchanged': True, 'reservedTestContentConsumed': False,
        'modelTrainingExecuted': False, 'inferenceExecuted': False, 'newMetricsProduced': False, 'modelPromoted': False, 'qualityPromotionPassed': False,
        'databaseWritten': False, 'serviceRestarted': False, 'liveApplicationReaccepted': False, 'reportExpansionPaused': True,
        'dataManifestSha256': c.file_sha256(DATA/'manifest.json'), 'labelIndependence': 'same_session_AI_reference_not_human_gold',
        'notice': 'Partial training-label enrichment; correlated mention pairs are not independent evaluations. Complete dev coverage/rare support and global semantic correctness are not established.'}
    return audit, summary, cases, unchanged


def main(action):
    audit, summary, cases, unchanged = checked()
    if action == 'prepare':
        if EVIDENCE.exists(): raise FileExistsError('Preserve evidence')
        EVIDENCE.mkdir(parents=True)
        paths = [Path(__file__), CONTRACT, DECISIONS, REVIEWS, TRIAGE, ROOT/'scripts/enrich_abstract_relations.py', ROOT/'tests/test_relation_enrichment.py',
            ROOT/'README.md', ROOT/'docs/system_status_round39.md', TESTS] + [p for p in DATA.iterdir() if p.is_file()]
        for source in paths:
            target = EVIDENCE/'sources'/source.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        c.write_json(EVIDENCE/'audit_state.json', audit); c.write_json(EVIDENCE/'relation_cases.json', cases)
        body = '<h2>四篇已锁定train摘要 · 实体不改、关系有证据才判</h2>'+table(['项目', '实际结果', '限制'], [
            ['明确训练关系对', '201 → 268；新增67', '32 USED_FOR / 16 EVALUATED_ON / 19 NO_RELATION'],
            ['累计关系标签', 'USED_FOR183 / EVALUATED_ON59 / NO_RELATION26', '同会话AI参考，不是独立gold'],
            ['已判断覆盖', f'{268/1845:.2%}，原为{201/1845:.2%}', '1577/1845对仍未决，不训练成负例'],
            ['新增评测证据', '16跨度对 / 7源文方法–benchmark名称组合 / 3论文', '重复名称相关；不是16次独立实验'],
            ['实体与原结果', '50篇NER不改，8隔离保留；旧201明确对不改', '其余54篇收据原样继承；未运行模型']])
        body += '<h2>整套方法被评测，不等于每个组件被独立评测</h2>'+table(['来源', '新明确关系', '仍不确定的内容'], [
            ['3D segmentation：2503.01309', 'voxel hashing用于scene querying；filtering用于3D merging', 'ScanNet/SceneNN只明确评测our approach；组件benchmark边全部未决'],
            ['RLQP：2107.10847', '参数调优用途、三benchmark泛化评测、solver接受调优的角色对照', '泛指RL/QP solver的其他benchmark归属不填'],
            ['CriticGPT：2402.14245', 'critic理解轨迹；reward model对应Meta-World', '不把critic、reward modeling和reward model全局合并'],
            ['SmoothGuard：2510.26830', '防御框架评测与过滤用途；生成/防御/接收者角色对照', '不把noise/clustering组件自动说成各自被评测']])
        body += '<h2>回归与尚未完成的门槛</h2><p>367项正式回归通过；50篇严格BIO往返，268个已判对的实体标记编码通过，最大333 tokens，不截断。八篇隔离已逐篇检查并另存排查原因，检查不冒充标签修订或准入。</p><p>完整RE train仍6/58；dev仍5/19完整、主pipeline EVALUATED_ON参考0。新增标注没有产生新F1，没有重训、推理、改旧dev/test、写库、重启或新线上验收。旧权重/成绩/图包哈希核验，qualityPromotionPassed=false。</p><p>MLE工作流先补稀有监督与明确反例；下一步补完整dev证据/任务跨度一致性，锁定下一次实验后训练对照。模型可靠性、独立核验与长尾概念/作者身份仍未全部解决。</p>'
        (EVIDENCE/'09_annotation_expansion.html').write_text(page('关系证据补强与未晋级边界 · 第39轮', body, datetime.now(UTC).isoformat(), ['audit_state.json', 'relation_cases.json', 'sources/kg_datasets/dblp/course_abstract_relation_enriched_20261008_39/summary.json']), encoding='utf-8')
        case = next(p for p in cases if p['arxivId'] == '2503.01309')
        body = '<p>完整训练源文与冻结实体，非模型预测。颜色仅标METHOD/TASK/DATASET，不表示已核实关系：</p><div style="line-height:1.8">'+highlight(case['source']['text'], case['after']['entities'])+'</div>'
        body += table(['源文归属', '本轮判断'], [['voxel hashing → 3D scene querying', 'USED_FOR：原文明确操作与目的'], ['similarity-based filtering → 3D merging', 'USED_FOR：原文through直接归属'], ['VFMs → 上述3D查询/合并步骤', '局部NO_RELATION：产生输入mask与执行后续步骤的角色对照'], ['各组件 → ScanNet/SceneNN', '全部UNRESOLVED：our approach被评测，独立组件归属未明'], ["CriticGPT's reward model → Meta-World（另一论文）", '只给reward model明确评测标签，不给所有CriticGPT/LLM类边']])
        body += '<p>NO_RELATION只表示固定文档操作范围内的角色判断，不是方法永远不能用于该任务。类型、共现或未报告测量不构成负例。详见逐条原文证据/理由和自复核收据。</p>'
        (EVIDENCE/'04_traceability.html').write_text(page('评测归属与反例证据 · 第39轮', body, datetime.now(UTC).isoformat(), ['relation_cases.json', 'sources/annotations/course_v4/abstract_relation_enrichment_reviews_20261008_39.json']), encoding='utf-8')
        c.write_json(EVIDENCE/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'filesSha256': {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})
        print(json.dumps({'prepared': True, 'engineeringTests': 367, 'trained': False}))
    else:
        target = RUNS/'verification_20261008_round39.json'
        if target.exists(): raise FileExistsError('Preserve verification seal')
        g.verified_files(EVIDENCE); assert read(EVIDENCE/'audit_state.json') == audit and read(EVIDENCE/'relation_cases.json') == cases
        captures = json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig')); assert captures['status'] == 'completed' and len(captures['captures']) == 2
        for capture in captures['captures']:
            assert c.file_sha256(EVIDENCE/capture['image']) == capture['sha256'] and c.file_sha256(EVIDENCE/capture['sourcePage']) == capture['sourcePageSha256']
        c.write_json(target, {'passed': True, 'checkedAtUTC': datetime.now(UTC).isoformat(), 'engineeringTests': 367, 'audit': audit, 'immutableSourceSha256': unchanged,
            'previousVerificationSha256': c.file_sha256(RUNS/'verification_20261008_round38.json'), 'evidenceManifestSha256': c.file_sha256(EVIDENCE/'manifest.json'),
            'capturesSha256': c.file_sha256(EVIDENCE/'captures.json'), 'qualityPromotionPassed': False})
        print(json.dumps({'passed': True, 'engineeringTests': 367, 'trained': False, 'modelPromoted': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('prepare', 'seal')); main(parser.parse_args().action)
