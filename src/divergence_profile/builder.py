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

import hashlib
import json

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import contract
from . import divergence
from . import probabilities as prob
from . import profile as prof
from . import publication
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
    development_labels: pd.DataFrame = field(default=None)  # type: ignore[assignment]
    sealed_labels: pd.DataFrame = field(default=None)  # type: ignore[assignment]


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
    if cohort_map["issue_instance"].duplicated().any():
        raise sources.UpstreamBindingError("#203 issue_instance maps to multiple cohorts")
    cells = cells.merge(
        cohort_map, on="issue_instance", how="left", validate="many_to_one",
        indicator="_cohort_merge",
    )
    cells["bj203_identity_status"] = np.where(
        cells["_cohort_merge"].eq("both"), "MATCHED", "NO_BJ203_IDENTITY"
    )
    # Prospective #204 cells outside #203 remain on the 3-cell axis and retain
    # #204's explicit role; they are unavailable causally, never silently
    # dropped or assigned a fabricated #203 cohort.
    cells["cohort"] = cells["split"].where(cells["split"].notna(), cells["role"])
    cells = cells.drop(columns=["_cohort_merge", "split"])

    # #203 identity match-level timestamps joined on (issue, match_idx) —
    # one row per match, never an issue-level broadcast.
    cells = cells.merge(
        meta, on=["issue", "match_idx"], how="left", validate="many_to_one",
        indicator="_meta_merge",
    )
    cells["bj203_match_meta_status"] = np.where(
        cells["_meta_merge"].eq("both"), "MATCHED", "NO_BJ203_MATCH_META"
    )
    cells = cells.drop(columns="_meta_merge")

    # per-cell #203 feature values for EU/uncertainty (devig_euro_probability)
    # bind via #203's hashed cell_join_key mapped through identity to the
    # readable (issue, match_idx, outcome_code) key.
    key_map = identity[["cell_join_key", "issue", "match_idx", "outcome_code"]]
    key_map["cell_join_key"] = key_map["cell_join_key"].astype(str)
    fv = feature_values.copy()
    fv["cell_join_key"] = fv["cell_join_key"].astype(str)
    fv_joined = fv.merge(
        key_map, on="cell_join_key", how="inner", validate="one_to_one"
    )
    if fv_joined.duplicated(["issue", "match_idx", "outcome_code"]).any():
        raise sources.UpstreamBindingError("#203 feature value maps to duplicate cell identity")
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
        validate="one_to_one",
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


def _apply_scalar_causal_feature(
    cells: pd.DataFrame, feature: str, observed_at_source: str
) -> pd.DataFrame:
    """Publish source observed-at and causal mask for scalar inference fields."""
    out = cells.copy()
    observed_name = contract.observed_at_col(feature)
    available_name = contract.available_col(feature)
    reason_name = contract.reason_col(feature)
    observed = pd.to_datetime(
        out.get(observed_at_source, pd.Series(pd.NaT, index=out.index)),
        errors="coerce",
        utc=True,
    )
    epoch = pd.to_datetime(out[contract.DECISION_EPOCH_COLUMN], errors="coerce", utc=True)
    kickoff = pd.to_datetime(out["kickoff_ts_utc"], errors="coerce", utc=True)
    present = pd.to_numeric(
        out.get(feature, pd.Series(np.nan, index=out.index)), errors="coerce"
    ).notna()
    available = present & observed.notna() & epoch.notna() & kickoff.ge(epoch) & observed.le(epoch)
    out[observed_name] = observed
    out[available_name] = available.astype(bool)
    out[reason_name] = np.select(
        [
            ~present,
            present & (observed.isna() | epoch.isna()),
            present & kickoff.lt(epoch),
            present & observed.gt(epoch),
        ],
        [
            "MISSING_SOURCE_VALUE",
            contract.REASON_NO_CAUSAL_EPOCH,
            contract.REASON_POST_DECISION_OBSERVATION,
            contract.REASON_OBSERVED_AFTER_EPOCH,
        ],
        default=None,
    )
    return out


