import hashlib
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from course_relation_evidence import evidence_gate, apply_gate


def pair(text, head='BERT', tail='classification', label='USED_FOR'):
    span = lambda name, typ: {'start': text.index(name), 'end': text.index(name)+len(name), 'text': name, 'label': typ}
    return {'sampleId': 's', 'text': text, 'textSha256': hashlib.sha256(text.encode()).hexdigest(),
        'head': span(head, 'METHOD'), 'tail': span(tail, 'TASK' if label == 'USED_FOR' else 'DATASET'), 'label': label}


def test_local_evidence_keeps_offsets_and_abstains_without_negative_relabeling():
    good = pair('We use BERT for classification.')
    result = evidence_gate(good); assert result['decision'].startswith('emit_')
    e = result['evidence']; assert good['text'][e['start']:e['end']] == e['text']
    for row in [pair('We study BERT. Our task is classification.'), pair('BERT may be used for classification.'), pair('BERT and classification are mentioned.')]:
        emitted, ledger = apply_gate([row]); assert not emitted
        assert ledger[0]['label'] == 'USED_FOR' and ledger[0]['evidenceGate']['decision'].startswith('abstain_')
    assert evidence_gate(pair('We perform classification using BERT.'))['decision'].startswith('emit_')
    assert evidence_gate(pair('We evaluate BERT on SQuAD.', tail='SQuAD', label='EVALUATED_ON'))['decision'].startswith('emit_')
    assert evidence_gate(pair('We train BERT on SQuAD.', tail='SQuAD', label='EVALUATED_ON'))['decision'] == 'abstain_no_evaluation_cue'
    with pytest.raises(ValueError): evidence_gate(good | {'textSha256': '0'*64})
