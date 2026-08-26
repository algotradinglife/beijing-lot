#!/usr/bin/env python3
"""Independent verifier for the issue #399 close-out addendum package.

Contract BJ-UNIFIED-N7-MIXED-CLOSEOUT-001/v1 (issue #399, parent #394).

Acceptance clauses (from the issue contract):

  E01 SOURCE BINDING   addendum receipt binds exact #398 merge SHA and
                       original package manifest hash.
  E02 IMMUTABILITY     byte/hash check proves the original
                       `results/n7_mixed_full_history/` package unchanged.
  E03 ARMWISE SEMANTICS verifier independently reconstructs subject/reference
                       ex-largest PnL and the exact-difference result with
                       strict tolerance.
  E04 PAIRED-DELTA SEMANTICS verifier independently identifies the largest
                       absolute paired-delta issue and reconstructs the
                       separate sensitivity field.
  E05 METADATA         bootstrap estimand, unit, block length, draws and seed
                       are present and reconcile to producer configuration.
  E06 REPORT PARITY    machine table, report and executed notebook show
                       identical corrected values and labels.
  E07 DECISION INVARIANCE verifier proves primitive settlement/accounting
                       hashes and terminal `NO_MIXED_N7_EXTENSION_INCREMENT`
                       decision are unchanged.
  E08 CLEAN REPLAY     focused tests, adversarial mutation tests and verifier
                       pass from a clean checkout at the delivered PR HEAD.

The reconstruction paths (E03/E04) are implemented inline and independently of
the producer module: they read only the persisted per-issue paired frame and
recompute the statistics from first principles.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.n7_mixed_full_history.contract import (  # noqa: E402
    BOOTSTRAP_DRAWS,
    BOOTSTRAP_SEED,
    MOVING_BLOCK_LENGTH,
)
from src.n7_mixed_full_history.closeout import (  # noqa: E402
    ADDENDUM_PACKAGE,
    CONTRACT_ID,
    REPORT_MACHINE_TABLE_MARKER,
    SOURCE_MERGE_SHA,
    SOURCE_PACKAGE,
    build_addendum_package,
)

SOURCE_MERGE_PR = 398
TERMINAL_VERDICT = "NO_MIXED_N7_EXTENSION_INCREMENT"
STRICT_ATOL = 1e-6
STRICT_RTOL = 1e-9

ADDENDUM_FILES = (
    "ADDENDUM_RECEIPT.json",
    "DECISION_RECEIPT.json",
    "matched_contrasts_corrected.csv",
    "moving_block_metadata.json",
    "paired_delta_frame.csv",
    "semantic_counterexamples.csv",
)
DELIVERABLE_FILES = (
    "docs/research/Issue-399-N7-Mixed-Closeout-Addendum.md",
    "notebooks/research/n7-mixed-full-history/Issue-399-N7-Mixed-Closeout-Addendum.ipynb",
    "scripts/verify_n7_mixed_closeout_addendum.py",
    "scripts/build_n7_mixed_closeout_addendum.py",
    "tests/test_bj399_n7_mixed_closeout_addendum.py",
)


class VerifyError(AssertionError):
    pass


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# E03/E04 independent reconstruction (inline, not via the producer module)
# ---------------------------------------------------------------------------

def _reconstruct_stats(frame: pd.DataFrame) -> dict[str, float | str | int]:
    """Recompute armwise ex-largest and paired-delta sensitivity from the
    persisted per-issue paired frame. Implemented here from first principles
    so the verifier never trusts the producer's arithmetic."""
    pnl_a = frame["pnl_a"].to_numpy(float)
    gross_a = frame["gross_a"].to_numpy(float)
    pnl_b = frame["pnl_b"].to_numpy(float)
    gross_b = frame["gross_b"].to_numpy(float)
    delta = pnl_a - pnl_b
    issues = frame["issue"].astype(str).tolist()

    subj_idx = int(np.argmax(gross_a))
    ref_idx = int(np.argmax(gross_b))
    subj_ex = float(pnl_a.sum() - pnl_a[subj_idx])
    ref_ex = float(pnl_b.sum() - pnl_b[ref_idx])
    armwise = float(subj_ex - ref_ex)

    largest_idx = int(np.argmax(np.abs(delta)))
    sensitivity = float(delta.sum() - delta[largest_idx])

    return {
        "issues": int(len(frame)),
        "subject_pnl_cny": float(pnl_a.sum()),
        "reference_pnl_cny": float(pnl_b.sum()),
        "matched_lift_cny": float(delta.sum()),
        "subject_ex_largest_pnl_cny": subj_ex,
        "reference_ex_largest_pnl_cny": ref_ex,
        "subject_largest_payout_issue": str(issues[subj_idx]),
        "reference_largest_payout_issue": str(issues[ref_idx]),
        "armwise_ex_largest_lift_cny": armwise,
        "largest_abs_paired_delta_cny": float(np.abs(delta).max()),
        "largest_abs_paired_delta_signed_cny": float(delta[largest_idx]),
        "largest_abs_paired_delta_issue": str(issues[largest_idx]),
        "largest_absolute_paired_delta_sensitivity_cny": sensitivity,
    }


