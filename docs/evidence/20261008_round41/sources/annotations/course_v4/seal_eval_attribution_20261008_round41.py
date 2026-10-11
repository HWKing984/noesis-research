"""Recompute attribution revisions and seal real artifact captures; no model execution."""
import argparse
import copy
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
from course_abstract_relation import NER_FIELDS, rows_for
from review_eval_attribution import CONTRACT, source_cohorts, revise_attribution
from export_course_evidence import page, table, highlight
import seal_dev_relations_20261008_round40 as previous_round

RUNS = ROOT/'kg_datasets/dblp/course_v4_runs'
DATA = ROOT/'kg_datasets/dblp/course_abstract_eval_attribution_reviewed_20261008_41'
EVIDENCE = ROOT/'docs/evidence/20261008_round41'
DECISIONS = ROOT/'annotations/course_v4/abstract_eval_attribution_decisions_20261008_41.json'
REVIEWS = ROOT/'annotations/course_v4/abstract_eval_attribution_reviews_20261008_41.json'
TESTS = RUNS/'tests_20261008_round41.xml'


def checked():
    _, _, _, unchanged = previous_round.checked()
    prior_seal = read(RUNS/'verification_20261008_round40.json'); assert prior_seal['passed']
    previous_evidence = ROOT/'docs/evidence/20261008_round40'
    g.verified_files(previous_evidence, prior_seal['evidenceManifestSha256'])
    assert c.file_sha256(previous_evidence/'captures.json') == prior_seal['capturesSha256']
    for capture in json.loads((previous_evidence/'captures.json').read_text(encoding='utf-8-sig'))['captures']:
        assert c.file_sha256(previous_evidence/capture['image']) == capture['sha256']
    config, sources = source_cohorts(); manifest = g.verified_files(DATA)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items()) and read(DATA/'contract.json') == config
    decisions = {(d['split'], d['arxivId']): d for d in read(DECISIONS)['documents']}
    reviews = {(d['split'], d['arxivId']): d for d in read(REVIEWS)['reviews']}
    assert len(decisions) == len(reviews) == 15 and set(decisions) == set(reviews) and read(REVIEWS)['independent'] is False
    inspections = []; cases = []; fresh = 0; inherited = 0; alignment_count = 0
    for split, (refs, old) in sources.items():
        receipts = c.read_jsonl(DATA/(split+'_reviewed_receipts.jsonl')); origins = c.read_jsonl(DATA/(split+'_origins.jsonl'))
        generated = {r['reference']['arxivId']: r for r in c.read_jsonl(DATA/(split+'_generation_receipts.jsonl'))}
        assert refs == c.read_jsonl(DATA/(split+'_references.jsonl')) and len(refs) == len(old) == len(receipts) == len(origins)
        assert set(generated) == ({'2107.03374'} if split == 'train' else {'1904.04163'})
        old_lines = (ROOT/config['sources'][split]['path']/'reviewed_receipts.jsonl').read_bytes().splitlines(keepends=True)
        new_lines = (DATA/(split+'_reviewed_receipts.jsonl')).read_bytes().splitlines(keepends=True)
        for i, (ref, before, after, origin) in enumerate(zip(refs, old, receipts, origins)):
            identity = (split, ref['arxivId']); selected = identity in decisions; changed = ref['arxivId'] in generated
            assert not c.validate_receipt(after, ref) and all(before['annotation'][k] == after['annotation'][k] for k in NER_FIELDS)
            assert origin == {'sampleId': ref['sampleId'], 'upstreamReceiptSha256': before['contentSha256'], 'attributionInspected': selected, 'relationRejudged': changed, 'NERReannotated': False}
            if selected:
                revised, inspected = revise_attribution(before, ref, decisions[identity]); inspections.extend(inspected)
                assert revised['relations'] == after['annotation']['relations']
            if changed:
                fresh += 1; initial = generated[ref['arxivId']]
                assert initial['annotation'] == revised and not c.validate_receipt(initial, ref) and not c.eligible_tasks(initial, ref)['ner']
                assert after['initialContentSha256'] == initial['contentSha256'] and after['review']['inputContentSha256'] == initial['contentSha256']
                assert initial['generation']['sourceArtifactSha256'] == c.file_sha256(DECISIONS) and after['review']['provenance']['sourceArtifactSha256'] == c.file_sha256(REVIEWS)
                expected = copy.deepcopy(revised); expected['reviewOfSha256'] = initial['contentSha256']; expected['notes'] += ' Self-review: '+reviews[identity]['reason']
                assert after['annotation'] == expected
                cases.append({'split': split, 'arxivId': ref['arxivId'], 'source': ref, 'before': before['annotation'], 'after': after['annotation']})
            else:
                inherited += 1; assert before == after and old_lines[i] == new_lines[i]
            prior_pairs = {(p['head'], p['tail']): p for p in before['annotation']['relations']}
            current = {(p['head'], p['tail']): p for p in after['annotation']['relations']}
            assert set(prior_pairs) == set(current)
            assert all(p == current[key] for key, p in prior_pairs.items() if p['label'] != 'EVALUATED_ON')
        rows = rows_for(refs, receipts); previous = rows_for(refs, old)
        for name, expected in zip(('ner', 'relation', 'full_relation', 'excluded_ner'), rows[:4]):
            assert expected == c.read_jsonl(DATA/(name+'_'+split+'.jsonl'))
        assert rows[3] == previous[3] and len(rows[0]) == (50 if split == 'train' else 16) and len(rows[2]) == len(previous[2]) == (6 if split == 'train' else 7)
        assert len(rows[1]) == (267 if split == 'train' else 333) and rows[4:] == ((1578, 1845) if split == 'train' else (99, 432))
        assert Counter(p['label'] for p in rows[1]) == ({'USED_FOR': 183, 'EVALUATED_ON': 58, 'NO_RELATION': 26} if split == 'train' else {'USED_FOR': 259, 'EVALUATED_ON': 8, 'NO_RELATION': 66})
        if split == 'dev':
            full_ids = {d['sampleId'] for d in rows[2]}; full_pairs = [p for p in rows[1] if p['sampleId'] in full_ids]
            assert len(full_pairs) == 107 and Counter(p['label'] for p in full_pairs) == {'USED_FOR': 84, 'NO_RELATION': 23}
        alignment = c.read_jsonl(DATA/('token_alignment_'+split+'.jsonl')); assert [a['sampleId'] for a in alignment] == [d['sampleId'] for d in rows[0]]
        for doc, entry in zip(rows[0], alignment):
            assert c.align_bio(entry['offsets'], doc['entities'], doc['text']) == entry['labels'] and entry['tokens'] == len(entry['offsets']) <= 512
            decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else label for o, label in zip(entry['offsets'], entry['labels'])], entry['offsets'], doc['text'])
            assert not decoded['invalidTransitions'] and decoded['entities'] == [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in doc['entities']]
            alignment_count += 1
    assert fresh == 2 and inherited == 75 and alignment_count == 66 and len(inspections) == 69
    assert inspections == c.read_jsonl(DATA/'attribution_inspections.jsonl') and Counter(p['action'] for p in inspections) == {'keep': 65, 'retract': 3, 'repair_evidence': 1}
    actions = [p for p in inspections if p['action'] != 'keep']; assert actions == c.read_jsonl(DATA/'quality_actions.jsonl')
    for action in actions:
        assert action['beforeSha256'] == c.canonical_sha256(action['before']) and action['afterSha256'] == c.canonical_sha256(action['after'])
    summary = read(DATA/'summary.json')
    assert not any(summary[k] for k in ('trainingExecuted', 'inferenceExecuted', 'newMetricsProduced', 'testContentAccessed', 'modelPromoted', 'qualityPromotionPassed')) and summary['developmentPreviouslyExposed']
    assert summary['splits']['train']['maxMarkedTokens'] == 333 and summary['splits']['dev']['maxMarkedTokens'] == 306
    suite = ElementTree.parse(TESTS).getroot().find('testsuite'); assert suite.get('tests') == '369' and all(suite.get(k) == '0' for k in ('errors', 'failures', 'skipped'))
    audit = {'passed': True, 'engineeringTests': 369, 'inspectedWholeDocuments': 15, 'inspectedEVALSpanPairs': 69, 'keptEVALPairs': 65, 'retractions': 3, 'evidenceOnlyRepairs': 1,
        'freshGenerationAndReviewDocuments': 2, 'inheritedByteIdenticalReceipts': 75, 'NERFieldsAndCandidateInventoryUnchanged': True, 'previousUnknownAndNonEVALPairsExact': True,
        'qualityActionsPreserveOldAndNewPairs': True, 'strictBIORoundTripDocuments': 66, 'knownPairMarkedEncodingPreflightPassed': True, 'knownMarkedPairs': 600,
        'splits': summary['splits'], 'historicalTrain39AndDev40SnapshotsUnchanged': True, 'newVersionContainsTrainAndDevLabelRevisions': True,
        'developmentPreviouslyExposed': True, 'independentHumanGold': False, 'reservedTestContentConsumed': False, 'modelTrainingExecuted': False, 'inferenceExecuted': False,
        'newMetricsProduced': False, 'modelPromoted': False, 'qualityPromotionPassed': False, 'databaseWritten': False, 'serviceRestarted': False, 'liveApplicationReaccepted': False,
        'reportExpansionPaused': True, 'dataManifestSha256': c.file_sha256(DATA/'manifest.json'), 'labelIndependence': 'source_only_same_session_AI_review_not_independent_gold',
        'notice': 'Evaluation attribution does not require independent ablation; required configuration/version must not be lost. Label QC, not new model accuracy.'}
    return audit, summary, cases, unchanged


