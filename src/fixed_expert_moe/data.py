"""Causal source assembly and frozen expert counterfactual surfaces."""

from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
import sqlite3

import numpy as np
import pandas as pd

from issue314.data import issue_features, load_pre_event_units, load_settlement
from issue314.experts import EXPERTS, generate_tickets, settle_tickets

from .contract import (
    CURRENT_COLUMNS,
    EXPERT_LAG_METRICS,
    EXPERT_LAG_WINDOWS,
    EXPERT_NAMES,
    STATE_LAG_COLUMNS,
)


def load_sources(repo_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load frozen pre-event units, exact settlement and the #330 state ledger."""

    units = load_pre_event_units((2020, 2021, 2022, 2023, 2024))
    settlement = load_settlement(set(units["issue"].astype(str)))
    state = pd.read_parquet(repo_root / "results/regime_state/state_ledger.parquet")
    state["issue"] = state["issue_code"].astype(str)
    state["issue_anchor_ts"] = pd.to_datetime(state["issue_anchor_ts"], utc=True)
    availability = _load_conservative_availability(repo_root)
    state = state.merge(availability, on="issue", how="left", validate="one_to_one")
    state = _rebuild_global_lag(state)
    return units, settlement, state


def build_counterfactual_surface(
    units: pd.DataFrame,
    settlement: pd.DataFrame,
    *,
    seeds: tuple[int, ...],
    counts: tuple[int, ...],
) -> pd.DataFrame:
    """Settle every fixed expert on every issue/seed at requested prefix counts."""

    rows: list[dict[str, object]] = []
    maximum = max(counts)
    for issue, group in units.groupby("issue", sort=True):
        local = settlement[settlement["issue"].eq(str(issue))]
        year = int(group["issue_year"].iloc[0])
        for spec in EXPERTS:
            if len(group) < spec.n:
                continue
            descriptor = asdict(spec)
            for seed in seeds:
                matches, outcomes, _, receipt = generate_tickets(
                    group, spec, k=maximum, seed=seed
                )
                gross, _, miss = settle_tickets(matches, outcomes, group, local)
                gross_cumulative = np.cumsum(gross)
                for count in counts:
                    local_miss = miss[:count]
                    local_gross = float(gross_cumulative[count - 1])
                    stake = 2.0 * count
                    rows.append(
                        {
                            "issue": str(issue),
                            "issue_year": year,
                            "seed": int(seed),
                            "expert": spec.name,
                            "k": int(count),
                            "stake_cny": stake,
                            "gross_cny": local_gross,
                            "pnl_cny": local_gross - stake,
                            "hit_count": int((local_miss == 0).sum()),
                            "miss_one_count": int((local_miss == 1).sum()),
                            "miss_two_count": int((local_miss == 2).sum()),
                            "natural_support": int(receipt["natural_support"]),
                            **descriptor,
                        }
                    )
    result = pd.DataFrame(rows)
    expected = set(EXPERT_NAMES)
    observed = set(result["expert"].unique())
    if observed != expected:
        raise AssertionError(f"expert surface mismatch: {observed ^ expected}")
    return result.sort_values(["issue_year", "issue", "expert", "seed", "k"])


def aggregate_model_labels(surface: pd.DataFrame) -> pd.DataFrame:
    """Aggregate K=512 nuisance seeds into dense issue × expert labels."""

    frame = surface[surface["k"].eq(512)].copy()
    keys = [
        "issue",
        "issue_year",
        "expert",
        "sleeve",
        "n",
        "selector",
        "outcome_direction",
        "generator",
        "pool_excess",
        "protection",
        "protected_leg_count",
    ]
    labels = frame.groupby(keys, as_index=False).agg(
        stake_cny=("stake_cny", "first"),
        mean_gross_cny=("gross_cny", "mean"),
        mean_pnl_cny=("pnl_cny", "mean"),
        pnl_std_cny=("pnl_cny", "std"),
        hit_count=("hit_count", "sum"),
        miss_one_count=("miss_one_count", "sum"),
        miss_two_count=("miss_two_count", "sum"),
        positive_seed_fraction=("pnl_cny", lambda x: float((x > 0).mean())),
        nuisance_seeds=("seed", "nunique"),
    )
    denominator = labels["nuisance_seeds"] * 512.0
    labels["hit_rate"] = labels["hit_count"] / denominator
    labels["within_one_rate"] = (
        labels["hit_count"] + labels["miss_one_count"]
    ) / denominator
    labels["within_two_rate"] = (
        labels["hit_count"] + labels["miss_one_count"] + labels["miss_two_count"]
    ) / denominator
    labels["roi"] = labels["mean_pnl_cny"] / labels["stake_cny"]
    labels["clipped_roi"] = labels["roi"].clip(-1.0, 4.0)
    return labels


def assemble_learning_panel(
    units: pd.DataFrame,
    labels: pd.DataFrame,
    state: pd.DataFrame,
) -> pd.DataFrame:
    """Join current issue features, strict global lag state and expert history."""

    current = issue_features(units)
    current["issue"] = current["issue"].astype(str)
    global_columns = [
        "issue",
        "issue_anchor_ts",
        "global_lag_last_available_ts",
        *STATE_LAG_COLUMNS,
    ]
    missing = sorted(set(global_columns) - set(state.columns))
    if missing:
        raise AssertionError(f"#330 state columns missing: {missing}")
    panel = labels.merge(
        current[["issue", *CURRENT_COLUMNS]], on="issue", validate="many_to_one"
    ).merge(
        state[[*global_columns, "outcome_available_ts"]],
        on="issue",
        validate="many_to_one",
    )
    panel = _add_descriptors(panel)
    panel = _add_expert_lag(panel)
    panel = panel.sort_values(["issue_anchor_ts", "issue", "expert"]).reset_index(
        drop=True
    )
    if panel.duplicated(["issue", "expert"]).any():
        raise AssertionError("learning panel key is not unique")
    if panel.groupby("issue")["expert"].nunique().min() != len(EXPERT_NAMES):
        raise AssertionError("not every issue has the complete fixed expert library")
    return panel


def _add_descriptors(panel: pd.DataFrame) -> pd.DataFrame:
    frame = panel.copy()
    frame["expert_n"] = frame["n"].astype(float)
    frame["expert_pool_excess"] = frame["pool_excess"].astype(float)
    frame["expert_protected_leg_count"] = frame["protected_leg_count"].astype(float)
    frame["expert_is_tail"] = frame["sleeve"].eq("TAIL").astype(float)
    frame["expert_is_wr"] = frame["generator"].eq("WR").astype(float)
    for value in ("GLOBAL", "VALUE", "DIVERGENCE", "HYBRID"):
        frame[f"expert_selector_{value.lower()}"] = frame["selector"].eq(value).astype(float)
    for value in ("MARKET", "VALUE", "DIVERGENCE"):
        frame[f"expert_direction_{value.lower()}"] = (
            frame["outcome_direction"].eq(value).astype(float)
        )
    return frame


def _add_expert_lag(panel: pd.DataFrame) -> pd.DataFrame:
    """Add expert feedback from strictly earlier anchor groups."""

    frame = panel.copy()
    frame["issue_anchor_ts"] = pd.to_datetime(frame["issue_anchor_ts"], utc=True)
    lag_columns: list[str] = []
    for metric in EXPERT_LAG_METRICS:
        for window in EXPERT_LAG_WINDOWS:
            lag_columns.extend(
                [
                    f"expert_lag_{metric}_roll{window}_mean",
                    f"expert_lag_{metric}_roll{window}_std",
                    f"expert_lag_{metric}_roll{window}_count",
                ]
            )
    for column in lag_columns:
        frame[column] = np.nan
    frame["expert_lag_last_available_ts"] = pd.Series(
        pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]"
    )

    for expert, expert_rows in frame.groupby("expert", sort=False):
        for anchor, block in expert_rows.groupby("issue_anchor_ts", sort=True):
            indices = block.index
            history = expert_rows[
                expert_rows["outcome_available_ts"].notna()
                & expert_rows["outcome_available_ts"].lt(anchor)
            ]
            if len(history):
                frame.loc[indices, "expert_lag_last_available_ts"] = history[
                    "outcome_available_ts"
                ].max()
            for metric in EXPERT_LAG_METRICS:
                for window in EXPERT_LAG_WINDOWS:
                    values = pd.to_numeric(history[metric], errors="coerce").dropna().tail(window)
                    frame.loc[indices, f"expert_lag_{metric}_roll{window}_mean"] = (
                        float(values.mean()) if len(values) else np.nan
                    )
                    frame.loc[indices, f"expert_lag_{metric}_roll{window}_std"] = (
                        float(values.std(ddof=0)) if len(values) else np.nan
                    )
                    frame.loc[indices, f"expert_lag_{metric}_roll{window}_count"] = len(values)
    return frame


