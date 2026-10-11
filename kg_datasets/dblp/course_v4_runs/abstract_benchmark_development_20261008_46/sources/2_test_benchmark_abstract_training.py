"""One contract/rare-recall/held-out boundary check; no training in regression."""
import copy
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import train_benchmark_abstract_models as training


def test_benchmark_inputs_and_recall_guard():
    with patch.object(training.c, 'read_jsonl', wraps=training.c.read_jsonl) as reads:
        config, parent, _, data = training.load_inputs()
    assert len(data['train']['ner']) == 58 and len(data['train']['relation']) == 271
    assert not any('test' in p.args[0].name for p in reads.call_args_list)
    assert {p.args[0].parent.name for p in reads.call_args_list} == {'course_abstract_benchmark_inputs_20261008_45'}
    old = training.read(training.c.ROOT/config['baselineRun']/'pipeline_development_result.json')
    result = {'pipelineMetrics': {'old_NER_old_RE': old['pipelineMetrics']['new_NER_new_RE'], 'new_NER_new_RE': old['pipelineMetrics']['new_NER_new_RE']}, 'nerDevMetrics': {k: copy.deepcopy(old['nerDevMetrics']['new']) for k in ('old', 'new')}}
    checks = training.gates(config, parent, data, result)
    assert checks['checks']['DATASETRecallRegressionWithinGuard']
    result['nerDevMetrics']['new']['metrics']['perClass']['DATASET']['recall'] = 0.0
    checks = training.gates(config, parent, data, result)
    assert not checks['checks']['DATASETRecallRegressionWithinGuard']
    assert {'completeReferenceEVALUATED_ONSupport', 'completeDocumentCoverage'} <= set(checks['blockedBy'])
    assert checks['qualityPromotionPassed'] is False and checks['independentHumanGoldRequired'] is False
    with pytest.raises(FileExistsError): training.run(Path(__file__).parent.resolve())
