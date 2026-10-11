import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from refine_author_crosswalk import crosswalk_decision


def test_repeated_unique_orcid_crosswalk_never_guesses_same_names():
    oid = '0000-0002-1825-0097'; s = {'name': 'Li Wei', 'orcid': oid}
    p = {'p1': {'names': ['Li Wei 0001']}, 'p2': {'names': ['Li Wei 0002']}}
    assert crosswalk_decision(s, {oid: {'p1': {'paper1', 'paper2'}}}, p, set())[0]['key'] == 'p1'
    assert crosswalk_decision(s, {oid: {'p1': {'paper1'}}}, p, set())[1] == 'single_publication_support_only'
    assert crosswalk_decision(s, {oid: {'p1': {'a', 'b'}, 'p2': {'c', 'd'}}}, p, set())[0] is None
    assert crosswalk_decision(s, {oid: {'p1': {'a', 'b'}}}, p, {oid})[0] is None
    assert crosswalk_decision(s | {'name': 'li wei'}, {oid: {'p1': {'a', 'b'}}}, p, set())[0] is None
