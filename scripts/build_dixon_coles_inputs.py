"""Build the frozen inputs the Dixon-Coles delivery QMD renders from.

Writes two artifacts into the repo-local scratch directory that the QMD reads:

``lam_with_dc.csv``
    One row per admitted fixture carrying the recovered ``(lambda_home,
    lambda_away)`` plus the independent-Poisson and Dixon-Coles draw
    probabilities under that fixture's frozen ``rho``.

``rho_final.csv``
    One row per issue carrying the cutoff-selected ``rho``, whether it was
    selected inside its own prior window, and — for issues whose prior window
    was too short — the explicit backfill provenance.

Everything the learning side needs comes from :mod:`src.dixon_coles_rho`; this
script only wires sources to that module. It never selects ``rho`` itself.

Usage::

    ./.venv/bin/python scripts/build_dixon_coles_inputs.py [--output DIR]

The admission source is the sealed ``handicap-line-gap-v1`` audit, whose
``inputs.json.gz`` holds one row per fixture with a full net-goal distribution.
The ``rho`` selection replays the same walk-forward cutoffs the delivery used.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.stats import poisson

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.dixon_coles_rho import (  # noqa: E402
    backfill_inadmissible_rho,
    dixon_coles_history,
    freeze_rho_by_band,
    _draw_probability,
    _independent_draw_probability,
)
from src.temporal_learning import AvailabilityPolicy, Cutoff  # noqa: E402

DEFAULT_DATA_ROOT = Path("/run/media/drwho1985/Sandisk/data/beijing-lot")
AUDIT_RELATIVE = "audits/handicap-line-gap-v1"
MAX_GOALS = 25
BACKFILL_PROVENANCE = (
    "CARRY_BACK_STABLE_CONSTANT: rho is a single low-score dependence parameter; "
    "issues whose complete-prior-years window is too short reuse the earliest "
    "in-window selection instead of falling back to an independent grid"
)


def _net_goal_distribution(entries) -> tuple[np.ndarray, np.ndarray]:
    """Return sorted net-goal values and their probabilities."""
    pairs = sorted((int(item["net"]), float(item["probability"])) for item in entries)
    nets = np.array([net for net, _ in pairs], dtype=int)
    masses = np.array([mass for _, mass in pairs], dtype=float)
    total = masses.sum()
    if not np.isfinite(total) or total <= 0:
        raise ValueError("net-goal distribution has no usable mass")
    return nets, masses / total


def recover_lambdas(entries, goals: np.ndarray, net_grid: np.ndarray):
    """Recover ``(lambda_home, lambda_away)`` from a net-goal distribution.

    The distribution is independent of the handicap line, so any admitted row
    for a fixture recovers the same rates. Returns the pair and the maximum
    absolute residual of the fit.
    """
    nets, observed = _net_goal_distribution(entries)

    def residual(params: np.ndarray) -> np.ndarray:
        home, away = params
        if home <= 0 or away <= 0:
            return np.full(nets.shape, 1e6)
        grid = np.outer(poisson.pmf(goals, home), poisson.pmf(goals, away))
        grid = grid / grid.sum()
        return np.array([grid[net_grid == net].sum() for net in nets]) - observed

    fit = least_squares(residual, [1.3, 1.1], method="lm")
    return float(fit.x[0]), float(fit.x[1]), float(np.abs(fit.fun).max())


def load_fixtures(inputs_path: Path) -> pd.DataFrame:
    rows = []
    with gzip.open(inputs_path, "rt") as handle:
        for line in handle:
            rows.extend(json.loads(line)["rows"])
    if not rows:
        raise ValueError(f"{inputs_path} contained no fixture rows")
    frame = pd.DataFrame(rows)
    frame["issue"] = frame["issue"].astype(str)
    frame["provider_id"] = frame["provider_id"].astype(str)
    return frame


def load_labels(data_root: Path) -> pd.DataFrame:
    """Read settled directions; these are labels, never model inputs."""
    path = data_root / AUDIT_RELATIVE / "fixtures.csv"
    frame = pd.read_csv(path, dtype={"issue": str, "provider_id": str})
    return frame[["issue", "slot", "provider_id", "handicap", "actual_direction"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root", type=Path, default=DEFAULT_DATA_ROOT,
        help="sealed audit root holding handicap-line-gap-v1",
    )
    parser.add_argument(
        "--output", type=Path, default=REPOSITORY_ROOT / ".tmpwork",
        help="directory that receives the two derived artifacts",
    )
    args = parser.parse_args()

    inputs_path = args.data_root / AUDIT_RELATIVE / "inputs.json.gz"
    if not inputs_path.exists():
        raise SystemExit(f"missing sealed audit input: {inputs_path}")

    goals = np.arange(0, MAX_GOALS + 1)
    net_grid = goals[:, None] - goals[None, :]

    fixtures = load_fixtures(inputs_path)
    print(f"recovering rates for {len(fixtures)} fixtures ...")
    rates = [
        recover_lambdas(entries, goals, net_grid)
        for entries in fixtures["distribution"]
    ]
    fixtures["lambda_home"] = [r[0] for r in rates]
    fixtures["lambda_away"] = [r[1] for r in rates]
    fixtures["fit_err"] = [r[2] for r in rates]
    print(
        "fit residual: median {:.2e} p99 {:.2e} max {:.2e}".format(
            fixtures["fit_err"].median(),
            fixtures["fit_err"].quantile(0.99),
            fixtures["fit_err"].max(),
        )
    )

    # rho is historically learned: one walk-forward selection per issue, driven
    # by the shared cutoff contract rather than by any target-issue outcome.
    labelled = load_labels(args.data_root)
    joined = fixtures.merge(
        labelled[["issue", "slot", "provider_id", "actual_direction"]],
        on=["issue", "slot", "provider_id"],
        how="inner",
    )
    joined["is_draw"] = joined["actual_direction"].eq("D").astype(int)
    joined["decision_ts"] = pd.to_datetime(joined["issue"], format="%y%m%d", utc=True)
    history = dixon_coles_history(
        joined[["issue", "decision_ts", "lambda_home", "lambda_away", "is_draw"]]
    )

    issues = sorted(joined["issue"].unique())
    stamps = pd.to_datetime(issues, format="%y%m%d", utc=True)
    cutoffs = {
        issue: Cutoff.decision_epoch(issue, stamps[index])
        for index, issue in enumerate(issues)
    }
    policy = AvailabilityPolicy.historical_proxy(
        "handicap-line-gap-v1 net-goal distributions"
    )
    frozen = freeze_rho_by_band(
        history,
        cutoffs=cutoffs,
        repository_root=REPOSITORY_ROOT,
        source_hashes={"handicap-line-gap-v1/inputs.json.gz": "sealed-audit"},
        availability_policy=policy,
    )
    print(
        f"selected rho in-window for {int(frozen['admissible'].sum())} of "
        f"{len(frozen)} issues"
    )
    rho_table = backfill_inadmissible_rho(frozen, provenance=BACKFILL_PROVENANCE)
    rho_table["year"] = rho_table["issue_code"].str[:2].astype(int) + 2000

    rho_by_issue = dict(zip(rho_table["issue_code"], rho_table["rho"]))
    fixtures["rho"] = fixtures["issue"].map(rho_by_issue)
    if fixtures["rho"].isna().any():
        missing = sorted(fixtures.loc[fixtures["rho"].isna(), "issue"].unique())
        raise SystemExit(f"no frozen rho for issues: {missing[:10]}")

    home = fixtures["lambda_home"].to_numpy(float)
    away = fixtures["lambda_away"].to_numpy(float)
    rho = fixtures["rho"].to_numpy(float)
    fixtures["q_D_independent"] = _independent_draw_probability(home, away, MAX_GOALS)
    fixtures["q_D_dc"] = _draw_probability(home, away, rho, MAX_GOALS)
    fixtures["q_D"] = fixtures["q_D_dc"]
    fixtures["year"] = fixtures["issue"].str[:2].astype(int) + 2000

    args.output.mkdir(parents=True, exist_ok=True)
    lam_path = args.output / "lam_with_dc.csv"
    rho_path = args.output / "rho_final.csv"
    fixtures.to_csv(lam_path, index=False)
    rho_table.to_csv(rho_path, index=False)
    print(f"wrote {lam_path} ({len(fixtures)} rows) and {rho_path} ({len(rho_table)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
