"""Seal actual Chinese-search evidence while preserving prior artifacts."""
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
    evidence = ROOT / 'docs/evidence/20261007_round27'
    runs = ROOT / 'kg_datasets/dblp/course_v4_runs'
    output = runs / 'verification_20261007_round27.json'
    if output.exists() or (evidence / 'manifest.json').exists(): raise FileExistsError('Preserve sealed evidence')
    old = json.loads((runs / 'verification_20261007_round26.json').read_text(encoding='utf-8'))
    for path, sha in old['immutableSourceSha256'].items():
        assert g.c.file_sha256(ROOT / path) == sha, path
    # Verify historical source copies, not documents intentionally updated in this iteration.
    g.verified_files(ROOT / 'docs/evidence/20261007_round26')
    bundle = ROOT / 'kg_datasets/dblp/course_v4_graph_production_20261007_25'
    graph = g.verified_files(bundle)
    assert g.c.file_sha256(bundle / 'manifest.json') == '246e695ec3aa0ae32af5287955f9acf1a6e8502ca1c56078b8538a34eb30126b'
    actual = json.loads((runs / 'chinese_acceptance_20261007_27.json').read_text(encoding='utf-8'))
    assert actual['status'] == 'completed' and actual['passed'] and actual['readOnly']
    assert not actual['modelQualityEvaluation'] and actual['checkedRequests'] == len(actual['checks']) == 18
    assert actual['graphId'] == graph['graphId'] and len(actual['comparisons']) == 5
    assert all(c['orderedFirstPageEqual'] and not c['allPagesCompared'] for c in actual['comparisons'])
    for filename, count in [('tests_graph_20261007_round27.xml', 9), ('tests_20261007_round27_tests_only.xml', 351)]:
        suite = ET.parse(runs / filename).getroot().find('testsuite')
        assert int(suite.attrib['tests']) == count
        assert all(suite.attrib[k] == '0' for k in ('failures', 'errors', 'skipped'))
    failed = ET.parse(runs / 'tests_20261007_round27_all.xml').getroot().find('testsuite')
    assert failed.attrib['errors'] == '7'
    image = evidence / '01_chinese_search_detail.jpeg'
    assert image.stat().st_size > 1000 and image.read_bytes().startswith(b'\xff\xd8')
    paths = [ROOT / p for p in ('scripts/course_graph.py', 'resources/course_literature.html', 'tests/test_course_graph.py',
             'annotations/course_v4/check_chinese_20261007_round27.py', 'annotations/course_v4/seal_chinese_20261007_round27.py')]
    paths += [runs / name for name in ('chinese_acceptance_20261007_27.json', 'tests_graph_20261007_round27.xml',
                                       'tests_20261007_round27_tests_only.xml', 'tests_20261007_round27_all.xml')]
    files = {image.name: g.c.file_sha256(image)}
    for path in paths:
        target = evidence / 'sources' / path.relative_to(ROOT)
        if target.exists(): raise FileExistsError('Preserve source copies')
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        assert g.c.file_sha256(target) == g.c.file_sha256(path)
        files[target.relative_to(evidence).as_posix()] = g.c.file_sha256(target)
    now = datetime.now(UTC).isoformat()
    g.c.write_json(evidence / 'manifest.json', {'kind': 'actual_chinese_search_application_evidence',
        'graphId': graph['graphId'], 'sealedAtUTC': now, 'filesSha256': files, 'credentialSaved': False,
        'screenshotNotice': 'Unmodified native browser JPEG, 1440x1100 viewport, full-page capture; visually reviewed.',
        'knownFailure': 'Root pytest collected archived duplicate test modules: 7 collection errors; preserved XML.'})
    docs = [ROOT / 'README.md'] + [ROOT / 'docs' / name for name in ('course_v4_chinese_search_round27.md',
        'course_v4_progress.md', 'course_v4_plan.md', 'course_v4_runbook.md', 'course_v4_report_evidence.md', 'course_v4_graph_application.md')]
    g.c.write_json(output, {'passed': True, 'checkedAtUTC': now, 'graphId': graph['graphId'],
        'HTTPChecks': 18, 'engineeringTests': 351, 'aliasEntries': len(g.TERMINOLOGY['aliases']),
        'immutableSourceSha256': old['immutableSourceSha256'],
        'graphManifestSha256': g.c.file_sha256(bundle / 'manifest.json'),
        'evidenceManifestSha256': g.c.file_sha256(evidence / 'manifest.json'),
        'documentsSha256': {p.relative_to(ROOT).as_posix(): g.c.file_sha256(p) for p in docs},
        'modelRetrained': False, 'finalTestRepeated': False, 'databaseWritten': False,
        'qualityPromotionPassed': False, 'passwordWrittenToArtifacts': False})
    print(json.dumps({'passed': True, 'sourceCopies': len(paths), 'screenshots': 1, 'HTTPChecks': 18}))


if __name__ == '__main__': main()
