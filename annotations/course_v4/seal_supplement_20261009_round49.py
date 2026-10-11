"""Recompute source/receipt/BIO counts and capture truthful supplementary-dev evidence."""
import argparse
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import UTC,datetime
from pathlib import Path
from urllib.robotparser import RobotFileParser

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'scripts'))
import prepare_supplementary_dev as p
from export_course_evidence import page,table

RUNS=ROOT/'kg_datasets/dblp/course_v4_runs'
SOURCE=ROOT/'kg_datasets/dblp/course_abstract_supplement_sources_20261008_49_runtime'
GENERATED=ROOT/'kg_datasets/dblp/course_abstract_supplement_generated_20261009_49'
REVIEWED=ROOT/'kg_datasets/dblp/course_abstract_supplement_reviewed_20261009_49'
EVIDENCE=ROOT/'docs/evidence/20261009_round49'
REGRESSION=RUNS/'tests_20261009_round49_complete.xml'


def checked():
    p.locked()
    for folder in (SOURCE,GENERATED,REVIEWED):
        manifest=p.g.verified_files(folder)
        if any(p.c.file_sha256(ROOT/name)!=sha for name,sha in manifest['inputSha256'].items()): raise ValueError('Source/annotation input drift')
    refs=p.c.read_jsonl(REVIEWED/'references.jsonl'); receipts=p.c.read_jsonl(REVIEWED/'reviewed_receipts.jsonl'); initial=p.c.read_jsonl(GENERATED/'generation_receipts.jsonl')
    if len(refs)!=8 or refs!=p.c.read_jsonl(SOURCE/'references.jsonl') or len(receipts)!=8 or len(initial)!=8 or any(p.c.validate_receipt(a,r) or a['review'] is None or a['initialAnnotation']!=old['annotation'] for r,a,old in zip(refs,receipts,initial)): raise ValueError('Fresh source/review chain invalid')
    requests=p.read(SOURCE/'requests.json'); times=[datetime.fromisoformat(r['startedAtUTC']) for r in requests]
    robots=RobotFileParser(); robots.parse((SOURCE/'robots.txt').read_text(encoding='utf-8').splitlines()); required=robots.crawl_delay(p.transport.AGENT)
    gaps=[(b-a).total_seconds() for a,b in zip(times,times[1:])]; policy=p.read(SOURCE/'policy.json')
    # UTC receipts cannot prove the collector's monotonic 15.1-second scheduling margin.
    if required!=15 or policy['crawlDelaySeconds']!=15.1 or policy['robotsSha256']!=p.c.file_sha256(SOURCE/'robots.txt') or len(requests)!=8 or any(r['status']!='completed' or not r['titleMatch'] or r['tokens']>512 or not robots.can_fetch(p.transport.AGENT,r['url']) for r in requests) or any(gap<required for gap in gaps): raise ValueError('Collection status/robots delay/truncation drift')
    for ref,request in zip(refs,requests):
        raw=(SOURCE/request['rawResponseFile']).read_bytes(); title,text=p.parse_page(raw,request)
        if p.c.file_sha256(SOURCE/request['rawResponseFile'])!=request['rawResponseSha256'] or text!=ref['text'] or title!=ref['referenceTitle']: raise ValueError('Raw citation metadata differs')
    rows,pairs,full,excluded,unknown,total=p.rows_for(refs,receipts)
    for name,values in [('ner_dev',rows),('relation_dev',pairs),('full_relation_dev',full),('excluded_ner',excluded)]:
        if p.c.read_jsonl(REVIEWED/(name+'.jsonl'))!=values: raise ValueError('Serialized label rows differ')
    alignment=p.c.read_jsonl(REVIEWED/'token_alignment.jsonl')
    if len(alignment)!=len(rows): raise ValueError('Missing BIO alignment rows')
    for row,a in zip(rows,alignment):
        if row['sampleId']!=a['sampleId'] or len(a['offsets'])>512 or p.c.align_bio(a['offsets'],row['entities'],row['text'])!=a['labels']: raise ValueError('Token/BIO binding differs')
        decoded=p.ner.decode_bio([0 if tuple(o)==(0,0) else t for t,o in zip(a['labels'],a['offsets'])],a['offsets'],row['text'])
        if decoded['invalidTransitions'] or decoded['entities']!=[{k:e[k] for k in ('start','end','text','label')} for e in row['entities']]: raise ValueError('BIO reconstruction differs')
    summary=p.read(REVIEWED/'summary.json'); evals=[r for r in pairs if r['label']=='EVALUATED_ON']
    if (len(rows),len(pairs),len(full),len(excluded),unknown,total,len(evals),len({r['sampleId'] for r in evals}))!=(7,88,0,1,390,478,14,3) or summary['trainingExecuted'] or summary['inferenceExecuted'] or summary['testEvaluated'] or summary['modelPromoted']: raise ValueError('Supplement count/execution drift')
    junit=ET.parse(REGRESSION).getroot().find('testsuite').attrib
    if (junit['tests'],junit['failures'],junit['errors'],junit['skipped'])!=('378','0','0','0'): raise ValueError('Regression failed/incomplete')
    return {'collectionManifestSha256':p.c.file_sha256(SOURCE/'manifest.json'),'reviewedManifestSha256':p.c.file_sha256(REVIEWED/'manifest.json'),'engineeringTests':378,'regressionSeconds':float(junit['time']),'collectionTiming':{'configuredMonotonicSeconds':15.1,'robotsRequiredSeconds':required,'recordedUTCGapsSeconds':gaps,'minimumRecordedUTCSeconds':min(gaps),'allRecordedUTCAtLeastConfigured':all(gap>=15.1 for gap in gaps),'robotsMinimumSatisfied':True},'NER':7,'quarantinedNER':1,'knownPairs':88,'unknownPairs':390,'eligiblePairs':478,'EVALUATED_ON':14,'EVALSourcePapers':3,'completeDocuments':0,'completeEVALSupport':0,'trainingExecuted':False,'inferenceExecuted':False,'testEvaluated':False,'modelPromoted':False},refs,receipts


