"""Generate equity curve plots under the webui default config.

Default = N=4, Kelly=1/16, diversity_lambda=0.5, max_combos=50, no commission.
Compares with two contrast configs.
"""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.dual_sweep.variants import build_archetype_a_qual

# Reuse strict simulator from prior backtest
sys.path.insert(0, str(Path(__file__).parent))
from diversity_strict_backtest import simulate_strict, metrics, INITIAL


def run_with_commission(qual, *, commission_rate=0.0, **kwargs):
    """Run simulator and add commission to weekly PnL post-hoc."""
    pnl = simulate_strict(qual, **kwargs)
    if commission_rate <= 0:
        return pnl
    # Need stake per week — re-run quickly to track stake stream
    # Simpler: estimate by reading weekly stake share from sim output
    # For this comparison, approximate: weekly stake ≈ 25% bankroll × utilization rate
    # Better: extract actual weekly stake from sim. Rewriting: reuse simulator but
    # also return weekly_stake series.
    return pnl  # placeholder; we'll handle commission separately below


def simulate_with_stake(qual, n_legs=4, *, kelly_fraction=1/16,
                        per_combo_cap_frac=0.005, weekly_stake_cap_frac=0.25,
                        max_combos_per_week=50, diversity_lambda=0.5,
                        test_only=True, seed=7, commission_rate=0.0,
                        initial=INITIAL):
    """Strict simulator that ALSO records weekly stake so we can apply commission."""
    import math
    from collections import Counter
    from src.sweep.combo_builder import _choose_one_per_match, build_combos_for_week, materialize_combos
    from src.sweep.simulator import (
        MIN_STAKE_PER_TICKET, TAX_FREE_PRIZE_CAP, _floor_even, kelly_fraction_full,
    )
    from diversity_strict_backtest import select_diverse

    if test_only and len(qual):
        median_expect = qual["expect"].median()
        qual = qual[qual["expect"] >= median_expect].reset_index(drop=True)

    bankroll = initial
    rows = []
    rng = np.random.default_rng(seed)

    for wk, sub in qual.groupby("week_key", sort=True):
        ded = _choose_one_per_match(sub, rng)
        if len(ded) < n_legs:
            rows.append((wk, 0.0, 0.0, bankroll))
            continue
        combos = build_combos_for_week(ded, n_legs, max_combos_per_week=max_combos_per_week,
                                        enumerate_threshold=5000, rng=rng)
        if not combos:
            rows.append((wk, 0.0, 0.0, bankroll))
            continue
        mat = materialize_combos(ded, combos)
        kept_idx, kept_rows = select_diverse(combos, mat, max_combos_per_week, diversity_lambda)
        if not kept_rows:
            rows.append((wk, 0.0, 0.0, bankroll))
            continue
        per_cap = per_combo_cap_frac * bankroll
        plans = []
        for combo_legs, row in zip(kept_idx, kept_rows):
            payout = float(row["payout_per_yuan"])
            p = float(row["joint_p"])
            f = kelly_fraction_full(p, payout)
            raw_stake = bankroll * kelly_fraction * f
            if raw_stake <= 0 or payout <= 0:
                continue
            raw_stake = min(raw_stake, per_cap)
            cap_per_ticket = _floor_even(TAX_FREE_PRIZE_CAP / payout)
            if cap_per_ticket < MIN_STAKE_PER_TICKET:
                continue
            if raw_stake <= cap_per_ticket:
                stake = _floor_even(raw_stake)
                if stake < MIN_STAKE_PER_TICKET:
                    continue
                n_t = 1
                spt = stake
            else:
                n_t = max(1, math.ceil(raw_stake / cap_per_ticket))
                spt = cap_per_ticket
            plans.append(dict(spt=spt, n=n_t, total=spt*n_t,
                              payout=payout, all_hit=bool(row["all_hit"])))
        if not plans:
            rows.append((wk, 0.0, 0.0, bankroll))
            continue
        weekly_cap = weekly_stake_cap_frac * bankroll
        total = sum(p["total"] for p in plans)
        if total > weekly_cap and total > 0:
            scale = weekly_cap / total
            for p in plans:
                ns = _floor_even(p["spt"] * scale)
                if ns < MIN_STAKE_PER_TICKET:
                    p["total"] = 0
                else:
                    p["spt"] = ns
                    p["total"] = ns * p["n"]
            plans = [p for p in plans if p["total"] > 0]
            if not plans:
                rows.append((wk, 0.0, 0.0, bankroll))
                continue
        wk_stake = sum(p["total"] for p in plans)
        wk_payout = sum(p["total"] * p["payout"] for p in plans if p["all_hit"])
        wk_pnl_market = wk_payout - wk_stake
        wk_commission = wk_stake * commission_rate
        wk_pnl = wk_pnl_market + wk_commission
        bankroll += wk_pnl
        rows.append((wk, wk_stake, wk_pnl, bankroll))
        if bankroll <= 0:
            break

    df = pd.DataFrame(rows, columns=["week_key", "week_stake", "week_pnl", "bankroll_end"])
    return df


