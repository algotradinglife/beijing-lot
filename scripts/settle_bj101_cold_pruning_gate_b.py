#!/usr/bin/env python3
"""One-shot canonical outcome settlement for #101's accepted Gate-A package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from decimal import Decimal, getcontext
from pathlib import Path

from scipy.stats import binomtest

getcontext().prec = 80
FACTOR = Decimal("0.65")
STAKE = Decimal(2)
CODES = ("3", "1", "0")
GATE_A_MANIFEST = "86e37682a95fad2a2a67187f1ee528f665d371583c621dc9d14af58f74302447"
SOURCE_DB_SHA = "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"
MEMBERSHIP_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "match_id", "match_idx", "kickoff_ts", "p3", "p1", "p0", "deleted_code",
    "p_min", "p_min_rank", "p_min_bucket", "eligible_t05", "eligible_t10",
    "eligible_t15", "eligible_t20",
)
FRONTIER_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_match_count",
    "match_id", "match_idx", "kickoff_ts", "threshold", "arm", "deleted_code",
    "p_min", "p_min_rank", "n7_combination_count", "tickets_per_n7",
    "total_tickets", "stake_yuan", "portfolio_descriptor_sha256",
)
OUTCOME_FIELDS = ("match_id", "result_code", "winning_sp", "winning_sp_source", "settlement_quality", "has_trusted_settlement")
SETTLEMENT_FIELDS = FRONTIER_FIELDS + (
    "deleted_outcome_occurred", "coverage_hit", "expected_deleted_probability",
    "full_control_gross_yuan", "pruned_gross_yuan", "gross_retention_ratio",
    "full_control_net_yuan", "pruned_net_yuan", "full_control_roi", "pruned_roi",
    "settlement_factor", "companion_product_sum", "settlement_status",
)
SUMMARY_FIELDS = (
    "threshold", "arm", "frontier_rows", "coverage_hits", "deleted_upsets",
    "expected_deleted_upsets", "full_control_gross_yuan", "pruned_gross_yuan",
    "full_control_stake_yuan", "pruned_stake_yuan", "gross_retention_ratio",
    "full_control_net_yuan", "pruned_net_yuan", "full_control_roi", "pruned_roi",
)
DIAGNOSTIC_FIELDS = (
    "threshold", "arm", "stratum", "n", "deleted_upsets", "expected_upsets",
    "observed_rate", "mean_probability", "calibration_gap", "brier", "log_loss",
    "exact_ci_low", "exact_ci_high", "issue_cluster_ci_low", "issue_cluster_ci_high",
)
POOL_FAILURE_FIELDS = (
    "threshold", "arm", "pool_id", "issue", "year", "pool_match_count",
    "candidate_count", "deleted_upsets", "at_least_one_deleted_upset",
    "expected_at_least_one_deleted_upset",
)
PORTFOLIO_FIELDS = (
    "threshold", "arm", "year", "issue", "frontier_rows", "gross_yuan", "stake_yuan",
    "net_yuan", "roi", "max_drawdown_yuan", "max_losing_streak",
)
EXCLUSION_FIELDS = (
    "threshold", "arm", "excluded_frontier_descriptor_sha256", "gross_retention_ratio_ex_best",
    "pruned_roi_ex_best", "full_control_roi_ex_best",
)
LOYO_FIELDS = (
    "threshold", "arm", "excluded_year", "frontier_rows", "deleted_upsets",
    "expected_deleted_upsets", "gross_retention_ratio", "pruned_roi", "full_control_roi",
)


def root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    return anchor.resolve().parent


ROOT = root(Path(__file__))
GATE_A = ROOT / "results" / "bj101_gate_a_preoutcome_v1r1"
DEFAULT_DB = ROOT.parents[1] / "data" / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite"
OUT = ROOT / "results" / "bj101_gate_b_outcome_settlement_v1r3"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def exact_manifest(bundle: Path, expected: str) -> dict[str, str]:
    manifest_path = bundle / "SHA256SUMS.json"
    if sha(manifest_path) != expected:
        raise RuntimeError("unaccepted Gate-A manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {path.name: sha(path) for path in bundle.iterdir() if path.is_file() and path.name != "SHA256SUMS.json"}
    if actual != manifest:
        raise RuntimeError("Gate-A manifest coverage drift")
    return manifest


def read_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != fields:
            raise RuntimeError(f"schema drift: {path}")
        return list(reader)


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def ratio(value: Decimal | None) -> str:
    return "" if value is None else format(value, ".12f")


def diagnostic_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Compute binomial and issue-clustered diagnostics only for deleted-code arms."""
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if not row["deleted_code"]:
            continue
        for stratum in (
            "ALL",
            f"CODE={row['deleted_code']}",
            f"P_BUCKET=[{(int(Decimal(str(row['p_min'])) * 20) * 5) / 100:.2f},{(int(Decimal(str(row['p_min'])) * 20) * 5 + 5) / 100:.2f})",
            f"YEAR={row['year']}",
            f"ISSUE={row['issue']}",
            f"POOL_SIZE={row['pool_match_count']}",
        ):
            grouped[(str(row["threshold"]), str(row["arm"]), stratum)].append(row)
    output = []
    for (threshold, arm, stratum), items in sorted(grouped.items()):
        observed = [int(str(item["deleted_outcome_occurred"]) == "TRUE") for item in items]
        probabilities = [Decimal(str(item["p_min"])) for item in items]
        n, hits = len(items), sum(observed)
        interval = binomtest(hits, n).proportion_ci(confidence_level=0.95, method="exact")
        by_issue: dict[str, list[int]] = defaultdict(list)
        for item, hit in zip(items, observed, strict=True):
            by_issue[str(item["issue"])].append(hit)
        issue_rates = [sum(values) / len(values) for values in by_issue.values()]
        if len(issue_rates) > 1:
            mean = sum(issue_rates) / len(issue_rates)
            variance = sum((value - mean) ** 2 for value in issue_rates) / (len(issue_rates) - 1)
            half = 1.96 * (variance / len(issue_rates)) ** 0.5
            low, high = max(0.0, mean - half), min(1.0, mean + half)
        else:
            low = high = issue_rates[0]
        mean_probability = sum(probabilities) / n
        output.append({
            "threshold": threshold, "arm": arm, "stratum": stratum, "n": n,
            "deleted_upsets": hits, "expected_upsets": money(sum(probabilities)),
            "observed_rate": ratio(Decimal(hits) / n), "mean_probability": ratio(mean_probability),
            "calibration_gap": ratio(Decimal(hits) / n - mean_probability),
            "brier": ratio(sum((Decimal(hit) - probability) ** 2 for hit, probability in zip(observed, probabilities, strict=True)) / n),
            "log_loss": ratio(sum(-(Decimal(hit) * probability.ln() + Decimal(1 - hit) * (Decimal(1) - probability).ln()) for hit, probability in zip(observed, probabilities, strict=True)) / n),
            "exact_ci_low": f"{interval.low:.12f}", "exact_ci_high": f"{interval.high:.12f}",
            "issue_cluster_ci_low": f"{low:.12f}", "issue_cluster_ci_high": f"{high:.12f}",
        })
    return output


