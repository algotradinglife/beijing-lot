# 北单 7-leg combo optimizer (v1 prototype)

**Date**: 2026-05-02
**Code**: `src/combo_optimizer/`
**Tests**: `tests/combo_optimizer/` (36 passed)
**Demo**: `notebooks/combo_optimizer_demo.py`

## Why a combo optimizer

Single-bet 北单 is structurally −EV (35% rake; need r ≥ 1.538 single-leg, i.e. 53.8% probability edge — impossible). For an N-leg combo the rake is paid **once**: payout = ∏SP × stake × 0.65, so per-leg break-even drops to (1/0.65)^(1/N). At N = 7 it is 6.35% per leg — achievable if the group-bias edge thesis (`docs/research/sp-bias-and-kelly.md`) holds.

Plus two tax/structuring multipliers stacked on top:
- China lottery tax: prize ≥ 10,000 yuan → 20% on full amount (cliff). Splitting one combo bet into multiple identical sub-9999 tickets dodges the cliff entirely.
- Co-owned 彩票站 commission rebate (orthogonal — not modeled here).

This optimizer takes the weekly candidate list and produces a portfolio of 7-leg combo tickets sized for ¼-Kelly under both a tax-cap-per-ticket constraint and a 25%-of-bankroll weekly stake cap.

## Algorithm

1. **Filter** candidates by single-leg edge > 0.05 (consistent with `T = 0.05` from the v1 design spec).
2. **Same-match dedup**: a combo cannot have two legs on the same match (only one outcome happens). Keep the highest-edge selection per match_id.
3. **Top-K**: take the K = 14 highest-edge candidates.
4. **Enumerate** C(K, 7) combos (3,432 at K = 14).
5. **Filter combos** by EV ≥ 0.10 (i.e. 10% expected return per yuan; well above break-even, leaves headroom for model error).
6. **Rank** by EV; cap at `max_combos = 50`.
7. **Per-combo Kelly stake**: f* = (p × payout − 1)/(payout − 1); raw_stake = bankroll × ¼ × f*.
8. **Per-ticket tax cap**: max stake/ticket = floor(9999 / (∏SP × 0.65)), rounded down to even.
9. **Split**: if raw ≤ cap → 1 ticket; else ⌈raw/cap⌉ tickets at cap.
10. **Bankroll cap**: scale all per-ticket stakes proportionally if Σ total > 25% × bankroll.

## Public API

```python
from src.combo_optimizer import build_plan, Candidate

plans = build_plan(
    candidates,            # list[Candidate(match_id, selection, p_hat, sp)]
    bankroll=100_000,
    weekly_stake_cap_frac=0.25,
    n_legs=7,
    top_k=14,
    combo_ev_threshold=0.10,
    kelly_fraction=0.25,
    max_combos=50,
)
# → list[TicketPlan(combo, stake_per_ticket, n_tickets)]
```

## Sample output (mock 30-candidate run, bankroll = 100k)

```
  #     ∏SP   p_combo      EV   stake   n   total   prize  legs
  1  2254.6  0.01560  +21.86       6  63     378    8793  M25:0,M05:3,M28:3,M03:3,M07:3,M16:1,M10:1
  2  2579.8  0.01359  +21.78       4  82     328    6707  M25:0,M05:3,M28:3,M03:3,M07:3,M16:1,M19:0
  3  4031.3  0.00869  +21.77       2 104     208    5241  M25:0,M05:3,M28:3,M03:3,M07:3,M10:1,M19:0
  ... (50 combos total) ...
Total stake:  12,956 yuan  (13.0% of bankroll)
Total tickets:  3,852      max prize/ticket 9984  all tax-free: True
```

(Mock distribution: 70% of candidates at 3-8% edge, 30% at 8-15% edge, SP uniform 2-5. Inflated combo EVs reflect mock priors — real-world edges will produce far smaller, but still positive, combo EVs.)

## Known limitations (read these)

1. **Combo independence is assumed**. ∏SP × ∏p is exact only for independent legs; legs from different matches are usually only weakly correlated, so the per-combo EV is approximately right. **But combos that share legs in the portfolio are very correlated** — e.g. combos #1 and #2 in the demo share 6 legs. Per-combo Kelly therefore systematically **overstates** the optimal aggregate stake. The 25% weekly bankroll cap is the safety net; in the demo the natural sizing came in at 13% (under cap) but with adversarial parameters the cap binds. Do not treat per-combo Kelly as exact.

2. **Mock candidates ≠ real candidates**. Demo edges (3-15% per leg) are illustrative; real Live Collector edges may be smaller (1-4% per leg) once we have ≥ 6 months of SP data, and many weeks may produce zero combos.

3. **Independence in p_hat estimation**. `p_hat` for each leg is treated as a point estimate; no shrinkage / no model uncertainty propagated. A miscalibration of 1pp on each leg compounds to ~7pp on a 7-leg combo's joint p.

4. **No correlation-aware portfolio optimization**. Future work: replace per-combo Kelly with a portfolio-level log-utility maximization across overlapping combos (LP / convex program over combo weights).

5. **No commission share / station economics**. The 7% rebate on self-bets through co-owned stations is orthogonal here; multiply final EV by `(1 + 0.07 × ownership_frac)` outside this module.

6. **Cliff-only tax model**. We assume splitting is operationally clean (different physical tickets, different claimants). User has confirmed this is feasible but the regulatory edge case has not been pressure-tested.

## Edge cases handled

- < 7 viable candidates → `[]` with `WARNING` log.
- No combo passes EV threshold → `[]`.
- Computed stake < 2 yuan → combo skipped (cannot place a legal ticket).
- Payout so large that even a 2-yuan ticket would exceed the 10k cliff → combo skipped.
- Bankroll-cap scaling that would push a stake below 2 yuan → that combo dropped from the final plan.
