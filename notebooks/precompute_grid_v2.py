"""V2 grid: base cells (N=2,3,4) + mix cells (N_p × N_s × weight).

Cell key examples:
  Base:  "N3_K0.0625_L0.50_M50_C0.000"
  Mix:   "MIX_P4_S2_W0.70_K0.0625_L0.50_M50_C0.000"
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).parent))

from src.dual_sweep.variants import build_archetype_a_qual
from equity_curve_default import simulate_with_stake, INITIAL


def base_key(n, k, lam, m, c):
    return f"N{n}_K{k:.4f}_L{lam:.2f}_M{m}_C{c:.3f}"


def mix_key(np_, ns_, w, k, lam, m, c):
    return f"MIX_P{np_}_S{ns_}_W{w:.2f}_K{k:.4f}_L{lam:.2f}_M{m}_C{c:.3f}"


def metrics_full(weekly_pnl, weekly_stake, initial=INITIAL):
    bankroll = initial + np.cumsum(weekly_pnl)
    bankroll = np.maximum(bankroll, 0.01)
    n_weeks = len(weekly_pnl)
    if n_weeks == 0:
        return None
    cum_roi = (bankroll[-1] - initial) / initial
    yrs = n_weeks / 52.0
    cagr = (bankroll[-1] / initial) ** (1.0 / max(yrs, 1e-6)) - 1.0
    pct = weekly_pnl / initial
    sharpe = (np.mean(pct) * 52) / (np.std(pct, ddof=1) * np.sqrt(52)) if len(pct) > 1 and np.std(pct, ddof=1) > 0 else 0
    seq = np.concatenate([[initial], bankroll])
    rm = np.maximum.accumulate(seq)
    dd = (seq - rm) / rm
    max_dd = float(np.min(dd))
    calmar = cagr / abs(max_dd) if max_dd < 0 else 0
    avg_stake = float(weekly_stake[weekly_stake > 0].mean()) if (weekly_stake > 0).any() else 0
    util = avg_stake / initial * 100
    bsr = bankroll
    if len(bsr) > 50:
        idx = np.linspace(0, len(bsr) - 1, 50).astype(int)
        bsr = bsr[idx]
    return dict(
        n_weeks=n_weeks, final=float(bankroll[-1]), cum_roi=float(cum_roi),
        cagr=float(cagr), sharpe=float(sharpe), max_dd=float(max_dd),
        calmar=float(calmar), hit_rate=float((weekly_pnl > 0).mean()),
        avg_weekly_stake=avg_stake, utilization_pct=util,
        equity_curve=[round(float(x), 0) for x in bsr],
    )


def main():
    print("Loading qual_a (one-time)...")
    qual_a, _ = build_archetype_a_qual()
    print(f"qual_a rows: {len(qual_a)}")

    n_grid = [2, 3, 4]
    kelly_grid = [1/32, 1/16, 1/8, 1/4]
    lambda_grid = [0.0, 0.5, 1.0, 2.0]
    max_grid = [25, 50, 100, 200]
    comm_grid = [0.0, 0.07]

    # Cache base sims: each cell stores weekly pnl + stake series
    base_cache = {}
    cells = {}

    base_total = len(n_grid) * len(kelly_grid) * len(lambda_grid) * len(max_grid) * len(comm_grid)
    print(f"\nPhase 1: base grid ({base_total} cells)")
    i = 0
    for n in n_grid:
        for kf in kelly_grid:
            for lam in lambda_grid:
                for mc in max_grid:
                    for comm in comm_grid:
                        i += 1
                        try:
                            df = simulate_with_stake(
                                qual_a, n_legs=n, kelly_fraction=kf,
                                diversity_lambda=lam, max_combos_per_week=mc,
                                commission_rate=comm,
                            )
                            pnl = df["week_pnl"].values
                            stake = df["week_stake"].values
                            base_cache[(n, kf, lam, mc, comm)] = (
                                df["week_key"].values, pnl, stake
                            )
                            m = metrics_full(pnl, stake)
                            if m is None:
                                continue
                            cells[base_key(n, kf, lam, mc, comm)] = m
                            if i % 25 == 0 or i == base_total:
                                print(f"  [{i}/{base_total}] N{n} K={kf:.4f} done, "
                                      f"CAGR={m['cagr']*100:.1f}%, util={m['utilization_pct']:.1f}%")
                        except Exception as e:
                            print(f"  [{i}/{base_total}] FAILED {n} {kf}: {e}")

    # Phase 2: mix cells (post-processing of cached series, no new sims!)
    pair_grid = [(4, 2), (4, 3), (3, 2), (3, 4)]
    weight_grid = [0.3, 0.5, 0.7]
    mix_total = len(pair_grid) * len(weight_grid) * len(kelly_grid) * len(lambda_grid) * len(max_grid) * len(comm_grid)
    print(f"\nPhase 2: mix grid ({mix_total} cells, post-processing)")
    j = 0
    for (np_, ns_) in pair_grid:
        for w in weight_grid:
            for kf in kelly_grid:
                for lam in lambda_grid:
                    for mc in max_grid:
                        for comm in comm_grid:
                            j += 1
                            kp = (np_, kf, lam, mc, comm)
                            ks = (ns_, kf, lam, mc, comm)
                            if kp not in base_cache or ks not in base_cache:
                                continue
                            wkp, pnlp, stp = base_cache[kp]
                            wks, pnls, sts = base_cache[ks]
                            # Outer-merge by week_key
                            import pandas as pd
                            df_p = pd.DataFrame({"k": wkp, "pp": pnlp, "sp_p": stp})
                            df_s = pd.DataFrame({"k": wks, "ps": pnls, "sp_s": sts})
                            merged = df_p.merge(df_s, on="k", how="outer").fillna(0)
                            pnl_mix = w * merged["pp"].values + (1 - w) * merged["ps"].values
                            stake_mix = w * merged["sp_p"].values + (1 - w) * merged["sp_s"].values
                            m = metrics_full(pnl_mix, stake_mix)
                            if m is None:
                                continue
                            m["n_legs_primary"] = np_
                            m["n_legs_secondary"] = ns_
                            m["weight_primary"] = w
                            cells[mix_key(np_, ns_, w, kf, lam, mc, comm)] = m

    out = Path("/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/backtest_grid.json")
    out.write_text(json.dumps(cells, ensure_ascii=False))
    print(f"\nSaved {len(cells)} cells (base + mix) to {out}")
    print(f"  base cells: {sum(1 for k in cells if k.startswith('N'))}")
    print(f"  mix cells:  {sum(1 for k in cells if k.startswith('MIX'))}")


if __name__ == "__main__":
    main()