def pool_failure_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if row["deleted_code"]:
            grouped[(str(row["threshold"]), str(row["arm"]), str(row["pool_id"]))].append(row)
    output = []
    for (_threshold, _arm, _pool), items in sorted(grouped.items()):
        output.append({
            "threshold": items[0]["threshold"], "arm": items[0]["arm"], "pool_id": items[0]["pool_id"],
            "issue": items[0]["issue"], "year": items[0]["year"], "pool_match_count": items[0]["pool_match_count"],
            "candidate_count": len(items), "deleted_upsets": sum(item["deleted_outcome_occurred"] == "TRUE" for item in items),
            "at_least_one_deleted_upset": str(any(item["deleted_outcome_occurred"] == "TRUE" for item in items)).upper(),
            "expected_at_least_one_deleted_upset": ratio(Decimal(1) - __import__("functools").reduce(lambda a, item: a * (Decimal(1) - Decimal(str(item["p_min"]))), items, Decimal(1))),
        })
    return output


def e6(values: list[Decimal]) -> Decimal:
    """Sum products of all six-element subsets, without materialising N7s."""
    coefficients = [Decimal(0)] * 7
    coefficients[0] = Decimal(1)
    for value in values:
        for degree in range(6, 0, -1):
            coefficients[degree] += value * coefficients[degree - 1]
    return coefficients[6]


