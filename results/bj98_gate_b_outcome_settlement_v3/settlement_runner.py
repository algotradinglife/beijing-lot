#!/usr/bin/env python3
"""One-shot canonical outcome settlement for #98's immutable Gate-A freeze."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import shutil
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 80
CODES = ("3", "1", "0")
FACTOR = Decimal("0.65")
GATE_A_MANIFEST = "fd142cc2594f2e71b4b81136e91e7ecfcf8623b07c94d92d0b9c1cf6a212b4cb"
BJ95_GATE_A_MANIFEST = (
    "10b4d6d274aef53e1e1d4abe30cd9f683cf296865ee131f00f5c1e1d16d0725c"
)
BJ95_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
BJ91_MANIFEST = "07957d4e21076bc9799f16e3b582e36854a16858436f07adf306260a474c271f"
LEG_SHA = "369c2ab398cb996bcd913f9ff7d3d71431303c957bb349e43b774c87c40e377e"
BOOTSTRAPS = 200
BANKROLLS = (10_000, 100_000, 1_000_000)
TEMPERATURES = (Decimal("0.80"), Decimal("1.00"), Decimal("1.20"))

GATE_A_FIELDS = (
    "group_id",
    "issue",
    "year",
    "fold",
    "seed",
    "arm",
    "selection_status",
    "selection_rule",
    "quality_score",
    "prior_quality_q75",
    "omitted_codes",
    "selected_sequence_count",
    "stake_yuan",
    "calibrated_mass",
    "euro_novig_mass",
    "portfolio_descriptor_sha256",
)
LEG_FIELDS = (
    "group_id",
    "position",
    "match_id",
    "issue",
    "match_idx",
    "year",
    "fold",
    "handicap_line_norm",
    "p3",
    "p1",
    "p0",
    "euro_p3",
    "euro_p1",
    "euro_p0",
    "predicted_sp_3",
    "predicted_sp_1",
    "predicted_sp_0",
    "sp5_3",
    "sp5_1",
    "sp5_0",
)
OUTCOME_FIELDS = (
    "match_id",
    "result_code",
    "winning_sp",
    "winning_sp_source",
    "settlement_quality",
    "has_trusted_settlement",
)
SETTLEMENT_FIELDS = GATE_A_FIELDS + (
    "quarter",
    "truth_sequence",
    "final_winning_sp_product_uncapped",
    "winning_sp_sources",
    "settlement_status",
    "hit",
    "gross_yuan",
    "net_yuan",
    "settlement_factor",
)
SUMMARY_FIELDS = (
    "arm",
    "seed",
    "settled_groups",
    "no_bet_groups",
    "hits",
    "hit_rate",
    "stake_yuan",
    "gross_yuan",
    "net_yuan",
    "roi",
    "max_drawdown_yuan",
    "longest_losing_streak",
    "fold_roi_empirical_range_low",
    "fold_roi_empirical_range_high",
)
CONTROL_FIELDS = (
    "family",
    "arm",
    "depth",
    "group_count",
    "stake_yuan",
    "gross_yuan",
    "net_yuan",
    "roi",
)
BANKROLL_FIELDS = (
    "arm",
    "seed",
    "bankroll_yuan",
    "executed_groups",
    "unaffordable_groups",
    "first_unaffordable_issue",
    "first_unaffordable_group_id",
    "final_balance_yuan",
)
CALIBRATION_FIELDS = (
    "top1_probability_bin",
    "leg_count",
    "mean_top1_probability",
    "observed_top1_hit_rate",
    "multiclass_brier_score",
)
SENSITIVITY_FIELDS = (
    "arm",
    "seed",
    "temperature",
    "selected_groups",
    "mean_fixed_ticket_retained_mass",
)


def repository_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    return anchor.resolve().parent


ROOT = repository_root(Path(__file__))
GATE_A = ROOT / "results" / "bj98_gate_a_preoutcome_v1"
BJ95 = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
BJ95_GATE_A = ROOT / "results" / "bj95_gate_a_preoutcome_v5"
BJ91 = ROOT / "results" / "bj91_gate_b_outcome_settlement_v1"
OUT = ROOT / "results" / "bj98_gate_b_outcome_settlement_v3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decompressed_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_manifest(bundle: Path, expected: str) -> dict[str, str]:
    path = bundle / "SHA256SUMS.json"
    if sha256(path) != expected:
        raise RuntimeError(f"unaccepted bundle manifest: {bundle}")
    declared = json.loads(path.read_text(encoding="utf-8"))
    entries = list(bundle.iterdir())
    if not isinstance(declared, dict) or any(not entry.is_file() for entry in entries):
        raise RuntimeError(f"non-exact bundle: {bundle}")
    actual = {entry.name: sha256(entry) for entry in entries if entry.name != path.name}
    if actual != declared:
        raise RuntimeError(f"manifest coverage drift: {bundle}")
    return declared


def authenticated_snapshot(
    private_dir: Path,
    name: str,
    source: Path,
    expected_sha256: str,
    *,
    expected_decompressed_sha256: str | None = None,
) -> Path:
    """Copy an authenticated input once, then bind every later read to that copy."""
    destination = private_dir / name
    shutil.copyfile(source, destination)
    if sha256(destination) != expected_sha256:
        raise RuntimeError(f"authenticated source drift during copy: {source}")
    if (
        expected_decompressed_sha256 is not None
        and decompressed_sha256(destination) != expected_decompressed_sha256
    ):
        raise RuntimeError(f"authenticated decompressed source drift: {source}")
    return destination


def read_gzip(path: Path, fields: tuple[str, ...]) -> Iterable[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != fields:
            raise RuntimeError(f"schema mismatch: {path}")
        yield from reader


def read_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != fields:
            raise RuntimeError(f"schema mismatch: {path}")
        return list(reader)


def money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def ratio(value: Decimal | None) -> str:
    return "" if value is None else format(value, ".12f")


def quarter(issue: str) -> str:
    month = int(issue[2:4])
    return f"20{issue[:2]}-Q{(month - 1) // 3 + 1}"


def load_truth_and_legs(
    outcome_path: Path,
    leg_path: Path,
) -> tuple[dict[str, tuple[str, Decimal, str]], dict[str, list[dict[str, str]]]]:
    outcome = {
        row["match_id"]: (
            row["result_code"],
            Decimal(row["winning_sp"]),
            row["winning_sp_source"],
        )
        for row in read_csv(outcome_path, OUTCOME_FIELDS)
    }
    if any(code not in CODES or sp <= 0 for code, sp, _ in outcome.values()):
        raise RuntimeError("invalid canonical outcome payload")
    legs: dict[str, list[dict[str, str]]] = defaultdict(list)
    with gzip.open(leg_path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != LEG_FIELDS:
            raise RuntimeError("#95 safe-leg schema drift")
        for row in reader:
            legs[row["group_id"]].append(row)
    if len(legs) != 6686 or sum(map(len, legs.values())) != 46802:
        raise RuntimeError("frozen N7 cohort cardinality drift")
    for group_id, group in legs.items():
        group.sort(key=lambda row: int(row["position"]))
        if [int(row["position"]) for row in group] != list(range(1, 8)):
            raise RuntimeError(f"invalid frozen positions: {group_id}")
    return outcome, legs


def omitted_codes(raw: str) -> list[str]:
    if not raw:
        return [""] * 7
    pairs = raw.split("|")
    if len(pairs) != 7:
        raise RuntimeError("invalid frozen omission cardinality")
    output = [""] * 7
    for pair in pairs:
        position, code = pair.split(":", 1)
        index = int(position) - 1
        if index not in range(7) or code not in CODES or output[index]:
            raise RuntimeError("invalid frozen omission encoding")
        output[index] = code
    return output


def hit_gross(hit: str, winning_sp_product: Decimal) -> Decimal:
    """Return the single-ticket gross payout under the locked 65% factor."""
    if hit == "YES":
        return Decimal(2) * FACTOR * winning_sp_product
    if hit == "NO":
        return Decimal(0)
    raise RuntimeError(f"invalid settled hit state: {hit}")


@dataclass
class Metrics:
    bets: int = 0
    no_bets: int = 0
    hits: int = 0
    stake: Decimal = Decimal(0)
    gross: Decimal = Decimal(0)
    cumulative: Decimal = Decimal(0)
    peak: Decimal = Decimal(0)
    max_drawdown: Decimal = Decimal(0)
    losing_streak: int = 0
    longest_losing_streak: int = 0

    def add(self, hit: str, stake: Decimal, gross: Decimal) -> Decimal:
        if hit == "NO_BET":
            self.no_bets += 1
            return Decimal(0)
        self.bets += 1
        self.hits += hit == "YES"
        net = gross - stake
        self.stake += stake
        self.gross += gross
        self.cumulative += net
        self.peak = max(self.peak, self.cumulative)
        self.max_drawdown = max(self.max_drawdown, self.peak - self.cumulative)
        self.losing_streak = 0 if net > 0 else self.losing_streak + 1
        self.longest_losing_streak = max(self.longest_losing_streak, self.losing_streak)
        return net


def percentile(values: list[Decimal], fraction: float) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def stable_bootstrap_indices(key: str, population: int, count: int) -> Iterable[int]:
    """Version-independent 64-bit LCG for artifact-stable bootstrap sampling."""
    if population < 1:
        raise RuntimeError("empty bootstrap population")
    state = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
    for _ in range(count):
        state = (6364136223846793005 * state + 1442695040888963407) & ((1 << 64) - 1)
        yield state % population


def settle(
    stage: Path,
    frontier_path: Path,
    outcome_path: Path,
    leg_path: Path,
) -> tuple[
    dict[tuple[str, str], Metrics],
    dict[tuple[str, str], dict[str, tuple[Decimal, Decimal]]],
    dict[tuple[str, str], list[Decimal]],
]:
    truth, legs = load_truth_and_legs(outcome_path, leg_path)
    metrics: dict[tuple[str, str], Metrics] = defaultdict(Metrics)
    by_issue: dict[tuple[str, str], dict[str, tuple[Decimal, Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: (Decimal(0), Decimal(0)))
    )
    by_fold: dict[tuple[str, str], dict[str, Metrics]] = defaultdict(
        lambda: defaultdict(Metrics)
    )
    settlement = stage / "group_seed_settlement.csv.gz"
    with (
        settlement.open("wb") as binary,
        gzip.GzipFile(fileobj=binary, mode="wb", mtime=0) as compressed,
        io.TextIOWrapper(compressed, newline="", encoding="utf-8") as handle,
    ):
        writer = csv.DictWriter(
            handle, fieldnames=SETTLEMENT_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        for row in read_gzip(frontier_path, GATE_A_FIELDS):
            group = legs.get(row["group_id"])
            if group is None:
                raise RuntimeError("Gate-A group is outside frozen #95 cohort")
            sequence = []
            product = Decimal(1)
            sources = []
            for leg in group:
                code, sp, source = truth[leg["match_id"]]
                sequence.append(code)
                product *= sp
                sources.append(source)
            omitted = omitted_codes(row["omitted_codes"])
            selected = row["selection_status"] == "SELECTED"
            if not selected:
                hit, status, stake, gross = "NO_BET", "NO_BET", Decimal(0), Decimal(0)
            else:
                hit = (
                    "YES"
                    if all(code != omit for code, omit in zip(sequence, omitted))
                    else "NO"
                )
                status = "SETTLED"
                stake = Decimal(row["stake_yuan"])
                gross = hit_gross(hit, product)
            key = (row["arm"], row["seed"])
            net = metrics[key].add(hit, stake, gross)
            by_fold[key][row["fold"]].add(hit, stake, gross)
            old_net, old_stake = by_issue[key][row["issue"]]
            by_issue[key][row["issue"]] = (old_net + net, old_stake + stake)
            writer.writerow(
                {
                    **row,
                    "quarter": quarter(row["issue"]),
                    "truth_sequence": "".join(sequence),
                    "final_winning_sp_product_uncapped": money(product),
                    "winning_sp_sources": "|".join(sources),
                    "settlement_status": status,
                    "hit": hit,
                    "gross_yuan": money(gross),
                    "net_yuan": money(net),
                    "settlement_factor": "0.65",
                }
            )
    fold_rois = {
        key: [
            metric.gross / metric.stake - 1 for metric in folds.values() if metric.stake
        ]
        for key, folds in by_fold.items()
    }
    return metrics, by_issue, fold_rois


def write_summaries(
    stage: Path,
    metrics: dict[tuple[str, str], Metrics],
    by_issue: dict[tuple[str, str], dict[str, tuple[Decimal, Decimal]]],
    fold_rois: dict[tuple[str, str], list[Decimal]],
) -> None:
    rows = []
    simulation_rows = []
    for key, metric in sorted(metrics.items()):
        arm, seed = key
        net = metric.gross - metric.stake
        values = fold_rois[key]
        rows.append(
            {
                "arm": arm,
                "seed": seed,
                "settled_groups": metric.bets,
                "no_bet_groups": metric.no_bets,
                "hits": metric.hits,
                "hit_rate": ratio(Decimal(metric.hits) / metric.bets)
                if metric.bets
                else "",
                "stake_yuan": money(metric.stake),
                "gross_yuan": money(metric.gross),
                "net_yuan": money(net),
                "roi": ratio(net / metric.stake) if metric.stake else "",
                "max_drawdown_yuan": money(metric.max_drawdown),
                "longest_losing_streak": metric.longest_losing_streak,
                "fold_roi_empirical_range_low": ratio(percentile(values, 0.025)),
                "fold_roi_empirical_range_high": ratio(percentile(values, 0.975)),
            }
        )
        issues = list(by_issue[key].values())
        for bankroll in BANKROLLS:
            totals: list[Decimal] = []
            ruins = 0
            for replicate in range(BOOTSTRAPS):
                cumulative = Decimal(0)
                ruined = False
                indices = stable_bootstrap_indices(
                    f"{arm}|{seed}|{bankroll}|bj98-v2|{replicate}",
                    len(issues),
                    len(issues),
                )
                for index in indices:
                    issue_net, _ = issues[index]
                    cumulative += issue_net
                    ruined = ruined or cumulative <= -Decimal(bankroll)
                totals.append(cumulative)
                ruins += ruined
            simulation_rows.append(
                {
                    "arm": arm,
                    "seed": seed,
                    "bankroll_yuan": bankroll,
                    "replicates": BOOTSTRAPS,
                    "net_q025_yuan": money(percentile(totals, 0.025) or Decimal(0)),
                    "net_median_yuan": money(percentile(totals, 0.5) or Decimal(0)),
                    "net_q975_yuan": money(percentile(totals, 0.975) or Decimal(0)),
                    "loss_threshold_probability": format(
                        Decimal(ruins) / BOOTSTRAPS, ".12f"
                    ),
                }
            )
    for filename, fields, payload in (
        ("arm_seed_summary.csv", SUMMARY_FIELDS, rows),
        (
            "budget_bootstrap.csv",
            (
                "arm",
                "seed",
                "bankroll_yuan",
                "replicates",
                "net_q025_yuan",
                "net_median_yuan",
                "net_q975_yuan",
                "loss_threshold_probability",
            ),
            simulation_rows,
        ),
    ):
        with (stage / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(payload)


def write_control_comparison(
    stage: Path,
    metrics: dict[tuple[str, str], Metrics],
    bj95_control_path: Path,
    bj91_control_path: Path,
) -> None:
    """Bind published #91/#95 controls without recomputing either policy."""
    totals: list[tuple[str, str, str, int, Decimal, Decimal]] = []
    for arm, seed in (
        ("FULL_COVER_CONTROL", "CONTROL"),
        ("FIXED_LOWEST_P_OMIT", "FIXED"),
    ):
        metric = metrics[(arm, seed)]
        totals.append(("BJ98", arm, "", metric.bets, metric.stake, metric.gross))
    with bj95_control_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        buckets: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in reader:
            if (row["arm"], row["depth"]) in (
                ("FULL_COVERAGE_CONTROL", "0"),
                ("CAL_MIN_P", "7"),
            ):
                buckets[(row["arm"], row["depth"])].append(row)
        for (arm, depth), rows in sorted(buckets.items()):
            stake = sum((Decimal(row["stake_yuan"]) for row in rows), Decimal(0))
            gross = sum((Decimal(row["gross_yuan"]) for row in rows), Decimal(0))
            totals.append(("BJ95", arm, depth, len(rows), stake, gross))
    with bj91_control_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
        allowed = {
            "FULL_3_TO_N_ANALYTIC",
            "POINT_SP5_POSITIVE_EV",
            "CONSERVATIVE_M2_SP5_POSITIVE_EV",
        }
        for row in reader:
            if row["cohort"] == "PRIMARY" and row["n"] == "7" and row["arm"] in allowed:
                buckets[row["arm"]].append(row)
        for arm, rows in sorted(buckets.items()):
            stake = sum((Decimal(row["stake_yuan"]) for row in rows), Decimal(0))
            gross = sum((Decimal(row["gross_yuan"]) for row in rows), Decimal(0))
            totals.append(("BJ91", arm, "", len(rows), stake, gross))
    with (stage / "accepted_control_comparison.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=CONTROL_FIELDS, lineterminator="\n")
        writer.writeheader()
        for family, arm, depth, count, stake, gross in totals:
            net = gross - stake
            writer.writerow(
                {
                    "family": family,
                    "arm": arm,
                    "depth": depth,
                    "group_count": count,
                    "stake_yuan": money(stake),
                    "gross_yuan": money(gross),
                    "net_yuan": money(net),
                    "roi": ratio(net / stake) if stake else "",
                }
            )


def write_quality_matched_controls(
    stage: Path,
    frontier_path: Path,
    bj95_control_path: Path,
    bj91_control_path: Path,
) -> None:
    """Compare #91/#95 only on the fixed 3,900 quality-selected identities."""
    selected: set[str] = set()
    for row in read_gzip(frontier_path, GATE_A_FIELDS):
        if (
            row["arm"] == "QUALITY_WEIGHTED_OMIT"
            and row["seed"] == "10001"
            and row["selection_status"] == "SELECTED"
        ):
            selected.add(row["group_id"])
    if len(selected) != 3900:
        raise RuntimeError("quality matched-group identity drift")
    fields = (
        "family",
        "arm",
        "seed",
        "matched_group_count",
        "stake_yuan",
        "gross_yuan",
        "net_yuan",
        "roi",
    )
    rows: list[dict[str, object]] = []
    for row in read_csv(stage / "arm_seed_summary.csv", SUMMARY_FIELDS):
        if row["arm"] == "QUALITY_WEIGHTED_OMIT":
            if row["settled_groups"] != "3900":
                raise RuntimeError("quality candidate matched-group cardinality drift")
            rows.append(
                {
                    "family": "BJ98",
                    "arm": row["arm"],
                    "seed": row["seed"],
                    "matched_group_count": 3900,
                    "stake_yuan": row["stake_yuan"],
                    "gross_yuan": row["gross_yuan"],
                    "net_yuan": row["net_yuan"],
                    "roi": row["roi"],
                }
            )
    for family, path, arm_field, required in (
        (
            "BJ95",
            bj95_control_path,
            "arm",
            {"FULL_COVERAGE_CONTROL", "CAL_MIN_P"},
        ),
        (
            "BJ91",
            bj91_control_path,
            "arm",
            {
                "FULL_3_TO_N_ANALYTIC",
                "POINT_SP5_POSITIVE_EV",
                "CONSERVATIVE_M2_SP5_POSITIVE_EV",
            },
        ),
    ):
        buckets: dict[str, list[dict[str, str]]] = defaultdict(list)
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                depth_ok = family != "BJ95" or (row["arm"], row["depth"]) in (
                    ("FULL_COVERAGE_CONTROL", "0"),
                    ("CAL_MIN_P", "7"),
                )
                n_ok = family != "BJ91" or (
                    row["cohort"] == "PRIMARY" and row["n"] == "7"
                )
                if (
                    depth_ok
                    and n_ok
                    and row[arm_field] in required
                    and row["group_id"] in selected
                ):
                    buckets[row[arm_field]].append(row)
        for arm, matched in sorted(buckets.items()):
            if len(matched) != 3900:
                raise RuntimeError(f"incomplete matched control: {family} {arm}")
            stake = sum((Decimal(row["stake_yuan"]) for row in matched), Decimal(0))
            gross = sum((Decimal(row["gross_yuan"]) for row in matched), Decimal(0))
            rows.append(
                {
                    "family": family,
                    "arm": arm,
                    "seed": "CONTROL",
                    "matched_group_count": len(matched),
                    "stake_yuan": money(stake),
                    "gross_yuan": money(gross),
                    "net_yuan": money(gross - stake),
                    "roi": ratio((gross - stake) / stake) if stake else "",
                }
            )
    with (stage / "quality_matched_control_comparison.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def write_calibration_and_sensitivity(
    stage: Path,
    frontier_path: Path,
    outcome_path: Path,
    leg_path: Path,
) -> None:
    """Report outcome diagnostics without changing the frozen tickets or selection."""
    truth, legs = load_truth_and_legs(outcome_path, leg_path)
    bins: dict[int, dict[str, Decimal | int]] = defaultdict(
        lambda: {
            "legs": 0,
            "top_probability": Decimal(0),
            "top_hit": Decimal(0),
            "brier": Decimal(0),
        }
    )
    for group in legs.values():
        for leg in group:
            probabilities = {code: Decimal(leg[f"p{code}"]) for code in CODES}
            top_code = max(
                CODES, key=lambda code: (probabilities[code], -CODES.index(code))
            )
            top_probability = probabilities[top_code]
            outcome_code = truth[leg["match_id"]][0]
            index = min(9, int(top_probability * 10))
            bucket = bins[index]
            bucket["legs"] += 1
            bucket["top_probability"] += top_probability
            bucket["top_hit"] += outcome_code == top_code
            bucket["brier"] += sum(
                (probability - Decimal(code == outcome_code)) ** 2
                for code, probability in probabilities.items()
            )
    with (stage / "calibration_diagnostics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=CALIBRATION_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        for index, bucket in sorted(bins.items()):
            count = int(bucket["legs"])
            writer.writerow(
                {
                    "top1_probability_bin": f"[{index / 10:.1f},{(index + 1) / 10:.1f})",
                    "leg_count": count,
                    "mean_top1_probability": ratio(bucket["top_probability"] / count),
                    "observed_top1_hit_rate": ratio(bucket["top_hit"] / count),
                    "multiclass_brier_score": ratio(bucket["brier"] / count),
                }
            )

    sensitivity: dict[tuple[str, str, Decimal], list[Decimal]] = defaultdict(list)
    for row in read_gzip(frontier_path, GATE_A_FIELDS):
        if row["selection_status"] != "SELECTED" or row["arm"] not in {
            "WEIGHTED_OMIT",
            "QUALITY_WEIGHTED_OMIT",
        }:
            continue
        group = legs[row["group_id"]]
        omissions = omitted_codes(row["omitted_codes"])
        for temperature in TEMPERATURES:
            retained_mass = Decimal(1)
            for leg, omission in zip(group, omissions):
                probabilities = {code: Decimal(leg[f"p{code}"]) for code in CODES}
                weights = {
                    # This is a descriptive sensitivity table, not a payout or
                    # selection calculation.  Float exponentiation keeps the
                    # 869,180-row replay bounded while the reported values are
                    # serialized back to Decimal deterministically.
                    code: Decimal(str(float(probability) ** (1.0 / float(temperature))))
                    for code, probability in probabilities.items()
                }
                normalized = weights[omission] / sum(weights.values(), Decimal(0))
                retained_mass *= Decimal(1) - normalized
            sensitivity[(row["arm"], row["seed"], temperature)].append(retained_mass)
    with (stage / "probability_misspecification_sensitivity.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(
            handle, fieldnames=SENSITIVITY_FIELDS, lineterminator="\n"
        )
        writer.writeheader()
        for (arm, seed, temperature), masses in sorted(sensitivity.items()):
            writer.writerow(
                {
                    "arm": arm,
                    "seed": seed,
                    "temperature": format(temperature, ".2f"),
                    "selected_groups": len(masses),
                    "mean_fixed_ticket_retained_mass": ratio(
                        sum(masses, Decimal(0)) / len(masses)
                    ),
                }
            )


def write_bankroll_execution(stage: Path) -> None:
    """Exact chronological execution path: tickets cannot use implicit credit."""
    states: dict[tuple[str, str, int], dict[str, object]] = {}
    for summary in read_csv(stage / "arm_seed_summary.csv", SUMMARY_FIELDS):
        for bankroll in BANKROLLS:
            states[(summary["arm"], summary["seed"], bankroll)] = {
                "balance": Decimal(bankroll),
                "executed": 0,
                "unaffordable": 0,
                "issue": "",
                "group": "",
            }
    for row in read_gzip(stage / "group_seed_settlement.csv.gz", SETTLEMENT_FIELDS):
        if row["settlement_status"] != "SETTLED":
            continue
        for bankroll in BANKROLLS:
            state = states[(row["arm"], row["seed"], bankroll)]
            stake, gross = Decimal(row["stake_yuan"]), Decimal(row["gross_yuan"])
            if stake > state["balance"]:
                state["unaffordable"] += 1
                if not state["issue"]:
                    state["issue"], state["group"] = row["issue"], row["group_id"]
                continue
            state["balance"] += gross - stake
            state["executed"] += 1
    with (stage / "bankroll_execution.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=BANKROLL_FIELDS, lineterminator="\n")
        writer.writeheader()
        for (arm, seed, bankroll), state in sorted(states.items()):
            writer.writerow(
                {
                    "arm": arm,
                    "seed": seed,
                    "bankroll_yuan": bankroll,
                    "executed_groups": state["executed"],
                    "unaffordable_groups": state["unaffordable"],
                    "first_unaffordable_issue": state["issue"],
                    "first_unaffordable_group_id": state["group"],
                    "final_balance_yuan": money(state["balance"]),
                }
            )


def build(out: Path) -> dict[str, object]:
    if out.exists():
        raise RuntimeError(f"refusing to overwrite immutable output: {out}")
    gate_a_manifest = exact_manifest(GATE_A, GATE_A_MANIFEST)
    bj95_gate_a_manifest = exact_manifest(BJ95_GATE_A, BJ95_GATE_A_MANIFEST)
    bj95_manifest = exact_manifest(BJ95, BJ95_MANIFEST)
    bj91_manifest = exact_manifest(BJ91, BJ91_MANIFEST)
    with tempfile.TemporaryDirectory(
        prefix=".bj98_gate_b_", dir=out.parent
    ) as temp_name:
        stage = Path(temp_name)
        private_dir = stage / "_authenticated_inputs"
        private_dir.mkdir()
        frontier_path = authenticated_snapshot(
            private_dir,
            "bj98_sampling_frontier.csv.gz",
            GATE_A / "sampling_frontier.csv.gz",
            gate_a_manifest["sampling_frontier.csv.gz"],
        )
        leg_path = authenticated_snapshot(
            private_dir,
            "bj95_safe_legs.csv.gz",
            BJ95_GATE_A / "outcome_safe_n7_legs.csv.gz",
            bj95_gate_a_manifest["outcome_safe_n7_legs.csv.gz"],
            expected_decompressed_sha256=LEG_SHA,
        )
        outcome_path = authenticated_snapshot(
            private_dir,
            "bj95_canonical_outcome_join.csv",
            BJ95 / "canonical_outcome_join.csv",
            bj95_manifest["canonical_outcome_join.csv"],
        )
        bj95_control_path = authenticated_snapshot(
            private_dir,
            "bj95_group_frontier_settlement.csv",
            BJ95 / "group_frontier_settlement.csv",
            bj95_manifest["group_frontier_settlement.csv"],
        )
        bj91_control_path = authenticated_snapshot(
            private_dir,
            "bj91_group_arm_settlement.csv",
            BJ91 / "group_arm_settlement.csv",
            bj91_manifest["group_arm_settlement.csv"],
        )
        metrics, by_issue, fold_rois = settle(
            stage, frontier_path, outcome_path, leg_path
        )
        write_summaries(stage, metrics, by_issue, fold_rois)
        write_control_comparison(stage, metrics, bj95_control_path, bj91_control_path)
        write_quality_matched_controls(
            stage, frontier_path, bj95_control_path, bj91_control_path
        )
        write_bankroll_execution(stage)
        write_calibration_and_sensitivity(stage, frontier_path, outcome_path, leg_path)
        snapshot_hashes = {
            path.name: sha256(path)
            for path in (
                frontier_path,
                leg_path,
                outcome_path,
                bj95_control_path,
                bj91_control_path,
            )
        }
        shutil.rmtree(private_dir)
        card = {
            "issue": 98,
            "stage": "GATE_B_ONE_SHOT_CANONICAL_OUTCOME_SETTLEMENT",
            "gate_a_manifest_sha256": GATE_A_MANIFEST,
            "bj95_gate_a_manifest_sha256": BJ95_GATE_A_MANIFEST,
            "bj95_safe_leg_decompressed_sha256": LEG_SHA,
            "private_snapshot_sha256": snapshot_hashes,
            "private_snapshot_protocol": "every parsed accepted source was byte-verified against its accepted manifest after copy, then parsed only from the private build snapshot",
            "canonical_outcome_bundle": "results/bj95_gate_b_outcome_settlement_v2r8",
            "canonical_outcome_manifest_sha256": BJ95_MANIFEST,
            "bj91_control_manifest_sha256": BJ91_MANIFEST,
            "factor": "0.65",
            "factor_application": "gross=2*0.65*uncapped final winning-SP product for each hit; exactly once",
            "outcome_read_once": True,
            "outcome_payload": "#95 canonical_outcome_join.csv only",
            "controls": "#91 dynamic-EV and #95 structured-pruning accepted comparators",
            "matched_controls": "#91/#95 controls restricted to the exact 3,900 QUALITY_WEIGHTED_OMIT selected group identities",
            "fold_summary": "empirical fold range, not a confidence interval",
            "calibration_diagnostics": "top-1 calibration and multiclass Brier score on the authenticated #95 frozen legs; descriptive only",
            "probability_misspecification_sensitivity": "fixed frozen weighted tickets evaluated at temperature 0.80/1.00/1.20; no omission, selection, stake, or outcome result is changed",
            "bankroll_execution": "chronological frozen CSV order within each issue; a ticket is skipped when its stake exceeds current cash balance; no implicit credit",
            "portable_replay_identity": "CONTENT_SHA256SUMS.json; it hashes the decompressed group settlement payload because gzip transport bytes may vary across supported zlib builds",
            "bootstrap": {
                "unit": "issue",
                "replicates": BOOTSTRAPS,
                "prng": "SHA256-seeded 64-bit LCG; version-independent",
                "bankrolls_yuan": BANKROLLS,
                "interpretation": "loss-threshold distribution, not a ruin model; it does not claim stake-affordability execution",
            },
            "terminal_disposition": "NO_PROMOTION: all 130 frozen candidate arm/seed aggregates have non-positive ROI; matched controls are diagnostic only",
            "scope": "historical research only; no purchase or production promotion",
        }
        (stage / "settlement_card.json").write_text(
            json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.copy2(Path(__file__), stage / "settlement_runner.py")
        # The gzip transport stream can differ between supported Python/zlib
        # builds even with mtime fixed.  Bind its decompressed CSV payload as
        # the portable replay identity while retaining byte hashes below for
        # the exact delivered package.
        content_manifest = {
            path.name: decompressed_sha256(path)
            if path.suffix == ".gz"
            else sha256(path)
            for path in sorted(stage.iterdir())
            if path.is_file()
        }
        (stage / "CONTENT_SHA256SUMS.json").write_text(
            json.dumps(content_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest = {
            path.name: sha256(path)
            for path in sorted(stage.iterdir())
            if path.is_file()
        }
        (stage / "SHA256SUMS.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.copytree(stage, out)
    return {"output": str(out), "arm_seed_summaries": len(metrics)}


def main() -> None:
    global GATE_A, BJ95_GATE_A, BJ95, BJ91
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--gate-a", type=Path, default=GATE_A)
    parser.add_argument("--bj95-gate-a", type=Path, default=BJ95_GATE_A)
    parser.add_argument("--bj95-outcome", type=Path, default=BJ95)
    parser.add_argument("--bj91-control", type=Path, default=BJ91)
    args = parser.parse_args()
    GATE_A, BJ95_GATE_A, BJ95, BJ91 = (
        args.gate_a.resolve(),
        args.bj95_gate_a.resolve(),
        args.bj95_outcome.resolve(),
        args.bj91_control.resolve(),
    )
    print(json.dumps(build(args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
