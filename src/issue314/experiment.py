"""Chronological CORE/TAIL soft-MoE experiment for Issue #314."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from issue209.dynamic_policy import (
    ActionSpec as LegacyActionSpec,
    _derived_seed,
    generate_tickets as generate_legacy_tickets,
)

from .data import (
    OUTCOMES,
    issue_features,
    load_pre_event_units,
    load_settlement,
    source_receipt,
)
from .experts import (
    EXPERTS,
    K_ANCHORS,
    ExpertSpec,
    expert_registry,
    generate_tickets,
    settle_tickets,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "results/issue-314"
ISSUE312_PATHS = ROOT / "results/issue-312/capital_paths.csv"
MODEL_SEEDS = (31401, 31402, 31403, 31404, 31405)
# Use the already-frozen #312 physical seeds so the inherited comparator is an
# exact numeric control rather than a similarly named reconstruction.
EVALUATION_SEEDS = tuple(range(312101, 312132))
FEATURE_COLUMNS = (
    "n_matches",
    "books_mean",
    "line_abs_mean",
    "line_std",
    "market_top_mean",
    "market_top_q90",
    "entropy_mean",
    "divergence_abs_mean",
    "divergence_abs_q90",
    "divergence_signed_mean",
    "value_best_mean",
    "value_best_q90",
    "accepted_fraction",
)
OUTCOME_INDEX = {outcome: index for index, outcome in enumerate(OUTCOMES)}


def freeze() -> dict[str, object]:
    """Fit through 2022, validate 2023, and freeze all 2024 decisions pre-outcome."""

    OUTPUT.mkdir(parents=True, exist_ok=True)
    units = load_pre_event_units((2019, 2020, 2021, 2022, 2023, 2024))
    features = issue_features(units)
    features.to_csv(OUTPUT / "issue_features_2019_2024.csv", index=False)
    expert_registry().to_csv(OUTPUT / "expert_registry.csv", index=False)
    support = features.groupby(["issue_year", "experiment_role"], as_index=False).agg(
        issues=("issue", "nunique"),
        minimum_matches=("n_matches", "min"),
        median_matches=("n_matches", "median"),
        maximum_matches=("n_matches", "max"),
    )
    support.to_csv(OUTPUT / "support_receipt.csv", index=False)
    (OUTPUT / "pre_event_source_receipt.json").write_text(
        json.dumps(source_receipt(units), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    development_units = units[units["issue_year"].le(2023)].copy()
    development_issues = set(development_units["issue"])
    settlement = load_settlement(development_issues)
    surface_frames = []
    for year in (2019, 2020, 2021, 2022, 2023):
        year_path = OUTPUT / f"development_expert_surface_{year}.parquet"
        if year_path.exists():
            year_surface = pd.read_parquet(year_path)
        else:
            year_surface = build_expert_surface(
                development_units,
                settlement,
                years=(year,),
                seeds=MODEL_SEEDS,
            )
            temporary = year_path.with_suffix(".tmp.parquet")
            year_surface.to_parquet(temporary, index=False)
            temporary.replace(year_path)
        surface_frames.append(year_surface)
    surface = pd.concat(surface_frames, ignore_index=True)
    surface.to_parquet(OUTPUT / "development_expert_surface.parquet", index=False)
    training = aggregate_surface(surface, features)
    training.to_parquet(OUTPUT / "development_action_labels.parquet", index=False)

    candidate_rows = []
    fitted: dict[str, object] = {}
    for family in ("RIDGE", "HGB", "MLP"):
        model = fit_model(training[training["issue_year"].le(2021)], family)
        fitted[family] = model
        predictions = predict_action_rows(
            model,
            features[features["issue_year"].eq(2022)],
        )
        for tail_fraction in (0.05, 0.10, 0.15):
            allocations = make_allocations(
                predictions,
                condition=f"SCREEN_{family}_T{int(tail_fraction * 100):02d}",
                tail_fraction=tail_fraction,
            )
            paths, _ = evaluate_allocations(
                allocations,
                units,
                settlement,
                seeds=MODEL_SEEDS,
            )
            summary = summarize_paths(paths).iloc[0]
            candidate_rows.append(
                {
                    "model_family": family,
                    "tail_fraction": tail_fraction,
                    **summary.to_dict(),
                }
            )
    screening = pd.DataFrame(candidate_rows).sort_values(
        ["median_terminal_capital_cny", "median_ex_largest_pnl_cny"],
        ascending=False,
    )
    screening.to_csv(OUTPUT / "screening_2022.csv", index=False)
    winner = screening.iloc[0]
    selected_family = str(winner["model_family"])
    selected_tail = float(winner["tail_fraction"])

    final_model = fit_model(training[training["issue_year"].le(2022)], selected_family)
    joblib.dump(final_model, OUTPUT / "frozen_gate.joblib")
    prediction_frames = []
    allocations = []
    for year in (2023, 2024):
        prediction = predict_action_rows(
            final_model,
            features[features["issue_year"].eq(year)],
        )
        prediction["prediction_year"] = year
        prediction_frames.append(prediction)
        allocations.append(
            make_allocations(
                prediction,
                condition="RAW_LEARNED_MOE",
                tail_fraction=selected_tail,
            )
        )
    predictions = pd.concat(prediction_frames, ignore_index=True)
    predictions.to_parquet(OUTPUT / "frozen_action_predictions.parquet", index=False)
    learned_allocations = pd.concat(allocations, ignore_index=True)

    validation_allocations = learned_allocations[
        learned_allocations["issue_year"].eq(2023)
    ]
    controls = control_allocations(
        features[features["issue_year"].eq(2023)],
        selected_tail,
    )
    validation_all = pd.concat([validation_allocations, controls], ignore_index=True)
    validation_paths, validation_near = evaluate_allocations(
        validation_all,
        units,
        settlement,
        seeds=EVALUATION_SEEDS,
        near_miss_conditions={"RAW_LEARNED_MOE", "PORTABLE_N7_K512_WOR"},
    )
    validation_paths = pd.concat(
        [validation_paths, exact_issue312_control_paths()], ignore_index=True
    ).sort_values(["condition", "seed", "issue_year", "issue"])
    validation_paths.to_csv(OUTPUT / "validation_capital_paths_2023.csv", index=False)
    validation_near.to_parquet(
        OUTPUT / "validation_near_miss_2023.parquet", index=False
    )
    validation_summary = summarize_paths(validation_paths)
    validation_summary.to_csv(OUTPUT / "validation_summary_2023.csv", index=False)
    learned = validation_summary[
        validation_summary["condition"].eq("RAW_LEARNED_MOE")
    ].iloc[0]
    fixed = validation_summary[
        validation_summary["condition"].eq("FIXED_N7_K512_WOR")
    ].iloc[0]
    validation_pass = bool(
        learned["median_terminal_capital_cny"] > fixed["median_terminal_capital_cny"]
        and learned["median_ex_largest_pnl_cny"] >= fixed["median_ex_largest_pnl_cny"]
        and learned["paired_seed_wins_vs_fixed"]
        >= math.ceil(0.60 * len(EVALUATION_SEEDS))
    )
    frozen_source = (
        "RAW_LEARNED_MOE" if validation_pass else "PORTABLE_N7_K512_WOR"
    )
    terminal_learned = learned_allocations[
        learned_allocations["issue_year"].eq(2024)
    ].copy()
    terminal_control = control_allocations(
        features[features["issue_year"].eq(2024)], selected_tail
    )
    terminal_primary = (
        terminal_learned
        if validation_pass
        else terminal_control[
            terminal_control["condition"].eq("PORTABLE_N7_K512_WOR")
        ]
    ).copy()
    terminal_primary["condition"] = "GUARDED_PRIMARY"
    terminal_allocations = pd.concat(
        [terminal_learned, terminal_control, terminal_primary], ignore_index=True
    )
    terminal_allocations = append_factor_resets(terminal_allocations, terminal_learned)
    terminal_allocations.to_json(
        OUTPUT / "frozen_allocations_2024.jsonl", orient="records", lines=True
    )
    freeze_payload = {
        "contract": "BJ-UNIFIED-CORE-TAIL-MOE-001/v1",
        "selected_model_family": selected_family,
        "selected_tail_fraction": selected_tail,
        "validation_pass": validation_pass,
        "guarded_source": frozen_source,
        "validation_control": "EXACT_ISSUE312_FIXED_N7_K512_WOR",
        "terminal_control": "PORTABLE_N7_K512_WOR",
        "terminal_control_limitation": (
            "same N7/K512/WOR exposure and current causal value input; "
            "#312 fitted-value identities do not exist for 2024"
        ),
        "2024_feature_issues": int(terminal_learned["issue"].nunique()),
        "2024_outcome_columns_opened": [],
        "allocation_sha256": _sha(OUTPUT / "frozen_allocations_2024.jsonl"),
        "model_sha256": _sha(OUTPUT / "frozen_gate.joblib"),
        "independent_unit": "BEIJING_ISSUE",
        "nuisance_seeds_nested": list(EVALUATION_SEEDS),
    }
    (OUTPUT / "freeze_receipt.json").write_text(
        json.dumps(freeze_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_manifest(stage="freeze")
    return freeze_payload


def settle() -> dict[str, object]:
    """Settle the immutable 2024 allocations and publish the terminal decision."""

    freeze_receipt = json.loads((OUTPUT / "freeze_receipt.json").read_text())
    if (
        _sha(OUTPUT / "frozen_allocations_2024.jsonl")
        != freeze_receipt["allocation_sha256"]
    ):
        raise AssertionError("frozen 2024 allocation drift")
    units = load_pre_event_units((2019, 2020, 2021, 2022, 2023, 2024))
    terminal_units = units[units["issue_year"].eq(2024)].copy()
    settlement = load_settlement(set(terminal_units["issue"]))
    allocations = pd.read_json(
        OUTPUT / "frozen_allocations_2024.jsonl", lines=True, dtype={"issue": str}
    )
    allocations, correction = apply_terminal_diagnostic_correction(allocations)
    (OUTPUT / "terminal_diagnostic_correction_receipt.json").write_text(
        json.dumps(correction, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    paths, near = evaluate_allocations(
        allocations,
        terminal_units,
        settlement,
        seeds=EVALUATION_SEEDS,
        near_miss_conditions={
            "RAW_LEARNED_MOE",
            "GUARDED_PRIMARY",
            "PORTABLE_N7_K512_WOR",
        },
    )
    paths.to_csv(OUTPUT / "terminal_capital_paths_2024.csv", index=False)
    near.to_parquet(OUTPUT / "terminal_near_miss_2024.parquet", index=False)
    summary = summarize_paths(paths)
    summary.to_csv(OUTPUT / "terminal_summary_2024.csv", index=False)
    attribution = factor_attribution(paths)
    attribution.to_csv(OUTPUT / "matched_factor_attribution_2024.csv", index=False)
    source = source_receipt(terminal_units, settlement)
    (OUTPUT / "terminal_source_receipt.json").write_text(
        json.dumps(source, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    replay = ticket_replay_receipt(paths)
    (OUTPUT / "ticket_replay_receipt.json").write_text(
        json.dumps(replay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    primary = _summary_row(summary, "GUARDED_PRIMARY")
    learned = _summary_row(summary, "RAW_LEARNED_MOE")
    fixed = _summary_row(summary, "PORTABLE_N7_K512_WOR")
    lower_exposure = learned["median_stake_cny"] < fixed["median_stake_cny"] - 1e-9
    moe_signal = bool(
        learned["median_terminal_capital_cny"] > fixed["median_terminal_capital_cny"]
        and learned["median_ex_largest_pnl_cny"] >= fixed["median_ex_largest_pnl_cny"]
        and not lower_exposure
        and learned["median_terminal_capital_cny"] > 100_000.0
    )
    structural = _has_structural_signal(attribution)
    promotable = bool(moe_signal and freeze_receipt["validation_pass"])
    verdict = (
        "CANDIDATE_SIGNAL"
        if promotable
        else "MOE_SIGNAL"
        if moe_signal
        else "STRUCTURAL_SIGNAL"
        if structural
        else "NO_LEARNABLE_INCREMENT"
    )
    decision = {
        "verdict": verdict,
        "promotable": promotable,
        "guarded_source": freeze_receipt["guarded_source"],
        "validation_pass": bool(freeze_receipt["validation_pass"]),
        "terminal_issues": int(paths["issue"].nunique()),
        "guarded_terminal_capital_cny": primary["median_terminal_capital_cny"],
        "raw_learned_terminal_capital_cny": learned["median_terminal_capital_cny"],
        "fixed_n7_terminal_capital_cny": fixed["median_terminal_capital_cny"],
        "paired_seed_median_lift_raw_vs_fixed_cny": _paired_median(
            paths, "RAW_LEARNED_MOE", "PORTABLE_N7_K512_WOR"
        ),
        "raw_learned_median_stake_cny": learned["median_stake_cny"],
        "fixed_n7_median_stake_cny": fixed["median_stake_cny"],
        "lower_exposure_explanation": lower_exposure,
        "maximum_coverage_depth": 2,
        "payout_factor": 0.65,
        "payout_application": "ONCE_PER_WINNING_COMPLETE_TICKET",
        "unlock_issue_210": promotable,
    }
    payload = {"issue": 314, "decision": decision}
    (OUTPUT / "decision.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _plot_paths(paths, OUTPUT / "capital_paths_2024.png")
    _plot_frontier(summary, OUTPUT / "risk_return_frontier_2024.png")
    _plot_near_miss(near, OUTPUT / "near_miss_attribution_2024.png")
    write_manifest(stage="terminal")
    return payload


def build_expert_surface(
    units: pd.DataFrame,
    settlement: pd.DataFrame,
    *,
    years: tuple[int, ...],
    seeds: tuple[int, ...],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for issue, group in units[units["issue_year"].isin(years)].groupby(
        "issue", sort=True
    ):
        local_settlement = settlement[settlement["issue"].eq(issue)]
        for spec in EXPERTS:
            if len(group) < spec.n:
                continue
            for seed in seeds:
                matches, outcomes, _, receipt = generate_tickets(
                    group, spec, k=max(K_ANCHORS), seed=seed
                )
                gross, correct, miss = settle_tickets(
                    matches, outcomes, group, local_settlement
                )
                cumulative = np.cumsum(gross - 2.0)
                for k in K_ANCHORS:
                    rows.append(
                        {
                            "issue": str(issue),
                            "issue_year": int(group["issue_year"].iloc[0]),
                            "source_temporal_role": str(
                                group["source_temporal_role"].iloc[0]
                            ),
                            "experiment_role": str(group["experiment_role"].iloc[0]),
                            "seed": seed,
                            "expert": spec.name,
                            "sleeve": spec.sleeve,
                            "n": spec.n,
                            "k": k,
                            "selector": spec.selector,
                            "outcome_direction": spec.outcome_direction,
                            "generator": spec.generator,
                            "pool_excess": spec.pool_excess,
                            "protection": spec.protection,
                            "protected_leg_count": spec.protected_leg_count,
                            "stake_cny": 2.0 * k,
                            "pnl_cny": float(cumulative[k - 1]),
                            "gross_cny": float(gross[:k].sum()),
                            "hit_count": int((miss[:k] == 0).sum()),
                            "miss_one_count": int((miss[:k] == 1).sum()),
                            "miss_two_count": int((miss[:k] == 2).sum()),
                            "natural_support": int(receipt["natural_support"]),
                        }
                    )
    return pd.DataFrame(rows).sort_values(
        ["issue_year", "issue", "expert", "k", "seed"]
    )


def aggregate_surface(surface: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    keys = [
        "issue",
        "issue_year",
        "source_temporal_role",
        "experiment_role",
        "expert",
        "sleeve",
        "n",
        "k",
        "selector",
        "outcome_direction",
        "generator",
        "pool_excess",
        "protection",
        "protected_leg_count",
    ]
    labels = surface.groupby(keys, as_index=False).agg(
        stake_cny=("stake_cny", "first"),
        mean_pnl_cny=("pnl_cny", "mean"),
        pnl_std_cny=("pnl_cny", "std"),
        positive_seed_fraction=("pnl_cny", lambda value: float((value > 0).mean())),
        tail_seed_fraction=(
            "gross_cny",
            lambda value: float(
                (value >= 5 * surface.loc[value.index, "stake_cny"]).mean()
            ),
        ),
    )
    labels["roi"] = labels["mean_pnl_cny"] / labels["stake_cny"]
    return labels.merge(
        features,
        on=["issue", "issue_year", "source_temporal_role", "experiment_role"],
        validate="many_to_one",
    )


def fit_model(training: pd.DataFrame, family: str):
    design = _design_matrix(training)
    target = training["roi"].clip(
        training["roi"].quantile(0.01), training["roi"].quantile(0.99)
    )
    if family == "RIDGE":
        estimator = Ridge(alpha=20.0)
    elif family == "HGB":
        estimator = HistGradientBoostingRegressor(
            max_iter=160,
            max_leaf_nodes=15,
            learning_rate=0.05,
            l2_regularization=5.0,
            random_state=314,
        )
    elif family == "MLP":
        estimator = MLPRegressor(
            hidden_layer_sizes=(32, 16),
            activation="tanh",
            alpha=0.2,
            early_stopping=True,
            max_iter=350,
            random_state=314,
        )
    else:
        raise ValueError(family)
    model = make_pipeline(StandardScaler(), estimator)
    model.fit(design, target)
    return {"family": family, "model": model, "columns": list(design.columns)}


def predict_action_rows(bundle, features: pd.DataFrame) -> pd.DataFrame:
    registry = expert_registry()
    rows = (
        features.assign(_key=1)
        .merge(registry.assign(_key=1), on="_key")
        .drop(columns="_key")
    )
    rows = (
        rows.assign(_key=1)
        .merge(pd.DataFrame({"k": K_ANCHORS, "_key": 1}), on="_key")
        .drop(columns="_key")
    )
    design = _design_matrix(rows).reindex(columns=bundle["columns"], fill_value=0.0)
    rows["predicted_roi"] = bundle["model"].predict(design)
    return rows


def make_allocations(
    predictions: pd.DataFrame, *, condition: str, tail_fraction: float
) -> pd.DataFrame:
    rows = []
    for issue, group in predictions.groupby("issue", sort=True):
        utility_by_k = []
        for k, local in group.groupby("k"):
            weights = _soft_weights(local, tail_fraction)
            utility_by_k.append(
                (float(np.dot(weights, local["predicted_roi"])), int(k), local, weights)
            )
        _, total_k, selected, weights = max(
            utility_by_k, key=lambda item: (item[0], item[1])
        )
        counts = _integer_counts(weights, total_k)
        rows.append(
            {
                "issue": str(issue),
                "issue_year": int(selected["issue_year"].iloc[0]),
                "condition": condition,
                "total_k": total_k,
                "tail_fraction": tail_fraction,
                "expert_counts": json.dumps(
                    {
                        expert: int(count)
                        for expert, count in zip(selected["name"], counts, strict=True)
                        if count > 0
                    },
                    sort_keys=True,
                ),
                "reset_factor": "NONE",
                "unique_cap": total_k,
            }
        )
    return pd.DataFrame(rows)


def control_allocations(features: pd.DataFrame, tail_fraction: float) -> pd.DataFrame:
    rows = []
    core = [spec.name for spec in EXPERTS if spec.sleeve == "CORE"]
    tail = [spec.name for spec in EXPERTS if spec.sleeve == "TAIL"]
    for issue in features.itertuples(index=False):
        fixed = {"LEGACY_N7_VALUE_WOR": 512}
        equal = _split_counts(core, 512)
        split = {**_split_counts(core, 461), **_split_counts(tail, 51)}
        for condition, counts in (
            ("PORTABLE_N7_K512_WOR", fixed),
            ("EQUAL_CORE_MIXTURE", equal),
            ("FIXED_CORE_TAIL_90_10", split),
        ):
            rows.append(
                {
                    "issue": str(issue.issue),
                    "issue_year": int(issue.issue_year),
                    "condition": condition,
                    "total_k": int(sum(counts.values())),
                    "tail_fraction": tail_fraction,
                    "expert_counts": json.dumps(counts, sort_keys=True),
                    "reset_factor": "NONE",
                    "unique_cap": int(sum(counts.values())),
                }
            )
    return pd.DataFrame(rows)


def append_factor_resets(
    allocation_frame: pd.DataFrame, learned: pd.DataFrame
) -> pd.DataFrame:
    frames = [allocation_frame]
    for factor in (
        "n",
        "generator",
        "candidate_selector",
        "outcome_direction",
        "coverage_protection",
    ):
        local = learned.copy()
        local["condition"] = f"RESET_{factor.upper()}"
        local["reset_factor"] = factor
        frames.append(local)
    local = learned.copy()
    local["condition"] = "RESET_K_STRUCTURE"
    local["unique_cap"] = np.minimum(local["total_k"], 512)
    frames.append(local)
    random = learned.copy()
    random["condition"] = "RANDOM_PROTECTION_CONTROL"
    random["reset_factor"] = "random_protection"
    frames.append(random)
    exposure = learned.copy()
    exposure["condition"] = "FIXED_EXPOSURE_512_DIAGNOSTIC"
    exposure["total_k"] = 512
    exposure["unique_cap"] = 512
    exposure["expert_counts"] = exposure["expert_counts"].map(
        lambda value: json.dumps(
            _rescale_counts(json.loads(value), 512), sort_keys=True
        )
    )
    frames.append(exposure)
    return pd.concat(frames, ignore_index=True)


def apply_terminal_diagnostic_correction(
    allocations: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Repair only the frozen fixed-exposure diagnostic's count reconciliation.

    The raw learned policy, guarded primary and portable control are byte-level
    untouched.  The correction is fully determined by the already-frozen
    `total_k=512` intent and expert proportions; it reads no outcome.
    """

    corrected = allocations.copy()
    mask = corrected["condition"].eq("FIXED_EXPOSURE_512_DIAGNOSTIC")
    before = corrected.loc[mask, "expert_counts"].map(
        lambda value: sum(json.loads(value).values())
    )
    corrected.loc[mask, "expert_counts"] = corrected.loc[
        mask, "expert_counts"
    ].map(
        lambda value: json.dumps(
            _rescale_counts(json.loads(value), 512), sort_keys=True
        )
    )
    after = corrected.loc[mask, "expert_counts"].map(
        lambda value: sum(json.loads(value).values())
    )
    unchanged = corrected.loc[~mask].equals(allocations.loc[~mask])
    if not after.eq(512).all() or not unchanged:
        raise AssertionError("terminal diagnostic correction escaped its scope")
    receipt = {
        "scope": "FIXED_EXPOSURE_512_DIAGNOSTIC_ONLY",
        "reason": "frozen total_k was 512 while expert_counts retained raw K",
        "rows_corrected": int(mask.sum()),
        "expert_count_total_before": sorted(int(value) for value in before.unique()),
        "expert_count_total_after": sorted(int(value) for value in after.unique()),
        "outcome_columns_used": [],
        "primary_policy_changed": False,
        "guarded_policy_changed": False,
        "portable_control_changed": False,
        "frozen_allocation_sha256": _sha(OUTPUT / "frozen_allocations_2024.jsonl"),
    }
    return corrected, receipt


