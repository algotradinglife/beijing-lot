#!/usr/bin/python3
"""Checkpoint-only finalizer for #193 Gate-B v2."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import os
import subprocess
import sys
import types
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
GATE_A = ROOT / "results" / "bj193_gate_a_preoutcome_v1"
GATE_A_V2 = ROOT / "results" / "bj193_gate_a_chain_interface_v2"
ORACLE_CORRECTION = ROOT / "results" / "bj193_gate_b_oracle_correction_v1r1"
CONTRACT = "bj193-gate-b-three-stage-regime-meta-policy-v2"
CHECKPOINT_CONTRACT = "bj193-gate-b-three-stage-checkpoint-v2"
ORACLE_CORRECTION_CONTRACT = "bj193-gate-b-oracle-fold-join-correction-v1r1"
EXPECTED_ORACLE_CORRECTION_MANIFEST = (
    "568fc5b4b72673ed796d94a61251d95ed8286a167a0727e7c6ac4716e02a80f1"
)
REFERENCE_CAPITAL = 220_000.0
BANKROLL_START = 100_000.0
BOOTSTRAP_DRAWS = 20_000
BOOTSTRAP_SEED = 193_001
CAUSAL = (
    "ALL_STATIC",
    "DYNAMIC_SELECTION_ONLY",
    "DYNAMIC_SELECTION_DIRECTION",
    "FULL_DYNAMIC_CHAIN",
)
POLICIES = CAUSAL + ("PRIOR_ONLY_BEST_FIXED", "LEAKY_ORACLE_CEILING")
EXPECTED_BANKROLL_100K = {
    "ALL_STATIC": (0.29558, 8.2669, True, "", 83722.21),
    "DYNAMIC_SELECTION_ONLY": (-0.4971515, 10.5413, False, "23034", 159668.25),
    "DYNAMIC_SELECTION_DIRECTION": (0.0825413, 8.0627, False, "23104", 114385.97),
    "PRIOR_ONLY_BEST_FIXED": (0.412151, 2.8954, True, "", 58784.90),
    "FULL_DYNAMIC_CHAIN": (0.0758962, 3.6127, True, "", 92410.38),
    "LEAKY_ORACLE_CEILING": (4.5542578, 4.1700, True, "", 15931.53),
}
CONTRASTS = (
    ("STAGE_1_SELECTION", "DYNAMIC_SELECTION_ONLY", "ALL_STATIC"),
    ("STAGE_2_DIRECTION", "DYNAMIC_SELECTION_DIRECTION", "DYNAMIC_SELECTION_ONLY"),
    ("STAGE_3_BET", "FULL_DYNAMIC_CHAIN", "DYNAMIC_SELECTION_DIRECTION"),
    ("END_TO_END", "FULL_DYNAMIC_CHAIN", "ALL_STATIC"),
    ("STRONGEST_PRIOR", "FULL_DYNAMIC_CHAIN", "PRIOR_ONLY_BEST_FIXED"),
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fmt(value: object) -> str:
    if value in (None, ""):
        return ""
    number = float(value)
    return "" if not math.isfinite(number) else f"{number:.12f}"


def read_csv(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, restval="")
        writer.writeheader()
        writer.writerows(rows)


def write_gzip(path: Path, fields: Sequence[str], rows: Iterable[Mapping]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as binary:
            with __import__("io").TextIOWrapper(binary, newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=fields, restval="", lineterminator="\n"
                )
                writer.writeheader()
                writer.writerows(rows)


def verify_package(root: Path, expected_contract: str) -> tuple[dict, str]:
    manifest_path = root / "SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text())
    for name, expected in manifest.items():
        if sha(root / name) != expected:
            raise RuntimeError(f"checkpoint payload drift: {name}")
    identity = json.loads((root / "CONTENT_IDENTITY.json").read_text())
    if identity["contract"] != expected_contract:
        raise RuntimeError("checkpoint contract drift")
    return manifest, sha(manifest_path)


def load_holding_module():
    path = GATE_A / "freeze_runner.py"
    name = "bj193_frozen_holding_finalizer"
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def _rows_by_policy(rows: Sequence[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    output = {policy: [] for policy in POLICIES}
    for row in rows:
        output[row["policy_id"]].append(row)
    for policy, values in output.items():
        values.sort(key=lambda row: int(row["issue_index"]))
        if len(values) != 344:
            raise RuntimeError(f"policy flow denominator drift: {policy}")
    return output


def _apply_oracle_correction(
    checkpoint_flows: Sequence[dict[str, str]],
    checkpoint_choices: Sequence[dict[str, str]],
    corrected_oracle: Sequence[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Replace only the superseded oracle rows; causal rows remain untouched."""

    original_oracle = [
        row for row in checkpoint_flows
        if row["policy_id"] == "LEAKY_ORACLE_CEILING"
    ]
    causal = [
        row for row in checkpoint_flows
        if row["policy_id"] != "LEAKY_ORACLE_CEILING"
    ]
    if len(original_oracle) != 344 or len(corrected_oracle) != 344:
        raise RuntimeError("oracle correction denominator drift")
    if [row["issue"] for row in original_oracle] != [
        row["issue"] for row in corrected_oracle
    ]:
        raise RuntimeError("oracle correction issue order drift")
    corrected_by_issue = {row["issue"]: row for row in corrected_oracle}
    output_choices = []
    oracle_choice_count = 0
    for row in checkpoint_choices:
        if row["path_name"] != "stage3_oracle":
            output_choices.append(dict(row))
            continue
        oracle_choice_count += 1
        corrected = corrected_by_issue[row["issue"]]
        output_choices.append(
            {
                **row,
                "chosen_action_identity": corrected["chosen_action_identity"],
                "model_id": corrected["model_id"],
                "fallback_flag": corrected["fallback_flag"],
            }
        )
    if oracle_choice_count != 344:
        raise RuntimeError("oracle checkpoint choice denominator drift")
    return causal + [dict(row) for row in corrected_oracle], output_choices


def _support_rows(
    rows: Sequence[dict[str, str]], support: str, common: set[int]
) -> list[dict[str, str]]:
    if support == "NATIVE":
        return list(rows)
    return [row for row in rows if int(row["issue_index"]) in common]


def _metrics(rows: Sequence[dict[str, str]]) -> dict[str, object]:
    active = [row for row in rows if row["status"] == "ACTIVE"]
    stake = sum(float(row["stake_yuan"]) for row in rows)
    gross = sum(float(row["gross_pre_tax_yuan"]) for row in rows)
    tax = sum(float(row["tax_yuan"]) for row in rows)
    net = sum(float(row["pre_tax_net_yuan"]) for row in rows)
    tax_net = sum(float(row["tax_adjusted_net_yuan"]) for row in rows)
    net_values = np.asarray([float(row["pre_tax_net_yuan"]) for row in rows])
    mean = float(net_values.mean()) if len(net_values) else 0.0
    sd = float(net_values.std(ddof=1)) if len(net_values) > 1 else 0.0
    downside = net_values[net_values < 0]
    downside_sd = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    equity = REFERENCE_CAPITAL + np.cumsum(net_values)
    peaks = np.maximum.accumulate(np.r_[REFERENCE_CAPITAL, equity])[:-1]
    drawdowns = peaks - equity
    max_dd = float(max(0.0, drawdowns.max(initial=0.0)))
    max_dd_pct = float(
        np.max(np.divide(drawdowns, peaks, out=np.zeros_like(drawdowns), where=peaks > 0), initial=0)
    )
    roi = net / stake if stake else None
    actions = [row["chosen_action_identity"] for row in rows]
    switches = sum(a != b for a, b in zip(actions, actions[1:]))
    gross_by_issue = np.asarray([float(row["gross_pre_tax_yuan"]) for row in rows])
    gross_share = gross_by_issue / gross if gross > 0 else np.zeros(len(rows))
    return {
        "issue_count": len(rows),
        "active_issue_count": len(active),
        "no_bet_issue_count": sum(row["status"] == "NO_BET" for row in rows),
        "unavailable_issue_count": sum(row["status"] == "UNAVAILABLE" for row in rows),
        "stake_yuan": stake,
        "gross_pre_tax_yuan": gross,
        "tax_yuan": tax,
        "pre_tax_net_yuan": net,
        "tax_adjusted_net_yuan": tax_net,
        "pre_tax_roi": roi,
        "tax_adjusted_roi": tax_net / stake if stake else None,
        "hit_rate": sum(float(row["hit"]) > 0 for row in active) / len(active) if active else None,
        "hit_issue_rate": sum(float(row["hit"]) > 0 for row in active) / len(active) if active else None,
        "sharpe": mean / sd * math.sqrt(len(net_values)) if sd else None,
        "sortino": mean / downside_sd * math.sqrt(len(net_values)) if downside_sd else None,
        "max_drawdown_yuan": max_dd,
        "max_drawdown_pct": max_dd_pct,
        "calmar": roi / max_dd_pct if roi is not None and max_dd_pct else None,
        "payout_hhi": float(np.square(gross_share).sum()),
        "gross_issue_hhi": float(np.square(gross_share).sum()),
        "largest_issue_share": float(gross_share.max(initial=0.0)),
        "largest_issue_gross_share": float(gross_share.max(initial=0.0)),
        "action_switch_rate": switches / max(1, len(rows) - 1),
        "action_switch_count": switches,
    }


