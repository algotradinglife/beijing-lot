"""Issue #232 — issue-level modelability (REQ-S08, contract item 6).

Reports complete matched issue counts per chronological cohort:

- fit (label year <= 2021), tune (2022), calibration (2023);
- the distribution of complete matches per issue (min/median/max, and the
  fraction of issues with >= N complete matches for every feasible N);
- support for each modelability interface (Q_BJ x SP, Q_BJ x EU x SP,
  Q_BJ x POWER x SP) at issue level, not only cell level.

Everything is computed from committed upstream packages; no conclusion is
asserted from raw presence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import contract
from .recovery import build_sp_recovery
from .waterfall import _load_anchor_axis, _load_identity, _load_match_meta
from .waterfall import _eu_from_bj203, _power_from_bj180


@dataclass
class Modelability:
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    summary: pd.DataFrame = field(default_factory=pd.DataFrame)


def _cohort_of_year(year: int | None) -> str:
    if year is None:
        return contract.COHORT_LATER
    return contract.COHORT_BY_LABEL_YEAR.get(int(year), contract.COHORT_LATER)


def _complete_match_support_per_n(
    complete_matches: pd.DataFrame,
) -> pd.DataFrame:
    """Distribution of complete matches per issue and fraction with >= N."""
    if complete_matches.empty:
        return pd.DataFrame(
            [{"n": 1, "issues_with_ge_n": 0, "fraction_of_issues": 0.0}]
        )
    per_issue = (
        complete_matches.groupby(["issue", "cohort"], as_index=False)
        .size()
        .rename(columns={"size": "complete_matches"})
    )
    issues_total = per_issue["issue"].nunique()
    max_n = int(per_issue["complete_matches"].max()) if len(per_issue) else 1
    rows = []
    for n in range(1, max_n + 1):
        count = int((per_issue["complete_matches"] >= n).sum())
        rows.append(
            {
                "n": n,
                "issues_with_ge_n": count,
                "fraction_of_issues": round(count / issues_total, 6) if issues_total else 0.0,
            }
        )
    return pd.DataFrame(rows)


def build_modelability(root: Path, observations: pd.DataFrame) -> Modelability:
    """Compute issue-level modelability across cohorts and interfaces."""
    identity = _load_identity(root)
    anchor = _load_anchor_axis(root)
    meta = _load_match_meta(root)

    year_map = identity[["issue", "year"]].drop_duplicates()
    year_map["issue"] = year_map["issue"].astype(str)
    year_map["cohort"] = year_map["year"].map(_cohort_of_year)

    # ---- interface support: SP recovery (causal triplets per issue) ----
    sp = build_sp_recovery(root, observations)
    sp_triplets = sp.sp_triplets
    sp_issue_support = pd.DataFrame(
        columns=["sp_issue", "sp_causal_matches", "sp_causal_cells"]
    )
    if len(sp_triplets):
        sp_issue_support = (
            sp_triplets.groupby(["issue"], as_index=False)
            .agg(
                sp_causal_matches=("match_idx", "nunique"),
                sp_causal_cells=("Q_BJ_SP_DEVIG_3", "size"),
            )
            .rename(columns={"issue": "sp_issue"})
        )

    # ---- EU support (causal de-vig cells per issue) ----
    eu = _eu_from_bj203(root)
    meta_eu = _load_identity(root)[
        ["issue", "match_idx", "euro_1h_available_ts_utc"]
    ].drop_duplicates()
    eu = eu.merge(meta_eu, on=["issue", "match_idx"], how="left", validate="many_to_one")
    eu = eu.merge(
        meta[["issue", "match_idx", "feature_cutoff_ts_utc"]],
        on=["issue", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    cutoff = pd.to_datetime(eu["feature_cutoff_ts_utc"], errors="coerce", utc=True)
    eu_observed = pd.to_datetime(
        eu["euro_1h_available_ts_utc"], errors="coerce", utc=True
    )
    eu_causal = eu[eu_observed.notna() & cutoff.notna() & eu_observed.le(cutoff)]
    eu_issue_support = pd.DataFrame(
        columns=["eu_issue", "eu_causal_matches", "eu_causal_cells"]
    )
    if len(eu_causal):
        eu_issue_support = (
            eu_causal.groupby(["issue"], as_index=False)
            .agg(
                eu_causal_matches=("match_idx", "nunique"),
                eu_causal_cells=("devig_euro_probability", "size"),
            )
            .rename(columns={"issue": "eu_issue"})
        )

    # ---- POWER support (#180 causal matches per issue) ----
    power = _power_from_bj180(root)
    power = power.merge(
        meta[["issue", "match_idx", "feature_cutoff_ts_utc"]],
        on=["issue", "match_idx"],
        how="left",
        validate="many_to_one",
    )
    cutoff = pd.to_datetime(power["feature_cutoff_ts_utc"], errors="coerce", utc=True)
    # #180 timestamps are naive Beijing time (+08:00 per #229 verified binding).
    power_ts_raw = pd.to_datetime(power.get("feature_cutoff_ts"), errors="coerce")
    power_ts = power_ts_raw.dt.tz_localize("Asia/Shanghai").dt.tz_convert("UTC")
    power_causal = power[
        power_ts.notna() & cutoff.notna() & power_ts.le(cutoff)
    ]
    power_issue_support = pd.DataFrame(
        columns=["power_issue", "power_causal_matches", "power_causal_cells"]
    )
    if len(power_causal):
        power_issue_support = (
            power_causal.groupby(["issue"], as_index=False)
            .agg(
                power_causal_matches=("match_idx", "nunique"),
                power_causal_cells=("market_p3", "size"),
            )
            .rename(columns={"issue": "power_issue"})
        )

    # ---- issue registry with cohort and per-interface support ----
    issues = year_map[["issue", "year", "cohort"]].copy()
    issues = issues.merge(
        sp_issue_support, left_on="issue", right_on="sp_issue", how="left"
    )
    issues = issues.merge(
        eu_issue_support, left_on="issue", right_on="eu_issue", how="left"
    )
    issues = issues.merge(
        power_issue_support, left_on="issue", right_on="power_issue", how="left"
    )
    for column in [
        "sp_causal_matches",
        "sp_causal_cells",
        "eu_causal_matches",
        "eu_causal_cells",
        "power_causal_matches",
        "power_causal_cells",
    ]:
        issues[column] = issues[column].fillna(0).astype(int)
    issues = issues.drop(
        columns=[c for c in ["sp_issue", "eu_issue", "power_issue"] if c in issues]
    )

    # interface complete matches: Q_BJ x SP needs anchor causal + SP causal
    anchor_matches = anchor[anchor["qbj_causal_available"]][
        ["issue", "match_idx"]
    ].drop_duplicates()
    anchor_matches["issue"] = anchor_matches["issue"].astype(str)
    sp_matches = (
        sp_triplets[["issue", "match_idx"]].drop_duplicates()
        if len(sp_triplets)
        else pd.DataFrame(columns=["issue", "match_idx"])
    )
    sp_matches["issue"] = sp_matches["issue"].astype(str)
    qbj_sp = anchor_matches.merge(sp_matches, on=["issue", "match_idx"], how="inner")
    qbj_sp["cohort"] = qbj_sp["issue"].map(
        dict(zip(year_map["issue"], year_map["cohort"]))
    )
    qbj_sp_complete = qbj_sp

    eu_matches = (
        eu_causal[["issue", "match_idx"]].drop_duplicates()
        if len(eu_causal)
        else pd.DataFrame(columns=["issue", "match_idx"])
    )
    eu_matches["issue"] = eu_matches["issue"].astype(str)
    qbj_eu_sp = qbj_sp.merge(eu_matches, on=["issue", "match_idx"], how="inner")

    power_matches = (
        power_causal[["issue", "match_idx"]].drop_duplicates()
        if len(power_causal)
        else pd.DataFrame(columns=["issue", "match_idx"])
    )
    power_matches["issue"] = power_matches["issue"].astype(str)
    qbj_power_sp = qbj_sp.merge(power_matches, on=["issue", "match_idx"], how="inner")

    def _cohort_summary(frame: pd.DataFrame, interface: str) -> dict:
        out = {}
        for cohort in (
            contract.COHORT_FIT,
            contract.COHORT_TUNE,
            contract.COHORT_CALIBRATION,
            contract.COHORT_LATER,
        ):
            sub = frame[frame["cohort"].eq(cohort)] if "cohort" in frame else frame.iloc[0:0]
            out[f"{cohort}_issues"] = int(sub["issue"].nunique()) if len(sub) else 0
            out[f"{cohort}_matches"] = int(len(sub)) if len(sub) else 0
        return out

    summary_rows = []
    for interface, frame in [
        ("Q_BJ_x_SP", qbj_sp_complete),
        ("Q_BJ_x_EU_x_SP", qbj_eu_sp),
        ("Q_BJ_x_POWER_x_SP", qbj_power_sp),
    ]:
        row = {"interface": interface}
        row.update(_cohort_summary(frame, interface))
        summary_rows.append(row)

    summary = pd.DataFrame(summary_rows)

    # per-N feasibility on the Q_BJ x SP interface (the primary modelability axis)
    n_support = _complete_match_support_per_n(
        qbj_sp_complete.rename(columns={"match_idx": "complete_matches"})
    ) if len(qbj_sp_complete) else pd.DataFrame(
        [{"n": 1, "issues_with_ge_n": 0, "fraction_of_issues": 0.0}]
    )

    model = Modelability()
    model.tables["issue_registry"] = issues
    model.tables["interface_summary"] = summary
    model.tables["n_support_qbj_sp"] = n_support
    model.tables["qbj_sp_complete_matches"] = qbj_sp_complete
    model.tables["qbj_eu_sp_complete_matches"] = qbj_eu_sp
    model.tables["qbj_power_sp_complete_matches"] = qbj_power_sp
    model.summary = summary
    return model
