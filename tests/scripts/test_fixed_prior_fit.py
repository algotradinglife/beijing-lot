"""Fixed diagnostic fits retain strict shared chronology and provenance."""
from pathlib import Path

import pandas as pd
import pytest

from beidan_backend.temporal_learning import (
    AvailabilityFilter, AvailabilityPolicy, Cutoff, PartitionPolicy,
    TemporalContractError, WeightingPolicy, prepare_learning_context,
)


def test_fixed_prior_fit_excludes_target_future_and_preserves_empty_splits():
    history = pd.DataFrame({
        "issue_code": ["100101", "100102", "100105", "100106"],
        "issue_year": [2010] * 4,
        "label_available_ts": ["2010-01-02Z", "2010-01-05Z", "2010-01-01Z", "2010-01-20Z"],
        "value": [1, 2, 99, 99],
    })
    history["label_available_ts"] = [s.replace("Z", "T00:00:00Z") for s in history.label_available_ts]
    kwargs = dict(
        cutoff=Cutoff.decision_epoch("100105", "2010-01-12T15:01:00Z"),
        source_hashes={"fixture": "test"}, repository_root=Path(__file__).resolve().parents[2],
        implementation_modules=("beidan_backend.temporal_learning.core",),
        availability=AvailabilityFilter(AvailabilityPolicy.historical_proxy("TEST")),
        intended_use="HISTORICAL_DIAGNOSTIC",
        partition_policy=PartitionPolicy("FIXED_PRIOR_FIT", 0, 0, 1),
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=2),
    )
    first = prepare_learning_context(history, **kwargs)
    assert first.eligible.issue_code.tolist() == ["100101", "100102"]
    assert first.partitions["tune"].empty and first.partitions["calibration"].empty
    assert first.receipt.payload["partition"]["fit_rows"] == 2
    history.loc[2:, "value"] = -10000
    second = prepare_learning_context(history, **kwargs)
    assert first.receipt.payload == second.receipt.payload
    with pytest.raises(TemporalContractError, match="prospective"):
        prepare_learning_context(history, **{**kwargs, "intended_use": "PROSPECTIVE_DECISION"})
    with pytest.raises(TemporalContractError, match="diagnostic only"):
        prepare_learning_context(history, **{**kwargs, "intended_use": "PROSPECTIVE_DECISION",
            "availability": AvailabilityFilter(AvailabilityPolicy.observed("TEST"))})
    with pytest.raises(TemporalContractError, match="zero tuning"):
        prepare_learning_context(history, **{**kwargs, "partition_policy": PartitionPolicy("FIXED_PRIOR_FIT")})
    with pytest.raises(TemporalContractError, match="insufficient complete"):
        prepare_learning_context(history, **{**kwargs, "partition_policy": PartitionPolicy()})
    with pytest.raises(TemporalContractError, match="no prior observations"):
        prepare_learning_context(history.iloc[2:], **kwargs)
