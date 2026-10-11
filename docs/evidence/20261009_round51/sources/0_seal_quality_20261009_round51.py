"""Archive quality iteration evidence with executable assertions, not a model promotion."""
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT/'scripts'))
import course_graph as g


def run():
    runs = ROOT/'kg_datasets/dblp/course_v4_runs'; evidence = ROOT/'docs/evidence/20261009_round51'
    if (evidence/'manifest.json').exists(): raise FileExistsError('Preserve sealed evidence')
    graph = g.verify_bundle(g.configured_bundle(ROOT/'resources/course_graph_quality_runtime.json'))
    acceptance = json.loads((runs/'quality_acceptance_20261009_51.json').read_text(encoding='utf-8'))
    assert acceptance['passed'] and len(acceptance['checks']) == 32 and not acceptance['qualityPromotionPassed']
    assert acceptance['graphCounts'] == graph['manifest']['counts'] and all(c['passed'] for c in acceptance['checks'])
    xml = runs/'tests_20261009_round51_final.xml'; suites = ET.parse(xml).getroot().findall('testsuite')
    totals = {key: sum(int(s.get(key, '0')) for s in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
    assert totals == {'tests': 385, 'failures': 0, 'errors': 0, 'skipped': 0}
    receipt = json.loads((evidence/'capture_receipt.json').read_text(encoding='utf-8-sig')); images = [r for r in receipt if 'Observed' in r]
    assert len(images) == 3 and all(not r['Observed']['overflow'] and r['Observed']['status'].startswith('10节点 / 11关系') for r in images)
    downloads = json.loads((evidence/'downloads/ai-literature-candidates.json').read_text(encoding='utf-8-sig'))
    assert len(downloads['items']) == 1 and downloads['items'][0]['graphId'] == graph['manifest']['graphId']
    assert downloads['items'][0]['data']['publication']['publicationId'] == 'conf/3dim/VavilalaVF25'
    assert len(downloads['items'][0]['data']['assertions']) == 1
    sources = [Path(__file__), ROOT/'annotations/course_v4/check_quality_20261009_round51.py']
    sources += [ROOT/'scripts'/name for name in ('refine_author_identities.py', 'refine_author_crosswalk.py', 'normalize_course_concepts.py', 'course_quality_app.py', 'course_relation_evidence.py', 'evaluate_relation_evidence.py')]
    sources += [ROOT/'tests'/name for name in ('test_refine_author_identities.py', 'test_refine_author_crosswalk.py', 'test_normalize_course_concepts.py', 'test_course_quality_app.py', 'test_relation_evidence.py', 'test_relation_evidence_metrics.py')]
    sources += [ROOT/'resources'/name for name in ('course_concept_v2.json', 'course_relation_evidence_v1.json', 'course_graph_quality_runtime.json', 'course_graph_runtime.json', 'course_literature.html')]
    sources += [ROOT/'docs'/name for name in ('system_status_round51.md', 'quality_iteration_round51.md', 'course_v4_plan.md', 'course_v4_runbook.md', 'model_optimization_abstract_v1.md', 'status_log.md')]+[ROOT/'README.md']
    sources += [runs/name for name in ('quality_acceptance_20261009_51.json', 'import_quality_20261009_51.json', 'tests_20261009_round51_complete.xml', 'tests_20261009_round51_final.xml')]
    sources += [ROOT/'annotations/course_v4/capture_system_20261007_round29.ps1']
    for folder in ('course_v4_identity_20261009_51', 'course_v4_identity_crosswalk_20261009_51', 'course_v4_graph_authors_20261009_51', 'course_v4_graph_quality_20261009_51'):
        parent = ROOT/'kg_datasets/dblp'/folder; manifest = g.verified_files(parent)
        assert all(g.c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
        sources.append(parent/'manifest.json')
        for name in ('summary.json', 'resolution_summary.json'):
            if (parent/name).exists(): sources.append(parent/name)
    model = runs/'relation_evidence_development_20261009_51'; manifest = g.verified_files(model)
    assert all(g.c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    sources += [model/name for name in ('manifest.json', 'selection_lock.json', 'development_result.json', 'status.json')]
    snapshots = evidence/'sources'; snapshots.mkdir()
    for i, path in enumerate(sources): shutil.copy2(path, snapshots/(str(i)+'_'+path.name))
    with urlopen('http://127.0.0.1:8766/api/health', timeout=30) as response: health = json.load(response)
    assert health['data']['graphId'] == graph['manifest']['graphId'] and health['data']['appCodeSha256'] == g.c.file_sha256(ROOT/'scripts/course_quality_app.py')
    g.c.write_json(evidence/'health.json', health)
    g.c.write_json(evidence/'browser_observation.json', {'source': 'actual_chrome_devtools_inline_observation', 'liveURL': 'http://127.0.0.1:8766/',
        'observedLLMResults': 20, 'aliasVersion': 'typed_controlled_aliases_v2', 'inputs': 8, 'consoleErrorsOrWarningsObserved': 0,
        'networkRequestsObserved': 9, 'statusesObserved': [200, 204], 'completeAccessibilityAudit': False,
        'notice': 'Chrome page observation plus separately captured actual Edge screenshots/downloads; not synthesized UI or a full browser regression suite.'})
    result = {'passed': True, 'engineeringTests': totals, 'applicationChecks': 32, 'graphId': graph['manifest']['graphId'],
        'graphCounts': graph['manifest']['counts'], 'liveImportCompleted': True, 'originalDefaultGraphUnchanged': True,
        'recoveredSignatures': 2, 'remainingUnresolvedSignatures': 9062, 'conceptsGrouped': 39,
        'modelPromoted': False, 'qualityPromotionPassed': False, 'trainingExecuted': False, 'testContentConsumed': False,
        'authorFullyDisambiguated': False, 'conceptsGloballyCanonicalized': False, 'modelReliabilityResolved': False,
        'notice': 'Quality iteration and preserved-evidence checks passed; none of these flags claim complete semantic quality.'}
    target = runs/'verification_20261009_round51.json'
    if target.exists(): raise FileExistsError('Preserve verification')
    g.c.write_json(target, result); shutil.copy2(target, evidence/target.name)
    g.c.write_json(evidence/'manifest.json', {'kind': 'actual_quality_iteration_application_and_model_diagnostic',
        'inputSha256': {p.relative_to(ROOT).as_posix(): g.c.file_sha256(p) for p in sources},
        'filesSha256': {p.relative_to(evidence).as_posix(): g.c.file_sha256(p) for p in evidence.rglob('*') if p.is_file()}})
    g.verified_files(evidence); print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': run()
