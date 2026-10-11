"""Keep sealed outside-path tests meaningful under an in-workspace basetemp."""
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def outside_run_guard_workspace(request, monkeypatch):
    if request.node.path.name == 'test_pretrained_ner_comparison.py' and request.node.name == 'test_no_overwrite_or_output_escape':
        import compare_pretrained_ner as comparison
        temporary = request.getfixturevalue('tmp_path')
        monkeypatch.setattr(comparison.g, 'ROOT', Path(temporary.parent)/'separate_guard_workspace')
        assert not temporary.is_relative_to(comparison.g.ROOT)
    if request.node.path.name == 'test_diverse_role_training.py' and request.node.name == 'test_existing_and_outside_run_paths_rejected_before_reads':
        import train_diverse_abstract_relation as training
        temporary = request.getfixturevalue('tmp_path')
        # The D-drive test temp can itself be within runs; use a distinct fictional workspace.
        monkeypatch.setattr(training.c, 'ROOT', Path(temporary.parent)/'separate_guard_workspace')
        assert not temporary.is_relative_to(training.c.ROOT)