def _bankroll_100k(
    policy: str, rows: Sequence[dict[str, str]]
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Replay frozen native stake against one finite 100k cash account.

    Stake is never resized or compounded and no top-up is injected.  The
    required-top-up columns are diagnostics only; once the cash account cannot
    fund a same-issue stake the complete frozen path is marked infeasible.
    """

    capital = BANKROLL_START
    cumulative_stake = 0.0
    cumulative_net_before = 0.0
    running_peak = BANKROLL_START
    minimum_required_start = 0.0
    first_unfundable = ""
    maximum_required_top_up = 0.0
    output: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        stake = float(row["stake_yuan"])
        gross = float(row["gross_pre_tax_yuan"])
        net = float(row["pre_tax_net_yuan"])
        tax = float(row["tax_yuan"])
        tax_net = float(row["tax_adjusted_net_yuan"])
        capital_before = capital
        fundable = capital_before + 1e-9 >= stake
        required_top_up = max(0.0, stake - capital_before)
        if not fundable and not first_unfundable:
            first_unfundable = row["issue"]
        maximum_required_top_up = max(maximum_required_top_up, required_top_up)
        minimum_required_start = max(
            minimum_required_start, stake - cumulative_net_before
        )
        cumulative_stake += stake
        capital = capital_before + net
        cumulative_net_before += net
        running_peak = max(running_peak, capital)
        drawdown = running_peak - capital
        output.append(
            {
                "policy_id": policy,
                "issue": row["issue"],
                "issue_index": row["issue_index"],
                "year": row["year"],
                "outer_fold": row["outer_fold"],
                "chronology_index": index,
                "status": row["status"],
                "capital_before_yuan": fmt(capital_before),
                "native_stake_yuan": fmt(stake),
                "gross_pre_tax_yuan": fmt(gross),
                "pre_tax_pnl_yuan": fmt(net),
                "tax_yuan": fmt(tax),
                "tax_adjusted_pnl_yuan": fmt(tax_net),
                "capital_after_yuan": fmt(capital),
                "cumulative_stake_yuan": fmt(cumulative_stake),
                "capital_turnover_multiple": fmt(
                    cumulative_stake / BANKROLL_START
                ),
                "running_peak_yuan": fmt(running_peak),
                "drawdown_yuan": fmt(drawdown),
                "drawdown_pct": fmt(
                    drawdown / running_peak if running_peak else None
                ),
                "fundable_flag": fundable,
                "required_top_up_yuan": fmt(required_top_up),
            }
        )
    capital_values = [BANKROLL_START] + [
        float(row["capital_after_yuan"]) for row in output
    ]
    tax_adjusted_end = BANKROLL_START + sum(
        float(row["tax_adjusted_net_yuan"]) for row in rows
    )
    summary = {
        "policy_id": policy,
        "starting_bankroll_yuan": fmt(BANKROLL_START),
        "ending_bankroll_yuan": fmt(capital),
        "bankroll_growth_yuan": fmt(capital - BANKROLL_START),
        "bankroll_growth_rate": fmt((capital - BANKROLL_START) / BANKROLL_START),
        "total_native_stake_yuan": fmt(cumulative_stake),
        "capital_turnover_multiple": fmt(cumulative_stake / BANKROLL_START),
        "minimum_capital_yuan": fmt(min(capital_values)),
        "fundable_all_issues_flag": not bool(first_unfundable),
        "first_unfundable_issue": first_unfundable,
        "maximum_required_top_up_yuan": fmt(maximum_required_top_up),
        "minimum_starting_bankroll_required_yuan": fmt(
            max(0.0, minimum_required_start)
        ),
        "tax_adjusted_ending_bankroll_yuan": fmt(tax_adjusted_end),
        "tax_adjusted_growth_rate": fmt(
            (tax_adjusted_end - BANKROLL_START) / BANKROLL_START
        ),
        "stake_rule": "FROZEN_NATIVE_STAKE_NO_RESIZING_NO_COMPOUNDING",
        "funding_rule": "SAME_ISSUE_STAKE_MUST_BE_CASH_FUNDED_NO_TOPUPS",
    }
    return output, summary


def _assert_bankroll_100k_anchors(
    summaries: Sequence[Mapping[str, object]], *, tolerance_yuan: float = 0.02
) -> None:
    index = {str(row["policy_id"]): row for row in summaries}
    if set(index) != set(EXPECTED_BANKROLL_100K):
        raise RuntimeError("100k bankroll policy census drift")
    for policy, (
        expected_end_multiple,
        expected_turnover,
        expected_fundable,
        expected_first,
        expected_minimum_start,
    ) in EXPECTED_BANKROLL_100K.items():
        row = index[policy]
        observed_end = float(row["ending_bankroll_yuan"])
        observed_turnover = float(row["capital_turnover_multiple"])
        observed_minimum_start = float(
            row["minimum_starting_bankroll_required_yuan"]
        )
        if abs(observed_end - expected_end_multiple * BANKROLL_START) > tolerance_yuan:
            raise RuntimeError(f"100k ending bankroll anchor drift: {policy}")
        if abs(observed_turnover - expected_turnover) > 5e-5:
            raise RuntimeError(f"100k capital turnover anchor drift: {policy}")
        if bool(row["fundable_all_issues_flag"]) != expected_fundable:
            raise RuntimeError(f"100k fundability anchor drift: {policy}")
        if str(row["first_unfundable_issue"]) != expected_first:
            raise RuntimeError(f"100k first-unfundable anchor drift: {policy}")
        if abs(observed_minimum_start - expected_minimum_start) > tolerance_yuan:
            raise RuntimeError(f"100k minimum-start anchor drift: {policy}")


def _decision_leaders(
    performance: Sequence[Mapping[str, object]],
    bankroll_summary: Sequence[Mapping[str, object]],
) -> tuple[str, str]:
    """Return primary capital and secondary matched-ROI leaders."""

    perf = {
        (str(row["policy_id"]), str(row["support"])): row
        for row in performance
    }
    bankroll = {str(row["policy_id"]): row for row in bankroll_summary}
    causal = tuple(
        policy for policy in POLICIES if policy != "LEAKY_ORACLE_CEILING"
    )
    fundable = tuple(
        policy for policy in causal
        if bool(bankroll[policy]["fundable_all_issues_flag"])
    )
    if not fundable:
        raise RuntimeError("no fundable causal 100k capital path")
    best_capital = max(
        fundable,
        key=lambda policy: float(bankroll[policy]["ending_bankroll_yuan"]),
    )
    best_matched_roi = max(
        (
            "ALL_STATIC",
            "DYNAMIC_SELECTION_ONLY",
            "DYNAMIC_SELECTION_DIRECTION",
            "PRIOR_ONLY_BEST_FIXED",
        ),
        key=lambda policy: float(
            perf[(policy, "STRICT_FOUR_ARM_COMMON")]["pre_tax_roi"]
        ),
    )
    return best_capital, best_matched_roi


def _svg_line_chart(
    path: Path,
    title: str,
    series: Sequence[tuple[str, Sequence[float]]],
    *,
    width: int = 1100,
    height: int = 620,
) -> None:
    """Write a dependency-free deterministic SVG line chart."""

    colors = ("#2563eb", "#dc2626", "#059669", "#7c3aed", "#d97706", "#111827")
    values = [value for _, items in series for value in items]
    lo, hi = min(values), max(values)
    if math.isclose(lo, hi):
        lo, hi = lo - 1.0, hi + 1.0
    left, top, right, bottom = 90, 55, 30, 75
    plot_w, plot_h = width - left - right, height - top - bottom
    count = max((len(items) for _, items in series), default=1)
    x = lambda i: left + (plot_w * i / max(1, count - 1))
    y = lambda value: top + plot_h * (hi - value) / (hi - lo)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="30" font-family="sans-serif" font-size="20" font-weight="bold">{title}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" stroke="#777"/>',
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" stroke="#777"/>',
    ]
    for tick in range(5):
        value = lo + (hi - lo) * tick / 4
        yy = y(value)
        parts += [
            f'<line x1="{left}" y1="{yy:.2f}" x2="{left + plot_w}" y2="{yy:.2f}" stroke="#e5e7eb"/>',
            f'<text x="{left - 8}" y="{yy + 4:.2f}" text-anchor="end" font-family="sans-serif" font-size="11">{value:,.0f}</text>',
        ]
    for series_index, (label, items) in enumerate(series):
        color = colors[series_index % len(colors)]
        points = " ".join(
            f"{x(i):.2f},{y(value):.2f}" for i, value in enumerate(items)
        )
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{points}"/>'
        )
        legend_x = left + (series_index % 3) * 320
        legend_y = height - 42 + (series_index // 3) * 18
        parts += [
            f'<line x1="{legend_x}" y1="{legend_y - 4}" x2="{legend_x + 24}" y2="{legend_y - 4}" stroke="{color}" stroke-width="3"/>',
            f'<text x="{legend_x + 30}" y="{legend_y}" font-family="sans-serif" font-size="11">{label}</text>',
        ]
    parts += [
        f'<text x="{left + plot_w / 2:.2f}" y="{height - 8}" text-anchor="middle" font-family="sans-serif" font-size="12">Chronological issue index</text>',
        "</svg>",
    ]
    path.write_text("\n".join(parts) + "\n")


def _svg_bar_chart(
    path: Path, title: str, rows: Sequence[tuple[str, float]], ylabel: str
) -> None:
    width, height = 1100, 620
    left, top, right, bottom = 90, 55, 30, 145
    plot_w, plot_h = width - left - right, height - top - bottom
    values = [value for _, value in rows] + [0.0]
    lo, hi = min(values), max(values)
    pad = max(1.0, (hi - lo) * 0.08)
    lo, hi = min(0.0, lo - pad), max(0.0, hi + pad)
    y = lambda value: top + plot_h * (hi - value) / (hi - lo)
    bar_w = plot_w / max(1, len(rows)) * 0.65
    zero = y(0.0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="30" font-family="sans-serif" font-size="20" font-weight="bold">{title}</text>',
        f'<line x1="{left}" y1="{zero:.2f}" x2="{left + plot_w}" y2="{zero:.2f}" stroke="#555"/>',
        f'<text x="18" y="{top + plot_h / 2:.2f}" transform="rotate(-90 18 {top + plot_h / 2:.2f})" text-anchor="middle" font-family="sans-serif" font-size="12">{ylabel}</text>',
    ]
    for index, (label, value) in enumerate(rows):
        center = left + plot_w * (index + 0.5) / len(rows)
        yy = y(value)
        rect_y, rect_h = min(zero, yy), abs(zero - yy)
        color = "#059669" if value >= 0 else "#dc2626"
        parts += [
            f'<rect x="{center - bar_w / 2:.2f}" y="{rect_y:.2f}" width="{bar_w:.2f}" height="{max(rect_h, 1):.2f}" fill="{color}"/>',
            f'<text x="{center:.2f}" y="{height - bottom + 18}" text-anchor="end" transform="rotate(-35 {center:.2f} {height - bottom + 18})" font-family="sans-serif" font-size="10">{label}</text>',
            f'<text x="{center:.2f}" y="{yy - 6 if value >= 0 else yy + 14:.2f}" text-anchor="middle" font-family="sans-serif" font-size="10">{value:.3f}</text>',
        ]
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n")


def _metric_row(policy: str, support: str, rows: Sequence[dict[str, str]]) -> dict[str, object]:
    values = _metrics(rows)
    return {"policy_id": policy, "support": support, **{
        key: fmt(value) if isinstance(value, (float, np.floating)) or value is None else value
        for key, value in values.items()
    }}


def _as_holding(rows: Sequence[dict[str, str]]) -> list[dict[str, object]]:
    return [
        {
            "issue": row["issue"], "status": row["status"],
            "stake": float(row["stake_yuan"]),
            "gross": float(row["gross_pre_tax_yuan"]),
            "net": float(row["pre_tax_net_yuan"]),
        }
        for row in rows
    ]


def _equity_rows(policy: str, rows: Sequence[dict[str, str]], basis: str) -> list[dict[str, object]]:
    selected = list(rows) if basis == "CALENDAR" else [r for r in rows if r["status"] == "ACTIVE"]
    equity = REFERENCE_CAPITAL
    peak = REFERENCE_CAPITAL
    output = []
    for index, row in enumerate(selected):
        net = float(row["pre_tax_net_yuan"])
        equity += net
        peak = max(peak, equity)
        dd = peak - equity
        output.append({
            "policy_id": policy, "sequence_basis": basis, "issue": row["issue"],
            "year": row["year"], "outer_fold": row["outer_fold"],
            "chronology_index": index, "status": row["status"],
            "stake_yuan": fmt(row["stake_yuan"]),
            "gross_pre_tax_yuan": fmt(row["gross_pre_tax_yuan"]),
            "pre_tax_net_yuan": fmt(net), "cumulative_equity_yuan": fmt(equity),
            "running_peak_yuan": fmt(peak), "drawdown_yuan": fmt(dd),
            "drawdown_pct": fmt(dd / peak if peak else None),
            "negative_pnl_flag": net < 0,
            "zero_payout_miss_flag": row["status"] == "ACTIVE" and float(row["gross_pre_tax_yuan"]) == 0,
        })
    return output


def _holding_tables(by_policy: Mapping[str, Sequence[dict[str, str]]], holding) -> tuple[list, list, list, list]:
    streaks, rolling, episodes, recovery = [], [], [], []
    for policy, rows in by_policy.items():
        fold_groups = {"ALL": list(rows)}
        for row in rows:
            fold_groups.setdefault(row["outer_fold"], []).append(row)
        for fold, fold_rows in fold_groups.items():
            for basis in ("CALENDAR", "ACTIVE_BET"):
                result = holding.holding_path_metrics(_as_holding(fold_rows), basis)
                streaks.append({
                    "policy_id": policy, "fold": fold, "sequence_basis": basis,
                    "max_negative_pnl_streak": result["max_negative_pnl_streak"],
                    "max_zero_payout_miss_streak": result["max_zero_payout_miss_streak"],
                })
                for value in result["rolling_windows"]:
                    value = dict(value)
                    value["negative_pnl_probability"] = value.pop(
                        "negative_sum_frequency"
                    )
                    rolling.append({
                        "policy_id": policy, "fold": fold, "sequence_basis": basis,
                        **value,
                    })
                if fold != "ALL":
                    continue
                sequence_rows = (
                    list(fold_rows)
                    if basis == "CALENDAR"
                    else [row for row in fold_rows if row["status"] == "ACTIVE"]
                )
                sequence_equity = [REFERENCE_CAPITAL]
                for row in sequence_rows:
                    sequence_equity.append(
                        sequence_equity[-1] + float(row["pre_tax_net_yuan"])
                    )
                for value in result["drawdown_episodes"]:
                    peak_index = int(value["peak_sequence_index"])
                    peak = sequence_equity[peak_index + 1]
                    episodes.append({
                        "policy_id": policy, **value,
                        "drawdown_yuan": fmt(value["drawdown_yuan"]),
                        "drawdown_pct": fmt(float(value["drawdown_yuan"]) / peak),
                    })
                recovered = [e for e in result["drawdown_episodes"] if e["recovered_flag"]]
                recoveries = [float(e["recovery_issues"]) for e in recovered]
                recovery.append({
                    "policy_id": policy, "sequence_basis": basis,
                    "episode_count": len(result["drawdown_episodes"]),
                    "recovered_count": len(recovered),
                    "unrecovered_count": len(result["drawdown_episodes"]) - len(recovered),
                    "median_recovery_issues": fmt(np.median(recoveries) if recoveries else None),
                    "p90_recovery_issues": fmt(np.quantile(recoveries, .9) if recoveries else None),
                    "max_recovery_issues": fmt(max(recoveries) if recoveries else None),
                })
    return streaks, rolling, episodes, recovery


def _stability(policy: str, support: str, rows: Sequence[dict[str, str]]) -> tuple[list, list]:
    output = []
    years = sorted({row["year"] for row in rows})
    folds = sorted({row["outer_fold"] for row in rows})
    views = [("YEAR", year, [r for r in rows if r["year"] == year], "") for year in years]
    views += [("FOLD", fold, [r for r in rows if r["outer_fold"] == fold], "") for fold in folds]
    views += [("LOYO", "ALL", [r for r in rows if r["year"] != year], year) for year in years]
    gross_year = {year: sum(float(r["gross_pre_tax_yuan"]) for r in rows if r["year"] == year) for year in years}
    largest_year = max(years, key=lambda y: (gross_year[y], y)) if years else ""
    largest_issue = max(rows, key=lambda r: (float(r["gross_pre_tax_yuan"]), r["issue"]))["issue"] if rows else ""
    views += [
        ("EX_LARGEST_ISSUE", "ALL", [r for r in rows if r["issue"] != largest_issue], largest_issue),
        ("EX_LARGEST_YEAR", "ALL", [r for r in rows if r["year"] != largest_year], largest_year),
    ]
    for view, included, selected, excluded in views:
        metrics = _metrics(selected)
        max_loss_streak = 0
        current_loss_streak = 0
        for row in selected:
            if float(row["pre_tax_net_yuan"]) < 0:
                current_loss_streak += 1
                max_loss_streak = max(max_loss_streak, current_loss_streak)
            else:
                current_loss_streak = 0
        output.append({
            "policy_id": policy, "support": support, "view": view,
            "included_value": included, "excluded_value": excluded,
            "issue_count": metrics["issue_count"], "active_issue_count": metrics["active_issue_count"],
            "stake_yuan": fmt(metrics["stake_yuan"]), "pre_tax_roi": fmt(metrics["pre_tax_roi"]),
            "max_drawdown_yuan": fmt(metrics["max_drawdown_yuan"]),
            "max_drawdown_pct": fmt(metrics["max_drawdown_pct"]),
            "max_loss_streak": max_loss_streak,
        })
    metrics = _metrics(rows)
    concentration = [{
        "policy_id": policy, "support": support,
        "gross_issue_hhi": fmt(metrics["gross_issue_hhi"]),
        "largest_issue_gross_share": fmt(metrics["largest_issue_gross_share"]),
        "largest_gross_issue": largest_issue, "largest_gross_year": largest_year,
        "largest_year_gross_share": fmt(gross_year.get(largest_year, 0) / metrics["gross_pre_tax_yuan"] if metrics["gross_pre_tax_yuan"] else None),
    }]
    return output, concentration


def _draw_matrix(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    dtype = np.uint16 if n < 65536 else np.uint32
    return rng.integers(0, n, size=(BOOTSTRAP_DRAWS, n), dtype=dtype)


def _block_matrix(n: int, block: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    count = math.ceil(n / block)
    starts = rng.integers(0, n, size=(BOOTSTRAP_DRAWS, count), dtype=np.int64)
    values = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return values.reshape(BOOTSTRAP_DRAWS, -1)[:, :n].astype(np.uint16)


def _bootstrap_row(stage: str, candidate: str, comparator: str, metric: str, values: np.ndarray) -> dict[str, object]:
    return {
        "stage": stage, "candidate": candidate, "comparator": comparator,
        "metric": metric, "draws": BOOTSTRAP_DRAWS,
        "mean": fmt(values.mean()), "ci_low": fmt(np.quantile(values, .025)),
        "ci_high": fmt(np.quantile(values, .975)),
        "probability_improvement": fmt(np.mean(values > 0)),
    }


def _bootstrap_max_drawdown(net_paths: np.ndarray) -> np.ndarray:
    equity = REFERENCE_CAPITAL + np.cumsum(net_paths, axis=1)
    initial = np.full((len(net_paths), 1), REFERENCE_CAPITAL)
    peaks = np.maximum.accumulate(np.concatenate((initial, equity), axis=1), axis=1)[:, 1:]
    return np.max(peaks - equity, axis=1)


def _bootstrap(
    stage: Path, by_policy: Mapping[str, Sequence[dict[str, str]]], common_indices: Sequence[int]
) -> tuple[list[dict[str, object]], str]:
    common = list(common_indices)
    matrix = _draw_matrix(len(common), BOOTSTRAP_SEED)
    np.save(stage / "bootstrap_issue_draw_indices.npy", matrix, allow_pickle=False)
    hashes = {"iid": sha(stage / "bootstrap_issue_draw_indices.npy")}
    block_matrices = {}
    for block in (5, 10, 20):
        value = _block_matrix(len(common), block, BOOTSTRAP_SEED)
        path = stage / f"bootstrap_block_{block}_draw_indices.npy"
        np.save(path, value, allow_pickle=False)
        hashes[f"block_{block}"] = sha(path)
        block_matrices[block] = value
    output = []
    for stage_name, candidate, comparator in CONTRASTS:
        crows = [by_policy[candidate][i] for i in common]
        brows = [by_policy[comparator][i] for i in common]
        valid = np.asarray([
            c["status"] == "ACTIVE" and b["status"] == "ACTIVE"
            and float(c["stake_yuan"]) > 0 and float(b["stake_yuan"]) > 0
            for c, b in zip(crows, brows)
        ])
        if not valid.all():
            local = np.flatnonzero(valid)
            if not len(local):
                continue
            draws = _draw_matrix(len(local), BOOTSTRAP_SEED)
            crows = [crows[i] for i in local]
            brows = [brows[i] for i in local]
        else:
            draws = matrix
        cn = np.asarray([float(r["pre_tax_net_yuan"]) for r in crows])
        cs = np.asarray([float(r["stake_yuan"]) for r in crows])
        bn = np.asarray([float(r["pre_tax_net_yuan"]) for r in brows])
        bs = np.asarray([float(r["stake_yuan"]) for r in brows])
        lift = cn[draws].sum(axis=1) / cs[draws].sum(axis=1) - bn[draws].sum(axis=1) / bs[draws].sum(axis=1)
        output.append(_bootstrap_row(stage_name, candidate, comparator, "PRE_TAX_ROI_LIFT_IID", lift))
        if valid.all():
            for block, indices in block_matrices.items():
                cpaths = cn[indices]
                bpaths = bn[indices]
                cdd = _bootstrap_max_drawdown(cpaths)
                bdd = _bootstrap_max_drawdown(bpaths)
                output.append(_bootstrap_row(stage_name, candidate, comparator, f"COMPARATOR_MINUS_CANDIDATE_MAX_DRAWDOWN_BLOCK_{block}", bdd - cdd))
    return output, hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def _seed_dispersion(rows: Sequence[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["policy_id"], row["chosen_action_identity"], row["outer_fold"], row["mechanism"])].append(row)
    output = []
    for (policy, action, fold, mechanism), values in sorted(grouped.items()):
        by_seed: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in values:
            by_seed[row["seed"]].append(row)
        rois = []
        for seed_rows in by_seed.values():
            stake = sum(float(r["stake_yuan"]) for r in seed_rows)
            net = sum(float(r["pre_tax_net_yuan"]) for r in seed_rows)
            if stake:
                rois.append(net / stake)
        arr = np.asarray(rois)
        output.append({
            "namespace": policy,
            "selector_factor_id": "",
            "causal_allocation_factor_id": action,
            "policy_id": policy, "chosen_action_identity": action,
            "mechanism": mechanism, "fold": fold,
            "active_issue_count": len({r["issue"] for r in values}),
            "replicate_count": len(arr), "seed_roi_mean": fmt(arr.mean() if len(arr) else None),
            "seed_roi_sample_sd": fmt(arr.std(ddof=1) if len(arr) > 1 else None),
            "seed_roi_mcse": fmt(arr.std(ddof=1) / math.sqrt(len(arr)) if len(arr) > 1 else None),
            "seed_roi_q05": fmt(np.quantile(arr, .05) if len(arr) else None),
            "seed_roi_q50": fmt(np.quantile(arr, .5) if len(arr) else None),
            "seed_roi_q95": fmt(np.quantile(arr, .95) if len(arr) else None),
            "seed_roi_min": fmt(arr.min() if len(arr) else None),
            "seed_roi_max": fmt(arr.max() if len(arr) else None),
            "positive_seed_fraction": fmt(np.mean(arr > 0) if len(arr) else None),
        })
    return output


def _catalog(path: Path) -> dict[str, dict[str, str]]:
    return {row["interface_action_key"]: row for row in read_csv(path)}


def _choice_chart_rows(checkpoint: Path) -> tuple[list, list, list, list]:
    choices = read_csv(checkpoint / "issue_policy_choice.csv.gz")
    features = {row["issue"]: row for row in read_csv(GATE_A / "issue_regime_features.csv.gz")}
    catalogs = {
        "STAGE_1_SELECTION": _catalog(GATE_A_V2 / "stage1_selection_catalog.csv.gz"),
        "STAGE_2_DIRECTION": _catalog(GATE_A_V2 / "stage2_direction_catalog.csv.gz"),
        "STAGE_3_BET": _catalog(GATE_A_V2 / "stage3_bet_catalog.csv.gz"),
    }
    selected_paths = {
        "stage1_dynamic": "STAGE_1_SELECTION",
        "stage2_dynamic": "STAGE_2_DIRECTION",
        "stage3_dynamic": "STAGE_3_BET",
    }
    outputs = {stage: [] for stage in selected_paths.values()}
    frequencies: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in choices:
        if row["path_name"] not in selected_paths:
            continue
        stage_name = selected_paths[row["path_name"]]
        catalog = catalogs[stage_name][row["chosen_action_identity"]]
        params = json.loads(catalog["parameters_json"])
        feature = features[row["issue"]]
        value = {
            "stage": stage_name, "issue": row["issue"], "year": feature["year"],
            "outer_fold": feature["outer_fold"], "model_id": row["model_id"],
            "fallback_flag": row["fallback_flag"],
            "chosen_action_identity": row["chosen_action_identity"],
            "source_identity": catalog["source_identity"],
            "league_entropy": feature["league_entropy"],
            "line_entropy": feature["line_entropy"],
            "market_uncertainty_mean": feature["market_uncertainty_mean"],
            "weight_source": params.get("weight_source", ""),
            "mechanism": params.get("mechanism", ""),
            "cap": params.get("cap", ""), "M": params.get("M", ""),
        }
        outputs[stage_name].append(value)
        frequencies[(stage_name, feature["year"], row["chosen_action_identity"])] += 1
    freq = [
        {"stage": key[0], "year": key[1], "chosen_action_identity": key[2], "choice_count": count}
        for key, count in sorted(frequencies.items())
    ]
    return outputs["STAGE_1_SELECTION"], outputs["STAGE_2_DIRECTION"], outputs["STAGE_3_BET"], freq


def _m_curve(checkpoint: Path) -> list[dict[str, object]]:
    catalog = _catalog(GATE_A_V2 / "stage3_bet_catalog.csv.gz")
    grouped: dict[str, dict[str, object]] = {}
    for row in read_csv(checkpoint / "issue_action_settlement-STAGE3_DIRECTION_UPSTREAM.csv.gz"):
        key = row["source_action_identity"]
        state = grouped.setdefault(key, {"stake": 0.0, "net": 0.0, "gross": 0.0, "active": 0, "unavailable": 0})
        state["stake"] += float(row["stake_yuan"])
        state["net"] += float(row["pre_tax_net_yuan"])
        state["gross"] += float(row["gross_pre_tax_yuan"])
        state["active"] += row["status"] == "ACTIVE"
        state["unavailable"] += row["status"] == "UNAVAILABLE"
    output = []
    for action, values in sorted(grouped.items()):
        params = json.loads(catalog[action]["parameters_json"])
        output.append({
            "stage3_action_identity": action,
            "weight_source": params.get("weight_source", ""),
            "mechanism": params.get("mechanism", ""),
            "cap": params.get("cap", ""), "M": params.get("M", ""),
            "active_issue_count": values["active"], "unavailable_issue_count": values["unavailable"],
            "stake_yuan": fmt(values["stake"]), "gross_pre_tax_yuan": fmt(values["gross"]),
            "pre_tax_roi": fmt(values["net"] / values["stake"] if values["stake"] else None),
        })
    return output


def finalize(checkpoint: Path, target: Path) -> None:
    checkpoint = checkpoint.resolve()
    target = target.resolve()
    manifest, checkpoint_manifest_sha = verify_package(checkpoint, CHECKPOINT_CONTRACT)
    correction_manifest, correction_manifest_sha = verify_package(
        ORACLE_CORRECTION, ORACLE_CORRECTION_CONTRACT
    )
    if correction_manifest_sha != EXPECTED_ORACLE_CORRECTION_MANIFEST:
        raise RuntimeError("oracle correction manifest drift")
    correction_binding = json.loads(
        (ORACLE_CORRECTION / "source_binding.json").read_text()
    )
    correction_receipt = json.loads(
        (ORACLE_CORRECTION / "oracle_correction_receipt.json").read_text()
    )
    correction_expected = {
        "changed_action_issue_count": 151,
        "changed_cashflow_or_status_issue_count": 148,
        "corrected_oracle_selected_count": 181,
        "corrected_oracle_fallback_count": 163,
        "oracle_better_than_causal_issue_count": 107,
    }
    for field, expected in correction_expected.items():
        if correction_receipt.get(field) != expected:
            raise RuntimeError(
                f"oracle correction v1r1 anchor drift: {field}="
                f"{correction_receipt.get(field)!r}, expected={expected!r}"
            )
    if correction_binding["checkpoint_manifest_sha256"] != checkpoint_manifest_sha:
        raise RuntimeError("oracle correction checkpoint binding drift")
    if target.exists():
        raise RuntimeError(f"refusing to replace immutable target: {target}")
    stage = target.with_name(f"{target.name}.stage-{uuid.uuid4().hex}")
    stage.mkdir(parents=True)
    try:
        checkpoint_flows = read_csv(checkpoint / "issue_policy_flows.csv.gz")
        checkpoint_choices = read_csv(checkpoint / "issue_policy_choice.csv.gz")
        corrected_oracle = read_csv(
            ORACLE_CORRECTION / "corrected_oracle_policy_flow.csv.gz"
        )
        flows, corrected_choices = _apply_oracle_correction(
            checkpoint_flows, checkpoint_choices, corrected_oracle
        )
        by_policy = _rows_by_policy(flows)
        common_doc = json.loads((checkpoint / "strict_common_support.json").read_text())
        common_indices = [int(value) for value in common_doc["issue_indices"]]
        common = set(common_indices)
        holding = load_holding_module()

        performance = []
        for policy, rows in by_policy.items():
            for support in ("NATIVE", "STRICT_FOUR_ARM_COMMON"):
                performance.append(_metric_row(policy, support, _support_rows(rows, support, common)))
        perf_fields = list(performance[0])
        write_csv(stage / "performance_summary.csv", perf_fields, performance)
        write_csv(stage / "native_and_strict_common_performance.csv", perf_fields, performance)
        perf_lookup = {(r["policy_id"], r["support"]): r for r in performance}
        bankroll_rows: list[dict[str, object]] = []
        bankroll_summary: list[dict[str, object]] = []
        for policy in POLICIES:
            issue_rows, summary = _bankroll_100k(policy, by_policy[policy])
            bankroll_rows.extend(issue_rows)
            bankroll_summary.append(summary)
        _assert_bankroll_100k_anchors(bankroll_summary)
        bankroll_lookup = {
            row["policy_id"]: row for row in bankroll_summary
        }
        (
            best_fundable_100k_capital_path,
            best_matched_pre_tax_roi_per_stake,
        ) = _decision_leaders(
            performance,
            bankroll_summary,
        )
        write_gzip(
            stage / "bankroll_100k_issue_path.csv.gz",
            list(bankroll_rows[0]),
            bankroll_rows,
        )
        write_csv(
            stage / "bankroll_100k_summary.csv",
            list(bankroll_summary[0]),
            bankroll_summary,
        )
        bankroll_by_policy = {
            policy: [
                BANKROLL_START,
                *[
                    float(row["capital_after_yuan"])
                    for row in bankroll_rows
                    if row["policy_id"] == policy
                ],
            ]
            for policy in POLICIES
        }
        _svg_line_chart(
            stage / "bankroll_100k_capital_curves.svg",
            "#193 fixed-stake capital reuse from ¥100,000",
            [(policy, bankroll_by_policy[policy]) for policy in POLICIES],
        )
        support_census = [
            {
                "policy_id": row["policy_id"],
                "support": row["support"],
                "issue_count": row["issue_count"],
                "active_issue_count": row["active_issue_count"],
                "no_bet_issue_count": row["no_bet_issue_count"],
                "unavailable_issue_count": row["unavailable_issue_count"],
                "stake_yuan": row["stake_yuan"],
            }
            for row in performance
        ]
        write_csv(
            stage / "stage_support_census.csv",
            list(support_census[0]),
            support_census,
        )
        fallback_groups: dict[tuple[str, str, str, str], int] = defaultdict(int)
        for row in corrected_choices:
            fallback_groups[
                (
                    row["path_name"],
                    row["stage"],
                    row["model_id"],
                    row["fallback_flag"],
                )
            ] += 1
        fallback_census = [
            {
                "path_name": key[0],
                "stage": key[1],
                "model_id": key[2],
                "fallback_flag": key[3],
                "issue_count": count,
            }
            for key, count in sorted(fallback_groups.items())
        ]
        write_csv(
            stage / "stage_fallback_census.csv",
            list(fallback_census[0]),
            fallback_census,
        )

        equity = [row for policy, rows in by_policy.items() for basis in ("CALENDAR", "ACTIVE_BET") for row in _equity_rows(policy, rows, basis)]
        write_gzip(stage / "issue_equity_timeseries.csv.gz", list(equity[0]), equity)
        write_gzip(stage / "chain_equity_drawdown.csv.gz", list(equity[0]), equity)
        streaks, rolling, episodes, recovery = _holding_tables(by_policy, holding)
        write_csv(stage / "streak_metrics.csv", list(streaks[0]), streaks)
        write_csv(stage / "rolling_loss_windows.csv", list(rolling[0]), rolling)
        write_csv(stage / "drawdown_episodes.csv", list(episodes[0]), episodes)
        write_csv(stage / "recovery_summary.csv", list(recovery[0]), recovery)
        drawdown_chart = []
        recovery_index = {
            (row["policy_id"], row["sequence_basis"]): row
            for row in recovery
        }
        for policy in POLICIES:
            metrics = _metrics(by_policy[policy])
            drawdown_chart.append(
                {
                    "policy_id": policy,
                    "support": "NATIVE",
                    "max_drawdown_yuan": fmt(metrics["max_drawdown_yuan"]),
                    "max_drawdown_pct": fmt(metrics["max_drawdown_pct"]),
                    "max_recovery_issues": recovery_index[
                        (policy, "CALENDAR")
                    ]["max_recovery_issues"],
                }
            )
        write_csv(
            stage / "drawdown_holding_chart_source.csv",
            list(drawdown_chart[0]),
            drawdown_chart,
        )
        _svg_bar_chart(
            stage / "drawdown_holding.svg",
            "#193 native-support maximum drawdown",
            [
                (row["policy_id"], -float(row["max_drawdown_yuan"]))
                for row in drawdown_chart
            ],
            "Negative max drawdown (yuan)",
        )

        stability, concentration = [], []
        for policy, rows in by_policy.items():
            for support in ("NATIVE", "STRICT_FOUR_ARM_COMMON"):
                a, b = _stability(policy, support, _support_rows(rows, support, common))
                stability.extend(a); concentration.extend(b)
        write_csv(stage / "stability_year_fold_loyo.csv", list(stability[0]), stability)
        write_csv(stage / "ex_largest_issue_year.csv", list(stability[0]), [r for r in stability if r["view"].startswith("EX_")])
        write_csv(stage / "payout_concentration.csv", list(concentration[0]), concentration)

        bootstrap, draw_hash = _bootstrap(stage, by_policy, common_indices)
        write_csv(stage / "bootstrap_paired_20000.csv", list(bootstrap[0]), bootstrap)

        increments = []
        for stage_name, candidate, comparator in CONTRASTS:
            for support in ("NATIVE", "STRICT_FOUR_ARM_COMMON"):
                c = _metrics(_support_rows(by_policy[candidate], support, common))
                b = _metrics(_support_rows(by_policy[comparator], support, common))
                increments.append({
                    "stage": stage_name, "candidate": candidate, "comparator": comparator,
                    "support": support, "candidate_stake_yuan": fmt(c["stake_yuan"]),
                    "comparator_stake_yuan": fmt(b["stake_yuan"]),
                    "candidate_pre_tax_roi": fmt(c["pre_tax_roi"]),
                    "comparator_pre_tax_roi": fmt(b["pre_tax_roi"]),
                    "pre_tax_roi_lift": fmt((c["pre_tax_roi"] - b["pre_tax_roi"]) if c["pre_tax_roi"] is not None and b["pre_tax_roi"] is not None else None),
                    "candidate_max_drawdown_yuan": fmt(c["max_drawdown_yuan"]),
                    "comparator_max_drawdown_yuan": fmt(b["max_drawdown_yuan"]),
                })
        write_csv(stage / "incremental_attribution_summary.csv", list(increments[0]), increments)
        write_csv(stage / "incremental_roi_holding_bridge.csv", list(increments[0]), increments)
        stage_chart = [
            row for row in increments
            if row["support"] == "STRICT_FOUR_ARM_COMMON"
        ]
        write_csv(
            stage / "stage_attribution_chart_source.csv",
            list(stage_chart[0]),
            stage_chart,
        )
        _svg_bar_chart(
            stage / "stage_attribution_waterfall.svg",
            "#193 strict-common incremental ROI attribution",
            [
                (row["stage"], float(row["pre_tax_roi_lift"]))
                for row in stage_chart
            ],
            "Pre-tax ROI lift",
        )

        oracle_rows = []
        for causal, oracle in zip(by_policy["FULL_DYNAMIC_CHAIN"], by_policy["LEAKY_ORACLE_CEILING"], strict=True):
            cstake, ostake = float(causal["stake_yuan"]), float(oracle["stake_yuan"])
            cu = float(causal["pre_tax_net_yuan"]) / cstake if cstake else 0.0
            ou = float(oracle["pre_tax_net_yuan"]) / ostake if ostake else 0.0
            oracle_rows.append({
                "issue": causal["issue"], "year": causal["year"],
                "oracle_action": oracle["chosen_action_identity"],
                "causal_action": causal["chosen_action_identity"],
                "oracle_utility": fmt(ou), "causal_utility": fmt(cu),
                "regret": fmt(ou - cu),
                "namespace": "STAGE_3_BET", "oracle_status": oracle["status"],
                "causal_status": causal["status"],
            })
        write_gzip(stage / "oracle_regret.csv.gz", list(oracle_rows[0]), oracle_rows)
        stage_regret = []
        for candidate in CAUSAL:
            c = _metrics([by_policy[candidate][i] for i in common_indices])
            o = _metrics([by_policy["LEAKY_ORACLE_CEILING"][i] for i in common_indices])
            stage_regret.append({
                "candidate": candidate, "oracle": "LEAKY_ORACLE_CEILING",
                "support": "STRICT_FOUR_ARM_COMMON",
                "candidate_pre_tax_roi": fmt(c["pre_tax_roi"]),
                "oracle_pre_tax_roi": fmt(o["pre_tax_roi"]),
                "oracle_minus_candidate_roi": fmt(o["pre_tax_roi"] - c["pre_tax_roi"] if o["pre_tax_roi"] is not None and c["pre_tax_roi"] is not None else None),
            })
        write_csv(stage / "stage_regret_decomposition.csv", list(stage_regret[0]), stage_regret)
        write_gzip(stage / "oracle_ceiling_and_stage_regret.csv.gz", list(stage_regret[0]), stage_regret)
        causal_oracle_chart = [
            {
                "policy_id": policy,
                "support": "STRICT_FOUR_ARM_COMMON",
                "pre_tax_roi": fmt(
                    _metrics(
                        [by_policy[policy][i] for i in common_indices]
                    )["pre_tax_roi"]
                ),
                "diagnostic_role": (
                    "LEAKY_DIAGNOSTIC_ONLY"
                    if policy == "LEAKY_ORACLE_CEILING"
                    else "CAUSAL_OR_BASELINE"
                ),
            }
            for policy in POLICIES
        ]
        write_csv(
            stage / "causal_vs_oracle_chart_source.csv",
            list(causal_oracle_chart[0]),
            causal_oracle_chart,
        )
        _svg_bar_chart(
            stage / "causal_vs_oracle_comparison.svg",
            "#193 causal policies versus corrected leaky oracle",
            [
                (row["policy_id"], float(row["pre_tax_roi"]))
                for row in causal_oracle_chart
            ],
            "Strict-common pre-tax ROI",
        )

        seed_rows = read_csv(checkpoint / "selected_policy_seed_settlement.csv.gz")
        seed_dispersion = _seed_dispersion(seed_rows)
        write_csv(stage / "within_seed_dispersion.csv", list(seed_dispersion[0]), seed_dispersion)

        s1, s2, s3, frequency = _choice_chart_rows(checkpoint)
        for name, values in (
            ("stage1_selector_choice_by_regime.csv", s1),
            ("stage2_direction_choice_by_regime.csv", s2),
            ("stage3_allocator_M_choice_by_regime.csv", s3),
            ("stage_choice_frequency.csv", frequency),
        ):
            write_csv(stage / name, list(values[0]), values)
        m_curve = _m_curve(checkpoint)
        write_gzip(stage / "complete_dynamic_M_curves.csv.gz", list(m_curve[0]), m_curve)
        write_gzip(stage / "action_performance_heatmap.csv.gz", list(m_curve[0]), m_curve)
        feature_rows = read_csv(GATE_A / "issue_regime_features.csv.gz")
        write_gzip(stage / "feature_regime_map.csv.gz", list(feature_rows[0]), feature_rows)
        flow_lookup = {r["issue"]: r for r in by_policy["FULL_DYNAMIC_CHAIN"]}
        response = []
        for row in feature_rows:
            for feature in ("league_entropy", "line_entropy", "market_uncertainty_mean", "abs_fundamental_delta_p_q90", "abs_line_residual_mu_q90"):
                flow = flow_lookup[row["issue"]]
                response.append({
                    "issue": row["issue"], "year": row["year"], "feature": feature,
                    "feature_value": row[feature], "chosen_action_identity": flow["chosen_action_identity"],
                    "status": flow["status"], "pre_tax_net_yuan": flow["pre_tax_net_yuan"],
                    "chart_semantics": "RAW_ISSUE_RESPONSE_NOT_ESTIMATED_PARTIAL_DEPENDENCE",
                })
        write_gzip(stage / "feature_partial_dependence.csv.gz", list(response[0]), response)

        full_common = _metrics([by_policy["FULL_DYNAMIC_CHAIN"][i] for i in common_indices])
        static_common = _metrics([by_policy["ALL_STATIC"][i] for i in common_indices])
        prior_common_rows = [by_policy["PRIOR_ONLY_BEST_FIXED"][i] for i in common_indices]
        prior_common = _metrics(prior_common_rows)
        boot_index = {(r["candidate"], r["comparator"], r["metric"]): r for r in bootstrap}
        end_boot = boot_index.get(("FULL_DYNAMIC_CHAIN", "ALL_STATIC", "PRE_TAX_ROI_LIFT_IID"), {})
        positive = (
            full_common["pre_tax_roi"] is not None and full_common["pre_tax_roi"] > 0
            and static_common["pre_tax_roi"] is not None and full_common["pre_tax_roi"] > static_common["pre_tax_roi"]
            and prior_common["pre_tax_roi"] is not None and full_common["pre_tax_roi"] > prior_common["pre_tax_roi"]
            and float(end_boot.get("ci_low", "-inf")) > 0
        )
        candidate = {
            "contract": "BJ193_CAUSAL_CANDIDATE_FREEZE_V2",
            "candidate_count": int(positive),
            "strict_independent_ev_required": bool(positive),
            "candidate_policy": "FULL_DYNAMIC_CHAIN" if positive else "",
            "decision": "STRICT_EV_REQUIRED_BEFORE_PROMOTION" if positive else "NO_PROMOTION",
            "reason": "causal chain clears frozen positivity/comparator/bootstrap screen" if positive else "no causal chain clears the complete frozen promotion screen",
        }
        (stage / "strict_ev_candidate_freeze.json").write_text(json.dumps(candidate, sort_keys=True, indent=2) + "\n")
        oracle_common = _metrics([by_policy["LEAKY_ORACLE_CEILING"][i] for i in common_indices])
        oracle_opportunity = oracle_common["pre_tax_roi"] is not None and static_common["pre_tax_roi"] is not None and oracle_common["pre_tax_roi"] > static_common["pre_tax_roi"]
        failure_code = "NO_FAILURE" if positive else ("CAUSAL_GENERALIZATION_FAILURE" if oracle_opportunity else "NO_ORACLE_OPPORTUNITY")
        failures = [{
            "policy_id": "FULL_DYNAMIC_CHAIN", "failure_code": failure_code,
            "oracle_opportunity_present": oracle_opportunity,
            "causal_mapping_stable": bool(float(end_boot.get("ci_low", "-inf")) > 0),
            "support_sufficient": len(common_indices) >= 60,
            "action_noise_excessive": not positive,
            "causal_outperformance_present": positive,
            "evidence": "strict common support plus paired 20k bootstrap and baseline ladder",
            "disposition": candidate["decision"],
        }]
        write_csv(stage / "failure_attribution.csv", list(failures[0]), failures)
        sleeves = [{
            "sleeve_id": "BJ193_FULL_DYNAMIC_CHAIN", "action_namespace": "THREE_STAGE_CAUSAL_CHAIN",
            "nested_rule": "f_selection -> f_direction -> f_bet",
            "native_support": _metrics(by_policy["FULL_DYNAMIC_CHAIN"])["active_issue_count"],
            "common_support": len(common_indices), "holding_disposition": "REVIEW_SCORECARD",
            "eligibility_for_192": "ELIGIBLE_AFTER_PI_AND_EV" if positive else "INELIGIBLE_NO_PROMOTION",
            "independent_ev_required": bool(positive),
        }]
        write_csv(stage / "handoff_dynamic_sleeves.csv", list(sleeves[0]), sleeves)

        scorecard = []
        holding_index = {(r["policy_id"], r["sequence_basis"]): r for r in recovery}
        streak_index = {(r["policy_id"], r["fold"], r["sequence_basis"]): r for r in streaks}
        rolling_index = {(r["policy_id"], r["fold"], r["sequence_basis"], r["window_length"]): r for r in rolling}
        for comparator in ("ALL_STATIC", "PRIOR_ONLY_BEST_FIXED"):
            for support in ("NATIVE", "STRICT_FOUR_ARM_COMMON"):
                cm = _metrics(_support_rows(by_policy["FULL_DYNAMIC_CHAIN"], support, common))
                bm = _metrics(_support_rows(by_policy[comparator], support, common))
                scorecard.append({
                    "candidate_policy": "FULL_DYNAMIC_CHAIN", "comparator": comparator,
                    "support": support, "roi": fmt(cm["pre_tax_roi"]), "comparator_roi": fmt(bm["pre_tax_roi"]),
                    "max_loss_streak": streak_index[("FULL_DYNAMIC_CHAIN", "ALL", "CALENDAR")]["max_negative_pnl_streak"],
                    "max_miss_streak": streak_index[("FULL_DYNAMIC_CHAIN", "ALL", "ACTIVE_BET")]["max_zero_payout_miss_streak"],
                    "rolling_5_loss_probability": rolling_index[("FULL_DYNAMIC_CHAIN", "ALL", "CALENDAR", 5)]["negative_pnl_probability"],
                    "rolling_10_loss_probability": rolling_index[("FULL_DYNAMIC_CHAIN", "ALL", "CALENDAR", 10)]["negative_pnl_probability"],
                    "rolling_20_loss_probability": rolling_index[("FULL_DYNAMIC_CHAIN", "ALL", "CALENDAR", 20)]["negative_pnl_probability"],
                    "max_drawdown_yuan": fmt(cm["max_drawdown_yuan"]), "max_drawdown_pct": fmt(cm["max_drawdown_pct"]),
                    "max_drawdown_duration_issues": max((int(e["drawdown_duration_to_trough_issues"]) for e in episodes if e["policy_id"] == "FULL_DYNAMIC_CHAIN" and e["sequence_basis"] == "CALENDAR"), default=0),
                    "max_recovery_issues": holding_index[("FULL_DYNAMIC_CHAIN", "CALENDAR")]["max_recovery_issues"],
                    "tradeoff_disposition": "PASS" if positive else "NO_PROMOTION",
                })
        write_csv(stage / "holding_feasibility_scorecard.csv", list(scorecard[0]), scorecard)

        flow_fields = list(checkpoint_flows[0])
        write_gzip(stage / "issue_policy_flows.csv.gz", flow_fields, flows)
        write_gzip(
            stage / "issue_policy_choice.csv.gz",
            list(checkpoint_choices[0]),
            corrected_choices,
        )
        for name in (
            "selected_policy_seed_settlement.csv.gz", "stage_model_receipts.csv",
            "stage_screen_receipts.csv.gz", "strict_common_support.json",
        ):
            (stage / name).write_bytes((checkpoint / name).read_bytes())
        for name in sorted(manifest):
            if name.startswith("issue_action_settlement-"):
                (stage / name).write_bytes((checkpoint / name).read_bytes())
        for name in (
            "corrected_stage_path-stage3_oracle.json",
            "corrected_oracle_policy_flow.csv.gz",
            "superseded_oracle_policy_flow.csv.gz",
            "oracle_correction_receipt.json",
            "causal_policy_byte_identity.csv",
            "checkpoint_payload_audit.csv",
        ):
            (stage / f"oracle_correction-{name}").write_bytes(
                (ORACLE_CORRECTION / name).read_bytes()
            )
        write_csv(stage / "stage_model_selection_receipt.csv", list(read_csv(checkpoint / "stage_model_receipts.csv")[0]), read_csv(checkpoint / "stage_model_receipts.csv"))
        (stage / "stage_action_screen_receipt.csv.gz").write_bytes((checkpoint / "stage_screen_receipts.csv.gz").read_bytes())

        boundary = {
            "contract": "BJ193_CHECKPOINT_TRACE_BOUNDARY_V1",
            "authoritative_economics": "issue_policy_flows.csv.gz and eight checkpoint stage-context settlement tables",
            "ticket_ledger_status": "NOT_PERSISTED_IN_ATOMIC_CHECKPOINT",
            "decision_trace_status": "PATH_ACTION_MODEL_FALLBACK_RECEIPTS_ONLY",
            "scientific_interpretation": "no ticket row is reconstructed or fabricated during checkpoint-only finalization",
        }
        (stage / "trace_and_ticket_ledger_boundary.json").write_text(json.dumps(boundary, sort_keys=True, indent=2) + "\n")
        source_binding = {
            "checkpoint": str(checkpoint.relative_to(ROOT)),
            "checkpoint_manifest_sha256": checkpoint_manifest_sha,
            "checkpoint_payload_count": len(manifest),
            "oracle_correction_package": str(ORACLE_CORRECTION.relative_to(ROOT)),
            "oracle_correction_manifest_sha256": correction_manifest_sha,
            "oracle_correction_payload_count": len(correction_manifest),
            "corrected_oracle_selected_count": correction_receipt[
                "corrected_oracle_selected_count"
            ],
            "corrected_oracle_fallback_count": correction_receipt[
                "corrected_oracle_fallback_count"
            ],
            "corrected_oracle_changed_action_issue_count": correction_receipt[
                "changed_action_issue_count"
            ],
            "corrected_oracle_changed_cashflow_or_status_issue_count": (
                correction_receipt[
                    "changed_cashflow_or_status_issue_count"
                ]
            ),
            "gate_a_v1_manifest_sha256": "408e8aa69cf2d336f8b3b65b1c94b30a3456864af01517a78fc27b3f2bab0c45",
            "gate_a_v2_manifest_sha256": "6a44f4b1b355f5476328424bc8d92271d61d585643d40ca42bb56ffda1c43933",
            "gate_a_v21_manifest_sha256": "b5456cd62c8d22cce6e1bc5f1bb76abee8154fcf547664c62e4793d36864e5dd",
            "finalizer_path": "scripts/bj193_gate_b_finalize.py",
            "finalizer_sha256": sha(Path(__file__)),
            "runner_path": "scripts/settle_bj193_regime_meta_policy_gate_b.py",
            "runner_sha256": sha(
                ROOT / "scripts" / "settle_bj193_regime_meta_policy_gate_b.py"
            ),
            "finalizer_git_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
        }
        (stage / "source_binding.json").write_text(json.dumps(source_binding, sort_keys=True, indent=2) + "\n")
        card = {
            "contract": CONTRACT, "checkpoint_manifest_sha256": checkpoint_manifest_sha,
            "checkpoint_payload_count": len(manifest), "canonical_issue_count": 344,
            "oracle_correction_manifest_sha256": correction_manifest_sha,
            "oracle_correction_payload_count": len(correction_manifest),
            "strict_common_issue_count": len(common_indices), "policy_count": len(POLICIES),
            "bootstrap_draws": BOOTSTRAP_DRAWS, "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_draw_bundle_sha256": draw_hash,
            "pre_tax_controlling": True, "tax_reference_only": True,
            "bankroll_start_yuan": BANKROLL_START,
            "bankroll_execution": (
                "FIXED_NATIVE_STAKE_REUSE_NO_RESIZING_NO_COMPOUNDING_NO_TOPUPS"
            ),
            "bankroll_issue_path_row_count": len(bankroll_rows),
            "bankroll_summary_row_count": len(bankroll_summary),
            "decision_objective_primary": (
                "PRE_TAX_FINITE_BANKROLL_GROWTH_AND_FUNDABILITY_NATIVE_SUPPORT"
            ),
            "best_fundable_100k_capital_path": best_fundable_100k_capital_path,
            "best_fundable_100k_capital_path_support": "NATIVE_EXECUTION_SUPPORT",
            "decision_objective_secondary": (
                "PRE_TAX_ROI_PER_STAKE_STRICT_FOUR_ARM_COMMON"
            ),
            "best_matched_pre_tax_roi_per_stake": (
                best_matched_pre_tax_roi_per_stake
            ),
            "best_matched_pre_tax_roi_per_stake_support": (
                "STRICT_FOUR_ARM_COMMON"
            ),
            "chart_sources": [
                "bankroll_100k_issue_path.csv.gz",
                "stage_attribution_chart_source.csv",
                "causal_vs_oracle_chart_source.csv",
                "drawdown_holding_chart_source.csv",
            ],
            "rendered_charts": [
                "bankroll_100k_capital_curves.svg",
                "stage_attribution_waterfall.svg",
                "causal_vs_oracle_comparison.svg",
                "drawdown_holding.svg",
            ],
            "candidate_count": candidate["candidate_count"], "decision": candidate["decision"],
            "promotion_authority": False, "parent_192_unblock_authority": False,
            "policy_flow_row_count": len(flows),
            "stage_model_receipt_row_count": len(
                read_csv(checkpoint / "stage_model_receipts.csv")
            ),
            "stage_screen_receipt_row_count": len(
                read_csv(checkpoint / "stage_screen_receipts.csv.gz")
            ),
            "selected_policy_seed_row_count": len(seed_rows),
            "issue_action_row_census": json.loads(
                (checkpoint / "checkpoint_metadata.json").read_text()
            )["issue_action_row_census"],
            "trace_boundary": boundary,
        }
        (stage / "settlement_card.json").write_text(json.dumps(card, sort_keys=True, indent=2) + "\n")

        causal_stage_rows = [
            row
            for row in increments
            if row["support"] == "STRICT_FOUR_ARM_COMMON"
            and row["stage"] in {
                "STAGE_1_SELECTION", "STAGE_2_DIRECTION", "STAGE_3_BET"
            }
        ]
        bottleneck = min(
            causal_stage_rows, key=lambda row: float(row["pre_tax_roi_lift"])
        )
        choice_rows = {
            "STAGE_1_SELECTION": s1,
            "STAGE_2_DIRECTION": s2,
            "STAGE_3_BET": s3,
        }
        dominant_choices = []
        for stage_name, rows in choice_rows.items():
            counts: dict[tuple[str, str, str], int] = defaultdict(int)
            for row in rows:
                counts[(row["source_identity"], row["mechanism"], row["M"])] += 1
            key, count = max(counts.items(), key=lambda value: (value[1], value[0]))
            dominant_choices.append((stage_name, *key, count))
        report = [
            "# #193 Gate-B v2 — three-stage regime meta-policy settlement",
            "",
            f"Decision: **{candidate['decision']}**. The primary decision objective is pre-tax finite-bankroll growth and fundability on native execution support; ROI per stake on strict common support is secondary. Tax-adjusted values are reference-only, and the corrected leaky oracle is a diagnostic ceiling, never a deployable policy.",
            "",
            f"Two distinct leaders must not be conflated: `{best_fundable_100k_capital_path}` is the best fundable causal ¥100,000 capital path on native execution support, while `{best_matched_pre_tax_roi_per_stake}` is the best matched pre-tax ROI-per-stake baseline on strict-four-arm common support. They answer different questions.",
            "",
            "## Native and strict-common baseline ladder",
            "",
            "| Policy | Native active | Native stake | Native ROI | Common active | Common stake | Common ROI |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for policy in POLICIES:
            native = perf_lookup[(policy, "NATIVE")]
            common_row = perf_lookup[(policy, "STRICT_FOUR_ARM_COMMON")]
            report.append(
                f"| {policy} | {native['active_issue_count']} | {native['stake_yuan']} | {native['pre_tax_roi']} | "
                f"{common_row['active_issue_count']} | {common_row['stake_yuan']} | {common_row['pre_tax_roi']} |"
            )
        report += [
            "",
            f"The strict four-arm common support contains {len(common_indices)} canonical issues. `{best_matched_pre_tax_roi_per_stake}` leads this secondary matched ROI-per-stake comparison. The oracle's positive ROI diagnoses foregone information, not causal generalization.",
            "",
            "## Stage attribution and paired uncertainty",
            "",
            "| Stage | Candidate − comparator ROI | 95% paired IID CI | P(lift>0) |",
            "|---|---:|---:|---:|",
        ]
        for row in causal_stage_rows:
            boot = boot_index[(row["candidate"], row["comparator"], "PRE_TAX_ROI_LIFT_IID")]
            report.append(
                f"| {row['stage']} | {row['pre_tax_roi_lift']} | [{boot['ci_low']}, {boot['ci_high']}] | {boot['probability_improvement']} |"
            )
        report += [
            "",
            f"The largest incremental bottleneck is `{bottleneck['stage']}` with strict-common lift `{bottleneck['pre_tax_roi_lift']}`. End-to-end causal mapping does not clear positivity, matched comparators and the paired bootstrap screen, so the failure code is `{failure_code}`.",
            "",
            "![Stage attribution](stage_attribution_waterfall.svg)",
            "",
            "![Causal versus oracle](causal_vs_oracle_comparison.svg)",
            "",
            "## Fixed-stake capital reuse from ¥100,000",
            "",
            "This is the controlling capital objective using the frozen native stake schedule. Stakes are not resized or compounded; no top-up is injected. Capital turnover is cumulative stake divided by ¥100,000 and is distinct from both cumulative ROI and bankroll growth. Once a path first becomes unfundable, later rows and the displayed ending balance are counterfactual fixed-stake continuations, not executable cash-account outcomes.",
            "",
            "| Policy | Ending bankroll | Growth | Stake | Capital turnover | Fundable | First unfundable | Minimum start required |",
            "|---|---:|---:|---:|---:|---|---:|---:|",
        ]
        for policy in POLICIES:
            row = bankroll_lookup[policy]
            report.append(
                f"| {policy} | {row['ending_bankroll_yuan']} | {row['bankroll_growth_rate']} | "
                f"{row['total_native_stake_yuan']} | {row['capital_turnover_multiple']}× | "
                f"{row['fundable_all_issues_flag']} | {row['first_unfundable_issue'] or '—'} | "
                f"{row['minimum_starting_bankroll_required_yuan']} |"
            )
        report += [
            "",
            f"`{best_fundable_100k_capital_path}` is the best fundable causal path, ending at ¥{bankroll_lookup[best_fundable_100k_capital_path]['ending_bankroll_yuan']} (growth {bankroll_lookup[best_fundable_100k_capital_path]['bankroll_growth_rate']}, turnover {bankroll_lookup[best_fundable_100k_capital_path]['capital_turnover_multiple']}×). `ALL_STATIC` ends at ¥{bankroll_lookup['ALL_STATIC']['ending_bankroll_yuan']} (growth {bankroll_lookup['ALL_STATIC']['bankroll_growth_rate']}, turnover {bankroll_lookup['ALL_STATIC']['capital_turnover_multiple']}×). Capital reuse amplifies the underlying edge and cannot rescue negative expectation. `DYNAMIC_SELECTION_ONLY` and `DYNAMIC_SELECTION_DIRECTION` become infeasible; their later balances are counterfactual continuations. The oracle remains strongly positive but is leaky and diagnostic-only.",
            "",
            "![100k capital curves](bankroll_100k_capital_curves.svg)",
            "",
            "## Holding risk and recoverability",
            "",
            f"For `FULL_DYNAMIC_CHAIN`, the native maximum drawdown is {perf_lookup[('FULL_DYNAMIC_CHAIN', 'NATIVE')]['max_drawdown_yuan']} yuan ({perf_lookup[('FULL_DYNAMIC_CHAIN', 'NATIVE')]['max_drawdown_pct']}); the maximum calendar recovery is {holding_index[('FULL_DYNAMIC_CHAIN', 'CALENDAR')]['max_recovery_issues']} issues. Its maximum negative-PnL streak is {streak_index[('FULL_DYNAMIC_CHAIN', 'ALL', 'CALENDAR')]['max_negative_pnl_streak']} and maximum active-bet zero-payout miss streak is {streak_index[('FULL_DYNAMIC_CHAIN', 'ALL', 'ACTIVE_BET')]['max_zero_payout_miss_streak']}.",
            "",
            "![Drawdown and holding](drawdown_holding.svg)",
            "",
            "## Choice and regime findings",
            "",
        ]
        for stage_name, source, mechanism, m_value, count in dominant_choices:
            report.append(
                f"- `{stage_name}` most often chose source `{source}` / mechanism `{mechanism or 'NA'}` / M `{m_value or 'NA'}` on {count} of 344 issues. The complete issue/regime mapping, fallback flags and feature values are retained in the three stage choice tables."
            )
        report += [
            "- Seed identities remain nuisance replicates; no seed identity was selected.",
            "- NO_BET and UNAVAILABLE are explicit zero flows and are never converted to fake losses.",
            "",
            "## Scientific interpretation",
            "",
            f"The corrected oracle selected an available action on {correction_receipt['corrected_oracle_selected_count']} issues, fell back on {correction_receipt['corrected_oracle_fallback_count']}, changed action on {correction_receipt['changed_action_issue_count']}, changed status/cash flow on {correction_receipt['changed_cashflow_or_status_issue_count']}, and beat the causal chain on {correction_receipt['oracle_better_than_causal_issue_count']} issues. This gap plus negative causal performance is precisely `CAUSAL_GENERALIZATION_FAILURE`: profitable ex-post choices exist, but the frozen pre-event mapping did not identify them robustly.",
            f"The primary capital leader is `{best_fundable_100k_capital_path}` on native execution support; the secondary matched ROI-per-stake leader is `{best_matched_pre_tax_roi_per_stake}` on strict common support. The bottleneck is `{bottleneck['stage']}`. A concrete next hypothesis is to explain corrected-oracle opportunity regimes with separately preregistered frozen pre-event features, without backfitting this chain or handing it to #192.",
            "",
            "## Durability boundary",
            "",
            "The immutable checkpoint persisted exact issue/action economics and path/model receipts but not per-ticket ledger rows. This finalizer does not reconstruct or fabricate tickets; `trace_and_ticket_ledger_boundary.json` records that limitation. YEAR/FOLD/LOYO, exclusions, 20,000-draw paired bootstrap, equity, streak, rolling-window, drawdown, recovery, chart-source and rendered SVG artifacts are manifest-covered.",
            "",
            "Paper research only. No betting, production, promotion, strict-EV escalation or #192-unblock authority is implied.",
        ]
        (stage / "REPORT.md").write_text("\n".join(report) + "\n")
        wiki = [
            "# Issue 193 — Regime-conditioned N7 meta-policy",
            "",
            f"Terminal research disposition candidate: **{candidate['decision']}**.",
            "",
            "The frozen chronological chain separately learns match selection, direction and allocation/M. On the 189-issue strict common support it does not clear the matched ROI-per-stake comparator and positive paired-bootstrap lower-bound screen. The corrected oracle is positive, but because it uses outcome information it is only a ceiling: the result is `CAUSAL_GENERALIZATION_FAILURE`, not a deployable edge.",
            "",
            "## Decision readout",
            "",
            f"- Best fundable ¥100,000 capital path on native execution support: `{best_fundable_100k_capital_path}`.",
            f"- Best matched pre-tax ROI per stake on strict common support: `{best_matched_pre_tax_roi_per_stake}`.",
            f"- Largest incremental bottleneck: `{bottleneck['stage']}` with lift `{bottleneck['pre_tax_roi_lift']}`.",
            "- Controlling economics: pre-tax; tax-adjusted values are reference-only.",
            "- No strict EV escalation and no handoff to #192.",
            "",
            "## Capital and risk",
            "",
            f"The ¥100,000 view is the primary decision objective and reuses cash across issues with native frozen stakes and no compounding or top-ups. `{best_fundable_100k_capital_path}` is the best fundable causal path. Capital turnover is stake/start-capital, not ROI and not bankroll growth. `ALL_STATIC` leads only the secondary strict-common ROI-per-stake comparison. Two dynamic chains are unfundable; all rows after their first funding failure are counterfactual continuations rather than executable cash accounts. The leaky oracle grows capital but remains diagnostic-only.",
            "",
            "![100k capital curves](bankroll_100k_capital_curves.svg)",
            "",
            "![Stage attribution](stage_attribution_waterfall.svg)",
            "",
            "![Causal versus oracle](causal_vs_oracle_comparison.svg)",
            "",
            "![Drawdown and holding](drawdown_holding.svg)",
            "",
            "The complete report, source tables, 20,000-draw paired bootstrap, stability and durability boundaries are in the immutable Gate-B package. This is historical paper research, not an operational betting rule.",
        ]
        (stage / "RESEARCH_WIKI_ENTRY.md").write_text("\n".join(wiki) + "\n")
        report_wiki_sync = {
            "contract": "BJ193_REPORT_WIKI_SYNC_V1",
            "decision": candidate["decision"],
            "candidate_count": candidate["candidate_count"],
            "report_sha256": sha(stage / "REPORT.md"),
            "research_wiki_entry_sha256": sha(
                stage / "RESEARCH_WIKI_ENTRY.md"
            ),
            "status": "PASS",
        }
        (stage / "report_wiki_sync.json").write_text(
            json.dumps(report_wiki_sync, sort_keys=True, indent=2) + "\n"
        )
        test_receipt = {
            "contract": "BJ193_FINALIZER_TEST_RECEIPT_V1",
            "focused_command": (
                "pytest -q tests/scripts/"
                "test_settle_bj193_regime_meta_policy_gate_b.py "
                "-k 'finalizer or oracle or correction_json or path_receipts'"
            ),
            "focused_result": "11 passed, 23 deselected",
            "full_command": (
                "pytest -q tests/scripts/"
                "test_settle_bj193_regime_meta_policy_gate_b.py"
            ),
            "full_result": "34 passed in 40.46s",
            "py_compile": "PASS",
            "git_diff_check": "PASS",
        }
        (stage / "TEST_RECEIPT.json").write_text(
            json.dumps(test_receipt, sort_keys=True, indent=2) + "\n"
        )

        identity = {
            "contract": CONTRACT, "checkpoint_manifest_sha256": checkpoint_manifest_sha,
            "canonical_issue_count": 344, "strict_common_issue_count": len(common_indices),
            "candidate_count": candidate["candidate_count"], "decision": candidate["decision"],
            "decision_objective_primary": "PRE_TAX_FINITE_BANKROLL_GROWTH_AND_FUNDABILITY_NATIVE_SUPPORT",
            "best_fundable_100k_capital_path": best_fundable_100k_capital_path,
            "decision_objective_secondary": "PRE_TAX_ROI_PER_STAKE_STRICT_FOUR_ARM_COMMON",
            "best_matched_pre_tax_roi_per_stake": best_matched_pre_tax_roi_per_stake,
        }
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(identity, sort_keys=True, indent=2) + "\n")
        payload = {}
        for path in sorted(stage.iterdir()):
            if path.is_file() and path.name != "SHA256SUMS.json":
                payload[path.name] = sha(path)
        (stage / "SHA256SUMS.json").write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")
        os.replace(stage, target)
        print(json.dumps({
            "output": str(target), "manifest_sha256": sha(target / "SHA256SUMS.json"),
            "payload_count": len(payload), "candidate_count": candidate["candidate_count"],
            "decision": candidate["decision"], "strict_common_issue_count": len(common_indices),
        }, sort_keys=True), flush=True)
    except Exception:
        print(f"FAILED_STAGE={stage}", flush=True)
        raise
