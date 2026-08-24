"""Verifier + coordinated tamper tests for BJ-UNIFIED-N7-SUPPORT-SHAPE-001/v1.

Run with pytest from the repo root (results/n7_support_shape must exist, built
by scripts/run_n7_support_shape.py). The verifier replays #366, rebuilds all
#369 frames, validates strict booleans and exact (rtol=0) scientific semantics,
and proves that four classes of tampering are detected.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO.parent / "beijing-lot/data"
sys.path.insert(0, str(REPO))

from src.n7_support_shape.contract import (
    BASE_UNITS,
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    EXTRA_UNIT_TICKETS,
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    PAYOUT_FACTOR,
    SHAPES,
    STAKE_PER_UNIT_CNY,
    TICKETS_PER_SHAPE,
)
from src.n7_support_shape.pipeline import (
    ContractError,
    _ticket_identity_hash,
    build_contrasts,
    scientific_frames_369,
    sha256_file,
    stable_frame_sha,
    verify_package,
)

PACKAGE = REPO / "results/n7_support_shape"


@pytest.fixture(scope="module")
def frames():
    return scientific_frames_369(REPO, DATA_ROOT)


@pytest.fixture(scope="module")
def package_frames(frames):
    return frames


def test_upstream_n366_replay():
    """The verifier's own #366 replay must pass (source-bound foundation)."""
    from src.n7_support_shape.pipeline import replay_n366
    replay_n366(REPO, DATA_ROOT)


def test_ticket_counts_and_units(frames):
    tickets = frames["tickets"]
    count = tickets.groupby(["base", "shape", "issue"])["ticket_ordinal"].count()
    for shape in SHAPES:
        for base in ("R0_CORRECTED", "R3_CORRECTED"):
            per_issue = count.loc[base, shape]
            assert (per_issue == TICKETS_PER_SHAPE[shape]).all()
    for shape in SHAPES:
        sub = tickets[tickets["shape"].eq(shape)]
        unit_counts = sub["units"].value_counts().to_dict()
        if shape == "CONTROL":
            assert unit_counts == {4: 128 * 151 * 2}
        elif shape == "CONTRACTION_ONLY":
            assert unit_counts == {8: 64 * 151 * 2}
        elif shape == "EXPANSION_ONLY":
            assert unit_counts == {3: 128 * 151 * 2, 2: 64 * 151 * 2}
        else:  # BOTH
            assert unit_counts == {6: 32 * 151 * 2, 5: 64 * 151 * 2}


def test_stake_funding_exact(frames):
    tickets = frames["tickets"]
    for (base, shape, issue), group in tickets.groupby(["base", "shape", "issue"]):
        assert np.isclose(group["stake_cny"].sum(), ISSUE_STAKE_CNY, rtol=0, atol=1e-9)
        assert np.isclose(group["stake_frac_cny"].sum(), ISSUE_STAKE_CNY, rtol=1e-9, atol=1e-9)
        assert (group["stake_cny"] == group["units"] * STAKE_PER_UNIT_CNY).all()


def test_sha256_extra_unit_assignment(frames):
    """Only the EXTRA_UNIT_TICKETS lowest SHA-256 identities per issue get the extra unit."""
    tickets = frames["tickets"]
    for shape in ("EXPANSION_ONLY", "BOTH"):
        sub = tickets[tickets["shape"].eq(shape)]
        for (base, issue), group in sub.groupby(["base", "issue"]):
            assert len(group) == TICKETS_PER_SHAPE[shape]
            lowest = group["ticket_sha256"].sort_values().head(EXTRA_UNIT_TICKETS[shape]).index
            expected = group.index.isin(lowest)
            assert (group["extra_unit"].to_numpy() == expected).all()


