#!/usr/bin/env python3
"""Finalize hashes and portable metadata for the #145 Gate-B v2 package."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import shutil
from pathlib import Path


BASE_COMPRESSED = (
    "issue_allocation_settlement.csv.gz",
    "winning_ticket_tax_ledger.csv.gz",
)
COPY_SOURCES = {
    "settlement_runner.py": "settle_bj145_ticket_allocation_gate_b.py",
    "settlement_finalizer_v2.py": "finalize_bj145_gate_b_v2.py",
    "derived_rebuilder.py": "rebuild_bj145_gate_b_derived.py",
    "outcome_code_marginal_builder.py": "build_bj145_outcome_code_marginals.py",
    "outcome_code_marginal_merger.py": "merge_bj145_code_marginal_shards.py",
    "outcome_code_atlas_splitter.py": "split_bj145_code_atlas.py",
    "chart_generator_v2.py": "plot_bj145_gate_b_v2.py",
    "report_generator_v2.py": "report_bj145_gate_b_v2.py",
    "bj145_fast_alloc.cpp": "bj145_fast_alloc.cpp",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decompressed(path: Path) -> tuple[str, int, int]:
    digest, size, lines = hashlib.sha256(), 0, 0
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
            lines += chunk.count(b"\n")
    return digest.hexdigest(), size, lines - 1


def atlas_paths(package: Path) -> list[Path]:
    index_path = package / "outcome_code_frequency.index.json"
    if index_path.is_file():
        if (package / "outcome_code_frequency.csv.gz").exists():
            raise RuntimeError("single-file and split code atlases cannot coexist")
        index = json.loads(index_path.read_text(encoding="utf-8"))
        paths = [package / part["file"] for part in index["parts"]]
        if len(paths) != index["part_count"] or any(
            not path.is_file() for path in paths
        ):
            raise RuntimeError("code-atlas part index drift")
        for path, part in zip(paths, index["parts"]):
            if sha256(path) != part["sha256"] or path.stat().st_size != part["bytes"]:
                raise RuntimeError(f"code-atlas indexed identity drift: {path.name}")
        return paths
    single = package / "outcome_code_frequency.csv.gz"
    if not single.is_file():
        raise RuntimeError("complete code atlas unavailable")
    return [single]


def logical_atlas_identity(paths: list[Path]) -> tuple[str, int, int]:
    digest, size, rows = hashlib.sha256(), 0, 0
    header = None
    for index, path in enumerate(paths):
        with gzip.open(path, "rb") as handle:
            current_header = handle.readline()
            if not current_header or (header is not None and current_header != header):
                raise RuntimeError(f"code-atlas header drift: {path.name}")
            header = header or current_header
            if index == 0:
                digest.update(current_header)
                size += len(current_header)
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
                size += len(chunk)
                rows += chunk.count(b"\n")
    return digest.hexdigest(), size, rows


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    scripts = Path(__file__).resolve().parent
    for target, source in COPY_SOURCES.items():
        shutil.copy2(scripts / source, package / target)
    summary = read_rows(package / "mechanism_weight_surface_summary.csv")
    full = read_rows(package / "full_control_deltas.csv")
    pairwise = read_rows(package / "mechanism_pairwise_deltas.csv")
    loio = read_rows(package / "leave_one_issue_out_summary.csv")
    largest = read_rows(package / "largest_issue_exclusion.csv")
    bootstrap = read_rows(package / "issue_bootstrap.csv")
    multiple = read_rows(package / "multiple_comparison.csv")
    tax = read_rows(package / "tax_reconciliation.csv")
    expected_counts = {
        "summary": (len(summary), 63624),
        "full_control": (len(full), 63360),
        "mechanism_pairwise": (len(pairwise), 12960),
        "leave_one_issue_out": (len(loio), 2892),
        "largest_issue_exclusion": (len(largest), 2892),
        "bootstrap": (len(bootstrap), 5760),
        "multiple_comparison": (len(multiple), 2880),
        "tax_reconciliation": (len(tax), 2892),
    }
    drift = {
        name: values
        for name, values in expected_counts.items()
        if values[0] != values[1]
    }
    if drift:
        raise RuntimeError(f"v2 row-count drift: {drift}")
    full_all = [
        row
        for row in summary
        if row["scope"] == "ALL" and row["mechanism"] == "FULL_ENUMERATED"
    ]
    if len(full_all) != 12 or any(
        row["coverage_hit_rate"] != "1.000000000000" for row in full_all
    ):
        raise RuntimeError("FULL settled-support coverage regression")
    if {int(row["M"]) for row in pairwise} != set(range(16, 257, 16)) | {
        512,
        1024,
        1458,
        2187,
    }:
        raise RuntimeError("mechanism pairwise M-grid drift")
    for chart in (
        "roi_vs_m_cap.svg",
        "matched_pre_tax_comparison.svg",
        "uncertainty_stability.svg",
    ):
        if not (package / chart).is_file():
            raise RuntimeError(f"missing chart: {chart}")
    if list(package.glob("*.sqlite")) or list(package.glob("*.db")):
        raise RuntimeError("mutable database leaked into immutable package")
    top = sorted(
        (row for row in full if row["scope"] == "ALL" and row["no_tax_roi_delta"]),
        key=lambda row: float(row["no_tax_roi_delta"]),
        reverse=True,
    )[:20]
    decision = {
        "decision": "DESCRIPTIVE_SURFACE_ONLY_NO_PROMOTION",
        "promotion_authorized": False,
        "primary_metric": "pre-tax no_tax_roi including the 0.65 BJ Single Match payout factor",
        "tax_secondary": "20pct per individual winning ticket iff gross >= 10000 yuan; no pooling or aggregation",
        "support_rule": "coverage, miss streak and drawdown use settled positive-stake issue rows; Gate-A no-bets and unavailable outcomes are separate",
        "complete_code_atlas": "2,187 codes per each of 2,892 configurations; target/allocated/delta and actual hits separate",
        "positive_same_window_rule": "descriptive only; strict independent EV and genuinely held-out/forward validation required",
        "top_pre_tax_full_deltas": top,
        "negative_control": "No purchase, production, betting or promotion authority",
    }
    (package / "decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    code_files = atlas_paths(package)
    code_digest, code_bytes, code_rows = logical_atlas_identity(code_files)
    if code_rows != 6_324_804:
        raise RuntimeError(f"complete code-atlas denominator drift: {code_rows}")
    card = {
        "issue": 145,
        "contract": "BJ-HIST-TICKET-ALLOCATION-001",
        "version": "bj145-gate-b-v2-substantive-correction",
        "supersedes": "results/bj145_gate_b_outcome_settlement_v1 (retained unchanged)",
        "gate_a_manifest_sha256": "da1165d3d2be49deac85a494443ba04606d176ca059c265857573ce24360114c",
        "outcome_manifest_sha256": "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc",
        "outcome_payload_sha256": "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89",
        "source_manifests_transitive": {
            "bj137": "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df",
            "bj148": "fd4a0f4dc0ab5ef97f3c260a082515aa7874a60a1ac1e5e0ecd865fdb1eeafd6",
            "bj151": "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6",
            "bj154": "f81146959fd734c3d15a2579a3921b2afc86d6f633e174c8294763279f9937c5",
        },
        "surface": {
            "issue_rows": 1006416,
            "configuration_count": 2892,
            "summary_rows": len(summary),
            "full_control_delta_rows": len(full),
            "mechanism_pairwise_rows": len(pairwise),
            "bootstrap_rows": len(bootstrap),
            "holm_rows": len(multiple),
            "tax_reconciliation_rows": len(tax),
            "leave_one_issue_out_rows": len(loio),
            "largest_issue_exclusion_rows": len(largest),
            "outcome_code_rows": code_rows,
            "codes_per_configuration": 2187,
        },
        "m_grid": list(range(16, 257, 16)) + [512, 1024, 1458, 2187],
        "support_rule": decision["support_rule"],
        "drawdown_rule": "chronological cumulative tax-adjusted net over settled positive-stake issue rows",
        "outcome_code_decompressed_sha256": code_digest,
        "outcome_code_decompressed_bytes": code_bytes,
        "outcome_code_files": [path.name for path in code_files],
        "charts": [
            "roi_vs_m_cap.svg",
            "matched_pre_tax_comparison.svg",
            "uncertainty_stability.svg",
        ],
        "tax_rule": decision["tax_secondary"],
        "decision": decision["decision"],
        "promotion_authorized": False,
    }
    (package / "settlement_card.json").write_text(
        json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    compressed_names = (*BASE_COMPRESSED, *(path.name for path in code_files))
    compressed_identity = {}
    for name in compressed_names:
        digest, size, rows = decompressed(package / name)
        compressed_identity[name] = {
            "canonical_decompressed_sha256": digest,
            "canonical_decompressed_bytes": size,
            "rows": rows,
        }
    controls = {
        path.name: sha256(path)
        for path in sorted(package.iterdir())
        if path.is_file()
        and path.name not in compressed_names
        and path.name not in {"CONTENT_IDENTITY.json", "SHA256SUMS.json"}
    }
    content = {
        "contract_version": "bj145-gate-b-portable-content-v2",
        "gzip_payloads": compressed_identity,
        "non_compressed_controls": controls,
        "outcome_boundary": "Gate-A allocations unchanged; v2 corrects only settlement-derived summaries, complete code marginals, analyses, charts and report",
    }
    (package / "CONTENT_IDENTITY.json").write_text(
        json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        path.name: sha256(path)
        for path in sorted(package.iterdir())
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (package / "SHA256SUMS.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "package": str(package),
                "manifest_sha256": sha256(package / "SHA256SUMS.json"),
                "files": len(manifest),
                "outcome_code_rows": code_rows,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
