"""Source-only development relation revision; unknown pairs never become default negatives."""
import argparse
import copy
import hashlib
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_graph as g
import course_weak as c
import train_course_ner as ner
import train_course_relation as re_model
from course_abstract_v1 import protocol, read, seal
from course_abstract_relation import NER_FIELDS, revise, rows_for

CONTRACT = c.ROOT/'resources/course_abstract_dev_relations_v1.json'


def source_cohort():
    config = read(CONTRACT); parent = c.ROOT/config['parentRelationContract']; folder = c.ROOT/config['source']
    if config['version'] != 'abstract_dev_relation_enrichment_v1' or c.file_sha256(parent) != config['parentRelationContractSha256'] or config['automaticPromotionAllowed'] is not False:
        raise ValueError('Development revision contract drift')
    manifest = g.verified_files(folder, config['sourceManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Upstream development source drift')
    _, queue = protocol(); refs = c.read_jsonl(folder/'dev_references.jsonl'); receipts = c.read_jsonl(folder/'dev_reviewed_receipts.jsonl')
    if refs != c.read_jsonl(queue/'dev_references.jsonl') or len(refs) != len(receipts) or len({r['sampleId'] for r in refs}) != len(refs) or len({r['groupId'] for r in refs}) != len(refs):
        raise ValueError('Missing/duplicate locked development cohort')
    for ref, receipt in zip(refs, receipts):
        if ref['split'] != 'dev' or ref['textKind'] != 'abstract' or hashlib.sha256(ref['text'].encode('utf-8')).hexdigest() != ref['textSha256'] or c.validate_receipt(receipt, ref) or receipt['review'] is None:
            raise ValueError('Source is not reviewed whole DEV data')
    selected = [r['arxivId'] for r, a in zip(refs, receipts) if c.eligible_tasks(a, r)['ner'] and not c.eligible_tasks(a, r)['relation']]
    if selected != config['revisionCohort']: raise ValueError('Revision scope differs from all incomplete development documents')
    return config, read(parent), refs, receipts


def build(decisions_path, reviews_path, output):
    if output.exists(): raise FileExistsError('Preserve development revision snapshot')
    config, parent, refs, old = source_cohort(); source = read(decisions_path); judgments = read(reviews_path)
    if [d['arxivId'] for d in source['documents']] != config['revisionCohort'] or [j['arxivId'] for j in judgments['reviews']] != config['revisionCohort'] or judgments['independent'] is not False:
        raise ValueError('Incomplete/mis-scoped generation and actual self-review')
    decisions = {d['arxivId']: d for d in source['documents']}; reviews = {j['arxivId']: j for j in judgments['reviews']}
    generation, receipts, origins = [], [], []
    def metadata(document, path):
        return {'provider': document['provider'], 'model': document['model'], 'promptSha256': c.file_sha256(CONTRACT), 'sourceArtifactSha256': c.file_sha256(path), 'createdAt': datetime.now(UTC).isoformat()}
    for ref, prior in zip(refs, old):
        identity = ref['arxivId']; receipt = prior
        if identity in decisions:
            decision = decisions[identity]; judgment = reviews[identity]
            if decision['textSha256'] != ref['textSha256'] or not decision['unresolvedReason'].strip() or set(judgment) != {'arxivId', 'reason'} or not judgment['reason'].strip():
                raise ValueError('Wrong source hash or missing inspection/review reason')
            response = revise(prior['annotation'], ref, decision, parent)
            initial = c.make_receipt(response, ref, metadata(source, decisions_path)); generation.append(initial)
            reviewed = copy.deepcopy(response); reviewed['reviewOfSha256'] = initial['contentSha256']; reviewed['notes'] += ' Self-review: '+judgment['reason']
            receipt = c.make_receipt(reviewed, ref, metadata(judgments, reviews_path), previous=initial)
        if any(prior['annotation'][k] != receipt['annotation'][k] for k in NER_FIELDS): raise ValueError('Development entity labels changed')
        receipts.append(receipt); origins.append({'sampleId': ref['sampleId'], 'upstreamReceiptSha256': prior['contentSha256'], 'relationRejudged': identity in decisions, 'NERReannotated': False})
    docs, pairs, full, excluded, unknown, total = rows_for(refs, receipts); before = rows_for(refs, old)
    key = lambda p: (p['sampleId'], p['head']['entityId'], p['tail']['entityId'])
    inherited = {key(p): p for p in before[1]}; added = [p for p in pairs if key(p) not in inherited]
    if len(pairs) != len(inherited)+len(added) or any(any(p[k] != inherited[key(p)][k] for k in ('head', 'tail', 'label', 'evidence', 'reason')) for p in pairs if key(p) in inherited):
        raise ValueError('Resolved development labels require separate explicit retraction to change')
    os.environ.setdefault('HF_HUB_OFFLINE', '1'); tokenizer = re_model.prepare_tokenizer(c.ROOT/'kg_datasets/models/scibert_24f92d32'); alignment = []
    for doc in docs:
        encoded = ner.encode_row(tokenizer, doc, parent['maxTokens']); offsets = encoded['offsets']; labels = encoded['features']['labels']
        decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else label for o, label in zip(offsets, labels)], offsets, doc['text'])
        if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in doc['entities']]: raise ValueError('Strict development NER BIO round-trip failed')
        alignment.append({'sampleId': doc['sampleId'], 'tokens': len(offsets), 'offsets': offsets, 'labels': labels})
    encoded_pairs = [re_model.encode_pair(tokenizer, p, parent['maxTokens']) for p in pairs]
    full_ids = {d['sampleId'] for d in full}; eval_full = [p for p in pairs if p['sampleId'] in full_ids and p['label'] == 'EVALUATED_ON']
    summary = {'version': config['version'], 'wholeDevCohort': len(refs), 'nerCandidates': len(docs), 'excludedNER': len(excluded), 'rejudgedRelationDocuments': len(generation),
        'previousKnownPairs': len(before[1]), 'knownPairs': len(pairs), 'additionalKnownPairs': len(added), 'relationSupport': dict(Counter(p['label'] for p in pairs)), 'additionalSupport': dict(Counter(p['label'] for p in added)),
        'eligiblePairs': total, 'unresolvedPairs': unknown, 'knownPairCoverage': len(pairs)/total, 'previousCompleteRelationDocuments': len(before[2]), 'completeRelationDocuments': len(full), 'fullDevDocumentCoverage': len(full)/len(refs),
        'completeDocumentEVALSupport': len(eval_full), 'completeDocumentEVALSourcePapers': len({p['sampleId'] for p in eval_full}),
        'maxMarkedTokens': max(len(e['features']['input_ids']) for e in encoded_pairs), 'strictBIOAllNERPassed': True, 'NERFieldsUnchanged': True, 'historicalKnownPairsUnchanged': True,
        'independentHumanGold': False, 'developmentPreviouslyExposed': True, 'testContentAccessed': False, 'trainingExecuted': False, 'inferenceExecuted': False, 'newMetricsProduced': False, 'modelPromoted': False, 'qualityPromotionPassed': False}
    output.mkdir(parents=True)
    for name, rows in [('references', refs), ('generation_receipts', generation), ('reviewed_receipts', receipts), ('origins', origins), ('ner_dev', docs), ('relation_dev', pairs), ('additional_relation_dev', added), ('full_relation_dev', full), ('excluded_ner', excluded), ('token_alignment', alignment)]:
        c.write_jsonl(output/(name+'.jsonl'), rows)
    c.write_json(output/'summary.json', summary); c.write_json(output/'contract.json', config)
    _, queue = protocol()
    seal(output, [CONTRACT, c.ROOT/config['parentRelationContract'], c.ROOT/config['source']/'manifest.json', queue/'manifest.json', decisions_path, reviews_path, Path(__file__),
        c.ROOT/'scripts/course_abstract_relation.py', c.ROOT/'scripts/course_abstract_v1.py', c.ROOT/'scripts/course_weak.py', c.ROOT/'scripts/train_course_ner.py', c.ROOT/'scripts/train_course_relation.py', c.SCHEMA_PATH,
        c.ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt', c.ROOT/'kg_datasets/models/scibert_24f92d32/config.json'])
    print(json.dumps(summary))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('decisions', 'reviews', 'output'): parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    try: build(args.decisions.resolve(), args.reviews.resolve(), args.output.resolve())
    except Exception as error:
        if args.output.exists() and not (args.output/'manifest.json').exists(): c.write_json(args.output/'failure.json', {'status': 'failed_no_synthetic_fallback', 'errorType': type(error).__name__, 'error': str(error)})
        raise