def test_initial_support_from_n366_decisions(frames):
    """Every base's initial support equals the corrected #366 support_json exactly."""
    from src.n7_support_shape.pipeline import _parse_support_json
    import json as _json
    decisions366 = pd.read_parquet(REPO / "results/n7_chronology_sync/decisions.parquet")
    feats = frames["support_features"]
    for base in ("R0_CORRECTED", "R3_CORRECTED"):
        arm = "R0" if base == "R0_CORRECTED" else "R3"
        dec = decisions366[decisions366["arm"].eq(arm)].set_index("issue")
        for issue in feats[feats["base"].eq(base)]["issue"].unique():
            support_map = _parse_support_json(dec.loc[issue, "support_json"])
            sub = feats[feats["base"].eq(base) & feats["issue"].eq(issue)].set_index("match_idx")
            for mid, support in support_map.items():
                assert sub.loc[mid, "base_support"] == support


def test_exact_common_denominator(frames):
    """All 8 arms settle on the same issue set (exact-common denominator)."""
    bundles = frames["bundles"]
    issue_sets = {
        (base, shape): set(bundles[bundles["base"].eq(base) & bundles["shape"].eq(shape)]["issue"])
        for base in ("R0_CORRECTED", "R3_CORRECTED") for shape in SHAPES
    }
    reference = issue_sets[("R0_CORRECTED", "CONTROL")]
    for key, issues in issue_sets.items():
        assert issues == reference, f"{key} issue set differs"
    assert len(reference) > 100  # roughly the 151 settled issues


def test_settlement_exact_formula(frames):
    """Complete-ticket settlement: gross = stake*0.65*prod(sp), 0.65 once, rtol=0."""
    tickets = frames["tickets"]
    bundles = frames["bundles"]
    for (base, shape), group in tickets.groupby(["base", "shape"]):
        for issue, sub in group.groupby("issue"):
            bundle = bundles[(bundles["issue"].eq(issue)) & (bundles["base"].eq(base)) & (bundles["shape"].eq(shape))].iloc[0]
            winners = sub[sub["gross_cny"].gt(0)]
            if bundle["hit"]:
                # exactly one winning ticket, gross equals the bundle's gross
                assert len(winners) == 1
                row = winners.iloc[0]
                assert np.isclose(row["gross_cny"], bundle["gross_cny"], rtol=0, atol=1e-9)
                # fractional counterfactual pays the same sp product scaled by stake
                expected_frac = row["gross_cny"] * row["stake_frac_cny"] / row["stake_cny"]
                assert np.isclose(row["gross_frac_cny"], expected_frac, rtol=0, atol=1e-9)
                assert (sub["gross_frac_cny"] == winners.iloc[0]["gross_frac_cny"]).sum() == 1
            else:
                assert len(winners) == 0
                assert not sub["gross_cny"].any()
                assert not sub["gross_frac_cny"].any()


def test_contrasts_deterministic(frames):
    c1 = build_contrasts(frames["bundles"])
    c2 = build_contrasts(frames["bundles"])
    assert stable_frame_sha(c1) == stable_frame_sha(c2)
    assert not c1["contrast"].duplicated().any()
    assert set(c1["contrast"]) == {
        "BASE=R0_CORRECTED|EFFECT=contraction",
        "BASE=R0_CORRECTED|EFFECT=expansion",
        "BASE=R0_CORRECTED|EFFECT=interaction",
        "BASE=R3_CORRECTED|EFFECT=contraction",
        "BASE=R3_CORRECTED|EFFECT=expansion",
        "BASE=R3_CORRECTED|EFFECT=interaction",
        "SHAPE=CONTROL|LIFT=R3-R0",
        "SHAPE=CONTRACTION_ONLY|LIFT=R3-R0",
        "SHAPE=EXPANSION_ONLY|LIFT=R3-R0",
        "SHAPE=BOTH|LIFT=R3-R0",
    }


def test_dev_diagnostic_reproducible(frames):
    dev = frames["dev_check"]
    assert len(dev) == 4  # 2 bases x 2 scores
    summary = frames["dev_summary"]
    assert summary["pass"] in (True, False)
    assert summary["dev_issues"] > 50


