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


def _handoff_ref_in_package(package: Path, ref: str) -> Path | None:
    """Map a repo-root-relative handoff ref (results/issue-208/...) into the
    package tree, tolerating a staging or temp package directory name.

    The handoff serializes canonical post-publication paths (e.g.
    `results/issue-208/SHA256SUMS.json`).  Verification runs on the staging
    tree before atomic rename AND on the final package afterwards, so the ref
    is resolved relative to the package root by stripping the canonical
    package-name segment.  Temp copies used by the tamper suite carry the same
    relative layout, so the same resolution applies there.
    """
    ref_path = Path(ref)
    if ref_path.is_absolute():
        return None
    canonical = package.name.removesuffix(".staging")
    parts = ref_path.parts
    if canonical in parts:
        sub = Path(*parts[parts.index(canonical) + 1:])
        return package / sub
    return package / ref_path


def verify_handoff_paths(package: Path) -> list[str]:
    """Every #209 handoff artifact path must resolve inside the published
    package and must never reference the staging directory (`.staging`).

    REWORK v3.1 (PI narrow durability REJECT 2026-08-15): the v3 handoff
    serialized `results/issue-208.staging/SHA256SUMS.json` because
    `_build_handoff` received the staging output path.  This verifier runs on
    both the staging tree (pre-rename) and the final package (post-rename) and
    fails closed if any handoff path points at `.staging` or does not resolve
    after publication.
    """
    failures: list[str] = []
    handoff_path = package / "handoff_209.json"
    if not handoff_path.exists():
        return ["missing handoff_209.json"]
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    refs: list[tuple[str, str]] = []
    if "package_manifest" in handoff:
        refs.append(("package_manifest", str(handoff["package_manifest"])))
    if "model_file" in handoff:
        refs.append(("model_file", str(handoff["model_file"])))
    for field, ref in refs:
        if ".staging" in ref:
            failures.append(
                f"handoff {field} references staging path: {ref}"
            )
            continue
        target = _handoff_ref_in_package(package, ref)
        if target is None:
            failures.append(f"handoff {field} path not under package root: {ref}")
            continue
        if not target.exists():
            failures.append(
                f"handoff {field} does not resolve after publish: {ref}"
            )
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


# --- REWORK v3 (PI payout-economics) verifier --------------------------------

# Beijing ticket payout coefficient — applied exactly once per winning N-fold
# ticket.  Never divided out, never per leg, never compounded as 0.65^N.
_PAYOUT_COEFFICIENT = 0.65
_PAYOUT_REL_TOL = 1e-6


def _official_sp_for_ticket(
    panels: dict[tuple[str, str], Any],
    split: str,
    issue: str,
    match_indices: str,
    outcomes: str,
) -> float:
    """Product of official final SP for a ticket's (match, outcome) legs.

    Recomputed independently from the frozen value-matrix panels so the
    verifier does not trust the worker's `pre_tax_gross_multiple` field.
    """
    panel = panels.get((str(split), str(issue)))
    if panel is None:
        raise VerifyError(f"payout-economics panel missing: {split}/{issue}")
    idx = [int(x) for x in str(match_indices).split("|")]
    out_rank = {"3": 0, "1": 1, "0": 2}
    oidx = [out_rank[o] for o in str(outcomes).split("|")]
    if len(idx) != len(oidx):
        raise VerifyError("ticket leg count mismatch in payout-economics")
    sp = panel.official_sp[np.asarray(idx, dtype=int), np.asarray(oidx, dtype=int)]
    return float(np.prod(sp))


