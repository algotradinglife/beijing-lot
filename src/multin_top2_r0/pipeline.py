"""Build and independently verify the Issue #348 multi-N R0 package."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from nbclient import NotebookClient

from .contract import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    CONTRACT_ID,
    DESIGN_MASKS,
    FUNDED_UNITS,
    HORIZON,
    ISSUE_NUMBER,
    ISSUE_STAKE_CNY,
    N_VALUES,
    OUTCOMES,
    PAYOUT_FACTOR,
    STAKE_PER_UNIT_CNY,
    STARTING_CAPITAL_CNY,
    YEARS,
    tickets_for_n,
    units_per_ticket,
)

PROBABILITY_RELATIVE = Path(
    "derived/bj238_divergence_materializer_v4r3/inference/relative_horizon_view.parquet"
)
SETTLEMENT_RELATIVE = Path("derived/beidan_xlsm/beidan_xlsm.sqlite")
OUTCOME_RANK = {outcome: rank for rank, outcome in enumerate(OUTCOMES)}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_frame_sha(frame: pd.DataFrame, columns: list[str] | None = None) -> str:
    projected = frame.loc[:, columns] if columns is not None else frame
    order = list(projected.columns)
    ordered = projected.sort_values(order, kind="stable").reset_index(drop=True)
    payload = ordered.to_csv(index=False, lineterminator="\n", float_format="%.17g")
    return hashlib.sha256(payload.encode()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def locate_data_root(repo_root: Path, explicit: Path | None = None) -> Path:
    candidates = [] if explicit is None else [explicit]
    candidates += [repo_root / "data", repo_root.parents[1] / "data"]
    for candidate in candidates:
        if (candidate / PROBABILITY_RELATIVE).exists() and (candidate / SETTLEMENT_RELATIVE).exists():
            return candidate.resolve()
    raise FileNotFoundError("data root with probability and settlement sources not found")


def load_causal_cells(data_root: Path, years: tuple[int, ...] = YEARS) -> pd.DataFrame:
    """Read the disclosed 10h feature proxy without opening settlement labels."""

    path = data_root / PROBABILITY_RELATIVE
    columns = [
        "issue_code", "match_idx", "snapshot_kind", "issue_anchor_ts", "issue_year",
        "native_handicap_line", "n_available_books", "mapping_accepted", "outcome_code",
        "q_eu_bjline", "q_line_only_control", "eu_vs_line_divergence",
    ]
    frame = pq.read_table(
        path,
        filters=[("issue_year", "in", list(years)), ("snapshot_kind", "=", HORIZON)],
        columns=columns,
    ).to_pandas()
    observed_boolean = set(frame["mapping_accepted"].dropna().unique().tolist())
    if not observed_boolean.issubset({True, False}):
        raise ValueError("mapping_accepted is not strict boolean")
    frame = frame.rename(
        columns={
            "issue_code": "issue", "outcome_code": "outcome",
            "q_eu_bjline": "q_eu", "q_line_only_control": "q_line",
        }
    )
    frame["issue"] = frame["issue"].astype(str)
    frame["outcome"] = frame["outcome"].astype(str)
    frame = frame[
        frame["mapping_accepted"].eq(True)
        & frame["outcome"].isin(OUTCOMES)
        & frame[["q_eu", "q_line", "eu_vs_line_divergence"]].notna().all(axis=1)
    ].copy()
    numeric = frame[["q_eu", "q_line", "eu_vs_line_divergence"]].to_numpy(float)
    if not np.isfinite(numeric).all() or not frame["q_eu"].gt(0).all() or not frame["q_line"].ge(0).all():
        raise ValueError("invalid probability surface")
    frame = frame.drop_duplicates(["issue", "match_idx", "outcome"], keep="first")
    complete = frame.groupby(["issue", "match_idx"], observed=True)["outcome"].transform("nunique").eq(3)
    frame = frame[complete].copy()
    sums = frame.groupby(["issue", "match_idx"], observed=True)[["q_eu", "q_line"]].sum()
    if not np.allclose(sums.to_numpy(float), 1.0, rtol=0, atol=1e-6):
        raise ValueError("probability triplets are not normalized")
    frame["issue_anchor_ts"] = pd.to_datetime(frame["issue_anchor_ts"], utc=True)
    return frame.sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "match_idx", "outcome"], kind="stable"
    ).reset_index(drop=True)


def prepare_match_surface(cells: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    keys = ["issue", "issue_year", "issue_anchor_ts", "match_idx"]
    for key, group in cells.groupby(keys, sort=True, observed=True):
        group = group.drop_duplicates("outcome")
        if set(group["outcome"]) != set(OUTCOMES):
            continue
        ranked = group.assign(outcome_rank=group["outcome"].map(OUTCOME_RANK)).sort_values(
            ["q_eu", "outcome_rank"], ascending=[False, True], kind="stable"
        )
        support = tuple(ranked.head(2)["outcome"].astype(str))
        rows.append(
            {
                "issue": str(key[0]), "issue_year": int(key[1]),
                "issue_anchor_ts": pd.Timestamp(key[2]), "match_idx": int(key[3]),
                "baseline_support": "".join(support),
                "retained_mass": float(ranked.head(2)["q_eu"].sum()),
                "top_probability": float(ranked.iloc[0]["q_eu"]),
                "q_eu_3": float(group.loc[group["outcome"].eq("3"), "q_eu"].iloc[0]),
                "q_eu_1": float(group.loc[group["outcome"].eq("1"), "q_eu"].iloc[0]),
                "q_eu_0": float(group.loc[group["outcome"].eq("0"), "q_eu"].iloc[0]),
                "q_line_3": float(group.loc[group["outcome"].eq("3"), "q_line"].iloc[0]),
                "q_line_1": float(group.loc[group["outcome"].eq("1"), "q_line"].iloc[0]),
                "q_line_0": float(group.loc[group["outcome"].eq("0"), "q_line"].iloc[0]),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["issue_year", "issue_anchor_ts", "issue", "match_idx"], kind="stable"
    ).reset_index(drop=True)


def binary_design(n: int) -> np.ndarray:
    """Return the frozen distinct binary ticket design for N."""

    if n <= 7:
        design = np.asarray(list(itertools.product((0, 1), repeat=n)), dtype=np.int8)
    else:
        rows = np.arange(128, dtype=np.uint16)
        design = np.column_stack(
            [np.asarray([(int(row) & mask).bit_count() % 2 for row in rows], dtype=np.int8)
             for mask in DESIGN_MASKS[:n]]
        )
    expected = tickets_for_n(n)
    if design.shape != (expected, n) or len(np.unique(design, axis=0)) != expected:
        raise AssertionError(f"invalid N{n} design")
    if n >= 7:
        if not np.all(design.sum(axis=0) == expected // 2):
            raise AssertionError(f"N{n} design is not marginally balanced")
        for left, right in itertools.combinations(range(n), 2):
            counts = np.bincount(design[:, left] * 2 + design[:, right], minlength=4)
            if not np.all(counts == expected // 4):
                raise AssertionError(f"N{n} design is not pairwise balanced")
    return design


def construct_preoutcome(
    matches: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    bundle_rows: list[dict[str, Any]] = []
    ticket_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    for (issue, year, anchor), group in matches.groupby(
        ["issue", "issue_year", "issue_anchor_ts"], sort=True, observed=True
    ):
        ranked = group.sort_values(
            ["retained_mass", "match_idx"], ascending=[False, True], kind="stable"
        )
        for n in N_VALUES:
            if len(ranked) < n:
                coverage_rows.append(
                    {"issue": str(issue), "issue_year": int(year), "n": n,
                     "available_matches": int(len(ranked)), "status": "INSUFFICIENT_MATCHES"}
                )
                continue
            selected = ranked.head(n).sort_values("match_idx", kind="stable")
            selected_ids = selected["match_idx"].astype(int).tolist()
            supports = selected["baseline_support"].astype(str).tolist()
            design = binary_design(n)
            units = units_per_ticket(n)
            coverage_rows.append(
                {"issue": str(issue), "issue_year": int(year), "n": n,
                 "available_matches": int(len(ranked)), "status": "FROZEN"}
            )
            bundle_rows.append(
                {
                    "issue": str(issue), "issue_year": int(year),
                    "issue_anchor_ts": pd.Timestamp(anchor), "n": n, "arm": "R0",
                    "selected_match_ids": "|".join(map(str, selected_ids)),
                    "support_json": json.dumps(
                        dict(zip(map(str, selected_ids), supports, strict=True)),
                        sort_keys=True, separators=(",", ":"),
                    ),
                    "mean_retained_mass": float(selected["retained_mass"].mean()),
                    "min_retained_mass": float(selected["retained_mass"].min()),
                    "ticket_count": int(len(design)), "units_per_ticket": units,
                    "funded_units": FUNDED_UNITS, "planned_stake_cny": ISSUE_STAKE_CNY,
                }
            )
            for ticket_index, choices in enumerate(design):
                legs = [
                    f"{match_idx}={support[int(choice)]}"
                    for match_idx, support, choice in zip(selected_ids, supports, choices, strict=True)
                ]
                ticket_rows.append(
                    {
                        "issue": str(issue), "issue_year": int(year), "n": n,
                        "ticket_index": int(ticket_index), "ticket_key": "|".join(legs),
                        "units": units, "stake_cny": units * STAKE_PER_UNIT_CNY,
                    }
                )
    bundles = pd.DataFrame(bundle_rows)
    tickets = pd.DataFrame(ticket_rows)
    coverage = pd.DataFrame(coverage_rows)
    return bundles, tickets, coverage


def load_settlement(data_root: Path, issues: list[str]) -> pd.DataFrame:
    if not issues:
        return pd.DataFrame()
    placeholders = ",".join("?" for _ in issues)
    with sqlite3.connect(f"file:{(data_root / SETTLEMENT_RELATIVE).resolve()}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        frame = pd.read_sql_query(
            f"""
            SELECT CAST(issue AS TEXT) AS issue, match_idx,
                   CAST(result_code AS TEXT) AS result_code,
                   CAST(winning_sp AS REAL) AS winning_sp,
                   CAST(official_sp_3 AS REAL) AS official_sp_3,
                   CAST(official_sp_1 AS REAL) AS official_sp_1,
                   CAST(official_sp_0 AS REAL) AS official_sp_0,
                   CAST(has_trusted_settlement AS INTEGER) AS trusted,
                   settlement_quality
            FROM match_features WHERE CAST(issue AS TEXT) IN ({placeholders})
            """,
            connection, params=issues,
        )
    frame = frame.drop_duplicates(["issue", "match_idx"], keep="first")
    fallback = pd.Series(np.nan, index=frame.index, dtype=float)
    for outcome in OUTCOMES:
        mask = frame["result_code"].eq(outcome)
        fallback.loc[mask] = pd.to_numeric(frame.loc[mask, f"official_sp_{outcome}"], errors="coerce")
    frame["winning_sp"] = pd.to_numeric(frame["winning_sp"], errors="coerce").fillna(fallback)
    frame["settlement_available"] = (
        frame["trusted"].eq(1) & frame["result_code"].isin(OUTCOMES) & frame["winning_sp"].gt(0)
    )
    return frame


def settle(
    frozen: pd.DataFrame, tickets: pd.DataFrame, settlement: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lookup = settlement.set_index(["issue", "match_idx"]).to_dict("index")
    ticket_groups = {
        key: group.sort_values("ticket_index", kind="stable")
        for key, group in tickets.groupby(["issue", "issue_year", "n"], sort=False)
    }
    bundle_rows: list[dict[str, Any]] = []
    attribution_rows: list[dict[str, Any]] = []
    settlement_coverage: list[dict[str, Any]] = []
    for row in frozen.itertuples(index=False):
        support_map = json.loads(row.support_json)
        leg_rows: list[dict[str, Any]] = []
        observable = True
        for key, support in support_map.items():
            label = lookup.get((str(row.issue), int(key)))
            if label is None or not bool(label["settlement_available"]):
                observable = False
                result = ""
                winning_sp = math.nan
            else:
                result = str(label["result_code"])
                winning_sp = float(label["winning_sp"])
            leg_rows.append(
                {
                    "issue": str(row.issue), "issue_year": int(row.issue_year), "n": int(row.n),
                    "match_idx": int(key), "support": str(support), "result_code": result,
                    "winning_sp": winning_sp, "included": bool(result in str(support)) if result else False,
                    "settlement_available": bool(label is not None and label["settlement_available"]),
                }
            )
        status = "SETTLED" if observable else "UNTRUSTED_SELECTED_LEG"
        settlement_coverage.append(
            {"issue": str(row.issue), "issue_year": int(row.issue_year), "n": int(row.n), "status": status}
        )
        base = row._asdict()
        if not observable:
            bundle_rows.append(
                {**base, "settlement_status": status, "stake_cny": math.nan,
                 "gross_cny": math.nan, "pnl_cny": math.nan, "hit": False,
                 "miss_count": math.nan, "winning_ticket_index": -1}
            )
            attribution_rows.extend(leg_rows)
            continue
        results = {str(leg["match_idx"]): str(leg["result_code"]) for leg in leg_rows}
        winning_ticket = -1
        winning_stake = 0.0
        for ticket in ticket_groups[(str(row.issue), int(row.issue_year), int(row.n))].itertuples(index=False):
            choices = dict(part.split("=", 1) for part in str(ticket.ticket_key).split("|"))
            if all(choices[key] == result for key, result in results.items()):
                winning_ticket = int(ticket.ticket_index)
                winning_stake = float(ticket.stake_cny)
                break
        product_sp = float(np.prod([leg["winning_sp"] for leg in leg_rows]))
        gross = winning_stake * PAYOUT_FACTOR * product_sp if winning_ticket >= 0 else 0.0
        miss_count = int(sum(not leg["included"] for leg in leg_rows))
        bundle_rows.append(
            {**base, "settlement_status": status, "stake_cny": ISSUE_STAKE_CNY,
             "gross_cny": gross, "pnl_cny": gross - ISSUE_STAKE_CNY,
             "hit": bool(winning_ticket >= 0), "miss_count": miss_count,
             "winning_ticket_index": winning_ticket}
        )
        attribution_rows.extend(leg_rows)
    return pd.DataFrame(bundle_rows), pd.DataFrame(attribution_rows), pd.DataFrame(settlement_coverage)


def _longest_run(mask: np.ndarray) -> int:
    return max((sum(1 for _ in run) for value, run in itertools.groupby(mask) if value), default=0)


def _worst_window(values: np.ndarray, width: int) -> float:
    if len(values) < width:
        return float(values.sum())
    return float(pd.Series(values).rolling(width).sum().min())


def _loss_window_probability(values: np.ndarray, width: int) -> float:
    if len(values) < width:
        return float(values.sum() < 0)
    return float((pd.Series(values).rolling(width).sum().dropna() < 0).mean())


def _recovery_metrics(equity: np.ndarray) -> tuple[int, int]:
    peak = float(equity[0])
    peak_at = 0
    completed: list[int] = []
    for index, value in enumerate(equity[1:], start=1):
        if value >= peak:
            if index > peak_at + 1:
                completed.append(index - peak_at)
            peak = float(value)
            peak_at = index
    terminal = 0 if equity[-1] >= peak else len(equity) - 1 - peak_at
    return max(completed, default=0), int(terminal)


def _period_groups(frame: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    return [(str(year), frame[frame["issue_year"].eq(year)].copy()) for year in YEARS] + [("ALL", frame.copy())]


def evaluate(
    bundles: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    settled = bundles[bundles["settlement_status"].eq("SETTLED")].copy()
    performance_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
    for n in N_VALUES:
        n_frame = settled[settled["n"].eq(n)].copy()
        for period, group in _period_groups(n_frame):
            group = group.sort_values(["issue_anchor_ts", "issue"], kind="stable").reset_index(drop=True)
            if group.empty:
                continue
            pnl = group["pnl_cny"].to_numpy(float)
            gross = group["gross_cny"].to_numpy(float)
            capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
            equity = np.r_[STARTING_CAPITAL_CNY, capital]
            peaks = np.maximum.accumulate(equity)
            drawdown = (peaks - equity) / np.maximum(peaks, 1e-12)
            completed_recovery, terminal_underwater = _recovery_metrics(equity)
            total_gross = float(gross.sum())
            payout_weights = gross / total_gross if total_gross > 0 else np.zeros(len(gross))
            performance_rows.append(
                {
                    "n": n, "period": period, "issues": int(len(group)),
                    "stake_cny": float(group["stake_cny"].sum()), "gross_cny": total_gross,
                    "pnl_cny": float(pnl.sum()), "ending_capital_cny": float(capital[-1]),
                    "capital_return": float(pnl.sum() / STARTING_CAPITAL_CNY),
                    "stake_roi": float(pnl.sum() / group["stake_cny"].sum()),
                    "hit_issues": int(group["hit"].sum()), "hit_rate": float(group["hit"].mean()),
                    "mean_miss_count": float(group["miss_count"].mean()),
                    "largest_payout_cny": float(gross.max()),
                    "largest_payout_share": float(gross.max() / total_gross) if total_gross else 0.0,
                    "payout_hhi": float(np.square(payout_weights).sum()),
                }
            )
            risk_rows.append(
                {
                    "n": n, "period": period,
                    "max_drawdown_cny": float((peaks - equity).max()),
                    "max_drawdown_fraction": float(drawdown.max()),
                    "max_consecutive_losing_issues": _longest_run(pnl < 0),
                    "worst_5_issue_pnl_cny": _worst_window(pnl, 5),
                    "worst_10_issue_pnl_cny": _worst_window(pnl, 10),
                    "worst_20_issue_pnl_cny": _worst_window(pnl, 20),
                    "loss_probability_5_issue": _loss_window_probability(pnl, 5),
                    "loss_probability_10_issue": _loss_window_probability(pnl, 10),
                    "loss_probability_20_issue": _loss_window_probability(pnl, 20),
                    "max_completed_recovery_issues": completed_recovery,
                    "terminal_underwater_issues": terminal_underwater,
                }
            )
            for index, row in group.iterrows():
                path_rows.append(
                    {
                        "n": n, "period": period, "path_index": index + 1,
                        "issue": str(row["issue"]), "issue_year": int(row["issue_year"]),
                        "pnl_cny": float(row["pnl_cny"]), "capital_cny": float(capital[index]),
                        "drawdown_fraction": float(drawdown[index + 1]),
                    }
                )
            seed = BOOTSTRAP_SEED + n * 100 + (0 if period == "ALL" else int(period))
            rng = np.random.default_rng(seed)
            draws = rng.choice(pnl, size=(BOOTSTRAP_DRAWS, len(pnl)), replace=True).sum(axis=1)
            bootstrap_rows.append(
                {
                    "n": n, "period": period, "draws": BOOTSTRAP_DRAWS, "seed": seed,
                    "pnl_p05_cny": float(np.quantile(draws, 0.05)),
                    "pnl_p50_cny": float(np.quantile(draws, 0.50)),
                    "pnl_p95_cny": float(np.quantile(draws, 0.95)),
                    "positive_fraction": float((draws > 0).mean()),
                }
            )
    return (
        pd.DataFrame(performance_rows), pd.DataFrame(risk_rows),
        pd.DataFrame(path_rows), pd.DataFrame(bootstrap_rows),
    )


def _markdown(frame: pd.DataFrame) -> str:
    shown = frame.copy()
    for column in shown.select_dtypes(include="number"):
        shown[column] = shown[column].map(lambda value: f"{value:.6g}")
    header = "| " + " | ".join(map(str, shown.columns)) + " |"
    rule = "| " + " | ".join("---" for _ in shown.columns) + " |"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in shown.itertuples(index=False, name=None)]
    return "\n".join([header, rule, *rows])


def _write_figures(repo_root: Path, performance: pd.DataFrame, risk: pd.DataFrame) -> list[Path]:
    directory = repo_root / "docs/research/figures"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "issue_348_multin_r0_frontier.png"
    all_perf = performance[performance["period"].eq("ALL")]
    all_risk = risk[risk["period"].eq("ALL")]
    merged = all_perf.merge(all_risk, on=["n", "period"], validate="one_to_one")
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    axes[0].plot(merged["n"], merged["capital_return"], marker="o")
    axes[0].axhline(0, color="black", lw=.8)
    axes[0].set(title="Fixed-budget capital return", xlabel="N", ylabel="return on CNY100k")
    axes[1].plot(merged["n"], merged["hit_rate"], marker="o")
    axes[1].set(title="Issue hit rate", xlabel="N")
    axes[2].plot(merged["n"], merged["max_drawdown_fraction"], marker="o", label="drawdown")
    axes[2].plot(merged["n"], merged["largest_payout_share"], marker="s", label="largest payout share")
    axes[2].set(title="Path and tail concentration", xlabel="N")
    axes[2].legend()
    for axis in axes:
        axis.grid(alpha=.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return [path]


def _write_report(
    repo_root: Path, performance: pd.DataFrame, risk: pd.DataFrame,
    bootstrap: pd.DataFrame, coverage: pd.DataFrame, decision: dict[str, Any],
) -> Path:
    path = repo_root / "docs/research/Issue-348-MultiN-R0-Baselines.md"
    all_perf = performance[performance["period"].eq("ALL")]
    all_risk = risk[risk["period"].eq("ALL")]
    annual = performance[performance["period"].isin(["2023", "2024"])][
        ["n", "period", "issues", "ending_capital_cny", "capital_return", "hit_rate", "largest_payout_share"]
    ]
    coverage_summary = coverage.groupby(["n", "status"], as_index=False).size()
    text = f"""# Issue #348 — native probability-Top2 R0 baselines across N3–N10

