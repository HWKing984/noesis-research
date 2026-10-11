"""Verify actual train benchmark sources, receipts, BIO and regression; render and seal evidence."""
import argparse
import hashlib
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.robotparser import RobotFileParser

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT/'scripts'))
import expand_train_benchmarks as expansion
from compile_abstract_annotations import annotate
from export_course_evidence import page, table, highlight
c = expansion.c; g = expansion.g; read = expansion.read
RUNS = ROOT/'kg_datasets/dblp/course_v4_runs'
SOURCE = ROOT/'kg_datasets/dblp/course_abstract_benchmark_sources_20261008_45'
GENERATION = ROOT/'kg_datasets/dblp/course_abstract_benchmark_generation_20261008_45'
REVIEWED = ROOT/'kg_datasets/dblp/course_abstract_benchmark_reviewed_20261008_45'
FINAL = ROOT/'kg_datasets/dblp/course_abstract_benchmark_inputs_20261008_45'
DECISIONS = ROOT/'annotations/course_v4/abstract_benchmark_decisions_20261008_45.json'
REVIEWS = ROOT/'annotations/course_v4/abstract_benchmark_reviews_20261008_45.json'
EVIDENCE = ROOT/'docs/evidence/20261008_round45'
REGRESSION = RUNS/'tests_20261008_round45_workspace_temp.xml'


