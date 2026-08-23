"""Build and source-verify Issue #352 annual N3-N6 x R diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient

from src.multin_fixed_rn.pipeline import (
    _armwise_ex_largest,
    _risk_values,
    freeze_bundles,
    prepare_support_matches,
    settle_bundles,
)
from src.multin_top2_r0.contract import (
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    N_VALUES,
    PAYOUT_FACTOR,
    STAKE_PER_UNIT_CNY,
    tickets_for_n,
    units_per_ticket,
)
from src.multin_top2_r0.pipeline import (
    PROBABILITY_RELATIVE,
    SETTLEMENT_RELATIVE,
    binary_design,
    load_causal_cells,
    load_settlement,
    locate_data_root,
    sha256_file,
    stable_frame_sha,
)

from .contract import (
    CONTRACT_ID,
    FIGURE_LIFT_RELATIVE,
    FIGURE_RISK_RELATIVE,
    FROZEN_349_RECEIPT,
    FROZEN_349_RECEIPT_SHA256,
    FROZEN_349_SELECTED_R,
    ISSUE_NUMBER,
    NOTEBOOK_RELATIVE,
    PERIOD_ROLES,
    PERIODS,
    REPORT_RELATIVE,
    STARTING_CAPITAL_CNY,
    TARGET_N_VALUES,
    YEARS,
)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_table(path: Path, frame: pd.DataFrame) -> None:
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False)
    else:
        frame.to_csv(path, index=False, lineterminator="\n", float_format="%.17g")


def diagnostic_spec() -> dict[int, tuple[int, ...]]:
    """Return full R grids only for target N while satisfying the inherited API."""

    return {
        n: tuple(range(n + 1)) if n in TARGET_N_VALUES else tuple()
        for n in N_VALUES
    }


def freeze_diagnostic(matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    frozen, coverage = freeze_bundles(
        matches, diagnostic_spec(), YEARS, "RETROSPECTIVE_DIAGNOSTIC"
    )
    frozen = frozen[frozen["n"].isin(TARGET_N_VALUES)].reset_index(drop=True)
    coverage = coverage[coverage["n"].isin(TARGET_N_VALUES)].reset_index(drop=True)
    return frozen, coverage


def common_settled_bundles(bundles: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep the exact within-N/year denominator shared by every R arm."""

    kept: list[pd.DataFrame] = []
    ledger: list[dict[str, Any]] = []
    for (n, year), group in bundles.groupby(["n", "issue_year"], sort=True):
        expected_r = set(range(int(n) + 1))
        status = group.pivot(index="issue", columns="r", values="settlement_status")
        common = status.columns.astype(int).isin(expected_r).all() and set(status.columns) == expected_r
        if not common:
            raise AssertionError(f"missing R arm for N{n}/{year}")
        settled_mask = status.eq("SETTLED").all(axis=1)
        common_issues = set(status.index[settled_mask].astype(str))
        kept.append(group[group["issue"].astype(str).isin(common_issues)].copy())
        for issue, row in status.iterrows():
            statuses = sorted(set(map(str, row.tolist())))
            ledger.append(
                {
                    "n": int(n), "issue_year": int(year), "issue": str(issue),
                    "included": bool(str(issue) in common_issues),
                    "status": "SETTLED" if str(issue) in common_issues else "EXCLUDED",
                    "arm_statuses": "|".join(statuses),
                }
            )
    return pd.concat(kept, ignore_index=True), pd.DataFrame(ledger)


def _period_frame(frame: pd.DataFrame, period: str) -> pd.DataFrame:
    if period == "ALL_2022_2024":
        return frame.copy()
    return frame[frame["issue_year"].eq(int(period))].copy()