def expert_lag_columns(panel: pd.DataFrame) -> tuple[str, ...]:
    return tuple(
        column
        for column in panel
        if column.startswith("expert_lag_") and not column.endswith("_ts")
    )


def assert_strict_chronology(panel: pd.DataFrame) -> None:
    """Verify equal-anchor state parity and absence of prohibited feature names."""

    forbidden = {"year", "issue_code", "same_outcome", "terminal_sp", "winning_sp"}
    feature_candidates = [
        *CURRENT_COLUMNS,
        *STATE_LAG_COLUMNS,
        *expert_lag_columns(panel),
    ]
    if any(name in forbidden or name.startswith("issue_") for name in feature_candidates):
        raise AssertionError("prohibited feature entered model interface")
    lag_cols = [*STATE_LAG_COLUMNS, *expert_lag_columns(panel)]
    for timestamp_column in (
        "global_lag_last_available_ts",
        "expert_lag_last_available_ts",
    ):
        valid = panel[timestamp_column].notna()
        if not panel.loc[valid, timestamp_column].lt(
            panel.loc[valid, "issue_anchor_ts"]
        ).all():
            raise AssertionError(f"non-causal lag timestamp: {timestamp_column}")
    for (_, expert), group in panel.groupby(["issue_anchor_ts", "expert"]):
        if len(group) > 1 and not group[lag_cols].nunique(dropna=False).le(1).all():
            raise AssertionError("equal-anchor issues do not share lag state")


