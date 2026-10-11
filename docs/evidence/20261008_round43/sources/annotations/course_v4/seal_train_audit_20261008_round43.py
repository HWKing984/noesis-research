"""Recompute saved train diagnostics and verify the narrow source correction, then capture/seal evidence."""
import argparse
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT/'scripts'))
import audit_abstract_ner_training as audit
import revise_train_task_boundary as boundary
from course_abstract_relation import rows_for
from export_course_evidence import page, table, escaped
c = audit.c; g = audit.g; read = audit.read
RUNS = ROOT/'kg_datasets/dblp/course_v4_runs'
RUN = RUNS/'abstract_train_diagnostic_20261008_43'
REVISION = ROOT/'kg_datasets/dblp/course_abstract_task_boundary_reviewed_20261008_43'
EVIDENCE = ROOT/'docs/evidence/20261008_round43'
REGRESSION = RUNS/'tests_20261008_round43_final_workspace_temp.xml'


def checked():
    config, rows, refs, review = audit.load_inputs(); report = read(RUN/'audit.json')
    for folder, digest in ((RUN, '47de2c98efdf3bc92849b7f32c32a40cb005c53e0c19aee62df348e3cb759bd8'), (REVISION, '401267ceeb46e8f0f0b6e25f6fdf09d9f1caaaf8654d29d21ce1f56f22bbb5a1')):
        manifest = g.verified_files(folder, digest)
        assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    assert report['inventory'] == audit.inventory(rows) and read(RUN/'status.json')['status'] == 'completed'
    by_id = {r['sampleId']: r for r in refs}
    for name in config['models']:
        saved = c.read_jsonl(RUN/(name+'_train_predictions.jsonl')); assert [r['sampleId'] for r in saved] == [r['sampleId'] for r in rows]
        assert all(p['textSha256'] == r['textSha256'] and p['referenceEntities'] == r['entities'] for r, p in zip(rows, saved))
        predicted = [r['predictedEntities'] for r in saved]
        assert audit.ner.score_rows(rows, predicted, evaluation_target=config['evaluationTarget']) == report['models'][name]['metrics']
        expected = [e | {'arxivId': by_id[e['sampleId']]['arxivId']} for r, p in zip(rows, predicted) for e in audit.errors_for(r, p)]
        assert expected == c.read_jsonl(RUN/(name+'_train_errors.jsonl'))
        assert dict(Counter(e['side'] for e in expected)) == report['models'][name]['errorCounts']
        assert dict(Counter(e['side']+'/'+e['label']+'/'+e['cause'] for e in expected)) == report['models'][name]['errorClusters']
    parent = ROOT/config['snapshot']; old = c.read_jsonl(parent/'train_reviewed_receipts.jsonl'); fresh = c.read_jsonl(REVISION/'train_reviewed_receipts.jsonl'); proposal = read(boundary.CONTRACT)
    changed = next(i for i, r in enumerate(refs) if r['arxivId'] == proposal['arxivId'])
    assert len(old) == len(fresh) == 58 and [i for i, (a, b) in enumerate(zip(old, fresh)) if a != b] == [changed]
    for ref, receipt in zip(refs, fresh): assert not c.validate_receipt(receipt, ref) and receipt['review'] is not None
    initial = c.read_jsonl(REVISION/'changed_generation_receipts.jsonl'); assert len(initial) == 1 and initial[0]['annotation'] == boundary.amend(proposal, refs[changed], old[changed])
    ann = fresh[changed]['annotation']; assert ann['entities'][2] == proposal['after'] and ann['relations'] == old[changed]['annotation']['relations']
    assert ann['entities'][:2]+ann['entities'][3:] == old[changed]['annotation']['entities'][:2]+old[changed]['annotation']['entities'][3:]
    rebuilt = rows_for(refs, fresh)
    for name, values in zip(('ner_train', 'relation_train', 'full_relation_train', 'excluded_ner_train'), rebuilt[:4]): assert c.read_jsonl(REVISION/(name+'.jsonl')) == values
    assert rebuilt[4:] == (1578, 1845)
    alignments = c.read_jsonl(REVISION/'token_alignment_train.jsonl'); assert len(alignments) == len(rebuilt[0]) == 50
    for row, alignment in zip(rebuilt[0], alignments):
        assert row['sampleId'] == alignment['sampleId']; offsets = alignment['offsets']; labels = alignment['labels']
        assert c.align_bio(offsets, row['entities'], row['text']) == labels
        decoded = audit.ner.decode_bio([0 if tuple(o) == (0, 0) else tag for o, tag in zip(offsets, labels)], offsets, row['text'])
        assert not decoded['invalidTransitions'] and decoded['entities'] == [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]
    copied = [p for p in parent.iterdir() if p.is_file() and ('dev' in p.stem or p.name == 'train_references.jsonl')]
    assert all(c.file_sha256(p) == c.file_sha256(REVISION/p.name) for p in copied)
    old_lines = (parent/'train_reviewed_receipts.jsonl').read_bytes().splitlines(); new_lines = (REVISION/'train_reviewed_receipts.jsonl').read_bytes().splitlines()
    assert len(old_lines) == len(new_lines) == 58 and all(a == b for i, (a, b) in enumerate(zip(old_lines, new_lines)) if i != changed)
    suite = ET.parse(REGRESSION).getroot().find('testsuite'); assert suite is not None and int(suite.attrib['tests']) == 371 and all(int(suite.attrib[k]) == 0 for k in ('errors', 'failures', 'skipped'))
    assert c.file_sha256(RUNS/'verification_20261008_round42.json') == '61ac33d201a5f50cc19b112912a11fa3167115c47f234621792aff7edc131bd7'
    state = {'trainDiagnosticMetricsAndErrorsRecomputed': True, 'changedTrainSpanCount': 1, 'unchangedReceiptLines': 57, 'revisedTrainBIORecomputed': 50, 'opaqueDevFilesIdentical': len(copied)-1, 'knownRelationCount': 267, 'unknownPairs': 1578, 'independentHumanGold': False, 'trainingExecuted': False, 'testSemanticallyRead': False, 'modelPromoted': False, 'qualityPromotionPassed': False, 'engineeringTests': 371, 'regressionSeconds': float(suite.attrib['time']), 'regressionScope': 'D_drive_isolated_process_temp; C_drive_previous_rename_problem_not_fixed'}
    return state, report, proposal


