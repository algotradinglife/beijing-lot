#!/usr/bin/env python3
"""Freeze the #286 base, protection-candidate and continuation manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue209.contract import INFERENCE_VIEW  # noqa: E402
from issue209.data import load_inference_view  # noqa: E402
from issue286.manifest import (  # noqa: E402
    GENERATORS,
    OUTCOME_MODES,
    SELECTORS,
    JointBaseAction,
    build_action_manifest,
    prepare_horizon_surface,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results/issue-286")
    parser.add_argument(
        "--subset-profile",
        type=Path,
        default=ROOT / "results/issue-284/subset_profile.parquet",
    )
    parser.add_argument("--limit-issues", type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    profile_path = args.subset_profile.resolve()
    if not profile_path.is_file():
        raise FileNotFoundError(profile_path)
    view = load_inference_view()
    surface = prepare_horizon_surface(view, horizon="10h")
    profile = pd.read_parquet(profile_path)
    selected = (
        profile.loc[
            profile["n"].isin((7, 8, 9))
            & profile["proposal_family"].isin(SELECTORS)
        ]
        .sort_values(["issue_year", "issue", "n", "proposal_family", "subset_id"])
        .groupby(["issue", "n", "proposal_family"], as_index=False)
        .head(1)
        .copy()
    )
    selected["issue"] = selected["issue"].astype(str)
    issue_index = selected[["issue", "issue_year"]].drop_duplicates().copy()
    issue_index["issue_numeric"] = pd.to_numeric(issue_index["issue"], errors="raise")
    issue_order = issue_index.sort_values(
        ["issue_year", "issue_numeric"]
    )["issue"].tolist()
    if args.limit_issues is not None:
        issue_order = issue_order[: args.limit_issues]
    selected = selected[selected["issue"].isin(issue_order)]
    selected_by_issue = {
        issue: group for issue, group in selected.groupby("issue", sort=False)
    }
    surface_by_issue = {
        issue: group for issue, group in surface.groupby("issue", sort=False)
    }
    targets = {
        "base": output / "base_tickets.parquet",
        "candidate": output / "protection_candidates.parquet",
        "continuation": output / "continuation_tickets.parquet",
    }
    temporary = {name: path.with_suffix(".tmp.parquet") for name, path in targets.items()}
    writers: dict[str, pq.ParquetWriter] = {}
    rows = {"base": 0, "candidate": 0, "continuation": 0}
    issue_action_counts: dict[str, int] = {}
    exclusions: list[dict[str, str]] = []
    try:
        for issue_number, issue in enumerate(issue_order, 1):
            issue_surface = surface_by_issue.get(issue)
            subsets = selected_by_issue.get(issue)
            if issue_surface is None or subsets is None:
                exclusions.append({"issue": issue, "reason": "MISSING_SURFACE_OR_SUBSET"})
                continue
            issue_frames = {"base": [], "candidate": [], "continuation": []}
            for subset in subsets.itertuples(index=False):
                match_ids = json.loads(subset.match_ids)
                for k in (16, 64):
                    for outcome_mode in OUTCOME_MODES:
                        for generator in GENERATORS:
                            action = JointBaseAction(
                                n=int(subset.n),
                                k=k,
                                selector=str(subset.proposal_family),
                                outcome_mode=outcome_mode,
                                generator=generator,
                                stream_seed=286_001,
                            )
                            try:
                                base, candidate, continuation = build_action_manifest(
                                    issue_surface,
                                    match_ids=match_ids,
                                    subset_id=str(subset.subset_id),
                                    action=action,
                                )
                            except ValueError as exc:
                                exclusions.append(
                                    {
                                        "issue": issue,
                                        "action_key": action.key,
                                        "reason": str(exc),
                                    }
                                )
                                continue
                            issue_frames["base"].append(base)
                            issue_frames["candidate"].append(candidate)
                            issue_frames["continuation"].append(continuation)
                            issue_action_counts[issue] = issue_action_counts.get(issue, 0) + 1
            for name, frames in issue_frames.items():
                nonempty = [frame for frame in frames if not frame.empty]
                if not nonempty:
                    continue
                frame = pd.concat(nonempty, ignore_index=True)
                table = pa.Table.from_pandas(frame, preserve_index=False)
                if name not in writers:
                    writers[name] = pq.ParquetWriter(
                        temporary[name], table.schema, compression="zstd"
                    )
                writers[name].write_table(table)
                rows[name] += len(frame)
            if issue_number % 25 == 0:
                print(
                    f"manifest issues={issue_number}/{len(issue_order)} "
                    f"candidate_rows={rows['candidate']}",
                    flush=True,
                )
    finally:
        for writer in writers.values():
            writer.close()
    for name, path in targets.items():
        if name not in writers:
            raise RuntimeError(f"no {name} manifest rows were produced")
        temporary[name].replace(path)
    exclusion_frame = pd.DataFrame(exclusions)
    exclusion_frame.to_csv(output / "manifest_exclusions.csv", index=False)
    receipt = {
        "contract": "BJ-UNIFIED-JOINT-PROTECTION-001/label-free-manifest-v1",
        "horizon": "10h",
        "issues_requested": len(issue_order),
        "issues_materialized": int(
            pq.read_table(targets["base"], columns=["issue"])
            .to_pandas()["issue"]
            .nunique()
        ),
        "rows": rows,
        "action_cells_materialized": int(sum(issue_action_counts.values())),
        "expected_full_action_cells": int(len(issue_order) * 48),
        "fully_supported_48_action_issues": int(
            sum(count == 48 for count in issue_action_counts.values())
        ),
        "partial_action_support": {
            issue: count for issue, count in issue_action_counts.items() if count != 48
        },
        "action_levels": {
            "n": [7, 8, 9],
            "k": [16, 64],
            "selectors": list(SELECTORS),
            "outcome_modes": list(OUTCOME_MODES),
            "generators": list(GENERATORS),
        },
        "settlement_columns_opened": [],
        "source_sha256": {
            "relative_horizon_view": _sha256(INFERENCE_VIEW),
            "subset_profile": _sha256(profile_path),
        },
        "manifest_sha256": {name: _sha256(path) for name, path in targets.items()},
        "exclusions": len(exclusions),
    }
    _atomic_json(receipt, output / "label_free_manifest_receipt.json")
    print(json.dumps(receipt, indent=2), flush=True)
    return 0


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
