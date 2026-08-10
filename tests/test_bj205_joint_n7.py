from __future__ import annotations

import numpy as np
import pandas as pd

from unified_value.joint_n7 import (
    CONFIGS,
    N,
    OUTCOMES,
    _config_products,
    _fallback_mix,
    _normalize,
    build_value_matrix,
)


def test_exhaustive_n7_identity_and_product_normalize() -> None:
    assert CONFIGS.shape == (3**N, N)
    p = np.tile(np.asarray([[0.2, 0.3, 0.5]]), (N, 1))
    joint = _normalize(_config_products(p))
    assert np.isclose(joint.sum(), 1.0)
    assert np.isclose(joint[0], 0.2**N)


def test_fallback_is_exact_market_bytes() -> None:
    market = _normalize(np.arange(1, 3**N + 1, dtype=float))
    candidate = market[::-1].copy()
    record = {"context": np.asarray([9.0, 9.0, 9.0]), "market_joint": market}
    mixed, supported = _fallback_mix([record], [candidate], (np.zeros(3), np.ones(3)))
    assert not supported[0]
    assert mixed[0].tobytes() == market.tobytes()


def test_zero_residual_cell_matrix_uses_exact_market_probability() -> None:
    row = {
        "issue": "x",
        "year": 2025,
        "issue_order": 1.0,
        "match_idx": 1,
        "split": "LOCKED_TEST",
        "result_code": "3",
        "market_eligible": True,
        "model_used": False,
        "fallback_reason": "OOD",
        "seed_count": 3,
    }
    for code, probability, sp in zip(
        OUTCOMES, (0.2, 0.3, 0.5), (5.0, 3.0, 2.0), strict=True
    ):
        row[f"market_probability_{code}"] = probability
        row[f"fallback_mixed_probability_{code}"] = probability
        row[f"predicted_final_sp_{code}"] = sp
        row[f"official_final_sp_{code}"] = sp
        row[f"seed_std__fallback_mixed_probability_{code}"] = 0.0
        row[f"seed_std__predicted_final_sp_{code}"] = 0.0
    value = build_value_matrix(pd.DataFrame([row]))
    assert value.calibrated_true_probability.to_list() == [0.2, 0.3, 0.5]
    assert value.fallback_applied.all()
