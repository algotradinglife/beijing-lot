#!/usr/bin/env python3
"""Build #176 issue-ordered equity and risk diagnostics from #167/#170.

The accepted #170 settlement implementation is replayed for native-support
issue tax amounts.  The accepted #170 common-support contribution ledger is
used byte-for-byte for the matched three-way view.  This script does not scan
selectors, allocation parameters, or outcomes beyond those already frozen by
#167/#170.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
import shutil
import statistics
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


CONTRACT = "BJ-HIST-N7-EQUITY-RISK-001"
VERSION = "bj176-issue-equity-risk-v1"
EXPECTED_BJ170_GATE_B_MANIFEST = (
    "08e83353ad483e5d75911116a413186f007385f5dd37b8c4b757ac903221e512"
)
EXPECTED_BJ170_GATE_B_CONTENT = (
    "75325aa0f60e277ad3fbf9d90116450833106bc3863b412ea3efcad9948a47b2"
)
EXPECTED_BJ137_GATE_A_MANIFEST = (
    "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df"
)
EXPECTED_BJ137_GATE_A_CONTENT = (
    "36d6afcc33a5b5ceb3e4a990bfe6ec05503be115270c3489f4973dc3a59dd236"
)
EXPECTED_ISSUE_CENSUS_SHA256 = (
    "69d7463b6f83af4127059d6ea34095292646ec2a98abc39d56551b76d6ea6dd5"
)
REQUIRED_ARMS = (
    ("BEST_FULL", "FULL_ENUMERATED", "BEST_FULL_FULL"),
    ("MODEL_SOURCE", "MODEL_CAP1_M512", "MODEL_SOURCE_MODEL_CAP1_M512"),
    ("Q_SOURCE", "Q_TOP_MASS_M192", "Q_SOURCE_Q_TOP_MASS_M192"),
)
SUPPORT_NATIVE = "NATIVE_SELECTOR"
SUPPORT_COMMON = "THREE_WAY_COMMON"
RETURN_CALENDAR = "CALENDAR_EQUITY"
RETURN_ACTIVE = "ACTIVE_STAKE"
BANKROLL_SCALES = (0.5, 1.0, 2.0)
MONEY_FIELDS = (
    "planned_stake_yuan",
    "stake_yuan",
    "gross_pre_tax_yuan",
    "tax_yuan",
    "pre_tax_net_yuan",
    "tax_adjusted_net_yuan",
)


def repo_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
BJ170 = ROOT / "results" / "bj170_gate_b_selector_allocator_stack_v1"
BJ137 = ROOT / "results" / "bj137_gate_a_preoutcome_v2"
BJ170_GATE_A = ROOT / "results" / "bj170_gate_a_preoutcome_v2"
DEFAULT_OUTPUT = ROOT / "results" / "bj176_issue_equity_risk_v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path, fields: Sequence[str], rows: Iterable[dict[str, object]]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, lineterminator="\n", extrasaction="raise"
        )
        writer.writeheader()
        writer.writerows(rows)


def write_gzip(
    path: Path, fields: Sequence[str], rows: Iterable[dict[str, object]]
) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
            writer = csv.DictWriter(
                text, fieldnames=fields, lineterminator="\n", extrasaction="raise"
            )
            writer.writeheader()
            writer.writerows(rows)
            text.flush()
            text.detach()


def fmt_money(value: float) -> str:
    return f"{value:.6f}"


def fmt_ratio(value: float | None) -> str:
    return "" if value is None or not math.isfinite(value) else f"{value:.12f}"


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"module loader unavailable: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_package(
    directory: Path, expected_manifest: str, expected_content: str
) -> dict[str, str]:
    if sha256_file(directory / "SHA256SUMS.json") != expected_manifest:
        raise RuntimeError(f"source manifest drift: {directory.name}")
    if sha256_file(directory / "CONTENT_IDENTITY.json") != expected_content:
        raise RuntimeError(f"source content identity drift: {directory.name}")
    manifest = json.loads((directory / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = sorted(
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    )
    if sorted(manifest) != actual:
        raise RuntimeError(f"source manifest coverage drift: {directory.name}")
    for name, expected in manifest.items():
        if sha256_file(directory / name) != expected:
            raise RuntimeError(f"source payload drift: {directory.name}/{name}")
    return manifest


def source_modules_and_bindings() -> tuple[object, dict[str, object]]:
    bj170_manifest = verify_package(
        BJ170, EXPECTED_BJ170_GATE_B_MANIFEST, EXPECTED_BJ170_GATE_B_CONTENT
    )
    bj137_manifest = verify_package(
        BJ137, EXPECTED_BJ137_GATE_A_MANIFEST, EXPECTED_BJ137_GATE_A_CONTENT
    )
    if sha256_file(BJ137 / "issue_census.csv") != EXPECTED_ISSUE_CENSUS_SHA256:
        raise RuntimeError("#137 chronology census drift")
    settler_path = ROOT / "scripts" / "settle_bj170_selector_allocator_stack_gate_b.py"
    settler = load_module(settler_path, "bj176_frozen_bj170_settler")
    gate_a_manifest = settler.verify_package(
        settler.GATE_A, settler.EXPECTED_GATE_A_MANIFEST, settler.EXPECTED_GATE_A_CONTENT
    )
    bj167_manifest = settler.verify_package(
        settler.BJ167, settler.EXPECTED_BJ167_MANIFEST, settler.EXPECTED_BJ167_CONTENT
    )
    outcome_manifest = settler.verify_package(
        settler.OUTCOME_DIR, settler.EXPECTED_OUTCOME_MANIFEST
    )
    if outcome_manifest.get("canonical_outcome_join.csv") != settler.EXPECTED_OUTCOME_PAYLOAD:
        raise RuntimeError("#170 canonical outcome binding drift")
    return settler, {
        "bj170_gate_b": {
            "package": BJ170.name,
            "manifest_sha256": EXPECTED_BJ170_GATE_B_MANIFEST,
            "content_identity_sha256": EXPECTED_BJ170_GATE_B_CONTENT,
            "payload_count": len(bj170_manifest),
        },
        "bj170_gate_a": {
            "package": settler.GATE_A.name,
            "manifest_sha256": settler.EXPECTED_GATE_A_MANIFEST,
            "content_identity_sha256": settler.EXPECTED_GATE_A_CONTENT,
            "payload_count": len(gate_a_manifest),
        },
        "bj167_terminal": {
            "package": settler.BJ167.name,
            "manifest_sha256": settler.EXPECTED_BJ167_MANIFEST,
            "content_identity_sha256": settler.EXPECTED_BJ167_CONTENT,
            "payload_count": len(bj167_manifest),
        },
        "canonical_outcomes": {
            "package": settler.OUTCOME_DIR.name,
            "manifest_sha256": settler.EXPECTED_OUTCOME_MANIFEST,
            "canonical_outcome_join_sha256": settler.EXPECTED_OUTCOME_PAYLOAD,
            "payload_count": len(outcome_manifest),
        },
        "chronology": {
            "package": BJ137.name,
            "manifest_sha256": EXPECTED_BJ137_GATE_A_MANIFEST,
            "content_identity_sha256": EXPECTED_BJ137_GATE_A_CONTENT,
            "issue_census_sha256": EXPECTED_ISSUE_CENSUS_SHA256,
            "payload_count": len(bj137_manifest),
            "role": "transitively bound #167 source; kickoff timestamps only",
        },
        "allocator_sha256": settler.EXPECTED_ALLOCATOR_SHA256,
    }


def issue_calendar() -> dict[str, dict[str, str]]:
    rows = read_csv(BJ137 / "issue_census.csv")
    calendar = {row["issue_instance"]: row for row in rows}
    if len(calendar) != 348:
        raise RuntimeError(f"issue calendar drift: {len(calendar)}")
    if any(not row["first_kickoff_ts"] for row in calendar.values()):
        raise RuntimeError("blank kickoff timestamp in issue calendar")
    return calendar


def empty_totals() -> dict[str, float]:
    return {
        "executed_identity_count": 0.0,
        "ticket_count": 0.0,
        "stake_yuan": 0.0,
        "gross_yuan": 0.0,
        "tax_yuan": 0.0,
        "hit_ticket_count": 0.0,
        "coverage_hits": 0.0,
        "unique_ticket_count": 0.0,
        "duplicate_ticket_count": 0.0,
        "tax_line_exposure_yuan": 0.0,
        "tax_line_hit_ticket_count": 0.0,
    }


def contribution_row(
    *,
    support_view: str,
    arm_id: str,
    selector_alias: str,
    allocation_arm: str,
    participation: dict[str, str],
    calendar: dict[str, str],
    policy_status: str,
    aggregate: dict[str, float],
    planned_ticket_count: int,
    planned_stake_yuan: float,
) -> dict[str, object]:
    stake = aggregate["stake_yuan"]
    gross = aggregate["gross_yuan"]
    tax = aggregate["tax_yuan"]
    return {
        "support_view": support_view,
        "arm_id": arm_id,
        "selector_alias": selector_alias,
        "allocation_arm": allocation_arm,
        "issue": participation["issue"],
        "year": participation["year"],
        "fold": participation["fold"],
        "issue_instance": participation["issue_instance"],
        "first_kickoff_ts": calendar["first_kickoff_ts"],
        "policy_status": policy_status,
        "planned_identity_count": int(participation["selected_identity_count"]),
        "executed_identity_count": int(aggregate["executed_identity_count"]),
        "planned_ticket_count": planned_ticket_count,
        "executed_ticket_count": int(aggregate["ticket_count"]),
        "planned_stake_yuan": planned_stake_yuan,
        "stake_yuan": stake,
        "gross_pre_tax_yuan": gross,
        "tax_yuan": tax,
        "pre_tax_net_yuan": gross - stake,
        "tax_adjusted_net_yuan": gross - tax - stake,
        "hit_ticket_count": int(aggregate["hit_ticket_count"]),
        "coverage_hits": int(aggregate["coverage_hits"]),
    }


def native_contributions(settler: object) -> list[dict[str, object]]:
    frozen = settler.load_frozen_data()
    outcomes = settler.load_outcomes()
    _, by_policy = settler.settle_identities(frozen, outcomes)
    calendar = issue_calendar()
    rows: list[dict[str, object]] = []
    participation = frozen["participation"]
    for selector_alias, allocation_arm, arm_id in REQUIRED_ARMS:
        selected = [row for row in participation if row["selector_alias"] == selector_alias]
        if len(selected) != 348:
            raise RuntimeError(f"native participation drift: {selector_alias}/{len(selected)}")
        for part in selected:
            issue = part["issue_instance"]
            records = by_policy.get((selector_alias, issue, allocation_arm), [])
            status = settler.policy_status(records)
            aggregate = (
                settler.sum_records(records, True) if status == "SETTLED" else empty_totals()
            )
            identity_count = int(part["selected_identity_count"])
            m = settler.ARM_M[allocation_arm]
            rows.append(
                contribution_row(
                    support_view=SUPPORT_NATIVE,
                    arm_id=arm_id,
                    selector_alias=selector_alias,
                    allocation_arm=allocation_arm,
                    participation=part,
                    calendar=calendar[issue],
                    policy_status=status,
                    aggregate=aggregate,
                    planned_ticket_count=identity_count * m,
                    planned_stake_yuan=identity_count * m * settler.STAKE_PER_TICKET,
                )
            )
    return sort_contributions(rows)


def common_contributions() -> list[dict[str, object]]:
    raw = read_gzip(BJ170 / "three_way_issue_contributions.csv.gz")
    arm_by_key = {(selector, arm): arm_id for selector, arm, arm_id in REQUIRED_ARMS}
    rows: list[dict[str, object]] = []
    for source in raw:
        key = (source["selector_alias"], source["allocation_arm"])
        if key not in arm_by_key:
            continue
        rows.append(
            {
                "support_view": SUPPORT_COMMON,
                "arm_id": arm_by_key[key],
                "selector_alias": source["selector_alias"],
                "allocation_arm": source["allocation_arm"],
                "issue": source["issue"],
                "year": source["year"],
                "fold": source["fold"],
                "issue_instance": source["issue_instance"],
                "first_kickoff_ts": source["first_kickoff_ts"],
                "policy_status": source["common_policy_status"],
                "planned_identity_count": int(source["planned_identity_count"]),
                "executed_identity_count": int(source["executed_identity_count"]),
                "planned_ticket_count": int(source["planned_ticket_count"]),
                "executed_ticket_count": int(source["executed_ticket_count"]),
                **{field: float(source[field]) for field in MONEY_FIELDS},
                "hit_ticket_count": int(source["hit_ticket_count"]),
                "coverage_hits": int(source["coverage_hits"]),
            }
        )
    if len(rows) != 177 * len(REQUIRED_ARMS):
        raise RuntimeError(f"common contribution drift: {len(rows)}")
    return sort_contributions(rows)


def sort_contributions(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        rows,
        key=lambda row: (
            str(row["support_view"]),
            str(row["arm_id"]),
            str(row["first_kickoff_ts"]),
            str(row["issue_instance"]),
        ),
    )


def grouped_contributions(
    rows: Sequence[dict[str, object]],
) -> dict[tuple[str, str], list[dict[str, object]]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["support_view"]), str(row["arm_id"]))].append(row)
    for values in grouped.values():
        values.sort(key=lambda row: (str(row["first_kickoff_ts"]), str(row["issue_instance"])))
    return grouped


def reconcile_sources(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    grouped = grouped_contributions(rows)
    source_rows = {
        (row["selector_alias"], row["allocation_arm"]): row
        for row in read_csv(BJ170 / "source_row_reproduction.csv")
    }
    common_rows = {
        (row["selector_alias"], row["allocation_arm"]): row
        for row in read_csv(BJ170 / "nine_cell_primary.csv")
    }
    output: list[dict[str, object]] = []
    for selector_alias, allocation_arm, arm_id in REQUIRED_ARMS:
        for support_view in (SUPPORT_NATIVE, SUPPORT_COMMON):
            values = grouped[(support_view, arm_id)]
            stake = sum(float(row["stake_yuan"]) for row in values)
            gross = sum(float(row["gross_pre_tax_yuan"]) for row in values)
            tax = sum(float(row["tax_yuan"]) for row in values)
            roi = safe_ratio(gross - stake, stake)
            tax_roi = safe_ratio(gross - tax - stake, stake)
            expected = (
                source_rows[(selector_alias, allocation_arm)]
                if support_view == SUPPORT_NATIVE
                else common_rows[(selector_alias, allocation_arm)]
            )
            expected_stake = float(
                expected[
                    "actual_stake_yuan" if support_view == SUPPORT_NATIVE else "stake_yuan"
                ]
            )
            expected_gross = float(
                expected[
                    "actual_gross_yuan"
                    if support_view == SUPPORT_NATIVE
                    else "gross_pre_tax_yuan"
                ]
            )
            expected_roi = float(
                expected["actual_no_tax_roi" if support_view == SUPPORT_NATIVE else "no_tax_roi"]
            )
            expected_tax_roi = float(
                expected[
                    "actual_tax_adjusted_roi"
                    if support_view == SUPPORT_NATIVE
                    else "tax_adjusted_roi"
                ]
            )
            deltas = {
                "stake": stake - expected_stake,
                "gross": gross - expected_gross,
                "roi": float(roi) - expected_roi,
                "tax_roi": float(tax_roi) - expected_tax_roi,
            }
            if abs(deltas["stake"]) > 5e-6 or abs(deltas["gross"]) > 5e-6:
                raise RuntimeError(f"monetary source reconciliation drift: {support_view}/{arm_id}")
            if abs(deltas["roi"]) > 1e-10 or abs(deltas["tax_roi"]) > 1e-10:
                raise RuntimeError(f"ROI source reconciliation drift: {support_view}/{arm_id}")
            expected_status = (
                {
                    "SETTLED": int(expected["settled_policy_count"]),
                    "UNAVAILABLE_CANONICAL_OUTCOME": int(expected["unavailable_policy_count"]),
                    "NO_BET_FROZEN": int(expected["no_bet_policy_count"]),
                }
                if support_view == SUPPORT_NATIVE
                else {
                    "SETTLED_COMMON": int(expected["settled_common_issue_count"]),
                    "UNAVAILABLE_COMMON_OUTCOME": int(
                        expected["unavailable_common_issue_count"]
                    ),
                }
            )
            actual_status: dict[str, int] = defaultdict(int)
            for row in values:
                actual_status[str(row["policy_status"])] += 1
            if dict(actual_status) != expected_status:
                raise RuntimeError(f"policy census drift: {support_view}/{arm_id}")
            output.append(
                {
                    "support_view": support_view,
                    "arm_id": arm_id,
                    "selector_alias": selector_alias,
                    "allocation_arm": allocation_arm,
                    "issue_count": len(values),
                    "active_issue_count": sum(float(row["stake_yuan"]) > 0 for row in values),
                    "stake_yuan": fmt_money(stake),
                    "gross_pre_tax_yuan": fmt_money(gross),
                    "tax_yuan": fmt_money(tax),
                    "no_tax_roi": fmt_ratio(roi),
                    "tax_adjusted_roi": fmt_ratio(tax_roi),
                    "source_expected_stake_yuan": fmt_money(expected_stake),
                    "source_expected_gross_yuan": fmt_money(expected_gross),
                    "stake_delta_yuan": f"{deltas['stake']:.12f}",
                    "gross_delta_yuan": f"{deltas['gross']:.12f}",
                    "roi_delta": f"{deltas['roi']:.15f}",
                    "tax_roi_delta": f"{deltas['tax_roi']:.15f}",
                    "status_census_json": json.dumps(
                        dict(actual_status), sort_keys=True, separators=(",", ":")
                    ),
                    "reconciliation_status": "PASS",
                }
            )
    return output


def derive_common_bankroll(rows: Sequence[dict[str, object]]) -> dict[str, object]:
    worst_loss = 0.0
    worst_key = ""
    grouped = grouped_contributions(rows)
    for (support, arm), values in grouped.items():
        for basis, field in (
            ("PRE_TAX", "pre_tax_net_yuan"),
            ("TAX_ADJUSTED", "tax_adjusted_net_yuan"),
        ):
            cumulative = 0.0
            minimum = 0.0
            for row in values:
                cumulative += float(row[field])
                minimum = min(minimum, cumulative)
            loss = -minimum
            if loss > worst_loss:
                worst_loss = loss
                worst_key = f"{support}/{arm}/{basis}"
    base = max(10_000.0, math.ceil((2.0 * worst_loss + 1.0) / 10_000.0) * 10_000.0)
    if 0.5 * base <= worst_loss:
        raise RuntimeError("derived bankroll does not keep every 0.5x equity positive")
    return {
        "base_bankroll_yuan": base,
        "worst_historical_cumulative_loss_yuan": worst_loss,
        "worst_curve": worst_key,
        "derivation": (
            "ceil((2 * worst historical cumulative loss + 1) / 10000) * 10000; "
            "minimum 10000; guarantees positive equity at 0.5x"
        ),
        "scales": list(BANKROLL_SCALES),
    }


def time_series_rows(
    rows: Sequence[dict[str, object]], base_bankroll: float
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for (support, arm), values in sorted(grouped_contributions(rows).items()):
        cumulative_pre = cumulative_tax = 0.0
        peak_pre = peak_tax = base_bankroll
        for index, row in enumerate(values):
            pre_net = float(row["pre_tax_net_yuan"])
            tax_net = float(row["tax_adjusted_net_yuan"])
            prior_pre = base_bankroll + cumulative_pre
            prior_tax = base_bankroll + cumulative_tax
            cumulative_pre += pre_net
            cumulative_tax += tax_net
            equity_pre = base_bankroll + cumulative_pre
            equity_tax = base_bankroll + cumulative_tax
            peak_pre = max(peak_pre, equity_pre)
            peak_tax = max(peak_tax, equity_tax)
            stake = float(row["stake_yuan"])
            output.append(
                {
                    **row,
                    "issue_index": index,
                    "issue_date": str(row["first_kickoff_ts"])[:10],
                    "pre_tax_payout_yuan": fmt_money(float(row["gross_pre_tax_yuan"])),
                    "tax_adjusted_payout_yuan": fmt_money(
                        float(row["gross_pre_tax_yuan"]) - float(row["tax_yuan"])
                    ),
                    "cumulative_pre_tax_profit_yuan": fmt_money(cumulative_pre),
                    "cumulative_tax_adjusted_profit_yuan": fmt_money(cumulative_tax),
                    "research_bankroll_yuan": fmt_money(base_bankroll),
                    "pre_tax_equity_yuan": fmt_money(equity_pre),
                    "tax_adjusted_equity_yuan": fmt_money(equity_tax),
                    "pre_tax_running_peak_yuan": fmt_money(peak_pre),
                    "tax_adjusted_running_peak_yuan": fmt_money(peak_tax),
                    "pre_tax_drawdown_yuan": fmt_money(peak_pre - equity_pre),
                    "tax_adjusted_drawdown_yuan": fmt_money(peak_tax - equity_tax),
                    "pre_tax_drawdown_pct": fmt_ratio((peak_pre - equity_pre) / peak_pre),
                    "tax_adjusted_drawdown_pct": fmt_ratio(
                        (peak_tax - equity_tax) / peak_tax
                    ),
                    "pre_tax_issue_equity_return": fmt_ratio(pre_net / prior_pre),
                    "tax_adjusted_issue_equity_return": fmt_ratio(tax_net / prior_tax),
                    "pre_tax_active_stake_return": fmt_ratio(
                        safe_ratio(pre_net, stake) if stake else None
                    ),
                    "tax_adjusted_active_stake_return": fmt_ratio(
                        safe_ratio(tax_net, stake) if stake else None
                    ),
                }
            )
    return output


def elapsed_years(rows: Sequence[dict[str, object]]) -> float:
    first = datetime.fromisoformat(str(rows[0]["first_kickoff_ts"]))
    last = datetime.fromisoformat(str(rows[-1]["first_kickoff_ts"]))
    return max((last - first).total_seconds() / (365.2425 * 86400.0), 1.0 / 365.2425)


def sharpe_sortino(values: Sequence[float], annual_frequency: float) -> tuple[float | None, float | None]:
    if len(values) < 2 or annual_frequency <= 0:
        return None, None
    mean = statistics.fmean(values)
    std = statistics.stdev(values)
    sharpe = mean / std * math.sqrt(annual_frequency) if std > 0 else None
    downside = math.sqrt(statistics.fmean(min(value, 0.0) ** 2 for value in values))
    sortino = mean / downside * math.sqrt(annual_frequency) if downside > 0 else None
    return sharpe, sortino


def longest_miss_streak(rows: Sequence[dict[str, object]]) -> int:
    longest = current = 0
    for row in rows:
        if float(row["stake_yuan"]) <= 0:
            continue
        if float(row["gross_pre_tax_yuan"]) <= 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def metric_row(
    rows: Sequence[dict[str, object]],
    *,
    basis: str,
    base_bankroll: float,
    bankroll_scale: float,
    return_scope: str,
) -> dict[str, object]:
    net_field = "pre_tax_net_yuan" if basis == "PRE_TAX" else "tax_adjusted_net_yuan"
    payout = [
        float(row["gross_pre_tax_yuan"])
        - (float(row["tax_yuan"]) if basis == "TAX_ADJUSTED" else 0.0)
        for row in rows
    ]
    net = [float(row[net_field]) for row in rows]
    stake = [float(row["stake_yuan"]) for row in rows]
    years = elapsed_years(rows)
    issue_frequency = len(rows) / years
    active_indices = [index for index, value in enumerate(stake) if value > 0]
    active_frequency = len(active_indices) / years
    bankroll = base_bankroll * bankroll_scale
    cumulative = 0.0
    peak = bankroll
    max_drawdown_yuan = 0.0
    max_drawdown_pct = 0.0
    equity_returns: list[float] = []
    for value in net:
        prior = bankroll + cumulative
        equity_returns.append(value / prior)
        cumulative += value
        equity = bankroll + cumulative
        if equity <= 0:
            raise RuntimeError("research equity became non-positive")
        peak = max(peak, equity)
        drawdown = peak - equity
        max_drawdown_yuan = max(max_drawdown_yuan, drawdown)
        max_drawdown_pct = max(max_drawdown_pct, drawdown / peak)
    active_returns = [net[index] / stake[index] for index in active_indices]
    returns = equity_returns if return_scope == RETURN_CALENDAR else active_returns
    frequency = issue_frequency if return_scope == RETURN_CALENDAR else active_frequency
    sharpe, sortino = sharpe_sortino(returns, frequency)
    end_equity = bankroll + sum(net)
    cagr = (end_equity / bankroll) ** (1.0 / years) - 1.0
    calmar = cagr / max_drawdown_pct if max_drawdown_pct > 0 else None
    annualized_net = sum(net) / years
    pnl_calmar = annualized_net / max_drawdown_yuan if max_drawdown_yuan > 0 else None
    total_stake = sum(stake)
    total_payout = sum(payout)
    roi = safe_ratio(sum(net), total_stake)
    gross_hhi = (
        sum((value / total_payout) ** 2 for value in payout) if total_payout > 0 else None
    )
    largest_issue_index = max(range(len(rows)), key=lambda index: payout[index])
    ex_issue_stake = total_stake - stake[largest_issue_index]
    ex_issue_net = sum(net) - net[largest_issue_index]
    year_stake: dict[str, float] = defaultdict(float)
    year_payout: dict[str, float] = defaultdict(float)
    year_net: dict[str, float] = defaultdict(float)
    for index, row in enumerate(rows):
        year = str(row["year"])
        year_stake[year] += stake[index]
        year_payout[year] += payout[index]
        year_net[year] += net[index]
    largest_year = max(year_payout, key=year_payout.get)
    ex_year_stake = total_stake - year_stake[largest_year]
    ex_year_net = sum(net) - year_net[largest_year]
    undefined: list[str] = []
    metrics = {
        "annualized_sharpe": sharpe,
        "annualized_sortino": sortino,
        "cagr": cagr if return_scope == RETURN_CALENDAR else None,
        "calmar": calmar if return_scope == RETURN_CALENDAR else None,
        "pnl_calmar": pnl_calmar if return_scope == RETURN_CALENDAR else None,
    }
    for name, value in metrics.items():
        if value is None:
            undefined.append(name)
    return {
        "support_view": rows[0]["support_view"],
        "arm_id": rows[0]["arm_id"],
        "selector_alias": rows[0]["selector_alias"],
        "allocation_arm": rows[0]["allocation_arm"],
        "basis": basis,
        "return_scope": return_scope,
        "bankroll_scale": f"{bankroll_scale:.1f}",
        "starting_bankroll_yuan": fmt_money(bankroll),
        "issue_count": len(rows),
        "active_issue_count": len(active_indices),
        "elapsed_years": f"{years:.12f}",
        "issue_frequency_per_year": f"{issue_frequency:.12f}",
        "active_issue_frequency_per_year": f"{active_frequency:.12f}",
        "stake_yuan": fmt_money(total_stake),
        "payout_yuan": fmt_money(total_payout),
        "net_yuan": fmt_money(sum(net)),
        "roi": fmt_ratio(roi),
        "annualized_sharpe": fmt_ratio(sharpe),
        "annualized_sortino": fmt_ratio(sortino),
        "cagr": fmt_ratio(metrics["cagr"]),
        "calmar": fmt_ratio(metrics["calmar"]),
        "pnl_calmar": fmt_ratio(metrics["pnl_calmar"]),
        "max_drawdown_yuan": fmt_money(max_drawdown_yuan),
        "max_drawdown_pct": fmt_ratio(max_drawdown_pct),
        "longest_active_miss_streak": longest_miss_streak(rows),
        "payout_issue_hhi": fmt_ratio(gross_hhi),
        "largest_payout_issue": rows[largest_issue_index]["issue_instance"],
        "largest_payout_issue_share": fmt_ratio(
            safe_ratio(payout[largest_issue_index], total_payout)
        ),
        "ex_largest_issue_roi": fmt_ratio(safe_ratio(ex_issue_net, ex_issue_stake)),
        "largest_payout_year": largest_year,
        "largest_payout_year_share": fmt_ratio(
            safe_ratio(year_payout[largest_year], total_payout)
        ),
        "ex_largest_year_roi": fmt_ratio(safe_ratio(ex_year_net, ex_year_stake)),
        "ending_equity_yuan": fmt_money(end_equity),
        "downside_target": "0 per issue return",
        "undefined_metrics": "|".join(undefined),
    }


def all_metric_rows(
    rows: Sequence[dict[str, object]], bankroll: dict[str, object]
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    risk: list[dict[str, object]] = []
    sensitivity: list[dict[str, object]] = []
    base = float(bankroll["base_bankroll_yuan"])
    for values in grouped_contributions(rows).values():
        for basis in ("PRE_TAX", "TAX_ADJUSTED"):
            for scale in BANKROLL_SCALES:
                calendar = metric_row(
                    values,
                    basis=basis,
                    base_bankroll=base,
                    bankroll_scale=scale,
                    return_scope=RETURN_CALENDAR,
                )
                sensitivity.append(calendar)
                if scale == 1.0:
                    risk.append(calendar)
                    risk.append(
                        metric_row(
                            values,
                            basis=basis,
                            base_bankroll=base,
                            bankroll_scale=scale,
                            return_scope=RETURN_ACTIVE,
                        )
                    )
    return risk, sensitivity


def stability_rows(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for (support, arm), values in sorted(grouped_contributions(rows).items()):
        years = sorted({str(row["year"]) for row in values})
        for basis, net_field in (
            ("PRE_TAX", "pre_tax_net_yuan"),
            ("TAX_ADJUSTED", "tax_adjusted_net_yuan"),
        ):
            for stability_type in ("YEAR", "FOLD", "LOYO"):
                keys = years if stability_type != "FOLD" else sorted(
                    {str(row["fold"]) for row in values}
                )
                for key in keys:
                    selected = [
                        row
                        for row in values
                        if (
                            str(row["year"]) == key
                            if stability_type == "YEAR"
                            else str(row["fold"]) == key
                            if stability_type == "FOLD"
                            else str(row["year"]) != key
                        )
                    ]
                    stake = sum(float(row["stake_yuan"]) for row in selected)
                    gross = sum(float(row["gross_pre_tax_yuan"]) for row in selected)
                    tax = sum(float(row["tax_yuan"]) for row in selected)
                    net = sum(float(row[net_field]) for row in selected)
                    output.append(
                        {
                            "support_view": support,
                            "arm_id": arm,
                            "selector_alias": values[0]["selector_alias"],
                            "allocation_arm": values[0]["allocation_arm"],
                            "basis": basis,
                            "stability_type": stability_type,
                            "held_or_included_key": key,
                            "issue_count": len(selected),
                            "active_issue_count": sum(
                                float(row["stake_yuan"]) > 0 for row in selected
                            ),
                            "stake_yuan": fmt_money(stake),
                            "gross_pre_tax_yuan": fmt_money(gross),
                            "tax_yuan": fmt_money(tax),
                            "net_yuan": fmt_money(net),
                            "roi": fmt_ratio(safe_ratio(net, stake)),
                        }
                    )
    return output


def svg_line_chart(
    path: Path,
    title: str,
    y_label: str,
    series: Sequence[tuple[str, Sequence[float], str]],
) -> None:
    width, height = 1200, 650
    left, right, top, bottom = 100, 30, 70, 90
    plot_w, plot_h = width - left - right, height - top - bottom
    values = [value for _, data, _ in series for value in data]
    lo, hi = min(values + [0.0]), max(values + [0.0])
    if math.isclose(lo, hi):
        lo -= 1.0
        hi += 1.0
    pad = (hi - lo) * 0.08
    lo -= pad
    hi += pad

    def x_at(index: int, count: int) -> float:
        return left + (plot_w * index / max(count - 1, 1))

    def y_at(value: float) -> float:
        return top + plot_h * (hi - value) / (hi - lo)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width / 2}" y="36" text-anchor="middle" font-size="22" font-family="sans-serif">{title}</text>',
        f'<text x="22" y="{height / 2}" transform="rotate(-90 22 {height / 2})" text-anchor="middle" font-size="14" font-family="sans-serif">{y_label}</text>',
    ]
    for tick in range(6):
        value = lo + (hi - lo) * tick / 5
        y = y_at(value)
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width-right}" y2="{y:.2f}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{left-8}" y="{y+5:.2f}" text-anchor="end" font-size="12" font-family="monospace">{value:,.2f}</text>')
    for label, data, color in series:
        points = " ".join(f"{x_at(i, len(data)):.2f},{y_at(value):.2f}" for i, value in enumerate(data))
        parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{points}"/>')
    legend_y = height - 48
    for index, (label, _, color) in enumerate(series):
        x = left + (index % 3) * 350
        y = legend_y + (index // 3) * 22
        parts.append(f'<line x1="{x}" y1="{y}" x2="{x+28}" y2="{y}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{x+36}" y="{y+5}" font-size="12" font-family="sans-serif">{label}</text>')
    parts.append("</svg>\n")
    path.write_text("".join(parts), encoding="utf-8")


def chart_series(
    time_rows: Sequence[dict[str, object]], field: str
) -> list[tuple[str, list[float], str]]:
    colors = {
        (SUPPORT_NATIVE, "BEST_FULL_FULL"): "#1d4ed8",
        (SUPPORT_NATIVE, "MODEL_SOURCE_MODEL_CAP1_M512"): "#059669",
        (SUPPORT_NATIVE, "Q_SOURCE_Q_TOP_MASS_M192"): "#d97706",
        (SUPPORT_COMMON, "BEST_FULL_FULL"): "#60a5fa",
        (SUPPORT_COMMON, "MODEL_SOURCE_MODEL_CAP1_M512"): "#6ee7b7",
        (SUPPORT_COMMON, "Q_SOURCE_Q_TOP_MASS_M192"): "#fbbf24",
    }
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in time_rows:
        grouped[(str(row["support_view"]), str(row["arm_id"]))].append(row)
    output = []
    for key, values in sorted(grouped.items()):
        values.sort(key=lambda row: int(row["issue_index"]))
        output.append((f"{key[0]} / {key[1]}", [float(row[field]) for row in values], colors[key]))
    return output


def package_identity(stage: Path, controls: dict[str, object]) -> tuple[str, str]:
    names = sorted(
        path.name
        for path in stage.iterdir()
        if path.is_file() and path.name not in {"CONTENT_IDENTITY.json", "SHA256SUMS.json"}
    )
    content = {
        "contract_version": VERSION,
        "controls": controls,
        "payloads": {name: sha256_file(stage / name) for name in names},
    }
    (stage / "CONTENT_IDENTITY.json").write_text(
        json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sums = {
        path.name: sha256_file(path)
        for path in stage.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (stage / "SHA256SUMS.json").write_text(
        json.dumps(sums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return sha256_file(stage / "SHA256SUMS.json"), sha256_file(
        stage / "CONTENT_IDENTITY.json"
    )


def build_report(
    risk: Sequence[dict[str, object]],
    bankroll: dict[str, object],
    reconciliation: Sequence[dict[str, object]],
) -> str:
    primary = [
        row
        for row in risk
        if row["basis"] == "PRE_TAX" and row["return_scope"] == RETURN_CALENDAR
    ]
    lines = [
        "# #176 issue-level equity and risk-adjusted diagnostics",
        "",
        "## Decision",
        "",
        "This retrospective diagnostic adds path risk; it does not promote a betting policy. "
        "BEST_FULL/FULL remains the #134 controlling selection baseline. The positive MODEL "
        "and Q sleeves remain source-context diagnostics and must not be relabelled as a "
        "BEST_FULL stack.",
        "",
        "## Primary pre-tax metrics (1x common research bankroll)",
        "",
        "| Support | Arm | ROI | Sharpe | Sortino | Calmar | Max DD | Max DD % | P&L Calmar | HHI | Ex-largest year ROI |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in primary:
        lines.append(
            f"| {row['support_view']} | {row['arm_id']} | {float(row['roi']):+.2%} | "
            f"{float(row['annualized_sharpe']):+.3f} | {float(row['annualized_sortino']):+.3f} | "
            f"{float(row['calmar']):+.3f} | ¥{float(row['max_drawdown_yuan']):,.0f} | "
            f"{float(row['max_drawdown_pct']):.2%} | {float(row['pnl_calmar']):+.3f} | "
            f"{float(row['payout_issue_hhi']):.4f} | {float(row['ex_largest_year_roi']):+.2%} |"
        )
    lines.extend(
        [
            "",
            "## Conventions",
            "",
            f"- Common 1x research bankroll: ¥{float(bankroll['base_bankroll_yuan']):,.0f}; "
            "0.5x/1x/2x sensitivity uses the same frozen P&L and no reinvestment.",
            "- Calendar Sharpe uses path-dependent issue equity returns, sample standard "
            "deviation, zero risk-free rate and observed calendar issue frequency/year.",
            "- Sortino downside target is zero per issue; downside deviation includes zero-flow "
            "calendar rows.",
            "- CAGR and Calmar use elapsed kickoff time and fixed starting equity. P&L Calmar is "
            "annualized net divided by absolute maximum yuan drawdown.",
            "- Miss streak counts consecutive active issues with zero payout; no-bet and unavailable "
            "zero-flow rows neither create nor end a betting miss streak.",
            "- HHI and ex-largest issue/year use payout contributions. Native and THREE_WAY_COMMON "
            "supports are separate denominators.",
            "",
            "## Source integrity",
            "",
            f"All {len(reconciliation)} required arm/support bridges reconcile to accepted #167/#170 "
            "stake, gross, ROI and policy counts within the frozen serialization tolerances.",
            "",
            "Pre-tax is primary; tax-adjusted results are secondary. This package grants no purchase, "
            "execution, betting, production or promotion authority.",
            "",
        ]
    )
    return "\n".join(lines)


def build(output: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    settler, source_binding = source_modules_and_bindings()
    if output.exists():
        raise RuntimeError(f"refusing to replace immutable output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        contributions = native_contributions(settler) + common_contributions()
        contributions = sort_contributions(contributions)
        reconciliation = reconcile_sources(contributions)
        bankroll = derive_common_bankroll(contributions)
        time_rows = time_series_rows(contributions, float(bankroll["base_bankroll_yuan"]))
        risk, sensitivity = all_metric_rows(contributions, bankroll)
        stability = stability_rows(contributions)

        contribution_fields = tuple(contributions[0])
        serialized_contributions = [
            {
                key: fmt_money(float(value)) if key in MONEY_FIELDS else value
                for key, value in row.items()
            }
            for row in contributions
        ]
        write_gzip(
            stage / "issue_contributions.csv.gz",
            contribution_fields,
            serialized_contributions,
        )
        write_gzip(stage / "issue_time_series.csv.gz", tuple(time_rows[0]), time_rows)
        write_csv(stage / "risk_metrics.csv", tuple(risk[0]), risk)
        write_csv(
            stage / "bankroll_sensitivity.csv", tuple(sensitivity[0]), sensitivity
        )
        write_csv(stage / "stability_year_fold_loyo.csv", tuple(stability[0]), stability)
        write_csv(
            stage / "source_reconciliation.csv", tuple(reconciliation[0]), reconciliation
        )
        write_gzip(
            stage / "chart_source_equity_drawdown.csv.gz", tuple(time_rows[0]), time_rows
        )
        write_csv(stage / "chart_source_risk_metrics.csv", tuple(risk[0]), risk)
        write_csv(
            stage / "chart_source_bankroll_sensitivity.csv",
            tuple(sensitivity[0]),
            sensitivity,
        )

        svg_line_chart(
            stage / "equity_curves_pre_tax.svg",
            "#176 pre-tax cumulative P&L",
            "Cumulative profit (yuan)",
            chart_series(time_rows, "cumulative_pre_tax_profit_yuan"),
        )
        svg_line_chart(
            stage / "drawdown_curves_pre_tax.svg",
            "#176 pre-tax percentage drawdown (1x bankroll)",
            "Drawdown fraction",
            chart_series(time_rows, "pre_tax_drawdown_pct"),
        )
        svg_line_chart(
            stage / "equity_curves_tax_adjusted.svg",
            "#176 tax-adjusted cumulative P&L",
            "Cumulative profit (yuan)",
            chart_series(time_rows, "cumulative_tax_adjusted_profit_yuan"),
        )

        (stage / "source_binding.json").write_text(
            json.dumps(source_binding, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        card = {
            "issue": 176,
            "contract": CONTRACT,
            "version": VERSION,
            "stage": "RETROSPECTIVE_ISSUE_EQUITY_RISK_DIAGNOSTIC",
            "required_arms": [
                {
                    "selector_alias": selector,
                    "allocation_arm": allocation,
                    "arm_id": arm_id,
                }
                for selector, allocation, arm_id in REQUIRED_ARMS
            ],
            "support_views": {
                SUPPORT_NATIVE: {
                    "issue_count_per_arm": 348,
                    "definition": "selector-native frozen calendar; no-bet and unavailable rows are zero-flow",
                },
                SUPPORT_COMMON: {
                    "issue_count_per_arm": 177,
                    "definition": "#170 THREE_WAY_ALL frozen common calendar; 36 unavailable rows fail closed",
                },
            },
            "bankroll": bankroll,
            "metric_contract": {
                "primary": "pre-tax",
                "secondary": "tax-adjusted",
                "sharpe": "mean issue return / sample standard deviation * sqrt(observed issue frequency/year); zero risk-free",
                "sortino": "mean issue return / sqrt(mean(min(return,0)^2)) * sqrt(frequency); downside target 0",
                "calmar": "elapsed-time CAGR / maximum percentage drawdown",
                "pnl_calmar": "annualized net yuan / absolute maximum drawdown yuan",
                "miss_streak": "consecutive active issues with zero payout; zero-flow calendar rows ignored",
                "concentration": "payout issue HHI plus ex-largest payout issue/year ROI",
                "returns": [RETURN_CALENDAR, RETURN_ACTIVE],
            },
            "denominators": {
                "contribution_rows": len(contributions),
                "time_series_rows": len(time_rows),
                "risk_metric_rows": len(risk),
                "bankroll_sensitivity_rows": len(sensitivity),
                "stability_rows": len(stability),
                "reconciliation_rows": len(reconciliation),
            },
            "source_binding": source_binding,
            "decision": "RETROSPECTIVE_RISK_DIAGNOSTIC_ONLY",
            "promotion_boundary": (
                "No new selector/allocation scan and no production, purchase, betting or promotion authority; "
                "positive source-context sleeves remain non-independent diagnostics."
            ),
        }
        (stage / "settlement_card.json").write_text(
            json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        report = build_report(risk, bankroll, reconciliation)
        (stage / "REPORT.md").write_text(report, encoding="utf-8")
        (stage / "README.md").write_text(
            "# #176 immutable issue-equity/risk package\n\n"
            "See `REPORT.md`. Native and THREE_WAY_COMMON support are never pooled. "
            "All no-bet/unavailable issues are explicit zero-flow calendar rows.\n",
            encoding="utf-8",
        )
        shutil.copy2(Path(__file__).resolve(), stage / "analysis_runner.py")
        controls = {
            "source_binding": source_binding,
            "contributions_sha256": sha256_file(stage / "issue_contributions.csv.gz"),
            "time_series_sha256": sha256_file(stage / "issue_time_series.csv.gz"),
            "risk_metrics_sha256": sha256_file(stage / "risk_metrics.csv"),
            "reconciliation_sha256": sha256_file(stage / "source_reconciliation.csv"),
            "bankroll": bankroll,
            "decision": card["decision"],
        }
        manifest_sha, content_sha = package_identity(stage, controls)
        os.replace(stage, output)
        return {
            "output": str(output),
            "manifest_sha256": manifest_sha,
            "content_identity_sha256": content_sha,
            "payload_count": len(json.loads((output / "SHA256SUMS.json").read_text())),
            "bankroll": bankroll,
            "reconciliation_status": "PASS",
        }
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    print(json.dumps(build(output.resolve()), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
