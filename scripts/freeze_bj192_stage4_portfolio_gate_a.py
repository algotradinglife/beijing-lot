#!/usr/bin/env python3
"""Create #192's outcome-unexposed Stage-4 capital-portfolio Gate-A freeze.

The script reads only #170's pre-outcome allocation package and #137's
pre-outcome chronology census.  Accepted settled packages are bound by hash in
the card but deliberately never parsed here: Stage 4 cannot choose a sleeve
from historical returns.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path


CONTRACT = "BJ-HIST-N7-STRATEGY-ENSEMBLE-001"
VERSION = "bj192-gate-a-v3"
OUTCOME_BOUNDARY = (
    "Gate A is outcome-unexposed: no score, result, final/winning SP, payout, "
    "tax realization, ROI, net, gross, or settlement payload is read."
)
INITIAL_BANKROLL_YUAN = 100_000
TICKET_STAKE_YUAN = 2
POSITION_FRACTIONS = tuple(range(5, 101, 5))
BOOTSTRAP_REPLICATES = 20_000
BOOTSTRAP_SEED = 192001


def repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
SOURCE_170 = ROOT / "results" / "bj170_gate_a_preoutcome_v2"
SOURCE_137 = ROOT / "results" / "bj137_gate_a_preoutcome_v2"
SOURCE_176 = ROOT / "results" / "bj176_issue_equity_risk_v1"
SOURCE_190 = ROOT / "results" / "bj190_gate_b_sparse_divergence_v1"
SOURCE_193 = ROOT / "results" / "bj193_gate_b_regime_meta_policy_v2"
SOURCE_145 = ROOT / "results" / "bj145_gate_a_preoutcome_v8"
SOURCE_148 = ROOT / "results" / "bj148_gate_a_preoutcome_v1"
SOURCE_151 = ROOT / "results" / "bj151_gate_a_preoutcome_v1"
SOURCE_159 = ROOT / "results" / "bj159_gate_a_preoutcome_v2r1"
SOURCE_167A = ROOT / "results" / "bj167_gate_a_strategy_atlas_v3r1"
SOURCE_167B = (
    ROOT / "results" / "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1"
)
SOURCE_170B = ROOT / "results" / "bj170_gate_b_selector_allocator_stack_v1"
DEFAULT_OUTPUT = ROOT / "results" / "bj192_gate_a_preoutcome_v1"

EXPECTED_SOURCES = {
    "bj170_gate_a_preoutcome_v2": {
        "path": SOURCE_170,
        "manifest": "bb60ac5638d29674ad8c1c05f1ffe3ab9cdf12acb70ebdae6cea679743136d87",
        "content": "adc4d0f96628c784149da998a20e8830cde26db4001fe457eaf9ca4b7bb74223",
        "role": "accepted outcome-unexposed sleeve identity, ticket and support freeze",
    },
    "bj137_gate_a_preoutcome_v2": {
        "path": SOURCE_137,
        "manifest": "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df",
        "content": "36d6afcc33a5b5ceb3e4a990bfe6ec05503be115270c3489f4973dc3a59dd236",
        "role": "accepted outcome-unexposed chronological issue census",
    },
    "bj176_issue_equity_risk_v1": {
        "path": SOURCE_176,
        "manifest": "39316952296c2349f5da2f963d43c0baf0d812fba4eea967536a8b80bd57d5ee",
        "content": "94188354baf01c68cb0ec0791248d3f8f03e31d4a7011db7b6b68e9797720f5c",
        "role": "accepted terminal three-sleeve settlement and holding-risk convention bridge; hash-only during Gate A",
    },
    "bj190_gate_b_sparse_divergence_v1": {
        "path": SOURCE_190,
        "manifest": "5685f25d9ce70a66b38b283f668d258d97dfe2e356c5bd45d9666400c6ab4554",
        "content": "5112dc652277a234fcb36687d59e2bd96bf8daeaaa1c9ddd06481923de909ce6",
        "role": "terminal eligibility decision only; excluded from sleeve catalog; hash-only during Gate A",
    },
    "bj193_gate_b_regime_meta_policy_v2": {
        "path": SOURCE_193,
        "manifest": "83b6c67fc91f59fcbf90895413c570225bbc34b18bf8d1d1c0f89634e9fce4d5",
        "content": "0c3a68e75dba540127ec5304e5b28aea73bc9dc191573682de9029efffc30e40",
        "role": "terminal interface/accounting lessons only; FULL_DYNAMIC_CHAIN excluded; hash-only during Gate A",
    },
    "bj145_gate_a_preoutcome_v8": {
        "path": SOURCE_145,
        "manifest": "da1165d3d2be49deac85a494443ba04606d176ca059c265857573ce24360114c",
        "content": "074c9b06c024a1db80b5b53cfc99a1bc164001b205fcd94a0c159daf445dab7f",
        "role": "accepted allocation mechanism/M/seed evidence; composable only with a complete selector trace",
    },
    "bj148_gate_a_preoutcome_v1": {
        "path": SOURCE_148,
        "manifest": "fd4a0f4dc0ab5ef97f3c260a082515aa7874a60a1ac1e5e0ecd865fdb1eeafd6",
        "content": "dfd3ac234f95f28185a09a6bb2f69c3ff66ddb696ce1fe45a6a1215d932dcd0a",
        "role": "accepted dense-M support/seed evidence; no stable sweet spot, descriptive frontier only",
    },
    "bj151_gate_a_preoutcome_v1": {
        "path": SOURCE_151,
        "manifest": "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6",
        "content": "ac36bc2422d1afd22c3bb4bd680568401cbaec30e0d2006d13afcdfa141b89a5",
        "role": "accepted fixed-candidate reproduction identity/M/seed evidence; descriptive only",
    },
    "bj159_gate_a_preoutcome_v2r1": {
        "path": SOURCE_159,
        "manifest": "a15c585fc1836da4f558d07ce19c925561bfd1c240e834b7e3e0da22701cd325",
        "content": "4ec52432ec6c1779bab33b0c4bdc4e381b0ae7434228637c509970291ed7361e",
        "role": "accepted complete selected WOR N2–N10 chain identity/M/seed evidence",
    },
    "bj167_gate_a_strategy_atlas_v3r1": {
        "path": SOURCE_167A,
        "manifest": "5a82422755723453638d25c90f91213da046a9e7bed87a851b2e5700faa9c724",
        "content": "0806185a7a68b99fd2a6a465308d11e2886995f992bfa722adb287a4e6a4d147",
        "role": "accepted complete selector×allocation atlas identity/M/seed/support evidence",
    },
    "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1": {
        "path": SOURCE_167B,
        "manifest": "b3fa02f5cc2722932ff55fffb0bd9672508f6e78104cfb2458ad81c826f3b313",
        "content": "bfe29083b74d5d212555c261e888d6f5d4d5fd163b56e1876944d1f5d04aa5c7",
        "role": "accepted terminal atlas baseline ladder/evidence; hash-only during Gate A",
    },
    "bj170_gate_b_selector_allocator_stack_v1": {
        "path": SOURCE_170B,
        "manifest": "08e83353ad483e5d75911116a413186f007385f5dd37b8c4b757ac903221e512",
        "content": "75325aa0f60e277ad3fbf9d90116450833106bc3863b412ea3efcad9948a47b2",
        "role": "accepted exact three-way matched baseline bridge; hash-only during Gate A",
    },
}

SLEEVES = (
    (
        "BEST_FULL_FULL",
        "BEST_FULL",
        "FULL_ENUMERATED",
        "primary fixed upstream FULL control",
    ),
    (
        "MODEL_SOURCE_MODEL_CAP1_M512",
        "MODEL_SOURCE",
        "MODEL_CAP1_M512",
        "primary fixed upstream model sleeve",
    ),
    (
        "Q_SOURCE_Q_TOP_MASS_M192",
        "Q_SOURCE",
        "Q_TOP_MASS_M192",
        "primary fixed upstream Q sleeve",
    ),
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=fields, lineterminator="\n", extrasaction="raise"
        )
        w.writeheader()
        w.writerows(rows)


def verify_source(spec: dict[str, object]) -> dict[str, object]:
    path = Path(spec["path"])
    manifest_path, content_path = (
        path / "SHA256SUMS.json",
        path / "CONTENT_IDENTITY.json",
    )
    if (
        sha256_file(manifest_path) != spec["manifest"]
        or sha256_file(content_path) != spec["content"]
    ):
        raise RuntimeError(f"source hash drift: {path.name}")
    manifest = json.loads(manifest_path.read_text())
    actual = {
        p.name for p in path.iterdir() if p.is_file() and p.name != "SHA256SUMS.json"
    }
    if set(manifest) != actual:
        raise RuntimeError(f"source manifest coverage drift: {path.name}")
    for name, expected in manifest.items():
        if sha256_file(path / name) != expected:
            raise RuntimeError(f"source payload drift: {path.name}/{name}")
    return {
        "package": path.name,
        "manifest_sha256": spec["manifest"],
        "content_identity_sha256": spec["content"],
        "payload_count": len(manifest),
        "role": spec["role"],
    }


def source_inputs() -> tuple[
    list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]
]:
    """Return full calendar requests, strict-common flags and chronology.

    Capital feasibility is defined on all 348 canonical issues, including each
    sleeve's frozen NO_BET rows.  The 177 issue strict-common view is carried
    as a flag for matched attribution only; it never truncates the bankroll
    path.
    """
    selectors = {
        r["selector_alias"]: r for r in read_csv(SOURCE_170 / "selector_registry.csv")
    }
    arms = {
        r["allocation_arm"]: r for r in read_csv(SOURCE_170 / "allocation_registry.csv")
    }
    wanted = {
        (alias, arm): (sleeve, rationale) for sleeve, alias, arm, rationale in SLEEVES
    }
    planned = {
        (r["issue_instance"], r["selector_alias"], r["allocation_arm"]): r
        for r in read_csv(SOURCE_170 / "planned_issue_stake.csv")
        if (r["selector_alias"], r["allocation_arm"]) in wanted
    }
    membership = {
        r["issue_instance"]
        for r in read_csv(SOURCE_170 / "support_issue_membership.csv")
        if r["support_view_id"] == "THREE_WAY_ALL"
    }
    chronology = {
        r["issue_instance"]: r for r in read_csv(SOURCE_137 / "issue_census.csv")
    }
    if len(chronology) != 348 or len(membership) != 177 or membership - set(chronology):
        raise RuntimeError("canonical calendar/three-way support mismatch")
    rows: list[dict[str, str]] = []
    for c in chronology.values():
        for (alias, arm), (sleeve, rationale) in wanted.items():
            p = planned.get((c["issue_instance"], alias, arm))
            if p is None:
                raise RuntimeError(
                    f"missing frozen planned stake: {c['issue_instance']} {alias}/{arm}"
                )
            if (p["issue_instance"], p["selector_id"]) != (
                c["issue_instance"],
                selectors[alias]["selector_id"],
            ):
                raise RuntimeError("frozen request identity mismatch")
            rows.append(
                {
                    "issue": c["issue"],
                    "year": c["year"],
                    "fold": c["fold"],
                    "issue_instance": c["issue_instance"],
                    "first_kickoff_ts": c["first_kickoff_ts"],
                    "strict_three_way_common": "1"
                    if c["issue_instance"] in membership
                    else "0",
                    "sleeve_id": sleeve,
                    "selector_alias": alias,
                    "selector_id": selectors[alias]["selector_id"],
                    "allocation_arm": arm,
                    "M": arms[arm]["M"],
                    "mechanism": arms[arm]["mechanism"],
                    "cap": arms[arm]["cap"],
                    "weight_source": arms[arm]["weight_source"],
                    "native_policy_status": p["policy_status"],
                    "settlement_availability_state": "OUTCOME_UNEXPOSED_PENDING_GATE_B",
                    "native_requested_ticket_count": p["planned_ticket_count"],
                    "native_requested_stake_yuan": p["planned_stake_yuan"],
                    "selected_identity_count": p["selected_identity_count"],
                    "rationale": rationale,
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
    rows.sort(
        key=lambda r: (r["first_kickoff_ts"], r["issue_instance"], r["sleeve_id"])
    )
    for i, row in enumerate(rows):
        row["calendar_index"] = i // len(SLEEVES)
    calendar = [dict(r) for r in rows if r["sleeve_id"] == SLEEVES[0][0]]
    return rows, calendar, list(chronology.values())


def sleeve_trace_registry(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Bind the inherited Stage-1→3 trace, without reading its settlement.

    #170's identity freeze holds the upstream selection/direction identity and
    # its allocation digest holds the ticket-construction multiplicities.  A
    #192 sleeve may resize only those exact trace elements, never substitute a
    #new selection, result code, or ticket vector.
    """
    common_issues = {r["issue_instance"] for r in rows}
    identities = read_csv_gzip(SOURCE_170 / "identity_freeze.csv.gz")
    allocations = read_csv_gzip(SOURCE_170 / "identity_allocation_digest.csv.gz")
    result: list[dict[str, object]] = []
    for sleeve, alias, arm, _ in SLEEVES:
        ids = [
            r
            for r in identities
            if r["selector_alias"] == alias and r["issue_instance"] in common_issues
        ]
        allocs = [
            r
            for r in allocations
            if r["selector_alias"] == alias
            and r["allocation_arm"] == arm
            and r["issue_instance"] in common_issues
        ]
        ids.sort(
            key=lambda r: (
                r["issue_instance"],
                r["portfolio_id"],
                r["source_identity_row_sha256"],
            )
        )
        allocs.sort(
            key=lambda r: (r["issue_instance"], r["portfolio_id"], r["counts_sha256"])
        )
        validate_trace_keys(ids, allocs, sleeve)
        requests = [r for r in rows if r["sleeve_id"] == sleeve]
        result.append(
            {
                "sleeve_id": sleeve,
                "selector_alias": alias,
                "allocation_arm": arm,
                "stage_1_3_trace_status": "COMPLETE_INHERITED_FROZEN",
                "source_identity_count": len(ids),
                "source_allocation_count": len(allocs),
                "source_identity_trace_sha256": canonical_hash(
                    [r["source_identity_row_sha256"] for r in ids]
                ),
                "source_ticket_trace_sha256": canonical_hash(
                    [r["counts_sha256"] for r in allocs]
                ),
                "native_requested_ticket_count": sum(
                    int(r["native_requested_ticket_count"]) for r in requests
                ),
                "native_requested_stake_yuan": sum(
                    int(r["native_requested_stake_yuan"]) for r in requests
                ),
                "trace_rule": "Stage 4 may only size down/abstain from these inherited selection→direction→ticket traces.",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return result


def validate_trace_keys(
    identities: list[dict[str, str]], allocations: list[dict[str, str]], sleeve_id: str
) -> None:
    """Reject same-count but non-identical upstream trace rows."""
    if not identities or not allocations:
        raise RuntimeError(f"empty inherited trace: {sleeve_id}")

    def key(row: dict[str, str]) -> tuple[str, str]:
        return (row["issue_instance"], row["portfolio_id"])

    id_by_key = {key(row): row for row in identities}
    allocation_by_key = {key(row): row for row in allocations}
    if len(id_by_key) != len(identities) or len(allocation_by_key) != len(allocations):
        raise RuntimeError(f"non-unique inherited trace key: {sleeve_id}")
    if id_by_key.keys() != allocation_by_key.keys():
        raise RuntimeError(f"inherited trace key mismatch: {sleeve_id}")
    for trace_key, identity in id_by_key.items():
        allocation = allocation_by_key[trace_key]
        if identity["selector_alias"] != allocation["selector_alias"]:
            raise RuntimeError(f"selector mismatch in inherited trace: {sleeve_id}")
        if identity["support_key_sha256"] != allocation["support_key_sha256"]:
            raise RuntimeError(f"support mismatch in inherited trace: {sleeve_id}")


def read_csv_gzip(path: Path) -> list[dict[str, str]]:
    import gzip

    with gzip.open(path, "rt", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalize(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in weights.values())
    if total <= 0.0 or not math.isfinite(total):
        n = len(weights)
        return {key: 1.0 / n for key in sorted(weights)}
    return {key: max(0.0, value) / total for key, value in weights.items()}


def equal_weights(sleeves: list[str]) -> tuple[dict[str, float], str]:
    return ({sleeve: 1.0 / len(sleeves) for sleeve in sleeves}, "EQUAL_WEIGHT")


def active_common_history(
    history: list[dict[str, float | None]], sleeves: list[str]
) -> list[dict[str, float]]:
    """Keep only full sleeve observations with positive actual stake.

    Gate B supplies `None` rather than 0 for a NO_BET/unavailable sleeve.
    Zero flow remains in the capital calendar but is not an active return
    observation for the 52-observation estimator.
    """
    active = [
        {s: float(row[s]) for s in sleeves}
        for row in history
        if all(row.get(s) is not None for s in sleeves)
    ]
    return active[-52:]


def covariance_matrix(
    observations: list[dict[str, float]], sleeves: list[str], shrinkage: float = 0.10
) -> list[list[float]]:
    n = len(observations)
    if n < 2:
        raise ValueError("insufficient observations")
    means = {s: sum(row[s] for row in observations) / n for s in sleeves}
    sample = [
        [
            sum((row[a] - means[a]) * (row[b] - means[b]) for row in observations)
            / (n - 1)
            for b in sleeves
        ]
        for a in sleeves
    ]
    # Deterministic diagonal shrinkage makes the matrix well-conditioned but
    # does not conceal a zero/singular data condition: callers still fallback.
    return [
        [
            (1.0 - shrinkage) * sample[i][j]
            + (shrinkage * sample[i][i] if i == j else 0.0)
            for j in range(len(sleeves))
        ]
        for i in range(len(sleeves))
    ]


def dynamic_weights(
    method: str, history: list[dict[str, float | None]], sleeves: list[str]
) -> tuple[dict[str, float], str]:
    """Exact prior-only model used by Gate B; never inspect the current issue."""
    if method == "EQUAL_WEIGHT":
        return equal_weights(sleeves)
    observations = active_common_history(history, sleeves)
    if len(observations) < 52:
        return (*equal_weights(sleeves)[0:1], "FALLBACK_INSUFFICIENT_52_COMMON_ACTIVE")
    try:
        covariance = covariance_matrix(observations, sleeves)
        vols = {s: math.sqrt(max(0.0, covariance[i][i])) for i, s in enumerate(sleeves)}
        if any(not math.isfinite(v) or v <= 1e-12 for v in vols.values()):
            return (*equal_weights(sleeves)[0:1], "FALLBACK_ZERO_OR_NONFINITE_VOL")
        if method == "PRIOR_INVERSE_VOL":
            return normalize({s: 1.0 / vols[s] for s in sleeves}), "PRIOR_INVERSE_VOL"
        if method == "PRIOR_DRAWDOWN_AWARE":
            penalties: dict[str, float] = {}
            for s in sleeves:
                equity = peak = 1.0
                max_drawdown = 0.0
                for row in observations:
                    equity *= 1.0 + row[s]
                    peak = max(peak, equity)
                    max_drawdown = max(max_drawdown, 1.0 - equity / peak)
                penalties[s] = max_drawdown
            return normalize(
                {s: 1.0 / (vols[s] * (1.0 + penalties[s])) for s in sleeves}
            ), "PRIOR_DRAWDOWN_AWARE"
        if method != "PRIOR_ERC":
            raise ValueError(f"unknown weight method: {method}")
        weights = [1.0 / len(sleeves)] * len(sleeves)
        for _ in range(5000):
            marginal = [
                sum(covariance[i][j] * weights[j] for j in range(len(sleeves)))
                for i in range(len(sleeves))
            ]
            contributions = [weights[i] * marginal[i] for i in range(len(sleeves))]
            total = sum(contributions)
            if total <= 1e-15 or any(
                x <= 0.0 or not math.isfinite(x) for x in contributions
            ):
                return (*equal_weights(sleeves)[0:1], "FALLBACK_ERC_NONPOSITIVE_RISK")
            target = total / len(sleeves)
            if max(abs(x - target) for x in contributions) <= 1e-12:
                return normalize(dict(zip(sleeves, weights))), "PRIOR_ERC"
            weights = list(
                normalize(
                    {
                        s: weights[i] * target / contributions[i]
                        for i, s in enumerate(sleeves)
                    }
                ).values()
            )
        return (*equal_weights(sleeves)[0:1], "FALLBACK_ERC_NO_CONVERGENCE")
    except (ArithmeticError, ValueError, OverflowError):
        return (*equal_weights(sleeves)[0:1], "FALLBACK_SINGULAR_COVARIANCE")


def allocate_integer_tickets(
    mode: str,
    fraction: float,
    preissue_bankroll_yuan: int,
    native_ticket_caps: dict[str, int],
    weights: dict[str, float],
) -> dict[str, object]:
    """Freeze the simultaneous, capped integer ticket allocator.

    It uses a deterministic weighted water-fill: repeatedly distribute the
    remaining whole-ticket budget over uncapped sleeves by normalized weights;
    floor, then award fractional remainders in sleeve-id order.  Sleeves that
    hit their native cap are removed and the residual is re-water-filled.
    """
    if mode not in {
        "NATIVE_REQUEST_CONTROL",
        "FIXED_100K_NOTIONAL",
        "COMPOUNDING_BANKROLL",
    }:
        raise ValueError(f"unknown funding mode: {mode}")
    if not 0.0 < fraction <= 1.0 or preissue_bankroll_yuan < 0:
        raise ValueError("invalid fraction or preissue bankroll")
    cap_total = sum(max(0, value) for value in native_ticket_caps.values())
    if mode == "NATIVE_REQUEST_CONTROL":
        mode_notional = fraction * cap_total * TICKET_STAKE_YUAN
    elif mode == "FIXED_100K_NOTIONAL":
        mode_notional = fraction * INITIAL_BANKROLL_YUAN
    else:
        mode_notional = fraction * preissue_bankroll_yuan
    budget_yuan = min(mode_notional, float(preissue_bankroll_yuan))
    budget_tickets = int(math.floor(budget_yuan / TICKET_STAKE_YUAN))
    assigned = {s: 0 for s in sorted(native_ticket_caps)}
    reasons: set[str] = set()
    if cap_total == 0:
        reasons.add("NO_BET_NATIVE_ZERO_REQUEST")
    if budget_tickets == 0 and cap_total:
        reasons.add("NO_BET_BUDGET_LT_TICKET")
    remaining = min(budget_tickets, cap_total)
    if budget_tickets < int(math.ceil(mode_notional / TICKET_STAKE_YUAN)):
        reasons.add("SCALED_BY_PREISSUE_BANKROLL")
    if remaining < cap_total and cap_total:
        reasons.add("SCALED_BY_MODE_NOTIONAL")
    while remaining:
        free = [
            s for s in sorted(assigned) if assigned[s] < max(0, native_ticket_caps[s])
        ]
        if not free:
            break
        free_weights = normalize({s: weights.get(s, 0.0) for s in free})
        quotas = {
            s: min(native_ticket_caps[s] - assigned[s], remaining * free_weights[s])
            for s in free
        }
        increments = {
            s: min(native_ticket_caps[s] - assigned[s], int(math.floor(quotas[s])))
            for s in free
        }
        placed = sum(increments.values())
        if placed == 0:
            # One-ticket residual round.  Ties are always sleeve_id ascending.
            winner = sorted(
                free, key=lambda s: (-(quotas[s] - math.floor(quotas[s])), s)
            )[0]
            increments[winner] = 1
            placed = 1
        for s, count in increments.items():
            assigned[s] += count
        remaining -= placed
    actual_tickets = sum(assigned.values())
    if actual_tickets < min(budget_tickets, cap_total) and cap_total:
        reasons.add("CAPACITY_EXHAUSTED_RETAIN_CASH")
    if (
        any(
            assigned[s] == native_ticket_caps[s] and native_ticket_caps[s] > 0
            for s in assigned
        )
        and actual_tickets < cap_total
    ):
        reasons.add("CAP_BOUND_WATERFILL")
    actual_stake = actual_tickets * TICKET_STAKE_YUAN
    return {
        "mode_notional_yuan": mode_notional,
        "issue_budget_yuan": budget_yuan,
        "requested_ticket_count": cap_total,
        "actual_ticket_count_by_sleeve": assigned,
        "actual_total_stake_yuan": actual_stake,
        "retained_cash_yuan": preissue_bankroll_yuan - actual_stake,
        "reason_codes": "|".join(sorted(reasons)) or "FUNDED_AS_REQUESTED",
    }


def funding_contract() -> dict[str, object]:
    return {
        "initial_bankroll_yuan": INITIAL_BANKROLL_YUAN,
        "ticket_stake_yuan": TICKET_STAKE_YUAN,
        "position_budget_fractions": [x / 100 for x in POSITION_FRACTIONS],
        "modes": {
            "NATIVE_REQUEST_CONTROL": "mode_notional=fraction × sum(native requested ticket caps) × ¥2",
            "FIXED_100K_NOTIONAL": "mode_notional=fraction × ¥100,000; notional does not reinvest",
            "COMPOUNDING_BANKROLL": "mode_notional=fraction × preissue bankroll",
        },
        "integer_allocator": {
            "universal_budget": "issue_budget=min(mode_notional, preissue_bankroll); ticket_budget=floor(issue_budget/¥2)",
            "raw_ticket_target": "iterative normalized sleeve weight × remaining ticket budget, hard-capped at native requested tickets",
            "rounding": "each water-fill pass floors capped quotas, then gives one residual ticket to largest fractional quota; ties sleeve_id ascending",
            "cap_bound_leftover": "remove sleeves at native cap and repeat weighted water-fill until no ticket budget or no capacity; retain any unspendable cash",
            "minimum": "budget under ¥2 or all native requests zero is NO_BET, zero flow not a loss",
            "concurrency": "all sleeve tickets for an issue are funded before that issue's outcomes; no payout recycling, deposit, loan, or top-up",
            "invariants": [
                "actual_total_stake <= preissue_bankroll",
                "actual_ticket_count_by_sleeve <= native_requested_ticket_count",
                "retained_cash=preissue_bankroll-actual_total_stake >= 0",
            ],
            "reason_codes": [
                "FUNDED_AS_REQUESTED",
                "SCALED_BY_MODE_NOTIONAL",
                "SCALED_BY_PREISSUE_BANKROLL",
                "CAP_BOUND_WATERFILL",
                "CAPACITY_EXHAUSTED_RETAIN_CASH",
                "NO_BET_NATIVE_ZERO_REQUEST",
                "NO_BET_BUDGET_LT_TICKET",
            ],
            "gate_b_requirement": "settle each allocated ticket with native per-ticket tax; fail closed if no exact ticket-level settlement bridge exists",
        },
    }


def methodology_contract() -> dict[str, object]:
    return {
        "membership": "all nonempty subsets of every ELIGIBLE_COMPLETE_TRACE or ELIGIBLE_EXPLORATORY_FAMILY frozen sleeve family; no Stage 1–3 selection, direction, ticket, M, seed, or support construction changes",
        "attribution": {
            "upstream": "report each inherited Stage-1→3 sleeve path unchanged at native request alongside its actual Stage-4 funded flow",
            "stage4": "attribute size/downscale/cash/weight lift against the same-sleeve native-request and equal-weight controls; do not mislabel it as selection, direction, or ticket-construction lift",
            "covariance": "report cross-sleeve concurrent issue covariance and diversification attribution separately from within-sleeve ticket outcomes",
        },
        "weight_model": {
            "issue_return": "pre-tax sleeve net / actual sleeve stake; only actual stake > ¥0 produces an active observation",
            "history": "strictly prior chronological full-calendar issues. NO_BET/unavailable stays a zero-flow path row but is absent from active-return samples. Dynamic methods require 52 most-recent common active observations for every participating sleeve.",
            "covariance": "unbiased sample covariance of 52 common active issue returns, then 10% diagonal shrinkage",
            "constraints": "long-only weights, each >=0, sum exactly 1; current issue is never in history",
            "PRIOR_INVERSE_VOL": "w_i ∝ 1/vol_i, vol_i=sqrt(shrunk covariance_ii); vol floor 1e-12",
            "PRIOR_ERC": "start equal; multiplicative risk-contribution iteration w_i←normalize(w_i×target_RC/RC_i), max 5000 iterations, convergence max|RC-target|<=1e-12",
            "PRIOR_DRAWDOWN_AWARE": "w_i ∝ 1/(vol_i×(1+max prior common-active compounded drawdown_i))",
            "fallbacks": [
                "under 52 common active observations",
                "zero/nonfinite volatility",
                "singular/nonpositive ERC risk contributions",
                "ERC no convergence",
            ],
            "fallback_action": "EQUAL_WEIGHT with explicit per-issue fallback reason",
        },
        "weight_methods": [
            "EQUAL_WEIGHT",
            "PRIOR_INVERSE_VOL",
            "PRIOR_ERC",
            "PRIOR_DRAWDOWN_AWARE",
        ],
        "M_rule": "UPSTREAM_FROZEN_FIXED: FULL=2187, MODEL=512, Q=192. No new M scan or post-outcome M choice.",
        "primary_hypothesis": {
            "id": "H1_STAGE4_FIXED_THREE_SLEEVE_EQUAL_NATIVE",
            "candidate": "#170 BEST_FULL_FULL + MODEL_SOURCE_MODEL_CAP1_M512 + Q_SOURCE_Q_TOP_MASS_M192",
            "mode": "NATIVE_REQUEST_CONTROL",
            "position_fraction": 1.0,
            "weights": "EQUAL_WEIGHT",
            "comparison": "absolute pre-tax ¥100k path plus matched lift versus B170 BEST_FULL/FULL on exact common support and actual funding convention",
            "decision": "a positive claim requires paired sequential lower bound >0, all primary support/capital controls, and later independent held-out/forward validation",
        },
        "multiplicity": {
            "frontier_status": "all non-primary catalog combinations are exploratory/descriptive; raw Pareto or best-cell rank is never Edge evidence",
            "families": [
                "catalog_sleeve_family",
                "portfolio_membership",
                "weight_method",
                "capital_mode",
                "position_fraction",
            ],
            "positive_inference": "20,000 paired stationary-block bootstrap max-T family-wise adjusted lower bounds at alpha=0.05; test all candidate-minus-control lifts within each frozen family",
            "winner_rule": "screen all cells, but no ladder advancement unless the preregistered H1 or a family-wise adjusted candidate passes strict matched PI review",
            "negative_rule": "negative/no-promotion results report full frontier and may use proportionate descriptive evidence",
        },
        "sequential_inference": {
            "primary_estimand": "original strict chronological walk-forward replay; recompute weights, funding, cash, equity, drawdown and all state inside every replay",
            "path_bootstrap": "paired stationary block bootstrap, 20,000 replicates, expected block length 12 issues, seed 192001, each candidate/control shares exact resampled blocks and replays the complete state machine",
            "moving_block_sensitivity": "paired moving block bootstrap, block lengths 6, 12 and 20 chronological issues; full state replay",
            "iid_diagnostic": "IID issue bootstrap is ROI-only diagnostic and must not support bankroll, drawdown, recovery, dynamic-weight or compounded-growth claims",
        },
        "bootstrap": {
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
            "draw": "common deterministic issue-resample matrix paired across every portfolio",
        },
        "stability": ["YEAR", "FOLD", "LOYO", "EX_LARGEST_ISSUE", "EX_LARGEST_YEAR"],
        "gate_b_outputs": [
            "per_issue_paths",
            "ending_capital",
            "fundability",
            "first_unfundable",
            "drawdown",
            "time_under_water",
            "recovery",
            "ruin",
            "covariance_attribution",
            "pre_tax_primary_tax_reference",
        ],
        "chart_sources": [
            "issue_equity_paths",
            "capital_utilization_frontier",
            "risk_return_frontier",
            "pairwise_covariance",
            "weight_history",
            "fundability_waterfall",
            "bootstrap_and_stability",
        ],
        "challenger_case": [
            "survivor/winner catalog selection",
            "parameter-search/multiple-comparison luck",
            "outcome/oracle leakage",
            "native versus exact-common support",
            "fewer bets/turnover/retained cash",
            "ex-post covariance/weight fitting",
            "single issue/year/payout cluster",
            "simpler-control explanation",
            "descriptive frontier overstated as Edge",
        ],
    }


def eligibility_ledger() -> list[dict[str, str]]:
    rows = [
        {
            "candidate_id": sleeve,
            "source_package": "bj170_gate_a_preoutcome_v2",
            "identity_source": "identity_freeze.csv.gz + identity_allocation_digest.csv.gz",
            "inherited_M_seed_support": "M fixed by arm; deterministic/no-seed as declared",
            "decision": "ELIGIBLE_COMPLETE_TRACE",
            "frontier_role": "CONFIRMATORY_FIXED_SLEEVE",
            "reason": "complete frozen Stage-1→3 selection/direction/ticket trace; exact requested tickets and M bound",
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        for sleeve, _, _, _ in SLEEVES
    ]
    rows.extend(
        [
            {
                "candidate_id": "BJ137_COMPLETE_ISSUE_Q_SAMPLING",
                "source_package": "bj137_gate_a_preoutcome_v2",
                "identity_source": "n7_identities.csv.gz + sampler_plan.csv",
                "inherited_M_seed_support": "frozen complete-issue sampling M/seed plan",
                "decision": "ELIGIBLE_EXPLORATORY_FAMILY",
                "frontier_role": "EXPLORATORY_SOURCE_FAMILY",
                "reason": "complete pre-outcome selection/direction/ticket source; every raw cell remains multiplicity-controlled",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ145_ALLOCATION_MECHANISMS",
                "source_package": "bj145_gate_a_preoutcome_v8",
                "identity_source": "identity_catalog.csv.gz + allocation_plan.csv.gz",
                "inherited_M_seed_support": "frozen M grid/mechanism/cap/repeat plans",
                "decision": "COMPOSABLE_NOT_STANDALONE",
                "frontier_role": "ALLOCATION_COMPONENT_ONLY",
                "reason": "allocation source has no independent selector chain; may only pair with an eligible frozen Stage-1→3 source",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ148_DENSE_M_COMMON_SUPPORT",
                "source_package": "bj148_gate_a_preoutcome_v1",
                "identity_source": "common_support_identities.csv.gz + sampling_plan.csv",
                "inherited_M_seed_support": "dense M grid and frozen three-seed sampling plan",
                "decision": "ELIGIBLE_EXPLORATORY_FAMILY",
                "frontier_role": "EXPLORATORY_DENSE_M",
                "reason": "accepted dense-M evidence; terminal no-stable-sweet-spot makes it descriptive, never ladder replacement",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ151_FIXED_CANDIDATE_REPRODUCTION",
                "source_package": "bj151_gate_a_preoutcome_v1",
                "identity_source": "candidate_identities.csv.gz + sampling_plan.csv",
                "inherited_M_seed_support": "fixed candidate dense-M plus frozen seed plan",
                "decision": "ELIGIBLE_EXPLORATORY_FAMILY",
                "frontier_role": "EXPLORATORY_FIXED_REPRODUCTION",
                "reason": "complete fixed reproduction; not independent validation and cannot become an accepted ladder head",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ159_SELECTED_WOR_N2_N10",
                "source_package": "bj159_gate_a_preoutcome_v2r1",
                "identity_source": "identity_catalog.csv.gz + sampling_plan.csv",
                "inherited_M_seed_support": "N2–N10, M={32,64,128}, seeds 137001–137003",
                "decision": "ELIGIBLE_EXPLORATORY_FAMILY",
                "frontier_role": "EXPLORATORY_COMPLETE_CHAIN",
                "reason": "complete issue-level chain but same-window positives require independent validation",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ167_SELECTOR_ALLOCATION_ATLAS",
                "source_package": "bj167_gate_a_strategy_atlas_v3r1",
                "identity_source": "selector_identities shards + allocation_grid.csv",
                "inherited_M_seed_support": "full frozen selector/allocation M/seed/support surface",
                "decision": "ELIGIBLE_EXPLORATORY_FAMILY",
                "frontier_role": "EXPLORATORY_ATLAS",
                "reason": "complete Stage-1→3 atlas; search family is preserved and must receive multiplicity control",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ176_THREE_SLEEVE_RISK_BRIDGE",
                "source_package": "bj176_issue_equity_risk_v1",
                "identity_source": "three fixed #170 sleeves only",
                "inherited_M_seed_support": "BEST_FULL/FULL, MODEL/M512, Q/M192",
                "decision": "CONTROL_AND_CONVENTION_ONLY",
                "frontier_role": "RISK_BASELINE_BRIDGE",
                "reason": "accepted settled risk convention bridge, not an independently selected sleeve",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ190_SPARSE_DIVERGENCE",
                "source_package": "bj190_gate_b_sparse_divergence_v1",
                "identity_source": "terminal identity only",
                "inherited_M_seed_support": "as terminal package",
                "decision": "EXCLUDED_NOT_SLEEVE",
                "frontier_role": "EXCLUDED",
                "reason": "terminal strict promotion count is zero; coverage-limited diagnostic is not an eligible complete capital sleeve",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "candidate_id": "BJ193_FULL_DYNAMIC_CHAIN",
                "source_package": "bj193_gate_b_regime_meta_policy_v2",
                "identity_source": "terminal identity only",
                "inherited_M_seed_support": "as terminal package",
                "decision": "EXCLUDED_NEGATIVE_NON_PROMOTED",
                "frontier_role": "EXCLUDED",
                "reason": "PI excludes negative non-promoted FULL_DYNAMIC_CHAIN; package supplies interface/accounting lessons only",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
        ]
    )
    return rows


def baseline_registry() -> list[dict[str, object]]:
    return [
        {
            "baseline_id": "B167_BEST_FULL_NATIVE_LADDER_HEAD",
            "source_package": "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1",
            "source_gate_a_binding": "bj167_gate_a_strategy_atlas_v3r1",
            "source_gate_b_binding": "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1",
            "identity": "BEST_FULL/FULL_ENUMERATED",
            "support_context": "NATIVE_BEST_FULL",
            "pre_tax_roi": -0.0947,
            "role": "ACCEPTED_LADDER_HEAD_CONTEXT",
            "comparison_rule": "context only; never substitute for exact matched-support lift",
        },
        {
            "baseline_id": "B170_BEST_FULL_THREE_WAY_BRIDGE",
            "source_package": "bj170_gate_b_selector_allocator_stack_v1",
            "source_gate_a_binding": "bj170_gate_a_preoutcome_v2",
            "source_gate_b_binding": "bj170_gate_b_selector_allocator_stack_v1",
            "identity": "BEST_FULL/FULL_ENUMERATED",
            "support_context": "THREE_WAY_ALL",
            "pre_tax_roi": -0.0909,
            "role": "EXACT_THREE_WAY_MATCHED_BRIDGE",
            "comparison_rule": "candidate and control must share exact issue support, capital mode, fraction, preissue bankroll and actual funding convention",
        },
        {
            "baseline_id": "MATCHED_STRONGEST_STANDALONE",
            "source_package": "GATE_B_DERIVED",
            "source_gate_a_binding": "GATE_A_FROZEN_SOURCE_BINDINGS",
            "source_gate_b_binding": "GATE_B_DERIVED",
            "identity": "max standalone on candidate exact support",
            "support_context": "CANDIDATE_EXACT_SUPPORT",
            "pre_tax_roi": "DERIVED_GATE_B",
            "role": "MANDATORY_MATCHED_CONTROL",
            "comparison_rule": "candidate-minus-control published with absolute metrics",
        },
        {
            "baseline_id": "MATCHED_EQUAL_WEIGHT",
            "source_package": "GATE_B_DERIVED",
            "source_gate_a_binding": "GATE_A_FROZEN_SOURCE_BINDINGS",
            "source_gate_b_binding": "GATE_B_DERIVED",
            "identity": "same sleeves, equal weights",
            "support_context": "CANDIDATE_EXACT_SUPPORT",
            "pre_tax_roi": "DERIVED_GATE_B",
            "role": "MANDATORY_MATCHED_CONTROL",
            "comparison_rule": "candidate-minus-control published with absolute metrics",
        },
    ]


def frontier_contract(eligibility: list[dict[str, str]]) -> dict[str, object]:
    """Define the complete, immutable Gate-B sleeve frontier without settling it.

    A source-family row is not a permission to silently pick a successful cell.
    Gate B must materialize every frozen plan/grid identity that the ledger calls
    eligible, carry its inherited support/M/seed tuple forward, and preserve an
    explicit inapplicability record for the two excluded sources.
    """
    complete = [
        row["candidate_id"]
        for row in eligibility
        if row["decision"] in {"ELIGIBLE_COMPLETE_TRACE", "ELIGIBLE_EXPLORATORY_FAMILY"}
    ]
    return {
        "eligible_candidate_sources": complete,
        "eligible_source_count": len(complete),
        "materialization_rule": (
            "Gate B enumerates every immutable source-plan/grid identity from each "
            "eligible source, retaining exact selector, support, M, seed, mechanism, "
            "cap, weight source and ticket multiplicity. It writes every nonempty "
            "same-support portfolio combination permitted by those identities."
        ),
        "component_rule": (
            "BJ145_ALLOCATION_MECHANISMS is composable only: pair each frozen "
            "allocation tuple with an eligible complete selector identity; never "
            "invent a selector or overwrite its inherited tuple."
        ),
        "comparison_rule": (
            "Each portfolio row includes absolute pre-tax capital/path results and "
            "matched lifts to B167/B170 where exact support and funding permit, "
            "strongest standalone on its exact support, and equal-weight same sleeves."
        ),
        "screening_rule": (
            "The full materialized frontier is exploratory except the fixed H1. "
            "Raw rank, raw Pareto membership or a best descriptive cell cannot be "
            "reported as Edge; all positive claims require the frozen family-wise "
            "sequential inference and later independent validation."
        ),
        "excluded_source_records": [
            {
                "candidate_id": row["candidate_id"],
                "decision": row["decision"],
                "reason": row["reason"],
            }
            for row in eligibility
            if row["frontier_role"] == "EXCLUDED"
        ],
    }


def output_schema() -> dict[str, object]:
    """Manifest-covered Gate-B deliverable schema and equations."""
    return {
        "issue_ledger": {
            "key": [
                "portfolio_id",
                "mode",
                "position_fraction",
                "weight_method",
                "calendar_index",
                "issue_instance",
            ],
            "fields": [
                "preissue_bankroll_yuan",
                "mode_notional_yuan",
                "issue_budget_yuan",
                "requested_stake_yuan",
                "actual_stake_yuan",
                "scaled_stake_yuan",
                "skipped_stake_yuan",
                "retained_cash_yuan",
                "reason_codes",
                "pre_tax_gross_yuan",
                "pre_tax_net_yuan",
                "tax_yuan",
                "postissue_bankroll_yuan",
                "ruin_flag",
            ],
            "formulas": [
                "actual_stake=sum(actual ticket count)×¥2",
                "postissue_bankroll=preissue_bankroll+pre_tax_net",
                "turnover=cumulative actual_stake",
                "all sleeve flows in an issue fund concurrently",
            ],
        },
        "capital_summary": {
            "fields": [
                "starting_bankroll_yuan",
                "ending_bankroll_yuan",
                "minimum_bankroll_yuan",
                "minimum_required_start_yuan",
                "fundable_issue_count",
                "first_unfundable_issue",
                "scaled_stake_yuan",
                "skipped_stake_yuan",
                "cash_yuan",
                "turnover_yuan",
                "pre_tax_roi",
                "tax_adjusted_roi",
                "ruin_flag",
            ],
            "formulas": [
                "minimum_bankroll=min(preissue_bankroll,postissue_bankroll) over full 348 calendar",
                "minimum_required_start is smallest b found by deterministic integer-yuan bisection for zero unfundable non-NO_BET requests under same policy",
                "ruin_flag=1 iff any postissue_bankroll < ¥2 while a positive native request exists",
                "pre_tax_roi=sum(pre_tax_net)/sum(actual_stake); blank if zero actual stake",
            ],
        },
        "weight_history": {
            "fields": [
                "portfolio_id",
                "issue_instance",
                "weight_method",
                "sleeve_id",
                "weight",
                "history_active_observation_count",
                "estimator_status",
                "fallback_reason",
                "covariance_hash",
            ],
            "formulas": [
                "weights use only issues strictly before issue_instance",
                "fallback_rate=count(non-primary estimator_status)/348",
                "NO_BET/unavailable excluded from active observation but retained as capital zero flow",
            ],
        },
        "dependence": {
            "fields": [
                "portfolio_id",
                "sleeve_left",
                "sleeve_right",
                "prior_covariance",
                "prior_correlation",
                "downside_correlation",
                "tail_co_loss_count",
                "concurrent_issue_count",
                "diversification_attribution_yuan",
            ],
            "formulas": [
                "downside_correlation=corr(min(r_left,0),min(r_right,0)) over common active returns; blank for <2/nonpositive variance",
                "tail_co_loss_count=count both returns in their own prior 10% lower tail",
                "diversification_attribution=portfolio pre-tax net minus sum(weighted matched standalone nets), reported separately from retained cash",
            ],
        },
        "holding_metrics": {
            "fields": [
                "portfolio_id",
                "mode",
                "position_fraction",
                "ending_bankroll_yuan",
                "max_drawdown_yuan",
                "max_drawdown_fraction",
                "drawdown_duration_issues",
                "time_under_water_issues",
                "recovery_issue",
                "loss_streak_calendar",
                "loss_streak_active",
                "miss_streak_calendar",
                "miss_streak_active",
                "rolling_loss_5_yuan",
                "rolling_loss_10_yuan",
                "rolling_loss_20_yuan",
                "ruin_flag",
                "near_ruin_flag",
                "sharpe",
                "sortino",
                "calmar",
            ],
            "formulas": [
                "loss=pre_tax_net<0; miss=actual_stake>0 and pre_tax_gross=0; calendar streak includes zero-flow rows, active streak skips zero-flow rows",
                "rolling loss W=sum(min(pre_tax_net,0)) over trailing calendar W={5,10,20}; report worst and frequency",
                "drawdown=running equity peak minus postissue bankroll; duration/time-under-water count chronological issues below peak; recovery is first later issue reaching former peak, blank if absent",
                "near_ruin_flag=1 iff min bankroll < ¥2×max native issue ticket count; sharpe=mean calendar bank return/sample sd×sqrt(issue frequency/year), sortino divides by downside RMS, calmar=annualized compounded bank return/max drawdown fraction; blank where denominator zero",
            ],
        },
        "bootstrap_stability": {
            "fields": [
                "target_id",
                "paired_control_id",
                "bootstrap_replicates",
                "bootstrap_seed",
                "paired_growth_delta_low",
                "YEAR",
                "FOLD",
                "LOYO",
                "EX_LARGEST_ISSUE",
                "EX_LARGEST_YEAR",
                "fallback_rate",
            ],
            "formulas": [
                "YEAR/FOLD replays retain chronological order within subset; LOYO removes every issue from one year then recomputes state; ex-largest issue/year removes the largest signed pre-tax-net contributor (year aggregates first); decision panels use same full-calendar zero-flow convention"
            ],
        },
        "baseline_lift": {
            "fields": [
                "candidate_id",
                "control_id",
                "support_hash",
                "capital_mode",
                "position_fraction",
                "actual_funding_hash",
                "absolute_ending_bankroll_yuan",
                "absolute_pre_tax_roi",
                "candidate_minus_control_bankroll_yuan",
                "candidate_minus_control_pre_tax_roi",
                "ladder_decision",
            ],
            "formulas": [
                "all comparisons require identical issue support, mode, fraction, starting capital, available bankroll and actual funding convention",
                "publish absolute path and lift together; blank lift if exact matching is impossible",
                "ladder_decision=ADVANCES only after strict matched PI terminal review",
            ],
        },
        "challenger_case": {
            "fields": [
                "candidate_id",
                "alternative_explanation",
                "test_id",
                "result",
                "decision_impact",
            ],
            "formulas": [
                "each headline candidate receives survivor/search, leakage, support, turnover/cash, covariance fitting, largest issue/year, payout cluster and simple-control tests",
                "cash-only smoothing is separately labeled risk reduction, never diversification edge",
            ],
        },
        "chart_sources": [
            "chart_source_issue_equity.csv.gz",
            "chart_source_capital_frontier.csv",
            "chart_source_risk_return.csv",
            "chart_source_dependence.csv",
            "chart_source_weight_history.csv.gz",
            "chart_source_fundability.csv",
            "chart_source_bootstrap_stability.csv",
        ],
    }


def write_package(output: Path) -> None:
    bindings = {name: verify_source(spec) for name, spec in EXPECTED_SOURCES.items()}
    rows, calendar, _ = source_inputs()
    traces = sleeve_trace_registry(rows)
    eligibility = eligibility_ledger()
    baselines = baseline_registry()
    frontier = frontier_contract(eligibility)
    schemas = output_schema()
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        fields = list(rows[0])
        write_csv(stage / "frozen_native_sleeve_requests.csv", fields, rows)
        cal_fields = [
            "calendar_index",
            "issue",
            "year",
            "fold",
            "issue_instance",
            "first_kickoff_ts",
            "strict_three_way_common",
            "outcome_boundary",
        ]
        write_csv(
            stage / "full_calendar.csv",
            cal_fields,
            [{k: r[k] for k in cal_fields} for r in calendar],
        )
        write_csv(
            stage / "strict_three_way_calendar.csv",
            cal_fields,
            [
                {k: r[k] for k in cal_fields}
                for r in calendar
                if r["strict_three_way_common"] == "1"
            ],
        )
        catalog = []
        for sleeve, alias, arm, rationale in SLEEVES:
            example = next(r for r in rows if r["sleeve_id"] == sleeve)
            catalog.append(
                {
                    k: example[k]
                    for k in [
                        "sleeve_id",
                        "selector_alias",
                        "selector_id",
                        "allocation_arm",
                        "M",
                        "mechanism",
                        "cap",
                        "weight_source",
                    ]
                }
                | {"rationale": rationale, "outcome_boundary": OUTCOME_BOUNDARY}
            )
        write_csv(stage / "sleeve_catalog.csv", list(catalog[0]), catalog)
        write_csv(stage / "sleeve_trace_registry.csv", list(traces[0]), traces)
        write_csv(
            stage / "sleeve_eligibility_ledger.csv", list(eligibility[0]), eligibility
        )
        write_csv(stage / "baseline_registry.csv", list(baselines[0]), baselines)
        (stage / "frontier_contract.json").write_text(
            json.dumps(frontier, indent=2, sort_keys=True) + "\n"
        )
        (stage / "funding_algorithm.json").write_text(
            json.dumps(funding_contract(), indent=2, sort_keys=True) + "\n"
        )
        (stage / "inference_contract.json").write_text(
            json.dumps(
                {
                    "primary_hypothesis": methodology_contract()["primary_hypothesis"],
                    "multiplicity": methodology_contract()["multiplicity"],
                    "sequential_inference": methodology_contract()[
                        "sequential_inference"
                    ],
                    "challenger_case": methodology_contract()["challenger_case"],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        (stage / "output_schema.json").write_text(
            json.dumps(schemas, indent=2, sort_keys=True) + "\n"
        )
        card = {
            "contract": CONTRACT,
            "version": VERSION,
            "issue": 192,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_STAGE4_CAPITAL_PORTFOLIO_FREEZE",
            "outcome_boundary": OUTCOME_BOUNDARY,
            "source_binding": bindings,
            "sleeve_catalog": catalog,
            "sleeve_trace_registry": traces,
            "eligibility_ledger": eligibility,
            "frontier_contract": frontier,
            "baseline_registry": baselines,
            "full_calendar": {
                "source": "#137 canonical census/#170 all three frozen request rows",
                "issue_count": len(calendar),
                "chronological_sort": "first_kickoff_ts, issue_instance",
                "zero_flow": "retain NO_BET and Gate-B unavailable rows as zero flow; neither is a loss",
            },
            "strict_three_way_calendar": {
                "source": "#170 THREE_WAY_ALL",
                "issue_count": sum(
                    r["strict_three_way_common"] == "1" for r in calendar
                ),
                "usage": "matched attribution only; never truncate capital/holding paths",
            },
            "funding_contract": funding_contract(),
            "methodology_contract": methodology_contract(),
            "output_schema": schemas,
            "denominator": {
                "calendar_issue_count": len(calendar),
                "strict_three_way_issue_count": sum(
                    r["strict_three_way_common"] == "1" for r in calendar
                ),
                "native_sleeve_request_rows": len(rows),
                "fixed_sleeve_count": len(catalog),
                "catalog_identity_count": len(eligibility),
                "eligible_exploratory_family_count": sum(
                    row["decision"] == "ELIGIBLE_EXPLORATORY_FAMILY"
                    for row in eligibility
                ),
                "eligible_complete_source_count": frontier["eligible_source_count"],
                "position_fraction_count": len(POSITION_FRACTIONS),
            },
            "gate_b_status": "NOT_RUN_AND_NOT_AUTHORIZED_PENDING_PI_GATE_A_ACCEPTANCE",
            "promotion_boundary": "Historical results cannot authorize purchase, betting, production or promotion. Any candidate requires PI review plus independent held-out/forward validation.",
        }
        (stage / "gate_a_card.json").write_text(
            json.dumps(card, indent=2, sort_keys=True) + "\n"
        )
        (stage / "README.md").write_text(
            "# #192 Gate A\n\nImmutable outcome-unexposed Stage-4 capital portfolio freeze.  See `gate_a_card.json`.\n"
        )
        # CONTENT_IDENTITY binds the scientific payloads.  SHA256SUMS then
        # covers that identity document as well as every payload (but cannot
        # recursively cover itself), matching the repository package contract.
        payload = {
            p.name: sha256_file(p) for p in sorted(stage.iterdir()) if p.is_file()
        }
        content = {
            "contract": CONTRACT,
            "version": VERSION,
            "payload_sha256": payload,
            "content_identity_sha256": canonical_hash(payload),
        }
        (stage / "CONTENT_IDENTITY.json").write_text(
            json.dumps(content, indent=2, sort_keys=True) + "\n"
        )
        manifest = {
            p.name: sha256_file(p) for p in sorted(stage.iterdir()) if p.is_file()
        }
        (stage / "SHA256SUMS.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        if output.exists():
            raise RuntimeError(f"refusing to overwrite immutable output: {output}")
        os.replace(stage, output)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = p.parse_args()
    write_package(args.output.resolve())


if __name__ == "__main__":
    main()
