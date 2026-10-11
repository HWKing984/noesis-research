"""Recover unresolved signatures by unique DBLP profile ORCID plus exact name evidence."""
import argparse
import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from lxml import etree
import course_graph as g
from course_identity import LocalDTDResolver, inspect_dtd, element_text, RECORD_TAGS


def orcid_id(value):
    if not isinstance(value, str): return None
    value = re.sub(r'^https?://orcid\.org/', '', value)
    if not re.fullmatch(r'\d{4}-\d{4}-\d{4}-\d{3}[\dX]', value): return None
    digits = value.replace('-', ''); total = 0
    for digit in digits[:15]: total = (total + int(digit)) * 2
    check = (12 - total % 11) % 11
    return value if digits[-1] == ('X' if check == 10 else str(check)) else None


def resolve_orcid(signature, profiles, index):
    oid = orcid_id(signature.get('orcid', ''))
    if not oid: return None, 'missing_or_invalid_orcid'
    keys = sorted(index.get(oid, []))
    if len(keys) != 1: return None, 'orcid_profile_conflict' if keys else 'orcid_no_profile'
    profile = profiles[keys[0]]
    if profile['disambiguation']: return None, 'orcid_disambiguation_profile'
    names = {re.sub(r' \d{4}$', '', name) for name in profile['names']}
    if signature['name'] not in names: return None, 'orcid_exact_name_conflict'
    return {'status': 'dblp_homepage_resolved', 'key': keys[0], 'matchedExactName': signature['name'],
            'method': 'unique_profile_orcid_and_exact_base_name', 'orcid': oid}, 'recovered'


def run(source, baseline, output):
    if output.exists(): raise FileExistsError('Preserve identity history; use a new output')
    manifest = g.verified_files(baseline)
    signatures = g.c.read_jsonl(baseline/'signatures.jsonl')
    profiles = json.loads((baseline/'profiles.json').read_text(encoding='utf-8'))
    needed = {orcid_id(s['orcid']) for s in signatures if s['identity']['status'] != 'dblp_homepage_resolved'} - {None}
    dtd = inspect_dtd(source)
    paths = [source, dtd, baseline/'manifest.json', Path(__file__), g.ROOT/'tests/test_refine_author_identities.py']
    hashes = {p.relative_to(g.ROOT).as_posix(): g.c.file_sha256(p) for p in paths}
    output.mkdir(parents=True)
    state = {'status': 'running', 'createdAtUTC': datetime.now(UTC).isoformat(), 'databaseWritten': False}
    g.c.write_json(output/'status.json', state)
    try:
        index = defaultdict(set); new_profiles = {}; count = 0
        with gzip.open(source, 'rb') as stream:
            parser = etree.iterparse(stream, events=('end',), tag=RECORD_TAGS+('person',),
                load_dtd=True, resolve_entities=True, no_network=True, huge_tree=True)
            parser.resolvers.add(LocalDTDResolver(dtd))
            for _, element in parser:
                count += 1; key = element.get('key', '')
                if element.tag in ('www', 'person') and key.startswith('homepages/'):
                    urls = [element_text(u) for u in element.findall('url') if orcid_id(element_text(u)) in needed]
                    if urls:
                        if key in new_profiles: raise ValueError('Duplicate authority profile')
                        new_profiles[key] = {'key': key,
                            'names': list(dict.fromkeys(''.join(a.itertext()).strip() for a in element.findall('author'))),
                            'orcidURLs': urls,
                            'disambiguation': element.get('type') == 'disambiguation' or element.get('publtype') == 'disambiguation' or any(n.get('type') == 'disambiguation' for n in element.findall('note'))}
                        for url in urls: index[orcid_id(url)].add(key)
                element.clear(); parent = element.getparent()
                while parent is not None and element.getprevious() is not None: del parent[0]
                if count % 1000000 == 0: print(json.dumps({'recordsScanned': count, 'ORCIDProfiles': len(new_profiles)}), flush=True)
        for key, profile in new_profiles.items():
            if key in profiles and any(profiles[key][k] != profile[k] for k in ('names', 'disambiguation')): raise ValueError('Authority profile drift')
            profiles[key] = profile
        ledger = []; counts = Counter()
        for signature in signatures:
            if signature['identity']['status'] == 'dblp_homepage_resolved': continue
            old = signature['identity']; identity, reason = resolve_orcid(signature, profiles, index); counts[reason] += 1
            ledger.append({'publicationId': signature['publicationId'], 'position': signature['position'], 'name': signature['name'],
                           'orcidSourceValue': signature['orcid'], 'previousIdentity': old, 'decision': reason, 'newIdentity': identity})
            if identity: signature['identity'] = identity
        if any(g.c.file_sha256(g.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Identity source drift')
        summary = {'signatures': len(signatures), 'previousUnresolved': len(ledger), 'recoveredSignatures': counts['recovered'],
            'remainingUnresolved': len(ledger)-counts['recovered'], 'decisionCounts': dict(counts), 'authorityProfilesScanned': count,
            'matchedORCIDProfiles': len(new_profiles), 'neededORCIDs': len(needed), 'fuzzyMatching': False,
            'independentRealWorldVerification': False, 'databaseWritten': False,
            'notice': 'Unique local DBLP profile ORCID plus exact base-name match, not ORCID Registry authentication. Unknown signatures remain separate.'}
        g.c.write_jsonl(output/'signatures.jsonl', signatures); g.c.write_json(output/'profiles.json', profiles)
        g.c.write_json(output/'redirects.json', json.loads((baseline/'redirects.json').read_text(encoding='utf-8')))
        g.c.write_jsonl(output/'recovery_ledger.jsonl', ledger); g.c.write_json(output/'summary.json', summary)
        state.update(status='completed', finishedAtUTC=datetime.now(UTC).isoformat()); g.c.write_json(output/'status.json', state)
        g.c.write_json(output/'manifest.json', {'kind': 'dblp_orcid_identity_refinement_v1', 'inputSha256': hashes,
            'baselineManifestSha256': g.c.file_sha256(baseline/'manifest.json'),
            'authorityURLs': ['https://dblp.org/faq/1474704.html', 'https://blog.dblp.org/2020/07/20/dblp-and-orcid-2020/',
                'https://support.orcid.org/hc/en-us/articles/360006897674-Structure-of-the-ORCID-Identifier'],
            'filesSha256': {p.name: g.c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
        g.verified_files(output); print(json.dumps(summary), flush=True)
    except Exception as error:
        g.c.write_json(output/'status.json', state | {'status': 'failed', 'error': str(error)}); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=g.ROOT/'kg_datasets/dblp/dblp.xml.gz')
    parser.add_argument('--baseline', type=Path, default=g.ROOT/'kg_datasets/dblp/course_v4_identity_20261007_31_recovered')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); run(args.source.resolve(), args.baseline.resolve(), args.output.resolve())
