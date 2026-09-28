"""Rebase the handicap-line-gap audit onto Dixon-Coles corrected score grids.

The sealed audit ``audits/handicap-line-gap-v1`` froze per-fixture net-goal
distributions produced by the independent-Poisson projection.  This script
re-derives the same grid under Dixon-Coles low-score dependence, then re-runs
the *unchanged* ``handicap_line_gap`` semantics so every downstream quantity
(``optimal_line``, ``delta``, ``q_W``/``q_D``/``q_L``, ``signal``) reflects the
corrected probability base.

Chronology: ``rho`` is read from the frozen per-issue table produced by the
cutoff-driven selector in ``src/dixon_coles_rho.py``.  No label at or after an
issue's cutoff participates in that selection, and this script never re-selects
rho -- it only applies the frozen value.

Inputs
    --data-root   sealed audit root (default: Sandisk data root)
    --rho         frozen per-issue rho table from build_dixon_coles_inputs.py
    --output      directory for the rebased artifacts

Outputs
    ``handicap_line_gap_dc.csv``  one row per fixture: DC-corrected
        ``optimal_line``/``delta``/``q_*``/``signal`` plus the frozen ``rho``
        and its provenance flags.
    ``rebase_receipt.json``       input hashes, counts, and the rho ledger.

The independent-Poisson baseline is carried alongside (``q_*_base``,
``delta_base``) so downstream work can attribute any change to the correction
rather than to the rebase itself.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize, stats

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = Path("/run/media/drwho1985/Sandisk/data/beijing-lot")
AUDIT_RELATIVE = "audits/handicap-line-gap-v1"
MAX_GOALS = 25
TOLERANCE = 1e-12


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dc_tau(home: int, away: int, lambda_home: float, lambda_away: float, rho: float) -> float:
    """Dixon-Coles low-score multiplier for one scoreline."""
    if home == 0 and away == 0:
        return 1.0 - lambda_home * lambda_away * rho
    if home == 0 and away == 1:
        return 1.0 + lambda_home * rho
    if home == 1 and away == 0:
        return 1.0 + lambda_away * rho
    if home == 1 and away == 1:
        return 1.0 - rho
    return 1.0


def score_grid(lambda_home: float, lambda_away: float, rho: float, goals: np.ndarray) -> np.ndarray:
    """Return the normalized DC score grid ``[home, away]``."""
    if not (np.isfinite(lambda_home) and lambda_home > 0):
        raise ValueError(f"lambda_home must be finite and positive, got {lambda_home!r}")
    if not (np.isfinite(lambda_away) and lambda_away > 0):
        raise ValueError(f"lambda_away must be finite and positive, got {lambda_away!r}")
    if not (np.isfinite(rho) and -0.5 <= rho <= 0.5):
        raise ValueError(f"rho must lie in [-0.5, 0.5], got {rho!r}")
    grid = np.outer(stats.poisson.pmf(goals, lambda_home), stats.poisson.pmf(goals, lambda_away))
    if rho != 0.0:
        for home in (0, 1):
            for away in (0, 1):
                grid[home, away] *= dc_tau(home, away, lambda_home, lambda_away, rho)
    total = grid.sum()
    if not np.isfinite(total) or total <= 0:
        raise ValueError("score grid has no usable mass")
    return grid / total


def net_distribution(grid: np.ndarray, net_grid: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Collapse a score grid onto sorted net-goal values."""
    nets = np.unique(net_grid)
    masses = np.array([grid[net_grid == net].sum() for net in nets], dtype=float)
    masses = masses / masses.sum()
    return nets, masses


def recover_lambdas(nets: np.ndarray, observed: np.ndarray, goals: np.ndarray, net_grid: np.ndarray):
    """Recover ``(lambda_home, lambda_away)`` from a net-goal distribution."""

    def residual(params: np.ndarray) -> np.ndarray:
        home, away = params
        if home <= 0 or away <= 0:
            return np.full(nets.shape, 1e6)
        grid = np.outer(stats.poisson.pmf(goals, home), stats.poisson.pmf(goals, away))
        grid = grid / grid.sum()
        return np.array([grid[net_grid == net].sum() for net in nets]) - observed

    fit = optimize.least_squares(residual, [1.3, 1.1], method="lm")
    return float(fit.x[0]), float(fit.x[1]), float(np.abs(fit.fun).max())


def handicap_line_gap(nets: np.ndarray, masses: np.ndarray, handicap: int, tolerance: float):
    """Mirror of ``r/handicap_line_gap.R`` for an already-sorted distribution."""
    lines = np.arange(-nets.max() - 1, -nets.min() + 2, dtype=float)
    cdf = np.concatenate([[0.0], np.cumsum(masses)])
    # findInterval(x, vec) counts vec elements <= x; index into cdf is that + 1.
    idx_w = np.searchsorted(nets, -lines, side="right")
    w = masses.sum() - cdf[idx_w]
    idx_l = np.searchsorted(nets, -lines - 0.25, side="right")
    l = cdf[idx_l]
    objective = np.abs(w - l)
    finite = np.isfinite(objective)
    if not finite.any():
        raise ValueError("no finite candidate line")
    best = lines[finite & (objective <= objective[finite].min() + tolerance)]
    order = np.lexsort((best, np.abs(best)))
    hstar = best[order][0]
    qw = masses[nets + handicap > 0].sum()
    ql = masses[nets + handicap < 0].sum()
    qd = masses[nets + handicap == 0].sum()
    if len(best) > 1:
        signal = "AMBIGUOUS"
    elif handicap > hstar:
        signal = "W"
    elif handicap < hstar:
        signal = "L"
    else:
        signal = "NONE"
    return {
        "optimal_line": float(hstar),
        "optimal_min": float(best.min()),
        "optimal_max": float(best.max()),
        "ties": int(len(best)),
        "delta": float(handicap - hstar),
        "imbalance": float(objective[finite].min()),
        "q_W": float(qw),
        "q_D": float(qd),
        "q_L": float(ql),
        "signal": signal,
    }


