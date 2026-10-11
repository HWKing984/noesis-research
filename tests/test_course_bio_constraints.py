import itertools
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from course_bio_constraints import legal_bio_labels,c


def test_legal_bio_is_global_optimum_and_never_repairs_with_gold():
    scores=[[0,2,9,1,1,1,1],[0,1,8,1,1,1,1],[4,1,1,1,1,1,1]]
    offsets=[(0,1),(2,3),(4,5)]
    prediction=legal_bio_labels(scores,offsets)
    def legal(tags):
        names=[c.CONFIG['bioLabels'][t] for t in tags]
        return all(not tag.startswith('I-') or (i>0 and names[i-1] in ('B-'+tag[2:],'I-'+tag[2:])) for i,tag in enumerate(names))
    assert legal(prediction)
    best=max(sum(scores[i][v] for i,v in enumerate(tags)) for tags in itertools.product(range(7),repeat=3) if legal(tags))
    assert sum(scores[i][v] for i,v in enumerate(prediction))==best
    assert legal_bio_labels([[0,0,100,0,0,0,0]],[(0,0)])==[0]
    assert legal_bio_labels([],[])==[]
    for bad in ([[float('nan')]*7],[[0]*6]):
        with pytest.raises(ValueError):legal_bio_labels(bad,[(0,1)])
