#!/usr/bin/env python3
"""Walk-forward ablation of league, rank, and Asian-line match tags."""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data/beidan_features.db"
DEFAULT_REPORT = ROOT / "docs/research/historical_match_tag_walkforward_2026-07-11.md"
DEFAULT_CSV = ROOT / "docs/research/historical_match_tag_walkforward_2026-07-11.csv"
OUTCOMES = ("3", "1", "0")

MARKET_HCAP = (
    "beidan_hcap",
    "p_close_3", "p_close_1", "p_close_0",
    "p_open_3", "p_open_1", "p_open_0",
)
RANKS = ("rank_home", "rank_away")
ASIAN = ("asian_p_home_close", "asian_p_home_open", "asian_line")


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    numeric: tuple[str, ...]
    categorical: tuple[str, ...] = ()


def feature_specs() -> list[FeatureSpec]:
    return [
        FeatureSpec("market_hcap", MARKET_HCAP),
        FeatureSpec("market_hcap_league", MARKET_HCAP, ("league",)),
        FeatureSpec("market_hcap_ranks", MARKET_HCAP + RANKS),
        FeatureSpec("market_hcap_asian", MARKET_HCAP + ASIAN),
        FeatureSpec("all_no_league", MARKET_HCAP + RANKS + ASIAN),
        FeatureSpec("all_with_league", MARKET_HCAP + RANKS + ASIAN, ("league",)),
    ]


def load_data(db_path: Path) -> pd.DataFrame:
    columns = sorted({"season", "result_code", *(col for spec in feature_specs() for col in (*spec.numeric, *spec.categorical))})
    with sqlite3.connect(db_path) as conn:
        frame = pd.read_sql_query(
            f"SELECT {', '.join(columns)} FROM matches "
            "WHERE result_code IN ('3','1','0') AND season IS NOT NULL "
            "AND p_close_3 IS NOT NULL AND p_close_1 IS NOT NULL AND p_close_0 IS NOT NULL",
            conn,
        )
    frame["season"] = frame["season"].astype(int)
    frame["result_code"] = frame["result_code"].astype(str)
    frame["league"] = frame["league"].fillna("__missing__").astype(str)
    return frame


def build_pipeline(spec: FeatureSpec) -> Pipeline:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median", add_indicator=True)),
        ("scale", StandardScaler()),
    ])
    transformers: list[tuple[str, Any, list[str]]] = [("numeric", numeric, list(spec.numeric))]
    if spec.categorical:
        categorical = OneHotEncoder(
            handle_unknown="infrequent_if_exist",
            min_frequency=100,
            sparse_output=True,
        )
        transformers.append(("categorical", categorical, list(spec.categorical)))
    preprocessor = ColumnTransformer(transformers, sparse_threshold=0.3)
    model = LogisticRegression(
        solver="lbfgs",
        max_iter=250,
        C=1.0,
        random_state=0,
    )
    return Pipeline([("features", preprocessor), ("model", model)])


def reorder_probabilities(probabilities: np.ndarray, classes: list[str]) -> np.ndarray:
    indices = [classes.index(code) for code in OUTCOMES]
    return probabilities[:, indices]