def _load_conservative_availability(repo_root: Path) -> pd.DataFrame:
    """Approximate outcome availability as latest issue kickoff plus four hours."""

    runtime = Path(os.environ.get("BEIJING_LOT_RUNTIME_ROOT", repo_root)).resolve()
    database = runtime / "data/derived/beidan_xlsm/beidan_xlsm.sqlite"
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        frame = pd.read_sql_query(
            "SELECT CAST(issue AS TEXT) AS issue, kickoff_ts FROM match_features",
            connection,
        )
    frame["kickoff_ts"] = pd.to_datetime(frame["kickoff_ts"], errors="coerce", utc=True)
    availability = frame.groupby("issue", as_index=False).agg(
        latest_fixture_kickoff_ts=("kickoff_ts", "max")
    )
    availability["outcome_available_ts"] = (
        availability["latest_fixture_kickoff_ts"] + pd.Timedelta(hours=4)
    )
    return availability[["issue", "outcome_available_ts"]]


def _rebuild_global_lag(state: pd.DataFrame) -> pd.DataFrame:
    """Replace #330 anchor-surrogate lags with conservative availability lags."""

    frame = state.copy()
    for column in STATE_LAG_COLUMNS:
        frame[column] = np.nan
    frame["global_lag_last_available_ts"] = pd.Series(
        pd.NaT, index=frame.index, dtype="datetime64[ns, UTC]"
    )
    for anchor, block in frame.groupby("issue_anchor_ts", sort=True):
        history = frame[
            frame["outcome_available_ts"].notna()
            & frame["outcome_available_ts"].lt(anchor)
        ].sort_values(["outcome_available_ts", "issue"])
        if len(history):
            frame.loc[block.index, "global_lag_last_available_ts"] = history[
                "outcome_available_ts"
            ].max()
        for metric in ("eu_brier", "line_brier", "eu_top2_residual", "line_top2_residual"):
            values = pd.to_numeric(history[metric], errors="coerce").dropna()
            for window in (5, 20):
                local = values.tail(window)
                frame.loc[block.index, f"lag_{metric}_roll{window}_mean"] = (
                    float(local.mean()) if len(local) else np.nan
                )
                frame.loc[block.index, f"lag_{metric}_roll{window}_std"] = (
                    float(local.std(ddof=0)) if len(local) else np.nan
                )
                frame.loc[block.index, f"lag_{metric}_roll{window}_count"] = len(local)
            frame.loc[block.index, f"lag_{metric}_ewm5"] = (
                float(values.ewm(span=5, adjust=False).mean().iloc[-1])
                if len(values)
                else np.nan
            )
            frame.loc[block.index, f"lag_{metric}_ewm20"] = (
                float(values.ewm(span=20, adjust=False).mean().iloc[-1])
                if len(values)
                else np.nan
            )
    return frame
