"""Seal real train-label artifacts and a browser-rendered summary, not a model-quality claim."""
import argparse
import json
import shutil
import sys
from datetime import UTC,datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import course_graph as g
import course_weak as c
from export_course_evidence import page,table,highlight
from train_course_ner import decode_bio

RUNS=ROOT/'kg_datasets/dblp/course_v4_runs'
EVIDENCE=ROOT/'docs/evidence/20261008_round33'
FOLDERS=['course_abstract_train_generation_20261008_33','course_abstract_train_reviewed_20261008_33']

def checked():
    previous=json.loads((RUNS/'verification_20261008_round32.json').read_text(encoding='utf-8'))
    assert previous['passed'] and all(c.file_sha256(ROOT/p)==sha for p,sha in previous['immutableSourceSha256'].items())
    g.verified_files(ROOT/'docs/evidence/20261008_round32',previous['evidenceManifestSha256'])
    assert c.file_sha256(ROOT/'docs/evidence/20261008_round32/captures.json')==previous['capturesSha256']
    for folder in FOLDERS:
        manifest=g.verified_files(ROOT/'kg_datasets/dblp'/folder)
        assert all(c.file_sha256(ROOT/p)==sha for p,sha in manifest['inputSha256'].items())
    reviewed=ROOT/'kg_datasets/dblp'/FOLDERS[1]
    refs=c.read_jsonl(reviewed/'references.jsonl');receipts=c.read_jsonl(reviewed/'reviewed_receipts.jsonl');aligned=c.read_jsonl(reviewed/'token_alignment.jsonl')
    assert len(refs)==len(receipts)==len(aligned)==37 and all(r['split']=='train' for r in refs)
    for ref,receipt,encoded in zip(refs,receipts,aligned):
        assert not c.validate_receipt(receipt,ref) and encoded['eligibility']==c.eligible_tasks(receipt,ref)
        if encoded['strictAlignmentPassed']:
            expected=[{k:e[k] for k in ('start','end','text','label')} for e in receipt['annotation']['entities']]
            assert all(label!=-100 or tuple(offset)==(0,0) for label,offset in zip(encoded['BIOLabels'],encoded['offsets']))
            tags=[0 if tuple(offset)==(0,0) else label for label,offset in zip(encoded['BIOLabels'],encoded['offsets'])]
            assert decode_bio(tags,encoded['offsets'],ref['text'])=={'entities':expected,'invalidTransitions':0}
    summary=json.loads((reviewed/'summary.json').read_text(encoding='utf-8'))
    assert summary['nerCandidates']==29 and summary['excludedNER']==8 and not summary['trainingExecuted']
    assert len(c.read_jsonl(reviewed/'ner_train_candidates.jsonl'))==29
    positives=c.read_jsonl(reviewed/'positive_relation_candidates.jsonl')
    assert len(positives)==17 and not any(r['fullRelationTrainingEligible'] for r in positives)
    suite=ElementTree.parse(RUNS/'tests_20261008_round33_all.xml').getroot().find('testsuite')
    assert suite.get('tests')=='361' and all(suite.get(k)=='0' for k in ('errors','failures','skipped'))
    return previous,summary,refs,receipts

def main(action):
    previous,summary,refs,receipts=checked()
    if action=='prepare':
        if EVIDENCE.exists():raise FileExistsError('Preserve evidence')
        sources=EVIDENCE/'sources';sources.mkdir(parents=True)
        paths=[Path(__file__),ROOT/'scripts/compile_abstract_annotations.py',ROOT/'scripts/review_abstract_annotations.py',ROOT/'tests/test_abstract_annotations.py',RUNS/'tests_20261008_round33_all.xml']
        paths+=list((ROOT/'annotations/course_v4').glob('abstract_*20261008_33.json'))
        for path in paths:shutil.copy2(path,sources/path.name)
        for folder in FOLDERS:shutil.copytree(ROOT/'kg_datasets/dblp'/folder,sources/folder)
        body='<h2>整篇训练摘要标注与复核</h2>'+table(['项目','核验结果'],[
            ['覆盖','37篇训练摘要逐篇AI判断及同会话复核；不是人工金标准'],
            ['NER候选','29篇通过严格分词/BIO往返；METHOD211 / TASK109 / DATASET35'],
            ['NER隔离','8篇：2篇首轮歧义、1篇并列组、5篇复核发现边界/内容不完整'],
            ['关系候选','11条EVALUATED_ON、6条USED_FOR；1,119对UNRESOLVED，未填负例'],
            ['关系训练可用性','17条正例均非整篇完整关系监督；尚不能直接重训RE'],
            ['数据隔离','验证19篇待标注；测试19篇未读取内容/未评测；旧标题标签不改'],
            ['模型状态','没有重训或新F1，没有数据库写入或候选晋级'],
            ['工程检查','361项通过；不等于361项语义正确验证'],
            ['已知失败','首轮边界编译失败保留，修正显式原文跨度及双破折号解析后重建']])
        body+='<h2>真实摘要与AI标签示例</h2>'+''.join('<div class="title">'+highlight(ref['text'],receipt['annotation']['entities'])+'</div>' for ref,receipt in zip(refs,receipts) if ref['arxivId']=='2008.10400')
        body+='<p>图为真实保存产物的浏览器渲染截图，不是训练控制台或应用界面截图。MLE隔离合同不允许直接混入旧标题训练数据；后续先完成验证侧标注与关系歧义处理，再冻结新训练方案。完整课程报告继续暂停。</p>'
        (EVIDENCE/'09_annotation_expansion.html').write_text(page('整篇摘要AI标注验收 · 2026-10-08',body,datetime.now(UTC).isoformat(),FOLDERS),encoding='utf-8')
        c.write_json(EVIDENCE/'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui','filesSha256':{p.relative_to(EVIDENCE).as_posix():c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})
    else:
        output=RUNS/'verification_20261008_round33.json'
        if output.exists():raise FileExistsError('Preserve seal')
        g.verified_files(EVIDENCE)
        captures=json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig'))
        assert captures['status']=='completed' and captures['originalConsoleScreenshot'] is False and len(captures['captures'])==1
        for capture in captures['captures']:
            assert c.file_sha256(EVIDENCE/capture['image'])==capture['sha256'] and c.file_sha256(EVIDENCE/capture['sourcePage'])==capture['sourcePageSha256']
        c.write_json(output,{'passed':True,'checkedAtUTC':datetime.now(UTC).isoformat(),'engineeringTests':361,'summary':summary,
            'immutableSourceSha256':previous['immutableSourceSha256'],'previousVerificationSha256':c.file_sha256(RUNS/'verification_20261008_round32.json'),
            'evidenceManifestSha256':c.file_sha256(EVIDENCE/'manifest.json'),'capturesSha256':c.file_sha256(EVIDENCE/'captures.json'),
            'modelRetrained':False,'testEvaluated':False,'databaseWritten':False,'qualityPromotionPassed':False,'reportExpansionPaused':True})
        print(json.dumps({'passed':True,'engineeringTests':361,'nerCandidates':29,'newModelScore':None}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','seal'));main(parser.parse_args().action)
