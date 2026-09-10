import pytest
from src.temporal_learning import Cutoff
from src.temporal_learning.diagnostic_labels import diagnostic_label_clock


def test_label_proxy_is_explicit_and_strictly_prior():
    c=Cutoff.decision_epoch('100305','2010-03-07T00:00:00Z')
    assert diagnostic_label_clock('2010-03-01T00:00:00Z',cutoff=c,delay_hours=6)=='2010-03-01T06:00:00+00:00'
    for stamp,hours in [('2010-03-06T18:00:00Z',6),('NaT',6),('2010-03-01T00:00:00Z',0)]:
        with pytest.raises(ValueError):diagnostic_label_clock(stamp,cutoff=c,delay_hours=hours)
