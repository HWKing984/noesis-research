"""Execute frozen V2 test IDs; external passing XML is never a build authority."""
import argparse
import json
import math
import os
import platform
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harden_v2_identity import read, sha

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT/'resources/course_v2_admission_test_inventory_v1.json'
TESTS = tuple('tests/'+name+'.py' for name in ('test_v2_evidence_pilot', 'test_v2_semantic_revision',
    'test_v2_entity_completion', 'test_v2_priority_revision', 'test_v2_supervision_protocol',
    'test_v2_identity_guard', 'test_v2_admission'))


def junit(path, expected):
    root = ET.parse(path).getroot(); cases = list(root.iter('testcase')); suites = list(root.iter('testsuite'))
    actual = [(r.get('classname'), r.get('name')) for r in cases]
    if not cases or len(actual) != len(set(actual)) or set(actual) != set(map(tuple, expected)): raise ValueError('JUnit test identity inventory mismatch')
    for suite in suites + ([root] if root.tag == 'testsuites' and 'tests' in root.attrib else []):
        if int(suite.get('tests', '-1')) != len(list(suite.iter('testcase'))): raise ValueError('JUnit declared/actual count mismatch')
        if any(int(suite.get(k, '-1')) != 0 for k in ('failures', 'errors', 'skipped')): raise ValueError('JUnit is not fully passing')
    if not suites or any(r.find(k) is not None for r in cases for k in ('failure', 'error', 'skipped')): raise ValueError('JUnit failing testcase')
    for suite in suites:
        stamp = datetime.fromisoformat(suite.attrib['timestamp'])
        if stamp.utcoffset() is None: raise ValueError('JUnit timestamp must have timezone')
        if not suite.get('hostname') or not math.isfinite(float(suite.attrib['time'])) or float(suite.attrib['time']) < 0: raise ValueError('JUnit missing runtime metadata')
    return len(cases)


def collected(command, env):
    process = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
    if process.returncode: raise ValueError('pytest collection failed: '+process.stdout+process.stderr)
    return sorted(line.strip() for line in process.stdout.splitlines() if line.strip().startswith('tests/') and '::' in line)


def verify(folder, inventory, source_root):
    folder = Path(folder); source_root = Path(source_root); receipt = read(folder/'run_receipt.json')
    if (receipt['status'] != 'passed' or receipt['exitCode'] != 0 or receipt['inventorySha256'] != sha(folder/'test_inventory.json')
            or read(folder/'test_inventory.json') != inventory or receipt['sourceSha256'] != inventory['sourceSha256']): raise ValueError('Unbound controlled test receipt')
    if any(sha(source_root/p) != h for p, h in inventory['sourceSha256'].items()): raise ValueError('Tested source snapshot drift')
    if receipt['testFiles'] != list(TESTS) or receipt['collectedNodeIds'] != inventory['nodeIds']: raise ValueError('Test execution inventory drift')
    if (receipt['command'][1:] != ['-m', 'pytest', '-q', '-o', 'junit_suite_name=v2_admission', '-o', 'junit_family=xunit2',
            *TESTS, '--junitxml='+receipt['junitPath']] or not receipt['pythonVersion'] or not receipt['pytestVersion']): raise ValueError('Uncontrolled test invocation')
    if (datetime.fromisoformat(receipt['endedAtUTC']) <= datetime.fromisoformat(receipt['startedAtUTC'])
            or receipt['wallSeconds'] <= 0 or not receipt['runId']): raise ValueError('Invalid test runtime interval')
    if sha(folder/'checks.xml') != receipt['junitSha256'] or sha(folder/'pytest.log') != receipt['logSha256']: raise ValueError('Test execution artifact drift')
    start = datetime.fromisoformat(receipt['startedAtUTC']); end = datetime.fromisoformat(receipt['endedAtUTC'])
    for suite in ET.parse(folder/'checks.xml').getroot().iter('testsuite'):
        stamp = datetime.fromisoformat(suite.attrib['timestamp'])
        if suite.get('name') != 'v2_admission' or stamp.utcoffset() is None or not start <= stamp <= end: raise ValueError('JUnit/runtime interval mismatch')
    expected = [('tests.'+Path(n.split('::')[0]).stem, n.split('::', 1)[1]) for n in inventory['nodeIds']]
    count = junit(folder/'checks.xml', expected)
    if receipt['actualTests'] != count: raise ValueError('Receipt count mismatch')
    return count


def run(folder):
    folder = Path(folder).resolve()
    if folder.exists(): raise FileExistsError('Preserve prior test execution: '+str(folder))
    inventory = read(INVENTORY)
    if inventory['testFiles'] != list(TESTS) or any(sha(ROOT/p) != h for p,h in inventory['sourceSha256'].items()): raise ValueError('Frozen test/source inventory drift')
    env = dict(os.environ); env.pop('PYTEST_ADDOPTS', None); env.pop('PYTEST_PLUGINS', None); env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] = '1'
    collect_command = [sys.executable, '-m', 'pytest', '--collect-only', '-q', *TESTS]
    nodeids = collected(collect_command, env)
    if nodeids != inventory['nodeIds']: raise ValueError('Collected test identities differ from fixed inventory')
    folder.mkdir(parents=True); (folder/'test_inventory.json').write_bytes(INVENTORY.read_bytes())
    started = datetime.now(UTC); command = [sys.executable, '-m', 'pytest', '-q', '-o', 'junit_suite_name=v2_admission', '-o', 'junit_family=xunit2',
        *TESTS, '--junitxml='+str(folder/'checks.xml')]
    receipt = {'status':'running', 'runId':str(uuid.uuid4()), 'startedAtUTC':started.isoformat(), 'command':command,
        'collectionCommand':collect_command, 'cwd':str(ROOT), 'testFiles':list(TESTS), 'collectedNodeIds':nodeids,
        'sourceSha256':inventory['sourceSha256'], 'inventorySha256':sha(INVENTORY), 'junitPath':str(folder/'checks.xml'),
        'pythonVersion':platform.python_version(), 'pytestVersion':version('pytest'), 'platform':platform.platform(),
        'notice':'Local controlled execution record, not cryptographic attestation against an operator who rewrites all artifacts.'}
    write = lambda: (folder/'run_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    write(); print('Running frozen V2 suite: '+str(len(nodeids))+' test IDs.', flush=True)
    try:
        with (folder/'pytest.log').open('w', encoding='utf-8') as log:
            process = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        receipt.update(exitCode=process.returncode, junitSha256=sha(folder/'checks.xml'), logSha256=sha(folder/'pytest.log'))
        expected = [('tests.'+Path(n.split('::')[0]).stem, n.split('::', 1)[1]) for n in nodeids]
        receipt['actualTests'] = junit(folder/'checks.xml', expected)
        if process.returncode or any(sha(ROOT/p) != h for p,h in inventory['sourceSha256'].items()): raise ValueError('Test process/source drift')
        receipt['status'] = 'passed'
    except Exception as error:
        receipt.update(status='failed', error=str(error)); raise
    finally:
        ended = datetime.now(UTC); receipt.update(endedAtUTC=ended.isoformat(), wallSeconds=(ended-started).total_seconds()); write()
    verify(folder, inventory, ROOT); return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False); parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output), ensure_ascii=False, indent=2))