def main(action):
    audit, summary, cases, unchanged = checked()
    if action == 'prepare':
        if EVIDENCE.exists(): raise FileExistsError('Preserve evidence')
        EVIDENCE.mkdir(parents=True)
        paths = [Path(__file__), CONTRACT, DECISIONS, REVIEWS, ROOT/'scripts/review_eval_attribution.py', ROOT/'tests/test_eval_attribution_revision.py', ROOT/'README.md', ROOT/'docs/system_status_round41.md', TESTS] + [p for p in DATA.iterdir() if p.is_file()]
        for source in paths:
            target = EVIDENCE/'sources'/source.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        c.write_json(EVIDENCE/'audit_state.json', audit); c.write_json(EVIDENCE/'attribution_cases.json', cases)
        body = '<h2>15篇完整源文 · 69个既有评测跨度对</h2>'+table(['检查/动作', '实际结果', '含义'], [
            ['保持 / 撤回 / 补摘录', '65 / 3 / 1', '未增加正例或负例；旧对与新对完整留存'],
            ['新版train明确 / 未决', '268 → 267 / 1578，共1845候选', 'EVALUATED_ON58 / USED_FOR183 / NO_RELATION26'],
            ['新版dev明确 / 未决', f'335 → 333 / 99，共432候选；覆盖{333/432:.2%}', 'EVALUATED_ON8 / USED_FOR259 / NO_RELATION66'],
            ['完整dev关系参考', '7 / 19文档；107对：84用途、23负例', '完整EVALUATED_ON仍0，不能验证评测能力'],
            ['NER与收据', 'NER50train / 16dev不改，8 / 3隔离不改', '2篇新初判+实际自复核；75篇原收据字节保持']])
        body += '<h2>评测配置不能丢失；不要求独立消融</h2>'+table(['源文与风险', '显式操作', '不应误读'], [
            ['Codex生产版本 → HumanEval', '退回UNRESOLVED，版本与研究模型测量归属不唯一', '不声称该版本永远不能用于此数据集'],
            ['distillation / trust regularization → Penn Treebank', '两组件各自边退回UNRESOLVED，组合结果原证据保留', '不是因为缺少独立消融就一概撤回'],
            ['repeated sampling → HumanEval', '保留EVALUATED_ON和理由；证据[202,454) → [202,640)', '摘录补到实际测量句，不产生本项目新分数'],
            ['实测model / baseline / protocol', '来源能唯一归属到被测配置则保持', '低性能仍是评测正例；缺证据不是负例']])
        body += '<h2>检查通过，不等于模型可靠性通过</h2><p>66篇严格BIO往返、600个明确关系对标记编码通过，最大333 / 306 tokens，无截断。369项正式工程回归通过（114.87秒），不是369项独立语义认证。所有引用原文、旧/新对、理由和SHA均可复查。</p><p>本轮没有训练、模型推理、新Precision/Recall/F1、test语义读取、写库、重启或新线上验收。历史39/40包、35/36/37成绩与权重、31图保持。AI初判、同会话自复核和并行AI检查不是独立人工金标准。</p><p>qualityPromotionPassed=false。下一步锁定修订快照的新训练对照；稀有评测支持与完整文档覆盖仍不足，不改旧成绩分母，不用未决补负例。完整课程报告暂停。</p>'
        (EVIDENCE/'09_annotation_expansion.html').write_text(page('评测归属修订与边界 · 第41轮', body, datetime.now(UTC).isoformat(), ['audit_state.json', 'sources/kg_datasets/dblp/course_abstract_eval_attribution_reviewed_20261008_41/quality_actions.jsonl']), encoding='utf-8')
        case = next(p for p in cases if p['arxivId'] == '2107.03374')
        body = '<p>完整训练摘要与冻结实体，非模型预测；METHOD / TASK / DATASET高亮不表示事实已被独立核实。</p><div style="line-height:1.8">'+highlight(case['source']['text'], case['after']['entities'])+'</div>'
        body += table(['源文角色', '旧标签 / 证据', '新版本判断'], [
            ['e4: distinct production version of Codex', 'EVALUATED_ON → e5 HumanEval', 'UNRESOLVED：后文研究模型测量不能无条件归属生产版本'],
            ['e9: repeated sampling → e5 HumanEval', 'EVALUATED_ON；摘录结束在repeated sampling', '标签/理由不改；补到Using this method后的测量句'],
            ['另一论文：distillation + trust regularization', '两组件各自EVALUATED_ON → Penn Treebank', '分别退回未知，组合结果与旧证据保留ledger']])
        body += '<p>本页原文中的测量数值是来源论文的报告，不是本项目新成绩。评测边不要求独立消融，但必须保留必要版本/组合的归属。旧标签、旧证据、新未决原因与摘录扩展均在quality_actions.jsonl保存；没有改NO_RELATION或既有未决。</p><p>15篇源文检查≠15份新收据，只有发生变更的2篇建立新初判→实际自复核。旧版本与模型不覆盖，AI标签不是独立gold，完整dev评测支持仍为0。</p>'
        (EVIDENCE/'04_traceability.html').write_text(page('模型版本归属与截短证据 · 第41轮', body, datetime.now(UTC).isoformat(), ['attribution_cases.json', 'sources/annotations/course_v4/abstract_eval_attribution_reviews_20261008_41.json']), encoding='utf-8')
        c.write_json(EVIDENCE/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'filesSha256': {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})
        print(json.dumps({'prepared': True, 'engineeringTests': 369, 'trained': False}))
    else:
        target = RUNS/'verification_20261008_round41.json'
        if target.exists(): raise FileExistsError('Preserve verification seal')
        g.verified_files(EVIDENCE); assert read(EVIDENCE/'audit_state.json') == audit and read(EVIDENCE/'attribution_cases.json') == cases
        captures = json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig')); assert captures['status'] == 'completed' and len(captures['captures']) == 2
        assert {(p['sourcePage'], p['image']) for p in captures['captures']} == {('04_traceability.html', '04_traceability.png'), ('09_annotation_expansion.html', '09_annotation_expansion.png')}
        for capture in captures['captures']:
            assert c.file_sha256(EVIDENCE/capture['image']) == capture['sha256'] and c.file_sha256(EVIDENCE/capture['sourcePage']) == capture['sourcePageSha256']
        c.write_json(target, {'passed': True, 'checkedAtUTC': datetime.now(UTC).isoformat(), 'engineeringTests': 369, 'audit': audit, 'immutableSourceSha256': unchanged,
            'previousVerificationSha256': c.file_sha256(RUNS/'verification_20261008_round40.json'), 'evidenceManifestSha256': c.file_sha256(EVIDENCE/'manifest.json'), 'capturesSha256': c.file_sha256(EVIDENCE/'captures.json'), 'qualityPromotionPassed': False})
        print(json.dumps({'passed': True, 'engineeringTests': 369, 'trained': False, 'modelPromoted': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('prepare', 'seal')); main(parser.parse_args().action)
