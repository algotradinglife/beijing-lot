#!/usr/bin/env python3
"""Run chronological decomposed rare-event value heads for Issue #291."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.linear_model import LogisticRegression, Ridge, TweedieRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue291.modeling import (  # noqa: E402
    apply_platt_calibrator,
    derived_ticket_ev,
    deterministic_rare_event_sample,
    fit_platt_calibrator,
    reliability_table,
    weighted_probability_metrics,
)

CATEGORICAL = ["selector", "outcome_mode", "generator", "n", "k"]
CONTEXT = [
    "issue_match_count",
    "issue_probability_entropy_mean",
    "issue_probability_max_mean",
    "issue_divergence_abs_mean",
    "issue_divergence_abs_max",
    "issue_native_line_abs_mean",
    "issue_books_mean",
]
BASE_NUMERIC = [
    "ticket_index",
    "ticket_probability_product",
    "ticket_divergence_sum",
    "negative_log_probability_product",
    "geometric_mean_probability",
    *CONTEXT,
]
CANDIDATE_NUMERIC = [
    "candidate_rank",
    "parent_ticket_index",
    "protected_leg",
    "selected_outcome_position",
    "alternative_outcome_position",
    "selected_probability",
    "alternative_probability",
    "probability_delta",
    "selected_divergence",
    "alternative_divergence",
    "divergence_delta",
    "match_entropy",
    "proposal_margin_delta",
    "parent_ticket_probability_product",
    "candidate_probability_product",
    "negative_log_probability_product",
    "geometric_mean_probability",
    "parent_negative_log_probability_product",
    "candidate_probability_ratio_to_parent",
    *CONTEXT,
]
SHARED = [
    "issue",
    "issue_year",
    "subset_id",
    "action_key",
    "hit",
    "stake_cny",
    "gross_cny",
    "pnl_cny",
    *CATEGORICAL,
]
MODEL_SPECS = {
    "ACTION_LOGIT_RIDGE": "action",
    "DATA_LOGIT_RIDGE": "linear",
    "DATA_HGB": "nonlinear",
}
ENGINEERED = {
    "negative_log_probability_product",
    "geometric_mean_probability",
    "parent_negative_log_probability_product",
    "candidate_probability_ratio_to_parent",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "results/issue-286")
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-291")
    parser.add_argument("--oof-start", type=int, default=2019)
    parser.add_argument("--negative-per-action", type=int, default=24)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipt286 = json.loads((source / "settlement_receipt.json").read_text())
    if receipt286["sealed_years_opened"]:
        raise RuntimeError("upstream settlement receipt opened the sealed period")

    metrics: list[dict[str, object]] = []
    reliability: list[pd.DataFrame] = []
    ranking: list[dict[str, object]] = []
    ranking_paths: list[pd.DataFrame] = []
    ranking_tickets: list[pd.DataFrame] = []
    ledger: list[pd.DataFrame] = []
    sample_hashes: dict[str, str] = {}
    for domain, filename, identity, numeric in (
        ("BASE", "base_settlement_labels.parquet", "ticket_identity", BASE_NUMERIC),
        (
            "PROTECTION",
            "candidate_settlement_labels.parquet",
            "candidate_identity",
            CANDIDATE_NUMERIC,
        ),
    ):
        path = source / filename
        sample_path = output / f"{domain.lower()}_training_sample.parquet"
        sample = _build_training_sample(
            path,
            identity_column=identity,
            numeric=numeric,
            negative_per_action=args.negative_per_action,
        )
        sample.to_parquet(sample_path, index=False)
        sample_hashes[domain] = _sha256(sample_path)
        for year in range(args.oof_start, 2024):
            train = sample.loc[sample["issue_year"].lt(year - 1)].copy()
            calibration = sample.loc[sample["issue_year"].eq(year - 1)].copy()
            test = _read_year(path, year, identity, numeric)
            if train.empty or calibration.empty or test.empty:
                raise RuntimeError(f"insufficient chronological split for {domain} {year}")
            test["issue_weight"] = 1.0 / test.groupby("issue")["issue"].transform("size")
            for model_name, kind in MODEL_SPECS.items():
                features = CATEGORICAL if kind == "action" else [*CATEGORICAL, *numeric]
                probability_model = _probability_model(kind, features)
                gross_model = _gross_model(kind, features)
                direct_model = _regression_model(kind, features)
                probability_model.fit(
                    train[features],
                    train["hit"],
                    model__sample_weight=train["issue_weight"],
                )
                calibration_raw = probability_model.predict_proba(calibration[features])[:, 1]
                calibrator = fit_platt_calibrator(
                    calibration_raw,
                    calibration["hit"].to_numpy(int),
                    calibration["issue_weight"].to_numpy(float),
                )
                positive = train.loc[train["hit"].eq(1)].copy()
                if positive.empty:
                    raise RuntimeError(f"no positive gross rows for {domain} {year}")
                positive["positive_issue_weight"] = 1.0 / positive.groupby("issue")[
                    "issue"
                ].transform("size")
                gross_model.fit(
                    positive[features],
                    positive["gross_cny"],
                    model__sample_weight=positive["positive_issue_weight"],
                )
                direct_model.fit(
                    train[features],
                    train["pnl_cny"],
                    model__sample_weight=train["issue_weight"],
                )
                raw = probability_model.predict_proba(test[features])[:, 1]
                probability = apply_platt_calibrator(raw, calibrator)
                gross = np.clip(gross_model.predict(test[features]), 0.0, None)
                expected_value = derived_ticket_ev(probability, gross)
                direct_pnl = direct_model.predict(test[features])
                scored = test[
                    [
                        "issue",
                        "issue_year",
                        "action_key",
                        identity,
                        "hit",
                        "gross_cny",
                        "pnl_cny",
                        "issue_weight",
                        "n",
                        "k",
                        "selector",
                        "outcome_mode",
                        "generator",
                        *(["selected_divergence", "alternative_probability"] if domain == "PROTECTION" else []),
                        *( ["ticket_probability_product"] if domain == "BASE" else ["candidate_probability_product"] ),
                    ]
                ].copy()
                scored["predicted_probability"] = probability
                scored["predicted_conditional_gross_cny"] = gross
                scored["predicted_ev_cny"] = expected_value
                scored["predicted_direct_pnl_cny"] = direct_pnl
                probability_metric = weighted_probability_metrics(
                    scored["hit"].to_numpy(int),
                    probability,
                    scored["issue_weight"].to_numpy(float),
                )
                hit_mask = scored["hit"].eq(1).to_numpy()
                metrics.append(
                    {
                        "domain": domain,
                        "model": model_name,
                        "oof_year": year,
                        "train_end_year": year - 2,
                        "calibration_year": year - 1,
                        **probability_metric,
                        "conditional_gross_mae_cny": float(
                            np.mean(np.abs(gross[hit_mask] - scored.loc[hit_mask, "gross_cny"]))
                        )
                        if hit_mask.any()
                        else np.nan,
                        "mean_predicted_ev_cny": float(
                            np.average(expected_value, weights=scored["issue_weight"])
                        ),
                        "platt_intercept": calibrator.intercept,
                        "platt_coefficient": calibrator.coefficient,
                        "platt_fitted": calibrator.fitted,
                    }
                )
                table = reliability_table(scored, probability_column="predicted_probability")
                table["domain"] = domain
                table["model"] = model_name
                table["oof_year"] = year
                reliability.append(table)
                for score_name, score_column in (
                    ("HIT_PROBABILITY", "predicted_probability"),
                    ("DECOMPOSED_EV", "predicted_ev_cny"),
                    ("DIRECT_PNL", "predicted_direct_pnl_cny"),
                ):
                    ranking.extend(
                        _ranking_rows(
                            scored,
                            domain=domain,
                            model=model_name,
                            score_name=score_name,
                            score_column=score_column,
                            identity_column=identity,
                            year=year,
                            path_sink=ranking_paths,
                            ticket_sink=ranking_tickets,
                        )
                    )
                if model_name == "ACTION_LOGIT_RIDGE":
                    ranking.extend(
                        _control_ranking_rows(
                            scored,
                            domain=domain,
                            identity_column=identity,
                            year=year,
                            path_sink=ranking_paths,
                            ticket_sink=ranking_tickets,
                        )
                    )
                if year == 2023:
                    ledger.append(
                        _top_issue_ledger(
                            scored,
                            domain=domain,
                            model=model_name,
                            identity_column=identity,
                        )
                    )
                print(
                    f"domain={domain} year={year} model={model_name} "
                    f"brier={probability_metric['brier']:.8f} "
                    f"event={probability_metric['weighted_event_rate']:.8f}",
                    flush=True,
                )

    outputs = {
        "model_metrics": output / "model_metrics.csv",
        "reliability": output / "reliability_bins.csv",
        "ranking": output / "ranking_metrics.csv",
        "ranking_paths": output / "ranking_issue_paths.csv",
        "ranking_tickets": output / "ranking_selected_tickets.csv",
        "attribution_2023": output / "issue_2023_top_predictions.csv",
    }
    pd.DataFrame(metrics).to_csv(outputs["model_metrics"], index=False)
    pd.concat(reliability, ignore_index=True).to_csv(outputs["reliability"], index=False)
    pd.DataFrame(ranking).to_csv(outputs["ranking"], index=False)
    pd.concat(ranking_paths, ignore_index=True).to_csv(
        outputs["ranking_paths"], index=False
    )
    pd.concat(ranking_tickets, ignore_index=True).to_csv(
        outputs["ranking_tickets"], index=False
    )
    pd.concat(ledger, ignore_index=True).to_csv(outputs["attribution_2023"], index=False)
    receipt = {
        "contract": "BJ-UNIFIED-RARE-EVENT-VALUE-001/oof-v1",
        "independent_unit": "BEIJING_ISSUE",
        "development_years": list(range(2014, 2024)),
        "oof_years": list(range(args.oof_start, 2024)),
        "calibration": "PREVIOUS_YEAR_PLATT_ONLY",
        "negative_per_issue_action": args.negative_per_action,
        "issue_weighting": "EACH_TRAINING_AND_TEST_ISSUE_SUMS_TO_ONE",
        "sealed_years_opened": [],
        "input_sha256": {
            "base_labels": _sha256(source / "base_settlement_labels.parquet"),
            "candidate_labels": _sha256(source / "candidate_settlement_labels.parquet"),
            "issue286_settlement_receipt": _sha256(source / "settlement_receipt.json"),
        },
        "training_sample_sha256": sample_hashes,
        "output_sha256": {name: _sha256(path) for name, path in outputs.items()},
    }
    _atomic_json(receipt, output / "oof_receipt.json")
    return 0


def _build_training_sample(
    path: Path,
    *,
    identity_column: str,
    numeric: list[str],
    negative_per_action: int,
) -> pd.DataFrame:
    frames = []
    for year in range(2014, 2024):
        frame = _read_year(path, year, identity_column, numeric)
        frame = frame.rename(columns={identity_column: "candidate_identity"})
        frames.append(
            deterministic_rare_event_sample(
                frame,
                negative_per_action=negative_per_action,
            )
        )
    return pd.concat(frames, ignore_index=True)


def _read_year(
    path: Path,
    year: int,
    identity_column: str,
    numeric: list[str],
) -> pd.DataFrame:
    columns = [*SHARED, identity_column, *(value for value in numeric if value not in ENGINEERED)]
    frame = pd.read_parquet(
        path,
        filters=[("issue_year", "==", year), ("settlement_valid", "==", True)],
        columns=list(dict.fromkeys(columns)),
    )
    frame["issue"] = frame["issue"].astype(str)
    if identity_column == "ticket_identity":
        probability_product = frame["ticket_probability_product"].to_numpy(float)
    else:
        probability_product = frame["candidate_probability_product"].to_numpy(float)
        parent_product = np.clip(
            frame["parent_ticket_probability_product"].to_numpy(float), 1e-15, 1.0
        )
        frame["parent_negative_log_probability_product"] = -np.log(parent_product)
        frame["candidate_probability_ratio_to_parent"] = probability_product / parent_product
    bounded_product = np.clip(probability_product, 1e-15, 1.0)
    frame["negative_log_probability_product"] = -np.log(bounded_product)
    frame["geometric_mean_probability"] = np.exp(
        np.log(bounded_product) / frame["n"].to_numpy(float)
    )
    if frame["issue_year"].ge(2024).any():
        raise RuntimeError("sealed 2024+ outcome entered Issue #291")
    return frame


def _transformer(features: list[str]) -> ColumnTransformer:
    categorical = [feature for feature in CATEGORICAL if feature in features]
    numeric = [feature for feature in features if feature not in categorical]
    return ColumnTransformer(
        [
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                categorical,
            ),
            ("numeric", StandardScaler(), numeric),
        ],
        remainder="drop",
    )


def _probability_model(kind: str, features: list[str]) -> Pipeline:
    model = (
        HistGradientBoostingClassifier(
            max_iter=100,
            max_leaf_nodes=15,
            min_samples_leaf=50,
            learning_rate=0.05,
            l2_regularization=10.0,
            random_state=291_001,
        )
        if kind == "nonlinear"
        else LogisticRegression(C=0.1, solver="lbfgs", max_iter=400)
    )
    return Pipeline([("features", _transformer(features)), ("model", model)])


def _regression_model(kind: str, features: list[str]) -> Pipeline:
    model = (
        HistGradientBoostingRegressor(
            max_iter=100,
            max_leaf_nodes=15,
            min_samples_leaf=50,
            learning_rate=0.05,
            l2_regularization=10.0,
            random_state=291_002,
        )
        if kind == "nonlinear"
        else Ridge(alpha=10.0)
    )
    return Pipeline([("features", _transformer(features)), ("model", model)])


def _gross_model(kind: str, features: list[str]) -> Pipeline:
    """Estimate the conditional mean gross directly on its positive support."""

    model = (
        HistGradientBoostingRegressor(
            loss="poisson",
            max_iter=100,
            max_leaf_nodes=15,
            min_samples_leaf=30,
            learning_rate=0.05,
            l2_regularization=10.0,
            random_state=291_003,
        )
        if kind == "nonlinear"
        else TweedieRegressor(
            power=1.0,
            link="log",
            alpha=10.0,
            max_iter=1_000,
        )
    )
    return Pipeline([("features", _transformer(features)), ("model", model)])


def _ranking_rows(
    frame: pd.DataFrame,
    *,
    domain: str,
    model: str,
    score_name: str,
    score_column: str,
    identity_column: str,
    year: int,
    path_sink: list[pd.DataFrame],
    ticket_sink: list[pd.DataFrame],
) -> list[dict[str, object]]:
    return _summarize_ranked(
        _deduplicated_rank(frame, score_column, identity_column),
        domain=domain,
        model=model,
        score=score_name,
        year=year,
        path_sink=path_sink,
        ticket_sink=ticket_sink,
    )


def _control_ranking_rows(
    frame: pd.DataFrame,
    *,
    domain: str,
    identity_column: str,
    year: int,
    path_sink: list[pd.DataFrame],
    ticket_sink: list[pd.DataFrame],
) -> list[dict[str, object]]:
    work = frame.copy()
    market = (
        "ticket_probability_product" if domain == "BASE" else "candidate_probability_product"
    )
    work["_random"] = pd.util.hash_pandas_object(
        work[["issue", identity_column]], index=False
    ).to_numpy(dtype="uint64") / np.iinfo("uint64").max
    controls = [("MARKET_PRODUCT", market), ("RANDOM", "_random")]
    if domain == "PROTECTION":
        work["_adverse"] = -work["selected_divergence"] + work["alternative_probability"]
        controls.append(("ADVERSE_DIVERGENCE", "_adverse"))
    work["_oracle"] = work["hit"] * 1e12 + work["gross_cny"]
    controls.append(("UNATTAINABLE_ORACLE", "_oracle"))
    rows = []
    for name, column in controls:
        rows.extend(
            _summarize_ranked(
                _deduplicated_rank(work, column, identity_column),
                domain=domain,
                model="CONTROL",
                score=name,
                year=year,
                path_sink=path_sink,
                ticket_sink=ticket_sink,
            )
        )
    return rows


def _deduplicated_rank(
    frame: pd.DataFrame,
    score_column: str,
    identity_column: str,
) -> pd.DataFrame:
    columns = [
        "issue",
        "action_key",
        "n",
        "k",
        "selector",
        "outcome_mode",
        "generator",
        "hit",
        "gross_cny",
        "pnl_cny",
        identity_column,
        score_column,
    ]
    ranked = frame[columns].sort_values(
        ["issue", score_column, identity_column],
        ascending=[True, False, True],
        kind="stable",
    )
    ranked = ranked.drop_duplicates(["issue", identity_column], keep="first")
    ranked["rank"] = ranked.groupby("issue").cumcount() + 1
    return ranked


def _summarize_ranked(
    ranked: pd.DataFrame,
    *,
    domain: str,
    model: str,
    score: str,
    year: int,
    path_sink: list[pd.DataFrame],
    ticket_sink: list[pd.DataFrame],
) -> list[dict[str, object]]:
    rows = []
    for budget in (1, 4, 16, 64):
        selected = ranked.loc[ranked["rank"].le(budget)]
        selected_tickets = selected.copy()
        selected_tickets["domain"] = domain
        selected_tickets["model"] = model
        selected_tickets["score"] = score
        selected_tickets["oof_year"] = year
        selected_tickets["ticket_budget_per_issue"] = budget
        ticket_sink.append(selected_tickets)
        issue = selected.groupby("issue", as_index=False).agg(
            tickets=("rank", "size"),
            hits=("hit", "sum"),
            gross_cny=("gross_cny", "sum"),
            pnl_cny=("pnl_cny", "sum"),
        )
        issue["domain"] = domain
        issue["model"] = model
        issue["score"] = score
        issue["oof_year"] = year
        issue["ticket_budget_per_issue"] = budget
        issue["stake_cny"] = 2.0 * issue["tickets"]
        path_sink.append(issue)
        total_pnl = float(issue["pnl_cny"].sum())
        largest = float(issue["pnl_cny"].max())
        rows.append(
            {
                "domain": domain,
                "model": model,
                "score": score,
                "oof_year": year,
                "ticket_budget_per_issue": budget,
                "issues": len(issue),
                "tickets": int(issue["tickets"].sum()),
                "hits": int(issue["hits"].sum()),
                "hit_rate": float(issue["hits"].sum() / issue["tickets"].sum()),
                "gross_cny": float(issue["gross_cny"].sum()),
                "pnl_cny": total_pnl,
                "ex_largest_issue_pnl_cny": total_pnl - largest,
                "positive_issue_fraction": float((issue["pnl_cny"] > 0).mean()),
            }
        )
    return rows


def _top_issue_ledger(
    frame: pd.DataFrame,
    *,
    domain: str,
    model: str,
    identity_column: str,
) -> pd.DataFrame:
    top = _deduplicated_rank(frame, "predicted_ev_cny", identity_column)
    top = top.loc[top["rank"].le(16)].copy()
    details = frame[
        [
            "issue",
            identity_column,
            "predicted_probability",
            "predicted_conditional_gross_cny",
            "predicted_ev_cny",
            "predicted_direct_pnl_cny",
        ]
    ].sort_values(["issue", "predicted_ev_cny"], ascending=[True, False])
    details = details.drop_duplicates(["issue", identity_column], keep="first")
    top = top.merge(details, on=["issue", identity_column], how="left", validate="one_to_one")
    top["domain"] = domain
    top["model"] = model
    return top


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(payload: dict[str, object], path: Path) -> None:
    temporary = path.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
