"""Check queue completion, isolated records, exports and frozen models; render saved evidence."""
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
    run = runs / 'pending_train_20261007_24'
    failed = runs / 'pending_train_20261007_24_initial_compile_failed'
    parent = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_16'
    new = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_17'
    dataset = ROOT / 'kg_datasets/dblp/course_v4_weak'
    output = runs / 'verification_20261007_round24.json'
    excluded_path = runs / 'excluded_training_20261007_round24.jsonl'
    evidence = ROOT / 'docs/evidence/20261007_round24'
    assert not output.exists() and not evidence.exists() and not excluded_path.exists(), 'Preserve evidence.'
    refs = verify_dataset(dataset)
    for p in (parent,new,run): verify_files(p)
    rm = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
    assert rm['parentSnapshotManifestSha256']==c.file_sha256(parent / 'manifest.json')
    assert rm['newSnapshotManifestSha256']==c.file_sha256(new / 'manifest.json')
    original = c.read_jsonl(parent / 'receipts.jsonl')
    added = c.read_jsonl(run / 'review/receipts.jsonl')
    receipts = c.read_jsonl(new / 'receipts.jsonl')
    assert len(original)==1608 and len(added)==392 and receipts==original+added
    ids = {r['reference']['sampleId'] for r in receipts}
    assert len(ids)==2000 and ids=={r['sampleId'] for r in refs}
    assert all(r['reference']['split']=='train' for r in added)
    assert not c.read_jsonl(new / 'pending_generation.jsonl')
    _, summary = load_snapshot(dataset,new,include_test=True)  # Binding only, no inference/evaluation.
    batch = assess_readiness(added,refs)
    assert summary['aiReviewedDocuments']==2000 and summary['pendingGenerationDocuments']==0
    assert summary['nerEligibleSplits']=={'train':1219,'dev':167,'test':144}
    assert summary['relationEligibleSplits']=={'train':1061,'dev':158,'test':138}
    assert batch['nerEligibleDocuments']==292 and batch['relationEligibleDocuments']==247
    assert batch['entitySupport']['train']=={'METHOD':369,'TASK':259,'DATASET':0}
    assert batch['relationSupport']['train']=={'USED_FOR':240,'EVALUATED_ON':0,'NO_RELATION':2}
    judgments = json.loads((run / 'review_judgments.json').read_text(encoding='utf-8'))
    verdicts = Counter(j['verdict'] for j in judgments['judgments'])
    assert verdicts=={'confirmed':379,'revised':13}
    assert [j['sampleId'] for j in judgments['judgments']]==[r['reference']['sampleId'] for r in added]
    assert judgments['generationDecisionsSha256']==c.file_sha256(run / 'generation_decisions.json')
    with tempfile.TemporaryDirectory(prefix='course-v4-export-check-') as tmp:
        expected = Path(tmp)
        save_training_inputs(expected,receipts,refs)
        files = list(expected.glob('*.jsonl'))
        assert len(files)==6 and all(p.read_bytes()==(new / p.name).read_bytes() for p in files)
    unchanged = {}
    for task in ('ner','relation'):
        for split in ('dev','test'):
            name = f'{task}_inputs_{split}.jsonl'
            assert (parent / name).read_bytes()==(new / name).read_bytes()
            unchanged[name] = c.file_sha256(new / name)
    pairs = {s:len(c.read_jsonl(new / f'relation_inputs_{s}.jsonl')) for s in ('train','dev','test')}
    assert pairs=={'train':975,'dev':162,'test':137}
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
    failure = json.loads((failed / 'failure.json').read_text(encoding='utf-8'))
    assert failure['status']=='failed' and failure['index']==235 and not failure['importExecuted']
    assert all(c.file_sha256(failed / n)==v for n,v in failure['filesSha256'].items())
    initial = json.loads((failed / 'generation_decisions.json').read_text(encoding='utf-8'))['decisions']
    first = json.loads((run / 'generation_decisions.json').read_text(encoding='utf-8'))['decisions']
    assert len(initial)==len(first)==392
    assert all(a==b for i,(a,b) in enumerate(zip(initial,first)) if i!=235)
    assert initial[235]['entities'][0]['text']=='Mapping Pre- and Post-Hurricane Mangrove Canopy Heights'
    assert first[235]['entities'][0]['text']=='Mapping of Pre- and Post-Hurricane Mangrove Canopy Heights'
    tests = runs / 'tests_20261007_round24_all.xml'
    counts = {k:sum(int(s.get(k,0)) for s in ET.parse(tests).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
    assert counts=={'tests':345,'failures':0,'errors':0,'skipped':0}
    # Exact structural reasons, no keyword heuristic pretending to resolve semantic labels.
    exclusions = {s:Counter() for s in ('train','dev','test')}
    eligible_empty = {s:Counter() for s in exclusions}
    excluded = []
    for r in receipts:
        a,ref = r['annotation'],r['reference']
        tasks = c.eligible_tasks(r,ref)
        split = ref['split']
        category = ('group_challenge' if a['groupMentions'] else
                    'entity_unresolved' if a['entityStatus']=='unresolved' else
                    'relation_unresolved' if a['relationStatus']=='unresolved' else 'eligible')
        exclusions[split][category] += 1
        if tasks['ner'] and not a['entities']: eligible_empty[split]['nerNoEntities'] += 1
        if tasks['relation'] and not a['relations']: eligible_empty[split]['reNoPairs'] += 1
        if split=='train' and not tasks['relation']:
            excluded.append({'sampleId':ref['sampleId'],'text':ref['text'],'textSha256':ref['textSha256'],
                'annotationSha256':r['contentSha256'],'groupId':ref['groupId'],'eligibleTasks':tasks,
                'exclusionCategory':category,'entityReason':a['entityReason'],'relationReason':a['relationReason'],
                'groupMentions':a['groupMentions'],'labelSource':'ai_pseudo','status':'processed_isolated_not_pending'})
    assert len(excluded)==539 and sum(not r['eligibleTasks']['ner'] for r in excluded)==381
    c.write_jsonl(excluded_path,excluded)
    unresolved = {k:sum(r['annotation'][k]=='unresolved' for r in added) for k in ('entityStatus','relationStatus')}
    stamp = datetime.now(UTC).isoformat()
    report = {'passed':True,'checkedAtUTC':stamp,'summary':summary,'newBatchSummary':batch,
        'snapshotManifestSha256':c.file_sha256(new / 'manifest.json'),'parentManifestSha256':c.file_sha256(parent / 'manifest.json'),
        'runManifestSha256':c.file_sha256(run / 'manifest.json'),'verdicts':dict(verdicts),'newUnresolved':unresolved,
        'relationPairs':pairs,'frozenModels':frozen,'tests':counts,'devTestByteIdentical':unchanged,
        'exclusionCategoriesBySplit':{s:dict(v) for s,v in exclusions.items()},
        'eligibleEmptyBySplit':{s:dict(v) for s,v in eligible_empty.items()},
        'excludedTrainingSha256':c.file_sha256(excluded_path),'excludedTrainingDocuments':len(excluded),
        'compileFailurePreservedSha256':c.file_sha256(failed / 'failure.json'),
        'oldReceiptsUnchanged':True,'allExportRowsMatchReceipts':True,'firstQueueComplete':True,
        'trainingExecuted':False,'modelInferenceExecuted':False,'databaseWriteExecuted':False,'humanGold':False,'independentReviewer':False}
    c.write_json(output,report)
    evidence.mkdir(parents=True)
    sources = [new / 'summary.json',new / 'manifest.json',tests,output,excluded_path,Path(__file__),
        ROOT / 'scripts/export_course_evidence.py',ROOT / 'scripts/capture_course_evidence.ps1']
    sources += [run / f for f in ('manifest.json','generation_decisions.json','review/receipts.jsonl','review_judgments.json','authored_generation.py','authored_review.py')]
    sources += [failed / f for f in ('failure.json','authored_generation.py','generation_decisions.json')]
    bindings = {}
    for source in sources:
        destination = evidence / 'sources' / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination)
        bindings[source.relative_to(ROOT).as_posix()] = c.file_sha256(source)
    body = '<h2>首批2,000篇队列完成：未决已隔离，不是全可训练</h2>'
    body += table(['口径','本轮392篇','累计新17快照'],[
        ('两轮AI判断','379确认 / 13修订','2,000 / 2,000；待首轮0；train1600 / dev200 / test200'),
        ('NER可用','292篇；100篇隔离','1,530篇（1219 / 167 / 144）；470篇隔离'),
        ('RE完整可用','247篇；242对','1,357篇；1,274对（975 / 162 / 137）'),
        ('新增类别','METHOD369 / TASK259；USED_FOR240 / NO_RELATION2','DATASET12 / EVALUATED_ON3（train）；本轮均未新增'),
        ('本轮未决/挑战','实体未决96；关系未决141；并列5篇','全队列并列挑战21篇；不凑标签'),
        ('训练隔离清单','保留具体理由和跨度','539篇RE隔离，其中381篇也NER隔离，158篇仅NER可用'),
        ('工程核验','345回归通过；6份导出重建一致','旧1608凭据、4份dev/test、选择锁及权重不变')])
    body += '<h2>自复核：边界和执行角色</h2>'
    for index in (39,150,351):
        r = added[index]
        body += '<p class="title">'+highlight(r['reference']['text'],r['annotation']['entities'])+'</p><p>'+escaped(judgments['judgments'][index]['reason'])+'</p>'
    body += '<h2>真实失败 → 修正 → 新成功版本</h2><p>首次编译第235篇任务漏写原文介词 of，校验拒绝；失败源码、原答案和failure.json另存，不删除或覆盖。修正为 Mapping of 后392篇通过，首次失败没有导入或训练。失败不是13项语义自复核之一。</p>'
    body += '<h2>来源与剩余工作</h2><p>codex_session / unknown_session_model；同会话候选可见AI自复核，不是独立审核、人工gold或训练模型预测。按MLE流程封存版本，未训练、未推理、未重跑最终test、未入库。哈希/回归不认证语义正确。</p>'
    body += '<p>20,000篇书目仍保留，模型抽取图谱仍仅138篇。本轮队列完成不等于全语料生产推理、Neo4j成功入库或课程整体验收；下一步使用冻结模型做生产抽取并保留来源。若训练新模型，须先确定未暴露新holdout，不复用旧最终test调优。</p>'
    (evidence / '09_annotation_expansion.html').write_text(page('首批AI标注完成 · 第24轮',body,stamp,[
        f'{new.name}/manifest.json · SHA256 {report["snapshotManifestSha256"]}',
        'verification_20261007_round24.json / excluded_training_20261007_round24.jsonl / tests_20261007_round24_all.xml',
        '逐篇首轮、自复核、失败记录和副本哈希见 sources/ 与 manifest.json']),encoding='utf-8')
    c.write_json(evidence / 'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui','generatedAtUTC':stamp,
        'screenshotCapturePending':True,'sourceFilesSha256':bindings,
        'filesSha256':{p.relative_to(evidence).as_posix():c.file_sha256(p) for p in sorted(evidence.rglob('*')) if p.is_file()}})
    print(json.dumps({'passed':True,'reviewed':2000,'pending':0,'ner':1530,'relationPairs':1274,
        'exclusionCategoriesBySplit':report['exclusionCategoriesBySplit'],'eligibleEmptyBySplit':report['eligibleEmptyBySplit'],
        'unresolved':unresolved,'snapshotSha256':report['snapshotManifestSha256'],'tests':counts},ensure_ascii=False))


if __name__=='__main__':
    main()
