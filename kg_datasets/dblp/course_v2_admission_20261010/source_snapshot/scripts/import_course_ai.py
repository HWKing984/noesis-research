"""Import actual AI response artifacts, bind reviews and assemble weak training inputs.

This tool does not call an LLM or train a model. Unknown/unannotated jobs remain
pending. Only explicitly complete, reviewed AI labels enter task-specific inputs.
"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_weak as c
from prepare_course_weak import verify_dataset


def assess_readiness(receipts: list[dict], references: list[dict]) -> dict:
    lookup = {r['sampleId']:r for r in references}
    if len(lookup)!=len(references):
        raise ValueError('Duplicate canonical sample IDs')
    support = {split:{label:0 for label in c.CONFIG['entityLabels']} for split in c.CONFIG['splitRatios']}
    relation_support = {split:{label:0 for label in c.CONFIG['relationLabels'] if label!='UNRESOLVED'} for split in support}
    ner_counts,relation_counts = Counter(),Counter()
    seen,group_splits = set(),{}
    reviewed,challenge = 0,0
    for reference in references:
        group_splits.setdefault(reference['groupId'],set()).add(reference['split'])
    if any(len(values)!=1 for values in group_splits.values()):
        raise ValueError('A paper group crosses splits')
    for receipt in receipts:
        pid = receipt['reference']['sampleId']
        if pid in seen or pid not in lookup:
            raise ValueError('Duplicate or unknown receipt sample ID')
        seen.add(pid)
        reference = lookup[pid]
        errors = c.validate_receipt(receipt,reference)
        if errors:
            raise ValueError('; '.join(errors))
        eligible = c.eligible_tasks(receipt,reference)
        reviewed += receipt['review'] is not None
        challenge += bool(receipt['annotation']['groupMentions'])
        if eligible['ner']:
            ner_counts[reference['split']] += 1
            for entity in receipt['annotation']['entities']:
                support[reference['split']][entity['label']] += 1
        if eligible['relation']:
            relation_counts[reference['split']] += 1
            for relation in receipt['annotation']['relations']:
                relation_support[reference['split']][relation['label']] += 1
    return {'referenceDocuments':len(references),'generationReceiptDocuments':len(receipts),
            'pendingGenerationDocuments':len(references)-len(receipts),'aiReviewedDocuments':reviewed,
            'humanReviewedDocuments':0,'humanGoldAvailable':False,'challengeDocuments':challenge,
            'nerEligibleDocuments':sum(ner_counts.values()),'relationEligibleDocuments':sum(relation_counts.values()),
            'nerEligibleSplits':{split:ner_counts[split] for split in support},
            'relationEligibleSplits':{split:relation_counts[split] for split in support},
            'entitySupport':support,'relationSupport':relation_support,
            'nerTrainingReady':all(ner_counts[s]>0 and all(support[s][label]>0 for label in c.CONFIG['entityLabels']) for s in support),
            'relationTrainingReady':all(relation_counts[s]>0 and all(relation_support[s][label]>0 for label in relation_support[s]) for s in support),
            'trainingStarted':False,'evaluationTarget':c.CONFIG['evaluationTarget'],
            'notice':'Readiness requires nonzero per-class support, not a quality guarantee. Hashes detect drift, not authentic AI execution or semantic truth.'}


def save_training_inputs(output,receipts,references) -> None:
    lookup = {r['sampleId']:r for r in references}
    for split in c.CONFIG['splitRatios']:
        ner,relation = [],[]
        for receipt in receipts:
            reference = lookup[receipt['reference']['sampleId']]
            if reference['split']!=split:
                continue
            tasks = c.eligible_tasks(receipt,reference)
            common = {'sampleId':reference['sampleId'],'text':reference['text'],'textSha256':reference['textSha256'],
                      'referenceSha256':c.canonical_sha256(reference),'annotationSha256':receipt['contentSha256'],'labelSource':'ai_pseudo'}
            if tasks['ner']:
                ner.append(common|{'entities':copy.deepcopy(receipt['annotation']['entities'])})
            if tasks['relation']:
                entities = {e['entityId']:e for e in receipt['annotation']['entities']}
                for pair in receipt['annotation']['relations']:
                    relation.append(common|{'head':entities[pair['head']],'tail':entities[pair['tail']],
                                           'label':pair['label'],'evidence':pair['evidence'],'reason':pair['reason']})
        c.write_jsonl(output/f'ner_inputs_{split}.jsonl',ner)
        c.write_jsonl(output/f'relation_inputs_{split}.jsonl',relation)


def seal_output(output,details) -> None:
    files = {p.relative_to(output).as_posix():c.file_sha256(p) for p in sorted(output.iterdir()) if p.is_file()}
    c.write_json(output/'manifest.json',details|{'filesSha256':files,'schemaVersion':c.CONFIG['version'],
                                              'importerCodeSha256':c.file_sha256(Path(__file__))})


def import_results(dataset: Path, responses_path: Path, output: Path, *, provider: str, model: str, previous: Path | None=None) -> dict:
    if output.exists():
        raise FileExistsError('Preserve AI artifacts: choose a new output directory')
    references = verify_dataset(dataset)
    lookup = {r['sampleId']:r for r in references}
    response_hash = c.file_sha256(responses_path)
    responses = c.read_jsonl(responses_path)
    if not responses:
        raise ValueError('An empty response file is not an annotated negative dataset')
    previous_hash = c.file_sha256(previous) if previous is not None else None
    initial = c.read_jsonl(previous) if previous is not None else []
    prior = {r['reference']['sampleId']:r for r in initial}
    if len(prior)!=len(initial):
        raise ValueError('Duplicate previous receipts')
    seen,receipts = set(),[]
    provenance = {'provider':provider,'model':model,'promptSha256':c.file_sha256(dataset/'ai_prompt.md'),
                  'sourceArtifactSha256':response_hash,'createdAt':datetime.now(UTC).isoformat()}
    for response in responses:
        sample = response.get('sampleId') if isinstance(response,dict) else None
        if sample in seen or sample not in lookup:
            raise ValueError('Duplicate or unknown AI response sample ID')
        seen.add(sample)
        if previous is not None and sample not in prior:
            raise ValueError('Review response has no preserved first-pass receipt')
        receipts.append(c.make_receipt(response,lookup[sample],provenance,previous=prior.get(sample)))
    if previous is not None and set(prior)!=seen:
        raise ValueError('Review batch must exactly cover its first-pass batch')
    if c.file_sha256(responses_path)!=response_hash or (previous is not None and c.file_sha256(previous)!=previous_hash):
        raise ValueError('AI input artifact changed while importing')
    report = assess_readiness(receipts,references)
    report.update(round='generation' if previous is None else 'candidate_aware_ai_review',provider=provider,model=model,
                  sourceResponseSha256=response_hash,previousReceiptSha256=previous_hash,
                  modelCallExecutedByImporter=False)
    output.mkdir(parents=True,exist_ok=False)
    shutil.copyfile(responses_path,output/'raw_responses.jsonl')
    if previous is not None:
        shutil.copyfile(previous,output/'previous_receipts.jsonl')
    c.write_jsonl(output/'receipts.jsonl',receipts)
    if previous is None:
        c.write_jsonl(output/'review_inputs.jsonl',[c.model_payload(r['reference'])|{
            'annotation':r['annotation'],'reviewOfSha256':r['contentSha256']} for r in receipts])
    save_training_inputs(output,receipts,references)
    c.write_json(output/'summary.json',report)
    seal_output(output,{'sourceDatasetManifestSha256':c.file_sha256(dataset/'manifest.json'),
                        'sourceResponsesPath':str(responses_path.resolve()),'sourceResponseSha256':response_hash,
                        'previousReceiptsPath':str(previous.resolve()) if previous else None,'previousReceiptSha256':previous_hash})
    return report


def assemble(dataset: Path, receipt_paths: list[Path], output: Path) -> dict:
    if output.exists():
        raise FileExistsError('Preserve prior training exports: choose a new output directory')
    references = verify_dataset(dataset)
    hashes = {str(path.resolve()):c.file_sha256(path) for path in receipt_paths}
    receipts = [row for path in receipt_paths for row in c.read_jsonl(path)]
    report = assess_readiness(receipts,references)
    if any(c.file_sha256(Path(path))!=digest for path,digest in hashes.items()):
        raise ValueError('Receipt artifact changed while assembling')
    output.mkdir(parents=True,exist_ok=False)
    c.write_jsonl(output/'receipts.jsonl',receipts)
    save_training_inputs(output,receipts,references)
    annotated = {row['reference']['sampleId'] for row in receipts}
    c.write_jsonl(output/'pending_generation.jsonl',[c.model_payload(row) for row in references if row['sampleId'] not in annotated])
    c.write_json(output/'summary.json',report)
    seal_output(output,{'sourceDatasetManifestSha256':c.file_sha256(dataset/'manifest.json'),'inputReceiptsSha256':hashes})
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    annotation = sub.add_parser('import')
    annotation.add_argument('--dataset',type=Path,required=True)
    annotation.add_argument('--responses',type=Path,required=True)
    annotation.add_argument('--output',type=Path,required=True)
    annotation.add_argument('--provider',required=True)
    annotation.add_argument('--model',required=True)
    annotation.add_argument('--previous',type=Path)
    export = sub.add_parser('assemble')
    export.add_argument('--dataset',type=Path,required=True)
    export.add_argument('--receipts',type=Path,nargs='+',required=True)
    export.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.command=='import':
        result = import_results(args.dataset,args.responses,args.output,provider=args.provider,model=args.model,previous=args.previous)
    else:
        result = assemble(args.dataset,args.receipts,args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
