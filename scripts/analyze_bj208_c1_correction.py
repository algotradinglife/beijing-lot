#!/usr/bin/env python3
"""Reproduce the Issue #208 C1 before/after correction evidence.

The superseded package is read directly from an exact Git commit; the accepted
candidate package is read from the working tree.  This keeps the scientific
runner free of one-off backward-compatibility logic while making the correction
delta independently reproducible.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

import numpy as np
import pandas as pd


DEFAULT_BEFORE_COMMIT = "d51bd3e07b84039cc7172c8d3fef776d99aca95d"
GROUP_KEYS = ["split", "n", "k", "lane", "seed"]
BUNDLE_KEYS = ["split", "issue", "n", "k", "lane", "seed"]


def _extract_from_commit(commit: str, relative_path: str, target: Path) -> None:
    with target.open("wb") as handle:
        subprocess.run(
            ["git", "show", f"{commit}:{relative_path}"],
            check=True,
            stdout=handle,
        )


def _canonical_semantic_key(frame: pd.DataFrame) -> pd.Series:
    def canonical(row: pd.Series) -> str:
        matches = str(row["match_indices"]).split("|")
        outcomes = str(row["outcomes"]).split("|")
        pairs = sorted(zip(matches, outcomes, strict=True), key=lambda pair: int(pair[0]))
        return "|".join(f"{match_idx}:{outcome}" for match_idx, outcome in pairs)

    return frame.apply(canonical, axis=1)


def _bundle_census(frame: pd.DataFrame, version: str) -> pd.DataFrame:
    enriched = frame.assign(semantic_key=_canonical_semantic_key(frame))
    census = (
        enriched.groupby(BUNDLE_KEYS, as_index=False, sort=True)
        .agg(
            ticket_rows=("ticket_identity", "size"),
            stored_identity_unique=("ticket_identity", "nunique"),
            semantic_unique=("semantic_key", "nunique"),
        )
    )
    census["semantic_duplicate_rows"] = (
        census["ticket_rows"] - census["semantic_unique"]
    )
    census["repeat_semantics"] = np.where(
        census["lane"].eq("MARKET_WR"),
        "WITH_REPLACEMENT_ALLOWED",
        "UNIQUE_REQUIRED",
    )
    census["unexpected_semantic_duplicate_rows"] = np.where(
        census["lane"].eq("MARKET_WR"),
        0,
        census["semantic_duplicate_rows"],
    )
    census.insert(0, "version", version)
    return census


def _payout_delta(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    aggregations = {
        "ticket_rows": ("ticket_identity", "size"),
        "hit_tickets": ("realized_hit", "sum"),
        "gross_multiple_sum": ("pre_tax_gross_multiple", "sum"),
        "payout_yuan_sum": ("payout_yuan", "sum"),
    }
    left = before.groupby(GROUP_KEYS, as_index=False).agg(**aggregations)
    right = after.groupby(GROUP_KEYS, as_index=False).agg(**aggregations)
    merged = left.merge(
        right,
        on=GROUP_KEYS,
        how="outer",
        suffixes=("_before", "_after"),
        validate="one_to_one",
    ).fillna(0)
    for metric in aggregations:
        merged[f"{metric}_delta"] = (
            merged[f"{metric}_after"] - merged[f"{metric}_before"]
        )
    return merged.sort_values(GROUP_KEYS, kind="stable").reset_index(drop=True)


def _label_surface_delta(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    keys = ["issue", "split", "action_key", "n", "k", "lane", "capital"]
    metrics = [
        "matched_lift_mean",
        "matched_lift_median",
        "matched_lift_std",
        "payout_mean",
        "funded_mean",
    ]
    merged = before[keys + metrics].merge(
        after[keys + metrics],
        on=keys,
        how="outer",
        suffixes=("_before", "_after"),
        validate="one_to_one",
    )
    for metric in metrics:
        merged[f"{metric}_delta"] = (
            merged[f"{metric}_after"] - merged[f"{metric}_before"]
        )
    return merged.sort_values(keys, kind="stable").reset_index(drop=True)


def _capital_endpoint_delta(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    def endpoints(frame: pd.DataFrame) -> pd.DataFrame:
        ordered = frame.assign(_issue_order=frame["issue"].astype(str)).sort_values(
            ["split", "policy", "_issue_order"], kind="stable"
        )
        return ordered.groupby(["split", "policy"], as_index=False).tail(1)[
            ["split", "policy", "post_issue_bankroll_yuan"]
        ]

    merged = endpoints(before).merge(
        endpoints(after),
        on=["split", "policy"],
        how="outer",
        suffixes=("_before", "_after"),
        validate="one_to_one",
    )
    merged["ending_capital_delta_yuan"] = (
        merged["post_issue_bankroll_yuan_after"]
        - merged["post_issue_bankroll_yuan_before"]
    )
    return merged.sort_values(["split", "policy"], kind="stable").reset_index(
        drop=True
    )


def _read_package(package: Path) -> dict[str, pd.DataFrame]:
    return {
        "tickets": pd.read_parquet(package / "ticket_economics.parquet"),
        "surface": pd.read_parquet(package / "label_surface_fit.parquet"),
        "capital": pd.read_parquet(package / "issue_capital_ledger.parquet"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-commit", default=DEFAULT_BEFORE_COMMIT)
    parser.add_argument("--after-package", default="results/issue-208")
    parser.add_argument(
        "--output-dir", default="docs/research/evidence/issue-208-r8"
    )
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="bj208-c1-before-") as tmp:
        before_package = Path(tmp)
        for filename in (
            "ticket_economics.parquet",
            "label_surface_fit.parquet",
            "issue_capital_ledger.parquet",
            "selection.json",
        ):
            _extract_from_commit(
                args.before_commit,
                f"results/issue-208/{filename}",
                before_package / filename,
            )
        before = _read_package(before_package)
        after_package = Path(args.after_package)
        after = _read_package(after_package)

        census = pd.concat(
            [
                _bundle_census(before["tickets"], "BEFORE_C1"),
                _bundle_census(after["tickets"], "AFTER_C1"),
            ],
            ignore_index=True,
        )
        payout = _payout_delta(before["tickets"], after["tickets"])
        surface = _label_surface_delta(before["surface"], after["surface"])
        capital = _capital_endpoint_delta(before["capital"], after["capital"])

        before_selection = json.loads(
            (before_package / "selection.json").read_text(encoding="utf-8")
        )
        after_selection = json.loads(
            (after_package / "selection.json").read_text(encoding="utf-8")
        )

    census.to_csv(output / "semantic_duplicate_census.csv", index=False)
    payout.to_csv(output / "corrected_result_delta.csv", index=False)
    surface.to_csv(output / "label_surface_delta.csv", index=False)
    capital.to_csv(output / "capital_endpoint_delta.csv", index=False)

    unique_required = census["repeat_semantics"].eq("UNIQUE_REQUIRED")
    after_mask = census["version"].eq("AFTER_C1") & unique_required
    before_mask = census["version"].eq("BEFORE_C1") & unique_required
    surface_metrics = [
        "matched_lift_mean_delta",
        "matched_lift_median_delta",
        "matched_lift_std_delta",
        "payout_mean_delta",
        "funded_mean_delta",
    ]
    changed_surface = surface[
        np.logical_or.reduce(
            [
                ~np.isclose(surface[column], 0.0, rtol=0.0, atol=1e-9)
                for column in surface_metrics
            ]
        )
    ]
    summary = {
        "before_commit": args.before_commit,
        "after_producer_commit": json.loads(
            (Path(args.after_package) / "provenance.json").read_text(
                encoding="utf-8"
            )
        )["producer_code_commit"],
        "before_unexpected_semantic_duplicate_rows": int(
            census.loc[before_mask, "unexpected_semantic_duplicate_rows"].sum()
        ),
        "after_unexpected_semantic_duplicate_rows": int(
            census.loc[after_mask, "unexpected_semantic_duplicate_rows"].sum()
        ),
        "payout_groups_changed": int(
            (~np.isclose(payout["payout_yuan_sum_delta"], 0.0, atol=1e-9)).sum()
        ),
        "label_surface_rows_changed": int(len(changed_surface)),
        "label_surface_rows_total": int(len(surface)),
        "max_abs_matched_lift_mean_delta_yuan": float(
            changed_surface["matched_lift_mean_delta"].abs().max()
        ),
        "capital_endpoints_changed": int(
            (~np.isclose(capital["ending_capital_delta_yuan"], 0.0, atol=1e-9)).sum()
        ),
        "max_abs_capital_endpoint_delta_yuan": float(
            capital["ending_capital_delta_yuan"].abs().max()
        ),
        "selection_eligible_before": bool(before_selection["eligible"]),
        "selection_eligible_after": bool(after_selection["eligible"]),
        "frozen_candidate_before": before_selection["frozen_candidate"],
        "frozen_candidate_after": after_selection["frozen_candidate"],
        "final_disposition_changed": (
            before_selection["eligible"] != after_selection["eligible"]
            or before_selection["frozen_candidate"]
            != after_selection["frozen_candidate"]
        ),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
