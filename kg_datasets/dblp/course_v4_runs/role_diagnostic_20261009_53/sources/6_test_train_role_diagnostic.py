"""One identity/score/scope check without GPU execution or final-test access."""
import copy
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_train_roles as diagnostic


def test_role_diagnostic_scores_all_known_training_pairs_and_rejects_drift():
    with patch.object(diagnostic.c, 'read_jsonl', wraps=diagnostic.c.read_jsonl) as reads:
        rows, old, checkpoint = diagnostic.load_inputs()
    assert len(rows) == 115 and len(old) == 271 and checkpoint.name == 'checkpoint_epoch_06'
    assert not any('test' in call.args[0].name or 'dev' in call.args[0].name for call in reads.call_args_list)
    predictions = [r | {'pairId': diagnostic.re_model.pair_id(r), 'probabilities': {label: float(label == r['label']) for label in diagnostic.re_model.LABELS}} for r in rows]
    metrics = diagnostic.scored(rows, predictions)
    assert metrics['accuracy'] == 1 and metrics['perClass']['NO_RELATION']['reference'] == 8
    assert metrics['evaluationTarget'] == diagnostic.TARGET and metrics['positiveMicro']['evaluationTarget'] == diagnostic.TARGET
    bad = copy.deepcopy(predictions); bad[0]['textSha256'] = '0'*64
    with pytest.raises(ValueError): diagnostic.scored(rows, bad)
    bad = copy.deepcopy(predictions); bad[0]['probabilities']['NO_RELATION'] = float('nan')
    with pytest.raises(ValueError): diagnostic.scored(rows, bad)
    with pytest.raises(ValueError): diagnostic.scored(rows, predictions[::-1])
    with pytest.raises(FileExistsError): diagnostic.run(Path(__file__).parent.resolve())
