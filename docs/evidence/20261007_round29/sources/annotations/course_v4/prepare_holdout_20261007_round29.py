"""Prepare the previously reserved 200-paper test queue and freeze both models before labels."""
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import course_weak as c
from prepare_course_weak import verify_dataset
from course_graph import verified_files


def main():
    runs = ROOT / 'kg_datasets/dblp/course_v4_runs'
    dataset = ROOT / 'kg_datasets/dblp/course_v4_holdout_20261007_29'
    selection = runs / 'refresh_selection_20261007_29.json'
    if dataset.exists() or selection.exists(): raise FileExistsError('Preserve reserved test version')
    policy = runs / 'refresh_lock_20261007_28.json'
    reserved = json.loads(policy.read_text(encoding='utf-8'))
    for p, sha in reserved['inputSha256'].items(): assert c.file_sha256(ROOT / p) == sha
    old = ROOT / 'kg_datasets/dblp/course_v4_weak'
    existing = verify_dataset(old)
    corpus = ROOT / 'kg_datasets/dblp/ner_v1/corpus_manifest.jsonl'
    rows = {r['publicationId']: r for r in c.read_jsonl(corpus)}
    refs = [c.make_reference(rows[r['publicationId']], r['groupId'], 'test', c.file_sha256(corpus))
            for r in reserved['holdout']]
    assert len(refs) == len({r['groupId'] for r in refs}) == 200
    assert not {r['groupId'] for r in refs} & {r['groupId'] for r in existing}
    models = {}
    for kind, name in [('ner', 'ner_expanded_development_20261007_28'), ('re', 're_expanded_development_20261007_28')]:
        folder = runs / name
        manifest = verified_files(folder)
        result = json.loads((folder / 'development_result.json').read_text(encoding='utf-8'))
        assert result['passed'] and not result['testEvaluated']
        weights = folder / result['bestCheckpoint'] / 'model.safetensors'
        models[kind] = {'developmentRun': folder.relative_to(ROOT).as_posix(), 'checkpoint': result['bestCheckpoint'],
                        'developmentManifestSha256': c.file_sha256(folder / 'manifest.json'),
                        'weightsSha256': c.file_sha256(weights), 'config': manifest['config']}
    created = datetime.now(UTC).isoformat()
    dataset.mkdir(); (dataset / 'jobs').mkdir()
    c.write_jsonl(dataset / 'references.jsonl', refs)
    c.write_jsonl(dataset / 'jobs/generation.jsonl', [c.model_payload(r) for r in refs])
    for source, target in [(old / 'corpus_split_manifest.jsonl', 'corpus_split_manifest.jsonl'),
                            (c.SCHEMA_PATH, 'response_schema.json'), (c.CONFIG_PATH, 'config.json'),
                            (old / 'ai_prompt.md', 'ai_prompt.md')]: shutil.copyfile(source, dataset / target)
    c.write_json(dataset / 'manifest.json', {'kind': 'reserved_refresh_test_only', 'createdAtUTC': created,
        'schemaSha256': c.file_sha256(c.SCHEMA_PATH), 'configSha256': c.file_sha256(c.CONFIG_PATH),
        'inputSha256': {p.relative_to(ROOT).as_posix(): c.file_sha256(p) for p in (policy, corpus, old / 'manifest.json', Path(__file__))},
        'filesSha256': {p.relative_to(dataset).as_posix(): c.file_sha256(p) for p in dataset.rglob('*') if p.is_file()}})
    c.write_json(selection, {'lockedAtUTC': created, 'models': models, 'referenceSha256': c.canonical_sha256(refs),
        'datasetManifestSha256': c.file_sha256(dataset / 'manifest.json'),
        'reservedPolicySha256': c.file_sha256(policy), 'annotationSchemaSha256': c.file_sha256(c.SCHEMA_PATH),
        'annotationConfigSha256': c.file_sha256(c.CONFIG_PATH), 'oldProductionRun': 'kg_datasets/dblp/course_v4_runs/corpus_production_20261007_25',
        'oldProductionManifestSha256': c.file_sha256(runs / 'corpus_production_20261007_25/manifest.json'),
        'evaluationPolicy': 'one frozen NER/module/pipeline evaluation on all eligible reviewed titles; disclose exclusions and zero supports',
        'promotionGates': {'pipelineF1AtLeastOldOnSameTitles': True, 'pipelinePrecisionAtLeastOldOnSameTitles': True,
            'minimumReferenceRareEntitySupport': 10, 'minimumReferenceRareRelationSupport': 10,
            'rareNERDevNonRegression': False},
        'promotionNotice': 'The NER DATASET dev slice already regressed: no automatic deployment even if new overall scores improve.',
        'labelsSeenBeforeThisSelection': False, 'humanGold': False, 'independentAnnotator': False,
        'noTestTuning': True, 'oldProductionCorpusPreviouslyInferred': True})
    assert len(verify_dataset(dataset)) == 200
    print(json.dumps({'prepared': 200, 'newLabelsPending': True, 'candidateSelectionFrozen': True}))


if __name__ == '__main__': main()
