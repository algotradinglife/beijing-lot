"""Append max_combos=150 cells to the existing backtest_grid.json.

Runs the same 3 × 4 × 4 base grid (N × Kelly × λ) as precompute_grid_parallel
but only at max=150, commission=0 — keeping the new cell count low so the
job finishes in seconds. Skips cells already present.
"""
from __future__ import annotations
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).parent))

from precompute_grid_parallel import base_key, metrics_full, run_one_cell

GRID_PATH = Path(__file__).resolve().parents[1] / "data" / "raw" / "backtest_grid.json"
NEW_MAX = int(__import__("sys").argv[1]) if len(__import__("sys").argv) > 1 else 150
NEW_COMM = 0.0
N_GRID = [2, 3, 4]
KELLY_GRID = [1/32, 1/16, 1/8, 1/4]
LAMBDA_GRID = [0.0, 0.5, 1.0, 2.0]


def main():
    cells = json.loads(GRID_PATH.read_text())
    print(f"Loaded {len(cells)} existing cells")

    tasks = []
    for n in N_GRID:
        for kf in KELLY_GRID:
            for lam in LAMBDA_GRID:
                key = base_key(n, kf, lam, NEW_MAX, NEW_COMM)
                if key in cells:
                    continue
                tasks.append((n, kf, lam, NEW_MAX, NEW_COMM))
    print(f"Running {len(tasks)} new cells at max={NEW_MAX} c={NEW_COMM} on 8 cores…")
    if not tasks:
        print("Nothing to do — already cached.")
        return

    t0 = time.time()
    done = 0
    with ProcessPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(run_one_cell, task) for task in tasks]
        for fut in as_completed(futures):
            try:
                cfg, wk, pnl, stake, m = fut.result()
                if m is not None:
                    cells[base_key(*cfg)] = m
                done += 1
                if done % 8 == 0 or done == len(tasks):
                    print(f"  [{done}/{len(tasks)}] {time.time()-t0:.0f}s")
            except Exception as e:
                done += 1
                print(f"  [{done}/{len(tasks)}] FAILED: {e}")

    GRID_PATH.write_text(json.dumps(cells, ensure_ascii=False))
    print(f"\nTotal {len(cells)} cells now in {GRID_PATH} (added max={NEW_MAX})")


if __name__ == "__main__":
    main()
