"""Add source-local TRAIN evidence without changing sealed trainers or reference entities."""
import argparse
import copy
import hashlib
import os
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import enrich_train_roles as role
from course_abstract_v1 import read, seal

c, g, ner, re_model = role.c, role.g, role.ner, role.re_model
CONTRACT = c.ROOT/'resources/course_diverse_train_roles_v1.json'


def load_sources():
    config = read(CONTRACT); folder = c.ROOT/config['snapshot']
    if config['version'] != 'diverse_train_roles_v1' or any(config[k] is not False for k in ('trainingAllowed', 'testContentAccessAllowed', 'automaticPromotionAllowed')): raise ValueError('Evidence scope drift')
    if c.file_sha256(c.ROOT/config['relationContract']) != config['relationContractSha256']: raise ValueError('Relation scope drift')
    manifest = g.verified_files(folder, config['snapshotManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Upstream input drift')
    refs = c.read_jsonl(folder/'references.jsonl'); old = c.read_jsonl(folder/'reviewed_receipts.jsonl')
    if len(refs) != len(old) or len(refs) != config['expected']['trainReferences'] or any(len({r[k] for r in refs}) != len(refs) for k in ('sampleId', 'groupId', 'arxivId')): raise ValueError('Incomplete/duplicate TRAIN cohort')
    for ref, prior in zip(refs, old):
        if ref['split'] != 'train' or ref['textKind'] != 'abstract' or hashlib.sha256(ref['text'].encode()).hexdigest() != ref['textSha256'] or c.validate_receipt(prior, ref) or prior['review'] is None: raise ValueError('Unreviewed or mis-bound TRAIN source')
    selected = [r['arxivId'] for r, a in zip(refs, old) if r['arxivId'] in config['revisionCohort'] and c.eligible_tasks(a, r)['ner']]
    if selected != config['revisionCohort']: raise ValueError('Selected source missing, reordered or quarantined')
    before = role.rows_for(refs, old); expected = config['expected']
    if (len(before[0]), len(before[3]), len(before[1]), before[4], before[5]) != tuple(expected[k] for k in ('NERTrainFrozen', 'NERQuarantines', 'knownPairs', 'unknownPairs', 'eligiblePairs')) or before[1] != c.read_jsonl(folder/'relation_train.jsonl'): raise ValueError('Training inventory differs from sealed receipts')
    return config, read(c.ROOT/config['relationContract']), refs, old


def revision(prior, ref, decision, parent):
    pairs = {(p['head'], p['tail']): p['label'] for p in prior['annotation']['relations']}
    if any(pairs.get((h, t)) != 'UNRESOLVED' for group in decision['groups'] for h in group['heads'] for t in group['tails']): raise ValueError('Only previously unknown pairs may change')
    return role.response(prior, ref, decision, parent)


def build(decisions_path, reviews_path, output):
    output = output.resolve()
    if output.exists(): raise FileExistsError('Preserve evidence snapshot')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Output outside datasets')
    config, parent, refs, old = load_sources(); source = read(decisions_path); reviews = read(reviews_path)
    if [d['arxivId'] for d in source['documents']] != config['revisionCohort'] or [r['arxivId'] for r in reviews['reviews']] != config['revisionCohort'] or reviews['independent'] is not False: raise ValueError('Incomplete decision/self-review cohort')
    decisions = {d['arxivId']: d for d in source['documents']}; judgments = {j['arxivId']: j for j in reviews['reviews']}
    initial, receipts, ledger = [], [], []
    def metadata(document, path): return {'provider': document['provider'], 'model': document['model'], 'promptSha256': c.file_sha256(CONTRACT), 'sourceArtifactSha256': c.file_sha256(path), 'createdAt': datetime.now(UTC).isoformat()}
    for ref, prior in zip(refs, old):
        receipt = prior
        if ref['arxivId'] in decisions:
            decision = decisions[ref['arxivId']]; judgment = judgments[ref['arxivId']]
            if set(judgment) != {'arxivId', 'reason'} or not isinstance(judgment['reason'], str) or not judgment['reason'].strip(): raise ValueError('Missing actual source self-review')
            revised = revision(prior, ref, decision, parent); generated = c.make_receipt(revised, ref, metadata(source, decisions_path)); initial.append(generated)
            reviewed = copy.deepcopy(revised); reviewed['reviewOfSha256'] = generated['contentSha256']; reviewed['notes'] += ' Source self-review: '+judgment['reason']
            receipt = c.make_receipt(reviewed, ref, metadata(reviews, reviews_path), previous=generated)
            ledger.append({'arxivId': ref['arxivId'], 'sampleId': ref['sampleId'], 'textSha256': ref['textSha256'], 'upstreamReceiptSha256': prior['contentSha256'], 'reviewedReceiptSha256': receipt['contentSha256'], 'groups': decision['groups'], 'deferred': decision['deferred'], 'selfReview': judgment['reason']})
        receipts.append(receipt)
    docs, pairs, full, excluded, unknown, total = role.rows_for(refs, receipts); before = role.rows_for(refs, old)
    inherited = {re_model.pair_key(p): p for p in before[1]}; added = [p for p in pairs if re_model.pair_key(p) not in inherited]
    if len(pairs) != len(inherited)+len(added) or any(p != inherited[re_model.pair_key(p)] for p in pairs if re_model.pair_key(p) in inherited): raise ValueError('Resolved rows or receipt bindings changed')
    if excluded != before[3] or total != before[5] or unknown != before[4]-len(added) or Counter(p['label'] for p in added) != config['expected']['addedSupport']: raise ValueError('Known/unknown or quarantine conservation failed')
    folder = c.ROOT/config['snapshot']; frozen = c.read_jsonl(folder/'ner_train_frozen.jsonl')
    if [(d['sampleId'], d['textSha256'], d['entities']) for d in docs] != [(d['sampleId'], d['textSha256'], d['entities']) for d in frozen]: raise ValueError('Frozen NER inventory changed')
    os.environ.setdefault('HF_HUB_OFFLINE', '1'); tokenizer = re_model.prepare_tokenizer(c.ROOT/'kg_datasets/models/scibert_24f92d32')
    for doc in docs:
        encoded = ner.encode_row(tokenizer, doc, parent['maxTokens']); decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else t for o, t in zip(encoded['offsets'], encoded['features']['labels'])], encoded['offsets'], doc['text'])
        if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in doc['entities']]: raise ValueError('Strict BIO round-trip failed')
    encoded_pairs = [re_model.encode_pair(tokenizer, p, parent['maxTokens']) for p in pairs]
    dev = [p for p in folder.iterdir() if p.is_file() and 'dev' in p.stem]
    if len(dev) != 9: raise ValueError('Opaque development file cohort changed')
    paths = [CONTRACT, c.ROOT/config['relationContract'], folder/'manifest.json', decisions_path, reviews_path, Path(__file__), Path(role.__file__), c.ROOT/'tests/test_diverse_train_roles.py']
    paths += [c.ROOT/'scripts'/n for n in ('course_abstract_v1.py', 'course_abstract_relation.py', 'course_weak.py', 'course_graph.py', 'train_course_ner.py', 'train_course_relation.py', 'course_relation_model.py')]
    paths += [c.SCHEMA_PATH, c.CONFIG_PATH, c.ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt', c.ROOT/'kg_datasets/models/scibert_24f92d32/config.json']
    hashes = {p: c.file_sha256(p) for p in paths}; output.mkdir(parents=True)
    for name, rows in (('references', refs), ('generation_receipts', initial), ('reviewed_receipts', receipts), ('role_ledger', ledger), ('relation_train', pairs), ('additional_relation_train', added), ('full_relation_train', full), ('excluded_ner_train', excluded)): c.write_jsonl(output/(name+'.jsonl'), rows)
    for p in [folder/'ner_train_frozen.jsonl']+dev: shutil.copy2(p, output/p.name)
    if any(c.file_sha256(p) != c.file_sha256(output/p.name) for p in [folder/'ner_train_frozen.jsonl']+dev) or any(c.file_sha256(p) != sha for p, sha in hashes.items()): raise ValueError('Opaque file or source drift during build')
    summary = {'wholeTrainQueue': len(refs), 'NERTrainFrozen': len(docs), 'NEREntitiesFrozen': sum(len(d['entities']) for d in docs), 'NERQuarantines': len(excluded), 'reviewedRoleDocuments': len(initial), 'inheritedReceipts': len(refs)-len(initial), 'inheritedKnownPairs': len(inherited), 'knownPairs': len(pairs), 'addedKnownPairs': len(added), 'relationSupport': dict(Counter(p['label'] for p in pairs)), 'addedSupport': dict(Counter(p['label'] for p in added)), 'knownSourceDocuments': len({p['sampleId'] for p in pairs}), 'sourceDocumentsByClass': {label: len({p['sampleId'] for p in pairs if p['label'] == label}) for label in re_model.LABELS}, 'addedSourceDocumentsByClass': {label: len({p['sampleId'] for p in added if p['label'] == label}) for label in re_model.LABELS}, 'eligiblePairs': total, 'unknownPairs': unknown, 'knownPairCoverage': len(pairs)/total, 'completeTrainDocuments': len(full), 'maxMarkedTokens': max(len(e['features']['input_ids']) for e in encoded_pairs), 'opaqueDevFilesPreserved': len(dev), 'trainingExecuted': False, 'inferenceExecuted': False, 'devContentParsed': False, 'testContentConsumed': False, 'independentHumanGold': False, 'qualityPromotionPassed': False, 'modelPromoted': False}
    c.write_json(output/'summary.json', summary); c.write_json(output/'contract.json', config); seal(output, paths); print(summary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('decisions', 'reviews', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    build(args.decisions.resolve(), args.reviews.resolve(), args.output.resolve())
