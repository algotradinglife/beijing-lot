#!/usr/bin/env python3
"""Compare executable segment betting plan artifacts without rerunning decisions."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any


def fnum(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def inum(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def resolve_artifact_path(summary_path: Path, value: Any, fallback_name: str) -> Path:
    candidate = Path(str(value or fallback_name))
    if candidate.is_absolute():
        return candidate
    if candidate.is_file():
        return candidate.resolve()
    return summary_path.parent / candidate.name


def bundle_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    if not rows:
        return {
            "base_bundles": 0,
            "expanded_tickets": 0,
            "selected_cost_yuan": 0.0,
            "covered_match_count": 0,
            "mean_pair_overlap": 0.0,
            "max_pair_overlap": 0,
            "mean_pair_jaccard": 0.0,
            "max_bundle_cost_share": 0.0,
            "max_match_cost_exposure_share": 0.0,
            "selected_leg_single_share": 0.0,
            "selected_leg_double_share": 0.0,
            "selected_leg_full_share": 0.0,
        }

    match_sets = [{inum(item) for item in row.get("match_indices", "").split(",") if item} for row in rows]
    pair_overlaps = [len(left & right) for left, right in combinations(match_sets, 2)]
    pair_jaccards = [len(left & right) / len(left | right) for left, right in combinations(match_sets, 2) if left | right]
    scaled_costs = [fnum(row.get("scaled_cost_yuan")) for row in rows]
    total_cost = sum(scaled_costs)
    match_exposure: dict[int, float] = defaultdict(float)
    width_counts: dict[int, int] = defaultdict(int)
    for row, matches, scaled_cost in zip(rows, match_sets, scaled_costs):
        per_match_cost = scaled_cost / len(matches) if matches else 0.0
        for match_idx in matches:
            match_exposure[match_idx] += per_match_cost
        for width in row.get("widths", "").split(","):
            width_counts[inum(width)] += 1
    leg_slots = sum(width_counts.values())
    return {
        "base_bundles": len(rows),
        "expanded_tickets": round(sum(fnum(row.get("scaled_cost_units")) for row in rows), 6),
        "selected_cost_yuan": round(total_cost, 6),
        "covered_match_count": len(set().union(*match_sets)),
        "mean_pair_overlap": round(sum(pair_overlaps) / len(pair_overlaps), 6) if pair_overlaps else 0.0,
        "max_pair_overlap": max(pair_overlaps, default=0),
        "mean_pair_jaccard": round(sum(pair_jaccards) / len(pair_jaccards), 6) if pair_jaccards else 0.0,
        "max_bundle_cost_share": round(max(scaled_costs, default=0.0) / total_cost, 6) if total_cost else 0.0,
        "max_match_cost_exposure_share": round(max(match_exposure.values(), default=0.0) / total_cost, 6) if total_cost else 0.0,
        "selected_leg_single_share": round(width_counts[1] / leg_slots, 6) if leg_slots else 0.0,
        "selected_leg_double_share": round(width_counts[2] / leg_slots, 6) if leg_slots else 0.0,
        "selected_leg_full_share": round(width_counts[3] / leg_slots, 6) if leg_slots else 0.0,
    }


def audit_plan(summary_path: Path) -> dict[str, Any]:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    bundle_path = resolve_artifact_path(summary_path, payload.get("bundle_csv"), "segment_betting_plan_bundles.csv")
    segment_path = resolve_artifact_path(summary_path, payload.get("segment_csv"), "segment_betting_plan_segments.csv")
    bundle_rows = read_csv(bundle_path)
    segment_rows = read_csv(segment_path)
    seeds = sorted({inum(row.get("sample_seed")) for row in bundle_rows if row.get("sample_seed")})
    primary_seed = seeds[0] if seeds else 0
    primary_bundles = [row for row in bundle_rows if inum(row.get("sample_seed")) == primary_seed]
    primary_segments = [row for row in segment_rows if inum(row.get("sample_seed")) == primary_seed]
    segment_audits: list[dict[str, Any]] = []
    for segment_row in primary_segments:
        segment_idx = inum(segment_row.get("segment_idx"))
        rows = [row for row in primary_bundles if inum(row.get("segment_idx")) == segment_idx]
        segment_audits.append({
            "segment_idx": segment_idx,
            "eligible_matches": inum(segment_row.get("eligible_matches")),
            "recommended_n": inum(segment_row.get("recommended_n")),
            "expected_roi": fnum(segment_row.get("expected_roi")),
            **bundle_metrics(rows),
        })
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "label": payload.get("label", summary_path.parent.name),
        "summary_path": str(summary_path),
        "primary_seed": primary_seed,
        "max_selected_bundles": inum((payload.get("settings") or {}).get("max_selected_bundles")),
        "mean_selected_bundles": fnum(summary.get("selected_bundles")),
        "mean_selected_cost_yuan": fnum(summary.get("selected_cost_yuan")),
        "mean_expected_roi": fnum(summary.get("expected_roi")),
        "segments": segment_audits,
    }


def metric_delta(current: dict[str, Any], baseline: dict[str, Any], key: str) -> float:
    return round(fnum(current.get(key)) - fnum(baseline.get(key)), 6)


def compare(audits: list[dict[str, Any]]) -> dict[str, Any]:
    baseline = audits[0]
    baseline_segments = {row["segment_idx"]: row for row in baseline["segments"]}
    comparisons = []
    for audit in audits[1:]:
        segment_deltas = []
        for segment in audit["segments"]:
            reference = baseline_segments.get(segment["segment_idx"], {})
            segment_deltas.append({
                "segment_idx": segment["segment_idx"],
                **{
                    f"{key}_delta": metric_delta(segment, reference, key)
                    for key in (
                        "base_bundles",
                        "expanded_tickets",
                        "covered_match_count",
                        "mean_pair_overlap",
                        "mean_pair_jaccard",
                        "max_bundle_cost_share",
                        "max_match_cost_exposure_share",
                        "expected_roi",
                    )
                },
            })
        comparisons.append({
            "label": audit["label"],
            "mean_selected_bundles_delta": metric_delta(audit, baseline, "mean_selected_bundles"),
            "mean_selected_cost_yuan_delta": metric_delta(audit, baseline, "mean_selected_cost_yuan"),
            "mean_expected_roi_delta": metric_delta(audit, baseline, "mean_expected_roi"),
            "segments": segment_deltas,
        })
    return {"schema_version": "segment_betting_plan_version_audit_v1", "baseline": baseline["label"], "plans": audits, "comparisons": comparisons}


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Segment Betting Plan Version Audit",
        "",
        f"Baseline: `{result['baseline']}`",
        "",
        "| Plan | Cap | Segment | Base bundles | Expanded tickets | Covered matches | Mean overlap | Max bundle share | Max match exposure | Expected ROI |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for plan in result["plans"]:
        for segment in plan["segments"]:
            lines.append(
                f"| {plan['label']} | {plan['max_selected_bundles']} | {segment['segment_idx']} | "
                f"{segment['base_bundles']} | {segment['expanded_tickets']:.0f} | {segment['covered_match_count']} | "
                f"{segment['mean_pair_overlap']:.3f} | {segment['max_bundle_cost_share']:.1%} | "
                f"{segment['max_match_cost_exposure_share']:.1%} | {segment['expected_roi']:.3f} |"
            )
    lines.extend(["", "Expected ROI is a pre-match model proxy, not settled return.", ""])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="append", type=Path, required=True, help="Summary JSON; first item is the baseline.")
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-markdown", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = compare([audit_plan(path.resolve()) for path in args.summary])
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.output_markdown:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(render_markdown(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