def checked():
    config, parent, old_refs, old = expansion.locked()
    for folder, digest in [(SOURCE, '51446422108d0fbbb8a23607248d888cbbff6c052fd566cedfecfd25cbcdde0d'), (GENERATION, '6a6a2708544a1c949f87a1ff65da25acd5fb512746462a1ad1f90623b30f885e'), (REVIEWED, '80484ffe4b6fa5f18b4f9cd47c75e56e02973c29398ce37a837eefef88de8c69'), (FINAL, 'efbd9c2fc1f1e89f7cfc2cc59ec2df239e534f763d07a4a38b92d9464016e167')]:
        manifest = g.verified_files(folder, digest); assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    assert c.file_sha256(RUNS/'verification_20261008_round44.json') == '56d091cb3f0ddeb32e2d2af9a2d73464cd6ff4bc891145d799d0abd5b159fd49'
    refs = c.read_jsonl(SOURCE/'train_references.jsonl'); records = c.read_jsonl(SOURCE/'abstracts.jsonl'); initial = c.read_jsonl(GENERATION/'generation_receipts.jsonl'); fresh = c.read_jsonl(REVIEWED/'reviewed_receipts.jsonl')
    decisions = read(DECISIONS)['documents']; review = read(REVIEWS); assert review['independent'] is False
    assert read(SOURCE/'selection_lock.json')['selected'] == config['seeds'] and len(refs) == len(records) == len(initial) == len(fresh) == len(decisions) == len(review['reviews']) == 4
    robots = RobotFileParser(); robots.parse((SOURCE/'robots.txt').read_text(encoding='utf-8').splitlines()); policy = read(SOURCE/'policy.json')
    assert policy['robotsSha256'] == c.file_sha256(SOURCE/'robots.txt') and policy['crawlDelaySeconds'] >= max(15.1, robots.crawl_delay(expansion.transport.AGENT) or 0)
    requests = read(SOURCE/'requests.json'); assert len(requests) == 4 and all(r['status'] == 'completed' for r in requests)
    times = [datetime.fromisoformat(r['startedAtUTC']) for r in requests]; intervals = [(b-a).total_seconds() for a, b in zip(times, times[1:])]; assert min(intervals) >= 15
    for seed, ref, record, prior, receipt, decision, judgment in zip(config['seeds'], refs, records, initial, fresh, decisions, review['reviews']):
        raw = (SOURCE/record['rawResponseFile']).read_bytes(); title, text = expansion.parse_page(raw, seed)
        assert robots.can_fetch(expansion.transport.AGENT, ref['sourceURL']) and expansion.title_key(title) == expansion.title_key(seed['title'])
        assert ref['arxivId'] == record['arxivId'] == decision['arxivId'] == seed['arxivId'] and ref['text'] == text == record['abstract'] and ref['split'] == 'train'
        assert ref['textSha256'] == record['content_hash'] == decision['textSha256'] == hashlib.sha256(text.encode('utf-8')).hexdigest() and record['raw_response_sha256'] == hashlib.sha256(raw).hexdigest()
        assert prior['annotation'] == annotate(decision, ref) and prior['review'] is None and judgment['reason'].strip()
        assert not c.validate_receipt(receipt, ref) and receipt['review'] is not None
        assert receipt['annotation'] == prior['annotation'] | {'reviewOfSha256': prior['contentSha256'], 'notes': prior['annotation']['notes']+' Self-review: '+judgment['reason']}
    final_refs = c.read_jsonl(FINAL/'train_references.jsonl'); final_receipts = c.read_jsonl(FINAL/'train_reviewed_receipts.jsonl')
    assert final_refs == old_refs+refs and final_receipts == old+fresh and len({r['groupId'] for r in final_refs}) == len(final_refs) == 62
    assert (parent/'train_reviewed_receipts.jsonl').read_bytes().splitlines() == (FINAL/'train_reviewed_receipts.jsonl').read_bytes().splitlines()[:58]
    rebuilt = expansion.rows_for(final_refs, final_receipts)
    for name, rows in zip(('ner_train', 'relation_train', 'full_relation_train', 'excluded_ner_train'), rebuilt[:4]): assert c.read_jsonl(FINAL/(name+'.jsonl')) == rows
    assert tuple(map(len, rebuilt[:4])) == (58, 271, 11, 4) and rebuilt[4:] == (1659, 1930)
    assert Counter(e['label'] for r in rebuilt[0] for e in r['entities']) == {'METHOD': 405, 'TASK': 218, 'DATASET': 55}
    old_pairs = expansion.rows_for(old_refs, old)[1]; assert rebuilt[1][:267] == old_pairs
    new_pairs = rebuilt[1][267:]; assert Counter(p['label'] for p in new_pairs) == {'EVALUATED_ON': 3, 'USED_FOR': 1} and len({p['sampleId'] for p in new_pairs}) == 1
    alignment = c.read_jsonl(FINAL/'token_alignment_train.jsonl'); assert len(alignment) == 58
    for row, item in zip(rebuilt[0], alignment):
        offsets = item['offsets']; labels = item['labels']; assert row['sampleId'] == item['sampleId'] and c.align_bio(offsets, row['entities'], row['text']) == labels
        decoded = expansion.ner.decode_bio([0 if tuple(o) == (0, 0) else tag for o, tag in zip(offsets, labels)], offsets, row['text'])
        assert not decoded['invalidTransitions'] and decoded['entities'] == [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]
    dev = [p for p in parent.iterdir() if p.is_file() and 'dev' in p.stem]; assert len(dev) == 9 and all(c.file_sha256(p) == c.file_sha256(FINAL/p.name) for p in dev)
    counts = lambda rows: (sum(any(e['label'] == 'DATASET' for e in r['entities']) for r in rows), {e['text'] for r in rows for e in r['entities'] if e['label'] == 'DATASET'})
    before = counts(expansion.rows_for(old_refs, old)[0]); after = counts(rebuilt[0]); assert before[0] == 16 and after[0] == 20 and len(before[1]) == 27 and len(after[1]) == 31
    suite = ET.parse(REGRESSION).getroot().find('testsuite'); assert suite is not None and int(suite.attrib['tests']) == 373 and all(int(suite.attrib[k]) == 0 for k in ('errors', 'failures', 'skipped'))
    summary = read(FINAL/'summary.json'); assert summary['maxMarkedTokens'] == 333 and all(summary[k] is False for k in ('trainingExecuted', 'inferenceExecuted', 'heldOutAbstractsAccessed', 'modelPromoted', 'qualityPromotionPassed', 'independentHumanGold'))
    state = summary | {'BIORecomputed': 58, 'actualSourcesParsed': 4, 'sourceRequestWallSpacingsSeconds': intervals, 'newLiteralDatasetNames': sorted(after[1]-before[1]), 'literalDatasetNames': 31, 'newEVALUATED_ONSourcePapers': 1, 'engineeringTests': 373, 'regressionSeconds': float(suite.attrib['time']), 'regressionScope': 'D_drive_isolated_process_temp; C_drive_previous_rename_problem_not_fixed'}
    return state, refs, fresh


