"""Compile explicitly authored AI literal-span decisions; never infer semantic labels.

This helper does not call an AI. The preserved decisions file is the semantic
source; exact text matching merely computes Unicode offsets and full-title
evidence. Missing, ambiguous or invented decisions fail instead of being filled.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

import course_weak as c
from prepare_course_weak import verify_dataset

DECISION_KEYS = {'sampleId','entityStatus','entityReason','entities','groupMentions',
                 'relationStatus','relationReason','relations','notes'}


def literal_span(item: dict, text: str) -> dict:
    if not isinstance(item,dict) or not {'text','label'} <= set(item) or not set(item) <= {'text','label','occurrence'}:
        raise ValueError('Unexpected literal-span decision fields')
    if not isinstance(item['text'],str) or not item['text']:
        raise ValueError('An AI boundary must specify nonempty original text')
    hits = list(re.finditer(re.escape(item['text']),text))
    occurrence = item.get('occurrence',1)
    if type(occurrence) is not int or occurrence < 1 or occurrence > len(hits) or (len(hits)!=1 and 'occurrence' not in item):
        raise ValueError('Literal absent or repeated without a valid explicit occurrence')
    hit = hits[occurrence-1]
    return {'start':hit.start(),'end':hit.end(),'text':hit.group(),'label':item['label']}


def compile_decisions(decisions,references,*,previous=None) -> list[dict]:
    lookup = {r['sampleId']:r for r in references}
    if len(lookup)!=len(references) or not decisions:
        raise ValueError('Reference IDs must be unique and AI decisions must be nonempty')
    prior = {r['reference']['sampleId']:r for r in previous or []}
    if previous is not None and (len(prior)!=len(previous) or set(prior)!=set(lookup)):
        raise ValueError('Review decisions require the exact preserved generation batch')
    responses,seen = [],set()
    for decision in decisions:
        if not isinstance(decision,dict) or set(decision)!=DECISION_KEYS:
            raise ValueError('Unexpected semantic AI decision fields')
        sample = decision['sampleId']
        if sample not in lookup or sample in seen:
            raise ValueError('Duplicate or unknown AI decision sample ID')
        seen.add(sample)
        reference = lookup[sample]
        if previous is not None:
            errors = c.validate_receipt(prior[sample],reference)
            if errors:
                raise ValueError('; '.join(errors))
        response = {key:decision[key] for key in ('sampleId','entityStatus','entityReason','relationStatus','relationReason','notes')}
        response.update(textSha256=reference['textSha256'],reviewOfSha256=prior[sample]['contentSha256'] if previous is not None else None)
        for key,prefix,id_key in (('entities','e','entityId'),('groupMentions','g','groupId')):
            response[key] = [{id_key:f'{prefix}{index}',**literal_span(item,reference['text'])}
                             for index,item in enumerate(decision[key],1)]
        response['relations'] = []
        for relation in decision['relations']:
            if not isinstance(relation,dict) or set(relation)!={'head','tail','label','reason'}:
                raise ValueError('Unexpected explicit relation decision fields')
            response['relations'].append(relation|{'evidence':None if relation['label']=='UNRESOLVED' else
                {'start':0,'end':len(reference['text']),'text':reference['text']}})
        errors = c.validate_response(response,reference)
        if errors:
            raise ValueError('; '.join(errors))
        responses.append(response)
    if seen!=set(lookup):
        raise ValueError('AI decisions must cover the complete supplied batch')
    return responses


def compile_artifact(dataset,jobs,decisions_path,output,*,previous=None) -> dict:
    if output.exists():
        raise FileExistsError('Preserve AI decision artifacts: choose a new output directory')
    all_references = {r['sampleId']:r for r in verify_dataset(dataset)}
    input_paths = [jobs,decisions_path]+([previous] if previous is not None else [])
    hashes = {str(path.resolve()):c.file_sha256(path) for path in input_paths}
    job_rows = c.read_jsonl(jobs)
    if not job_rows or len({r['sampleId'] for r in job_rows})!=len(job_rows):
        raise ValueError('Jobs must be a nonempty unique batch')
    references = []
    for job in job_rows:
        if job['sampleId'] not in all_references or job!=c.model_payload(all_references[job['sampleId']]):
            raise ValueError('Job text or fields differ from the sealed anonymous queue')
        references.append(all_references[job['sampleId']])
    source = json.loads(decisions_path.read_text(encoding='utf-8'))
    if set(source)!={'provider','model','round','decisions'} or source['round']!=('generation' if previous is None else 'candidate_aware_ai_review'):
        raise ValueError('AI source and round must be explicitly declared')
    responses = compile_decisions(source['decisions'],references,previous=c.read_jsonl(previous) if previous is not None else None)
    if any(c.file_sha256(Path(name))!=digest for name,digest in hashes.items()):
        raise ValueError('AI source changed while compiling')
    output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(decisions_path,output/'ai_decisions.json')
    c.write_jsonl(output/'responses.jsonl',responses)
    details = {'documents':len(responses),'provider':source['provider'],'model':source['model'],'round':source['round'],
               'modelCallExecutedByCompiler':False,'inputSha256':hashes,'compilerCodeSha256':c.file_sha256(Path(__file__)),
               'notice':'Semantic decisions were authored by the declared AI; compilation only assigns literal offsets and validates.'}
    c.write_json(output/'manifest.json',details|{'filesSha256':{name:c.file_sha256(output/name) for name in ('ai_decisions.json','responses.jsonl')}})
    return details


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--jobs',type=Path,required=True)
    parser.add_argument('--decisions',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--previous',type=Path)
    args = parser.parse_args()
    print(json.dumps(compile_artifact(args.dataset,args.jobs,args.decisions,args.output,previous=args.previous),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
