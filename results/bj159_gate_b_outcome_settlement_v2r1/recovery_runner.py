#!/usr/bin/env python3
"""Reporting-only recovery for the accepted #159 Gate-B v2 ledgers.

This runner deliberately does not open the Gate-A package or the canonical
outcome join.  It authenticates the already accepted v2 package, copies its
three settlement ledgers byte-for-byte, and rebuilds only derived reporting
artifacts.  The recovery fixes signed contribution exclusions, year controls,
executed-support miss streaks, and separate pre-tax/tax drawdown fields.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path


CONTRACT = "BJ-HIST-SELECTED-WOR-CROSS-N-001"
VERSION = "bj159-gate-b-v2r1-reporting-recovery"
V2_MANIFEST = "ad724693f7fbee8a120030cb4ace852a4cf69011bf98b39b41ae427bcfbd0917"
V2_CONTENT_IDENTITY = "42f8960c9754efb3033cb6da54f38b759da3cb64d7272f195845aeabb51b1b08"
M_GRID = (32, 64, 128)
N_GRID = tuple(range(2, 11))
SEEDS = ("137001", "137002", "137003")
MONEY_Q = Decimal("0.000001")
getcontext().prec = 96

ROOT = next(
    candidate
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents)
    if (candidate / ".git").exists() and (candidate / "results").is_dir()
)
SOURCE = ROOT / "results" / "bj159_gate_b_outcome_settlement_v2"
OUTPUT = ROOT / "results" / "bj159_gate_b_outcome_settlement_v2r1"
LEDGER_NAMES = (
    "identity_settlement.csv.gz",
    "issue_settlement.csv.gz",
    "winning_ticket_tax_ledger.csv.gz",
)

SUMMARY_FIELDS = (
    "scope", "scope_value", "n", "M", "nominal_M", "effective_M", "seed", "saturation_status",
    "frozen_issue_count", "frozen_available_issue_count", "frozen_no_bet_issue_count",
    "settled_issue_count", "unavailable_outcome_issue_count", "planned_identity_count",
    "settled_identity_count", "planned_draw_count", "executed_draw_count", "planned_stake_yuan",
    "stake_yuan", "full_control_stake_yuan", "capital_utilization_vs_full", "stake_mean_yuan",
    "stake_p50_yuan", "stake_p90_yuan", "stake_p95_yuan", "stake_max_yuan", "unique_ticket_count",
    "duplicate_ticket_count", "duplicate_ticket_ratio", "winning_ticket_count", "hit_identity_count",
    "coverage_hit_rate", "ticket_hit_rate", "gross_pre_tax_yuan", "taxable_winning_ticket_count",
    "tax_line_share", "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan",
    "no_tax_roi", "tax_adjusted_roi", "gm_expected_sp_mean", "expected_sp_product_q_mean",
    "actual_winning_sp_product_mean", "gross_top_issue_share", "gross_issue_hhi", "largest_issue",
    "largest_issue_gross_yuan", "largest_issue_stake_yuan", "largest_issue_pre_tax_net_yuan",
    "largest_issue_tax_adjusted_net_yuan", "ex_largest_issue_no_tax_roi",
    "ex_largest_issue_tax_adjusted_roi", "largest_year", "largest_year_stake_yuan",
    "largest_year_pre_tax_net_yuan", "largest_year_tax_adjusted_net_yuan", "ex_largest_year_no_tax_roi",
    "ex_largest_year_tax_adjusted_roi", "max_drawdown_no_tax_yuan", "max_drawdown_tax_adjusted_yuan",
    "longest_frozen_calendar_miss_streak", "longest_executed_miss_streak",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def dec(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise RuntimeError(f"invalid {label}: {value!r}") from error
    if not result.is_finite():
        raise RuntimeError(f"non-finite {label}: {value!r}")
    return result


def money(value: Decimal) -> str:
    return format(value.quantize(MONEY_Q), "f")


def ratio(value: Decimal | None) -> str:
    return "" if value is None else f"{float(value):.12f}"


def quantile(values: list[Decimal], q: float) -> Decimal:
    if not values:
        return Decimal(0)
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * q) - 1))]


def read_gzip_rows(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def verify_source() -> tuple[dict[str, str], dict[str, object]]:
    manifest_path = SOURCE / "SHA256SUMS.json"
    if sha256(manifest_path) != V2_MANIFEST:
        raise RuntimeError("v2 source manifest hash drift")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {p.name: sha256(p) for p in SOURCE.iterdir() if p.is_file() and p.name != manifest_path.name}
    if declared != actual:
        raise RuntimeError("v2 source manifest coverage drift")
    content_path = SOURCE / "CONTENT_IDENTITY.json"
    if sha256(content_path) != V2_CONTENT_IDENTITY:
        raise RuntimeError("v2 source content identity drift")
    card = json.loads((SOURCE / "settlement_card.json").read_text(encoding="utf-8"))
    if card.get("issue") != 159 or card.get("contract") != CONTRACT:
        raise RuntimeError("v2 source settlement card drift")
    return declared, card


def contribution_groups(rows: list[dict[str, str]], key: str) -> dict[str, dict[str, Decimal]]:
    groups: dict[str, dict[str, Decimal]] = {}
    for row in rows:
        stake = dec(row["stake_yuan"], "stake")
        if stake <= 0:
            continue
        group = str(row[key])
        current = groups.setdefault(group, {"stake": Decimal(0), "gross": Decimal(0), "pre": Decimal(0), "tax": Decimal(0)})
        current["stake"] += stake
        current["gross"] += dec(row["gross_pre_tax_yuan"], "gross")
        current["pre"] += dec(row["pre_tax_net_yuan"], "pre-tax net")
        current["tax"] += dec(row["tax_adjusted_net_yuan"], "tax net")
    return groups


def largest_group(groups: dict[str, dict[str, Decimal]]) -> tuple[str, dict[str, Decimal]]:
    if not groups:
        return "", {"stake": Decimal(0), "gross": Decimal(0), "pre": Decimal(0), "tax": Decimal(0)}
    # Signed pre-tax net is the contribution criterion.  The key tie-break is
    # deterministic and keeps zero/no-bet rows out of the selection.
    return max(groups.items(), key=lambda item: (item[1]["pre"], item[0]))


def exclusion_roi(total_net: Decimal, total_stake: Decimal, contribution: dict[str, Decimal]) -> str:
    remaining = total_stake - contribution["stake"]
    return ratio((total_net - contribution["pre"]) / remaining) if remaining > 0 else ""


def exclusion_tax_roi(total_net: Decimal, total_stake: Decimal, contribution: dict[str, Decimal]) -> str:
    remaining = total_stake - contribution["stake"]
    return ratio((total_net - contribution["tax"]) / remaining) if remaining > 0 else ""


def drawdown(rows: list[dict[str, str]], field: str) -> Decimal:
    cumulative = Decimal(0)
    peak = Decimal(0)
    maximum = Decimal(0)
    for row in sorted(rows, key=lambda item: (item.get("first_kickoff_ts", ""), item["issue_instance"])):
        cumulative += dec(row[field], field)
        peak = max(peak, cumulative)
        maximum = max(maximum, peak - cumulative)
    return maximum


def miss_streak(rows: list[dict[str, str]], executed_only: bool) -> int:
    ordered = sorted(rows, key=lambda item: (item.get("first_kickoff_ts", ""), item["issue_instance"]))
    streak = longest = 0
    for row in ordered:
        if executed_only and dec(row["stake_yuan"], "stake") <= 0:
            continue
        streak = 0 if row["coverage_hit"] == "YES" else streak + 1
        longest = max(longest, streak)
    return longest


def summary_rows(issue_rows: list[dict[str, str]], scope: str, scope_value: str) -> dict[str, object]:
    if not issue_rows:
        raise RuntimeError("empty summary support")
    first = issue_rows[0]
    n, nominal_m, effective_m, seed = int(first["n"]), int(first["nominal_M"]), int(first["effective_M"]), first["seed"]
    frozen = len(issue_rows)
    available = sum(row["selection_status"] == "AVAILABLE" for row in issue_rows)
    no_bet = frozen - available
    settled = [row for row in issue_rows if int(row["settled_identity_count"]) > 0]
    executed = [row for row in issue_rows if dec(row["stake_yuan"], "stake") > 0]
    stake = sum((dec(row["stake_yuan"], "stake") for row in issue_rows), Decimal(0))
    full = sum((dec(row["full_control_stake_yuan"], "full stake") for row in issue_rows), Decimal(0))
    planned_ids = sum(int(row["planned_identity_count"]) for row in issue_rows)
    settled_ids = sum(int(row["settled_identity_count"]) for row in issue_rows)
    planned_draw = sum(int(row["planned_draw_count"]) for row in issue_rows)
    executed_draw = sum(int(row["executed_draw_count"]) for row in issue_rows)
    unique = sum(int(row["unique_ticket_count"]) for row in issue_rows)
    duplicate = sum(int(row["duplicate_ticket_count"]) for row in issue_rows)
    wins = sum(int(row["winning_ticket_count"]) for row in issue_rows)
    hit_ids = sum(int(row["hit_identity_count"]) for row in issue_rows)
    gross = sum((dec(row["gross_pre_tax_yuan"], "gross") for row in issue_rows), Decimal(0))
    taxable = sum(int(row["taxable_winning_ticket_count"]) for row in issue_rows)
    tax = sum((dec(row["tax_yuan"], "tax") for row in issue_rows), Decimal(0))
    after = sum((dec(row["after_tax_gross_yuan"], "after-tax gross") for row in issue_rows), Decimal(0))
    pre_net = sum((dec(row["pre_tax_net_yuan"], "pre-tax net") for row in issue_rows), Decimal(0))
    tax_net = sum((dec(row["tax_adjusted_net_yuan"], "tax net") for row in issue_rows), Decimal(0))
    stake_values = [dec(row["stake_yuan"], "stake") for row in executed]
    gross_groups = contribution_groups(issue_rows, "issue_instance")
    issue_groups = gross_groups
    year_groups = contribution_groups(issue_rows, "year")
    largest_gross_issue, largest_gross = max(gross_groups.items(), key=lambda item: (item[1]["gross"], item[0])) if gross_groups else ("", {"gross": Decimal(0), "stake": Decimal(0), "pre": Decimal(0), "tax": Decimal(0)})
    largest_issue, issue_contribution = largest_group(issue_groups)
    largest_year, year_contribution = largest_group(year_groups)
    total_gross = sum((item["gross"] for item in gross_groups.values()), Decimal(0))
    hhi = sum((item["gross"] / total_gross) ** 2 for item in gross_groups.values()) if total_gross else Decimal(0)
    gm_values = [dec(row["gm_expected_sp_mean"], "GM") for row in settled if row["gm_expected_sp_mean"]]
    expected_values = [dec(row["expected_sp_product_q_mean"], "expected") for row in settled if row["expected_sp_product_q_mean"]]
    actual_values = [dec(row["actual_winning_sp_product_mean"], "actual") for row in settled if row["actual_winning_sp_product_mean"]]
    return {
        "scope": scope, "scope_value": scope_value, "n": n, "M": nominal_m, "nominal_M": nominal_m, "effective_M": effective_m,
        "seed": seed, "saturation_status": first["saturation_status"], "frozen_issue_count": frozen,
        "frozen_available_issue_count": available, "frozen_no_bet_issue_count": no_bet,
        "settled_issue_count": len(settled), "unavailable_outcome_issue_count": sum(int(row["unavailable_identity_count"]) > 0 for row in issue_rows),
        "planned_identity_count": planned_ids, "settled_identity_count": settled_ids, "planned_draw_count": planned_draw,
        "executed_draw_count": executed_draw, "planned_stake_yuan": money(sum((dec(row["planned_stake_yuan"], "planned stake") for row in issue_rows), Decimal(0))),
        "stake_yuan": money(stake), "full_control_stake_yuan": money(full), "capital_utilization_vs_full": ratio(stake / full if full else None),
        "stake_mean_yuan": money(sum(stake_values, Decimal(0)) / len(stake_values)) if stake_values else money(Decimal(0)),
        "stake_p50_yuan": money(quantile(stake_values, .50)), "stake_p90_yuan": money(quantile(stake_values, .90)),
        "stake_p95_yuan": money(quantile(stake_values, .95)), "stake_max_yuan": money(max(stake_values, default=Decimal(0))),
        "unique_ticket_count": unique, "duplicate_ticket_count": duplicate,
        "duplicate_ticket_ratio": ratio(Decimal(duplicate) / (unique + duplicate) if unique + duplicate else None),
        "winning_ticket_count": wins, "hit_identity_count": hit_ids,
        "coverage_hit_rate": ratio(Decimal(hit_ids) / settled_ids if settled_ids else None),
        "ticket_hit_rate": ratio(Decimal(wins) / executed_draw if executed_draw else None),
        "gross_pre_tax_yuan": money(gross), "taxable_winning_ticket_count": taxable,
        "tax_line_share": ratio(Decimal(taxable) / wins if wins else None), "tax_yuan": money(tax),
        "after_tax_gross_yuan": money(after), "pre_tax_net_yuan": money(pre_net), "tax_adjusted_net_yuan": money(tax_net),
        "no_tax_roi": ratio(pre_net / stake if stake else None), "tax_adjusted_roi": ratio(tax_net / stake if stake else None),
        "gm_expected_sp_mean": ratio(sum(gm_values, Decimal(0)) / len(gm_values) if gm_values else None),
        "expected_sp_product_q_mean": ratio(sum(expected_values, Decimal(0)) / len(expected_values) if expected_values else None),
        "actual_winning_sp_product_mean": ratio(sum(actual_values, Decimal(0)) / len(actual_values) if actual_values else None),
        "gross_top_issue_share": ratio(largest_gross["gross"] / total_gross if total_gross else None), "gross_issue_hhi": ratio(hhi),
        "largest_issue": largest_issue, "largest_issue_gross_yuan": money(largest_gross["gross"]),
        "largest_issue_stake_yuan": money(issue_contribution["stake"]), "largest_issue_pre_tax_net_yuan": money(issue_contribution["pre"]),
        "largest_issue_tax_adjusted_net_yuan": money(issue_contribution["tax"]),
        "ex_largest_issue_no_tax_roi": exclusion_roi(pre_net, stake, issue_contribution),
        "ex_largest_issue_tax_adjusted_roi": exclusion_tax_roi(tax_net, stake, issue_contribution),
        "largest_year": largest_year, "largest_year_stake_yuan": money(year_contribution["stake"]),
        "largest_year_pre_tax_net_yuan": money(year_contribution["pre"]), "largest_year_tax_adjusted_net_yuan": money(year_contribution["tax"]),
        "ex_largest_year_no_tax_roi": exclusion_roi(pre_net, stake, year_contribution),
        "ex_largest_year_tax_adjusted_roi": exclusion_tax_roi(tax_net, stake, year_contribution),
        "max_drawdown_no_tax_yuan": money(drawdown(executed, "pre_tax_net_yuan")),
        "max_drawdown_tax_adjusted_yuan": money(drawdown(executed, "tax_adjusted_net_yuan")),
        "longest_frozen_calendar_miss_streak": miss_streak(issue_rows, False),
        "longest_executed_miss_streak": miss_streak(issue_rows, True),
    }


def matched_deltas(by_cfg: dict[tuple[int, int, str], list[dict[str, str]]]) -> list[dict[str, object]]:
    output = []
    for n in N_GRID:
        for m in M_GRID:
            for seed in SEEDS:
                left_rows = {row["issue_instance"]: row for row in by_cfg[(n, m, seed)] if dec(row["stake_yuan"], "stake") > 0}
                base_rows = {row["issue_instance"]: row for row in by_cfg[(7, m, seed)] if dec(row["stake_yuan"], "stake") > 0}
                common = sorted(set(left_rows) & set(base_rows))
                def roi(rows: dict[str, dict[str, str]], field: str) -> tuple[Decimal, Decimal]:
                    st = sum((dec(rows[k]["stake_yuan"], "stake") for k in common), Decimal(0))
                    net = sum((dec(rows[k][field], field) for k in common), Decimal(0))
                    return (net / st if st else Decimal(0), st)
                n_roi, n_stake = roi(left_rows, "pre_tax_net_yuan"); b_roi, b_stake = roi(base_rows, "pre_tax_net_yuan")
                n_tax, _ = roi(left_rows, "tax_adjusted_net_yuan"); b_tax, _ = roi(base_rows, "tax_adjusted_net_yuan")
                output.append({"n": n, "M": m, "nominal_M": m, "effective_M": min(m, 3 ** n), "n7_nominal_M": m, "n7_effective_M": min(m, 3 ** 7), "seed": seed, "common_issue_count": len(common), "n_stake_yuan": money(n_stake), "n7_stake_yuan": money(b_stake), "n_no_tax_roi": ratio(n_roi), "n7_no_tax_roi": ratio(b_roi), "no_tax_roi_delta": ratio(n_roi - b_roi), "n_tax_adjusted_roi": ratio(n_tax), "n7_tax_adjusted_roi": ratio(b_tax), "tax_adjusted_roi_delta": ratio(n_tax - b_tax), "rule": "matched issue-instance support only; N7 descriptive baseline; pre-tax primary"})
    return output


def write_svg(path: Path, title: str, ylabel: str, series: dict[str, list[tuple[int, float | None]]], yzero: bool = True) -> None:
    width, height, left, bottom = 860, 470, 78, 62
    points = [(n, value) for values in series.values() for n, value in values if value is not None]
    if not points:
        path.write_text("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"860\" height=\"470\"/>\n", encoding="utf-8"); return
    ymin, ymax = min(value for _, value in points), max(value for _, value in points)
    if yzero: ymin, ymax = min(ymin, 0.0), max(ymax, 0.0)
    span = max(ymax - ymin, 0.05); ymin -= span * .08; ymax += span * .08
    chart_w, chart_h = width - left - 40, height - bottom - 35
    colors = ("#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e")
    def x(n: int) -> float: return left + chart_w * (n - 2) / 8
    def y(value: float) -> float: return 35 + chart_h * (ymax - value) / (ymax - ymin)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="100%" height="100%" fill="white"/><text x="{left}" y="22" font-size="16">{title}</text><line x1="{left}" y1="{height-bottom}" x2="{width-40}" y2="{height-bottom}" stroke="#333"/><line x1="{left}" y1="35" x2="{left}" y2="{height-bottom}" stroke="#333"/><text x="8" y="{height/2}" font-size="12" transform="rotate(-90 8 {height/2})">{ylabel}</text>']
    for n in range(2, 11): lines.append(f'<text x="{x(n)-5:.1f}" y="{height-bottom+18}" font-size="11">{n}</text>')
    if ymin < 0 < ymax: lines.append(f'<line x1="{left}" y1="{y(0):.1f}" x2="{width-40}" y2="{y(0):.1f}" stroke="#999" stroke-dasharray="4,4"/>')
    for index, (label, values) in enumerate(series.items()):
        color = colors[index % len(colors)]
        valid = [(n, v) for n, v in values if v is not None]
        coords = " ".join(f"{x(n):.1f},{y(value):.1f}" for n, value in valid)
        lines.append(f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{coords}"/>')
        if valid:
            lx, ly = x(valid[-1][0]), y(valid[-1][1]); lines.append(f'<text x="{min(lx+7,width-130):.1f}" y="{ly:.1f}" font-size="11" fill="{color}">{label}</text>')
            for n, value in valid: lines.append(f'<circle cx="{x(n):.1f}" cy="{y(value):.1f}" r="3" fill="{color}"><title>{label}, N={n}: {value:.6f}</title></circle>')
    lines.append("</svg>\n"); path.write_text("\n".join(lines), encoding="utf-8")


def build(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    source_manifest, source_card = verify_source()
    stage_root = ROOT / ".scratch"
    stage_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj159_v2r1_", dir=stage_root))
    try:
        for name in LEDGER_NAMES:
            shutil.copyfile(SOURCE / name, stage / name)
        source_metadata = {"source_package": "results/bj159_gate_b_outcome_settlement_v2", "source_manifest_sha256": V2_MANIFEST, "source_content_identity_sha256": V2_CONTENT_IDENTITY, "copied_ledgers": {name: sha256(stage / name) for name in LEDGER_NAMES}, "source_ledger_hashes": {name: source_manifest[name] for name in LEDGER_NAMES}, "inode_independent_copy": True}
        (stage / "source_v2_binding.json").write_text(json.dumps(source_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        issue_rows = read_gzip_rows(stage / "issue_settlement.csv.gz")
        if len(issue_rows) != 28188:
            raise RuntimeError(f"issue ledger row drift: {len(issue_rows)}")
        by_cfg: dict[tuple[int, int, str], list[dict[str, str]]] = defaultdict(list)
        for row in issue_rows: by_cfg[(int(row["n"]), int(row["nominal_M"]), row["seed"])].append(row)
        if len(by_cfg) != 81 or any(len(rows) != 348 for rows in by_cfg.values()):
            raise RuntimeError("complete issue ledger surface drift")
        all_summaries: list[dict[str, object]] = []
        robustness: list[dict[str, object]] = []
        for key, rows in sorted(by_cfg.items()):
            all_summaries.append(summary_rows(rows, "ALL", "ALL"))
            years = sorted({row["year"] for row in rows}); folds = sorted({row["fold"] for row in rows})
            for year in years: robustness.append(summary_rows([row for row in rows if row["year"] == year], "YEAR", year))
            for fold in folds: robustness.append(summary_rows([row for row in rows if row["fold"] == fold], "FOLD", fold))
            for year in years: robustness.append(summary_rows([row for row in rows if row["year"] != year], "LOYO", year))
        write_csv(stage / "surface_summary.csv", SUMMARY_FIELDS, all_summaries + robustness)
        deltas = matched_deltas(by_cfg); write_csv(stage / "matched_n7_deltas.csv", tuple(deltas[0].keys()), deltas)
        shutil.copyfile(SOURCE / "issue_bootstrap.csv", stage / "issue_bootstrap.csv")
        shutil.copyfile(SOURCE / "overlap_summary.csv", stage / "overlap_summary.csv")
        curve_rows = []
        for n in N_GRID:
            rows = [row for row in all_summaries if int(row["n"]) == n and int(row["M"]) == 64]
            def mean(field: str) -> str:
                values = [dec(row[field], field) for row in rows if row[field] != ""]
                return ratio(sum(values, Decimal(0)) / len(values)) if values else ""
            curve_rows.append({"n": n, "no_tax_roi_mean": mean("no_tax_roi"), "tax_adjusted_roi_mean": mean("tax_adjusted_roi"), "ex_largest_issue_no_tax_roi_mean": mean("ex_largest_issue_no_tax_roi"), "ex_largest_year_no_tax_roi_mean": mean("ex_largest_year_no_tax_roi"), "coverage_hit_rate_mean": mean("coverage_hit_rate"), "stake_yuan_mean": mean("stake_yuan"), "longest_executed_miss_streak_mean": mean("longest_executed_miss_streak")})
        write_csv(stage / "n_curve_M64.csv", tuple(curve_rows[0].keys()), curve_rows)
        def values(field: str, m: int, n: int | None = None) -> list[tuple[int, float | None]]:
            output_values = []
            for nn in N_GRID if n is None else (n,):
                selected = [row for row in all_summaries if int(row["n"]) == nn and int(row["M"]) == m]
                vals = [dec(row[field], field) for row in selected if row[field] != ""]
                output_values.append((nn, float(sum(vals, Decimal(0)) / len(vals)) if vals else None))
            return output_values
        write_svg(stage / "roi_surface_pre_tax.svg", "#159 pre-tax ROI by N and nominal M (seed mean)", "pre-tax no-tax ROI", {f"M={m}": values("no_tax_roi", m) for m in M_GRID})
        delta_series = {}
        for m in M_GRID:
            points = []
            for n in N_GRID:
                vals = [dec(row["no_tax_roi_delta"], "delta") for row in deltas if int(row["n"]) == n and int(row["M"]) == m]
                points.append((n, float(sum(vals, Decimal(0)) / len(vals)) if vals else None))
            delta_series[f"M={m}"] = points
        write_svg(stage / "matched_n7_pre_tax_delta.svg", "#159 matched/common-support pre-tax delta vs N7", "ROI delta", delta_series)
        write_svg(stage / "stability_exclusions_M64.svg", "#159 M=64 stability after concentration exclusions", "pre-tax ROI", {"raw": values("no_tax_roi", 64), "ex-largest-issue": values("ex_largest_issue_no_tax_roi", 64), "ex-largest-year": values("ex_largest_year_no_tax_roi", 64)})
        positives_raw = [row for row in all_summaries if row["no_tax_roi"] and dec(row["no_tax_roi"], "ROI") > 0]
        positives_issue = [row for row in all_summaries if row["ex_largest_issue_no_tax_roi"] and dec(row["ex_largest_issue_no_tax_roi"], "ex issue ROI") > 0]
        positives_year = [row for row in all_summaries if row["ex_largest_year_no_tax_roi"] and dec(row["ex_largest_year_no_tax_roi"], "ex year ROI") > 0]
        decision = {"decision": "POSITIVE_REQUIRES_STRICT_INDEPENDENT_EV" if positives_raw else "NO_PROMOTION", "positive_all_rows": len(positives_raw), "positive_after_largest_issue_exclusion": len(positives_issue), "positive_after_largest_year_exclusion": len(positives_year), "promotion_authorized": False, "strict_independent_ev_required": bool(positives_raw), "rule": "Pre-tax no_tax_roi is primary; tax-adjusted ROI is secondary. Largest issue/year controls use signed pre-tax net contribution and actual executed stake. Same-window positives are descriptive only and require strict independent EV plus held-out/forward validation; no purchase, production, betting or promotion authority."}
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        m64 = [row for row in all_summaries if int(row["M"]) == 64]
        def mean_m64(field: str, n: int) -> str:
            vals = [dec(row[field], field) for row in m64 if int(row["n"]) == n and row[field] != ""]
            return ratio(sum(vals, Decimal(0)) / len(vals)) if vals else ""
        report: list[str] = ["# #159 Gate B v2r1 — reporting recovery", "", "This package is a reporting-only recovery from the authenticated #159 Gate-B v2 ledgers. It does not reopen Gate A, reread canonical outcomes, or alter any identity, issue, winning-ticket, tax, or settlement row.", "", "## Source binding", "", f"- v2 source package manifest: `{V2_MANIFEST}`", f"- v2 source content identity: `{V2_CONTENT_IDENTITY}`", "- copied ledgers are inode-independent byte-for-byte copies; see `source_v2_binding.json`.", "- the repository GitHub Wiki is disabled; the durable Research-Wiki section is committed at `docs/research-notes/Research-Wiki.md`.", "", "## Corrections", "", "1. Largest issue/year is selected by signed pre-tax net contribution among positive-stake issue rows; exclusions subtract that group's actual stake, pre-tax net, and tax-adjusted net separately.", "2. Miss streaks distinguish frozen-calendar rows from executed positive-stake support; no-bet and unavailable rows are never counted in the executed streak.", "3. Drawdown is emitted separately for pre-tax primary and tax-adjusted secondary net.", "", "## Complete ALL N×M×seed surface", "", "The following table is the complete primary/secondary and concentration-control surface. `M` remains a reporting label and actual stake is already settled in the copied ledger.", "", "| N | M | seed | settled IDs | executed tickets | stake ¥ | pre-tax ROI | tax ROI | ex-issue pre-tax ROI | ex-year pre-tax ROI | executed miss streak |", "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for row in all_summaries:
            report.append(f"| {row['n']} | {row['M']} | {row['seed']} | {row['settled_identity_count']} | {row['executed_draw_count']} | {row['stake_yuan']} | {row['no_tax_roi']} | {row['tax_adjusted_roi']} | {row['ex_largest_issue_no_tax_roi']} | {row['ex_largest_year_no_tax_roi']} | {row['longest_executed_miss_streak']} |")
        report += ["", "## M=64 seed-mean stability", "", "| N | raw pre-tax ROI | ex-largest-issue ROI | ex-largest-year ROI | raw tax ROI | executed miss streak |", "|---:|---:|---:|---:|---:|---:|"]
        for n in N_GRID:
            report.append(f"| {n} | {mean_m64('no_tax_roi', n)} | {mean_m64('ex_largest_issue_no_tax_roi', n)} | {mean_m64('ex_largest_year_no_tax_roi', n)} | {mean_m64('tax_adjusted_roi', n)} | {mean_m64('longest_executed_miss_streak', n)} |")
        raw9, issue9, year9 = (mean_m64(field, 9) for field in ("no_tax_roi", "ex_largest_issue_no_tax_roi", "ex_largest_year_no_tax_roi"))
        report += ["", "## Interpretation", "", f"The raw M=64 N=9 seed-mean pre-tax ROI is `{raw9}`; after removing each seed's largest signed issue contribution it is `{issue9}`, and after removing each seed's largest signed year contribution it is `{year9}`. Across all 81 ALL cells, raw positives={len(positives_raw)}, positives after largest-issue exclusion={len(positives_issue)}, positives after largest-year exclusion={len(positives_year)}.", "", "The positive N=9 cluster is therefore an extreme concentration signal, not evidence of a stable N sweet spot. The result is descriptive, requires strict independent EV and held-out/forward validation, and grants no purchase, production, betting, or promotion authority.", "", "## Artifacts", "", "- `surface_summary.csv`: complete ALL plus YEAR/FOLD/LOYO summaries with corrected controls.", "- `matched_n7_deltas.csv`: matched/common-support pre-tax-primary deltas against N7.", "- `roi_surface_pre_tax.svg`, `matched_n7_pre_tax_delta.svg`, `stability_exclusions_M64.svg`: readable primary and stability charts.", "- `issue_bootstrap.csv` and `overlap_summary.csv`: copied from the authenticated v2 package; no underlying ledger changed.", "- `identity_settlement.csv.gz`, `issue_settlement.csv.gz`, `winning_ticket_tax_ledger.csv.gz`: byte-for-byte source evidence copies.", ""]
        (stage / "report.md").write_text("\n".join(report), encoding="utf-8")
        source_census = {"source_v2_package_manifest_sha256": V2_MANIFEST, "source_v2_content_identity_sha256": V2_CONTENT_IDENTITY, "source_outcome_and_selection_ledgers": "copied byte-for-byte; recovery reads only issue_settlement.csv.gz", "canonical_outcome_loader": "NOT_OPENED_BY_RECOVERY", "recovery_boundary": "derived reporting only"}
        (stage / "source_census.json").write_text(json.dumps(source_census, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        card = {"issue": 159, "contract": CONTRACT, "runner_version": VERSION, "stage": "GATE_B_REPORTING_RECOVERY", "source_v2_manifest_sha256": V2_MANIFEST, "source_v2_content_identity_sha256": V2_CONTENT_IDENTITY, "gate_a_manifest_sha256": source_card["provenance"]["gate_a_manifest_sha256"], "canonical_outcome_manifest_sha256": source_card["provenance"]["canonical_outcome_manifest_sha256"], "decision": decision, "correction_boundary": "v2 identity, issue and winning-ticket ledgers are copied byte-for-byte and never recomputed; recovery does not open canonical outcomes", "exclusion_rule": "largest signed pre-tax net contribution among executed positive-stake rows; remove actual stake and both net variants", "miss_streak_rule": "frozen-calendar and executed-positive-stake streaks are emitted separately", "drawdown_rule": "pre-tax-primary and tax-adjusted-secondary net drawdowns are emitted separately", "output": {"issue_settlement_rows": len(issue_rows), "surface_summary_rows": len(all_summaries) + len(robustness), "matched_delta_rows": len(deltas), "positive_all_rows": len(positives_raw), "positive_after_largest_issue_exclusion": len(positives_issue), "positive_after_largest_year_exclusion": len(positives_year), "copied_ledger_files": list(LEDGER_NAMES)}, "scope": "historical paper-only reporting recovery; no purchase, production, betting or promotion authority"}
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(Path(__file__), stage / "recovery_runner.py")
        (stage / "README.md").write_text("# #159 Gate B v2r1\n\nReporting-only recovery from the authenticated `bj159_gate_b_outcome_settlement_v2` ledgers. The recovery does not open canonical outcomes or alter settlement rows. Replay with `python3 recovery_runner.py --output <new-dir>`; staging uses the repository `.scratch` directory, never `/tmp`.\n", encoding="utf-8")
        content = {"contract_version": "bj159-gateb-content-v2r1", "source_v2_manifest_sha256": V2_MANIFEST, "source_v2_content_identity_sha256": V2_CONTENT_IDENTITY, "copied_ledger_bytes_sha256": {name: sha256(stage / name) for name in LEDGER_NAMES}, "non_compressed_controls": {p.name: sha256(p) for p in sorted(stage.iterdir()) if p.is_file() and p.name not in LEDGER_NAMES}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sums = {p.name: sha256(p) for p in sorted(stage.iterdir())}; (stage / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True); os.replace(stage, output)
        return {"manifest_sha256": sha256(output / "SHA256SUMS.json"), "content_identity_sha256": sha256(output / "CONTENT_IDENTITY.json"), "issue_settlement_rows": len(issue_rows), "surface_summary_rows": len(all_summaries) + len(robustness), "positive_all_rows": len(positives_raw), "positive_after_largest_issue_exclusion": len(positives_issue), "positive_after_largest_year_exclusion": len(positives_year)}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True); raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
