"""Compare presets across weekly_stake_cap_frac values."""
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).parent))

from equity_curve_default import simulate_with_stake
from src.dual_sweep.variants import build_archetype_a_qual
import numpy as np

INITIAL = 100_000.0


def run_one(args):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).parent))
    from equity_curve_default import simulate_with_stake
    from src.dual_sweep.variants import build_archetype_a_qual
    cap, n, k, lam, mc = args
    qual, _ = build_archetype_a_qual()
    res = simulate_with_stake(qual, n_legs=n, kelly_fraction=k,
                              diversity_lambda=lam, max_combos_per_week=mc,
                              commission_rate=0.0, weekly_stake_cap_frac=cap)
    return (cap, n, k, lam, mc), res["week_pnl"].values.tolist(), res["week_stake"].values.tolist()


def metrics(pnl, stake):
    pnl = np.array(pnl); stake = np.array(stake)
    bk = INITIAL + np.cumsum(pnl); bk = np.maximum(bk, 0.01); n = len(pnl)
    cagr = (bk[-1]/INITIAL)**(52/max(n,1)) - 1
    pct = pnl/INITIAL
    sh = (np.mean(pct)*52)/(np.std(pct,ddof=1)*np.sqrt(52)) if np.std(pct,ddof=1)>0 else 0
    seq = np.concatenate([[INITIAL], bk]); rm = np.maximum.accumulate(seq); dd=(seq-rm)/rm; mdd=float(np.min(dd))
    avg_st = float(stake[stake>0].mean()) if (stake>0).any() else 0
    avg_bk = float(np.mean(bk))
    return dict(cagr=cagr, sharpe=sh, max_dd=mdd, calmar=cagr/abs(mdd) if mdd<0 else 0,
                final=float(bk[-1]), util=avg_st/INITIAL*100, util_curr=avg_st/avg_bk*100)


def main():
    presets = [
        ((4, 0.03125, 0.0, 200), "稳健 K=1/32"),
        ((4, 0.0625,  0.5, 200), "Calmar王 N=4 K=1/16"),
        ((4, 0.125,   0.5, 200), "Sharpe 优先 N=4 K=1/8"),
        ((4, 0.25,    0.5, 200), "激进 N=4 K=¼"),
        ((3, 0.125,   0.0, 200), "纯 N=3 K=1/8"),
    ]
    tasks = []
    for cap in [0.10, 0.15, 0.25, 0.50]:
        for cfg, _ in presets:
            n, k, lam, mc = cfg
            tasks.append((cap, n, k, lam, mc))

    print(f"Running {len(tasks)} configs in parallel...\n")
    with ProcessPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(run_one, tasks))

    label_map = {cfg: lab for cfg, lab in presets}
    print(f"{'cap':>5} {'preset':<26} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'Calmar':>7} {'final万':>9} {'util_init%':>11} {'util_curr%':>11}")
    print("-"*100)
    for cap_group in [0.10, 0.15, 0.25, 0.50]:
        for cfg, lab in presets:
            n, k, lam, mc = cfg
            for (c, n_, k_, lm_, mc_), pnl, stake in results:
                if c == cap_group and (n_, k_, lm_, mc_) == cfg:
                    m = metrics(pnl, stake)
                    print(f"{c:>5.2f} {lab:<26} {m['cagr']*100:>+6.1f}% {m['sharpe']:>7.2f} {m['max_dd']*100:>+6.1f}% "
                          f"{m['calmar']:>7.2f} {m['final']/1e4:>8.1f} {m['util']:>10.1f}% {m['util_curr']:>10.1f}%")
                    break
        print()


if __name__ == "__main__":
    main()
