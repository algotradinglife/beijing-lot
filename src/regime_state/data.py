"""Source-bound issue panel and strictly lagged state construction."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.dynamic_allocator.pipeline import _load_labels_exact

from .contract import HALF_LIVES, OUTCOMES, PRIMARY_HORIZON, TARGETS, WINDOWS, YEARS


def load_market_rows(data_root: Path) -> tuple[pd.DataFrame, Path]:
    path = data_root / "derived/bj238_divergence_materializer_v4r3/inference/relative_horizon_view.parquet"
    columns = [
        "issue_code", "issue_year", "issue_anchor_ts", "snapshot_kind",
        "canonical_fixture_key", "outcome_code", "mapping_accepted", "causal_grade",
        "temporal_role", "native_handicap_line", "n_available_books",
        "q_eu_bjline", "q_line_only_control", "eu_vs_line_divergence",
    ]
    frame = pd.read_parquet(
        path, columns=columns,
        filters=[("issue_year", "in", list(YEARS)), ("snapshot_kind", "==", PRIMARY_HORIZON)],
    )
    frame["issue_code"] = frame.issue_code.astype(str)
    frame["outcome_code"] = frame.outcome_code.astype(str)
    frame = frame[
        frame.mapping_accepted.fillna(False)
        & frame.q_eu_bjline.notna()
        & frame.q_line_only_control.notna()
        & frame.outcome_code.isin(OUTCOMES)
    ].copy()
    return frame, path


def fixture_panel(rows: pd.DataFrame, settlement_path: Path) -> pd.DataFrame:
    keys = ["issue_code", "issue_year", "issue_anchor_ts", "canonical_fixture_key"]
    valid = rows.groupby(keys, observed=True).outcome_code.nunique().eq(len(OUTCOMES))
    valid_index = valid[valid].index
    rows = rows.set_index(keys).loc[valid_index].reset_index()
    meta = rows.groupby(keys, as_index=False, observed=True).agg(
        native_handicap_line=("native_handicap_line", "first"),
        n_available_books=("n_available_books", "first"),
        causal_grade=("causal_grade", "first"),
        temporal_role=("temporal_role", "first"),
    )
    output = meta
    for prefix, value in (
        ("q", "q_eu_bjline"), ("line_q", "q_line_only_control"),
        ("div", "eu_vs_line_divergence"),
    ):
        wide = rows.pivot(index=keys, columns="outcome_code", values=value).reset_index()
        wide = wide.rename(columns={code: f"{prefix}{code}" for code in OUTCOMES})
        output = output.merge(wide, on=keys, validate="one_to_one")
    for prefix in ("q", "line_q"):
        matrix = output[[f"{prefix}{code}" for code in OUTCOMES]].to_numpy(float)
        total = matrix.sum(axis=1)
        if not np.allclose(total, 1.0, atol=1e-6):
            raise ValueError(f"{prefix} probabilities are not normalized")

    labels = _load_labels_exact(settlement_path, output.issue_code)
    output = output.merge(
        labels[[
            "issue_code", "canonical_fixture_key", "result_code", "winning_sp",
            "has_trusted_settlement", "settlement_quality",
        ]],
        on=["issue_code", "canonical_fixture_key"], how="left", validate="one_to_one",
    )
    trusted = (
        output.has_trusted_settlement.fillna(0).eq(1)
        & output.result_code.astype(str).isin(OUTCOMES)
        & pd.to_numeric(output.winning_sp, errors="coerce").gt(0)
    )
    output["trusted_target"] = trusted

    for prefix in ("q", "line_q"):
        matrix = output[[f"{prefix}{code}" for code in OUTCOMES]].to_numpy(float)
        output[f"{prefix}_entropy"] = -(matrix * np.log(np.maximum(matrix, 1e-12))).sum(axis=1)
        output[f"{prefix}_concentration"] = np.square(matrix).sum(axis=1)
        sorted_probability = np.sort(matrix, axis=1)[:, ::-1]
        output[f"{prefix}_top1_mass"] = sorted_probability[:, 0]
        output[f"{prefix}_top2_mass"] = sorted_probability[:, :2].sum(axis=1)

        realized_index = np.array([
            OUTCOMES.index(str(code)) if str(code) in OUTCOMES else 0
            for code in output.result_code
        ])
        realized_probability = matrix[np.arange(len(output)), realized_index]
        one_hot = np.zeros_like(matrix)
        one_hot[np.arange(len(output)), realized_index] = 1.0
        output[f"{prefix}_brier"] = np.where(
            trusted, np.square(matrix - one_hot).sum(axis=1), np.nan
        )
        output[f"{prefix}_logloss"] = np.where(
            trusted, -np.log(np.maximum(realized_probability, 1e-12)), np.nan
        )
        order = np.argsort(-matrix, axis=1, kind="stable")
        rank = np.argmax(order == realized_index[:, None], axis=1) + 1
        output[f"{prefix}_realized_rank"] = np.where(trusted, rank, np.nan)
        output[f"{prefix}_top1_residual"] = np.where(
            trusted, (rank == 1).astype(float) - output[f"{prefix}_top1_mass"], np.nan
        )
        output[f"{prefix}_top2_residual"] = np.where(
            trusted, (rank <= 2).astype(float) - output[f"{prefix}_top2_mass"], np.nan
        )
    divergence = output[[f"div{code}" for code in OUTCOMES]].to_numpy(float)
    output["divergence_signed"] = divergence.mean(axis=1)
    output["divergence_abs"] = np.abs(divergence).mean(axis=1)
    output["divergence_abs_max"] = np.abs(divergence).max(axis=1)
    return output


def issue_market_panel(fixtures: pd.DataFrame) -> pd.DataFrame:
    grouped = fixtures.groupby(["issue_code", "issue_year", "issue_anchor_ts"], observed=True)
    output = grouped.agg(
        fixture_count=("canonical_fixture_key", "nunique"),
        trusted_fixture_count=("trusted_target", "sum"),
        eu_entropy_mean=("q_entropy", "mean"),
        eu_entropy_std=("q_entropy", "std"),
        line_entropy_mean=("line_q_entropy", "mean"),
        line_entropy_std=("line_q_entropy", "std"),
        eu_top1_mass_mean=("q_top1_mass", "mean"),
        eu_top2_mass_mean=("q_top2_mass", "mean"),
        line_top1_mass_mean=("line_q_top1_mass", "mean"),
        line_top2_mass_mean=("line_q_top2_mass", "mean"),
        eu_concentration_mean=("q_concentration", "mean"),
        line_concentration_mean=("line_q_concentration", "mean"),
        divergence_signed_mean=("divergence_signed", "mean"),
        divergence_abs_mean=("divergence_abs", "mean"),
        divergence_abs_p90=("divergence_abs_max", lambda values: float(values.quantile(0.9))),
        line_abs_mean=("native_handicap_line", lambda values: float(values.abs().mean())),
        books_mean=("n_available_books", "mean"),
        eu_brier=("q_brier", "mean"),
        line_brier=("line_q_brier", "mean"),
        eu_logloss=("q_logloss", "mean"),
        line_logloss=("line_q_logloss", "mean"),
        eu_top1_residual=("q_top1_residual", "mean"),
        eu_top2_residual=("q_top2_residual", "mean"),
        line_top1_residual=("line_q_top1_residual", "mean"),
        line_top2_residual=("line_q_top2_residual", "mean"),
    ).reset_index()
    output["trusted_fixture_fraction"] = output.trusted_fixture_count / output.fixture_count
    return output.sort_values(["issue_anchor_ts", "issue_code"], kind="stable").reset_index(drop=True)


def attach_expert_targets(repo_root: Path, issue_panel: pd.DataFrame) -> pd.DataFrame:
    oof = pd.read_parquet(repo_root / "results/dynamic_allocator/oof_static_settlement.parquet")
    evaluation = pd.read_parquet(repo_root / "results/dynamic_allocator/settlement.parquet")
    allocation = pd.concat([oof, evaluation], ignore_index=True)
    allocation = allocation[
        allocation.arm.isin(["L000", "L100"])
        & allocation.settlement_status.eq("SETTLED")
    ]
    surface = allocation.pivot(
        index=["issue_code", "issue_year"], columns="arm", values=["pnl", "hit", "gross"]
    )
    surface.columns = [f"{metric.lower()}_{arm.lower()}" for metric, arm in surface.columns]
    surface = surface.reset_index()
    surface["allocator_delta"] = surface.pnl_l100 - surface.pnl_l000

    top2 = pd.read_parquet(repo_root / "results/top2_n7_stable/issue_bundles.parquet")
    top2 = top2[
        top2.horizon.eq(PRIMARY_HORIZON)
        & top2.arm.eq("P_TOP2_NO_GATE")
        & top2.gate.astype(str).eq("NONE")
        & top2.seed.eq(-1)
    ][["issue_code", "pnl", "gross", "hit", "miss_distance", "settlement_status"]]
    top2 = top2.rename(columns={
        "pnl": "top2_n7_pnl", "gross": "top2_n7_gross", "hit": "top2_n7_hit",
        "miss_distance": "top2_n7_miss_distance",
        "settlement_status": "top2_n7_settlement_status",
    })
    output = issue_panel.merge(surface, on=["issue_code", "issue_year"], how="left", validate="one_to_one")
    return output.merge(top2, on="issue_code", how="left", validate="one_to_one")


def add_lagged_state(panel: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    output = panel.sort_values(["issue_anchor_ts", "issue_code"], kind="stable").reset_index(drop=True).copy()
    lag_columns: list[str] = []
    derived: dict[str, pd.Series] = {}
    target_sources = [
        *TARGETS, "eu_logloss", "line_logloss", "eu_top1_residual", "line_top1_residual",
        "pnl_l000", "pnl_l100", "top2_n7_pnl", "top2_n7_hit", "top2_n7_miss_distance",
    ]
    timestamps = pd.to_datetime(output.issue_anchor_ts, utc=True)
    for target in target_sources:
        last_observation = pd.Series(pd.NaT, index=output.index, dtype="datetime64[ns, UTC]")
        rolling_values: dict[str, pd.Series] = {}
        for window in WINDOWS:
            prefix = f"lag_{target}_roll{window}"
            rolling_values[f"{prefix}_mean"] = pd.Series(np.nan, index=output.index)
            rolling_values[f"{prefix}_std"] = pd.Series(np.nan, index=output.index)
            rolling_values[f"{prefix}_count"] = pd.Series(0.0, index=output.index)
        ewm_values = {
            f"lag_{target}_ewm{half_life}": pd.Series(np.nan, index=output.index)
            for half_life in HALF_LIVES
        }
        for anchor in timestamps.drop_duplicates().sort_values():
            indices = output.index[timestamps.eq(anchor)]
            prior_mask = timestamps.lt(anchor) & output[target].notna()
            history = output.loc[prior_mask, target].astype(float)
            history_timestamps = timestamps[prior_mask]
            if not history.empty:
                last_observation.loc[indices] = history_timestamps.max()
            for window in WINDOWS:
                minimum = max(3, window // 2)
                values = history.tail(window)
                prefix = f"lag_{target}_roll{window}"
                rolling_values[f"{prefix}_count"].loc[indices] = len(values)
                if len(values) >= minimum:
                    rolling_values[f"{prefix}_mean"].loc[indices] = values.mean()
                    rolling_values[f"{prefix}_std"].loc[indices] = values.std(ddof=0)
            for half_life in HALF_LIVES:
                name = f"lag_{target}_ewm{half_life}"
                if len(history) >= 3:
                    ewm_values[name].loc[indices] = history.ewm(
                        halflife=half_life, adjust=False
                    ).mean().iloc[-1]
        derived[f"lag_{target}_last_observation_ts"] = last_observation.astype("string")
        for window in WINDOWS:
            prefix = f"lag_{target}_roll{window}"
            derived[f"{prefix}_mean"] = rolling_values[f"{prefix}_mean"]
            derived[f"{prefix}_std"] = rolling_values[f"{prefix}_std"]
            derived[f"{prefix}_count"] = rolling_values[f"{prefix}_count"]
            lag_columns.extend([f"{prefix}_mean", f"{prefix}_std", f"{prefix}_count"])
        for half_life in HALF_LIVES:
            name = f"lag_{target}_ewm{half_life}"
            derived[name] = ewm_values[name]
            lag_columns.append(name)
    output = pd.concat([output, pd.DataFrame(derived, index=output.index)], axis=1)
    output["state_warmup_market"] = output["lag_eu_brier_roll20_count"].lt(10)
    output["state_warmup_allocator"] = output["lag_allocator_delta_roll20_count"].lt(10)
    return output, lag_columns
