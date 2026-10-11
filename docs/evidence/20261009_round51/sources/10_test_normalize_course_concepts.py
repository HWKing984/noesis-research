import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from normalize_course_concepts import vocabulary, canonical, family


def test_explicit_typed_aliases_preserve_model_dataset_versions():
    config, index = vocabulary(); key = lambda text, typ='METHOD': canonical(text, typ, index)[0]
    for a, b in [('LLMs', 'Large Language Models'), ('CNN', 'Convolutional Neural Networks'), ('Bi-LSTM', 'BiLSTM'), ('GPT 4', 'GPT-4')]: assert key(a) == key(b)
    for a, b in config['noMergeExamples']:
        for typ in ('METHOD', 'TASK', 'DATASET'): assert key(a, typ) != key(b, typ)
    assert key('NER', 'TASK') == 'named entity recognition'
    assert key('NER', 'METHOD') == 'ner'
    assert key('RL') == 'rl'
    assert family(key('GPT-4o'), 'METHOD') == 'gpt'
    assert family('GPT-4o', 'DATASET') is None
    with pytest.raises(ValueError): key('')
    with pytest.raises(ValueError): key('x', 'VENUE')
