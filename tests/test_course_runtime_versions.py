"""Application activation must not invalidate sealed training provenance."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import course_quality_app as app


def test_v3_application_pin_is_separate_from_historical_training_pin():
    assert app.CONFIG.name == 'course_graph_quality_v3_runtime.json'
    bundle = app.g.configured_bundle(app.CONFIG)
    manifest = app.g.verified_files(bundle)
    assert manifest['graphId'] == 'ai-literature-63686318d85cccb07afb'
    assert app.load_vocabulary(manifest)[0]['version'] == 'typed_controlled_aliases_v3'


def test_historical_runtime_bytes_still_match_boundary_training_manifest():
    root = app.g.ROOT
    manifest = json.loads((root/'kg_datasets/dblp/course_abstract_boundary_inputs_20261009_52/manifest.json').read_text())
    relative = 'resources/course_graph_quality_runtime.json'
    assert app.g.c.file_sha256(root/relative) == manifest['inputSha256'][relative]
