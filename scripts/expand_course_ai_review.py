"""Expand preserved, explicitly authored AI confirmations/revisions, not model review."""
from __future__ import annotations

import argparse
import copy
import json
import shutil
from pathlib import Path

import course_weak as c
from compile_course_ai import DECISION_KEYS


def expand_review(first,review,generation_hash) -> dict:
    if (not isinstance(first,dict) or set(first)!={'provider','model','round','decisions'} or first['round']!='generation' or
            not isinstance(review,dict) or set(review)!={'provider','model','round','generationDecisionsSha256','judgments'} or
            review['round']!='candidate_aware_ai_review' or review['generationDecisionsSha256']!=generation_hash):
        raise ValueError('Review must bind the exact preserved generation artifact and declare candidate-aware AI review')
    lookup = {d['sampleId']:d for d in first['decisions']}
    if len(lookup)!=len(first['decisions']) or not lookup:
        raise ValueError('Initial semantic decisions must be nonempty and unique')
    seen,decisions = set(),[]
    for judgment in review['judgments']:
        if not isinstance(judgment,dict) or judgment.get('verdict') not in {'confirmed','revised'}:
            raise ValueError('Explicit AI confirmation or revision required')
        expected = {'sampleId','verdict','reason'} | ({'replacement'} if judgment['verdict']=='revised' else set())
        if set(judgment)!=expected or not isinstance(judgment['reason'],str) or not judgment['reason'].strip():
            raise ValueError('Unexpected or incomplete AI review judgment')
        sample = judgment['sampleId']
        if sample not in lookup or sample in seen:
            raise ValueError('Duplicate or unknown AI review sample')
        seen.add(sample)
        decision = copy.deepcopy(lookup[sample] if judgment['verdict']=='confirmed' else judgment['replacement'])
        if not isinstance(decision,dict) or set(decision)!=DECISION_KEYS or decision['sampleId']!=sample:
            raise ValueError('Revision must explicitly supply the full same-sample decision')
        decision['notes'] += '\nAI self-review: '+judgment['reason']
        decisions.append(decision)
    if seen!=set(lookup):
        raise ValueError('AI review must explicitly cover every initial sample')
    return {key:review[key] for key in ('provider','model','round')} | {'decisions':decisions}


def expand_artifact(generation,judgments,output) -> dict:
    if output.exists():
        raise FileExistsError('Preserve AI review judgments: choose a new output directory')
    hashes = {str(path.resolve()):c.file_sha256(path) for path in (generation,judgments)}
    expanded = expand_review(json.loads(generation.read_text(encoding='utf-8')),
                             json.loads(judgments.read_text(encoding='utf-8')),hashes[str(generation.resolve())])
    if any(c.file_sha256(Path(path))!=digest for path,digest in hashes.items()):
        raise ValueError('AI review input changed while expanding')
    output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(generation,output/'generation_decisions.json')
    shutil.copyfile(judgments,output/'review_judgments.json')
    c.write_json(output/'review_decisions.json',expanded)
    report = {'documents':len(expanded['decisions']),'inputSha256':hashes,
              'expanderCodeSha256':c.file_sha256(Path(__file__)),'modelCallExecutedByExpander':False,
              'notice':'This step only expands recorded AI judgments; it neither runs a model nor invents confirmations.'}
    c.write_json(output/'manifest.json',report|{'filesSha256':{name:c.file_sha256(output/name) for name in
        ('generation_decisions.json','review_judgments.json','review_decisions.json')}})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generation',type=Path,required=True)
    parser.add_argument('--judgments',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(expand_artifact(args.generation,args.judgments,args.output),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
