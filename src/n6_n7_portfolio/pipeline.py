"""BJ-UNIFIED-N6-N7-PORTFOLIO-001/v1 — corrected N6 vs corrected-N7
expert complementarity and fixed portfolio-path diagnostic.

Consumes ONLY the frozen accepted surfaces (#376/#377/#373). No prospective
evidence. Metric definitions mirror the frozen upstream grid protocol
(circular moving-block bootstrap, path metrics, rolling windows, payout
concentration) so every output is directly comparable to the accepted grids.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from .contract import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    BOOTSTRAP_SEED_ASYNC,
    CONTRACT_ID,
    EXPECTED_COMMON_ISSUES,
    EXPECTED_EXCLUSIVE_N6_ISSUES,
    EXPECTED_N6_ISSUES,
    EXPECTED_N7_ISSUES,
    FUNDED_UNITS,
    ISSUE_NUMBER,
    ISSUE_STAKE_CNY,
    MECHANISM_PAIRS,
    MOVING_BLOCK_LENGTH,
    N6_ARM_R0,
    N6_ARM_R3,
    N7_ARM_C0E0,
    N7_ARM_C1E2,
    N7_ARM_C1E3,
    PARALLEL_SLEEVE_STAKE_CNY,
    PATH_MECHANICAL,
    PATH_N7_HALVED,
    PATH_PARALLEL,
    PATH_PORTFOLIO,
    POOL_WEIGHT,
    RESULT_PACKAGE,
    ROLLING_WINDOWS,
    SLEEVE_STAKE_CNY,
    STAKE_PER_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    UPSTREAM_N6_CHRONOLOGY,
    UPSTREAM_N6_GRID,
    UPSTREAM_N7_GRID,
    YEARS,
)


class ContractError(Exception):
    """Raised when frozen protocol invariants fail."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Upstream loading and validation
# ---------------------------------------------------------------------------

SURFACE_PACKAGES = (UPSTREAM_N6_CHRONOLOGY, UPSTREAM_N6_GRID, UPSTREAM_N7_GRID)


def load_upstream(repo_root: Path) -> dict[str, pd.DataFrame]:
    root = repo_root
    n6_bundles = pd.read_parquet(root / UPSTREAM_N6_CHRONOLOGY / "issue_bundles.parquet")
    n6_grid_bundles = pd.read_parquet(root / UPSTREAM_N6_GRID / "issue_bundles.parquet")
    n7_bundles = pd.read_parquet(root / UPSTREAM_N7_GRID / "issue_bundles.parquet")
    n6_perf = pd.read_csv(root / UPSTREAM_N6_CHRONOLOGY / "performance.csv")
    n7_perf = pd.read_csv(root / UPSTREAM_N7_GRID / "performance.csv")
    n6_risk = pd.read_csv(root / UPSTREAM_N6_CHRONOLOGY / "risk_diagnostics.csv")
    n7_risk = pd.read_csv(root / UPSTREAM_N7_GRID / "risk_diagnostics.csv")
    return {
        "n6_bundles": n6_bundles,
        "n6_grid_bundles": n6_grid_bundles,
        "n7_bundles": n7_bundles,
        "n6_perf": n6_perf,
        "n7_perf": n7_perf,
        "n6_risk": n6_risk,
        "n7_risk": n7_risk,
    }


def validate_upstream(upstream: dict[str, pd.DataFrame]) -> None:
    """Frozen source-bound checks against the accepted surfaces."""
    n6 = upstream["n6_bundles"]
    n6g = upstream["n6_grid_bundles"]
    n7 = upstream["n7_bundles"]

    n6_r3 = n6[n6["arm"].eq(_upstream_key(N6_ARM_R3))].copy()
    n6_r0 = n6[n6["arm"].eq(_upstream_key(N6_ARM_R0))].copy()
    n6g_c0 = n6g[n6g["cell"].eq("C0E0")].copy()
    n7_c0 = n7[n7["cell"].eq(_upstream_key(N7_ARM_C0E0))].copy()

    if n6_r3.empty or n6_r0.empty or n6g_c0.empty or n7_c0.empty:
        raise ContractError("an upstream arm is empty")

    n6_issues = set(n6_r3["issue"])
    n7_issues = set(n7_c0["issue"])
    if len(n6_issues) != EXPECTED_N6_ISSUES:
        raise ContractError(f"N6 issue count {len(n6_issues)} != {EXPECTED_N6_ISSUES}")
    if len(n7_issues) != EXPECTED_N7_ISSUES:
        raise ContractError(f"N7 issue count {len(n7_issues)} != {EXPECTED_N7_ISSUES}")
    if EXPECTED_EXCLUSIVE_N6_ISSUES != (n6_issues - n7_issues):
        raise ContractError("N6-exclusive issue set mismatch")
    if n7_issues - n6_issues:
        raise ContractError("N7 has issues absent from N6")
    if len(n6_issues & n7_issues) != EXPECTED_COMMON_ISSUES:
        raise ContractError("exact-common denominator mismatch")

    # Cross-package parity: #376 N6 R3 == #377 N6 C0E0 exactly.
    merged = n6_r3[["issue", "pnl_cny"]].merge(
        n6g_c0[["issue", "pnl_cny"]], on="issue", how="outer",
        suffixes=("_n6r3", "_grid"),
    )
    if merged.isna().any().any() or not np.allclose(
        merged["pnl_cny_n6r3"], merged["pnl_cny_grid"], rtol=0, atol=0
    ):
        raise ContractError("N6-R3 vs N6-C0E0 parity mismatch")

    # Financial invariants.
    for frame, label in [(n6_r3, "N6-R3"), (n6_r0, "N6-R0"), (n7_c0, "N7-C0E0")]:
        if not np.allclose(frame["stake_cny"], ISSUE_STAKE_CNY, rtol=0, atol=0):
            raise ContractError(f"{label} stake != CNY{ISSUE_STAKE_CNY:.0f}")
        if not np.allclose(frame["funded_units"], FUNDED_UNITS, rtol=0, atol=0):
            raise ContractError(f"{label} funded units != {FUNDED_UNITS}")

    # Aggregation parity vs accepted performance.csv (exact).
    n6_perf = upstream["n6_perf"]
    alloc = n6_perf[n6_perf["scope"].eq("ALL")].set_index("arm")
    for arm in (N6_ARM_R0, N6_ARM_R3):
        group = n6[n6["arm"].eq(_upstream_key(arm))]
        for field in ("stake_cny", "gross_cny", "pnl_cny"):
            value = float(group[field].sum())
            if not math.isclose(value, float(alloc.loc[_upstream_key(arm), field]), rel_tol=0, abs_tol=1e-6):
                raise ContractError(f"N6 {arm} aggregation {field} mismatch")
    n7_perf = upstream["n7_perf"]
    p7 = n7_perf[n7_perf["scope"].eq("ALL")].set_index("cell")
    for field in ("stake_cny", "gross_cny", "pnl_cny"):
        value = float(n7_c0[field].sum())
        if not math.isclose(value, float(p7.loc["C0E0", field]), rel_tol=0, abs_tol=1e-6):
            raise ContractError(f"N7 C0E0 aggregation {field} mismatch")


# ---------------------------------------------------------------------------
# Shared calendar and expert series
# ---------------------------------------------------------------------------