def outcomes(db: Path, match_ids: list[str]) -> dict[str, dict[str, str]]:
    if sha(db) != SOURCE_DB_SHA:
        raise RuntimeError("canonical outcome database hash drift")
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        result = {}
        for start in range(0, len(match_ids), 900):
            batch = match_ids[start:start + 900]
            placeholders = ",".join("?" for _ in batch)
            query = f"""
                select match_id, result_code, winning_sp, winning_sp_source,
                       settlement_quality, has_trusted_settlement
                from match_features where match_id in ({placeholders})
            """
            for item in connection.execute(query, tuple(int(value) for value in batch)):
                row = dict(zip(OUTCOME_FIELDS, item, strict=True))
                row = {key: "" if value is None else str(value) for key, value in row.items()}
                if row["result_code"] not in CODES or Decimal(row["winning_sp"]) <= 0 or row["settlement_quality"] != "trusted" or row["has_trusted_settlement"] != "1":
                    raise RuntimeError(f"untrusted canonical outcome {row['match_id']}")
                result[row["match_id"]] = row
        if len(result) != len(match_ids):
            raise RuntimeError("canonical outcome coverage drift")
        return result
    finally:
        connection.close()


def build(out: Path, db: Path = DEFAULT_DB) -> dict[str, int]:
    if out.exists():
        raise RuntimeError(f"refusing immutable overwrite: {out}")
    exact_manifest(GATE_A, GATE_A_MANIFEST)
    membership = read_csv(GATE_A / "issue_pool_membership.csv", MEMBERSHIP_FIELDS)
    frontier = read_csv(GATE_A / "n7_cold_pruning_frontier.csv", FRONTIER_FIELDS)
    by_pool: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in membership:
        by_pool[row["pool_id"]].append(row)
    for rows in by_pool.values():
        rows.sort(key=lambda row: (row["kickoff_ts"], int(row["match_idx"]), int(row["match_id"])))
    truth = outcomes(db, sorted({row["match_id"] for row in membership}, key=int))
    with tempfile.TemporaryDirectory(prefix=".bj101_gate_b_", dir=out.parent) as temp_name:
        stage = Path(temp_name)
        settlement: list[dict[str, object]] = []
        summaries: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        for row in frontier:
            pool = by_pool[row["pool_id"]]
            deleted = row["deleted_code"]
            candidate = truth[row["match_id"]]
            companion_sp = [Decimal(truth[item["match_id"]]["winning_sp"]) for item in pool if item["match_id"] != row["match_id"]]
            product_sum = e6(companion_sp)
            full_gross = STAKE * FACTOR * Decimal(candidate["winning_sp"]) * product_sum
            upset = candidate["result_code"] == deleted if deleted else False
            pruned_gross = Decimal(0) if upset else full_gross
            full_stake = Decimal(row["n7_combination_count"]) * Decimal(2187) * STAKE
            pruned_stake = Decimal(row["stake_yuan"])
            if row["arm"] == "FULL_COVER_CONTROL":
                pruned_stake = full_stake
                pruned_gross = full_gross
            output = {**row,
                "deleted_outcome_occurred": "" if not deleted else str(upset).upper(),
                "coverage_hit": "YES" if not upset else "NO",
                "expected_deleted_probability": row["p_min"],
                "full_control_gross_yuan": money(full_gross), "pruned_gross_yuan": money(pruned_gross),
                "gross_retention_ratio": ratio(pruned_gross / full_gross if full_gross else None),
                "full_control_net_yuan": money(full_gross - full_stake), "pruned_net_yuan": money(pruned_gross - pruned_stake),
                "full_control_roi": ratio((full_gross - full_stake) / full_stake),
                "pruned_roi": ratio((pruned_gross - pruned_stake) / pruned_stake),
                "settlement_factor": "0.65", "companion_product_sum": money(product_sum), "settlement_status": "SETTLED"}
            settlement.append(output)
            metric = summaries[(row["threshold"], row["arm"])]
            metric["frontier_rows"] += 1; metric["coverage_hits"] += int(not upset); metric["deleted_upsets"] += int(upset)
            metric["expected_deleted_upsets"] += Decimal(row["p_min"]); metric["full_control_gross_yuan"] += full_gross; metric["pruned_gross_yuan"] += pruned_gross
            metric["full_control_stake_yuan"] += full_stake; metric["pruned_stake_yuan"] += pruned_stake
        summary_rows = []
        for (threshold, arm), metric in sorted(summaries.items()):
            fg, pg, fs, ps = metric["full_control_gross_yuan"], metric["pruned_gross_yuan"], metric["full_control_stake_yuan"], metric["pruned_stake_yuan"]
            summary_rows.append({"threshold": threshold, "arm": arm, "frontier_rows": int(metric["frontier_rows"]), "coverage_hits": int(metric["coverage_hits"]), "deleted_upsets": int(metric["deleted_upsets"]), "expected_deleted_upsets": money(metric["expected_deleted_upsets"]), "full_control_gross_yuan": money(fg), "pruned_gross_yuan": money(pg), "full_control_stake_yuan": money(fs), "pruned_stake_yuan": money(ps), "gross_retention_ratio": ratio(pg / fg if fg else None), "full_control_net_yuan": money(fg - fs), "pruned_net_yuan": money(pg - ps), "full_control_roi": ratio((fg - fs) / fs), "pruned_roi": ratio((pg - ps) / ps)})
        portfolio_groups: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
        for row in settlement:
            portfolio_groups[(str(row["threshold"]), str(row["arm"]), str(row["year"]), str(row["issue"]))].append(row)
        portfolio_rows = []
        for (threshold, arm, year, issue), items in sorted(portfolio_groups.items()):
            ordered = sorted(items, key=lambda item: (str(item["kickoff_ts"]), int(str(item["match_idx"]))))
            balance = peak = Decimal(0); drawdown = Decimal(0); streak = max_streak = 0
            for item in ordered:
                balance += Decimal(str(item["pruned_net_yuan"]))
                peak = max(peak, balance); drawdown = max(drawdown, peak - balance)
                streak = streak + 1 if Decimal(str(item["pruned_net_yuan"])) < 0 else 0; max_streak = max(max_streak, streak)
            gross = sum((Decimal(str(item["pruned_gross_yuan"])) for item in items), Decimal(0)); stake = sum((Decimal(str(item["stake_yuan"])) for item in items), Decimal(0))
            portfolio_rows.append({"threshold": threshold, "arm": arm, "year": year, "issue": issue, "frontier_rows": len(items), "gross_yuan": money(gross), "stake_yuan": money(stake), "net_yuan": money(gross-stake), "roi": ratio((gross-stake)/stake), "max_drawdown_yuan": money(drawdown), "max_losing_streak": max_streak})
        exclusions = []
        for (threshold, arm), metric in sorted(summaries.items()):
            items = [row for row in settlement if row["threshold"] == threshold and row["arm"] == arm]
            best = max(items, key=lambda item: Decimal(str(item["full_control_gross_yuan"])))
            best_full_stake = Decimal(str(best["n7_combination_count"])) * Decimal(2187) * STAKE
            best_pruned_stake = Decimal(str(best["stake_yuan"]))
            fg = metric["full_control_gross_yuan"] - Decimal(str(best["full_control_gross_yuan"])); pg = metric["pruned_gross_yuan"] - Decimal(str(best["pruned_gross_yuan"])); fs = metric["full_control_stake_yuan"] - best_full_stake; ps = metric["pruned_stake_yuan"] - best_pruned_stake
            exclusions.append({"threshold": threshold, "arm": arm, "excluded_frontier_descriptor_sha256": best["portfolio_descriptor_sha256"], "gross_retention_ratio_ex_best": ratio(pg/fg if fg else None), "pruned_roi_ex_best": ratio((pg-ps)/ps if ps else None), "full_control_roi_ex_best": ratio((fg-fs)/fs if fs else None)})
        loyo = []
        for threshold, arm in sorted(summaries):
            arm_rows = [row for row in settlement if row["threshold"] == threshold and row["arm"] == arm]
            for year in sorted({str(row["year"]) for row in arm_rows}):
                items = [row for row in arm_rows if str(row["year"]) != year]
                fg = sum((Decimal(str(row["full_control_gross_yuan"])) for row in items), Decimal(0)); pg = sum((Decimal(str(row["pruned_gross_yuan"])) for row in items), Decimal(0))
                fs = sum((Decimal(str(row["n7_combination_count"])) * Decimal(2187) * STAKE for row in items), Decimal(0)); ps = sum((Decimal(str(row["stake_yuan"])) for row in items), Decimal(0))
                loyo.append({"threshold": threshold, "arm": arm, "excluded_year": year, "frontier_rows": len(items), "deleted_upsets": sum(row["deleted_outcome_occurred"] == "TRUE" for row in items), "expected_deleted_upsets": money(sum((Decimal(str(row["p_min"])) for row in items), Decimal(0))), "gross_retention_ratio": ratio(pg/fg if fg else None), "pruned_roi": ratio((pg-ps)/ps if ps else None), "full_control_roi": ratio((fg-fs)/fs if fs else None)})
        write_csv(stage / "canonical_outcome_join.csv", OUTCOME_FIELDS, [truth[key] for key in sorted(truth, key=int)])
        write_csv(stage / "frontier_settlement.csv", SETTLEMENT_FIELDS, settlement)
        write_csv(stage / "settlement_summary.csv", SUMMARY_FIELDS, summary_rows)
        write_csv(stage / "deleted_outcome_diagnostics.csv", DIAGNOSTIC_FIELDS, diagnostic_rows(settlement))
        write_csv(stage / "pool_failure_concentration.csv", POOL_FAILURE_FIELDS, pool_failure_rows(settlement))
        write_csv(stage / "issue_portfolio_summary.csv", PORTFOLIO_FIELDS, portfolio_rows)
        write_csv(stage / "ex_best_payout_sensitivity.csv", EXCLUSION_FIELDS, exclusions)
        write_csv(stage / "leave_one_year_out.csv", LOYO_FIELDS, loyo)
        card = {"issue": 101, "stage": "GATE_B_ONE_SHOT_OUTCOME_SETTLEMENT", "gate_a_manifest_sha256": GATE_A_MANIFEST, "canonical_source_db_sha256": SOURCE_DB_SHA, "canonical_source": "data/derived/beidan_xlsm/beidan_xlsm.sqlite:match_features", "outcome_fields": list(OUTCOME_FIELDS), "settlement_rule": "all frozen six-companion combinations settled analytically using elementary symmetric degree-6 final-SP product; gross=2*0.65*final-SP product; factor exactly once", "diagnostics": "exact binomial and issue-clustered intervals; calibration, stratification, pool failure concentration, issue portfolio paths and ex-best-payout sensitivity", "scope": "historical research only; no purchase or production promotion"}
        (stage / "settlement_card.json").write_text(json.dumps(card, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        shutil.copy2(Path(__file__), stage / "settlement_runner.py")
        manifest = {path.name: sha(path) for path in stage.iterdir() if path.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        shutil.copytree(stage, out)
    return {"settled_frontiers": len(settlement), "outcomes": len(truth)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve(), args.db.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
