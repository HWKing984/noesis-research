"""Add one source-reviewed METHOD omission; preserve old relation semantics via literal endpoint mapping."""
import argparse
import copy
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import course_graph as g
import course_weak as c
import train_course_ner as ner
from course_abstract_relation import rows_for
from course_abstract_v1 import read, seal

CONTRACT = c.ROOT/'resources/course_abstract_inventory_patch_v1.json'


def add_method(ref, prior, config):
    if ref['split'] != 'train' or ref['arxivId'] != config['arxivId'] or ref['textSha256'] != config['textSha256'] or config['sourceQuote'] not in ref['text'] or not c.eligible_tasks(prior, ref)['ner']: raise ValueError('Inventory patch source binding failed')
    addition = config['addEntity']; old = prior['annotation']; signature = lambda e: (e['start'], e['end'], e['label'])
    if set(addition) != {'start', 'end', 'text', 'label'} or addition['label'] != 'METHOD' or c.span_errors(addition, ref['text']) or any(e['start'] < addition['end'] and addition['start'] < e['end'] for e in old['entities']): raise ValueError('Added METHOD invalid/overlapping')
    entities = sorted(copy.deepcopy(old['entities'])+[copy.deepcopy(addition)], key=lambda e: e['start'])
    for i, e in enumerate(entities, 1): e['entityId'] = f'e{i}'
    by_span = {signature(e): e['entityId'] for e in entities}; mapping = {e['entityId']: by_span[signature(e)] for e in old['entities']}
    remapped = {(mapping[p['head']], mapping[p['tail']]): copy.deepcopy(p) | {'head': mapping[p['head']], 'tail': mapping[p['tail']]} for p in old['relations']}
    candidates = c.candidate_pairs(entities)
    if len(remapped) != len(old['relations']) or not set(remapped) <= set(candidates): raise ValueError('Old relation identity lost')
    relations = [remapped.get((h, t), {'head': h, 'tail': t, 'label': 'UNRESOLVED', 'evidence': None, 'reason': 'New background-family endpoint has no certified task/benchmark assertion; do not inherit another method evaluation or fill negative.'}) for h, t in candidates]
    ann = copy.deepcopy(old); ann.update(entities=entities, relations=relations, reviewOfSha256=None, relationStatus='unresolved', relationReason='New background-family pairs require separate evidence judgments.'); ann['notes'] += ' Source-bound inventory repair: '+config['decision']
    if c.validate_response(ann, ref): raise ValueError('Patched annotation invalid')
    return ann, mapping