def main():
    print("Loading qual_a...")
    qual_a, _ = build_archetype_a_qual()
    print(f"qual_a rows: {len(qual_a)}")

    configs = [
        ("Default (no commission)", dict(diversity_lambda=0.5, max_combos_per_week=50, commission_rate=0.0)),
        ("Default + 7% commission", dict(diversity_lambda=0.5, max_combos_per_week=50, commission_rate=0.07)),
        ("100 tix + lambda=0.3", dict(diversity_lambda=0.3, max_combos_per_week=100, commission_rate=0.0)),
        ("25 tix + lambda=2.0 (best Sharpe)", dict(diversity_lambda=2.0, max_combos_per_week=25, commission_rate=0.0)),
    ]

    results = {}
    for name, cfg in configs:
        df = simulate_with_stake(qual_a, n_legs=4, kelly_fraction=1/16, **cfg)
        results[name] = df
        m = metrics(df["week_pnl"].values)
        if m:
            print(f"\n{name}:")
            print(f"  final={m['final']:>13,.0f}  CAGR={m['cagr']*100:>6.1f}%  "
                  f"Sharpe={m['sharpe']:>5.2f}  MaxDD={m['max_dd']*100:>6.1f}%  "
                  f"Calmar={m['calmar']:>5.2f}  hit={m['hit_rate']*100:>5.1f}%")

    # Plot equity curves
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 9))
    colors = ["#b04a2f", "#2e6b4a", "#a45a00", "#3a5a8c"]
    for (name, df), color in zip(results.items(), colors):
        bankroll = INITIAL + np.cumsum(df["week_pnl"].values)
        weeks = np.arange(len(bankroll))
        ax1.plot(weeks, bankroll, label=name, color=color, linewidth=1.5)

        # Drawdown
        peak = np.maximum.accumulate(bankroll)
        dd = (bankroll - peak) / peak * 100
        ax2.plot(weeks, dd, label=name, color=color, linewidth=1.2, alpha=0.8)

    ax1.axhline(INITIAL, color="gray", linestyle="--", alpha=0.5, label="Initial 100k")
    ax1.set_xlabel("Weeks (OOS test period ~4 years)")
    ax1.set_ylabel("Bankroll (yuan)")
    ax1.set_title("Equity Curves: N=4, Kelly=1/16, 4 configs", fontsize=14, fontweight="bold")
    ax1.set_yscale("log")
    ax1.legend(loc="upper left", fontsize=9)
    ax1.grid(True, alpha=0.3)

    ax2.set_xlabel("Weeks")
    ax2.set_ylabel("Drawdown %")
    ax2.set_title("Drawdown (peak-to-trough)", fontsize=12)
    ax2.legend(loc="lower left", fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.axhline(0, color="black", linewidth=0.5)

    plt.tight_layout()
    out_png = "/Volumes/Data Drive/workspace/trading/beijing-lot/docs/research/figures/equity_curve_default.png"
    plt.savefig(out_png, dpi=120, bbox_inches="tight")
    print(f"\nSaved equity curve to {out_png}")

    # Save weekly data for HTML
    for name, df in results.items():
        slug = name.replace(" ", "_").replace("(", "").replace(")", "").replace("%", "pct")
        df.to_csv(f"/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/equity_{slug}.csv", index=False)


if __name__ == "__main__":
    main()
