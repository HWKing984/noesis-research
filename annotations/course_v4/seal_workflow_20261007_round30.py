"""Seal actual workflow/download checks; does not train, label or write Neo4j."""
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT / 'scripts'))
import course_graph as g


def main():
    runs = ROOT / 'kg_datasets/dblp/course_v4_runs'
    evidence = ROOT / 'docs/evidence/20261007_round30'
    output = runs / 'verification_20261007_round30.json'
    if output.exists() or (evidence / 'manifest.json').exists() or (evidence / 'sources').exists():
        raise FileExistsError('Preserve sealed evidence')
    load = lambda p: json.loads(p.read_text(encoding='utf-8'))
    previous = load(runs / 'verification_20261007_round29.json')
    g.verified_files(ROOT / 'docs/evidence/20261007_round29',previous['evidenceManifestSha256'])
    assert all(g.c.file_sha256(ROOT / p)==sha for p,sha in previous['immutableSourceSha256'].items())
    assert g.c.file_sha256(runs / 'refresh_final_test_20261007_29/test_result.json')==previous['testResultSha256']
    assert g.c.file_sha256(ROOT / 'kg_datasets/dblp/course_v4_graph_production_20261007_25/manifest.json')==previous['graphManifestSha256']
    suite = ET.parse(runs / 'tests_20261007_round30_all.xml').getroot().find('testsuite')
    assert suite.attrib['tests']=='356' and all(suite.attrib[k]=='0' for k in ('errors','failures','skipped'))
    acceptance = load(runs / 'graph_explorer_acceptance_live_20261007_30.json')
    assert acceptance['passed'] and acceptance['readOnly'] and len(acceptance['checks'])==15
    base = acceptance['baseURL']
    def get(path):
        with urlopen(base+path,timeout=20) as response: return json.load(response)
    saved = load(evidence / 'downloads/ai-literature-candidates.json')
    assert len(saved['items'])==1 and saved['schemaVersion']==1 and '候选' in saved['notice']
    item = saved['items'][0]
    pid = item['data']['publication']['publicationId']
    actual = get('/api/publication?'+urlencode({'id':pid}))['data']
    assert actual==item['data'] and item['graphId']==acceptance['graphId']
    assert item['source']=='live_neo4j_detail_snapshot' and len(actual['assertions'])==1
    draft = (evidence / 'downloads/ai-literature-reference-drafts.txt').read_text(encoding='utf-8')
    assert actual['citationDraft'] in draft and actual['publication']['dblpUrl'] in draft
    path_records = {}
    for mode,hops in (('coauthors',2),('methods',4)):
        response = get('/api/graph?'+urlencode({'id':pid,'mode':mode,'limit':30}))
        data = response['data'];nodes={n['props']['id']:n for n in data['nodes']};edges={e['id']:e for e in data['edges']}
        assert len(data['paths'])==response['meta']['pathsReturned']>0
        for path in data['paths']:
            assert len(path['nodes'])==hops+1 and len(path['edges'])==hops and path['nodes'][0]==data['rootId']
            for i,eid in enumerate(path['edges']):
                assert {edges[eid]['source'],edges[eid]['target']}==set(path['nodes'][i:i+2])
                assert nodes[path['nodes'][i]]['props']['graphId']==acceptance['graphId']
        path_records[mode]=response
    g.c.write_json(evidence / 'ordered_paths_live.json',path_records)
    captures = load(evidence / 'capture_receipt.json')
    for capture in captures:
        if 'Observed' not in capture: continue
        assert not capture['Observed']['overflow'] and capture['Observed']['status'].startswith('10节点 / 11关系')
        with Path(capture['Screenshot']).open('rb') as stream: header=stream.read(24)
        assert header[:8]==b'\x89PNG\r\n\x1a\n'
        assert int.from_bytes(header[16:20],'big')==capture['Observed']['width']
    sources = [Path(__file__),ROOT / 'README.md',ROOT / 'docs/course_v4_progress.md',
        ROOT / 'scripts/course_graph.py',ROOT / 'resources/course_literature.html',ROOT / 'tests/test_course_graph.py',
        ROOT / 'tests/test_course_ui.py',ROOT / 'tests/test_course_ui.cjs',
        ROOT / 'annotations/course_v4/capture_system_20261007_round29.ps1',
        ROOT / 'annotations/course_v4/check_graph_explorer_20261007_round29.py']
    sources += list(runs.glob('*20261007*30*.xml'))+[runs / 'graph_explorer_acceptance_live_20261007_30.json']
    for p in sources:
        target=evidence / 'sources' / p.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        assert g.c.file_sha256(p)==g.c.file_sha256(target)
    now=datetime.now(UTC).isoformat()
    g.c.write_json(evidence / 'manifest.json',{'sealedAtUTC':now,'graphId':acceptance['graphId'],
        'filesSha256':{p.relative_to(evidence).as_posix():g.c.file_sha256(p) for p in evidence.rglob('*') if p.is_file()},
        'credentialsIncluded':False,'visualRegression':'INCONCLUSIVE_no_baseline'})
    g.c.write_json(output,{'passed':True,'checkedAtUTC':now,'engineeringTests':356,'HTTPChecks':15,'liveExportMatchesDetail':True,
        'nativeScreenshots':4,'orderedPathModes':['coauthors','methods'],'graphId':acceptance['graphId'],
        'immutableSourceSha256':previous['immutableSourceSha256'],'graphManifestSha256':previous['graphManifestSha256'],
        'testResultSha256':previous['testResultSha256'],'evidenceManifestSha256':g.c.file_sha256(evidence / 'manifest.json'),
        'modelRetrained':False,'testRepeated':False,'labelsModified':False,'databaseWritten':False,'qualityPromotionPassed':False,
        'reportExpansionPaused':True,'passwordWrittenToArtifacts':False})
    print(json.dumps({'passed':True,'engineeringTests':356,'HTTPChecks':15,'nativeScreenshots':4,'downloadMatchesLiveAPI':True}))


if __name__=='__main__': main()
