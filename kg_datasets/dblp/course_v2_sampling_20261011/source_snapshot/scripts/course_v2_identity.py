"""Canonical arXiv identity and fail-closed metadata/assessment guards; no retrieval."""
import re
from collections import Counter
from urllib.parse import urlsplit

ARXIV_HOSTS = {'arxiv.org', 'www.arxiv.org', 'export.arxiv.org'}
MIN_REFERENCE_PAPERS = 10


def canonical_arxiv(value):
    if not isinstance(value, str) or not value.strip(): raise ValueError('Missing arXiv identity')
    value = value.strip()
    if re.match(r'https?://', value, re.I):
        url = urlsplit(value)
        if (url.hostname not in ARXIV_HOSTS or url.username or url.password or url.port is not None
                or url.query or url.fragment or '%' in url.path): raise ValueError('Untrusted arXiv URL')
        match = re.fullmatch(r'/(abs|pdf)/(.+)', url.path)
        if not match: raise ValueError('Unsupported arXiv URL path')
        value = match[2]
        if match[1] == 'pdf' and value.endswith('.pdf'): value = value[:-4]
    elif re.match(r'journals/corr/abs-', value, re.I):
        match = re.fullmatch(r'journals/corr/abs-(\d{4})-(\d{4,5})(v[1-9]\d*)?', value, re.I | re.ASCII)
        if not match: raise ValueError('Malformed DBLP arXiv key')
        value = match[1]+'.'+match[2]+(match[3] or '')
    else:
        value = re.sub(r'^arxiv:', '', value, flags=re.I)
    match = re.fullmatch(r'(\d{2})(\d{2})\.(\d{4,5})(?:v[1-9]\d*)?', value, re.I | re.ASCII)
    # shortcut: legacy pre-2007 IDs are quarantined; add their authority mapping if such a cohort is requested.
    if not match: raise ValueError('Unsupported or malformed arXiv identifier')
    period = int(match[1]+match[2]); month = int(match[2]); sequence = match[3]
    if period < 704 or not 1 <= month <= 12 or len(sequence) != (4 if period < 1501 else 5) or int(sequence) == 0:
        raise ValueError('Invalid arXiv month or sequence width')
    return match[1]+match[2]+'.'+sequence


def publication_arxiv(value):
    if re.match(r'arxiv:|journals/corr/abs-|https?://(?:www\.|export\.)?arxiv\.org/', value, re.I):
        return canonical_arxiv(value)
    return None


def alias_index(metadata):
    by_publication = {}; blocked = {}; counts = Counter(); seen = set()
    for row in metadata:
        publication = row['publicationId']; urls = row['sourceURLs']
        if (not isinstance(publication, str) or not publication.strip() or publication != publication.strip()
                or publication in seen or not isinstance(urls, list)):
            raise ValueError('Invalid or duplicate source publication')
        seen.add(publication); claims = set(); errors = []; from_key = False; from_url = False
        try:
            claim = publication_arxiv(publication)
            if claim: claims.add(claim); from_key = True
        except ValueError as error: errors.append(str(error))
        for url in urls:
            if not isinstance(url, str): raise ValueError('Invalid source URL')
            if urlsplit(url).hostname not in ARXIV_HOSTS: continue
            try: claims.add(canonical_arxiv(url)); from_url = True
            except ValueError as error: errors.append(str(error))
        if errors or len(claims) > 1:
            blocked[publication] = {'claims': sorted(claims), 'errors': errors or ['Conflicting source identities']}
            counts['quarantinedRows'] += 1
        elif claims:
            by_publication[publication] = next(iter(claims)); counts['canonicalArxivRows'] += 1
            if from_key: counts['fromEncodedKeyRows'] += 1
            if from_url and not from_key: counts['fromURLOnlyRows'] += 1
            if from_url and from_key: counts['keyAndURLAgreeRows'] += 1
        else: counts['noArxivMappingRows'] += 1
    return {'byPublication': by_publication, 'blockedPublications': blocked,
        'coverage': {k: counts[k] for k in ('canonicalArxivRows', 'fromEncodedKeyRows', 'fromURLOnlyRows',
            'keyAndURLAgreeRows', 'noArxivMappingRows', 'quarantinedRows')} | {
            'sourceRows': len(seen), 'uniqueCanonicalArxivIds': len(set(by_publication.values()))}}


