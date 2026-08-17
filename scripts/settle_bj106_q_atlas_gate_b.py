#!/usr/bin/env python3
"""Settle #106's frozen q-atlas exactly once against the canonical #95 truth."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import shutil
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal, getcontext
from pathlib import Path

from scipy.stats import beta as beta_distribution
from scipy.stats import t as student_t

getcontext().prec = 50

CODES = ("3", "1", "0")
BOOTSTRAPS = 10_000
BOOTSTRAP_SEED = "10620260801"
FDR = Decimal("0.10")
GATE_A_MANIFEST = "fb45cacccb4c9ab2b52c8a538f489fb3e3197fa138245f0d83cf98a3cbb0db5d"
GATE_A_CONTENT = "306fe9c79ecae8ff4a1a8e4769cf13fbc43aa9da449f6c5f7f5d61986b561d4d"
CANONICAL_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
CANONICAL_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"

ATLAS_FIELDS = (
    "match_id", "issue", "match_idx", "kickoff_ts", "year", "fold",
    "candidate_code", "p_cal", "predicted_sp", "conservative_sp", "q_hat",
    "q_lb", "entropy", "dispersion_mean_relative_range",
    "initial_to_10h_log_probability_movement", "handicap_line_norm",
    "handicap_sign", "league_stratum", "probability_band", "predicted_sp_band",
    "conservative_sp_band", "q_hat_band", "q_lb_band", "stratum_id",
    "fallback_level", "stratum_support", "stratum_issue_count",
    "stratum_year_count", "nomination_eligible",
)
OUTCOME_FIELDS = (
    "match_id", "result_code", "winning_sp", "winning_sp_source",
    "settlement_quality", "has_trusted_settlement",
)
SETTLED_ATLAS_FIELDS = ATLAS_FIELDS + (
    "outcome_status", "actual_result_code", "final_winning_sp",
    "winning_sp_source", "settlement_quality", "has_trusted_settlement",
    "outcome_hit", "realized_pre_factor_leg_contribution",
    "predicted_vs_realized_gap_point", "predicted_vs_realized_gap_conservative",
)
SUMMARY_FIELDS = (
    "stratum_id", "fallback_level", "comparison_eligible", "n_frozen_rows",
    "n_settled_rows", "n_unavailable_rows", "settled_issues", "settled_years",
    "actual_hits", "actual_occurrence", "jeffreys_occurrence_mean",
    "jeffreys_occurrence_ci_low", "jeffreys_occurrence_ci_high", "mean_p_cal",
    "calibration_alignment_gap", "bootstrap_calibration_ci_low",
    "bootstrap_calibration_ci_high", "mean_realized_pre_factor", "mean_q_hat",
    "mean_q_lb", "point_gap", "conservative_gap", "bootstrap_point_gap_ci_low",
    "bootstrap_point_gap_ci_high", "bootstrap_conservative_gap_ci_low",
    "bootstrap_conservative_gap_ci_high", "conservative_cluster_p_value",
    "bh_fdr_q_value", "every_fold_direction_pass", "every_loyo_direction_pass",
    "ex_best_payout_point_gap", "ex_best_payout_conservative_gap",
    "ex_best_issue_point_gap", "ex_best_issue_conservative_gap",
    "top_payout_realized_share", "best_issue_realized_share", "robustness_pass",
    "nomination_status", "nomination_rank", "failure_reason",
)
SLICE_FIELDS = (
    "slice_type", "slice_value", "stratum_id", "comparison_eligible", "n_settled_rows",
    "actual_occurrence", "mean_p_cal", "calibration_alignment_gap",
    "mean_realized_pre_factor", "mean_q_hat", "mean_q_lb", "point_gap",
    "conservative_gap", "direction_pass",
)
EXCLUSION_FIELDS = (
    "stratum_id", "comparison_eligible", "exclusion_type", "excluded_identifier",
    "excluded_rows", "remaining_rows", "point_gap", "conservative_gap",
    "direction_pass",
)
CONCENTRATION_FIELDS = (
    "stratum_id", "comparison_eligible", "n_settled_rows", "realized_total",
    "top_payout_match_id", "top_payout_candidate_code", "top_payout_value",
    "top_payout_realized_share", "best_issue", "best_issue_value",
    "best_issue_realized_share",
)


def repo_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root(Path(__file__))
DEFAULT_GATE_A = ROOT / "results" / "bj106_gate_a_preoutcome_v2r1"
DEFAULT_CANONICAL = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
DEFAULT_OUT = ROOT / "results" / "bj106_gate_b_outcome_settlement_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def exact_manifest(bundle: Path, expected: str) -> dict[str, str]:
    manifest_path = bundle / "SHA256SUMS.json"
    if sha256(manifest_path) != expected:
        raise RuntimeError(f"unaccepted input manifest: {bundle}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {
        path.name: sha256(path)
        for path in bundle.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    if manifest != actual:
        raise RuntimeError(f"manifest coverage drift: {bundle}")
    return manifest


def read_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != fields:
            raise RuntimeError(f"schema drift: {path}")
        return list(reader)


def read_gzip_csv(path: Path, fields: tuple[str, ...]) -> Iterable[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != fields:
            raise RuntimeError(f"schema drift: {path}")
        yield from reader


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def ratio(value: Decimal | float | None) -> str:
    if value is None:
        return ""
    return f"{value:.12f}"


def decimal(value: str | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(value)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    values.sort()
    return values[round((len(values) - 1) * fraction)]


def stable_bootstrap_indices(key: str, population: int, count: int) -> Iterable[int]:
    """Version-independent 64-bit LCG for artifact-stable cluster bootstrap."""
    if population < 1:
        raise RuntimeError("empty bootstrap population")
    state = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
    for _ in range(count):
        state = (6364136223846793005 * state + 1442695040888963407) & ((1 << 64) - 1)
        yield state % population


def trusted_outcomes(bundle: Path) -> dict[str, dict[str, str]]:
    manifest = exact_manifest(bundle, CANONICAL_MANIFEST)
    if manifest.get("canonical_outcome_join.csv") != CANONICAL_PAYLOAD:
        raise RuntimeError("canonical outcome payload identity drift")
    rows = read_csv(bundle / "canonical_outcome_join.csv", OUTCOME_FIELDS)
    truth: dict[str, dict[str, str]] = {}
    for row in rows:
        if (
            row["match_id"] in truth
            or row["result_code"] not in CODES
            or decimal(row["winning_sp"]) <= 0
            or row["settlement_quality"] != "trusted"
            or row["has_trusted_settlement"] != "1"
        ):
            raise RuntimeError(f"untrusted canonical outcome: {row['match_id']}")
        truth[row["match_id"]] = row
    return truth


def comparison_eligible(row: dict[str, str]) -> bool:
    return (
        row["nomination_eligible"] == "TRUE"
        and int(row["stratum_support"]) >= 500
        and int(row["stratum_year_count"]) >= 3
        and row["fallback_level"] != "L5_CODE_ONLY"
    )


def empty_total() -> dict[str, Decimal | int]:
    return {
        "n": 0, "hits": 0, "p": Decimal(0), "y": Decimal(0),
        "q_hat": Decimal(0), "q_lb": Decimal(0),
    }


def add_total(target: dict[str, Decimal | int], item: dict[str, Decimal | int]) -> None:
    for key in target:
        target[key] += item[key]  # type: ignore[operator]


def row_total(row: dict[str, object]) -> dict[str, Decimal | int]:
    return {
        "n": 1,
        "hits": int(row["hit"]),
        "p": decimal(str(row["p"])),
        "y": decimal(str(row["y"])),
        "q_hat": decimal(str(row["q_hat"])),
        "q_lb": decimal(str(row["q_lb"])),
    }


def metrics(total: dict[str, Decimal | int]) -> dict[str, Decimal | int | None]:
    n = int(total["n"])
    if n == 0:
        return {"n": 0, "occurrence": None, "mean_p": None, "calibration": None,
                "mean_y": None, "mean_q_hat": None, "mean_q_lb": None,
                "point_gap": None, "conservative_gap": None}
    divisor = Decimal(n)
    occurrence = Decimal(int(total["hits"])) / divisor
    mean_p = decimal(total["p"]) / divisor
    mean_y = decimal(total["y"]) / divisor
    mean_q_hat = decimal(total["q_hat"]) / divisor
    mean_q_lb = decimal(total["q_lb"]) / divisor
    return {
        "n": n, "occurrence": occurrence, "mean_p": mean_p,
        "calibration": occurrence - mean_p, "mean_y": mean_y,
        "mean_q_hat": mean_q_hat, "mean_q_lb": mean_q_lb,
        "point_gap": mean_y - mean_q_hat,
        "conservative_gap": mean_y - mean_q_lb,
    }


def direction(metric: dict[str, Decimal | int | None]) -> bool:
    return bool(
        metric["n"]
        and metric["point_gap"] is not None
        and metric["conservative_gap"] is not None
        and decimal(metric["point_gap"]) > 0
        and decimal(metric["conservative_gap"]) > 0
    )


def jeffreys_interval(hits: int, n: int) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    if n == 0:
        return None, None, None
    alpha, beta = hits + 0.5, n - hits + 0.5
    return (
        Decimal(str(beta_distribution.mean(alpha, beta))),
        Decimal(str(beta_distribution.ppf(0.025, alpha, beta))),
        Decimal(str(beta_distribution.ppf(0.975, alpha, beta))),
    )


def bootstrap_metrics(by_issue: dict[str, dict[str, Decimal | int]], stratum: str) -> dict[str, float | None]:
    buckets = [by_issue[issue] for issue in sorted(by_issue, key=lambda value: int(value))]
    if not buckets:
        return {key: None for key in ("cal_low", "cal_high", "point_low", "point_high", "cons_low", "cons_high")}
    calibration, point, conservative = [], [], []
    for replicate in range(BOOTSTRAPS):
        total = empty_total()
        for index in stable_bootstrap_indices(f"{BOOTSTRAP_SEED}|{stratum}|{replicate}", len(buckets), len(buckets)):
            add_total(total, buckets[index])
        observed = metrics(total)
        calibration.append(float(decimal(observed["calibration"])))
        point.append(float(decimal(observed["point_gap"])))
        conservative.append(float(decimal(observed["conservative_gap"])))
    return {
        "cal_low": percentile(calibration, 0.025), "cal_high": percentile(calibration, 0.975),
        "point_low": percentile(point, 0.025), "point_high": percentile(point, 0.975),
        "cons_low": percentile(conservative, 0.025), "cons_high": percentile(conservative, 0.975),
    }


def conservative_cluster_p_value(by_issue: dict[str, dict[str, Decimal | int]]) -> Decimal | None:
    """One-sided cluster-t p-value for E[sum(actual - q_lb) per issue] > 0."""
    differences = [
        float(decimal(value["y"]) - decimal(value["q_lb"]))
        for _, value in sorted(by_issue.items(), key=lambda item: int(item[0]))
    ]
    if len(differences) < 2:
        return None
    mean = sum(differences) / len(differences)
    variance = sum((value - mean) ** 2 for value in differences) / (len(differences) - 1)
    if variance == 0:
        return Decimal(0) if mean > 0 else Decimal(1)
    statistic = mean / math.sqrt(variance / len(differences))
    return Decimal(str(student_t.sf(statistic, len(differences) - 1)))


def benjamini_hochberg(p_values: dict[str, Decimal | None]) -> dict[str, Decimal | None]:
    valid = sorted((value, key) for key, value in p_values.items() if value is not None)
    m = len(valid)
    output: dict[str, Decimal | None] = {key: None for key in p_values}
    adjusted = Decimal(1)
    for rank in range(m, 0, -1):
        value, key = valid[rank - 1]
        adjusted = min(adjusted, value * Decimal(m) / Decimal(rank))
        output[key] = min(Decimal(1), adjusted)
    return output


def complete_slice_rows(
    grouped: dict[tuple[str, str], dict[str, Decimal | int]],
    kind: str,
    eligible_by_stratum: dict[str, bool],
) -> list[dict[str, object]]:
    output = []
    for (stratum, slice_value), total in sorted(grouped.items()):
        item = metrics(total)
        output.append({
            "slice_type": kind, "slice_value": slice_value, "stratum_id": stratum,
            "comparison_eligible": str(eligible_by_stratum[stratum]).upper(),
            "n_settled_rows": item["n"], "actual_occurrence": ratio(item["occurrence"]),
            "mean_p_cal": ratio(item["mean_p"]), "calibration_alignment_gap": ratio(item["calibration"]),
            "mean_realized_pre_factor": ratio(item["mean_y"]), "mean_q_hat": ratio(item["mean_q_hat"]),
            "mean_q_lb": ratio(item["mean_q_lb"]), "point_gap": ratio(item["point_gap"]),
            "conservative_gap": ratio(item["conservative_gap"]),
            "direction_pass": str(direction(item)).upper(),
        })
    return output


def build(out: Path, gate_a: Path = DEFAULT_GATE_A, canonical: Path = DEFAULT_CANONICAL) -> dict[str, object]:
    if out.exists():
        raise RuntimeError(f"refusing immutable overwrite: {out}")
    gate_a_manifest = exact_manifest(gate_a, GATE_A_MANIFEST)
    content = json.loads((gate_a / "CONTENT_IDENTITY.json").read_text(encoding="utf-8"))
    if (
        sha256(gate_a / "CONTENT_IDENTITY.json") != GATE_A_CONTENT
        or content.get("gzip_payloads", {}).get("q_atlas.csv.gz", {}).get("canonical_decompressed_sha256")
        != "ba3c3e1a846466a95376117b0d9ac44650bc1de9cb894ded3d84f0609efa4dbe"
    ):
        raise RuntimeError("Gate-A portable identity drift")
    if gate_a_manifest.get("q_atlas.csv.gz") != "b710dd4fe792e69727b898a615e1cb4899175e329c71bcee46788fb859c43b26":
        raise RuntimeError("Gate-A atlas delivery identity drift")
    truth = trusted_outcomes(canonical)
    atlas_path = gate_a / "q_atlas.csv.gz"
    with tempfile.TemporaryDirectory(prefix=".bj106_gate_b_", dir=out.parent) as temporary:
        stage = Path(temporary)
        all_totals: dict[str, dict[str, Decimal | int]] = defaultdict(empty_total)
        by_issue: dict[str, dict[str, dict[str, Decimal | int]]] = defaultdict(lambda: defaultdict(empty_total))
        by_fold: dict[tuple[str, str], dict[str, Decimal | int]] = defaultdict(empty_total)
        by_year: dict[tuple[str, str], dict[str, Decimal | int]] = defaultdict(empty_total)
        best_payout: dict[str, dict[str, object]] = {}
        eligible: dict[str, bool] = {}
        frozen_rows: dict[str, int] = defaultdict(int)
        unavailable_rows: dict[str, int] = defaultdict(int)
        atlas_matches: set[str] = set()
        settled_rows = 0
        unavailable = 0
        settled_path = stage / "settled_q_atlas.csv.gz"
        with (
            settled_path.open("wb") as binary,
            gzip.GzipFile(fileobj=binary, mode="wb", mtime=0) as compressed,
            io.TextIOWrapper(compressed, newline="", encoding="utf-8") as handle,
        ):
            writer = csv.DictWriter(handle, fieldnames=SETTLED_ATLAS_FIELDS, lineterminator="\n")
            writer.writeheader()
            for row in read_gzip_csv(atlas_path, ATLAS_FIELDS):
                match_id, stratum = row["match_id"], row["stratum_id"]
                atlas_matches.add(match_id)
                frozen_rows[stratum] += 1
                frozen_eligible = comparison_eligible(row)
                if stratum in eligible and eligible[stratum] != frozen_eligible:
                    raise RuntimeError(f"stratum eligibility drift: {stratum}")
                eligible[stratum] = frozen_eligible
                outcome = truth.get(match_id)
                if outcome is None:
                    unavailable += 1
                    unavailable_rows[stratum] += 1
                    writer.writerow({
                        **row, "outcome_status": "UNAVAILABLE_CANONICAL_OUTCOME",
                        "actual_result_code": "", "final_winning_sp": "", "winning_sp_source": "",
                        "settlement_quality": "", "has_trusted_settlement": "", "outcome_hit": "",
                        "realized_pre_factor_leg_contribution": "",
                        "predicted_vs_realized_gap_point": "", "predicted_vs_realized_gap_conservative": "",
                    })
                    continue
                hit = int(outcome["result_code"] == row["candidate_code"])
                realized = decimal(outcome["winning_sp"]) if hit else Decimal(0)
                item = {"hit": hit, "p": decimal(row["p_cal"]), "y": realized,
                        "q_hat": decimal(row["q_hat"]), "q_lb": decimal(row["q_lb"])}
                total = row_total(item)
                add_total(all_totals[stratum], total)
                add_total(by_issue[stratum][row["issue"]], total)
                add_total(by_fold[(stratum, row["fold"])], total)
                add_total(by_year[(stratum, row["year"])], total)
                settled_rows += 1
                payout = {
                    "match_id": match_id, "candidate_code": row["candidate_code"], "issue": row["issue"],
                    "total": total, "realized": realized,
                }
                prior = best_payout.get(stratum)
                if prior is None or (realized, -int(match_id), row["candidate_code"]) > (decimal(prior["realized"]), -int(str(prior["match_id"])), str(prior["candidate_code"])):
                    best_payout[stratum] = payout
                writer.writerow({
                    **row, "outcome_status": "SETTLED", "actual_result_code": outcome["result_code"],
                    "final_winning_sp": outcome["winning_sp"], "winning_sp_source": outcome["winning_sp_source"],
                    "settlement_quality": outcome["settlement_quality"], "has_trusted_settlement": outcome["has_trusted_settlement"],
                    "outcome_hit": str(bool(hit)).upper(),
                    "realized_pre_factor_leg_contribution": ratio(realized),
                    "predicted_vs_realized_gap_point": ratio(realized - decimal(row["q_hat"])),
                    "predicted_vs_realized_gap_conservative": ratio(realized - decimal(row["q_lb"])),
                })
        if len(atlas_matches) != 47_819 or len(eligible) != 17:
            raise RuntimeError("frozen Gate-A atlas cardinality drift")
        if len(truth.keys() & atlas_matches) != 46_802 or unavailable != 3_051:
            raise RuntimeError("canonical outcome coverage drift")
        family = sorted(stratum for stratum, value in eligible.items() if value)
        if len(family) != 14:
            raise RuntimeError("frozen comparison family drift")
        fold_rows = complete_slice_rows(by_fold, "CHRONOLOGICAL_FOLD", eligible)
        annual_rows = complete_slice_rows(by_year, "CALENDAR_YEAR", eligible)
        loyo_rows: list[dict[str, object]] = []
        loyo_direction: dict[str, bool] = {}
        for stratum in sorted(all_totals):
            passes = []
            for year in sorted({key[1] for key in by_year if key[0] == stratum}):
                remaining = empty_total()
                for (source_stratum, source_year), total in by_year.items():
                    if source_stratum == stratum and source_year != year:
                        add_total(remaining, total)
                item = metrics(remaining)
                passed = direction(item)
                passes.append(passed)
                loyo_rows.append({
                    "slice_type": "LEAVE_ONE_YEAR_OUT", "slice_value": year, "stratum_id": stratum,
                    "comparison_eligible": str(eligible[stratum]).upper(), "n_settled_rows": item["n"],
                    "actual_occurrence": ratio(item["occurrence"]), "mean_p_cal": ratio(item["mean_p"]),
                    "calibration_alignment_gap": ratio(item["calibration"]), "mean_realized_pre_factor": ratio(item["mean_y"]),
                    "mean_q_hat": ratio(item["mean_q_hat"]), "mean_q_lb": ratio(item["mean_q_lb"]),
                    "point_gap": ratio(item["point_gap"]), "conservative_gap": ratio(item["conservative_gap"]),
                    "direction_pass": str(passed).upper(),
                })
            loyo_direction[stratum] = bool(passes) and all(passes)
        fold_direction = {
            stratum: bool(rows) and all(row["direction_pass"] == "TRUE" for row in rows)
            for stratum, rows in defaultdict(list, {
                key: [row for row in fold_rows if row["stratum_id"] == key] for key in all_totals
            }).items()
        }
        p_values = {stratum: conservative_cluster_p_value(by_issue[stratum]) if eligible[stratum] else None for stratum in all_totals}
        fdr_q = benjamini_hochberg(p_values)
        exclusion_rows, concentration_rows, summaries = [], [], []
        pending_candidates: list[tuple[Decimal, Decimal, str]] = []
        for stratum in sorted(all_totals):
            total = all_totals[stratum]
            item = metrics(total)
            n, hits = int(total["n"]), int(total["hits"])
            posterior_mean, posterior_low, posterior_high = jeffreys_interval(hits, n)
            boot = bootstrap_metrics(by_issue[stratum], stratum)
            payout = best_payout[stratum]
            without_payout = {key: total[key] - payout["total"][key] for key in total}  # type: ignore[index,operator]
            payout_metrics = metrics(without_payout)
            issue_items = by_issue[stratum]
            best_issue, best_issue_total = max(issue_items.items(), key=lambda pair: (decimal(pair[1]["y"]), -int(pair[0])))
            without_issue = {key: total[key] - best_issue_total[key] for key in total}  # type: ignore[operator]
            issue_metrics = metrics(without_issue)
            exclusion_rows.extend((
                {"stratum_id": stratum, "comparison_eligible": str(eligible[stratum]).upper(), "exclusion_type": "BEST_PAYOUT", "excluded_identifier": f"{payout['match_id']}:{payout['candidate_code']}", "excluded_rows": 1, "remaining_rows": payout_metrics["n"], "point_gap": ratio(payout_metrics["point_gap"]), "conservative_gap": ratio(payout_metrics["conservative_gap"]), "direction_pass": str(direction(payout_metrics)).upper()},
                {"stratum_id": stratum, "comparison_eligible": str(eligible[stratum]).upper(), "exclusion_type": "BEST_ISSUE", "excluded_identifier": best_issue, "excluded_rows": best_issue_total["n"], "remaining_rows": issue_metrics["n"], "point_gap": ratio(issue_metrics["point_gap"]), "conservative_gap": ratio(issue_metrics["conservative_gap"]), "direction_pass": str(direction(issue_metrics)).upper()},
            ))
            realized = decimal(total["y"])
            top_share = decimal(payout["realized"]) / realized if realized else None
            issue_share = decimal(best_issue_total["y"]) / realized if realized else None
            concentration_rows.append({
                "stratum_id": stratum, "comparison_eligible": str(eligible[stratum]).upper(), "n_settled_rows": n,
                "realized_total": ratio(realized), "top_payout_match_id": payout["match_id"],
                "top_payout_candidate_code": payout["candidate_code"], "top_payout_value": ratio(decimal(payout["realized"])),
                "top_payout_realized_share": ratio(top_share), "best_issue": best_issue,
                "best_issue_value": ratio(decimal(best_issue_total["y"])), "best_issue_realized_share": ratio(issue_share),
            })
            conditions = {
                "FDR": fdr_q[stratum] is not None and fdr_q[stratum] <= FDR,
                "BOOTSTRAP_CALIBRATION": boot["cal_low"] is not None and boot["cal_low"] > 0,
                "BOOTSTRAP_POINT": boot["point_low"] is not None and boot["point_low"] > 0,
                "BOOTSTRAP_CONSERVATIVE": boot["cons_low"] is not None and boot["cons_low"] > 0,
                "EVERY_FOLD": fold_direction[stratum], "EVERY_LOYO": loyo_direction[stratum],
                "EX_BEST_PAYOUT": direction(payout_metrics), "EX_BEST_ISSUE": direction(issue_metrics),
            }
            robust = eligible[stratum] and all(conditions.values())
            failures = [key for key, value in conditions.items() if not value]
            if robust:
                pending_candidates.append((decimal(fdr_q[stratum]), -decimal(str(boot["cons_low"])), stratum))
            summaries.append({
                "stratum_id": stratum, "fallback_level": next(row["fallback_level"] for row in read_gzip_csv(atlas_path, ATLAS_FIELDS) if row["stratum_id"] == stratum),
                "comparison_eligible": str(eligible[stratum]).upper(), "n_frozen_rows": frozen_rows[stratum], "n_settled_rows": n,
                "n_unavailable_rows": unavailable_rows[stratum], "settled_issues": len(issue_items),
                "settled_years": len({key[1] for key in by_year if key[0] == stratum}), "actual_hits": hits,
                "actual_occurrence": ratio(item["occurrence"]), "jeffreys_occurrence_mean": ratio(posterior_mean),
                "jeffreys_occurrence_ci_low": ratio(posterior_low), "jeffreys_occurrence_ci_high": ratio(posterior_high),
                "mean_p_cal": ratio(item["mean_p"]), "calibration_alignment_gap": ratio(item["calibration"]),
                "bootstrap_calibration_ci_low": ratio(boot["cal_low"]), "bootstrap_calibration_ci_high": ratio(boot["cal_high"]),
                "mean_realized_pre_factor": ratio(item["mean_y"]), "mean_q_hat": ratio(item["mean_q_hat"]), "mean_q_lb": ratio(item["mean_q_lb"]),
                "point_gap": ratio(item["point_gap"]), "conservative_gap": ratio(item["conservative_gap"]),
                "bootstrap_point_gap_ci_low": ratio(boot["point_low"]), "bootstrap_point_gap_ci_high": ratio(boot["point_high"]),
                "bootstrap_conservative_gap_ci_low": ratio(boot["cons_low"]), "bootstrap_conservative_gap_ci_high": ratio(boot["cons_high"]),
                "conservative_cluster_p_value": ratio(p_values[stratum]), "bh_fdr_q_value": ratio(fdr_q[stratum]),
                "every_fold_direction_pass": str(fold_direction[stratum]).upper(), "every_loyo_direction_pass": str(loyo_direction[stratum]).upper(),
                "ex_best_payout_point_gap": ratio(payout_metrics["point_gap"]), "ex_best_payout_conservative_gap": ratio(payout_metrics["conservative_gap"]),
                "ex_best_issue_point_gap": ratio(issue_metrics["point_gap"]), "ex_best_issue_conservative_gap": ratio(issue_metrics["conservative_gap"]),
                "top_payout_realized_share": ratio(top_share), "best_issue_realized_share": ratio(issue_share),
                "robustness_pass": str(robust).upper(), "nomination_status": "NOT_NOMINATED", "nomination_rank": "", "failure_reason": "|".join(failures) if not robust else "",
            })
        for rank, (_fdr, _bound, stratum) in enumerate(sorted(pending_candidates)[:2], start=1):
            row = next(item for item in summaries if item["stratum_id"] == stratum)
            row["nomination_status"], row["nomination_rank"], row["failure_reason"] = "BOUNDED_CANDIDATE", rank, ""
        write_csv(stage / "stratum_settlement_summary.csv", SUMMARY_FIELDS, summaries)
        write_csv(stage / "chronological_fold_metrics.csv", SLICE_FIELDS, fold_rows)
        write_csv(stage / "annual_metrics.csv", SLICE_FIELDS, annual_rows)
        write_csv(stage / "leave_one_year_out_metrics.csv", SLICE_FIELDS, loyo_rows)
        write_csv(stage / "ex_best_sensitivity.csv", EXCLUSION_FIELDS, exclusion_rows)
        write_csv(stage / "concentration_diagnostics.csv", CONCENTRATION_FIELDS, concentration_rows)
        shutil.copy2(canonical / "canonical_outcome_join.csv", stage / "canonical_outcome_join.csv")
        with gzip.open(settled_path, "rt", encoding="utf-8") as handle:
            decompressed = handle.read().encode("utf-8")
        content_identity = {
            "settled_q_atlas.csv.gz": {
                "canonical_decompressed_sha256": hashlib.sha256(decompressed).hexdigest(),
                "canonical_decompressed_bytes": len(decompressed), "container_type": "gzip",
            },
            "canonical_outcome_join.csv": {"sha256": sha256(stage / "canonical_outcome_join.csv")},
        }
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content_identity, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        nominated = [row["stratum_id"] for row in summaries if row["nomination_status"] == "BOUNDED_CANDIDATE"]
        card = {
            "issue": 106, "stage": "GATE_B_ONE_SHOT_OUTCOME_SETTLEMENT", "gate_a_manifest_sha256": GATE_A_MANIFEST,
            "gate_a_content_identity_sha256": GATE_A_CONTENT, "canonical_outcome_manifest_sha256": CANONICAL_MANIFEST,
            "canonical_outcome_payload_sha256": CANONICAL_PAYLOAD, "canonical_outcome_source": "results/bj95_gate_b_outcome_settlement_v2r8/canonical_outcome_join.csv",
            "outcome_read_once": True, "outcome_join_rule": "left join every frozen 3/1/0 atlas row on match_id; 1,017 frozen matches absent from the canonical source remain UNAVAILABLE_CANONICAL_OUTCOME and are never dropped",
            "rows": {"frozen_atlas": 143457, "settled": settled_rows, "unavailable": unavailable, "comparison_family": len(family)},
            "definitions": {"realized_pre_factor_leg_contribution": "indicator(actual_result_code == candidate_code) * final_winning_sp", "point_gap": "mean(realized_pre_factor_leg_contribution - q_hat)", "conservative_gap": "mean(realized_pre_factor_leg_contribution - q_lb)", "calibration_alignment": "actual occurrence - mean(p_cal)"},
            "uncertainty": {"Jeffreys_occurrence": "Beta(0.5,0.5) 95% interval", "issue_cluster_bootstrap": {"replicates": BOOTSTRAPS, "seed": BOOTSTRAP_SEED, "rng": "SHA256-seeded 64-bit LCG", "interval": "percentile 95%"}, "fdr": {"method": "Benjamini-Hochberg", "level": "0.10", "family": "all 14 frozen comparison-eligible strata", "p_value": "one-sided issue-cluster Student-t test on per-issue sum(realized - q_lb)"}},
            "nomination_rule": "At most two strata; BH q<=0.10, positive lower issue-bootstrap 95% bounds for calibration, point and conservative contribution gaps, positive point/conservative direction in every frozen fold and LOYO, and positive point/conservative gaps after ex-best-payout and ex-best-issue. Any missing condition is NO_PROMOTION for that stratum.",
            "nominated_strata": nominated, "terminal_disposition": "NO_PROMOTION" if not nominated else "BOUNDED_CANDIDATES_FOR_FUTURE_PREREGISTERED_RESEARCH_ONLY",
            "factor_boundary": "0.65 is absent from per-leg/stratum eligibility and is reserved for later complete-ticket economics, applied exactly once after ticket assembly.",
            "scope": "historical paper-only research; no portfolio construction, purchase, production policy, or performance promotion.",
        }
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(Path(__file__), stage / "settlement_runner.py")
        manifest = {path.name: sha256(path) for path in sorted(stage.iterdir()) if path.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copytree(stage, out)
    return {"output": str(out), "settled_rows": settled_rows, "unavailable_rows": unavailable, "nominated_strata": nominated, "manifest_sha256": sha256(out / "SHA256SUMS.json")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--gate-a", type=Path, default=DEFAULT_GATE_A)
    parser.add_argument("--canonical-outcomes", type=Path, default=DEFAULT_CANONICAL)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve(), args.gate_a.resolve(), args.canonical_outcomes.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
