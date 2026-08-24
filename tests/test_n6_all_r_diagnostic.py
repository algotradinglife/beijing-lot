from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from src.n6_all_r_diagnostic.contract import (
    ARMS,
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    PAYOUT_FACTOR,
    R_GRID,
    STAKE_PER_TICKET_CNY,
    TICKETS,
)
from src.n6_all_r_diagnostic.pipeline import ContractError, verify_package


REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "results/n6_all_r_diagnostic"
UPSTREAM_N6 = REPO / "results/n6_chronology_sync"
DATA_ROOT = Path("/home/drwho1985/workspace/soccer/beijing-lot/data")


def _rehash(package: Path, relative: str) -> None:
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload = (package / relative).read_bytes()
    manifest["files"][relative] = {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "package"
    shutil.copytree(PACKAGE, target)
    return target


def test_committed_package_source_bound_replay() -> None:
    checks = verify_package(REPO, PACKAGE, DATA_ROOT)
    assert all(checks.values())


def test_exact_ticket_budget_and_cartesian() -> None:
    tickets = pd.read_parquet(PACKAGE / "tickets.parquet")
    groups = tickets.groupby(["issue", "arm"], observed=True)
    assert set(groups.groups) == set(map(tuple, pd.read_parquet(PACKAGE / "decisions.parquet")[["issue", "arm"]].to_numpy()))
    assert groups.size().eq(TICKETS).all()
    assert groups["ticket_code"].nunique().eq(TICKETS).all()
    assert groups["units"].sum().eq(FUNDED_UNITS).all()
    assert np.allclose(groups["stake_cny"].sum(), ISSUE_STAKE_CNY, rtol=0, atol=1e-12)


def test_arm_support_semantics_match_fixed_r_oracle() -> None:
    attribution = pd.read_parquet(PACKAGE / "support_attribution.parquet")
    for r, arm in enumerate(ARMS):
        rows = attribution[attribution["arm"].eq(arm)]
        oracle = np.where(
            rows["pressure_rank"].le(r), rows["qeu_support"], rows["baseline_support"]
        )
        assert np.array_equal(rows["active_support"].to_numpy(), oracle)


def test_set_replacement_saturation_disclosed_and_singleton() -> None:
    attribution = pd.read_parquet(PACKAGE / "support_attribution.parquet")
    assert attribution["candidate_set_size"].eq(1).all()
    assert not attribution["saturated"].any()
    changed = attribution[attribution["support_changed"]]
    assert (changed["replaced_outcome"] != "").all()
    assert (changed["replacement_outcome"] != "").all()
    depth = pd.read_csv(PACKAGE / "depth_saturation.csv")
    assert depth["saturated_legs"].sum() == 0
    assert depth["noop_legs"].sum() > 0  # pressure-zero activated legs disclosed
    per_arm = depth.groupby("arm", as_index=False).agg(
        activated_legs=("activated_legs", "sum"),
        noop_legs=("noop_legs", "sum"),
        replaced_legs=("replaced_legs", "sum"),
    )
    assert (
        per_arm["activated_legs"] == per_arm["noop_legs"] + per_arm["replaced_legs"]
    ).all()
    decision = json.loads((PACKAGE / "decision.json").read_text(encoding="utf-8"))
    disclosure = decision["replacement_disclosure"]
    assert disclosure["saturated_legs"] == 0
    assert disclosure["candidate_set_size_max"] == 1
    assert disclosure["replaced_legs_total"] == int(changed["issue"].count())


def test_payout_factor_is_applied_once_per_winning_ticket() -> None:
    bundles = pd.read_parquet(PACKAGE / "issue_bundles.parquet")
    attribution = pd.read_parquet(PACKAGE / "support_attribution.parquet")
    winners = bundles[bundles["hit"]]
    assert len(winners) > 0
    for row in winners.head(20).itertuples():
        legs = attribution[
            attribution["issue"].eq(row.issue) & attribution["arm"].eq(row.arm)
        ]
        expected = STAKE_PER_TICKET_CNY * PAYOUT_FACTOR * legs["winning_sp"].prod()
        assert row.gross_cny == pytest.approx(expected, rel=0, abs=1e-9)


def test_exact_common_across_all_arms() -> None:
    bundles = pd.read_parquet(PACKAGE / "issue_bundles.parquet")
    for scope in ["2022", "2023", "2024", "ALL"]:
        scoped = bundles if scope == "ALL" else bundles[bundles["issue_year"].eq(int(scope))]
        issue_sets = {
            arm: frozenset(scoped.loc[scoped["arm"].eq(arm), "issue"]) for arm in ARMS
        }
        assert all(issue_sets[arm] == issue_sets[ARMS[0]] for arm in ARMS[1:])


def test_r0_r3_exact_parity_with_n6_package() -> None:
    mine = pd.read_parquet(PACKAGE / "issue_bundles.parquet")
    upstream = pd.read_parquet(UPSTREAM_N6 / "issue_bundles.parquet")
    r03 = mine[mine["arm"].isin(["R0", "R3"])]
    shared = sorted(set(upstream.columns) & set(r03.columns))
    left = upstream[shared].sort_values(["issue", "arm"], kind="stable").reset_index(drop=True)
    right = r03[shared].sort_values(["issue", "arm"], kind="stable").reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right, check_exact=True, rtol=0, atol=0)
    parity = json.loads((PACKAGE / "n6_parity.json").read_text(encoding="utf-8"))
    assert all(
        parity[key] for key in [
            "decisions_exact", "tickets_exact", "issue_bundles_exact",
            "attribution_exact", "performance_exact", "hit_rate_exact", "risk_exact",
            "capital_paths_exact", "coverage_exact", "bootstrap_reproduction_exact",
            "point_lift_exact",
        ]
    )


