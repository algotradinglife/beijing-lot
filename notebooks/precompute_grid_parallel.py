"""V2 grid with multiprocessing — uses all CPU cores.

Phase 1: parallel base cells (each worker runs one simulate_with_stake call)
Phase 2: in-process mix combination (post-processing, fast)
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).parent))

INITIAL = 100_000.0


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


def run_one_cell(args):
    """Worker fn: returns (config_tuple, week_keys, weekly_pnl, weekly_stake, metrics_dict).

    Also embeds the full ``weekly_pnl`` list inside the metrics dict so the
    grid JSON can be used downstream for arbitrary post-hoc mix combinations
    (3-way, custom weights, etc.).
    """
    n, kf, lam, mc, comm = args
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).parent))
    import json as _json
    from src.dual_sweep.variants import build_archetype_a_qual
    from equity_curve_default import simulate_with_stake
    qual_a, _ = build_archetype_a_qual()
    # League q≥0.65 filter (drops historically -EV leagues)
    lq_path = Path(__file__).resolve().parents[1] / "src" / "phase5a" / "league_quality.json"
    if lq_path.exists():
        lq = _json.loads(lq_path.read_text())
        allowed = {k for k, v in lq.items() if v.get("q", 0) >= 0.65}
        qual_a = qual_a[qual_a["league"].isin(allowed)].reset_index(drop=True)
    df = simulate_with_stake(
        qual_a, n_legs=n, kelly_fraction=kf,
        diversity_lambda=lam, max_combos_per_week=mc,
        commission_rate=comm,
    )
    pnl = df["week_pnl"].values
    stake = df["week_stake"].values
    week_keys = df["week_key"].values
    m = metrics_full(pnl, stake)
    if m is not None:
        m["weekly_pnl"] = [round(float(x), 2) for x in pnl]
        m["weekly_stake"] = [round(float(x), 2) for x in stake]
        m["week_keys"] = [str(k) for k in week_keys]
    return ((n, kf, lam, mc, comm), week_keys.tolist(), pnl.tolist(),
            stake.tolist(), m)


def main():
    n_grid = [2, 3, 4]
    kelly_grid = [1/32, 1/16, 1/8, 1/4]
    lambda_grid = [0.0, 0.5, 1.0, 2.0]
    max_grid = [25, 50, 100, 200]
    comm_grid = [0.0, 0.07]

    # Build base task list
    base_tasks = []
    for n in n_grid:
        for kf in kelly_grid:
            for lam in lambda_grid:
                for mc in max_grid:
                    for comm in comm_grid:
                        base_tasks.append((n, kf, lam, mc, comm))

    base_total = len(base_tasks)
    print(f"Phase 1: parallel base grid ({base_total} cells, 8 cores)")
    t0 = time.time()

    base_cache = {}  # (n, kf, lam, mc, comm) -> (week_keys, pnl, stake, metrics)
    cells = {}
    completed = 0

    with ProcessPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(run_one_cell, task) for task in base_tasks]
        for fut in as_completed(futures):
            try:
                cfg, wk, pnl, stake, m = fut.result()
                base_cache[cfg] = (wk, pnl, stake)
                if m is not None:
                    cells[base_key(*cfg)] = m
                completed += 1
                if completed % 25 == 0 or completed == base_total:
                    elapsed = time.time() - t0
                    eta = elapsed / completed * (base_total - completed)
                    print(f"  [{completed}/{base_total}] elapsed {elapsed:.0f}s, ETA {eta:.0f}s")
            except Exception as e:
                completed += 1
                print(f"  [{completed}/{base_total}] FAILED: {e}")

    print(f"\nPhase 1 done in {time.time() - t0:.0f}s")

    # Phase 2: mix cells (in-process, fast post-processing)
    pair_grid = [(4, 2), (4, 3), (3, 2), (3, 4)]
    weight_grid = [0.3, 0.5, 0.7]
    mix_total = len(pair_grid) * len(weight_grid) * len(kelly_grid) * len(lambda_grid) * len(max_grid) * len(comm_grid)
    print(f"\nPhase 2: mix grid ({mix_total} cells, in-process)")

    import pandas as pd
    t1 = time.time()
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

    print(f"Phase 2 done in {time.time() - t1:.0f}s")

    out = Path("/Volumes/Data Drive/workspace/trading/beijing-lot/data/raw/backtest_grid.json")
    out.write_text(json.dumps(cells, ensure_ascii=False))
    print(f"\nTotal {len(cells)} cells (base + mix) saved to {out}")
    print(f"  base: {sum(1 for k in cells if k.startswith('N'))}")
    print(f"  mix:  {sum(1 for k in cells if k.startswith('MIX'))}")


if __name__ == "__main__":
    main()
