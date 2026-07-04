#!/usr/bin/env python3
"""Analyze high-N directional clusters and q/conf ML feature value.

This script has two independent parts:

1. Replay existing N7 EV-framework tickets through directional-cluster gates.
2. Train walk-forward-safe ML models on 2014-2022 leg rows and evaluate
   q_score/confidence/LL-style features on 2023-2025.

No settlement-derived columns are used as model features.  Settlement columns
are only labels or reporting fields.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import hcp_bucket, md_table


N7_STRATEGIES = [
    "ev_m0p95_p0p85_full_opt__budget256_fractional",
    "ev_m0p95_p0p8_full_opt__budget256_fractional",
]


def issue_year(issue: object) -> int:
    text = str(issue)
    if len(text) >= 2 and text[:2].isdigit():
        yy = int(text[:2])
        return 2000 + yy if yy < 80 else 1900 + yy
    return 0


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


LEG_RE = re.compile(r"(?P<match_id>\d+):(?P<code>[013]+)@(?P<hcp>-?\d+(?:\.\d+)?)")


def parse_ticket_legs(raw: object) -> list[tuple[str, str, float]]:
    out = []
    for item in str(raw).split(";"):
        match = LEG_RE.fullmatch(item.strip())
        if not match:
            continue
        out.append((match.group("match_id"), match.group("code"), float(match.group("hcp"))))
    return out


def ticket_direction_features(legs: object) -> dict[str, object]:
    parsed = parse_ticket_legs(legs)
    n_legs = len(parsed)
    neg0 = 0
    pos3 = 0
    draw = 0
    neg0_single = 0
    pos3_single = 0
    pure_single = 0
    for _match_id, code, hcp in parsed:
        code_set = set(code)
        if hcp < 0 and "0" in code_set:
            neg0 += 1
            if code == "0":
                neg0_single += 1
        if hcp > 0 and "3" in code_set:
            pos3 += 1
            if code == "3":
                pos3_single += 1
        if "1" in code_set:
            draw += 1
        if len(code_set) == 1:
            pure_single += 1
    directional = neg0 + pos3
    return {
        "parsed_legs": n_legs,
        "neg0_count": neg0,
        "pos3_count": pos3,
        "draw_cover_count": draw,
        "neg0_single_count": neg0_single,
        "pos3_single_count": pos3_single,
        "directional_count": directional,
        "directional_share": directional / n_legs if n_legs else math.nan,
        "single_share": pure_single / n_legs if n_legs else math.nan,
        "topology": f"neg0_{neg0}_pos3_{pos3}_draw_{draw}",
    }


def directional_gate(name: str, row: pd.Series) -> bool:
    neg0 = int(row["neg0_count"])
    pos3 = int(row["pos3_count"])
    draw = int(row["draw_cover_count"])
    directional = int(row["directional_count"])
    if name == "all":
        return True
    if name == "draw_free":
        return draw == 0
    if name == "directional_ge6":
        return directional >= 6
    if name == "directional_ge6_draw_le1":
        return directional >= 6 and draw <= 1
    if name == "directional_ge7":
        return directional >= 7
    if name == "neg0_ge5":
        return neg0 >= 5
    if name == "neg0_ge5_draw_free":
        return neg0 >= 5 and draw == 0
    if name == "neg0_ge6":
        return neg0 >= 6
    if name == "neg0_ge6_draw_free":
        return neg0 >= 6 and draw == 0
    if name == "neg0_ge7":
        return neg0 >= 7
    if name == "mixed_neg0_ge4_pos3_ge1":
        return neg0 >= 4 and pos3 >= 1
    if name == "mixed_neg0_ge4_pos3_ge1_draw_le1":
        return neg0 >= 4 and pos3 >= 1 and draw <= 1
    if name == "pos3_ge2_neg0_ge3":
        return pos3 >= 2 and neg0 >= 3
    raise ValueError(f"unknown gate: {name}")


def summarize_ticket_subset(
    rows: pd.DataFrame,
    *,
    all_issue_count: int,
    issue_budget: float,
) -> dict[str, object]:
    if rows.empty:
        return {
            "n_tickets": 0,
            "active_issues": 0,
            "stake_units": 0.0,
            "profit_units": 0.0,
            "roi": math.nan,
        }
    stake = float(rows["stake_units"].sum())
    profit = float(rows["profit_units"].sum())
    hits = rows[rows["hit"].astype(int) == 1].copy()
    issue_rows = []
    for issue, group in rows.groupby("issue"):
        spent = float(group["stake_units"].sum())
        scale = issue_budget / spent if spent > 0 else 0.0
        issue_profit = float((group["profit_units"] * scale).sum())
        issue_rows.append(
            {
                "issue": issue,
                "stake_units": issue_budget,
                "profit_units": issue_profit,
                "hits": int(group["hit"].sum()),
                "tickets": len(group),
            }
        )
    issue_df = pd.DataFrame(issue_rows)
    scaled_profit = float(issue_df["profit_units"].sum()) if len(issue_df) else 0.0
    scaled_stake = float(issue_df["stake_units"].sum()) if len(issue_df) else 0.0
    best_issue = float(issue_df["profit_units"].max()) if len(issue_df) else 0.0
    return {
        "n_tickets": len(rows),
        "active_issues": int(rows["issue"].nunique()),
        "active_issue_share": rows["issue"].nunique() / all_issue_count if all_issue_count else math.nan,
        "stake_units": stake,
        "profit_units": profit,
        "roi": profit / stake if stake else math.nan,
        "hit_stake_rate": float((rows["hit"].astype(int) * rows["stake_units"]).sum()) / stake if stake else math.nan,
        "avg_hit_unit_payout": float((hits["payout_units"] / hits["stake_units"]).mean()) if len(hits) else math.nan,
        "median_hit_unit_payout": float((hits["payout_units"] / hits["stake_units"]).median()) if len(hits) else math.nan,
        "scaled_profit_units": scaled_profit,
        "scaled_stake_units": scaled_stake,
        "scaled_roi_active": scaled_profit / scaled_stake if scaled_stake else math.nan,
        "scaled_profit_per_all_issue": scaled_profit / all_issue_count if all_issue_count else math.nan,
        "scaled_issue_win_rate": float((issue_df["profit_units"] > 0).mean()) if len(issue_df) else math.nan,
        "best_scaled_issue_profit": best_issue,
        "best_scaled_issue_profit_share": best_issue / scaled_profit if scaled_profit > 0 else math.nan,
    }


def analyze_directional_tickets(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame]:
    tickets = pd.read_csv(args.ev_ticket_path)
    tickets = tickets[tickets["strategy"].isin(N7_STRATEGIES)].copy()
    tickets["year"] = tickets["issue"].map(issue_year)
    feat = tickets["legs"].map(ticket_direction_features).apply(pd.Series)
    tickets = pd.concat([tickets, feat], axis=1)

    gates = [
        "all",
        "draw_free",
        "directional_ge6",
        "directional_ge6_draw_le1",
        "directional_ge7",
        "neg0_ge5",
        "neg0_ge5_draw_free",
        "neg0_ge6",
        "neg0_ge6_draw_free",
        "neg0_ge7",
        "mixed_neg0_ge4_pos3_ge1",
        "mixed_neg0_ge4_pos3_ge1_draw_le1",
        "pos3_ge2_neg0_ge3",
    ]
    rows = []
    for strategy, strat_rows in tickets.groupby("strategy"):
        for period_name, period_rows in [
            ("2014-2022", strat_rows[strat_rows["year"].between(2014, 2022)]),
            ("2023-2025", strat_rows[strat_rows["year"].between(2023, 2025)]),
        ]:
            all_issue_count = int(period_rows["issue"].nunique())
            if all_issue_count == 0:
                continue
            for gate in gates:
                mask = period_rows.apply(lambda row: directional_gate(gate, row), axis=1)
                selected = period_rows[mask].copy()
                summary = summarize_ticket_subset(
                    selected,
                    all_issue_count=all_issue_count,
                    issue_budget=args.ev_issue_budget,
                )
                rows.append({"strategy": strategy, "period": period_name, "gate": gate, **summary})
    gate_summary = pd.DataFrame(rows)

    topology_rows = []
    recent = tickets[tickets["year"].between(2023, 2025)].copy()
    for (strategy, topology), group in recent.groupby(["strategy", "topology"]):
        if len(group) < args.min_topology_tickets:
            continue
        summary = summarize_ticket_subset(
            group,
            all_issue_count=int(recent[recent["strategy"] == strategy]["issue"].nunique()),
            issue_budget=args.ev_issue_budget,
        )
        topology_rows.append({"strategy": strategy, "topology": topology, **summary})
    topology_summary = pd.DataFrame(topology_rows).sort_values(
        ["strategy", "scaled_profit_units"], ascending=[True, False]
    )
    return gate_summary, topology_summary


def add_leg_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["hcp_bucket"] = out["hcp"].map(hcp_bucket)
    out["pocket"] = out["action_code"].astype(str) + "@" + out["hcp_bucket"].astype(str)
    out["quad2"] = np.where(out["q_score"] >= out.groupby("issue")["q_score"].transform("median"), "H", "L")
    out["quad2"] += np.where(out["conf_weight"] >= out.groupby("issue")["conf_weight"].transform("median"), "H", "L")
    out["is_LL"] = (out["quad2"] == "LL").astype(int)
    out["is_neg0"] = ((out["hcp"] < 0) & (out["action_code"].astype(str) == "0")).astype(int)
    out["is_pos3"] = ((out["hcp"] > 0) & (out["action_code"].astype(str) == "3")).astype(int)
    out["is_draw"] = (out["action_code"].astype(str) == "1").astype(int)
    out["q_conf_product"] = out["q_score"] * out["conf_weight"]
    out["q_conf_ratio"] = out["q_score"] / out["conf_weight"].replace(0, np.nan)
    out["q_minus_conf"] = out["q_score"] - out["conf_weight"]
    out["ll_pocket"] = np.where(out["is_LL"] == 1, out["pocket"], "not_LL")
    return out


def group_value_summary(df: pd.DataFrame, group_cols: list[str], min_rows: int = 1) -> pd.DataFrame:
    rows = []
    for key, group in df.groupby(group_cols, dropna=False):
        if len(group) < min_rows:
            continue
        if not isinstance(key, tuple):
            key = (key,)
        hits = group[group["hit"].astype(int) == 1]
        hit_rate = len(hits) / len(group) if len(group) else math.nan
        avg_snapshot_p = float(pd.to_numeric(group["snapshot_p"], errors="coerce").mean())
        avg_mult = float(pd.to_numeric(hits["realized_sp_multiplier"], errors="coerce").mean()) if len(hits) else math.nan
        market_q_proxy = hit_rate / avg_snapshot_p if avg_snapshot_p and math.isfinite(avg_snapshot_p) else math.nan
        row = {col: value for col, value in zip(group_cols, key)}
        row.update(
            {
                "n_legs": len(group),
                "n_issues": group["issue"].nunique(),
                "hit_rate": hit_rate,
                "avg_snapshot_p": avg_snapshot_p,
                "avg_snapshot_odds": float(pd.to_numeric(group["snapshot_odds"], errors="coerce").mean()),
                "avg_realized_sp_multiplier_on_hits": avg_mult,
                "avg_winning_sp_on_hits": float(pd.to_numeric(hits["winning_sp"], errors="coerce").mean())
                if len(hits)
                else math.nan,
                "market_q_proxy": market_q_proxy,
                "drift_adjusted_ev_proxy": market_q_proxy * avg_mult
                if math.isfinite(market_q_proxy) and math.isfinite(avg_mult)
                else math.nan,
                "baseline_ticket_uses": int(pd.to_numeric(group["baseline_ticket_uses"], errors="coerce").sum()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def auc_for_score(y: np.ndarray, score: np.ndarray) -> float:
    finite = np.isfinite(score)
    if len(np.unique(y[finite])) < 2:
        return math.nan
    return float(roc_auc_score(y[finite], score[finite]))


def evaluate_model(name: str, pipeline: Pipeline, train: pd.DataFrame, test: pd.DataFrame, features: list[str]) -> dict[str, object]:
    y_train = train["hit"].astype(int).to_numpy()
    y_test = test["hit"].astype(int).to_numpy()
    pipeline.fit(train[features], y_train)
    p_train = pipeline.predict_proba(train[features])[:, 1]
    p_test = pipeline.predict_proba(test[features])[:, 1]
    return {
        "model": name,
        "train_rows": len(train),
        "test_rows": len(test),
        "train_auc": roc_auc_score(y_train, p_train),
        "test_auc": roc_auc_score(y_test, p_test),
        "test_log_loss": log_loss(y_test, p_test, labels=[0, 1]),
        "test_brier": brier_score_loss(y_test, p_test),
        "pipeline": pipeline,
    }


def aggregate_rf_importance(pipeline: Pipeline) -> pd.DataFrame:
    pre = pipeline.named_steps["prep"]
    model = pipeline.named_steps["model"]
    names = pre.get_feature_names_out()
    rows = []
    for name, importance in zip(names, model.feature_importances_):
        clean = name.replace("num__", "").replace("cat__", "")
        if "_" in clean and clean.split("_", 1)[0] in {
            "action",
            "q",
            "confidence",
            "drift",
            "pocket",
            "hcp",
            "quad2",
            "ll",
        }:
            if clean.startswith("action_code_"):
                feature = "action_code"
            elif clean.startswith("q_bucket_"):
                feature = "q_bucket"
            elif clean.startswith("confidence_bucket_"):
                feature = "confidence_bucket"
            elif clean.startswith("drift_bucket_"):
                feature = "drift_bucket"
            elif clean.startswith("pocket_"):
                feature = "pocket"
            elif clean.startswith("hcp_bucket_"):
                feature = "hcp_bucket"
            elif clean.startswith("quad2_"):
                feature = "quad2"
            elif clean.startswith("ll_pocket_"):
                feature = "ll_pocket"
            else:
                feature = clean
        else:
            feature = clean
        rows.append({"feature": feature, "importance": float(importance)})
    out = pd.DataFrame(rows).groupby("feature", as_index=False)["importance"].sum()
    return out.sort_values("importance", ascending=False)


def analyze_ml(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    leg = pd.read_csv(args.joint_leg_path)
    leg = leg[leg["spec"] == args.joint_spec].copy()
    leg = add_leg_features(leg)
    train = leg[leg["year"].between(2014, 2022)].copy()
    test = leg[leg["year"].between(2023, 2025)].copy()

    numeric_features = [
        "q_score",
        "conf_weight",
        "q_conf_product",
        "q_conf_ratio",
        "q_minus_conf",
        "selected_model_p",
        "selected_market_p",
        "model_market_ratio",
        "top_p",
        "margin",
        "top1_agree",
        "top2_agree",
        "pred_sp_multiplier",
        "snapshot_odds",
        "snapshot_p",
        "selected_prob_rank",
        "hcp",
        "is_LL",
        "is_neg0",
        "is_pos3",
        "is_draw",
    ]
    categorical_features = [
        "action_code",
        "q_bucket",
        "confidence_bucket",
        "drift_bucket",
        "hcp_bucket",
        "pocket",
        "quad2",
        "ll_pocket",
    ]
    features = numeric_features + categorical_features
    for col in numeric_features:
        train[col] = pd.to_numeric(train[col], errors="coerce")
        test[col] = pd.to_numeric(test[col], errors="coerce")
    for col in categorical_features:
        train[col] = train[col].astype(str)
        test[col] = test[col].astype(str)

    prep = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("scale", StandardScaler())]), numeric_features),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", min_frequency=args.onehot_min_frequency),
                categorical_features,
            ),
        ],
        remainder="drop",
    )
    logistic = Pipeline(
        [
            ("prep", prep),
            (
                "model",
                LogisticRegression(max_iter=1000, class_weight="balanced", C=0.5, n_jobs=-1),
            ),
        ]
    )
    rf = Pipeline(
        [
            ("prep", prep),
            (
                "model",
                RandomForestClassifier(
                    n_estimators=args.rf_trees,
                    min_samples_leaf=args.rf_min_leaf,
                    class_weight="balanced_subsample",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    model_rows = [
        evaluate_model("logistic", logistic, train, test, features),
        evaluate_model("random_forest", rf, train, test, features),
    ]
    model_summary = pd.DataFrame([{k: v for k, v in row.items() if k != "pipeline"} for row in model_rows])

    y_test = test["hit"].astype(int).to_numpy()
    univariate_rows = []
    for col in numeric_features:
        values = pd.to_numeric(test[col], errors="coerce").to_numpy()
        univariate_rows.append(
            {
                "feature": col,
                "auc": auc_for_score(y_test, values),
                "auc_inverse": auc_for_score(y_test, -values),
                "mean_hit": float(np.nanmean(values[y_test == 1])),
                "mean_miss": float(np.nanmean(values[y_test == 0])),
            }
        )
    univariate = pd.DataFrame(univariate_rows).sort_values(
        ["auc", "auc_inverse"], ascending=False
    )

    rf_importance = aggregate_rf_importance(model_rows[1]["pipeline"])
    sample = test[features + ["hit"]].sample(
        n=min(args.permutation_sample, len(test)), random_state=42
    )
    perm = permutation_importance(
        model_rows[1]["pipeline"],
        sample[features],
        sample["hit"].astype(int),
        scoring="roc_auc",
        n_repeats=args.permutation_repeats,
        random_state=42,
        n_jobs=-1,
    )
    perm_importance = pd.DataFrame(
        {
            "feature": features,
            "importance_mean": perm.importances_mean,
            "importance_std": perm.importances_std,
        }
    ).sort_values("importance_mean", ascending=False)

    period_quad = group_value_summary(
        leg.assign(period=np.where(leg["year"] >= 2023, "2023-2025", "2014-2022")),
        ["period", "quad2"],
    ).sort_values(["period", "quad2"])
    recent_pocket = group_value_summary(test, ["quad2", "pocket"], min_rows=args.min_group_rows).sort_values(
        ["drift_adjusted_ev_proxy", "baseline_ticket_uses"], ascending=False
    )
    return model_summary, univariate, rf_importance, perm_importance, period_quad, recent_pocket


def run(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    gate_summary, topology_summary = analyze_directional_tickets(args)
    (
        model_summary,
        univariate,
        rf_importance,
        perm_importance,
        period_quad,
        recent_pocket,
    ) = analyze_ml(args)

    gate_summary.to_csv(args.output_dir / "directional_gate_summary.csv", index=False)
    topology_summary.to_csv(args.output_dir / "directional_topology_summary.csv", index=False)
    model_summary.to_csv(args.output_dir / "ml_model_summary.csv", index=False)
    univariate.to_csv(args.output_dir / "ml_univariate_auc.csv", index=False)
    rf_importance.to_csv(args.output_dir / "ml_rf_importance.csv", index=False)
    perm_importance.to_csv(args.output_dir / "ml_permutation_importance.csv", index=False)
    period_quad.to_csv(args.output_dir / "q_conf_period_quad_value.csv", index=False)
    recent_pocket.to_csv(args.output_dir / "q_conf_recent_pocket_value.csv", index=False)

    recent_gates = gate_summary[gate_summary["period"] == "2023-2025"].copy()
    recent_gates = recent_gates.sort_values(
        ["strategy", "scaled_profit_units"], ascending=[True, False]
    )
    report = [
        "# High-N directional cluster and q/conf ML feature audit",
        "",
        "## Scope",
        "",
        "- Directional gate: existing N7 EV-framework budget tickets.",
        "- ML feature audit: `joint_leg_rows.csv`, train 2014-2022, test 2023-2025.",
        "- Model features are pre-match only. `hit`, `winning_sp`, and realized multipliers are labels/reporting only.",
        "",
        "## Recent Directional Gates",
        "",
        md_table(
            recent_gates[
                [
                    "strategy",
                    "gate",
                    "active_issues",
                    "active_issue_share",
                    "scaled_profit_units",
                    "scaled_roi_active",
                    "scaled_profit_per_all_issue",
                    "scaled_issue_win_rate",
                    "hit_stake_rate",
                    "median_hit_unit_payout",
                    "best_scaled_issue_profit_share",
                ]
            ]
            .head(40)
            .to_dict("records")
        ),
        "",
        "## Recent Topologies",
        "",
        md_table(
            topology_summary[
                [
                    "strategy",
                    "topology",
                    "active_issues",
                    "scaled_profit_units",
                    "scaled_roi_active",
                    "scaled_issue_win_rate",
                    "median_hit_unit_payout",
                ]
            ]
            .head(30)
            .to_dict("records")
        ),
        "",
        "## ML Model Summary",
        "",
        md_table(model_summary.to_dict("records")),
        "",
        "## Random Forest Feature Importance",
        "",
        md_table(rf_importance.head(25).to_dict("records")),
        "",
        "## Permutation Importance",
        "",
        md_table(perm_importance.head(25).to_dict("records")),
        "",
        "## Univariate AUC",
        "",
        md_table(univariate.head(25).to_dict("records")),
        "",
        "## q/conf Period Quadrants",
        "",
        md_table(period_quad.to_dict("records")),
        "",
        "## Recent q/conf Pocket Value",
        "",
        md_table(recent_pocket.head(40).to_dict("records")),
        "",
        "## Files",
        "",
        f"- Directional gates: `{args.output_dir / 'directional_gate_summary.csv'}`",
        f"- Directional topologies: `{args.output_dir / 'directional_topology_summary.csv'}`",
        f"- ML model summary: `{args.output_dir / 'ml_model_summary.csv'}`",
        f"- RF importance: `{args.output_dir / 'ml_rf_importance.csv'}`",
        f"- Permutation importance: `{args.output_dir / 'ml_permutation_importance.csv'}`",
        f"- q/conf quadrants: `{args.output_dir / 'q_conf_period_quad_value.csv'}`",
        f"- q/conf pockets: `{args.output_dir / 'q_conf_recent_pocket_value.csv'}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ev-ticket-path",
        type=Path,
        default=Path("results/n7_ev_framework_selector_2014_1h_minodds4_optional/ev_framework_budget_fractional_tickets.csv"),
    )
    parser.add_argument("--ev-issue-budget", type=float, default=256.0)
    parser.add_argument(
        "--joint-leg-path",
        type=Path,
        default=Path("results/n7_q_conf_drift_joint_2014_10h_trusted/joint_leg_rows.csv"),
    )
    parser.add_argument("--joint-spec", default="keyed_pockets")
    parser.add_argument("--onehot-min-frequency", type=int, default=80)
    parser.add_argument("--rf-trees", type=int, default=300)
    parser.add_argument("--rf-min-leaf", type=int, default=80)
    parser.add_argument("--permutation-sample", type=int, default=12000)
    parser.add_argument("--permutation-repeats", type=int, default=5)
    parser.add_argument("--min-group-rows", type=int, default=80)
    parser.add_argument("--min-topology-tickets", type=int, default=40)
    parser.add_argument("--output-dir", type=Path, default=Path("results/high_n_directional_ml_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/high_n_directional_ml_2026-06-28.md"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
