#!/usr/bin/env python3
"""One-shot canonical outcome settlement for #95's accepted Gate-A v5.

The runner first verifies the immutable v5 pruning package and the immutable
#91 canonical outcome join.  Only then does it join each frozen match identity
to result code and uncapped final winning SP.  It never regenerates a group,
pruning order, threshold, depth, stake, or descriptor.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import shutil
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path


def repository_root(anchor: Path) -> Path:
    resolved = anchor.resolve()
    for candidate in (resolved.parent, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError(f"cannot locate repository root from {anchor}")


ROOT = repository_root(Path(__file__))
FREEZE = ROOT / "results" / "bj95_gate_a_preoutcome_v5"
OUTCOME_SOURCE = ROOT / "results" / "bj91_gate_b_outcome_settlement_v1"
BJ91_SETTLEMENT = OUTCOME_SOURCE / "group_arm_settlement.csv"
OUT = ROOT / "results" / "bj95_gate_b_outcome_settlement_v1"

EXPECTED_GATE_A_MANIFEST = (
    "10b4d6d274aef53e1e1d4abe30cd9f683cf296865ee131f00f5c1e1d16d0725c"
)
EXPECTED_OUTCOME_SOURCE_MANIFEST = (
    "07957d4e21076bc9799f16e3b582e36854a16858436f07adf306260a474c271f"
)
EXPECTED_CANONICAL_DB_SHA256 = (
    "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"
)
EXPECTED_GROUPS = 6_686
EXPECTED_LEGS = 46_802
EXPECTED_FRONTIERS = 240_696
EXPECTED_DELETIONS = 230_527
FACTOR = Decimal("0.65")
STAKE_PER_SEQUENCE = Decimal(2)
CODES = ("3", "1", "0")
MONEY_QUANTUM = Decimal("0.000001")
CONTROL = "FULL_COVERAGE_CONTROL"
PRUNING_ARMS = (
    "CAL_MIN_P",
    "EURO_MIN_P",
    "MIN_PXSP5",
    "MODEL_MARKET_AGREE",
    "RANDOM_HASH_BASELINE",
)
BJ91_COMPARISON_ARMS = (
    "FULL_3_TO_N_ANALYTIC",
    "POINT_SP5_POSITIVE_EV",
    "CONSERVATIVE_M2_SP5_POSITIVE_EV",
)
getcontext().prec = 128

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
FRONTIER_FIELDS = (
    "cohort",
    "group_id",
    "issue",
    "fold",
    "year",
    "arm",
    "depth",
    "disposition",
    "eligible_removals",
    "actual_removals",
    "removed_positions",
    "removed_codes",
    "formula_k",
    "selected_sequence_count",
    "stake_yuan",
    "calibrated_mass",
    "euro_novig_mass",
    "portfolio_descriptor_sha256",
    "generator_version",
)
DELETION_FIELDS = (
    "group_id",
    "arm",
    "removal_rank",
    "position",
    "removed_code",
    "handicap_line_norm",
    "calibrated_probability",
    "euro_novig_probability",
    "predicted_sp",
    "sp5",
    "p_times_sp5",
    "selection_score",
    "score_semantics",
)
OUTCOME_FIELDS = (
    "match_id",
    "result_code",
    "winning_sp",
    "winning_sp_source",
    "settlement_quality",
    "has_trusted_settlement",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def decimal(value: object, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise RuntimeError(f"invalid decimal {label}: {value!r}") from error
    if not parsed.is_finite():
        raise RuntimeError(f"non-finite decimal {label}: {value!r}")
    return parsed


def six(value: Decimal | None) -> str:
    return "" if value is None else format(value.quantize(MONEY_QUANTUM), "f")


def ratio(value: Decimal | None) -> str:
    return "" if value is None else format(value, ".12f")


def write_csv(
    path: Path, fields: Iterable[str], rows: Iterable[dict[str, object]]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv_exact(
    path: Path, expected_fields: tuple[str, ...]
) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected_fields:
            raise RuntimeError(f"schema mismatch for {path}: {reader.fieldnames}")
        return list(reader)


def read_gzip_csv_exact(
    path: Path, expected_fields: tuple[str, ...]
) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected_fields:
            raise RuntimeError(f"schema mismatch for {path}: {reader.fieldnames}")
        return list(reader)


def verify_manifest(bundle: Path, expected_manifest_sha: str) -> dict[str, str]:
    manifest_path = bundle / "SHA256SUMS.json"
    if sha256(manifest_path) != expected_manifest_sha:
        raise RuntimeError(f"unaccepted manifest identity: {bundle}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or not manifest
        or len(manifest) != len(set(manifest))
    ):
        raise RuntimeError(f"invalid manifest: {bundle}")
    actual = {
        path.name: sha256(path)
        for path in bundle.iterdir()
        if path.is_file() and path.name != manifest_path.name
    }
    if actual != manifest:
        raise RuntimeError(f"manifest is not exact coverage: {bundle}")
    return manifest


def frozen_quarter(issue: str) -> str:
    if len(issue) < 5 or not issue.isdigit():
        raise RuntimeError(f"invalid frozen issue: {issue!r}")
    month = int(issue[2:4])
    if month not in range(1, 13):
        raise RuntimeError(f"invalid frozen issue month: {issue!r}")
    return f"20{issue[:2]}-Q{(month - 1) // 3 + 1}"


def verify_pre_outcome_inputs() -> dict[str, object]:
    verify_manifest(FREEZE, EXPECTED_GATE_A_MANIFEST)
    verify_manifest(OUTCOME_SOURCE, EXPECTED_OUTCOME_SOURCE_MANIFEST)
    card = json.loads((FREEZE / "preoutcome_card.json").read_text(encoding="utf-8"))
    if (
        card.get("contract") != "BJ-HIST-N7-PRUNING-001"
        or card.get("stage") != "GATE_A_PREOUTCOME_STRUCTURED_PRUNING_FREEZE"
    ):
        raise RuntimeError("unexpected Gate-A contract")
    counts = card.get("counts", {})
    if counts != {
        "groups": EXPECTED_GROUPS,
        "legs": EXPECTED_LEGS,
        "frontier_rows": EXPECTED_FRONTIERS,
        "deletion_rows": EXPECTED_DELETIONS,
    }:
        raise RuntimeError("Gate-A cardinality binding drift")
    outcome_card = json.loads(
        (OUTCOME_SOURCE / "settlement_card.json").read_text(encoding="utf-8")
    )
    if (
        outcome_card.get("provenance", {}).get("source_db_sha256")
        != EXPECTED_CANONICAL_DB_SHA256
    ):
        raise RuntimeError("canonical outcome source lineage drift")
    if tuple(outcome_card.get("outcome_read_whitelist", ())) != (
        "match_features.match_id",
        "match_features.result_code",
        "match_features.winning_sp",
        "match_features.winning_sp_source",
        "match_features.settlement_quality",
        "match_features.has_trusted_settlement",
    ):
        raise RuntimeError("canonical outcome source read contract drift")
    return {
        "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
        "canonical_outcome_join_manifest_sha256": EXPECTED_OUTCOME_SOURCE_MANIFEST,
        "canonical_source_db_sha256": EXPECTED_CANONICAL_DB_SHA256,
    }


def load_frozen_inputs() -> tuple[
    dict[str, list[dict[str, str]]], list[dict[str, str]], list[dict[str, str]]
]:
    legs = read_gzip_csv_exact(FREEZE / "outcome_safe_n7_legs.csv.gz", LEG_FIELDS)
    frontiers = read_gzip_csv_exact(FREEZE / "pruning_frontier.csv.gz", FRONTIER_FIELDS)
    deletions = read_gzip_csv_exact(
        FREEZE / "pruning_deletions.csv.gz", DELETION_FIELDS
    )
    if (
        len(legs) != EXPECTED_LEGS
        or len(frontiers) != EXPECTED_FRONTIERS
        or len(deletions) != EXPECTED_DELETIONS
    ):
        raise RuntimeError("frozen input cardinality mismatch")
    by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for leg in legs:
        by_group[leg["group_id"]].append(leg)
    if len(by_group) != EXPECTED_GROUPS:
        raise RuntimeError("frozen group count mismatch")
    for group_id, group_legs in by_group.items():
        group_legs.sort(key=lambda row: int(row["position"]))
        if len(group_legs) != 7 or [int(row["position"]) for row in group_legs] != list(
            range(1, 8)
        ):
            raise RuntimeError(f"invalid frozen leg ordering: {group_id}")
    frontier_by_group: dict[str, set[tuple[str, int]]] = defaultdict(set)
    for row in frontiers:
        frontier_by_group[row["group_id"]].add((row["arm"], int(row["depth"])))
    if sum(len(keys) for keys in frontier_by_group.values()) != len(frontiers):
        raise RuntimeError("duplicate frozen frontier key")
    expected_per_group = {
        (CONTROL, 0),
        *((arm, depth) for arm in PRUNING_ARMS for depth in range(1, 8)),
    }
    for group_id in by_group:
        observed = frontier_by_group.get(group_id, set())
        if observed != expected_per_group:
            raise RuntimeError(f"incomplete frozen frontier: {group_id}")
    return by_group, frontiers, deletions


def load_canonical_outcomes(
    frozen_match_ids: set[str],
) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    # This is Gate B's single outcome/final-SP read.  The immutable #91 source
    # itself is manifest-pinned before this function may be called.
    source_rows = read_csv_exact(OUTCOME_SOURCE / "outcome_join.csv", OUTCOME_FIELDS)
    outcomes = {
        row["match_id"]: row
        for row in source_rows
        if row["match_id"] in frozen_match_ids
    }
    if len(outcomes) != len(frozen_match_ids):
        raise RuntimeError(
            f"canonical outcomes do not cover frozen identities: {len(outcomes)} != {len(frozen_match_ids)}"
        )
    if any(
        row["result_code"] not in CODES
        or not row["winning_sp_source"]
        or row["settlement_quality"] != "trusted"
        or row["has_trusted_settlement"] != "1"
        or decimal(row["winning_sp"], "final SP") <= 0
        for row in outcomes.values()
    ):
        raise RuntimeError("invalid canonical result or final winning SP")
    ordered = [outcomes[match_id] for match_id in sorted(outcomes, key=int)]
    return outcomes, ordered


def removals_by_frontier(
    deletions: list[dict[str, str]],
) -> dict[tuple[str, str], list[dict[str, str]]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in deletions:
        grouped[(row["group_id"], row["arm"])].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: int(row["removal_rank"]))
        if [int(row["removal_rank"]) for row in rows] != list(range(1, len(rows) + 1)):
            raise RuntimeError("invalid frozen deletion ordering")
    return grouped


def settled_gross_yuan(hit: str, final_product: Decimal) -> Decimal:
    """Return the production Gate-B payout from an injected settled outcome."""
    if hit not in ("YES", "NO", "NO_BET"):
        raise RuntimeError(f"invalid hit status for payout: {hit!r}")
    if final_product <= 0:
        raise RuntimeError("nonpositive final winning SP product")
    return Decimal(0) if hit != "YES" else STAKE_PER_SEQUENCE * FACTOR * final_product


def hit_and_geometry(
    frontier: dict[str, str], truth: dict[int, str], removals: list[dict[str, str]]
) -> tuple[str, int, Decimal, Decimal, str]:
    depth = int(frontier["depth"])
    formula_k = int(frontier["formula_k"])
    expected_k = 3**7 if depth == 0 else 2**depth * 3 ** (7 - depth)
    if formula_k != expected_k:
        raise RuntimeError("frozen K formula drift")
    disposition = frontier["disposition"]
    selected = int(frontier["selected_sequence_count"])
    stake = decimal(frontier["stake_yuan"], "frozen stake")
    if disposition == "UNAVAILABLE_BY_RULE":
        if selected != 0 or stake != 0 or frontier["actual_removals"] != "0":
            raise RuntimeError("unavailable frontier has stake or selected sequences")
        return "NO_BET", 0, Decimal(0), Decimal(0), disposition
    if disposition != "AVAILABLE":
        raise RuntimeError(f"unknown Gate-A disposition: {disposition!r}")
    if selected != formula_k or stake != STAKE_PER_SEQUENCE * formula_k:
        raise RuntimeError("frozen selected count/stake drift")
    if depth == 0:
        if frontier["arm"] != CONTROL or frontier["actual_removals"] != "0":
            raise RuntimeError("invalid full-coverage control")
        return "YES", selected, stake, Decimal(1), disposition
    if frontier["arm"] not in PRUNING_ARMS or int(frontier["actual_removals"]) != depth:
        raise RuntimeError("invalid frozen pruning geometry")
    chosen = removals[:depth]
    if len(chosen) != depth:
        raise RuntimeError("missing frozen removals")
    positions = [int(row["position"]) for row in chosen]
    codes = [row["removed_code"] for row in chosen]
    if positions != [
        int(value) for value in frontier["removed_positions"].split("|")
    ] or codes != frontier["removed_codes"].split("|"):
        raise RuntimeError("frontier/deletion prefix mismatch")
    hit = (
        "NO"
        if any(truth[position] == code for position, code in zip(positions, codes))
        else "YES"
    )
    return hit, selected, stake, Decimal(frontier["calibrated_mass"]), disposition


def sorted_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(rows, key=lambda row: (int(str(row["issue"])), str(row["group_id"])))


def net_and_stake(rows: list[dict[str, object]]) -> tuple[Decimal, Decimal]:
    stake = sum((decimal(row["stake_yuan"], "stake") for row in rows), Decimal(0))
    net = sum((decimal(row["net_yuan"], "net") for row in rows), Decimal(0))
    return net, stake


def aggregate(rows: list[dict[str, object]], **scope: object) -> dict[str, object]:
    bet_rows = [row for row in rows if row["settlement_status"] == "SETTLED"]
    no_bet = [row for row in rows if row["settlement_status"] != "SETTLED"]
    stake = sum((decimal(row["stake_yuan"], "stake") for row in bet_rows), Decimal(0))
    gross = sum((decimal(row["gross_yuan"], "gross") for row in bet_rows), Decimal(0))
    net = gross - stake
    cumulative = peak = maximum_drawdown = Decimal(0)
    no_hit_streak = nonpositive_streak = max_no_hit = max_nonpositive = 0
    for row in sorted_rows(bet_rows):
        row_net = decimal(row["net_yuan"], "net")
        cumulative += row_net
        peak = max(peak, cumulative)
        maximum_drawdown = max(maximum_drawdown, peak - cumulative)
        if row["hit"] == "YES":
            no_hit_streak = 0
        else:
            no_hit_streak += 1
            max_no_hit = max(max_no_hit, no_hit_streak)
        if row_net > 0:
            nonpositive_streak = 0
        else:
            nonpositive_streak += 1
            max_nonpositive = max(max_nonpositive, nonpositive_streak)
    hits = sum(row["hit"] == "YES" for row in bet_rows)
    profitable_hits = sum(
        row["hit"] == "YES" and decimal(row["net_yuan"], "net") > 0 for row in bet_rows
    )
    mean_cal_mass = (
        sum(
            (decimal(row["calibrated_mass"], "cal mass") for row in bet_rows),
            Decimal(0),
        )
        / Decimal(len(bet_rows))
        if bet_rows
        else None
    )
    mean_euro_mass = (
        sum(
            (decimal(row["euro_novig_mass"], "euro mass") for row in bet_rows),
            Decimal(0),
        )
        / Decimal(len(bet_rows))
        if bet_rows
        else None
    )
    # Concentration is intentionally positive-only, but robustness must remove
    # the issue with the largest signed total net, including any losing issue.
    positive = [
        (max(Decimal(0), decimal(row["net_yuan"], "net")), row) for row in bet_rows
    ]
    total_positive = sum((value for value, _ in positive), Decimal(0))
    positive_by_issue: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    signed_by_issue: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for value, row in positive:
        positive_by_issue[str(row["issue"])] += value
        signed_by_issue[str(row["issue"])] += decimal(row["net_yuan"], "net")
    best = max(bet_rows, key=lambda row: decimal(row["net_yuan"], "net"), default=None)
    best_issue = max(signed_by_issue, key=signed_by_issue.get, default="")
    without_best_group = [
        row for row in bet_rows if best is None or row["group_id"] != best["group_id"]
    ]
    without_best_issue = [row for row in bet_rows if row["issue"] != best_issue]
    ex_group_net, ex_group_stake = net_and_stake(without_best_group)
    ex_issue_net, ex_issue_stake = net_and_stake(without_best_issue)
    return {
        **scope,
        "frontier_keys": len(rows),
        "bet_groups": len(bet_rows),
        "no_bet_groups": len(no_bet),
        "coverage_hits": hits,
        "coverage_hit_rate": ratio(Decimal(hits) / Decimal(len(bet_rows)))
        if bet_rows
        else "",
        "profitable_hits": profitable_hits,
        "profitable_hit_rate": ratio(Decimal(profitable_hits) / Decimal(len(bet_rows)))
        if bet_rows
        else "",
        "mean_calibrated_retained_mass": ratio(mean_cal_mass),
        "mean_euro_retained_mass": ratio(mean_euro_mass),
        "total_k": sum(int(str(row["selected_sequence_count"])) for row in bet_rows),
        "stake_yuan": six(stake),
        "gross_yuan": six(gross),
        "net_yuan": six(net),
        "roi": ratio(net / stake) if stake else "",
        "max_drawdown_yuan": six(maximum_drawdown),
        "longest_no_hit_streak": max_no_hit,
        "longest_nonpositive_net_streak": max_nonpositive,
        "best_net_group_id": "" if best is None else str(best["group_id"]),
        "best_net_issue": best_issue,
        "best_net_yuan": "" if best is None else six(decimal(best["net_yuan"], "net")),
        "ex_best_group_net_yuan": six(ex_group_net),
        "ex_best_group_roi": ratio(ex_group_net / ex_group_stake)
        if ex_group_stake
        else "",
        "ex_best_issue_net_yuan": six(ex_issue_net),
        "ex_best_issue_roi": ratio(ex_issue_net / ex_issue_stake)
        if ex_issue_stake
        else "",
        "positive_net_top_group_share": ratio(
            max((value for value, _ in positive), default=Decimal(0)) / total_positive
        )
        if total_positive
        else "",
        "positive_net_top_issue_share": ratio(
            max(positive_by_issue.values(), default=Decimal(0)) / total_positive
        )
        if total_positive
        else "",
    }


def summarise(
    rows: list[dict[str, object]],
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    overview: list[dict[str, object]] = []
    annual: list[dict[str, object]] = []
    quarterly: list[dict[str, object]] = []
    loyo: list[dict[str, object]] = []
    keys = sorted({(str(row["arm"]), int(str(row["depth"]))) for row in rows})
    for arm, depth in keys:
        members = [
            row for row in rows if row["arm"] == arm and int(str(row["depth"])) == depth
        ]
        overview.append(aggregate(members, arm=arm, depth=depth, scope="ALL"))
        for year in sorted({str(row["year"]) for row in members}):
            annual.append(
                aggregate(
                    [row for row in members if row["year"] == year],
                    arm=arm,
                    depth=depth,
                    scope="YEAR",
                    scope_value=year,
                )
            )
            loyo.append(
                aggregate(
                    [row for row in members if row["year"] != year],
                    arm=arm,
                    depth=depth,
                    scope="LEAVE_ONE_YEAR_OUT",
                    scope_value=year,
                )
            )
        for quarter in sorted({str(row["quarter"]) for row in members}):
            quarterly.append(
                aggregate(
                    [row for row in members if row["quarter"] == quarter],
                    arm=arm,
                    depth=depth,
                    scope="QUARTER",
                    scope_value=quarter,
                )
            )
    return overview, annual, quarterly, loyo


def load_bj91_comparison(
    group_ids: set[str],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    with BJ91_SETTLEMENT.open(newline="", encoding="utf-8") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["cohort"] == "PRIMARY"
            and row["n"] == "7"
            and row["group_id"] in group_ids
            and row["arm"] in BJ91_COMPARISON_ARMS
        ]
    expected = len(group_ids) * len(BJ91_COMPARISON_ARMS)
    if len(rows) != expected:
        raise RuntimeError("#91 comparison does not exactly cover frozen #95 groups")
    transformed = []
    for row in rows:
        transformed.append(
            {
                "arm": f"BJ91::{row['arm']}",
                "depth": "",
                "issue": row["issue"],
                "year": row["year"],
                "quarter": row["quarter"],
                "group_id": row["group_id"],
                "settlement_status": row["settlement_status"],
                "selected_sequence_count": row["k"],
                "stake_yuan": row["stake_yuan"],
                "gross_yuan": row["gross_yuan"],
                "net_yuan": row["net_yuan"],
                "hit": row["hit"],
                "calibrated_mass": row["retained_mass"],
                "euro_novig_mass": row["retained_mass"],
            }
        )
    overview = []
    for arm in sorted({str(row["arm"]) for row in transformed}):
        overview.append(
            aggregate(
                [row for row in transformed if row["arm"] == arm],
                arm=arm,
                depth="",
                scope="SAME_6686_GROUPS",
            )
        )
    return transformed, overview


def nomination(
    overview: list[dict[str, object]],
    annual: list[dict[str, object]],
    loyo: list[dict[str, object]],
) -> dict[str, object]:
    """A predeclared conservative rule; it never tunes an arm or threshold."""
    candidates = []
    for row in overview:
        arm, depth = str(row["arm"]), int(str(row["depth"]))
        if (
            arm == CONTROL
            or not row["roi"]
            or Decimal(str(row["roi"])) <= 0
            or Decimal(str(row["ex_best_group_roi"])) <= 0
            or Decimal(str(row["ex_best_issue_roi"])) <= 0
        ):
            continue
        related_annual = [
            item
            for item in annual
            if item["arm"] == arm and int(str(item["depth"])) == depth
        ]
        related_loyo = [
            item
            for item in loyo
            if item["arm"] == arm and int(str(item["depth"])) == depth
        ]
        if (
            related_annual
            and related_loyo
            and all(
                item["roi"] and Decimal(str(item["roi"])) > 0
                for item in [*related_annual, *related_loyo]
            )
        ):
            candidates.append((depth, arm, row))
    if not candidates:
        return {
            "decision": "NO_PROMOTION",
            "rule": "No frozen pruning frontier satisfied positive ALL, ex-best-group, ex-best-issue, every annual, and every LOYO ROI simultaneously.",
        }
    depth, arm, row = min(candidates, key=lambda item: (item[0], item[1]))
    return {
        "decision": "NOMINATION",
        "rule": "Lowest depth then lexical arm among the predeclared all-positive stability set.",
        "arm": arm,
        "depth": depth,
        "all_roi": row["roi"],
        "ex_best_group_roi": row["ex_best_group_roi"],
        "ex_best_issue_roi": row["ex_best_issue_roi"],
    }


def main() -> int:
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=OUT, help="new immutable Gate-B output directory"
    )
    args = parser.parse_args()
    OUT = args.output.resolve()
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite immutable output: {OUT}")
    stage = Path(tempfile.mkdtemp(prefix="bj95_gate_b_", dir=OUT.parent))
    try:
        provenance = verify_pre_outcome_inputs()
        legs_by_group, frontiers, deletions = load_frozen_inputs()
        match_ids = {leg["match_id"] for legs in legs_by_group.values() for leg in legs}
        outcomes, outcome_rows = load_canonical_outcomes(match_ids)
        deletion_lookup = removals_by_frontier(deletions)
        settlement_rows: list[dict[str, object]] = []
        for frontier in sorted(
            frontiers,
            key=lambda row: (
                int(row["issue"]),
                row["group_id"],
                row["arm"],
                int(row["depth"]),
            ),
        ):
            group_id = frontier["group_id"]
            legs = legs_by_group[group_id]
            truth = {
                int(leg["position"]): outcomes[leg["match_id"]]["result_code"]
                for leg in legs
            }
            final_product = Decimal(1)
            for leg in legs:
                final_product *= decimal(
                    outcomes[leg["match_id"]]["winning_sp"], "final winning SP"
                )
            hit, selected, stake, cal_mass, disposition = hit_and_geometry(
                frontier, truth, deletion_lookup.get((group_id, frontier["arm"]), [])
            )
            euro_mass = (
                Decimal(frontier["euro_novig_mass"])
                if frontier["euro_novig_mass"]
                else Decimal(0)
            )
            gross = settled_gross_yuan(hit, final_product)
            net = gross - stake
            break_even_threshold = (
                Decimal(selected) / (FACTOR * final_product) if selected else None
            )
            settlement_rows.append(
                {
                    "cohort": frontier["cohort"],
                    "group_id": group_id,
                    "issue": frontier["issue"],
                    "year": frontier["year"],
                    "quarter": frozen_quarter(frontier["issue"]),
                    "fold": frontier["fold"],
                    "arm": frontier["arm"],
                    "depth": frontier["depth"],
                    "gate_a_disposition": disposition,
                    "settlement_status": "SETTLED"
                    if disposition == "AVAILABLE"
                    else "NO_BET",
                    "eligible_removals": frontier["eligible_removals"],
                    "actual_removals": frontier["actual_removals"],
                    "removed_positions": frontier["removed_positions"],
                    "removed_codes": frontier["removed_codes"],
                    "portfolio_descriptor_sha256": frontier[
                        "portfolio_descriptor_sha256"
                    ],
                    "formula_k": frontier["formula_k"],
                    "selected_sequence_count": selected,
                    "stake_yuan": six(stake),
                    "calibrated_mass": ratio(cal_mass),
                    "euro_novig_mass": ratio(euro_mass),
                    "truth_sequence": "".join(
                        truth[position] for position in range(1, 8)
                    ),
                    "final_winning_sp_product_uncapped": six(final_product),
                    "winning_sp_sources": ";".join(
                        sorted(
                            {
                                outcomes[leg["match_id"]]["winning_sp_source"]
                                for leg in legs
                            }
                        )
                    ),
                    "hit": hit,
                    "gross_yuan": six(gross),
                    "net_yuan": six(net),
                    "settlement_factor": "0.65",
                    "paid_cent_rounding_applied": "NO",
                    "hit_break_even_threshold": ratio(break_even_threshold),
                    "hit_profit_after_factor": ""
                    if hit != "YES"
                    else ("YES" if gross > stake else "NO"),
                }
            )
        if len(settlement_rows) != EXPECTED_FRONTIERS:
            raise RuntimeError("settlement frontier cardinality drift")
        overview, annual, quarterly, loyo = summarise(settlement_rows)
        bj91_rows, bj91_overview = load_bj91_comparison(set(legs_by_group))
        own_control = {
            row["group_id"]: row
            for row in settlement_rows
            if row["arm"] == CONTROL and row["depth"] == "0"
        }
        bj91_control = {
            row["group_id"]: row
            for row in bj91_rows
            if row["arm"] == "BJ91::FULL_3_TO_N_ANALYTIC"
        }
        reconciliation = []
        for group_id in sorted(own_control):
            own, inherited = own_control[group_id], bj91_control.get(group_id)
            if (
                inherited is None
                or own["stake_yuan"] != inherited["stake_yuan"]
                or own["gross_yuan"] != inherited["gross_yuan"]
                or own["net_yuan"] != inherited["net_yuan"]
            ):
                raise RuntimeError(
                    f"#91 full-control reconciliation failed: {group_id}"
                )
            reconciliation.append(
                {
                    "group_id": group_id,
                    "issue": own["issue"],
                    "stake_yuan": own["stake_yuan"],
                    "gross_yuan": own["gross_yuan"],
                    "net_yuan": own["net_yuan"],
                    "match": "YES",
                }
            )
        decision = nomination(overview, annual, loyo)
        fields = list(settlement_rows[0])
        write_csv(stage / "canonical_outcome_join.csv", OUTCOME_FIELDS, outcome_rows)
        write_csv(stage / "group_frontier_settlement.csv", fields, settlement_rows)
        write_csv(stage / "frontier_overview.csv", list(overview[0]), overview)
        write_csv(stage / "annual_summary.csv", list(annual[0]), annual)
        write_csv(stage / "quarterly_summary.csv", list(quarterly[0]), quarterly)
        write_csv(stage / "leave_one_year_out_summary.csv", list(loyo[0]), loyo)
        write_csv(
            stage / "bj91_same_group_comparison.csv",
            list(bj91_overview[0]),
            bj91_overview,
        )
        write_csv(
            stage / "full_control_reconciliation_with_bj91.csv",
            list(reconciliation[0]),
            reconciliation,
        )
        (stage / "decision.json").write_text(
            json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.copyfile(__file__, stage / "settlement_runner.py")
        card = {
            "issue": 95,
            "stage": "GATE_B_ONE_SHOT_CANONICAL_OUTCOME_SETTLEMENT",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "provenance": provenance,
            "input_freeze": "results/bj95_gate_a_preoutcome_v5",
            "canonical_outcome_source": "results/bj91_gate_b_outcome_settlement_v1/outcome_join.csv",
            "outcome_read_once": True,
            "settlement_rule": "For each available frozen frontier: stake=2*K; hit iff no frozen removed code equals its final result; gross=2*0.65*product(uncapped final winning SP) on hit else 0; factor exactly once; pre-round Decimal serialized to 6 places.",
            "no_bet_rule": "Gate-A UNAVAILABLE_BY_RULE rows retain K formula but have selected_sequence_count=0, stake=0, gross=0, net=0, and are reported as NO_BET.",
            "decision_rule": decision["rule"],
            "scope": "historical research only; no purchase, production policy, or promotion claim before PI terminal review.",
        }
        (stage / "settlement_card.json").write_text(
            json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        manifest = {
            path.name: sha256(path)
            for path in sorted(stage.iterdir())
            if path.is_file()
        }
        (stage / "SHA256SUMS.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(stage, OUT)
        print(
            json.dumps(
                {
                    "output": str(OUT),
                    "manifest_sha256": sha256(OUT / "SHA256SUMS.json"),
                    "frontier_rows": len(settlement_rows),
                    "decision": decision["decision"],
                },
                sort_keys=True,
            )
        )
        return 0
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