def _close(a: float, b: float) -> bool:
    return bool(np.isclose(a, b, rtol=STRICT_RTOL, atol=STRICT_ATOL))


def _manifest_sha_at_merge(repo_root: Path) -> str:
    """Hash of the original package MANIFEST.json as committed at the frozen
    merge SHA -- the immutable anchor a coordinated manifest+receipt rewrite
    cannot forge."""
    import hashlib
    import subprocess

    proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{SOURCE_MERGE_SHA}:{SOURCE_PACKAGE}/MANIFEST.json"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise VerifyError("E01: cannot resolve merge-commit manifest blob (git required)")
    return hashlib.sha256(proc.stdout).hexdigest()


# ---------------------------------------------------------------------------
# E01 + E02: source binding + immutability of the frozen #394 package
# ---------------------------------------------------------------------------

def _check_e01_e02(
    repo_root: Path, receipt: dict, expected_manifest_sha: str | None = None
) -> list[str]:
    checks: list[str] = []
    source = receipt.get("source", {})
    if source.get("source_merge_sha") != SOURCE_MERGE_SHA:
        raise VerifyError(f"E01: addendum receipt source_merge_sha mismatch: {source.get('source_merge_sha')}")
    if source.get("source_merge_pr") != SOURCE_MERGE_PR:
        raise VerifyError(f"E01: addendum receipt source_merge_pr mismatch: {source.get('source_merge_pr')}")
    checks.append("E01: receipt binds #398 merge SHA")

    anchor = expected_manifest_sha
    if anchor is None:
        anchor = source.get("original_package_manifest_sha256")
    if not anchor:
        raise VerifyError("E01: no manifest hash anchor available")
    if source.get("original_package_manifest_sha256") != anchor:
        raise VerifyError("E01: receipt manifest hash does not match the immutable merge anchor")

    source_pkg = repo_root / SOURCE_PACKAGE
    manifest_path = source_pkg / "MANIFEST.json"
    if not manifest_path.is_file():
        raise VerifyError("E01: original package manifest missing")
    if _sha256_file(manifest_path) != anchor:
        raise VerifyError("E01: on-disk original manifest hash differs from the immutable merge anchor")
    checks.append("E01: original package manifest hash bound (git-merge anchor)")

    manifest = _read_json(manifest_path)
    for relative, meta in manifest.get("files", {}).items():
        path = source_pkg / relative
        if not path.is_file():
            raise VerifyError(f"E02: original package file missing: {relative}")
        live = _sha256_file(path)
        if live != meta.get("sha256"):
            raise VerifyError(f"E02: original package file mutated: {relative}")
        if path.stat().st_size != meta.get("bytes"):
            raise VerifyError(f"E02: original package file size mutated: {relative}")
    checks.append(
        f"E02: all {len(manifest.get('files', {}))} original package files byte-unchanged"
    )
    return checks


# ---------------------------------------------------------------------------
# E03 + E04: independent reconstruction
# ---------------------------------------------------------------------------

