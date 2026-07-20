"""Delimited-file adapter for the approximate score-play replay.

Only this adapter reads the supplied proxy artifacts.  Its field allowlists
make the exclusion of terminal correct-score odds, payout/ROI, and ticket
data inspectable.  It has no discovery or database path.
"""
from __future__ import annotations

import csv
import hashlib
from itertools import zip_longest
from pathlib import Path

from .approximate_replay import ApproximateReplayRow


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _probabilities(row: dict[str, str], prefix: str) -> tuple[float, float, float]:
    return tuple(float(row[f"{prefix}_{outcome}"]) for outcome in ("p3", "p1", "p0"))  # type: ignore[return-value]


def _core_baseline_probabilities(row: dict[str, str]) -> tuple[float, float, float]:
    return float(row["p_sp_3"]), float(row["p_sp_1"]), float(row["p_sp_0"])


def load_historical_proxy_rows(
    core_dataset: Path, baseline_predictions: Path, team_strength_predictions: Path
) -> tuple[ApproximateReplayRow, ...]:
    """Join only identity, label, G0 baseline, and G1 projection columns.

    The core dataset is an integrity anchor.  It is not used to add a feature;
    its raw prices and all market fields are intentionally outside this
    adapter's allowlist.
    """

    values: list[ApproximateReplayRow] = []
    sentinel = object()
    with (
        core_dataset.open(newline="", encoding="utf-8") as core_handle,
        baseline_predictions.open(newline="", encoding="utf-8") as baseline_handle,
        team_strength_predictions.open(newline="", encoding="utf-8") as team_handle,
    ):
        triples = zip_longest(
            csv.DictReader(core_handle),
            csv.DictReader(baseline_handle),
            csv.DictReader(team_handle),
            fillvalue=sentinel,
        )
        for core_row, baseline_row, team_row in triples:
            if sentinel in (core_row, baseline_row, team_row):
                raise ValueError("source_key_sets_do_not_match")
            assert isinstance(core_row, dict)
            assert isinstance(baseline_row, dict)
            assert isinstance(team_row, dict)
            key = (core_row["issue"], int(core_row["match_idx"]))
            if key != (baseline_row["issue"], int(baseline_row["match_idx"])) or key != (
                team_row["issue"], int(team_row["match_idx"])
            ):
                raise ValueError("source_key_sets_do_not_match")
            if (
                core_row["label_handicap_result"] != baseline_row["label"]
                or core_row["label_handicap_result"] != team_row["label"]
                or float(core_row["handicap_line"]) != float(baseline_row["handicap_line"])
                or float(core_row["handicap_line"]) != float(team_row["handicap_line"])
            ):
                raise ValueError("source_label_or_handicap_mismatch")
            baseline_probabilities = _probabilities(baseline_row, "g0")
            if any(
                abs(left - right) > 1e-12
                for left, right in zip(baseline_probabilities, _core_baseline_probabilities(core_row))
            ):
                raise ValueError("baseline_not_equal_to_frozen_core_probability")
            g1_probabilities = _probabilities(baseline_row, "g1_1h")
            if any(
                abs(left - right) > 1e-12
                for left, right in zip(g1_probabilities, _probabilities(team_row, "g1"))
            ):
                raise ValueError("g1_sources_do_not_agree")
            values.append(
                ApproximateReplayRow(
                    issue_id=core_row["issue"],
                    match_id=core_row["match_id"],
                    match_index=key[1],
                    baseline_probabilities=baseline_probabilities,
                    g1_probabilities=g1_probabilities,
                    outcome=core_row["label_handicap_result"],  # type: ignore[arg-type]
                )
            )
    return tuple(values)


def load_a5_proxy_rows(a5_predictions: Path) -> tuple[ApproximateReplayRow, ...]:
    """Read the frozen A5 G0/G1 diagnostic fields without fitting on them."""

    values: list[ApproximateReplayRow] = []
    for row in _csv_rows(a5_predictions):
        values.append(
            ApproximateReplayRow(
                issue_id=row["issue"],
                match_id=row["match_id"],
                match_index=int(row["match_idx"]),
                baseline_probabilities=_probabilities(row, "g0"),
                g1_probabilities=_probabilities(row, "g1"),
                outcome=row["label_handicap_result"],  # type: ignore[arg-type]
            )
        )
    return tuple(values)
