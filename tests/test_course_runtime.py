"""Pinned runtime selection must fail closed without changing historical graph artifacts."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import course_graph as g

def test_default_graph_is_pinned_and_bad_configuration_never_falls_back(tmp_path,monkeypatch,capsys):
    actual=g.configured_bundle()
    assert actual.name=='course_v4_graph_resolved_20261007_31_ready'
    bundle=tmp_path/'kg_datasets/dblp/pinned';bundle.mkdir(parents=True)
    artifact=bundle/'nodes.jsonl';artifact.write_text('{}\n',encoding='utf-8')
    g.c.write_json(bundle/'manifest.json',{'graphId':'test','filesSha256':{'nodes.jsonl':g.c.file_sha256(artifact)}})
    config=tmp_path/'runtime.json'
    good={'bundle':'kg_datasets/dblp/pinned','graphId':'test','manifestSha256':g.c.file_sha256(bundle/'manifest.json')}
    monkeypatch.setattr(g,'ROOT',tmp_path)
    g.c.write_json(config,good);assert g.configured_bundle(config)==bundle
    for update in ({'bundle':'../outside'},{'bundle':str(bundle.resolve())},{'graphId':'wrong'},{'manifestSha256':''},{'manifestSha256':'0'*64}):
        g.c.write_json(config,good|update)
        with pytest.raises((ValueError,FileNotFoundError)):g.configured_bundle(config)
    g.c.write_json(config,good);artifact.write_text('changed',encoding='utf-8')
    with pytest.raises(ValueError):g.configured_bundle(config)
    with pytest.raises(FileNotFoundError):g.configured_bundle(tmp_path/'absent.json')
    monkeypatch.setattr(g,'configured_bundle',lambda:actual)
    monkeypatch.setattr(g,'verify_bundle',lambda p:{'manifest':{'graphId':'test','selected':str(p)}})
    monkeypatch.setattr(sys,'argv',['course_graph.py','verify']);g.main()
    assert json.loads(capsys.readouterr().out)['selected']==str(actual)
    monkeypatch.setattr(sys,'argv',['course_graph.py','verify','--bundle','historic']);g.main()
    assert json.loads(capsys.readouterr().out)['selected']=='historic'
    monkeypatch.setattr(sys,'argv',['course_graph.py','export'])
    with pytest.raises(SystemExit) as error:g.main()
    assert error.value.code==2
