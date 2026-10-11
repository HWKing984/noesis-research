"""Check all new exports and frozen artifacts; render actual saved evidence."""
import json
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / 'scripts'))
import course_weak as c
from train_course_ner import load_snapshot, verify_files
from prepare_course_weak import verify_dataset
from import_course_ai import assess_readiness, save_training_inputs
from export_course_evidence import page, table, highlight, escaped


def main():
    runs = ROOT / 'kg_datasets/dblp/course_v4_runs'
    run = runs / 'pending_train_20261007_23'
    parent = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_15'
    new = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_16'
    dataset = ROOT / 'kg_datasets/dblp/course_v4_weak'
    output = runs / 'verification_20261007_round23.json'
    evidence = ROOT / 'docs/evidence/20261007_round23'
    assert not output.exists() and not evidence.exists(), 'Preserve sealed evidence.'
    refs = verify_dataset(dataset)
    for p in (parent,new,run): verify_files(p)
    rm = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
    assert rm['parentSnapshotManifestSha256']==c.file_sha256(parent / 'manifest.json')
    assert rm['newSnapshotManifestSha256']==c.file_sha256(new / 'manifest.json')
    original = c.read_jsonl(parent / 'receipts.jsonl')
    added = c.read_jsonl(run / 'review/receipts.jsonl')
    receipts = c.read_jsonl(new / 'receipts.jsonl')
    assert len(original)==1408 and len(added)==200 and receipts==original+added
    assert len({r['reference']['sampleId'] for r in receipts})==1608
    assert all(r['reference']['split']=='train' for r in added)
    _, summary = load_snapshot(dataset,new,include_test=True)  # Binding only, no evaluation.
    combined = assess_readiness(added,refs)
    assert summary['generationReceiptDocuments']==1608 and summary['nerEligibleDocuments']==1238
    assert combined['nerEligibleDocuments']==126 and combined['relationEligibleDocuments']==104
    assert combined['entitySupport']['train']=={'METHOD':194,'TASK':93,'DATASET':0}
    assert combined['relationSupport']['train']=={'USED_FOR':93,'EVALUATED_ON':0,'NO_RELATION':1}
    judgments = json.loads((run / 'review_judgments.json').read_text(encoding='utf-8'))
    verdicts = Counter(j['verdict'] for j in judgments['judgments'])
    assert verdicts=={'confirmed':187,'revised':13}
    assert [j['sampleId'] for j in judgments['judgments']]==[r['reference']['sampleId'] for r in added]
    assert judgments['generationDecisionsSha256']==c.file_sha256(run / 'generation_decisions.json')
    with tempfile.TemporaryDirectory(prefix='course-v4-export-check-') as tmp:
        expected = Path(tmp)
        save_training_inputs(expected,receipts,refs)
        assert len(list(expected.glob('*.jsonl')))==6
        assert all(p.read_bytes()==(new / p.name).read_bytes() for p in expected.glob('*.jsonl'))
    unchanged = {}
    for task in ('ner','relation'):
        for split in ('dev','test'):
            name = f'{task}_inputs_{split}.jsonl'
            assert (parent / name).read_bytes()==(new / name).read_bytes()
            unchanged[name] = c.file_sha256(new / name)
    pairs = {s:len(c.read_jsonl(new / f'relation_inputs_{s}.jsonl')) for s in ('train','dev','test')}
    assert pairs=={'train':733,'dev':162,'test':137}
    lookup = {r['sampleId']:r for r in refs}
    pending = c.read_jsonl(new / 'pending_generation.jsonl')
    assert len(pending)==392 and len({r['sampleId'] for r in pending})==392
    assert {r['sampleId'] for r in pending}==set(lookup)-{r['reference']['sampleId'] for r in receipts}
    assert all(lookup[r['sampleId']]['split']=='train' and r==c.model_payload(lookup[r['sampleId']]) for r in pending)
    frozen = {}
    for name,digest in [('ner','cf30fe489da3eb4aa22c309687e86fc711b9db564586d371e4792be8902ba96d'),
                        ('re','e4010d162f525221de7da30cf4c412892564a1da894d1271a72f1ddfa1893978')]:
        lockpath = ROOT / f'annotations/course_v4/{name}_test_selection_20261006.json'
        assert c.file_sha256(lockpath)==digest
        lock = json.loads(lockpath.read_text(encoding='utf-8'))
        model = ROOT / lock['developmentRun']
        verify_files(model)
        assert c.file_sha256(model / 'manifest.json')==lock['developmentManifestSha256']
        assert c.file_sha256(model / lock['checkpoint'] / 'model.safetensors')==lock['weightsSha256']
        frozen[name] = {'selectionSha256':digest,'weightsSha256':lock['weightsSha256']}
    tests = runs / 'tests_20261007_round23_all.xml'
    counts = {k:sum(int(s.get(k,0)) for s in ET.parse(tests).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
    assert counts=={'tests':345,'failures':0,'errors':0,'skipped':0}
    unresolved = {k:sum(r['annotation'][k]=='unresolved' for r in added) for k in ('entityStatus','relationStatus')}
    stamp = datetime.now(UTC).isoformat()
    report = {'passed':True,'checkedAtUTC':stamp,'summary':summary,'newBatchSummary':combined,
        'snapshotManifestSha256':c.file_sha256(new / 'manifest.json'),'parentManifestSha256':c.file_sha256(parent / 'manifest.json'),
        'runManifestSha256':c.file_sha256(run / 'manifest.json'),'verdicts':dict(verdicts),'newUnresolved':unresolved,
        'relationPairs':pairs,'frozenModels':frozen,'tests':counts,'devTestByteIdentical':unchanged,
        'oldReceiptsUnchanged':True,'allExportRowsMatchReceipts':True,'pendingOnlyTrain':True,
        'trainingExecuted':False,'modelInferenceExecuted':False,'databaseWriteExecuted':False,'humanGold':False,'independentReviewer':False}
    c.write_json(output,report)
    evidence.mkdir(parents=True)
    sources = [new / 'summary.json',new / 'manifest.json',tests,output,Path(__file__),
        ROOT / 'scripts/export_course_evidence.py',ROOT / 'scripts/capture_course_evidence.ps1']
    sources += [run / f for f in ('manifest.json','generation_decisions.json','review/receipts.jsonl','review_judgments.json','authored_generation.py','authored_review.py')]
    bindings = {}
    for source in sources:
        destination = evidence / 'sources' / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination)
        bindings[source.relative_to(ROOT).as_posix()] = c.file_sha256(source)
    body = '<h2>200篇训练侧：首轮AI判断 → 同会话自复核 → 隔离 → 新16快照</h2>'
    body += table(['项目','本次新增','累计 / 边界'],[
        ('两轮AI判断','200篇；187确认 / 13修订','1,608 / 2,000篇；392篇train待首轮'),
        ('NER可用','126篇；74篇隔离','1,238篇（train927 / dev167 / test144）'),
        ('RE完整可用','104篇；94个实体对','1,110篇 / 1,032对（733 / 162 / 137）'),
        ('新类别支持','METHOD194 / TASK93 / USED_FOR93 / NO_RELATION1','DATASET / EVALUATED_ON均未新增'),
        ('未决 / 并列',f'实体未决{unresolved["entityStatus"]} / 关系未决{unresolved["relationStatus"]} / 并列3篇','未决不当负例；模型/资源角色不强判'),
        ('工程核验','345回归通过；0失败 / 错误 / 跳过','旧1,408份凭据、4份dev/test和冻结权重未变')])
    body += '<h2>实际自复核与角色案例</h2>'
    for index in (8,35,112,130):
        r = added[index]; a = r['annotation']
        judgment = judgments['judgments'][index]
        body += '<p class="title">'+highlight(r['reference']['text'],a['entities'])+'</p><p>'
        body += escaped(judgment['reason'])+'</p>'
    body += '<h2>来源与限制</h2><p>来源codex_session / unknown_session_model；同会话候选可见AI自复核，不是独立模型审核、人工gold或深度学习模型预测。本次未训练、未推理、未重跑最终test、未入库。训练新增标签不会自动成为旧模型输出。</p>'
    body += '<p>20,000篇书目仍保留；现有图谱包预测仍仅138篇。稀有DATASET/EVALUATED_ON没有改善；CARLA-v2资源候选未进训练。认证只影响Neo4j入库，不影响继续392篇数据处理。哈希检测漂移，不保证语义正确。</p>'
    (evidence / '09_annotation_expansion.html').write_text(page('数据扩展 · 第23轮',body,stamp,[
        f'{new.name}/manifest.json · SHA256 {report["snapshotManifestSha256"]}',
        '逐项核验：verification_20261007_round23.json；逐篇判断/复核与来源副本：sources/ 和 manifest.json']),encoding='utf-8')
    c.write_json(evidence / 'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui','generatedAtUTC':stamp,
        'screenshotCapturePending':True,'sourceFilesSha256':bindings,
        'filesSha256':{p.relative_to(evidence).as_posix():c.file_sha256(p) for p in sorted(evidence.rglob('*')) if p.is_file()}})
    print(json.dumps({'passed':True,'reviewed':1608,'pending':392,'ner':1238,'relationPairs':1032,'unresolved':unresolved,'tests':counts}))


if __name__=='__main__':
    main()
