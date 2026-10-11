import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import build_delivery as build
import delivery


def test_demo_highlight_checks_span_and_escapes_original():
    text = '<method> task'
    result = build.highlight(text, [{'start':0,'end':8,'text':'<method>','label':'METHOD'}])
    assert '&lt;method&gt;' in result and '<method>' not in result
    with pytest.raises(ValueError):
        build.highlight(text, [{'start':0,'end':7,'text':'<method>','label':'METHOD'}])


def test_delivery_manifest_refuses_escape_and_promotion(tmp_path, monkeypatch):
    folder = tmp_path/'docs/delivery'; folder.mkdir(parents=True)
    monkeypatch.setattr(delivery, 'ROOT', tmp_path)
    for manifest in (
        {'filesSha256':{'../outside':'0'*64},'productionReplacementAllowed':False,'test20BodyIncluded':False},
        {'filesSha256':{},'productionReplacementAllowed':True,'test20BodyIncluded':False},
        {'filesSha256':{},'productionReplacementAllowed':False,'test20BodyIncluded':True},
    ):
        (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
        with pytest.raises(ValueError):
            delivery.verify_files()


def test_delivery_pinned_graph_is_production_v1():
    assert delivery.app.g.verified_files(delivery.app.g.configured_bundle(delivery.app.CONFIG))['graphId'] == delivery.GRAPH
    assert 'outputs/v2' not in delivery.app.CONFIG.read_text(encoding='utf-8')


def test_human_reference_confirmation_preserves_frozen_results_and_scope():
    confirmation = build.read(build.OUT/'human_review_confirmation.json')
    assert confirmation['referenceClassification'] == 'human_reviewed_gold_for_adjudicated_scope'
    assert not confirmation['fullCorpusPredictionsHumanVerified']
    assert not confirmation['scoresRecomputed'] and not confirmation['test20Read']
    assert confirmation['fullV2PipelineF1'] is None
    for path, sha in confirmation['frozenBindings'].items():
        assert build.app.g.c.file_sha256(build.ROOT/path) == sha
    comparison = build.read(build.OUT/'experiment_comparison.json')
    assert comparison['referenceProvenance'] == confirmation
    assert comparison['fullV2PipelineF1'] is None
    assert comparison['V1_title_historical_AI_test']['NER'] == build.read(build.ROOT/'kg_datasets/dblp/course_v4_runs/ner_final_test_20261006_09/test_result.json')
    home = (build.OUT/'v1-home.html').read_text(encoding='utf-8')
    assert home == (build.ROOT/'resources/course_literature.html').read_text(encoding='utf-8').replace('（AI参考、','（AI初标后用户逐条人工审核、')
    assert (build.OUT/'demo.html').read_text(encoding='utf-8').count('checked disabled data-paper=') == 3
