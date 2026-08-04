#!/usr/bin/env python3
"""Apply #190's authorized arm-specific coverage correction without replay.

The correction reads the already-settled, manifest-bound four-arm ledgers and
recomputes only selected-support diagnostics and their deterministic dependent
artifacts.  Every other Gate-B payload is protected byte-for-byte.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path

import settle_bj190_sparse_divergence_gate_b as R


BASE_MANIFEST_SHA256 = (
    "642464aeb9be0a20fa37e6c5a2a01c459bbb5fe45ad330ea4dffd99aa302243b"
)
BASE_CONTENT_IDENTITY_SHA256 = (
    "b33393860827352d7f81baadb0cc7d0385383c089c4c2fe496c167130f197585"
)
CORRECTION_ID = "BJ190_ARM_SPECIFIC_COVERAGE_V1"
MUTABLE_FILES = {
    "CONTENT_IDENTITY.json",
    "README.md",
    "REPORT.md",
    "RESEARCH_WIKI_ENTRY.md",
    "SHA256SUMS.json",
    "candidate_coverage_breakdown.csv.gz",
    "chart_source_candidate_coverage.csv.gz",
    "coverage_correction_runner.py",
    "decision.json",
    "settlement_card.json",
    "settlement_runner.py",
    "source_binding.json",
    "strict_ev_candidate_freeze.json",
}


def load_canonical_outcomes(package: Path) -> dict[str, R.Outcome]:
    outcomes: dict[str, R.Outcome] = {}
    for row in R.read_gzip(package / "canonical_outcome_ledger.csv.gz"):
        if row["availability_status"] != "TRUSTED":
            continue
        match_id = row["match_id"]
        outcomes[match_id] = R.Outcome(
            match_id=match_id,
            issue=row["issue"],
            match_idx=row["match_idx"],
            result_code=row["result_code"],
            winning_sp=float(row["winning_sp"]),
            winning_sp_source=row["winning_sp_source"],
            settlement_quality=row["settlement_quality"],
        )
    if len(outcomes) != R.EXPECTED_TRUSTED_ROWS:
        raise RuntimeError(f"canonical trusted outcome drift: {len(outcomes)}")
    return outcomes


def recompute_arm_diagnostics(
    package: Path,
    gate: Mapping[str, object],
) -> list[dict[str, object]]:
    grid_by_policy = gate["grid_by_policy"]
    identities = gate["identities"]
    estimator_by_match = gate["estimator_by_match"]
    assert isinstance(grid_by_policy, dict)
    assert isinstance(identities, dict)
    assert isinstance(estimator_by_match, dict)
    expected_policy_order = [str(row["policy_id"]) for row in gate["grid"]]
    coverage: list[dict[str, object]] = []

    for arm in R.ARMS:
        path = package / f"issue_arm_settlement_{arm.lower()}.csv.gz"
        observed: list[str] = []
        current_policy = ""
        records: list[dict[str, str]] = []

        def finalize() -> None:
            if not current_policy:
                return
            policy_coverage = R.candidate_coverage(
                grid_by_policy[current_policy],
                arm,
                records,
                identities,
                estimator_by_match,
            )
            coverage.extend(policy_coverage)
            observed.append(current_policy)

        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                policy_id = row["policy_id"]
                if current_policy and policy_id != current_policy:
                    if len(records) != R.MASTER_ISSUE_COUNT:
                        raise RuntimeError(
                            f"settlement policy width drift: {arm}/{current_policy}"
                        )
                    finalize()
                    records = []
                current_policy = policy_id
                records.append(row)
        if current_policy:
            if len(records) != R.MASTER_ISSUE_COUNT:
                raise RuntimeError(
                    f"settlement policy width drift: {arm}/{current_policy}"
                )
            finalize()
        if observed != expected_policy_order:
            raise RuntimeError(f"settlement policy order drift: {arm}")

    if not coverage or {str(row["arm"]) for row in coverage} != set(R.ARMS):
        raise RuntimeError("arm coverage diagnostic census drift")
    return coverage


def write_corrected_dependents(
    stage: Path,
    package: Path,
    gate: Mapping[str, object],
) -> dict[str, object]:
    load_canonical_outcomes(package)
    coverage = recompute_arm_diagnostics(package, gate)
    R.write_gzip(
        stage / "candidate_coverage_breakdown.csv.gz", tuple(coverage[0]), coverage
    )
    R.write_gzip(
        stage / "chart_source_candidate_coverage.csv.gz", tuple(coverage[0]), coverage
    )

    frontier = R.read_gzip(package / "full_frontier.csv.gz")
    risk = R.read_gzip(package / "risk_concentration.csv.gz")
    stability = R.read_gzip(package / "stability_year_fold_loyo.csv.gz")
    bootstrap = R.read_csv(package / "bootstrap_paired_lift_20000.csv")
    freeze = R.candidate_freeze(frontier, risk, stability, coverage, bootstrap)
    if freeze["positive_screen_count"] != 475:
        raise RuntimeError(
            "descriptive positive screen changed during coverage correction"
        )
    if freeze["strict_stability_candidate_count"] != 0:
        raise RuntimeError(
            "arm-specific correction must produce zero strict candidates"
        )

    old_freeze = json.loads(
        (package / "strict_ev_candidate_freeze.json").read_text(encoding="utf-8")
    )
    old_strict = {
        (str(row["policy_id"]), str(row["arm"]))
        for row in old_freeze["strict_stability_rows"]
    }
    new_positive = {
        (str(row["policy_id"]), str(row["arm"])): row
        for row in freeze["positive_screen_rows"]
    }
    if len(old_strict) != 18 or any(
        key not in new_positive or new_positive[key]["line_stratum_count"] != 1
        for key in old_strict
    ):
        raise RuntimeError("formal #195 line-0 correction reconciliation failed")

    decision = json.loads((package / "decision.json").read_text(encoding="utf-8"))
    decision.update(
        {
            "decision": "NO_PROMOTION_FROM_GATE_B",
            "positive_screen_count": freeze["positive_screen_count"],
            "strict_stability_candidate_count": 0,
            "strict_independent_ev_required": False,
            "interpretation": (
                "475 descriptive positive screen rows remain; candidate-arm-own coverage "
                "leaves the former direction-only strict cluster on line stratum 0 only, "
                "so no row passes the frozen cross-line coverage requirement"
            ),
            "coverage_correction": CORRECTION_ID,
        }
    )
    (stage / "decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (stage / "strict_ev_candidate_freeze.json").write_text(
        json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    binding = json.loads((package / "source_binding.json").read_text(encoding="utf-8"))
    binding["coverage_correction"] = {
        "correction_id": CORRECTION_ID,
        "prior_manifest_sha256": BASE_MANIFEST_SHA256,
        "prior_content_identity_sha256": BASE_CONTENT_IDENTITY_SHA256,
        "independent_validation_issue": 195,
        "semantics": "coverage derives separately from each arm own selected N7 identities",
        "ticket_or_outcome_replay": False,
    }
    (stage / "source_binding.json").write_text(
        json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    card = json.loads((package / "settlement_card.json").read_text(encoding="utf-8"))
    card.update(
        {
            "coverage_correction": CORRECTION_ID,
            "coverage_semantics": "candidate-arm-own selected N7 identities",
            "descriptive_positive_screen_count": 475,
            "strict_stability_candidate_count": 0,
            "issue_level_economics_replayed": False,
        }
    )
    (stage / "settlement_card.json").write_text(
        json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    ledger_binding = json.loads(
        (package / "canonical_outcome_ledger_binding.json").read_text(encoding="utf-8")
    )
    ledger_receipt = ledger_binding["receipt"]
    identity_distribution = {
        int(key): int(value)
        for key, value in ledger_binding["identity_available_leg_distribution"].items()
    }
    population = R.read_csv(package / "full_population_probability_metrics.csv")
    for row in population:
        row["settled_match_count"] = int(row["settled_match_count"])
    report = R.report_markdown(
        ledger_receipt,
        identity_distribution,
        R.read_csv(package / "baseline_bridge.csv"),
        population,
        frontier,
        freeze,
    )
    (stage / "REPORT.md").write_text(report, encoding="utf-8")
    wiki_entry = "\n".join(
        [
            "# #190 sparse divergence Gate B — arm-specific coverage correction",
            "",
            "- Decision: `NO_PROMOTION_FROM_GATE_B`.",
            "- Canonical settlement/economics were not replayed and remain byte-identical.",
            "- Positive screen rows: 475 descriptive rows; strict-stability candidates: 0.",
            "- Coverage is derived separately from each arm's own selected N7 identities.",
            "- The former 18 direction-only strict aliases cover line stratum `0` only; they remain descriptive evidence but fail the frozen >=2-line coverage rule.",
            "- Performance checks (bootstrap, ex-largest, positive years) are distinct from coverage checks (league and line counts).",
            "- Paper research only; no promotion, betting or production authority.",
            "",
        ]
    )
    (stage / "RESEARCH_WIKI_ENTRY.md").write_text(wiki_entry, encoding="utf-8")
    (stage / "README.md").write_text(
        "# #190 Gate B immutable sparse-divergence settlement\n\n"
        "This corrected package preserves the canonical ledger and every issue-level "
        "economic payload byte-for-byte. Candidate coverage is arm-specific; deterministic "
        "dependent summaries, report, Wiki entry and manifest were re-frozen without ticket "
        "or bootstrap replay.\n",
        encoding="utf-8",
    )
    shutil.copy2(
        Path(R.__file__).resolve(),
        stage / "settlement_runner.py",
    )
    shutil.copy2(Path(__file__), stage / "coverage_correction_runner.py")
    return freeze


def correct(package: Path = R.DEFAULT_OUTPUT) -> dict[str, object]:
    package = package.resolve()
    if R.sha256_file(package / "SHA256SUMS.json") != BASE_MANIFEST_SHA256:
        raise RuntimeError("correction requires exact reviewed Gate-B v1 manifest")
    if R.sha256_file(package / "CONTENT_IDENTITY.json") != BASE_CONTENT_IDENTITY_SHA256:
        raise RuntimeError(
            "correction requires exact reviewed Gate-B v1 content identity"
        )
    R.verify_package(package, BASE_MANIFEST_SHA256, BASE_CONTENT_IDENTITY_SHA256)
    existing_files = {path.name for path in package.iterdir() if path.is_file()}
    protected = existing_files - MUTABLE_FILES
    protected_hashes = {name: R.sha256_file(package / name) for name in protected}

    scratch_root = R.ROOT / ".scratch" / "bj190-arm-coverage-correction"
    scratch_root.mkdir(parents=True, exist_ok=True)
    stage = scratch_root / f"{package.name}.stage"
    backup = scratch_root / f"{package.name}.{BASE_MANIFEST_SHA256[:12]}.backup"
    if stage.exists() or backup.exists():
        raise RuntimeError("exact correction stage/backup already exists")
    shutil.copytree(package, stage, copy_function=os.link)
    for name in MUTABLE_FILES:
        path = stage / name
        if path.exists():
            path.unlink()
    try:
        gate = R.load_gate_a()
        freeze = write_corrected_dependents(stage, package, gate)
        for name, expected in protected_hashes.items():
            actual = R.sha256_file(stage / name)
            if actual != expected:
                raise RuntimeError(f"protected payload changed: {name}")
        old_content = json.loads((package / "CONTENT_IDENTITY.json").read_text())
        controls = dict(old_content["controls"])
        controls.update(
            {
                "coverage_correction": CORRECTION_ID,
                "prior_manifest_sha256": BASE_MANIFEST_SHA256,
                "prior_content_identity_sha256": BASE_CONTENT_IDENTITY_SHA256,
                "arm_specific_coverage": True,
                "strict_stability_candidate_count": 0,
                "ticket_or_bootstrap_replay": False,
            }
        )
        manifest_hash, content_hash = R.package_identity(stage, controls)
        manifest = R.verify_package(stage, manifest_hash, content_hash)
        for name, expected in protected_hashes.items():
            if manifest[name] != expected:
                raise RuntimeError(f"protected manifest binding changed: {name}")

        os.replace(package, backup)
        try:
            os.replace(stage, package)
        except Exception:
            os.replace(backup, package)
            raise
        return {
            "output": str(package),
            "backup": str(backup),
            "manifest_sha256": manifest_hash,
            "content_identity_sha256": content_hash,
            "payload_count": len(manifest),
            "protected_payload_count": len(protected_hashes),
            "positive_screen_count": freeze["positive_screen_count"],
            "strict_stability_candidate_count": freeze[
                "strict_stability_candidate_count"
            ],
            "decision": "NO_PROMOTION_FROM_GATE_B",
        }
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=R.DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(correct(args.package), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
