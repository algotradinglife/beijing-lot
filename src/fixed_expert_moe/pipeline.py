"""End-to-end reproducible Issue #332 pipeline."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd

from issue314.experts import expert_registry

from .contract import (
    CONTRACT_ID,
    EVALUATION_SEEDS,
    EVALUATION_YEARS,
    ISSUE,
    MODEL_SEEDS,
    SURFACE_COUNTS,
)
from .data import (
    aggregate_model_labels,
    assemble_learning_panel,
    assert_strict_chronology,
    build_counterfactual_surface,
    load_sources,
)
from .evaluation import (
    accepted_baseline_comparison,
    allocation_attribution,
    auxiliary_metrics,
    bootstrap_issue_lift,
    capital_paths,
    make_allocations,
    paired_lifts,
    policy_summary,
    settle_allocations,
)
from .model import chronological_predictions
from .reporting import write_notebook, write_report


def build_package(repo_root: Path, output: Path | None = None) -> dict[str, object]:
    repo_root = repo_root.resolve()
    output = output or repo_root / "results/fixed_expert_moe"
    output.mkdir(parents=True, exist_ok=True)
    units, settlement, state = load_sources(repo_root)

    model_surface_path = output / "model_surface.parquet"
    if model_surface_path.exists():
        model_surface = pd.read_parquet(model_surface_path)
        _validate_cached_surface(model_surface, MODEL_SEEDS, (512,))
    else:
        model_surface = build_counterfactual_surface(
            units,
            settlement,
            seeds=MODEL_SEEDS,
            counts=(512,),
        )
    labels = aggregate_model_labels(model_surface)
    panel = assemble_learning_panel(units, labels, state)
    assert_strict_chronology(panel)
    model_result = chronological_predictions(panel)
    allocations = make_allocations(panel, model_result.predictions)

    evaluation_units = units[units["issue_year"].isin(EVALUATION_YEARS)]
    evaluation_surface_path = output / "evaluation_surface.parquet"
    if evaluation_surface_path.exists():
        evaluation_surface = pd.read_parquet(evaluation_surface_path)
        _validate_cached_surface(
            evaluation_surface, EVALUATION_SEEDS, SURFACE_COUNTS
        )
    else:
        evaluation_surface = build_counterfactual_surface(
            evaluation_units,
            settlement,
            seeds=EVALUATION_SEEDS,
            counts=SURFACE_COUNTS,
        )
    settled = settle_allocations(allocations, evaluation_surface)
    paths = capital_paths(settled)
    summary = policy_summary(settled)
    paired = paired_lifts(settled)
    bootstrap = bootstrap_issue_lift(settled)
    auxiliary = auxiliary_metrics(model_result.predictions)
    attribution = allocation_attribution(allocations)
    accepted = accepted_baseline_comparison(repo_root, settled)
    decision = decide(summary, paired, bootstrap, settled, accepted)

    expert_registry().to_csv(output / "expert_registry.csv", index=False)
    model_surface.to_parquet(output / "model_surface.parquet", index=False)
    labels.to_parquet(output / "expert_labels.parquet", index=False)
    panel.to_parquet(output / "learning_panel.parquet", index=False)
    model_result.predictions.to_parquet(output / "oof_predictions.parquet", index=False)
    allocations.to_parquet(output / "allocations.parquet", index=False)
    evaluation_surface.to_parquet(output / "evaluation_surface.parquet", index=False)
    settled.to_parquet(output / "settlement.parquet", index=False)
    paths.to_parquet(output / "capital_paths.parquet", index=False)
    summary.to_csv(output / "policy_summary.csv", index=False)
    paired.to_csv(output / "paired_lifts.csv", index=False)
    bootstrap.to_csv(output / "bootstrap_lift.csv", index=False)
    auxiliary.to_csv(output / "auxiliary_metrics.csv", index=False)
    attribution.to_csv(output / "allocation_attribution.csv", index=False)
    accepted.to_csv(output / "accepted_baseline_comparison.csv", index=False)
    (output / "model_receipt.json").write_text(
        json.dumps(model_result.receipt, separators=(",", ":"), sort_keys=True) + "\n"
    )
    (output / "decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n"
    )
    write_report(
        repo_root,
        decision,
        summary,
        paired,
        bootstrap,
        auxiliary,
        attribution,
        paths,
        accepted,
    )
    write_notebook(repo_root)
    _write_receipts(repo_root, output, units, state, decision)
    return decision


def decide(
    summary: pd.DataFrame,
    paired: pd.DataFrame,
    bootstrap: pd.DataFrame,
    settlement: pd.DataFrame,
    accepted: pd.DataFrame,
) -> dict[str, object]:
    def capital(condition: str, year: int) -> float:
        rows = summary[
            summary["condition"].eq(condition) & summary["issue_year"].eq(year)
        ]
        return float(rows["terminal_capital_cny"].iloc[0])

    def lift(condition: str, baseline: str, year: int) -> float:
        rows = paired[
            paired["condition"].eq(condition)
            & paired["baseline"].eq(baseline)
            & paired["issue_year"].eq(year)
        ]
        return float(rows["median_lift_cny"].iloc[0])

    static = ("BEST_SINGLE_EXPERT", "EQUAL_MIX", "STATIC_SHRUNK_MIX")
    lag_consistent = all(lift("LAGGED_MULTITASK_MOE", "CURRENT_ONLY_MOE", year) > 0 for year in (2023, 2024))
    lag_beats_static = all(
        capital("LAGGED_MULTITASK_MOE", year) > max(capital(base, year) for base in static)
        for year in (2023, 2024)
    )
    bootstrap_rows = bootstrap[
        bootstrap["condition"].eq("LAGGED_MULTITASK_MOE")
        & bootstrap["issue_year"].isin([2023, 2024])
    ]
    bootstrap_positive = bool(
        len(bootstrap_rows) == 2
        and bootstrap_rows["bootstrap_p025_cny"].gt(0).all()
    )
    current_beats_static = all(
        capital("CURRENT_ONLY_MOE", year) > max(capital(base, year) for base in static)
        for year in (2023, 2024)
    )
    static_diversifies = all(
        max(capital("EQUAL_MIX", year), capital("STATIC_SHRUNK_MIX", year))
        > capital("BEST_SINGLE_EXPERT", year)
        for year in (2023, 2024)
    )
    if lag_consistent and lag_beats_static and bootstrap_positive:
        disposition = "CAUSAL_MOE_SIGNAL"
        interpretation = (
            "Lagged dense state adds a year-consistent, bootstrap-positive increment over "
            "the identical current-only gate and every static control. A small neural gate "
            "is now justified, but only on this frozen interface."
        )
        next_interface = "NEURAL_GATE_ON_FROZEN_MULTITASK_STATE"
    elif current_beats_static:
        disposition = "CURRENT_ONLY_EXPERT_SIGNAL"
        interpretation = (
            "Dynamic expert choice adds value, but lagged state is not independently proven. "
            "The next test should learn richer current issue × match representations while "
            "retaining the lag ablation."
        )
        next_interface = "NEURAL_CURRENT_CROSS_SECTION_WITH_LAG_ABLATION"
    elif static_diversifies:
        disposition = "STATIC_DIVERSIFICATION_ONLY"
        interpretation = (
            "Static diversification survives, while state-dependent gating does not. The next "
            "highest-information experiment is a richer match-level action representation, not "
            "a higher-capacity regime gate."
        )
        next_interface = "MATCH_LEVEL_ACTION_VALUE_REPRESENTATION"
    else:
        disposition = "NO_EXPERT_MIX_SIGNAL"
        interpretation = ""
        next_interface = "NEURAL_TOP2_RESIDUAL_ACTION_VALUE"

    issue_mean = settlement.groupby(["condition", "issue_year", "issue"], as_index=False)["pnl_cny"].mean()
    lag = issue_mean[issue_mean["condition"].eq("LAGGED_MULTITASK_MOE")]
    current = issue_mean[issue_mean["condition"].eq("CURRENT_ONLY_MOE")].rename(columns={"pnl_cny": "current_pnl"})
    matched = lag.merge(current[["issue_year", "issue", "current_pnl"]], on=["issue_year", "issue"])
    matched["lift"] = matched["pnl_cny"] - matched["current_pnl"]
    ex_largest = {
        str(year): float(group["lift"].sum() - max(0.0, group["lift"].max()))
        for year, group in matched.groupby("issue_year")
    }
    promotion = bool(
        disposition == "CAUSAL_MOE_SIGNAL"
        and ex_largest.get("2023", 0.0) > 0
        and ex_largest.get("2024", 0.0) > 0
    )
    accepted_rows = accepted[
        accepted["condition"].eq("LAGGED_MULTITASK_MOE")
        & accepted["issue_year"].isin([2023, 2024])
    ]
    accepted_baseline_beaten = bool(
        len(accepted_rows) == 2
        and accepted_rows["matched_lift_cny"].gt(0).all()
        and accepted_rows["ex_largest_lift_cny"].gt(0).all()
    )
    accepted_lift = {
        str(int(row.issue_year)): {
            "matched_lift_cny": float(row.matched_lift_cny),
            "ex_largest_lift_cny": float(row.ex_largest_lift_cny),
            "matched_issues": int(row.matched_issues),
        }
        for row in accepted_rows.itertuples(index=False)
    }
    if disposition == "NO_EXPERT_MIX_SIGNAL":
        interpretation = (
            "Dense hit and near-miss structure is learnable, but it does not map to stable payout "
            "value through this fixed expert library. The lagged soft mixture has only a small raw "
            f"2023 lift against accepted Top-2 ({accepted_lift.get('2023', {}).get('matched_lift_cny', 0.0):.0f} CNY) "
            f"that becomes {accepted_lift.get('2023', {}).get('ex_largest_lift_cny', 0.0):.0f} CNY ex-largest, "
            f"then trails it by {abs(accepted_lift.get('2024', {}).get('matched_lift_cny', 0.0)):.0f} CNY in 2024. "
            "This falsifies more capacity on the same mixture-weight interface. The next experiment "
            "will keep the accepted Top-2 N7 baseline and learn residual match/outcome/ticket value directly."
        )
    promotion = bool(promotion and accepted_baseline_beaten)
    return {
        "issue": ISSUE,
        "contract_id": CONTRACT_ID,
        "claim_boundary": "HISTORICAL_EXPANDING_DIAGNOSTIC_2020_2024",
        "disposition": disposition,
        "interpretation": interpretation,
        "next_interface": next_interface,
        "lag_consistent": lag_consistent,
        "lag_beats_static": lag_beats_static,
        "bootstrap_positive": bootstrap_positive,
        "current_beats_static": current_beats_static,
        "static_diversifies": static_diversifies,
        "accepted_top2_baseline_beaten": accepted_baseline_beaten,
        "accepted_top2_matched_lift": accepted_lift,
        "lag_vs_current_ex_largest_lift_cny": ex_largest,
        "promotion": promotion,
        "unlock_210": promotion,
        "payout_factor": 0.65,
        "payout_application": "ONCE_PER_WINNING_COMPLETE_TICKET",
        "evaluation_seeds": len(EVALUATION_SEEDS),
    }


def _write_receipts(
    repo_root: Path,
    output: Path,
    units: pd.DataFrame,
    state: pd.DataFrame,
    decision: dict[str, object],
) -> None:
    runtime = Path(os.environ.get("BEIJING_LOT_RUNTIME_ROOT", repo_root)).resolve()
    sources = {
        "market_panel": runtime / "data/derived/bj238_divergence_materializer_v4r3/inference/relative_horizon_view.parquet",
        "settlement": runtime / "data/derived/beidan_xlsm/beidan_xlsm.sqlite",
        "regime_state": repo_root / "results/regime_state/state_ledger.parquet",
        "expert_code": repo_root / "src/issue314/experts.py",
    }
    receipt = {
        "contract_id": CONTRACT_ID,
        "issues": int(units["issue"].nunique()),
        "years": sorted(units["issue_year"].unique().astype(int).tolist()),
        "state_issues": int(state["issue"].nunique()),
        "model_seeds": list(MODEL_SEEDS),
        "evaluation_seeds": list(EVALUATION_SEEDS),
        "source_hashes": {name: _sha256(path) for name, path in sources.items()},
        "decision": decision["disposition"],
    }
    (output / "freeze_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    files = sorted(
        path
        for path in output.iterdir()
        if path.is_file()
        and path.name not in {"SHA256SUMS.json", "MANIFEST.json"}
    )
    hashes = {path.name: _sha256(path) for path in files}
    (output / "SHA256SUMS.json").write_text(
        json.dumps(hashes, indent=2, sort_keys=True) + "\n"
    )
    manifest = {
        "issue": ISSUE,
        "contract_id": CONTRACT_ID,
        "files": sorted(path.name for path in output.iterdir() if path.is_file()),
        "decision": decision,
    }
    (output / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_cached_surface(
    surface: pd.DataFrame,
    seeds: tuple[int, ...],
    counts: tuple[int, ...],
) -> None:
    if set(surface["seed"].unique()) != set(seeds):
        raise AssertionError("cached surface seed contract mismatch")
    if set(surface["k"].unique()) != set(counts):
        raise AssertionError("cached surface ticket-count contract mismatch")
