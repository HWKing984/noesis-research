"""Seal observed round31 artifacts and verify old/new live graph isolation."""
import getpass
import json
import shutil
import sys
from datetime import UTC,datetime
from pathlib import Path
from xml.etree import ElementTree

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import course_graph as g

def main():
    runs=ROOT/'kg_datasets/dblp/course_v4_runs';evidence=ROOT/'docs/evidence/20261007_round31'
    output=runs/'verification_20261007_round31.json'
    if output.exists():raise FileExistsError('Preserve sealed verification')
    prior=json.loads((runs/'verification_20261007_round30.json').read_text(encoding='utf-8'))
    immutable=prior['immutableSourceSha256']|{
        'kg_datasets/dblp/course_v4_graph_production_20261007_25/manifest.json':prior['graphManifestSha256'],
        'kg_datasets/dblp/course_v4_runs/refresh_final_test_20261007_29/test_result.json':prior['testResultSha256'],
        'docs/evidence/20261007_round30/manifest.json':prior['evidenceManifestSha256']}
    assert all(g.c.file_sha256(ROOT/p)==sha for p,sha in immutable.items())
    bundle=ROOT/'kg_datasets/dblp/course_v4_graph_resolved_20261007_31_ready'
    data=g.verify_bundle(bundle);manifest=data['manifest']
    assert all(g.c.file_sha256(ROOT/p)==sha for p,sha in manifest['inputSha256'].items())
    for folder in ('course_v4_identity_20261007_31_recovered','course_v4_rare_queue_full_20261007_31'):
        g.verified_files(ROOT/'kg_datasets/dblp'/folder)
    decoder=runs/'decoder_development_20261007_31_cuda';g.verified_files(decoder)
    experiment=json.loads((decoder/'development_result.json').read_text(encoding='utf-8'))
    assert experiment['metrics']['constrained']['micro']['f1']<experiment['metrics']['argmax']['micro']['f1']
    assert not experiment['modelPromoted'] and not experiment['testEvaluated'] and experiment['weightsUnchanged']
    suite=ElementTree.parse(runs/'tests_20261007_round31_all.xml').getroot().find('testsuite')
    assert int(suite.get('tests'))==359 and not int(suite.get('errors')) and not int(suite.get('failures'))
    acceptance=[runs/p for p in ('identity_acceptance_20261007_31.json','graph_explorer_resolved_20261007_31.json')]
    assert all(json.loads(p.read_text(encoding='utf-8'))['passed'] for p in acceptance)
    receipt=runs/'graph_import_resolved_retry_20261007_31.json'
    imported=json.loads(receipt.read_text(encoding='utf-8'))
    assert imported['status']=='completed' and imported['actualCounts']==manifest['counts']
    client=g.Neo4j('http://127.0.0.1:7474','neo4j','neo4j',getpass.getpass('Neo4j password (not saved): '))
    live={}
    for graph,expected in ((manifest['graphId'],manifest['counts']),(prior['graphId'],g.verified_files(ROOT/'kg_datasets/dblp/course_v4_graph_production_20261007_25')['counts'])):
        actual={'nodes':{},'edges':{}}
        for kind in g.KINDS:
            count=client.query(f'MATCH (n:Course{kind} {{graphId:$graph}}) RETURN count(n) AS count',{'graph':graph})[0]['count']
            if count:actual['nodes'][kind]=count
        for kind in g.EDGE_KINDS:
            count=client.query(f'MATCH (a:CourseNode {{graphId:$graph}})-[r:{kind} {{graphId:$graph}}]->(b:CourseNode {{graphId:$graph}}) RETURN count(r) AS count',{'graph':graph})[0]['count']
            if count:actual['edges'][kind]=count
        assert actual==expected;live[graph]=actual
    source=evidence/'sources';source.mkdir()
    files=['scripts/course_graph.py','scripts/course_identity.py','scripts/course_resolution.py','scripts/course_bio_constraints.py',
        'resources/course_literature.html','annotations/course_v4/decoder_dev_20261007_round31.py',
        'annotations/course_v4/prepare_rare_queue_20261007_round31.py','annotations/course_v4/check_identity_20261007_round31.py',
        'annotations/course_v4/check_graph_explorer_20261007_round29.py','annotations/course_v4/capture_system_20261007_round29.ps1',
        'annotations/course_v4/seal_resolution_20261007_round31.py']
    for p in files:shutil.copy2(ROOT/p,source/Path(p).name)
    for p in [receipt,*acceptance,runs/'tests_20261007_round31_all.xml',decoder/'development_result.json',bundle/'resolution_summary.json']:
        shutil.copy2(p,evidence/p.name)
    evidence_manifest={'filesSha256':{p.relative_to(evidence).as_posix():g.c.file_sha256(p) for p in evidence.rglob('*') if p.is_file()}}
    g.c.write_json(evidence/'manifest.json',evidence_manifest)
    result={'passed':True,'checkedAtUTC':datetime.now(UTC).isoformat(),'engineeringTests':359,'liveCounts':live,
        'graphId':manifest['graphId'],'graphManifestSha256':g.c.file_sha256(bundle/'manifest.json'),
        'immutableSourceSha256':immutable,'evidenceManifestSha256':g.c.file_sha256(evidence/'manifest.json'),
        'modelRetrained':False,'testRepeated':False,'decoderDevExperimentRejected':True,'qualityPromotionPassed':False,
        'databaseWritten':True,'oldGraphPreserved':True,'reportExpansionPaused':True,'passwordWrittenToArtifacts':False}
    g.c.write_json(output,result);print(json.dumps({'passed':True,'graphId':manifest['graphId'],'engineeringTests':359,'modelPromoted':False}))

if __name__=='__main__':main()
