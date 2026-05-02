"""Tests for archetype_b_niches discovery."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.dual_sweep.archetype_b_niches import (
    SP_BUCKETS_B,
    _bucket_sp_b,
)


def test_bucket_sp_b_boundaries():
    assert _bucket_sp_b(1.4) == "na"
    assert _bucket_sp_b(1.5) == "1.5-2"
    assert _bucket_sp_b(1.99) == "1.5-2"
    assert _bucket_sp_b(2.0) == "2-2.5"
    assert _bucket_sp_b(2.5) == "2.5-3"
    assert _bucket_sp_b(3.0) == "3-3.5"
    assert _bucket_sp_b(3.5) == "3.5-4.5"
    assert _bucket_sp_b(4.49) == "3.5-4.5"
    assert _bucket_sp_b(4.5) == "na"
    assert _bucket_sp_b(8.0) == "na"
    assert _bucket_sp_b(float("nan")) == "na"


def test_buckets_cover_range_no_overlap():
    # check buckets are contiguous and within [1.5, 4.5]
    los = [b[1] for b in SP_BUCKETS_B]
    his = [b[2] for b in SP_BUCKETS_B]
    assert los == sorted(los)
    for i in range(len(SP_BUCKETS_B) - 1):
        assert his[i] == los[i + 1]
    assert los[0] == 1.5 and his[-1] == 4.5
