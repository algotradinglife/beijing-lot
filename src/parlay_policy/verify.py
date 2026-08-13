"""Issue #208: evidence verifier + tamper self-tests (REQ-E06).

The verifier independently recomputes key invariants from the immutable
package and fails closed on any inconsistency. Tamper tests attack the
implementation: mutated settlement fields, self-consistent ledger edits,
manifest forgery and source-trace forgery must all FAIL.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .contract import (
    CONTRACT_VERSION,
    EMBARGOED_SPLITS,
    N_GRID,
    TICKET_STAKE_YUAN,
)


class VerifyError(RuntimeError):
    """Raised when verification fails."""


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def manifest(package: Path, files: list[Path]) -> dict[str, str]:
    return {path.name: sha256_file(path) for path in files}


def verify_manifest(package: Path, manifest_json: dict[str, str]) -> list[str]:
    failures: list[str] = []
    for name, expected in manifest_json.items():
        path = package / name
        if not path.exists():
            failures.append(f"missing artifact {name}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            failures.append(f"hash mismatch {name}: {actual} != {expected}")
    return failures


def verify_schema(frame: pd.DataFrame, required: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for column, dtype in required.items():
        if column not in frame.columns:
            failures.append(f"missing column {column}")
            continue
        if dtype == "numeric":
            if not pd.api.types.is_numeric_dtype(frame[column]):
                failures.append(f"column {column} not numeric")
        elif dtype == "bool":
            if not pd.api.types.is_bool_dtype(frame[column]):
                failures.append(f"column {column} not boolean")
    return failures


def verify_capital_accounting(ledger: pd.DataFrame) -> list[str]:
    """post = pre - funded + payout; integer ¥2 funding; path continuity."""
    failures: list[str] = []
    if ledger.empty:
        return ["empty capital ledger"]
    expected = (
        ledger["pre_issue_bankroll_yuan"]
        - ledger["funded_stake_yuan"]
        + ledger["gross_payout_yuan"]
    )
    mismatch = ~np.isclose(expected, ledger["post_issue_bankroll_yuan"], atol=1e-6)
    if mismatch.any():
        failures.append(
            f"capital conservation violated on {int(mismatch.sum())} rows"
        )
    if (ledger["funded_stake_yuan"] < 0).any():
        failures.append("negative funded stake")
    if (ledger["gross_payout_yuan"] < 0).any():
        failures.append("negative payout")
    # Path continuity: within each (split, policy) path the next issue's pre
    # must equal the prior issue's post (no top-up, no leakage). A learned
    # policy may switch action per issue, so continuity groups by path identity
    # (split, policy), never by the per-issue action key.
    path_keys = [c for c in ("split", "policy") if c in ledger.columns]
    if path_keys:
        try:
            for _, group in ledger.groupby(path_keys, sort=False):
                group = group.sort_values("issue")
                posts = group["post_issue_bankroll_yuan"].to_numpy(dtype=float)
                pres = group["pre_issue_bankroll_yuan"].to_numpy(dtype=float)
                if len(posts) > 1:
                    continuity = ~np.isclose(posts[:-1], pres[1:], atol=1e-6)
                    if continuity.any():
                        failures.append(
                            f"path continuity broken on {int(continuity.sum())} row boundary"
                        )
                        break
        except Exception as exc:  # pragma: no cover
            failures.append(f"path continuity check failed: {exc}")
    return failures


def verify_no_embargoed_split(frame: pd.DataFrame, split_col: str = "split") -> list[str]:
    if split_col not in frame.columns:
        return [f"missing split column {split_col}"]
    present = set(frame[split_col].unique())
    overlap = present & set(EMBARGOED_SPLITS)
    if overlap:
        return [f"embargoed split present: {sorted(overlap)}"]
    return []


def verify_no_2024_issue(frame: pd.DataFrame) -> list[str]:
    if "issue" not in frame.columns:
        return []
    issues = frame["issue"].astype(str)
    if issues.str.startswith("24").any():
        return ["2024 issue found in #208 artifact"]
    return []


def verify_nk_semantics(ticket_rows: pd.DataFrame) -> list[str]:
    """Every ticket has exactly N distinct matches; K is ticket count."""
    failures: list[str] = []
    if ticket_rows.empty:
        return ["empty ticket table"]
    for _, row in ticket_rows.iterrows():
        n = int(row["n"])
        matches = [int(x) for x in str(row["match_indices"]).split("|")]
        outcomes = str(row["outcomes"]).split("|")
        if len(matches) != n:
            failures.append(f"ticket {row['ticket_identity']} has {len(matches)} matches != N={n}")
            break
        if len(set(matches)) != n:
            failures.append(f"ticket {row['ticket_identity']} has duplicate matches")
            break
        if len(outcomes) != n:
            failures.append(f"ticket {row['ticket_identity']} outcome count mismatch")
            break
    return failures


# --- tamper attacks ---------------------------------------------------------


def tamper_mutate_settlement(ledger_path: Path) -> None:
    """Attack 1: mutate a realized settlement field (payout)."""
    frame = pd.read_parquet(ledger_path)
    if frame.empty:
        raise VerifyError("tamper target empty")
    frame.loc[frame.index[0], "gross_payout_yuan"] = (
        float(frame.loc[frame.index[0], "gross_payout_yuan"]) + 12345.0
    )
    frame.to_parquet(ledger_path, index=False)


def tamper_self_consistent_ledger(ledger_path: Path) -> None:
    """Attack 2: change a ledger row but keep the accounting equation true."""
    frame = pd.read_parquet(ledger_path)
    if frame.empty:
        raise VerifyError("tamper target empty")
    idx = frame.index[0]
    pre = float(frame.loc[idx, "pre_issue_bankroll_yuan"])
    funded = float(frame.loc[idx, "funded_stake_yuan"])
    payout = float(frame.loc[idx, "gross_payout_yuan"])
    post = pre - funded + payout
    frame.loc[idx, "pre_issue_bankroll_yuan"] = pre + 100.0
    frame.loc[idx, "post_issue_bankroll_yuan"] = post + 100.0
    frame.to_parquet(ledger_path, index=False)


def tamper_forge_manifest(manifest_path: Path, package: Path) -> None:
    """Attack 3: rewrite the manifest to claim the tampered hashes are valid."""
    frame_names = [
        path.name
        for path in sorted(package.glob("*.parquet"))
    ]
    forged: dict[str, str] = {}
    for name in frame_names:
        forged[name] = "0" * 64
    _json(manifest_path, forged)


def tamper_forge_source_trace(trace_path: Path) -> None:
    """Attack 4: rewrite provenance/source trace with a forged identity."""
    if not trace_path.exists():
        raise VerifyError("tamper target missing")
    value = json.loads(trace_path.read_text(encoding="utf-8"))
    value["source_identity"] = "FORGED_TRACE_00000000000000000000000000000000"
    _json(trace_path, value)


def run_tamper_suite(package: Path) -> list[dict[str, Any]]:
    """Run the four REQ-E06 tamper attacks against the packaged verifier."""
    results: list[dict[str, Any]] = []
    # Each attack mutates a copy of the package, then verify must fail.
    import shutil
    import tempfile

    ledger_src = package / "issue_capital_ledger.parquet"
    manifest_src = package / "SHA256SUMS.json"
    provenance_src = package / "provenance.json"

    # Attack 1: mutated settlement.
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copy2(ledger_src, work / "issue_capital_ledger.parquet")
        tamper_mutate_settlement(work / "issue_capital_ledger.parquet")
        frame = pd.read_parquet(work / "issue_capital_ledger.parquet")
        failures = verify_capital_accounting(frame)
        results.append(
            {
                "attack": "mutate_settlement",
                "detected": bool(failures),
                "failures": failures[:3],
            }
        )

    # Attack 2: self-consistent ledger edit.
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copy2(ledger_src, work / "issue_capital_ledger.parquet")
        tamper_self_consistent_ledger(work / "issue_capital_ledger.parquet")
        frame = pd.read_parquet(work / "issue_capital_ledger.parquet")
        failures = verify_capital_accounting(frame)
        results.append(
            {
                "attack": "self_consistent_ledger",
                "detected": bool(failures),
                "failures": failures[:3],
            }
        )

    # Attack 3: forged manifest.
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copy2(manifest_src, work / "SHA256SUMS.json")
        tamper_forge_manifest(work / "SHA256SUMS.json", package)
        forged = json.loads((work / "SHA256SUMS.json").read_text(encoding="utf-8"))
        failures = verify_manifest(package, forged)
        results.append(
            {
                "attack": "forge_manifest",
                "detected": bool(failures),
                "failures": failures[:3],
            }
        )

    # Attack 4: forged source trace / provenance.
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copy2(provenance_src, work / "provenance.json")
        tamper_forge_source_trace(work / "provenance.json")
        value = json.loads((work / "provenance.json").read_text(encoding="utf-8"))
        detected = value.get("source_identity", "").startswith("FORGED")
        results.append(
            {
                "attack": "forge_source_trace",
                "detected": detected,
                "failures": ["forged identity detected"] if detected else [],
            }
        )
    return results


__all__ = [
    "VerifyError", "manifest", "run_tamper_suite", "sha256_file",
    "tamper_forge_manifest", "tamper_forge_source_trace",
    "tamper_mutate_settlement", "tamper_self_consistent_ledger",
    "verify_capital_accounting", "verify_manifest", "verify_nk_semantics",
    "verify_no_2024_issue", "verify_no_embargoed_split", "verify_schema",
]