def test_pair_selection_oracle(frames):
    """Independent brute-force oracle for the (c, e) pair selection.

    Recomputes contraction/expansion ranks and the lexicographic argmin over
    (rank_c+rank_e, max, rank_c, rank_e, c_id, e_id) with a deliberately
    different code path; flags failures like wrong rank-coupling (e.g. using
    contraction ranks for the e side).
    """
    feats = frames["support_features"]
    for (issue, base), group in feats.groupby(["issue", "base"]):
        ids = group["match_idx"].astype(int).tolist()
        if len(ids) < 2:
            continue
        c_rank = (
            group.sort_values(["contraction_score", "expansion_score", "match_idx"],
                              ascending=[False, False, True], kind="stable")
            .assign(_r=range(1, len(group) + 1))
            .set_index("match_idx")["_r"]
        )
        e_rank = (
            group.sort_values(["expansion_score", "contraction_score", "match_idx"],
                              ascending=[False, False, True], kind="stable")
            .assign(_r=range(1, len(group) + 1))
            .set_index("match_idx")["_r"]
        )
        best = None
        for c_id in ids:
            for e_id in ids:
                if c_id == e_id:
                    continue
                key = (
                    int(c_rank.loc[c_id]) + int(e_rank.loc[e_id]),
                    max(int(c_rank.loc[c_id]), int(e_rank.loc[e_id])),
                    int(c_rank.loc[c_id]),
                    int(e_rank.loc[e_id]),
                    c_id,
                    e_id,
                )
                if best is None or key < best[0]:
                    best = (key, c_id, e_id)
        assert best is not None
        best_c, best_e = best[1], best[2]
        chosen = group[group["is_c"] | group["is_e"]]
        c_chosen = int(chosen.loc[chosen["is_c"], "match_idx"].iloc[0])
        e_chosen = int(chosen.loc[chosen["is_e"], "match_idx"].iloc[0])
        assert (c_chosen, e_chosen) == (best_c, best_e), (
            f"pair mismatch {issue} {base}: got ({c_chosen},{e_chosen}) want ({best_c},{best_e})"
        )


def test_ex_largest_negative_max():
    """Removing the largest |value| must remove its SIGNED value (r2 fix)."""
    from src.n7_support_shape.pipeline import _ex_largest
    import numpy as _np
    # largest |value| is negative: sum - (-1024) = +100 if [-1024, +100]
    assert _ex_largest(_np.array([-1024.0, 100.0])) == 100.0
    # largest |value| is positive: [-500, +1000] -> -500 + 1000 - 1000 = -500 (removes +1000)
    assert _ex_largest(_np.array([-500.0, 1000.0])) == -500.0
    # abs tie: keeps the smallest index -> removes index 0 (-900)
    assert _ex_largest(_np.array([-900.0, 900.0, 5.0])) == 905.0
    import math as _math
    assert _math.isnan(_ex_largest(_np.array([])))


def test_verifier_passes_on_pristine_package():
    checks = verify_package(REPO, PACKAGE, DATA_ROOT)
    assert all(checks.values())


###############################################################################
# Tamper tests (REQ-E06): every class of forgery must FAIL verification.
###############################################################################


def _copy_package(tmp_path: Path) -> Path:
    target = tmp_path / "package"
    shutil.copytree(PACKAGE, target)
    return target


def test_tamper_settlement_fields(tmp_path):
    """1. Modify realized_gross/pnl in the settled ledger -> verifier FAIL."""
    target = _copy_package(tmp_path)
    bundles = pd.read_parquet(target / "issue_bundles.parquet")
    bundles.loc[0, "gross_cny"] = bundles.loc[0, "gross_cny"] + 1234.5
    bundles.loc[0, "pnl_cny"] = bundles.loc[0, "pnl_cny"] + 1234.5
    bundles.to_parquet(target / "issue_bundles.parquet", index=False)
    with pytest.raises(ContractError):
        verify_package(REPO, target, DATA_ROOT)


