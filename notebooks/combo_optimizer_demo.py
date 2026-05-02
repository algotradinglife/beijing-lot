"""Demo: 30 mock candidates → 7-leg combo plan at bankroll = 100k yuan.

Run from project root:
    python3 notebooks/combo_optimizer_demo.py
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

# Allow running directly from the notebooks/ folder.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.combo_optimizer import Candidate, build_plan  # noqa: E402


def make_mock_candidates(seed: int = 7, n: int = 30) -> list[Candidate]:
    """Realistic edge mix:
    - 70% candidates: per-leg edge in [3%, 8%] (most marginal)
    - 30% candidates: per-leg edge in [8%, 15%] (a few standouts)
    SP uniform in [2.0, 5.0].
    """
    rng = random.Random(seed)
    cands: list[Candidate] = []
    for i in range(n):
        sp = rng.uniform(2.0, 5.0)
        edge = (
            rng.uniform(0.03, 0.08) if rng.random() < 0.7 else rng.uniform(0.08, 0.15)
        )
        # p × SP × 0.65 = 1 + edge
        p_hat = (1.0 + edge) / (sp * 0.65)
        p_hat = min(0.95, max(0.01, p_hat))
        sel = rng.choice([3, 1, 0])
        cands.append(
            Candidate(match_id=f"M{i:02d}", selection=sel, p_hat=p_hat, sp=sp)
        )
    return cands


def main() -> None:
    bankroll = 100_000.0
    cands = make_mock_candidates()

    # Show input candidate distribution
    print("=" * 100)
    print("INPUT — 30 mock candidates")
    print("=" * 100)
    print(f"{'match':>6}  {'sel':>3}  {'p_hat':>7}  {'SP':>5}  {'edge':>7}")
    for c in sorted(cands, key=lambda c: c.edge, reverse=True):
        print(
            f"{c.match_id:>6}  {c.selection:>3}  {c.p_hat:>7.4f}  "
            f"{c.sp:>5.2f}  {c.edge:>+7.4f}"
        )

    plans = build_plan(
        cands,
        bankroll=bankroll,
        weekly_stake_cap_frac=0.25,
        n_legs=7,
        top_k=14,
        combo_ev_threshold=0.10,
        kelly_fraction=0.25,
        max_combos=50,
    )

    print()
    print("=" * 100)
    print(f"OUTPUT — {len(plans)} combo tickets at bankroll = {bankroll:,.0f} yuan")
    print("=" * 100)
    header = (
        f"{'#':>3}  {'∏SP':>9}  {'p_combo':>9}  {'EV':>7}  "
        f"{'stake':>6}  {'n':>3}  {'total':>7}  {'prize':>9}  legs"
    )
    print(header)
    print("-" * len(header))
    for i, p in enumerate(plans, 1):
        legs = ",".join(f"{leg.match_id}:{leg.selection}" for leg in p.combo.legs)
        print(
            f"{i:>3}  {p.combo.joint_sp:>9.2f}  {p.combo.joint_p:>9.6f}  "
            f"{p.combo.ev:>+7.3f}  {p.stake_per_ticket:>6d}  "
            f"{p.n_tickets:>3d}  {p.total_stake:>7d}  "
            f"{p.prize_per_ticket:>9.0f}  {legs}"
        )

    total_stake = sum(p.total_stake for p in plans)
    total_tickets = sum(p.n_tickets for p in plans)
    pct = total_stake / bankroll * 100
    all_tax_free = all(p.is_tax_free for p in plans)
    print()
    print(f"Total stake:         {total_stake:>10,d} yuan  ({pct:.2f}% of bankroll)")
    print(f"Total tickets:       {total_tickets:>10d}")
    print(f"All tax-free:        {all_tax_free}")
    if plans:
        max_prize = max(p.prize_per_ticket for p in plans)
        print(f"Max single-ticket prize:  {max_prize:>6.0f} yuan (cap = 9_999)")


if __name__ == "__main__":
    main()
