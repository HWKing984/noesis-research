"""Seal v3 source-complete candidate package; verify preserved v2 sources and run all browser generations."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from annotation_v3 import ROOT, SCHEMA_SHA256, RULES_SHA256, read_jsonl, validate_records
from prepare_revision_v3 import import_stress_review
from prepare_ner import digest, write_json
from replay_review_package import verify_archive
from verify_export_v2 import check_source_pool


def add_legacy_v2_inputs(contents, previous):
    for name in ('pilot_review.html','rare_review.html','blind_50_a.html','blind_50_b.html'):
        contents['kg_datasets/dblp/ner_v2/'+name]=(previous/name).read_bytes()


def run(command):
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=60)
    return {'command':command,'exit_code':result.returncode,'output':result.stdout+result.stderr}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=ROOT/'kg_datasets/dblp/ner_v3')
    parser.add_argument('--previous-data',type=Path,default=ROOT/'kg_datasets/dblp/ner_v2_1')
    parser.add_argument('--previous-package',type=Path,required=True)
    parser.add_argument('--previous-export-manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--playwright-module',required=True)
    parser.add_argument('--prior-replay-failure',type=Path)
    args=parser.parse_args()
    data,previous,output=args.data.resolve(),args.previous_data.resolve(),args.output.resolve()
    report=output/'AI-Literature-KG-v3-revision-report.md'
    plan=output/'AI-Literature-KG-v3-plan.md'
    archive=output/'AI-Literature-KG-v3-review-package.zip'
    exterior=output/'AI-Literature-KG-v3-export-manifest.json'
    if not report.is_file() or not plan.is_file():raise FileNotFoundError('Author report and plan before sealing')
    if archive.exists() or exterior.exists() or (data/'verification.json').exists():raise FileExistsError('Preserve prior sealed artifacts')
    pages={name:'AI-Literature-KG-v3-'+name.replace('_','-') for name in
           ('pilot20_blind_review.html','pilot20_ai_review.html','pilot_review.html','rare_review.html','blind_50_a.html','blind_50_b.html')}
    if any((output/name).exists() for name in pages.values()):raise FileExistsError('Standalone outputs already exist')
    source=import_stress_review(data/'source_review',data/'legacy_reference')
    original_v2_manifest=json.loads((previous/'manifest.json').read_text(encoding='utf-8'))
    v2_intact=all(digest(previous/name)==value for name,value in original_v2_manifest['outputs_sha256'].items())
    previous_integrity=verify_archive(args.previous_package)
    previous_expected=json.loads(args.previous_export_manifest.read_text(encoding='utf-8'))['zip_sha256']
    old_package_intact=previous_integrity['zip_sha256']==previous_expected
    with zipfile.ZipFile(args.previous_package) as prior:
        prior_manifest=json.loads(prior.read('manifest.json'))
        old_sources_intact=all(digest(ROOT/name)==expected for name,expected in prior_manifest['files_sha256'].items()
                             if name.startswith(('scripts/','tests/','docs/','schemas/','resources/')))
    v1=ROOT/'kg_datasets/dblp/ner_v1'
    old_manifest=json.loads((v1/'manifest.json').read_text(encoding='utf-8'))
    v1_intact=all(digest(v1/name)==value for name,value in old_manifest['output_sha256'].items())
    csv_intact=all(digest(ROOT/'kg_datasets/dblp/processed_ai'/name)==value for name,value in old_manifest['input_sha256'].items())
    raw_info=json.loads((v1/'data_audit.json').read_text(encoding='utf-8'))['raw_source']
    raw=ROOT/'kg_datasets/dblp/dblp.xml.gz'
    raw_intact=raw.stat().st_size==raw_info['bytes'] and digest(raw,'md5')==raw_info['md5']
    initial=json.loads((data/'manifest.json').read_text(encoding='utf-8'))
    generated_intact=all(digest(data/name)==value for name,value in initial['outputs_sha256'].items())
    evidence_names=('near_duplicate_review','abstract_sources','benchmark_abstract_sources')
    for name in evidence_names:shutil.copytree(previous/name,data/name)
    sources={name:check_source_pool(data/name) for name in evidence_names if name!='near_duplicate_review'}
    python=run([sys.executable,'-m','pytest','tests','-q','--cov=annotation_v3','--cov=prepare_revision_v3','--cov-branch',
                '--cov-report=term-missing','--cov-report=json:'+str(data/'coverage.json')])
    browser={version:run(['node','tests/test_'+('pilot_review' if version=='v1' else 'review_'+version)+'.cjs',args.playwright_module]+
                        ([str(previous)] if version=='v2' else [str(data)] if version=='v3' else [])) for version in ('v1','v2','v3')}
    cohorts={name:read_jsonl(data/name) for name in ('pilot_200.jsonl','rare_candidates_train.jsonl','blind_50_reference.jsonl',
                                                 'pilot20_ai_candidates.jsonl','pilot20_blind_reference.jsonl')}
    validations={name:validate_records(rows,reference=rows) for name,rows in cohorts.items()}
    gold_rejected=all(not validate_records(rows,reference=rows,**{scope:True})['valid']
                      for rows in cohorts.values() for scope in ('entity_gold','relation_gold','domain_gold'))
    blanks=[cohorts[name] for name in ('blind_50_reference.jsonl','pilot20_blind_reference.jsonl')]
    blank=all(not r['entities'] and not r['relations'] and not r['domains'] and not r['notes']
              and r['initialDraftProvenance']['kind']=='blind' and r['initialDraftProvenance']['aiReviewSha256'] is None for rows in blanks for r in rows)
    overlap=len({r['groupId'] for r in cohorts['pilot_200.jsonl']} & {r['groupId'] for r in cohorts['rare_candidates_train.jsonl']})
    ai,blind20=cohorts['pilot20_ai_candidates.jsonl'],cohorts['pilot20_blind_reference.jsonl']
    paired=all(a['publicationId']==b['publicationId'] and a['text']==b['text'] for a,b in zip(ai,blind20)) and len(ai)==len(blind20)==20
    fixture_files=['pilot20_ai_candidates.jsonl','pilot20_blind_reference.jsonl']+['source_review/'+name for name in
                   ('pilot20_boundary_review.json','pilot20_boundary_review.csv','AI-Literature-KG-pilot20-boundary-review.md')]+[
                   'legacy_reference/'+name for name in ('pilot_200.jsonl','blind_50_reference.jsonl','rare_candidates_train.jsonl')]
    fixture_inputs_match=all(digest(data/name)==digest(ROOT/'kg_datasets/dblp/ner_v3'/name) for name in fixture_files)
    freeze=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True,timeout=30)
    code_hashes={p.relative_to(ROOT).as_posix():digest(p) for folder in ('scripts','tests','docs','schemas','resources')
                 for p in sorted((ROOT/folder).iterdir()) if p.is_file()}
    evidence={'captured_at_utc':datetime.now(UTC).isoformat(),'schema_sha256':SCHEMA_SHA256,'boundary_rules_sha256':RULES_SHA256,
        'python':sys.version,'executable':sys.executable,'installed_packages':freeze.splitlines(),
        'playwright_version':json.loads((Path(args.playwright_module)/'package.json').read_text(encoding='utf-8'))['version'],
        'tests':python,'browser':browser,'coverage':json.loads((data/'coverage.json').read_text(encoding='utf-8'))['totals'],
        'validations':validations,'source_review':source['stats'],'source_abstracts':sources,
        'all_draft_gold_scopes_rejected':gold_rejected,'blind_answers_and_notes_empty':blank,'ai_and_blind20_ids_texts_match':paired,
        'cross_training_candidate_groups':overlap,'v1_outputs_unchanged':v1_intact,'v2_outputs_unchanged':v2_intact,
        'previous_package_integrity':previous_integrity,'previous_package_unchanged':old_package_intact,'v2_sources_unchanged':old_sources_intact,
        'raw_dblp_source_unchanged':raw_intact,'source_csvs_unchanged':csv_intact,'initial_outputs_unchanged':generated_intact,
        'test_fixture_inputs_identical_to_active_data':fixture_inputs_match,
        'code_sha256':code_hashes,'human_gold_complete':False,'schema_frozen':False,'training_started':False,
        'notice':'Source hashes and policy fixtures are not human semantic gold or independent model performance'}
    evidence['passed']=all([python['exit_code']==0,'skipped' not in python['output'],all(r['exit_code']==0 for r in browser.values()),
        all(r['valid'] for r in validations.values()),gold_rejected,blank,paired,overlap==0,v1_intact,v2_intact,old_package_intact,old_sources_intact,
        raw_intact,csv_intact,generated_intact,fixture_inputs_match,all(r['hashes_verified'] and r['candidate_boundary_verified'] for r in sources.values())])
    write_json(data/'verification.json',evidence)
    if not evidence['passed']:raise ValueError('Verification failed; evidence retained, package export refused')
    contents={'README.md':(ROOT/'docs/review_package_v3_readme.md').read_bytes(),report.name:report.read_bytes(),plan.name:plan.read_bytes(),
              'requirements-validation.txt':(ROOT/'requirements-validation.txt').read_bytes(),'requirements-validation.lock.txt':freeze.encode('utf-8'),
              'evidence/verification.json':(data/'verification.json').read_bytes(),'evidence/v1-data-audit.json':(v1/'data_audit.json').read_bytes()}
    if args.prior_replay_failure:
        contents['evidence/first-export-replay-failure.json']=args.prior_replay_failure.read_bytes()
    for folder in ('scripts','tests','docs','schemas','resources'):
        for p in sorted((ROOT/folder).iterdir()):
            if p.is_file():contents[p.relative_to(ROOT).as_posix()]=p.read_bytes()
    for p in sorted(data.rglob('*')):
        if p.is_file():contents['kg_datasets/dblp/ner_v3/'+p.relative_to(data).as_posix()]=p.read_bytes()
    add_legacy_v2_inputs(contents,previous)
    for name in ('pilot_review.html','rare_train_candidates/rare_candidates_review.html'):
        contents['kg_datasets/dblp/ner_v1/'+name]=(v1/name).read_bytes()
    contents['manifest.json']=json.dumps({'status':'candidate_pending_human_pilot','schema_sha256':SCHEMA_SHA256,'rules_sha256':RULES_SHA256,
        'files_sha256':{name:hashlib.sha256(value).hexdigest() for name,value in contents.items()}},indent=2).encode('utf-8')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as bundle:
        for name,payload in sorted(contents.items()):bundle.writestr(name,payload)
    integrity=verify_archive(archive)
    for source_name,target in pages.items():(output/target).write_bytes((data/source_name).read_bytes())
    guideline=output/'AI-Literature-KG-v3-guidelines.md';guideline.write_bytes((ROOT/'docs/annotation_guidelines_v3.md').read_bytes())
    write_json(exterior,{'status':'verified_candidate_package','zip_sha256':integrity['zip_sha256'],'zip_entries':len(contents),'zip_bytes':archive.stat().st_size,
        'schema_sha256':SCHEMA_SHA256,'rules_sha256':RULES_SHA256,'code_sha256':code_hashes,
        'standalone_sha256':{p.name:digest(p) for p in [report,plan,guideline]+[output/name for name in pages.values()]},'human_gold_complete':False})
    print(json.dumps({'passed':True,'entries':len(contents),'zip_bytes':archive.stat().st_size,'output':str(output)}))


if __name__=='__main__':main()
