"""Regression coverage for #90's durable outcome-safe OOS projection."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "bj90_safe_projection", ROOT / "scripts" / "project_bj90_downstream_safe_vectors.py"
)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

BUNDLE = ROOT / "results" / "bj90_downstream_safe_projection_v1r1"
MANIFEST_SHA256 = "4a1107ca64d169bf0171a394d1e450a14ee5386005fce34f6ca7ebb70bd720b2"


def source_row(index: int, method: str = "M1_RIDGE_LOG_SP") -> dict[str, str]:
    """Minimal accepted-evaluator-shaped row; target data must be projected away."""
    return {
        "match_id": f"m{index}", "issue": "26000", "match_idx": str(index),
        "year": "2020", "fold": "OOS_2020", "deployed_method": method,
        "m0_3": "2.10", "m0_1": "3.10", "m0_0": "4.10",
        "m1_3": "2.20", "m1_1": "3.20", "m1_0": "4.20",
        "m2_3": "2.00", "m2_1": "3.00", "m2_0": "4.00",
        "y3": "9.99", "y1": "8.88", "y0": "7.77", "result_code": "3",
    }


def test_committed_projection_is_safe_complete_and_manifest_bound() -> None:
    assert MOD.verified_manifest(BUNDLE) == MANIFEST_SHA256
    rows = MOD.read_projection(BUNDLE / "oos_prediction_vectors.csv.gz")
    assert len(rows) == MOD.EXPECTED_OOS_ROWS == 100_589
    assert list(rows[0]) == MOD.PROJECTION_FIELDS
    assert not {
        field
        for field in MOD.PROJECTION_FIELDS
        if any(token in field.lower() for token in MOD.FORBIDDEN_PROJECTION_SUBSTRINGS)
    }
    identities = [
        (row["match_id"], row["issue"], row["match_idx"], row["fold"])
        for row in rows
    ]
    assert len(identities) == len(set(identities))
    card = json.loads((BUNDLE / "projection_card.json").read_text())
    assert card["oos_row_count"] == len(rows)
    assert card["projection_schema"] == MOD.PROJECTION_FIELDS


def test_projection_is_exact_and_rejects_schema_or_identity_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    source_rows = [source_row(1), source_row(2, "M0_EURO_10H"), source_row(3)]
    projected = [MOD.project(row) for row in source_rows]
    monkeypatch.setattr(MOD, "EXPECTED_OOS_ROWS", len(projected))

    MOD.validate_projection(projected, source_rows)
    assert "y3" not in projected[0]
    assert projected[0]["deployed_sp_3"] == "2.20"
    assert projected[1]["deployed_sp_3"] == "2.10"

    with pytest.raises(RuntimeError, match="unexpected projected row count"):
        MOD.validate_projection(projected[:-1], source_rows)

    unsafe = [dict(row) for row in projected]
    unsafe[0]["target_sp_3"] = "9.99"
    with pytest.raises(RuntimeError, match="schema drift"):
        MOD.validate_projection(unsafe, source_rows)

    duplicate = [dict(row) for row in projected]
    duplicate[1].update({key: duplicate[0][key] for key in ("match_id", "issue", "match_idx", "fold")})
    with pytest.raises(RuntimeError, match="non-unique"):
        MOD.validate_projection(duplicate, source_rows)

    changed = [dict(row) for row in projected]
    changed[2]["deployed_sp_0"] = "999.00"
    with pytest.raises(RuntimeError, match="differ"):
        MOD.validate_projection(changed, source_rows)
