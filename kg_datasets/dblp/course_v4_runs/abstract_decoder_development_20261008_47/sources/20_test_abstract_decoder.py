"""One boundary check for frozen, label-free decoder comparison."""
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import evaluate_abstract_decoder as decoder


def test_frozen_abstract_decoder_scope_and_parity_contract():
    with patch.object(decoder.c,'read_jsonl',wraps=decoder.c.read_jsonl) as reads:
        config,_,_,data=decoder.load_inputs()
    assert len(data['dev']['ner'])==16 and len(data['dev']['full_relation'])==7
    assert not any('test' in p.args[0].name for p in reads.call_args_list)
    assert config['trainingAllowed'] is False and config['labelMutationAllowed'] is False
    modes=decoder.decode_modes([[0,2,9,1,1,1,1],[0,1,8,1,1,1,1]],[(0,1),(2,3)],'a b')
    assert modes['argmax']['invalidTransitions']==2 and modes['argmax']['entities']==[]
    assert modes['constrained']['invalidTransitions']==0
    assert modes['constrained']['entities']==[{'start':0,'end':3,'text':'a b','label':'METHOD'}]
    with pytest.raises(ValueError): decoder.decode_modes([[0]*6],[(0,1)],'a')
    with pytest.raises(FileExistsError): decoder.run(Path(__file__).parent.resolve())
