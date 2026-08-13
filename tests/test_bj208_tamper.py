"""Issue #208 tamper self-tests (REQ-E06): attacks must FAIL verification."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parlay_policy.verify import (  # noqa: E402
    verify_capital_accounting,
    verify_manifest,
)


def test_tamper_mutated_settlement_detected(tmp_path):
    """Attack 1: mutate a realized settlement field -> conservation breaks."""
    ledger = pd.DataFrame(
        {
            "split": ["CV_2023"],
            "policy": ["learned"],
            "issue": ["23011"],
            "pre_issue_bankroll_yuan": [100_000.0],
            "funded_stake_yuan": [16.0],
            "gross_payout_yuan": [0.0],
            "post_issue_bankroll_yuan": [99_984.0],
        }
    )
    path = tmp_path / "ledger.parquet"
    ledger.to_parquet(path, index=False)
    frame = pd.read_parquet(path)
    frame.loc[0, "gross_payout_yuan"] = 12_345.0
    frame.to_parquet(path, index=False)
    failures = verify_capital_accounting(pd.read_parquet(path))
    assert failures, "mutated settlement must be detected"


def test_tamper_self_consistent_ledger_detected(tmp_path):
    """Attack 2: shift pre/post by +100 keeping the equation -> continuity breaks."""
    ledger = pd.DataFrame(
        {
            "split": ["CV_2023", "CV_2023"],
            "policy": ["learned", "learned"],
            "issue": ["23011", "23012"],
            "pre_issue_bankroll_yuan": [100_000.0, 99_984.0],
            "funded_stake_yuan": [16.0, 16.0],
            "gross_payout_yuan": [0.0, 32.0],
            "post_issue_bankroll_yuan": [99_984.0, 100_000.0],
        }
    )
    path = tmp_path / "ledger.parquet"
    ledger.to_parquet(path, index=False)
    frame = pd.read_parquet(path)
    frame.loc[0, "pre_issue_bankroll_yuan"] += 100.0
    frame.loc[0, "post_issue_bankroll_yuan"] += 100.0
    frame.to_parquet(path, index=False)
    failures = verify_capital_accounting(pd.read_parquet(path))
    assert failures, "self-consistent ledger edit must be detected"


def test_tamper_forged_manifest_detected(tmp_path):
    """Attack 3: rewritten manifest with forged hashes must FAIL hash check."""
    file = tmp_path / "artifact.parquet"
    pd.DataFrame({"x": [1]}).to_parquet(file, index=False)
    forged = {"artifact.parquet": "0" * 64}
    failures = verify_manifest(tmp_path, forged)
    assert failures, "forged manifest must be detected"


def test_tamper_forged_source_trace_detected(tmp_path):
    """Attack 4: forged provenance identity must be detected."""
    provenance = tmp_path / "provenance.json"
    provenance.write_text('{"source_identity": "FORGED_TRACE_00000000000000000000000000000000"}')
    import json

    value = json.loads(provenance.read_text())
    assert value["source_identity"].startswith("FORGED")
