"""Recompute train-only scope repairs and seal real-artifact browser evidence."""
import argparse
import hashlib
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT/'scripts'))
import review_train_entity_scope as scope
import patch_train_method_inventory as inventory
from course_abstract_relation import rows_for
from export_course_evidence import page, table, escaped
c = scope.c; g = scope.g; read = scope.read
RUNS = ROOT/'kg_datasets/dblp/course_v4_runs'
GENERATION = ROOT/'kg_datasets/dblp/course_abstract_scope_generation_20261008_44'
BASE = ROOT/'kg_datasets/dblp/course_abstract_scope_reviewed_20261008_44'
FINAL = ROOT/'kg_datasets/dblp/course_abstract_scope_inventory_reviewed_20261008_44'
REVIEWS = ROOT/'annotations/course_v4/abstract_scope_reviews_20261008_44.json'
EVIDENCE = ROOT/'docs/evidence/20261008_round44'
REGRESSION = RUNS/'tests_20261008_round44_workspace_temp.xml'


def checked():
    config, refs, old, decisions = scope.load_inputs(); parent = ROOT/config['snapshot']
    bindings = [(GENERATION, '69ff614a23decc204d1fa548b91dbeb41a5007a605172ac5950326afade5df83'), (BASE, '8c8d66afbacec040e2e00120d884fd179f215fd42a19024ca2726175d84ad01c'), (FINAL, '3bbad6603684b1ea47e70ddd9193d8e037eda0d285cea7cbb84050fc21b2921f'), (RUNS/'abstract_train_diagnostic_20261008_43', '47de2c98efdf3bc92849b7f32c32a40cb005c53e0c19aee62df348e3cb759bd8')]
    for folder, digest in bindings:
        manifest = g.verified_files(folder, digest)
        assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    assert c.file_sha256(RUNS/'verification_20261008_round43.json') == '7308470f344f189e7207cc888e31e4f756e64a220c12f5fd64d04e0e4ba26271'
    initial = c.read_jsonl(GENERATION/'generation_receipts.jsonl'); base = c.read_jsonl(BASE/'train_reviewed_receipts.jsonl'); final = c.read_jsonl(FINAL/'train_reviewed_receipts.jsonl')
    reviews = read(REVIEWS); lookup = {r['arxivId']: i for i, r in enumerate(refs)}; generated = {r['reference']['arxivId']: r for r in initial}
    assert len(base) == len(final) == 58 and len(generated) == len(initial) == 5
    assert reviews['independent'] is False and reviews['generationManifestSha256'] == bindings[0][1]
    assert [r['arxivId'] for r in reviews['documents']] == config['reviewCohort']
    for decision, judgment in zip(decisions['documents'], reviews['documents']):
        index = lookup[decision['arxivId']]; previous = old[index]; receipt = base[index]; gen = generated.get(decision['arxivId'])
        assert not c.validate_receipt(receipt, refs[index]) and judgment['reason'].strip()
        if decision['action'] == 'keep':
            assert receipt == previous and gen is None and judgment['generationContentSha256'] is None
        else:
            assert gen['annotation'] == scope.response_for(decision, refs[index], previous) and gen['review'] is None
            assert judgment['generationContentSha256'] == gen['contentSha256'] and receipt['annotation']['reviewOfSha256'] == gen['contentSha256']
            assert receipt['annotation'] == gen['annotation'] | {'reviewOfSha256': gen['contentSha256'], 'notes': gen['annotation']['notes']+' Actual same-session self-review: '+judgment['reason']}
    changed = {lookup[d['arxivId']] for d in decisions['documents'] if d['action'] != 'keep'}
    assert {i for i, (a, b) in enumerate(zip(old, base)) if a != b} == changed
    repair = read(inventory.CONTRACT); index = lookup[repair['arxivId']]; expected, mapping = inventory.add_method(refs[index], base[index], repair)
    patch_initial = c.read_jsonl(FINAL/'inventory_generation_receipts.jsonl'); assert len(patch_initial) == 1 and patch_initial[0]['annotation'] == expected
    assert {i for i, (a, b) in enumerate(zip(base, final)) if a != b} == {index}
    assert final[index]['annotation'] == expected | {'reviewOfSha256': patch_initial[0]['contentSha256'], 'notes': expected['notes']+' Actual same-session self-review: '+repair['selfReview']}
    ledger = read(FINAL/'inventory_patch.json'); assert ledger['oldToNewEntityIds'] == mapping
    old_pairs = base[index]['annotation']['relations']; new_pairs = {(p['head'], p['tail']): p for p in final[index]['annotation']['relations']}
    assert len(old_pairs) == 45 and len(new_pairs) == 60
    for p in old_pairs: assert new_pairs[(mapping[p['head']], mapping[p['tail']])] == p | {'head': mapping[p['head']], 'tail': mapping[p['tail']]}
    added = [p for p in new_pairs.values() if p['head'] == 'e1']; assert len(added) == 15 and all(p['label'] == 'UNRESOLVED' and p['evidence'] is None for p in added)
    for ref, receipt in zip(refs, final):
        assert hashlib.sha256(ref['text'].encode('utf-8')).hexdigest() == ref['textSha256'] and not c.validate_receipt(receipt, ref) and receipt['review'] is not None
    rebuilt = rows_for(refs, final)
    for name, values in zip(('ner_train', 'relation_train', 'full_relation_train', 'excluded_ner_train'), rebuilt[:4]): assert c.read_jsonl(FINAL/(name+'.jsonl')) == values
    assert tuple(map(len, rebuilt[:4])) == (54, 267, 8, 4) and rebuilt[4:] == (1647, 1914)
    support = Counter(e['label'] for r in rebuilt[0] for e in r['entities']); assert support == {'METHOD': 403, 'TASK': 196, 'DATASET': 44}
    assert Counter(p['label'] for p in rebuilt[1]) == {'USED_FOR': 183, 'EVALUATED_ON': 58, 'NO_RELATION': 26}
    alignments = c.read_jsonl(FINAL/'token_alignment_train.jsonl'); assert len(alignments) == 54
    for row, alignment in zip(rebuilt[0], alignments):
        offsets = alignment['offsets']; labels = alignment['labels']; assert row['sampleId'] == alignment['sampleId'] and c.align_bio(offsets, row['entities'], row['text']) == labels
        decoded = scope.ner.decode_bio([0 if tuple(o) == (0, 0) else tag for o, tag in zip(offsets, labels)], offsets, row['text'])
        assert not decoded['invalidTransitions'] and decoded['entities'] == [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]
    unchanged = set(range(58))-(changed | {index}); old_lines = (parent/'train_reviewed_receipts.jsonl').read_bytes().splitlines(); new_lines = (FINAL/'train_reviewed_receipts.jsonl').read_bytes().splitlines()
    assert len(unchanged) == 52 and len(old_lines) == len(new_lines) == 58 and all(old_lines[i] == new_lines[i] for i in unchanged)
    opaque = [p for p in parent.iterdir() if p.is_file() and ('dev' in p.stem or p.name == 'train_references.jsonl')]
    assert len(opaque) == 10 and all(c.file_sha256(p) == c.file_sha256(FINAL/p.name) for p in opaque)
    admitted = [final[lookup[d['arxivId']]]['annotation'] for d in decisions['documents'] if d['action'] == 'admit']
    assert sum(len(a['relations']) for a in admitted) == 54 and sum(not a['relations'] for a in admitted) == 2 and all(p['label'] == 'UNRESOLVED' for a in admitted for p in a['relations'])
    touched = next(d['touchingPairs'] for d in decisions['documents'] if d['action'] == 'edit'); assert len(touched) == 8 and Counter(p['label'] for p in touched) == {'USED_FOR': 3, 'UNRESOLVED': 5}
    suite = ET.parse(REGRESSION).getroot().find('testsuite'); assert suite is not None and int(suite.attrib['tests']) == 372 and all(int(suite.attrib[k]) == 0 for k in ('errors', 'failures', 'skipped'))
    summary = read(FINAL/'summary.json'); assert summary['status'] == 'completed' and all(summary[k] is False for k in ('trainingExecuted', 'testSemanticallyRead', 'modelPromoted', 'qualityPromotionPassed', 'independentHumanGold', 'DATASETSupportIncreased'))
    state = {'sourceReviewedTrainDocuments': 11, 'NERtrain': 54, 'NERexcluded': 4, 'entitySupport': dict(support), 'freshReviewedDocumentsComparedTo43': 6, 'unchangedReceiptLines': 52, 'knownRelations': 267, 'unknownPairs': 1647, 'eligiblePairs': 1914, 'completeRelationDocuments': 8, 'newZeroCandidateDocuments': 2, 'rejudgedTouchingPairs': 8, 'oldInventoryRelationsPreserved': 45, 'newInventoryUnknownPairs': 15, 'BIORecomputed': 54, 'opaqueDevFilesIdentical': 9, 'engineeringTests': 372, 'regressionSeconds': float(suite.attrib['time']), 'regressionScope': 'D_drive_isolated_process_temp; C_drive_previous_rename_problem_not_fixed', 'trainingExecuted': False, 'testSemanticallyRead': False, 'modelPromoted': False, 'qualityPromotionPassed': False, 'independentHumanGold': False}
    return state, config, repair


