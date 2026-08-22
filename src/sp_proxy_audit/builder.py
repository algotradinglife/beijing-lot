"""Build the immutable Issue #318 SP/proxy admissibility package."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from .data import AuditPaths, load_all_cells, sha256, source_inventory
from .grading import grade_vectors
from .metrics import (
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
    coverage_by_issue,
    exclusion_ledger,
    overlap_diagnostics,
    terminal_decision,
)

CONTRACT = "BJ-UNIFIED-SP-PROXY-AUDIT-001/v1"
REQUIRED_COLUMNS = [
    "issue_code",
    "match_idx",
    "outcome_code",
    "source_id",
    "source_grade",
    "snapshot_kind",
    "observed_at_utc",
    "decision_epoch_utc",
    "kickoff_utc",
    "sp_value",
    "probability_source",
    "probability_value",
    "q_value",
    "fixture_identity",
    "exclusion_reason",
]
THRESHOLDS = {
    "strict_min_issues_per_partition": 30,
    "strict_min_n7_rate": 0.80,
    "proxy_min_overlap_issues": 20,
    "proxy_min_overlap_fixtures": 500,
    "proxy_min_spearman": 0.75,
    "proxy_min_top2": 0.85,
    "proxy_min_top7_jaccard": 0.70,
    "proxy_max_median_abs_log_price_error": 0.15,
    "bootstrap_resamples": BOOTSTRAP_REPLICATES,
    "bootstrap_seed": BOOTSTRAP_SEED,
}


def _json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _fsync(path: Path, *, directory: bool = False) -> None:
    flags = os.O_RDONLY | (getattr(os, "O_DIRECTORY", 0) if directory else 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _save_figure(path: Path) -> None:
    plt.tight_layout()
    plt.savefig(
        path,
        dpi=140,
        metadata={"Software": "beijing-lot Issue #318"},
    )
    plt.close()


def _figures(
    staging: Path, coverage: pd.DataFrame, overlap: pd.DataFrame, paired: pd.DataFrame
) -> None:
    accepted = coverage.loc[
        coverage["source_grade"].isin(["STRICT_PRE_EVENT", "HISTORICAL_PROXY"])
    ]
    if accepted.empty:
        plt.figure(figsize=(9, 5))
        plt.title("Accepted vector coverage by partition")
        plt.text(0.5, 0.5, "No accepted vectors", ha="center", va="center")
        plt.axis("off")
    else:
        chart = (
            accepted.groupby(["partition", "source_grade"], observed=True)[
                "vector_count"
            ]
            .sum()
            .unstack(fill_value=0)
        )
        ax = chart.plot(
            kind="bar", figsize=(9, 5), title="Accepted vector coverage by partition"
        )
        ax.set_ylabel("complete Mx3 vectors")
        ax.set_xlabel("partition")
    _save_figure(staging / "coverage_by_partition.png")

    if overlap.empty:
        for name, title in (
            ("price_error_by_horizon.png", "No strict/proxy overlap"),
            ("top2_top7_agreement.png", "No strict/proxy overlap"),
            ("q_distortion.png", "No strict/proxy overlap"),
        ):
            plt.figure(figsize=(9, 5))
            plt.title(title)
            plt.text(0.5, 0.5, "No exact accepted overlap", ha="center", va="center")
            plt.axis("off")
            _save_figure(staging / name)
        return

    ordered = overlap.sort_values(["partition", "snapshot_kind"], kind="mergesort")
    plt.figure(figsize=(9, 5))
    plt.bar(ordered["snapshot_kind"], ordered["median_abs_log_price_error_issue_equal"])
    plt.axhline(
        THRESHOLDS["proxy_max_median_abs_log_price_error"],
        color="red",
        linestyle="--",
        label="frozen maximum",
    )
    plt.ylabel("issue-equal median absolute log-price error")
    plt.title("Proxy price error by relative horizon")
    plt.legend()
    _save_figure(staging / "price_error_by_horizon.png")

    x = np.arange(len(ordered))
    plt.figure(figsize=(9, 5))
    plt.plot(
        x, ordered["top2_agreement_issue_equal"], marker="o", label="Top-2 agreement"
    )
    plt.plot(x, ordered["top7_jaccard_issue_equal"], marker="o", label="Top-7 Jaccard")
    plt.xticks(x, ordered["snapshot_kind"])
    plt.ylim(0, 1.05)
    plt.title("Outcome and match-selection agreement")
    plt.legend()
    _save_figure(staging / "top2_top7_agreement.png")

    plt.figure(figsize=(9, 5))
    available = paired.loc[paired["q_distortion"].notna()]
    data = [
        available.loc[available["snapshot_kind"].eq(horizon), "q_distortion"].to_numpy()
        for horizon in ordered["snapshot_kind"]
    ]
    plt.boxplot(data, tick_labels=ordered["snapshot_kind"], showfliers=False)
    plt.axhline(0, color="black", linewidth=0.8)
    plt.ylabel("q_proxy - q_strict")
    plt.title("q distortion by relative horizon")
    _save_figure(staging / "q_distortion.png")


def _recommendation(disposition: str) -> str:
    if disposition == "STRICT_HISTORY_AVAILABLE":
        return "Historical strict Beijing SP is admissible under the frozen partitions."
    if disposition == "PROXY_USABLE_FOR_EXPLORATION":
        return "Use only the passing relative proxy lanes for exploration; no promotion authority is granted."
    return "Do not use historical Beijing SP or its current proxy for value ranking; #319 may proceed probability-only while #218 accumulates strict prospective support."


def _publish(staging: Path, output: Path) -> None:
    for artifact in staging.iterdir():
        if artifact.is_file():
            _fsync(artifact)
    _fsync(staging, directory=True)
    if not output.exists():
        os.replace(staging, output)
        _fsync(output.parent, directory=True)
        return
    backup = output.with_name(output.name + ".previous")
    if backup.exists():
        shutil.rmtree(backup)
    os.replace(output, backup)
    _fsync(output.parent, directory=True)
    try:
        os.replace(staging, output)
        _fsync(output.parent, directory=True)
    except BaseException:
        os.replace(backup, output)
        _fsync(output.parent, directory=True)
        raise
    shutil.rmtree(backup)
    _fsync(output.parent, directory=True)


def build_package(repo_root: Path, data_root: Path, output: Path) -> dict[str, object]:
    """Read every frozen source, compute metrics, and publish an atomic package."""
    repo_root = repo_root.resolve()
    data_root = data_root.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    paths = AuditPaths(repo_root=repo_root, data_root=data_root)
    inventory = source_inventory(paths)
    raw = load_all_cells(paths, inventory)
    cells = grade_vectors(raw)
    if (
        not cells.groupby(
            list(("source_id", "issue_code", "match_idx", "snapshot_kind")),
            dropna=False,
        )
        .size()
        .eq(3)
        .all()
    ):
        raise ValueError("normalized Mx3 output is not exactly three cells per vector")
    cells = cells[REQUIRED_COLUMNS + ["provenance_sha256"]]
    coverage = coverage_by_issue(cells)
    exclusions = exclusion_ledger(cells, inventory)
    paired, issue_overlap, overlap = overlap_diagnostics(cells)
    terminal = terminal_decision(cells, overlap, inventory)
    disposition = str(terminal["terminal_disposition"])
    decision = {
        "contract_version": CONTRACT,
        "source_hashes": {
            row.source_id: row.sha256 if pd.notna(row.sha256) else None
            for row in inventory.itertuples(index=False)
        },
        "thresholds": THRESHOLDS,
        "observed_metrics": {
            "graded_cells": int(len(cells)),
            "strict_accepted_cells": int(
                cells["source_grade"].eq("STRICT_PRE_EVENT").sum()
            ),
            "proxy_accepted_cells": int(
                cells["source_grade"].eq("HISTORICAL_PROXY").sum()
            ),
            "overlap_cells": int(len(paired)),
            "overlap_issues": int(issue_overlap["issue_code"].nunique())
            if not issue_overlap.empty
            else 0,
        },
        **terminal,
        "recommendation": _recommendation(disposition),
    }

    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent)
    )
    try:
        inventory.to_csv(staging / "source_inventory.csv", index=False)
        cells.to_parquet(
            staging / "graded_cells.parquet", index=False, compression="zstd"
        )
        coverage.to_csv(staging / "coverage_by_issue.csv", index=False)
        overlap.to_csv(staging / "overlap_metrics.csv", index=False)
        issue_overlap.to_csv(staging / "issue_overlap_diagnostics.csv", index=False)
        paired.to_parquet(
            staging / "overlap_cells.parquet", index=False, compression="zstd"
        )
        exclusions.to_parquet(
            staging / "exclusion_ledger.parquet", index=False, compression="zstd"
        )
        _json(staging / "decision.json", decision)
        _figures(staging, coverage, overlap, paired)
        files = {
            str(path.relative_to(staging)): sha256(path)
            for path in sorted(staging.iterdir())
            if path.is_file()
        }
        _json(
            staging / "MANIFEST.json",
            {
                "contract_version": CONTRACT,
                "files": files,
                "source_inventory_sha256": sha256(staging / "source_inventory.csv"),
            },
        )
        checksums = {
            str(path.relative_to(staging)): sha256(path)
            for path in sorted(staging.iterdir())
            if path.is_file()
        }
        _json(staging / "SHA256SUMS.json", checksums)
        _publish(staging, output)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return decision
