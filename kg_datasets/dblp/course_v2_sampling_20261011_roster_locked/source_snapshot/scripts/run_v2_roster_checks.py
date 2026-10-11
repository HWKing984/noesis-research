"""Collect and execute actual roster/sampling/admission tests, retaining failures."""
import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import prepare_v2_sampling as p
from run_v2_admission_checks import junit

ROOT=p.ROOT
TESTS=('tests/test_v2_sampling.py','tests/test_v2_training_roster.py','tests/test_v2_admission.py',
       'tests/test_v2_dev_collection.py')
SOURCES=tuple(dict.fromkeys((*p.SOURCES,*TESTS,'scripts/run_v2_roster_checks.py',
                            'scripts/collect_v2_dev.py','scripts/collect_course_abstract_pages.py',
                            'scripts/run_v2_admission_checks.py','scripts/harden_v2_identity.py')))


def run(folder):
    folder=Path(folder).resolve()
    if folder.exists(): raise FileExistsError('Preserve previous test execution')
    env=dict(os.environ)
    for key in ('PYTEST_ADDOPTS','PYTEST_PLUGINS'): env.pop(key,None)
    env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
    hashes={name:p.sha(ROOT/name) for name in SOURCES}
    collect=[sys.executable,'-B','-m','pytest','--collect-only','-q',*TESTS]
    process=subprocess.run(collect,cwd=ROOT,env=env,capture_output=True,text=True)
    if process.returncode: raise ValueError('Test collection failed: '+process.stdout+process.stderr)
    nodes=sorted(line.strip() for line in process.stdout.splitlines() if line.startswith('tests/') and '::' in line)
    if not nodes or len(nodes)!=len(set(nodes)): raise ValueError('Empty/duplicate test inventory')
    folder.mkdir(parents=True)
    inventory={'testFiles':list(TESTS),'nodeIds':nodes,'sourceSha256':hashes}
    p.write(folder/'test_inventory.json',inventory)
    started=datetime.now(UTC)
    command=[sys.executable,'-B','-m','pytest','-q','-p','no:cacheprovider',
             '-o','junit_suite_name=v2_roster','-o','junit_family=xunit2',*TESTS,
             '--junitxml='+str(folder/'checks.xml')]
    receipt={'status':'running','runId':str(uuid.uuid4()),'startedAtUTC':started.isoformat(),
             'command':command,'collectionCommand':collect,'cwd':str(ROOT),
             'pythonVersion':platform.python_version(),'sourceSha256':hashes,
             'inventorySha256':p.sha(folder/'test_inventory.json'),'collectedTests':len(nodes),
             'notice':'Actual local subprocess execution; engineering tests are not semantic model accuracy.'}
    p.write(folder/'run_receipt.json',receipt)
    try:
        with (folder/'pytest.log').open('w',encoding='utf-8') as log:
            process=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        receipt['exitCode']=process.returncode
        expected=[('tests.'+Path(n.split('::')[0]).stem,n.split('::',1)[1]) for n in nodes]
        receipt['actualTests']=junit(folder/'checks.xml',expected)
        if process.returncode or any(p.sha(ROOT/n)!=h for n,h in hashes.items()):
            raise ValueError('Test failed or tested sources changed')
        receipt.update(status='passed',junitSha256=p.sha(folder/'checks.xml'),logSha256=p.sha(folder/'pytest.log'))
    except Exception as error:
        receipt.update(status='failed',error=str(error));raise
    finally:
        ended=datetime.now(UTC)
        receipt.update(endedAtUTC=ended.isoformat(),wallSeconds=(ended-started).total_seconds())
        p.write(folder/'run_receipt.json',receipt)
    return receipt


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(parser.parse_args().output),ensure_ascii=False,indent=2))
