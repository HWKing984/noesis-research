"""Data/held-out isolation and fail-closed guards; no model fit in regression."""
import copy
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import train_role_abstract_relation as training


def test_role_fit_is_re_only_and_preserves_dev_and_test_boundaries():
    with patch.object(training.c, 'read_jsonl', wraps=training.c.read_jsonl) as reads:
        config, parent, parent_re, data, _, added = training.load_inputs()
    assert len(data['train']['relation']) == 386 and len(added) == 115 and len(data['train']['ner']) == 65
    assert not any('test' in p.args[0].name for p in reads.call_args_list)
    assert config['NERTrainingAllowed'] is False and config['reserveBytes'] == 1_000_000_000
    assert parent_re['RETraining']['epochs'] == 6 and parent_re['RETraining']['batchSize'] == 4
    assert 6*((len(data['train']['relation'])+3)//4) == 582
    previous = training.read(training.c.ROOT/config['frozenNERRun']/'comparison.json')
    old_re = training.read(training.c.ROOT/'kg_datasets/dblp/course_v4_runs/abstract_benchmark_development_20261008_46/re/development_result.json')['bestDev']['metrics']
    pipeline = {k: copy.deepcopy(previous['historicalPipeline']['new']) for k in ('old', 'new')}; module = {k: copy.deepcopy(old_re) for k in ('old', 'new')}
    guards = training.gates(parent, data, pipeline, module, previous['historicalNER']['new']['metrics'])
    assert {'completeReferenceEVALUATED_ONSupport', 'completeDocumentCoverage'} <= set(guards['blockedBy'])
    assert guards['checks']['completeDevFalsePositiveNonRegression'] and guards['checks']['knownDevNegativeRecallNonRegression']
    pipeline['new']['positiveMicro']['predicted'] += 1; module['new']['perClass']['NO_RELATION']['recall'] = 0
    guards = training.gates(parent, data, pipeline, module, previous['historicalNER']['new']['metrics'])
    assert not guards['checks']['completeDevFalsePositiveNonRegression'] and not guards['checks']['knownDevNegativeRecallNonRegression']
    assert guards['qualityPromotionPassed'] is False
    with pytest.raises(FileExistsError): training.run(Path(__file__).parent.resolve())
