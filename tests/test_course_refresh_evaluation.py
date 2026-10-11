import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'scripts'))
from evaluate_course_refresh import promotion_decision


def test_refresh_promotion_cannot_hide_rare_support_or_dev_regression():
    new, old = {'f1':.8,'precision':.8}, {'f1':.6,'precision':.7}
    gates = {'rareNERDevNonRegression':False,'minimumReferenceRareEntitySupport':10,'minimumReferenceRareRelationSupport':10}
    result = promotion_decision(new,old,{'DATASET':4,'EVALUATED_ON':0},gates)
    assert not result['passed'] and set(result['failedChecks']) == {'rareNERDevNonRegression','rareEntitySupport','rareRelationSupport'}
    assert promotion_decision(new,old,{'DATASET':10,'EVALUATED_ON':10},gates | {'rareNERDevNonRegression':True})['passed']
    with pytest.raises(ValueError): promotion_decision({'f1':None,'precision':.8},old,{'DATASET':4,'EVALUATED_ON':0},gates)