def test_matched_r3_lift_matches_published_n6_bootstrap() -> None:
    my_contrasts = pd.read_csv(PACKAGE / "matched_contrasts.csv")
    upstream = pd.read_csv(UPSTREAM_N6 / "bootstrap_lift.csv")
    r3 = my_contrasts[my_contrasts["arm"].eq("R3")].sort_values("scope", kind="stable").reset_index(drop=True)
    up = upstream.sort_values("scope", kind="stable").reset_index(drop=True)
    assert len(r3) == len(up) == 4
    assert np.allclose(r3["matched_lift_cny"], up["matched_lift_cny"], rtol=0, atol=1e-9)
    assert np.allclose(r3["ex_largest_lift_cny"], up["ex_largest_lift_cny"], rtol=0, atol=1e-9)


def test_legacy_ledger_has_full_r_grid_and_changed_rows() -> None:
    summary = pd.read_csv(PACKAGE / "legacy_summary.csv")
    assert set(summary["arm"]).issuperset(set(ARMS))
    total = summary[summary["arm"].eq("ALL")].iloc[0]
    assert total["common_issues"] > 0
    assert total["changed_pnl_rows"] > 0  # chronology correction must change rows
    assert total["attribution_common_legs"] > 0
    assert total["legacy_only_issue_arm_rows"] >= 0
    assert total["legacy_only_unique_issues"] >= 0
    year_routing = pd.read_csv(PACKAGE / "legacy_year_routing.csv")
    attribution_ledger = pd.read_parquet(PACKAGE / "legacy_attribution_ledger.parquet")
    assert "exact_leg" in attribution_ledger.columns
    decision = json.loads((PACKAGE / "decision.json").read_text(encoding="utf-8"))
    assert decision["r0_r3_exact_parity_376"] is True
    assert decision["promotable_to_210"] is False
    assert decision["r_grid"] == list(R_GRID)
    assert decision["replacement_disclosure"]["protocol_log"].endswith("entry 001")