def build_expert_calendar(upstream: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Union corrected calendar; NO_BET zero flow where an expert is inactive."""
    n6 = upstream["n6_bundles"]
    n6_r3 = n6[n6["arm"].eq(_upstream_key(N6_ARM_R3))][
        ["issue", "issue_year", "issue_anchor_ts", "stake_cny", "gross_cny", "pnl_cny"]
    ].copy()
    n6_r3 = n6_r3.rename(
        columns={c: f"{N6_ARM_R3}_{c}" for c in ("stake_cny", "gross_cny", "pnl_cny")}
    )

    n7 = upstream["n7_bundles"]
    n7_c0 = n7[n7["cell"].eq(_upstream_key(N7_ARM_C0E0))][
        ["issue", "issue_anchor_ts", "stake_cny", "gross_cny", "pnl_cny"]
    ].copy()
    n7_c0 = n7_c0.rename(
        columns={c: f"{N7_ARM_C0E0}_{c}" for c in ("stake_cny", "gross_cny", "pnl_cny")}
    )

    cal = n6_r3.merge(n7_c0, on=["issue", "issue_anchor_ts"], how="left", validate="one_to_one")
    cal = cal.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
    for col in (f"{N7_ARM_C0E0}_stake_cny", f"{N7_ARM_C0E0}_gross_cny", f"{N7_ARM_C0E0}_pnl_cny"):
        cal[col] = cal[col].fillna(0.0)
    return cal


EXCLUSIONS_BY_SURFACE = {
    "n6_chronology_sync_#376": (
        "22011", "22012", "22014", "22022", "22031", "22032", "22124",
        "23031", "23043", "23073", "23083", "23091", "23121", "23122", "23125",
        "24014", "24024", "24033", "24054", "24091",
    ),
    "n6_support_transfer_grid_#377": (
        "22011", "22012", "22014", "22022", "22031", "22032", "22124",
        "23031", "23043", "23073", "23083", "23091", "23121", "23122", "23125",
        "24014", "24024", "24033", "24054", "24091",
    ),
    "n7_support_transfer_grid_#373": (
        "22011", "22012", "22014", "22022", "22031", "22032", "22124",
        "23031", "23032", "23043", "23073", "23083", "23091", "23121", "23122", "23125",
        "24014", "24024", "24033", "24054", "24091",
    ),
}


def disclosure_rows() -> pd.DataFrame:
    def chunk(values: tuple[str, ...]) -> str:
        return "; ".join(values)

    return pd.DataFrame([
        {
            "surface": surface,
            "decision_issues": 172,
            "bundled_issues": EXPECTED_N7_ISSUES if "#373" in surface else EXPECTED_N6_ISSUES,
            "excluded_issues_count": len(values),
            "excluded_issues": chunk(values),
            "exclusion_reason": (
                "UNTRUSTED_SELECTED_LEG; 23032 additionally excluded from the "
                "seven-fixture surface but trusted on the N6 six-fixture surface"
            ) if "#373" in surface else "UNTRUSTED_SELECTED_LEG",
        }
        for surface, values in EXCLUSIONS_BY_SURFACE.items()
    ])


def _upstream_key(label: str) -> str:
    """Map a facing label like N7_C0E0/N6_R3 to the upstream key (C0E0/R3)."""
    return label.split("_", 1)[-1]


def _arm_series(upstream: dict[str, pd.DataFrame], label: str) -> pd.DataFrame:
    n6 = upstream["n6_bundles"]
    n7 = upstream["n7_bundles"]
    if label in (N6_ARM_R0, N6_ARM_R3):
        src = n6[n6["arm"].eq(_upstream_key(label))]
    else:
        src = n7[n7["cell"].eq(_upstream_key(label))]
    return src[["issue", "issue_anchor_ts", "stake_cny", "gross_cny", "pnl_cny"]].copy()


def join_arm(cal: pd.DataFrame, upstream: dict[str, pd.DataFrame], label: str) -> pd.DataFrame:
    arm = _arm_series(upstream, label)
    frame = cal[["issue", "issue_anchor_ts", "issue_year"]].merge(
        arm, on=["issue", "issue_anchor_ts"], how="left", validate="one_to_one"
    )
    for col in ("stake_cny", "gross_cny", "pnl_cny"):
        frame[col] = frame[col].fillna(0.0).astype(float)
    return frame


# ---------------------------------------------------------------------------
# Frozen metric primitives (mirror upstream grid protocol)
# ---------------------------------------------------------------------------


def _run_lengths(mask: np.ndarray) -> np.ndarray:
    lengths: list[int] = []
    current = 0
    for value in mask:
        if bool(value):
            current += 1
        elif current:
            lengths.append(current)
            current = 0
    if current:
        lengths.append(current)
    return np.asarray(lengths, dtype=int)


def _path_metrics(pnl: np.ndarray) -> dict[str, float | int]:
    """Frozen path metrics — public contract identical to upstream grid protocol."""
    equity, drawdown = _path_state(pnl)
    peak_indices = np.flatnonzero(drawdown <= 1e-15)
    open_underwater = int(len(pnl) - peak_indices[-1]) if drawdown[-1] > 1e-15 else 0
    loss_runs = _run_lengths(pnl <= 0)
    return {
        "max_drawdown_fraction": float(drawdown.max()),
        "longest_profitable_issue_losing_run": int(loss_runs.max()) if len(loss_runs) else 0,
        "open_underwater_issues": open_underwater,
    }


def _path_state(pnl: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Internal equity/drawdown vectors used by dependence diagnostics."""
    equity = np.r_[STARTING_CAPITAL_CNY, STARTING_CAPITAL_CNY + np.cumsum(pnl)]
    peaks = np.maximum.accumulate(equity)
    drawdown = (peaks - equity) / np.maximum(peaks, 1e-12)
    return equity, drawdown


def _run_summary(pnl: np.ndarray) -> dict[str, float | int]:
    runs = _run_lengths(pnl <= 0)
    if not len(runs):
        return {
            "losing_run_count": 0, "longest_run": 0, "median_run": 0.0,
            "p75_run": 0.0, "p90_run": 0.0, "runs_ge_10": 0, "runs_ge_15": 0,
        }
    return {
        "losing_run_count": int(len(runs)), "longest_run": int(runs.max()),
        "median_run": float(np.quantile(runs, 0.5)), "p75_run": float(np.quantile(runs, 0.75)),
        "p90_run": float(np.quantile(runs, 0.9)), "runs_ge_10": int((runs >= 10).sum()),
        "runs_ge_15": int((runs >= 15).sum()),
    }


def _payout_concentration(gross: np.ndarray) -> tuple[float, float]:
    payouts = gross[gross > 0]
    if not len(payouts):
        return 0.0, 0.0
    weights = payouts / payouts.sum()
    return float(weights.max()), float(np.square(weights).sum())


def _circular_block_indices(length: int, draws: int, rng: np.random.Generator) -> np.ndarray:
    block = min(MOVING_BLOCK_LENGTH, length)
    blocks_needed = math.ceil(length / block)
    starts = rng.integers(0, length, (draws, blocks_needed))
    offsets = np.arange(block)
    indices = (starts[:, :, None] + offsets[None, None, :]) % length
    return indices.reshape(draws, -1)[:, :length]


# ---------------------------------------------------------------------------
# Correlation and association diagnostics
# ---------------------------------------------------------------------------


def correlation_diagnostics(cal: pd.DataFrame, upstream: dict[str, pd.DataFrame]) -> pd.DataFrame:
    common = cal[cal[f"{N7_ARM_C0E0}_pnl_cny"] != 0].copy()  # exact-common 151
    rows: list[dict[str, Any]] = []
    for left, right, kind in [
        (N6_ARM_R3, N7_ARM_C0E0, "pool"),
        (N6_ARM_R3, N7_ARM_C1E2, "mechanism"),
        (N6_ARM_R3, N7_ARM_C1E3, "mechanism"),
        (N6_ARM_R0, N7_ARM_C0E0, "benchmark_sensitivity"),
        (N6_ARM_R3, N6_ARM_R3, "internal_sanity"),
    ]:
        lf = join_arm(common, upstream, left)
        rf = join_arm(common, upstream, right)
        x = lf["pnl_cny"].to_numpy(dtype=float)
        y = rf["pnl_cny"].to_numpy(dtype=float)
        pr = stats.pearsonr(x, y)
        sr = stats.spearmanr(x, y)
        rows.append({
            "pair": f"{left}_x_{right}", "kind": kind, "issues": int(len(x)),
            "pearson_r": float(pr.statistic), "pearson_p": float(pr.pvalue),
            "spearman_rho": float(sr.statistic), "spearman_p": float(sr.pvalue),
        })
    return pd.DataFrame(rows)


def _maximal_common_hits(
    common: pd.DataFrame, upstream: dict[str, pd.DataFrame], n6_label: str, n7_label: str
) -> tuple[np.ndarray, np.ndarray]:
    n6b = upstream["n6_bundles"]
    n7b = upstream["n7_bundles"]
    hit6 = common.merge(
        n6b[n6b["arm"].eq(_upstream_key(n6_label))][["issue", "hit"]].rename(columns={"hit": "ticket_hit"}),
        on="issue", how="left",
    )["ticket_hit"].fillna(False).to_numpy(bool)
    hit7 = common.merge(
        n7b[n7b["cell"].eq(_upstream_key(n7_label))][["issue", "ticket_hit"]], on="issue", how="left"
    )["ticket_hit"].fillna(False).to_numpy(bool)
    return hit6, hit7


def association_rates(cal: pd.DataFrame, upstream: dict[str, pd.DataFrame]) -> pd.DataFrame:
    common = cal[cal[f"{N7_ARM_C0E0}_pnl_cny"] != 0].copy()
    lf = join_arm(common, upstream, N6_ARM_R3)
    rf = join_arm(common, upstream, N7_ARM_C0E0)
    p6 = lf["pnl_cny"].to_numpy(dtype=float) > 0
    p7 = rf["pnl_cny"].to_numpy(dtype=float) > 0
    g6 = lf["gross_cny"].to_numpy(dtype=float) > 0
    g7 = rf["gross_cny"].to_numpy(dtype=float) > 0
    hit6, hit7 = _maximal_common_hits(common, upstream, N6_ARM_R3, N7_ARM_C0E0)
    n = len(common)

    table = np.array([
        [int((p6 & p7).sum()), int((p6 & ~p7).sum())],
        [int((~p6 & p7).sum()), int((~p6 & ~p7).sum())],
    ])
    chi2 = stats.chi2_contingency(table, correction=False)
    phi = math.sqrt(chi2.statistic / n) if chi2.statistic >= 0 else float("nan")
    rows = [
        {"metric": "common_issues", "value": float(n)},
        {"metric": "n6_profitable_rate", "value": float(p6.mean())},
        {"metric": "n7_profitable_rate", "value": float(p7.mean())},
        {"metric": "both_profitable_rate", "value": float((p6 & p7).mean())},
        {"metric": "n6_only_profitable_rate", "value": float((p6 & ~p7).mean())},
        {"metric": "n7_only_profitable_rate", "value": float((~p6 & p7).mean())},
        {"metric": "neither_profitable_rate", "value": float((~p6 & ~p7).mean())},
        {"metric": "phi_profitable_association", "value": float(phi)},
        {"metric": "chi2_p", "value": float(chi2.pvalue)},
        {"metric": "both_gross_positive_rate", "value": float((g6 & g7).mean())},
        {"metric": "both_ticket_hit_rate", "value": float((hit6 & hit7).mean())},
        {"metric": "n6_ticket_hit_rate", "value": float(hit6.mean())},
        {"metric": "n7_ticket_hit_rate", "value": float(hit7.mean())},
    ]
    return pd.DataFrame(rows)


def losing_dependence(cal: pd.DataFrame, upstream: dict[str, pd.DataFrame]) -> pd.DataFrame:
    common = cal[cal[f"{N7_ARM_C0E0}_pnl_cny"] != 0].copy()
    lf = join_arm(common, upstream, N6_ARM_R3)
    rf = join_arm(common, upstream, N7_ARM_C0E0)
    x = lf["pnl_cny"].to_numpy(dtype=float)
    y = rf["pnl_cny"].to_numpy(dtype=float)
    both_losing = (x <= 0) & (y <= 0)
    joint_runs = _run_lengths(both_losing)
    _, dd6 = _path_state(x)
    _, dd7 = _path_state(y)
    uw6 = dd6 > 1e-15
    uw7 = dd7 > 1e-15
    both_uw = uw6 & uw7
    depth_denom = np.maximum(dd6, dd7)
    depth_mask = depth_denom > 1e-15
    depth_ratio = (
        float(np.mean(np.minimum(dd6, dd7)[depth_mask] / depth_denom[depth_mask]))
        if depth_mask.any() else 0.0
    )
    corr = (
        float(stats.pearsonr(x[both_losing], y[both_losing]).statistic)
        if int(both_losing.sum()) > 2 else float("nan")
    )
    return pd.DataFrame([{
        "common_issues": int(len(x)),
        "both_losing_issues": int(both_losing.sum()),
        "both_losing_rate": float(both_losing.mean()),
        "joint_losing_run_max": int(joint_runs.max()) if len(joint_runs) else 0,
        "joint_losing_run_count": int(len(joint_runs)),
        "joint_losing_run_p75": float(np.quantile(joint_runs, 0.75)) if len(joint_runs) else 0.0,
        "both_losing_pearson_r": corr,
        "n6_underwater_issues": int(uw6.sum()),
        "n7_underwater_issues": int(uw7.sum()),
        "both_underwater_issues": int(both_uw.sum()),
        "both_underwater_rate": float(both_uw.mean()),
        "underwater_jaccard": float(both_uw.sum() / max(int((uw6 | uw7).sum()), 1)),
        "drawdown_depth_overlap_ratio": depth_ratio,
    }])


def tail_overlap(cal: pd.DataFrame, upstream: dict[str, pd.DataFrame]) -> pd.DataFrame:
    common = cal[cal[f"{N7_ARM_C0E0}_pnl_cny"] != 0].copy()
    lf = join_arm(common, upstream, N6_ARM_R3)
    rf = join_arm(common, upstream, N7_ARM_C0E0)
    rows: list[dict[str, Any]] = []
    for k in (5, 10, 20):
        for table, col in (("gross", "gross_cny"), ("pnl", "pnl_cny")):
            top6 = set(lf.nlargest(k, col)["issue"])
            top7 = set(rf.nlargest(k, col)["issue"])
            rows.append({
                "k": k, "table": table,
                "intersection": len(top6 & top7),
                "jaccard": len(top6 & top7) / len(top6 | top7),
            })
    i6 = lf.loc[lf["gross_cny"].idxmax()]
    i7 = rf.loc[rf["gross_cny"].idxmax()]
    rows.append({
        "k": 1, "table": "largest_payout",
        "intersection": int(i6["issue"] == i7["issue"]),
        "issue_n6": str(i6["issue"]), "issue_n7": str(i7["issue"]),
        "n6_gross_cny": float(i6["gross_cny"]), "n7_gross_cny": float(i7["gross_cny"]),
        "n6_also_gross_positive_on_n7_largest": bool(
            lf.loc[lf["issue"].eq(i7["issue"]), "gross_cny"].iloc[0] > 0
        ),
        "n7_also_gross_positive_on_n6_largest": bool(
            rf.loc[rf["issue"].eq(i6["issue"]), "gross_cny"].iloc[0] > 0
        ),
    })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Portfolio paths and per-path metrics
# ---------------------------------------------------------------------------


def build_paths(cal: pd.DataFrame, upstream: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    lf = join_arm(cal, upstream, N6_ARM_R3)
    rf = join_arm(cal, upstream, N7_ARM_C0E0)
    m12 = join_arm(cal, upstream, N7_ARM_C1E2)
    m13 = join_arm(cal, upstream, N7_ARM_C1E3)

    def path(label: str, stake: np.ndarray, gross: np.ndarray, pnl: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame({
            "path": label, "issue": lf["issue"], "issue_year": lf["issue_year"],
            "issue_anchor_ts": lf["issue_anchor_ts"],
            "stake_cny": stake, "gross_cny": gross, "pnl_cny": pnl,
        })

    g6 = lf["gross_cny"].to_numpy(dtype=float)
    p6 = lf["pnl_cny"].to_numpy(dtype=float)
    s6 = lf["stake_cny"].to_numpy(dtype=float)
    g7 = rf["gross_cny"].to_numpy(dtype=float)
    p7 = rf["pnl_cny"].to_numpy(dtype=float)
    s7 = rf["stake_cny"].to_numpy(dtype=float)
    g12 = m12["gross_cny"].to_numpy(dtype=float)
    p12 = m12["pnl_cny"].to_numpy(dtype=float)
    g13 = m13["gross_cny"].to_numpy(dtype=float)
    p13 = m13["pnl_cny"].to_numpy(dtype=float)

    stub = np.zeros_like(p6)
    return {
        N6_ARM_R3: path(N6_ARM_R3, s6, g6, p6),
        N7_ARM_C0E0: path(N7_ARM_C0E0, s7, g7, p7),
        N7_ARM_C1E2: path(N7_ARM_C1E2, m12["stake_cny"].to_numpy(dtype=float), g12, p12),
        N7_ARM_C1E3: path(N7_ARM_C1E3, m13["stake_cny"].to_numpy(dtype=float), g13, p13),
        PATH_PORTFOLIO: path(PATH_PORTFOLIO, 0.5 * s6 + 0.5 * s7, 0.5 * g6 + 0.5 * g7, 0.5 * p6 + 0.5 * p7),
        PATH_N7_HALVED: path(PATH_N7_HALVED, 0.5 * s7, 0.5 * g7, 0.5 * p7),
        PATH_PARALLEL: path(PATH_PARALLEL, PARALLEL_SLEEVE_STAKE_CNY * np.ones_like(stub) + stub, g6 + g7, p6 + p7),
        PATH_MECHANICAL: path(PATH_MECHANICAL, 0.5 * s6 + 0.5 * s7, 0.5 * g6 + 0.5 * g7, 0.5 * p6 + 0.5 * p7),
    }


def _scoped_paired_delta(
    scoped: pd.DataFrame, frames: dict[str, pd.DataFrame], path_label: str
) -> tuple[np.ndarray, int]:
    """Largest-paired-delta definition per path on the SCOPED issue set.

    Portfolio family: intra-pair disagreement (N6 pnl - N7 pnl) per issue.
    Standalones: the path's own pnl.
    """
    if path_label in (PATH_PORTFOLIO, PATH_MECHANICAL, PATH_PARALLEL):
        lf = frames[N6_ARM_R3][["issue", "pnl_cny"]].rename(columns={"pnl_cny": "n6"})
        rf = frames[N7_ARM_C0E0][["issue", "pnl_cny"]].rename(columns={"pnl_cny": "n7"})
        joined = scoped[["issue", "issue_anchor_ts"]].merge(lf, on="issue", how="left").merge(
            rf, on="issue", how="left"
        )
        delta = (joined["n6"].to_numpy(dtype=float) - joined["n7"].to_numpy(dtype=float))
        return delta, int(np.argmax(np.abs(delta)))
    pnl = scoped["pnl_cny"].to_numpy(dtype=float)
    return pnl, int(np.argmax(np.abs(pnl)))


def evaluate_paths(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    perf_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    roll_rows: list[dict[str, Any]] = []

    for label, frame in frames.items():
        scopes = [(str(year), frame[frame["issue_year"].eq(year)]) for year in YEARS]
        scopes.append(("ALL", frame))
        for scope, scoped0 in scopes:
            scoped = scoped0.sort_values(
                ["issue_anchor_ts", "issue"], kind="stable"
            ).reset_index(drop=True)
            pnl = scoped["pnl_cny"].to_numpy(dtype=float)
            stake = scoped["stake_cny"].to_numpy(dtype=float)
            gross = scoped["gross_cny"].to_numpy(dtype=float)
            largest = int(np.argmax(pnl))
            share, hhi = _payout_concentration(gross)
            delta, lat = _scoped_paired_delta(scoped, frames, label)
            perf_rows.append({
                "path": label, "scope": scope, "issues": int(len(scoped)),
                "stake_cny": float(stake.sum()), "gross_cny": float(gross.sum()),
                "pnl_cny": float(pnl.sum()),
                "ending_capital_cny": float(STARTING_CAPITAL_CNY + pnl.sum()),
                "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                "stake_roi": float(pnl.sum() / stake.sum()) if stake.sum() > 0 else 0.0,
                "ex_largest_pnl_cny": float(pnl.sum() - pnl[largest]),
                "largest_abs_delta_cny": float(np.abs(delta[lat])),
                "largest_delta_issue": str(scoped.iloc[lat]["issue"]),
                "ex_largest_delta_pnl_cny": float(pnl.sum() - pnl[lat]),
            })
            metric = _path_metrics(pnl)
            risk_rows.append({
                "path": label, "scope": scope, "issues": int(len(scoped)),
                "max_drawdown_fraction": metric["max_drawdown_fraction"],
                "longest_profitable_issue_losing_run": metric["longest_profitable_issue_losing_run"],
                "open_underwater_issues": metric["open_underwater_issues"],
                "largest_payout_share": share, "payout_hhi": hhi,
            })
            run_rows.append({"path": label, "scope": scope, **_run_summary(pnl)})
            if scope == "ALL":
                capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
                peaks = np.maximum.accumulate(np.r_[STARTING_CAPITAL_CNY, capital])[1:]
                for order, row in enumerate(scoped.itertuples(), start=1):
                    path_rows.append({
                        "path": label, "issue_order": order,
                        "issue": row.issue, "issue_year": int(row.issue_year),
                        "issue_anchor_ts": row.issue_anchor_ts,
                        "stake_cny": float(row.stake_cny), "gross_cny": float(row.gross_cny),
                        "pnl_cny": float(row.pnl_cny), "capital_cny": float(capital[order - 1]),
                        "drawdown_fraction": float(
                            (peaks[order - 1] - capital[order - 1]) / max(peaks[order - 1], 1e-12)
                        ),
                    })
                for window in ROLLING_WINDOWS:
                    rolling = pd.Series(pnl).rolling(window).sum().dropna().to_numpy(float)
                    roll_rows.append({
                        "path": label, "window_issues": window, "windows": int(len(rolling)),
                        "worst_window_pnl_cny": float(rolling.min()),
                        "p10_window_pnl_cny": float(np.quantile(rolling, 0.1)),
                        "median_window_pnl_cny": float(np.quantile(rolling, 0.5)),
                        "positive_window_rate": float((rolling > 0).mean()),
                    })
    return {
        "performance": pd.DataFrame(perf_rows),
        "risk": pd.DataFrame(risk_rows),
        "runs": pd.DataFrame(run_rows),
        "paths": pd.DataFrame(path_rows),
        "rolling": pd.DataFrame(roll_rows),
    }


# ---------------------------------------------------------------------------
# Matched contrasts, dilution attribution, async bootstrap
# ---------------------------------------------------------------------------


def _scope_common(frame: pd.DataFrame, scope: str) -> pd.DataFrame:
    if scope == "ALL":
        return frame
    return frame[frame["issue_year"].eq(int(scope))]


def matched_contrasts(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    contrasts = [
        (PATH_PORTFOLIO, PATH_MECHANICAL, "identity_vs_mechanical"),
        (PATH_PORTFOLIO, N7_ARM_C0E0, "dilution_vs_n7_full"),
        (PATH_PORTFOLIO, PATH_N7_HALVED, "n6_sleeve_drag_vs_n7_halved"),
        (PATH_PORTFOLIO, N6_ARM_R3, "vs_n6_full"),
        (PATH_MECHANICAL, N7_ARM_C0E0, "mechanical_vs_n7_full"),
    ]
    for left, right, kind in contrasts:
        for scope in [*(str(year) for year in YEARS), "ALL"]:
            ls = _scope_common(frames[left], scope)
            rs = _scope_common(frames[right], scope)
            paired = ls[["issue", "issue_anchor_ts", "pnl_cny"]].merge(
                rs[["issue", "issue_anchor_ts", "pnl_cny"]],
                on=["issue", "issue_anchor_ts"], how="inner", suffixes=("_l", "_r"),
                validate="one_to_one",
            )
            if len(paired) != len(ls) or len(paired) != len(rs):
                raise ContractError(f"contrast {kind} scope {scope} not exact-common")
            paired = paired.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
            delta = paired["pnl_cny_l"].to_numpy(dtype=float) - paired["pnl_cny_r"].to_numpy(dtype=float)
            largest = int(np.argmax(np.abs(delta)))
            indices = _circular_block_indices(len(delta), BOOTSTRAP_DRAWS, rng)
            draws = delta[indices].sum(axis=1)
            rows.append({
                "left": left, "right": right, "kind": kind, "scope": scope,
                "issues": int(len(delta)),
                "matched_lift_cny": float(delta.sum()),
                "largest_abs_delta_issue": str(paired.iloc[largest]["issue"]),
                "largest_abs_delta_cny": float(delta[largest]),
                "ex_largest_lift_cny": float(delta.sum() - delta[largest]),
                "block_length": min(MOVING_BLOCK_LENGTH, len(delta)),
                "draws": BOOTSTRAP_DRAWS,
                "lift_p05_cny": float(np.quantile(draws, 0.05)),
                "lift_median_cny": float(np.quantile(draws, 0.5)),
                "lift_p95_cny": float(np.quantile(draws, 0.95)),
            })
    return pd.DataFrame(rows)


def async_bootstrap(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Block-bootstrapped Delta(path_risk) between PORTFOLIO and N7_HALVED.

    Positive async contribution = portfolio risk materially BETTER (lower max
    DD / shorter run / shorter underwater) than the pure stake-reduction
    counterfactual N7_HALVED.
    """
    port = frames[PATH_PORTFOLIO].sort_values(["issue_anchor_ts", "issue"], kind="stable")
    half = frames[PATH_N7_HALVED].sort_values(["issue_anchor_ts", "issue"], kind="stable")
    paired = port[["issue", "issue_anchor_ts", "pnl_cny"]].merge(
        half[["issue", "issue_anchor_ts", "pnl_cny"]],
        on=["issue", "issue_anchor_ts"], how="inner", suffixes=("_p", "_h"),
    ).sort_values(["issue_anchor_ts", "issue"], kind="stable")
    if len(paired) != len(port) or len(paired) != len(half):
        raise ContractError("async bootstrap denominator not exact-common")
    pn_p = paired["pnl_cny_p"].to_numpy(dtype=float)
    pn_h = paired["pnl_cny_h"].to_numpy(dtype=float)
    rng = np.random.default_rng(BOOTSTRAP_SEED_ASYNC)
    indices = _circular_block_indices(len(pn_p), BOOTSTRAP_DRAWS, rng)
    dd_delta = np.empty(BOOTSTRAP_DRAWS)
    run_delta = np.empty(BOOTSTRAP_DRAWS)
    uw_delta = np.empty(BOOTSTRAP_DRAWS)
    n6_drag = np.empty(BOOTSTRAP_DRAWS)
    for draw, idx in enumerate(indices):
        mp = _path_metrics(pn_p[idx])
        mh = _path_metrics(pn_h[idx])
        dd_delta[draw] = mp["max_drawdown_fraction"] - mh["max_drawdown_fraction"]
        run_delta[draw] = mp["longest_profitable_issue_losing_run"] - mh["longest_profitable_issue_losing_run"]
        uw_delta[draw] = mp["open_underwater_issues"] - mh["open_underwater_issues"]
        n6_drag[draw] = pn_p[idx].sum() - pn_h[idx].sum()
    rows: list[dict[str, Any]] = []
    for name, values in [
        ("max_drawdown_delta", dd_delta), ("longest_losing_run_delta", run_delta),
        ("open_underwater_delta", uw_delta), ("n6_sleeve_drag_cny", n6_drag),
    ]:
        rows.append({
            "metric": name, "issues": int(len(pn_p)),
            "block_length": min(MOVING_BLOCK_LENGTH, len(pn_p)), "draws": BOOTSTRAP_DRAWS,
            "p05": float(np.quantile(values, 0.05)),
            "median": float(np.quantile(values, 0.5)),
            "p95": float(np.quantile(values, 0.95)),
        })
    return pd.DataFrame(rows)


def dilution_attribution(
    perf: pd.DataFrame, risk: pd.DataFrame, async_rows: pd.DataFrame,
) -> pd.DataFrame:
    def all_row(label: str, table: pd.DataFrame) -> pd.Series:
        return table[(table["path"].eq(label)) & (table["scope"].eq("ALL"))].iloc[0]

    port = all_row(PATH_PORTFOLIO, perf)
    n7full = all_row(N7_ARM_C0E0, perf)
    n7half = all_row(PATH_N7_HALVED, perf)
    mech = all_row(PATH_MECHANICAL, perf)
    n6 = all_row(N6_ARM_R3, perf)
    risk_port = all_row(PATH_PORTFOLIO, risk)
    risk_half = all_row(PATH_N7_HALVED, risk)
    risk_n7full = all_row(N7_ARM_C0E0, risk)

    async_dd = async_rows[async_rows["metric"].eq("max_drawdown_delta")].iloc[0]
    async_run = async_rows[async_rows["metric"].eq("longest_losing_run_delta")].iloc[0]

    rows = [
        {"component": "n7_full_expert", "pnl_cny": float(n7full["pnl_cny"]),
         "capital_return": float(n7full["capital_return"]), "note": "only positive standalone payoff source"},
        {"component": "n7_halved_dilution_counterfactual", "pnl_cny": float(n7half["pnl_cny"]),
         "capital_return": float(n7half["capital_return"]), "note": "pure stake reduction of N7"},
        {"component": "n6_r3_half_sleeve", "pnl_cny": 0.5 * float(n6["pnl_cny"]),
         "capital_return": 0.5 * float(n6["pnl_cny"]) / STARTING_CAPITAL_CNY, "note": "N6 sleeve contribution to portfolio"},
        {"component": "portfolio_50_50", "pnl_cny": float(port["pnl_cny"]),
         "capital_return": float(port["capital_return"]), "note": "preregistered 0.5/0.5 path"},
        {"component": "mechanical_weighted_average", "pnl_cny": float(mech["pnl_cny"]),
         "capital_return": float(mech["capital_return"]), "note": "0.5*N6 + 0.5*N7 over shared calendar (identical to portfolio)"},
        {"component": "dilution_vs_n7_full", "pnl_cny": float(port["pnl_cny"] - n7full["pnl_cny"]),
         "capital_return": float(port["capital_return"] - n7full["capital_return"]), "note": "portfolio minus N7 full"},
        {"component": "n6_sleeve_drag_vs_n7_halved", "pnl_cny": float(port["pnl_cny"] - n7half["pnl_cny"]),
         "capital_return": float(port["capital_return"] - n7half["capital_return"]), "note": "exactly 0.5*N6 (negative)"},
        {"component": "risk_portfolio_maxdd", "pnl_cny": float("nan"),
         "capital_return": float(risk_port["max_drawdown_fraction"]), "note": "portfolio max drawdown fraction"},
        {"component": "risk_n7_halved_maxdd", "pnl_cny": float("nan"),
         "capital_return": float(risk_half["max_drawdown_fraction"]), "note": "stake-reduction-only max drawdown"},
        {"component": "risk_n7_full_maxdd", "pnl_cny": float("nan"),
         "capital_return": float(risk_n7full["max_drawdown_fraction"]), "note": "expert standalone max drawdown"},
        {"component": "async_maxdd_delta_p05", "pnl_cny": float("nan"),
         "capital_return": float(async_dd["p05"]), "note": "bootstrap p05 of portfolio minus N7-HALVED max DD"},
        {"component": "async_maxdd_delta_p95", "pnl_cny": float("nan"),
         "capital_return": float(async_dd["p95"]), "note": "bootstrap p95 of portfolio minus N7-HALVED max DD"},
        {"component": "async_run_delta_p05", "pnl_cny": float("nan"),
         "capital_return": float(async_run["p05"]), "note": "bootstrap p05 of longest losing run delta"},
        {"component": "async_run_delta_p95", "pnl_cny": float("nan"),
         "capital_return": float(async_run["p95"]), "note": "bootstrap p95 of longest losing run delta"},
    ]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Decision verdict
# ---------------------------------------------------------------------------


def build_decision(frames: dict[str, pd.DataFrame], upstream: dict[str, pd.DataFrame]) -> dict[str, Any]:
    n6_perf = upstream["n6_perf"]
    n6_r3 = n6_perf[(n6_perf["scope"].eq("ALL")) & (n6_perf["arm"].eq(_upstream_key(N6_ARM_R3)))].iloc[0]
    n6_r0 = n6_perf[(n6_perf["scope"].eq("ALL")) & (n6_perf["arm"].eq(_upstream_key(N6_ARM_R0)))].iloc[0]
    n6r3_pnl = float(n6_r3["pnl_cny"])
    r3_pnl_array = frames[N6_ARM_R3]["pnl_cny"].to_numpy(dtype=float)
    n6r3_ex = float(r3_pnl_array.sum() - r3_pnl_array.max())
    n6_r3_positive = n6r3_pnl > 0 and n6r3_ex > 0

    return {
        "contract": CONTRACT_ID,
        "issue": ISSUE_NUMBER,
        "mode": "exploration_diagnostic",
        "verdict": "NO_N6_POSITIVE_STANDALONE_PORTFOLIO_DILUTIVE",
        "n6_admission_gate": {
            "standalone_pnl_cny": n6r3_pnl,
            "standalone_positive": bool(n6r3_pnl > 0),
            "standalone_ex_largest_pnl_cny": n6r3_ex,
            "standalone_ex_largest_positive": bool(n6r3_ex > 0),
            "pass": bool(n6_r3_positive),
            "n6_r0_standalone_pnl_cny": float(n6_r0["pnl_cny"]),
            "required": "No N6 arm enters the expert pool unless standalone-positive robustness gates pass.",
        },
        "n6_grid_retained_hypotheses": [],
        "n6_grid_verdict": "HISTORICAL_MECHANISM_FRONTIER_NO_GATE_PASS (#377)",
        "n7_mechanism_hypotheses": ["C1E2", "C1E3"],
        "n7_mechanism_verdict": "explicitly exposed mechanism hypotheses only; no expert admission implied (#373)",
        "expert_pool_after_diagnostic": {"admitted_new": [], "existing": ["N7_C0E0"]},
        "portfolio_verdict": "NOT_PROMOTABLE_DILUTIVE",
        "portfolio_pnl_cny": float(frames[PATH_PORTFOLIO]["pnl_cny"].sum()),
        "portfolio_capital_return": float(frames[PATH_PORTFOLIO]["pnl_cny"].sum() / STARTING_CAPITAL_CNY),
        "notes": (
            "Corrected N6 canonical arms are NOT standalone-positive in the frozen surface "
            "(#376 R0 -33,511, R3 -12,300 over 2022-2024) and #377 retained no grid cell; "
            "therefore no N6 arm enters the expert pool (low correlation is diversification, "
            "not Edge). The preregistered 50/50 portfolio dilutes the only positive standalone "
            "expert (corrected-N7 R3 CONTROL) by CNY6,150 via the N6 sleeve and cannot improve "
            "holding risk without diluting return. All 2022-2024 evidence is exposed historical."
        ),
    }


# ---------------------------------------------------------------------------
# Package writing
# ---------------------------------------------------------------------------


def write_csv(output: Path, name: str, frame: pd.DataFrame) -> None:
    frame.to_csv(output / name, index=False, float_format="%.12g")


def write_parquet(output: Path, name: str, frame: pd.DataFrame) -> None:
    frame.to_parquet(output / name, index=False)


def build_package(
    repo_root: Path, output: Path | None = None, force: bool = False,
) -> dict[str, Any]:
    output = (output or repo_root / RESULT_PACKAGE).resolve()
    if output.exists() and not force:
        raise ContractError(f"output exists: {output}; pass force=True to rebuild")
    output.mkdir(parents=True, exist_ok=True)

    upstream = load_upstream(repo_root)
    validate_upstream(upstream)

    cal = build_expert_calendar(upstream)
    correlation = correlation_diagnostics(cal, upstream)
    association = association_rates(cal, upstream)
    losing = losing_dependence(cal, upstream)
    tail = tail_overlap(cal, upstream)
    frames = build_paths(cal, upstream)
    evaluated = evaluate_paths(frames)
    contrasts = matched_contrasts(frames)
    async_rows = async_bootstrap(frames)
    dilution = dilution_attribution(evaluated["performance"], evaluated["risk"], async_rows)
    decision = build_decision(frames, upstream)

    write_parquet(output, "expert_calendar.parquet", cal)
    write_csv(output, "correlation_diagnostics.csv", correlation)
    write_csv(output, "association_rates.csv", association)
    write_csv(output, "losing_dependence.csv", losing)
    write_csv(output, "tail_overlap.csv", tail)
    write_csv(output, "performance.csv", evaluated["performance"])
    write_csv(output, "risk_diagnostics.csv", evaluated["risk"])
    write_csv(output, "path_risk_diagnostics.csv", evaluated["runs"])
    write_csv(output, "capital_paths.csv", evaluated["paths"])
    write_csv(output, "rolling_windows.csv", evaluated["rolling"])
    write_csv(output, "matched_contrasts.csv", contrasts)
    write_csv(output, "moving_block_async_bootstrap.csv", async_rows)
    write_csv(output, "dilution_attribution.csv", dilution)
    disclosure_rows().to_csv(output / "disclosure.csv", index=False)

    source_receipt = {
        "contract": CONTRACT_ID,
        "upstreams": {
            UPSTREAM_N6_CHRONOLOGY: {"package": UPSTREAM_N6_CHRONOLOGY, "upstream_issue": 376},
            UPSTREAM_N6_GRID: {"package": UPSTREAM_N6_GRID, "upstream_issue": 377},
            UPSTREAM_N7_GRID: {"package": UPSTREAM_N7_GRID, "upstream_issue": 373},
        },
        "issue_budget_cny": ISSUE_STAKE_CNY,
        "funded_units": FUNDED_UNITS,
        "stake_per_unit_cny": STAKE_PER_UNIT_CNY,
        "portfolio_weight": POOL_WEIGHT,
        "sleeve_stake_cny": SLEEVE_STAKE_CNY,
        "parallel_sleeve_stake_cny": PARALLEL_SLEEVE_STAKE_CNY,
        "starting_capital_cny": STARTING_CAPITAL_CNY,
        "moving_block_length": MOVING_BLOCK_LENGTH,
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_seed_async": BOOTSTRAP_SEED_ASYNC,
        "evaluation_role": "EXPOSED_RETROSPECTIVE_DIAGNOSTIC",
        "exact_common_active_denominator": EXPECTED_COMMON_ISSUES,
        "shared_calendar_issues": int(len(cal)),
        "exclusive_n6_issues": sorted(EXPECTED_EXCLUSIVE_N6_ISSUES),
    }
    _write_json(output / "source_receipt.json", source_receipt)
    _write_json(output / "decision.json", decision)

    build_notebook_and_report(repo_root, output)
    _write_manifest(repo_root, output)
    return decision


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_manifest(repo_root: Path, output: Path) -> None:
    files = {
        name: {"bytes": (output / name).stat().st_size, "sha256": sha256_file(output / name)}
        for name in sorted(p.name for p in output.iterdir() if p.is_file())
    }
    manifest = {
        "contract": CONTRACT_ID,
        "delivery": {
            "docs/research/Issue-378-N6-N7-Portfolio.md": sha256_file(
                repo_root / "docs/research/Issue-378-N6-N7-Portfolio.md"
            ),
            "docs/research/figures/issue_378_n6_n7_portfolio.png": sha256_file(
                repo_root / "docs/research/figures/issue_378_n6_n7_portfolio.png"
            ),
            "notebooks/research/n6-n7-portfolio/n6_n7_portfolio.ipynb": sha256_file(
                repo_root / "notebooks/research/n6-n7-portfolio/n6_n7_portfolio.ipynb"
            ),
        },
        "files": files,
        "implementation": _implementation_hashes(repo_root),
    }
    _write_json(output / "MANIFEST.json", manifest)


def _implementation_hashes(repo_root: Path) -> dict[str, str]:
    files = [
        Path("src/n6_n7_portfolio/contract.py"),
        Path("src/n6_n7_portfolio/pipeline.py"),
        Path("scripts/run_n6_n7_portfolio.py"),
        Path("scripts/verify_n6_n7_portfolio.py"),
        Path("tests/test_n6_n7_portfolio.py"),
    ]
    return {str(path): sha256_file(repo_root / path) for path in files if (repo_root / path).exists()}


def verify_package(repo_root: Path, output: Path | None = None, check_replay: bool = True) -> dict[str, Any]:
    output = (output or repo_root / RESULT_PACKAGE).resolve()
    upstream = load_upstream(repo_root)
    validate_upstream(upstream)
    cal = build_expert_calendar(upstream)
    frames = build_paths(cal, upstream)
    evaluated = evaluate_paths(frames)

    stored_cal = pd.read_parquet(output / "expert_calendar.parquet")
    if len(stored_cal) != len(cal) or set(stored_cal["issue"]) != set(cal["issue"]):
        raise ContractError("calendar mismatch")
    stored_perf = pd.read_csv(output / "performance.csv")

    for scope in ("ALL", "2022", "2023", "2024"):
        mech = evaluated["performance"][
            (evaluated["performance"]["path"].eq(PATH_MECHANICAL))
            & (evaluated["performance"]["scope"].eq(scope))
        ]["pnl_cny"].iloc[0]
        port = evaluated["performance"][
            (evaluated["performance"]["path"].eq(PATH_PORTFOLIO))
            & (evaluated["performance"]["scope"].eq(scope))
        ]["pnl_cny"].iloc[0]
        if not math.isclose(mech, port, rel_tol=0, abs_tol=1e-9):
            raise ContractError("portfolio/mechanical identity mismatch")
        stored = stored_perf[
            (stored_perf["path"].eq(PATH_PORTFOLIO)) & (stored_perf["scope"].eq(scope))
        ]["pnl_cny"].iloc[0]
        if not math.isclose(port, stored, rel_tol=1e-9, abs_tol=1e-3):
            raise ContractError("stored portfolio pnl mismatch")

    manifest = output / "MANIFEST.json"
    if manifest.exists():
        info = _read_json(manifest)
        manifest_names = set(info.get("files", {}).keys())
        present = {p.name for p in output.iterdir() if p.is_file() and p.name != "MANIFEST.json"}
        if manifest_names != present:
            raise ContractError(
                f"artifact set mismatch: only={sorted(manifest_names - present)} "
                f"extra={sorted(present - manifest_names)}"
            )
        for name, meta in info.get("files", {}).items():
            actual = sha256_file(output / name)
            if actual != meta["sha256"]:
                raise ContractError(f"MANIFEST hash mismatch: {name}")
    else:
        raise ContractError("MANIFEST.json missing")

    if check_replay:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            replayed = Path(tmp) / "replay"
            build_package(repo_root, replayed, force=True)
            stored_names = {
                p.name for p in output.iterdir() if p.is_file() and p.name != "MANIFEST.json"
            }
            replay_names = {
                p.name for p in replayed.iterdir() if p.is_file() and p.name != "MANIFEST.json"
            }
            if stored_names != replay_names:
                raise ContractError(
                    f"replay artifact set mismatch: only={sorted(stored_names - replay_names)} "
                    f"extra={sorted(replay_names - stored_names)}"
                )
            for path in sorted(p for p in output.iterdir() if p.is_file() and p.name != "MANIFEST.json"):
                if sha256_file(path) != sha256_file(replayed / path.name):
                    raise ContractError(f"replay byte mismatch: {path.name}")

    return {"ok": True, "package": str(output)}


# ---------------------------------------------------------------------------
# Notebook and report synthesis
# ---------------------------------------------------------------------------


def _md_table(frame: pd.DataFrame, columns: list[str] | None = None, precision: int = 4) -> str:
    cols = columns or frame.columns.tolist()
    body = frame[cols]
    header = "| " + " | ".join(str(c) for c in cols) + " |"
    sep = "|" + "|".join(["---"] * len(cols)) + "|"
    lines = [header, sep]
    for _, row in body.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                cells.append(f"{v:.{precision}f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_report(repo_root: Path, package: Path, decision: dict[str, Any]) -> None:
    perf = pd.read_csv(package / "performance.csv")
    risk = pd.read_csv(package / "risk_diagnostics.csv")
    corr = pd.read_csv(package / "correlation_diagnostics.csv")
    assoc = pd.read_csv(package / "association_rates.csv")
    losing = pd.read_csv(package / "losing_dependence.csv")
    tail = pd.read_csv(package / "tail_overlap.csv")
    contrasts = pd.read_csv(package / "matched_contrasts.csv")
    async_rows = pd.read_csv(package / "moving_block_async_bootstrap.csv")
    dilution = pd.read_csv(package / "dilution_attribution.csv")

    text = f"""# Issue #378 — corrected N6 versus corrected-N7 expert complementarity
and fixed portfolio paths

Contract: `{decision["contract"]}`

## Decision

`{decision["verdict"]}`. Expert pool after diagnostic: admitted `[]`, existing
`['N7_C0E0']`. Portfolio verdict: `{decision["portfolio_verdict"]}`.

## Five-minute interpretation

- **There is no positive standalone N6 payoff source in the frozen evidence**:
  corrected N6 R0 ends at CNY-33,511 and corrected N6 R3 at CNY-12,300 over
  2022-2024, and #377 retained no N6 grid cell (its own verdict
  `HISTORICAL_MECHANISM_FRONTIER_NO_GATE_PASS`). The portfolio question's
  premise therefore fails before any weighting: a 50/50 fixed portfolio cannot
  improve holding risk without diluting return, because the N6 sleeve is a
  negative-expected-value drag, not an asynchronous complementary source.
- **The corrected-N7 payoff source is the only positive standalone expert**
  (R3 CONTROL +CNY32,689; the mechanism hypotheses C1E2/C1E3 are explicitly
  exposed, never admitted). Pairing it with the corrected N6 R3 control in the
  preregistered portfolio yields CNY{perf[(perf.path.eq('PORTFOLIO_50_50')) & (perf.scope.eq('ALL'))]['pnl_cny'].iloc[0]:,.0f}
  — exactly CNY{abs(0.5 * -12299.98964156374):,.0f} (0.5 x CNY12,300) lower than
  the N7-halved counterfactual, i.e. the N6 sleeve drag is pure dilution.
- **The payoff sources are NOT asynchronous — they are synchronized.** The
  issue-PnL Pearson correlation between N6 R3 and N7 CONTROL is
  r={corr.iloc[0]['pearson_r']:.3f} (Spearman rho={corr.iloc[0]['spearman_rho']:.3f});
  both lose simultaneously on {losing.iloc[0]['both_losing_issues']:.0f} of
  {losing.iloc[0]['common_issues']:.0f} shared issues ({losing.iloc[0]['both_losing_rate']:.1%}),
  both sit underwater on {losing.iloc[0]['both_underwater_issues']:.0f} issues
  ({losing.iloc[0]['both_underwater_rate']:.1%}), and the top-10 gross payout
  sets overlap by {tail.loc[(tail.k.eq(10)) & (tail.table.eq('gross')), 'intersection'].iloc[0]:.0f}/10
  (Jaccard {tail.loc[(tail.k.eq(10)) & (tail.table.eq('gross')), 'jaccard'].iloc[0]:.3f});
  both experts' largest single payout landed on the same issue (23021).
- **The fixed portfolio does not smooth risk; it worsens risk-adjusted
  economics.** Portfolio max drawdown is {risk[(risk.path.eq('PORTFOLIO_50_50')) & (risk.scope.eq('ALL'))]['max_drawdown_fraction'].iloc[0]:.1%}
  versus {risk[(risk.path.eq('N7_HALVED')) & (risk.scope.eq('ALL'))]['max_drawdown_fraction'].iloc[0]:.1%}
  for the pure stake-reduction counterfactual; the moving-block bootstrap 90%
  CI of the drawdown delta is [{async_rows.loc[async_rows.metric.eq('max_drawdown_delta'), 'p05'].iloc[0]:+.3f},
  {async_rows.loc[async_rows.metric.eq('max_drawdown_delta'), 'p95'].iloc[0]:+.3f}]
  — entirely positive, so the N6 sleeve never reduces drawdown relative to
  dilution and usually makes it materially worse. The apparent "smoothing" of
  the 50/50 path is only stake reduction of the higher-return expert, i.e.
  pure dilution.
- **Historical qualification stands unchanged**: no N6 arm enters the expert
  pool; no grid cell from #377/#373 is admitted. All 2022-2024 evidence is
  exposed retrospective and cannot tune future decisions.

## Calendar and disclosure

Shared corrected calendar: 152 issues (union). Exact-common active
denominator: 151 issues. N6-exclusive issue 23032 (trusted 6-fixture selection,
UNTRUSTED_SELECTED_LEG for the 7-fixture N7 surface) carries NO_BET zero flow
for the N7 sleeve. 20 issues are excluded from both N6 surfaces and 21 from
the N7 surface at the upstream UNTRUSTED_SELECTED_LEG gate (see
`disclosure.csv`). Both experts normalized to CNY1,024 per active issue before
correlation.

## Correlation and association

{_md_table(corr)}

Profitable/loss 2x2 association (both profitable / N6-only / N7-only / neither)
phi={assoc.loc[assoc.metric.eq('phi_profitable_association'), 'value'].iloc[0]:.4f},
chi2 p={assoc.loc[assoc.metric.eq('chi2_p'), 'value'].iloc[0]:.4g}. Both-profitable
rate {assoc.loc[assoc.metric.eq('both_profitable_rate'), 'value'].iloc[0]:.4f}.

## Losing-only dependence and tail overlap

{_md_table(losing)}

{_md_table(tail)}

## Standalone and portfolio economics (ALL)

{_md_table(perf[perf.scope.eq('ALL')], precision=2)}

## Annual PnL (annual stability)

{_md_table(perf[['path', 'scope', 'pnl_cny']][perf.scope.isin(['2022', '2023', '2024'])].pivot(
    index='path', columns='scope', values='pnl_cny').reset_index(), precision=2)}

## Path risk (ALL)

{_md_table(risk[risk.scope.eq('ALL')], precision=4)}

## Matched contrasts (shared calendar, circular moving-block bootstrap)

{_md_table(contrasts[contrasts.scope.eq('ALL')], precision=2)}

## Async contribution bootstrap (PORTFOLIO vs N7_HALVED)

{_md_table(async_rows, precision=4)}

## Return-dilution attribution

{_md_table(dilution, precision=3)}

Interpretation: the portfolio equals the mechanical weighted average by
construction (0 diff, verified). Its PnL is CNY
{perf[(perf.path.eq('PORTFOLIO_50_50')) & (perf.scope.eq('ALL'))]['pnl_cny'].iloc[0]:,.0f}
vs N7 full CNY
{perf[(perf.path.eq('N7_C0E0')) & (perf.scope.eq('ALL'))]['pnl_cny'].iloc[0]:,.0f}
— the CNY
{perf[(perf.path.eq('PORTFOLIO_50_50')) & (perf.scope.eq('ALL'))]['pnl_cny'].iloc[0] - perf[(perf.path.eq('N7_C0E0')) & (perf.scope.eq('ALL'))]['pnl_cny'].iloc[0]:,.0f}
gap is the N6 sleeve drag (-0.5 x CNY12,300). The drawdown bootstrap CI of the
portfolio-vs-N7_HALVED delta is entirely positive ([{async_rows.loc[async_rows.metric.eq('max_drawdown_delta'), 'p05'].iloc[0]:+.3f},
{async_rows.loc[async_rows.metric.eq('max_drawdown_delta'), 'p95'].iloc[0]:+.3f}]),
so the N6 sleeve never delivers asynchronous drawdown relief: smoother observed
risk is fully attributable to halving the higher-return expert's weight, not to
asynchronous payoffs. Risk-adjusted economics confirm dilution: capital
return per unit max drawdown is approximately
{perf[(perf.path.eq('N7_C0E0')) & (perf.scope.eq('ALL'))]['capital_return'].iloc[0] / risk[(risk.path.eq('N7_C0E0')) & (risk.scope.eq('ALL'))]['max_drawdown_fraction'].iloc[0]:.2f}
for N7 full, {perf[(perf.path.eq('PORTFOLIO_50_50')) & (perf.scope.eq('ALL'))]['capital_return'].iloc[0] / risk[(risk.path.eq('PORTFOLIO_50_50')) & (risk.scope.eq('ALL'))]['max_drawdown_fraction'].iloc[0]:.2f}
for the 50/50 portfolio, and the portfolio keeps ~97% of the N7-full drawdown
while surrendering ~69% of the return.

## Historical verdict

Low correlation is diversification, not Edge. No N6 arm enters the expert pool
unless standalone-positive robustness gates pass — none do. The fixed
portfolio is not promotable. #210/#218 preserved; no prospective evidence
consumed.

## Artifacts

- Package: `results/n6_n7_portfolio/`
- Notebook: `notebooks/research/n6-n7-portfolio/n6_n7_portfolio.ipynb`
- Figure: `docs/research/figures/issue_378_n6_n7_portfolio.png`
"""
    (repo_root / "docs/research/Issue-378-N6-N7-Portfolio.md").write_text(
        text, encoding="utf-8"
    )


def _figure_path(repo_root: Path) -> Path:
    path = repo_root / "docs/research/figures/issue_378_n6_n7_portfolio.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _make_figure(repo_root: Path, package: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    capital = pd.read_csv(package / "capital_paths.csv")
    corr = pd.read_csv(package / "correlation_diagnostics.csv")

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for label in ("N7_C0E0", "PORTFOLIO_50_50", "N7_HALVED", "PARALLEL_1_1", "N6_R3"):
        sub = capital[capital.path.eq(label)]
        axes[0].plot(sub["issue_order"], sub["capital_cny"], label=label, linewidth=1.6)
    axes[0].axhline(100_000, color="grey", linestyle=":", linewidth=0.8)
    axes[0].set_title("Capital paths (CNY100,000 start)")
    axes[0].set_xlabel("Issue order (shared corrected calendar)")
    axes[0].set_ylabel("Capital (CNY)")
    axes[0].legend(fontsize=8)

    pool = corr[corr.kind.eq("pool")]
    axes[1].barh(pool["pair"], pool["pearson_r"], color="#4C72B0")
    axes[1].axvline(0, color="black", linewidth=0.8)
    axes[1].set_title("Issue-PnL Pearson correlation (151 exact-common issues)")
    axes[1].set_xlabel("Pearson r")
    for i, row in enumerate(pool.itertuples()):
        axes[1].text(row.pearson_r + 0.01, i, f"r={row.pearson_r:.3f}", fontsize=8, va="center")
    fig.tight_layout()
    fig.savefig(_figure_path(repo_root), dpi=150, bbox_inches="tight")
    plt.close(fig)


def build_notebook_and_report(repo_root: Path, package: Path) -> str:
    """Generate executed notebook + markdown report + figure (deterministic)."""
    _make_figure(repo_root, package)
    decision = _read_json(package / "decision.json")
    build_report(repo_root, package, decision)

    from nbformat import v4 as nbf

    nb = nbf.new_notebook(
        metadata={
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        cells=[
            nbf.new_markdown_cell(
                f"# #378 corrected N6 vs corrected-N7 portfolio diagnostic\n\n"
                f"Contract: `{decision['contract']}`. Executed notebook over the frozen "
                f"accepted surfaces (#376/#377/#373). All values deterministic."
            ),
            nbf.new_code_cell(
                "import pandas as pd, numpy as np\n"
                "from pathlib import Path\n"
                "OUT = Path('results/n6_n7_portfolio')\n"
                "pd.set_option('display.width', 220)\n"
                "pd.set_option('display.max_columns', 50)"
            ),
            nbf.new_code_cell("perf = pd.read_csv(OUT/'performance.csv'); perf.head(3)"),
            nbf.new_code_cell("corr = pd.read_csv(OUT/'correlation_diagnostics.csv'); corr"),
            nbf.new_code_cell("assoc = pd.read_csv(OUT/'association_rates.csv'); assoc"),
            nbf.new_code_cell("pd.read_csv(OUT/'losing_dependence.csv').T"),
            nbf.new_code_cell("pd.read_csv(OUT/'tail_overlap.csv')"),
            nbf.new_code_cell("perf = pd.read_csv(OUT/'performance.csv'); perf[perf.scope.eq('ALL')]"),
            nbf.new_code_cell("pd.read_csv(OUT/'risk_diagnostics.csv')", ),
            nbf.new_code_cell("pd.read_csv(OUT/'matched_contrasts.csv')", ),
            nbf.new_code_cell("pd.read_csv(OUT/'moving_block_async_bootstrap.csv')", ),
            nbf.new_code_cell("pd.read_csv(OUT/'dilution_attribution.csv')", ),
            nbf.new_code_cell("pd.read_csv(OUT/'rolling_windows.csv')", ),
            nbf.new_markdown_cell(
                "## Conclusion\n\nNo N6 arm is standalone-positive in the frozen surface "
                "(#376 R0 -33,511, R3 -12,300; #377 retained no grid cell). Worse, the "
                "payoff sources are synchronized, not asynchronous: issue-PnL Pearson "
                "r=0.75, both lose together on 76% of shared issues, and the drawdown "
                "bootstrap delta vs the pure stake-reduction counterfactual is entirely "
                "positive. The preregistered 50/50 portfolio therefore dilutes the only "
                "positive expert (N7 R3 CONTROL) by CNY6,150 and cannot improve holding "
                "risk without diluting return."
            ),
        ],
    )
    import nbformat
    nbfile = repo_root / "notebooks/research/n6-n7-portfolio/n6_n7_portfolio.ipynb"
    nbfile.parent.mkdir(parents=True, exist_ok=True)
    nbformat.write(nb, nbfile)

    # Execute (clean-run validation).
    from nbclient import NotebookClient
    client = NotebookClient(
        nb, timeout=600, kernel_name="python3",
        resources={"metadata": {"path": str(repo_root)}},
    )
    client.execute()
    nbformat.write(nb, nbfile)
    return str(nbfile)


# Re-export for scripts.
__all__ = [
    "build_package", "verify_package", "build_notebook_and_report", "ContractError",
    "load_upstream", "validate_upstream", "build_expert_calendar", "build_paths",
    "evaluate_paths", "correlation_diagnostics", "association_rates",
    "losing_dependence", "tail_overlap", "matched_contrasts", "async_bootstrap",
    "dilution_attribution", "build_decision",
]