def load_rows(inputs_path: Path) -> list[dict]:
    rows: list[dict] = []
    with gzip.open(inputs_path, "rt") as handle:
        for line in handle:
            rows.extend(json.loads(line)["rows"])
    if not rows:
        raise ValueError(f"{inputs_path} contained no fixture rows")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--rho", type=Path, default=REPOSITORY_ROOT / ".tmpwork" / "rho_final.csv")
    parser.add_argument("--output", type=Path, default=REPOSITORY_ROOT / ".tmpwork")
    args = parser.parse_args()

    audit_root = args.data_root / AUDIT_RELATIVE
    inputs_path = audit_root / "inputs.json.gz"
    if not inputs_path.exists():
        raise SystemExit(f"missing sealed audit input: {inputs_path}")
    if not args.rho.exists():
        raise SystemExit(f"missing frozen rho table: {args.rho}")

    args.output.mkdir(parents=True, exist_ok=True)

    rho_table = pd.read_csv(args.rho, dtype={"issue_code": str})
    if rho_table.issue_code.duplicated().any():
        raise SystemExit("rho table has duplicate issue codes")
    rho_by_issue = dict(zip(rho_table.issue_code, rho_table.rho))
    backfilled = dict(zip(rho_table.issue_code, rho_table.rho_backfilled))

    goals = np.arange(0, MAX_GOALS + 1)
    net_grid = goals[:, None] - goals[None, :]

    rows = load_rows(inputs_path)
    print(f"rebasing {len(rows)} fixtures onto Dixon-Coles grids ...")

    records = []
    missing_rho: set[str] = set()
    residuals = []
    for i, row in enumerate(rows):
        issue = str(row["issue"])
        handicap = int(row["handicap"])
        if issue not in rho_by_issue:
            missing_rho.add(issue)
            continue
        rho = float(rho_by_issue[issue])

        entries = row["distribution"]
        nets = np.array(sorted(int(e["net"]) for e in entries))
        masses = np.array([float(e["probability"]) for e in sorted(entries, key=lambda e: int(e["net"]))])
        masses = masses / masses.sum()

        lambda_home, lambda_away, residual = recover_lambdas(nets, masses, goals, net_grid)
        residuals.append(residual)

        base = handicap_line_gap(nets, masses, handicap, TOLERANCE)
        grid = score_grid(lambda_home, lambda_away, rho, goals)
        dc_nets, dc_masses = net_distribution(grid, net_grid)
        corrected = handicap_line_gap(dc_nets, dc_masses, handicap, TOLERANCE)

        records.append(
            {
                "issue": issue,
                "slot": int(row["slot"]),
                "provider_id": str(row["provider_id"]),
                "handicap": handicap,
                "rho": rho,
                "rho_backfilled": bool(backfilled.get(issue, False)),
                "lambda_home": lambda_home,
                "lambda_away": lambda_away,
                "fit_residual": residual,
                **corrected,
                **{f"{k}_base": v for k, v in base.items()},
            }
        )
        if (i + 1) % 10000 == 0:
            print(f"  {i + 1}/{len(rows)}")

    if missing_rho:
        raise SystemExit(
            f"{len(missing_rho)} issues absent from the rho table, e.g. {sorted(missing_rho)[:5]}"
        )

    frame = pd.DataFrame(records)
    out_csv = args.output / "handicap_line_gap_dc.csv"
    frame.to_csv(out_csv, index=False)

    residual_array = np.array(residuals)
    receipt = {
        "status": "COMPUTED_PENDING_REVIEW",
        "method": "EXISTING_OU_FIXED_MEAN_LEAST_SQUARES_1X2_DIXON_COLES",
        "inputs": {
            "audit_inputs": str(inputs_path),
            "audit_inputs_sha256": sha256(inputs_path),
            "rho_table": str(args.rho),
            "rho_table_sha256": sha256(args.rho),
        },
        "fixtures": int(len(frame)),
        "issues": int(frame.issue.nunique()),
        "rho_ledger": {
            "values": sorted(frame.rho.unique().tolist()),
            "in_window": int((~frame.rho_backfilled).sum()),
            "backfilled": int(frame.rho_backfilled.sum()),
        },
        "lambda_fit_residual": {
            "median": float(np.median(residual_array)),
            "p99": float(np.percentile(residual_array, 99)),
            "max": float(residual_array.max()),
        },
        "output": str(out_csv),
        "output_sha256": sha256(out_csv),
    }
    (args.output / "rebase_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt["lambda_fit_residual"], indent=2))
    print(f"wrote {out_csv} ({len(frame)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
