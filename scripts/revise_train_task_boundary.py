"""One source-bound train TASK span correction; inherited dev is copied as opaque bytes."""
import argparse
import copy
import shutil
from datetime import UTC, datetime
from pathlib import Path
from collections import Counter

import audit_abstract_ner_training as audit
import course_weak as c
import train_course_ner as ner
from course_abstract_relation import rows_for
from course_abstract_v1 import read, seal

CONTRACT = c.ROOT/'resources/course_abstract_task_boundary_v1.json'


def amend(config, ref, prior):
    if ref['split'] != 'train' or ref['arxivId'] != config['arxivId'] or ref['sampleId'] != config['sampleId'] or ref['textSha256'] != config['textSha256'] or c.validate_receipt(prior, ref): raise ValueError('Revision source binding failed')
    ann = copy.deepcopy(prior['annotation']); index = next(i for i, e in enumerate(ann['entities']) if e['entityId'] == config['entityId'])
    if ann['entities'][index] != config['before'] or config['equivalentSourceOccurrence'] not in ann['entities'] or config['sourceQuote'] not in ref['text'] or c.span_errors(config['after'], ref['text']) or config['before']['text'] != ref['text'][377:393]: raise ValueError('Original/updated literal occurrence drift')
    affected = [p for p in ann['relations'] if config['entityId'] in (p['head'], p['tail'])]
    if len(affected) != config['expectedAffectedUnknownPairs'] or any(p['label'] != 'UNRESOLVED' for p in affected): raise ValueError('Changed endpoint has resolved relation; explicit rejudgment required')
    ann['entities'][index] = copy.deepcopy(config['after']); ann['reviewOfSha256'] = None; ann['notes'] += ' Source-bound train task revision: '+config['decision']
    if c.validate_response(ann, ref): raise ValueError('Invalid revised annotation')
    return ann


