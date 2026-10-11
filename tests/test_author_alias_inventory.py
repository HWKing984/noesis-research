import json
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import course_graph as g
from replay_author_alias_inventory import replay, run

OID = '0000-0001-6284-5904'


def inventory():
    profiles = {'homepages/a': {'names': ['Muhammad Waseem Iqbal 0001'],
                'orcidURLs': ['https://orcid.org/'+OID], 'disambiguation': False}}
    ledger = [{'publicationId': 'paper0', 'position': 1, 'name': 'Muhammad Iqbal',
               'orcidSourceValue': OID, 'previousIdentity': {'status': 'unresolved_profile'}}]
    occurrences = [{'publicationId': p, 'name': 'Muhammad Waseem Iqbal 0001', 'orcid': OID}
                   for p in ('paper1', 'paper2')]
    return ledger, occurrences, profiles


def test_baseline_aliases_remove_false_authority_conflict_without_merging():
    ledger, occurrences, profiles = inventory()
    old, conflicts, _ = replay(ledger, occurrences, profiles, {}, restricted=True)
    new, after, _ = replay(ledger, occurrences, profiles, {})
    assert old[0]['decision'] == 'contradictory_orcid_authority'
    assert conflicts == {OID}
    assert new[0]['decision'] == 'exact_base_name_mismatch'
    assert new[0]['newIdentity'] is None and after == set()


def test_genuine_orcid_conflicts_stay_rejected():
    ledger, occurrences, profiles = inventory()
    profiles['homepages/b'] = {'names': ['Other Name'], 'orcidURLs': [], 'disambiguation': False}
    occurrences.append({'publicationId': 'paper3', 'name': 'Other Name', 'orcid': OID})
    result, conflicts, _ = replay(ledger, occurrences, profiles, {})
    assert conflicts == {OID}
    assert result[0]['decision'] == 'contradictory_orcid_authority'


def test_replay_preserves_supported_links_and_invalid_orcid_rejection():
    ledger, occurrences, profiles = inventory()
    profiles['homepages/a']['names'] = ['Muhammad Iqbal 0001']
    for item in occurrences: item['name'] = 'Muhammad Iqbal 0001'
    old, _, _ = replay(ledger, occurrences, profiles, {}, restricted=True)
    new, _, _ = replay(ledger, occurrences, profiles, {})
    assert new == old and new[0]['newIdentity']['key'] == 'homepages/a'
    ledger[0]['orcidSourceValue'] = '0000-0001-6284-5900'
    assert replay(ledger, occurrences, profiles, {})[0][0]['decision'] == 'no_valid_orcid'


def test_run_seals_diagnostic_only_and_refuses_overwrite(tmp_path):
    ledger, occurrences, profiles = inventory()
    old, conflicts, _ = replay(ledger, occurrences, profiles, {}, restricted=True)
    source = tmp_path/'source'; source.mkdir()
    g.c.write_json(source/'profiles.json', profiles)
    g.c.write_json(source/'redirects.json', {})
    g.c.write_jsonl(source/'orcid_source_occurrences.jsonl', occurrences)
    g.c.write_jsonl(source/'recovery_ledger.jsonl', old)
    g.c.write_jsonl(source/'signatures.jsonl', [{'publicationId': 'paper0', 'position': 1,
                       'name': ledger[0]['name'], 'orcid': OID, 'identity': ledger[0]['previousIdentity']}])
    g.c.write_json(source/'summary.json', {'signatures': 1, 'remainingUnresolved': 1,
                       'decisionCounts': dict(Counter(r['decision'] for r in old)), 'ORCIDConflicts': len(conflicts)})
    g.c.write_json(source/'manifest.json', {'kind': 'dblp_source_orcid_crosswalk_v1',
                       'filesSha256': {p.name: g.c.file_sha256(p) for p in source.iterdir()}})
    output = tmp_path/'audit'
    run(source, output)
    g.verified_files(output)
    summary = json.loads((output/'summary.json').read_text(encoding='utf-8'))
    assert summary['changedRejectionReasons'] == 1
    assert summary['identityLinksChanged'] == 0 and summary['remainingUnresolved'] == 1
    assert summary['databaseWritten'] is False and summary['xmlScanned'] is False
    assert not (output/'signatures.jsonl').exists()
    with pytest.raises(FileExistsError): run(source, output)
    old[0]['name'] = 'changed'
    g.c.write_jsonl(source/'recovery_ledger.jsonl', old)
    manifest = json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    manifest['filesSha256']['recovery_ledger.jsonl'] = g.c.file_sha256(source/'recovery_ledger.jsonl')
    g.c.write_json(source/'manifest.json', manifest)
    with pytest.raises(ValueError, match='Source.*parity'): run(source, tmp_path/'bad')
