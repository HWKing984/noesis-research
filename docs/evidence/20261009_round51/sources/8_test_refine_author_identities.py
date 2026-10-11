import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from refine_author_identities import orcid_id, resolve_orcid


def test_orcid_checksum_and_exact_unique_authority():
    oid = '0000-0002-1825-0097'
    assert orcid_id('https://orcid.org/'+oid) == oid
    assert orcid_id('0000-0002-1825-0098') is None
    assert orcid_id('0000-0002-1694-233X') == '0000-0002-1694-233X'
    assert orcid_id(None) is None
    p = {'homepages/a': {'names': ['Li Wei 0001'], 'disambiguation': False}}
    s = {'name': 'Li Wei', 'orcid': oid}
    assert resolve_orcid(s, p, {oid: {'homepages/a'}})[0]['key'] == 'homepages/a'
    assert resolve_orcid(s, p, {oid: {'homepages/a', 'homepages/b'}})[1] == 'orcid_profile_conflict'
    assert resolve_orcid(s | {'name': 'li wei'}, p, {oid: {'homepages/a'}})[1] == 'orcid_exact_name_conflict'
    assert resolve_orcid(s, p, {})[1] == 'orcid_no_profile'
    assert resolve_orcid(s | {'orcid': ''}, p, {})[0] is None
    p['homepages/a']['disambiguation'] = True
    assert resolve_orcid(s, p, {oid: {'homepages/a'}})[1] == 'orcid_disambiguation_profile'
