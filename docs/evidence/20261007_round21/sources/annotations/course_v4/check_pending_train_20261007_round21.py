"""Check both new batches/snapshots and render evidence from real saved results."""
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
from prepare_course_weak import verify_dataset
from import_course_ai import assess_readiness, save_training_inputs
from export_course_evidence import page, table, highlight, escaped


def main():
    dataset = ROOT / 'kg_datasets/dblp/course_v4_weak'
    runs = ROOT / 'kg_datasets/dblp/course_v4_runs'
    snapshots = [ROOT / f'kg_datasets/dblp/course_v4_training_inputs_{i}' for i in ('12','13','14')]
    batches = [runs / f'pending_train_20261007_{i}' for i in (20,21)]
    evidence = ROOT / 'docs/evidence/20261007_round21'
    output = runs / 'verification_20261007_round21.json'
    if evidence.exists() or output.exists():
        raise ValueError('Preserve existing evidence/verification; use a new version.')
    references = verify_dataset(dataset)
    additions, verdicts, batch_results = [], Counter(), []
    for parent,new,run in zip(snapshots,snapshots[1:],batches):
        pm, nm, rm = (verify_files(p) for p in (parent,new,run))
        assert rm['parentSnapshotManifestSha256'] == c.file_sha256(parent / 'manifest.json')
        assert rm['newSnapshotManifestSha256'] == c.file_sha256(new / 'manifest.json')
        added = c.read_jsonl(run / 'review/receipts.jsonl')
        assert len(added) == 100 and all(r['reference']['split'] == 'train' for r in added)
        assert c.read_jsonl(new / 'receipts.jsonl') == c.read_jsonl(parent / 'receipts.jsonl') + added
        _, summary = load_snapshot(dataset,new,include_test=True)  # Binding only; no model evaluation.
        result = assess_readiness(added,references)
        judgments = json.loads((run / 'review_judgments.json').read_text(encoding='utf-8'))
        current = Counter(j['verdict'] for j in judgments['judgments'])
        assert len(judgments['judgments']) == 100 and set(current) <= {'confirmed','revised'}
        assert [j['sampleId'] for j in judgments['judgments']] == [r['reference']['sampleId'] for r in added]
        assert judgments['generationDecisionsSha256'] == c.file_sha256(run / 'generation_decisions.json')
        verdicts.update(current); additions.extend(added)
        batch_results.append({'run':run.name,'summary':result,'verdicts':dict(current),
                              'runManifestSha256':c.file_sha256(run / 'manifest.json')})
        with tempfile.TemporaryDirectory(prefix='course-v4-pair-check-') as temporary:
            expected = Path(temporary)
            save_training_inputs(expected,c.read_jsonl(new / 'receipts.jsonl'),references)
            assert all(p.read_bytes() == (new / p.name).read_bytes() for p in expected.glob('*.jsonl'))
    parent, new = snapshots[0], snapshots[-1]
    combined = assess_readiness(additions,references)
    assert len({r['reference']['sampleId'] for r in additions}) == 200
    assert verdicts == {'confirmed':191,'revised':9}
    assert summary['generationReceiptDocuments'] == 1208 and summary['nerEligibleDocuments'] == 956
    assert combined['nerEligibleDocuments'] == 153 and combined['relationEligibleDocuments'] == 133
    assert combined['relationSupport']['train'] == {'USED_FOR':120,'EVALUATED_ON':0,'NO_RELATION':3}
    unchanged = {}
    for task in ('ner','relation'):
        for split in ('dev','test'):
            name = f'{task}_inputs_{split}.jsonl'
            assert (parent / name).read_bytes() == (new / name).read_bytes()
            unchanged[name] = c.file_sha256(new / name)
    pairs = {s:len(c.read_jsonl(new / f'relation_inputs_{s}.jsonl')) for s in ('train','dev','test')}
    assert pairs == {'train':538,'dev':162,'test':137}
    lookup = {r['sampleId']:r for r in references}
    seen = {r['reference']['sampleId'] for r in c.read_jsonl(new / 'receipts.jsonl')}
    pending = c.read_jsonl(new / 'pending_generation.jsonl')
    assert len(pending) == 792 and len({r['sampleId'] for r in pending}) == 792
    assert {r['sampleId'] for r in pending} == set(lookup) - seen
    assert all(set(r)=={'sampleId','text','textSha256'} and lookup[r['sampleId']]['split']=='train' and r==c.model_payload(lookup[r['sampleId']]) for r in pending)
    frozen = {}
    for name,digest in [('ner','cf30fe489da3eb4aa22c309687e86fc711b9db564586d371e4792be8902ba96d'),
                        ('re','e4010d162f525221de7da30cf4c412892564a1da894d1271a72f1ddfa1893978')]:
        path = ROOT / f'annotations/course_v4/{name}_test_selection_20261006.json'
        assert c.file_sha256(path) == digest
        lock = json.loads(path.read_text(encoding='utf-8'))
        model = ROOT / lock['developmentRun']
        verify_files(model)
        assert c.file_sha256(model / 'manifest.json') == lock['developmentManifestSha256']
        assert c.file_sha256(model / lock['checkpoint'] / 'model.safetensors') == lock['weightsSha256']
        frozen[name] = {'selectionSha256':digest,'weightsSha256':lock['weightsSha256']}
    tests = runs / 'tests_20261007_round20_all.xml'
    counts = {k:sum(int(s.get(k,0)) for s in ET.parse(tests).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
    assert counts == {'tests':345,'failures':0,'errors':0,'skipped':0}
    unresolved = {k:sum(r['annotation'][k]=='unresolved' for r in additions) for k in ('entityStatus','relationStatus')}
    stamp = datetime.now(UTC).isoformat()
    report = {'passed':True,'checkedAtUTC':stamp,'summary':summary,'newBatchSummary':combined,'batches':batch_results,
        'snapshotManifestSha256':c.file_sha256(new / 'manifest.json'),'parentManifestSha256':c.file_sha256(parent / 'manifest.json'),
        'relationPairs':pairs,'verdicts':dict(verdicts),'newUnresolved':unresolved,'frozenModels':frozen,'tests':counts,
        'oldReceiptsUnchanged':True,'devTestByteIdentical':unchanged,'allExportRowsMatchReceipts':True,'pendingOnlyTrain':True,
        'trainingExecuted':False,'modelInferenceExecuted':False,'databaseWriteExecuted':False,'humanGold':False,'independentReviewer':False}
    c.write_json(output,report)
    evidence.mkdir(parents=True)
    sources = [new / 'summary.json',new / 'manifest.json',tests,output,Path(__file__),
               ROOT / 'scripts/export_course_evidence.py',ROOT / 'scripts/capture_course_evidence.ps1']
    sources += [run / file for run in batches for file in ('manifest.json','review/receipts.jsonl','review_judgments.json')]
    bindings = {}
    for source in sources:
        destination = evidence / 'sources' / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination)
        bindings[source.relative_to(ROOT).as_posix()] = c.file_sha256(source)
    body = '<h2>训练侧200篇：两批首轮 → 同会话自复核 → 隔离 → 快照13/14</h2>'
    body += table(['项目','本次新增','累计 / 边界'],[
        ('两轮AI判断','200篇；191确认 / 9修订','1,208 / 2,000篇；792篇待首轮'),
        ('NER可用','153篇；47篇隔离','956篇（train645 / dev167 / test144）'),
        ('RE完整可用','133篇；123个实体对','873篇 / 837对（538 / 162 / 137）'),
        ('新类别支持','METHOD189 / TASK131 / USED_FOR120 / NO_RELATION3','DATASET / EVALUATED_ON均未新增'),
        ('未决 / 并列',f'实体未决{unresolved["entityStatus"]} / 关系未决{unresolved["relationStatus"]} / 并列3篇','未决不当负例；共享中心词不补造'),
        ('工程核验','345回归通过；0失败 / 错误 / 跳过','旧1,008份凭据、4份dev/test和冻结权重未变')])
    body += '<h2>实际自复核及角色案例</h2>'
    for index in (19,71,132,142):
        receipt = additions[index]; annotation = receipt['annotation']
        body += '<p class="title">' + highlight(receipt['reference']['text'],annotation['entities']) + '</p>'
        body += '<p>' + escaped(annotation['entityReason'] or annotation['relationReason'] or annotation['relations'][0]['reason']) + '</p>'
    body += '<h2>来源与限制</h2><p>所有新增记录仅train；来源codex_session / unknown_session_model，同会话候选可见自复核，不是人工gold或独立模型审核。本次不重训、不重新测试、不入库。标题中的更正通知/综述不作为新的实验验证，器件Transformer不改成神经网络，普通资源不凑DATASET。</p>'
    body += '<p>20,000篇书目仍保留；现有图谱包模型预测仍仅138篇，新增伪标签不自动成为模型抽取结果。认证问题只阻塞Neo4j入库，不阻塞继续数据处理。哈希用于检测漂移，不证明语义正确。</p>'
    (evidence / '09_annotation_expansion.html').write_text(page('数据扩展 · 第20–21轮',body,stamp,[
        f'{new.name}/manifest.json · SHA256 {report["snapshotManifestSha256"]}',
        '逐项核验：verification_20261007_round21.json；逐篇判断、复核和来源副本：sources/ 与 manifest.json']),encoding='utf-8')
    c.write_json(evidence / 'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui','generatedAtUTC':stamp,
        'screenshotCapturePending':True,'sourceFilesSha256':bindings,
        'filesSha256':{p.relative_to(evidence).as_posix():c.file_sha256(p) for p in sorted(evidence.rglob('*')) if p.is_file()}})
    print(json.dumps({'passed':True,'reviewed':1208,'pending':792,'ner':956,'relationPairs':837,'unresolved':unresolved,'tests':345}))


if __name__ == '__main__':
    main()
