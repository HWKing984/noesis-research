"""Freeze real course-demo acceptance without changing the graph or model."""
import json
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'scripts'))
import course_graph as g

RUNS=ROOT/'kg_datasets/dblp/course_v4_runs'
EVIDENCE=ROOT/'docs/evidence/20261009_round50'


def main():
    output=RUNS/'verification_20261009_round50.json'
    if output.exists() or (EVIDENCE/'manifest.json').exists(): raise FileExistsError('Preserve frozen application evidence')
    bundle=g.configured_bundle(); manifest=g.verified_files(bundle)
    read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
    app_path=RUNS/'application_acceptance_20261009_50_final.json'; graph_path=RUNS/'graph_explorer_acceptance_20261009_50.json'
    app=read(app_path); graph=read(graph_path); qa=read(EVIDENCE/'browser_qa.json'); capture=read(EVIDENCE/'capture_receipt.json')
    checker=ROOT/'annotations/course_v4/check_application_20261009_round50.py'
    assert app['passed'] and graph['passed'] and app['sourceSha256']==g.c.file_sha256(checker)
    assert app['graphId']==graph['graphId']==manifest['graphId'] and app['bundleManifestSha256']==g.c.file_sha256(bundle/'manifest.json')
    assert len(app['HTTPChecks'])==32 and len(graph['checks'])==15 and len(app['databaseChecks'])==8 and all(r['actualStatus']==r['expectedStatus'] for r in app['HTTPChecks']+graph['checks'])
    assert app['nodeCount']==194639 and app['edgeCount']==263059 and not app['modelQualityEvaluation'] and not graph['modelQualityEvaluation']
    with urlopen('http://127.0.0.1:8765/api/health',timeout=30) as response: health=json.load(response)['data']
    assert health['graphId']==manifest['graphId'] and health['status']=='ready' and health['source']=='live_neo4j' and health['scope']['bibliographyTitles']==20000
    junit=ET.parse(RUNS/'tests_20261009_round50_complete.xml').getroot().find('testsuite').attrib
    assert (junit['tests'],junit['failures'],junit['errors'],junit['skipped'])==('378','0','0','0')
    screenshots=[]
    for name,width in [('04_graph_desktop',1440),('05_graph_tablet',768),('06_graph_mobile',375)]:
        image=EVIDENCE/(name+'_round50.png'); baseline=ROOT/'docs/evidence/20261007_round31'/(name+'_round31.png'); raw=image.read_bytes()
        assert raw[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',raw[16:24])==(width,1100)
        sha=g.c.file_sha256(image); assert sha==g.c.file_sha256(baseline)
        receipt=next(r for r in capture if r.get('Screenshot','').endswith(image.name)); assert receipt['Observed']['width']==width and not receipt['Observed']['overflow']
        screenshots.append({'image':image.name,'sha256':sha,'baseline':baseline.relative_to(ROOT).as_posix(),'baselineByteIdentical':True})
    exported=read(EVIDENCE/'downloads/ai-literature-candidates.json'); item=exported['items'][0]
    detail=next(r['response']['data'] for r in app['HTTPChecks'] if r['route']=='/api/publication?id=conf%2F3dim%2FVavilalaVF25')
    assert len(exported['items'])==1 and item['source']=='live_neo4j_detail_snapshot' and item['data']==detail
    assert detail['publication']['title'] in (EVIDENCE/'downloads/ai-literature-reference-drafts.txt').read_text(encoding='utf-8')
    assert not qa['modelQualityPromoted'] and qa['smoke']['observedFailedRequests']==0 and not qa['accessibilityChecks']['fullWCAGAuditPerformed']
    failed=read(RUNS/'application_acceptance_20261009_50.json'); assert not failed['passed'] and failed['errorType']=='AssertionError'
    node=Path('C:/Users/Y7000P/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
    command=[str(node),str(ROOT/'tests/test_course_ui.cjs')]; result=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',timeout=30)
    assert result.returncode==0 and result.stdout.startswith('PASS:')
    g.c.write_json(EVIDENCE/'node_ui_check.json',{'command':command,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'checkedAtUTC':datetime.now(UTC).isoformat()})
    paths=[Path(__file__),checker,ROOT/'scripts/course_graph.py',ROOT/'scripts/course_weak.py',ROOT/'resources/course_literature.html',g.RUNTIME_CONFIG,bundle/'manifest.json',ROOT/'annotations/course_v4/check_graph_explorer_20261007_round29.py',ROOT/'annotations/course_v4/capture_system_20261007_round29.ps1',ROOT/'tests/test_course_ui.cjs',app_path,graph_path,RUNS/'application_acceptance_20261009_50.json',RUNS/'tests_20261009_round50_complete.xml']
    paths += [ROOT/p for p in ('README.md','docs/system_status_round50.md','docs/course_v4_plan.md','docs/course_v4_runbook.md','docs/status_log.md','docs/model_optimization_abstract_v1.md')]
    for path in paths:
        target=EVIDENCE/'sources'/path.relative_to(ROOT)
        if target.exists(): raise FileExistsError('Preserve archived source')
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(path,target)
    state={'checkedAtUTC':datetime.now(UTC).isoformat(),'passed':True,'liveApplicationPassed':True,'courseCandidateSystemReady':True,'qualityPromotionPassed':False,'modelPromoted':False,'trainingExecuted':False,'testEvaluated':False,'graphWritten':False,'graphId':manifest['graphId'],'bundleManifestSha256':g.c.file_sha256(bundle/'manifest.json'),'HTTPChecks':47,'databaseChecks':8,'engineeringTests':378,'regressionSeconds':float(junit['time']),'health':health,'screenshots':screenshots,'actualDownloads':True,'fullWCAGAuditPerformed':False,'nodeUICheckPassed':True}
    g.c.write_json(EVIDENCE/'audit_state.json',state)
    g.c.write_json(EVIDENCE/'manifest.json',{'kind':'actual_live_application_http_browser_evidence','createdAtUTC':datetime.now(UTC).isoformat(),'filesSha256':{p.relative_to(EVIDENCE).as_posix():g.c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})
    g.verified_files(EVIDENCE)
    g.c.write_json(output,state|{'evidenceManifestSha256':g.c.file_sha256(EVIDENCE/'manifest.json')})
    print(json.dumps({'liveApplicationPassed':True,'HTTPChecks':47,'databaseChecks':8,'engineeringTests':378,'qualityPromotionPassed':False}))


if __name__=='__main__': main()
