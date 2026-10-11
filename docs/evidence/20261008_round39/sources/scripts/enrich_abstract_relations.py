"""Evidence-only TRAIN relation enrichment using the existing scoped resolver and receipt contract."""
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
from course_abstract_v1 import read, seal
from course_abstract_relation import NER_FIELDS, revise, rows_for

CONTRACT = c.ROOT/'resources/course_abstract_relation_enrichment_v1.json'


def source_cohort():
    config = read(CONTRACT); parent = c.ROOT/config['parentRelationContract']; source = c.ROOT/config['source']
    if config['version'] != 'abstract_relation_enrichment_v1' or c.file_sha256(parent) != config['parentRelationContractSha256'] or config['automaticPromotionAllowed'] is not False:
        raise ValueError('Relation enrichment contract drift')
    manifest = g.verified_files(source, config['sourceManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Upstream annotation source drift')
    refs = c.read_jsonl(source/'references.jsonl'); receipts = c.read_jsonl(source/'reviewed_receipts.jsonl')
    if len(refs) != len(receipts) or len({r['sampleId'] for r in refs}) != len(refs) or len({r['groupId'] for r in refs}) != len(refs): raise ValueError('Missing/duplicate source cohort')
    for ref, receipt in zip(refs, receipts):
        if ref['split'] != 'train' or ref['textKind'] != 'abstract' or hashlib.sha256(ref['text'].encode('utf-8')).hexdigest() != ref['textSha256'] or c.validate_receipt(receipt, ref) or receipt['review'] is None:
            raise ValueError('Source is not reviewed whole TRAIN data')
    selected = [r['arxivId'] for r, a in zip(refs, receipts) if r['sourceOrigin'] == 'fresh_locked_train_expansion' and c.eligible_tasks(a, r)['ner'] and any(e['label'] == 'DATASET' for e in a['annotation']['entities'])]
    if selected != config['revisionCohort']: raise ValueError('Selection differs from all named-dataset expansion documents')
    return config, read(parent), refs, receipts


def build(decisions_path, reviews_path, output):
    if output.exists(): raise FileExistsError('Preserve enrichment snapshot')
    config, parent, refs, old = source_cohort(); source = read(decisions_path); judgments = read(reviews_path)
    if [d['arxivId'] for d in source['documents']] != config['revisionCohort'] or [j['arxivId'] for j in judgments['reviews']] != config['revisionCohort'] or judgments['independent'] is not False:
        raise ValueError('Incomplete/mis-scoped explicit generation and self-review')
    decisions = {d['arxivId']: d for d in source['documents']}; reviews = {j['arxivId']: j for j in judgments['reviews']}
    generation, receipts, origins = [], [], []
    def metadata(document, path):
        return {'provider': document['provider'], 'model': document['model'], 'promptSha256': c.file_sha256(CONTRACT), 'sourceArtifactSha256': c.file_sha256(path), 'createdAt': datetime.now(UTC).isoformat()}
    for ref, prior in zip(refs, old):
        identity = ref['arxivId']; receipt = prior
        if identity in decisions:
            decision = decisions[identity]; judgment = reviews[identity]
            if decision['textSha256'] != ref['textSha256'] or set(judgment) != {'arxivId', 'reason'} or not judgment['reason'].strip(): raise ValueError('Wrong source hash or missing actual review')
            response = revise(prior['annotation'], ref, decision, parent)
            initial = c.make_receipt(response, ref, metadata(source, decisions_path)); generation.append(initial)
            reviewed = copy.deepcopy(response); reviewed['reviewOfSha256'] = initial['contentSha256']; reviewed['notes'] += ' Self-review: '+judgment['reason']
            receipt = c.make_receipt(reviewed, ref, metadata(judgments, reviews_path), previous=initial)
        if any(prior['annotation'][k] != receipt['annotation'][k] for k in NER_FIELDS): raise ValueError('Entity annotation changed during relation-only enrichment')
        receipts.append(receipt); origins.append({'sampleId': ref['sampleId'], 'upstreamReceiptSha256': prior['contentSha256'], 'relationRejudged': identity in decisions, 'NERReannotated': False})
    docs, pairs, full, excluded, unknown, total = rows_for(refs, receipts)
    os.environ.setdefault('HF_HUB_OFFLINE', '1'); tokenizer = re_model.prepare_tokenizer(c.ROOT/'kg_datasets/models/scibert_24f92d32')
    alignment = []
    for doc in docs:
        encoded = ner.encode_row(tokenizer, doc, parent['maxTokens']); offsets = encoded['offsets']; labels = encoded['features']['labels']
        decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else label for o, label in zip(offsets, labels)], offsets, doc['text'])
        if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in doc['entities']]: raise ValueError('Strict NER BIO round-trip failed')
        alignment.append({'sampleId': doc['sampleId'], 'tokens': len(offsets), 'offsets': offsets, 'labels': labels})
    encoded_pairs = [re_model.encode_pair(tokenizer, row, parent['maxTokens']) for row in pairs]
    before = rows_for(refs, old)[1]; key = lambda p: (p['sampleId'], p['head']['entityId'], p['tail']['entityId'])
    inherited = {key(p): p for p in before}; added = [p for p in pairs if key(p) not in inherited]
    evidence_fields = ('head', 'tail', 'label', 'evidence', 'reason')
    if any(any(p[k] != inherited[key(p)][k] for k in evidence_fields) for p in pairs if key(p) in inherited): raise ValueError('Previously resolved pair changed without explicit retraction')
    if len(pairs) != len(before)+len(added): raise ValueError('Previously resolved pair disappeared')
    summary = {'version': config['version'], 'wholeTrainCohort': len(refs), 'nerCandidates': len(docs), 'excludedNER': len(excluded), 'rejudgedRelationDocuments': len(generation),
        'inheritedReceipts': len(refs)-len(generation), 'previousKnownPairs': len(before), 'knownPairs': len(pairs), 'additionalKnownPairs': len(added),
        'relationSupport': dict(Counter(p['label'] for p in pairs)), 'additionalSupport': dict(Counter(p['label'] for p in added)),
        'eligiblePairs': total, 'unresolvedPairs': unknown, 'knownPairCoverage': len(pairs)/total, 'completeRelationDocuments': len(full),
        'positiveEVALSourceDocuments': len({p['sampleId'] for p in added if p['label'] == 'EVALUATED_ON'}),
        'maxMarkedTokens': max(len(e['features']['input_ids']) for e in encoded_pairs), 'strictBIOAllNERPassed': True, 'NERFieldsUnchanged': True,
        'independentHumanGold': False, 'devContentAccessed': False, 'testContentAccessed': False, 'trainingExecuted': False, 'inferenceExecuted': False, 'modelPromoted': False, 'qualityPromotionPassed': False}
    output.mkdir(parents=True)
    for name, rows in [('references', refs), ('generation_receipts', generation), ('reviewed_receipts', receipts), ('origins', origins), ('ner_train', docs), ('relation_train', pairs), ('additional_relation_train', added), ('full_relation_train', full), ('excluded_ner', excluded), ('token_alignment', alignment)]: c.write_jsonl(output/(name+'.jsonl'), rows)
    c.write_json(output/'summary.json', summary)
    seal(output, [CONTRACT, c.ROOT/config['parentRelationContract'], c.ROOT/config['source']/'manifest.json', decisions_path, reviews_path, Path(__file__),
        c.ROOT/'scripts/course_abstract_relation.py', c.ROOT/'scripts/course_weak.py', c.ROOT/'scripts/train_course_ner.py', c.ROOT/'scripts/train_course_relation.py', c.SCHEMA_PATH,
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