def verify_payout_economics(
    package: Path,
    panels: dict[tuple[str, str], Any],
    upstream_tickets: pd.DataFrame,
    ledger: pd.DataFrame | None = None,
) -> list[str]:
    """REWORK v3 (PI payout-economics) production-entry verifier.

    Independent checks that the Beijing payout coefficient 0.65 is applied
    EXACTLY ONCE per winning N-fold ticket and never divided out:

    1. `ticket_economics.parquet` per-ticket pre_tax_gross_multiple must equal
       0.65 * prod(official_sp) for hit rows (0.0 for miss rows).  This
       detects BOTH omission (multiple == prod(SP)) AND compounding
       (multiple == 0.65^N * prod(SP)).
    2. `incumbent_paths.parquet` gross_payout_yuan must equal the frozen
       CONTROLLING tickets' sum(realized_gross) * ¥2 (realized_gross already
       includes 0.65 exactly once).  This detects division-out (payout
       inflated by /0.65).
    3. The consolidated ledger's FROZEN_INCUMBENT_207 rows must match the
       incumbent_paths rows (binding consistency).
    """
    failures: list[str] = []

    # 1. Per-ticket economics from the immutable package.
    econ_path = package / "ticket_economics.parquet"
    if not econ_path.exists():
        failures.append("missing ticket_economics.parquet for payout economics")
        return failures
    econ = pd.read_parquet(econ_path)
    if econ.empty:
        failures.append("empty ticket_economics.parquet")
        return failures
    checked = 0
    for _, row in econ.iterrows():
        try:
            sp_prod = _official_sp_for_ticket(
                panels,
                str(row["split"]),
                str(row["issue"]),
                str(row["match_indices"]),
                str(row["outcomes"]),
            )
        except VerifyError as exc:
            failures.append(str(exc))
            continue
        hit = bool(row["realized_hit"])
        if hit:
            expected = _PAYOUT_COEFFICIENT * sp_prod
            actual = float(row["pre_tax_gross_multiple"])
            if not np.isclose(actual, expected, rtol=_PAYOUT_REL_TOL, atol=1e-9):
                failures.append(
                    f"payout coefficient violation ticket {str(row['ticket_identity'])} "
                    f"{row['split']}/{row['issue']}: multiple={actual:.6f} "
                    f"expected 0.65*prod(SP)={expected:.6f} (prod(SP)={sp_prod:.6f})"
                )
                if len(failures) >= 5:
                    break
        else:
            actual = float(row["pre_tax_gross_multiple"])
            if not np.isclose(actual, 0.0, atol=1e-9):
                failures.append(
                    f"miss ticket {str(row['ticket_identity'])} has nonzero multiple "
                    f"{actual}"
                )
        checked += 1
    if checked == 0:
        failures.append("ticket_economics had no rows with official SP available")

    # 2. Incumbent path payout vs frozen CONTROLLING realized_gross.
    inc_path = package / "incumbent_paths.parquet"
    if not inc_path.exists():
        failures.append("missing incumbent_paths.parquet")
    else:
        incumbent = pd.read_parquet(inc_path)
        if "source" in incumbent.columns:
            reconstructed = incumbent[
                incumbent["source"].str.startswith(
                    "RECONSTRUCTED_CORRECTED_ECONOMICS"
                )
            ]
        else:
            reconstructed = incumbent
        for _, row in reconstructed.iterrows():
            tickets = upstream_tickets[
                (upstream_tickets["split"] == row["split"])
                & (upstream_tickets["issue"] == row["issue"])
                & (upstream_tickets["panel_role"] == "CONTROLLING")
                & (upstream_tickets["policy"] == "MARKET_WOR")
                & (upstream_tickets["k"] == 8)
            ]
            if tickets.empty:
                failures.append(
                    f"incumbent reconstruction missing CONTROLLING tickets "
                    f"{row['split']}/{row['issue']}"
                )
                continue
            expected_payout = float(
                tickets["realized_gross"].fillna(0.0).sum() * 2.0
            )
            actual_payout = float(row["gross_payout_yuan"])
            if not np.isclose(
                actual_payout, expected_payout, rtol=_PAYOUT_REL_TOL, atol=1e-6
            ):
                failures.append(
                    f"incumbent payout division-out at {row['split']}/{row['issue']}: "
                    f"payout={actual_payout:.4f} expected "
                    f"sum(realized_gross)*2={expected_payout:.4f}"
                )
                if len(failures) >= 5:
                    break

    # 3. FROZEN_INCUMBENT_207 ledger rows must equal incumbent_paths.
    if ledger is not None and not ledger.empty:
        if "source" in ledger.columns:
            frozen_rows = ledger[ledger["source"] == "FROZEN_INCUMBENT_207"]
            if not frozen_rows.empty:
                inc_path2 = package / "incumbent_paths.parquet"
                if inc_path2.exists():
                    incumbent = pd.read_parquet(inc_path2)
                    for _, row in frozen_rows.iterrows():
                        sub = incumbent[
                            (incumbent["split"] == row["split"])
                            & (incumbent["issue"] == row["issue"])
                        ]
                        if sub.empty:
                            continue
                        if not np.isclose(
                            float(sub.iloc[0]["gross_payout_yuan"]),
                            float(row["gross_payout_yuan"]),
                            rtol=_PAYOUT_REL_TOL, atol=1e-6,
                        ):
                            failures.append(
                                f"FROZEN_INCUMBENT_207 ledger row {row['split']}/"
                                f"{row['issue']} does not match incumbent_paths"
                            )
                            break
    return failures


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


def tamper_omit_payout_coefficient(econ_path: Path) -> None:
    """Attack 5 (REWORK v3): drop the 0.65 coefficient from a hit ticket.

    Sets a winning ticket's pre_tax_gross_multiple to the raw product(SP)
    (the superseded omission defect).  The payout-economics verifier must
    recompute 0.65*prod(SP) and FAIL the tampered multiple.
    """
    frame = pd.read_parquet(econ_path)
    hits = frame[frame["realized_hit"] == True]  # noqa: E712
    if hits.empty:
        raise VerifyError("tamper target has no hit ticket")
    idx = hits.index[0]
    # raw product(SP) = pre_tax_gross_multiple / 0.65 (omission).
    frame.loc[idx, "pre_tax_gross_multiple"] = (
        float(frame.loc[idx, "pre_tax_gross_multiple"]) / _PAYOUT_COEFFICIENT
    )
    frame.to_parquet(econ_path, index=False)


