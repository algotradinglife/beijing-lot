"""Run SP-EFF-001: a leakage-safe SP market-efficiency experiment.

This module is intentionally independent from betting/strategy code.  It reads
the append-only live collector database, selects the last *complete* SP vector
strictly before kickoff, evaluates fixed probabilistic baselines on a
chronological issue holdout, and writes the research record required by Issue
#3.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import norm


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "beidan_live.db"
DEFAULT_REPORT = ROOT / "docs" / "research" / "experiments" / "SP-EFF-001.md"
DEFAULT_FIGURE = ROOT / "docs" / "research" / "figures" / "sp_eff_001_calibration.png"

OUTCOMES = ("3", "1", "0")
SP_COLUMNS = ("sp_3", "sp_1", "sp_0")
PROBABILITY_BINS = np.linspace(0.0, 1.0, 11)
SP_BINS = np.array([1.0, 1.5, 2.0, 3.0, 5.0, 8.0, np.inf])
SP_LABELS = ("1-1.5", "1.5-2", "2-3", "3-5", "5-8", "8+")


@dataclass(frozen=True)
class DatasetAudit:
    database_path: str
    database_size_bytes: int
    extracted_at_utc: str
    extract_sha256: str
    settled_matches: int
    complete_snapshot_rows: int
    invalid_timestamp_rows: int
    postkickoff_rows_rejected: int
    eligible_matches: int
    first_kickoff: str
    last_kickoff: str
    earliest_snapshot: str
    latest_snapshot: str
    minimum_closing_mtk: float
    median_closing_mtk: float


def _readonly_connection(path: Path) -> sqlite3.Connection:
    """Open a query-only SQLite connection and pin a consistent read view."""
    uri = f"file:{path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def _utc_timestamp(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    return None if pd.isna(parsed) else parsed


def _extract_fingerprint(frame: pd.DataFrame) -> str:
    columns = [
        "match_id", "issue", "kickoff_ts", "opening_snapshot_ts",
        "closing_snapshot_ts", "opening_sp_3", "opening_sp_1", "opening_sp_0",
        "sp_3", "sp_1", "sp_0", "result_code",
    ]
    canonical = frame.sort_values("match_id")[columns].to_csv(
        index=False, lineterminator="\n", float_format="%.10g"
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_experiment_frame(
    database_path: str | Path,
    *,
    as_of: str | None = None,
) -> tuple[pd.DataFrame, DatasetAudit]:
    """Load one leakage-safe opening/closing SP vector per settled match.

    Collector timestamps are UTC.  Kickoffs are stored as naive Beijing time,
    so they are explicitly localized to Asia/Shanghai before comparison.
    """
    path = Path(database_path)
    if not path.is_file():
        raise FileNotFoundError(f"live database not found: {path}")
    as_of_ts = _utc_timestamp(as_of)
    if as_of and as_of_ts is None:
        raise ValueError(f"invalid --as-of timestamp: {as_of}")

    connection = _readonly_connection(path)
    try:
        settled_matches = int(
            connection.execute(
                "SELECT COUNT(*) FROM settlements WHERE result_code IN ('3','1','0')"
            ).fetchone()[0]
        )
        raw = pd.read_sql_query(
            """
            SELECT s.id, s.match_id, s.snapshot_ts,
                   s.sp_3, s.sp_1, s.sp_0,
                   m.issue, m.match_idx, m.league, m.kickoff_ts,
                   m.handicap_line, st.result_code
            FROM snapshots s
            JOIN matches m ON m.match_id = s.match_id
            JOIN settlements st ON st.match_id = s.match_id
            WHERE st.result_code IN ('3','1','0')
              AND s.sp_3 > 1.0 AND s.sp_1 > 1.0 AND s.sp_0 > 1.0
            """,
            connection,
        )
    finally:
        connection.rollback()
        connection.close()

    complete_snapshot_rows = len(raw)
    raw["snapshot_at"] = pd.to_datetime(raw["snapshot_ts"], utc=True, errors="coerce")
    kickoff_local = pd.to_datetime(raw["kickoff_ts"], errors="coerce")
    raw["kickoff_at"] = kickoff_local.dt.tz_localize(
        "Asia/Shanghai", ambiguous="NaT", nonexistent="NaT"
    ).dt.tz_convert("UTC")
    invalid = raw["snapshot_at"].isna() | raw["kickoff_at"].isna()
    invalid_timestamp_rows = int(invalid.sum())
    valid = raw.loc[~invalid].copy()
    if as_of_ts is not None:
        valid = valid[valid["snapshot_at"] <= as_of_ts]

    prekickoff = valid[valid["snapshot_at"] < valid["kickoff_at"]].copy()
    postkickoff_rows_rejected = int(len(valid) - len(prekickoff))
    if prekickoff.empty:
        raise ValueError("no settled matches have a complete pre-kickoff SP vector")

    prekickoff["mtk"] = (
        prekickoff["kickoff_at"] - prekickoff["snapshot_at"]
    ).dt.total_seconds() / 60.0
    prekickoff = prekickoff.sort_values(["match_id", "snapshot_at", "id"])
    opening = prekickoff.groupby("match_id", sort=False).first().reset_index()
    closing = prekickoff.groupby("match_id", sort=False).last().reset_index()

    opening = opening[["match_id", "snapshot_ts", "sp_3", "sp_1", "sp_0"]].rename(
        columns={
            "snapshot_ts": "opening_snapshot_ts",
            "sp_3": "opening_sp_3",
            "sp_1": "opening_sp_1",
            "sp_0": "opening_sp_0",
        }
    )
    closing = closing.rename(columns={"snapshot_ts": "closing_snapshot_ts"})
    frame = closing.merge(opening, on="match_id", how="inner", validate="one_to_one")
    frame["result_code"] = frame["result_code"].astype(str)
    frame["issue"] = frame["issue"].astype(str)

    inverse = 1.0 / frame.loc[:, SP_COLUMNS].to_numpy(dtype=float)
    probabilities = inverse / inverse.sum(axis=1, keepdims=True)
    for index, outcome in enumerate(OUTCOMES):
        frame[f"market_p_{outcome}"] = probabilities[:, index]

    opening_values = frame[
        ["opening_sp_3", "opening_sp_1", "opening_sp_0"]
    ].to_numpy(dtype=float)
    closing_values = frame.loc[:, SP_COLUMNS].to_numpy(dtype=float)
    frame["sp_change_magnitude"] = np.mean(
        np.abs(np.log(closing_values / opening_values)), axis=1
    )

    audit = DatasetAudit(
        database_path=str(path.resolve()),
        database_size_bytes=path.stat().st_size,
        extracted_at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        extract_sha256=_extract_fingerprint(frame),
        settled_matches=settled_matches,
        complete_snapshot_rows=complete_snapshot_rows,
        invalid_timestamp_rows=invalid_timestamp_rows,
        postkickoff_rows_rejected=postkickoff_rows_rejected,
        eligible_matches=len(frame),
        first_kickoff=frame["kickoff_at"].min().isoformat(),
        last_kickoff=frame["kickoff_at"].max().isoformat(),
        earliest_snapshot=prekickoff["snapshot_at"].min().isoformat(),
        latest_snapshot=prekickoff["snapshot_at"].max().isoformat(),
        minimum_closing_mtk=float(frame["mtk"].min()),
        median_closing_mtk=float(frame["mtk"].median()),
    )
    return frame.sort_values(["kickoff_at", "match_id"]).reset_index(drop=True), audit


def chronological_issue_split(
    frame: pd.DataFrame, train_fraction: float = 0.70
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...], tuple[str, ...]]:
    """Split entire issues chronologically so one issue cannot cross the holdout."""
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between zero and one")
    issue_order = (
        frame.groupby("issue")["kickoff_at"].min().sort_values().index.astype(str).tolist()
    )
    if len(issue_order) < 2:
        raise ValueError("at least two issues are required for an out-of-sample split")
    train_count = min(max(int(math.floor(len(issue_order) * train_fraction)), 1), len(issue_order) - 1)
    train_issues = tuple(issue_order[:train_count])
    test_issues = tuple(issue_order[train_count:])
    train = frame[frame["issue"].isin(train_issues)].copy()
    test = frame[frame["issue"].isin(test_issues)].copy()
    return train, test, train_issues, test_issues


def outcome_matrix(frame: pd.DataFrame) -> np.ndarray:
    lookup = {outcome: index for index, outcome in enumerate(OUTCOMES)}
    indexes = frame["result_code"].map(lookup)
    if indexes.isna().any():
        raise ValueError("unexpected result_code in experiment frame")
    return np.eye(len(OUTCOMES), dtype=float)[indexes.astype(int).to_numpy()]


def market_probabilities(frame: pd.DataFrame) -> np.ndarray:
    return frame[[f"market_p_{outcome}" for outcome in OUTCOMES]].to_numpy(dtype=float)


def temperature_scale(probabilities: np.ndarray, temperature: float) -> np.ndarray:
    if not np.isfinite(temperature) or temperature <= 0:
        raise ValueError("temperature must be positive")
    logits = np.log(np.clip(probabilities, 1e-15, 1.0)) / temperature
    logits -= logits.max(axis=1, keepdims=True)
    scaled = np.exp(logits)
    return scaled / scaled.sum(axis=1, keepdims=True)


def fit_temperature(probabilities: np.ndarray, outcomes: np.ndarray) -> float:
    """Fit one pre-specified sharpness parameter using training rows only."""
    result = minimize_scalar(
        lambda value: multiclass_log_loss(outcomes, temperature_scale(probabilities, value)),
        bounds=(0.25, 4.0),
        method="bounded",
        options={"xatol": 1e-8},
    )
    if not result.success:
        raise RuntimeError(f"temperature calibration failed: {result.message}")
    return float(result.x)


def multiclass_log_loss(outcomes: np.ndarray, probabilities: np.ndarray) -> float:
    clipped = np.clip(probabilities, 1e-15, 1.0)
    return float(-np.mean(np.sum(outcomes * np.log(clipped), axis=1)))


def multiclass_brier(outcomes: np.ndarray, probabilities: np.ndarray) -> float:
    """Return the unscaled three-class Brier score (range 0..2)."""
    return float(np.mean(np.sum((probabilities - outcomes) ** 2, axis=1)))


def paired_score_comparisons(
    outcomes: np.ndarray,
    predictions: dict[str, np.ndarray],
    issue_labels: Iterable[str],
    *,
    bootstrap_samples: int = 5_000,
    seed: int = 20260721,
) -> pd.DataFrame:
    """Paired score deltas with a chronological-issue cluster bootstrap.

    Negative deltas favor the SP model. Resampling whole issues avoids treating
    matches from the same collector issue as fully independent.
    """
    issue_array = np.asarray(list(issue_labels), dtype=str)
    unique_issues = np.unique(issue_array)
    if len(issue_array) != len(outcomes) or len(unique_issues) < 2:
        raise ValueError("score comparison requires aligned rows from at least two issues")
    rng = np.random.default_rng(seed)
    draws = rng.integers(
        0, len(unique_issues), size=(bootstrap_samples, len(unique_issues))
    )
    comparisons = (
        ("B1 normalized inverse SP", "B0 uniform random"),
        ("B1 normalized inverse SP", "B2 historical outcome frequency"),
        ("B1-T train-fitted temperature", "B0 uniform random"),
        ("B1-T train-fitted temperature", "B2 historical outcome frequency"),
    )
    rows = []
    for model, comparator in comparisons:
        model_probabilities = np.clip(predictions[model], 1e-15, 1.0)
        comparator_probabilities = np.clip(predictions[comparator], 1e-15, 1.0)
        per_match = {
            "Log Loss": (
                -np.sum(outcomes * np.log(model_probabilities), axis=1)
                + np.sum(outcomes * np.log(comparator_probabilities), axis=1)
            ),
            "Brier Score": (
                np.sum((model_probabilities - outcomes) ** 2, axis=1)
                - np.sum((comparator_probabilities - outcomes) ** 2, axis=1)
            ),
        }
        for metric, differences in per_match.items():
            cluster_sums = np.array(
                [differences[issue_array == issue].sum() for issue in unique_issues]
            )
            cluster_counts = np.array(
                [(issue_array == issue).sum() for issue in unique_issues], dtype=float
            )
            bootstrap_means = (
                cluster_sums[draws].sum(axis=1) / cluster_counts[draws].sum(axis=1)
            )
            low, high = np.quantile(bootstrap_means, [0.025, 0.975])
            rows.append(
                {
                    "Model": model,
                    "Comparator": comparator,
                    "Metric": metric,
                    "Delta": float(differences.mean()),
                    "95% CI low": float(low),
                    "95% CI high": float(high),
                }
            )
    return pd.DataFrame(rows)


def calibration_table(
    outcomes: np.ndarray,
    probabilities: np.ndarray,
    *,
    bins: np.ndarray = PROBABILITY_BINS,
) -> pd.DataFrame:
    """Fixed-width calibration cells with Holm-adjusted residual tests."""
    rows: list[dict[str, object]] = []
    for outcome_index, outcome in enumerate(OUTCOMES):
        predicted = probabilities[:, outcome_index]
        observed = outcomes[:, outcome_index]
        bin_ids = np.clip(np.digitize(predicted, bins[1:-1], right=False), 0, len(bins) - 2)
        for bin_id in range(len(bins) - 1):
            mask = bin_ids == bin_id
            if not mask.any():
                continue
            p = predicted[mask]
            y = observed[mask]
            variance = float(np.sum(p * (1.0 - p)))
            residual = float(np.sum(y - p))
            z_score = residual / math.sqrt(variance) if variance > 0 else float("nan")
            p_value = float(2.0 * norm.sf(abs(z_score))) if np.isfinite(z_score) else float("nan")
            rows.append(
                {
                    "outcome": outcome,
                    "probability_bin": f"{bins[bin_id]:.1f}-{bins[bin_id + 1]:.1f}",
                    "n": int(mask.sum()),
                    "mean_predicted": float(p.mean()),
                    "observed_rate": float(y.mean()),
                    "gap": float(y.mean() - p.mean()),
                    "z_score": z_score,
                    "p_value": p_value,
                }
            )
    result = pd.DataFrame(rows)
    finite = result["p_value"].notna()
    adjusted = pd.Series(np.nan, index=result.index, dtype=float)
    if finite.any():
        ordered = result.loc[finite, "p_value"].sort_values()
        count = len(ordered)
        running = 0.0
        for rank, (index, value) in enumerate(ordered.items()):
            running = max(running, min(1.0, float(value) * (count - rank)))
            adjusted.loc[index] = running
    result["p_value_holm"] = adjusted
    result["significant_5pct"] = result["p_value_holm"] < 0.05
    return result


def expected_calibration_error(calibration: pd.DataFrame) -> float:
    if calibration.empty:
        return float("nan")
    return float(
        np.average(np.abs(calibration["gap"]), weights=calibration["n"])
    )


def evaluate_models(
    train: pd.DataFrame, test: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, np.ndarray], float, pd.DataFrame]:
    y_train = outcome_matrix(train)
    y_test = outcome_matrix(test)
    market_train = market_probabilities(train)
    market_test = market_probabilities(test)
    temperature = fit_temperature(market_train, y_train)
    historical_prior = y_train.mean(axis=0)
    predictions = {
        "B0 uniform random": np.full_like(y_test, 1.0 / len(OUTCOMES)),
        "B1 normalized inverse SP": market_test,
        "B1-T train-fitted temperature": temperature_scale(market_test, temperature),
        "B2 historical outcome frequency": np.tile(historical_prior, (len(test), 1)),
    }
    metric_rows = []
    calibration_tables = []
    for model, probabilities in predictions.items():
        calibration = calibration_table(y_test, probabilities)
        calibration["model"] = model
        calibration_tables.append(calibration)
        metric_rows.append(
            {
                "model": model,
                "log_loss": multiclass_log_loss(y_test, probabilities),
                "brier_score": multiclass_brier(y_test, probabilities),
                "ece": expected_calibration_error(calibration),
            }
        )
    return (
        pd.DataFrame(metric_rows),
        predictions,
        temperature,
        pd.concat(calibration_tables, ignore_index=True),
    )


def _band_diagnostics(
    train: pd.DataFrame,
    test: pd.DataFrame,
    probabilities: np.ndarray,
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    y_test = outcome_matrix(test)
    long_rows = []
    for index, outcome in enumerate(OUTCOMES):
        values = test[SP_COLUMNS[index]].to_numpy(dtype=float)
        band_ids = np.digitize(values, SP_BINS[1:-1], right=False)
        for band_id, label in enumerate(SP_LABELS):
            mask = band_ids == band_id
            if not mask.any():
                continue
            long_rows.append(
                {
                    "outcome": outcome,
                    "SP band": label,
                    "n": int(mask.sum()),
                    "mean p": float(probabilities[mask, index].mean()),
                    "hit rate": float(y_test[mask, index].mean()),
                    "gap": float(y_test[mask, index].mean() - probabilities[mask, index].mean()),
                }
            )
    sp_bands = pd.DataFrame(long_rows)

    thresholds = np.quantile(train["sp_change_magnitude"], [0.25, 0.50, 0.75])
    drift_ids = np.searchsorted(thresholds, test["sp_change_magnitude"].to_numpy(), side="right")
    drift_rows = []
    for band_id in range(4):
        mask = drift_ids == band_id
        if not mask.any():
            continue
        drift_rows.append(
            {
                "change quartile": f"Q{band_id + 1}",
                "n": int(mask.sum()),
                "mean change": float(test.loc[mask, "sp_change_magnitude"].mean()),
                "log loss": multiclass_log_loss(y_test[mask], probabilities[mask]),
                "Brier": multiclass_brier(y_test[mask], probabilities[mask]),
            }
        )
    return sp_bands, pd.DataFrame(drift_rows), thresholds


def _markdown_table(frame: pd.DataFrame, formats: dict[str, str] | None = None) -> str:
    formats = formats or {}
    display = frame.copy()
    for column, fmt in formats.items():
        if column in display:
            display[column] = display[column].map(
                lambda value: "—" if pd.isna(value) else format(value, fmt)
            )
    headers = [str(column) for column in display.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in display.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def _make_calibration_figure(
    calibration: pd.DataFrame, output_path: Path
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    models = ("B1 normalized inverse SP", "B1-T train-fitted temperature")
    colors = {"3": "#2166ac", "1": "#7b3294", "0": "#b2182b"}
    labels = {"3": "home/handicap win (3)", "1": "draw (1)", "0": "away/handicap loss (0)"}
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharex=True, sharey=True)
    for axis, model in zip(axes, models):
        subset = calibration[calibration["model"] == model]
        axis.plot([0, 1], [0, 1], linestyle="--", linewidth=1, color="#666666")
        for outcome in OUTCOMES:
            rows = subset[subset["outcome"] == outcome]
            axis.scatter(
                rows["mean_predicted"], rows["observed_rate"],
                s=np.maximum(20.0, rows["n"].to_numpy() * 0.8),
                alpha=0.75, color=colors[outcome], label=labels[outcome],
                edgecolor="white", linewidth=0.5,
            )
        axis.set_title(model)
        axis.set_xlabel("Mean predicted probability")
        axis.grid(alpha=0.25)
    axes[0].set_ylabel("Observed frequency")
    axes[1].legend(fontsize=8, loc="lower right")
    fig.suptitle("SP-EFF-001 — out-of-sample calibration")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def render_report(
    *,
    audit: DatasetAudit,
    train: pd.DataFrame,
    test: pd.DataFrame,
    train_issues: tuple[str, ...],
    test_issues: tuple[str, ...],
    metrics: pd.DataFrame,
    score_comparisons: pd.DataFrame,
    calibration: pd.DataFrame,
    temperature: float,
    sp_bands: pd.DataFrame,
    drift_bands: pd.DataFrame,
    drift_thresholds: np.ndarray,
    figure_path: Path,
    output_path: Path,
) -> None:
    calibrated = calibration[calibration["model"] == "B1-T train-fitted temperature"].copy()
    significant = calibrated[calibrated["significant_5pct"]]
    raw_metrics = metrics.set_index("model").loc["B1 normalized inverse SP"]
    calibrated_metrics = metrics.set_index("model").loc["B1-T train-fitted temperature"]
    calibration_conclusion = (
        "Reject H0 on this holdout: at least one pre-specified probability/outcome cell "
        "retains a calibration deviation after Holm correction."
        if not significant.empty
        else "Fail to reject H0 on this holdout: no pre-specified probability/outcome cell "
        "retains a calibration deviation after Holm correction."
    )
    calibrated_log_comparisons = score_comparisons[
        (score_comparisons["Model"] == "B1-T train-fitted temperature")
        & (score_comparisons["Metric"] == "Log Loss")
    ]
    predictive_conclusion = (
        "The calibrated SP model beats both non-market baselines in holdout Log Loss, "
        "but at least one issue-block-bootstrap interval crosses zero. This is directional, "
        "not conclusive, evidence of incremental predictive information."
        if (calibrated_log_comparisons["95% CI high"] >= 0).any()
        else "The calibrated SP model beats both non-market baselines in holdout Log Loss, "
        "with both issue-block-bootstrap intervals below zero. This supports incremental "
        "predictive information in SP for this sample."
    )
    relative_figure = Path("..") / "figures" / figure_path.name
    metric_display = metrics.rename(
        columns={"model": "Baseline", "log_loss": "Log Loss", "brier_score": "Brier Score", "ece": "ECE"}
    )
    calibration_display = calibrated[
        ["outcome", "probability_bin", "n", "mean_predicted", "observed_rate", "gap", "p_value_holm", "significant_5pct"]
    ].rename(
        columns={
            "outcome": "Outcome", "probability_bin": "Probability bin",
            "mean_predicted": "Mean p", "observed_rate": "Actual rate",
            "gap": "Gap", "p_value_holm": "Holm p", "significant_5pct": "Significant",
        }
    )
    lines = [
        "# SP-EFF-001 — SP Market Efficiency Study",
        "",
        "> This is a market-information experiment, not a strategy backtest. No betting rule, stake rule, parameter search, or ROI objective is used.",
        "",
        "## Dataset version",
        "",
        f"- Source: `data/{Path(audit.database_path).name}` (`{audit.database_size_bytes:,}` bytes)",
        f"- Extracted: `{audit.extracted_at_utc}`",
        f"- Canonical extract SHA-256: `{audit.extract_sha256}`",
        f"- Complete-snapshot rows examined: `{audit.complete_snapshot_rows:,}`; valid settled matches: `{audit.settled_matches:,}`",
        f"- Eligible matches after strict pre-kickoff filtering: `{audit.eligible_matches:,}`",
        f"- Kickoff range (UTC): `{audit.first_kickoff}` to `{audit.last_kickoff}`",
        f"- Included snapshot range (UTC): `{audit.earliest_snapshot}` to `{audit.latest_snapshot}`",
        f"- Rejected invalid-timestamp rows: `{audit.invalid_timestamp_rows:,}`; rejected post-kickoff rows: `{audit.postkickoff_rows_rejected:,}`",
        f"- Closing snapshot lead time: minimum `{audit.minimum_closing_mtk:.2f}` min; median `{audit.median_closing_mtk:.2f}` min",
        "",
        "Dataset version is the canonical extract hash, not merely the mutable SQLite filename. It hashes match identity, opening/closing snapshot timestamps and SP vectors, and settlement outcome.",
        "",
        "## Research Question",
        "",
        "RQ001: Does Beijing Single Match (北京单场) SP contain calibrated predictive information about the 90-minute handicap win/draw/loss result?",
        "",
        "- H0: after a reasonable probability transformation/calibration, SP probabilities agree with realized outcome frequencies.",
        "- H1: systematic calibration deviations remain.",
        "",
        "## Methodology",
        "",
        "1. Keep settled 3/1/0 matches with a complete three-way SP vector (`SP > 1` for all outcomes).",
        "2. Interpret `snapshot_ts` as UTC and naive `kickoff_ts` as Asia/Shanghai. Select the latest complete vector strictly before kickoff; post-kickoff and invalid timestamps are excluded.",
        "3. Transform SP jointly, not as `P = 1/SP`: `p_i = (1/SP_i) / Σ_j(1/SP_j)`. This removes the match-level overround and forces coherent three-way probabilities.",
        "4. Preserve full issue boundaries in a fixed 70/30 chronological split. The first issues train the historical prior and one temperature parameter; the last issues are untouched holdout data.",
        "5. Fit temperature scaling only on training log loss: `p'_i ∝ p_i^(1/T)`. No outcome-dependent rule or profitability search is performed.",
        "6. Report fixed 0.1 probability calibration bins, fixed SP bands, and SP movement quartiles. SP movement is the mean absolute log change across the three outcomes from the earliest to the closing eligible snapshot; quartile cutoffs come from training data only.",
        "",
        f"Training issues ({len(train_issues)}, n={len(train):,}): `{', '.join(train_issues)}`.",
        "",
        f"Holdout issues ({len(test_issues)}, n={len(test):,}): `{', '.join(test_issues)}`.",
        "",
        "## Baseline",
        "",
        "- B0 — uniform random: `(1/3, 1/3, 1/3)`.",
        "- B1 — SP market: normalized inverse-SP probabilities.",
        f"- B1-T — the same market probabilities with a single train-fitted temperature (`T={temperature:.4f}`). This is the calibrated H0 check.",
        "- B2 — independent historical-win-rate model: the constant 3/1/0 frequencies estimated only from training outcomes.",
        "",
        "## Metrics",
        "",
        "- Multiclass Log Loss (lower is better).",
        "- Three-class Brier Score `mean(Σ(p-y)²)`, unscaled, range 0–2 (lower is better).",
        "- Calibration curve and ECE (cell-count-weighted absolute calibration gap).",
        "- Per-cell standardized calibration residual tests with Holm family-wise correction across the fixed holdout cells.",
        "- Paired proper-score differences with a 5,000-sample whole-issue cluster bootstrap.",
        "",
        "ROI is deliberately absent.",
        "",
        "## Results",
        "",
        "### Holdout baseline comparison",
        "",
        _markdown_table(metric_display, {"Log Loss": ".5f", "Brier Score": ".5f", "ECE": ".4f"}),
        "",
        f"Temperature calibration changes holdout Log Loss by `{calibrated_metrics['log_loss'] - raw_metrics['log_loss']:+.5f}` and Brier Score by `{calibrated_metrics['brier_score'] - raw_metrics['brier_score']:+.5f}` relative to raw normalized SP.",
        "",
        "### Paired holdout score differences",
        "",
        "Negative values favor the SP model. Confidence intervals resample whole holdout issues.",
        "",
        _markdown_table(score_comparisons, {"Delta": "+.5f", "95% CI low": "+.5f", "95% CI high": "+.5f"}),
        "",
        f"![Out-of-sample calibration]({relative_figure.as_posix()})",
        "",
        "### Calibrated market probability bins (holdout)",
        "",
        _markdown_table(calibration_display, {"Mean p": ".3f", "Actual rate": ".3f", "Gap": "+.3f", "Holm p": ".4f"}),
        "",
        "### Closing SP bands (calibrated market, holdout)",
        "",
        _markdown_table(sp_bands, {"mean p": ".3f", "hit rate": ".3f", "gap": "+.3f"}),
        "",
        "### SP change magnitude (calibrated market, holdout)",
        "",
        f"Training cutoffs for mean absolute log-SP change: `{', '.join(f'{value:.5f}' for value in drift_thresholds)}`.",
        "",
        _markdown_table(drift_bands, {"mean change": ".5f", "log loss": ".5f", "Brier": ".5f"}),
        "",
        "## Limitations",
        "",
        "- The live collector covers only a short 2026 window; issue sizes and league mix vary, and early issues are much larger than later issues.",
        "- The last observed collector snapshot is a closing proxy, not an exchange-grade official closing timestamp. Lead time varies by match.",
        "- `result_code` is taken from the settlement table as the 90-minute handicap 3/1/0 label; this experiment does not independently reconstruct every settlement from raw scores and handicap history.",
        "- The historical-frequency baseline is intentionally simple. It establishes an outcome-frequency comparator, not a best possible team-strength model such as a mature Elo system.",
        "- Calibration cells in the tail can be small. Holm correction controls the declared family of fixed-bin tests, but the short holdout still has limited power.",
        "- SP movement is descriptive and may reflect unequal observation windows. It is not interpreted as a tradable signal.",
        "",
        "## Conclusion",
        "",
        predictive_conclusion,
        "",
        calibration_conclusion,
        "",
        "The market-information conclusion should also consider whether B1/B1-T improve proper scoring rules over B0 and B2. A detected statistical bias is only a research starting point; it does not establish a realizable trading edge after payout rules, timing, limits, or costs.",
        "",
        "## Reproduction",
        "",
        "```bash",
        "python scripts/run_sp_eff_001.py --db data/beidan_live.db",
        "```",
        "",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    frame, audit = load_experiment_frame(args.db, as_of=args.as_of)
    train, test, train_issues, test_issues = chronological_issue_split(
        frame, train_fraction=args.train_fraction
    )
    metrics, predictions, temperature, calibration = evaluate_models(train, test)
    score_comparisons = paired_score_comparisons(
        outcome_matrix(test), predictions, test["issue"]
    )
    calibrated_predictions = predictions["B1-T train-fitted temperature"]
    sp_bands, drift_bands, drift_thresholds = _band_diagnostics(
        train, test, calibrated_predictions
    )
    figure_path = Path(args.figure)
    report_path = Path(args.output)
    _make_calibration_figure(calibration, figure_path)
    render_report(
        audit=audit, train=train, test=test,
        train_issues=train_issues, test_issues=test_issues,
        metrics=metrics, score_comparisons=score_comparisons,
        calibration=calibration, temperature=temperature,
        sp_bands=sp_bands, drift_bands=drift_bands,
        drift_thresholds=drift_thresholds, figure_path=figure_path,
        output_path=report_path,
    )
    print(f"SP-EFF-001 complete: {len(train):,} train / {len(test):,} holdout matches")
    print(metrics.to_string(index=False, float_format=lambda value: f"{value:.6f}"))
    print(f"Report: {report_path}")
    print(f"Figure: {figure_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--figure", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument(
        "--as-of",
        help="optional inclusive UTC snapshot cutoff (ISO-8601) for a stable rerun",
    )
    parser.add_argument("--train-fraction", type=float, default=0.70)
    return parser


if __name__ == "__main__":
    run(build_parser().parse_args())
