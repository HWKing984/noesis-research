import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare_course_refresh import select_holdout


def test_refresh_reserves_unused_test_groups_deterministically():
    rows = [{'publicationId': str(i), 'groupId': 'g' + str(i // 2), 'split': 'test', 'historicalTrainOnly': False}
            for i in range(10)]
    rows += [{'publicationId': 'train', 'groupId': 'gt', 'split': 'train', 'historicalTrainOnly': False},
             {'publicationId': 'exposed', 'groupId': 'gx', 'split': 'test', 'historicalTrainOnly': True}]
    selected = select_holdout(rows, [{'groupId': 'g0'}], 3)
    assert selected == select_holdout(list(reversed(rows)), [{'groupId': 'g0'}], 3)
    assert len({r['groupId'] for r in selected}) == 3
    assert all(r['groupId'] not in {'g0', 'gt', 'gx'} for r in selected)
    for size in (0, True, 100):
        with pytest.raises(ValueError): select_holdout(rows, [], size)
    with pytest.raises(ValueError): select_holdout(rows + [rows[0]], [], 1)