def tamper_divide_out_payout(incumbent_paths_path: Path) -> None:
    """Attack 6 (REWORK v3): divide the payout coefficient back out.

    Inflates an incumbent issue's gross_payout_yuan by /0.65 (the superseded
    division-out defect: pre-tax = realized_gross / 0.65).  The verifier must
    recompute payout = sum(realized_gross)*2 and FAIL.  The mutated row is a
    NONZERO-payout issue (a zero-payout row would make /0.65 a no-op).
    """
    frame = pd.read_parquet(incumbent_paths_path)
    if frame.empty:
        raise VerifyError("tamper target empty")
    nonzero = frame[frame["gross_payout_yuan"] > 1e-9]
    if nonzero.empty:
        raise VerifyError("tamper target has no nonzero incumbent payout")
    idx = nonzero.index[0]
    frame.loc[idx, "gross_payout_yuan"] = (
        float(frame.loc[idx, "gross_payout_yuan"]) / _PAYOUT_COEFFICIENT
    )
    frame.to_parquet(incumbent_paths_path, index=False)


def tamper_compound_coefficient(econ_path: Path, n: int = 4) -> None:
    """Attack 7 (REWORK v3): compound the coefficient per leg (0.65^N).

    Sets a winning ticket's pre_tax_gross_multiple to 0.65^N * prod(SP)
    (the superseded per-leg compounding defect).  The verifier must recompute
    0.65*prod(SP) (coefficient exactly once) and FAIL the 0.65^N multiple.
    """
    frame = pd.read_parquet(econ_path)
    hits = frame[frame["realized_hit"] == True]  # noqa: E712
    if hits.empty:
        raise VerifyError("tamper target has no hit ticket")
    idx = hits.index[0]
    # 0.65^N * prod(SP) = (0.65^N)/0.65 * (0.65*prod(SP)) = 0.65^(N-1)*multiple.
    frame.loc[idx, "pre_tax_gross_multiple"] = (
        float(frame.loc[idx, "pre_tax_gross_multiple"])
        * (_PAYOUT_COEFFICIENT ** (n - 1))
    )
    frame.to_parquet(econ_path, index=False)


def tamper_handoff_staging_path(handoff_path: Path) -> None:
    """Attack 8 (REWORK v3.1): rewrite handoff_209.json to point package_manifest
    at the transient staging directory.

    The v3 defect serialized `results/issue-208.staging/SHA256SUMS.json`
    because `_build_handoff` received the staging output path.  A handoff that
    references `.staging` must FAIL `verify_handoff_paths` (and therefore the
    production package verifier) even though the path is a valid relative
    string — the staging directory does not exist after atomic publication.
    """
    if not handoff_path.exists():
        raise VerifyError("tamper target missing")
    value = json.loads(handoff_path.read_text(encoding="utf-8"))
    value["package_manifest"] = "results/issue-208.staging/SHA256SUMS.json"
    _json(handoff_path, value)


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
    _run_attack(
        "omit_payout_coefficient",
        lambda target: tamper_omit_payout_coefficient(
            target / "ticket_economics.parquet"
        ),
    )
    _run_attack(
        "divide_out_payout",
        lambda target: tamper_divide_out_payout(
            target / "incumbent_paths.parquet"
        ),
    )
    _run_attack(
        "compound_coefficient_0_65_n",
        lambda target: tamper_compound_coefficient(
            target / "ticket_economics.parquet", n=4
        ),
    )
    _run_attack(
        "handoff_staging_path",
        lambda target: tamper_handoff_staging_path(target / "handoff_209.json"),
    )
    return results


__all__ = [
    "MANIFEST_EXCLUDED", "VerifyError", "manifest", "run_tamper_suite",
    "sha256_file", "tamper_forge_manifest", "tamper_forge_source_trace",
    "tamper_mutate_settlement", "tamper_self_consistent_ledger",
    "tamper_omit_payout_coefficient", "tamper_divide_out_payout",
    "tamper_compound_coefficient", "tamper_handoff_staging_path",
    "verify_2024_mutation_invariance", "verify_capital_accounting",
    "verify_handoff_paths", "verify_manifest", "verify_nk_semantics",
    "verify_no_2024_issue", "verify_no_embargoed_split",
    "verify_payout_economics", "verify_provenance", "verify_receipt",
    "verify_schema",
]