def identity(row, aliases):
    if not isinstance(row, dict): raise ValueError('Identity must be an object')
    result = {}; claims = set()
    for field in ('publicationId', 'groupId', 'textSha256'):
        if field not in row: continue
        value = row[field]
        if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value): raise ValueError('Invalid '+field)
        result[field] = value.strip()
    if 'textSha256' in result:
        if not re.fullmatch(r'[0-9a-fA-F]{64}', result['textSha256']): raise ValueError('Invalid text SHA-256')
        result['textSha256'] = result['textSha256'].lower()
    if 'arxivId' in row: claims.add(canonical_arxiv(row['arxivId']))
    publication = result.get('publicationId')
    if publication:
        if publication in aliases['blockedPublications']: raise ValueError('Quarantined source publication')
        claim = publication_arxiv(publication)
        if claim: claims.add(claim)
        if publication in aliases['byPublication']: claims.add(canonical_arxiv(aliases['byPublication'][publication]))
    if 'sourceURL' in row:
        if not isinstance(row['sourceURL'], str) or not row['sourceURL'].strip(): raise ValueError('Invalid source URL')
        if urlsplit(row['sourceURL']).hostname in ARXIV_HOSTS: claims.add(canonical_arxiv(row['sourceURL']))
    if len(claims) > 1: raise ValueError('Conflicting paper identity fields')
    canonical = next(iter(claims), None)
    if canonical:
        result['canonicalArxivId'] = canonical; result['canonicalPaperId'] = 'arxiv:'+canonical
    elif publication: result['canonicalPaperId'] = 'dblp:'+publication
    for field in ('canonicalArxivId', 'canonicalPaperId'):
        if field in row and row[field] != result.get(field): raise ValueError('Unverified or conflicting canonical identity')
    return result


def validate_partition(assignments, excluded, aliases):
    fields = {'publicationId', 'groupId', 'textSha256', 'arxivId', 'canonicalArxivId', 'canonicalPaperId', 'sourceURL'}
    if any(not isinstance(row, dict) or set(row) - fields - {'origin', 'split'} for row in excluded):
        raise ValueError('Metadata-only exclusions required')
    normalized_exclusions = [identity(row, aliases) for row in excluded]
    if any('canonicalPaperId' not in row for row in normalized_exclusions):
        raise ValueError('Missing exclusion paper identity')
    forbidden = {(k, v) for row in normalized_exclusions for k, v in row.items()}
    owners = {}; papers = set()
    for row in assignments:
        if (not isinstance(row, dict) or set(row) - fields - {'split'}
                or row.get('split') not in ('train', 'dev', 'test', 'challenge')):
            raise ValueError('Metadata-only partition required')
        ids = identity(row, aliases); publication = ids.get('publicationId')
        if not publication or not ids.get('groupId'): raise ValueError('Missing publication/group identity')
        if row['split'] != 'train' and ('canonicalArxivId' not in ids or aliases['blockedPublications']):
            raise ValueError('Unverified cross-source identity; evaluation admission blocked')
        # shortcut: known aliases are not exhaustive journal/conference dedup; audit new populations before authorizing evaluation.
        for item in ids.items():
            if row['split'] != 'train' and item in forbidden: raise ValueError('Exposed paper cannot enter new evaluation')
            if item in owners and owners[item] != row['split']: raise ValueError('Paper/group/version overlaps partitions')
            owners[item] = row['split']
        if ids['canonicalPaperId'] in papers: raise ValueError('Duplicate paper/alias in publication-grain inventory')
        papers.add(ids['canonicalPaperId'])
    return dict(Counter(row['split'] for row in assignments))


def evaluation_readiness(reference):
    keys = ('positivePairs', 'negativePairs', 'unresolvedPairs', 'totalPairs', 'sourcePapers')
    if (any(type(reference.get(k)) is not int or reference[k] < 0 for k in keys)
            or type(reference.get('referenceComplete')) is not bool
            or reference['totalPairs'] != sum(reference[k] for k in keys[:3])
            or reference['sourcePapers'] > reference['positivePairs']): raise ValueError('Inconsistent evaluation reference counts')
    reasons = []
    if reference['positivePairs'] == 0: reasons.append('no_positive_reference')
    if reference['negativePairs'] == 0: reasons.append('no_explicit_negative_reference')
    if not reference['referenceComplete'] or reference['unresolvedPairs']: reasons.append('incomplete_reference')
    covered = reference['positivePairs']+reference['negativePairs']
    coverage = covered/reference['totalPairs'] if reference['totalPairs'] else 0.0
    if coverage < 1: reasons.append('incomplete_coverage')
    support = reference['sourcePapers'] >= MIN_REFERENCE_PAPERS
    return reference | {'status': 'not_evaluable' if reasons else 'reference_ready_for_scoring', 'reasons': reasons,
        'referenceCoverage': coverage, 'sourceSupportStatus': 'support_gate_met' if support else 'insufficient_source_support',
        'promotionStatus': 'not_evaluable' if reasons or not support else 'requires_frozen_comparable_predictions',
        'metrics': {'precision': None, 'recall': None, 'f1': None, 'tp': None, 'fp': None, 'fn': None},
        'notice': 'Reference readiness only, no prediction or accuracy. Rare-source threshold is a practical guard, not statistical significance.'}
