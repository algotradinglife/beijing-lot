"""Generate N=5 backtest cells with league q≥0.65 filter applied.

Output: appends keys `N5Q65_K{kelly:.4f}_L{lam:.2f}_M{mc}_C0.000` into the
existing backtest_grid.json so the explorer / API can read them by an
augmented key. Independent of the unfiltered N∈{2,3,4} cells.
"""
from __future__ import annotations
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from precompute_grid_parallel import metrics_full

GRID = ROOT / "data" / "raw" / "backtest_grid.json"
LQ = ROOT / "src" / "phase5a" / "league_quality.json"


def run_one(args):
    """Worker: simulate N=5 with league q≥0.65 filter."""
    n, kf, lam, mc = args
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(Path(__file__).parent))
    import json as _json
    from src.dual_sweep.variants import build_archetype_a_qual
    from equity_curve_default import simulate_with_stake

    qual, _ = build_archetype_a_qual()
    lq = _json.loads(open(LQ).read())
    allowed = {k for k, v in lq.items() if v.get("q", 0) >= 0.65}
    qual_filtered = qual[qual["league"].isin(allowed)].reset_index(drop=True)
    df = simulate_with_stake(
        qual_filtered, n_legs=n, kelly_fraction=kf,
        diversity_lambda=lam, max_combos_per_week=mc,
        commission_rate=0.0,
    )
    pnl = df["week_pnl"].values
    stake = df["week_stake"].values
    week_keys = df["week_key"].values
    m = metrics_full(pnl, stake)
    if m is not None:
        m["weekly_pnl"] = [round(float(x), 2) for x in pnl]
        m["weekly_stake"] = [round(float(x), 2) for x in stake]
        m["week_keys"] = [str(k) for k in week_keys]
    return ((n, kf, lam, mc), m)


def main():
    cells = json.loads(GRID.read_text())
    print(f"Loaded {len(cells)} existing cells")

    n = 5
    kelly_grid = [1/32, 1/16, 1/8, 1/4]
    lambda_grid = [0.0, 0.5, 1.0, 2.0]
    max_grid = [25, 50, 100, 150, 200]

    tasks = [(n, kf, lam, mc) for kf in kelly_grid
             for lam in lambda_grid for mc in max_grid]
    print(f"Running {len(tasks)} N=5 q-filtered cells on 8 cores…")
    t0 = time.time()
    done = 0
    with ProcessPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(run_one, task) for task in tasks]
        for fut in as_completed(futures):
            try:
                (n, kf, lam, mc), m = fut.result()
                if m is not None:
                    key = f"N{n}Q65_K{kf:.4f}_L{lam:.2f}_M{mc}_C0.000"
                    cells[key] = m
                done += 1
                if done % 10 == 0 or done == len(tasks):
                    print(f"  [{done}/{len(tasks)}] {time.time()-t0:.0f}s")
            except Exception as e:
                done += 1
                print(f"  [{done}/{len(tasks)}] FAILED: {e}")

    GRID.write_text(json.dumps(cells, ensure_ascii=False))
    n_n5q = sum(1 for k in cells if k.startswith("N5Q65"))
    print(f"\nTotal cells: {len(cells)} ({n_n5q} are N=5 q-filtered)")


if __name__ == "__main__":
    main()
