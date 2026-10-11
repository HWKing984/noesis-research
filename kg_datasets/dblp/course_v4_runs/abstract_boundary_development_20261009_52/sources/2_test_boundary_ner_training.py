"""Bounded new loader and CPU-best-state check; no fitting in regression."""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import train_boundary_abstract_ner as training


def test_boundary_fit_preserves_original_rows_and_rejects_test_reads():
    with patch.object(training.c, 'read_jsonl', wraps=training.c.read_jsonl) as reads:
        config, _, _, data = training.load_inputs()
    assert len(data['train']['ner']) == 65 and len(data['train']['relation']) == 271 and len(data['dev']['full_relation']) == 7
    assert not any('test' in p.args[0].name for p in reads.call_args_list)
    assert config['RETrainingAllowed'] is False and config['reserveBytes'] == 1_000_000_000
    with pytest.raises(FileExistsError): training.run(Path(__file__).parent.resolve())


def test_best_state_requires_detached_cpu_clones():
    model = MagicMock(); value = MagicMock(); cloned = value.detach.return_value.cpu.return_value.clone.return_value
    model.state_dict.return_value = {'weight': value}; cloned.device.type = 'cpu'; cloned.requires_grad = False
    assert training.clone_best(model) == {'weight': cloned}
    value.detach.assert_called_once_with(); value.detach.return_value.cpu.assert_called_once_with()
    value.detach.return_value.cpu.return_value.clone.assert_called_once_with()
    cloned.requires_grad = True
    with pytest.raises(ValueError): training.clone_best(model)
    cloned.requires_grad = False; cloned.device.type = 'cuda'
    with pytest.raises(ValueError): training.clone_best(model)
