"""Runnable snapshot-12 integrity check and real-artifact report page; no inference."""
import json
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_weak as c
from train_course_ner import load_snapshot, verify_files
from import_course_ai import assess_readiness, save_training_inputs
from prepare_course_weak import verify_dataset
from export_course_evidence import page, table, highlight, escaped


def main():
    dataset = ROOT / 'kg_datasets/dblp/course_v4_weak'
    old = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_11'
    new = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_12'
    run = ROOT / 'kg_datasets/dblp/course_v4_runs/pending_train_20261007_19'
    evidence = ROOT / 'docs/evidence/20261007_round19'
    verification = ROOT / 'kg_datasets/dblp/course_v4_runs/verification_20261007_round19.json'
    if evidence.exists() or verification.exists():
        raise ValueError('Preserve existing verification/evidence; choose a fresh version.')
    for folder in (old, new, run):
        verify_files(folder)
    references = verify_dataset(dataset)
    _, summary = load_snapshot(dataset, new, include_test=True)  # Binding only, not test inference.
    receipts = c.read_jsonl(new / 'receipts.jsonl')
    previous = c.read_jsonl(old / 'receipts.jsonl')
    added = c.read_jsonl(run / 'review/receipts.jsonl')
    assert receipts == previous + added and len(previous) == 908 and len(added) == 100
    assert all(r['reference']['split'] == 'train' for r in added)
    added_summary = assess_readiness(added, references)
    assert summary['generationReceiptDocuments'] == 1008 and summary['nerEligibleDocuments'] == 803
    assert added_summary['nerEligibleDocuments'] == 75 and added_summary['relationEligibleDocuments'] == 70
    assert added_summary['relationSupport']['train'] == {'USED_FOR': 70, 'EVALUATED_ON': 0, 'NO_RELATION': 2}
    unchanged = {}
    for task in ('ner', 'relation'):
        for split in ('dev', 'test'):
            name = f'{task}_inputs_{split}.jsonl'
            assert (old / name).read_bytes() == (new / name).read_bytes()
            unchanged[name] = c.file_sha256(new / name)
    # Reuse the canonical exporter to check every NER/RE row, including pairs/evidence.
    with tempfile.TemporaryDirectory(prefix='course-v4-export-check-') as temporary:
        expected = Path(temporary)
        save_training_inputs(expected, receipts, references)
        for path in expected.glob('*.jsonl'):
            assert path.read_bytes() == (new / path.name).read_bytes(), path.name
    pending = c.read_jsonl(new / 'pending_generation.jsonl')
    lookup = {r['sampleId']: r for r in references}
    seen = {r['reference']['sampleId'] for r in receipts}
    assert len(pending) == 992 and len({r['sampleId'] for r in pending}) == 992
    assert {r['sampleId'] for r in pending} == set(lookup) - seen
    assert all(lookup[r['sampleId']]['split'] == 'train' and set(r) == {'sampleId', 'text', 'textSha256'} for r in pending)
    pairs = {s: len(c.read_jsonl(new / f'relation_inputs_{s}.jsonl')) for s in ('train', 'dev', 'test')}
    assert pairs == {'train': 415, 'dev': 162, 'test': 137}
    frozen = {}
    for name, digest in [('ner', 'cf30fe489da3eb4aa22c309687e86fc711b9db564586d371e4792be8902ba96d'),
                         ('re', 'e4010d162f525221de7da30cf4c412892564a1da894d1271a72f1ddfa1893978')]:
        lock_path = ROOT / f'annotations/course_v4/{name}_test_selection_20261006.json'
        assert c.file_sha256(lock_path) == digest
        lock = json.loads(lock_path.read_text(encoding='utf-8'))
        model = ROOT / lock['developmentRun']
        assert c.file_sha256(model / 'manifest.json') == lock['developmentManifestSha256']
        verify_files(model)
        assert c.file_sha256(model / lock['checkpoint'] / 'model.safetensors') == lock['weightsSha256']
        frozen[name] = {'selectionSha256': digest, 'weightsSha256': lock['weightsSha256']}
    tests = ROOT / 'kg_datasets/dblp/course_v4_runs/tests_20261007_round19_all.xml'
    counts = {k: sum(int(s.get(k, 0)) for s in ET.parse(tests).getroot().iter('testsuite'))
              for k in ('tests', 'failures', 'errors', 'skipped')}
    assert counts == {'tests': 345, 'failures': 0, 'errors': 0, 'skipped': 0}
    judgments = json.loads((run / 'review_judgments.json').read_text(encoding='utf-8'))
    verdicts = Counter(r['verdict'] for r in judgments['judgments'])
    assert verdicts == {'confirmed': 97, 'revised': 3}
    stamp = datetime.now(UTC).isoformat()
    result = {'passed': True, 'checkedAtUTC': stamp, 'snapshotManifestSha256': c.file_sha256(new / 'manifest.json'),
              'runManifestSha256': c.file_sha256(run / 'manifest.json'), 'summary': summary,
              'newBatchSummary': added_summary, 'relationPairs': pairs, 'verdicts': dict(verdicts),
              'oldReceiptsUnchanged': True, 'devTestByteIdentical': unchanged, 'pendingOnlyTrain': True,
              'allExportRowsMatchReceipts': True, 'frozenModels': frozen, 'tests': counts,
              'trainingExecuted': False, 'modelInferenceExecuted': False, 'databaseWriteExecuted': False,
              'humanGold': False, 'independentReviewer': False}
    c.write_json(verification, result)
    evidence.mkdir(parents=True)
    sources = [new / 'summary.json', new / 'manifest.json', run / 'review/receipts.jsonl',
               run / 'review_judgments.json', tests, verification, Path(__file__),
               ROOT / 'scripts/export_course_evidence.py', ROOT / 'scripts/capture_course_evidence.ps1']
    bindings = {}
    for source in sources:
        destination = evidence / 'sources' / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        bindings[source.relative_to(ROOT).as_posix()] = c.file_sha256(source)
    body = '<h2>训练侧100篇：首轮 → 同会话候选可见自复核 → 隔离 → 新快照12</h2>'
    body += table(['项目', '本轮新增', '累计/范围'], [
        ('AI判断与自复核', '100篇；97确认 / 3修订', '1,008 / 2,000篇；992篇待首轮'),
        ('NER可用', '75篇；25篇隔离', '803篇：train492 / dev167 / test144'),
        ('RE可用', '70篇；72个实体对', '740篇 / 714个实体对（415 / 162 / 137）'),
        ('新关系类别', '70 USED_FOR / 2 NO_RELATION', '本轮没有新增 EVALUATED_ON'),
        ('命名数据集', '本轮没有新增 DATASET', 'train12 / dev3 / test2，覆盖仍薄弱'),
        ('回归与封存', '345通过，0失败/错误/跳过', '旧908份凭据、4个dev/test文件及权重未变')])
    body += '<h2>真实题名与修订记录</h2>'
    for index in (44, 71, 82, 97):
        receipt = added[index]
        annotation = receipt['annotation']
        body += '<p class="title">' + highlight(receipt['reference']['text'], annotation['entities']) + '</p>'
        body += '<p>' + escaped(annotation['entityReason'] or annotation['relationReason'] or judgments['judgments'][index]['reason']) + '</p>'
    body += '<h2>进度边界</h2><p>1,008是已两轮判断数量，不是全部可训练或已预测论文。20,000篇书目保留；当前图谱包模型预测仍仅138篇。本轮不重训、不重测、不入库。数据库认证只阻塞入库，不阻塞继续标注。</p>'
    body += '<p>来源为 codex_session / unknown_session_model；同会话自复核，不是独立模型审核或人工gold。哈希证明文件一致性，不认证语义真值。</p>'
    output = evidence / '09_annotation_expansion.html'
    output.write_text(page('数据处理继续推进 · 第19轮', body, stamp, [
        f'{new.name}/manifest.json · SHA256 {result["snapshotManifestSha256"]}',
        f'{run.name}/manifest.json · SHA256 {result["runManifestSha256"]}',
        '逐项来源副本与哈希：本目录 sources/ 与 manifest.json；核验：verification_20261007_round19.json']), encoding='utf-8')
    c.write_json(evidence / 'manifest.json', {'kind': 'real_artifact_visualization_not_original_console_ui',
        'generatedAtUTC': stamp, 'screenshotCapturePending': True, 'sourceFilesSha256': bindings,
        'filesSha256': {p.relative_to(evidence).as_posix(): c.file_sha256(p)
                        for p in sorted(evidence.rglob('*')) if p.is_file()}})
    print(json.dumps({'passed': True, 'reviewed': 1008, 'pending': 992, 'ner': 803, 'relationPairs': 714, 'tests': 345}))


if __name__ == '__main__':
    main()
