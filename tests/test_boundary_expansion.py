import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from expand_boundary_abstracts import locked, fresh


def test_boundary_training_cohort_rejects_identity_leaks_and_overwrite():
    config, base = locked()
    assert len(config['seeds']) == 8 and config['automaticPromotionAllowed'] is False
    assert '49' in config['supplement'] and base.name.endswith('_45')
    with pytest.raises(FileExistsError): fresh(base)
    with pytest.raises(ValueError): fresh(Path('C:/outside-boundary-output').resolve())