@pytest.mark.parametrize(
    "kind",
    [
        "pnl",            # 篡改结算字段: 单行 pnl 改值
        "coordinated",    # 篡改 ledger 行但保持会计等式 (stake 与 gross 同步改)
        "ticket",         # 篡改票面: 改一张票的 ticket_code
        "missing_group",  # 删掉一个 issue-arm 的整个票组
        "receipt",        # 伪造 source trace: 改 chronology 标记
        "actions_label",  # 伪造 label / future 信息: 训练标签时间戳改为未来
        "decisions",      # 伪造 actions/support: 改 decisions 的 support map
        "metrics",        # 篡改指标: 改 performance.csv 一行
        "manifest_bytes",  # 重写 manifest 伪造: 伪造 bytes 元数据
        "manifest_frame_hash",  # 重写 manifest 伪造: 伪造 frame hash 元数据
    ],
)
def test_tamper_fails_source_replay(tmp_path: Path, kind: str) -> None:
    """REQ-E06: every coordinated tamper class must fail the semantic verifier."""
    package = _copy(tmp_path)
    if kind == "pnl":
        relative = "issue_bundles.parquet"
        frame = pd.read_parquet(package / relative)
        frame.loc[0, "pnl_cny"] += 10_000.0
        frame.to_parquet(package / relative, index=False)
    elif kind == "coordinated":
        relative = "issue_bundles.parquet"
        frame = pd.read_parquet(package / relative)
        # keep pnl = gross - stake identity intact while changing the ledger row
        frame.loc[0, "stake_cny"] += 200.0
        frame.loc[0, "gross_cny"] += 200.0
        frame.to_parquet(package / relative, index=False)
    elif kind == "ticket":
        relative = "tickets.parquet"
        frame = pd.read_parquet(package / relative)
        frame.loc[0, "ticket_code"] = "0|0|0|0|0|0"
        frame.to_parquet(package / relative, index=False)
    elif kind == "missing_group":
        relative = "tickets.parquet"
        frame = pd.read_parquet(package / relative)
        first = frame.iloc[0]
        frame = frame[~(frame["issue"].eq(first.issue) & frame["arm"].eq(first.arm))]
        frame.to_parquet(package / relative, index=False)
    elif kind == "receipt":
        relative = "source_receipt.json"
        receipt = json.loads((package / relative).read_text(encoding="utf-8"))
        receipt["chronology"] = "FORGED"
        (package / relative).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    elif kind == "actions_label":
        relative = "action_receipts.parquet"
        frame = pd.read_parquet(package / relative)
        frame.loc[0, "training_label_available_max_ts"] = "2099-01-01T00:00:00+00:00"
        frame.to_parquet(package / relative, index=False)
    elif kind == "decisions":
        relative = "decisions.parquet"
        frame = pd.read_parquet(package / relative)
        frame.loc[0, "support_json"] = '{"1":"31","2":"31","3":"31","4":"31","5":"31","6":"31"}'
        frame.to_parquet(package / relative, index=False)
    elif kind == "manifest_bytes":
        relative = "performance.csv"
        manifest_path = package / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"][relative]["bytes"] += 1  # metadata-only forgery
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with pytest.raises(ContractError):
            verify_package(REPO, package, DATA_ROOT)
        return
    elif kind == "manifest_frame_hash":
        relative = "issue_bundles.parquet"
        manifest_path = package / "MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["frame_hashes"]["settled"] = "0" * 64  # metadata-only forgery
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with pytest.raises(ContractError):
            verify_package(REPO, package, DATA_ROOT)
        return
    else:  # metrics
        relative = "performance.csv"
        frame = pd.read_csv(package / relative)
        frame.loc[0, "pnl_cny"] += 5_000.0
        frame.to_csv(package / relative, index=False)
    _rehash(package, relative)
    with pytest.raises(ContractError):
        verify_package(REPO, package, DATA_ROOT)


def test_manifest_forgery_fails(tmp_path: Path) -> None:
    """重写 manifest 伪造: contract/implementation 篡改必须被拒."""
    package = _copy(tmp_path)
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contract"] = "FORGED-CONTRACT"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ContractError):
        verify_package(REPO, package, DATA_ROOT)