def prepare_label_namespaces(
    labels: pd.DataFrame, identity: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Join labels to authoritative #203 identity year and seal future years.

    Issue identifiers such as ``21001`` are opaque IDs, never dates.  All
    year/cohort/match identity comes from ``cell_identity.year/split``.
    """
    required_identity = {
        "cell_join_key", "issue", "issue_instance", "match_idx",
        "outcome_code", "year", "split",
    }
    if not required_identity.issubset(identity.columns):
        raise ValueError(
            f"cell identity missing label-boundary fields: {sorted(required_identity - set(identity.columns))}"
        )
    if "cell_join_key" not in labels.columns:
        raise ValueError("labels missing cell_join_key")
    if identity["cell_join_key"].astype(str).duplicated().any():
        raise ValueError("cell identity duplicate cell_join_key")
    if labels["cell_join_key"].astype(str).duplicated().any():
        raise ValueError("labels duplicate cell_join_key")

    authoritative = identity[list(required_identity)].copy()
    authoritative["cell_join_key"] = authoritative["cell_join_key"].astype(str)
    authoritative["cell_key"] = (
        authoritative["issue"].astype(str)
        + ":" + authoritative["match_idx"].astype(int).astype(str)
        + ":" + authoritative["outcome_code"].astype(str)
    )
    lab = labels.copy()
    lab["cell_join_key"] = lab["cell_join_key"].astype(str)
    # Source copies are non-authoritative and are discarded before the join.
    lab = lab.drop(
        columns=[
            column for column in (
                "issue", "issue_instance", "match_idx", "outcome_code",
                "year", "split", "cohort", "cell_key",
            ) if column in lab.columns
        ]
    )
    joined = lab.merge(
        authoritative,
        on="cell_join_key",
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if joined["_merge"].ne("both").any():
        raise ValueError("labels contain unidentifiable cell_join_key")
    joined = joined.drop(columns="_merge").rename(columns={"split": "cohort"})
    joined["year"] = joined["year"].astype(int)
    joined["match_idx"] = joined["match_idx"].astype(int)
    joined["outcome_code"] = joined["outcome_code"].astype(str)
    if "result_code" in joined.columns:
        joined["is_winner"] = (
            joined["result_code"].astype(str).str.strip()
            == joined["outcome_code"].astype(str).str.strip()
        )
    dev = joined[joined["year"] <= contract.LABEL_OPEN_MAX_YEAR].copy()
    receipts = []
    for namespace, selector in (
        ("2024_labels", joined["year"].eq(2024)),
        ("2025_plus_labels", joined["year"].ge(2025)),
        ("2024_plus_labels", joined["year"].ge(2024)),
    ):
        receipts.append(
            {
                "namespace": namespace,
                "status": "SEALED_NOT_OPENED",
                "upstream_rows": int(selector.sum()),
                "handoff_rows": 0,
            }
        )
    return dev.reset_index(drop=True), pd.DataFrame(receipts)


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

    # 6. publish causal masks BEFORE every divergence/profile consumer.
    cells, causal = quality.apply_causal_availability(cells)
    cells = _apply_scalar_causal_feature(
        cells, "predicted_final_sp_input", "predicted_sp_available_ts_utc"
    )
    cells = _apply_scalar_causal_feature(
        cells, "market_uncertainty", "euro_1h_available_ts_utc"
    )

    # 7. divergence features consume causal masks only.
    cells = divergence.build_divergence_features(cells)

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
    identity = sources.load_bj203_identity(root)
    dev_labels, sealed_labels = prepare_label_namespaces(labels, identity)
    receipt.development_labels = dev_labels
    receipt.sealed_labels = sealed_labels
    receipt.checks["DQ12_payout_factor_boundary"] = pd.concat(
        [
            receipt.checks.get("DQ12_payout_factor_boundary", pd.DataFrame()),
            quality.dq12_payout_boundary_payload(dev_labels, "development_labels"),
            quality.dq12_payout_boundary_payload(sealed_labels, "sealed_label_namespaces"),
        ],
        ignore_index=True,
    )

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
        "probability_distribution_eu_raw": prof.probability_distribution(
            cells, contract.Q_EU_RAW_1X2
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
            cells, dev_labels
        ),
        "predicted_sp_vs_settlement_sp": prof.predicted_sp_vs_settlement_sp(
            cells, dev_labels
        ),
        "outlier_heavy_tail": prof.outlier_heavy_tail_table(
            receipt.checks.get("DQ10_outlier_constant_fields", pd.DataFrame())
        ),
    }
    receipt.tables["chart_source_mapping"] = prof.chart_source_mapping(
        receipt.tables
    )

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
    no_causal_epoch = 0
    if causal is not None and not causal.empty:
        observed_after = int(
            (causal["unavailable_reason"] == contract.REASON_OBSERVED_AFTER_EPOCH)
            .sum()
        )
        no_causal_epoch = int(
            (causal["unavailable_reason"] == contract.REASON_NO_CAUSAL_EPOCH).sum()
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
        and no_causal_epoch == 0
        and available_violations == 0
    )

    dup_count = _count(checks, "DQ01_duplicate_identity")
    invalid_count = _count(checks, "DQ05_invalid_probability_triplets")
    payout_count = _count(checks, "DQ12_payout_factor_boundary")

    # REQ-D04: every translated expert must remain in the target BJ line
    # space. A POWER source-line mismatch is unavailable, never merged.
    invalid_line = 0
    if "eu_bjline_reason" in cells.columns:
        invalid_line = int(
            (cells["eu_bjline_reason"] == contract.REASON_INVALID_LINE).sum()
        )
    power_line_mismatch = int(
        cells.get(
            contract.producer_reason_col(contract.P_POWER_BJLINE),
            pd.Series(dtype=object),
        ).eq(contract.REASON_SOURCE_LINE_MISMATCH).sum()
    )
    d04_pass = invalid_line == 0 and power_line_mismatch == 0

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
    dev_labels = getattr(receipt, "development_labels", None)
    sealed_labels = getattr(receipt, "sealed_labels", None)
    label_year_ok = (
        dev_labels is not None
        and not dev_labels.empty
        and "year" in dev_labels
        and dev_labels["year"].astype(int).le(contract.LABEL_OPEN_MAX_YEAR).all()
    )
    sealed_ok = (
        sealed_labels is not None
        and not sealed_labels.empty
        and sealed_labels["handoff_rows"].eq(0).all()
        and {"2024_labels", "2025_plus_labels", "2024_plus_labels"}.issubset(
            set(sealed_labels["namespace"])
        )
    )
    d06_pass = not any(c in cells.columns for c in forbidden) and label_year_ok and sealed_ok

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
    calibration = receipt.tables.get("development_only_calibration", pd.DataFrame())
    expected_calibration = {
        (representation, outcome, "development")
        for representation in contract.PROBABILITY_REPRESENTATIONS
        for outcome in contract.OUTCOME_CODES
    }
    actual_calibration = (
        set(calibration[["representation", "outcome", "cohort"]].itertuples(index=False, name=None))
        if {"representation", "outcome", "cohort"}.issubset(calibration.columns)
        else set()
    )
    chart_mapping = receipt.tables.get("chart_source_mapping", pd.DataFrame())
    d08_pass = (
        all(t in receipt.tables for t in required_tables)
        and expected_calibration.issubset(actual_calibration)
        and not chart_mapping.empty
        and not chart_mapping["status"].eq("UNASSESSED").any()
    )

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

    # REQ-D10: the disposition must match the independently recomputable
    # minimum interface, not merely be one of three allowed strings.
    expected_disposition = prof.readiness_disposition(
        cells,
        has_post_decision_exclusions=post_decision > 0,
    )
    d10_pass = receipt.disposition == expected_disposition

    rows = [
        {
            "requirement": "REQ-D01",
            "name": "Causal provenance",
            "evidence": (
                f"match-level kickoff/decision-epoch join (no issue-level "
                f"broadcast); post-decision cells={post_decision}; "
                f"missing timestamps={missing_ts}; observed-after-epoch "
                f"features={observed_after}; raw-present/no-causal-epoch="
                f"{no_causal_epoch}; available-set violations="
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
                f"{invalid_line}; POWER source-line mismatches: "
                f"{power_line_mismatch}; unidentifiable translations emit "
                "TRANSLATION_NOT_IDENTIFIABLE and mismatched POWER lines "
                "remain unavailable."
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
                f"disposition={receipt.disposition}; expected="
                f"{expected_disposition}; causal support="
                f"{prof.readiness_support(cells)}; no data gap repaired by "
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

    return prof.readiness_disposition(
        receipt.cells,
        has_post_decision_exclusions=post_decision > 0,
    )


# ---------------------------------------------------------------------------
# Atomic publication (class 6)
# ---------------------------------------------------------------------------
def write_package(receipt: BuildReceipt, *, force: bool = False) -> Path:
    """Publish the complete package through one crash-durable directory swap."""
    target = contract.package_path(receipt.root)
    return publication.atomic_publish_directory(
        target, lambda staging: _write_staging(receipt, staging), force=force
    )


def _write_staging(receipt: BuildReceipt, target: Path) -> None:
    """Populate an unpublished staging tree; no live package is mutated."""
    tables_dir = target / "tables"
    figures_dir = target / "figures"
    ledger_dir = target / "ledger"
    evidence_dir = target / "evidence"
    for directory in (tables_dir, figures_dir, ledger_dir, evidence_dir):
        directory.mkdir(parents=True, exist_ok=True)

    cells = receipt.cells.copy()
    forbidden = [
        "result_code", "final_sp", "winning_zero_return_units", "payout_factor",
        "payout_after_65_units", "tax_rate", "tax_cliff_gross_yuan",
        "tax_realized_yuan", "settlement_status", "settlement_quality",
        "settlement_source",
    ]
    cells = cells.drop(columns=[column for column in forbidden if column in cells.columns])
    if receipt.development_labels is None or receipt.sealed_labels is None:
        raise RuntimeError(
            "label namespaces must be prepared from authoritative #203 identity before publication"
        )
    dev_labels = receipt.development_labels.copy()
    dev_labels = dev_labels.drop(
        columns=[column for column in forbidden if column in dev_labels.columns and column != "final_sp"],
        errors="ignore",
    )
    sealed = receipt.sealed_labels.copy()
    feature_dictionary = build_feature_dictionary(cells)
    mapping = build_probability_mapping_registry(receipt)
    cohort = (
        cells[["issue", "cohort", "year"]]
        .drop_duplicates()
        .sort_values(["year", "issue"])
        .reset_index(drop=True)
    )

    manifest_payload = _build_manifest(receipt, cells)
    reviewed_binding = str(manifest_payload["reviewed_commit_sha"])
    evidence = receipt.evidence.copy()
    evidence["reviewed_commit_sha"] = reviewed_binding

    payloads: dict[str, tuple[str, pd.DataFrame]] = {
        "inference_cells": ("inference_cells.parquet", cells),
        "development_labels": ("development_labels_through_2023.parquet", dev_labels),
        "sealed_label_namespaces": ("sealed_label_namespaces.csv", sealed),
        "feature_dictionary": ("feature_dictionary.csv", feature_dictionary),
        "probability_mapping_registry": ("probability_mapping_registry.csv", mapping),
        "cohort_registry": ("cohort_registry.csv", cohort),
        "causal_eligibility": ("causal_eligibility.parquet", receipt.causal),
        "evidence": ("evidence/req_d_evidence.csv", evidence),
    }
    for name, table in sorted(receipt.tables.items()):
        if table is not None:
            payloads[name] = (f"tables/{name}.csv", table)
    for name, table in sorted(receipt.checks.items()):
        materialized = table
        if materialized is None or materialized.empty:
            materialized = pd.DataFrame({"check": [name], "rows": [0]})
        payloads[f"ledger_{name}"] = (f"ledger/{name}.csv", materialized)

    for _, (relative, frame) in sorted(payloads.items()):
        destination = target / relative
        if relative.endswith(".parquet"):
            publication.atomic_write_parquet(frame, destination)
        else:
            publication.atomic_write_csv(frame, destination)

    from . import figures
    figures.write_all_figures(receipt.tables, cells, figures_dir)

    schema = build_schema(payloads)
    publication.atomic_write_json(target / "handoff_schema.json", schema)

    from . import handoff as handoff_mod
    report = handoff_mod.render_data_readiness(
        cells, dev_labels, sealed, manifest_payload
    )
    publication.atomic_write_text(target / "DATA_READINESS.md", report)
    for evidence_note in ("R4_PI_TAKEOVER.md", "DEBT-LEDGER.md"):
        source_note = receipt.root / evidence_note
        if source_note.exists():
            publication.atomic_write_text(
                target / evidence_note,
                source_note.read_text(encoding="utf-8"),
            )
    manifest_payload["report_sha256"] = sources.sha256_file(target / "DATA_READINESS.md")
    manifest_payload["schema_sha256"] = sources.sha256_file(target / "handoff_schema.json")
    publication.atomic_write_json(target / "MANIFEST.json", manifest_payload)

    from . import manifest as manifest_mod
    manifest_mod.write_replay(
        target,
        receipt,
        receipt.root,
        manifest_payload,
        package_name=contract.PACKAGE_NAME,
    )
    manifest_mod.write_sha256sums(target)


def _build_manifest(receipt: BuildReceipt, cells: pd.DataFrame) -> dict:
    """Bind PR review symbolically plus exact code/notebook/dependency bytes.

    A Git commit cannot contain its own SHA.  ``PR_HEAD`` is resolved by the
    verifier and ``post_handoff.py`` against PR #231; unlike R2's stale parent
    SHA, this binding remains true at the final delivery commit.
    """
    root = receipt.root.resolve()
    producer_commit = _git_head(root)
    code_hash = _dir_hash(root / "src" / "divergence_profile")
    notebook = root / "notebooks" / "research" / "issue-229" / "bj229_divergence_profile.ipynb"
    notebook_hash = _notebook_semantic_hash(notebook) if notebook.exists() else "missing"
    requirements = root / "requirements.txt"
    requirements_hash = (
        sources.sha256_file(requirements) if requirements.exists() else "missing"
    )
    return {
        "package": contract.PACKAGE_NAME,
        "contract_version": "BJ-UNIFIED-DIVERGENCE-DATA-PROFILE-001/v2",
        "rework": "PI takeover R4 candidate-mode conclusion correction (2026-08-16)",
        "audit_mode": "candidate",
        "reviewed_commit_sha": "PR_HEAD",
        "producer_commit_sha": producer_commit,
        "commit_binding_mode": "github_pr_231_head_plus_content_hashes",
        "code_hash": code_hash,
        "notebook_hash": notebook_hash,
        "notebook_hash_mode": "semantic_source_cells_v1",
        "requirements_hash": requirements_hash,
        "built_at_utc": _commit_date(root, producer_commit) or datetime.now(timezone.utc).isoformat(),
        "disposition": receipt.disposition,
        "cell_count": len(cells),
        "issue_count": int(cells["issue"].nunique()),
        "match_count": int(cells[["issue", "match_idx"]].drop_duplicates().shape[0]),
        "causally_available_cells_by_source": {
            representation: int(
                cells.get(
                    contract.available_col(representation),
                    pd.Series(False, index=cells.index),
                ).fillna(False).astype(bool).sum()
            )
            for representation in contract.CAUSAL_REPRESENTATIONS
        },
        "development_label_rows_through_2023": int(len(receipt.development_labels)),
        "sealed_label_namespaces": receipt.sealed_labels.to_dict("records"),
        "upstream_packages": {
            key: _relative_to_root(
                contract.upstream_path(receipt.root, key), receipt.root
            )
            for key in contract.UPSTREAM_PACKAGES
        },
        "source_hashes": receipt.source_hashes,
        "environment": _environment(),
    }


def _commit_date(root: Path, commit: str) -> str | None:
    """Committer ISO date of ``commit`` (deterministic replay anchor)."""
    try:
        result = __import__("subprocess").run(
            ["git", "-C", str(root), "show", "-s", "--format=%cI", commit],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except Exception:  # noqa: BLE001
        pass
    return None


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


def _notebook_semantic_hash(path: Path) -> str:
    """Hash notebook source/structure while excluding execution outputs.

    The executable notebook builds the package before the executor persists
    outputs, so a byte hash would be a self-reference.  This hash binds every
    code/markdown cell, cell id, and notebook/kernel metadata while excluding
    only execution counts and outputs; the package hash manifest separately
    binds every generated artifact byte.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    normalized = {
        "nbformat": payload.get("nbformat"),
        "nbformat_minor": payload.get("nbformat_minor"),
        "metadata": payload.get("metadata", {}),
        "cells": [
            {
                "cell_type": cell.get("cell_type"),
                "id": cell.get("id"),
                "metadata": {
                    key: value
                    for key, value in cell.get("metadata", {}).items()
                    if key != "execution"
                },
                "source": cell.get("source", []),
                "attachments": cell.get("attachments", {}),
            }
            for cell in payload.get("cells", [])
        ],
    }
    encoded = json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    return "UNSPECIFIED"

def _feature_key_role(column: str) -> str:
    if column == "cell_key":
        return "primary_key"
    if column in ("issue", "match_idx", "outcome_code"):
        return "identity_key"
    if column in ("issue_instance", "year", "cohort"):
        return "foreign_key"
    return "NONE"


def build_schema(
    payloads: dict[str, tuple[str, pd.DataFrame]] | pd.DataFrame,
) -> dict:
    """Describe every physical package table, not only inference columns.

    A DataFrame argument is accepted only for legacy callers and is promoted to
    the canonical inference table; publication always passes the full payload
    registry.
    """
    if isinstance(payloads, pd.DataFrame):
        payloads = {"inference_cells": ("inference_cells.parquet", payloads)}

    primary_keys: dict[str, list[str]] = {
        "inference_cells": ["cell_key"],
        "development_labels": ["cell_key"],
        "sealed_labels": ["namespace"],
        "feature_dictionary": ["feature"],
        "evidence": ["requirement"],
        "probability_mapping_registry": ["representation"],
        "cohort_registry": ["issue"],
        "causal_eligibility": ["cell_key", "representation"],
        "chart_source_mapping": ["figure"],
    }
    foreign_keys: dict[str, list[dict[str, object]]] = {
        "development_labels": [
            {"column": "cell_key", "columns": ["cell_key"], "references": "inference_cells.cell_key", "cardinality": "zero_or_one_to_one"}
        ],
        "causal_eligibility": [
            {"column": "cell_key", "columns": ["cell_key"], "references": "inference_cells.cell_key", "cardinality": "many_to_one"}
        ],
        "cohort_registry": [
            {"column": "issue", "columns": ["issue"], "references": "inference_cells.issue", "cardinality": "one_to_many"}
        ],
    }
    tables: dict[str, object] = {}
    for table_name, (relative_path, frame) in sorted(payloads.items()):
        columns = []
        for column in frame.columns:
            raw = frame[column]
            list_shape = [3] if column in contract.PROBABILITY_REPRESENTATIONS else None
            physical = str(raw.dtype)
            if relative_path.endswith(".parquet"):
                try:
                    import pyarrow as pa

                    physical = str(pa.Schema.from_pandas(frame[[column]], preserve_index=False).field(column).type)
                except Exception:  # pragma: no cover - pandas dtype remains explicit
                    physical = str(raw.dtype)
            columns.append(
                {
                    "name": column,
                    "physical_type": physical,
                    "logical_type": (
                        "probability_vector_3"
                        if list_shape
                        else "utc_timestamp"
                        if column.endswith("_utc") or column.endswith("_ts_utc")
                        else "boolean"
                        if pd.api.types.is_bool_dtype(raw.dtype)
                        else "integer"
                        if pd.api.types.is_integer_dtype(raw.dtype)
                        else "number"
                        if pd.api.types.is_float_dtype(raw.dtype)
                        else "string_or_struct"
                    ),
                    "units": _feature_units(column),
                    "nullable": bool(raw.isna().any()),
                    "domain": _feature_domain(column, raw),
                    "list_shape": list_shape,
                    "source": _feature_source(column),
                    "admissible_use": _feature_admissible_use(column),
                }
            )
        keys = primary_keys.get(table_name, [])
        distinct_pk = (
            int(frame[keys].drop_duplicates().shape[0])
            if keys and all(key in frame.columns for key in keys)
            else None
        )
        tables[table_name] = {
            "path": relative_path,
            "format": Path(relative_path).suffix.lstrip("."),
            "row_count": int(len(frame)),
            "primary_key": keys,
            "foreign_keys": foreign_keys.get(table_name, []),
            "cardinality": {
                "rows": int(len(frame)),
                "distinct_primary_keys": distinct_pk,
            },
            "columns": columns,
        }
    return {
        "package": contract.PACKAGE_NAME,
        "schema_version": "2.0",
        "tables": tables,
        "relationships": {
            "development_labels_to_inference": "physical cell_key FK; no upstream private map",
            "feature_dictionary_to_inference": "feature is exactly one inference column",
            "causal_eligibility_to_inference": "one row per cell_key × representation",
        },
    }


def build_probability_mapping_registry(receipt: BuildReceipt) -> pd.DataFrame:
    """Probability mapping/reconciliation registry incl. source identity."""
    cells = receipt.cells
    rows = []
    for representation in contract.PROBABILITY_REPRESENTATIONS:
        if representation not in cells.columns:
            continue
        raw = cells[representation]
        raw_present = raw.apply(
            lambda value: isinstance(value, (list, tuple, np.ndarray))
            and len(value) == 3
        ).sum()
        causal_available = int(
            cells.get(
                contract.available_col(representation),
                pd.Series(False, index=cells.index),
            ).fillna(False).astype(bool).sum()
        )
        source_col = contract.source_identity_col(representation)
        source_values = (
            cells[source_col].value_counts().to_dict()
            if source_col in cells.columns
            else {}
        )
        rows.append(
            {
                "representation": representation,
                "definition": _representation_definition(representation),
                "raw_present_cells": int(raw_present),
                "causally_available_cells": causal_available,
                "total_cells": len(cells),
                "causal_coverage_fraction": float(causal_available / len(cells)),
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
