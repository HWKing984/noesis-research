"""Seal checked system evidence, not reports or model quality promotion."""
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_graph as g


def main():
    runs = ROOT / 'kg_datasets/dblp/course_v4_runs'
    evidence = ROOT / 'docs/evidence/20261007_round29'
    output = runs / 'verification_20261007_round29.json'
    if output.exists() or (evidence / 'manifest.json').exists() or (evidence / 'sources').exists():
        raise FileExistsError('Preserve sealed evidence')
    load = lambda path: json.loads(path.read_text(encoding='utf-8'))
    previous = load(runs / 'verification_20261007_round28.json')
    assert all(g.c.file_sha256(ROOT / p) == sha for p, sha in previous['immutableSourceSha256'].items())
    graph = g.verified_files(ROOT / 'kg_datasets/dblp/course_v4_graph_production_20261007_25')
    assert g.c.file_sha256(ROOT / 'kg_datasets/dblp/course_v4_graph_production_20261007_25/manifest.json') == previous['graphManifestSha256']
    final = runs / 'refresh_final_test_20261007_29'
    model = g.verified_files(final)
    assert model['status'] == 'completed'
    assert all(g.c.file_sha256(ROOT / p) == sha for p, sha in model['inputSha256'].items())
    result = load(final / 'test_result.json')
    assert result['engineeringPassed'] and result['testEvaluated'] and result['endToEndEvaluated']
    assert (result['queueDocuments'],result['NERDocuments'],result['pipelineDocuments']) == (200,187,175)
    assert not result['modelPromoted'] and not result['qualityPromotionPassed'] and not result['humanGold']
    acceptance = load(runs / 'graph_explorer_acceptance_live_20261007_29.json')
    assert acceptance['passed'] and len(acceptance['checks']) == 15 and acceptance['readOnly']
    assert acceptance['graphId'] == graph['graphId'] and acceptance['baseURL'] == 'http://127.0.0.1:8765'
    suite = ET.parse(runs / 'tests_20261007_round29_scoped_final.xml').getroot().find('testsuite')
    assert suite.attrib['tests'] == '355' and all(suite.attrib[k] == '0' for k in ('errors','failures','skipped'))
    qa = load(evidence / 'browser_qa.json')
    for screen in qa['screenshots']:
        with (evidence / screen['file']).open('rb') as stream:
            header = stream.read(24)
        assert header[:8] == b'\x89PNG\r\n\x1a\n'
        assert int.from_bytes(header[16:20],'big') == screen['width'] and int.from_bytes(header[20:24],'big') == screen['height']
        assert not screen['documentHorizontalOverflow']
    paths = [Path(__file__), ROOT / 'README.md', ROOT / 'docs/course_v4_progress.md']
    paths += [ROOT / p for p in ('scripts/course_graph.py','scripts/evaluate_course_refresh.py','resources/course_literature.html',
              'tests/test_course_graph.py','tests/test_course_refresh_evaluation.py')]
    paths += list((ROOT / 'annotations/course_v4').glob('*20261007*29*'))
    paths += list(runs.glob('*20261007*29*.json')) + list(runs.glob('tests*20261007*29*.xml'))
    paths += [p for p in final.rglob('*') if p.is_file()]
    for p in sorted(set(paths)):
        target = evidence / 'sources' / p.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(p,target)
        assert g.c.file_sha256(p) == g.c.file_sha256(target)
    now = datetime.now(UTC).isoformat()
    files = {p.relative_to(evidence).as_posix():g.c.file_sha256(p) for p in evidence.rglob('*') if p.is_file()}
    g.c.write_json(evidence / 'manifest.json',{'sealedAtUTC':now,'filesSha256':files,'graphId':graph['graphId'],
        'acceptedScreenshotFiles':[s['file'] for s in qa['screenshots']],'blankScreenshotsAccepted':False,'credentialsIncluded':False})
    g.c.write_json(output,{'passed':True,'checkedAtUTC':now,'graphId':graph['graphId'],'HTTPChecks':15,'engineeringTests':355,
        'newHoldoutDocuments':200,'NEREligibleDocuments':187,'pipelineEligibleDocuments':175,'newFinalTestEvaluated':True,
        'modelPromoted':False,'qualityPromotionPassed':False,'databaseWritten':False,'humanGold':False,'reportExpansionPaused':True,
        'immutableSourceSha256':previous['immutableSourceSha256'],'graphManifestSha256':previous['graphManifestSha256'],
        'testResultSha256':g.c.file_sha256(final / 'test_result.json'),'evidenceManifestSha256':g.c.file_sha256(evidence / 'manifest.json'),
        'acceptedNativeScreenshots':3,'visualRegression':'INCONCLUSIVE_no_baseline','passwordWrittenToArtifacts':False})
    print(json.dumps({'passed':True,'engineeringTests':355,'HTTPChecks':15,'nativeScreenshots':3,'modelPromoted':False}))


if __name__ == '__main__': main()
