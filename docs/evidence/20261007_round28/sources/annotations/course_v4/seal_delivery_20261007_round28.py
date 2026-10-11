"""Seal checked reports and a compact evidence ZIP, never include model weights or credentials."""
import json
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_graph as g


def main():
    runs = ROOT / 'kg_datasets/dblp/course_v4_runs'
    evidence = ROOT / 'docs/evidence/20261007_round28'
    output = runs / 'verification_20261007_round28.json'
    archive = runs / 'course_delivery_20261007_28.zip'
    if any(p.exists() for p in (output, archive, evidence / 'manifest.json', evidence / 'sources')):
        raise FileExistsError('Preserve sealed delivery; use a new version')
    old = json.loads((runs / 'verification_20261007_round27.json').read_text(encoding='utf-8'))
    assert all(g.c.file_sha256(ROOT / p) == sha for p, sha in old['immutableSourceSha256'].items())
    g.verified_files(ROOT / 'docs/evidence/20261007_round27')
    bundle = ROOT / 'kg_datasets/dblp/course_v4_graph_production_20261007_25'
    graph = g.verified_files(bundle)
    assert g.c.file_sha256(bundle / 'manifest.json') == old['graphManifestSha256']
    actual = json.loads((runs / 'delivery_checks_20261007_28_final/result.json').read_text(encoding='utf-8'))
    assert actual['passed'] and actual['status'] == 'completed' and len(actual['checks']) == 4
    assert actual['readOnlyDatabase'] and actual['sameDevContent'] and not actual['qualityPromotionPassed']
    assert actual['graphId'] == graph['graphId']
    suite = ET.parse(runs / 'tests_20261007_round28_final.xml').getroot().find('testsuite')
    assert int(suite.attrib['tests']) == 353
    assert all(suite.attrib[k] == '0' for k in ('failures', 'errors', 'skipped'))
    lock = json.loads((runs / 'refresh_lock_20261007_28.json').read_text(encoding='utf-8'))
    assert lock['holdoutDocuments'] == 200 and lock['labelsPending'] and not lock['newTestEvaluated']
    for p, sha in lock['inputSha256'].items(): assert g.c.file_sha256(ROOT / p) == sha, p
    candidates = {}
    for name, saved in actual['candidateDevelopment'].items():
        folder = runs / name
        g.verified_files(folder)
        weights = folder / saved['result']['bestCheckpoint'] / 'model.safetensors'
        assert g.c.file_sha256(weights) == saved['weightsSha256']
        candidates[name] = {'checkpoint': weights.relative_to(ROOT).as_posix(), 'sha256': saved['weightsSha256'],
                            'includedInArchive': False, 'testEvaluated': False, 'promoted': False}
    docs = [ROOT / 'README.md'] + [ROOT / 'docs' / n for n in (
        'course_complete_report_20261007.md', 'course_complete_report_20261007.html', 'course_v4_delivery_round28.md',
        'course_v4_progress.md', 'course_v4_plan.md', 'course_v4_runbook.md', 'course_v4_report_evidence.md',
        'course_v4_graph_application.md', 'course_v4_ner_development.md', 'course_v4_ner_test.md',
        'course_v4_relation_entity.md', 'course_v4_relation_test.md', 'course_v4_corpus_inference_round25.md',
        'course_v4_live_application_round26.md', 'course_v4_chinese_search_round27.md')]
    images = [ROOT / 'docs' / p for p in re.findall(r'^!\[[^\]]*\]\(([^)]+)\)$', docs[1].read_text(encoding='utf-8'), re.M)]
    assert len(images) == 5 and len(set(images)) == 5
    assert all(p.stat().st_size > 1000 and p.read_bytes().startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8')) for p in images)
    paths = docs + images + [ROOT / p for p in (
        'scripts/build_course_report.py', 'scripts/prepare_course_refresh.py', 'scripts/capture_delivery_round28.ps1',
        'scripts/train_course_ner.py', 'scripts/train_course_relation.py', 'scripts/course_weak.py',
        'scripts/course_graph.py', 'scripts/export_course_evidence.py', 'resources/course_demo_queries.cypher',
        'resources/course_v4_config.json', 'schemas/annotation_course_v4.schema.json',
        'resources/course_literature.html', 'tests/test_course_refresh.py', 'tests/test_course_report.py',
        'annotations/course_v4/check_delivery_20261007_round28.py',
        'annotations/course_v4/seal_delivery_20261007_round28.py')]
    paths += [runs / p for p in ('tests_20261007_round28_all.xml', 'tests_20261007_round28_final.xml',
        'refresh_lock_20261007_28.json', 'delivery_checks_20261007_28/result.json',
        'delivery_checks_20261007_28_final/result.json', 'delivery_checks_20261007_28_final/quality_marker_review.jsonl',
        'graph_import_20261007_26.json', 'graph_import_20261007_26_idempotent.json',
        'application_acceptance_20261007_26_final.json', 'chinese_acceptance_20261007_27.json')]
    for name in candidates:
        paths += [runs / name / p for p in ('manifest.json', 'development_result.json', 'epochs.json', 'steps.jsonl', 'status.json')]
    paths = list(dict.fromkeys(paths))
    assert all(p.is_file() and p.resolve().is_relative_to(ROOT) for p in paths)
    files = {p.relative_to(evidence).as_posix(): g.c.file_sha256(p) for p in evidence.iterdir() if p.is_file()}
    for path in paths:
        target = evidence / 'sources' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
        assert g.c.file_sha256(target) == g.c.file_sha256(path)
        files[target.relative_to(evidence).as_posix()] = g.c.file_sha256(target)
    now = datetime.now(UTC).isoformat()
    g.c.write_json(evidence / 'manifest.json', {'kind': 'course_report_and_candidate_development_delivery',
        'sealedAtUTC': now, 'filesSha256': files, 'candidateWeights': candidates, 'credentialSaved': False,
        'browserReview': {'sections': 9, 'tables': 8, 'loadedReportImages': 5, 'horizontalOverflow': False,
                          'printPaginationReviewed': False, 'docxCreated': False},
        'screenshotNotice': 'Native unedited browser captures; training PNG from actual logs, report PNG first viewport only.',
        'knownFailures': ['Initial live check required case-sensitive concept name; failed result and executed source preserved.',
                          'Browser tool filePath write rejected its workspace-root mapping; browser DOM checks returned inline, not saved by that tool.']})
    archive_paths = paths + [evidence / p for p in files] + [evidence / 'manifest.json']
    archive_paths = list(dict.fromkeys(archive_paths))
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as package:
        for path in archive_paths: package.write(path, path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(archive) as package:
        assert package.testzip() is None
        assert set(package.namelist()) == {p.relative_to(ROOT).as_posix() for p in archive_paths}
        import hashlib
        for path in archive_paths:
            assert hashlib.sha256(package.read(path.relative_to(ROOT).as_posix())).hexdigest() == g.c.file_sha256(path)
    g.c.write_json(output, {'passed': True, 'checkedAtUTC': now, 'engineeringTests': 353,
        'readOnlyNeo4jQueries': 4, 'graphId': actual['graphId'], 'immutableSourceSha256': old['immutableSourceSha256'],
        'graphManifestSha256': g.c.file_sha256(bundle / 'manifest.json'),
        'documentsSha256': {p.relative_to(ROOT).as_posix(): g.c.file_sha256(p) for p in docs},
        'evidenceManifestSha256': g.c.file_sha256(evidence / 'manifest.json'),
        'archiveSha256': g.c.file_sha256(archive), 'archiveMembers': len(archive_paths),
        'candidateWeights': candidates, 'holdoutDocuments': 200, 'holdoutLabelsPending': True,
        'modelRetrained': True, 'modelPromoted': False, 'newFinalTestEvaluated': False,
        'databaseWritten': False, 'qualityPromotionPassed': False, 'passwordWrittenToArtifacts': False})
    print(json.dumps({'passed': True, 'archiveMembers': len(archive_paths), 'archiveBytes': archive.stat().st_size}))


if __name__ == '__main__': main()
