"""Repair two admission gates, run the fixed suite, preserve every prior data byte."""
import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import course_v2_admission as admission
import harden_v2_identity as parent
import run_v2_admission_checks as checks

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT/'resources/course_v2_admission_v1.json'
OUTPUT = ROOT/'kg_datasets/dblp/course_v2_admission_20261010'
COPIED = parent.CORE + ('historical_exclusions.jsonl', 'identity_alias_index.json', 'identity_coverage.json',
    'identity_regression.json', 'evaluation_readiness.json', 'production_protection.json')
STATUS = 'admission_gates_repaired_missing_negatives_and_new_evaluation_not_training_ready'


def build(output=OUTPUT):
    output=Path(output).resolve()
    if output.exists():raise FileExistsError(output)
    config=parent.read(CONTRACT);old=ROOT/config['parent'];inventory=parent.read(checks.INVENTORY)
    if config['version']!='course_v2_admission_v1' or any(config[k] is not False for k in parent.previous.FLAGS):raise ValueError('Data-only contract drift')
    if parent.sha(old/'manifest.json')!=config['parentManifestSha256']:raise ValueError('Parent binding drift')
    replay=parent.verify(old);protection=parent.read(old/'production_protection.json')
    inputs={p:parent.sha(ROOT/p) for p in inventory['sourceSha256']}
    inputs[checks.INVENTORY.relative_to(ROOT).as_posix()]=parent.sha(checks.INVENTORY)
    inputs[config['parent']+'/manifest.json']=config['parentManifestSha256']
    for field in ('externalAudit','externalResults'):
        if parent.sha(config[field])!=config[field+'Sha256']:raise ValueError('External audit drift')
        inputs[config[field]]=config[field+'Sha256']
    if any(parent.sha(ROOT/p)!=h for p,h in protection.items()):raise ValueError('V1 drift')
    # Fixed local runner, not a caller-supplied successful XML or execution receipt.
    check_folder=ROOT/'outputs'/(output.name+'_checks')
    receipt=checks.run(check_folder)
    aliases=parent.read(old/'identity_alias_index.json');excluded=parent.rows(old/'historical_exclusions.jsonl')
    prior_lock=parent.read(old/'split_lock.json');lock=admission.prelock(prior_lock['assignments'],excluded,aliases,admission.FRAME)
    stamp=datetime.now(UTC).isoformat()
    summary=parent.read(old/'summary.json') | {'status':STATUS,'createdAtUTC':stamp,'activePartitionGuard':config['activeMetadataGuard'],
        'activeFinalGuard':config['activeFinalGuard'],'metadataStageStatus':lock['status'],'testExecutionCases':receipt['actualTests'],
        'testRunId':receipt['runId'],'samplingFrameLocked':False,'fullDBLPRepresentative':False,
        'finalContentBindingCompleted':False,'notice':config['scope']}
    import course_weak as c
    import export_course_evidence as evidence
    output.mkdir(parents=True);shutil.copytree(old,output/'audit_parent')
    for name in COPIED:shutil.copy2(old/name,output/name)
    for field in ('externalAudit','externalResults'):shutil.copy2(config[field],output/Path(config[field]).name)
    shutil.copytree(check_folder,output/'test_execution')
    split=prior_lock | {'activePartitionGuard':config['activeMetadataGuard'],'activeFinalGuard':config['activeFinalGuard'],
        'metadataStage':'evaluation_lock.json','finalContentBindingCompleted':False}
    for name,value in (('contract',config),('summary',summary),('parent_replay',replay),('split_lock',split),('evaluation_lock',lock)):
        c.write_json(output/(name+'.json'),value)
    snapshot=output/'source_snapshot';shutil.copytree(old/'source_snapshot',snapshot);bindings=parent.read(snapshot/'source_bindings.json')
    for p,h in inventory['sourceSha256'].items():
        target=snapshot/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/p,target);bindings[p]=h
    relative=checks.INVENTORY.relative_to(ROOT).as_posix();target=snapshot/relative;shutil.copy2(checks.INVENTORY,target);bindings[relative]=parent.sha(target)
    c.write_json(snapshot/'source_bindings.json',bindings)
    body='<p>只修测试证据与内容绑定准入；标签/旧模型/V1不变。新评测成员仍为空，没有新F1。</p>'
    body+=evidence.table(['修复','结果'],[['JUnit入口','构建内实际执行固定用例，不接受外部通过XML'],
        ['实际测试用例',receipt['actualTests']],['运行ID',receipt['runId']],['元数据预锁',lock['status']],
        ['原文/来源/近重复最终绑定','接口回归通过；真实新评测成员0'],['抽样范围','仅现代arXiv可识别AI摘要；不代表全部DBLP']])
    body+=evidence.table(['数据守恒','数量'],[['摘要/实体/候选','12 / 177 / 684'],['用途/评测/负例/未决','68 / 17 / 0 / 599'],
        ['训练授权','false'],['验证/测试/挑战成员','0 / 0 / 0']])
    (output/'09_annotation_expansion.html').write_text(evidence.page('V2测试执行证据与两阶段准入',body,stamp,
        ['test_execution/checks.xml','test_execution/run_receipt.json','evaluation_lock.json','summary.json']),encoding='utf-8')
    if any(parent.sha(Path(p) if Path(p).is_absolute() else ROOT/p)!=h for p,h in inputs.items()) or any(parent.sha(ROOT/p)!=h for p,h in protection.items()):raise ValueError('Input/V1 drift')
    c.write_json(output/'manifest.json',{'kind':'real_artifact_visualization_not_original_console_ui','inputSha256':inputs,
        'filesSha256':{p.relative_to(output).as_posix():parent.sha(p) for p in output.rglob('*') if p.is_file()}})
    verify(output);return summary


