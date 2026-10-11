"""Verify current round58 handoff, keeping historical failures and tests untouched."""
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
output = ROOT/'kg_datasets/dblp/course_v4_runs/system_verification_20261010_58'
if output.exists(): raise FileExistsError('Preserve previous system verification')
tests = ROOT/'kg_datasets/dblp/course_v4_runs/tests_all58_v3config.xml'
suites = list(ET.parse(tests).getroot().iter('testsuite'))
totals = {k: sum(int(s.get(k, 0)) for s in suites) for k in ('tests', 'failures', 'errors', 'skipped')}
assert totals == {'tests': 487, 'failures': 0, 'errors': 0, 'skipped': 0}, totals
bundle = g.configured_bundle(app.CONFIG); manifest = g.verified_files(bundle)
run = ROOT/'kg_datasets/dblp/course_v4_runs'
imported = read(run/'concept_import_20261010_58.json')
acceptance = read(run/'concept_app_acceptance_20261010_58_v3config.json')
assert imported['status'] == 'completed' and imported['actualCounts'] == manifest['counts']
assert acceptance['status'] == 'passed' and acceptance['runtimeConfigUnchanged'] and acceptance['graphFilesUnchanged']
assert acceptance['runtimeConfigSha256'] == c.file_sha256(app.CONFIG)
with urlopen('http://127.0.0.1:8765/api/health', timeout=15) as response: health = json.load(response)['data']
assert health['status'] == 'ready' and health['source'] == 'live_neo4j' and health['graphId'] == manifest['graphId']
assert health['appCodeSha256'] == c.file_sha256(Path(app.__file__)) == acceptance['appCodeSha256']
assert health['scope']['bibliographyTitles'] == 20000 and health['liveImportCompleted']
for folder in ('course_v4_identity_evidence_20261010_58', 'course_v4_runs/pretrained_ner_comparison_20261010_58_ready', 'course_v4_runs/pretrained_ner_comparison_20261010_58_replay'):
    checked = g.verified_files(ROOT/'kg_datasets/dblp'/folder)
    assert all(c.file_sha256(ROOT/p) == sha for p, sha in checked['inputSha256'].items())
captures = ROOT/'docs/evidence/20261010_round58_live_cdp_v3config/captures.json'; pictures = read(captures)
assert pictures['status'] == 'passed' and len(pictures['captures']) == 3 and pictures['appCodeSha256'] == health['appCodeSha256']
assert all(c.file_sha256(Path(p['file'])) == p['sha256'] and not p['observed']['overflow'] for p in pictures['captures'])
assert read(run/'pretrained_runtime_provenance_20261010_58/check.json')['status'] == 'passed'
ui = subprocess.run(['node', '--test', str(ROOT/'tests/test_course_ui.cjs')], capture_output=True, text=True, check=True)
paths = [Path(__file__), Path(app.__file__), app.CONFIG, ROOT/'resources/course_graph_quality_runtime.json',
         ROOT/'tests/conftest.py', ROOT/'tests/test_course_runtime_versions.py', tests, bundle/'manifest.json', captures,
         run/'concept_import_20261010_58.json', run/'concept_app_acceptance_20261010_58_v3config.json',
         run/'pretrained_runtime_provenance_20261010_58/check.json', ROOT/'README.md', ROOT/'docs/course_v4_plan.md', ROOT/'docs/system_status_round58.md',
         ROOT/'resources/course_literature.html', ROOT/'tests/test_course_ui.cjs', ROOT/'annotations/course_v4/capture_concepts_20261010_58.ps1']
output.mkdir()
for path in paths:
    target = output/'sources'/path.relative_to(ROOT); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(path, target)
c.write_json(output/'verification.json', {'status': 'passed', 'checkedAtUTC': datetime.now(UTC).isoformat(),
    'pythonTests': totals, 'nativeNodeUIExitCode': ui.returncode, 'nativeNodeUIOutput': ui.stdout,
    'liveHealth': health, 'databaseCounts': imported['actualCounts'], 'modelPromoted': False,
    'reservedTestParsed': False, 'humanGoldClaimed': False, 'independentSemanticAccuracyVerified': False})
seal(output, paths)
print({'verification': 'passed', 'pythonTests': totals, 'liveGraph': manifest['graphId']}, flush=True)
