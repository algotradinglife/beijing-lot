import math

import numpy as np
import pandas as pd

from issue284.sampler import assign_issue_weights, sample_issue_subsets


def _sample(**overrides):
    kwargs = {
        "issue": "26001",
        "match_ids": [f"m{index}" for index in range(20)],
        "n": 7,
        "value_score": np.linspace(-0.2, 0.4, 20),
        "divergence_score": np.linspace(-0.3, 0.2, 20),
        "reliability_score": np.linspace(0.5, 1.0, 20),
        "samples_per_family": 8,
        "seed": 284001,
        "epoch": 2,
    }
    kwargs.update(overrides)
    return sample_issue_subsets(**kwargs)


def test_sampler_is_deterministic_distinct_and_issue_normalized() -> None:
    first = _sample()
    second = _sample()
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 32
    assert first["subset_id"].is_unique
    assert first["match_ids"].map(len).eq(7).all()
    assert np.isclose(first["issue_training_weight"].sum(), 1.0)
    assert first["ordered_draw_probability"].between(0, 1, inclusive="right").all()


def test_sampler_changes_by_epoch_without_crossing_identity_semantics() -> None:
    first = _sample(epoch=0)
    second = _sample(epoch=1)
    assert set(first["subset_id"]) != set(second["subset_id"])
    assert first["match_indices"].map(lambda indexes: tuple(sorted(indexes)) == indexes).all()
    assert second["match_indices"].map(lambda indexes: tuple(sorted(indexes)) == indexes).all()


def test_small_combination_space_is_exhaustive() -> None:
    frame = _sample(
        match_ids=["a", "b", "c", "d"],
        n=3,
        value_score=[1, 2, 3, 4],
        divergence_score=[0.1, 0.2, 0.3, 0.4],
        reliability_score=[1, 1, 1, 1],
    )
    assert len(frame) == math.comb(4, 3)
    assert frame["subset_id"].is_unique
    assert np.isclose(frame["issue_training_weight"].sum(), 1.0)
    assert np.allclose(frame["ordered_draw_probability"], 1 / math.comb(4, 3))


def test_issue_weights_do_not_make_more_rows_more_independent() -> None:
    frame = pd.DataFrame(
        {"issue": ["A", "A", "B"], "epoch": [0, 0, 0], "row": [1, 2, 3]}
    )
    weighted = assign_issue_weights(frame)
    totals = weighted.groupby("issue")["issue_training_weight"].sum()
    assert totals.to_dict() == {"A": 1.0, "B": 1.0}


def test_invalid_shape_fails_closed() -> None:
    with np.testing.assert_raises_regex(ValueError, "one value per match"):
        _sample(value_score=[1.0, 2.0])