def metrics(probabilities: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    y = np.asarray([OUTCOMES.index(str(code)) for code in actual], dtype=int)
    clipped = np.clip(probabilities, 1e-12, 1.0)
    logloss = float(-np.log(clipped[np.arange(len(y)), y]).mean())
    truth = np.eye(len(OUTCOMES))[y]
    brier = float(np.square(probabilities - truth).sum(axis=1).mean())
    top1 = float((probabilities.argmax(axis=1) == y).mean())
    top2 = np.argpartition(probabilities, -2, axis=1)[:, -2:]
    top2_coverage = float(np.fromiter((target in choices for target, choices in zip(y, top2)), dtype=bool).mean())
    return {"logloss": logloss, "brier": brier, "accuracy": top1, "top2_coverage": top2_coverage}


def run_walkforward(frame: pd.DataFrame, test_seasons: list[int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for season in test_seasons:
        train = frame[frame["season"] < season]
        test = frame[frame["season"] == season]
        if len(train) < 1000 or test.empty:
            continue
        for spec in feature_specs():
            pipeline = build_pipeline(spec)
            columns = [*spec.numeric, *spec.categorical]
            pipeline.fit(train[columns], train["result_code"])
            model = pipeline.named_steps["model"]
            probabilities = reorder_probabilities(
                pipeline.predict_proba(test[columns]),
                [str(value) for value in model.classes_],
            )
            row = metrics(probabilities, test["result_code"].to_numpy())
            rows.append({
                "season": season,
                "model": spec.name,
                "n_train": len(train),
                "n_test": len(test),
                **row,
            })
    return rows


def pooled_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_model: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_model.setdefault(str(row["model"]), []).append(row)
    baseline = by_model.get("market_hcap", [])
    baseline_by_season = {int(row["season"]): row for row in baseline}
    summary: list[dict[str, Any]] = []
    for model, model_rows in by_model.items():
        total = sum(int(row["n_test"]) for row in model_rows)
        weighted = {
            key: sum(float(row[key]) * int(row["n_test"]) for row in model_rows) / total
            for key in ("logloss", "brier", "accuracy", "top2_coverage")
        }
        improved = sum(
            float(row["logloss"]) < float(baseline_by_season[int(row["season"])]["logloss"])
            for row in model_rows
            if int(row["season"]) in baseline_by_season and model != "market_hcap"
        )
        summary.append({"model": model, "n": total, "seasons_better": improved, **weighted})
    return summary


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def write_report(path: Path, frame: pd.DataFrame, rows: list[dict[str, Any]], test_seasons: list[int]) -> None:
    summary = pooled_summary(rows)
    by_name = {str(row["model"]): row for row in summary}
    baseline = by_name["market_hcap"]
    lines = [
        "# 历史联赛与比赛标签 Walk-forward 消融",
        "",
        "日期：2026-07-11  ",
        f"历史库：2014-{int(frame['season'].max())}，{len(frame):,} 场可用样本  ",
        f"样本外赛季：{min(test_seasons)}-{max(test_seasons)}",
        "",
        "## 设计",
        "",
        "- 每个测试赛季只使用更早赛季训练，禁止随机切分。",
        "- 所有模型使用同一多项 Logistic、同一正则和同一测试行，只改变特征集合。",
        "- 联赛使用 one-hot，并将训练样本少于 100 的类别合并为低频类别。",
        "- 收盘字段是开赛前可见，但不等同当前 v3.3.3 的 11 小时快照；本实验衡量标签的预测上限。",
        "",
        "## 汇总 OOS",
        "",
        "| 模型 | n | log-loss | 相对基线 | Brier | Top-1 | Top-2 | 改善赛季 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        delta = float(baseline["logloss"]) - float(row["logloss"])
        better = "-" if row["model"] == "market_hcap" else f"{row['seasons_better']}/{len(test_seasons)}"
        lines.append(
            f"| {row['model']} | {row['n']:,} | {row['logloss']:.6f} | {delta:+.6f} "
            f"| {row['brier']:.6f} | {pct(row['accuracy'])} | {pct(row['top2_coverage'])} | {better} |"
        )
    league_delta = float(by_name["market_hcap_league"]["logloss"]) - float(baseline["logloss"])
    full_league_delta = float(by_name["all_with_league"]["logloss"]) - float(by_name["all_no_league"]["logloss"])
    lines.extend([
        "",
        "## 联赛增量",
        "",
        f"- 在市场+盘口基线上加入联赛，log-loss 变化 `{league_delta:+.6f}`（负数才是改善）。",
        f"- 在排名+亚洲盘全数值模型上再加入联赛，log-loss 变化 `{full_league_delta:+.6f}`。",
        "- 是否进入生产以跨赛季方向一致性为准，不按单个联赛的回测胜负硬编码规则。",
        "",
        "## 逐季 log-loss",
        "",
        "| 赛季 | 基线 | +联赛 | +排名 | +亚洲盘 | 全数值 | 全部+联赛 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ])
    row_map = {(int(row["season"]), str(row["model"])): row for row in rows}
    for season in test_seasons:
        if (season, "market_hcap") not in row_map:
            continue
        values = [row_map[(season, name)]["logloss"] for name in (
            "market_hcap", "market_hcap_league", "market_hcap_ranks",
            "market_hcap_asian", "all_no_league", "all_with_league",
        )]
        lines.append(f"| {season} | " + " | ".join(f"{float(value):.5f}" for value in values) + " |")
    lines.extend([
        "",
        "## 约束",
        "",
        "- 情报文本、LLM标签和当前实时SP快照没有同口径长历史，未纳入本实验。",
        "- 本实验只评估单场结果概率；即使指标改善，也必须再过当前 v3.3.3 覆盖深度和组合成本回放。",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--start-season", type=int, default=2016)
    parser.add_argument("--end-season", type=int, default=2025)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    frame = load_data(args.db)
    seasons = list(range(args.start_season, args.end_season + 1))
    rows = run_walkforward(frame, seasons)
    write_csv(args.csv, rows)
    write_report(args.report, frame, rows, seasons)
    print(json.dumps({"rows": len(frame), "oos_rows": sum(row["n_test"] for row in pooled_summary(rows)[:1]), "report": str(args.report)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
