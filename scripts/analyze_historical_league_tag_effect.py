#!/usr/bin/env python3
"""Measure historical OOS league-tag effect for recent positive league groups."""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BASE_SCRIPT = ROOT / "scripts/backtest_historical_match_tags_walkforward.py"
DEFAULT_DB = ROOT / "data/beidan_features.db"
DEFAULT_REPORT = ROOT / "docs/research/historical_positive_league_tag_effect_2026-07-11.md"
DEFAULT_CSV = ROOT / "docs/research/historical_positive_league_tag_effect_2026-07-11.csv"

TARGET_LEAGUES = {
    "K2联赛": ("韩K2联",),
    "世界杯": ("世界杯",),
    "巴西乙": ("巴西乙",),
    "爱甲": ("爱甲",),
    "瑞典超": ("瑞典超",),
    "芬超": ("芬超",),
}
RECENT_DELTAS_PP = {
    "K2联赛": 12.5,
    "世界杯": 20.0,
    "巴西乙": 12.5,
    "爱甲": 20.0,
    "瑞典超": 37.5,
    "芬超": 25.0,
}


def load_base_module():
    spec = importlib.util.spec_from_file_location("historical_tag_walkforward_base", BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BASE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def target_label(league: str) -> str:
    for label, aliases in TARGET_LEAGUES.items():
        if league in aliases:
            return label
    return ""


def prediction_rows(frame: pd.DataFrame, test_seasons: list[int]) -> list[dict[str, Any]]:
    base = load_base_module()
    specs = {spec.name: spec for spec in base.feature_specs()}
    wanted = (specs["market_hcap"], specs["market_hcap_league"])
    records: list[dict[str, Any]] = []
    for season in test_seasons:
        train = frame[frame["season"] < season]
        test = frame[frame["season"] == season]
        target_mask = test["league"].map(target_label).astype(bool)
        target = test[target_mask]
        if len(train) < 1000 or target.empty:
            continue
        probabilities: dict[str, np.ndarray] = {}
        for feature_spec in wanted:
            pipeline = base.build_pipeline(feature_spec)
            columns = [*feature_spec.numeric, *feature_spec.categorical]
            pipeline.fit(train[columns], train["result_code"])
            model = pipeline.named_steps["model"]
            probabilities[feature_spec.name] = base.reorder_probabilities(
                pipeline.predict_proba(target[columns]),
                [str(value) for value in model.classes_],
            )
        actual = target["result_code"].astype(str).to_numpy()
        for pos, (_, row) in enumerate(target.iterrows()):
            record = {
                "season": season,
                "league_group": target_label(str(row["league"])),
                "historical_league": str(row["league"]),
                "result_code": actual[pos],
            }
            for model_name, values in probabilities.items():
                for idx, code in enumerate(base.OUTCOMES):
                    record[f"{model_name}_p_{code}"] = float(values[pos, idx])
            records.append(record)
    return records


def group_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base = load_base_module()
    results: list[dict[str, Any]] = []
    for label in TARGET_LEAGUES:
        group = [row for row in rows if row["league_group"] == label]
        if not group:
            continue
        actual = np.asarray([row["result_code"] for row in group])
        metrics_by_model: dict[str, dict[str, float]] = {}
        for model_name in ("market_hcap", "market_hcap_league"):
            probabilities = np.asarray([
                [row[f"{model_name}_p_{code}"] for code in base.OUTCOMES]
                for row in group
            ])
            metrics_by_model[model_name] = base.metrics(probabilities, actual)
        improved_seasons = 0
        eligible_seasons = 0
        for season in sorted({int(row["season"]) for row in group}):
            season_rows = [row for row in group if int(row["season"]) == season]
            if len(season_rows) < 20:
                continue
            eligible_seasons += 1
            season_actual = np.asarray([row["result_code"] for row in season_rows])
            season_metrics = {}
            for model_name in ("market_hcap", "market_hcap_league"):
                probabilities = np.asarray([
                    [row[f"{model_name}_p_{code}"] for code in base.OUTCOMES]
                    for row in season_rows
                ])
                season_metrics[model_name] = base.metrics(probabilities, season_actual)
            improved_seasons += season_metrics["market_hcap_league"]["logloss"] < season_metrics["market_hcap"]["logloss"]
        baseline = metrics_by_model["market_hcap"]
        league = metrics_by_model["market_hcap_league"]
        results.append({
            "league_group": label,
            "n": len(group),
            "recent_delta_pp": RECENT_DELTAS_PP[label],
            "baseline_logloss": baseline["logloss"],
            "league_logloss": league["logloss"],
            "logloss_delta": league["logloss"] - baseline["logloss"],
            "baseline_accuracy": baseline["accuracy"],
            "league_accuracy": league["accuracy"],
            "accuracy_delta": league["accuracy"] - baseline["accuracy"],
            "baseline_top2": baseline["top2_coverage"],
            "league_top2": league["top2_coverage"],
            "top2_delta": league["top2_coverage"] - baseline["top2_coverage"],
            "seasons_better": improved_seasons,
            "seasons_eligible": eligible_seasons,
        })
    return results


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def write_report(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# 近期正向联赛标签的历史样本外表现",
        "",
        "日期：2026-07-11  ",
        "历史窗口：2016-2025 OOS，训练仅使用更早赛季",
        "",
        "## 结果",
        "",
        "`log-loss Δ = 加联赛 - 基线`，负数表示联赛标签改善。",
        "",
        "| 联赛 | 历史n | 近期开发提升 | log-loss基线 | 加联赛 | Δ | Top-1变化 | Top-2变化 | 改善赛季 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['league_group']} | {row['n']} | +{row['recent_delta_pp']:.1f}pp "
            f"| {row['baseline_logloss']:.5f} | {row['league_logloss']:.5f} | {row['logloss_delta']:+.5f} "
            f"| {pct(row['accuracy_delta'])} | {pct(row['top2_delta'])} "
            f"| {row['seasons_better']}/{row['seasons_eligible']} |"
        )
    lines.extend([
        "",
        "## 判定",
        "",
        "- 近期提升来自26071-26072的小分组，只用于提出问题。",
        "- 历史结果按同场配对，只改变是否加入联赛分类标签。",
        "- 世界杯等低频赛事即使方向为正，也必须结合样本量和跨赛季一致性判断。",
        "- 不根据单个联赛的回测结果写入硬编码主押规则。",
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
    base = load_base_module()
    frame = base.load_data(args.db)
    seasons = list(range(args.start_season, args.end_season + 1))
    predictions = prediction_rows(frame, seasons)
    results = group_metrics(predictions)
    write_csv(args.csv, results)
    write_report(args.report, results)
    print(json.dumps({"prediction_rows": len(predictions), "league_groups": len(results), "report": str(args.report)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
