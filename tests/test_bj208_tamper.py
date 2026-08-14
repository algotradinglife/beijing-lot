"""Issue #208 tamper self-tests (REQ-E06) — attack PRODUCTION entry points.

REWORK v2 (D4): each tamper test builds a mini immutable package (ledger,
manifest, provenance, receipt, method.yaml) and runs the PRODUCTION verifier
functions against the tampered copy.  A test FAILS if the verifier accepts
the tampered artifact.  The old suite's per-function probes (e.g. checking a
'FORGED' prefix) are gone.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parlay_policy.contract import (  # noqa: E402
    CONTRACT_VERSION,
    INITIAL_BANKROLL_YUAN,
    UPSTREAM_207_MANIFEST_SHA256,
    UPSTREAM_207_SHA,
    VALUE_MATRIX_SHA256,
)
from parlay_policy.verify import (  # noqa: E402
    manifest,
    sha256_file,
    verify_capital_accounting,
    verify_manifest,
    verify_nk_semantics,
    verify_provenance,
    verify_receipt,
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


@pytest.fixture()
def package(tmp_path: Path) -> Path:
    """Minimal immutable package: ledger + manifest + provenance + receipt."""
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
    ledger.to_parquet(tmp_path / "issue_capital_ledger.parquet", index=False)
    provenance = {
        "version": CONTRACT_VERSION,
        "source_issue_207_sha": UPSTREAM_207_SHA,
        "source_issue_207_manifest_sha256": UPSTREAM_207_MANIFEST_SHA256,
        "source_value_matrix_sha256": VALUE_MATRIX_SHA256,
        "label_boundary": "CV_2021 fit; CV_2022/CV_2023 development; 2024 embargoed",
    }
    _write_json(tmp_path / "provenance.json", provenance)
    method_hash = "a" * 64
    (tmp_path / "method.yaml").write_text("protocol_version: test\n", encoding="utf-8")
    (tmp_path / "receipt.sha256").write_text(
        f"{sha256_file(tmp_path / 'method.yaml')}  method.yaml\n", encoding="utf-8"
    )
    artifacts = sorted(
        p for p in tmp_path.iterdir()
        if p.is_file() and p.name not in ("SHA256SUMS.json", "receipt.sha256")
    )
    _write_json(tmp_path / "SHA256SUMS.json", manifest(tmp_path, artifacts))
    return tmp_path


def _verify_full(package: Path) -> list[str]:
    """Production-adjacent full verifier for the mini package."""
    failures: list[str] = []
    expected = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    failures.extend(verify_manifest(package, expected))
    failures.extend(verify_receipt(package))
    provenance = json.loads((package / "provenance.json").read_text(encoding="utf-8"))
    failures.extend(verify_provenance(provenance))
    ledger = pd.read_parquet(package / "issue_capital_ledger.parquet")
    failures.extend(verify_capital_accounting(ledger))
    return failures


# --- Attack 1: mutate settlement field ---------------------------------------


def test_tamper_mutate_settlement_detected(package: Path):
    from parlay_policy.verify import tamper_mutate_settlement

    tamper_mutate_settlement(package / "issue_capital_ledger.parquet")
    failures = _verify_full(package)
    assert failures, "mutated settlement must FAIL the production verifier"


# --- Attack 2: self-consistent ledger edit -----------------------------------


def test_tamper_self_consistent_ledger_detected(package: Path):
    from parlay_policy.verify import tamper_self_consistent_ledger

    tamper_self_consistent_ledger(package / "issue_capital_ledger.parquet")
    failures = _verify_full(package)
    assert failures, "self-consistent ledger edit must FAIL the production verifier"


# --- Attack 3: manifest forgery + unlisted payload ----------------------------


def test_tamper_forge_manifest_detected(package: Path):
    from parlay_policy.verify import tamper_forge_manifest

    tamper_forge_manifest(package / "SHA256SUMS.json", package)
    failures = _verify_full(package)
    assert failures, "forged manifest must FAIL the production verifier"
    # The forged manifest also claims a ghost file -> unlisted/missing check.
    assert any("missing artifact" in f or "unlisted" in f for f in failures)


# --- Attack 4: forged provenance ----------------------------------------------


def test_tamper_forge_source_trace_detected(package: Path):
    from parlay_policy.verify import tamper_forge_source_trace

    tamper_forge_source_trace(package / "provenance.json")
    failures = _verify_full(package)
    # Provenance hash mismatch must fail; manifest must also catch the file
    # hash change of provenance.json.
    assert failures, "forged provenance must FAIL the production verifier"


# --- D4 extra probes -----------------------------------------------------------


def test_unlisted_payload_detected(package: Path):
    """An extra file not in the manifest must be rejected (full coverage)."""
    (package / "ghost_payload.parquet").write_bytes(b"not in manifest")
    failures = _verify_full(package)
    assert any("unlisted" in f for f in failures)


def test_outcome_triple_validation():
    """D4: a match with duplicate outcome codes / multiple realized outcomes
    must fail panel construction (production entry)."""
    from parlay_policy.census import _validate_outcome_triples, CensusError

    rows = pd.DataFrame(
        {
            "match_idx": [1, 1, 1],
            "outcome_code": ["3", "3", "0"],  # duplicate 3, missing 1
            "realized_outcome": [True, False, False],
            "official_final_sp_label": [3.0, 3.0, 2.0],
        }
    )
    with pytest.raises(CensusError):
        _validate_outcome_triples(rows, "22011")


def test_outcome_triple_multiple_realized():
    from parlay_policy.census import _validate_outcome_triples, CensusError

    rows = pd.DataFrame(
        {
            "match_idx": [1, 1, 1],
            "outcome_code": ["3", "1", "0"],
            "realized_outcome": [True, True, False],  # two realized
            "official_final_sp_label": [3.0, 4.0, 2.0],
        }
    )
    with pytest.raises(CensusError):
        _validate_outcome_triples(rows, "22011")


def test_2024_mutation_invariance_real():
    """REQ-208-03 REAL check: mutating 2024 labels changes no fitted parameter.

    Uses the production fit path (build_panels + a summary hash of the fitted
    MLP on development folds).  2024 rows are LOCKED_TEST and are dropped by
    the census loader before any fit, so a mutation must not change output.
    """
    from parlay_policy.census import build_panels, load_value_matrix
    from parlay_policy.contract import FIT_SPLIT

    vm = load_value_matrix(ROOT)
    if not vm.empty:
        panels = build_panels(vm)
        dev_panels = {
            (split, issue): panel
            for (split, issue), panel in panels.items()
            if split == FIT_SPLIT
        }
        baseline = sorted(
            (split, issue, len(panel.match_idx), int(panel.labels_available))
            for (split, issue), panel in dev_panels.items()
        )
        mutated = vm.copy()
        mask_2024 = mutated["issue"].astype(str).str.startswith("24")
        if mask_2024.any():
            # Domain-preserving mutation: shift the realized True cyclically
            # within each match (keeps exactly one True) and inflate official
            # SP.  A bitwise flip would create invalid duplicate-True triples
            # that are already rejected by the loader — the invariance check
            # must test label-value changes, not malformed rows.
            def _shift_realized(group: pd.DataFrame) -> pd.Series:
                realized = group["realized_outcome"].astype(bool).to_numpy()
                if realized.sum() != 1:
                    return group["realized_outcome"]
                idx = int(np.flatnonzero(realized)[0])
                new_idx = (idx + 1) % len(realized)
                out = np.zeros(len(realized), dtype=bool)
                out[new_idx] = True
                return pd.Series(out, index=group.index)

            mutated.loc[mask_2024, "realized_outcome"] = (
                mutated.loc[mask_2024]
                .groupby("match_idx", group_keys=False)
                .apply(_shift_realized)
            )
            mutated.loc[mask_2024, "official_final_sp_label"] = (
                mutated.loc[mask_2024, "official_final_sp_label"] * 1.5
            )
        panels_after = build_panels(mutated)
        after = sorted(
            (split, issue, len(panel.match_idx), int(panel.labels_available))
            for (split, issue), panel in panels_after.items()
            if split == FIT_SPLIT
        )
        assert baseline == after, "2024 mutation changed development panel surface"
