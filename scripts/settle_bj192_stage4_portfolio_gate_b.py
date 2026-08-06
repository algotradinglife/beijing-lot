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
import sqlite3
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
EXPECTED_BJ176_MANIFEST = "39316952296c2349f5da2f963d43c0baf0d812fba4eea967536a8b80bd57d5ee"
EXPECTED_BJ176_CONTENT = "94188354baf01c68cb0ec0791248d3f8f03e31d4a7011db7b6b68e9797720f5c"
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

SETTLED_SOURCE_PACKAGES = {
    "BJ145": (
        ROOT / "results" / "bj145_gate_b_outcome_settlement_v2",
        "10d5a5082a175ddc965b01fb257e8e5c7e91a844d7ee823fd6d2ad5aeff84cc9",
        "e5ebb462028b3abc9979656de37138c5674b52f1830d1ab6ee093c670236cf5b",
    ),
    "BJ148": (
        ROOT / "results" / "bj148_gate_b_outcome_settlement_v1",
        "a60389f27f0373ea03300db5edf28aebb3a0e567e47e78ade860094413756467",
        "38c3325fba0eb02f8701e96ac7cdee4fe9d1aabf146a48b954a0cacf08764b5b",
    ),
    "BJ151": (
        ROOT / "results" / "bj151_gate_b_outcome_settlement_v1",
        "7b88be8af887674875f831f2da0951a1bf7664041f40c10be00d09194ce6fbe2",
        "3214868b35b74c7ebdefeea5041dc30af86caeaced6a2a877db46e6c7e63508e",
    ),
    "BJ159": (
        ROOT / "results" / "bj159_gate_b_outcome_settlement_v2r1",
        "17b42f65b834f2b5afff0e52795588f95340d76810f7faec75b193b6eecc4cc8",
        "7ba60fcc8fa99c620c019f6098e3d9e8b5bb112f6622799baffa9c6f2422cbaf",
    ),
}

BJ145_CACHE_SCHEMA = "bj192-bj145-atomic-cache-v1"


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


def verify_gate_a_source_bindings() -> dict[str, dict[str, str]]:
    """Verify every full-payload predecessor declared by the accepted freeze.

    Gate A intentionally marks settled reference packages ``hash-only``.  They
    remain identity-bound here, while each outcome-consuming adapter must add
    its own exact ticket-ledger verification before it can execute a prefix.
    """
    verify_package(GATE_A, EXPECTED_GATE_A_MANIFEST, EXPECTED_GATE_A_CONTENT)
    card = json.loads((GATE_A / "gate_a_card.json").read_text(encoding="utf-8"))
    result: dict[str, dict[str, str]] = {}
    for name, binding in sorted(card["source_binding"].items()):
        directory = ROOT / "results" / binding["package"]
        if binding["verification_mode"] == "PREOUTCOME_FULL_PAYLOAD_VERIFICATION":
            verify_package(directory, binding["manifest_sha256"], binding["content_identity_sha256"])
        else:
            if sha256_file(directory / "SHA256SUMS.json") != binding["manifest_sha256"]:
                raise RuntimeError(f"settled identity manifest drift: {name}")
            if sha256_file(directory / "CONTENT_IDENTITY.json") != binding["content_identity_sha256"]:
                raise RuntimeError(f"settled identity content drift: {name}")
        result[name] = {
            "manifest_sha256": binding["manifest_sha256"],
            "content_identity_sha256": binding["content_identity_sha256"],
            "verification_mode": binding["verification_mode"],
        }
    if result["bj176_issue_equity_risk_v1"]["manifest_sha256"] != EXPECTED_BJ176_MANIFEST:
        raise RuntimeError("#176 manifest source contract drift")
    if result["bj176_issue_equity_risk_v1"]["content_identity_sha256"] != EXPECTED_BJ176_CONTENT:
        raise RuntimeError("#176 content source contract drift")
    return result


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