def annual_matrix(bundles: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute all preregistered absolute, matched and path-risk diagnostics."""

    rows: list[dict[str, Any]] = []
    paths: list[dict[str, Any]] = []
    for n in TARGET_N_VALUES:
        n_frame = bundles[bundles["n"].eq(n)].copy()
        for period in PERIODS:
            period_frame = _period_frame(n_frame, period)
            control = period_frame[period_frame["r"].eq(0)].sort_values(
                ["issue_anchor_ts", "issue"], kind="stable"
            ).reset_index(drop=True)
            for r in range(n + 1):
                arm = period_frame[period_frame["r"].eq(r)].sort_values(
                    ["issue_anchor_ts", "issue"], kind="stable"
                ).reset_index(drop=True)
                if arm["issue"].astype(str).tolist() != control["issue"].astype(str).tolist():
                    raise AssertionError(f"unmatched denominator N{n}/R{r}/{period}")
                paired = arm[["issue", "pnl_cny"]].merge(
                    control[["issue", "pnl_cny"]].rename(
                        columns={"pnl_cny": "r0_pnl_cny"}
                    ),
                    on="issue", validate="one_to_one",
                )
                delta = paired["pnl_cny"].to_numpy(float) - paired["r0_pnl_cny"].to_numpy(float)
                lift = float(delta.sum())
                sensitivity = float(
                    lift - delta[int(np.argmax(np.abs(delta)))]
                ) if len(delta) else 0.0
                pnl = arm["pnl_cny"].to_numpy(float)
                gross = arm["gross_cny"].to_numpy(float)
                stake = float(arm["stake_cny"].sum())
                total_gross = float(gross.sum())
                weights = gross / total_gross if total_gross > 0 else np.zeros(len(gross))
                risk = _risk_values(arm)
                capital = STARTING_CAPITAL_CNY + np.cumsum(pnl)
                rows.append(
                    {
                        "n": n, "r": r, "arm": f"R{r}", "period": period,
                        "period_role": PERIOD_ROLES[period],
                        "settled_issues": int(len(arm)),
                        "stake_cny": stake, "gross_cny": total_gross,
                        "pnl_cny": float(pnl.sum()),
                        "ending_capital_cny": float(STARTING_CAPITAL_CNY + pnl.sum()),
                        "stake_roi": float(pnl.sum() / stake) if stake else 0.0,
                        "hit_issues": int(arm["hit"].sum()),
                        "hit_rate": float(arm["hit"].mean()) if len(arm) else 0.0,
                        "hit_rate_lift_vs_r0": (
                            float(arm["hit"].mean() - control["hit"].mean())
                            if len(arm) else 0.0
                        ),
                        "lift_vs_r0_cny": lift,
                        "armwise_ex_largest_lift_vs_r0_cny": (
                            _armwise_ex_largest(arm, control) if len(arm) else 0.0
                        ),
                        "largest_abs_paired_delta_sensitivity_cny": sensitivity,
                        "max_drawdown_cny": risk["max_drawdown_cny"],
                        "max_drawdown_fraction": risk["max_drawdown_fraction"],
                        "longest_losing_run": risk["max_consecutive_losing_issues"],
                        "largest_payout_share": (
                            float(gross.max() / total_gross) if total_gross else 0.0
                        ),
                        "payout_hhi": float(np.square(weights).sum()),
                    }
                )
                for index, issue_row in arm.iterrows():
                    paths.append(
                        {
                            "n": n, "r": r, "period": period,
                            "period_role": PERIOD_ROLES[period],
                            "path_index": index + 1, "issue": str(issue_row["issue"]),
                            "issue_year": int(issue_row["issue_year"]),
                            "pnl_cny": float(issue_row["pnl_cny"]),
                            "capital_cny": float(capital[index]),
                        }
                    )
    matrix = pd.DataFrame(rows).sort_values(["n", "r", "period"], kind="stable")
    path = pd.DataFrame(paths).sort_values(
        ["n", "r", "period", "path_index"], kind="stable"
    )
    return matrix.reset_index(drop=True), path.reset_index(drop=True)


def replacement_signal_diagnostic(
    attribution: pd.DataFrame, settled_bundles: pd.DataFrame,
) -> pd.DataFrame:
    """Diagnose realized set replacements without treating order flips as actions."""

    keys = settled_bundles[["issue", "n", "r"]].drop_duplicates()
    frame = attribution.merge(keys, on=["issue", "n", "r"], how="inner", validate="many_to_one")
    baseline_sets = frame["baseline_support"].astype(str).map(frozenset)
    qeu_sets = frame["qeu_support"].astype(str).map(frozenset)
    applied_sets = frame["support"].astype(str).map(frozenset)
    result = frame["result_code"].astype(str)
    frame = frame.assign(
        support_set_changed=baseline_sets.ne(qeu_sets),
        qeu_set_applied=baseline_sets.ne(qeu_sets) & applied_sets.eq(qeu_sets),
        baseline_result_included=[value in support for value, support in zip(result, baseline_sets, strict=True)],
        applied_result_included=[value in support for value, support in zip(result, applied_sets, strict=True)],
    )
    frame["rescued_result"] = (
        frame["qeu_set_applied"]
        & ~frame["baseline_result_included"] & frame["applied_result_included"]
    )
    frame["displaced_winner"] = (
        frame["qeu_set_applied"]
        & frame["baseline_result_included"] & ~frame["applied_result_included"]
    )
    rows: list[dict[str, Any]] = []
    for n in TARGET_N_VALUES:
        n_frame = frame[frame["n"].eq(n)]
        for period in PERIODS:
            period_frame = _period_frame(n_frame, period)
            for r in range(n + 1):
                arm = period_frame[period_frame["r"].eq(r)]
                applied = int(arm["qeu_set_applied"].sum())
                rescued = int(arm["rescued_result"].sum())
                harmed = int(arm["displaced_winner"].sum())
                rows.append(
                    {
                        "n": n, "r": r, "period": period,
                        "period_role": PERIOD_ROLES[period],
                        "settled_issues": int(arm["issue"].nunique()),
                        "selected_legs": int(len(arm)),
                        "set_change_eligible_legs": int(arm["support_set_changed"].sum()),
                        "qeu_set_applied_legs": applied,
                        "rescued_results": rescued,
                        "displaced_winners": harmed,
                        "net_result_inclusions": rescued - harmed,
                        "rescue_rate_per_applied": float(rescued / applied) if applied else 0.0,
                        "displacement_rate_per_applied": float(harmed / applied) if applied else 0.0,
                        "net_inclusion_rate_per_applied": (
                            float((rescued - harmed) / applied) if applied else 0.0
                        ),
                    }
                )
    return pd.DataFrame(rows).sort_values(["n", "r", "period"], kind="stable").reset_index(drop=True)


def _markdown(frame: pd.DataFrame) -> str:
    shown = frame.copy()
    for column in shown.select_dtypes(include="number"):
        shown[column] = shown[column].map(
            lambda value: f"{value:.6g}" if pd.notna(value) else ""
        )
    header = "| " + " | ".join(shown.columns) + " |"
    rule = "| " + " | ".join(["---"] * len(shown.columns)) + " |"
    lines = ["| " + " | ".join(map(str, row)) + " |" for row in shown.itertuples(index=False, name=None)]
    return "\n".join([header, rule, *lines])


def _diagnostic_observations(
    matrix: pd.DataFrame, signal: pd.DataFrame,
) -> list[str]:
    observations: list[str] = []
    annual = matrix[matrix["period"].isin(["2022", "2023", "2024"])]
    for n in TARGET_N_VALUES:
        pieces = []
        for year in ("2022", "2023", "2024"):
            frame = annual[(annual["n"].eq(n)) & annual["period"].eq(year)]
            best = frame.sort_values(
                ["lift_vs_r0_cny", "armwise_ex_largest_lift_vs_r0_cny", "r"],
                ascending=[False, False, True], kind="stable",
            ).iloc[0]
            pieces.append(f"{year}: R{int(best.r)} lift {best.lift_vs_r0_cny:,.0f}")
        observations.append(f"N{n} descriptive annual maxima — " + "; ".join(pieces) + ".")
    nonzero = signal[
        signal["r"].gt(0) & signal["period"].isin(["2022", "2023", "2024"])
    ]
    if nonzero["net_result_inclusions"].lt(0).all():
        observations.append(
            "Every non-zero fixed-R arm has negative realized net result inclusion "
            "(rescued outcomes minus displaced winners); divergence replacement did not "
            "improve leg-level coverage accuracy in any displayed N/year cell."
        )
    n6r3 = matrix[matrix["n"].eq(6) & matrix["r"].eq(3)].set_index("period")
    observations.append(
        "N6/R3 illustrates payoff rather than accuracy: 2023 lift "
        f"{n6r3.loc['2023', 'lift_vs_r0_cny']:,.0f} with hit-rate change "
        f"{n6r3.loc['2023', 'hit_rate_lift_vs_r0']:+.2%}; 2024 lift "
        f"{n6r3.loc['2024', 'lift_vs_r0_cny']:,.0f} with hit-rate change "
        f"{n6r3.loc['2024', 'hit_rate_lift_vs_r0']:+.2%}; but its 2022 lift is "
        f"{n6r3.loc['2022', 'lift_vs_r0_cny']:,.0f}."
    )
    return observations


def write_delivery(
    repo_root: Path, output: Path, matrix: pd.DataFrame, paths: pd.DataFrame,
    coverage: pd.DataFrame, signal: pd.DataFrame, decision: dict[str, Any],
) -> list[Path]:
    lift_figure = repo_root / FIGURE_LIFT_RELATIVE
    risk_figure = repo_root / FIGURE_RISK_RELATIVE
    lift_figure.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=False)
    for axis, n in zip(axes.flat, TARGET_N_VALUES, strict=True):
        for period in ("2022", "2023", "2024"):
            frame = matrix[(matrix["n"].eq(n)) & matrix["period"].eq(period)]
            axis.plot(frame["r"], frame["lift_vs_r0_cny"], marker="o", label=period)
        axis.axhline(0, color="black", lw=.8)
        axis.set(title=f"N{n}: matched lift vs R0", xlabel="fixed R", ylabel="CNY")
        axis.grid(alpha=.25)
    axes.flat[0].legend()
    fig.tight_layout()
    fig.savefig(lift_figure, dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=False)
    for axis, n in zip(axes.flat, TARGET_N_VALUES, strict=True):
        for period in ("2022", "2023", "2024"):
            frame = matrix[(matrix["n"].eq(n)) & matrix["period"].eq(period)]
            axis.plot(frame["r"], frame["max_drawdown_fraction"], marker="o", label=period)
        axis.set(title=f"N{n}: max drawdown", xlabel="fixed R", ylabel="fraction")
        axis.grid(alpha=.25)
    axes.flat[0].legend()
    fig.tight_layout()
    fig.savefig(risk_figure, dpi=160)
    plt.close(fig)

    report = repo_root / REPORT_RELATIVE
    observations = "\n".join(
        f"- {item}" for item in _diagnostic_observations(matrix, signal)
    )
    report.write_text(
        f"""# Issue #352 — N3–N6 × fixed-R annual diagnostic matrix

## Five-minute decision summary

- This is **retrospective diagnostic evidence only**. It does not select or promote an R.
- 2022 is `DEVELOPMENT_DIAGNOSTIC`; 2023 and 2024 are `EXPOSED_HISTORICAL_EVALUATION`; the pooled row is `DESCRIPTIVE_ONLY`.
- The inherited probability candidate gate was confirmed with 2023 outcomes (post-merge #348 EV finding), so the entire matrix is conditional exposed history, **not chronology-clean evidence**. The year-role labels describe use inside this diagnostic, not upstream causal purity.
- The accepted #349 receipt remains byte-identical at `{FROZEN_349_RECEIPT_SHA256}` and its selected R values remain `{FROZEN_349_SELECTED_R}`.
- Every row preserves probability Top-2 match selection, complete distinct Top-2 ticket coverage, CNY1,024 per issue, and one ticket-level 0.65 payout factor.
- Verdict: **{decision['verdict']}**. No pooled or annual result has been used to reselect R.

## Descriptive observations (not selection)

{observations}

Annual maxima above are deliberately descriptive. They are not evidence that an R is stable across years and cannot modify #349.

## Metric definitions

- `lift_vs_r0_cny`: paired PnL difference on the exact N-period common denominator.
- `armwise_ex_largest_lift_vs_r0_cny`: remove each arm's own largest payout, then compare.
- `largest_abs_paired_delta_sensitivity_cny`: remove the issue with the largest absolute paired delta, then sum the remaining deltas.
- `stake_roi`: PnL divided by cumulative stake; `ending_capital_cny` starts each displayed period at CNY100,000.
- `hit_rate_lift_vs_r0` is the exact matched difference in issue hit rate.
- `largest_payout_share` and `payout_hhi` describe payout concentration.

## Complete 88-row matrix

{_markdown(matrix)}

## Settlement coverage

{_markdown(coverage.groupby(['n', 'issue_year', 'included', 'status'], as_index=False).size())}

## Realized divergence replacement signal

Only a changed Top-2 **outcome set** counts as an action. Order-only reversals such as `31` versus `13` are excluded because the complete Cartesian ticket set is unchanged.

{_markdown(signal)}

## Artifacts

- Exact matrix: `results/multin_r_diagnostic/annual_diagnostic_matrix.csv`
- Settled evidence: `results/multin_r_diagnostic/settled_bundles.parquet`
- Source receipt: `results/multin_r_diagnostic/source_receipt.json`
- Diagnostic receipt: `results/multin_r_diagnostic/diagnostic_receipt.json`
- Set-based replacement attribution: `results/multin_r_diagnostic/replacement_signal_diagnostic.csv`
- Executed notebook: `notebooks/research/multin-r-diagnostic/multin_r_diagnostic.ipynb`
- Figures: `{FIGURE_LIFT_RELATIVE}`, `{FIGURE_RISK_RELATIVE}`

## Boundary

This package does not authorize Phase C/D, does not alter #349, and does not unlock, rebind, or otherwise modify #210 or #218.
""",
        encoding="utf-8",
    )

    notebook_path = repo_root / NOTEBOOK_RELATIVE
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    cells = [
        nbformat.v4.new_markdown_cell(
            "# Issue #352 — N3–N6 × R annual diagnostics\n\n"
            "Retrospective diagnostic only; 2022 development, 2023/24 exposed evaluation."
        ),
        nbformat.v4.new_code_cell(
            "from pathlib import Path\nimport pandas as pd\n"
            "ROOT=Path.cwd().parents[2]\nOUT=ROOT/'results/multin_r_diagnostic'\n"
            "matrix=pd.read_csv(OUT/'annual_diagnostic_matrix.csv')"
        ),
        nbformat.v4.new_code_cell(
            "matrix.groupby(['period','period_role'], as_index=False).size()"
        ),
        nbformat.v4.new_code_cell("matrix"),
        nbformat.v4.new_code_cell(
            "matrix[matrix.period.isin(['2022','2023','2024'])].pivot_table("
            "index=['n','r'], columns='period', values='lift_vs_r0_cny')"
        ),
        nbformat.v4.new_code_cell(
            "matrix[matrix.period.isin(['2022','2023','2024'])].pivot_table("
            "index=['n','r'], columns='period', values='max_drawdown_fraction')"
        ),
        nbformat.v4.new_code_cell(
            "signal=pd.read_csv(OUT/'replacement_signal_diagnostic.csv', dtype={'period':str})\n"
            "signal[signal.period.isin(['2022','2023','2024'])]"
        ),
    ]
    for cell, suffix in zip(
        cells, ("intro", "load", "roles", "matrix", "lift", "risk", "signal"), strict=True
    ):
        cell["id"] = f"bj352-{suffix}"
    notebook = nbformat.v4.new_notebook(cells=cells)
    notebook.metadata = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3"},
    }
    executed = NotebookClient(notebook, timeout=180, kernel_name="python3").execute(
        cwd=str(notebook_path.parent)
    )
    for cell in executed.cells:
        cell.metadata.pop("execution", None)
    nbformat.write(executed, notebook_path)
    return [report, notebook_path, lift_figure, risk_figure]


def _expected_artifacts(repo_root: Path, output: Path) -> set[str]:
    package_names = {
        "match_support.parquet", "preoutcome_bundles.parquet", "settled_bundles.parquet",
        "support_attribution.parquet", "coverage_ledger.csv", "annual_diagnostic_matrix.csv",
        "capital_paths.csv", "replacement_signal_diagnostic.csv",
        "source_receipt.json", "diagnostic_receipt.json",
    }
    return {
        *(str((output / name).relative_to(repo_root)) for name in package_names),
        str(REPORT_RELATIVE), str(NOTEBOOK_RELATIVE),
        str(FIGURE_LIFT_RELATIVE), str(FIGURE_RISK_RELATIVE),
    }


def build_package(repo_root: Path, output: Path, data_root: Path | None = None) -> dict[str, Any]:
    repo_root, output = repo_root.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    data_root = locate_data_root(repo_root, data_root)
    frozen_receipt_path = repo_root / FROZEN_349_RECEIPT
    frozen_hash_before = sha256_file(frozen_receipt_path)
    if frozen_hash_before != FROZEN_349_RECEIPT_SHA256:
        raise AssertionError("accepted #349 freeze receipt changed")
    frozen_receipt = json.loads(frozen_receipt_path.read_text(encoding="utf-8"))
    if frozen_receipt["selected_r_by_n"] != FROZEN_349_SELECTED_R:
        raise AssertionError("accepted #349 selected R values changed")

    causal = load_causal_cells(data_root, years=YEARS)
    matches = prepare_support_matches(causal)
    frozen, freeze_coverage = freeze_diagnostic(matches)
    settlement = load_settlement(data_root, sorted(frozen["issue"].astype(str).unique()))
    settled_raw, attribution, settlement_coverage = settle_bundles(frozen, matches, settlement)
    settled, common_coverage = common_settled_bundles(settled_raw)
    matrix, paths = annual_matrix(settled)
    signal = replacement_signal_diagnostic(attribution, settled)
    if len(matrix) != 88:
        raise AssertionError(f"expected 88 diagnostic rows, got {len(matrix)}")

    coverage = common_coverage.merge(
        freeze_coverage[["issue", "issue_year", "n", "available_matches", "status"]].rename(
            columns={"status": "freeze_status"}
        ), on=["issue", "issue_year", "n"], how="left", validate="many_to_one",
    )
    receipt = {
        "contract": CONTRACT_ID, "issue": ISSUE_NUMBER,
        "diagnostic_only": True, "row_count": 88,
        "target_n": list(TARGET_N_VALUES), "years": list(YEARS),
        "period_roles": PERIOD_ROLES,
        "r_grid": {str(n): list(range(n + 1)) for n in TARGET_N_VALUES},
        "frozen_349_receipt_path": str(FROZEN_349_RECEIPT),
        "frozen_349_receipt_sha256": frozen_hash_before,
        "frozen_349_selected_r": frozen_receipt["selected_r_by_n"],
        "pooled_reselection_performed": False,
        "conditional_on_exposed_2023_translator_gate": True,
        "chronology_clean_claim": False,
        "changes_349_selection": False, "changes_210_or_218": False,
        "verdict": "DESCRIPTIVE_DIAGNOSTIC_COMPLETE_NO_RESELECTION",
    }
    source_receipt = {
        "probability_path": str(PROBABILITY_RELATIVE),
        "probability_sha256": sha256_file(data_root / PROBABILITY_RELATIVE),
        "settlement_path": str(SETTLEMENT_RELATIVE),
        "settlement_sha256": sha256_file(data_root / SETTLEMENT_RELATIVE),
        "causal_cells_sha256": stable_frame_sha(causal),
        "match_support_sha256": stable_frame_sha(matches),
        "preoutcome_sha256": stable_frame_sha(frozen),
        "settled_bundles_sha256": stable_frame_sha(settled),
        "proxy_grade": "RETROSPECTIVE_RELATIVE_PROXY",
        "upstream_gate_lineage": "CONDITIONAL_ON_2023_LABEL_CONFIRMED_MAPPING_ACCEPTANCE",
        "chronology_clean": False,
    }
    tables = {
        "match_support.parquet": matches,
        "preoutcome_bundles.parquet": frozen,
        "settled_bundles.parquet": settled,
        "support_attribution.parquet": attribution,
        "coverage_ledger.csv": coverage,
        "annual_diagnostic_matrix.csv": matrix,
        "capital_paths.csv": paths,
        "replacement_signal_diagnostic.csv": signal,
    }
    for name, frame in tables.items():
        _write_table(output / name, frame)
    _write_json(output / "source_receipt.json", source_receipt)
    _write_json(output / "diagnostic_receipt.json", receipt)
    deliveries = write_delivery(repo_root, output, matrix, paths, coverage, signal, receipt)
    artifacts = [output / name for name in tables] + [
        output / "source_receipt.json", output / "diagnostic_receipt.json", *deliveries
    ]
    _write_json(
        output / "MANIFEST.json",
        {
            "contract": CONTRACT_ID,
            "files": {
                str(path.relative_to(repo_root)): {
                    "sha256": sha256_file(path), "bytes": path.stat().st_size,
                }
                for path in sorted(artifacts)
            },
        },
    )
    if sha256_file(frozen_receipt_path) != frozen_hash_before:
        raise AssertionError("build altered #349 freeze receipt")
    return receipt


def _assert_equal(actual: pd.DataFrame, expected: pd.DataFrame, keys: list[str]) -> None:
    left = actual.sort_values(keys, kind="stable").reset_index(drop=True)
    right = expected.sort_values(keys, kind="stable").reset_index(drop=True)
    pd.testing.assert_frame_equal(
        left, right, check_dtype=False, check_exact=False, rtol=0, atol=1e-8
    )


def _verify_settlement_economics(
    bundles: pd.DataFrame, attribution: pd.DataFrame,
) -> bool:
    grouped = {
        (str(issue), int(n), int(r)): group
        for (issue, n, r), group in attribution.groupby(["issue", "n", "r"], sort=False)
    }
    for row in bundles.itertuples(index=False):
        legs = grouped[(str(row.issue), int(row.n), int(row.r))]
        included = bool(legs["included"].all())
        expected_gross = 0.0
        if included:
            expected_gross = (
                units_per_ticket(int(row.n)) * STAKE_PER_UNIT_CNY * PAYOUT_FACTOR
                * float(legs["winning_sp"].prod())
            )
        if not np.isclose(float(row.gross_cny), expected_gross, rtol=0, atol=1e-8):
            return False
        if not np.isclose(
            float(row.pnl_cny), float(row.gross_cny) - float(row.stake_cny),
            rtol=0, atol=1e-8,
        ):
            return False
    return True


def verify_package(repo_root: Path, output: Path, data_root: Path | None = None) -> dict[str, bool]:
    repo_root, output = repo_root.resolve(), output.resolve()
    data_root = locate_data_root(repo_root, data_root)
    checks: dict[str, bool] = {}
    manifest = json.loads((output / "MANIFEST.json").read_text(encoding="utf-8"))
    expected = _expected_artifacts(repo_root, output)
    checks["manifest_exact_nonempty"] = set(manifest.get("files", {})) == expected and bool(expected)
    checks["manifest_hashes"] = all(
        (repo_root / relative).exists()
        and sha256_file(repo_root / relative) == evidence["sha256"]
        and (repo_root / relative).stat().st_size == evidence["bytes"]
        for relative, evidence in manifest.get("files", {}).items()
    )
    checks["frozen_349_receipt"] = (
        sha256_file(repo_root / FROZEN_349_RECEIPT) == FROZEN_349_RECEIPT_SHA256
        and json.loads((repo_root / FROZEN_349_RECEIPT).read_text())["selected_r_by_n"]
        == FROZEN_349_SELECTED_R
    )
    source = json.loads((output / "source_receipt.json").read_text(encoding="utf-8"))
    checks["source_hashes"] = (
        source["probability_sha256"] == sha256_file(data_root / PROBABILITY_RELATIVE)
        and source["settlement_sha256"] == sha256_file(data_root / SETTLEMENT_RELATIVE)
    )
    checks["exposed_lineage_disclosed"] = (
        source["upstream_gate_lineage"]
        == "CONDITIONAL_ON_2023_LABEL_CONFIRMED_MAPPING_ACCEPTANCE"
        and source["chronology_clean"] is False
    )

    causal = load_causal_cells(data_root, years=YEARS)
    matches = prepare_support_matches(causal)
    frozen, freeze_coverage = freeze_diagnostic(matches)
    settlement = load_settlement(data_root, sorted(frozen["issue"].astype(str).unique()))
    settled_raw, attribution, _ = settle_bundles(frozen, matches, settlement)
    settled, common_coverage = common_settled_bundles(settled_raw)
    matrix, paths = annual_matrix(settled)
    signal = replacement_signal_diagnostic(attribution, settled)
    coverage = common_coverage.merge(
        freeze_coverage[["issue", "issue_year", "n", "available_matches", "status"]].rename(
            columns={"status": "freeze_status"}
        ), on=["issue", "issue_year", "n"], how="left", validate="many_to_one",
    )
    checks["source_bound_frames"] = all(
        (
            source["causal_cells_sha256"] == stable_frame_sha(causal),
            source["match_support_sha256"] == stable_frame_sha(matches),
            source["preoutcome_sha256"] == stable_frame_sha(frozen),
            source["settled_bundles_sha256"] == stable_frame_sha(settled),
        )
    )
    for name, expected_frame, keys in (
        ("match_support", matches, ["issue", "match_idx"]),
        ("preoutcome_bundles", frozen, ["issue", "n", "r"]),
        ("settled_bundles", settled, ["issue", "n", "r"]),
        ("support_attribution", attribution, ["issue", "n", "r", "match_idx"]),
    ):
        _assert_equal(pd.read_parquet(output / f"{name}.parquet"), expected_frame, keys)
    accepted_dev_pre = pd.read_parquet(
        repo_root / "results/multin_fixed_rn/development_preoutcome.parquet"
    )
    accepted_dev = pd.read_parquet(
        repo_root / "results/multin_fixed_rn/development_bundles.parquet"
    )
    accepted_eval = pd.read_parquet(
        repo_root / "results/multin_fixed_rn/evaluation_bundles.parquet"
    )
    frozen_columns = [
        "issue", "issue_year", "n", "r", "selected_match_ids", "support_json",
        "ticket_count", "units_per_ticket", "funded_units", "planned_stake_cny",
    ]
    bundle_columns = frozen_columns + [
        "settlement_status", "stake_cny", "gross_cny", "pnl_cny", "hit", "miss_count",
    ]
    new_dev_pre = frozen[frozen["issue_year"].eq(2022) & frozen["n"].isin(TARGET_N_VALUES)]
    accepted_dev_pre = accepted_dev_pre[accepted_dev_pre["n"].isin(TARGET_N_VALUES)]
    _assert_equal(new_dev_pre[frozen_columns], accepted_dev_pre[frozen_columns], ["issue", "n", "r"])
    new_dev = settled_raw[
        settled_raw["issue_year"].eq(2022) & settled_raw["n"].isin(TARGET_N_VALUES)
    ]
    accepted_dev = accepted_dev[accepted_dev["n"].isin(TARGET_N_VALUES)]
    _assert_equal(new_dev[bundle_columns], accepted_dev[bundle_columns], ["issue", "n", "r"])
    new_eval_r0 = settled_raw[
        settled_raw["issue_year"].isin((2023, 2024))
        & settled_raw["n"].isin(TARGET_N_VALUES) & settled_raw["r"].eq(0)
    ]
    accepted_eval_r0 = accepted_eval[
        accepted_eval["n"].isin(TARGET_N_VALUES) & accepted_eval["r"].eq(0)
    ]
    _assert_equal(
        new_eval_r0[bundle_columns], accepted_eval_r0[bundle_columns], ["issue", "n", "r"]
    )
    checks["accepted_349_exact_parity"] = True
    _assert_equal(
        pd.read_csv(output / "annual_diagnostic_matrix.csv", dtype={"period": str}),
        matrix, ["n", "r", "period"],
    )
    _assert_equal(
        pd.read_csv(output / "capital_paths.csv", dtype={"period": str, "issue": str}),
        paths, ["n", "r", "period", "path_index"],
    )
    _assert_equal(
        pd.read_csv(output / "coverage_ledger.csv", dtype={"issue": str}),
        coverage, ["n", "issue_year", "issue"],
    )
    _assert_equal(
        pd.read_csv(output / "replacement_signal_diagnostic.csv", dtype={"period": str}),
        signal, ["n", "r", "period"],
    )
    checks["source_recomputed_outputs"] = True
    expected_keys = {
        (n, r, period)
        for n in TARGET_N_VALUES for r in range(n + 1) for period in PERIODS
    }
    actual_keys = set(map(tuple, matrix[["n", "r", "period"]].itertuples(index=False, name=None)))
    checks["complete_88_row_keyspace"] = len(matrix) == 88 and actual_keys == expected_keys
    r0 = matrix[matrix["r"].eq(0)]
    checks["r0_zero_contrasts"] = bool(
        r0[[
            "lift_vs_r0_cny", "armwise_ex_largest_lift_vs_r0_cny",
            "largest_abs_paired_delta_sensitivity_cny",
            "hit_rate_lift_vs_r0",
        ]].eq(0).all().all()
    )
    checks["matched_denominators"] = all(
        group["settled_issues"].nunique() == 1
        for _, group in matrix.groupby(["n", "period"], sort=False)
    )
    checks["ticket_and_budget_semantics"] = all(
        tickets_for_n(n) == 2**n
        and len(binary_design(n)) == 2**n
        and units_per_ticket(n) * tickets_for_n(n) == FUNDED_UNITS
        for n in TARGET_N_VALUES
    ) and bool(settled["stake_cny"].eq(ISSUE_STAKE_CNY).all())
    checks["ticket_level_once_payout"] = _verify_settlement_economics(settled, attribution)
    receipt = json.loads((output / "diagnostic_receipt.json").read_text(encoding="utf-8"))
    checks["scope_boundary"] = (
        receipt["diagnostic_only"] is True
        and receipt["pooled_reselection_performed"] is False
        and receipt["conditional_on_exposed_2023_translator_gate"] is True
        and receipt["chronology_clean_claim"] is False
        and receipt["changes_349_selection"] is False
        and receipt["changes_210_or_218"] is False
        and receipt["frozen_349_selected_r"] == FROZEN_349_SELECTED_R
    )
    if not all(checks.values()):
        raise AssertionError(
            f"verification failed: {[name for name, passed in checks.items() if not passed]}"
        )
    return checks
