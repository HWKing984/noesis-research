"""The frozen comparison never expands its TRAIN scope or accepts malformed scores."""
import copy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_diverse_train_roles as diverse


def test_new_training_diagnostic_inventory_and_no_dev_test_parsing():
    with patch.object(diverse.c, 'read_jsonl', wraps=diverse.c.read_jsonl) as reads:
        rows, original, checkpoints = diverse.load_inputs()
    assert len(rows) == 22 and len(original) == 386 and set(checkpoints) == {'frozen46', 'frozen54'}
    assert len({r['sampleId'] for r in rows}) == 5
    assert not any('dev' in call.args[0].name or 'test' in call.args[0].name for call in reads.call_args_list)
    probabilities = {'USED_FOR': 1.0, 'EVALUATED_ON': 0.0, 'NO_RELATION': 0.0}
    predictions = [r | {'pairId': diverse.re_model.pair_id(r), 'label': 'USED_FOR', 'probabilities': probabilities.copy()} for r in rows]
    scored = diverse.diagnostic.scored(rows, predictions)
    assert scored['accuracy'] == 19/22 and scored['perClass']['NO_RELATION']['recall'] == 0
    for field in ('pairId', 'textSha256'):
        bad = copy.deepcopy(predictions); bad[0][field] = 'bad'
        with pytest.raises(ValueError): diverse.diagnostic.scored(rows, bad)
    bad = copy.deepcopy(predictions); bad[0]['probabilities']['USED_FOR'] = float('nan')
    with pytest.raises(ValueError): diverse.diagnostic.scored(rows, bad)


def test_diagnostic_will_not_overwrite_existing_run(tmp_path):
    with pytest.raises(FileExistsError): diverse.run(tmp_path)
    assert list(tmp_path.iterdir()) == []