def main(action):
    audit,refs,receipts=checked()
    if action=='prepare':
        if EVIDENCE.exists(): raise FileExistsError('Preserve source evidence')
        EVIDENCE.mkdir(parents=True); paths=[Path(__file__),p.CONTRACT,ROOT/'annotations/course_v4/annotate_supplement_20261009_round49.py',ROOT/'annotations/course_v4/abstract_supplement_decisions_20261009_49.json',ROOT/'annotations/course_v4/abstract_supplement_reviews_20261009_49.json',REGRESSION,ROOT/'scripts/capture_course_evidence.ps1',ROOT/'scripts/export_course_evidence.py',ROOT/'kg_datasets/dblp/course_abstract_supplement_sources_20261008_49/failure.json',RUNS/'tests_20261008_round49_targeted.xml',RUNS/'round49_evidence_preparation_failure.json']
        for folder in (SOURCE,GENERATED,REVIEWED): paths.extend(folder/name for name in ('manifest.json','summary.json'))
        for path in paths:
            target=EVIDENCE/'sources'/path.relative_to(ROOT); target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,target)
        p.c.write_json(EVIDENCE/'audit_state.json',audit); stamp=datetime.now(UTC).isoformat()
        rows=[]
        for ref,receipt in zip(refs,receipts):
            annotation=receipt['annotation']; relations=annotation['relations']; rows.append([ref['arxivId'],annotation['entityStatus'],len(annotation['entities']),sum(r['label']=='EVALUATED_ON' for r in relations),sum(r['label']=='UNRESOLVED' for r in relations),annotation['relationStatus']])
        body='<p>固定8篇补充开发来源，官方HTML原文、身份元数据重叠拒绝、串行采集。限速配置15.1秒；UTC记录最短15.092014秒，均满足保存robots的15秒要求，但UTC记录不能证明每次达到配置裕量。实际AI初标及同会话复核，不是独立人工金标准；不扩大生产图或改旧dev/test。</p>'+table(['论文ID','NER状态','提及数','明确EVAL','未决对','关系状态'],rows)
        body+='<h2>实际数据产物</h2><p>8采集成功，7篇NER通过/1篇共享词头隔离，109参考实体（METHOD55/TASK39/DATASET15）。明确88对：用途70/评测14/角色负例4；合格NER中的390/478对未决，未填负例。14条EVAL来自3论文，其中9条来自同一DeBERTa摘要，不是14次独立实验。</p><h2>停止质量晋级</h2><p>补充切片完整关系文档0/8、完整EVAL支持0；旧开发仍7/19、完整EVAL0。不能用部分标签证明整体关系正确率，不能缩小分母追分。暂缓新训练和替换，下一阶段转向现有候选检索系统终验。</p>'
        body+=table(['工程检查','结果'],[['严格BIO','7篇原文/跨度/标签逐项重放通过'],['回归',f'378通过；JUnit {audit["regressionSeconds"]:.3f}秒；D隔离tmp'],['失败留痕','初次环境缺分词器，请求前停止；原失败保留。首次证据审核误把UTC与单调计时15.1秒等同，改为核验真实robots底线并公开全部间隔，原始采集记录未改'],['本轮没有','新模型训练、推理、最终测试、图谱写入或质量晋级']])
        (EVIDENCE/'09_annotation_expansion.html').write_text(page('补充开发标注与完整性缺口 · 第49轮',body,stamp,[]),encoding='utf-8')
        body='<p>同会话AI参考，不是独立gold。正文没有RoBERTa/ALBERT/ELECTRA/T5的记录不从题名或URL补名；命名的训练资源不自动成为评测数据集。</p>'
        body+=table(['来源','明确评测对','配置边界'],[['2003.10555',1,'GPT作为GLUE比较基线，不扩大到所有同文模型'],['2006.03654',9,'半数据DeBERTa/RoBERTa-Large、scaled single和ensemble分开归属'],['1910.13461',4,'最近BART主语/RoBERTa比较，BERT/GPT前身不自动继承']])
        body+='<h2>两类实体边界处理</h2><p>BART架构内machine translation被记录为WITHIN_ENTITY；后面的真实翻译任务仍为独立TASK，原文Tranformer拼写不改。Sentence-BERT中的siamese and triplet network structures保留共享词头group，整篇NER/RE隔离，不拆造名称。</p><h2>当前结论</h2><p>取得了有证据的稀有关系参考，但不完整的全实体笛卡尔积仍无法支持完整文档pipeline评估。所有旧成绩、生产模型和31图保持；没有新F1。现有应用的实时验收另行保存，不能把本图称为应用成功截图。</p>'
        (EVIDENCE/'04_traceability.html').write_text(page('来源、配置归属与弃权边界 · 第49轮',body,stamp,[]),encoding='utf-8')
        p.c.write_json(EVIDENCE/'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui','filesSha256':{f.relative_to(EVIDENCE).as_posix():p.c.file_sha256(f) for f in EVIDENCE.rglob('*') if f.is_file()}}); print({'prepared':True,'engineeringTests':378})
    else:
        target=RUNS/'verification_20261009_round49.json'
        if target.exists(): raise FileExistsError('Preserve verification')
        p.g.verified_files(EVIDENCE); captures=json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig'))
        if p.read(EVIDENCE/'audit_state.json')!=audit or captures['status']!='completed' or len(captures['captures'])!=2: raise ValueError('Evidence incomplete')
        for item in captures['captures']:
            if p.c.file_sha256(EVIDENCE/item['image'])!=item['sha256'] or p.c.file_sha256(EVIDENCE/item['sourcePage'])!=item['sourcePageSha256']: raise ValueError('Screenshot changed')
        p.c.write_json(target,{'passed':True,'checkedAtUTC':datetime.now(UTC).isoformat(),'audit':audit,'evidenceManifestSha256':p.c.file_sha256(EVIDENCE/'manifest.json'),'capturesSha256':p.c.file_sha256(EVIDENCE/'captures.json'),'qualityPromotionPassed':False,'modelPromoted':False}); print({'passed':True,'engineeringTests':378,'qualityPromotionPassed':False})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('action',choices=('prepare','seal')); main(parser.parse_args().action)
