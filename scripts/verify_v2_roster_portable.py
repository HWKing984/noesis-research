"""Retain actual independent archive replay and Windows long-path failures."""
import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import prepare_v2_sampling as p


def replay(short_root,long_root):
    short_root=Path(short_root).resolve();long_root=Path(long_root).resolve()
    archive=p.ROOT/'outputs/v2_roster_and_dev_audit_20261011_v2.zip'
    package=p.sampling.read(p.ROOT/'outputs/v2_roster_and_dev_audit_20261011_v2_receipt.json')
    output=p.ROOT/'outputs/v2_roster_portable_replay_20261011.json'
    if output.exists():raise FileExistsError('Preserve actual replay receipt')
    receipt={'status':'running','archiveSha256':p.sha(archive),'startedAtUTC':datetime.now(UTC).isoformat(),
        'shortExtractionRoot':str(short_root),'longExtractionRoot':str(long_root),
        'commands':[],'trainingAuthorized':False,'evaluationAuthorized':False}
    if receipt['archiveSha256']!=package['archiveSha256']:raise ValueError('Sealed archive changed')
    try:
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None:raise ValueError('Archive CRC failed')
            missing=[]
            for name,value in package['filesSha256'].items():
                target=(short_root/name).resolve()
                if not target.is_relative_to(short_root) or p.sha(target)!=value or hashlib.sha256(z.read(name)).hexdigest()!=value:
                    raise ValueError('Independent extraction/file SHA mismatch: '+name)
                if not (long_root/name).is_file():missing.append({'file':name,'fullPathLength':len(str(long_root/name))})
        receipt.update(independentMemberHashChecks=len(package['filesSha256']),
            longPathReplay={'status':'failed_missing_extraction_files_not_bypassed',
                'missingFiles':missing,'reason':'Windows Expand-Archive omitted deeply nested paths in the long destination. Use a short extraction root; preserve original manifest and missing-file failures.'})
        bundle='kg_datasets/dblp/course_v2_sampling_20261011_roster_locked_v2'
        snapshot=bundle+'/source_snapshot/scripts/'
        commands=[[sys.executable,'-I','-B',snapshot+'prepare_v2_sampling.py','--verify',bundle],
            [sys.executable,'-I','-B',snapshot+'collect_v2_dev.py','--bundle',bundle,'--verify','kg_datasets/dblp/course_v2_dev_sources_20261011']]
        for command in commands:
            proc=subprocess.run(command,cwd=short_root,capture_output=True,text=True)
            record={'command':command,'cwd':str(short_root),'exitCode':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr}
            receipt['commands'].append(record)
            if proc.returncode:raise ValueError('Portable validator failed')
            result=json.loads(proc.stdout)
            if result.get('trainingAuthorized') is not False or result.get('evaluationAuthorized') is not False:
                raise ValueError('Portable replay cannot authorize training/evaluation')
        checks=long_root/'outputs/independent_replay_checks'
        run=p.sampling.read(checks/'run_receipt.json')
        if run['status']!='passed' or run['actualTests']!=96 or run['exitCode']!=0:
            raise ValueError('Independent pytest replay failed')
        saved=p.ROOT/'outputs/v2_roster_independent_checks_20261011'
        if saved.exists():raise FileExistsError('Preserve independent checks')
        import shutil
        shutil.copytree(checks,saved)
        receipt.update(status='passed',independentPytestCases=96,independentPytestRunId=run['runId'],
            independentTestReceiptSha256=p.sha(saved/'run_receipt.json'),
            notice='Same 96 engineering cases replayed, not 192 distinct checks; no model inference, training or new test text read.')
    except Exception as error:
        receipt.update(status='failed',errorType=type(error).__name__,error=str(error));raise
    finally:
        receipt['endedAtUTC']=datetime.now(UTC).isoformat();p.write(output,receipt)
    return {k:receipt[k] for k in ('status','archiveSha256','independentMemberHashChecks','independentPytestCases','independentPytestRunId')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--short-root',type=Path,required=True);parser.add_argument('--long-root',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(replay(args.short_root,args.long_root),ensure_ascii=False,indent=2))
