"""Bounded title experiment checks; never train a model in regression."""
import copy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_title_expansion_once as experiment


def metric(tp=6, predicted=10, reference=10):
    return {'truePositive': tp, 'predicted': predicted, 'reference': reference,
            'precision': tp / predicted, 'recall': tp / reference, 'f1': 2 * tp / (predicted + reference)}


def comparison():
    ner = {'micro': metric(), 'perClass': {k: metric() for k in ('METHOD', 'TASK', 'DATASET')}}
    pipeline = {'positiveMicro': metric(), 'perClass': {k: metric() for k in ('USED_FOR', 'EVALUATED_ON')}}
    module = {'perClass': {k: metric() for k in ('USED_FOR', 'EVALUATED_ON', 'NO_RELATION')}}
    result = {'ner': {k: copy.deepcopy(ner) for k in ('old', 'new')},
              'pipeline': {k: copy.deepcopy(pipeline) for k in ('old_ner_old_re', 'new_ner_new_re')},
              'module': {k: copy.deepcopy(module) for k in ('old', 'new')}}
    result['ner']['new']['micro'] = metric(7)
    result['pipeline']['new_ner_new_re']['positiveMicro'] = metric(7)
    return result


def test_fixed_title_inputs_and_isolation():
    with patch.object(experiment.c, 'read_jsonl', wraps=experiment.c.read_jsonl) as reads:
        ner_data, re_data, documents, audit = experiment.audit_inputs()
    assert len(ner_data['train']) == 1219 and len(re_data['train']) == 975
    assert len(documents) == 158
    assert audit['ner']['support']['DATASET'] == 12
    assert audit['re']['support'] == {'USED_FOR': 937, 'NO_RELATION': 35, 'EVALUATED_ON': 3}
    assert audit['re']['sourcePapers']['EVALUATED_ON'] == 2
    assert not any('test' in call.args[0].name for call in reads.call_args_list)
    assert not any('abstract' in str(call.args[0]) for call in reads.call_args_list)


def test_candidates_never_auto_deploy_and_stop_once():
    result = experiment.gates(comparison())
    assert result['candidateAccepted']
    assert result['optimizationStopped'] and not result['productionReplacementAllowed']
    assert not result['statisticalSignificanceEstablished']
    with pytest.raises(FileExistsError):
        experiment.run(Path(__file__).parent)


@pytest.mark.parametrize('change', ['no_gain', 'false_positives', 'common', 'negative', 'rare_ner', 'rare_re', 'unsupported'])
def test_regressions_fail_closed(change):
    result = comparison()
    if change == 'no_gain':
        result['pipeline']['new_ner_new_re']['positiveMicro'] = metric()
    elif change == 'false_positives':
        result['pipeline']['new_ner_new_re']['positiveMicro'] = metric(8, 13, 10)
    elif change == 'common':
        result['ner']['new']['perClass']['TASK'] = metric(5)
    elif change == 'negative':
        result['module']['new']['perClass']['NO_RELATION'] = metric(5)
    elif change == 'rare_ner':
        result['ner']['new']['perClass']['DATASET'] = metric(5)
    elif change == 'rare_re':
        result['pipeline']['new_ner_new_re']['perClass']['EVALUATED_ON'] = metric(5)
    else:
        result['ner']['new']['perClass']['DATASET']['reference'] = 0
        with pytest.raises(ValueError):
            experiment.gates(result)
        return
    assert not experiment.gates(result)['candidateAccepted']
