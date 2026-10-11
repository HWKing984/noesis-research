"""Check frozen corpus coverage, cached parity, graph endpoints and saved evidence."""
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / 'scripts'))
import course_weak as c
import course_graph as graph
import infer_course_corpus as production
import train_course_relation as relation
from train_course_ner import verify_files
from evaluate_course_relation import candidate_rows
from export_course_evidence import page,table,highlight,escaped


def main():
    runs = ROOT / 'kg_datasets/dblp/course_v4_runs'
    run = runs / 'corpus_production_20261007_25'
    pilot = runs / 'corpus_pilot_20261007_25'
    bundle = ROOT / 'kg_datasets/dblp/course_v4_graph_production_20261007_25'
    output = runs / 'verification_20261007_round25.json'
    evidence = ROOT / 'docs/evidence/20261007_round25'
    assert not output.exists() and not evidence.exists(), 'Preserve checks/evidence.'
    for folder in (pilot,run,runs / 'graph_export_sources_20261007_25'): verify_files(folder)
    artifacts = graph.verify_bundle(bundle)
    m = artifacts['manifest']
    source = production.read(run / 'manifest.json')
    state = production.read(run / 'status.json')
    assert state['status']=='completed' and state['processed']==20000
    assert not source['trainingExecuted'] and not source['evaluationExecuted'] and not source['databaseWriteExecuted']
    for p,sha in source['inputSha256'].items():
        path = run / Path(p).name if p.startswith('scripts/') else ROOT / p
        assert c.file_sha256(path)==sha,p
    docs,locks,cache_ner,cache_re,_ = production.load_sources()
    actual = c.read_jsonl(run / 'documents.jsonl')
    assert actual==docs and len(docs)==20000
    assert c.read_jsonl(run / 'model_inputs.jsonl')==[{k:d[k] for k in ('sampleId','text','textSha256')} for d in docs]
    nr = c.read_jsonl(run / 'ner_predictions.jsonl')
    rr = c.read_jsonl(run / 'relation_predictions.jsonl')
    rejected_pairs = c.read_jsonl(run / 'rejected_pairs.jsonl')
    assert [r['sampleId'] for r in nr]==[d['sampleId'] for d in docs]
    assert Counter(r['status'] for r in nr)=={'inferred':19855,'cached':144,'rejected':1}
    assert len(rr)==22574 and not rejected_pairs
    expected = {relation.pair_id(p) for d,r in zip(docs,nr) if r['status']!='rejected' for p in candidate_rows(d,r['predictedEntities'])}
    assert len(expected)==len(rr) and expected=={p['pairId'] for p in rr}
    for r in nr:
        if r['status']=='cached': assert r['predictedEntities']==cache_ner[r['sampleId']]
    for r in rr:
        if r['inferenceSource']=='cached':
            assert {k:v for k,v in r.items() if k not in ('inferenceSource','cacheManifestSha256')}==cache_re[r['pairId']]
    assert sum(r['inferenceSource']=='cached' for r in rr)==148
    chunks = run / 'chunks'
    for suffix,records in (('ner',nr),('re',rr),('re_rejected',rejected_pairs)):
        paths = sorted(chunks.glob(f'*_{suffix}.jsonl'))
        assert len(paths)==79
        assert [r for p in paths for r in c.read_jsonl(p)]==records
    pn = c.read_jsonl(pilot / 'ner_predictions.jsonl')
    pr = c.read_jsonl(pilot / 'relation_predictions.jsonl')
    first_ids = {r['sampleId'] for r in pn}
    assert [r['predictedEntities'] for r in nr[:64]]==[r['predictedEntities'] for r in pn]
    assert {r['pairId']:r['label'] for r in rr if r['sampleId'] in first_ids}=={r['pairId']:r['label'] for r in pr}
    summary = production.read(run / 'summary.json')
    assert summary['entitySupport']==dict(Counter(e['label'] for r in nr for e in r['predictedEntities']))
    assert summary['relationSupport']==dict(Counter(r['label'] for r in rr))
    assert summary['invalidBIOTransitions']==sum(r['invalidTransitions'] or 0 for r in nr)==13145
    assert m['modelSourceManifestSha256']==c.file_sha256(run / 'manifest.json')
    assert m['scope']['modelTitles']==19999 and m['scope']['processedModelTitles']==20000
    assert not m['scope']['modelAppliedToFullCorpus'] and m['scope']['rejectedNERTitles']==1
    assert not m['liveDatabaseImported'] and m['scope']['negativeDecisionsExcluded']==1077
    assert m['exporterCodeSha256']==c.file_sha256(runs / 'graph_export_sources_20261007_25/course_graph.py')
    nodes,edges = artifacts['nodes'],artifacts['edges']
    mention_nodes = {n['id']:n for n in nodes if n['kind']=='Mention'}
    assertions = [n for n in nodes if n['kind']=='Assertion']
    publications = {n['props']['publicationId']:n for n in nodes if n['kind']=='Publication'}
    allowed = Counter(r['label'] for r in rr if r['label']!='NO_RELATION')
    assert len(mention_nodes)==44904 and len(assertions)==21497
    assert Counter(n['props']['predicate'] for n in assertions)==allowed
    for n in list(mention_nodes.values())+assertions:
        props=n['props']
        assert props['source']=='model_prediction' and props['status']=='candidate'
        assert props['NERWeightsSha256']==locks['ner']['weightsSha256']
        assert props['sourceRunManifestSha256']==m['modelSourceManifestSha256']
        if n['kind']=='Assertion':
            assert props['REWeightsSha256']==locks['re']['weightsSha256'] and props['confidenceCalibrated'] is False
    by_assertion = {n['id']:[] for n in assertions}
    for e in edges:
        if e['head'] in by_assertion: by_assertion[e['head']].append(e)
    assert all(Counter(e['kind'] for e in es)=={'HAS_HEAD':1,'HAS_TAIL':1,'SUPPORTED_BY':1} for es in by_assertion.values())
    rejected = [d|r for d,r in zip(docs,nr) if r['status']=='rejected']
    assert len(rejected)==1 and rejected[0]['tokens']==199
    rejected_publication = publications[rejected[0]['publicationId']]['props']
    assert rejected_publication['modelApplied'] is False and rejected_publication['modelApplicationStatus']=='rejected'
    # Explicitly known counts, no candidate-confidence threshold or accuracy gate added.
    tests = runs / 'tests_20261007_round25_final.xml'
    counts = {k:sum(int(s.get(k,0)) for s in ET.parse(tests).getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
    assert counts=={'tests':350,'failures':0,'errors':0,'skipped':0}
    labels = ROOT / 'kg_datasets/dblp/course_v4_training_inputs_17'
    verify_files(labels)
    assert c.file_sha256(labels / 'manifest.json')=='44b4cded1460294e23d7b6d53303ddace56296fb1c0f2eacff4d009c667df9ef'
    frozen = {k:{'selectionSha256':production.LOCK_SHA[k],'weightsSha256':v['weightsSha256']} for k,v in locks.items()}
    old_graph = ROOT / 'kg_datasets/dblp/course_v4_graph_20261007_18_final'
    verify_files(old_graph)
    assert c.file_sha256(old_graph / 'manifest.json')=='da86ef12159470ce99d8392e5a4d5f688ea1232a84ef433ab5b58e3c062186a7'
    case_path = ROOT / 'annotations/course_v4/production_pilot_cases_20261007_round25.json'
    cases = production.read(case_path)
    by_sid = {d['sampleId']:d for d in docs}
    assert all(by_sid[x['sampleId']]['text']==x['title'] for x in cases['cases'])
    assert cases['modelOutputsChanged'] is False
    stamp = datetime.now(UTC).isoformat()
    report = {'passed':True,'checkedAtUTC':stamp,'productionSummary':summary,'graphCounts':m['counts'],'graphId':m['graphId'],
        'productionManifestSha256':c.file_sha256(run / 'manifest.json'),'graphManifestSha256':c.file_sha256(bundle / 'manifest.json'),
        'allInputsTitleOnly':True,'allCanonicalIDsCovered':True,'allPairsCovered':True,'chunkArtifactsMatchFinal':True,
        'pilotLabelsMatchFullRun':True,'cachedNEREntitiesByteLogicalIdentical':144,'cachedREPredictionsLogicalIdentical':148,
        'invalidBIOAffectedNewDocuments':sum(bool(r['invalidTransitions']) for r in nr),'invalidBIOCachedUnknownDocuments':144,
        'zeroEntitySuccessfulDocuments':sum(not r['predictedEntities'] for r in nr if r['status']!='rejected'),
        'rejectedDocuments':rejected,'frozenModels':frozen,'tests':counts,'labelSnapshotUnchanged':True,'oldGraphPreserved':True,
        'trainingExecuted':False,'newEvaluationExecuted':False,'liveDatabaseImported':False,'qualityPromotionPassed':False,
        'qualitativeCaseReviewSha256':c.file_sha256(case_path),'humanGold':False,'independentReviewer':False}
    c.write_json(output,report)
    evidence.mkdir(parents=True)
    sources = [run / 'manifest.json',run / 'summary.json',run / 'status.json',run / 'runtime.json',
        pilot / 'summary.json',bundle / 'manifest.json',output,tests,case_path,Path(__file__),
        runs / 'graph_export_sources_20261007_25/course_graph.py',runs / 'graph_export_20261007_25_initial_path_failure.json',
        ROOT / 'scripts/infer_course_corpus.py',ROOT / 'scripts/export_course_evidence.py',ROOT / 'scripts/capture_course_evidence.ps1']
    sources += [run / n for n in ('infer_course_corpus.py','ner_predictions.jsonl','relation_predictions.jsonl')]
    bindings = {}
    for source_path in sources:
        destination=evidence / 'sources' / source_path.relative_to(ROOT)
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source_path,destination)
        bindings[source_path.relative_to(ROOT).as_posix()]=c.file_sha256(source_path)
    body = '<h2>20,000篇已处理，19,999篇成功抽取，1篇超长隔离</h2>'
    body += table(['口径','实际结果','边界'],[
        ('NER题名','19,855新推理 / 144缓存 / 1拒绝','199 tokens超过冻结128，不截断；处理完不等于全成功'),
        ('实体提及','44,904（METHOD26,694 / TASK17,904 / DATASET306）','预测候选，不是新增gold或真实性认证'),
        ('关系判断','22,574（新22,426 / 缓存148）','USED_FOR21,318 / EVALUATED_ON179 / NO_RELATION1,077'),
        ('可追溯图谱包','192,185节点 / 263,059关系；候选断言21,497','1,077个模型负判断不生成断言；未真实入库'),
        ('计算留痕',f'RTX4060 CUDA；{summary["elapsedSeconds"]:.2f}秒；79个分块','旧NER/RE权重及已保存测试预测不变；无新评分'),
        ('工程核验','350回归通过；小批/全量标签一致','输入无labels；ID/跨度/头尾/证据/哈希绑定'),
        ('质量局限','新推理13,145次非法BIO转移，影响4,014篇','严格解码拒绝孤立I，不自动修补；旧144篇逐篇计数未知')])
    body += '<h2>真实预测：合理关联与误判均保留</h2>'
    predicted_by_sid = {r['sampleId']:r for r in nr}
    for case in (cases['cases'][1],cases['cases'][3],cases['cases'][0]):
        body += '<p class="title">'+highlight(case['title'],predicted_by_sid[case['sampleId']]['predictedEntities'])+'</p><p>'+escaped(case['reason'])+'</p>'
    body += '<h2>隔离与未完成事项</h2><p>超长书评题名 journals/idt/Tsihrintzis25a 199 tokens，书目节点保留并标modelApplied=false，未伪装全O成功。固定题名规则候选中仍可能有书评/通知，不宣称全部为原创AI研究论文。</p>'
    body += '<p>四例为同会话AI定性检查，不是随机精度评估；硬件当方法、输入当任务等错误未隐藏或手工改成模型结果。21,497条断言未获可靠性晋级，置信度未校准。实验四仍需有效Neo4j认证、真实导入、幂等/计数核验、节点图与成功查询截图。</p>'
    body += '<h2>MLE版本边界</h2><p>本轮只扩大生产抽取，不重训、不调阈值、不改AI标注、不重跑最终测试成绩。旧144份NER和148条RE预测原样复用，其余为无标签生产推理。执行代码副本与后续契约守卫加固分开绑定；封存产物不随当前源码修改。</p>'
    (evidence / '09_annotation_expansion.html').write_text(page('冻结模型生产抽取 · 第25轮',body,stamp,[
        f'corpus_production_20261007_25/manifest.json · SHA256 {report["productionManifestSha256"]}',
        f'course_v4_graph_production_20261007_25/manifest.json · SHA256 {report["graphManifestSha256"]}',
        'verification_20261007_round25.json / tests_20261007_round25_final.xml；原始预测、实际执行源码和失败原因见 sources/']),encoding='utf-8')
    c.write_json(evidence / 'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui','generatedAtUTC':stamp,
        'screenshotCapturePending':True,'sourceFilesSha256':bindings,
        'filesSha256':{p.relative_to(evidence).as_posix():c.file_sha256(p) for p in sorted(evidence.rglob('*')) if p.is_file()}})
    print(json.dumps({'passed':True,'documents':20000,'successful':19999,'rejected':1,'mentions':44904,
        'assertions':21497,'nodes':sum(m['counts']['nodes'].values()),'edges':sum(m['counts']['edges'].values()),
        'manifestSha256':report['graphManifestSha256'],'tests':counts},ensure_ascii=False))


if __name__=='__main__': main()