def main(action):
    state, config, repair = checked()
    if action == 'prepare':
        if EVIDENCE.exists(): raise FileExistsError('Preserve evidence')
        paths = [Path(__file__), scope.CONTRACT, scope.DECISIONS, REVIEWS, inventory.CONTRACT, ROOT/'scripts/review_train_entity_scope.py', ROOT/'scripts/patch_train_method_inventory.py', ROOT/'tests/test_train_scope_review.py', ROOT/'docs/system_status_round44.md', ROOT/'README.md', REGRESSION, RUNS/'tests_20261008_round44_inventory_targeted.xml', RUNS/'verification_20261008_round43.json', GENERATION/'manifest.json', GENERATION/'generation_receipts.jsonl', BASE/'manifest.json', BASE/'summary.json', BASE/'scope_review_ledger.jsonl', FINAL/'manifest.json', FINAL/'summary.json', FINAL/'inventory_patch.json', FINAL/'inventory_generation_receipts.jsonl']
        EVIDENCE.mkdir(parents=True)
        for source in paths:
            target = EVIDENCE/'sources'/source.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        c.write_json(EVIDENCE/'audit_state.json', state); stamp = datetime.now(UTC).isoformat()
        body = '<p>固定训练侧11篇整篇摘要：8篇旧隔离＋3篇源文范围提醒。AI初标与实际同会话自复核，不是独立金标准；没有重训、开发或最终测试推理。</p>'
        body += table(['训练输入', '第43轮', '第44轮最终'], [['NER准入 / 隔离', '50 / 8', '54 / 4'], ['METHOD / TASK / DATASET', '378 / 189 / 44', '403 / 196 / 44'], ['明确关系', '267', '267（183用途 / 58评测 / 26负例）'], ['未决 / 全部候选', '1578 / 1845', '1647 / 1914（不填负）'], ['完整关系文档', '6', '8（新增2篇真实零候选，不是负例）']])
        body += '<h2>四篇重新准入；仍保留四篇隔离</h2>'+table(['原文', '处理'], [['2009.03300 · MMLU源摘要', '仅GPT-3为方法；学科列表不是计算任务，MMLU名不在摘要'], ['2105.15057 · DNN摘要', '12方法 / 2技术任务；24对全部未决，源文拼写不修改'], ['2507.22101 · 农业综述', '6方法 / 5任务；30对全部未决，不从未来方向推实际应用'], ['2312.14977 · diffusion介绍', '5方法 / 0任务；排除物理PDE同名短语与课程领域列表'], ['2404.01036 / 1804.07461 / 2510.02719 / 2208.08611', '教育技能、共享头部、未命名任务/数据、低信息平台仍隔离']])
        body += '<p>DATASET仍44提及、16篇论文；没有提高稀有类独立支持。本轮新增NER输入尚未用于训练，没有新的F1收益。</p>'
        (EVIDENCE/'02_training.html').write_text(page('训练侧范围清洗与四篇准入 · 第44轮', body, stamp, ['sources/kg_datasets/dblp/course_abstract_scope_inventory_reviewed_20261008_44/summary.json']), encoding='utf-8')
        body = '<h2>两处修正，关系按原文端点处理</h2>'+table(['来源', '原文修正', '关系处理'], [['2510.26830 · SmoothGuard', '110:119 reasoning → 110:150 reasoning over textual and visual inputs', '8对明确复判：保留3用途、5未决；不把防御组件用途套成基础模型任务'], ['2406.01574 · MMLU-Pro', '补METHOD 14:41 large-scale language models', '18旧实体按跨度重绑定；45旧关系类别/证据/理由不变；15新对全未决']])
        body += f'<blockquote>{escaped(repair["sourceQuote"])}</blockquote><p>{escaped(repair["selfReview"])}</p>'
        body += '<h2>保留及可复算核验</h2>'+table(['项目', '实际结果'], [['相对43收据', '6份新初标＋同会话复核；52行字节不变'], ['最终BIO', '54篇保存offsets/labels严格重算，零非法转移'], ['开发侧', '9文件只按字节复制并核验SHA；训练原文不改'], ['工程回归', f'372通过 / {state["regressionSeconds"]:.2f}秒 / D隔离tmp；零失败或跳过'], ['历史现场', '初标44、基础复核44、库存修补44分别封存，不覆盖'], ['未执行', '新训练、dev/test推理、线上图写库、模型替换或服务重启']])
        body += '<p>模型泛化、DATASET长尾支持、完整dev EVALUATED_ON=0/覆盖7/19、独立评估与作者/概念长尾仍未解决。C默认临时目录历史rename问题未修。本轮按mle-workflow锁定训练侧契约和不泄漏边界；线上继续31图与旧模型，完整报告暂停。</p>'
        (EVIDENCE/'04_traceability.html').write_text(page('任务边界、漏方法与不可变证据 · 第44轮', body, stamp, ['sources/resources/course_abstract_scope_review_v1.json', 'sources/kg_datasets/dblp/course_abstract_scope_inventory_reviewed_20261008_44/inventory_patch.json']), encoding='utf-8')
        c.write_json(EVIDENCE/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'filesSha256': {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}}); print(state)
    else:
        target = RUNS/'verification_20261008_round44.json'
        if target.exists(): raise FileExistsError('Preserve verification')
        g.verified_files(EVIDENCE); assert read(EVIDENCE/'audit_state.json') == state
        captures = json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig')); assert captures['status'] == 'completed' and len(captures['captures']) == 2
        assert {(v['sourcePage'], v['image']) for v in captures['captures']} == {('02_training.html', '02_training.png'), ('04_traceability.html', '04_traceability.png')}
        for entry in captures['captures']: assert c.file_sha256(EVIDENCE/entry['image']) == entry['sha256'] and c.file_sha256(EVIDENCE/entry['sourcePage']) == entry['sourcePageSha256']
        c.write_json(target, {'passed': True, 'checkedAtUTC': datetime.now(UTC).isoformat(), 'audit': state, 'previousVerificationSha256': c.file_sha256(RUNS/'verification_20261008_round43.json'), 'finalTrainManifestSha256': c.file_sha256(FINAL/'manifest.json'), 'evidenceManifestSha256': c.file_sha256(EVIDENCE/'manifest.json'), 'capturesSha256': c.file_sha256(EVIDENCE/'captures.json'), 'qualityPromotionPassed': False}); print({'passed': True, 'engineeringTests': 372, 'modelPromoted': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('prepare', 'seal')); main(parser.parse_args().action)
