"""Check ORCID-bearing signatures throughout the XML against exact DBLP alias identities."""
import argparse
import gzip
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from lxml import etree
import course_graph as g
from course_identity import resolve_signature, LocalDTDResolver, inspect_dtd, element_text, RECORD_TAGS
from refine_author_identities import orcid_id


def crosswalk_decision(signature, bindings, profiles, conflicts):
    oid = orcid_id(signature['orcid'])
    if not oid: return None, 'no_valid_orcid'
    if oid in conflicts: return None, 'contradictory_orcid_authority'
    candidates = bindings.get(oid, {})
    if len(candidates) != 1: return None, 'ambiguous_crosswalk' if candidates else 'no_disambiguated_crosswalk'
    key, papers = next(iter(candidates.items()))
    if len(papers) < 2: return None, 'single_publication_support_only'
    if signature['name'] not in {re.sub(r' \d{4}$', '', n) for n in profiles[key]['names']}: return None, 'exact_base_name_mismatch'
    return {'status': 'dblp_homepage_resolved', 'key': key, 'matchedExactName': signature['name'],
        'method': 'source_orcid_unique_dblp_alias_crosswalk', 'orcid': oid,
        'supportPublications': sorted(papers), 'independentlyVerified': False}, 'recovered_source_crosswalk'


def run(source, baseline, output):
    if output.exists(): raise FileExistsError('Preserve crosswalk; use new output')
    g.verified_files(baseline); signatures = g.c.read_jsonl(baseline/'signatures.jsonl')
    profiles = json.loads((baseline/'profiles.json').read_text(encoding='utf-8')); redirects = json.loads((baseline/'redirects.json').read_text(encoding='utf-8'))
    unresolved = [s for s in signatures if s['identity']['status'] != 'dblp_homepage_resolved']
    names = {s['name'] for s in unresolved}; needed = {orcid_id(s['orcid']) for s in unresolved} - {None}
    dtd = inspect_dtd(source); paths = [source, dtd, baseline/'manifest.json', Path(__file__),
        g.ROOT/'scripts/refine_author_identities.py', g.ROOT/'scripts/course_identity.py', g.ROOT/'tests/test_refine_author_crosswalk.py']
    hashes = {p.relative_to(g.ROOT).as_posix(): g.c.file_sha256(p) for p in paths}
    output.mkdir(parents=True); state = {'status': 'running', 'databaseWritten': False}; g.c.write_json(output/'status.json', state)
    try:
        occurrences = []; aliases = defaultdict(set); authority = defaultdict(set); count = 0
        with gzip.open(source, 'rb') as stream:
            parser = etree.iterparse(stream, events=('end',), tag=RECORD_TAGS+('person',), load_dtd=True,
                resolve_entities=True, no_network=True, huge_tree=True); parser.resolvers.add(LocalDTDResolver(dtd))
            for _, element in parser:
                count += 1; key = element.get('key', '')
                if element.tag in ('www', 'person') and key.startswith('homepages/'):
                    literals = list(dict.fromkeys(''.join(a.itertext()).strip() for a in element.findall('author')))
                    urls = [element_text(u) for u in element.findall('url') if orcid_id(element_text(u))]
                    if any(re.sub(r' \d{4}$', '', n) in names for n in literals):
                        profiles[key] = {'key': key, 'names': literals, 'orcidURLs': urls,
                            'disambiguation': element.get('type') == 'disambiguation' or element.get('publtype') == 'disambiguation' or any(n.get('type') == 'disambiguation' for n in element.findall('note'))}
                        for n in literals: aliases[n].add(key)
                    for url in urls:
                        if orcid_id(url) in needed: authority[orcid_id(url)].add(key)
                else:
                    for author in element.findall('author'):
                        oid = orcid_id(author.get('orcid', ''))
                        if oid in needed: occurrences.append({'orcid': oid, 'name': ''.join(author.itertext()).strip(), 'publicationId': key})
                element.clear(); parent = element.getparent()
                while parent is not None and element.getprevious() is not None: del parent[0]
                if count % 2000000 == 0: print(json.dumps({'records': count, 'ORCIDSignatures': len(occurrences)}), flush=True)
        bindings = defaultdict(lambda: defaultdict(set))
        for item in occurrences:
            identity = resolve_signature(item, aliases, profiles, redirects)
            if identity['status'] == 'dblp_homepage_resolved': bindings[item['orcid']][identity['key']].add(item['publicationId'])
        conflicts = {oid for oid in needed if len(authority[oid] | set(bindings[oid])) > 1}
        # A profile ORCID cannot override contradictory signature evidence, including a different exact name.
        for oid, keys in authority.items():
            if keys and (not bindings[oid] or keys != set(bindings[oid])): conflicts.add(oid)
        ledger = []; counts = Counter()
        for s in unresolved:
            new, reason = crosswalk_decision(s, bindings, profiles, conflicts); counts[reason] += 1
            ledger.append({'publicationId': s['publicationId'], 'position': s['position'], 'name': s['name'],
                'orcidSourceValue': s['orcid'], 'previousIdentity': s['identity'], 'decision': reason, 'newIdentity': new})
            if new: s['identity'] = new
        if any(g.c.file_sha256(g.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Crosswalk source drift')
        summary = {'signatures': len(signatures), 'previousUnresolved': len(unresolved),
            'recoveredSignatures': counts['recovered_source_crosswalk'], 'remainingUnresolved': len(unresolved)-counts['recovered_source_crosswalk'],
            'decisionCounts': dict(counts), 'globalORCIDSignaturesExamined': len(occurrences), 'ORCIDConflicts': len(conflicts),
            'fuzzyMatching': False, 'databaseWritten': False, 'independentRealWorldVerification': False,
            'notice': 'New links require unique ORCID-to-exact-DBLP-profile binding from >=2 other publications and compatible exact base name; source attribution, not independent identity verification.'}
        g.c.write_jsonl(output/'signatures.jsonl', signatures); g.c.write_json(output/'profiles.json', profiles); g.c.write_json(output/'redirects.json', redirects)
        g.c.write_jsonl(output/'recovery_ledger.jsonl', ledger); g.c.write_jsonl(output/'orcid_source_occurrences.jsonl', occurrences)
        g.c.write_json(output/'summary.json', summary); state.update(status='completed', finishedAtUTC=datetime.now(UTC).isoformat()); g.c.write_json(output/'status.json', state)
        g.c.write_json(output/'manifest.json', {'kind': 'dblp_source_orcid_crosswalk_v1', 'inputSha256': hashes,
            'filesSha256': {p.name: g.c.file_sha256(p) for p in output.iterdir() if p.is_file()}})
        g.verified_files(output); print(json.dumps(summary), flush=True)
    except Exception as error:
        g.c.write_json(output/'status.json', state | {'status': 'failed', 'error': str(error)}); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=g.ROOT/'kg_datasets/dblp/dblp.xml.gz')
    parser.add_argument('--baseline', type=Path, default=g.ROOT/'kg_datasets/dblp/course_v4_identity_20261009_51')
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    run(args.source.resolve(), args.baseline.resolve(), args.output.resolve())
