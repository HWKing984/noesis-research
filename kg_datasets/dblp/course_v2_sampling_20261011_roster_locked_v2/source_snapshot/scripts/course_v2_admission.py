"""Two-stage evaluation admission. No fetching, annotation, prediction or training."""
import hashlib
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import urlsplit

import course_v2_identity as identity

FRAME = {'population': 'fresh_modern_arxiv_identifiable_AI_abstracts', 'fullDBLPRepresentative': False,
         'samplingFrameLocked': False, 'notice': 'Restricted identity-capable population; no population inventory or sample drawn yet.'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def prelock(assignments, excluded, aliases, frame):
    if (frame.get('population') != FRAME['population'] or frame.get('fullDBLPRepresentative') is not False
            or type(frame.get('samplingFrameLocked')) is not bool): raise ValueError('Restricted sampling frame required')
    counts = identity.validate_partition(assignments, excluded, aliases)
    members = [r | identity.identity(r, aliases) for r in assignments]
    evaluation = [r for r in members if r['split'] != 'train']
    return {'stage': 'metadata_prelock', 'status': 'pending_content_binding' if evaluation else 'no_new_evaluation_members',
        'assignments': members, 'counts': counts, 'samplingFrame': frame,
        'exclusionsSha256': digest(excluded), 'aliasIndexSha256': digest(aliases),
        'metadataSha256': digest(members), 'evaluationAuthorized': False}


def artifact(root, record):
    name = record.get('file')
    if not isinstance(name, str) or not name or Path(name).is_absolute(): raise ValueError('Relative evidence artifact required')
    path = (root/name).resolve()
    if not path.is_relative_to(root): raise ValueError('Evidence artifact escaped root')
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != record.get('sha256'): raise ValueError('Evidence artifact hash mismatch')
    return payload


def review(record, kind, row, context, root):
    if (record.get('kind') != kind or record.get('status') != 'cleared'
            or record.get('canonicalPaperId') != row['canonicalPaperId'] or record.get('textSha256') != row['textSha256']
            or record.get('contextSha256') != context or not isinstance(record.get('reviewer'), str) or not record['reviewer'].strip()
            or not isinstance(record.get('reason'), str) or not record['reason'].strip()): raise ValueError('Unbound source/duplicate review')
    stamp = datetime.fromisoformat(record['reviewedAtUTC'])
    if stamp.utcoffset() is None: raise ValueError('Review timestamp must have timezone')
    if not isinstance(record.get('evidenceArtifacts'), list) or not record['evidenceArtifacts']: raise ValueError('Missing review evidence artifacts')
    for evidence in record['evidenceArtifacts']:
        if not artifact(root, evidence): raise ValueError('Empty review evidence')


def finalize(lock, bindings, excluded, aliases, evidence_root):
    """Only call on separately authorized imports, never on model-selected samples."""
    if lock != prelock(lock['assignments'], excluded, aliases, lock['samplingFrame']): raise ValueError('Metadata/context lock changed')
    candidates = [r for r in lock['assignments'] if r['split'] != 'train']
    if not candidates: raise ValueError('Empty evaluation inventory cannot be finalized')
    if not lock['samplingFrame']['samplingFrameLocked']: raise ValueError('Sampling frame inventory not locked')
    if set(bindings) != {r['publicationId'] for r in candidates}: raise ValueError('Exact content binding inventory required')
    root = Path(evidence_root).resolve(); final = list(lock['assignments']); context = digest(lock)
    for row in candidates:
        bound = bindings[row['publicationId']]
        if not row.get('textSha256'): raise ValueError('Final evaluation requires precommitted textSha256')
        text = artifact(root, bound['content']).decode('utf-8')
        if not text.strip() or hashlib.sha256(text.encode('utf-8')).hexdigest() != row['textSha256']: raise ValueError('Content/text SHA mismatch')
        source = bound['sourceReview']
        if (urlsplit(source['sourceURL']).hostname not in identity.ARXIV_HOSTS
                or identity.canonical_arxiv(source['sourceURL']) != row['canonicalArxivId']): raise ValueError('Source identity mismatch')
        review(source, 'source_origin', row, context, root)
        review(bound['nearDuplicateReview'], 'near_duplicate', row, context, root)
    identity.validate_partition(final, excluded, aliases)
    return lock | {'stage': 'content_bound_reviewed', 'status': 'content_binding_checks_passed',
        'bindingsSha256': digest(bindings), 'evaluationAuthorized': False,
        'notice': 'Bound bytes and recorded reviews only; reference completeness and separate evaluation authorization still required.'}


def bind_content(lock, bindings, excluded, aliases, evidence_root):
    """Bind acquired hashes to the unchanged pre-lock, then enforce final checks."""
    if lock != prelock(lock['assignments'], excluded, aliases, lock['samplingFrame']): raise ValueError('Metadata/context lock changed')
    assignments = []; root = Path(evidence_root).resolve()
    for row in lock['assignments']:
        after = dict(row)
        if row['split'] != 'train':
            record = bindings[row['publicationId']]['content']; artifact(root, record)
            value = record['sha256']
            if row.get('textSha256') and row['textSha256'] != value: raise ValueError('Precommitted hash changed')
            after['textSha256'] = value
        assignments.append(after)
    updated = prelock(assignments, excluded, aliases, lock['samplingFrame'])
    return updated, digest(updated)
