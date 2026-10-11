"""Final59 engineering evidence verification; no reserved-test semantic access."""
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
import course_quality_app as app
from course_abstract_v1 import read, seal

g, c = app.g, app.g.c
RUNS = ROOT/'kg_datasets/dblp/course_v4_runs'
DATA = ROOT/'kg_datasets/dblp/course_abstract_supplement_relations_20261010_59_v2'
REPLAY = ROOT/'kg_datasets/dblp/course_abstract_supplement_relations_20261010_59_coverage_replay'
EVIDENCE = ROOT/'docs/evidence/20261010_round59_source_revision'
OUTPUT = RUNS/'system_verification_20261010_59'


def main():
    if OUTPUT.exists(): raise FileExistsError('Preserve final verification snapshot')
    tests = RUNS/'tests_all59_final.xml'; suites = list(ET.parse(tests).getroot().iter('testsuite'))
    totals = {k: sum(int(s.get(k, 0)) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
    assert totals == {'tests': 503, 'failures': 0, 'errors': 0, 'skipped': 0}, totals
    paths = [Path(__file__), Path(app.__file__), app.CONFIG, tests, RUNS/'coverage_source59.json', RUNS/'concept_app_acceptance_20261010_59.json',
             DATA/'manifest.json', REPLAY/'manifest.json', EVIDENCE/'manifest.json', EVIDENCE/'check.json', EVIDENCE/'captures.json',
             ROOT/'README.md', ROOT/'docs/system_status_round59.md', ROOT/'docs/course_v4_plan.md',
             ROOT/'scripts/revise_source_annotations.py', ROOT/'tests/test_source_annotation_revision.py',
             ROOT/'annotations/course_v4/check_source_revision_20261010_59.py', ROOT/'resources/course_source_annotation_revision_v1.json']
    reserved = ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl'
    expected_weights = {
        ROOT/'kg_datasets/dblp/course_v4_runs/ner_development_20261006_08/checkpoint_epoch_04/model.safetensors': '968a594de551a1ab77a263a725fcdf487b8c559539f7452e2edeb8cf62c8d996',
        ROOT/'kg_datasets/dblp/course_v4_runs/re_entity_development_20261006_15/checkpoint_epoch_03/model.safetensors': '082e9b3b280fe2bb9f4449205c801bcccaffbf1e661572406e5cb570e4ef6da1'}
    paths += [reserved]+list(expected_weights); hashes = {p: c.file_sha256(p) for p in paths}
    assert hashes[reserved] == '716b5cba5779d7c3b6e4bc404dba9579447b5c93768d56b0da28a70edc0bb3c1'
    assert all(hashes[p] == sha for p, sha in expected_weights.items())
    for folder in (DATA, REPLAY, EVIDENCE):
        manifest = g.verified_files(folder)
        assert all(c.file_sha256(ROOT/p) == sha for p, sha in manifest['inputSha256'].items())
    replay_files = ['ner_dev.jsonl', 'relation_dev.jsonl', 'additional_relation_dev.jsonl', 'full_relation_dev.jsonl', 'excluded_ner.jsonl', 'token_alignment.jsonl', 'summary.json']
    assert all(c.file_sha256(DATA/name) == c.file_sha256(REPLAY/name) for name in replay_files)
    check = read(EVIDENCE/'check.json'); assert check['status'] == 'passed' and check['inheritedRelationsExact'] == 88 and check['summary']['knownPairs'] == 111
    captures = read(EVIDENCE/'captures.json'); assert captures['status'] == 'completed' and len(captures['captures']) == 1
    for image in captures['captures']:
        assert c.file_sha256(EVIDENCE/image['image']) == image['sha256']
        assert c.file_sha256(EVIDENCE/image['sourcePage']) == image['sourcePageSha256']
    coverage = read(RUNS/'coverage_source59.json')['totals']
    assert coverage['covered_lines'] == coverage['num_statements'] == 81 and coverage['missing_lines'] == 0
    acceptance = read(RUNS/'concept_app_acceptance_20261010_59.json')
    assert acceptance['status'] == 'passed' and len(acceptance['checks']) == 33 and len(acceptance['oracleCases']) == 22
    assert acceptance['runtimeConfigUnchanged'] and acceptance['graphFilesUnchanged'] and acceptance['runtimeConfigSha256'] == hashes[app.CONFIG]
    with urlopen('http://127.0.0.1:8765/api/health', timeout=15) as response: health = json.load(response)['data']
    assert health['status'] == 'ready' and health['graphId'] == 'ai-literature-63686318d85cccb07afb' and health['scope']['bibliographyTitles'] == 20000
    assert health['appCodeSha256'] == hashes[Path(app.__file__)] == acceptance['appCodeSha256']
    ui = subprocess.run(['node', '--test', str(ROOT/'tests/test_course_ui.cjs')], capture_output=True, text=True, check=True)
    assert all(c.file_sha256(p) == sha for p, sha in hashes.items())
    OUTPUT.mkdir()
    for path in paths:
        if path == reserved or path.suffix == '.safetensors': continue
        target = OUTPUT/'sources'/path.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
    c.write_json(OUTPUT/'verification.json', {'status': 'passed', 'checkedAtUTC': datetime.now(UTC).isoformat(), 'pythonTests': totals,
        'nativeNodeUIExitCode': ui.returncode, 'nativeNodeUIOutput': ui.stdout, 'coverageStatements': '81/81_not_branch_or_model_accuracy',
        'sourceAmendmentCheck': check, 'liveGraphId': health['graphId'], 'liveStatus': health['status'], 'livePapers': 20000,
        'HTTPChecks': 33, 'oracleCases': 22, 'replaySemanticFilesByteEqual': replay_files,
        'reservedTestParsedOrCopied': False, 'reservedTestSha256': hashes[reserved], 'productionWeightsUnchanged': True,
        'trainingExecuted': False, 'modelPromoted': False, 'newAccuracyClaimed': False, 'humanGoldClaimed': False})
    seal(OUTPUT, paths)
    print({'verification': 'passed', 'pythonTests': totals, 'knownSupplementPairs': 111, 'livePapers': 20000})


if __name__ == '__main__': main()
