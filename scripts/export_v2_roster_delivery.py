"""Verify real batch artifacts, render a clearly labeled evidence page, package it."""
import argparse
import hashlib
import html
import json
import shutil
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import prepare_v2_sampling as p
import collect_v2_dev as dev
from run_v2_admission_checks import junit

ROOT=p.ROOT
BUNDLE=ROOT/'kg_datasets/dblp/course_v2_sampling_20261011_roster_locked_v2'
DEV=ROOT/'kg_datasets/dblp/course_v2_dev_sources_20261011'
CHECKS=ROOT/'outputs/v2_roster_20261011_checks_v2'
EVIDENCE=ROOT/'outputs/v2_roster_evidence_20261011'
ARCHIVE=ROOT/'outputs/v2_roster_and_dev_audit_20261011_v2.zip'


def actual():
    verification=p.verify(BUNDLE);collection=dev.verify(DEV,BUNDLE)
    inventory=p.sampling.read(CHECKS/'test_inventory.json');receipt=p.sampling.read(CHECKS/'run_receipt.json')
    expected=[('tests.'+Path(n.split('::')[0]).stem,n.split('::',1)[1]) for n in inventory['nodeIds']]
    count=junit(CHECKS/'checks.xml',expected)
    if (receipt['status']!='passed' or receipt['exitCode']!=0 or count!=receipt['actualTests']
            or receipt['inventorySha256']!=p.sha(CHECKS/'test_inventory.json')
            or receipt['junitSha256']!=p.sha(CHECKS/'checks.xml') or receipt['logSha256']!=p.sha(CHECKS/'pytest.log')
            or receipt['sourceSha256']!=inventory['sourceSha256']
            or any(p.sha(ROOT/name)!=value for name,value in receipt['sourceSha256'].items())):
        raise ValueError('Actual test receipt/source mismatch')
    previous=ROOT/'kg_datasets/dblp/course_v2_sampling_20261011_final'
    if (BUNDLE/'selected_members.json').read_bytes()!=(previous/'selected_members.json').read_bytes():
        raise ValueError('Fixed evaluation cohort changed')
    original=ROOT/'kg_datasets/dblp/course_v2_admission_20261010'
    if any((BUNDLE/'audit_parent'/n).read_bytes()!=(original/n).read_bytes() for n in p.CORE):
        raise ValueError('Old train labels changed')
    protection=p.sampling.read(original/'production_protection.json')
    if any(p.sha(ROOT/name)!=value for name,value in protection.items()):raise ValueError('V1 protected file changed')
    old_zip=ROOT/'outputs/v2_sampling_audit_20261011.zip'
    if p.sha(old_zip)!='90eac965619f09d6e3f6bf81596bbbb4f9a7e22620523840c89bf81695231084':
        raise ValueError('Old sealed sampling archive changed')
    train=p.sampling.read(BUNDLE/'audit_parent/split_lock.json')['assignments']
    aliases=p.sampling.read(BUNDLE/'audit_parent/identity_alias_index.json')
    excluded=p.sampling.rows(BUNDLE/'audit_parent/historical_exclusions.jsonl')
    extra={'publicationId':'arxiv:2502.00003','groupId':'arxiv-group:2502.00003','arxivId':'2502.00003','split':'train'}
    probes=[]
    for name,rows in [('empty',[]),('replacement',[extra]),('addition',train+[extra]),('deletion',train[:-1])]:
        try:p.sampling.prelock(BUNDLE,rows,excluded,aliases)
        except ValueError as error:probes.append({'probe':name,'accepted':False,'reason':str(error)})
        else:raise ValueError('Training roster mutation accepted: '+name)
    return {'status':'roster_fixed_dev_sources_ready_for_review_not_training_ready',
        'samplingVerification':verification,'devVerification':collection,
        'actualTests':count,'testRunId':receipt['runId'],'fixedFortyIdentitiesUnchanged':True,
        'sixTrainCoreFilesUnchanged':True,'v1ProtectedFileCount':len(protection),
        'oldSealedArchiveUnchanged':True,'acceptedNegativePairs':0,'negativeLabel':'UNRESOLVED',
        'rosterMutationProbes':probes,'trainingAuthorized':False,'evaluationAuthorized':False,
        'newModelMetrics':None,'testContentParsed':False,'verifiedAtUTC':datetime.now(UTC).isoformat()}


def render():
    if EVIDENCE.exists():raise FileExistsError('Preserve previous evidence page')
    result=actual();EVIDENCE.mkdir(parents=True)
    p.write(EVIDENCE/'verification.json',result)
    shutil.copy2(DEV/'dev_review.csv',EVIDENCE/'dev_review.csv')
    rows=p.sampling.rows(DEV/'references.jsonl')
    cells=''.join('<tr><td>'+html.escape(r['arxivId'])+'</td><td>'+html.escape(r['title'])+'</td></tr>' for r in rows)
    document='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>V2 训练锁修复与 dev 原文证据</title>
