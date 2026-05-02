"""Optional CLI: load candidates from CSV and print a plan.

CSV columns: match_id, selection, p_hat, sp
"""
from __future__ import annotations

import argparse
import csv
import sys
from typing import List

from .main import build_plan
from .types import Candidate, TicketPlan


def load_candidates(path: str) -> List[Candidate]:
    out: List[Candidate] = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out.append(
                Candidate(
                    match_id=row["match_id"].strip(),
                    selection=int(row["selection"]),
                    p_hat=float(row["p_hat"]),
                    sp=float(row["sp"]),
                )
            )
    return out


def format_plan(plans: List[TicketPlan]) -> str:
    if not plans:
        return "(no tickets)"
    header = (
        f"{'#':>3}  {'∏SP':>9}  {'p_combo':>8}  {'EV':>7}  "
        f"{'stake':>6}  {'n':>3}  {'total':>7}  {'prize':>9}  legs"
    )
    lines = [header, "-" * len(header)]
    for i, p in enumerate(plans, 1):
        legs = ", ".join(f"{leg.match_id}:{leg.selection}" for leg in p.combo.legs)
        lines.append(
            f"{i:>3}  {p.combo.joint_sp:>9.3f}  {p.combo.joint_p:>8.5f}  "
            f"{p.combo.ev:>7.3f}  {p.stake_per_ticket:>6d}  {p.n_tickets:>3d}  "
            f"{p.total_stake:>7d}  {p.prize_per_ticket:>9.0f}  {legs}"
        )
    total = sum(p.total_stake for p in plans)
    lines.append(f"\nTotal stake: {total} yuan across {len(plans)} combos")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="北单 7-leg combo plan builder")
    ap.add_argument("csv", help="candidate CSV (match_id,selection,p_hat,sp)")
    ap.add_argument("--bankroll", type=float, required=True)
    ap.add_argument("--n-legs", type=int, default=7)
    ap.add_argument("--top-k", type=int, default=14)
    ap.add_argument("--combo-ev", type=float, default=0.10)
    ap.add_argument("--kelly", type=float, default=0.25)
    ap.add_argument("--cap-frac", type=float, default=0.25)
    ap.add_argument("--max-combos", type=int, default=50)
    args = ap.parse_args(argv)

    cands = load_candidates(args.csv)
    plans = build_plan(
        cands,
        args.bankroll,
        n_legs=args.n_legs,
        top_k=args.top_k,
        combo_ev_threshold=args.combo_ev,
        kelly_fraction=args.kelly,
        weekly_stake_cap_frac=args.cap_frac,
        max_combos=args.max_combos,
    )
    print(format_plan(plans))
    return 0


if __name__ == "__main__":
    sys.exit(main())
