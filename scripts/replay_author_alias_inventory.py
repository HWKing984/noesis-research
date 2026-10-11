"""Replay sealed ORCID inventories; correct refusal reasons without changing author links."""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import course_graph as g
from refine_author_crosswalk import crosswalk_decision, orcid_id, resolve_signature


def replay(ledger, occurrences, profiles, redirects, restricted=False):
    names = {s['name'] for s in ledger}; needed = {orcid_id(s['orcidSourceValue']) for s in ledger} - {None}
    aliases = defaultdict(set); authority = defaultdict(set); bindings = defaultdict(lambda: defaultdict(set))
    for key, profile in profiles.items():
        if not restricted or any(re.sub(r' \d{4}$', '', n) in names for n in profile['names']):
            for name in profile['names']: aliases[name].add(key)
        for url in profile['orcidURLs']:
            oid = orcid_id(url)
            if oid in needed: authority[oid].add(key)
    for item in occurrences:
        identity = resolve_signature(item, aliases, profiles, redirects)
        if identity['status'] == 'dblp_homepage_resolved': bindings[item['orcid']][identity['key']].add(item['publicationId'])
    conflicts = {oid for oid in needed if len(authority[oid] | set(bindings[oid])) > 1}
    for oid, keys in authority.items():
        if keys and (not bindings[oid] or keys != set(bindings[oid])): conflicts.add(oid)
    result = []
    for entry in ledger:
        identity, reason = crosswalk_decision(entry | {'orcid': entry['orcidSourceValue']}, bindings, profiles, conflicts)
        result.append(entry | {'decision': reason, 'newIdentity': identity})
    return result, conflicts, aliases

def run(source, output):
    if output.exists(): raise FileExistsError('Preserve alias audit; use a new output')
    manifest = g.verified_files(source)
    if manifest['kind'] != 'dblp_source_orcid_crosswalk_v1': raise ValueError('Unexpected inventory contract')
    profiles = json.loads((source/'profiles.json').read_text(encoding='utf-8'))
    redirects = json.loads((source/'redirects.json').read_text(encoding='utf-8'))
    ledger = g.c.read_jsonl(source/'recovery_ledger.jsonl'); occurrences = g.c.read_jsonl(source/'orcid_source_occurrences.jsonl')
    summary = json.loads((source/'summary.json').read_text(encoding='utf-8'))
    paths = [source/'manifest.json', Path(__file__), g.ROOT/'tests/test_author_alias_inventory.py',
             g.ROOT/'scripts/refine_author_crosswalk.py', g.ROOT/'scripts/refine_author_identities.py',
             g.ROOT/'scripts/course_identity.py', Path(g.__file__), Path(g.c.__file__)]
    hashes = {p.relative_to(g.ROOT).as_posix(): g.c.file_sha256(p) for p in paths}
    old, before_conflicts, _ = replay(ledger, occurrences, profiles, redirects, restricted=True)
    if old != ledger or dict(Counter(r['decision'] for r in old)) != summary['decisionCounts'] or len(before_conflicts) != summary['ORCIDConflicts']:
        raise ValueError('Source decision parity failed')
    new, after_conflicts, aliases = replay(ledger, occurrences, profiles, redirects)
    if any(a['newIdentity'] != b['newIdentity'] for a, b in zip(old, new)): raise ValueError('Identity links changed; this audit cannot infer identities')
    by_signature = {(r['publicationId'], r['position']): r for r in ledger}
    if len(by_signature) != len(ledger): raise ValueError('Duplicate source ledger signature')
    total = resolved = 0
    with (source/'signatures.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            signature = json.loads(line); total += 1; entry = by_signature.get((signature['publicationId'], signature['position']))
            if entry:
                if signature['name'] != entry['name'] or signature['orcid'] != entry['orcidSourceValue'] or signature['identity'] != (entry['newIdentity'] or entry['previousIdentity']):
                    raise ValueError('Source signature parity failed')
            elif resolve_signature(signature, aliases, profiles, redirects) != signature['identity']:
                raise ValueError('Previously resolved alias changed')
            resolved += signature['identity']['status'] == 'dblp_homepage_resolved'
    if total != summary['signatures'] or total-resolved != summary['remainingUnresolved']: raise ValueError('Source signature coverage changed')
    changed = [b | {'previousDecision': a['decision']} for a, b in zip(old, new) if a['decision'] != b['decision']]
    if any(g.c.file_sha256(g.ROOT/p) != sha for p, sha in hashes.items()): raise ValueError('Audit source drift')
    g.verified_files(source); output.mkdir(parents=True)
    result = {'signaturesExamined': total, 'priorRejectionEntries': len(ledger), 'changedRejectionReasons': len(changed),
              'beforeDecisionCounts': summary['decisionCounts'], 'afterDecisionCounts': dict(Counter(r['decision'] for r in new)),
              'beforeORCIDConflicts': len(before_conflicts), 'afterORCIDConflicts': len(after_conflicts), 'identityLinksChanged': 0,
              'remainingUnresolved': total-resolved, 'databaseWritten': False, 'xmlScanned': False, 'networkAccess': False,
              'scope': 'Replay existing sealed inventory only; author aliases, labels, graph and resolved identities remain unchanged.',
              'limitations': 'No new authority evidence or independent real-world verification; refusal reason corrections cannot justify new links.'}
    g.c.write_jsonl(output/'recovery_ledger.jsonl', new); g.c.write_jsonl(output/'changed_rejections.jsonl', changed)
    g.c.write_json(output/'summary.json', result)
    g.c.write_json(output/'manifest.json', {'kind': 'dblp_alias_inventory_diagnostic_v1', 'inputSha256': hashes,
                   'sourceFilesSha256': manifest['filesSha256'], 'filesSha256': {p.name: g.c.file_sha256(p) for p in output.iterdir()}})
    g.verified_files(output); print(json.dumps(result), flush=True); return result

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); run(g.ROOT/'kg_datasets/dblp/course_v4_identity_crosswalk_20261009_51', args.output.resolve())
