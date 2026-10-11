"""Experiment-specific train roster/data binding. No training or authorization.

The parent manifest anchor is code-reviewed, never supplied by a caller's lock.
Changing the training cohort requires a new explicit experiment/version anchor.
This is tamper detection within a controlled checkout, not a digital signature.
"""
import hashlib
import json
from pathlib import Path

import course_v2_admission as admission
import course_v2_identity as identity

VERSION = 'course_v2_training_roster_20261011_v1'
PARENT_SHA = 'a48a65f4f86e499e2dd7e06bb3361cabc810493110c33f478c027475af64db94'
CORE = ('references.jsonl', 'generation_receipts.jsonl', 'reviewed_receipts.jsonl',
        'relation_ledger.jsonl', 'ner_candidates.jsonl', 're_candidates.jsonl')
BOUND = ('split_lock.json', *CORE, 'identity_alias_index.json', 'historical_exclusions.jsonl')
FIELDS = {'publicationId', 'groupId', 'textSha256', 'arxivId', 'canonicalArxivId',
          'canonicalPaperId', 'sourceURL', 'split'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def normalized(rows, aliases):
    if not isinstance(rows, list) or not rows:
        raise ValueError('Training roster cannot be empty')
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) - FIELDS or row.get('split') != 'train':
            raise ValueError('Invalid training roster metadata')
        result.append(row | identity.identity(row, aliases))
    keys = [r['canonicalPaperId'] for r in result]
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate training identity')
    return sorted(result, key=lambda r: r['canonicalPaperId'])


def expected(parent):
    parent = Path(parent).resolve()
    if sha(parent/'manifest.json') != PARENT_SHA:
        raise ValueError('Training parent manifest differs from approved version')
    manifest = read(parent/'manifest.json')
    hashes = {}
    for name in BOUND:
        path = (parent/name).resolve()
        if not path.is_relative_to(parent) or sha(path) != manifest['filesSha256'][name]:
            raise ValueError('Training data/source binding changed: '+name)
        hashes[name] = sha(path)
    aliases = read(parent/'identity_alias_index.json')
    train = normalized(read(parent/'split_lock.json')['assignments'], aliases)
    if len(train) != 12:
        raise ValueError('Approved training cohort requires twelve documents')
    return {'version': VERSION, 'parentManifestSha256': PARENT_SHA,
            'trainingDocuments': 12, 'assignments': train,
            'rosterSha256': admission.digest(train), 'boundFilesSha256': hashes,
            'trainingDataVersionSha256': admission.digest({n: hashes[n] for n in CORE}),
            'trainingAuthorized': False,
            'notice': 'Fixed cohort and data bytes only; not semantic certification or training admission.'}


def validate(folder, train, aliases):
    folder = Path(folder).resolve()
    parent = folder/'audit_parent'
    lock = expected(parent)
    if read(folder/'training_roster_lock.json') != lock:
        raise ValueError('Training roster lock differs from approved parent')
    if aliases != read(parent/'identity_alias_index.json'):
        raise ValueError('Training alias context differs from approved parent')
    if normalized(train, aliases) != lock['assignments']:
        raise ValueError('Training roster changed; explicit new experiment version required')
    return lock