@dataclass(frozen=True)
class AtomicIssueSleeve:
    """An exact source-settled sleeve that lacks a Gate-A prefix stream.

    The accepted Gate-A funded-prefix contract explicitly declares every
    expanded #145/#148/#151/#159 record whole-native-or-no-bet until a new
    immutable global order is supplied.  This class makes that restriction a
    runtime invariant while retaining the upstream's exact ticket-level gross
    and per-ticket-tax total for all-or-zero funding.
    """

    sleeve_id: str
    issue_instance: str
    status: str
    requested_ticket_count: int
    gross_yuan: float
    tax_yuan: float
    hit_ticket_count: int
    tax_lot_source_identity: str
    atomic: bool = True

    def settle_prefix(self, count: int) -> dict[str, float | int | str]:
        if count not in (0, self.requested_ticket_count):
            raise RuntimeError(f"partial atomic expanded funding: {self.sleeve_id}/{self.issue_instance}")
        if count and self.status != "SETTLED":
            raise RuntimeError(f"funding unavailable sleeve: {self.sleeve_id}/{self.issue_instance}")
        if not count:
            return {
                "actual_ticket_count": 0,
                "actual_stake_yuan": 0.0,
                "gross_yuan": 0.0,
                "tax_yuan": 0.0,
                "pre_tax_net_yuan": 0.0,
                "tax_adjusted_net_yuan": 0.0,
                "hit_ticket_count": 0,
                "funded_tax_lot_sha256": canonical_hash([]),
            }
        stake = count * TICKET_STAKE_YUAN
        return {
            "actual_ticket_count": count,
            "actual_stake_yuan": stake,
            "gross_yuan": self.gross_yuan,
            "tax_yuan": self.tax_yuan,
            "pre_tax_net_yuan": self.gross_yuan - stake,
            "tax_adjusted_net_yuan": self.gross_yuan - self.tax_yuan - stake,
            "hit_ticket_count": self.hit_ticket_count,
            "funded_tax_lot_sha256": canonical_hash(
                {"source": self.tax_lot_source_identity, "ticket_count": count}
            ),
        }


IssueSleeve = NativeIssueSleeve | AtomicIssueSleeve


def atomic_from_settled_row(
    *,
    sleeve_id: str,
    row: dict[str, str],
    source_identity: str,
    ticket_count_field: str = "executed_ticket_count",
    stake_field: str = "stake_yuan",
) -> AtomicIssueSleeve:
    """Turn a manifest-bound upstream issue row into a whole-native sleeve."""
    status = "SETTLED" if row.get("settlement_status") == "SETTLED" else row.get("settlement_status", "NO_BET_FROZEN")
    requested = int(row.get(ticket_count_field, "0")) if status == "SETTLED" else 0
    stake = float(row.get(stake_field, row.get("planned_stake_yuan", "0")))
    if requested and not math.isclose(stake, requested * TICKET_STAKE_YUAN, abs_tol=1e-6):
        raise RuntimeError(f"source ticket/stake drift: {sleeve_id}/{row.get('issue_instance', '')}")
    return AtomicIssueSleeve(
        sleeve_id=sleeve_id,
        issue_instance=row["issue_instance"],
        status=status,
        requested_ticket_count=requested,
        gross_yuan=float(row.get("gross_pre_tax_yuan", "0")),
        tax_yuan=float(row.get("tax_yuan", "0")),
        hit_ticket_count=int(row.get("hit_ticket_count", row.get("winning_ticket_count", "0"))),
        tax_lot_source_identity=source_identity,
    )


