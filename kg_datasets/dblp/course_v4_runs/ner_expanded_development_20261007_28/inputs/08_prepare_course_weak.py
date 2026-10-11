"""Prepare an immutable course-v4 AI queue without modifying historical data."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_weak as c

LEGACY_NAMES = {'pilot_200.jsonl','rare_candidates_train.jsonl','blind_50_reference.jsonl',
                'pilot20_ai_candidates.jsonl','pilot20_blind_reference.jsonl'}


def historical_sources(root: Path) -> list[Path]:
    return sorted(path for folder in (root/'kg_datasets/dblp').glob('ner_v*')
                  for path in folder.rglob('*.jsonl') if path.name in LEGACY_NAMES
                  and 'legacy_reference' not in path.parts and 'source_review' not in path.parts)


def load_inputs(root: Path) -> tuple[list[dict],set[str],list[tuple[str,str]],dict[str,str]]:
    corpus_path = root/'kg_datasets/dblp/ner_v1/corpus_manifest.jsonl'
    publications_path = root/'kg_datasets/dblp/processed_ai/publications.csv'
    near_path = root/'kg_datasets/dblp/ner_v3_1/near_duplicate_review/near_duplicate_pairs.csv'
    paths = [corpus_path,publications_path,near_path,*historical_sources(root)]
    before = {p.relative_to(root).as_posix():c.file_sha256(p) for p in paths}
    corpus = c.read_jsonl(corpus_path)
    with publications_path.open(encoding='utf-8-sig',newline='') as stream:
        publications = list(csv.DictReader(stream))
    lookup = {r['publicationId:ID(Publication)']:r for r in publications}
    if len(lookup)!=len(publications) or len(corpus)!=len(publications):
        raise ValueError('Corpus and CSV must have the same unique publications')
    for row in corpus:
        source = lookup.get(row['publicationId'])
        if source is None or (row['text'],row['doi'],row['year'],row['type']) != (source['title'],source['doi'],int(source['year:int']),source['type']):
            raise ValueError('Canonical corpus text/DOI/year/type differs from processed CSV')
    exposed = set()
    for path in paths[3:]:
        for record in c.read_jsonl(path):
            pid = record['publicationId']
            if pid not in lookup or record.get('text',record.get('title'))!=lookup[pid]['title']:
                raise ValueError('Historical candidate differs from canonical source')
            exposed.add(pid)
    with near_path.open(encoding='utf-8-sig',newline='') as stream:
        pairs = [(r['leftId'],r['rightId']) for r in csv.DictReader(stream)]
    if any(c.file_sha256(root/name)!=digest for name,digest in before.items()):
        raise ValueError('Sources changed while being read')
    return corpus,exposed,pairs,before


def legacy_ai_response(row: dict, reference: dict) -> dict:
    if row['text']!=reference['text'] or row['publicationId']!=reference['publicationId']:
        raise ValueError('Legacy AI candidate differs from canonical text')
    entities,groups = [],[]
    for item in row['entities']:
        if item['origin']!='ai_suggestion':
            raise ValueError('Dictionary or human annotations must not be renamed as AI output')
        span = {k:item[k] for k in ('start','end','text','label')}
        if item['mentionForm']=='coordinated':
            groups.append({'groupId':f'g{len(groups)+1}',**span})
        else:
            entities.append({'entityId':f'e{len(entities)+1}',**span})
    response = {'sampleId':reference['sampleId'],'textSha256':reference['textSha256'],'reviewOfSha256':None,
                'entityStatus':'unresolved','entityReason':'Preserved legacy boundary candidates; complete AI relabeling/review is pending.',
                'entities':entities,'groupMentions':groups,'relationStatus':'unresolved',
                'relationReason':'The original AI review did not provide relation annotations.',
                'relations':[],'notes':row['notes']}
    errors = c.validate_response(response,reference)
    if errors:
        raise ValueError('; '.join(errors))
    return response


def assert_input_hashes(root,hashes) -> None:
    if any(c.file_sha256(root/name)!=digest for name,digest in hashes.items()):
        raise ValueError('An input changed during dataset preparation')


def prepare(root: Path, output: Path, *, counts=None, seed=None) -> dict:
    if output.exists():
        raise FileExistsError('Preserve prior versions: choose a new output directory')
    counts = c.CONFIG['sampleCounts'] if counts is None else counts
    seed = c.CONFIG['seed'] if seed is None else seed
    corpus,exposed,pairs,inputs = load_inputs(root)
    groups = c.group_corpus(corpus,pairs)
    splits = c.assign_splits(corpus,groups,exposed,seed=seed)
    selected = c.select_cohort(corpus,splits,exposed,counts=counts,seed=seed)
    corpus_hash = inputs['kg_datasets/dblp/ner_v1/corpus_manifest.jsonl']
    references = [c.make_reference(row,groups[row['publicationId']],splits[row['publicationId']],corpus_hash) for row in selected]
    by_publication = {r['publicationId']:r for r in references}
    legacy_path = root/'kg_datasets/dblp/ner_v3_1/pilot20_ai_candidates.jsonl'
    legacy_responses = [legacy_ai_response(row,by_publication[row['publicationId']]) for row in c.read_jsonl(legacy_path)]
    created_at = datetime.now(UTC).isoformat()
    provenance = {'provider':'legacy_ai_artifact','model':'unknown_original_ai_model','promptSha256':None,
                  'sourceArtifactSha256':c.file_sha256(legacy_path),'createdAt':created_at}
    legacy_receipts = [c.make_receipt(r,by_publication[row['publicationId']],provenance)
                       for r,row in zip(legacy_responses,c.read_jsonl(legacy_path))]
    output.mkdir(parents=True,exist_ok=False)
    (output/'jobs/generation').mkdir(parents=True)
    (output/'legacy').mkdir()
    c.write_jsonl(output/'references.jsonl',references)
    c.write_jsonl(output/'corpus_split_manifest.jsonl',[{'publicationId':pid,'groupId':groups[pid],
                  'split':splits[pid],'historicalTrainOnly':pid in exposed} for pid in sorted(groups)])
    for split in counts:
        c.write_jsonl(output/f'{split}_references.jsonl',[r for r in references if r['split']==split])
    size = c.CONFIG['batchSize']
    for number,start in enumerate(range(0,len(references),size),1):
        c.write_jsonl(output/f'jobs/generation/batch-{number:04d}.jsonl',
                      [c.model_payload(r) for r in references[start:start+size]])
    shutil.copyfile(c.SCHEMA_PATH,output/'response_schema.json')
    shutil.copyfile(c.CONFIG_PATH,output/'config.json')
    shutil.copyfile(root/'docs/course_v4_ai_prompt.md',output/'ai_prompt.md')
    shutil.copyfile(legacy_path,output/'legacy/original_v3_ai_candidates.jsonl')
    c.write_jsonl(output/'legacy/converted_ai_candidates.jsonl',legacy_responses)
    c.write_jsonl(output/'legacy/generation_receipts.jsonl',legacy_receipts)
    forced_groups = {groups[pid] for pid in exposed}
    group_splits = {}
    for pid,group in groups.items():
        group_splits.setdefault(group,set()).add(splits[pid])
    summary = {'status':'queue_prepared_ai_labeling_pending','createdAt':created_at,
               'corpusDocuments':len(corpus),'paperGroups':len(set(groups.values())),
               'corpusSplits':dict(Counter(splits.values())),'selectedDocuments':len(references),
               'selectedSplits':dict(Counter(r['split'] for r in references)),
               'historicalTrainOnlyDocuments':len(exposed),'forcedTrainGroupDocuments':sum(groups[pid] in forced_groups for pid in groups),
               'nearDuplicatePairsCoLocated':len(pairs),'crossSplitGroups':sum(len(values)>1 for values in group_splits.values()),
               'pendingGenerationJobs':len(references),'generationBatches':(len(references)+size-1)//size,
               'legacyAiCandidateDocuments':len(legacy_receipts),
               'legacyRegularEntityCandidates':sum(len(r['entities']) for r in legacy_responses),
               'legacyGroupMentions':sum(len(r['groupMentions']) for r in legacy_responses),
               'aiReviewedDocuments':0,'humanReviewedDocuments':0,'nerTrainingReady':False,
               'relationTrainingReady':False,'trainingStarted':False,'evaluationTarget':c.CONFIG['evaluationTarget'],
               'limitations':['Group heuristics are conservative and not exhaustive; publication identities were not merged.',
                              'The original AI model/prompt were not supplied; unknown/null are preserved.',
                              'Legacy suggestions are incomplete first-pass candidates, not reviewed training labels.',
                              'Class coverage is unknown until complete AI labels exist; no empty jobs become negative examples.']}
    c.write_json(output/'summary.json',summary)
    assert_input_hashes(root,inputs)
    artifacts = {p.relative_to(output).as_posix():c.file_sha256(p) for p in sorted(output.rglob('*')) if p.is_file()}
    c.write_json(output/'manifest.json',{'schemaVersion':c.CONFIG['version'],'createdAt':created_at,'seed':seed,
                 'counts':counts,'inputSha256':inputs,'schemaSha256':c.file_sha256(c.SCHEMA_PATH),
                 'configSha256':c.file_sha256(c.CONFIG_PATH),'promptSha256':c.file_sha256(root/'docs/course_v4_ai_prompt.md'),
                 'codeSha256':{name:c.file_sha256(root/name) for name in ('scripts/course_weak.py','scripts/prepare_course_weak.py')},
                 'filesSha256':artifacts,'inputsPreserved':True})
    return summary


def verify_dataset(folder: Path) -> list[dict]:
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    required = {'references.jsonl','corpus_split_manifest.jsonl','response_schema.json','config.json','ai_prompt.md'}
    if not required <= set(manifest['filesSha256']):
        raise ValueError('Required dataset artifacts must be hash-bound')
    for name,digest in manifest['filesSha256'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or not (folder/relative).resolve().is_relative_to(folder.resolve()):
            raise ValueError('Unsafe dataset manifest path')
        if c.file_sha256(folder/relative)!=digest:
            raise ValueError('Prepared artifact changed: '+name)
    if manifest['schemaSha256']!=c.file_sha256(c.SCHEMA_PATH) or manifest['configSha256']!=c.file_sha256(c.CONFIG_PATH):
        raise ValueError('Dataset contract differs from active code')
    references = c.read_jsonl(folder/'references.jsonl')
    if len({r['sampleId'] for r in references})!=len(references):
        raise ValueError('Duplicate canonical sample IDs')
    return references


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=c.ROOT)
    parser.add_argument('--output',type=Path,default=c.ROOT/'kg_datasets/dblp/course_v4_weak')
    parser.add_argument('--verify-only',type=Path)
    args = parser.parse_args()
    result = {'valid':True,'documents':len(verify_dataset(args.verify_only))} if args.verify_only else prepare(args.root,args.output)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