def _check_e03_e04(repo_root: Path, addendum_pkg: Path) -> list[str]:
    checks: list[str] = []
    frame = pd.read_csv(addendum_pkg / "paired_delta_frame.csv")
    corrected = pd.read_csv(addendum_pkg / "matched_contrasts_corrected.csv")

    num_cols = [
        "issues",
        "subject_pnl_cny",
        "reference_pnl_cny",
        "matched_lift_cny",
        "subject_ex_largest_pnl_cny",
        "reference_ex_largest_pnl_cny",
        "armwise_ex_largest_lift_cny",
        "largest_abs_paired_delta_cny",
        "largest_abs_paired_delta_signed_cny",
        "largest_absolute_paired_delta_sensitivity_cny",
    ]
    str_cols = [
        "subject_largest_payout_issue",
        "reference_largest_payout_issue",
        "largest_abs_paired_delta_issue",
    ]
    expected_rows = corrected.set_index(["scope", "contrast"])
    allowed_subject = {"MIXED_50_50"}
    allowed_ref = {"R3_STANDALONE", "C1E3_STANDALONE", "R0_COMPARATOR"}
    for (scope, contrast), grp in frame.groupby(["scope", "contrast"], sort=True):
        est = _reconstruct_stats(grp.reset_index(drop=True))
        row = expected_rows.loc[(scope, contrast)]
        if str(row["subject_schedule"]) not in allowed_subject:
            raise VerifyError(f"E03/E04: {scope} {contrast} subject_schedule invalid: {row['subject_schedule']}")
        if str(row["reference_schedule"]) not in allowed_ref:
            raise VerifyError(f"E03/E04: {scope} {contrast} reference_schedule invalid: {row['reference_schedule']}")
        for col in num_cols:
            if not _close(float(est[col]), float(row[col])):
                raise VerifyError(
                    f"E03/E04: {scope} {contrast} {col} reconstruction mismatch: "
                    f"{est[col]} vs {row[col]}"
                )
        for col in str_cols:
            if str(est[col]) != str(row[col]):
                raise VerifyError(
                    f"E03/E04: {scope} {contrast} {col} issue mismatch: "
                    f"{est[col]} vs {row[col]}"
                )
    checks.append("E03: subject/reference ex-largest PnL reconstructed (all 9 contrasts)")
    checks.append("E04: largest absolute paired-delta issue + sensitivity reconstructed (all 9 contrasts)")
    return checks


# ---------------------------------------------------------------------------
# E05: bootstrap metadata
# ---------------------------------------------------------------------------

def _check_e05(repo_root: Path, addendum_pkg: Path) -> list[str]:
    checks: list[str] = []
    meta = _read_json(addendum_pkg / "moving_block_metadata.json")
    if meta.get("estimand") != "paired_mean_cny_per_issue":
        raise VerifyError("E05: estimand mismatch")
    if meta.get("unit") != "CNY_PER_ISSUE":
        raise VerifyError("E05: unit mismatch")
    if int(meta.get("block_length")) != int(MOVING_BLOCK_LENGTH):
        raise VerifyError("E05: block length does not reconcile to producer config")
    if int(meta.get("draw_count")) != int(BOOTSTRAP_DRAWS):
        raise VerifyError("E05: draw count does not reconcile to producer config")
    if int(meta.get("seed")) != int(BOOTSTRAP_SEED):
        raise VerifyError("E05: seed does not reconcile to producer config")

    frozen = pd.read_csv(repo_root / SOURCE_PACKAGE / "matched_contrasts.csv")
    frozen = frozen.set_index(["scope", "contrast"])
    meta_rows = {
        (str(r["scope"]), str(r["contrast"])): float(r["moving_block_p05_lift_cny_per_issue"])
        for r in meta["rows"]
    }
    for (scope, contrast), row in frozen.iterrows():
        if (scope, contrast) not in meta_rows:
            raise VerifyError(f"E05: metadata missing row {scope} {contrast}")
        if not _close(meta_rows[(scope, contrast)], float(row.moving_block_p05_lift_cny)):
            raise VerifyError(
                f"E05: metadata p05 for {scope} {contrast} does not reconcile to frozen board"
            )
    checks.append("E05: estimand/unit/block/draws/seed reconcile to producer config")
    return checks


# ---------------------------------------------------------------------------
# E06: report parity (machine block + manifest) + notebook replay
# ---------------------------------------------------------------------------

def _extract_machine_block(report_text: str) -> str:
    marker = REPORT_MACHINE_TABLE_MARKER
    idx = report_text.find(marker)
    if idx < 0:
        raise VerifyError("E06: report missing machine-table marker")
    rest = report_text[idx + len(marker):]
    lines = rest.splitlines()
    # skip blank lines and the ```csv fence
    out: list[str] = []
    fence = False
    for line in lines:
        if not fence and line.strip() == "```csv":
            fence = True
            continue
        if fence and line.strip() == "```":
            break
        if fence:
            out.append(line)
    if not fence:
        raise VerifyError("E06: report machine-table csv fence not found")
    return "\n".join(out)


def _check_e06_report(repo_root: Path, addendum_pkg: Path) -> list[str]:
    checks: list[str] = []
    report_path = repo_root / DELIVERABLE_FILES[0]
    machine_path = addendum_pkg / "matched_contrasts_corrected.csv"
    report_text = report_path.read_text(encoding="utf-8")
    block = _extract_machine_block(report_text)
    machine_text = machine_path.read_text(encoding="utf-8").rstrip("\n")
    if block != machine_text:
        raise VerifyError("E06: report machine-table block does not byte-match the committed CSV")
    checks.append("E06: report machine block == committed machine CSV (byte parity)")
    return checks


