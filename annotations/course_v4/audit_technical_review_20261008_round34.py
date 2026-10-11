"""Read-only technical audit and post-capture seal; no inference, fit, database write or restart."""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC,datetime
from pathlib import Path
from urllib.request import urlopen
from xml.etree import ElementTree

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import course_graph as g
import course_weak as c
from export_course_evidence import page,table

RUNS=ROOT/'kg_datasets/dblp/course_v4_runs'
EVIDENCE=ROOT/'docs/evidence/20261008_round34'

def read(path):return json.loads(path.read_text(encoding='utf-8'))

def checked():
    previous=read(RUNS/'verification_20261008_round33.json')
    assert previous['passed'] and all(c.file_sha256(ROOT/p)==sha for p,sha in previous['immutableSourceSha256'].items())
    g.verified_files(ROOT/'docs/evidence/20261008_round33',previous['evidenceManifestSha256'])
    assert c.file_sha256(ROOT/'docs/evidence/20261008_round33/captures.json')==previous['capturesSha256']
    suite=ElementTree.parse(RUNS/'tests_20261008_round34_all.xml').getroot().find('testsuite')
    assert suite.get('tests')=='362' and all(suite.get(k)=='0' for k in ('errors','failures','skipped'))
    return previous

def main(action):
    previous=checked()
    if action=='prepare':
        if EVIDENCE.exists():raise FileExistsError('Preserve audit')
        sources=EVIDENCE/'sources';sources.mkdir(parents=True)
        try:
            active=g.configured_bundle();manifest=g.verify_bundle(active)['manifest']
            command=[sys.executable,'-B',str(ROOT/'scripts/course_graph.py'),'verify']
            execution=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60,check=True,stdin=subprocess.DEVNULL)
            assert json.loads(execution.stdout)['graphId']==manifest['graphId']
            c.write_json(EVIDENCE/'default_cli_verify.json',{'command':command,'exitCode':execution.returncode,'stdout':execution.stdout,'stderr':execution.stderr,'readOnly':True})
            with urlopen('http://127.0.0.1:8765/api/health',timeout=20) as response:health=json.load(response)
            assert health['data']['status']=='ready' and health['data']['graphId']==manifest['graphId'] and health['data']['source']=='live_neo4j'
            c.write_json(EVIDENCE/'live_health.json',health)
            ner_path=RUNS/'ner_final_test_20261006_09/test_result.json';re_path=RUNS/'re_final_test_20261006_17/test_result.json';refresh_path=RUNS/'refresh_final_test_20261007_29/test_result.json'
            nr=read(ner_path);rr=read(re_path);fr=read(refresh_path)
            metrics=[{'task':'NER09','metrics':nr['test']['metrics']['micro'],'documents':nr['documents'],'queueDocuments':nr['queueReviewed']},
                {'task':'RE17_reference_entities','metrics':rr['moduleMetrics']['positiveMicro'],'documents':rr['evaluatedDocuments'],'queueDocuments':rr['queueDocuments']},
                {'task':'pipeline17','metrics':rr['pipelineMetrics']['positiveMicro'],'documents':rr['evaluatedDocuments'],'queueDocuments':rr['queueDocuments']},
                {'task':'NER29_candidate','metrics':fr['scores']['new']['NER']['micro'],'documents':fr['NERDocuments'],'queueDocuments':fr['queueDocuments']},
                {'task':'pipeline29_candidate','metrics':fr['scores']['new']['pipeline']['positiveMicro'],'documents':fr['pipelineDocuments'],'queueDocuments':fr['queueDocuments']}]
            for row in metrics:
                m=row['metrics'];tp=m['truePositive'];predicted=m['predicted'];reference=m['reference']
                assert abs(m['precision']-tp/predicted)<1e-12 and abs(m['recall']-tp/reference)<1e-12 and abs(m['f1']-2*tp/(predicted+reference))<1e-12
                row['documentCoverage']=row['documents']/row['queueDocuments']
            c.write_json(EVIDENCE/'stored_metrics_audit.json',{'metrics':metrics,'modelInferenceExecuted':False,'newMetricResult':False,'evaluationTarget':'AI_reference_not_human_gold','notice':'Stored scores from distinct queues and entity scopes; no pooled ranking or full-corpus error estimate.'})
            old_code=ROOT/'docs/evidence/20261007_round31/sources/course_graph.py'
            assert c.file_sha256(old_code)==manifest['inputSha256']['scripts/course_graph.py']
            paths=[Path(__file__),ROOT/'README.md',ROOT/'docs/system_status_round34.md',ROOT/'docs/model_optimization_abstract_v1.md',ROOT/'scripts/course_graph.py',g.RUNTIME_CONFIG,ROOT/'tests/test_course_runtime.py',RUNS/'tests_20261008_round34_all.xml',ner_path,re_path,refresh_path,active/'manifest.json']
            for path in paths:
                target=sources/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
            c.write_json(EVIDENCE/'audit_state.json',{'passed':True,'graphId':manifest['graphId'],'graphManifestSha256':c.file_sha256(active/'manifest.json'),'metricsReadOnly':True,
                'historicalExporterSnapshotVerified':True,'currentEntrypointDifferentFromHistoricalExporter':c.file_sha256(ROOT/'scripts/course_graph.py')!=c.file_sha256(old_code),
                'modelRetrained':False,'testInferenceRepeated':False,'databaseWritten':False,'serviceRestarted':False,'newDefaultEntrypointAppliedToRunningService':False,
                'scope':'Offline default CLI and existing live health only; no new browser interaction acceptance or full live node/edge recount.'})
            rows=[[r['task'],f"{r['metrics']['precision']:.2%}",f"{r['metrics']['recall']:.2%}",f"{r['metrics']['f1']:.2%}",r['metrics']['reference'],f"{r['documents']}/{r['queueDocuments']}"] for r in metrics]
            body='<h2>指标语义核对 · 只读封存结果</h2>'+table(['评估','Precision','Recall','F1','参考support','文档coverage'],rows)
            body+='<p>F1不等于正确率或错误比例；17轮子集82/140条预测严格匹配AI参考，不匹配58/140=41.43%，不能外推全量图谱。29轮没有EVALUATED_ON参考支持。不同队列不能直接排行。</p>'
            body+='<h2>版本与当前数据状态</h2>'+table(['核验项','实际结果'],[['默认入口','31轮ready包：路径/graphId/manifest与产物SHA锁定；配置无效不回退旧图'],['真实CLI','省略--bundle的verify成功，选择正确graphId，无凭据或数据库写入'],['现有服务','8765 health返回live_neo4j，graphId与配置一致；未重启、未完整重数节点边'],['摘要训练标签','37篇AI自复核，29篇NER候选、8篇隔离；DATASET35提及'],['关系候选','17条正例、1,119对未决；不能直接重训完整RE'],['工程回归','362项通过；不等于语义正确率'],['新实验','独立abstract_v1与同dev NER/RE四种交叉对照：计划，未训练'],['封存','旧权重/测试/图谱/33轮证据保留；旧执行源码SHA在原证据快照中核验']])
            (EVIDENCE/'09_annotation_expansion.html').write_text(page('技术评审纠错与只读验收 · 2026-10-08',body,datetime.now(UTC).isoformat(),['stored_metrics_audit.json','default_cli_verify.json','live_health.json']),encoding='utf-8')
            c.write_json(EVIDENCE/'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui','filesSha256':{p.relative_to(EVIDENCE).as_posix():c.file_sha256(p) for p in EVIDENCE.rglob('*') if p.is_file()}})
        except Exception as error:
            c.write_json(EVIDENCE/'failure.json',{'status':'failed_no_synthetic_fallback','errorType':type(error).__name__,'error':str(error)});raise
    else:
        output=RUNS/'verification_20261008_round34.json'
        if output.exists():raise FileExistsError('Preserve seal')
        g.verified_files(EVIDENCE)
        captures=json.loads((EVIDENCE/'captures.json').read_text(encoding='utf-8-sig'))
        assert captures['status']=='completed' and len(captures['captures'])==1 and captures['originalConsoleScreenshot'] is False
        for image in captures['captures']:
            assert c.file_sha256(EVIDENCE/image['image'])==image['sha256'] and c.file_sha256(EVIDENCE/image['sourcePage'])==image['sourcePageSha256']
        state=read(EVIDENCE/'audit_state.json');assert state['passed']
        c.write_json(output,{'passed':True,'checkedAtUTC':datetime.now(UTC).isoformat(),'engineeringTests':362,'audit':state,'immutableSourceSha256':previous['immutableSourceSha256'],
            'evidenceManifestSha256':c.file_sha256(EVIDENCE/'manifest.json'),'capturesSha256':c.file_sha256(EVIDENCE/'captures.json'),
            'previousVerificationSha256':c.file_sha256(RUNS/'verification_20261008_round33.json'),'qualityPromotionPassed':False,'reportExpansionPaused':True})
        print(json.dumps({'passed':True,'engineeringTests':362,'modelRetrained':False,'graphId':state['graphId']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','seal'));main(parser.parse_args().action)