def evaluate_allocations(
    allocations: pd.DataFrame,
    units: pd.DataFrame,
    settlement: pd.DataFrame,
    *,
    seeds: tuple[int, ...],
    near_miss_conditions: set[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    specs = {spec.name: spec for spec in EXPERTS}
    path_rows = []
    near_rows = []
    for allocation in allocations.itertuples(index=False):
        group = units[units["issue"].eq(str(allocation.issue))].reset_index(drop=True)
        local_settlement = settlement[settlement["issue"].eq(str(allocation.issue))]
        counts = json.loads(allocation.expert_counts)
        for seed in seeds:
            stake = gross_total = hits = miss_one = miss_two = 0.0
            reason_outside = reason_sampling = 0
            protection_cf_stake = protection_cf_gross = 0.0
            for expert, count in counts.items():
                if count <= 0:
                    continue
                if expert == "LEGACY_N7_VALUE_WOR":
                    matches, outcomes, support = _legacy_control_tickets(
                        group, k=count, seed=seed
                    )
                    gross, correct, miss = settle_tickets(
                        matches, outcomes, group, local_settlement
                    )
                    stake += 2.0 * count
                    gross_total += gross.sum()
                    hits += (miss == 0).sum()
                    miss_one += (miss == 1).sum()
                    miss_two += (miss == 2).sum()
                    if (
                        near_miss_conditions
                        and allocation.condition in near_miss_conditions
                    ):
                        outside, sampling, cf_stake, cf_gross = _near_miss_reasons(
                            matches,
                            outcomes,
                            miss,
                            group,
                            local_settlement,
                            support,
                        )
                        reason_outside += outside
                        reason_sampling += sampling
                        protection_cf_stake += cf_stake
                        protection_cf_gross += cf_gross
                    continue
                spec = specs[expert]
                factor = str(allocation.reset_factor)
                if factor in {
                    "n",
                    "generator",
                    "candidate_selector",
                    "outcome_direction",
                    "coverage_protection",
                }:
                    spec = spec.reset(factor)
                elif factor == "random_protection" and spec.protected_leg_count:
                    spec = ExpertSpec(**{**spec.__dict__, "protection": "RANDOM"})
                unique_cap = min(int(allocation.unique_cap), count)
                matches, outcomes, support, _ = generate_tickets(
                    group, spec, k=count, seed=seed, unique_cap=unique_cap
                )
                gross, correct, miss = settle_tickets(
                    matches, outcomes, group, local_settlement
                )
                stake += 2.0 * count
                gross_total += gross.sum()
                hits += (miss == 0).sum()
                miss_one += (miss == 1).sum()
                miss_two += (miss == 2).sum()
                if (
                    near_miss_conditions
                    and allocation.condition in near_miss_conditions
                ):
                    outside, sampling, cf_stake, cf_gross = _near_miss_reasons(
                        matches, outcomes, miss, group, local_settlement, support
                    )
                    reason_outside += outside
                    reason_sampling += sampling
                    protection_cf_stake += cf_stake
                    protection_cf_gross += cf_gross
            pnl = gross_total - stake
            path_rows.append(
                {
                    "issue": str(allocation.issue),
                    "issue_year": int(allocation.issue_year),
                    "condition": str(allocation.condition),
                    "seed": seed,
                    "stake_cny": stake,
                    "gross_cny": gross_total,
                    "pnl_cny": pnl,
                    "hit_count": int(hits),
                    "miss_one_count": int(miss_one),
                    "miss_two_count": int(miss_two),
                    "total_k": int(allocation.total_k),
                    "expert_hhi": _hhi(counts),
                }
            )
            if near_miss_conditions and allocation.condition in near_miss_conditions:
                near_rows.append(
                    {
                        "issue": str(allocation.issue),
                        "issue_year": int(allocation.issue_year),
                        "condition": str(allocation.condition),
                        "seed": seed,
                        "miss_one_count": int(miss_one),
                        "miss_two_count": int(miss_two),
                        "outcome_outside_support": int(reason_outside),
                        "finite_sampling_branch": int(reason_sampling),
                        "one_more_protection_stake_cny": protection_cf_stake,
                        "one_more_protection_gross_cny": protection_cf_gross,
                        "one_more_protection_pnl_cny": protection_cf_gross
                        - protection_cf_stake,
                    }
                )
    paths = pd.DataFrame(path_rows).sort_values(
        ["condition", "seed", "issue_year", "issue"]
    )
    return paths, pd.DataFrame(near_rows)


def summarize_paths(paths: pd.DataFrame) -> pd.DataFrame:
    rows = []
    baseline_condition = (
        "FIXED_N7_K512_WOR"
        if paths["condition"].eq("FIXED_N7_K512_WOR").any()
        else "PORTABLE_N7_K512_WOR"
    )
    fixed_seed = (
        paths[paths["condition"].eq(baseline_condition)]
        .groupby("seed")["pnl_cny"]
        .sum()
    )
    for condition, condition_rows in paths.groupby("condition", sort=True):
        seed_rows = []
        for seed, frame in condition_rows.groupby("seed"):
            frame = frame.sort_values(["issue_year", "issue"])
            pnl = frame["pnl_cny"].to_numpy(float)
            capital = 100_000.0 + np.cumsum(pnl)
            peak = np.maximum.accumulate(np.r_[100_000.0, capital])[1:]
            drawdown = peak - capital
            max_completed_recovery, open_underwater = _underwater_metrics(drawdown)
            seed_rows.append(
                {
                    "seed": seed,
                    "terminal": float(capital[-1]),
                    "stake": float(frame["stake_cny"].sum()),
                    "roi": float(pnl.sum() / frame["stake_cny"].sum()),
                    "max_drawdown": float(drawdown.max()),
                    "ex_largest": float(pnl.sum() - pnl.max()),
                    "positive_rate": float((pnl > 0).mean()),
                    "longest_losing": _longest(pnl < 0),
                    "worst_5": _worst_window(pnl, 5),
                    "worst_10": _worst_window(pnl, 10),
                    "worst_20": _worst_window(pnl, 20),
                    "underwater_issues": int((drawdown > 1e-9).sum()),
                    "max_completed_recovery": max_completed_recovery,
                    "open_underwater": open_underwater,
                    "longest_no_payout": _longest(
                        frame["hit_count"].to_numpy(int) == 0
                    ),
                    "any_payout_rate": float(frame["hit_count"].gt(0).mean()),
                    "ticket_hit_rate": float(
                        frame["hit_count"].sum() / frame["total_k"].sum()
                    ),
                    "hhi": float(frame["expert_hhi"].mean()),
                }
            )
        seeds = pd.DataFrame(seed_rows)
        wins = np.nan
        if condition != baseline_condition and not fixed_seed.empty:
            own = condition_rows.groupby("seed")["pnl_cny"].sum()
            wins = int((own - fixed_seed.reindex(own.index) > 0).sum())
        rows.append(
            {
                "condition": condition,
                "nuisance_seeds": int(len(seeds)),
                "issues": int(condition_rows["issue"].nunique()),
                "median_terminal_capital_cny": float(seeds["terminal"].median()),
                "median_stake_cny": float(seeds["stake"].median()),
                "median_turnover_roi": float(seeds["roi"].median()),
                "median_max_drawdown_cny": float(seeds["max_drawdown"].median()),
                "median_ex_largest_pnl_cny": float(seeds["ex_largest"].median()),
                "median_positive_issue_rate": float(seeds["positive_rate"].median()),
                "median_longest_losing_issues": float(seeds["longest_losing"].median()),
                "median_worst_5_pnl_cny": float(seeds["worst_5"].median()),
                "median_worst_10_pnl_cny": float(seeds["worst_10"].median()),
                "median_worst_20_pnl_cny": float(seeds["worst_20"].median()),
                "median_time_underwater_issues": float(
                    seeds["underwater_issues"].median()
                ),
                "median_maximum_completed_recovery_issues": float(
                    seeds["max_completed_recovery"].median()
                ),
                "median_open_terminal_underwater_issues": float(
                    seeds["open_underwater"].median()
                ),
                "median_longest_no_payout_issues": float(
                    seeds["longest_no_payout"].median()
                ),
                "median_any_payout_issue_rate": float(
                    seeds["any_payout_rate"].median()
                ),
                "median_ticket_hit_rate": float(seeds["ticket_hit_rate"].median()),
                "median_expert_hhi": float(seeds["hhi"].median()),
                "paired_seed_wins_vs_fixed": wins,
            }
        )
    return pd.DataFrame(rows)


def factor_attribution(paths: pd.DataFrame) -> pd.DataFrame:
    primary = paths[paths["condition"].eq("RAW_LEARNED_MOE")][
        ["issue", "seed", "pnl_cny"]
    ].rename(columns={"pnl_cny": "primary"})
    rows = []
    for condition in sorted(
        value for value in paths["condition"].unique() if value.startswith("RESET_")
    ):
        control = paths[paths["condition"].eq(condition)][
            ["issue", "seed", "pnl_cny"]
        ].rename(columns={"pnl_cny": "control"})
        paired = primary.merge(control, on=["issue", "seed"], validate="one_to_one")
        seed_lift = (
            paired.assign(lift=paired["primary"] - paired["control"])
            .groupby("seed")["lift"]
            .sum()
        )
        rows.append(
            {
                "reset": condition,
                "median_seed_lift_cny": float(seed_lift.median()),
                "positive_seed_fraction": float(seed_lift.gt(0).mean()),
                "matched_issue_seed_rows": int(len(paired)),
            }
        )
    return pd.DataFrame(rows)


def ticket_replay_receipt(paths: pd.DataFrame) -> dict[str, object]:
    stake_error = float((paths["stake_cny"] - 2.0 * paths["total_k"]).abs().max())
    accounting_error = float(
        (paths["gross_cny"] - paths["stake_cny"] - paths["pnl_cny"]).abs().max()
    )
    return {
        "ticket_rows": int(paths["total_k"].sum()),
        "path_rows": int(len(paths)),
        "stake_reconciliation_max_abs_cny": stake_error,
        "accounting_reconciliation_max_abs_cny": accounting_error,
        "payout_factor": 0.65,
        "payout_application": "once per complete winning ticket",
        "pass": stake_error < 1e-9 and accounting_error < 1e-8,
    }


def write_manifest(*, stage: str) -> None:
    files = {}
    for path in sorted(OUTPUT.iterdir()):
        if (
            path.name == "manifest.json"
            or not path.is_file()
            or path.suffix
            not in {".csv", ".json", ".jsonl", ".parquet", ".png", ".joblib"}
        ):
            continue
        files[path.name] = {"bytes": path.stat().st_size, "sha256": _sha(path)}
    (OUTPUT / "manifest.json").write_text(
        json.dumps(
            {"issue": 314, "stage": stage, "files": files}, indent=2, ensure_ascii=False
        )
        + "\n",
        encoding="utf-8",
    )


def _design_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    numeric = frame[list(FEATURE_COLUMNS)].astype(float).copy()
    numeric["n"] = frame["n"].astype(float).to_numpy()
    numeric["log_k"] = np.log(frame["k"].astype(float).to_numpy())
    numeric["pool_excess"] = frame["pool_excess"].astype(float).to_numpy()
    numeric["protected_leg_count"] = (
        frame["protected_leg_count"].astype(float).to_numpy()
    )
    categorical = pd.get_dummies(
        frame[
            [
                "name" if "name" in frame.columns else "expert",
                "sleeve",
                "selector",
                "outcome_direction",
                "generator",
                "protection",
            ]
        ].astype(str),
        prefix=["expert", "sleeve", "selector", "outcome", "generator", "protection"],
        dtype=float,
    )
    return pd.concat(
        [numeric.reset_index(drop=True), categorical.reset_index(drop=True)], axis=1
    )


def _legacy_control_tickets(
    group: pd.DataFrame, *, k: int, seed: int
) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """Retain the inherited all-branch N7/WOR comparator outside learned actions."""

    market = group[[f"q_eu_bjline_{c}" for c in OUTCOMES]].to_numpy(float)
    line = group[[f"q_line_only_control_{c}" for c in OUTCOMES]].to_numpy(float)
    value = market / np.clip(line, 1e-6, None)
    issue = str(group["issue"].iloc[0])
    matches, outcomes = generate_legacy_tickets(
        value,
        market,
        LegacyActionSpec(7, k, "WEIGHTED_WOR"),
        seed=_derived_seed(seed, issue, "FIXED_N7_K512_WOR"),
    )
    if len(matches) != k:
        raise AssertionError("legacy fixed control did not fund exactly K tickets")
    support = pd.DataFrame(
        {
            "match_position": np.arange(len(group), dtype=int),
            "match_idx": group["match_idx"].to_numpy(int),
            "coverage_depth": 3,
            "main_outcome": "3",
            "protection_outcome": "1",
            "protection_reason": "INHERITED_CONTROL_ALL_BRANCHES",
        }
    )
    return matches, outcomes, support


def exact_issue312_control_paths() -> pd.DataFrame:
    """Load the immutable #312 N7/K512/WOR comparator on exact 2023 support."""

    frame = pd.read_csv(ISSUE312_PATHS, dtype={"issue": str})
    frame = frame[frame["condition"].eq("FIXED_N7_K512_WOR")].copy()
    frame = frame[frame["seed"].isin(EVALUATION_SEEDS)].copy()
    expected_issues = 48
    if frame["issue"].nunique() != expected_issues:
        raise AssertionError("#312 exact control issue support drifted")
    if frame["seed"].nunique() != len(EVALUATION_SEEDS):
        raise AssertionError("#312 exact control seed support drifted")
    frame["miss_one_count"] = 0
    frame["miss_two_count"] = 0
    frame["total_k"] = frame["executed_tickets"].astype(int)
    frame["expert_hhi"] = 1.0
    return frame[
        [
            "issue",
            "issue_year",
            "condition",
            "seed",
            "stake_cny",
            "gross_cny",
            "pnl_cny",
            "hit_count",
            "miss_one_count",
            "miss_two_count",
            "total_k",
            "expert_hhi",
        ]
    ]


def _soft_weights(local: pd.DataFrame, tail_fraction: float) -> np.ndarray:
    result = np.zeros(len(local), dtype=float)
    for sleeve, budget in (("CORE", 1.0 - tail_fraction), ("TAIL", tail_fraction)):
        index = np.flatnonzero(local["sleeve"].eq(sleeve).to_numpy())
        score = local.iloc[index]["predicted_roi"].to_numpy(float)
        score = np.exp(np.clip((score - score.max()) / 0.20, -30, 0))
        result[index] = budget * score / score.sum()
    return result


def _integer_counts(weights: np.ndarray, total: int) -> np.ndarray:
    raw = weights * total
    counts = np.floor(raw).astype(int)
    for index in np.argsort(-(raw - counts))[: total - counts.sum()]:
        counts[index] += 1
    return counts


def _split_counts(names: list[str], total: int) -> dict[str, int]:
    counts = _integer_counts(np.full(len(names), 1.0 / len(names)), total)
    return {
        name: int(count) for name, count in zip(names, counts, strict=True) if count
    }


def _rescale_counts(counts: dict[str, int], total: int) -> dict[str, int]:
    """Preserve mixture proportions while enforcing a diagnostic ticket total."""

    names = sorted(counts)
    weights = np.asarray([counts[name] for name in names], dtype=float)
    weights /= weights.sum()
    scaled = _integer_counts(weights, total)
    return {
        name: int(count)
        for name, count in zip(names, scaled, strict=True)
        if count > 0
    }


def _hhi(counts: dict[str, int]) -> float:
    values = np.asarray(list(counts.values()), dtype=float)
    weights = values / values.sum()
    return float(np.square(weights).sum())


def _near_miss_reasons(matches, outcomes, miss, group, settlement, support):
    realized_map = (
        settlement.set_index("match_idx")["result_code"].astype(str).to_dict()
    )
    support_map = {}
    for row in support.itertuples(index=False):
        if int(row.coverage_depth) == 3:
            allowed = set(OUTCOME_INDEX.values())
        else:
            allowed = {OUTCOME_INDEX[str(row.main_outcome)]}
            if str(row.protection_outcome):
                allowed.add(OUTCOME_INDEX[str(row.protection_outcome)])
        support_map[int(row.match_position)] = allowed
    outside = sampling = 0
    cf_stake = cf_gross = 0.0
    sp_map = settlement.set_index("match_idx")["settlement_sp"].to_dict()
    for index in np.flatnonzero((miss == 1) | (miss == 2)):
        wrong = []
        for position, chosen in zip(matches[index], outcomes[index], strict=True):
            realized = OUTCOME_INDEX.get(
                realized_map.get(int(group.iloc[position]["match_idx"]), ""), -1
            )
            if chosen != realized:
                wrong.append((int(position), realized))
                if realized not in support_map.get(int(position), set()):
                    outside += 1
                else:
                    sampling += 1
        if miss[index] == 1 and wrong:
            cf_stake += 2.0
            ticket_sp = [
                float(sp_map.get(int(group.iloc[position]["match_idx"]), np.nan))
                for position in matches[index]
            ]
            if np.isfinite(ticket_sp).all():
                cf_gross += 2.0 * 0.65 * float(np.prod(ticket_sp))
    return outside, sampling, cf_stake, cf_gross


def _summary_row(summary: pd.DataFrame, condition: str) -> dict[str, object]:
    return summary[summary["condition"].eq(condition)].iloc[0].to_dict()


def _paired_median(paths: pd.DataFrame, primary: str, control: str) -> float:
    grouped = (
        paths[paths["condition"].isin([primary, control])]
        .groupby(["condition", "seed"])["pnl_cny"]
        .sum()
        .unstack("condition")
    )
    return float((grouped[primary] - grouped[control]).median())


def _has_structural_signal(attribution: pd.DataFrame) -> bool:
    """Accept any factor meeting both lift and paired-seed stability gates."""

    return bool(
        (
            attribution["median_seed_lift_cny"].gt(0)
            & attribution["positive_seed_fraction"].ge(0.60)
        ).any()
    )


def _longest(mask: Iterable[bool]) -> int:
    best = current = 0
    for value in mask:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def _worst_window(values: np.ndarray, window: int) -> float:
    if len(values) < window:
        return float(values.sum())
    return float(np.convolve(values, np.ones(window), mode="valid").min())


def _underwater_metrics(drawdown: np.ndarray) -> tuple[int, int]:
    """Return longest completed recovery and terminal open-underwater length."""

    completed = current = 0
    for value in drawdown > 1e-9:
        if value:
            current += 1
        else:
            completed = max(completed, current)
            current = 0
    return completed, current


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plot_paths(paths: pd.DataFrame, target: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 6))
    for condition in (
        "GUARDED_PRIMARY",
        "RAW_LEARNED_MOE",
        "PORTABLE_N7_K512_WOR",
        "EQUAL_CORE_MIXTURE",
    ):
        local = (
            paths[paths["condition"].eq(condition)]
            .groupby("issue", as_index=False)["pnl_cny"]
            .median()
            .sort_values("issue")
        )
        if not local.empty:
            ax.plot(
                range(len(local)), 100_000 + local["pnl_cny"].cumsum(), label=condition
            )
    ax.axhline(100_000, color="black", lw=0.8)
    ax.legend(fontsize=8)
    ax.set(title="#314 terminal 2024 capital path", xlabel="issue", ylabel="CNY")
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_frontier(summary: pd.DataFrame, target: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(
        summary["median_max_drawdown_cny"], summary["median_terminal_capital_cny"]
    )
    for row in summary.itertuples(index=False):
        ax.annotate(
            row.condition,
            (row.median_max_drawdown_cny, row.median_terminal_capital_cny),
            fontsize=6,
        )
    ax.axhline(100_000, color="black", lw=0.8)
    ax.set(
        xlabel="median max drawdown CNY",
        ylabel="median terminal capital CNY",
        title="#314 risk-return frontier",
    )
    fig.tight_layout()
    fig.savefig(target, dpi=160)
    plt.close(fig)


def _plot_near_miss(near: pd.DataFrame, target: Path) -> None:
    grouped = near.groupby("condition")[
        [
            "miss_one_count",
            "miss_two_count",
            "outcome_outside_support",
            "finite_sampling_branch",
        ]
    ].sum()
    ax = grouped.plot.bar(figsize=(11, 6))
    ax.set(title="#314 2024 near-miss attribution", ylabel="ticket/leg count")
    ax.figure.tight_layout()
    ax.figure.savefig(target, dpi=160)
    plt.close(ax.figure)