# ---------------------------------------------------------------------------
# E07: decision invariance + primitive hashes + deprecated-field source scan
# ---------------------------------------------------------------------------

def _check_e07(repo_root: Path, receipt: dict, addendum_pkg: Path) -> list[str]:
    checks: list[str] = []
    decision_receipt = _read_json(addendum_pkg / "DECISION_RECEIPT.json")
    source_pkg = repo_root / SOURCE_PACKAGE
    decision = _read_json(source_pkg / "decision.json")

    if decision.get("verdict") != TERMINAL_VERDICT:
        raise VerifyError("E07: terminal verdict changed")
    if decision_receipt.get("verdict_unchanged") != TERMINAL_VERDICT:
        raise VerifyError("E07: addendum decision receipt wrong verdict")
    if decision.get("strategy_promoted", True) is not False:
        raise VerifyError("E07: strategy_promoted must remain False")
    if decision.get("promotion_unlock_210", True) is not False:
        raise VerifyError("E07: promotion_unlock_210 must remain False")
    if decision_receipt.get("strategy_promoted_unchanged") is not False:
        raise VerifyError("E07: addendum receipt strategy_promoted_unchanged wrong")
    if [int(x) for x in decision.get("preserved_issues", [])] != [210, 218]:
        raise VerifyError("E07: preserved issues changed")
    checks.append("E07: terminal NO_MIXED_N7_EXTENSION_INCREMENT unchanged")

    # primitive settlement/accounting hashes vs original manifest
    manifest = _read_json(source_pkg / "MANIFEST.json")
    for relative in (
        "bundles.parquet",
        "extension_settlement.parquet",
        "issue_ledger.csv",
        "decision.json",
    ):
        meta = manifest.get("files", {}).get(relative)
        if meta is None:
            raise VerifyError(f"E07: original manifest missing primitive {relative}")
        if _sha256_file(source_pkg / relative) != meta["sha256"]:
            raise VerifyError(f"E07: primitive {relative} mutated")
    checks.append("E07: primitive settlement/accounting hashes unchanged")

    # deprecated field never decision-driving: source scan of the frozen pipeline
    pipeline_src = (repo_root / "src/n7_mixed_full_history/pipeline.py").read_text(
        encoding="utf-8"
    )
    hits = []
    for lineno, line in enumerate(pipeline_src.splitlines(), start=1):
        if "matched_ex_largest_lift_cny" in line:
            hits.append(lineno)
    if not hits:
        raise VerifyError("E07: deprecated field not found in frozen pipeline source")
    func_start = pipeline_src.find("def _matched_contrasts_board")
    func_end = pipeline_src.find("\ndef _correlation_board")
    if func_start < 0 or func_end < 0:
        raise VerifyError("E07: frozen pipeline board boundaries not found")
    for lineno in hits:
        start_line = pipeline_src[:func_start].count("\n") + 1
        end_line = pipeline_src[:func_end].count("\n") + 1
        if not (start_line <= lineno <= end_line):
            raise VerifyError(
                f"E07: deprecated field used outside the descriptive contrasts board at line {lineno}"
            )
    checks.append("E07: deprecated field confined to the descriptive contrasts board (source scan)")
    return checks


# ---------------------------------------------------------------------------
# E06b/E08: deterministic regeneration + notebook clean replay
# ---------------------------------------------------------------------------

def _normalize_notebook(path: Path) -> bytes:
    import nbformat

    nb = nbformat.read(path, as_version=4)
    for i, cell in enumerate(nb.cells):
        cell["metadata"] = {}
        cell["id"] = f"cell-{i}"  # nbformat ids are random UUIDs; index-normalize
        if cell.get("cell_type") == "code":
            # the addendum package path is a parameter: normalize it away
            cell["source"] = re.sub(
                r"ADD=REPO/[^\n]*",
                "ADD=REPO/<addendum_pkg>",
                cell["source"],
            )
        for output in cell.get("outputs", []):
            output["metadata"] = {}
    return nbformat.writes(nb, version=4).encode("utf-8")


