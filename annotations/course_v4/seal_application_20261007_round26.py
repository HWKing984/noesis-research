"""Verify and seal saved live application evidence; never includes credentials."""
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
    evidence = ROOT / 'docs/evidence/20261007_round26'
    output = ROOT / 'kg_datasets/dblp/course_v4_runs/verification_20261007_round26.json'
    if output.exists() or (evidence / 'manifest.json').exists(): raise FileExistsError('Preserve sealed evidence')
    runs = ROOT / 'kg_datasets/dblp/course_v4_runs'
    bundle = ROOT / 'kg_datasets/dblp/course_v4_graph_production_20261007_25'
    manifest = g.verified_files(bundle)
    first = json.loads((runs / 'graph_import_20261007_26.json').read_text(encoding='utf-8'))
    again = json.loads((runs / 'graph_import_20261007_26_idempotent.json').read_text(encoding='utf-8'))
    acceptance = json.loads((runs / 'application_acceptance_20261007_26_final.json').read_text(encoding='utf-8'))
    failed = json.loads((runs / 'application_acceptance_20261007_26.json').read_text(encoding='utf-8'))
    sha = g.c.file_sha256(bundle / 'manifest.json')
    for receipt in (first, again):
        assert receipt['status'] == 'completed' and receipt['liveDatabaseImported']
        assert receipt['graphId'] == manifest['graphId'] and receipt['bundleManifestSha256'] == sha
        assert receipt['actualCounts'] == manifest['counts'] and not receipt['databaseReset']
    assert first['batchesCommitted'] == 913
    assert again['alreadyImported'] and again['batchesCommitted'] == 0
    assert acceptance['passed'] and acceptance['checkedRequests'] == len(acceptance['checks']) == 18
    assert acceptance['readOnly'] and not acceptance['modelQualityEvaluation']
    assert failed['status'] == 'failed' and 'Known dataset candidate' in failed['error']
    suite = ET.parse(runs / 'tests_20261007_round26_all.xml').getroot().find('testsuite')
    assert suite.attrib['tests'] == '350'
    assert all(suite.attrib[k] == '0' for k in ('failures', 'errors', 'skipped'))
    immutable = {
        'kg_datasets/dblp/course_v4_training_inputs_17/manifest.json': '44b4cded1460294e23d7b6d53303ddace56296fb1c0f2eacff4d009c667df9ef',
        'kg_datasets/dblp/course_v4_runs/corpus_production_20261007_25/manifest.json': '9021e341e8928ad44edbff58690110cc7f109570eeaa8c73573b4eb3b6776fa7',
        'kg_datasets/dblp/course_v4_graph_20261007_18_final/manifest.json': 'da86ef12159470ce99d8392e5a4d5f688ea1232a84ef433ab5b58e3c062186a7',
        'kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/checkpoint_epoch_04/model.safetensors': '968a594de551a1ab77a263a725fcdf487b8c559539f7452e2edeb8cf62c8d996',
        'kg_datasets/dblp/course_v4_runs/re_entity_development_20261006_15/checkpoint_epoch_03/model.safetensors': '082e9b3b280fe2bb9f4449205c801bcccaffbf1e661572406e5cb570e4ef6da1',
    }
    assert all(g.c.file_sha256(ROOT / path) == expected for path, expected in immutable.items())
    paths = [bundle / 'manifest.json', Path(__file__), ROOT / 'annotations/course_v4/check_application_20261007_round26.py',
             ROOT / 'scripts/course_graph.py', ROOT / 'resources/course_literature.html', ROOT / 'tests/test_course_graph.py']
    paths += [runs / name for name in ('graph_import_20261007_26.json', 'graph_import_20261007_26_idempotent.json',
              'application_acceptance_20261007_26.json', 'application_acceptance_20261007_26_final.json',
              'tests_graph_20261007_round26.xml', 'tests_20261007_round26_all.xml')]
    files = {}; source_hashes = {}
    for path in paths:
        relative = path.relative_to(ROOT)
        target = evidence / 'sources' / relative
        assert not target.exists()
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        source_hashes[relative.as_posix()] = g.c.file_sha256(path)
        assert g.c.file_sha256(target) == source_hashes[relative.as_posix()]
        files[target.relative_to(evidence).as_posix()] = source_hashes[relative.as_posix()]
    for name in ('01_neo4j_graph.jpeg', '02_live_search.png', '03_live_detail.png', '04_desktop_evidence.jpeg',
                 'graph_query.cypher', 'acceptance_initial_source.py'):
        path = evidence / name
        assert path.exists() and path.stat().st_size > 100
        if path.suffix in ('.png', '.jpeg'):
            with path.open('rb') as image:
                signature = image.read(8)
            assert signature.startswith(b'\x89PNG\r\n\x1a\n') if path.suffix == '.png' else signature.startswith(b'\xff\xd8')
        files[name] = g.c.file_sha256(path)
    now = datetime.now(UTC).isoformat()
    g.c.write_json(evidence / 'manifest.json', {'kind': 'actual_live_browser_screenshots_and_application_evidence',
        'sealedAtUTC': now, 'graphId': manifest['graphId'], 'filesSha256': files, 'sourceSha256': source_hashes,
        'credentialSaved': False, 'visualReviewPerformed': True,
        'screenshotNotice': 'Unmodified native MCP screenshot bytes; file-save time is not capture-start time. Basic graph layout, no optimized zoom screenshot claimed.',
        'captureFailures': ['Direct filePath rejected by tool workspace roots', 'Dynamic graph calls interrupted',
                            'Oversized node_repl data transfer rejected; native bytes transported in bounded chunks',
                            'Closed console stdin export failed PNG validation before any file creation']})
    docs = [ROOT / 'README.md'] + [ROOT / 'docs' / name for name in ('course_v4_live_application_round26.md',
        'course_v4_progress.md', 'course_v4_plan.md', 'course_v4_runbook.md', 'course_v4_report_evidence.md', 'course_v4_graph_application.md')]
    g.c.write_json(output, {'passed': True, 'checkedAtUTC': now, 'graphId': manifest['graphId'],
        'contentNodes': sum(manifest['counts']['nodes'].values()), 'edges': sum(manifest['counts']['edges'].values()),
        'HTTPChecks': 18, 'engineeringTests': 350, 'immutableSourceSha256': immutable,
        'evidenceManifestSha256': g.c.file_sha256(evidence / 'manifest.json'),
        'documentsSha256': {p.relative_to(ROOT).as_posix(): g.c.file_sha256(p) for p in docs},
        'liveDatabaseImported': True, 'modelRetrained': False, 'finalTestRepeated': False,
        'qualityPromotionPassed': False, 'passwordWrittenToArtifacts': False})
    print(json.dumps({'passed': True, 'sourceCopies': len(paths), 'screenshots': 4, 'HTTPChecks': 18}))


if __name__ == '__main__': main()
