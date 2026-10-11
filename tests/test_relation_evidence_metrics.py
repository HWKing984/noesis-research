import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from evaluate_relation_evidence import positive_agreement


def test_abstention_counts_as_missed_positive_not_a_certified_negative():
    pair = {'sampleId': 's', 'head': {'start': 0, 'end': 1}, 'tail': {'start': 2, 'end': 3}, 'label': 'USED_FOR'}
    metric = positive_agreement([pair], [])
    assert metric['reference'] == 1 and metric['predicted'] == 0 and metric['recall'] == 0
    assert positive_agreement([pair], [pair])['f1'] == 1
