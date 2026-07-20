#!/usr/bin/env python3
"""Run the non-executable proxy replay from explicit, read-only source paths."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.handicap_draw_projection import (
    ApproximateReplayConfig,
    build_checksummed_approximate_artifact,
    fit_final_proxy_candidates,
    run_approximate_issue_replay,
    summarize_predictions,
)
from research.handicap_draw_projection.replay_io import (
    load_a5_proxy_rows,
    load_historical_proxy_rows,
    sha256_file,
)


STATUS = "research_only_approximate_non_executable_non_selectable_roi_unauthorized"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--core-dataset", type=Path, required=True)
    parser.add_argument("--baseline-predictions", type=Path, required=True)
    parser.add_argument("--team-strength-predictions", type=Path, required=True)
    parser.add_argument("--a5-predictions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-training-issues", type=int, default=20)
    parser.add_argument("--min-training-rows", type=int, default=5_000)
    parser.add_argument("--refit-interval-issues", type=int, default=10)
    return parser.parse_args()


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _verified_source_sha256(path: Path) -> str:
    sums_path = path.parent / "SHA256SUMS"
    if not sums_path.is_file():
        raise ValueError(f"missing source checksum manifest: {sums_path}")
    expected = None
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1] == path.name:
            expected = parts[0]
            break
    if expected is None:
        raise ValueError(f"source checksum not recorded: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"source checksum mismatch: {path}")
    return actual


def _summary_rows(summaries: tuple[object, ...], cohort: str) -> list[dict[str, object]]:
    return [{"cohort": cohort, **asdict(summary)} for summary in summaries]  # type: ignore[arg-type]


def _comparisons(summaries: tuple[object, ...]) -> list[dict[str, object]]:
    values = {summary.candidate: summary for summary in summaries}  # type: ignore[attr-defined]
    baseline = values["baseline_handicap_probability"]
    g1 = values["g1_score_projection"]
    comparisons: list[dict[str, object]] = []
    for candidate in values.values():
        comparisons.append(
            {
                "candidate": candidate.candidate,
                "draw_brier_delta_vs_baseline": candidate.binary_draw_brier - baseline.binary_draw_brier,
                "draw_brier_delta_vs_g1": candidate.binary_draw_brier - g1.binary_draw_brier,
                "draw_log_loss_delta_vs_baseline": candidate.binary_draw_log_loss - baseline.binary_draw_log_loss,
                "draw_log_loss_delta_vs_g1": candidate.binary_draw_log_loss - g1.binary_draw_log_loss,
                "three_way_brier_delta_vs_baseline": candidate.three_way_brier - baseline.three_way_brier,
                "three_way_brier_delta_vs_g1": candidate.three_way_brier - g1.three_way_brier,
                "three_way_log_loss_delta_vs_baseline": candidate.three_way_log_loss - baseline.three_way_log_loss,
                "three_way_log_loss_delta_vs_g1": candidate.three_way_log_loss - g1.three_way_log_loss,
                "draw_ece_delta_vs_baseline": candidate.draw_ece_10bin - baseline.draw_ece_10bin,
                "draw_ece_delta_vs_g1": candidate.draw_ece_10bin - g1.draw_ece_10bin,
            }
        )
    return comparisons


def _prediction_rows(predictions: tuple[object, ...]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for prediction in predictions:
        records.append(
            {
                "issue": prediction.issue_id,
                "match_id": prediction.match_id,
                "match_idx": prediction.match_index,
                "candidate": prediction.candidate,
                "p3": prediction.probabilities[0],
                "p1_draw": prediction.probabilities[1],
                "p0": prediction.probabilities[2],
                "outcome": prediction.outcome,
                "blend_weight": prediction.blend_weight,
                "training_issue_count": len(prediction.training_issue_ids),
                "training_issue_max": prediction.training_issue_ids[-1] if prediction.training_issue_ids else "",
            }
        )
    return records


def main() -> None:
    args = _arguments()
    config = ApproximateReplayConfig(
        min_training_issues=args.min_training_issues,
        min_training_rows=args.min_training_rows,
        refit_interval_issues=args.refit_interval_issues,
        retain_common_predictions=False,
    )
    historical_rows = load_historical_proxy_rows(
        args.core_dataset, args.baseline_predictions, args.team_strength_predictions
    )
    a5_rows = load_a5_proxy_rows(args.a5_predictions)
    result = run_approximate_issue_replay(historical_rows, config)
    if not result.eligibility.eligible:
        raise SystemExit(f"ineligible replay: {result.eligibility.reasons}")
    a5_predictions = fit_final_proxy_candidates(historical_rows, a5_rows, config)
    a5_summaries = summarize_predictions(a5_predictions)
    if not {row.issue_id for row in a5_rows}.isdisjoint(row.issue_id for row in historical_rows):
        raise SystemExit("A5 diagnostic overlaps the training panel")

    evidence = {
        "S13_0002_core_dataset": _verified_source_sha256(args.core_dataset),
        "S13_0003_baseline_predictions": _verified_source_sha256(args.baseline_predictions),
        "S13_0004_team_strength_predictions": _verified_source_sha256(args.team_strength_predictions),
        "S13_A5_frozen_predictions": _verified_source_sha256(args.a5_predictions),
    }
    artifact = build_checksummed_approximate_artifact(result, evidence=evidence, config=config)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_rows = _summary_rows(result.all_panel_summaries, "all_historical")
    metrics_rows += _summary_rows(result.common_cohort_summaries, "walk_forward_common_cohort")
    metrics_rows += _summary_rows(a5_summaries, "a5_untouched_diagnostic")
    _write_csv(
        output_dir / "proper_score_metrics.csv",
        list(metrics_rows[0]),
        metrics_rows,
    )
    _write_csv(
        output_dir / "a5_diagnostic_predictions.csv",
        [
            "issue", "match_id", "match_idx", "candidate", "p3", "p1_draw", "p0", "outcome",
            "blend_weight", "training_issue_count", "training_issue_max",
        ],
        _prediction_rows(a5_predictions),
    )
    payload = {
        **artifact["payload"],
        "experiment_id": "S13_0005_approximate_score_projection_draw_replay_v1",
        "a5_diagnostic": {
            "issues": sorted({row.issue_id for row in a5_rows}, key=int),
            "fit_on_a5": False,
            "summaries": [asdict(summary) for summary in a5_summaries],
            "comparisons": _comparisons(a5_summaries),
        },
        "walk_forward_common_cohort_comparisons": _comparisons(result.common_cohort_summaries),
        "source_row_counts": {"historical": len(historical_rows), "a5": len(a5_rows)},
        "allowed_input_fields": {
            "historical": ["identity", "settled_handicap_label", "G0_probabilities", "G1_probabilities"],
            "a5": ["identity", "settled_handicap_label", "G0_probabilities", "G1_probabilities"],
        },
        "excluded_inputs": ["terminal_correct_score_odds", "roi", "ticket_data", "payout_data"],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    final_artifact = {"payload": payload, "payload_sha256": hashlib.sha256(encoded).hexdigest()}
    with (output_dir / "artifact.json").open("w", encoding="utf-8") as handle:
        json.dump(final_artifact, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    output_hashes = {
        path.name: sha256_file(path)
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != "SHA256SUMS"
    }
    with (output_dir / "SHA256SUMS").open("w", encoding="utf-8") as handle:
        for name, digest in output_hashes.items():
            handle.write(f"{digest}  {name}\n")
    print(json.dumps({"status": STATUS, "artifact_sha256": final_artifact["payload_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
