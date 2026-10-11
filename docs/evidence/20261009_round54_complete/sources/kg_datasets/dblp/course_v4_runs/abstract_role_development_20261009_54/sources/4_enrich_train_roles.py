"""Source-local role judgments on frozen52 TRAIN data; no model/test content access."""
import argparse
import copy
import hashlib
import os
import re
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_graph as g
from course_abstract_v1 import read, seal
from course_abstract_relation import NER_FIELDS, revise, rows_for
import train_course_ner as ner
import train_course_relation as re_model

c = g.c
CONTRACT = c.ROOT/'resources/course_abstract_role_enrichment_v1.json'


def load_sources():
    config = read(CONTRACT); folder = c.ROOT/config['snapshot']
    if config['version'] != 'abstract_role_enrichment_v1' or any(config[k] is not False for k in ('trainingAllowed', 'testContentAccessAllowed', 'automaticPromotionAllowed')): raise ValueError('Role contract drift')
    if c.file_sha256(c.ROOT/config['relationContract']) != config['relationContractSha256']: raise ValueError('Relation scope drift')
    manifest = g.verified_files(folder, config['snapshotManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Source drift')
    refs = c.read_jsonl(folder/'train_references.jsonl')+c.read_jsonl(folder/'additional_references.jsonl')
    receipts = c.read_jsonl(folder/'train_reviewed_receipts.jsonl')+c.read_jsonl(folder/'additional_receipts.jsonl')
    if len(refs) != len(receipts) or len(refs) != 70 or any(len({r[k] for r in refs}) != 70 for k in ('sampleId', 'groupId', 'arxivId')): raise ValueError('Training cohort incomplete/duplicate')
    for ref, receipt in zip(refs, receipts):
        if ref['split'] != 'train' or ref['textKind'] != 'abstract' or hashlib.sha256(ref['text'].encode()).hexdigest() != ref['textSha256'] or c.validate_receipt(receipt, ref) or receipt['review'] is None: raise ValueError('Invalid source-bound reviewed training data')
    chosen = [r['arxivId'] for r, a in zip(refs[:62], receipts[:62]) if re.search('distill|prun|compress|quantiz', r['text'], re.I)]
    chosen += [r['arxivId'] for r, a in zip(refs[62:], receipts[62:]) if c.eligible_tasks(a, r)['ner']]
    if chosen != config['revisionCohort'] or any(not c.eligible_tasks(a, r)['ner'] for r, a in zip(refs, receipts) if r['arxivId'] in chosen): raise ValueError('Fixed source selection changed or quarantined')
    return config, read(c.ROOT/config['relationContract']), refs, receipts


def response(prior, ref, decision, parent):
    if set(decision) != {'arxivId', 'textSha256', 'upstreamReceiptSha256', 'groups', 'deferred'} or decision['arxivId'] != ref['arxivId'] or decision['textSha256'] != ref['textSha256'] or decision['upstreamReceiptSha256'] != prior['contentSha256'] or not isinstance(decision['deferred'], str) or not decision['deferred'].strip(): raise ValueError('Unbound/undocumented role judgment')
    revised = revise(prior['annotation'], ref, decision, parent)
    if any(revised[k] != prior['annotation'][k] for k in NER_FIELDS): raise ValueError('Role judgment changed NER')
    return revised


def build(decisions_path, reviews_path, output):
    if output.exists(): raise FileExistsError('Preserve role annotation artifact')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Output outside datasets')
    config, parent, refs, old = load_sources(); source = read(decisions_path); review = read(reviews_path)
    if [d['arxivId'] for d in source['documents']] != config['revisionCohort'] or [j['arxivId'] for j in review['reviews']] != config['revisionCohort'] or review['independent'] is not False: raise ValueError('Incomplete decision/self-review coverage')
    decisions = {d['arxivId']: d for d in source['documents']}; judgments = {d['arxivId']: d for d in review['reviews']}; receipts = []; initial = []; ledger = []
    def metadata(document, path): return {'provider': document['provider'], 'model': document['model'], 'promptSha256': c.file_sha256(CONTRACT), 'sourceArtifactSha256': c.file_sha256(path), 'createdAt': datetime.now(UTC).isoformat()}
    for ref, prior in zip(refs, old):
        receipt = prior
        if ref['arxivId'] in decisions:
            decision = decisions[ref['arxivId']]; judgment = judgments[ref['arxivId']]
            if set(judgment) != {'arxivId', 'reason'} or not isinstance(judgment['reason'], str) or not judgment['reason'].strip(): raise ValueError('Missing actual self-review')
            revised = response(prior, ref, decision, parent); generated = c.make_receipt(revised, ref, metadata(source, decisions_path)); initial.append(generated)
            reviewed = copy.deepcopy(revised); reviewed['reviewOfSha256'] = generated['contentSha256']; reviewed['notes'] += ' Source-role self-review: '+judgment['reason']
            receipt = c.make_receipt(reviewed, ref, metadata(review, reviews_path), previous=generated)
            ledger.append({'arxivId': ref['arxivId'], 'sampleId': ref['sampleId'], 'textSha256': ref['textSha256'], 'upstreamReceiptSha256': prior['contentSha256'], 'reviewedReceiptSha256': receipt['contentSha256'], 'groups': decision['groups'], 'deferred': decision['deferred'], 'selfReview': judgment['reason']})
        receipts.append(receipt)
    docs, pairs, full, excluded, unknown, total = rows_for(refs, receipts); before = rows_for(refs, old); key = lambda p: re_model.pair_key(p)
    inherited = {key(p): p for p in before[1]}; added = [p for p in pairs if key(p) not in inherited]
    if len(before[1]) != 271 or len(pairs) != 271+len(added) or any(p != inherited[key(p)] for p in pairs if key(p) in inherited): raise ValueError('Previously resolved rows changed or disappeared')
    if before[3] != excluded or total != before[5] or unknown != before[4]-len(added) or len(docs) != 65: raise ValueError('Candidate/quarantine conservation failed')
    os.environ.setdefault('HF_HUB_OFFLINE', '1'); tokenizer = re_model.prepare_tokenizer(c.ROOT/'kg_datasets/models/scibert_24f92d32')
    for doc in docs:
        encoded = ner.encode_row(tokenizer, doc, 512); decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else t for o, t in zip(encoded['offsets'], encoded['features']['labels'])], encoded['offsets'], doc['text'])
        if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in doc['entities']]: raise ValueError('Strict BIO round-trip failed')
    encoded_pairs = [re_model.encode_pair(tokenizer, p, 512) for p in pairs]
    paths = [CONTRACT, c.ROOT/config['relationContract'], c.ROOT/config['snapshot']/'manifest.json', decisions_path, reviews_path, Path(__file__), c.ROOT/'tests/test_train_roles.py']
    paths += [c.ROOT/'scripts'/n for n in ('course_abstract_relation.py', 'course_abstract_v1.py', 'course_weak.py', 'course_graph.py', 'train_course_ner.py', 'train_course_relation.py', 'course_relation_model.py')]
    paths += [c.SCHEMA_PATH, c.CONFIG_PATH, c.ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt', c.ROOT/'kg_datasets/models/scibert_24f92d32/config.json', c.ROOT/'resources/course_graph_runtime.json', c.ROOT/'resources/course_graph_quality_runtime.json', c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl']
    hashes = {p: c.file_sha256(p) for p in paths}; output.mkdir(parents=True)
    for name, rows in (('references', refs), ('generation_receipts', initial), ('reviewed_receipts', receipts), ('role_ledger', ledger), ('relation_train', pairs), ('additional_relation_train', added), ('full_relation_train', full), ('excluded_ner_train', excluded)): c.write_jsonl(output/(name+'.jsonl'), rows)
    source_folder = c.ROOT/config['snapshot']; shutil.copy2(source_folder/'ner_train.jsonl', output/'ner_train_frozen.jsonl')
    frozen_ner = c.read_jsonl(source_folder/'ner_train.jsonl')
    if [(d['sampleId'], d['textSha256'], d['entities']) for d in docs] != [(d['sampleId'], d['textSha256'], d['entities']) for d in frozen_ner]: raise ValueError('NER semantic inventory differs from frozen52 rows')
    dev = [p for p in source_folder.iterdir() if p.is_file() and 'dev' in p.stem]
    for p in dev: shutil.copy2(p, output/p.name)
    if len(dev) != 9 or any(c.file_sha256(p) != c.file_sha256(output/p.name) for p in dev) or any(c.file_sha256(p) != sha for p, sha in hashes.items()): raise ValueError('Opaque dev or source drift')
    summary = {'wholeTrainQueue': 70, 'NERtrainFrozen': 65, 'NEREntitiesFrozen': 787, 'NERQuarantines': 5, 'reviewedRoleDocuments': len(initial), 'inheritedReceipts': 70-len(initial), 'inheritedKnownPairs': 271, 'knownPairs': len(pairs), 'addedKnownPairs': len(added), 'relationSupport': dict(Counter(p['label'] for p in pairs)), 'addedSupport': dict(Counter(p['label'] for p in added)), 'eligiblePairs': total, 'unknownPairs': unknown, 'knownPairCoverage': len(pairs)/total, 'completeTrainDocuments': len(full), 'addedBenchmarkSourceDocuments': len({p['sampleId'] for p in added if p['label'] == 'EVALUATED_ON'}), 'maxMarkedTokens': max(len(p['features']['input_ids']) for p in encoded_pairs), 'opaqueDevFilesPreserved': 9, 'trainingExecuted': False, 'inferenceExecuted': False, 'devContentAccessed': False, 'testContentConsumed': False, 'independentHumanGold': False, 'qualityPromotionPassed': False, 'modelPromoted': False, 'NERSource': config['snapshot']+'/ner_train.jsonl'}
    c.write_json(output/'summary.json', summary); c.write_json(output/'contract.json', config); seal(output, paths); print(summary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('action', choices=('preflight', 'build'))
    for key in ('decisions', 'reviews', 'output'): parser.add_argument('--'+key, type=Path)
    args = parser.parse_args()
    if args.action == 'preflight': print({'trainSources': len(load_sources()[2]), 'selected': load_sources()[0]['revisionCohort'], 'devAndTestContentRead': False})
    elif any(getattr(args, k) is None for k in ('decisions', 'reviews', 'output')): parser.error('Fresh decisions/reviews/output required')
    else: build(args.decisions.resolve(), args.reviews.resolve(), args.output.resolve())