def main(action):
    state, report, proposal = checked()
    if action == 'prepare':
        if EVIDENCE.exists(): raise FileExistsError('Preserve evidence')
        EVIDENCE.mkdir(parents=True)
        paths = [Path(__file__), audit.CONTRACT, audit.REVIEW, boundary.CONTRACT, ROOT/'scripts/audit_abstract_ner_training.py', ROOT/'scripts/revise_train_task_boundary.py', ROOT/'tests/test_train_ner_audit.py', ROOT/'docs/system_status_round43.md', ROOT/'README.md', REGRESSION, RUNS/'tests_20261008_round43_targeted.xml', RUNS/'tests_20261008_round43_boundary_fixed.xml', RUN/'manifest.json', RUN/'audit.json', RUN/'status.json', RUN/'old35_train_errors.jsonl', RUN/'new42_train_errors.jsonl', REVISION/'manifest.json', REVISION/'revision.json', REVISION/'summary.json', REVISION/'changed_generation_receipts.jsonl']
        for source in paths:
            target = EVIDENCE/'sources'/source.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        c.write_json(EVIDENCE/'audit_state.json', state); stamp = datetime.now(UTC).isoformat(); pct = lambda n: f'{n*100:.2f}%'
        body = '<p>仅推理50篇已参与训练的摘要；旧35只训练过其中29篇，新42训练过全部50篇。分数不表示新模型泛化能力，未执行新的dev/test。</p>'
        body += table(['冻结模型', '训练集P / R / F1', 'DATASET TP / 参考', 'TASK TP / 参考', 'FP / FN'], [[name, ' / '.join(pct(m['metrics']['micro'][k]) for k in ('precision', 'recall', 'f1')), f'{m["metrics"]["perClass"]["DATASET"]["truePositive"]} / 44', f'{m["metrics"]["perClass"]["TASK"]["truePositive"]} / 189', f'{m["errorCounts"]["FP"]} / {m["errorCounts"]["FN"]}'] for name, m in report['models'].items()])
        tokens = report['BIOtokenCounts']; total = sum(tokens.values()); ds = tokens['B-DATASET']+tokens['I-DATASET']
        body += '<h2>稀有类支持与重复集中</h2>'+table(['量', '实际'], [['实体提及', 'METHOD 378 / TASK 189 / DATASET 44'], ['DATASET文档 / 字面名称', '16 / 27（未做同义名归一）'], ['同一MMLU-Pro文档', '14 / 44提及，31.82%'], ['DATASET标注token', f'{ds} / {total}，{pct(ds/total)}'], ['严格BIO', '50篇通过；新42训练侧非法转移0'], ['新42剩余训练错例', '同一2501.02474中TASK漏1、边界错1（计FP1/FN2）']])
        body += '<p>新42训练DATASET召回100%，第42轮已有dev记录只有40%（本轮不重评）。这更符合泛化/分布或标签规则问题，不支持再增加epoch就能解决；不是已证明的唯一因果解释。</p><p>后续优先统一训练侧任务规则并增加独立论文/上下文多样性；不从dev/test挑词，不补未知负例，不降低晋级护栏。所有分数基于AI参考，不能当事实正确率。</p>'
        (EVIDENCE/'02_training.html').write_text(page('训练侧诊断，不是新测试成绩 · 第43轮', body, stamp, ['sources/kg_datasets/dblp/course_v4_runs/abstract_train_diagnostic_20261008_43/audit.json']), encoding='utf-8')
        body = '<p>原文复核已在看到新训练侧预测前记录此问题；本次独立修订合同只改一处跨度，不按模型预测改开发标签。</p><h2>同一源文中的不一致任务边界</h2>'+table(['位置', '原标签', '修订标签'], [['e1 / 0:31', 'Remote sensing object detection', '保持'], ['e3 / 377:393 → 362:393', 'object detection', 'remote sensing object detection']])
        body += f'<blockquote>{escaped(proposal["sourceQuote"])}</blockquote><p>{escaped(proposal["selfReview"])}</p>'
        body += '<h2>重新生成与保留范围</h2>'+table(['核验', '实际结果'], [['新初标＋同会话复核', '1篇；不是独立gold'], ['其他原收据', '57行字节不变'], ['实体/关系', '20个其他实体不变；10个受影响对保留UNRESOLVED'], ['当前train', 'NER50 / 隔离8；明确267 / 未决1578'], ['开发集', f'{state["opaqueDevFilesIdentical"]}个文件仅按字节复制、SHA一致'], ['修订后BIO', '50篇从保存offsets/labels重算通过'], ['最终工程回归', f'371通过 / {state["regressionSeconds"]:.2f}秒，D隔离tmp'], ['没有执行', '修订后重训、dev/test推理、生产图更新或重启']])
        body += '<p>DATASET泛化、其他TASK语义范围、独立评估、完整EVALUATED_ON支持与作者/概念长尾质量仍未解决。C默认临时目录rename问题保留，未声称修复。修订没有新的模型收益成绩，线上继续31图/旧模型。</p>'
        (EVIDENCE/'04_traceability.html').write_text(page('一处训练任务边界修订与保留范围 · 第43轮', body, stamp, ['sources/resources/course_abstract_task_boundary_v1.json', 'sources/kg_datasets/dblp/course_abstract_task_boundary_reviewed_20261008_43/revision.json']), encoding='utf-8')
        c.write_json(EVIDENCE/'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui', 'filesSha256': {p.relative_to(EVIDENCE).as_posix(): c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}}); print(state)
    else:
        target = RUNS/'verification_20261008_round43.json'
        if target.exists(): raise FileExistsError('Preserve verification')
        g.verified_files(EVIDENCE); assert read(EVIDENCE/'audit_state.json') == state
        captures = json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig')); assert captures['status'] == 'completed' and len(captures['captures']) == 2
        assert {(v['sourcePage'], v['image']) for v in captures['captures']} == {('02_training.html', '02_training.png'), ('04_traceability.html', '04_traceability.png')}
        for entry in captures['captures']: assert c.file_sha256(EVIDENCE/entry['image']) == entry['sha256'] and c.file_sha256(EVIDENCE/entry['sourcePage']) == entry['sourcePageSha256']
        c.write_json(target, {'passed': True, 'checkedAtUTC': datetime.now(UTC).isoformat(), 'audit': state, 'previousVerificationSha256': c.file_sha256(RUNS/'verification_20261008_round42.json'), 'evidenceManifestSha256': c.file_sha256(EVIDENCE/'manifest.json'), 'capturesSha256': c.file_sha256(EVIDENCE/'captures.json'), 'qualityPromotionPassed': False}); print({'passed': True, 'engineeringTests': 371, 'modelPromoted': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('prepare', 'seal')); main(parser.parse_args().action)
