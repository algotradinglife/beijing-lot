#!/usr/bin/env python3
"""One-shot canonical outcome settlement for #98's immutable Gate-A freeze."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import random
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
BJ95_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
BJ91_MANIFEST = "07957d4e21076bc9799f16e3b582e36854a16858436f07adf306260a474c271f"
LEG_SHA = "369c2ab398cb996bcd913f9ff7d3d71431303c957bb349e43b774c87c40e377e"
BOOTSTRAPS = 200
BANKROLLS = (10_000, 100_000, 1_000_000)

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
    "fold_roi_ci_low",
    "fold_roi_ci_high",
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


def repository_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("could not locate repository root")


ROOT = repository_root(Path(__file__))
GATE_A = ROOT / "results" / "bj98_gate_a_preoutcome_v1"
BJ95 = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
BJ95_GATE_A = ROOT / "results" / "bj95_gate_a_preoutcome_v5"
BJ91 = ROOT / "results" / "bj91_gate_b_outcome_settlement_v1"
OUT = ROOT / "results" / "bj98_gate_b_outcome_settlement_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
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


def load_truth_and_legs() -> tuple[
    dict[str, tuple[str, Decimal, str]], dict[str, list[dict[str, str]]]
]:
    outcome = {
        row["match_id"]: (
            row["result_code"],
            Decimal(row["winning_sp"]),
            row["winning_sp_source"],
        )
        for row in read_csv(BJ95 / "canonical_outcome_join.csv", OUTCOME_FIELDS)
    }
    if any(code not in CODES or sp <= 0 for code, sp, _ in outcome.values()):
        raise RuntimeError("invalid canonical outcome payload")
    legs: dict[str, list[dict[str, str]]] = defaultdict(list)
    with gzip.open(
        BJ95_GATE_A / "outcome_safe_n7_legs.csv.gz", "rt", encoding="utf-8", newline=""
    ) as handle:
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


def settle(
    stage: Path,
) -> tuple[
    dict[tuple[str, str], Metrics],
    dict[tuple[str, str], dict[str, tuple[Decimal, Decimal]]],
    dict[tuple[str, str], list[Decimal]],
]:
    truth, legs = load_truth_and_legs()
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
        for row in read_gzip(GATE_A / "sampling_frontier.csv.gz", GATE_A_FIELDS):
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
                gross = Decimal(2) * FACTOR * product if hit == "YES" else Decimal(0)
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
                "fold_roi_ci_low": ratio(percentile(values, 0.025)),
                "fold_roi_ci_high": ratio(percentile(values, 0.975)),
            }
        )
        issues = list(by_issue[key].values())
        for bankroll in BANKROLLS:
            rng = random.Random(f"{arm}|{seed}|{bankroll}|bj98-v1")
            totals: list[Decimal] = []
            ruins = 0
            for _ in range(BOOTSTRAPS):
                cumulative = Decimal(0)
                ruined = False
                for _ in issues:
                    issue_net, _ = issues[rng.randrange(len(issues))]
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
                    "ruin_probability": format(Decimal(ruins) / BOOTSTRAPS, ".12f"),
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
                "ruin_probability",
            ),
            simulation_rows,
        ),
    ):
        with (stage / filename).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(payload)


def write_control_comparison(
    stage: Path, metrics: dict[tuple[str, str], Metrics]
) -> None:
    """Bind published #91/#95 controls without recomputing either policy."""
    totals: list[tuple[str, str, str, int, Decimal, Decimal]] = []
    for arm, seed in (
        ("FULL_COVER_CONTROL", "CONTROL"),
        ("FIXED_LOWEST_P_OMIT", "FIXED"),
    ):
        metric = metrics[(arm, seed)]
        totals.append(("BJ98", arm, "", metric.bets, metric.stake, metric.gross))
    with (BJ95 / "group_frontier_settlement.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
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
    with (BJ91 / "group_arm_settlement.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
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


def build(out: Path) -> dict[str, object]:
    if out.exists():
        raise RuntimeError(f"refusing to overwrite immutable output: {out}")
    exact_manifest(GATE_A, GATE_A_MANIFEST)
    exact_manifest(BJ95, BJ95_MANIFEST)
    exact_manifest(BJ91, BJ91_MANIFEST)
    with tempfile.TemporaryDirectory(
        prefix=".bj98_gate_b_", dir=out.parent
    ) as temp_name:
        stage = Path(temp_name)
        metrics, by_issue, fold_rois = settle(stage)
        write_summaries(stage, metrics, by_issue, fold_rois)
        write_control_comparison(stage, metrics)
        card = {
            "issue": 98,
            "stage": "GATE_B_ONE_SHOT_CANONICAL_OUTCOME_SETTLEMENT",
            "gate_a_manifest_sha256": GATE_A_MANIFEST,
            "canonical_outcome_bundle": "results/bj95_gate_b_outcome_settlement_v2r8",
            "canonical_outcome_manifest_sha256": BJ95_MANIFEST,
            "bj91_control_manifest_sha256": BJ91_MANIFEST,
            "factor": "0.65",
            "factor_application": "gross=2*0.65*uncapped final winning-SP product for each hit; exactly once",
            "outcome_read_once": True,
            "outcome_payload": "#95 canonical_outcome_join.csv only",
            "controls": "#91 dynamic-EV and #95 structured-pruning are bound accepted comparators; exact primary-group comparison is reserved for terminal report",
            "bootstrap": {
                "unit": "issue",
                "replicates": BOOTSTRAPS,
                "bankrolls_yuan": BANKROLLS,
            },
            "scope": "historical research only; no purchase or production promotion",
        }
        (stage / "settlement_card.json").write_text(
            json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.copy2(Path(__file__), stage / "settlement_runner.py")
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    print(json.dumps(build(parser.parse_args().output), sort_keys=True))


if __name__ == "__main__":
    main()
