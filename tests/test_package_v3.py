import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verify_export_v3 import add_legacy_v2_inputs


def test_legacy_v2_blind_dependencies_are_packaged(tmp_path):
    names=('pilot_review.html','rare_review.html','blind_50_a.html','blind_50_b.html')
    for name in names:(tmp_path/name).write_text(name,encoding='utf-8')
    contents={}
    add_legacy_v2_inputs(contents,tmp_path)
    assert set(contents)=={'kg_datasets/dblp/ner_v2/'+name for name in names}
    assert contents['kg_datasets/dblp/ner_v2/blind_50_a.html']==b'blind_50_a.html'


def test_missing_legacy_dependency_stops_export(tmp_path):
    with pytest.raises(FileNotFoundError):add_legacy_v2_inputs({},tmp_path)
