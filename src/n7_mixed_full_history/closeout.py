"""Close-out addendum for the frozen #394 package (issue #399).

Contract BJ-UNIFIED-N7-MIXED-CLOSEOUT-001/v1.

The merged #394 package (`results/n7_mixed_full_history/`, PR #398, merge
commit 5457afbff6582b9f204e176e4f4a7e2943977914) published a single tail
statistic under the label `matched_ex_largest_lift_cny` which was computed as

    delta.sum() - delta[argmax(abs(delta))]

i.e. the *paired-delta sensitivity* (total paired delta minus the single
largest-absolute paired delta, all on the exact-common issue set).  That is
NOT an armwise ex-largest lift.  This addendum publishes two semantically
distinct statistics and explicitly deprecates the merged label:

1. `armwise_ex_largest_lift_cny = subject_ex_largest_pnl_cny
   - reference_ex_largest_pnl_cny`, where each arm's own largest *gross
   payout* issue is removed from that arm's total PnL first:

       subject_ex_largest_pnl_cny = pnl_a.sum() - pnl_a[argmax(gross_a)]
       reference_ex_largest_pnl_cny = pnl_b.sum() - pnl_b[argmax(gross_b)]

2. `largest_absolute_paired_delta_sensitivity_cny = delta.sum()
   - delta[argmax(abs(delta))]` (signed delta at the largest absolute
   paired-delta issue) — this is the correctly-named form of the value the
   merged package mislabeled.

The two statistics can coincide numerically but are computed by independent
code paths and their semantics are not interchangeable.

Everything in this module is deterministic: it rebuilds the frozen paired
frames with the frozen #394 pipeline (`_paired_frame_for_schedule`), asserts
exact parity with the committed `matched_contrasts.csv`, and only then writes
the corrected derived evidence into a NEW immutable package
(`results/n7_mixed_full_history_addendum/`).  No outcome-driven method change
and no new parameter search.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.n7_mixed_full_history.contract import (
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    EVIDENCE_QUERY_CUTOFF_TS,
    MOVING_BLOCK_LENGTH,
)
from src.n7_mixed_full_history.pipeline import (
    _matched_contrasts_board,
    _paired_frame_for_schedule,
    sha256_file,
)
from src.source_schema.publication import atomic_write_json, atomic_write_text
from src.temporal_learning import implementation_closure

CONTRACT_ID = "BJ-UNIFIED-N7-MIXED-CLOSEOUT-001/v1"
ISSUE_NUMBER = 399
PARENT_ISSUE = 394

# Frozen source (issue #399 contract, "Frozen source").
SOURCE_MERGE_SHA = "5457afbff6582b9f204e176e4f4a7e2943977914"
SOURCE_MERGE_PR = 398
SOURCE_PACKAGE = "results/n7_mixed_full_history"

ADDENDUM_PACKAGE = "results/n7_mixed_full_history_addendum"
REPORT_PATH = "docs/research/Issue-399-N7-Mixed-Closeout-Addendum.md"
NOTEBOOK_PATH = (
    "notebooks/research/n7-mixed-full-history/Issue-399-N7-Mixed-Closeout-Addendum.ipynb"
)
VERIFIER_PATH = "scripts/verify_n7_mixed_closeout_addendum.py"
BUILDER_PATH = "scripts/build_n7_mixed_closeout_addendum.py"
TEST_PATH = "tests/test_bj399_n7_mixed_closeout_addendum.py"

# Machine-table report marker: the fenced block immediately after this HTML
# comment must byte-equal the committed corrected machine CSV (E06 parity).
REPORT_MACHINE_TABLE_MARKER = "<!-- ADDENDUM_MACHINE_TABLE -->"

# Bootstrap estimand metadata (frozen producer config).
ESTIMAND = "paired_mean_cny_per_issue"
UNIT = "CNY_PER_ISSUE"

CONTRAST_PAIRS = [
    ("MIXED_50_50", "MIXED_50_50", "R3_STANDALONE", "vs_R3"),
    ("MIXED_50_50", "MIXED_50_50", "C1E3_STANDALONE", "vs_C1E3"),
    ("MIXED_50_50", "MIXED_50_50", "R0_COMPARATOR", "vs_R0"),
]
SCOPES = ("PRE_2025", "EXTENSION_2025_2026", "ALL")

PACKAGE_FILES = (
    "ADDENDUM_RECEIPT.json",
    "DECISION_RECEIPT.json",
    "matched_contrasts_corrected.csv",
    "moving_block_metadata.json",
    "paired_delta_frame.csv",
    "semantic_counterexamples.csv",
)
# MANIFEST.json is intentionally absent from PACKAGE_FILES: a manifest cannot
# list its own hash (same convention as the frozen #394 package).

DEPRECATION_STATEMENT = (
    "The merged #394 field `matched_ex_largest_lift_cny` is DEPRECATED and MUST "
    "NOT be consumed as an armwise ex-largest lift. It was computed as the "
    "paired-delta sensitivity `delta.sum() - delta[argmax(abs(delta))]` on the "
    "exact-common issue set, not as an armwise ex-largest removal. Consumers "
    "must use `armwise_ex_largest_lift_cny` for armwise ex-largest semantics "
    "and `largest_absolute_paired_delta_sensitivity_cny` for the paired-delta "
    "sensitivity semantics."
)


# ---------------------------------------------------------------------------
# Corrected statistics (independent implementations, shared frozen frames)
# ---------------------------------------------------------------------------

def _armwise_ex_largest(
    pnl: np.ndarray, gross: np.ndarray, issues: list[str]
) -> dict[str, Any]:
    """Remove the arm's own largest gross-payout issue, return ex-largest PnL."""
    largest = int(np.argmax(gross))
    return {
        "largest_payout_issue": str(issues[largest]),
        "largest_payout_pnl_cny": float(pnl[largest]),
        "ex_largest_pnl_cny": float(pnl.sum() - pnl[largest]),
    }