def load_bj145_atomic_surface(
    candidate_ids: Iterable[str],
) -> dict[tuple[str, int, str, str], AtomicIssueSleeve]:
    """Load selected canonical #145 arms as whole-native issue sleeves.

    #145 has exact outcome and per-ticket-tax settlement, but its accepted
    #192 prefix contract has no issue-global prefix proof.  It is therefore
    #192-executable only at its inherited full issue request.  Candidate
    #identity is resolved from the accepted Gate-A registry before any settled
    payload is read; source rows are required to match exactly one candidate.
    """
    selected = set(candidate_ids)
    registry = {
        row["candidate_id"]: row
        for row in read_csv(GATE_A / "bj145_allocation_candidate_registry.csv")
        if row["candidate_id"] in selected
    }
    if registry.keys() != selected:
        raise RuntimeError("unknown #145 Gate-A candidate")
    config_to_candidate: dict[tuple[str, str, str, str, str, str], str] = {}
    for candidate, row in registry.items():
        for m_value in row["available_M_grid"].split(";"):
            for seed in row["seed_scope"].split(";"):
                key = (
                    row["arm_id"], row["weight_source"], row["mechanism"],
                    row["cap"], m_value, seed,
                )
                if key in config_to_candidate:
                    raise RuntimeError(f"ambiguous #145 source configuration: {key}")
                config_to_candidate[key] = candidate

    directory, manifest, content = SETTLED_SOURCE_PACKAGES["BJ145"]
    cache = prepare_bj145_source_cache(directory, manifest, content)
    result: dict[tuple[str, int, str, str], AtomicIssueSleeve] = {}
    try:
        for source_key, candidate in config_to_candidate.items():
            rows = cache.execute(
                """SELECT issue_instance, settlement_status, frozen_planned_draw_count,
                          frozen_planned_stake_yuan, gross_pre_tax_yuan, tax_yuan,
                          hit_ticket_count
                   FROM issue_rows
                   WHERE arm_id=? AND weight_source=? AND mechanism=? AND cap=? AND m=? AND seed=?
                   ORDER BY issue_instance""",
                source_key,
            ).fetchall()
            for values in rows:
                row = dict(zip(
                    ("issue_instance", "settlement_status", "frozen_planned_draw_count",
                     "frozen_planned_stake_yuan", "gross_pre_tax_yuan", "tax_yuan",
                     "hit_ticket_count"), values, strict=True,
                ))
                key = candidate, int(source_key[4]), source_key[5], row["issue_instance"]
                if key in result:
                    raise RuntimeError(f"duplicate #145 source issue row: {key}")
                result[key] = atomic_from_settled_row(
                    sleeve_id=f"{candidate}@M{key[1]}@{key[2]}",
                    row=row,
                    source_identity=canonical_hash({
                        "package": directory.name,
                        "candidate": candidate,
                        "source_key": source_key,
                        "issue": key[3],
                    }),
                    ticket_count_field="frozen_planned_draw_count",
                    stake_field="frozen_planned_stake_yuan",
                )
    finally:
        cache.close()
    config_counts: dict[tuple[str, int, str], int] = defaultdict(int)
    for candidate, m_value, seed, _ in result:
        config_counts[(candidate, m_value, seed)] += 1
    if set(config_counts) != {
        (candidate, int(m_value), seed)
        for key, candidate in config_to_candidate.items()
        for m_value, seed in [(key[4], key[5])]
    } or any(count != 348 for count in config_counts.values()):
        raise RuntimeError("incomplete #145 source surface")
    return result