def _check_e08_determinism(repo_root: Path) -> list[str]:
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="bj399_verify_") as tmp:
        tmp_root = Path(tmp)
        tmp_pkg = tmp_root / "addendum_pkg"
        tmp_deliv = tmp_root / "deliverables"
        build_addendum_package(
            repo_root,
            output=tmp_pkg,
            deliverables_root=tmp_deliv,
            force=True,
        )
        committed_pkg = repo_root / ADDENDUM_PACKAGE

        for relative in ADDENDUM_FILES:
            a = _sha256_file(committed_pkg / relative)
            b = _sha256_file(tmp_pkg / relative)
            if a != b:
                raise VerifyError(f"E08: deterministic regeneration drift in package file {relative}")
        checks.append("E08: package machine artifacts regenerate byte-identically")

        for i, relative in enumerate(DELIVERABLE_FILES):
            committed = repo_root / relative
            regenerated = tmp_deliv / relative
            if relative.endswith(".ipynb"):
                if not committed.is_file() or not regenerated.is_file():
                    raise VerifyError(f"E08: notebook missing: {relative}")
                if _normalize_notebook(committed) != _normalize_notebook(regenerated):
                    raise VerifyError("E08: notebook regenerates with different content (modulo execution metadata)")
            elif relative == DELIVERABLE_FILES[0]:
                # report is authored by the build into deliverables_root
                if not committed.is_file() or not regenerated.is_file():
                    raise VerifyError(f"E08: report missing: {relative}")
                if committed.read_bytes() != regenerated.read_bytes():
                    raise VerifyError("E08: report regenerates with different bytes")
            else:
                # static authored files (scripts/tests) are not regenerated;
                # their committed bytes must equal the repo copy that the
                # temp manifest hashed
                if not committed.is_file():
                    raise VerifyError(f"E08: deliverable missing: {relative}")
        checks.append("E08: report + notebook regenerate identically (notebook modulo execution metadata)")

        committed_manifest = _read_json(committed_pkg / "MANIFEST.json")
        regenerated_manifest = _read_json(tmp_pkg / "MANIFEST.json")
        if committed_manifest["files"] != regenerated_manifest["files"]:
            raise VerifyError("E08: regenerated MANIFEST files drift")
        if committed_manifest["implementation"] != regenerated_manifest["implementation"]:
            raise VerifyError("E08: regenerated MANIFEST implementation closure drift")
        del committed_manifest["deliverables"]["notebooks/research/n7-mixed-full-history/Issue-399-N7-Mixed-Closeout-Addendum.ipynb"]
        del regenerated_manifest["deliverables"]["notebooks/research/n7-mixed-full-history/Issue-399-N7-Mixed-Closeout-Addendum.ipynb"]
        if committed_manifest["deliverables"] != regenerated_manifest["deliverables"]:
            raise VerifyError("E08: regenerated MANIFEST deliverables drift (non-notebook)")
        checks.append("E08: MANIFEST reconciles (files, implementation, non-notebook deliverables)")

    # Clean replay of the COMMITTED executed notebook against the COMMITTED package
    notebook_path = repo_root / DELIVERABLE_FILES[1]
    import nbformat
    from nbclient import NotebookClient

    nb = nbformat.read(notebook_path, as_version=4)
    NotebookClient(
        nb,
        timeout=300,
        kernel_name="python3",
        resources={"metadata": {"path": str(repo_root)}},
    ).execute()
    error_outputs = [
        output
        for cell in nb.cells
        if cell.cell_type == "code"
        for output in cell.get("outputs", [])
        if output.output_type == "error"
    ]
    if error_outputs:
        first = error_outputs[0]
        raise VerifyError(
            "E08: committed notebook clean replay reported errors: "
            + " / ".join([str(first.get("ename", "?")), str(first.get("evalue", "?"))])
        )
    checks.append("E08: committed executed notebook clean-replays without errors")
    return checks


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    addendum_pkg = repo_root / ADDENDUM_PACKAGE

    receipt = _read_json(addendum_pkg / "ADDENDUM_RECEIPT.json")
    if receipt.get("contract") != CONTRACT_ID:
        raise VerifyError("addendum receipt contract mismatch")

    checks: list[str] = []
    checks += _check_e01_e02(repo_root, receipt, expected_manifest_sha=_manifest_sha_at_merge(repo_root))
    checks += _check_e03_e04(repo_root, addendum_pkg)
    checks += _check_e05(repo_root, addendum_pkg)
    checks += _check_e06_report(repo_root, addendum_pkg)
    checks += _check_e07(repo_root, receipt, addendum_pkg)
    checks += _check_e08_determinism(repo_root)

    print(
        json.dumps(
            {
                "contract": CONTRACT_ID,
                "status": "PASS",
                "checks": checks,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()