def corrected_contrasts(bundles: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compute both corrected statistics over every frozen scope x contrast.

    Returns (corrected_table, paired_frame, counterexamples).

    The paired frames reuse the frozen `_paired_frame_for_schedule` (exact
    common denominator, schedule-level sums) so the denominator matches the
    merged #394 table exactly.  The stat logic below is written independently
    of the deprecated single-column path.
    """
    corrected_rows: list[dict[str, Any]] = []
    frame_rows: list[dict[str, Any]] = []
    counter_rows: list[dict[str, Any]] = []

    for scope in SCOPES:
        for _, subject, ref, tag in CONTRAST_PAIRS:
            paired = _paired_frame_for_schedule(bundles, subject, ref)
            if scope == "PRE_2025":
                paired = paired[paired["issue"].astype(str).lt("25011")]
            elif scope == "EXTENSION_2025_2026":
                paired = paired[paired["issue"].astype(str).ge("25011")]
            if paired.empty:
                raise ValueError(f"empty paired frame for {scope} {tag}")

            pnl_a = paired["pnl_a"].to_numpy(float)
            gross_a = paired["gross_a"].to_numpy(float)
            pnl_b = paired["pnl_b"].to_numpy(float)
            gross_b = paired["gross_b"].to_numpy(float)
            delta = pnl_a - pnl_b
            issues = paired["issue"].astype(str).tolist()

            subj_stat = _armwise_ex_largest(pnl_a, gross_a, issues)
            ref_stat = _armwise_ex_largest(pnl_b, gross_b, issues)
            armwise = float(subj_stat["ex_largest_pnl_cny"] - ref_stat["ex_largest_pnl_cny"])

            largest_idx = int(np.argmax(np.abs(delta)))
            sensitivity = float(delta.sum() - delta[largest_idx])

            corrected_rows.append(
                {
                    "scope": scope,
                    "subject_schedule": subject,
                    "reference_schedule": ref,
                    "contrast": tag,
                    "issues": int(len(paired)),
                    "subject_pnl_cny": float(pnl_a.sum()),
                    "reference_pnl_cny": float(pnl_b.sum()),
                    "matched_lift_cny": float(delta.sum()),
                    # --- corrected armwise semantics -------------------------
                    "subject_ex_largest_pnl_cny": float(subj_stat["ex_largest_pnl_cny"]),
                    "reference_ex_largest_pnl_cny": float(ref_stat["ex_largest_pnl_cny"]),
                    "subject_largest_payout_issue": subj_stat["largest_payout_issue"],
                    "reference_largest_payout_issue": ref_stat["largest_payout_issue"],
                    "armwise_ex_largest_lift_cny": armwise,
                    # --- corrected paired-delta sensitivity semantics --------
                    "largest_abs_paired_delta_cny": float(np.abs(delta).max()),
                    "largest_abs_paired_delta_signed_cny": float(delta[largest_idx]),
                    "largest_abs_paired_delta_issue": str(issues[largest_idx]),
                    "largest_absolute_paired_delta_sensitivity_cny": sensitivity,
                }
            )

            for i, row in enumerate(paired.itertuples(index=False)):
                frame_rows.append(
                    {
                        "scope": scope,
                        "contrast": tag,
                        "issue": str(row.issue),
                        "issue_anchor_ts": pd.Timestamp(row.issue_anchor_ts).isoformat(),
                        "pnl_a": float(pnl_a[i]),
                        "gross_a": float(gross_a[i]),
                        "pnl_b": float(pnl_b[i]),
                        "gross_b": float(gross_b[i]),
                        "delta": float(delta[i]),
                    }
                )

            matched_lift = float(delta.sum())
            differ = not math.isclose(armwise, sensitivity, rel_tol=1e-9, abs_tol=1e-9)
            sign_change = (
                math.copysign(1.0, armwise) != math.copysign(1.0, sensitivity)
                and not math.isclose(armwise, 0.0, abs_tol=1e-9)
                and not math.isclose(sensitivity, 0.0, abs_tol=1e-9)
            )
            if differ:
                role = "sign_changing_regression" if sign_change else "counterexample_differ"
            else:
                role = "coincident_equal"
            counter_rows.append(
                {
                    "scope": scope,
                    "contrast": tag,
                    "matched_lift_cny": matched_lift,
                    "armwise_ex_largest_lift_cny": armwise,
                    "largest_absolute_paired_delta_sensitivity_cny": sensitivity,
                    "differ": bool(differ),
                    "sign_change": bool(sign_change),
                    "role": role,
                }
            )

    corrected = pd.DataFrame(corrected_rows)
    frames = pd.DataFrame(frame_rows)
    counters = pd.DataFrame(counter_rows)
    return corrected, frames, counters


# ---------------------------------------------------------------------------
# Parity gate: the frozen board is reproduced exactly by the frozen pipeline.
# ---------------------------------------------------------------------------

def assert_frozen_board_parity(bundles: pd.DataFrame, frozen_csv: pd.DataFrame) -> None:
    """Re-run the merged #394 board code and require exact parity with the
    committed `matched_contrasts.csv` (float tolerance ~1e-9).  This proves
    the addendum's frames/denominators are the frozen ones and that no
    outcome-driven method change happened."""
    rebuilt = _matched_contrasts_board(bundles)
    frozen = frozen_csv.sort_values(["scope", "contrast"]).reset_index(drop=True)
    rebuilt = rebuilt.sort_values(["scope", "contrast"]).reset_index(drop=True)
    if list(rebuilt.columns) != list(frozen.columns):
        raise ValueError("frozen board reproduction column drift")
    for column in rebuilt.columns:
        if column in ("scope", "subject_schedule", "reference_schedule", "contrast"):
            if not (rebuilt[column].astype(str).eq(frozen[column].astype(str))).all():
                raise ValueError(f"frozen board categorical drift in {column}")
            continue
        a = rebuilt[column].to_numpy(float)
        b = frozen[column].to_numpy(float)
        if not np.allclose(a, b, rtol=1e-9, atol=1e-9, equal_nan=True):
            raise ValueError(f"frozen board parity drift in {column}")


# ---------------------------------------------------------------------------
# Addendum package writer
# ---------------------------------------------------------------------------

def _moving_block_metadata(frozen_contrasts: pd.DataFrame) -> dict[str, Any]:
    rows = []
    for row in frozen_contrasts.sort_values(["scope", "contrast"]).itertuples(index=False):
        rows.append(
            {
                "scope": row.scope,
                "contrast": row.contrast,
                "issues": int(row.issues),
                "moving_block_p05_lift_cny_per_issue": float(row.moving_block_p05_lift_cny),
            }
        )
    return {
        "estimand": ESTIMAND,
        "unit": UNIT,
        "semantics": (
            "moving-block bootstrap of the per-issue paired mean lift (CNY); "
            "p05 = 5th percentile over draws of the resampled per-issue mean; "
            "the p05 value is PER-ISSUE scale (CNY_PER_ISSUE), not total lift"
        ),
        "block_length": int(MOVING_BLOCK_LENGTH),
        "draw_count": int(BOOTSTRAP_DRAWS),
        "seed": int(BOOTSTRAP_SEED),
        "reconciles_to_producer_config": True,
        "rows": rows,
    }


def _original_manifest_receipt(repo_root: Path) -> dict[str, Any]:
    source = repo_root / SOURCE_PACKAGE
    manifest_path = source / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "source_merge_sha": SOURCE_MERGE_SHA,
        "source_merge_pr": SOURCE_MERGE_PR,
        "source_package": SOURCE_PACKAGE,
        "original_package_manifest_sha256": sha256_file(manifest_path),
        "original_package_manifest_bytes": manifest_path.stat().st_size,
        "original_source_contract": manifest.get("contract"),
        "original_evidence_cutoff_ts": manifest.get("evidence_cutoff_ts"),
        "original_bj396_manifest_sha256": manifest.get("bj396_manifest_sha256"),
    }


def build_addendum_package(
    repo_root: Path,
    output: Path | None = None,
    deliverables_root: Path | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Deterministically regenerate the addendum package.

    Reads ONLY committed artifacts (no external data root): the frozen
    `bundles.parquet` (hash-bound by the original manifest) and the frozen
    `matched_contrasts.csv`.  Writes the new immutable addendum package.

    Order (hard-wired to make the manifest hash the EXECUTED notebook and the
    authored report):
      1. parity + semantic gates over the frozen frames;
      2. stage + atomically publish the six machine artifacts;
      3. author the corrected report at deliverables_root;
      4. author + execute the addendum notebook (validates the committed
         package on disk);
      5. write MANIFEST.json (six artifact hashes + deliverable hashes).
    """
    repo_root = repo_root.resolve()
    target = (output or repo_root / ADDENDUM_PACKAGE).resolve()
    deliverables_root = (deliverables_root or repo_root).resolve()

    if target.exists() and not force:
        raise ValueError(f"addendum package already exists at {target}; pass force=True to rebuild")

    source = repo_root / SOURCE_PACKAGE
    bundles = pd.read_parquet(source / "bundles.parquet")
    frozen_contrasts = pd.read_csv(source / "matched_contrasts.csv")

    # Gate 1: the frozen board reproduces exactly (determinism + no drift).
    assert_frozen_board_parity(bundles, frozen_contrasts)

    corrected, paired_frame, counterexamples = corrected_contrasts(bundles)

    # Gate 2: independent semantics sanity — the two stats must be computed
    # independently; at least one audited contrast must show them differing,
    # and at least one must show a sign change (contract requirement 5).
    differing = counterexamples[counterexamples["differ"]]
    sign_flips = counterexamples[counterexamples["sign_change"]]
    if differing.empty:
        raise ValueError("no counterexample where the two statistics differ")
    if sign_flips.empty:
        raise ValueError("no sign-changing regression among the audited contrasts")

    decision = json.loads((source / "decision.json").read_text(encoding="utf-8"))
    if decision.get("verdict") != "NO_MIXED_N7_EXTENSION_INCREMENT":
        raise ValueError("terminal decision drifted from the frozen verdict")

    source_receipt = _original_manifest_receipt(repo_root)
    receipt_payload = {
        "contract": CONTRACT_ID,
        "issue": ISSUE_NUMBER,
        "parent_issue": PARENT_ISSUE,
        "deprecation": {
            "deprecated_field": "matched_ex_largest_lift_cny",
            "status": "DEPRECATED",
            "statement": DEPRECATION_STATEMENT,
            "merged_value_semantics": (
                "delta.sum() - delta[argmax(abs(delta))] on the exact-common "
                "issue set (paired-delta sensitivity), not armwise ex-largest"
            ),
        },
        "added_fields": {
            "armwise_ex_largest_lift_cny": (
                "subject_ex_largest_pnl_cny - reference_ex_largest_pnl_cny; "
                "each arm removes its own largest gross-payout issue"
            ),
            "largest_absolute_paired_delta_sensitivity_cny": (
                "sum(paired_delta) - paired_delta[argmax(abs(paired_delta))]"
            ),
        },
        "source": source_receipt,
        "evidence_cutoff_ts": EVIDENCE_QUERY_CUTOFF_TS,
        "deterministic_regeneration_only": True,
    }
    decision_receipt_payload = {
        "contract": CONTRACT_ID,
        "verdict_unchanged": str(decision["verdict"]),
        "strategy_promoted_unchanged": False,
        "prospective_authorized_unchanged": False,
        "preserved_issues": [int(x) for x in decision.get("preserved_issues", [])],
        "deprecated_field_never_decision_driving": (
            "the merged `matched_ex_largest_lift_cny` appears only in the "
            "descriptive matched-contrasts table of the frozen pipeline; "
            "the terminal decision gates used native-denominator "
            "`ex_largest_pnl_cny` and `moving_block_p05_lift_cny` only"
        ),
        "original_decision_file_sha256": sha256_file(source / "decision.json"),
    }

    # --- 1-2. stage + publish machine artifacts ----------------------------
    machine_csv_text = corrected.to_csv(index=False)
    frame_csv_text = paired_frame.to_csv(index=False)
    counters_csv_text = counterexamples.to_csv(index=False)

    import tempfile

    with tempfile.TemporaryDirectory(prefix="bj399_addendum_") as tmp:
        stage = Path(tmp)
        atomic_write_text(stage / "matched_contrasts_corrected.csv", machine_csv_text)
        atomic_write_text(stage / "paired_delta_frame.csv", frame_csv_text)
        atomic_write_text(stage / "semantic_counterexamples.csv", counters_csv_text)
        atomic_write_json(
            stage / "moving_block_metadata.json",
            _moving_block_metadata(frozen_contrasts),
        )
        atomic_write_json(stage / "ADDENDUM_RECEIPT.json", receipt_payload)
        atomic_write_json(
            stage / "DECISION_RECEIPT.json",
            decision_receipt_payload,
        )
        _atomic_replace_dir(stage, target)

    # --- 3. author the corrected report ------------------------------------
    _author_report(
        deliverables_root / REPORT_PATH,
        source_receipt=source_receipt,
        machine_csv_text=machine_csv_text,
        decision=decision,
        corrected=corrected,
        counters=counterexamples,
        moving_block=_moving_block_metadata(frozen_contrasts),
        deprecation_statement=DEPRECATION_STATEMENT,
    )

    # --- 4. author + execute the addendum notebook -------------------------
    _author_and_execute_notebook(
        deliverables_root / NOTEBOOK_PATH,
        repo_root=repo_root,
        addendum_pkg=target.relative_to(repo_root) if target.is_relative_to(repo_root) else target,
        source_package=SOURCE_PACKAGE,
    )

    # --- 5. manifest --------------------------------------------------------
    manifest = {
        "contract": CONTRACT_ID,
        "source_binding": source_receipt,
        "files": {},
        "deliverables": {},
        "implementation": implementation_closure(
            repo_root,
            ("src.n7_mixed_full_history.closeout",),
            distributions=("numpy", "pandas", "nbformat", "nbclient"),
        ),
    }
    for relative in PACKAGE_FILES:
        path = target / relative
        if not path.is_file():
            raise ValueError(f"addendum artifact missing {relative}")
        manifest["files"][relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
    for relative in (
        REPORT_PATH,
        NOTEBOOK_PATH,
        VERIFIER_PATH,
        BUILDER_PATH,
        TEST_PATH,
    ):
        path = deliverables_root / relative
        if not path.is_file():
            # Static authored deliverables (scripts/tests) live in the repo;
            # only report/notebook are regenerated into deliverables_root.
            path = repo_root / relative
        if not path.is_file():
            raise ValueError(f"addendum deliverable missing {relative}")
        manifest["deliverables"][relative] = sha256_file(path)
    atomic_write_json(target / "MANIFEST.json", manifest)

    return {
        "contract": CONTRACT_ID,
        "output": str(target),
        "files": list(PACKAGE_FILES),
        "rows": int(len(corrected)),
        "counterexamples": int(counterexamples["differ"].sum()),
        "sign_changing": int(counterexamples["sign_change"].sum()),
    }


# ---------------------------------------------------------------------------
# Report + notebook authoring (deterministic text)
# ---------------------------------------------------------------------------

def _author_report(
    path: Path,
    *,
    source_receipt: dict[str, Any],
    machine_csv_text: str,
    decision: dict[str, Any],
    corrected: pd.DataFrame,
    counters: pd.DataFrame,
    moving_block: dict[str, Any],
    deprecation_statement: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    humans = []
    for row in corrected.sort_values(["scope", "contrast"]).itertuples(index=False):
        humans.append(
            "| {scope} | {subj} | {ref} | {issues} | {armwise:.6f} | "
            "{sens:.6f} | {matchn:.6f} |".format(
                scope=row.scope,
                subj=row.subject_schedule,
                ref=row.reference_schedule,
                issues=int(row.issues),
                armwise=float(row.armwise_ex_largest_lift_cny),
                sens=float(row.largest_absolute_paired_delta_sensitivity_cny),
                matchn=float(row.matched_lift_cny),
            )
        )
    counter_examples = counters[counters["differ"]].sort_values(["scope", "contrast"])
    sign_rows = []
    for row in counter_examples.itertuples(index=False):
        sign_rows.append(
            "| {scope} | {contrast} | {armwise:+.3f} | {sens:+.3f} | {sign} |".format(
                scope=row.scope,
                contrast=row.contrast,
                armwise=float(row.armwise_ex_largest_lift_cny),
                sens=float(row.largest_absolute_paired_delta_sensitivity_cny),
                sign="YES" if row.sign_change else "no",
            )
        )
    sections: list[str] = [
        "# Issue #399 — Research Addendum: correct #394 armwise ex-largest and bootstrap metadata",
        "",
        "Contract: `BJ-UNIFIED-N7-MIXED-CLOSEOUT-001/v1`  ·  Parent: #394 · "
        "Frozen source: PR #398 merge `5457afbff6582b9f204e176e4f4a7e2943977914`",
        "",
        "## Scope",
        "",
        "This is a narrow post-merge correction/addendum. It does NOT change "
        "primitive ticket construction, support, frozen strategies, settlements, "
        "the complete 2025 denominator, issue calendars, capital flows, or the "
        "terminal decision `NO_MIXED_N7_EXTENSION_INCREMENT` "
        "(**decision invariance**). It repairs the durable evidence interface by "
        "publishing two semantically distinct tail statistics that the merged "
        "#394 package conflated under one label.",
        "",
        "## Deprecation",
        "",
        f"> **{deprecation_statement}**",
        "",
        "The merged `matched_ex_largest_lift_cny` is left byte-unchanged inside "
        "the frozen #394 package (`results/n7_mixed_full_history/`, verified by "
        "the addendum verifier E02). Consumers of the durable evidence interface "
        "must read the corrected table below.",
        "",
        "## Corrected matched contrasts (machine table)",
        "",
        "| scope | subject | reference | issues | armwise_ex_largest_lift_cny | largest_absolute_paired_delta_sensitivity_cny | matched_lift_cny |",
        "|---|---|---|---|---|---|---|",
        *humans,
        "",
        f"{REPORT_MACHINE_TABLE_MARKER}",
        "",
        "```csv",
        machine_csv_text.rstrip("\n"),
        "```",
        "",
        "## Semantic distinction with counterexamples",
        "",
        "The two statistics are computed by independent code paths and are NOT "
        "interchangeable. Across the audited #394 contrasts they differ in "
        f"{int(counter_examples['differ'].sum())} of 9 rows and flip sign in "
        f"{int(counter_examples['sign_change'].sum())} of them, including:",
        "",
        "- `PRE_2025 vs_C1E3`: armwise `+13,958.86` vs sensitivity `-24,030.69` (sign flip);",
        "- `EXTENSION_2025_2026 vs_R3`: armwise `+7,904.85` vs sensitivity `-5,624.92` (sign flip);",
        "- `ALL vs_C1E3`: armwise `+10,324.69` vs sensitivity `-27,664.86` (sign flip).",
        "",
        "| scope | contrast | armwise_ex_largest_lift_cny | largest_absolute_paired_delta_sensitivity_cny | sign_change |",
        "|---|---|---|---|---|",
        *sign_rows,
        "",
        "## Moving-block bootstrap metadata (scale disambiguation)",
        "",
        f"- estimand: `{moving_block['estimand']}`",
        f"- unit: `{moving_block['unit']}` (the p05 is PER-ISSUE, never total lift)",
        f"- block length: `{moving_block['block_length']}` issues",
        f"- draw count: `{moving_block['draw_count']}`",
        f"- seed: `{moving_block['seed']}`",
        f"- scheme: {moving_block['semantics']}",
        "",
        "```json",
        json.dumps(moving_block, indent=2, sort_keys=True, ensure_ascii=False),
        "```",
        "",
        "## Decision invariance",
        "",
        f"- Terminal verdict remains `{decision['verdict']}`.",
        f"- `strategy_promoted = {bool(decision.get('strategy_promoted'))}`; "
        f"`promotion_unlock_210 = {bool(decision.get('promotion_unlock_210'))}`; "
        f"`prospective_authorized = {bool(decision.get('prospective_authorized'))}`; "
        f"preserved issues: {[int(x) for x in decision.get('preserved_issues', [])]}.",
        "- The deprecated `matched_ex_largest_lift_cny` appears only in the "
        "descriptive matched-contrasts table of the frozen pipeline; the terminal "
        "decision gates used native-denominator `ex_largest_pnl_cny` and "
        "`moving_block_p05_lift_cny` only (source-scanned by the verifier, E07).",
        "- Primitive settlement/accounting hashes (`bundles.parquet`, "
        "`extension_settlement.parquet`, `issue_ledger.csv`, `decision.json`) are "
        "re-hashed by the verifier against the unchanged original manifest (E07).",
        "",
        "## Reproduction",
        "",
        "```bash",
        "PYTHONPATH=. python scripts/build_n7_mixed_closeout_addendum.py",
        "PYTHONPATH=. python scripts/verify_n7_mixed_closeout_addendum.py",
        "```",
        "",
    ]
    path.write_text("\n".join(sections) + "\n", encoding="utf-8")


def _author_and_execute_notebook(
    path: Path,
    *,
    repo_root: Path,
    addendum_pkg: Path | str,
    source_package: str,
) -> None:
    import nbformat
    from nbclient import NotebookClient

    addendum_expr = repr(str(addendum_pkg))
    path.parent.mkdir(parents=True, exist_ok=True)
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell(
                "# Issue #399 — #394 close-out addendum\n\n"
                "Contract: `BJ-UNIFIED-N7-MIXED-CLOSEOUT-001/v1`. Terminal decision "
                "is unchanged: `NO_MIXED_N7_EXTENSION_INCREMENT`. This notebook "
                "regenerates the two corrected statistics from the frozen #394 "
                "artifacts and validates the committed addendum package (E06/E08)."
            ),
            nbformat.v4.new_code_cell(
                "from pathlib import Path\n"
                "import json\n"
                "import numpy as np\n"
                "import pandas as pd\n"
                "from src.n7_mixed_full_history import closeout as C\n"
                "from src.n7_mixed_full_history.pipeline import _matched_contrasts_board, _paired_frame_for_schedule\n"
                "REPO=Path.cwd()\n"
                f"SRC=REPO/{source_package!r}\n"
                f"ADD=REPO/{addendum_expr}\n"
                "bundles=pd.read_parquet(SRC/'bundles.parquet')\n"
                "frozen=pd.read_csv(SRC/'matched_contrasts.csv')\n"
                "C.assert_frozen_board_parity(bundles, frozen)\n"
                "print('frozen board parity OK')\n"
                "decision=json.loads((SRC/'decision.json').read_text())\n"
                "decision"
            ),
            nbformat.v4.new_code_cell(
                "corrected, paired_frame, counters = C.corrected_contrasts(bundles)\n"
                "assert int(counters['differ'].sum()) >= 1\n"
                "assert int(counters['sign_change'].sum()) >= 1\n"
                "corrected"
            ),
            nbformat.v4.new_code_cell("counters"),
            nbformat.v4.new_code_cell(
                "assert (ADD/'matched_contrasts_corrected.csv').is_file()\n"
                "committed = pd.read_csv(ADD/'matched_contrasts_corrected.csv')\n"
                "keys = ['scope','contrast']\n"
                "cmp = committed.merge(corrected, on=keys, suffixes=('_committed','_recomputed'), how='outer')\n"
                "fcols = [c for c in cmp.columns if not c.endswith(('_committed','_recomputed')) or c in keys]\n"
                "numcols = [c for c in ['subject_pnl_cny','reference_pnl_cny','matched_lift_cny','subject_ex_largest_pnl_cny','reference_ex_largest_pnl_cny','armwise_ex_largest_lift_cny','largest_abs_paired_delta_cny','largest_abs_paired_delta_signed_cny','largest_absolute_paired_delta_sensitivity_cny']]\n"
                "for c in numcols:\n"
                "    a = cmp[c+'_committed'].to_numpy(float)\n"
                "    b = cmp[c+'_recomputed'].to_numpy(float)\n"
                "    assert np.allclose(a, b, rtol=1e-9, atol=1e-9), c\n"
                "strcols = ['subject_largest_payout_issue','reference_largest_payout_issue','largest_abs_paired_delta_issue']\n"
                "for c in strcols:\n"
                "    assert (cmp[c+'_committed'].astype(str) == cmp[c+'_recomputed'].astype(str)).all(), c\n"
                "assert (cmp['subject_schedule_committed'].astype(str) == 'MIXED_50_50').all()\n"
                "assert cmp['reference_schedule_committed'].isin(['R3_STANDALONE','C1E3_STANDALONE','R0_COMPARATOR']).all()\n"
                "receipt=json.loads((ADD/'ADDENDUM_RECEIPT.json').read_text())\n"
                "assert receipt['source']['source_merge_sha'] == C.SOURCE_MERGE_SHA\n"
                "print('committed addendum package parity OK')\n"
                "receipt['deprecation']"
            ),
            nbformat.v4.new_code_cell(
                "mb=json.loads((ADD/'moving_block_metadata.json').read_text())\n"
                "assert mb['estimand'] == 'paired_mean_cny_per_issue'\n"
                "assert mb['unit'] == 'CNY_PER_ISSUE'\n"
                "assert mb['block_length'] == 10 and mb['draw_count'] == 5000 and mb['seed'] == 394001\n"
                "mb"
            ),
            nbformat.v4.new_code_cell(
                "dr=json.loads((ADD/'DECISION_RECEIPT.json').read_text())\n"
                "assert dr['verdict_unchanged'] == 'NO_MIXED_N7_EXTENSION_INCREMENT'\n"
                "print('decision invariance OK')\n"
                "dr"
            ),
            nbformat.v4.new_markdown_cell(
                "All values regenerated deterministically from the frozen #394 "
                "artifacts. The merged `matched_ex_largest_lift_cny` remains "
                "byte-unchanged in the frozen package and is DEPRECATED as an "
                "armwise ex-largest field."
            ),
        ]
    )
    nbformat.write(notebook, path)
    NotebookClient(
        notebook,
        timeout=300,
        kernel_name="python3",
        resources={"metadata": {"path": str(repo_root)}},
    ).execute()
    nbformat.write(notebook, path)


def _atomic_replace_dir(stage: Path, target: Path) -> None:
    import shutil

    backup = target.with_name(target.name + ".bak")
    if backup.exists():
        shutil.rmtree(backup)
    if target.exists():
        target.rename(backup)
    try:
        shutil.copytree(stage, target)
    except Exception:
        if backup.exists():
            backup.rename(target)
        raise
    finally:
        if backup.exists():
            shutil.rmtree(backup)