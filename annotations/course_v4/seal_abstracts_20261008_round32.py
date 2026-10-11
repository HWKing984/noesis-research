"""Verified artifact visualization and post-capture seal; no model or database writes."""
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

EVIDENCE=ROOT/'docs/evidence/20261008_round32'
RUNS=ROOT/'kg_datasets/dblp/course_v4_runs'
FOLDERS=['course_abstract_sources_20261008_32','course_abstract_pages_20261008_32',
    'course_abstract_pilot_20261008_32','course_abstract_pilot_reviewed_ready_20261008_32','course_abstract_queue_20261008_32']

def checked():
    previous=json.loads((RUNS/'verification_20261007_round31.json').read_text(encoding='utf-8'))
    assert all(c.file_sha256(ROOT/p)==sha for p,sha in previous['immutableSourceSha256'].items())
    g.verified_files(ROOT/'docs/evidence/20261007_round31',previous['evidenceManifestSha256'])
    assert c.file_sha256(ROOT/'kg_datasets/dblp/course_v4_graph_resolved_20261007_31_ready/manifest.json')==previous['graphManifestSha256']
    summaries={}
    for folder in FOLDERS:
        path=ROOT/'kg_datasets/dblp'/folder;manifest=g.verified_files(path)
        assert all(c.file_sha256(ROOT/p)==sha for p,sha in manifest['inputSha256'].items())
        summaries[folder]=json.loads((path/'summary.json').read_text(encoding='utf-8'))
    reviewed=ROOT/'kg_datasets/dblp/course_abstract_pilot_reviewed_ready_20261008_32'
    refs=c.read_jsonl(reviewed/'references.jsonl');receipts=c.read_jsonl(reviewed/'reviewed_receipts.jsonl');align=c.read_jsonl(reviewed/'token_alignment.jsonl')
    for ref,receipt,encoded in zip(refs,receipts,align):
        assert not c.validate_receipt(receipt,ref) and all(c.eligible_tasks(receipt,ref).values())
        expected=[{k:e[k] for k in ('start','end','text','label')} for e in receipt['annotation']['entities']]
        assert all(label!=-100 or start==end for label,(start,end) in zip(encoded['BIOLabels'],encoded['offsets']))
        tags=[0 if label==-100 else label for label in encoded['BIOLabels']]
        assert decode_bio(tags,encoded['offsets'],ref['text'])=={'entities':expected,'invalidTransitions':0}
    suite=ElementTree.parse(RUNS/'tests_20261008_round32_final.xml').getroot().find('testsuite')
    assert suite.get('tests')=='360' and all(suite.get(k)=='0' for k in ('errors','failures','skipped'))
    return previous,summaries,refs,receipts

def main(action):
    previous,summaries,refs,receipts=checked()
    if action=='prepare':
        if EVIDENCE.exists():raise FileExistsError('Preserve visualization')
        sources=EVIDENCE/'sources';sources.mkdir(parents=True)
        for folder in FOLDERS:
            path=ROOT/'kg_datasets/dblp'/folder
            for name in ('summary.json','manifest.json'):shutil.copy2(path/name,sources/(folder+'_'+name))
        paths=[Path(__file__),ROOT/'scripts/collect_course_abstracts.py',ROOT/'scripts/collect_course_abstract_pages.py',
            ROOT/'scripts/prepare_abstract_pilot.py',ROOT/'scripts/review_abstract_pilot.py',
            ROOT/'annotations/course_v4/prepare_abstract_queue_20261008_round32.py',
            ROOT/'annotations/course_v4/abstract_pilot_decisions_20261008_32.json',ROOT/'annotations/course_v4/abstract_pilot_review_20261008_32.json',
            ROOT/'tests/test_course_abstracts.py',ROOT/'scripts/capture_course_evidence.ps1',ROOT/'scripts/export_course_evidence.py',
            RUNS/'tests_20261008_round32_final.xml']
        for path in paths:shutil.copy2(path,sources/path.name)
        queue=summaries['course_abstract_queue_20261008_32'];pilot=summaries['course_abstract_pilot_reviewed_ready_20261008_32']
        body='<h2>来源与数据队列</h2>'+table(['项目','实际结果'],[
            ['导出API','5批请求超时，保存失败；没有合成摘要替代'],['官方摘要页','60次请求成功，57篇题名匹配、3篇隔离'],
            ['已有来源','18篇题名匹配；1篇旧题名不匹配隔离'],['整篇摘要',f"{queue['usableAbstracts']}篇；train37 / dev19 / test19；最大{queue['maxTokens']}token，无截断"],
            ['试标','8段原文 / 7个论文组，仅train；9个DATASET、5个METHOD、5个TASK'],
            ['关系','5条USED_FOR、2条EVALUATED_ON；均是AI参考标签'],['复核与对齐','同会话AI复核8段、修订2处边界；BIO严格往返一致'],
            ['模型状态','本轮未重训、未评测模型、未晋级；360工程检查通过，不等于语义准确率']])
        body+='<h2>真实原文与AI标注示例</h2>'+''.join('<div class="title">'+highlight(ref['text'],r['annotation']['entities'])+'</div>' for ref,r in zip(refs,receipts) if ref['arxivId']=='2107.03374')
        body+='<p>75篇整篇摘要仍待单独标注；8段试标不冒称整篇摘要已标注。没有独立人工金标准。报告继续暂停。</p>'
        c.write_json(EVIDENCE/'artifact_summary.json',summaries)
        (EVIDENCE/'09_annotation_expansion.html').write_text(page('摘要数据扩充与标注预检 · 2026-10-08',body,datetime.now(UTC).isoformat(),FOLDERS),encoding='utf-8')
        c.write_json(EVIDENCE/'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui',
            'filesSha256':{p.relative_to(EVIDENCE).as_posix():c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})
    else:
        output=RUNS/'verification_20261008_round32.json'
        if output.exists():raise FileExistsError('Preserve final seal')
        g.verified_files(EVIDENCE)
        captures=json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig'))
        assert captures['status']=='completed' and captures['originalConsoleScreenshot'] is False
        for image in captures['captures']:assert c.file_sha256(EVIDENCE/image['image'])==image['sha256']
        c.write_json(output,{'passed':True,'checkedAtUTC':datetime.now(UTC).isoformat(),'engineeringTests':360,
            'summaries':summaries,'immutableSourceSha256':previous['immutableSourceSha256'],
            'evidenceManifestSha256':c.file_sha256(EVIDENCE/'manifest.json'),'capturesSha256':c.file_sha256(EVIDENCE/'captures.json'),
            'modelRetrained':False,'testEvaluated':False,'databaseWritten':False,'qualityPromotionPassed':False,
            'titleLabelsModified':False,'reportExpansionPaused':True})
        print(json.dumps({'passed':True,'engineeringTests':360,'abstractsQueued':75,'modelPromoted':False}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','seal'));main(parser.parse_args().action)
