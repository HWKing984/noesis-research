"""Source-first supplementary relation amendments; NER and historical results stay frozen."""
import argparse
import copy
import os
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import enrich_train_roles as role
from course_abstract_v1 import read, seal
from course_abstract_relation import CONTRACT as RELATION_CONTRACT

c, g, ner, relation = role.c, role.g, role.ner, role.re_model
CONTRACT = c.ROOT/'resources/course_source_annotation_revision_v1.json'
response = role.response


def checked_output(output):
    if output.exists(): raise FileExistsError('Preserve source revision output')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Output outside datasets')


def load_sources():
    config = read(CONTRACT); folder = c.ROOT/config['source']
    if config['version'] != 'supplement_relation_revision_v1' or any(config[k] is not False for k in ('trainingAllowed', 'inferenceAllowed', 'testContentAccessAllowed', 'automaticPromotionAllowed', 'independentHumanGold')) or c.file_sha256(RELATION_CONTRACT) != config['relationContractSha256']: raise ValueError('Revision scope drift')
    manifest = g.verified_files(folder, config['sourceManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Upstream source drift')
    refs = c.read_jsonl(folder/'references.jsonl'); receipts = c.read_jsonl(folder/'reviewed_receipts.jsonl')
    if len(refs) != 8 or len(refs) != len(receipts) or any(len({r[k] for r in refs}) != len(refs) for k in ('sampleId', 'groupId', 'arxivId')): raise ValueError('Duplicate/incomplete supplementary cohort')
    for ref, prior in zip(refs, receipts):
        if ref['split'] != 'dev' or ref['textKind'] != 'abstract' or c.validate_receipt(prior, ref) or prior['review'] is None: raise ValueError('Invalid reviewed source binding')
    if [r['arxivId'] for r in refs if r['arxivId'] in config['revisionCohort']] != config['revisionCohort']: raise ValueError('Source selection missing/reordered')
    before = role.rows_for(refs, receipts)
    if (len(before[0]), len(before[3]), len(before[1]), before[4], before[5]) != (7, 1, 88, 390, 478): raise ValueError('Source inventory drift')
    return config, manifest, refs, receipts


def build(decisions_path, reviews_path, output):
    output = output.resolve(); checked_output(output)
    # Pin mutable judgments before semantic reads, not after tokenization.
    hashes = {p: c.file_sha256(p) for p in (CONTRACT, RELATION_CONTRACT, decisions_path, reviews_path)}
    config, manifest, refs, old = load_sources(); folder = c.ROOT/config['source']
    paths = [CONTRACT, RELATION_CONTRACT, folder/'manifest.json', decisions_path, reviews_path, Path(__file__), Path(role.__file__), c.ROOT/'tests/test_source_annotation_revision.py', c.SCHEMA_PATH, c.CONFIG_PATH]
    paths += [c.ROOT/'scripts'/n for n in ('course_abstract_v1.py', 'course_abstract_relation.py', 'course_weak.py', 'course_graph.py', 'train_course_ner.py', 'train_course_relation.py', 'course_relation_model.py')]
    paths += [c.ROOT/'kg_datasets/models/scibert_24f92d32'/n for n in ('vocab.txt', 'config.json')]
    paths += [c.ROOT/'resources/course_graph_quality_v3_runtime.json', c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl']
    hashes.update({folder/p: sha for p, sha in manifest['filesSha256'].items()})
    hashes.update({c.ROOT/p: sha for p, sha in manifest['inputSha256'].items()})
    for path in paths: hashes.setdefault(path, c.file_sha256(path))
    source, reviews = read(decisions_path), read(reviews_path); cohort = config['revisionCohort']
    if reviews['independent'] is not False or source['modelPredictionsUsed'] is not False or [d['arxivId'] for d in source['documents']] != cohort or [j['arxivId'] for j in reviews['reviews']] != cohort: raise ValueError('Incomplete/source-first decision and self-review cohort')
    decisions = {d['arxivId']: d for d in source['documents']}; judgments = {j['arxivId']: j for j in reviews['reviews']}
    parent = read(RELATION_CONTRACT); initial, receipts, ledger = [], [], []
    def metadata(document, path): return {'provider': document['provider'], 'model': document['model'], 'promptSha256': hashes[CONTRACT], 'sourceArtifactSha256': hashes[path], 'createdAt': datetime.now(UTC).isoformat()}
    for ref, prior in zip(refs, old):
        receipt = prior
        if ref['arxivId'] in decisions:
            decision = decisions[ref['arxivId']]; review = judgments[ref['arxivId']]
            if set(review) != {'arxivId', 'reason'} or not review['reason'].strip(): raise ValueError('Missing actual self-review')
            amended = response(prior, ref, decision, parent)
            generated = c.make_receipt(amended, ref, metadata(source, decisions_path)); initial.append(generated)
            reviewed = copy.deepcopy(amended); reviewed['reviewOfSha256'] = generated['contentSha256']; reviewed['notes'] += ' Actual same-session source review: '+review['reason']
            receipt = c.make_receipt(reviewed, ref, metadata(reviews, reviews_path), previous=generated)
            ledger.append({'arxivId': ref['arxivId'], 'sampleId': ref['sampleId'], 'textSha256': ref['textSha256'], 'oldReceiptSha256': prior['contentSha256'], 'newReceiptSha256': receipt['contentSha256'], 'groups': decision['groups'], 'deferred': decision['deferred'], 'selfReview': review['reason']})
        receipts.append(receipt)
    docs, pairs, full, excluded, unknown, total = role.rows_for(refs, receipts); before = role.rows_for(refs, old)
    key = lambda p: (p['sampleId'], p['head']['entityId'], p['tail']['entityId'])
    inherited = {key(p): p for p in before[1]}; after = {key(p): p for p in pairs}; added = [p for p in pairs if key(p) not in inherited]
    if any(after.get(k, {}).get('label') != p['label'] for k, p in inherited.items()) or excluded != before[3] or total != before[5] or unknown != before[4]-len(added) or any(a['annotation']['entities'] != b['annotation']['entities'] for a, b in zip(old, receipts)): raise ValueError('Known labels, NER, candidates or quarantine conservation failed')
    os.environ.setdefault('HF_HUB_OFFLINE', '1'); tokenizer = relation.prepare_tokenizer(c.ROOT/'kg_datasets/models/scibert_24f92d32'); alignment = []
    for doc in docs:
        encoded = ner.encode_row(tokenizer, doc, 512); offsets, labels = encoded['offsets'], encoded['features']['labels']
        decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else t for o, t in zip(offsets, labels)], offsets, doc['text'])
        if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in doc['entities']]: raise ValueError('Strict BIO round-trip failed')
        alignment.append({'sampleId': doc['sampleId'], 'offsets': offsets, 'labels': labels})
    marked = [relation.encode_pair(tokenizer, p, 512) for p in pairs]
    output.mkdir(parents=True)
    try:
        shutil.copy2(folder/'references.jsonl', output/'references.jsonl')
        for name, values in (('generation_receipts', initial), ('reviewed_receipts', receipts), ('revision_ledger', ledger), ('ner_dev', docs), ('relation_dev', pairs), ('additional_relation_dev', added), ('full_relation_dev', full), ('excluded_ner', excluded), ('token_alignment', alignment)): c.write_jsonl(output/(name+'.jsonl'), values)
        full_ids = {d['sampleId'] for d in full}; full_eval = [p for p in pairs if p['sampleId'] in full_ids and p['label'] == 'EVALUATED_ON']
        summary = {'queue': len(refs), 'NER': len(docs), 'quarantines': len(excluded), 'revisedDocuments': len(initial), 'NERChanged': False, 'knownPairs': len(pairs), 'addedPairs': len(added), 'relationSupport': dict(Counter(p['label'] for p in pairs)), 'addedSupport': dict(Counter(p['label'] for p in added)), 'eligiblePairs': total, 'unknownPairs': unknown, 'completeDocuments': len(full), 'completeCoverage': len(full)/len(refs), 'completeEVALSupport': len(full_eval), 'completeEVALPapers': len({p['sampleId'] for p in full_eval}), 'maxMarkedTokens': max(len(e['features']['input_ids']) for e in marked), 'strictBIOPassed': True, 'trainingExecuted': False, 'inferenceExecuted': False, 'modelPredictionsUsedForAnnotation': False, 'testContentConsumed': False, 'independentHumanGold': False, 'modelPromoted': False, 'qualityPromotionPassed': False}
        if any(c.file_sha256(p) != sha for p, sha in hashes.items()): raise ValueError('Early-pinned input drift')
        c.write_json(output/'summary.json', summary); c.write_json(output/'contract.json', config); seal(output, list(hashes)); print(summary)
    except Exception as error:
        c.write_json(output/'failure.json', {'status': 'failed_no_fallback', 'errorType': type(error).__name__, 'error': str(error)}); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('decisions', 'reviews', 'output'): parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args(); build(args.decisions.resolve(), args.reviews.resolve(), args.output.resolve())