def build(output):
    if output.exists(): raise FileExistsError('Preserve training revision')
    if not output.is_relative_to((c.ROOT/'kg_datasets/dblp').resolve()): raise ValueError('Revision outside dataset directory')
    config = read(CONTRACT)
    if config['version'] != 'abstract_train_task_boundary_v1' or c.file_sha256(c.ROOT/config['diagnosticContract']) != config['diagnosticContractSha256'] or any(config[k] is not False for k in ('independent', 'trainingAllowed', 'semanticDevReadAllowed', 'semanticTestReadAllowed', 'automaticPromotionAllowed')) or any(not config[k].strip() for k in ('decision', 'selfReview')): raise ValueError('Revision contract drift')
    parent, _, refs, _ = audit.load_inputs(); folder = c.ROOT/parent['snapshot']; old = c.read_jsonl(folder/'train_reviewed_receipts.jsonl'); index = next(i for i, r in enumerate(refs) if r['arxivId'] == config['arxivId']); ref = refs[index]
    metadata = {'provider': config['provider'], 'model': config['model'], 'promptSha256': c.file_sha256(CONTRACT), 'sourceArtifactSha256': c.file_sha256(CONTRACT), 'createdAt': datetime.now(UTC).isoformat()}
    annotation = amend(config, ref, old[index]); initial = c.make_receipt(annotation, ref, metadata)
    reviewed_annotation = copy.deepcopy(annotation); reviewed_annotation['reviewOfSha256'] = initial['contentSha256']; reviewed_annotation['notes'] += ' Actual same-session self-review: '+config['selfReview']
    replacement = c.make_receipt(reviewed_annotation, ref, metadata | {'createdAt': datetime.now(UTC).isoformat()}, previous=initial); receipts = old.copy(); receipts[index] = replacement
    rows, pairs, full, excluded, unknown, total = rows_for(refs, receipts)
    if len(rows) != 50 or len(pairs) != 267 or len(full) != 6 or len(excluded) != 8 or unknown != 1578 or total != 1845 or Counter(p['label'] for p in pairs) != {'USED_FOR': 183, 'EVALUATED_ON': 58, 'NO_RELATION': 26}: raise ValueError('Unexpected cohort/relation mutation')
    from transformers import BertTokenizerFast
    tokenizer = BertTokenizerFast.from_pretrained(c.ROOT/'kg_datasets/models/scibert_24f92d32', local_files_only=True, do_lower_case=True); alignments = []
    for row in rows:
        encoded = ner.encode_row(tokenizer, row, 512); offsets = encoded['offsets']; labels = encoded['features']['labels']; decoded = ner.decode_bio([0 if tuple(o) == (0, 0) else tag for o, tag in zip(offsets, labels)], offsets, row['text'])
        if decoded['invalidTransitions'] or decoded['entities'] != [{k: e[k] for k in ('start', 'end', 'text', 'label')} for e in row['entities']]: raise ValueError('Revised train BIO failed')
        alignments.append({'sampleId': row['sampleId'], 'offsets': offsets, 'labels': labels})
    inputs = [CONTRACT, audit.CONTRACT, audit.REVIEW, Path(__file__), c.ROOT/'scripts/audit_abstract_ner_training.py', c.ROOT/'scripts/course_weak.py', c.ROOT/'scripts/course_abstract_relation.py', c.ROOT/'scripts/train_course_ner.py', c.SCHEMA_PATH, folder/'manifest.json', folder/'train_references.jsonl', folder/'train_reviewed_receipts.jsonl', c.ROOT/'kg_datasets/models/scibert_24f92d32/vocab.txt']
    hashes = {p: c.file_sha256(p) for p in inputs}; output.mkdir(parents=True)
    try:
        for source in folder.iterdir():
            if source.is_file() and ('dev' in source.stem or source.name == 'train_references.jsonl'): shutil.copy2(source, output/source.name)
        for name, values in [('train_reviewed_receipts', receipts), ('ner_train', rows), ('relation_train', pairs), ('full_relation_train', full), ('excluded_ner_train', excluded), ('token_alignment_train', alignments), ('changed_generation_receipts', [initial])]: c.write_jsonl(output/(name+'.jsonl'), values)
        ledger = {'sampleId': ref['sampleId'], 'sourceTextSha256': ref['textSha256'], 'oldReceiptSha256': old[index]['contentSha256'], 'newReceiptSha256': replacement['contentSha256'], 'before': config['before'], 'after': config['after'], 'inheritedEntities': 20, 'affectedUnknownPairs': 10, 'independent': False}
        c.write_json(output/'revision.json', ledger); c.write_json(output/'contract.json', config)
        summary = {'status': 'completed', 'version': config['version'], 'trainQueue': 58, 'NERtrain': 50, 'NERexcluded': 8, 'resolvedRelations': 267, 'unknownPairs': 1578, 'freshlyReviewedDocuments': 1, 'inheritedReceiptDocuments': 57, 'changedEntitySpans': 1, 'sourceTextChanged': False, 'devCopiedAsOpaqueBytes': True, 'testSemanticallyRead': False, 'trainingExecuted': False, 'modelPromoted': False, 'qualityPromotionPassed': False}
        if any(c.file_sha256(p) != sha for p, sha in hashes.items()): raise ValueError('Revision input drift')
        if any(c.file_sha256(output/p.name) != c.file_sha256(p) for p in folder.iterdir() if p.is_file() and 'dev' in p.stem): raise ValueError('Dev bytes changed')
        if any(receipt != previous for i, (receipt, previous) in enumerate(zip(receipts, old)) if i != index): raise ValueError('Unrelated receipts changed')
        c.write_json(output/'summary.json', summary); seal(output, inputs); print(summary)
    except Exception as error:
        c.write_json(output/'failure.json', {'status': 'failed_no_fallback', 'errorType': type(error).__name__, 'error': str(error)}); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True); args = parser.parse_args(); build(args.output.resolve())
