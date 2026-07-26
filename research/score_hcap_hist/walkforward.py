"""Frozen B0/B1 retrospective walk-forward for SCORE-HCAP-HIST-001."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import scipy
from scipy.stats import skellam


CLASSES = ("3", "1", "0")
TEST_SEASONS = tuple(range(2016, 2026))
PRIOR_EXPOSURE = 5.0
BOOTSTRAP_REPLICATES = 2_000
BOOTSTRAP_SEED = 20260726
# The formal model, metrics, bootstrap, and decision use the in-memory
# full-precision probability vectors.  This codec is applied only at the
# CSV/JSON output boundary.  It deliberately removes machine-level last-bit
# variation from SciPy while preserving a probability sum tolerance far tighter
# than the contract's 1e-12 requirement.
PERSISTED_FLOAT_SIGNIFICANT_DIGITS = 13
PERSISTED_FLOAT_FORMAT = f".{PERSISTED_FLOAT_SIGNIFICANT_DIGITS}g"


def persistence_contract() -> dict[str, Any]:
    """Return the frozen representation contract for all persisted floats."""

    return {
        "kind": "decimal_significant_digits",
        "format": PERSISTED_FLOAT_FORMAT,
        "significant_digits": PERSISTED_FLOAT_SIGNIFICANT_DIGITS,
        "rounding": "python_general_format_round_to_nearest_even",
        "scope": (
            "CSV/JSON serialization only; in-memory B0/B1 probabilities remain "
            "full precision for metrics, bootstrap, and decision"
        ),
    }


def runtime_environment() -> dict[str, Any]:
    """Return a pathless numerical-runtime receipt for the frozen replay."""

    return {
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "float_radix": sys.float_info.radix,
            "float_mantissa_bits": sys.float_info.mant_dig,
        },
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "probability_backend": "scipy.stats.skellam",
        "persistence_contract": persistence_contract(),
    }


def _canonical_float(value: float) -> float:
    """Round a finite value to the frozen portable output representation."""

    number = float(value)
    if not math.isfinite(number):
        raise ValueError("persisted numerical outputs must be finite")
    canonical = float(format(number, PERSISTED_FLOAT_FORMAT))
    return 0.0 if canonical == 0.0 else canonical


def persisted_float_text(value: float) -> str:
    """Serialize a numeric output under the frozen portable float codec."""

    return format(_canonical_float(value), PERSISTED_FLOAT_FORMAT)


def _validate_persisted_probability_triplet(
    probabilities: tuple[float, float, float], label: str
) -> None:
    """Validate that output-boundary serialization preserves the probability contract.

    The returned model rows intentionally retain ``probabilities`` at full
    precision.  This check is solely for the serialized CSV representation.
    """

    serialized = tuple(persisted_float_text(value) for value in probabilities)
    if abs(sum(float(value) for value in serialized) - 1.0) > 1e-12:
        raise ValueError(f"{label} persisted probabilities do not sum to one within 1e-12")


def _canonical_payload(value: Any) -> Any:
    if isinstance(value, (float, np.floating)):
        return _canonical_float(float(value))
    if isinstance(value, dict):
        return {str(key): _canonical_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonical_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_canonical_payload(item) for item in value]
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(_canonical_payload(value), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def handicap_probabilities(lambda_home: float, lambda_away: float, handicap: int) -> tuple[float, float, float]:
    """Exact Skellam mapping for home/draw/away handicap 3/1/0."""
    threshold = -handicap
    p3 = float(skellam.sf(threshold, lambda_home, lambda_away))
    p1 = float(skellam.pmf(threshold, lambda_home, lambda_away))
    p0 = float(skellam.cdf(threshold - 1, lambda_home, lambda_away))
    probabilities = (p3, p1, p0)
    if not all(math.isfinite(value) and 0 <= value <= 1 for value in probabilities):
        raise ValueError("Skellam returned an invalid probability")
    if abs(sum(probabilities) - 1.0) > 1e-12:
        raise ValueError("Skellam handicap probabilities do not sum to one within 1e-12")
    return probabilities


def _smoothed_rate(total: float, n: int, prior: float) -> float:
    return (total + PRIOR_EXPOSURE * prior) / (n + PRIOR_EXPOSURE)


def _class_probabilities(counts: Counter[str]) -> tuple[float, float, float]:
    total = sum(counts[label] for label in CLASSES)
    return tuple((counts[label] + 1.0) / (total + 3.0) for label in CLASSES)  # type: ignore[return-value]


def _metrics(rows: Iterable[dict[str, Any]], model: str) -> dict[str, float | int]:
    observations = list(rows)
    n = len(observations)
    if not n:
        raise ValueError("metrics require at least one observation")
    losses, briers, correct = [], [], 0
    class_losses: dict[str, list[float]] = {label: [] for label in CLASSES}
    class_briers: dict[str, list[float]] = {label: [] for label in CLASSES}
    for row in observations:
        probabilities = [float(row[f"{model}_p{label}"]) for label in CLASSES]
        actual = CLASSES.index(str(row["label_310"]))
        losses.append(-math.log(max(probabilities[actual], 1e-15)))
        briers.append(sum((value - float(index == actual)) ** 2 for index, value in enumerate(probabilities)))
        correct += int(max(range(3), key=probabilities.__getitem__) == actual)
        for index, label in enumerate(CLASSES):
            y = float(index == actual)
            class_losses[label].append(-(y * math.log(max(probabilities[index], 1e-15)) + (1 - y) * math.log(max(1 - probabilities[index], 1e-15))))
            class_briers[label].append((probabilities[index] - y) ** 2)
    result: dict[str, float | int] = {"n": n, "log_loss": float(np.mean(losses)), "brier": float(np.mean(briers)), "top1_accuracy": correct / n}
    for label in CLASSES:
        result[f"p{label}_ovr_log_loss"] = float(np.mean(class_losses[label]))
        result[f"p{label}_ovr_brier"] = float(np.mean(class_briers[label]))
    return result


def _csv_value(value: Any) -> Any:
    return persisted_float_text(value) if isinstance(value, (float, np.floating)) else value


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            [
                {field: _csv_value(row[field]) for field in fields}
                for row in rows
            ]
        )


def _fit_predict(panel: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{panel.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        all_rows = [dict(row) for row in connection.execute("SELECT * FROM panel ORDER BY kickoff_utc,match_id")]
    finally:
        connection.close()
    predictions: list[dict[str, Any]] = []
    for year in TEST_SEASONS:
        train = [row for row in all_rows if int(row["fold_year"]) < year]
        test = [row for row in all_rows if int(row["fold_year"]) == year]
        if not train or not test:
            raise ValueError(f"missing frozen train/test rows for season {year}")
        global_home_gf = sum(int(row["fthg"]) for row in train) / len(train)
        global_home_ga = sum(int(row["ftag"]) for row in train) / len(train)
        global_away_gf, global_away_ga = global_home_ga, global_home_gf
        by_handicap: dict[int, Counter[str]] = defaultdict(Counter)
        home_stats: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        away_stats: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        for row in train:
            by_handicap[int(row["handicap"])][str(row["label_310"])] += 1
            home = home_stats[(str(row["league"]), str(row["normalized_home"]))]
            away = away_stats[(str(row["league"]), str(row["normalized_away"]))]
            home[0] += int(row["fthg"]); home[1] += int(row["ftag"]); home[2] += 1
            away[0] += int(row["ftag"]); away[1] += int(row["fthg"]); away[2] += 1
        global_prior = _class_probabilities(Counter(row["label_310"] for row in train))
        for row in test:
            hcp = int(row["handicap"])
            b0 = _class_probabilities(by_handicap.get(hcp, Counter())) if hcp in by_handicap else global_prior
            if abs(sum(b0) - 1.0) > 1e-12:
                raise ValueError("B0 probabilities do not sum to one within 1e-12")
            home = home_stats.get((str(row["league"]), str(row["normalized_home"])), [0.0, 0.0, 0.0])
            away = away_stats.get((str(row["league"]), str(row["normalized_away"])), [0.0, 0.0, 0.0])
            lambda_home = math.sqrt(_smoothed_rate(home[0], int(home[2]), global_home_gf) * _smoothed_rate(away[1], int(away[2]), global_home_gf))
            lambda_away = math.sqrt(_smoothed_rate(away[0], int(away[2]), global_away_gf) * _smoothed_rate(home[1], int(home[2]), global_away_gf))
            b1 = handicap_probabilities(lambda_home, lambda_away, hcp)
            # Check the output representation without replacing the formal
            # metric inputs.  RQ1 metrics and the decision must consume these
            # unrounded probability values.
            _validate_persisted_probability_triplet(b0, "B0")
            _validate_persisted_probability_triplet(b1, "Skellam")
            predictions.append({
                "fold_season": year, "match_id": int(row["match_id"]), "issue": str(row["issue"]), "match_idx": int(row["match_idx"]),
                "kickoff_utc": str(row["kickoff_utc"]), "league": str(row["league"]), "handicap": hcp, "label_310": str(row["label_310"]),
                "cold_start": int(home[2] == 0 or away[2] == 0), "lambda_home": lambda_home, "lambda_away": lambda_away,
                **{f"b0_p{label}": value for label, value in zip(CLASSES, b0)},
                **{f"b1_p{label}": value for label, value in zip(CLASSES, b1)},
            })
    return sorted(predictions, key=lambda row: (row["fold_season"], row["kickoff_utc"], row["match_id"]))


def _bootstrap(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rng = np.random.Generator(np.random.PCG64(BOOTSTRAP_SEED))
    by_season: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))
    for row in rows:
        actual = CLASSES.index(str(row["label_310"]))
        group = by_season[int(row["fold_season"])][str(row["issue"])]
        group[0] += -math.log(max(float(row[f"b1_p{CLASSES[actual]}"]), 1e-15))
        group[1] += -math.log(max(float(row[f"b0_p{CLASSES[actual]}"]), 1e-15))
        group[2] += 1
    ordered = {year: np.asarray([groups[issue] for issue in sorted(groups)], dtype=float) for year, groups in sorted(by_season.items())}
    output = []
    for replicate in range(BOOTSTRAP_REPLICATES):
        sum_b1 = sum_b0 = total_n = 0.0
        for groups in ordered.values():
            sampled = groups[rng.integers(0, len(groups), size=len(groups))].sum(axis=0)
            sum_b1 += sampled[0]; sum_b0 += sampled[1]; total_n += sampled[2]
        # Keep the full-precision bootstrap draw for quantiles and the
        # decision.  ``_write_csv`` applies the output codec later.
        output.append({"replicate": replicate, "delta_log_loss_b1_minus_b0": sum_b1 / total_n - sum_b0 / total_n})
    return output


def run_walkforward(
    *, panel: Path, output_dir: Path, frozen_config: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Run the single pre-registered B0/B1 configuration once from G0 panel."""
    output_dir.mkdir(parents=True, exist_ok=False)
    if frozen_config is not None:
        _write_json(output_dir / "frozen_b0_b1_config.json", dict(frozen_config))
    environment = runtime_environment()
    _write_json(output_dir / "runtime_environment.json", environment)
    rows = _fit_predict(panel)
    _write_csv(output_dir / "predictions.csv", rows, list(rows[0]))
    aggregate = {model: _metrics(rows, model) for model in ("b0", "b1")}
    for model in ("b0", "b1"):
        ece = 0.0
        for label in CLASSES:
            for bin_index in range(10):
                low, high = bin_index / 10, (bin_index + 1) / 10
                values = [row for row in rows if low <= float(row[f"{model}_p{label}"]) < high or (bin_index == 9 and float(row[f"{model}_p{label}"]) == 1)]
                if values:
                    mean_probability = float(np.mean([float(r[f"{model}_p{label}"]) for r in values]))
                    observed = float(np.mean([str(r["label_310"]) == label for r in values]))
                    ece += len(values) / (3 * len(rows)) * abs(mean_probability - observed)
        aggregate[model]["ece_fixed_10_bins"] = ece
    aggregate["delta_log_loss_b1_minus_b0"] = float(aggregate["b1"]["log_loss"]) - float(aggregate["b0"]["log_loss"])
    season_metrics = []
    for year in TEST_SEASONS:
        subset = [row for row in rows if int(row["fold_season"]) == year]
        b0, b1 = _metrics(subset, "b0"), _metrics(subset, "b1")
        season_metrics.append({"season": year, "n": b0["n"], "b0_log_loss": b0["log_loss"], "b1_log_loss": b1["log_loss"], "delta_log_loss_b1_minus_b0": float(b1["log_loss"]) - float(b0["log_loss"])})
    _write_csv(output_dir / "season_metrics.csv", season_metrics, list(season_metrics[0]))
    calibration = []
    for model in ("b0", "b1"):
        for label in CLASSES:
            for bin_index in range(10):
                low, high = bin_index / 10, (bin_index + 1) / 10
                values = [row for row in rows if low <= float(row[f"{model}_p{label}"]) < high or (bin_index == 9 and float(row[f"{model}_p{label}"]) == 1)]
                calibration.append({
                    "model": model, "class": label, "bin_low": low, "bin_high": high, "n": len(values),
                    "mean_probability": float(np.mean([float(r[f"{model}_p{label}"]) for r in values])) if values else None,
                    "observed_rate": float(np.mean([str(r["label_310"]) == label for r in values])) if values else None,
                })
    _write_csv(output_dir / "calibration_bins.csv", calibration, list(calibration[0]))
    def strata(field: str, value: str) -> list[dict[str, Any]]:
        subset = [row for row in rows if str(row[field]) == value]
        if not subset:
            return []
        a, b = _metrics(subset, "b0"), _metrics(subset, "b1")
        return [{"stratum_type": field, "stratum": value, "n": len(subset), "b0_log_loss": a["log_loss"], "b1_log_loss": b["log_loss"], "delta_log_loss_b1_minus_b0": float(b["log_loss"]) - float(a["log_loss"])}]
    hbucket = lambda h: str(h) if h in {-2, -1, 0, 1, 2} else "other"
    handicap = []
    for value in ("-2", "-1", "0", "1", "2", "other"):
        subset = [row for row in rows if hbucket(int(row["handicap"])) == value]
        handicap.extend(strata_rows := ([{"stratum_type": "handicap", "stratum": value, "n": len(subset), **{f"{model}_log_loss": _metrics(subset, model)["log_loss"] for model in ("b0", "b1")}}] if subset else []))
        if strata_rows: handicap[-1]["delta_log_loss_b1_minus_b0"] = float(handicap[-1]["b1_log_loss"]) - float(handicap[-1]["b0_log_loss"])
    _write_csv(output_dir / "handicap_strata.csv", handicap, list(handicap[0]))
    cold = []
    for value in ("0", "1"):
        cold.extend(strata("cold_start", value))
    _write_csv(output_dir / "cold_start_diagnostics.csv", cold, list(cold[0]))
    bootstrap = _bootstrap(rows)
    _write_csv(output_dir / "bootstrap_deltas.csv", bootstrap, list(bootstrap[0]))
    deltas = np.asarray([float(row["delta_log_loss_b1_minus_b0"]) for row in bootstrap])
    negatives = sum(float(row["delta_log_loss_b1_minus_b0"]) < 0 for row in season_metrics)
    required_negative_seasons = 7 if len(TEST_SEASONS) == 10 else math.ceil(0.7 * len(TEST_SEASONS))
    signal = aggregate["delta_log_loss_b1_minus_b0"] < 0 and float(np.quantile(deltas, .975)) < 0 and negatives >= required_negative_seasons
    final = {"experiment_id": "SCORE-HCAP-HIST-001", "status": "RETROSPECTIVE_INCREMENTAL_PREDICTIVE_SIGNAL" if signal else "NO_REPRODUCIBLE_INCREMENTAL_SIGNAL", "decision_rule": {"pooled_delta_negative": aggregate["delta_log_loss_b1_minus_b0"] < 0, "bootstrap_ci_upper_negative": float(np.quantile(deltas, .975)) < 0, "negative_seasons": negatives, "required_negative_seasons": required_negative_seasons, "test_season_count": len(TEST_SEASONS)}, "execution_enabled": False, "roi_authorized": False, "evidence_level": "C", "outcome_visibility": "historical_known"}
    bootstrap_summary = {"seed": BOOTSTRAP_SEED, "replicates": BOOTSTRAP_REPLICATES, "ci_95_percentile": [float(np.quantile(deltas, .025)), float(np.quantile(deltas, .975))]}
    # Keep this returned value full precision too.  The JSON writer owns all
    # serialization canonicalization, so no formal metric is derived from a
    # canonicalized persisted value.
    summary = {"aggregate": aggregate, "bootstrap": bootstrap_summary, "final_decision": final}
    _write_json(output_dir / "aggregate_metrics.json", summary)
    _write_json(output_dir / "bootstrap_summary.json", bootstrap_summary)
    _write_json(output_dir / "final_decision.json", final)
    receipt = {
        "panel_sha256": sha256_file(panel),
        "outputs": {
            path.name: sha256_file(path)
            for path in sorted(output_dir.iterdir())
            if path.is_file()
        },
        "configuration": {
            "prior_exposure": PRIOR_EXPOSURE,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "test_seasons": list(TEST_SEASONS),
            "persistence_contract": persistence_contract(),
        },
        "runtime_environment_sha256": sha256_file(output_dir / "runtime_environment.json"),
    }
    _write_json(output_dir / "reproducibility_receipt.json", receipt)
    return {"output_dir": output_dir, "summary": summary}
