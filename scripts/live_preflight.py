#!/usr/bin/env python3
"""Preflight bankroll and exposure checks before a live N7 issue."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


SETTLED_STATUSES = {"settled", "closed", "paid"}
INACTIVE_STATUSES = SETTLED_STATUSES | {"void", "cancelled", "canceled", "skipped", "paper"}

SLEEVE_RATIOS = {
    "fixed_base_units": 256.0 / 384.0,
    "same_ticket2_alt_risk_units": 32.0 / 384.0,
    "same_ticket4_full_risk_units": 76.8 / 384.0,
    "same_ticket2_draw_risk_units": 19.2 / 384.0,
}


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "是"}


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def status(row: dict[str, str]) -> str:
    return str(row.get("settlement_status", "")).strip().lower()


def latest_settled_state(rows: list[dict[str, str]], *, starting_equity: float) -> dict[str, float | str]:
    equity = starting_equity
    high_watermark = starting_equity
    issue = ""
    for row in rows:
        if status(row) not in SETTLED_STATUSES:
            continue
        after = fnum(row.get("equity_after"), math.nan)
        if not math.isfinite(after):
            continue
        equity = after
        high = fnum(row.get("high_watermark_after"), math.nan)
        high_watermark = high if math.isfinite(high) else max(high_watermark, equity)
        issue = row.get("issue", "")
    high_watermark = max(high_watermark, equity)
    return {"equity": equity, "high_watermark": high_watermark, "source_issue": issue}


def pending_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows:
        st = status(row)
        if st in INACTIVE_STATUSES:
            continue
        stake = fnum(row.get("actual_stake_units"), fnum(row.get("planned_stake_units")))
        if stake > 0:
            out.append(row)
    return out


def issue_cap_for_equity(equity: float) -> tuple[float, str]:
    if equity >= 15000:
        return 384.0, "live_equity_ge15000_384"
    if equity >= 12000:
        return 320.0, "live_equity_ge12000_320"
    return 256.0, "live_equity_base_256"


def sleeve_allocation(cap: float) -> dict[str, float]:
    return {name: cap * ratio for name, ratio in SLEEVE_RATIOS.items()}


def hard_stop_reasons(args: argparse.Namespace, rows: list[dict[str, str]]) -> list[str]:
    reasons: list[str] = []
    if args.data_bad:
        reasons.append("data_bad")
    if args.close_time_unverified:
        reasons.append("close_time_unverified")
    if args.plan_not_reproducible:
        reasons.append("plan_not_reproducible")
    if args.settlement_incomplete:
        reasons.append("settlement_incomplete")
    if args.ticket_mismatch:
        reasons.append("ticket_mismatch")
    if args.manual_override_needed:
        reasons.append("manual_override_needed")
    for row in rows:
        if truthy(row.get("hard_stop_violation")) or truthy(row.get("rule_violation")):
            reasons.append(f"ledger_violation:{row.get('issue', '')}")
    return reasons


def build_preflight(args: argparse.Namespace) -> dict[str, object]:
    rows = read_rows(args.ledger)
    state = latest_settled_state(rows, starting_equity=args.starting_equity)
    equity = fnum(args.equity_override, fnum(state["equity"])) if args.equity_override is not None else fnum(state["equity"])
    high_watermark = (
        fnum(args.high_watermark_override, fnum(state["high_watermark"]))
        if args.high_watermark_override is not None
        else fnum(state["high_watermark"])
    )
    high_watermark = max(high_watermark, equity)
    drawdown = max(0.0, high_watermark - equity)
    target_cap, cap_reason = issue_cap_for_equity(equity)
    issue_cap = min(target_cap, equity) if equity > 0 else 0.0

    open_rows = pending_rows(rows)
    pending_exposure = sum(
        fnum(row.get("actual_stake_units"), fnum(row.get("planned_stake_units"))) for row in open_rows
    )
    pending_exposure += args.pending_exposure_extra
    pending_limit = min(3.0 * issue_cap, 0.08 * equity) if issue_cap > 0 else 0.0
    allowed_by_pending = max(0.0, pending_limit - pending_exposure)
    execution_cap = min(issue_cap, allowed_by_pending)
    hard_reasons = hard_stop_reasons(args, rows)
    red_zone = drawdown >= args.red_zone_drawdown or equity < args.red_zone_equity
    full_cap_allowed = issue_cap > 0 and pending_exposure + issue_cap <= pending_limit
    live_allowed = issue_cap > 0 and execution_cap > 0 and not hard_reasons

    allocation = sleeve_allocation(execution_cap)
    next_row_preview = {
        "ledger_seq": len(rows) + 1,
        "issue": args.issue or "",
        "issue_close_ts": args.issue_close_ts or "",
        "settlement_status": "planned",
        "strategy_version": args.strategy_version,
        "equity_before": round(equity, 4),
        "high_watermark_before": round(high_watermark, 4),
        "drawdown_before": round(drawdown, 4),
        "issue_cap": round(execution_cap, 4),
        "target_issue_cap": round(target_cap, 4),
        "pending_exposure_before": round(pending_exposure, 4),
        "pending_limit": round(pending_limit, 4),
        "allowed_new_stake": round(allowed_by_pending, 4),
        "planned_stake_units": round(execution_cap, 4),
        "actual_stake_units": "",
        **{key: round(value, 4) for key, value in allocation.items()},
        "generated_plan_path": "",
        "submitted_ticket_ref": "",
        "profit_units": "",
        "equity_after": "",
        "high_watermark_after": "",
        "drawdown_after": "",
        "pending_exposure_after": round(pending_exposure + execution_cap, 4),
        "red_zone_review_required": int(red_zone),
        "hard_stop_violation": int(bool(hard_reasons)),
        "rule_violation": "",
        "notes": ";".join(hard_reasons),
    }
    return {
        "ledger": str(args.ledger),
        "source_issue": state["source_issue"],
        "issue": args.issue or "",
        "equity": round(equity, 4),
        "high_watermark": round(high_watermark, 4),
        "drawdown": round(drawdown, 4),
        "target_issue_cap": round(target_cap, 4),
        "issue_cap_after_equity_constraint": round(issue_cap, 4),
        "cap_reason": cap_reason,
        "pending_exposure": round(pending_exposure, 4),
        "pending_limit": round(pending_limit, 4),
        "allowed_new_stake_by_pending": round(allowed_by_pending, 4),
        "recommended_execution_cap": round(execution_cap, 4),
        "full_cap_allowed": full_cap_allowed,
        "red_zone_review_required": red_zone,
        "hard_stop": bool(hard_reasons),
        "hard_stop_reasons": hard_reasons,
        "live_allowed": live_allowed,
        "open_issues": [
            {
                "issue": row.get("issue", ""),
                "settlement_status": row.get("settlement_status", ""),
                "stake_units": fnum(row.get("actual_stake_units"), fnum(row.get("planned_stake_units"))),
            }
            for row in open_rows
        ],
        "sleeve_allocation": {key: round(value, 4) for key, value in allocation.items()},
        "next_row_preview": next_row_preview,
    }


def write_preview_row(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("docs/strategy/live_ledger_template_10000.csv"))
    parser.add_argument("--starting-equity", type=float, default=10000.0)
    parser.add_argument("--equity-override", type=float)
    parser.add_argument("--high-watermark-override", type=float)
    parser.add_argument("--pending-exposure-extra", type=float, default=0.0)
    parser.add_argument("--issue", default="")
    parser.add_argument("--issue-close-ts", default="")
    parser.add_argument("--strategy-version", default="scaled_b384_dd32_smooth80_convex19")
    parser.add_argument("--red-zone-drawdown", type=float, default=3200.0)
    parser.add_argument("--red-zone-equity", type=float, default=6800.0)
    parser.add_argument("--output-json", type=Path, default=Path("results/live_preflight/latest_preflight.json"))
    parser.add_argument("--write-preview-row", type=Path)
    parser.add_argument("--data-bad", action="store_true")
    parser.add_argument("--close-time-unverified", action="store_true")
    parser.add_argument("--plan-not-reproducible", action="store_true")
    parser.add_argument("--settlement-incomplete", action="store_true")
    parser.add_argument("--ticket-mismatch", action="store_true")
    parser.add_argument("--manual-override-needed", action="store_true")
    args = parser.parse_args()

    result = build_preflight(args)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.write_preview_row:
        write_preview_row(args.write_preview_row, result["next_row_preview"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Wrote {args.output_json}")


if __name__ == "__main__":
    main()
