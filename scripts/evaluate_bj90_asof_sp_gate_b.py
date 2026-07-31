#!/usr/bin/env python3
"""Fixed chronological M0/M1/M2 price-vector evaluation for #90 Gate B.

The runner never opens SQLite: every later-price label comes solely from the
immutable, one-query Gate-B ledger.  It streams the OOS prediction CSV and
keeps only sufficient statistics, so reporting cannot exhaust memory.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = root()
FREEZE = ROOT / "results/bj90_gate_a_preoutcome_v4"
LEDGER = ROOT / "results/bj90_gate_b_target_ledger_v2"
OUT = ROOT / "results/bj90_gate_b_price_vectors_v4"
CODES = ("3", "1", "0")
LAMBDA = 10.0
NUMERIC_DIM = 42


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_manifest(bundle: Path) -> str:
    declared = json.loads((bundle / "SHA256SUMS.json").read_text())
    actual = {p.name: sha256(p) for p in bundle.iterdir() if p.is_file() and p.name != "SHA256SUMS.json"}
    if actual != declared:
        raise RuntimeError(f"manifest mismatch: {bundle}")
    return sha256(bundle / "SHA256SUMS.json")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def logclip(value: object) -> float:
    try:
        return math.log(max(0.01, float(value)))
    except (TypeError, ValueError):
        return math.log(0.01)


def minute_of_day(kickoff_ts: str) -> int:
    return int(kickoff_ts[11:13]) * 60 + int(kickoff_ts[14:16])


def numeric_features(row: dict[str, str]) -> list[float]:
    values: list[float] = []
    for market in ("euro", "asian", "ou"):
        for position in ("1", "2", "3"):
            if market in ("asian", "ou") and position == "2":
                values.extend([
                    float(row[f"{market}_v2"]),
                    float(row[f"{market}_i_v2"]),
                    float(row[f"{market}_v2"]) - float(row[f"{market}_i_v2"]),
                    float(row[f"{market}_max2"]) - float(row[f"{market}_min2"]),
                ])
            else:
                values.extend([
                    logclip(row[f"{market}_v{position}"]),
                    logclip(row[f"{market}_i_v{position}"]),
                    logclip(row[f"{market}_v{position}"]) - logclip(row[f"{market}_i_v{position}"]),
                    logclip(row[f"{market}_max{position}"]) - logclip(row[f"{market}_min{position}"]),
                ])
    values.extend(math.log1p(max(0.0, float(row[f"{market}_n"]))) for market in ("euro", "asian", "ou"))
    values.append(float(row["handicap_line_norm"]))
    angle = 2.0 * math.pi * minute_of_day(row["kickoff_ts"]) / 1440.0
    values.extend((math.sin(angle), math.cos(angle)))
    if len(values) != NUMERIC_DIM:
        raise RuntimeError(f"feature dimension drift: {len(values)}")
    if not all(math.isfinite(value) for value in values):
        raise RuntimeError(f"non-finite feature: match_id={row['match_id']}")
    return values


def league_of(row: dict[str, str]) -> str:
    return row["league"] or "__MISSING__"


def design(train: list[dict[str, str]], test: list[dict[str, str]]) -> tuple[np.ndarray, np.ndarray]:
    """Dense reference design used by the deterministic one-hot regression test.

    Production fitting below uses an algebraically identical streamed normal
    equation.  The explicit zero initialization is intentional: unseen test
    leagues must retain an all-zero one-hot block.
    """
    raw = np.asarray([numeric_features(row) for row in train], dtype=float)
    mean = raw.mean(axis=0)
    sd = raw.std(axis=0)
    sd[sd == 0.0] = 1.0
    leagues = sorted({league_of(row) for row in train})
    index = {league: position for position, league in enumerate(leagues)}

    def encode(rows: list[dict[str, str]]) -> np.ndarray:
        matrix = np.zeros((len(rows), 1 + NUMERIC_DIM + len(leagues)), dtype=float)
        matrix[:, 0] = 1.0
        for position, row in enumerate(rows):
            matrix[position, 1 : 1 + NUMERIC_DIM] = (np.asarray(numeric_features(row)) - mean) / sd
            known = index.get(league_of(row))
            if known is not None:
                matrix[position, 1 + NUMERIC_DIM + known] = 1.0
        return matrix

    return encode(train), encode(test)


def fit_m1(train: list[dict[str, str]]) -> dict[str, object]:
    raw = np.asarray([numeric_features(row) for row in train], dtype=float)
    mean = raw.mean(axis=0)
    sd = raw.std(axis=0)
    sd[sd == 0.0] = 1.0
    dense = np.empty((len(train), 1 + NUMERIC_DIM), dtype=float)
    dense[:, 0] = 1.0
    dense[:, 1:] = (raw - mean) / sd
    y = np.log(np.asarray([[row["y3"], row["y1"], row["y0"]] for row in train], dtype=float))
    leagues = sorted({league_of(row) for row in train})
    league_index = {league: position for position, league in enumerate(leagues)}
    observed = np.asarray([league_index[league_of(row)] for row in train], dtype=int)
    d = dense.shape[1]
    l = len(leagues)
    cross = np.zeros((d, l), dtype=float)
    y_by_league = np.zeros((l, len(CODES)), dtype=float)
    counts = np.bincount(observed, minlength=l).astype(float)
    for position in range(l):
        mask = observed == position
        if mask.any():
            cross[:, position] = dense[mask].sum(axis=0)
            y_by_league[position] = y[mask].sum(axis=0)
    normal = np.zeros((d + l, d + l), dtype=float)
    normal[:d, :d] = dense.T @ dense
    normal[:d, d:] = cross
    normal[d:, :d] = cross.T
    normal[d:, d:] = np.diag(counts)
    normal[np.diag_indices_from(normal)] += LAMBDA
    normal[0, 0] -= LAMBDA  # unpenalized intercept
    rhs = np.zeros((d + l, len(CODES)), dtype=float)
    rhs[:d] = dense.T @ y
    rhs[d:] = y_by_league
    beta = np.linalg.solve(normal, rhs)
    return {"mean": mean, "sd": sd, "league_index": league_index, "beta_dense": beta[:d], "beta_league": beta[d:]}


def predict_m1(model: dict[str, object], row: dict[str, str]) -> np.ndarray:
    raw = np.asarray(numeric_features(row), dtype=float)
    dense = np.concatenate(([1.0], (raw - model["mean"]) / model["sd"]))
    fitted = dense @ model["beta_dense"]
    known = model["league_index"].get(league_of(row))
    if known is not None:
        fitted = fitted + model["beta_league"][known]
    return np.exp(np.clip(fitted, -10.0, 10.0))


def ranks(values: np.ndarray) -> np.ndarray:
    return np.argsort(np.argsort(-np.asarray(values), kind="stable"), kind="stable")


def errors(prediction: np.ndarray, actual: np.ndarray) -> tuple[float, float]:
    return float(np.mean(np.abs(np.log(prediction) - np.log(actual)))), float(np.mean(np.abs(ranks(prediction) - ranks(actual))))


def issue_mean(stats: dict[str, list[float]], index: int) -> float:
    if not stats:
        raise RuntimeError("empty issue metric")
    return sum(values[index] / values[0] for values in stats.values()) / len(stats)


def add_issue(stats: dict[str, list[float]], issue: str, logmae: float, rankdisp: float) -> None:
    values = stats.setdefault(issue, [0.0, 0.0, 0.0])
    values[0] += 1.0
    values[1] += logmae
    values[2] += rankdisp


def sp_band(value: float) -> str:
    if value < 2.0:
        return "LT2"
    if value < 3.0:
        return "2_3"
    if value < 5.0:
        return "3_5"
    if value < 10.0:
        return "5_10"
    return "GE10"


def asian_dispersion(row: dict[str, str]) -> str:
    value = (logclip(row["asian_max1"]) - logclip(row["asian_min1"]) + logclip(row["asian_max3"]) - logclip(row["asian_min3"])) / 2.0
    return "LOW_LE_005" if value <= 0.05 else ("MID_LE_015" if value <= 0.15 else "HIGH_GT_015")


PREDICTION_FIELDS = [
    "match_id", "issue", "match_idx", "year", "fold", "league", "handicap_line_norm", "asian_min1", "asian_max1", "asian_min3", "asian_max3",
    "y3", "y1", "y0", "m0_3", "m0_1", "m0_0", "m1_3", "m1_1", "m1_0", "m2_3", "m2_1", "m2_0", "deployed_method",
    "m0_logmae", "m0_rankdisp", "m1_logmae", "m1_rankdisp", "m2_logmae", "m2_rankdisp", "deployed_logmae", "deployed_rankdisp",
]


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite immutable output: {OUT}")
    stage = Path(tempfile.mkdtemp(prefix="bj90-eval-v4-", dir=OUT.parent))
    try:
        gate_a_manifest = verify_manifest(FREEZE)
        ledger_manifest = verify_manifest(LEDGER)
        rows = read_csv(FREEZE / "frozen_preoutcome_rows.csv")
        ledger = read_csv(LEDGER / "official_sp_target_ledger.csv")
        if len(rows) != 119_976 or len(ledger) != len(rows):
            raise RuntimeError("unexpected frozen or ledger row count")
        targets = {row["match_id"]: row for row in ledger}
        if len(targets) != len(rows) or set(targets) != {row["match_id"] for row in rows}:
            raise RuntimeError("ledger identity coverage mismatch")
        evaluable: list[dict[str, str]] = []
        availability: dict[tuple[str, str], int] = defaultdict(int)
        for row in rows:
            target = targets[row["match_id"]]
            availability[(row["year"], target["target_reason"])] += 1
            if target["target_reason"] == "AVAILABLE_POSITIVE":
                row.update(y3=target["sp_3"], y1=target["sp_1"], y0=target["sp_0"])
                evaluable.append(row)
        if len(evaluable) != 117_801:
            raise RuntimeError(f"unexpected complete-case cohort: {len(evaluable)}")

        prior_m0: dict[str, list[float]] = {}
        prior_m1: dict[str, list[float]] = {}
        all_m0: dict[str, list[float]] = {}
        all_policy: dict[str, list[float]] = {}
        yearly_issues: dict[int, dict[str, dict[str, list[float]]]] = defaultdict(lambda: {"m0": {}, "m1": {}, "policy": {}})
        residuals: list[list[float]] = [[], [], []]
        tail: dict[tuple[int, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        coverage: dict[tuple[int, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
        code_metrics: dict[tuple[int, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
        slices: dict[tuple[str, str, str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        decisions: list[dict[str, object]] = []

        with (stage / "oos_predictions.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=PREDICTION_FIELDS)
            writer.writeheader()
            for year in range(2019, 2026):
                train = [row for row in evaluable if int(row["year"]) < year]
                test = [row for row in evaluable if int(row["year"]) == year]
                if not train or not test:
                    raise RuntimeError(f"empty complete-case expanding fold {year}")
                model = fit_m1(train)
                if year == 2019:
                    chosen = "M0_EURO_10H"
                else:
                    choices = [
                        (issue_mean(prior_m0, 1), issue_mean(prior_m0, 2), "M0_EURO_10H"),
                        (issue_mean(prior_m1, 1), issue_mean(prior_m1, 2), "M1_RIDGE_LOG_SP"),
                    ]
                    chosen = min(choices, key=lambda item: (item[0], item[1], 0 if item[2].startswith("M0") else 1))[2]
                decisions.append({"year": year, "method": chosen, "prior_oos_years": "" if year == 2019 else f"2019-{year - 1}"})
                shift = np.asarray([sorted(values)[math.floor(0.20 * (len(values) - 1))] if values else 0.0 for values in residuals])
                for row in test:
                    actual = np.asarray([float(row["y3"]), float(row["y1"]), float(row["y0"])])
                    m0 = np.asarray([max(0.01, float(row["euro_v1"])), max(0.01, float(row["euro_v2"])), max(0.01, float(row["euro_v3"]))])
                    m1 = predict_m1(model, row)
                    m2 = m1 * np.exp(shift)
                    deployed = m0 if chosen.startswith("M0") else m1
                    m0_log, m0_rank = errors(m0, actual)
                    m1_log, m1_rank = errors(m1, actual)
                    m2_log, m2_rank = errors(m2, actual)
                    deployed_log, deployed_rank = errors(deployed, actual)
                    record = {
                        "match_id": row["match_id"], "issue": row["issue"], "match_idx": row["match_idx"], "year": row["year"], "fold": row["fold"],
                        "league": row["league"], "handicap_line_norm": row["handicap_line_norm"], "asian_min1": row["asian_min1"], "asian_max1": row["asian_max1"], "asian_min3": row["asian_min3"], "asian_max3": row["asian_max3"],
                        "y3": actual[0], "y1": actual[1], "y0": actual[2], "m0_3": m0[0], "m0_1": m0[1], "m0_0": m0[2], "m1_3": m1[0], "m1_1": m1[1], "m1_0": m1[2], "m2_3": m2[0], "m2_1": m2[1], "m2_0": m2[2],
                        "deployed_method": chosen, "m0_logmae": m0_log, "m0_rankdisp": m0_rank, "m1_logmae": m1_log, "m1_rankdisp": m1_rank, "m2_logmae": m2_log, "m2_rankdisp": m2_rank, "deployed_logmae": deployed_log, "deployed_rankdisp": deployed_rank,
                    }
                    writer.writerow(record)
                    add_issue(prior_m0, row["issue"], m0_log, m0_rank)
                    add_issue(prior_m1, row["issue"], m1_log, m1_rank)
                    add_issue(all_m0, row["issue"], m0_log, m0_rank)
                    add_issue(all_policy, row["issue"], deployed_log, deployed_rank)
                    add_issue(yearly_issues[year]["m0"], row["issue"], m0_log, m0_rank)
                    add_issue(yearly_issues[year]["m1"], row["issue"], m1_log, m1_rank)
                    add_issue(yearly_issues[year]["policy"], row["issue"], deployed_log, deployed_rank)
                    for index, code in enumerate(CODES):
                        residuals[index].append(math.log(actual[index]) - math.log(m1[index]))
                        if actual[index] >= 5.0:
                            stats = tail[(year, code)]
                            stats[0] += 1.0
                            stats[1] += abs(math.log(m0[index]) - math.log(actual[index]))
                            stats[2] += abs(math.log(m1[index]) - math.log(actual[index]))
                        covered = coverage[(year, code)]
                        covered[0] += 1.0
                        covered[1] += float(actual[index] >= m2[index])
                        for name, vector in (("M0", m0), ("M1", m1), ("M2", m2)):
                            metric = code_metrics[(year, name, code)]
                            metric[0] += 1.0
                            metric[1] += abs(math.log(vector[index]) - math.log(actual[index]))
                        for name, vector in (("M0", m0), ("M1", m1), ("M2", m2), ("DEPLOYED", deployed)):
                            error = abs(math.log(vector[index]) - math.log(actual[index]))
                            for dimension, value in (("sp_band", sp_band(actual[index])), ("league", league_of(row)), ("bj_line", str(row["handicap_line_norm"])), ("asian_dispersion", asian_dispersion(row))):
                                summary = slices[(name, code, dimension, value)]
                                summary[0] += 1.0
                                summary[1] += error
                                summary[2] += vector[index] - actual[index]

        choices = [
            (issue_mean(prior_m0, 1), issue_mean(prior_m0, 2), "M0_EURO_10H"),
            (issue_mean(prior_m1, 1), issue_mean(prior_m1, 2), "M1_RIDGE_LOG_SP"),
        ]
        next_method = min(choices, key=lambda item: (item[0], item[1], 0 if item[2].startswith("M0") else 1))[2]
        decisions.append({"year": "NEXT_PERIOD", "method": next_method, "prior_oos_years": "2019-2025"})
        yearly = []
        for year in range(2019, 2026):
            policy = yearly_issues[year]["policy"]
            m0 = yearly_issues[year]["m0"]
            m1 = yearly_issues[year]["m1"]
            yearly.append({
                "year": year, "policy_logmae": issue_mean(policy, 1), "m0_logmae": issue_mean(m0, 1), "m1_logmae": issue_mean(m1, 1),
                "policy_rankdisp": issue_mean(policy, 2), "m0_rankdisp": issue_mean(m0, 2), "m1_rankdisp": issue_mean(m1, 2),
                "policy_no_worse_logmae": issue_mean(policy, 1) <= issue_mean(m0, 1),
            })
        tail_rows = [{"year": year, "code": code, "target_sp_ge_5_n": int(stats[0]), "m0_logmae": stats[1] / stats[0] if stats[0] else "", "m1_logmae": stats[2] / stats[0] if stats[0] else ""} for (year, code), stats in sorted(tail.items())]
        nonempty_tail = [row for row in tail_rows if row["target_sp_ge_5_n"]]
        tail_n = sum(row["target_sp_ge_5_n"] for row in nonempty_tail)
        high_m0 = sum(float(row["m0_logmae"]) * row["target_sp_ge_5_n"] for row in nonempty_tail) / tail_n
        high_m1 = sum(float(row["m1_logmae"]) * row["target_sp_ge_5_n"] for row in nonempty_tail) / tail_n
        summary = {
            "frozen_preoutcome_n": len(rows), "evaluable_complete_case_n": len(evaluable), "next_period_method": next_method,
            "policy_logmae": issue_mean(all_policy, 1), "m0_logmae_same": issue_mean(all_m0, 1),
            "policy_rankdisp": issue_mean(all_policy, 2), "m0_rankdisp_same": issue_mean(all_m0, 2),
            "years_logmae_no_worse_than_m0": sum(row["policy_no_worse_logmae"] for row in yearly),
            "high_sp_ge5_m0_logmae": high_m0, "high_sp_ge5_m1_logmae": high_m1,
        }
        promote = next_method.startswith("M1") and summary["policy_logmae"] < summary["m0_logmae_same"] and summary["policy_rankdisp"] < summary["m0_rankdisp_same"] and summary["years_logmae_no_worse_than_m0"] >= 4 and high_m1 <= high_m0
        summary["decision"] = "PROMOTABLE_CANDIDATE" if promote else "NO_PROMOTION"
        availability_rows = [{"year": year, "target_reason": reason, "n": n} for (year, reason), n in sorted(availability.items(), key=lambda item: (int(item[0][0]), item[0][1]))]
        coverage_rows = [{"year": year, "code": code, "n": int(stats[0]), "m2_conservative_coverage": stats[1] / stats[0]} for (year, code), stats in sorted(coverage.items())]
        code_rows = [{"year": year, "method": method, "code": code, "n": int(stats[0]), "logmae": stats[1] / stats[0]} for (year, method, code), stats in sorted(code_metrics.items())]
        slice_rows = [{"method": method, "code": code, "dimension": dimension, "slice": value, "n": int(stats[0]), "logmae": stats[1] / stats[0], "mean_prediction_minus_target": stats[2] / stats[0]} for (method, code, dimension, value), stats in sorted(slices.items())]
        write_csv(stage / "selector_decisions.csv", decisions)
        write_csv(stage / "summary.csv", [summary])
        write_csv(stage / "metrics_by_year.csv", yearly)
        write_csv(stage / "high_sp_tail.csv", tail_rows)
        write_csv(stage / "m2_coverage.csv", coverage_rows)
        write_csv(stage / "code_logmae.csv", code_rows)
        write_csv(stage / "diagnostic_slices.csv", slice_rows)
        write_csv(stage / "target_availability_by_year.csv", availability_rows)
        shutil.copyfile(__file__, stage / "evaluation_runner.py")
        card = {
            "issue": 90, "stage": "GATE_B_FIXED_CHRONOLOGICAL_PRICE_EVALUATION", "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "gate_a_manifest_sha256": gate_a_manifest, "ledger_manifest_sha256": ledger_manifest,
            "inputs": "Gate-A v4 target-unexposed rows plus Gate-B v2 one-query official-SP ledger; complete case only where target_reason=AVAILABLE_POSITIVE",
            "one_hot_contract": "zero initialized matrix; intercept/numeric features plus only a known training-league indicator; unseen league is all-zero",
            "promotion_rule": "locked PI five-condition M1+M2 rule; diagnostics are descriptive only",
            "label": "RETROSPECTIVE_PRICE_TARGET; NOT_OBSERVED_PREBET_BJDC_QUOTE",
        }
        (stage / "evaluation_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n")
        manifest = {p.name: sha256(p) for p in sorted(stage.iterdir()) if p.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        os.replace(stage, OUT)
        print(json.dumps({"output": str(OUT), "manifest_sha256": sha256(OUT / "SHA256SUMS.json"), **summary}, sort_keys=True))
        return 0
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    sys.exit(main())
