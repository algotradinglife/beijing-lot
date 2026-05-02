"""Phase 5a CLI: ``python -m src.phase5a plan|reconcile``.

Examples:
    # Build & save weekly plan, print markdown
    python -m src.phase5a plan --bankroll 100000

    # Reconcile a saved plan against current settlements
    python -m src.phase5a reconcile --plan data/phase5a_plans/2026-W18.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .data_loader import load_open_matches
from .filter import NicheConfig
from .planner import (
    DEFAULT_KELLY_FRACTION,
    DEFAULT_N_LEGS,
    build_weekly_plan,
    format_plan_markdown,
    save_plan_json,
)
from .reconcile import reconcile_plan

DEFAULT_DB = "data/beidan_live.db"
DEFAULT_PLAN_DIR = "data/phase5a_plans"
DEFAULT_PNL_LOG = "data/phase5a_pnl/pnl_log.csv"


def _add_plan_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("--bankroll", type=float, required=True)
    p.add_argument("--n-legs", type=int, default=DEFAULT_N_LEGS)
    p.add_argument("--kelly", type=float, default=DEFAULT_KELLY_FRACTION,
                   help="Kelly fraction (default 1/16 = 0.0625)")
    p.add_argument("--cap-frac", type=float, default=0.25,
                   help="Weekly stake cap as fraction of bankroll")
    p.add_argument("--combo-ev", type=float, default=0.05,
                   help="Min combo EV (per yuan) to keep")
    p.add_argument("--top-k", type=int, default=14)
    p.add_argument("--max-combos", type=int, default=50)
    p.add_argument("--window-days", type=int, default=7)
    p.add_argument("--niches", default=None, help="Path to niches JSON")
    p.add_argument("--out-dir", default=DEFAULT_PLAN_DIR)
    p.add_argument("--no-save", action="store_true",
                   help="Print plan but skip saving JSON to disk")


def cmd_plan(args: argparse.Namespace) -> int:
    snaps = load_open_matches(args.db, window_days=args.window_days)
    cfg = NicheConfig.load(args.niches)
    plan = build_weekly_plan(
        snaps,
        bankroll=args.bankroll,
        niche_config=cfg,
        n_legs=args.n_legs,
        kelly_fraction=args.kelly,
        weekly_stake_cap_frac=args.cap_frac,
        combo_ev_threshold=args.combo_ev,
        top_k=args.top_k,
        max_combos=args.max_combos,
    )
    print(format_plan_markdown(plan))
    if not args.no_save:
        path = save_plan_json(plan, args.out_dir)
        print(f"\n_Saved: {path}_", file=sys.stderr)
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    res = reconcile_plan(args.plan, args.db, args.pnl_log)
    print(f"# Reconcile {res.plan_id}")
    print(f"- Reconciled at: {res.reconciled_at}")
    print(f"- Tickets settled: {res.n_tickets} (pending: {res.pending})")
    print(f"- Winning tickets: {res.n_winning_tickets}")
    print(f"- Total stake: {res.total_stake}")
    print(f"- Gross payout: {res.gross_payout:.2f}")
    print(f"- Net PnL: {res.net_pnl:+.2f}")
    print()
    print("| # | Status | Stake | Payout | PnL |")
    print("|---|---|---:|---:|---:|")
    for o in res.ticket_outcomes:
        print(f"| {o.ticket_no} | {o.status} | {o.stake} | {o.payout:.2f} | {o.pnl:+.2f} |")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="phase5a", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_plan = sub.add_parser("plan", help="Build weekly bet plan")
    _add_plan_args(p_plan)
    p_plan.set_defaults(func=cmd_plan)

    p_rec = sub.add_parser("reconcile", help="Reconcile saved plan vs settlements")
    p_rec.add_argument("--plan", required=True, help="Path to plan JSON")
    p_rec.add_argument("--db", default=DEFAULT_DB)
    p_rec.add_argument("--pnl-log", default=DEFAULT_PNL_LOG)
    p_rec.set_defaults(func=cmd_reconcile)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
