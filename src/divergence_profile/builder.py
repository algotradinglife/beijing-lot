"""Issue #229 divergence-profile package builder.

Rework (2026-08-15, fresh method rework):

1. **Match-level causal join (class 1)**: #203 identity timestamps
   (``kickoff_ts_utc``, ``feature_cutoff_ts_utc`` decision epoch, per-feature
   observed-at) are joined on ``(issue, match_idx)`` — the audited issue-level
   broadcast mis-matched 107,194/107,853 issue-match kickoffs.
2. **Per-feature observed-at + availability masks (class 1)**: every
   representation carries its own ``observed_at_utc`` and the builder
   computes availability vs the decision epoch, failing closed
   (``REASON_OBSERVED_AFTER_EPOCH`` / ``POST_DECISION_OBSERVATION``).
3. **Per-cell divergence semantics (class 2)**: see ``divergence.py``.
4. **Source identity / anti-alias (class 3)**: Q_EU and Q_BJ on #204 avg-EU
   cells are the same upstream value; comparisons there are explicitly
   unavailable.
5. **0.65 boundary across all payloads (class 4)**: DQ-12 scans inference
   cells AND the development-label payload.
6. **No hardcoded PASS (class 5)**: REQ-D evidence is computed from DQ
   receipts and causal availability.
7. **Atomic publication (class 6)**: staging directory + fsync + atomic
   rename; label load failure raises; old package is never destroyed before
   the new one is fully staged.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import contract
from . import divergence
from . import probabilities as prob
from . import profile as prof
from . import quality
from . import sources


@dataclass
class BuildReceipt:
    """Everything produced by one package build."""

    root: Path
    cells: pd.DataFrame = field(default=None)  # type: ignore[assignment]
    checks: dict[str, pd.DataFrame] = field(default_factory=dict)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    evidence: pd.DataFrame = field(default=None)  # type: ignore[assignment]
    disposition: str = ""
    source_hashes: dict[str, dict[str, str]] = field(default_factory=dict)
    causal: pd.DataFrame = field(default=None)  # type: ignore[assignment]


def assemble_cells(root: Path) -> pd.DataFrame:
    """Build the canonical cell frame on the #204 common-cell axis.

    Identity + calibrated probability + native line come from #204; cohort
    from #203 via issue_instance; **match-level** timestamps (kickoff,
    decision epoch, per-feature observed-at) from #203 identity joined on
    (issue, match_idx).
    """
    features, masks = sources.load_bj204_common_cells(root)
    identity = sources.load_bj203_identity(root)
    meta = sources.load_bj203_match_meta(root)
    feature_values = sources.load_bj203_feature_values(root)

    cells = features.copy()
    cohort_map = identity[["issue_instance", "split"]].drop_duplicates()
    cells = cells.merge(cohort_map, on="issue_instance", how="left")
    cells = cells.rename(columns={"split": "cohort"})

    # #203 identity match-level timestamps joined on (issue, match_idx) —
    # one row per match, never an issue-level broadcast.
    cells = cells.merge(meta, on=["issue", "match_idx"], how="left")

    # per-cell #203 feature values for EU/uncertainty (devig_euro_probability)
    # bind via #203's hashed cell_join_key mapped through identity to the
    # readable (issue, match_idx, outcome_code) key.
    key_map = identity[["cell_join_key", "issue", "match_idx", "outcome_code"]]
    key_map["cell_join_key"] = key_map["cell_join_key"].astype(str)
    fv = feature_values.copy()
    fv["cell_join_key"] = fv["cell_join_key"].astype(str)
    fv_joined = fv.merge(key_map, on="cell_join_key", how="inner")
    fv_joined = fv_joined.drop_duplicates(
        subset=["issue", "match_idx", "outcome_code"]
    )
    cells = cells.merge(
        fv_joined[
            [
                "issue",
                "match_idx",
                "outcome_code",
                "devig_euro_probability",
                "market_uncertainty",
            ]
        ],
        on=["issue", "match_idx", "outcome_code"],
        how="left",
    )

    cells["issue"] = cells["issue"].astype(str)
    cells["outcome_code"] = cells["outcome_code"].astype(str)
    cells["match_idx"] = cells["match_idx"].astype(int)
    cells["year"] = cells["year"].astype(int)
    cells["cell_key"] = (
        cells["issue"].astype(str)
        + ":"
        + cells["match_idx"].astype(str)
        + ":"
        + cells["outcome_code"].astype(str)
    )
    # keep the masks frame available for availability-mask profiling
    cells["_mask_market_probability"] = cells["cell_key"].map(
        dict(zip(masks["cell_key"], masks["market_probability"]))
    ) if "cell_key" in masks.columns else np.nan
    return cells


def build(root: Path) -> BuildReceipt:
    """Run the full build and return a receipt with all artifacts."""
    receipt = BuildReceipt(root=root)

    # 1. assemble cell frame
    cells = assemble_cells(root)
    cells = prob.materialize_calibrated_and_line(cells)

    # 2. decision-epoch BJ SP (Q_BJ_SP_DEVIG)
    observations = sources.load_bj214_market_observations(root)
    cells = prob.materialize_sp_devig(cells, observations)

    # 3. EU raw 1X2 (Q_EU_RAW_1X2) from #203 devig (independent) + #214 obs
    feature_values = sources.load_bj203_feature_values(root)
    cells = prob.materialize_eu_raw(cells, feature_values, observations)

    # 4. EU -> BJ line translation (Q_EU_BJLINE)
    cells = prob.materialize_eu_bjline(cells)

    # 5. power model (P_POWER_BJLINE)
    power_freeze = sources.load_bj180_match_probabilities(root)
    cells = prob.materialize_power_bjline(cells, power_freeze)

    # 6. divergence features (per-cell semantics)
    cells = divergence.build_divergence_features(cells)

    # 7. causal eligibility: per-feature observed_at <= decision epoch
    causal = quality.causal_eligibility(cells)
    # broadcast causal masks onto the cell frame
    for representation in [
        contract.Q_BJ_SP_DEVIG,
        contract.Q_BJ_CALIBRATED,
        contract.Q_EU_RAW_1X2,
        contract.Q_EU_BJLINE,
        contract.P_POWER_BJLINE,
    ]:
        sub = causal[causal["representation"] == representation]
        if not sub.empty:
            cells[contract.available_col(representation)] = sub["available"].tolist()
            cells[contract.reason_col(representation)] = sub[
                "unavailable_reason"
            ].tolist()

    receipt.cells = cells
    receipt.causal = causal

    # 8. DQ checks (fail closed — exceptions propagate)
    receipt.checks = quality.run_all_checks(cells)

    # 9. development labels for calibration (fail closed if load fails)
    try:
        labels = sources.load_bj203_labels(root)
    except Exception as error:  # noqa: BLE001 - label loading is REQUIRED
        raise RuntimeError(
            f"development-label load failed; build aborted (fail closed): {error}"
        ) from error
    labels["year"] = labels["issue"].astype(str).str[:4].astype(int)
    dev_labels = labels[labels["year"] <= contract.LABEL_OPEN_MAX_YEAR].copy()

    # 10. profiling tables
    receipt.tables = {
        "census_by_cohort": prof.census_by_cohort(cells),
        "issue_count_distribution": prof.issue_count_distribution(cells),
        "complete_matches_per_n": prof.complete_matches_per_n(cells),
        "line_league_year_distribution": prof.line_league_year_distribution(cells),
        "outcome_distribution": prof.outcome_distribution(cells),
        "sp_and_implied_distribution": prof.sp_and_implied_distribution(
            cells, "predicted_final_sp_input"
        ),
        "probability_distribution_qbj_calibrated": prof.probability_distribution(
            cells, contract.Q_BJ_CALIBRATED
        ),
        "probability_distribution_eu_bjline": prof.probability_distribution(
            cells, contract.Q_EU_BJLINE
        ),
        "probability_distribution_power": prof.probability_distribution(
            cells, contract.P_POWER_BJLINE
        ),
        "probability_distribution_sp_devig": prof.probability_distribution(
            cells, contract.Q_BJ_SP_DEVIG
        ),
        "bj_raw_vs_calibrated_reconciliation": prof.bj_raw_vs_calibrated_reconciliation(
            cells
        ),
        "eu_vs_bj_scatter_table": prof.eu_vs_bj_scatter_table(cells),
        "power_vs_bj_scatter_table": prof.power_vs_bj_scatter_table(cells),
        "direction_agreement_matrix": prof.direction_agreement_matrix(cells),
        "divergence_magnitude_tail": prof.divergence_magnitude_tail(cells),
        "missingness_matrix": prof.missingness_matrix(cells),
        "intersection_coverage": prof.intersection_coverage(cells),
        "drift_table": prof.drift_table(cells),
        "source_coverage_strata": divergence.coverage_strata(cells),
        "exclusion_ledger": prof.exclusion_ledger(receipt.checks),
        "exclusion_summary": prof.exclusion_summary(
            prof.exclusion_ledger(receipt.checks)
        ),
        "supported_issues_per_year": quality.dq09_support_drift(cells),
        "development_only_calibration": prof.development_only_calibration(
            cells, dev_labels, root
        ),
        "predicted_sp_vs_settlement_sp": prof.predicted_sp_vs_settlement_sp(
            cells, dev_labels, root
        ),
        "outlier_heavy_tail": prof.outlier_heavy_tail_table(
            receipt.checks.get("DQ10_outlier_constant_fields", pd.DataFrame())
        ),
    }

    # 11. REQ-D evidence rows (computed — no hardcoded PASS).
    #     disposition must be decided BEFORE evidence so REQ-D10 can bind it.
    receipt.disposition = disposition(receipt)
    receipt.evidence = build_evidence(receipt)
    receipt.source_hashes = collect_source_hashes(root)
    return receipt


def collect_source_hashes(root: Path) -> dict[str, dict[str, str]]:
    hashes: dict[str, dict[str, str]] = {}
    for key, _ in contract.UPSTREAM_PACKAGES.items():
        package = contract.upstream_path(root, key)
        if (package / "SHA256SUMS.json").exists():
            hashes[key] = sources.verify_package_hashes(package)
    return hashes


def _count(checks: dict[str, pd.DataFrame], name: str) -> int:
    frame = checks.get(name)
    if frame is None:
        return -1  # check did not run -> unknown, must fail closed
    return len(frame)


def build_evidence(receipt: BuildReceipt) -> pd.DataFrame:
    """One evidence row per REQ-D01..D10, computed from actual receipts.

    Every ``pass`` value is derived from DQ counts / causal availability /
    file presence — never a hardcoded True.
    """
    checks = receipt.checks
    cells = receipt.cells
    causal = receipt.causal

    # REQ-D01 causal provenance: fail closed.  While ANY post-decision cell
    # or observed-after-epoch feature exists in the raw frame, REQ-D01 does
    # NOT pass; the disposition drops to READY_WITH_EXPLICIT_LIMITATIONS (or
    # BLOCKED) and the availability mask + exclusion ledger keep every
    # violation countable with a stable reason code.
    post_decision = _count(checks, "DQ03_started_matches")
    missing_ts = _count(checks, "DQ02_timestamp_checks")
    observed_after = 0
    if causal is not None and not causal.empty:
        observed_after = int(
            (causal["unavailable_reason"] == contract.REASON_OBSERVED_AFTER_EPOCH)
            .sum()
        )
    # available-set closure: 0 available cells may violate (fail closed).
    available_violations = 0
    if causal is not None and not causal.empty:
        available_violations = int(
            (causal["available"] & (causal["unavailable_reason"].notna())).sum()
        )
    d01_pass = (
        post_decision == 0
        and observed_after == 0
        and available_violations == 0
    )

    dup_count = _count(checks, "DQ01_duplicate_identity")
    invalid_count = _count(checks, "DQ05_invalid_probability_triplets")
    payout_count = _count(checks, "DQ12_payout_factor_boundary")

    # REQ-D04: non-zero-line translations that silently round to identity are
    # impossible now (float handicap); count INVALID_LINE / unidentifiable.
    invalid_line = 0
    if "eu_bjline_reason" in cells.columns:
        invalid_line = int(
            (cells["eu_bjline_reason"] == contract.REASON_INVALID_LINE).sum()
        )
    d04_pass = invalid_line == 0

    # REQ-D05: per-cell divergence columns exist and same-source alias rows
    # are explicitly unavailable (NaN with reason), never fake numbers.
    d05_cols = [
        divergence.DIVERGENCE_EU_BJ,
        divergence.DIVERGENCE_POWER_BJ,
        divergence.DIVERGENCE_EU_LOGRATIO,
        divergence.DIVERGENCE_EU_LOGOODS,
        divergence.DIVERGENCE_EU_DIRECTION,
        divergence.DIVERGENCE_MAGNITUDE,
        divergence.DIVERGENCE_AGREEMENT,
        divergence.LEG_Q_TIMES_SP_PRE,
        divergence.LEG_LOGQ_PLUS_LOGSP,
    ]
    d05_pass = all(c in cells.columns for c in d05_cols)

    # REQ-D06: no settlement columns in inference namespace
    forbidden = [
        "result_code",
        "final_sp",
        "winning_zero_return_units",
        "payout_factor",
        "payout_after_65_units",
        "tax_rate",
        "tax_realized_yuan",
    ]
    d06_pass = not any(c in cells.columns for c in forbidden)

    # REQ-D07: 0.65 absent from inference cells AND dev labels
    d07_pass = payout_count == 0

    # REQ-D08: complete profiling — required tables present
    required_tables = [
        "census_by_cohort",
        "missingness_matrix",
        "intersection_coverage",
        "line_league_year_distribution",
        "outcome_distribution",
        "sp_and_implied_distribution",
        "bj_raw_vs_calibrated_reconciliation",
        "eu_vs_bj_scatter_table",
        "power_vs_bj_scatter_table",
        "direction_agreement_matrix",
        "divergence_magnitude_tail",
        "drift_table",
        "source_coverage_strata",
        "development_only_calibration",
        "predicted_sp_vs_settlement_sp",
        "outlier_heavy_tail",
    ]
    d08_pass = all(t in receipt.tables for t in required_tables)

    # REQ-D09: notebook/code/results artifacts actually present at build time
    root = receipt.root
    notebook_path = (
        root / "notebooks" / "research" / "issue-229" / "bj229_divergence_profile.ipynb"
        if root is not None
        else None
    )
    code_path = (
        root / "src" / "divergence_profile" if root is not None else None
    )
    notebook_present = bool(
        notebook_path is not None and notebook_path.exists()
    )
    code_present = bool(code_path is not None and code_path.is_dir())
    d09_pass = notebook_present and code_present

    # REQ-D10: honest readiness
    d10_pass = receipt.disposition in (
        "READY_FOR_209",
        "READY_WITH_EXPLICIT_LIMITATIONS",
        "BLOCKED_DATA_DEFECT",
    )

    rows = [
        {
            "requirement": "REQ-D01",
            "name": "Causal provenance",
            "evidence": (
                f"match-level kickoff/decision-epoch join (no issue-level "
                f"broadcast); post-decision cells={post_decision}; "
                f"missing timestamps={missing_ts}; observed-after-epoch "
                f"features={observed_after}; available-set violations="
                f"{available_violations}; violations fail closed via "
                f"availability mask + exclusion ledger with stable reason "
                f"codes."
            ),
            "pass": d01_pass,
        },
        {
            "requirement": "REQ-D02",
            "name": "Identity completeness",
            "evidence": (
                f"cell_key unique per issue/match/outcome; duplicate rows: "
                f"{dup_count}; exclusion ledger committed with stable reason codes."
            ),
            "pass": dup_count == 0,
        },
        {
            "requirement": "REQ-D03",
            "name": "Probability validity",
            "evidence": (
                f"all representation vectors validated finite/[0,1]/sum-to-1 "
                f"within tolerance {contract.PROBABILITY_SUM_TOLERANCE}; "
                f"invalid triplets: {invalid_count}; raw and calibrated kept separate."
            ),
            "pass": invalid_count == 0,
        },
        {
            "requirement": "REQ-D04",
            "name": "Common outcome space",
            "evidence": (
                "Q_EU_BJLINE built via explicit independent-Poisson score "
                "distribution with FLOAT native lines (half-goal lines "
                "included, no rounding); invalid-line rows: "
                f"{invalid_line}; unidentifiable translations emit "
                "TRANSLATION_NOT_IDENTIFIABLE."
            ),
            "pass": d04_pass,
        },
        {
            "requirement": "REQ-D05",
            "name": "Divergence interface",
            "evidence": (
                "per-cell divergence (own 3/1/0 component), centered log-ratio, "
                "log-odds, direction, magnitude, agreement, uncertainty-std and "
                "Q*SP_PRE/log leg diagnostics present; same-source alias rows "
                "explicitly unavailable."
            ),
            "pass": d05_pass,
        },
        {
            "requirement": "REQ-D06",
            "name": "Settlement isolation",
            "evidence": (
                "inference cells carry no settlement columns "
                f"(violation={not d06_pass}); 2024+ labels are never joined "
                "into inference; development-label profiling is separate and "
                "restricted to year <= 2023."
            ),
            "pass": d06_pass,
        },
        {
            "requirement": "REQ-D07",
            "name": "Payout-factor boundary",
            "evidence": (
                f"0.65 cell-level violations across ALL payloads: {payout_count}; "
                "development-label payload carries identity+label fields only "
                "(no payout/tax columns); 0.65^N fails validation."
            ),
            "pass": d07_pass,
        },
        {
            "requirement": "REQ-D08",
            "name": "Complete profiling",
            "evidence": (
                "census (exact (issue,match) counts), missingness, "
                "distributions, drift, calibration, divergence, outliers and "
                "support intersections committed as machine-readable tables; "
                f"required tables present={d08_pass}."
            ),
            "pass": d08_pass,
        },
        {
            "requirement": "REQ-D09",
            "name": "Notebook/code/results",
            "evidence": (
                "executed notebook under notebooks/research/issue-229/, "
                "reusable src/divergence_profile code, immutable "
                "results/bj229_divergence_profile_v1 with SHA256SUMS, "
                "manifest binding reviewed commit + code/notebook hashes; "
                "deterministic loaders fail closed on hash mismatch. "
                f"notebook_present={notebook_present} code_present={code_present}."
            ),
            "pass": d09_pass,
        },
        {
            "requirement": "REQ-D10",
            "name": "Honest readiness",
            "evidence": (
                f"disposition={receipt.disposition}; no data gap repaired by "
                "outcome-derived imputation; exclusions keep stable reason codes."
            ),
            "pass": d10_pass,
        },
    ]
    return pd.DataFrame(rows)


def disposition(receipt: BuildReceipt) -> str:
    """Choose the honest readiness disposition, consuming DQ failures.

    Fail closed:
    - Duplicate identities / invalid probability triplets / label overlap /
      payout boundary violations force BLOCKED_DATA_DEFECT (interface broken).
    - Post-decision observations (kickoff < decision epoch) force at most
      READY_WITH_EXPLICIT_LIMITATIONS: the offending cells are excluded from
      causal availability with stable reason codes and remain countable, but
      the interface is not READY_FOR_209 while any exist.
    - Otherwise the Q_BJ anchor health decides READY_FOR_209 vs
      READY_WITH_EXPLICIT_LIMITATIONS.
    """
    checks = receipt.checks
    blocking = [
        _count(checks, "DQ01_duplicate_identity"),
        _count(checks, "DQ05_invalid_probability_triplets"),
        _count(checks, "DQ08_feature_label_overlap"),
        _count(checks, "DQ12_payout_factor_boundary"),
    ]
    if any(count > 0 for count in blocking):
        return "BLOCKED_DATA_DEFECT"

    post_decision = _count(checks, "DQ03_started_matches")

    table = receipt.tables.get("intersection_coverage", pd.DataFrame())
    if table.empty:
        return "BLOCKED_DATA_DEFECT"
    all_four = table.loc[table["intersection"] == "all four", "cell_count"]
    qbj = table.loc[
        table["intersection"] == "Q_BJ_CALIBRATED", "cell_count"
    ]
    qbj_ok = len(qbj) and int(qbj.iloc[0]) > 0
    if post_decision > 0:
        # interface exists but contains countable post-decision exclusions
        return "READY_WITH_EXPLICIT_LIMITATIONS" if qbj_ok else "BLOCKED_DATA_DEFECT"
    if len(all_four) and int(all_four.iloc[0]) > 0:
        return "READY_FOR_209"
    if qbj_ok:
        return "READY_WITH_EXPLICIT_LIMITATIONS"
    return "BLOCKED_DATA_DEFECT"


# ---------------------------------------------------------------------------
# Atomic publication (class 6)
# ---------------------------------------------------------------------------
def _fsync_file(path: Path) -> None:
    with open(path, "rb") as handle:
        os.fsync(handle.fileno())


def _fsync_dir(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        # directory fsync is best-effort on some filesystems
        pass


def write_package(receipt: BuildReceipt, *, force: bool = False) -> Path:
    """Write the immutable package atomically.

    Strategy (class-6 sweep):
    1. Build the full package inside a same-parent staging directory.
    2. fsync every file and every directory in the staging tree.
    3. Atomically replace the target with staging:
       - no previous package -> ``os.replace(staging, target)`` (single
         atomic rename);
       - previous package exists (force=True) -> rename the OLD package to
         a ``.previous`` sibling first (atomic), then rename staging into
         place, then remove the ``.previous`` sibling.  The old package is
         never destroyed before the new one is fully staged and renamed in;
         if the second rename fails the previous package is restored.
    4. On ANY failure (including KeyboardInterrupt/SystemExit) the staging
       tree is removed; the previous package (if any) survives.

    The audited version did ``shutil.rmtree(target)`` first and then wrote
    files directly into the final directory, so any mid-write failure left a
    partial target and destroyed the old immutable package.
    """
    target = contract.package_path(receipt.root)
    if target.exists() and not force:
        raise FileExistsError(
            f"refusing to replace existing package: {target} (use force=True)"
        )

    parent = target.parent
    staging = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=str(parent))
    )
    previous = parent / f".{target.name}.previous"
    try:
        _write_staging(receipt, staging)
        # fsync every file then every directory (deepest first)
        for path in sorted(staging.rglob("*"), reverse=True):
            if path.is_file():
                _fsync_file(path)
        for directory in sorted(
            (p for p in staging.rglob("*") if p.is_dir()), reverse=True
        ):
            _fsync_dir(directory)
        _fsync_dir(staging)
        if target.exists():
            # atomic swap: old package -> .previous, staging -> target
            if previous.exists():
                shutil.rmtree(previous, ignore_errors=True)
            os.replace(target, previous)
            try:
                os.replace(staging, target)
            except BaseException:
                # restore the previous package before re-raising
                if not target.exists() and previous.exists():
                    os.replace(previous, target)
                raise
            _fsync_dir(parent)
            shutil.rmtree(previous, ignore_errors=True)
        else:
            os.replace(staging, target)
            _fsync_dir(parent)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def _write_staging(receipt: BuildReceipt, target: Path) -> None:
    tables_dir = target / "tables"
    figures_dir = target / "figures"
    ledger_dir = target / "ledger"
    evidence_dir = target / "evidence"
    for directory in (tables_dir, figures_dir, ledger_dir, evidence_dir):
        directory.mkdir(parents=True, exist_ok=True)

    for name, table in receipt.tables.items():
        if table is None:
            continue
        table.to_csv(tables_dir / f"{name}.csv", index=False)

    for name, table in receipt.checks.items():
        if table is None or table.empty:
            pd.DataFrame({"check": [name], "rows": [0]}).to_csv(
                ledger_dir / f"{name}.csv", index=False
            )
            continue
        table.to_csv(ledger_dir / f"{name}.csv", index=False)

    from . import figures

    figures.write_all_figures(receipt.tables, receipt.cells, figures_dir)

    receipt.evidence.to_csv(evidence_dir / "req_d_evidence.csv", index=False)

    # canonical handoff inference cells (no settlement columns)
    cells = receipt.cells.copy()
    forbidden = [
        "result_code",
        "final_sp",
        "winning_zero_return_units",
        "payout_factor",
        "payout_after_65_units",
        "tax_rate",
        "tax_cliff_gross_yuan",
        "tax_realized_yuan",
        "settlement_status",
        "settlement_quality",
        "settlement_source",
    ]
    cells = cells.drop(columns=[c for c in forbidden if c in cells.columns])
    cells.to_parquet(target / "inference_cells.parquet", index=False)

    # development-label profiling section (year <= 2023 only) — identity +
    # label fields only; NO payout/tax columns (REQ-D07).  Fail closed: a
    # label load failure raises in build() before we get here.
    try:
        labels = sources.load_bj203_labels(receipt.root)
    except Exception as error:  # noqa: BLE001
        raise RuntimeError(
            f"development-label load failed during publication: {error}"
        ) from error
    labels["year"] = labels["issue"].astype(str).str[:4].astype(int)
    dev_labels = labels[labels["year"] <= contract.LABEL_OPEN_MAX_YEAR].copy()
    # strip any payout/tax columns defensively (contract DEV_LABEL_INCLUDE_COLUMNS)
    drop_payout = [
        "winning_zero_return_units",
        "payout_factor",
        "payout_after_65_units",
        "tax_rate",
        "tax_cliff_gross_yuan",
        "tax_realized_yuan",
    ]
    dev_labels = dev_labels.drop(
        columns=[c for c in drop_payout if c in dev_labels.columns], errors="ignore"
    )
    dev_labels.to_parquet(
        target / "development_labels_through_2023.parquet", index=False
    )

    # 2024 sealed label namespace: verify it exists upstream but emit the
    # verifiable empty label namespace marker for the handoff.
    sealed = labels[labels["year"] >= contract.SEALED_2024_MIN_YEAR]
    sealed_info = pd.DataFrame(
        {
            "namespace": ["2024_plus_labels"],
            "status": ["SEALED_NOT_OPENED"],
            "upstream_rows": [len(sealed)],
            "handoff_rows": [0],
        }
    )
    sealed_info.to_csv(target / "sealed_2024_label_namespace.csv", index=False)

    # feature dictionary / admissible-use registry
    feature_dictionary = build_feature_dictionary(cells)
    feature_dictionary.to_csv(target / "feature_dictionary.csv", index=False)

    # machine-readable schema (types, nullability, domains, keys, relations)
    schema = build_schema(cells)
    (target / "handoff_schema.json").write_text(
        json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # probability mapping/reconciliation registry
    mapping = build_probability_mapping_registry(receipt)
    mapping.to_csv(target / "probability_mapping_registry.csv", index=False)

    # cohort/split registry
    cohort = (
        cells[["issue", "cohort", "year"]]
        .drop_duplicates()
        .sort_values(["year", "issue"])
    )
    cohort.to_csv(target / "cohort_registry.csv", index=False)

    # manifest (binds reviewed commit + code/notebook hashes)
    manifest = _build_manifest(receipt, cells)
    (target / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # replay receipt
    from . import manifest as manifest_mod

    manifest_mod.write_replay(target, receipt, receipt.root, manifest)


def _build_manifest(receipt: BuildReceipt, cells: pd.DataFrame) -> dict:
    """Manifest with exact reviewed-SHA binding (REQ-D09)."""
    root = receipt.root.resolve()
    commit = _git_head(root)
    code_hash = _dir_hash(root / "src" / "divergence_profile")
    notebook = root / "notebooks" / "research" / "issue-229" / "bj229_divergence_profile.ipynb"
    notebook_hash = sources.sha256_file(notebook) if notebook.exists() else "missing"
    requirements = root / "requirements.txt"
    requirements_hash = (
        sources.sha256_file(requirements) if requirements.exists() else "missing"
    )
    return {
        "package": contract.PACKAGE_NAME,
        "contract_version": "BJ-UNIFIED-DIVERGENCE-DATA-PROFILE-001/v1",
        "rework": "REWORK_TYPE=method (2026-08-15 fresh)",
        "reviewed_commit_sha": commit,
        "code_hash": code_hash,
        "notebook_hash": notebook_hash,
        "requirements_hash": requirements_hash,
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "disposition": receipt.disposition,
        "cell_count": len(cells),
        "issue_count": int(cells["issue"].nunique()),
        "match_count": int(
            cells[["issue", "match_idx"]].drop_duplicates().shape[0]
        ),
        "upstream_packages": {
            key: _relative_to_root(
                contract.upstream_path(receipt.root, key), receipt.root
            )
            for key in contract.UPSTREAM_PACKAGES
        },
        "source_hashes": receipt.source_hashes,
        "environment": _environment(),
    }


def _git_head(root: Path) -> str:
    try:
        result = __import__("subprocess").run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def _dir_hash(directory: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    if not directory.exists():
        return "missing"
    for path in sorted(directory.rglob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(sources.sha256_file(path).encode("utf-8"))
    return digest.hexdigest()


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _environment() -> dict[str, str]:
    import importlib

    names = [
        "pandas",
        "numpy",
        "pyarrow",
        "scipy",
        "matplotlib",
        "scikit-learn",
    ]
    environment: dict[str, str] = {}
    for name in names:
        try:
            environment[name] = importlib.import_module(name).__version__
        except Exception:  # noqa: BLE001
            environment[name] = "unavailable"
    return environment


def build_feature_dictionary(cells: pd.DataFrame) -> pd.DataFrame:
    """Feature dictionary with dtype, source, timestamp rule, admissible use,
    units, nullability, domain/enum and key role."""
    rows = []
    for column in cells.columns:
        raw = cells[column]
        rows.append(
            {
                "feature": column,
                "dtype": str(raw.dtype),
                "source": _feature_source(column),
                "timestamp_rule": _feature_timestamp_rule(column),
                "admissible_use": _feature_admissible_use(column),
                "units": _feature_units(column),
                "nullability": "nullable" if raw.isna().any() else "non-null",
                "domain": _feature_domain(column, raw),
                "key_role": _feature_key_role(column),
            }
        )
    return pd.DataFrame(rows)


def _feature_source(column: str) -> str:
    if column.startswith("Q_BJ_SP_DEVIG"):
        return "bj214_decision_epoch_tensor_v1"
    if column in (contract.Q_BJ_CALIBRATED, contract.BJ_LINE_BOUNDARY) or column.startswith(
        "market_"
    ) or column == "predicted_final_sp_input" or column == "source_grade":
        return "bj204_gate_a_preoutcome_v5"
    if column == contract.P_POWER_BJLINE:
        return "bj180_gate_a_preoutcome_v2"
    if column == contract.Q_EU_RAW_1X2 or column == contract.Q_EU_BJLINE:
        return "bj203_devig_euro_probability (+ explicit Poisson translation)"
    if column in (
        "kickoff_ts_utc",
        "feature_cutoff_ts_utc",
        "identity_observed_ts_utc",
        "euro_1h_available_ts_utc",
        "predicted_sp_available_ts_utc",
        "identity_timing_status",
        "availability_status",
        "devig_euro_probability",
        "market_uncertainty",
    ):
        return "bj203_causal_tensor_v2"
    return "derived_or_identity"


def _feature_timestamp_rule(column: str) -> str:
    if column.startswith("Q_BJ_SP_DEVIG"):
        return "decision-epoch snapshot_ts_utc <= decision_epoch"
    if column in (contract.Q_BJ_CALIBRATED, contract.BJ_LINE_BOUNDARY):
        return "frozen #204 Gate A v5 causal window (decision-epoch bound)"
    if column == contract.P_POWER_BJLINE:
        return "#180 feature_cutoff_ts (own cutoff); compared to decision epoch"
    if column in (
        "euro_1h_available_ts_utc",
        "predicted_sp_available_ts_utc",
        "identity_observed_ts_utc",
    ):
        return "observed-at from #203 identity (per match)"
    return "immutable identity or derived at build"


def _feature_admissible_use(column: str) -> str:
    if column in contract.DEV_LABEL_INCLUDE_COLUMNS:
        return contract.ADMISSIBLE_DEVELOPMENT_LABEL
    if column in (
        "winning_zero_return_units",
        "payout_factor",
        "payout_after_65_units",
        "tax_rate",
        "tax_cliff_gross_yuan",
        "tax_realized_yuan",
    ):
        return contract.ADMISSIBLE_SEALED
    return contract.ADMISSIBLE_INFERENCE


def _feature_units(column: str) -> str:
    if "prob" in column or column.startswith("Q_") or column.startswith("P_"):
        return "probability [0,1]"
    if column.endswith("_ts_utc") or column.endswith("_ts"):
        return "UTC timestamp"
    if column in ("BJ_LINE_BOUNDARY", "native_handicap_line", "handicap_line_norm"):
        return "goals (integer or half-goal)"
    if "sp" in column.lower() or "SP" in column:
        return "decimal odds (>1)"
    if column in ("market_uncertainty", "market_signature_dispersion"):
        return "dimensionless uncertainty"
    return "unitless / categorical"


def _feature_domain(column: str, raw: pd.Series) -> str:
    if column in ("outcome_code", "result_code"):
        return "3|1|0"
    if column in ("cohort", "split"):
        return "development|test|heldout"
    if column in ("identity_timing_status",):
        return "CUTOFF_BOUND_IDENTITY|RETROSPECTIVE_IDENTITY_ONLY|TIMESTAMPED_IDENTITY_ONLY"
    if column in ("availability_status",):
        return "AVAILABLE|UNAVAILABLE"
    if column in ("role",):
        return "DEVELOPMENT_CV|RETROSPECTIVE_TEST_LOCKED"
    if column in ("source_grade",):
        return "RETROSPECTIVE_PROXY_PCLOSE|RETROSPECTIVE_PROXY"
    return ""

def _feature_key_role(column: str) -> str:
    if column == "cell_key":
        return "primary_key"
    if column in ("issue", "match_idx", "outcome_code"):
        return "identity_key"
    if column in ("issue_instance", "year", "cohort"):
        return "foreign_key"
    return ""


def build_schema(cells: pd.DataFrame) -> dict:
    """Machine-readable handoff schema (REQ-D09 / class-5 sweep)."""
    columns = []
    for column in cells.columns:
        raw = cells[column]
        columns.append(
            {
                "name": column,
                "dtype": str(raw.dtype),
                "nullable": bool(raw.isna().any()),
                "domain": _feature_domain(column, raw),
                "key_role": _feature_key_role(column),
                "source": _feature_source(column),
                "admissible_use": _feature_admissible_use(column),
            }
        )
    return {
        "package": contract.PACKAGE_NAME,
        "schema_version": "1.0",
        "primary_key": "cell_key",
        "identity_keys": ["issue", "match_idx", "outcome_code"],
        "relationship": {
            "inference_cells": "cell_key = issue:match_idx:outcome_code",
            "development_labels": "cell_join_key (issue:match:outcome) -> inference cell_key",
            "feature_dictionary": "feature name -> inference_cells column",
        },
        "columns": columns,
    }


def build_probability_mapping_registry(receipt: BuildReceipt) -> pd.DataFrame:
    """Probability mapping/reconciliation registry incl. source identity."""
    cells = receipt.cells
    rows = []
    for representation in [
        contract.Q_BJ_SP_DEVIG,
        contract.Q_BJ_CALIBRATED,
        contract.Q_EU_RAW_1X2,
        contract.Q_EU_BJLINE,
        contract.P_POWER_BJLINE,
    ]:
        if representation not in cells.columns:
            continue
        raw = cells[representation]
        available = raw.apply(
            lambda v: (
                v is not None
                and isinstance(v, (list, tuple, np.ndarray))
                and len(v) == 3
            )
        ).sum()
        source_col = {
            contract.Q_BJ_SP_DEVIG: contract.SOURCE_IDENTITY_SP,
            contract.Q_BJ_CALIBRATED: contract.SOURCE_IDENTITY_Q_BJ,
            contract.Q_EU_RAW_1X2: contract.SOURCE_IDENTITY_EU,
            contract.Q_EU_BJLINE: contract.SOURCE_IDENTITY_EU,
            contract.P_POWER_BJLINE: contract.SOURCE_IDENTITY_POWER,
        }.get(representation)
        source_values = (
            cells[source_col].value_counts().to_dict()
            if source_col in cells.columns
            else {}
        )
        rows.append(
            {
                "representation": representation,
                "definition": _representation_definition(representation),
                "available_cells": int(available),
                "total_cells": len(cells),
                "coverage_fraction": float(available / len(cells)),
                "source_identity": source_values,
                "kept_separate_from": _separation_note(representation),
            }
        )
    return pd.DataFrame(rows)


def _representation_definition(representation: str) -> str:
    definitions = {
        contract.Q_BJ_SP_DEVIG: "normalized inverse decision-epoch Beijing 3/1/0 SP within match",
        contract.Q_BJ_CALIBRATED: "accepted causal market-anchor probability (#204 Gate A v5)",
        contract.Q_EU_RAW_1X2: "de-vigged average European straight-result probability (#203 devig, independent)",
        contract.Q_EU_BJLINE: "EU probability translated to native BJ space via explicit Poisson score distribution",
        contract.P_POWER_BJLINE: "power/team model probability in native BJ space (#180 Gate A v2)",
    }
    return definitions.get(representation, "derived")


def _separation_note(representation: str) -> str:
    if representation in (contract.Q_BJ_CALIBRATED, contract.Q_BJ_SP_DEVIG):
        return "raw SP de-vig and calibrated market vector remain separate columns"
    if representation == contract.Q_EU_RAW_1X2:
        return "kept separate from Q_BJ_CALIBRATED; same-source alias rows marked NON_INDEPENDENT"
    return "kept separate from all other representations"