def build(output):
    if output.exists(): raise FileExistsError('Preserve inventory patch')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Patch output outside dataset directory')
    config = read(CONTRACT); parent = (c.ROOT/config['snapshot']).resolve()
    if config['version'] != 'abstract_train_inventory_patch_v1' or any(config[k] is not False for k in ('independent', 'trainingAllowed', 'automaticPromotionAllowed')) or any(not config[k].strip() for k in ('decision', 'selfReview')) or not parent.is_relative_to(c.ROOT/'kg_datasets/dblp'): raise ValueError('Patch contract drift')
    manifest = g.verified_files(parent, config['snapshotManifestSha256'])
    if any(c.file_sha256(c.ROOT/p) != sha for p, sha in manifest['inputSha256'].items()): raise ValueError('Parent source drift')
    refs = c.read_jsonl(parent/'train_references.jsonl'); old = c.read_jsonl(parent/'train_reviewed_receipts.jsonl')
    if len(refs) != len(old) or len(refs) != 58 or len({r['sampleId'] for r in refs}) != 58 or any(r['split'] != 'train' or c.validate_receipt(a, r) for r, a in zip(refs, old)): raise ValueError('Missing/wrong training source')
    index = next(i for i, r in enumerate(refs) if r['arxivId'] == config['arxivId']); ref = refs[index]; ann, mapping = add_method(ref, old[index], config)
    metadata = {'provider': config['provider'], 'model': config['model'], 'promptSha256': c.file_sha256(CONTRACT), 'sourceArtifactSha256': c.file_sha256(CONTRACT), 'createdAt': datetime.now(UTC).isoformat()}
    initial = c.make_receipt(ann, ref, metadata); reviewed = copy.deepcopy(ann); reviewed['reviewOfSha256'] = initial['contentSha256']; reviewed['notes'] += ' Actual same-session self-review: '+config['selfReview']
    receipt = c.make_receipt(reviewed, ref, metadata | {'createdAt': datetime.now(UTC).isoformat()}, previous=initial); receipts = old.copy(); receipts[index] = receipt
    rows, pairs, full, excluded, unknown, total = rows_for(refs, receipts); support = Counter(e['label'] for r in rows for e in r['entities'])
    if (len(rows), len(pairs), len(full), len(excluded), unknown, total) != (54, 267, 8, 4, 1647, 1914) or support != {'METHOD': 403, 'TASK': 196, 'DATASET': 44}: raise ValueError('Patch support/pair inventory drift')
    from transformers import BertTokenizerFast
    tokenizer = BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32', local_files_only=True, do_lower_case=True); alignments = []
    for row in rows:
        encoded = ner.encode_row(tokenizer, row, 512); offsets = encoded['offsets']; labels = encoded['features']['labels']; decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else tag for o, tag in zip(offsets, labels)], offsets, row['text'])
        if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]: raise ValueError('Inventory repair BIO failed')
        alignments.append({'sampleId': row['sampleId'], 'offsets': offsets, 'labels': labels})
    paths = [CONTRACT, Path(__file__), parent/'manifest.json', parent/'train_references.jsonl', parent/'train_reviewed_receipts.jsonl', c.CONFIG_PATH, c.SCHEMA_PATH, c.ROOT/'scripts/course_weak.py', c.ROOT/'scripts/course_graph.py', c.ROOT/'scripts/course_abstract_relation.py', c.ROOT/'scripts/course_abstract_v1.py', c.ROOT/'scripts/train_course_ner.py', c.ROOT/'resources/course_abstract_relation_v1.json', c.ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt', c.ROOT/'kg_datasets/models/scibert_24f92d32/config.json', c.ROOT/'kg_datasets/dblp/course_abstract_queue_20261008_32/test_references.jsonl', c.ROOT/'resources/course_graph_runtime.json']
    hashes = {p: c.file_sha256(p) for p in paths}; output.mkdir(parents=True)
    try:
        opaque = [p for p in parent.iterdir() if p.is_file() and ('dev' in p.stem or p.name in ('train_references.jsonl', 'scope_review_ledger.jsonl'))]
        for path in opaque: shutil.copy2(path, output/path.name)
        for name, values in [('train_reviewed_receipts', receipts), ('ner_train', rows), ('relation_train', pairs), ('full_relation_train', full), ('excluded_ner_train', excluded), ('token_alignment_train', alignments), ('inventory_generation_receipts', [initial])]: c.write_jsonl(output/(name+'.jsonl'), values)
        ledger = {'arxivId': ref['arxivId'], 'sourceTextSha256': ref['textSha256'], 'oldReceiptSha256': old[index]['contentSha256'], 'newReceiptSha256': receipt['contentSha256'], 'addedEntity': config['addEntity'], 'oldToNewEntityIds': mapping, 'oldCandidates': 45, 'newCandidates': 60, 'newUnknownPairs': 15, 'oldRelationLabelsEvidenceReasonsPreserved': True, 'independent': False}
        c.write_json(output/'inventory_patch.json', ledger); c.write_json(output/'contract.json', config)
        c.write_json(output/'summary.json', {'status': 'completed', 'version': config['version'], 'sourceReviewDocuments': 11, 'freshReviewedDocumentsComparedTo43': 6, 'inheritedReceiptDocumentsComparedTo43': 52, 'trainQueue': 58, 'NERtrain': 54, 'NERexcluded': 4, 'entitySupport': dict(support), 'resolvedRelations': 267, 'relationSupport': dict(Counter(p['label'] for p in pairs)), 'unknownPairs': unknown, 'eligiblePairs': total, 'completeRelationDocuments': len(full), 'DATASETSupportIncreased': False, 'trainingExecuted': False, 'devCopiedAsOpaqueBytes': True, 'testSemanticallyRead': False, 'modelPromoted': False, 'qualityPromotionPassed': False, 'independentHumanGold': False})
        if any(c.file_sha256(p) != sha for p, sha in hashes.items()) or any(c.file_sha256(p) != c.file_sha256(output/p.name) for p in opaque): raise ValueError('Patch input/opaque dev drift')
        g.verified_files(parent, config['snapshotManifestSha256']); seal(output, paths); print({'NERtrain': 54, 'quarantined': 4, 'METHOD': 403, 'DATASET': 44, 'resolved': 267, 'unknown': unknown, 'trainingExecuted': False})
    except Exception as error:
        c.write_json(output/'failure.json', {'status': 'failed_no_fallback', 'errorType': type(error).__name__, 'error': str(error)}); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True); args = parser.parse_args(); build(args.output.resolve())
