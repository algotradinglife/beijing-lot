#!/usr/bin/env python3
"""Immutable streaming reporting recovery for #86 Gate B.

This runner is intentionally limited to the PI-verified, locked prediction CSV.
It never reads the source database, features, models, or outcome tables and
cannot generate predictions.  It reproduces the v3.1 reporting schemas while
keeping only sufficient statistics per issue for the clustered bootstrap.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import resource
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


ISSUE = 86
OUTCOMES = ("3", "1", "0")
OUTCOME_INDEX = {code: index for index, code in enumerate(OUTCOMES)}
CALIBRATION_BOUNDS = (0.0, 0.35, 0.45, 0.55, 0.65, 0.75, 1.0000001)
PREDICTION_FIELDS = [
    "snapshot", "devig", "eval_year", "issue", "match_id", "kickoff_ts", "native_line", "outcome",
    "arm", "p3", "p1", "p0", "market_raw_home", "market_raw_draw", "market_raw_away",
    "strength_mu", "market_mu_status", "delta_p3", "delta_p1", "delta_p0", "delta_margin",
    "history_depth", "history_uncertainty", "disagreement_bucket", "value_status", "arbitrage_status",
]
METRIC_FIELDS = [
    "snapshot", "devig", "arm", "view", "view_value", "n", "logloss", "brier", "top1_hit", "top2_hit",
    "mean_top1_probability", "actual_top1_hit", "top1_calibration_gap", "mean_top2_probability",
    "actual_top2_coverage", "top2_calibration_gap", "top1_calibration_intercept", "top1_calibration_slope",
]
PAIR_FIELDS = ["snapshot", "devig", "arm", "eval_year", "n", "delta_logloss", "delta_brier"]
UNCERTAINTY_FIELDS = ["snapshot", "devig", "arm", "cluster", "clusters", "bootstrap_reps", "seed", "logloss_p025", "logloss_p975"]
BASELINE = "M0_CONTINUOUS_EURO_BJLINE"
ARMS = (
    BASELINE,
    "S0_LEGACY_TEAM_FORM_POISSON",
    "S1_OPPONENT_ADJUSTED_STRENGTH",
    "S2_STRENGTH_SCORE_DISTRIBUTION",
    "F1_MARKET_PLUS_STRENGTH_RESIDUAL",
)
EXPECTED_INPUT_SHA256 = "8b26fbbdcdafb6aaeff398ee85342a279b71b9f5789357da78b67274e8b93af2"
ACCEPTED_OLD_SUMMARIZER_SHA256 = "dcc5912c0e8040a829367e3bcc559a82e08a632e5bdc1a833b5ee9380e1ffb26"
EXPECTED_DATA_ROWS = 6_881_040


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verify_old_summarizer(path: Path) -> str:
    """Bind synthetic equivalence to the one PI-accepted v3.1 authority."""
    actual = sha256(path)
    if actual != ACCEPTED_OLD_SUMMARIZER_SHA256:
        raise RuntimeError(
            "accepted old-summarizer hash mismatch: "
            f"expected={ACCEPTED_OLD_SUMMARIZER_SHA256} actual={actual}"
        )
    return actual


class Metric:
    """Byte-compatible copy of the accepted v3.1 reporting accumulator."""

    def __init__(self) -> None:
        self.n = 0
        self.ll = self.br = self.top1 = self.top2 = self.conf = self.top2mass = 0.0
        self.conf_sq = self.conf_hit = 0.0

    def add(self, row: dict[str, str]) -> float:
        p = np.asarray([float(row[key]) for key in ("p3", "p1", "p0")])
        y = OUTCOME_INDEX[row["outcome"]]
        order = np.argsort(-p)
        logloss = -math.log(max(p[y], 1e-12))
        self.n += 1
        self.ll += logloss
        self.br += float(np.sum((p - np.eye(3)[y]) ** 2))
        self.top1 += float(order[0] == y)
        self.top2 += float(y in order[:2])
        confidence, top2_mass = float(p[order[0]]), float(p[order[0]] + p[order[1]])
        self.conf += confidence
        self.top2mass += top2_mass
        self.conf_sq += confidence * confidence
        self.conf_hit += confidence * float(order[0] == y)
        return logloss

    def record(self, base: dict[str, object]) -> dict[str, object]:
        mean_conf, hit = self.conf / self.n, self.top1 / self.n
        variance = self.conf_sq / self.n - mean_conf * mean_conf
        slope = 0.0 if variance <= 0 else (self.conf_hit / self.n - mean_conf * hit) / variance
        return {
            **base,
            "n": self.n,
            "logloss": self.ll / self.n,
            "brier": self.br / self.n,
            "top1_hit": hit,
            "top2_hit": self.top2 / self.n,
            "mean_top1_probability": mean_conf,
            "actual_top1_hit": hit,
            "top1_calibration_gap": hit - mean_conf,
            "mean_top2_probability": self.top2mass / self.n,
            "actual_top2_coverage": self.top2 / self.n,
            "top2_calibration_gap": self.top2 / self.n - self.top2mass / self.n,
            "top1_calibration_intercept": hit - slope * mean_conf,
            "top1_calibration_slope": slope,
        }


def probability_values(row: dict[str, str]) -> tuple[np.ndarray, int, np.ndarray]:
    p = np.asarray([float(row[key]) for key in ("p3", "p1", "p0")])
    y = OUTCOME_INDEX[row["outcome"]]
    return p, y, np.eye(3)[y]


def add_pair(pairs: dict[tuple[str, str, str, str], list[float]], arms: dict[str, dict[str, str]]) -> None:
    baseline = arms.get(BASELINE)
    if not baseline:
        return
    bp, y, one_hot = probability_values(baseline)
    for arm, row in arms.items():
        if arm == BASELINE:
            continue
        cp, _, _ = probability_values(row)
        key = (row["snapshot"], row["devig"], arm, row["eval_year"])
        pairs[key][0] += 1
        pairs[key][1] += -math.log(max(cp[y], 1e-12)) + math.log(max(bp[y], 1e-12))
        pairs[key][2] += float(np.sum((cp - one_hot) ** 2 - (bp - one_hot) ** 2))


def calibration_bucket(row: dict[str, str]) -> str:
    p = np.asarray([float(row[key]) for key in ("p3", "p1", "p0")])
    confidence = float(p[np.argmax(p)])
    return next(
        f"{CALIBRATION_BOUNDS[index]:.2f}-{CALIBRATION_BOUNDS[index + 1]:.2f}"
        for index in range(len(CALIBRATION_BOUNDS) - 1)
        if CALIBRATION_BOUNDS[index] <= confidence < CALIBRATION_BOUNDS[index + 1]
    )


def summarize(input_path: Path, output: Path, *, strict: bool = True) -> dict[str, object]:
    groups: dict[tuple[str, str, str, str, str], Metric] = defaultdict(Metric)
    calibration: dict[tuple[str, str, str, str], Metric] = defaultdict(Metric)
    pairs: dict[tuple[str, str, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    # group -> insertion-ordered issue -> exact sufficient (n, sum_logloss)
    issue_stats: dict[tuple[str, str, str], dict[str, list[float]]] = defaultdict(dict)
    rows = 0
    malformed = 0
    full_strata: Counter[tuple[str, str, str, str]] = Counter()
    base_arms: dict[tuple[str, str, str], Counter[str]] = defaultdict(Counter)
    last_row: dict[str, str] | None = None
    current_key: tuple[str, str, str] | None = None
    current_arms: dict[str, dict[str, str]] = {}

    with input_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != PREDICTION_FIELDS:
            raise RuntimeError(f"prediction schema mismatch: {reader.fieldnames!r}")
        for row in reader:
            rows += 1
            if None in row or any(row.get(field) is None for field in PREDICTION_FIELDS):
                malformed += 1
                continue
            if row["arm"] not in ARMS or row["outcome"] not in OUTCOME_INDEX:
                malformed += 1
                continue
            key = (row["snapshot"], row["devig"], row["match_id"])
            if current_key is not None and key != current_key:
                if strict and set(current_arms) != set(ARMS):
                    raise RuntimeError(f"five-arm match buffer mismatch for {current_key}: {sorted(current_arms)}")
                add_pair(pairs, current_arms)
                current_arms = {}
            current_key = key
            if row["arm"] in current_arms:
                raise RuntimeError(f"duplicate arm in match buffer: {key}/{row['arm']}")
            current_arms[row["arm"]] = row
            depth = float(row["history_depth"])
            views = (
                ("OVERALL", "ALL"),
                ("YEAR", row["eval_year"]),
                ("NATIVE_LINE", row["native_line"]),
                ("DISAGREEMENT", row["disagreement_bucket"]),
                ("HISTORY_DEPTH", "0" if depth == 0 else "1to9" if depth < 10 else "10plus"),
            )
            logloss = None
            for view, value in views:
                observed = groups[(row["snapshot"], row["devig"], row["arm"], view, value)].add(row)
                if logloss is None:
                    logloss = observed
            calibration[(row["snapshot"], row["devig"], row["arm"], calibration_bucket(row))].add(row)
            issue_key = (row["snapshot"], row["devig"], row["arm"])
            stats = issue_stats[issue_key].setdefault(row["issue"], [0.0, 0.0])
            stats[0] += 1
            stats[1] += float(logloss)
            full_strata[(row["snapshot"], row["devig"], row["eval_year"], row["arm"])] += 1
            base_arms[(row["snapshot"], row["devig"], row["eval_year"])][row["arm"]] += 1
            last_row = row
    if current_key is not None:
        if strict and set(current_arms) != set(ARMS):
            raise RuntimeError(f"five-arm final match buffer mismatch for {current_key}: {sorted(current_arms)}")
        add_pair(pairs, current_arms)

    if malformed:
        raise RuntimeError(f"malformed prediction rows: {malformed}")
    if strict and rows != EXPECTED_DATA_ROWS:
        raise RuntimeError(f"prediction row count mismatch: {rows} != {EXPECTED_DATA_ROWS}")
    if strict and (len(full_strata) != 450 or len(base_arms) != 90):
        raise RuntimeError(f"strata mismatch: full={len(full_strata)} base={len(base_arms)}")
    if strict and any(set(counts) != set(ARMS) or len(set(counts.values())) != 1 for counts in base_arms.values()):
        raise RuntimeError("equal-arm check failed")
    final_key = ("1h", "power", "2025", "F1_MARKET_PLUS_STRENGTH_RESIDUAL")
    if strict and (last_row is None or tuple(last_row[field] for field in ("snapshot", "devig", "eval_year", "arm")) != final_key):
        raise RuntimeError(f"final-stratum check failed: {last_row}")

    metrics = [
        metric.record({"snapshot": snapshot, "devig": method, "arm": arm, "view": view, "view_value": value})
        for (snapshot, method, arm, view, value), metric in sorted(groups.items())
    ]
    write_csv(output / "probability_metrics.csv", metrics, METRIC_FIELDS)
    calibration_rows = [
        metric.record({"snapshot": snapshot, "devig": method, "arm": arm, "view": "TOP1_CONFIDENCE_BUCKET", "view_value": bucket})
        for (snapshot, method, arm, bucket), metric in sorted(calibration.items())
    ]
    write_csv(output / "calibration.csv", calibration_rows, METRIC_FIELDS)
    pair_rows = [
        {"snapshot": snapshot, "devig": method, "arm": arm, "eval_year": year, "n": int(values[0]), "delta_logloss": values[1] / values[0], "delta_brier": values[2] / values[0]}
        for (snapshot, method, arm, year), values in sorted(pairs.items())
    ]
    write_csv(output / "paired_differences.csv", pair_rows, PAIR_FIELDS)

    rng, uncertainty_rows = np.random.default_rng(86), []
    for (snapshot, method, arm), values in sorted(issue_stats.items()):
        issues = list(values)
        sizes = np.asarray([values[issue][0] for issue in issues], dtype=float)
        losses = np.asarray([values[issue][1] for issue in issues], dtype=float)
        means = []
        for _ in range(500):
            picked = rng.integers(0, len(issues), len(issues))
            means.append(float(losses[picked].sum() / sizes[picked].sum()))
        uncertainty_rows.append({
            "snapshot": snapshot, "devig": method, "arm": arm, "cluster": "issue", "clusters": len(issues),
            "bootstrap_reps": 500, "seed": 86, "logloss_p025": float(np.quantile(means, .025)), "logloss_p975": float(np.quantile(means, .975)),
        })
    write_csv(output / "uncertainty.csv", uncertainty_rows, UNCERTAINTY_FIELDS)
    availability = [
        {"arm": "V1_CROSS_MARKET_VALUE", "status": "QUOTED_BJDC_SP_UNAVAILABLE", "ranking_views": "probability_only|raw_quoted_sp_ev|min_quoted_sp_5_ev|conservative_retention_ev", "settlement": "NOT_RUN"},
        {"arm": "A1_LOCKED_ARBITRAGE_FEASIBILITY", "status": "NO_LOCKED_ARBITRAGE_AUTHORITY", "ranking_views": "", "settlement": "NOT_RUN"},
    ]
    write_csv(output / "sp_value_diagnostics.csv", availability, ["arm", "status", "ranking_views", "settlement"])
    write_csv(output / "arbitrage_provenance.csv", availability[1:], ["arm", "status", "ranking_views", "settlement"])
    return {
        "data_rows": rows,
        "schema_width": len(PREDICTION_FIELDS),
        "malformed_rows": malformed,
        "full_strata": len(full_strata),
        "base_strata": len(base_arms),
        "equal_arm_check": "PASS",
        "final_stratum": "/".join(final_key),
    }


def load_old_runner(path: Path):
    spec = importlib.util.spec_from_file_location("bj86_v31_old", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load old summarizer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_equivalence(old_runner: Path, output: Path) -> dict[str, object]:
    actual_old_runner_sha256 = verify_old_summarizer(old_runner)
    with tempfile.TemporaryDirectory(prefix="bj86-streaming-") as temp:
        root = Path(temp)
        old, new = root / "old", root / "new"
        old.mkdir(); new.mkdir()
        rows: list[dict[str, str]] = []
        for issue in ("I1", "I2", "I3"):
            for arm, probs in ((BASELINE, (.5, .3, .2)), ("S2_STRENGTH_SCORE_DISTRIBUTION", (.45, .35, .2))):
                rows.append({"snapshot": "1h", "devig": "proportional", "eval_year": "2016", "issue": issue, "match_id": issue, "kickoff_ts": "2016-01-01", "native_line": "0.00", "outcome": "3", "arm": arm, "p3": str(probs[0]), "p1": str(probs[1]), "p0": str(probs[2]), "market_raw_home": ".5", "market_raw_draw": ".3", "market_raw_away": ".2", "strength_mu": "0", "market_mu_status": "UNIDENTIFIED", "delta_p3": "0", "delta_p1": "0", "delta_p0": "0", "delta_margin": "", "history_depth": "0", "history_uncertainty": "1", "disagreement_bucket": "TOP1_AGREE", "value_status": "UNAVAILABLE", "arbitrage_status": "UNAVAILABLE"})
        write_csv(old / "prediction_rows.csv", rows, PREDICTION_FIELDS)
        shutil.copyfile(old / "prediction_rows.csv", new / "prediction_rows.csv")
        old_module = load_old_runner(old_runner)
        old_module.summarize_prediction_rows(old)
        # Fixture has 6 rather than production rows; invoke same streaming formulas with its contractual checks disabled.
        summary = summarize(new / "prediction_rows.csv", new, strict=False)
        fields = ["probability_metrics.csv", "calibration.csv", "paired_differences.csv", "uncertainty.csv", "sp_value_diagnostics.csv", "arbitrage_provenance.csv"]
        equal = {name: sha256(old / name) == sha256(new / name) for name in fields}
        if not all(equal.values()):
            raise RuntimeError(f"synthetic byte comparison failed: {equal}")
        wrong_runner = root / "wrong_old_summarizer.py"
        wrong_runner.write_bytes(old_runner.read_bytes() + b"\n# deterministic wrong-runner fixture\n")
        try:
            verify_old_summarizer(wrong_runner)
        except RuntimeError as error:
            wrong_runner_rejected = "accepted old-summarizer hash mismatch" in str(error)
        else:
            wrong_runner_rejected = False
        if not wrong_runner_rejected:
            raise RuntimeError("wrong old-summarizer fixture was not rejected")
        receipt = {
            "status": "PASS",
            "old_runner_expected_sha256": ACCEPTED_OLD_SUMMARIZER_SHA256,
            "old_runner_actual_sha256": actual_old_runner_sha256,
            "wrong_runner_rejected": wrong_runner_rejected,
            "files_byte_identical": equal,
            "fixture_rows": len(rows),
            "streaming_fixture_summary": summary,
        }
        (output / "synthetic_equivalence_receipt.json").write_text(dump(receipt) + "\n", encoding="utf-8")
        return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--old-runner", type=Path, required=True)
    args = parser.parse_args()
    input_path, output, old_runner = args.input.resolve(), args.output.resolve(), args.old_runner.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite {output}")
    if sha256(input_path) != EXPECTED_INPUT_SHA256:
        raise SystemExit("locked prediction CSV hash mismatch")
    actual_old_runner_sha256 = verify_old_summarizer(old_runner)
    output.mkdir(parents=True)
    copied_runner = output / Path(__file__).name
    copied_runner.write_bytes(Path(__file__).read_bytes())
    config = {
        "issue": ISSUE,
        "stage": "gate_b_streaming_summary_recovery",
        "authorization": "PI streaming-summary recovery; do not rerun predictions",
        "locked_prediction": {"path": str(input_path), "sha256": EXPECTED_INPUT_SHA256, "expected_data_rows": EXPECTED_DATA_ROWS, "fields": PREDICTION_FIELDS},
        "reporting": {"metric_schema": METRIC_FIELDS, "issue_bootstrap": {"replicates": 500, "seed": 86, "percentiles": [0.025, 0.975], "sufficient_statistics": ["n", "sum_logloss"]}, "V1": "QUOTED_BJDC_SP_UNAVAILABLE", "A1": "NO_LOCKED_ARBITRAGE_AUTHORITY"},
        "runner_sha256": sha256(copied_runner),
        "old_summarizer": {
            "expected_sha256": ACCEPTED_OLD_SUMMARIZER_SHA256,
            "actual_sha256": actual_old_runner_sha256,
        },
    }
    (output / "summary_recovery_config.json").write_text(dump(config) + "\n", encoding="utf-8")
    synthetic_equivalence(old_runner, output)
    summary = summarize(input_path, output)
    integrity = {"issue": ISSUE, "stage": "locked_prediction_integrity", "prediction_path": str(input_path), "prediction_sha256": EXPECTED_INPUT_SHA256, "expected_data_rows": EXPECTED_DATA_ROWS, "actual_data_rows": summary["data_rows"], "schema_width": summary["schema_width"], "malformed_rows": summary["malformed_rows"], "snapshot_devig_year_arm_strata": summary["full_strata"], "snapshot_devig_year_base_strata": summary["base_strata"], "equal_arm_check": summary["equal_arm_check"], "final_stratum": summary["final_stratum"]}
    (output / "prediction_integrity_receipt.json").write_text(dump(integrity) + "\n", encoding="utf-8")
    run = {"issue": ISSUE, "stage": "gate_b_streaming_summary", "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, "prediction_integrity_receipt_sha256": sha256(output / "prediction_integrity_receipt.json")}
    (output / "streaming_run_receipt.json").write_text(dump(run) + "\n", encoding="utf-8")
    names = ["probability_metrics.csv", "calibration.csv", "paired_differences.csv", "uncertainty.csv", "sp_value_diagnostics.csv", "arbitrage_provenance.csv", "prediction_integrity_receipt.json", "streaming_run_receipt.json", "synthetic_equivalence_receipt.json", "summary_recovery_config.json", copied_runner.name]
    manifest = {name: sha256(output / name) for name in names}
    (output / "summary_manifest.json").write_text(dump(manifest) + "\n", encoding="utf-8")
    manifest["summary_manifest.json"] = sha256(output / "summary_manifest.json")
    (output / "SHA256SUMS.json").write_text(dump(manifest) + "\n", encoding="utf-8")
    print(dump({"output": str(output), "manifest_sha256": sha256(output / "SHA256SUMS.json"), "peak_rss_kb": run["peak_rss_kb"]}))


if __name__ == "__main__":
    main()