<style>body{background:#eef2f7;color:#192942;font:17px/1.55 "Microsoft YaHei",sans-serif;margin:0}
main{max-width:1120px;margin:24px auto;background:white;padding:28px 38px;border-top:6px solid #2463bc}
h1{font-size:28px}h2{font-size:22px}.cards{display:flex;gap:14px}.cards div{flex:1;background:#f0f5fc;padding:16px}
strong{font-size:27px;color:#2463bc}table{width:100%;border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #dce3ec;text-align:left}
.warn{background:#fff4df;padding:14px;border-left:4px solid #c58620}.small{font-size:14px;color:#53637c}</style><main>
<h1>V2 · 训练身份锁修复与固定 dev 原文准备</h1><p>2026-10-11 · 基于真实文件的证据页，不是 Neo4j 或训练控制台截图</p>
<div class="cards"><div>正式工程检查<br><strong>TEST_COUNT 项</strong><br>真实 pytest 执行</div>
<div>固定 dev 官方摘要<br><strong>DEV_COUNT / 20</strong><br>已保存原文，未标注</div>
<div>测试正文请求<br><strong>0</strong><br>test20 仍仅元数据封存</div></div>
<h2>本批实际完成</h2><p>原12篇训练身份与六个核心数据文件绑定到固定上游 manifest。空名单、增加、删除、替换及重签自造名单均被阻断；原40篇 dev/test 身份不变，不重新抽样。</p>
<p>pooling → MNIST：独立审核裁决维持 UNRESOLVED，不作为 NO_RELATION。原始候选与旧标签保留，当前接受负例为0。</p>
<div class="warn">仍未准入训练：dev 标注0篇；可靠 RE 负例0条；test20 正文与参考标签未准备；来源版本/语义近重复仍需复核。没有训练、没有新 F1、没有改 V1 生产模型。</div>
<h2>固定 dev20 原文审核清单</h2><p class="small">官方页面/摘要字节哈希已绑定；不是独立人工金标准。失败不换样本，未决不补成负例。</p>
<table><tr><th>arXiv 身份</th><th>官方题名（完整摘要见 dev_review.csv）</th></tr>ROWS</table>
<p class="small">工程检查不代表语义正确率。README、工作记录和 verification.json 提供更完整边界。</p></main></html>'''
    document=document.replace('TEST_COUNT',str(result['actualTests'])).replace('DEV_COUNT',str(result['devVerification']['collectedDevDocuments'])).replace('ROWS',cells)
    (EVIDENCE/'10_roster_and_dev.html').write_text(document,encoding='utf-8')
    p.write(EVIDENCE/'manifest.json',{'kind':'verified_artifact_evidence_page_not_original_application_ui',
        'inputSha256':{'bundleManifest':p.sha(BUNDLE/'manifest.json'),'devManifest':p.sha(DEV/'manifest.json'),
                       'testReceipt':p.sha(CHECKS/'run_receipt.json'),'renderer':p.sha(Path(__file__))},
        'filesSha256':{x.name:p.sha(x) for x in EVIDENCE.iterdir() if x.is_file()}})
    return result


def package():
    if ARCHIVE.exists():raise FileExistsError('Preserve previous archive')
    result=actual()
    evidence=p.sampling.read(EVIDENCE/'manifest.json')
    for name,value in evidence['filesSha256'].items():
        p.sampling.admission.artifact(EVIDENCE,{'file':name,'sha256':value})
    captures=json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig'))
    if captures['status']!='completed' or captures['originalConsoleScreenshot'] is not False:
        raise ValueError('Capture failed or misrepresented')
    for capture in captures['captures']:
        if p.sha(EVIDENCE/capture['image'])!=capture['sha256'] or p.sha(EVIDENCE/capture['sourcePage'])!=capture['sourcePageSha256']:
            raise ValueError('Real capture/page binding drift')
    files={x.resolve() for folder in (BUNDLE,DEV,CHECKS,EVIDENCE) for x in folder.rglob('*') if x.is_file()}
    test_receipt=p.sampling.read(CHECKS/'run_receipt.json')
    files.update((ROOT/n).resolve() for n in test_receipt['sourceSha256'])
    files.update({Path(__file__).resolve(),ROOT/'scripts/capture_v2_roster_evidence.ps1',
                  ROOT/'docs/course_v2_roster_and_dev_20261011.md',ROOT/'README.md'})
    members={x.relative_to(ROOT).as_posix():x for x in files}
    # Include the actual parent at its experiment path and missing test/runtime
    # dependencies at package root, so replay is not dependent on this checkout.
    original=ROOT/'kg_datasets/dblp/course_v2_admission_20261010'
    for x in original.rglob('*'):
        if x.is_file():members.setdefault(x.relative_to(ROOT).as_posix(),x)
    snapshot=original/'source_snapshot'
    for x in snapshot.rglob('*'):
        if x.is_file():members.setdefault(x.relative_to(snapshot).as_posix(),x)
    hashes={name:p.sha(x) for name,x in members.items()}
    with zipfile.ZipFile(ARCHIVE,'x',zipfile.ZIP_DEFLATED) as archive:
        for name,x in sorted(members.items()):archive.write(x,name)
    with zipfile.ZipFile(ARCHIVE) as archive:
        if archive.testzip() is not None or set(archive.namelist())!=set(hashes):raise ValueError('Archive CRC/member mismatch')
        for name,value in hashes.items():
            if hashlib.sha256(archive.read(name)).hexdigest()!=value:raise ValueError('Archive file mismatch: '+name)
    receipt=result|{'archive':ARCHIVE.relative_to(ROOT).as_posix(),'archiveSha256':p.sha(ARCHIVE),
        'archiveBytes':ARCHIVE.stat().st_size,'filesSha256':hashes,'members':len(hashes),
        'notice':'Hash-bound offline bundle, not signed attestation; no model weights or new test contents.'}
    p.write(ROOT/'outputs/v2_roster_and_dev_audit_20261011_v2_receipt.json',receipt)
    return {k:receipt[k] for k in ('status','archive','archiveSha256','archiveBytes','members','actualTests')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--package',action='store_true')
    print(json.dumps(package() if parser.parse_args().package else render(),ensure_ascii=False,indent=2))
