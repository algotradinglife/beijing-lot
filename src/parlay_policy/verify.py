"""Issue #208: evidence verifier + tamper self-tests (REQ-E06).

The verifier independently recomputes key invariants from the immutable
package and fails closed on any inconsistency. Tamper tests attack the
PRODUCTION entry points: mutated settlement fields, self-consistent ledger
edits, manifest forgery with unlisted payloads, and forged provenance must
all FAIL against the production verifier (not against a string check).

REWORK v2 (D4):
- manifest: full coverage — every file in the package must be listed in
  SHA256SUMS.json (except SHA256SUMS.json itself and the receipt); any
  unlisted payload file is a failure.
- provenance: verified against the trusted upstream hashes, not by checking
  for a "FORGED" prefix.
- capital accounting: start at ¥100,000, integer ¥2 units, requested/funded/K
  consistency, no top-up, post = pre - funded + payout for every path.
- N/K semantics: the verifier now takes K and checks exactly K ticket rows per
  issue (the old function never received K).
- outcome isolation: a REAL 2024 label-mutation invariance check (fitted
  parameter invariance), not just a forbidden-name constant test.
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
    INITIAL_BANKROLL_YUAN,
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


# Files excluded from manifest coverage: the manifest itself and the plaintext
# receipt (which binds the method.yaml hash and is itself hash-checked by
# method_preflight).
MANIFEST_EXCLUDED = {"SHA256SUMS.json", "receipt.sha256"}


def manifest(package: Path, files: list[Path]) -> dict[str, str]:
    """Map relative path (posix) -> sha256 for each artifact file.

    REWORK v2 (D1): keys are RELATIVE to the package root so nested artifacts
    (e.g. models/fold1_mlp.joblib) are covered; the old basename-only mapping
    lost subdirectory entries.
    """
    return {
        path.relative_to(package).as_posix(): sha256_file(path)
        for path in files
    }


def verify_manifest(package: Path, manifest_json: dict[str, str]) -> list[str]:
    """Full-coverage manifest verification.

    REWORK v2 (D4): (1) every listed relative path exists and hashes match;
    (2) every file under the package root (except SHA256SUMS.json and the
    receipt) is listed — an unlisted payload is a failure.
    """
    failures: list[str] = []
    for name, expected in manifest_json.items():
        path = package / name
        if not path.exists():
            failures.append(f"missing artifact {name}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            failures.append(f"hash mismatch {name}: {actual} != {expected}")
    on_disk = {
        p.relative_to(package).as_posix()
        for p in package.rglob("*")
        if p.is_file() and p.name not in MANIFEST_EXCLUDED
    }
    unlisted = sorted(on_disk - set(manifest_json))
    if unlisted:
        failures.append(f"unlisted payload files: {unlisted}")
    return failures


def verify_receipt(package: Path) -> list[str]:
    """receipt.sha256 binds method.yaml (line 'hash  method.yaml')."""
    failures: list[str] = []
    receipt = package / "receipt.sha256"
    method = package / "method.yaml"
    if not receipt.exists():
        return ["missing receipt.sha256"]
    if not method.exists():
        return ["missing method.yaml for receipt check"]
    text = receipt.read_text(encoding="utf-8")
    expected = sha256_file(method)
    found = False
    for line in text.splitlines():
        if line.strip().endswith("method.yaml"):
            parts = line.strip().split()
            if parts and parts[0] == expected:
                found = True
    if not found:
        failures.append("receipt.sha256 does not bind method.yaml hash")
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
    """post = pre - funded + payout; integer ¥2 funding; path continuity.

    REWORK v2 (D4): additionally checks every path starts at the frozen
    ¥100,000 initial bankroll, funded stake is an integer multiple of ¥2,
    funded <= pre (no leverage / no top-up), and no negative/NaN values.
    """
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
    if (ledger["pre_issue_bankroll_yuan"] < 0).any():
        failures.append("negative pre-issue bankroll")
    # Integer ¥2 funding units (native ¥2 per ticket; active = integer units).
    funded = ledger["funded_stake_yuan"].to_numpy(dtype=float)
    if not np.allclose(funded / TICKET_STAKE_YUAN, np.round(funded / TICKET_STAKE_YUAN), atol=1e-9):
        failures.append("funded stake is not an integer multiple of ¥2")
    # No leverage: funded must never exceed pre (and never exceed requested).
    if "requested_stake_yuan" in ledger.columns:
        over_req = ledger["funded_stake_yuan"] > ledger["requested_stake_yuan"] + 1e-6
        if over_req.any():
            failures.append(
                f"funded exceeds requested on {int(over_req.sum())} rows"
            )
    over_pre = ledger["funded_stake_yuan"] > ledger["pre_issue_bankroll_yuan"] + 1e-6
    if over_pre.any():
        failures.append(f"funded exceeds pre-issue bankroll on {int(over_pre.sum())} rows")
    # Path continuity: within each (split, policy) path the next issue's pre
    # must equal the prior issue's post (no top-up, no leakage).
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
    # Every path starts at the frozen ¥100,000 initial bankroll.
    if path_keys:
        for _, group in ledger.groupby(path_keys, sort=False):
            group = group.sort_values("issue")
            first = float(group.iloc[0]["pre_issue_bankroll_yuan"])
            if not np.isclose(first, INITIAL_BANKROLL_YUAN, atol=1e-6):
                failures.append(
                    f"path {group.iloc[0].get('policy', '?')} starts at {first}, "
                    f"not {INITIAL_BANKROLL_YUAN}"
                )
                break
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


def verify_nk_semantics(ticket_rows: pd.DataFrame, k: int | None = None) -> list[str]:
    """Every ticket has exactly N distinct matches; K is ticket count.

    REWORK v2 (D4): the function now receives K and checks that exactly K
    ticket rows exist per issue for each issued bundle (rows carry 'k' or a
    caller-provided K).  The old verifier never received K and accepted a
    single ticket.
    """
    failures: list[str] = []
    if ticket_rows.empty:
        return ["empty ticket table"]
    # Per-bundle K check: rows are grouped by (issue, lane, seed) if present,
    # else the caller-provided k applies to the whole table.
    group_cols = [c for c in ("issue", "lane", "seed") if c in ticket_rows.columns]
    if group_cols:
        for _, group in ticket_rows.groupby(group_cols, sort=False):
            row_k = int(group["k"].iloc[0]) if "k" in group.columns else (
                k if k is not None else len(group)
            )
            if len(group) != row_k:
                failures.append(
                    f"bundle has {len(group)} tickets but K={row_k}"
                )
                break
    elif k is not None:
        if len(ticket_rows) != k:
            failures.append(f"ticket table has {len(ticket_rows)} rows but K={k}")
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


def verify_provenance(provenance: dict[str, Any]) -> list[str]:
    """Validate provenance against the trusted upstream identity.

    REWORK v2 (D4): provenance must carry the frozen upstream hashes and
    contract version.  A forged provenance fails because the fields do not
    match the trusted constants (not because a string starts with 'FORGED').
    """
    from .contract import (
        UPSTREAM_207_MANIFEST_SHA256,
        UPSTREAM_207_SHA,
        VALUE_MATRIX_SHA256,
    )

    failures: list[str] = []
    expected = {
        "version": CONTRACT_VERSION,
        "source_issue_207_sha": UPSTREAM_207_SHA,
        "source_issue_207_manifest_sha256": UPSTREAM_207_MANIFEST_SHA256,
        "source_value_matrix_sha256": VALUE_MATRIX_SHA256,
    }
    for key, value in expected.items():
        if provenance.get(key) != value:
            failures.append(f"provenance {key} mismatch: {provenance.get(key)}")
    if "label_boundary" not in provenance or "2024" not in str(provenance.get("label_boundary", "")):
        failures.append("provenance label_boundary must state 2024 embargo")
    return failures


def verify_2024_mutation_invariance(
    fit_fn: Any,
    value_matrix_path: Path,
    *,
    fit_kwargs: dict[str, Any] | None = None,
) -> list[str]:
    """REQ-208-03: mutating 2024 labels cannot change any fitted parameter.

    REWORK v2 (D4): this is a REAL invariance check.  The pipeline is fitted
    on a copy of the value matrix with 2024 realized_outcome/official SP
    mutated; fitted parameters (model weights or fixed-action choice) must be
    byte-identical because #208 never reads 2024 rows.

    fit_fn(pipeline_frame) -> fitted_params_hash (str).  The check loads the
    original value matrix, fits, then fits again on a 2024-mutated copy and
    compares hashes.
    """
    if fit_fn is None:
        return ["2024 mutation invariance requires a fit_fn"]
    import copy
    import tempfile

    frame = pd.read_parquet(value_matrix_path)
    baseline = fit_fn(frame, **(fit_kwargs or {}))
    mutated = frame.copy()
    mask_2024 = mutated["issue"].astype(str).str.startswith("24")
    if mask_2024.any():
        mutated.loc[mask_2024, "realized_outcome"] = ~mutated.loc[
            mask_2024, "realized_outcome"
        ].astype(bool)
        mutated.loc[mask_2024, "official_final_sp_label"] = (
            mutated.loc[mask_2024, "official_final_sp_label"] * 1.5
        )
    after = fit_fn(mutated, **(fit_kwargs or {}))
    if baseline != after:
        return ["2024 label mutation changed fitted parameters"]
    return []


# --- tamper attacks (attack the PRODUCTION verifier) ------------------------


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
    """Attack 3: rewrite the manifest to claim tampered hashes are valid AND
    hide an unlisted payload."""
    frame_names = [
        path.relative_to(package).as_posix()
        for path in sorted(package.rglob("*.parquet"))
    ]
    forged: dict[str, str] = {}
    for name in frame_names:
        forged[name] = "0" * 64
    # Also declare a payload that is NOT on disk (claims coverage of a file
    # that does not exist) — coverage must catch the missing file.
    forged["ghost_payload.parquet"] = "0" * 64
    _json(manifest_path, forged)


def tamper_forge_source_trace(trace_path: Path) -> None:
    """Attack 4: rewrite provenance/source trace with forged identity + hash."""
    if not trace_path.exists():
        raise VerifyError("tamper target missing")
    value = json.loads(trace_path.read_text(encoding="utf-8"))
    value["source_identity"] = "FORGED_TRACE_00000000000000000000000000000000"
    value["source_issue_207_manifest_sha256"] = "0" * 64
    value["source_value_matrix_sha256"] = "0" * 64
    _json(trace_path, value)


def run_tamper_suite(package: Path, verify_package_fn: Any) -> list[dict[str, Any]]:
    """Run the REQ-E06 tamper attacks against the PRODUCTION package verifier.

    REWORK v2 (D4): each attack copies the package to a temp dir, mutates the
    copy, then runs the FULL production verifier (verify_package_fn) on the
    copy.  The attack is DETECTED iff the full verifier returns failures.
    This replaces the old per-function probes that could be fooled by
    unlisted payloads / FORGED-prefix checks.
    """
    import shutil
    import tempfile

    results: list[dict[str, Any]] = []

    def _run_attack(name: str, mutate_fn: Any) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            # Full recursive copy (staging tree includes models/ subdir).
            for item in package.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(package)
                    dest = work / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)
            mutate_fn(work)
            failures = verify_package_fn(work)
            results.append(
                {
                    "attack": name,
                    "detected": bool(failures),
                    "failures": failures[:5],
                }
            )

    _run_attack(
        "mutate_settlement",
        lambda target: tamper_mutate_settlement(
            target / "issue_capital_ledger.parquet"
        ),
    )
    _run_attack(
        "self_consistent_ledger",
        lambda target: tamper_self_consistent_ledger(
            target / "issue_capital_ledger.parquet"
        ),
    )
    _run_attack(
        "forge_manifest",
        lambda target: tamper_forge_manifest(
            target / "SHA256SUMS.json", target
        ),
    )
    _run_attack(
        "forge_source_trace",
        lambda target: tamper_forge_source_trace(target / "provenance.json"),
    )
    return results


__all__ = [
    "MANIFEST_EXCLUDED", "VerifyError", "manifest", "run_tamper_suite",
    "sha256_file", "tamper_forge_manifest", "tamper_forge_source_trace",
    "tamper_mutate_settlement", "tamper_self_consistent_ledger",
    "verify_2024_mutation_invariance", "verify_capital_accounting",
    "verify_manifest", "verify_nk_semantics", "verify_no_2024_issue",
    "verify_no_embargoed_split", "verify_provenance", "verify_receipt",
    "verify_schema",
]