def prepare_bj145_source_cache(directory: Path, manifest: str, content: str) -> sqlite3.Connection:
    """Build a hash-bound local index for the 1M-row #145 source only once.

    This is an execution cache, not a research artifact: it is regenerated
    solely from the manifest-verified source inside this worktree's `.scratch`
    area.  Its explicit source binding prevents an old cache from silently
    serving a changed ledger and avoids serially decompressing the source once
    per frozen candidate/M path.
    """
    verify_package(directory, manifest, content)
    cache_dir = ROOT / ".scratch" / "bj192_gate_b_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / "bj145_issue_rows.sqlite"
    source_hash = sha256_file(directory / "issue_allocation_settlement.csv.gz")
    expected = canonical_hash({
        "schema": BJ145_CACHE_SCHEMA,
        "package": directory.name,
        "manifest": manifest,
        "content": content,
        "source_file_sha256": source_hash,
    })
    if path.exists():
        connection = sqlite3.connect(path)
        try:
            meta = dict(connection.execute("SELECT key, value FROM cache_meta"))
            if meta.get("identity") == expected:
                return connection
        except sqlite3.DatabaseError:
            pass
        connection.close()
        path.unlink()
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=OFF")
    connection.execute("PRAGMA synchronous=OFF")
    connection.execute("PRAGMA temp_store=MEMORY")
    connection.execute("CREATE TABLE cache_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute(
        """CREATE TABLE issue_rows (
            arm_id TEXT NOT NULL, weight_source TEXT NOT NULL, mechanism TEXT NOT NULL,
            cap TEXT NOT NULL, m TEXT NOT NULL, seed TEXT NOT NULL,
            issue_instance TEXT NOT NULL, settlement_status TEXT NOT NULL,
            frozen_planned_draw_count TEXT NOT NULL, frozen_planned_stake_yuan TEXT NOT NULL,
            gross_pre_tax_yuan TEXT NOT NULL, tax_yuan TEXT NOT NULL, hit_ticket_count TEXT NOT NULL,
            PRIMARY KEY (arm_id, weight_source, mechanism, cap, m, seed, issue_instance)
        ) WITHOUT ROWID"""
    )
    fields = (
        "arm_id", "weight_source", "mechanism", "cap", "M", "seed", "issue_instance",
        "settlement_status", "frozen_planned_draw_count", "frozen_planned_stake_yuan",
        "gross_pre_tax_yuan", "tax_yuan", "hit_ticket_count",
    )
    batch: list[tuple[str, ...]] = []
    with gzip.open(directory / "issue_allocation_settlement.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            batch.append(tuple(row[field] for field in fields))
            if len(batch) >= 10_000:
                connection.executemany("INSERT INTO issue_rows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                batch.clear()
    if batch:
        connection.executemany("INSERT INTO issue_rows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
    count = connection.execute("SELECT COUNT(*) FROM issue_rows").fetchone()[0]
    if count != 1_006_416:
        raise RuntimeError(f"#145 cache source row count drift: {count}")
    connection.executemany(
        "INSERT INTO cache_meta VALUES (?, ?)",
        [("identity", expected), ("source_rows", str(count))],
    )
    connection.commit()
    return connection


def load_dense_atomic_surface(
    source_key: str,
    candidate_specs: dict[str, tuple[str, str]],
) -> dict[tuple[str, int, str, str], AtomicIssueSleeve]:
    """Load complete #148/#151 issue×M×seed rows as atomic sleeves.

    The source packages contain exact per-ticket settlement and tax ledgers;
    #192 is allowed to consume the entire native issue request but the Gate-A
    prefix contract forbids a new cross-identity ticket ordering.  ``M`` and
    seed therefore remain part of the sleeve identity rather than being
    averaged or selected after the fact.
    """
    directory, manifest, content = SETTLED_SOURCE_PACKAGES[source_key]
    verify_package(directory, manifest, content)
    rows = read_gzip(directory / "issue_m_grid_settlement.csv.gz")
    result: dict[tuple[str, int, str, str], AtomicIssueSleeve] = {}
    expected_configs = set(candidate_specs.values())
    seen_configs: set[tuple[str, str, int, str]] = set()
    for row in rows:
        spec = (row["sampling_role"], row["ticket_mechanism"])
        if spec not in expected_configs:
            continue
        candidate_id = next(key for key, value in candidate_specs.items() if value == spec)
        m_value, seed = int(row["M"]), row["seed"]
        key = candidate_id, m_value, seed, row["issue_instance"]
        if key in result:
            raise RuntimeError(f"duplicate dense source issue row: {key}")
        result[key] = atomic_from_settled_row(
            sleeve_id=f"{candidate_id}@M{m_value}@{seed}",
            row=row,
            source_identity=canonical_hash(
                {"package": directory.name, "candidate": candidate_id, "M": m_value, "seed": seed, "issue": row["issue_instance"]}
            ),
        )
        seen_configs.add((spec[0], spec[1], m_value, seed))
    # Each frozen dense configuration has the canonical 348-issue calendar,
    # including no-bet and unavailable zero-flow records.
    config_counts: dict[tuple[str, int, str], int] = defaultdict(int)
    for candidate, m_value, seed, _ in result:
        config_counts[(candidate, m_value, seed)] += 1
    if not config_counts or any(count != 348 for count in config_counts.values()):
        raise RuntimeError(f"incomplete dense source surface: {source_key}")
    return result


def load_bj159_n7_atomic_surface() -> dict[tuple[int, str, str], AtomicIssueSleeve]:
    """Load the frozen N=7 #159 WOR M curve, retaining saturation semantics."""
    directory, manifest, content = SETTLED_SOURCE_PACKAGES["BJ159"]
    verify_package(directory, manifest, content)
    rows = read_gzip(directory / "issue_settlement.csv.gz")
    result: dict[tuple[int, str, str], AtomicIssueSleeve] = {}
    for row in rows:
        if int(row["n"]) != 7:
            continue
        key = int(row["M"]), row["seed"], row["issue_instance"]
        if key in result:
            raise RuntimeError(f"duplicate #159 N7 issue row: {key}")
        result[key] = atomic_from_settled_row(
            sleeve_id=f"BJ159_SELECTED_N7_WOR_M_CURVE@M{key[0]}@{key[1]}",
            row=row,
            source_identity=canonical_hash(
                {"package": directory.name, "n": 7, "M": key[0], "seed": key[1], "issue": key[2], "saturation": row["saturation_status"]}
            ),
        )
    config_counts: dict[tuple[int, str], int] = defaultdict(int)
    for m_value, seed, _ in result:
        config_counts[(m_value, seed)] += 1
    if not config_counts or any(count != 348 for count in config_counts.values()):
        raise RuntimeError("incomplete #159 N7 source surface")
    return result


def canonical_economic_catalog() -> dict[str, dict[str, str]]:
    """Read the immutable, alias-deduplicated Gate-A family catalog."""
    rows = read_csv(GATE_A / "economic_family_registry.csv")
    result = {
        row["candidate_id"]: row
        for row in rows
        if row["candidate_id"] == row["canonical_candidate_id"]
        and row["family_status"] == "CANONICAL_PRIMARY_FRONTIER"
    }
    if len(result) != 104 or set(result) - {row["candidate_id"] for row in rows}:
        raise RuntimeError("canonical economic family denominator drift")
    return result


def frozen_m_grid(candidate_id: str) -> tuple[int, ...]:
    row = canonical_economic_catalog().get(candidate_id)
    if row is None:
        raise RuntimeError(f"unknown canonical candidate: {candidate_id}")
    return tuple(int(value) for value in row["available_M_grid"].split(";"))


def materialize_candidate_bridge(
    candidate_id: str,
    m_value: int,
    seed: str = "NA",
) -> dict[tuple[str, str], IssueSleeve]:
    """Materialize one immutable candidate/M/seed path on all 348 issues.

    The function deliberately returns only one frozen economic identity at a
    time.  This keeps the million-row #145 source in its verified local index
    rather than treating an in-memory aggregate as a substitute for the source
    ledger.  Pairwise/higher-order runs compose these exact 348-row bridges.
    """
    catalog = canonical_economic_catalog()
    family = catalog.get(candidate_id)
    if family is None or m_value not in frozen_m_grid(candidate_id):
        raise RuntimeError(f"candidate/M outside Gate-A catalog: {candidate_id}@{m_value}")
    if family["source_kind"] == "H1_FIXED":
        if seed != "NA":
            raise RuntimeError("H1 sleeves have no deployment seed")
        bridge = h1_ticket_bridge()
        return {(candidate_id, issue): sleeve for (sleeve_id, issue), sleeve in bridge.items() if sleeve_id == candidate_id}
    if family["source_kind"] == "BJ145_ALLOCATION":
        surface = load_bj145_atomic_surface([candidate_id])
        result = {
            (candidate_id, issue): sleeve
            for (candidate, m_item, seed_item, issue), sleeve in surface.items()
            if candidate == candidate_id and m_item == m_value and seed_item == seed
        }
    elif candidate_id.startswith("BJ148_"):
        specs = {
            "BJ148_NOGATE_WR_DENSE_M": ("PRIMARY_WR_NATURAL_BASELINE", "Q_INFORMED_WR_DUPLICATE_STAKE"),
            "BJ148_NOGATE_WOR_DENSE_M": ("SENSITIVITY_WOR_DISTINCT", "Q_INFORMED_WOR_DISTINCT"),
        }
        surface = load_dense_atomic_surface("BJ148", {candidate_id: specs[candidate_id]})
        result = {
            (candidate_id, issue): sleeve
            for (candidate, m_item, seed_item, issue), sleeve in surface.items()
            if m_item == m_value and seed_item == seed
        }
    elif candidate_id.startswith("BJ151_"):
        specs = {
            "BJ151_NOGATE_K4_WR_DENSE_M": ("PRIMARY_WR_NATURAL_BASELINE", "Q_INFORMED_WR_DUPLICATE_STAKE"),
            "BJ151_NOGATE_K4_WOR_DENSE_M": ("SENSITIVITY_WOR_FIXED_CANDIDATE", "Q_INFORMED_WOR_DISTINCT"),
        }
        surface = load_dense_atomic_surface("BJ151", {candidate_id: specs[candidate_id]})
        result = {
            (candidate_id, issue): sleeve
            for (candidate, m_item, seed_item, issue), sleeve in surface.items()
            if m_item == m_value and seed_item == seed
        }
    elif candidate_id == "BJ159_SELECTED_N7_WOR_M_CURVE":
        surface = load_bj159_n7_atomic_surface()
        result = {
            (candidate_id, issue): sleeve
            for (m_item, seed_item, issue), sleeve in surface.items()
            if m_item == m_value and seed_item == seed
        }
    else:
        raise RuntimeError(f"unimplemented source adapter: {candidate_id}")
    if len(result) != 348:
        raise RuntimeError(f"incomplete candidate path: {candidate_id}@{m_value}@{seed}: {len(result)}")
    return result


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


def source_native_return(sleeve: IssueSleeve) -> float | None:
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
    bridge: dict[tuple[str, str], IssueSleeve],
    calendar: Sequence[dict[str, str]],
    bundle_id: str = "DETERMINISTIC_H1",
) -> list[dict[str, object]]:
    """Run one strictly-prior, concurrent, capital-limited Stage-4 path."""
    gate = frozen_gate_a()
    sleeves = tuple(sorted(sleeves))
    if not sleeves:
        raise ValueError("empty sleeve subset")
    if any((sleeve, row["issue_instance"]) not in bridge for sleeve in sleeves for row in calendar):
        raise ValueError("incomplete frozen sleeve/calendar bridge")
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


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def summarize_holding_path(rows: Sequence[dict[str, object]]) -> dict[str, object]:
    """Compute the frozen issue-level holding metrics without dropping cash rows."""
    if not rows:
        raise ValueError("cannot summarize empty capital path")
    ordered = sorted(rows, key=lambda row: int(row["calendar_index"]))
    enriched: list[dict[str, object]] = []
    rolling: list[dict[str, object]] = []
    peak = float(ordered[0]["preissue_bankroll_yuan"])
    loss_calendar = loss_active = miss_calendar = miss_active = 0
    max_loss_calendar = max_loss_active = max_miss_calendar = max_miss_active = 0
    drawdown_start: int | None = None
    recovery_durations: list[int] = []
    unrecovered = 0
    for row in ordered:
        item = dict(row)
        post = float(item["postissue_bankroll_yuan"])
        index = int(item["calendar_index"])
        if post >= peak:
            if drawdown_start is not None:
                recovery_durations.append(index - drawdown_start)
                drawdown_start = None
            peak = post
        elif drawdown_start is None:
            drawdown_start = index
        drawdown = peak - post
        item["running_peak_yuan"] = peak
        item["drawdown_yuan"] = drawdown
        item["drawdown_fraction"] = drawdown / peak if peak > 0 else None
        net, stake, gross = (float(item[field]) for field in ("pre_tax_net_yuan", "actual_stake_yuan", "pre_tax_gross_yuan"))
        if net < 0:
            loss_calendar += 1
        else:
            loss_calendar = 0
        max_loss_calendar = max(max_loss_calendar, loss_calendar)
        if stake > 0:
            loss_active = loss_active + 1 if net < 0 else 0
            max_loss_active = max(max_loss_active, loss_active)
        if stake > 0 and gross == 0:
            miss_calendar += 1
        else:
            miss_calendar = 0
        max_miss_calendar = max(max_miss_calendar, miss_calendar)
        if stake > 0:
            miss_active = miss_active + 1 if gross == 0 else 0
            max_miss_active = max(max_miss_active, miss_active)
        enriched.append(item)
    if drawdown_start is not None:
        unrecovered = 1

    for window_size in (5, 10, 20):
        windows: list[dict[str, object]] = []
        for end in range(window_size - 1, len(enriched)):
            selected = enriched[end + 1 - window_size : end + 1]
            net = sum(float(row["pre_tax_net_yuan"]) for row in selected)
            stake = sum(float(row["actual_stake_yuan"]) for row in selected)
            roi = net / stake if stake else None
            windows.append({
                "window_size_issues": window_size,
                "record_type": "WINDOW",
                "window_start_calendar_index": selected[0]["calendar_index"],
                "window_end_calendar_index": selected[-1]["calendar_index"],
                "window_pre_tax_net_yuan": net,
                "window_actual_stake_yuan": stake,
                "window_pre_tax_roi": roi,
                "is_negative": int(net < 0),
                "undefined_reason": "ZERO_WINDOW_STAKE" if stake == 0 else "",
            })
        if not windows:
            continue
        nets = [float(row["window_pre_tax_net_yuan"]) for row in windows]
        worst = min(windows, key=lambda row: (float(row["window_pre_tax_net_yuan"]), int(row["window_start_calendar_index"])))
        rolling.extend(windows)
        rolling.append({
            "window_size_issues": window_size,
            "record_type": "SUMMARY",
            "window_start_calendar_index": "",
            "window_end_calendar_index": "",
            "window_pre_tax_net_yuan": "",
            "window_actual_stake_yuan": "",
            "window_pre_tax_roi": "",
            "is_negative": "",
            "window_count": len(windows),
            "negative_window_count": sum(int(row["is_negative"]) for row in windows),
            "negative_window_probability": sum(int(row["is_negative"]) for row in windows) / len(windows),
            "worst_window_id": f"{worst['window_start_calendar_index']}:{worst['window_end_calendar_index']}",
            "worst_window_pre_tax_net_yuan": worst["window_pre_tax_net_yuan"],
            "worst_window_pre_tax_roi": worst["window_pre_tax_roi"],
            "undefined_reason": "",
        })
        for label, probability in (("MIN", 0.0), ("P05", 0.05), ("P50", 0.5), ("P95", 0.95), ("MAX", 1.0)):
            rolling.append({
                "window_size_issues": window_size,
                "record_type": "DISTRIBUTION",
                "window_start_calendar_index": "",
                "window_end_calendar_index": "",
                "distribution_statistic": label,
                "distribution_value": _quantile(nets, probability),
                "undefined_reason": "",
            })

    returns = [
        float(row["pre_tax_net_yuan"]) / float(row["preissue_bankroll_yuan"])
        for row in enriched
        if float(row["preissue_bankroll_yuan"]) > 0
    ]
    mean_return = sum(returns) / len(returns)
    sample_sd = math.sqrt(sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)) if len(returns) > 1 else 0.0
    downside_rms = math.sqrt(sum(min(value, 0.0) ** 2 for value in returns) / len(returns)) if returns else 0.0
    years = {str(row["issue_instance"]).split("@")[-1] for row in enriched}
    annualization = math.sqrt(len(enriched) / len(years)) if years else 1.0
    sharpe = mean_return / sample_sd * annualization if sample_sd > 0 else None
    sortino = mean_return / downside_rms * annualization if downside_rms > 0 else None
    starting = float(enriched[0]["preissue_bankroll_yuan"])
    ending = float(enriched[-1]["postissue_bankroll_yuan"])
    max_drawdown = max(float(row["drawdown_yuan"]) for row in enriched)
    max_drawdown_fraction = max(float(row["drawdown_fraction"] or 0.0) for row in enriched)
    annualized_growth = (ending / starting) ** (1.0 / len(years)) - 1.0 if starting > 0 and ending > 0 and years else None
    calmar = annualized_growth / max_drawdown_fraction if annualized_growth is not None and max_drawdown_fraction > 0 else None
    active = [row for row in enriched if float(row["actual_stake_yuan"]) > 0]
    return {
        "issue_rows": enriched,
        "rolling_rows": rolling,
        "summary": {
            "ending_bankroll_yuan": ending,
            "minimum_bankroll_yuan": min(min(float(row["preissue_bankroll_yuan"]), float(row["postissue_bankroll_yuan"])) for row in enriched),
            "max_drawdown_yuan": max_drawdown,
            "max_drawdown_fraction": max_drawdown_fraction,
            "drawdown_duration_issues": max((duration for duration in recovery_durations), default=0),
            "time_under_water_issues": sum(float(row["drawdown_yuan"]) > 0 for row in enriched),
            "recovery_issue": next((row["issue_instance"] for row in reversed(enriched) if float(row["drawdown_yuan"]) == 0), None),
            "recovery_episode_count": len(recovery_durations),
            "recovery_duration_median_issues": _quantile(recovery_durations, 0.5),
            "recovery_duration_tail_95_issues": _quantile(recovery_durations, 0.95),
            "recovery_duration_max_issues": max(recovery_durations, default=0),
            "unrecovered_episode_count": unrecovered,
            "loss_streak_calendar": max_loss_calendar,
            "loss_streak_active": max_loss_active,
            "miss_streak_calendar": max_miss_calendar,
            "miss_streak_active": max_miss_active,
            "rolling_window_metrics_sha256": canonical_hash(rolling),
            "ruin_flag": int(any(int(row["ruin_flag"]) for row in enriched)),
            "near_ruin_flag": int(min(float(row["postissue_bankroll_yuan"]) for row in enriched) < TICKET_STAKE_YUAN * max((int(sum(item["actual_ticket_count"] for item in row["sleeve_settlements"].values())) for row in enriched), default=0)),
            "sharpe": sharpe,
            "sortino": sortino,
            "calmar": calmar,
            "active_issue_count": len(active),
        },
    }