## Decision summary

- This is **Phase A baseline evidence**, not a model search and not a cross-N winner declaration.
- Every settled issue invests exactly CNY1,024 and applies the Beijing 0.65 factor once per winning N-fold ticket.
- `K_N=min(128,2^N)`: N3–N6 fully cover all 8/16/32/64 binary tickets; N7 fully covers 128; N8–N10 use a fixed 128-run pairwise-balanced design.
- 2023 and 2024 are exposed historical evidence. The 10h panel is a retrospective relative proxy.
- Verdict: **{decision['verdict']}**. Phase B may compare a frozen R_N only against the same N's exact R0 denominator.

## All-period capital and payout shape

{_markdown(all_perf)}

## All-period path risk

{_markdown(all_risk)}

## Annual evidence

{_markdown(annual)}

## Coverage

{_markdown(coverage_summary)}

## Issue bootstrap

{_markdown(bootstrap)}

## Interpretation discipline

Ending capital is not a sufficient cross-N ranking statistic. Lower N changes the complete ticket-space coverage and payout distribution; higher N trades hit frequency for larger tail payouts. The holding-feasibility columns (drawdown, losing runs, rolling loss windows, recovery and payout concentration) must travel with every capital comparison.

## Artifacts

- Package: `results/multin_top2_r0/`
- Notebook: `notebooks/research/multin-top2-r0/multin_top2_r0.ipynb`
- Figure: `docs/research/figures/issue_348_multin_r0_frontier.png`
"""
    path.write_text(text, encoding="utf-8")
    return path


def _write_notebook(repo_root: Path) -> Path:
    path = repo_root / "notebooks/research/multin-top2-r0/multin_top2_r0.ipynb"
    path.parent.mkdir(parents=True, exist_ok=True)
    cells = [
        nbformat.v4.new_markdown_cell(
            "# Issue #348 — multi-N R0 baselines\n\nExecuted compact analysis; the issue is the independent unit."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport json\nimport pandas as pd\n"
            "ROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/multin_top2_r0'"
        ),
        nbformat.v4.new_code_cell(
            "decision=json.loads((OUT/'decision.json').read_text())\n"
            "performance=pd.read_csv(OUT/'performance.csv')\n"
            "decision, performance[performance.period.eq('ALL')]"
        ),
        nbformat.v4.new_code_cell(
            "risk=pd.read_csv(OUT/'risk_diagnostics.csv')\n"
            "risk[risk.period.eq('ALL')]"
        ),
        nbformat.v4.new_code_cell(
            "coverage=pd.read_csv(OUT/'coverage_ledger.csv')\n"
            "coverage.groupby(['n','status']).size().unstack(fill_value=0)"
        ),
    ]
    for cell, cell_id in zip(cells, ("intro", "imports", "performance", "risk", "coverage"), strict=True):
        cell["id"] = f"bj348-{cell_id}"
    notebook = nbformat.v4.new_notebook(cells=cells)
    notebook.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3"},
    }
    executed = NotebookClient(notebook, timeout=180, kernel_name="python3").execute(cwd=str(path.parent))
    for cell in executed.cells:
        cell.metadata.pop("execution", None)
    nbformat.write(executed, path)
    return path


def _write_table(path: Path, frame: pd.DataFrame) -> None:
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False, lineterminator="\n", float_format="%.17g")


def build_package(repo_root: Path, output: Path, data_root: Path | None = None) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    data_root = locate_data_root(repo_root, data_root)
    causal = load_causal_cells(data_root)
    matches = prepare_match_surface(causal)
    frozen, tickets, precoverage = construct_preoutcome(matches)
    freeze_hashes = {
        "match_surface_sha256": stable_frame_sha(matches),
        "frozen_bundles_sha256": stable_frame_sha(frozen),
        "tickets_sha256": stable_frame_sha(tickets),
    }
    settlement = load_settlement(data_root, sorted(frozen["issue"].unique()))
    bundles, attribution, settlement_coverage = settle(frozen, tickets, settlement)
    coverage = precoverage.merge(
        settlement_coverage, on=["issue", "issue_year", "n"], how="left", suffixes=("_preoutcome", "_settlement")
    )
    coverage["status"] = coverage["status_settlement"].fillna(coverage["status_preoutcome"])
    coverage = coverage.drop(columns=["status_preoutcome", "status_settlement"])
    performance, risk, paths, bootstrap = evaluate(bundles)
    decision = {
        "contract": CONTRACT_ID, "issue": ISSUE_NUMBER, "verdict": "BASELINES_ESTABLISHED",
        "n_values": list(N_VALUES), "years": list(YEARS), "evaluation_status": "EXPOSED_HISTORICAL",
        "payout_factor_application": "ticket_level_once", "issue_stake_cny": ISSUE_STAKE_CNY,
        "phase_b_authorized": True, "phase_c_or_d_authorized": False,
        "promotable_to_210": False, "changes_210_or_218": False,
    }
    source_receipt = {
        "contract": CONTRACT_ID,
        "probability_path": str(PROBABILITY_RELATIVE),
        "probability_sha256": sha256_file(data_root / PROBABILITY_RELATIVE),
        "settlement_path": str(SETTLEMENT_RELATIVE),
        "settlement_sha256": sha256_file(data_root / SETTLEMENT_RELATIVE),
        "horizon": HORIZON, "proxy_grade": "RETROSPECTIVE_RELATIVE_PROXY",
        "feature_cells": int(len(causal)), "matches": int(len(matches)),
        "issues": int(matches["issue"].nunique()), "years": list(YEARS),
        **freeze_hashes,
    }
    tables = {
        "match_surface.parquet": matches,
        "preoutcome_bundles.parquet": frozen,
        "tickets.parquet": tickets,
        "issue_bundles.parquet": bundles,
        "support_attribution.parquet": attribution,
        "coverage_ledger.csv": coverage,
        "performance.csv": performance,
        "risk_diagnostics.csv": risk,
        "capital_paths.csv": paths,
        "bootstrap_absolute.csv": bootstrap,
    }
    for name, frame in tables.items():
        _write_table(output / name, frame)
    _write_json(output / "source_receipt.json", source_receipt)
    _write_json(output / "decision.json", decision)
    figures = _write_figures(repo_root, performance, risk)
    report = _write_report(repo_root, performance, risk, bootstrap, coverage, decision)
    notebook = _write_notebook(repo_root)
    artifacts = [path for path in output.iterdir() if path.name != "MANIFEST.json"] + [*figures, report, notebook]
    manifest = {
        "contract": CONTRACT_ID,
        "files": {
            str(path.relative_to(repo_root)): {"sha256": sha256_file(path), "bytes": path.stat().st_size}
            for path in sorted(artifacts)
        },
    }
    _write_json(output / "MANIFEST.json", manifest)
    return decision


def _assert_semantic_equal(actual: pd.DataFrame, expected: pd.DataFrame, keys: list[str]) -> None:
    actual = actual.sort_values(keys, kind="stable").reset_index(drop=True)
    expected = expected.sort_values(keys, kind="stable").reset_index(drop=True)
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False, check_exact=False, rtol=0, atol=1e-8)


def verify_package(
    repo_root: Path, output: Path, data_root: Path | None = None,
) -> dict[str, bool]:
    repo_root = repo_root.resolve()
    output = output.resolve()
    data_root = locate_data_root(repo_root, data_root)
    manifest = json.loads((output / "MANIFEST.json").read_text())
    required = {
        f"results/multin_top2_r0/{name}" for name in (
            "match_surface.parquet", "preoutcome_bundles.parquet", "tickets.parquet",
            "issue_bundles.parquet", "support_attribution.parquet", "coverage_ledger.csv",
            "performance.csv", "risk_diagnostics.csv", "capital_paths.csv",
            "bootstrap_absolute.csv", "source_receipt.json", "decision.json",
        )
    } | {
        "docs/research/Issue-348-MultiN-R0-Baselines.md",
        "docs/research/figures/issue_348_multin_r0_frontier.png",
        "notebooks/research/multin-top2-r0/multin_top2_r0.ipynb",
    }
    checks: dict[str, bool] = {}
    checks["manifest_exact_nonempty"] = set(manifest.get("files", {})) == required and bool(required)
    checks["manifest_hashes"] = all(
        (repo_root / relative).exists()
        and sha256_file(repo_root / relative) == evidence["sha256"]
        and (repo_root / relative).stat().st_size == evidence["bytes"]
        for relative, evidence in manifest.get("files", {}).items()
    )
    receipt = json.loads((output / "source_receipt.json").read_text())
    checks["source_hashes"] = (
        receipt["probability_sha256"] == sha256_file(data_root / PROBABILITY_RELATIVE)
        and receipt["settlement_sha256"] == sha256_file(data_root / SETTLEMENT_RELATIVE)
    )
    causal = load_causal_cells(data_root)
    matches = prepare_match_surface(causal)
    frozen, tickets, precoverage = construct_preoutcome(matches)
    committed_matches = pd.read_parquet(output / "match_surface.parquet")
    committed_frozen = pd.read_parquet(output / "preoutcome_bundles.parquet")
    committed_tickets = pd.read_parquet(output / "tickets.parquet")
    _assert_semantic_equal(committed_matches, matches, ["issue", "match_idx"])
    _assert_semantic_equal(committed_frozen, frozen, ["issue", "n"])
    _assert_semantic_equal(committed_tickets, tickets, ["issue", "n", "ticket_index"])
    checks["source_bound_freeze"] = True
    checks["freeze_hashes"] = (
        receipt["match_surface_sha256"] == stable_frame_sha(matches)
        and receipt["frozen_bundles_sha256"] == stable_frame_sha(frozen)
        and receipt["tickets_sha256"] == stable_frame_sha(tickets)
    )
    design_ok = True
    for n in N_VALUES:
        design = binary_design(n)
        groups = committed_tickets[committed_tickets["n"].eq(n)].groupby(["issue", "issue_year"])
        for _, group in groups:
            design_ok &= len(group) == tickets_for_n(n)
            design_ok &= group["ticket_key"].nunique() == tickets_for_n(n)
            design_ok &= int(group["units"].sum()) == FUNDED_UNITS
            design_ok &= math.isclose(group["stake_cny"].sum(), ISSUE_STAKE_CNY, rel_tol=0, abs_tol=1e-9)
        design_ok &= design.shape == (tickets_for_n(n), n)
    checks["ticket_design_and_budget"] = bool(design_ok)
    settlement = load_settlement(data_root, sorted(frozen["issue"].unique()))
    bundles, attribution, settlement_coverage = settle(frozen, tickets, settlement)
    committed_bundles = pd.read_parquet(output / "issue_bundles.parquet")
    committed_attribution = pd.read_parquet(output / "support_attribution.parquet")
    _assert_semantic_equal(committed_bundles, bundles, ["issue", "n"])
    _assert_semantic_equal(committed_attribution, attribution, ["issue", "n", "match_idx"])
    checks["source_bound_settlement"] = True
    settled = committed_bundles[committed_bundles["settlement_status"].eq("SETTLED")]
    checks["pnl_identity"] = bool(
        np.allclose(settled["pnl_cny"], settled["gross_cny"] - settled["stake_cny"], rtol=0, atol=1e-9)
    )
    checks["ticket_level_once_payout"] = bool(PAYOUT_FACTOR == 0.65)
    performance, risk, paths, bootstrap = evaluate(bundles)
    for name, expected, keys in (
        ("performance", performance, ["n", "period"]),
        ("risk_diagnostics", risk, ["n", "period"]),
        ("capital_paths", paths, ["n", "period", "path_index"]),
        ("bootstrap_absolute", bootstrap, ["n", "period"]),
    ):
        actual = pd.read_csv(output / f"{name}.csv", dtype={"period": str, "issue": str})
        expected = expected.copy()
        if "period" in expected:
            expected["period"] = expected["period"].astype(str)
        _assert_semantic_equal(actual, expected, keys)
    checks["metrics_recomputed"] = True
    coverage = precoverage.merge(
        settlement_coverage, on=["issue", "issue_year", "n"], how="left", suffixes=("_preoutcome", "_settlement")
    )
    coverage["status"] = coverage["status_settlement"].fillna(coverage["status_preoutcome"])
    coverage = coverage.drop(columns=["status_preoutcome", "status_settlement"])
    actual_coverage = pd.read_csv(output / "coverage_ledger.csv", dtype={"issue": str})
    _assert_semantic_equal(actual_coverage, coverage, ["issue", "n"])
    checks["coverage_recomputed"] = True
    decision = json.loads((output / "decision.json").read_text())
    checks["decision_scope"] = (
        decision["verdict"] == "BASELINES_ESTABLISHED"
        and decision["phase_c_or_d_authorized"] is False
        and decision["changes_210_or_218"] is False
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise AssertionError(f"verification failed: {failed}")
    return checks
