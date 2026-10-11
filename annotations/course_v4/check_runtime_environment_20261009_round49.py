"""Save real read-only runtime diagnostics after the temporary console was stopped."""
import json
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(ROOT/'scripts'))
import course_weak as c

INSTANCE=Path('D:/DevData/neo4j-desktop-data/Application/Data/dbmss/dbms-4da0e003-b3f9-4536-bacc-c65d6ab4df34')
RUNS=ROOT/'kg_datasets/dblp/course_v4_runs'


def main():
    output=RUNS/'runtime_environment_20261009_round49.json'
    if output.exists(): raise FileExistsError('Preserve runtime diagnostic evidence')
    assert INSTANCE.is_dir()
    state={'checkedAtUTC':datetime.now(UTC).isoformat(),'instancePath':str(INSTANCE),'modelPromoted':False,'graphWritten':False,'licenseAcceptedByAgent':False,'javaConfigChanged':False,'onlineAcceptanceExecuted':False,'commands':[]}
    for arguments in ([str(Path(os.environ['JAVA_HOME'])/'bin/java.exe'),'-version'],[os.environ['COMSPEC'],'/d','/c',str(INSTANCE/'bin/neo4j-admin.bat'),'server','license'],[os.environ['COMSPEC'],'/d','/c',str(INSTANCE/'bin/neo4j.bat'),'status']):
        result=subprocess.run(arguments,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
        state['commands'].append({'arguments':arguments,'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    listening=[]
    for port in (7474,7687,8765):
        with socket.socket() as connection:
            connection.settimeout(1); listening.append({'port':port,'listening':connection.connect_ex(('127.0.0.1',port))==0})
    logs=[RUNS/('neo4j_console_20261009_round49.'+kind+'.log') for kind in ('stdout','stderr')]
    state['ports']=listening; state['logSha256']={p.relative_to(ROOT).as_posix():c.file_sha256(p) for p in logs}
    state['shutdownConfirmed']='Stopped.' in logs[0].read_text(encoding='utf-8',errors='replace') and not any(p['listening'] for p in listening)
    state['blockingConditions']=['CLI license check says No license is accepted','Installed Java 23 is unsupported; CLI requests Java 21 or 25','Existing graph/search online acceptance has not been rerun']
    assert state['shutdownConfirmed'] and 'No license is accepted' in state['commands'][1]['stdout'] and 'unsupported Java runtime' in state['commands'][1]['stderr']
    state['status']='blocked_runtime_environment_not_model_failure'; c.write_json(output,state)
    print(json.dumps({'status':state['status'],'shutdownConfirmed':state['shutdownConfirmed'],'onlineAcceptanceExecuted':False}))


if __name__=='__main__': main()
