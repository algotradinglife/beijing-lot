#!/usr/bin/env python3
"""Replay #312 surfaces with label-safe reads and publish an identity receipt."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
import os
from pathlib import Path
import sys

import pandas as pd
from pandas.testing import assert_frame_equal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue312.design import actions_from_registry  # noqa: E402
from issue312.surface import (  # noqa: E402
    DEVELOPMENT_SEEDS,
    DEVELOPMENT_YEARS,
    EVALUATION_SEEDS,
    build_seed_action_ledger,
    load_causal_issue209_inputs,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _compare_year(
    tensor: pd.DataFrame,
    probabilities: pd.DataFrame,
    values: pd.DataFrame,
    *,
    actions,
    year: int,
    seeds: tuple[int, ...],
    prefix: str,
    output: Path,
) -> dict[str, object]:
    actual = build_seed_action_ledger(
        tensor,
        probabilities,
        values,
        actions,
        years=(year,),
        seeds=seeds,
    )
    expected = (
        pd.read_parquet(output / f"{prefix}_seed_action_ledger_{year}.parquet"),
        pd.read_csv(output / f"{prefix}_action_availability_{year}.csv"),
        pd.read_csv(output / f"{prefix}_coverage_{year}.csv"),
    )
    for regenerated, committed in zip(actual, expected, strict=True):
        for frame in (regenerated, committed):
            if "issue" in frame:
                frame["issue"] = frame["issue"].astype(str)
        assert_frame_equal(regenerated, committed, check_dtype=False, check_exact=True)
    return {
        "year": year,
        "ledger_rows": int(len(actual[0])),
        "availability_rows": int(len(actual[1])),
        "issue_count": int(actual[2]["issue"].nunique()),
        "byte_semantic_identity": "PASS",
    }


def _replay_year(year: int) -> tuple[dict[str, object], dict[str, object]]:
    output = ROOT / "results/issue-312"
    probability_path = ROOT / "results/issue-209/market_only_probabilities.parquet"
    value_path = ROOT / "results/issue-209/cell_value_distribution.parquet"
    if year in DEVELOPMENT_YEARS:
        actions = actions_from_registry(pd.read_csv(output / "action_registry.csv"))
        tensor, probabilities, values, causal_read = load_causal_issue209_inputs(
            probability_path,
            value_path,
            years=(year,),
        )
        comparison = _compare_year(
            tensor,
            probabilities,
            values,
            actions=actions,
            year=year,
            seeds=DEVELOPMENT_SEEDS,
            prefix="development",
            output=output,
        )
    else:
        support = pd.read_csv(
            ROOT / "results/issue-299/support_receipt.csv", dtype={"issue": str}
        )
        common_issues = set(
            support.loc[
                support["support_status"].eq("MATCHED_BASELINE_AND_FEATURES")
                & support["issue_year"].eq(2023),
                "issue",
            ]
        )
        actions = actions_from_registry(
            pd.read_csv(output / "evaluation_action_registry.csv")
        )
        tensor, probabilities, values, causal_read = load_causal_issue209_inputs(
            probability_path,
            value_path,
            years=(2023,),
            issues=common_issues,
        )
        comparison = _compare_year(
            tensor,
            probabilities,
            values,
            actions=actions,
            year=2023,
            seeds=EVALUATION_SEEDS,
            prefix="evaluation",
            output=output,
        )
    return comparison, causal_read


def main() -> None:
    output = ROOT / "results/issue-312"
    years = (*DEVELOPMENT_YEARS, 2023)
    with ProcessPoolExecutor(max_workers=min(len(years), os.cpu_count() or 1)) as executor:
        replayed = list(executor.map(_replay_year, years))
    comparisons = [item[0] for item in replayed]
    reads = {str(year): item[1] for year, item in zip(years, replayed, strict=True)}

    receipt = {
        "issue": 312,
        "check": "LABEL_SAFE_CAUSAL_REPLAY",
        "verdict": "PASS",
        "causal_reads_by_year": reads,
        "comparisons": comparisons,
        "frozen_allocation_sha256": _sha256(output / "pre2023_policy_allocations.csv"),
        "terminal_decision_sha256": _sha256(output / "decision.json"),
        "scientific_result_changed": False,
    }
    destination = output / "causal_replay_receipt.json"
    temporary = destination.with_suffix(".tmp.json")
    temporary.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(destination)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
