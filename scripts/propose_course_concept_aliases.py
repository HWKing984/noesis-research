"""Saved-title evidence for typed alias candidates; never migrate a graph or run a model."""
import argparse
import hashlib
import json
from pathlib import Path

from normalize_course_concepts import g, spelling, vocabulary

c = g.c
CONFIG = g.ROOT/'resources/course_concept_candidates_v1.json'
PRODUCTION = 'kg_datasets/dblp/course_v4_runs/corpus_production_20261007_25/'
MAPPING = 'kg_datasets/dblp/course_v4_graph_quality_20261009_51/concept_mapping.jsonl'
ALLOWED_SOURCES = {MAPPING, PRODUCTION+'documents.jsonl', PRODUCTION+'ner_predictions.jsonl', PRODUCTION+'manifest.json', 'resources/course_concept_v2.json'}


def audit(config, mapping, docs, predictions):
    groups, mentions, names = [], [], {}
    for group in config['groups']:
        if group['type'] != 'METHOD' or not group['reviewReason'] or not group['primaryUrls']: raise ValueError('Typed review required')
        for name in group['members']:
            key = spelling(name)
            if key in names: raise ValueError('Ambiguous or duplicated alias')
            names[key] = group['canonical']
    documents = {d['sampleId']: d for d in docs}
    if len(documents) != len(docs): raise ValueError('Duplicated source document')
    selected = [m for m in mapping if m['entityType'] == 'METHOD' and spelling(m['oldName']) in names]
    if len({m['newConceptId'] for m in selected}) != len(names): raise ValueError('Concept inventory mismatch')
    for prediction in predictions:
        for entity in prediction['predictedEntities']:
            if entity['label'] != 'METHOD' or spelling(entity['text']) not in names: continue
            doc = documents[prediction['sampleId']]; text = doc['text']
            if text[entity['start']:entity['end']] != entity['text'] or hashlib.sha256(text.encode()).hexdigest() != doc['textSha256']: raise ValueError('Literal evidence drift')
            mentions.append({'canonicalCandidate': names[spelling(entity['text'])], 'publicationId': doc['publicationId'],
                'sampleId': doc['sampleId'], 'mention': entity, 'evidenceQuote': text, 'evidenceStart': 0, 'evidenceEnd': len(text),
                'titleSha256': doc['textSha256'], 'documentRowSha256': c.canonical_sha256(doc), 'predictionRowSha256': c.canonical_sha256(prediction),
                'abstractSourceSha256': None, 'reviewedRole': 'named_method_in_saved_title_not_a_relation_fact'})
    for group in config['groups']:
        subset = [m for m in mentions if m['canonicalCandidate'] == group['canonical']]
        if sorted(m['publicationId'] for m in subset) != sorted(group['reviewedPublicationIds']): raise ValueError('Occurrence not manually reviewed')
        anchors = [m for m in subset if m['publicationId'] == group['anchorPublicationId']]
        if len(anchors) != 1 or anchors[0]['evidenceQuote'].count(group['supportQuote']) != 1: raise ValueError('Missing or ambiguous local evidence')
        quote = group['supportQuote']; start = anchors[0]['evidenceQuote'].index(quote)
        if group['basis'] == 'explicit_local_definition':
            if group['status'] != 'candidate_local_definition' or any(spelling(n) not in spelling(quote) for n in group['members']): raise ValueError('Unsupported local definition')
        elif group['basis'] == 'singular_plural_spelling':
            if group['status'] != 'candidate_spelling_only' or set(group['members']) != {group['canonical'], group['canonical']+'s'}: raise ValueError('Not spelling-only')
        elif group['basis'] != 'typed_context_only' or group['status'] != 'proposal_needs_local_definition': raise ValueError('Context is not approval')
        groups.append(group | {'anchorEvidence': {'quote': quote, 'start': start, 'end': start+len(quote), 'titleSha256': anchors[0]['titleSha256']},
            'sourceConcepts': [m for m in selected if names[spelling(m['oldName'])] == group['canonical']], 'mentionCount': len(subset)})
    counts = {'concepts': len(selected), 'mentions': len(mentions), 'potentialNodeReductions': len(selected)-len(groups)}
    if counts != config['expected']: raise ValueError('Candidate inventory drift')
    return groups, mentions, counts | {'kind': 'candidate_not_graph_migration', 'actualNodeReductions': 0,
        'localDefinitionGroups': sum(g['status'] == 'candidate_local_definition' for g in groups), 'spellingOnlyGroups': sum(g['status'] == 'candidate_spelling_only' for g in groups), 'proposalGroups': sum(g['status'] == 'proposal_needs_local_definition' for g in groups),
        'abstractSourcesUsed': False, 'modelPromoted': False, 'graphMigrated': False, 'trainingAllowed': False,
        'independentHumanGold': False, 'primaryUrlsAreExtractionFacts': False, 'confidenceProvided': False}


def run(output):
    output = output.resolve()
    if output.exists(): raise FileExistsError('Preserve candidate evidence')
    if not output.is_relative_to((g.ROOT/'kg_datasets/dblp/course_v4_runs').resolve()): raise ValueError('Output outside runs')
    config = json.loads(CONFIG.read_text(encoding='utf-8')); vocabulary()
    if config['kind'] != 'candidate_not_graph_migration' or config['trainingAllowed'] or config['databaseWriteAllowed'] or config['abstractSourcesUsed'] or set(config['sources']) != ALLOWED_SOURCES: raise ValueError('Candidate scope changed')
    hashes = config['sources'] | {p.relative_to(g.ROOT).as_posix(): c.file_sha256(p) for p in (CONFIG, Path(__file__), Path(c.__file__), Path(g.__file__), Path(__file__).with_name('normalize_course_concepts.py'), g.ROOT/'tests/test_concept_alias_candidates.py')}
    if any(c.file_sha256(g.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Source hash drift')
    groups, mentions, summary = audit(config, c.read_jsonl(g.ROOT/MAPPING), c.read_jsonl(g.ROOT/(PRODUCTION+'documents.jsonl')), c.read_jsonl(g.ROOT/(PRODUCTION+'ner_predictions.jsonl')))
    manifest = json.loads((g.ROOT/(PRODUCTION+'manifest.json')).read_text(encoding='utf-8'))
    summary |= {'modelSourceManifestSha256': hashes[PRODUCTION+'manifest.json'], 'historicalWeightsSha256FromSourceManifest': {p: sha for p, sha in manifest['inputSha256'].items() if p.endswith('/model.safetensors')}, 'weightsReverifiedLive': False, 'inferenceExecuted': False, 'abstractSourceSha256': None, 'notice': config['notice']}
    output.mkdir(parents=True)
    try:
        c.write_jsonl(output/'groups.jsonl', groups); c.write_jsonl(output/'mentions.jsonl', mentions); c.write_json(output/'summary.json', summary)
        if any(c.file_sha256(g.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Sources changed during evidence export')
        c.write_json(output/'manifest.json', {'kind': summary['kind'], 'status': 'completed', 'inputSha256': hashes, 'filesSha256': {p.name: c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
    except Exception as error:
        c.write_json(output/'status.json', {'status': 'failed_no_candidate_promotion', 'error': str(error)}); raise
    print(summary, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True); run(parser.parse_args().output)