def verify(bundle):
    bundle=Path(bundle).resolve();config=parent.read(bundle/'contract.json');manifest=parent.read(bundle/'manifest.json');old=bundle/'audit_parent'
    if parent.sha(old/'manifest.json')!=config['parentManifestSha256']:raise ValueError('Parent binding')
    replay=parent.verify(old);passed=set(replay['categories'])

    def check(condition,name):
        if not condition:raise ValueError('admission_'+name)
        passed.add('admission_'+name)

    for p,h in manifest['filesSha256'].items():
        target=(bundle/p).resolve();check(target.is_relative_to(bundle) and parent.sha(target)==h,'file_hashes')
    check(config['version']=='course_v2_admission_v1' and all(config[k] is False for k in parent.previous.FLAGS),'authorization')
    check(config==parent.read(bundle/'source_snapshot/resources/course_v2_admission_v1.json'),'contract_snapshot')
    for field in ('externalAudit','externalResults'):check(parent.sha(bundle/Path(config[field]).name)==config[field+'Sha256'],'external_audit_binding')
    for name in COPIED:check(parent.sha(bundle/name)==parent.sha(old/name),'core_and_metadata_byte_conservation')
    inventory=parent.read(bundle/'source_snapshot/resources/course_v2_admission_test_inventory_v1.json')
    count=checks.verify(bundle/'test_execution',inventory,bundle/'source_snapshot');check(count==len(inventory['nodeIds']),'controlled_test_execution')
    aliases=parent.read(bundle/'identity_alias_index.json');excluded=parent.rows(bundle/'historical_exclusions.jsonl');prior_lock=parent.read(old/'split_lock.json')
    lock=admission.prelock(prior_lock['assignments'],excluded,aliases,admission.FRAME)
    check(parent.read(bundle/'evaluation_lock.json')==lock and lock['evaluationAuthorized'] is False,'metadata_only_not_final')
    check(parent.read(bundle/'split_lock.json')==prior_lock | {'activePartitionGuard':config['activeMetadataGuard'],'activeFinalGuard':config['activeFinalGuard'],
        'metadataStage':'evaluation_lock.json','finalContentBindingCompleted':False},'active_entry_and_empty_inventory')
    check(lock['counts']=={'train':12} and not lock['samplingFrame']['samplingFrameLocked'] and lock['samplingFrame']['fullDBLPRepresentative'] is False,'restricted_frame_not_sampled')
    try:admission.finalize(lock,{},excluded,aliases,bundle)
    except ValueError as error:check('Empty evaluation' in str(error),'empty_cannot_finalize')
    else:raise ValueError('admission_empty_cannot_finalize')
    receipt=parent.read(bundle/'test_execution/run_receipt.json');summary=parent.read(bundle/'summary.json')
    expected=parent.read(old/'summary.json') | {'status':STATUS,'createdAtUTC':summary['createdAtUTC'],'activePartitionGuard':config['activeMetadataGuard'],
        'activeFinalGuard':config['activeFinalGuard'],'metadataStageStatus':lock['status'],'testExecutionCases':count,'testRunId':receipt['runId'],
        'samplingFrameLocked':False,'fullDBLPRepresentative':False,'finalContentBindingCompleted':False,'notice':config['scope']}
    check(summary==expected,'summary_recomputed');check(parent.read(bundle/'parent_replay.json')==replay,'parent_replay')
    for p,h in parent.read(bundle/'source_snapshot/source_bindings.json').items():
        target=(bundle/'source_snapshot'/p).resolve();check(target.is_relative_to(bundle/'source_snapshot') and parent.sha(target)==h,'snapshot_binding')
        if p in manifest['inputSha256']:check(h==manifest['inputSha256'][p],'input_source_binding')
    return {'status':'passed','assertionCategories':len(passed),'categories':sorted(passed),'actualTestExecutionCases':count,
        'evaluationInventoryLocked':False,'finalContentBindingCompleted':False,'semanticAccuracyCertified':False,'liveProductionVerified':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--output',type=Path,default=OUTPUT);parser.add_argument('--verify',type=Path)
    args=parser.parse_args();print(json.dumps(verify(args.verify) if args.verify else build(args.output),ensure_ascii=False,indent=2))
