#!/usr/bin/env python3
"""Exact Stage-4 capital-path primitives for #192 Gate B.

This module deliberately starts at the only three sleeves whose frozen ticket
order is materialised in the #192 Gate-A package.  It does not use a scalar
ROI to resize a sleeve: every funded prefix is settled from the immutable
ticket order and its original per-ticket payout/tax lot.  Expanded-source
adapters are expected to feed the same :func:`replay_path` state machine; a
missing exact prefix adapter is a fail-closed condition, never a proportional
approximation.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


CONTRACT = "BJ-HIST-N7-STRATEGY-ENSEMBLE-001"
VERSION = "bj192-gate-b-v1"
TICKET_STAKE_YUAN = 2.0
INITIAL_BANKROLL_YUAN = 100_000.0

EXPECTED_GATE_A_MANIFEST = "6108defd857bf431bcaf55109df0e195b45aa754e8fd46f1db82d329102ff256"
EXPECTED_GATE_A_CONTENT = "66ce6f86703b31d710ad678b49287de3bc6b2c43a5b36c278e1369bdecd861d5"
EXPECTED_BJ176_MANIFEST = ""  # Filled only by the complete Gate-B publisher.
EXPECTED_BJ170_RUNNER = "f593dd92c1b2afcc81ce50c65d61c9511070190c95b5cef98a13b05843ce2713"

H1_SLEEVES = (
    "BEST_FULL_FULL",
    "MODEL_SOURCE_MODEL_CAP1_M512",
    "Q_SOURCE_Q_TOP_MASS_M192",
)
_H1_TICKET_BRIDGE: dict[tuple[str, str], "NativeIssueSleeve"] | None = None
PATH_IDENTITY = (
    "portfolio_id",
    "mode",
    "position_fraction",
    "weight_method",
    "normalization_method",
    "deployment_replicate_bundle_id",
)


def repo_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
GATE_A = ROOT / "results" / "bj192_gate_a_preoutcome_v8r1r2"
BJ170 = ROOT / "results" / "bj170_gate_b_selector_allocator_stack_v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def verify_package(directory: Path, manifest_digest: str, content_digest: str) -> dict[str, str]:
    """Verify both recursive coverage and the authoritative identity bytes."""
    if sha256_file(directory / "SHA256SUMS.json") != manifest_digest:
        raise RuntimeError(f"manifest drift: {directory.name}")
    if sha256_file(directory / "CONTENT_IDENTITY.json") != content_digest:
        raise RuntimeError(f"content identity drift: {directory.name}")
    manifest = json.loads((directory / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = sorted(p.name for p in directory.iterdir() if p.is_file() and p.name != "SHA256SUMS.json")
    if sorted(manifest) != actual:
        raise RuntimeError(f"manifest coverage drift: {directory.name}")
    for name, digest in manifest.items():
        if sha256_file(directory / name) != digest:
            raise RuntimeError(f"payload drift: {directory.name}/{name}")
    return manifest


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"module loader unavailable: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_gate_a() -> Any:
    """Load source utilities only after the exact Gate-A identity verifies."""
    verify_package(GATE_A, EXPECTED_GATE_A_MANIFEST, EXPECTED_GATE_A_CONTENT)
    return load_module(ROOT / "scripts" / "freeze_bj192_stage4_portfolio_gate_a.py", "bj192_gate_a")


def frozen_bj170_runner() -> Any:
    path = BJ170 / "settlement_runner.py"
    if sha256_file(path) != EXPECTED_BJ170_RUNNER:
        raise RuntimeError("#170 manifest-bound ticket settler drift")
    return load_module(path, "bj170_settlement_runner")


@dataclass(frozen=True)
class TicketLot:
    rank: int
    tax_lot_id: str
    portfolio_id: str
    ticket_ordinal: int
    outcome_available: bool
    truth_ordinal: int
    payout_yuan: float

    @property
    def is_winner(self) -> bool:
        return self.outcome_available and self.ticket_ordinal == self.truth_ordinal

    @property
    def gross_yuan(self) -> float:
        return self.payout_yuan if self.is_winner else 0.0

    @property
    def tax_yuan(self) -> float:
        return self.payout_yuan * 0.20 if self.is_winner and self.payout_yuan >= 10_000 else 0.0


@dataclass(frozen=True)
class NativeIssueSleeve:
    sleeve_id: str
    issue_instance: str
    status: str
    requested_ticket_count: int
    atomic: bool
    lots: tuple[TicketLot, ...]

    def settle_prefix(self, count: int) -> dict[str, float | int | str]:
        if count < 0 or count > self.requested_ticket_count:
            raise RuntimeError(f"invalid funded prefix: {self.sleeve_id}/{self.issue_instance}")
        if self.atomic and count not in (0, self.requested_ticket_count):
            raise RuntimeError(f"partial atomic FULL funding: {self.issue_instance}")
        if count and self.status != "SETTLED":
            raise RuntimeError(f"funding unavailable sleeve: {self.sleeve_id}/{self.issue_instance}")
        lots = self.lots[:count]
        gross = sum(lot.gross_yuan for lot in lots)
        tax = sum(lot.tax_yuan for lot in lots)
        return {
            "actual_ticket_count": count,
            "actual_stake_yuan": count * TICKET_STAKE_YUAN,
            "gross_yuan": gross,
            "tax_yuan": tax,
            "pre_tax_net_yuan": gross - count * TICKET_STAKE_YUAN,
            "tax_adjusted_net_yuan": gross - tax - count * TICKET_STAKE_YUAN,
            "hit_ticket_count": sum(lot.is_winner for lot in lots),
            "funded_tax_lot_sha256": canonical_hash([lot.tax_lot_id for lot in lots]),
        }


def h1_ticket_bridge() -> dict[tuple[str, str], NativeIssueSleeve]:
    """Recreate Gate-A's H1 prefix ledger from the accepted #170 ticket replay.

    The rows in ``ticket_prefix_registry`` are immutable ordered tax lots.
    Their winning status/payout is reconstructed with #170's manifest-covered
    ticket settler rather than by rescaling an issue ROI.
    """
    global _H1_TICKET_BRIDGE
    if _H1_TICKET_BRIDGE is not None:
        return _H1_TICKET_BRIDGE
    gate = frozen_gate_a()
    runner = frozen_bj170_runner()
    frozen = runner.load_frozen_data()
    outcomes = runner.load_outcomes()
    records, _ = runner.settle_identities(frozen, outcomes)
    record_by_key = {
        (row["selector_alias"], row["issue_instance"], row["portfolio_id"], row["allocation_arm"]): row
        for row in records
    }
    requests = {
        (row["sleeve_id"], row["issue_instance"]): row
        for row in read_csv(GATE_A / "frozen_native_sleeve_requests.csv")
    }
    policy = {
        (row["sleeve_id"], row["issue_instance"], row["portfolio_id"]): row
        for row in read_csv(GATE_A / "ticket_prefix_policy_registry.csv")
    }
    aliases = {sleeve: alias for sleeve, alias, _, _ in gate.SLEEVES}
    arms = {sleeve: arm for sleeve, _, arm, _ in gate.SLEEVES}
    lots_by_key: dict[tuple[str, str], list[TicketLot]] = defaultdict(list)
    for row in read_gzip(GATE_A / "ticket_prefix_registry.csv.gz"):
        sleeve, issue = row["sleeve_id"], row["issue_instance"]
        if sleeve not in H1_SLEEVES:
            continue
        record = record_by_key.get((aliases[sleeve], issue, row["portfolio_id"], arms[sleeve]))
        if record is None:
            raise RuntimeError(f"unbound prefix identity: {sleeve}/{issue}/{row['portfolio_id']}")
        lots_by_key[(sleeve, issue)].append(
            TicketLot(
                rank=int(row["global_ticket_rank"]),
                tax_lot_id=row["tax_lot_id"],
                portfolio_id=row["portfolio_id"],
                ticket_ordinal=int(row["ticket_ordinal"]),
                outcome_available=bool(record["outcome_available"]),
                truth_ordinal=int(record["truth_ordinal"]),
                payout_yuan=float(record["payout_yuan"]),
            )
        )
    # FULL is intentionally absent from the partial-prefix stream: Gate A
    # binds it as an atomic whole-native block.  Materialise its immutable
    # ticket tax lots only for all-or-zero execution, never as a prefix.
    for (alias, issue, portfolio_id, arm), record in record_by_key.items():
        if alias != aliases["BEST_FULL_FULL"] or arm != arms["BEST_FULL_FULL"]:
            continue
        key = ("BEST_FULL_FULL", issue)
        for ordinal in range(2187):
            lots_by_key[key].append(
                TicketLot(
                    rank=len(lots_by_key[key]) + 1,
                    tax_lot_id=f"BEST_FULL_FULL:{issue}:{len(lots_by_key[key]) + 1}",
                    portfolio_id=portfolio_id,
                    ticket_ordinal=ordinal,
                    outcome_available=bool(record["outcome_available"]),
                    truth_ordinal=int(record["truth_ordinal"]),
                    payout_yuan=float(record["payout_yuan"]),
                )
            )
    bridge: dict[tuple[str, str], NativeIssueSleeve] = {}
    for key, req in requests.items():
        sleeve, issue = key
        if sleeve not in H1_SLEEVES:
            continue
        ordered = tuple(sorted(lots_by_key[key], key=lambda lot: lot.rank))
        requested = int(req["native_requested_ticket_count"])
        status = req["native_policy_status"]
        if requested != len(ordered):
            raise RuntimeError(f"prefix ticket denominator drift: {sleeve}/{issue}: {len(ordered)} != {requested}")
        if [lot.rank for lot in ordered] != list(range(1, requested + 1)):
            raise RuntimeError(f"noncontiguous frozen tax lots: {sleeve}/{issue}")
        if any(not lot.outcome_available for lot in ordered) and status == "SELECTED_PREOUTCOME":
            status = "UNAVAILABLE_CANONICAL_OUTCOME"
        bridge[key] = NativeIssueSleeve(
            sleeve_id=sleeve,
            issue_instance=issue,
            status="SETTLED" if status == "SELECTED_PREOUTCOME" else status,
            requested_ticket_count=requested,
            atomic=any(
                p["prefix_status"] == "WHOLE_NATIVE_OR_NO_BET"
                for pkey, p in policy.items()
                if pkey[:2] == key
            ),
            lots=ordered,
        )
    if len(bridge) != 3 * 348:
        raise RuntimeError(f"H1 bridge denominator drift: {len(bridge)}")
    _H1_TICKET_BRIDGE = bridge
    return bridge


def source_native_return(sleeve: NativeIssueSleeve) -> float | None:
    """Return only an active native observation for the prior weight estimator."""
    if sleeve.status != "SETTLED" or not sleeve.requested_ticket_count:
        return None
    row = sleeve.settle_prefix(sleeve.requested_ticket_count)
    return float(row["pre_tax_net_yuan"]) / float(row["actual_stake_yuan"])


def replay_path(
    *,
    sleeves: Sequence[str],
    mode: str,
    fraction: float,
    weight_method: str,
    normalization_method: str,
    bridge: dict[tuple[str, str], NativeIssueSleeve],
    calendar: Sequence[dict[str, str]],
    bundle_id: str = "DETERMINISTIC_H1",
) -> list[dict[str, object]]:
    """Run one strictly-prior, concurrent, capital-limited H1 state machine."""
    gate = frozen_gate_a()
    sleeves = tuple(sorted(sleeves))
    if not sleeves or set(sleeves) - set(H1_SLEEVES):
        raise ValueError("unknown or empty H1 sleeve subset")
    if mode == "NATIVE_REQUEST_CONTROL" and fraction != 1.0:
        raise ValueError("NATIVE_REQUEST_CONTROL requires a 100% fraction")
    portfolio_id = canonical_hash({"sleeves": sleeves, "stage": "H1_STAGE4"})
    history: list[dict[str, float | None]] = []
    bankroll = INITIAL_BANKROLL_YUAN
    output: list[dict[str, object]] = []
    for calendar_row in sorted(calendar, key=lambda row: (row["first_kickoff_ts"], row["issue_instance"])):
        issue = calendar_row["issue_instance"]
        issue_sleeves = {sleeve: bridge[(sleeve, issue)] for sleeve in sleeves}
        weights, weight_status = gate.dynamic_weights(weight_method, history, list(sleeves))
        observations = gate.active_common_history(history, list(sleeves))
        covariance = gate.covariance_matrix(observations, list(sleeves)) if len(observations) >= 52 else None
        requested_caps = {
            sleeve: item.requested_ticket_count if item.status == "SETTLED" else 0
            for sleeve, item in issue_sleeves.items()
        }
        native_stake = sum(count * TICKET_STAKE_YUAN for count in requested_caps.values())
        if mode == "NATIVE_REQUEST_CONTROL":
            raw_notional = native_stake
        elif mode == "SCALED_NATIVE_REQUEST":
            raw_notional = fraction * native_stake
        elif mode == "FIXED_100K_NOTIONAL":
            raw_notional = fraction * INITIAL_BANKROLL_YUAN
        elif mode == "COMPOUNDING_BANKROLL":
            raw_notional = fraction * bankroll
        else:
            raise ValueError(f"unknown funding mode: {mode}")
        normalization = gate.normalization_state(
            normalization_method,
            native_stake,
            bankroll,
            raw_notional,
            weight_method,
            weights,
            list(sleeves),
            covariance,
            len(observations),
        )
        if normalization["normalization_executable"]:
            funding = gate.allocate_integer_tickets(
                mode,
                fraction,
                int(math.floor(bankroll)),
                requested_caps,
                weights,
                {sleeve: item.atomic for sleeve, item in issue_sleeves.items()},
            )
            # The public allocator determines the mode budget; normalization is
            # a prior-only cap on that exact budget, therefore re-run it as a
            # deterministic scaled-native request without changing allocation
            # or ticket ordering.
            capped_budget = min(float(funding["issue_budget_yuan"]), float(normalization["normalized_mode_notional_yuan"]))
            capped_tickets = int(math.floor(capped_budget / TICKET_STAKE_YUAN))
            funding = gate.allocate_integer_tickets(
                "SCALED_NATIVE_REQUEST",
                1.0 if native_stake == 0 else min(1.0, capped_tickets * TICKET_STAKE_YUAN / native_stake),
                int(math.floor(bankroll)),
                requested_caps,
                weights,
                {sleeve: item.atomic for sleeve, item in issue_sleeves.items()},
            )
        else:
            funding = {"actual_ticket_count_by_sleeve": {s: 0 for s in sleeves}, "reason_codes": str(normalization["normalization_status"]), "mode_notional_yuan": raw_notional, "issue_budget_yuan": 0.0, "retained_cash_yuan": bankroll, "actual_total_stake_yuan": 0.0}
        settlements = {sleeve: issue_sleeves[sleeve].settle_prefix(int(funding["actual_ticket_count_by_sleeve"][sleeve])) for sleeve in sleeves}
        stake = sum(float(item["actual_stake_yuan"]) for item in settlements.values())
        gross = sum(float(item["gross_yuan"]) for item in settlements.values())
        tax = sum(float(item["tax_yuan"]) for item in settlements.values())
        net = gross - stake
        row = {
            "portfolio_id": portfolio_id,
            "mode": mode,
            "position_fraction": f"{fraction:.2f}",
            "weight_method": weight_method,
            "normalization_method": normalization_method,
            "deployment_replicate_bundle_id": bundle_id,
            "calendar_index": int(calendar_row["calendar_index"]),
            "issue_instance": issue,
            "preissue_bankroll_yuan": bankroll,
            "normalization_status": normalization["normalization_status"],
            "normalization_executable": normalization["normalization_executable"],
            "covariance_sleeve_order_json": normalization["covariance_sleeve_order_json"],
            "covariance_input_sha256": normalization["covariance_input_sha256"],
            "ex_ante_volatility": normalization["ex_ante_volatility"],
            "target_volatility": normalization["target_volatility"],
            "realized_capital_multiplier": normalization["realized_capital_multiplier"],
            "risk_budget_yuan": normalization["risk_budget_yuan"],
            "pre_normalization_mode_notional_yuan": normalization["pre_normalization_mode_notional_yuan"],
            "normalized_mode_notional_yuan": normalization["normalized_mode_notional_yuan"],
            "mode_notional_yuan": funding["mode_notional_yuan"],
            "issue_budget_yuan": funding["issue_budget_yuan"],
            "requested_stake_yuan": native_stake,
            "actual_stake_yuan": stake,
            "scaled_stake_yuan": max(0.0, native_stake - stake),
            "skipped_stake_yuan": max(0.0, native_stake - stake),
            "retained_cash_yuan": bankroll - stake,
            "reason_codes": f"{weight_status}|{funding['reason_codes']}",
            "pre_tax_gross_yuan": gross,
            "pre_tax_net_yuan": net,
            "tax_yuan": tax,
            "postissue_bankroll_yuan": bankroll + net,
            "ruin_flag": int(bankroll + net < TICKET_STAKE_YUAN and native_stake > 0),
            "sleeve_settlements": settlements,
        }
        if not math.isclose(stake, float(funding["actual_total_stake_yuan"]), abs_tol=1e-9):
            raise RuntimeError(f"funding/ticket reconciliation failure: {issue}")
        output.append(row)
        bankroll += net
        history.append({sleeve: source_native_return(item) for sleeve, item in issue_sleeves.items()})
    return output