def test_tamper_ledger_keeping_accounting_equal(tmp_path):
    """2. Shift payout between rows so totals stay identical -> verifier FAIL."""
    target = _copy_package(tmp_path)
    bundles = pd.read_parquet(target / "issue_bundles.parquet")
    hit_rows = bundles[bundles["gross_cny"].gt(0)].head(2)
    idx_a, idx_b = hit_rows.index[0], hit_rows.index[1]
    shift = 100.0
    bundles.loc[idx_a, "gross_cny"] += shift
    bundles.loc[idx_a, "pnl_cny"] += shift
    bundles.loc[idx_b, "gross_cny"] -= shift
    bundles.loc[idx_b, "pnl_cny"] -= shift
    assert np.isclose(bundles["pnl_cny"].sum(), pd.read_parquet(PACKAGE / "issue_bundles.parquet")["pnl_cny"].sum(), rtol=0, atol=1e-6)
    bundles.to_parquet(target / "issue_bundles.parquet", index=False)
    with pytest.raises(ContractError):
        verify_package(REPO, target, DATA_ROOT)


def test_tamper_rewrite_manifest(tmp_path):
    """3. Rewrite MANIFEST.json to match a tampered frame -> frame replay FAIL."""
    target = _copy_package(tmp_path)
    bundles = pd.read_parquet(target / "issue_bundles.parquet")
    bundles.loc[0, "pnl_frac_cny"] = bundles.loc[0, "pnl_frac_cny"] - 50.0
    bundles.to_parquet(target / "issue_bundles.parquet", index=False)
    manifest_path = target / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["issue_bundles.parquet"]["sha256"] = sha256_file(target / "issue_bundles.parquet")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ContractError):
        verify_package(REPO, target, DATA_ROOT)


def test_tamper_forge_source_trace(tmp_path):
    """4a. Forge source_receipt upstream hash -> verifier FAIL."""
    target = _copy_package(tmp_path)
    receipt = json.loads((target / "source_receipt.json").read_text())
    receipt["upstream_manifest"]["files"]["tickets.parquet"]["sha256"] = "0" * 64
    (target / "source_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = target / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["source_receipt.json"]["sha256"] = sha256_file(target / "source_receipt.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ContractError):
        verify_package(REPO, target, DATA_ROOT)


def test_tamper_change_label_and_future_information(tmp_path, monkeypatch):
    """4b. (i) change a calibrated probability label, (ii) inject future
    information by moving a fixture decision after its training label — both
    must FAIL verification (either our verifier or the upstream #366 guards)."""
    target = _copy_package(tmp_path)
    import src.n7_support_shape.pipeline as mod
    from src.n7_chronology_sync.pipeline import ContractError as UpstreamContractError
    original_replay = mod.replay_n366

    def tampered_qeu(repo_root, data_root):
        frames = original_replay(repo_root, data_root)
        actions = frames["actions"].copy()
        actions.loc[0, "q_eu_3"] = actions.loc[0, "q_eu_3"] + 0.01
        frames["actions"] = actions
        return frames

    monkeypatch.setattr(mod, "replay_n366", tampered_qeu)
    with pytest.raises((ContractError, UpstreamContractError)):
        verify_package(REPO, target, DATA_ROOT)

    # restore the q_eu patch so (ii) isolates the future-information guard
    monkeypatch.setattr(mod, "replay_n366", original_replay)

    # (ii) future information: a fixture decided AFTER its training label window
    # closes would leak the label into the decision; the #366 replay guards
    # (strict-prior check) must fail closed.
    import src.n7_chronology_sync.pipeline as upstream
    original_upstream = upstream.load_corrected_cells

    def tampered_future(repo_root, data_root):
        cells, settlement, receipt = original_upstream(repo_root, data_root)
        cells = cells.copy()
        idx = cells.index[0]
        cells.loc[idx, "training_label_available_max_ts"] = (
            pd.to_datetime(cells.loc[idx, "fixture_decision_ts"], utc=True)
            + pd.Timedelta(seconds=1)
        )
        return cells, settlement, receipt

    monkeypatch.setattr(upstream, "load_corrected_cells", tampered_future)
    with pytest.raises((ContractError, UpstreamContractError)):
        verify_package(REPO, target, DATA_ROOT)