def main(action):
    state, refs, fresh = checked()
    if action == 'prepare':
        if EVIDENCE.exists(): raise FileExistsError('Preserve evidence')
        paths = [Path(__file__), expansion.CONTRACT, DECISIONS, REVIEWS, ROOT/'scripts/expand_train_benchmarks.py', ROOT/'tests/test_train_benchmark_expansion.py', ROOT/'docs/system_status_round45.md', ROOT/'README.md', REGRESSION, RUNS/'tests_20261008_round45_targeted.xml', RUNS/'round45_snapshot_precondition_failure.json', RUNS/'verification_20261008_round44.json', SOURCE/'manifest.json', SOURCE/'selection_lock.json', SOURCE/'policy.json', SOURCE/'robots.txt', SOURCE/'requests.json', SOURCE/'abstracts.jsonl', SOURCE/'train_references.jsonl', GENERATION/'manifest.json', GENERATION/'generation_receipts.jsonl', REVIEWED/'manifest.json', REVIEWED/'reviewed_receipts.jsonl', FINAL/'manifest.json', FINAL/'summary.json']
        paths += [SOURCE/record['rawResponseFile'] for record in c.read_jsonl(SOURCE/'abstracts.jsonl')]
        EVIDENCE.mkdir(parents=True)
        for source in paths:
            target = EVIDENCE/'sources'/source.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        c.write_json(EVIDENCE/'audit_state.json', state); stamp = datetime.now(UTC).isoformat()
        body = '<p>四篇阅读理解基准原论文只用于训练；在获取页面/标签前锁定种子，并按规范化题名与arXiv ID检查现有论文身份。定向训练选择有偏，不是独立、代表性评测。</p>'
        body += table(['训练量', '第44轮', '第45轮'], [['固定队列 / NER / 隔离', '58 / 54 / 4', '62 / 58 / 4'], ['METHOD / TASK / DATASET', '403 / 196 / 44', '405 / 218 / 55'], ['含DATASET论文 / 字面名称', '16 / 27', '20 / 31（未做别名归一）'], ['明确 / 未决 / 全候选', '267 / 1647 / 1914', '271 / 1659 / 1930'], ['完整关系文档', '8', '11（新增3篇零候选，不是负例）']])
        body += '<h2>真实采集与AI复核</h2>'+table(['源论文', '新增实体/关系'], [['1704.04683 · RACE', 'DATASET3 / TASK3；无命名方法，零候选'], ['1705.03551 · TriviaQA', 'DATASET5 / TASK3 / METHOD2；3评测＋1用途，12未决'], ['1809.09600 · HotpotQA', 'DATASET2 / TASK6；无命名方法，零候选'], ['1903.00161 · DROP', 'DATASET1 / TASK10；无命名方法，零候选']])
        body += '<p>四个页面题名/ID匹配，169–219 tokens，无截断/失败/替换。原文、HTML、robots、请求时间与SHA保存；实际同会话自复核不是独立gold。新增31字面名称中的4个为DROP/HotpotQA/RACE/TriviaQA，重复提及不冒充独立论文。</p><p>新增评测仅3个跨度对、来自1篇论文；未增加dev EVALUATED_ON=0/覆盖7/19。没有新训练、推理或F1，不升级模型或31图。</p>'
        (EVIDENCE/'02_training.html').write_text(page('四篇训练基准与稀有实体支持 · 第45轮', body, stamp, ['sources/kg_datasets/dblp/course_abstract_benchmark_inputs_20261008_45/summary.json']), encoding='utf-8')
        body = '<h2>TriviaQA：局部原文与实体</h2><div class="title">'+highlight(refs[1]['text'][669:989], [{k: (e[k]-669 if k in ('start', 'end') else e[k]) for k in ('start', 'end', 'text', 'label')} for e in fresh[1]['annotation']['entities'] if 669 <= e['start'] and e['end'] <= 989])+'</div>'
        body += table(['关系', '为何这样判'], [['neural network → SQuAD / reading comprehension', '单数从句描述网络的局部表现与用途，不套给classifier'], ['classifier、network → 最后TriviaQA提及', '两baseline的23%/40%与human80%对比；同一源论文的3评测不是独立试验'], ['其余12对', 'UNRESOLVED，包括classifier→SQuAD；缺少表现报告不是负例']])
        body += '<h2>保护与核验</h2>'+table(['核验', '实际'], [['旧输入', '58行原收据字节不变，267旧关系不变；9dev文件原字节复制'], ['编码', '58篇BIO重算通过；271对已严格标记编码，最长333 tokens'], ['完整工程回归', f'373通过 / {state["regressionSeconds"]:.2f}秒 / D隔离tmp；无失败或跳过'], ['失败记录', '曾在review未封存时提前请求snapshot，被缺manifest拒绝，未写输出；等待原review完成后再推进'], ['没有执行', 'dev/test摘要或标签消费、模型训练/推理、写库/重启/晋级；C历史rename未修']])
        body += '<p>mle-workflow约束来源、论文身份隔离与未决遮罩。下一步另锁使用新版数据的单一模型对照与资源预算；四篇同任务族基准仍不能证明跨领域泛化、独立评估或长尾消歧完成。</p>'
        (EVIDENCE/'04_traceability.html').write_text(page('局部关系证据与不可变输入 · 第45轮', body, stamp, ['sources/annotations/course_v4/abstract_benchmark_reviews_20261008_45.json', 'sources/kg_datasets/dblp/course_abstract_benchmark_sources_20261008_45/requests.json']), encoding='utf-8')
        c.write_json(EVIDENCE/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'filesSha256': {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}}); print(state)
    else:
        target = RUNS/'verification_20261008_round45.json'
        if target.exists(): raise FileExistsError('Preserve verification')
        g.verified_files(EVIDENCE); assert read(EVIDENCE/'audit_state.json') == state
        captures = json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig')); assert captures['status'] == 'completed' and len(captures['captures']) == 2
        assert {(v['sourcePage'], v['image']) for v in captures['captures']} == {('02_training.html', '02_training.png'), ('04_traceability.html', '04_traceability.png')}
        for entry in captures['captures']: assert c.file_sha256(EVIDENCE/entry['image']) == entry['sha256'] and c.file_sha256(EVIDENCE/entry['sourcePage']) == entry['sourcePageSha256']
        c.write_json(target, {'passed': True, 'checkedAtUTC': datetime.now(UTC).isoformat(), 'audit': state, 'previousVerificationSha256': c.file_sha256(RUNS/'verification_20261008_round44.json'), 'finalTrainManifestSha256': c.file_sha256(FINAL/'manifest.json'), 'evidenceManifestSha256': c.file_sha256(EVIDENCE/'manifest.json'), 'capturesSha256': c.file_sha256(EVIDENCE/'captures.json'), 'qualityPromotionPassed': False}); print({'passed': True, 'engineeringTests': 373, 'modelPromoted': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('prepare', 'seal')); main(parser.parse_args().action)
