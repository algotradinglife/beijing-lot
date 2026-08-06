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
import gc
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
import shutil
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Sequence


CONTRACT = "BJ-HIST-N7-STRATEGY-ENSEMBLE-001"
VERSION = "bj192-gate-b-v1"
TICKET_STAKE_YUAN = 2.0
INITIAL_BANKROLL_YUAN = 100_000.0
PHASE0_CHECKPOINT = ".scratch/bj192_phase0_selected_m_checkpoint_v4.json"
PHASE0_MATERIALIZER_CONTRACT = "selected-native-outcome-cache-v4"

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
ROBUST_SLEEVES = (
    "BJ148_NOGATE_WR_DENSE_M",
    "BJ148_NOGATE_WOR_DENSE_M",
    "BJ151_NOGATE_K4_WR_DENSE_M",
    "BJ151_NOGATE_K4_WOR_DENSE_M",
    "BJ159_SELECTED_N7_WOR_M_CURVE",
)
CORE_SLEEVES = (*H1_SLEEVES, *ROBUST_SLEEVES)
CORE_WEIGHT_METHODS = (
    "EQUAL_WEIGHT",
    "PRIOR_INVERSE_VOL",
    "PRIOR_MINIMUM_VARIANCE",
    "PRIOR_MAXIMUM_DIVERSIFICATION",
)
CORE_NORMALIZATION_METHODS = ("UNIT_CAPITAL", "UNIT_EX_ANTE_VOL_CAPPED_5PCT")
MINIMAL_WEIGHT_METHODS = ("EQUAL_WEIGHT", "PRIOR_MINIMUM_VARIANCE")
MINIMAL_NORMALIZATION_METHODS = ("UNIT_CAPITAL", "UNIT_EX_ANTE_VOL_CAPPED_5PCT")
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
H1_TICKET_CACHE_SCHEMA = "bj192-h1-ticket-lot-cache-v1"


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


def canonical_scientific_sha256(path: Path) -> str:
    """Hash uncompressed science bytes while retaining transport hashes too."""
    digest = hashlib.sha256()
    opener = gzip.open if path.suffix == ".gz" else Path.open
    with opener(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_csv_rows(
    path: Path,
    rows: Sequence[dict[str, object]],
    *,
    compressed: bool,
    declared_fields: Sequence[str] = (),
) -> list[str]:
    """Write stable CSV bytes without a system temporary file."""
    fields = list(dict.fromkeys([*declared_fields, *sorted({field for row in rows for field in row})]))
    if not fields:
        raise RuntimeError(f"cannot write fieldless table: {path.name}")
    normalized = [{field: row.get(field, "") for field in fields} for row in rows]
    if compressed:
        with path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
                with io.TextIOWrapper(zipped, newline="", encoding="utf-8") as text:
                    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n", extrasaction="raise")
                    writer.writeheader()
                    writer.writerows(normalized)
    else:
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
            writer.writeheader()
            writer.writerows(normalized)
    return fields


def write_immutable_package(
    output: Path,
    tables: dict[str, Sequence[dict[str, object]]],
    *,
    source_binding: dict[str, object],
    package_note: str,
) -> dict[str, object]:
    """Write a complete package into a unique sibling stage then atomically land it.

    This helper is intentionally output-only: no output or stage is treated as
    input, and it refuses to overwrite an immutable target.  The caller must
    provide every table required by the accepted Gate-A schema before this
    function is used for a canonical Gate-B run.
    """
    output = output.resolve()
    stage = output.with_name(f".{output.name}.stage")
    if output.exists() or stage.exists():
        raise RuntimeError(f"immutable output or active stage already exists: {output}")
    schema = json.loads((GATE_A / "output_schema.json").read_text(encoding="utf-8"))
    required = {
        key for key, spec in schema.items()
        if isinstance(spec, dict) and "key" in spec
    }
    missing = required - set(tables)
    if missing:
        raise RuntimeError(f"missing Gate-B output tables: {sorted(missing)}")
    stage.mkdir(parents=False)
    try:
        table_manifest: dict[str, dict[str, object]] = {}
        for table, rows in sorted(tables.items()):
            compressed = table in {"issue_ledger", "weight_history", "selected_m_path", "standalone_m_curve"}
            filename = f"{table}.csv.gz" if compressed else f"{table}.csv"
            spec = schema[table]
            fields = write_csv_rows(
                stage / filename,
                list(rows),
                compressed=compressed,
                declared_fields=[*spec["key"], *spec["fields"]],
            )
            table_manifest[table] = {"filename": filename, "row_count": len(rows), "fields": fields}
        (stage / "source_binding.json").write_text(json.dumps(source_binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (stage / "table_manifest.json").write_text(json.dumps(table_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (stage / "README.md").write_text(package_note.rstrip() + "\n", encoding="utf-8")
        archive_transport = {path.name: sha256_file(path) for path in sorted(stage.iterdir()) if path.is_file()}
        scientific = {path.name: canonical_scientific_sha256(path) for path in sorted(stage.iterdir()) if path.is_file()}
        content = {
            "contract": CONTRACT,
            "version": VERSION,
            "canonical_scientific_payload_sha256": scientific,
            "canonical_scientific_identity_sha256": canonical_hash(scientific),
            "archive_transport_payload_sha256": archive_transport,
            "archive_transport_contract": {
                "gzip": "gzip.GzipFile(filename='', mtime=0)",
                "scientific_identity": "gzip payloads SHA-256 after decompression",
            },
        }
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {path.name: sha256_file(path) for path in sorted(stage.iterdir()) if path.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verify_package(stage, sha256_file(stage / "SHA256SUMS.json"), sha256_file(stage / "CONTENT_IDENTITY.json"))
        os.replace(stage, output)
        return {"output": str(output), "manifest_sha256": sha256_file(output / "SHA256SUMS.json"), "content_sha256": sha256_file(output / "CONTENT_IDENTITY.json"), "tables": table_manifest}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def write_surface_checkpoint(
    checkpoint: Path,
    *,
    binding: dict[str, object],
    completed_path_keys: Sequence[dict[str, object]],
) -> dict[str, object]:
    """Atomically save a resumable Gate-B surface boundary below ``.scratch``.

    A checkpoint is never a research artifact: it contains no settled output
    table and is rejected if it is outside the repository scratch hierarchy or
    its Gate-A/source identities do not match the currently accepted inputs.
    """
    scratch = (ROOT / ".scratch").resolve()
    checkpoint = checkpoint.resolve()
    if scratch not in checkpoint.parents:
        raise RuntimeError("checkpoint must remain under repository .scratch")
    keys = [dict(row) for row in completed_path_keys]
    if len({canonical_hash(row) for row in keys}) != len(keys):
        raise RuntimeError("duplicate completed path checkpoint key")
    required = {"gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST, "gate_a_content_sha256": EXPECTED_GATE_A_CONTENT}
    if any(binding.get(key) != value for key, value in required.items()):
        raise RuntimeError("checkpoint Gate-A binding mismatch")
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    stage = checkpoint.with_suffix(checkpoint.suffix + ".stage")
    if stage.exists():
        raise RuntimeError(f"active checkpoint stage exists: {stage}")
    payload = {
        "contract": CONTRACT,
        "version": VERSION,
        "binding": binding,
        "completed_path_keys": sorted(keys, key=canonical_hash),
    }
    payload["payload_sha256"] = canonical_hash(payload)
    stage.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(stage, checkpoint)
    return payload


def load_surface_checkpoint(checkpoint: Path, *, binding: dict[str, object]) -> list[dict[str, object]]:
    """Read only a matching complete checkpoint; stale state fails closed."""
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    expected = dict(payload)
    digest = expected.pop("payload_sha256", None)
    if digest != canonical_hash(expected) or payload.get("binding") != binding:
        raise RuntimeError("checkpoint integrity or binding mismatch")
    return list(payload["completed_path_keys"])


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
            ticket_count_field="frozen_planned_draw_count",
            stake_field="frozen_planned_stake_yuan",
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
        # #159's canonical ledger is draw-oriented rather than using the
        # generic `settlement_status`/`executed_ticket_count` names.  A
        # positive executed draw count is its exact settled native request;
        # zero draws remain an explicit no-bet/unavailable zero-flow row.
        row = dict(row)
        row["settlement_status"] = "SETTLED" if int(row["executed_draw_count"]) > 0 else "NO_BET_FROZEN"
        key = int(row["M"]), row["seed"], row["issue_instance"]
        if key in result:
            raise RuntimeError(f"duplicate #159 N7 issue row: {key}")
        result[key] = atomic_from_settled_row(
            sleeve_id=f"BJ159_SELECTED_N7_WOR_M_CURVE@M{key[0]}@{key[1]}",
            row=row,
            source_identity=canonical_hash(
                {"package": directory.name, "n": 7, "M": key[0], "seed": key[1], "issue": key[2], "saturation": row["saturation_status"]}
            ),
            ticket_count_field="executed_draw_count",
            stake_field="stake_yuan",
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


def materialize_candidate_m_surface(
    candidate_id: str,
) -> dict[tuple[int, str, str], IssueSleeve]:
    """Materialize every frozen M/seed issue row for one canonical family."""
    catalog = canonical_economic_catalog()
    family = catalog.get(candidate_id)
    if family is None:
        raise RuntimeError(f"unknown canonical candidate: {candidate_id}")
    if family["source_kind"] == "H1_FIXED":
        m_value = frozen_m_grid(candidate_id)[0]
        return {
            (m_value, "NA", issue): sleeve
            for (sleeve_id, issue), sleeve in h1_ticket_bridge().items()
            if sleeve_id == candidate_id
        }
    if family["source_kind"] == "BJ145_ALLOCATION":
        return {
            (m_value, seed, issue): sleeve
            for (_, m_value, seed, issue), sleeve in load_bj145_atomic_surface([candidate_id]).items()
        }
    if candidate_id.startswith("BJ148_"):
        specs = {
            "BJ148_NOGATE_WR_DENSE_M": ("PRIMARY_WR_NATURAL_BASELINE", "Q_INFORMED_WR_DUPLICATE_STAKE"),
            "BJ148_NOGATE_WOR_DENSE_M": ("SENSITIVITY_WOR_DISTINCT", "Q_INFORMED_WOR_DISTINCT"),
        }
        return {
            (m_value, seed, issue): sleeve
            for (_, m_value, seed, issue), sleeve in load_dense_atomic_surface("BJ148", {candidate_id: specs[candidate_id]}).items()
        }
    if candidate_id.startswith("BJ151_"):
        specs = {
            "BJ151_NOGATE_K4_WR_DENSE_M": ("PRIMARY_WR_NATURAL_BASELINE", "Q_INFORMED_WR_DUPLICATE_STAKE"),
            "BJ151_NOGATE_K4_WOR_DENSE_M": ("SENSITIVITY_WOR_FIXED_CANDIDATE", "Q_INFORMED_WOR_DISTINCT"),
        }
        return {
            (m_value, seed, issue): sleeve
            for (_, m_value, seed, issue), sleeve in load_dense_atomic_surface("BJ151", {candidate_id: specs[candidate_id]}).items()
        }
    if candidate_id == "BJ159_SELECTED_N7_WOR_M_CURVE":
        return load_bj159_n7_atomic_surface()
    raise RuntimeError(f"unimplemented source adapter: {candidate_id}")


def build_walk_forward_candidate_bridge(
    candidate_id: str,
    deployment_seed: str,
    calendar: Sequence[dict[str, str]] | None = None,
    m_surface: dict[tuple[int, str, str], IssueSleeve] | None = None,
) -> tuple[dict[tuple[str, str], IssueSleeve], list[dict[str, object]]]:
    """Select each M from prior native source outcomes, then return one seed path.

    This is the Gate-A chronological selection contract in executable form.  It
    records every issue's selected M and the exact pre-selection training hash;
    the selected source sleeve remains an unchanged upstream ticket allocation.
    """
    calendar = list(calendar or read_csv(GATE_A / "full_calendar.csv"))
    surface = m_surface if m_surface is not None else materialize_candidate_m_surface(candidate_id)
    available_m = frozen_m_grid(candidate_id)
    seeds = sorted({seed for _, seed, _ in surface})
    if deployment_seed not in seeds:
        raise RuntimeError(f"deployment seed outside frozen source: {candidate_id}/{deployment_seed}")
    if any((m_value, seed, row["issue_instance"]) not in surface for m_value in available_m for seed in seeds for row in calendar):
        raise RuntimeError(f"incomplete M surface: {candidate_id}")
    if canonical_economic_catalog()[candidate_id]["source_kind"] == "H1_FIXED":
        m_value = available_m[0]
        bridge = {
            (candidate_id, row["issue_instance"]): surface[(m_value, deployment_seed, row["issue_instance"])]
            for row in calendar
        }
        return bridge, [{
            "economic_family_id": canonical_economic_catalog()[candidate_id]["economic_family_id"],
            "deployment_seed": deployment_seed,
            "calendar_index": int(row["calendar_index"]),
            "issue_instance": row["issue_instance"],
            "selection_variant": "FIXED_FROZEN_M",
            "prior_training_start_calendar_index": "",
            "prior_training_end_calendar_index": "",
            "prior_active_issue_count": "",
            "prior_training_input_sha256": canonical_hash({"candidate_id": candidate_id, "M": m_value}),
            "selected_M": m_value,
            "fixed_M_comparator": m_value,
            "fallback_reason": "FROZEN_FIXED_M_NO_SELECTION",
        } for row in calendar]
    history: dict[int, dict[str, list[tuple[float, float]]]] = {
        m_value: {seed: [] for seed in seeds} for m_value in available_m
    }
    bridge: dict[tuple[str, str], IssueSleeve] = {}
    selected_path: list[dict[str, object]] = []
    for row in sorted(calendar, key=lambda item: (item["first_kickoff_ts"], item["issue_instance"])):
        decision = choose_prior_m(candidate_id, history)
        m_value = int(decision["selected_M"])
        issue = row["issue_instance"]
        bridge[(candidate_id, issue)] = surface[(m_value, deployment_seed, issue)]
        training_identity = canonical_hash({
            "candidate_id": candidate_id,
            "through_calendar_index": int(row["calendar_index"]) - 1,
            "history": history,
        })
        selected_path.append({
            "economic_family_id": canonical_economic_catalog()[candidate_id]["economic_family_id"],
            "deployment_seed": deployment_seed,
            "calendar_index": int(row["calendar_index"]),
            "issue_instance": issue,
            "selection_variant": "WALK_FORWARD",
            "prior_training_start_calendar_index": 0 if row["calendar_index"] != "0" else "",
            "prior_training_end_calendar_index": int(row["calendar_index"]) - 1 if row["calendar_index"] != "0" else "",
            "prior_active_issue_count": decision["prior_active_issue_count"],
            "prior_training_input_sha256": training_identity,
            "selected_M": m_value,
            "fixed_M_comparator": fixed_m_comparator(candidate_id),
            "fallback_reason": decision["fallback_reason"],
        })
        for history_m in available_m:
            for history_seed in seeds:
                sleeve = surface[(history_m, history_seed, issue)]
                result = source_native_return(sleeve)
                if result is None:
                    history[history_m][history_seed].append((0.0, 0.0))
                else:
                    full = sleeve.settle_prefix(sleeve.requested_ticket_count)
                    history[history_m][history_seed].append((float(full["pre_tax_net_yuan"]), float(full["actual_stake_yuan"])))
    return bridge, selected_path


def walk_forward_candidate_paths(
    candidate_id: str,
    calendar: Sequence[dict[str, str]] | None = None,
) -> dict[str, tuple[dict[tuple[str, str], IssueSleeve], list[dict[str, object]]]]:
    """Create one separate executable capital path per frozen deployment seed."""
    surface = materialize_candidate_m_surface(candidate_id)
    return {
        seed: build_walk_forward_candidate_bridge(candidate_id, seed, calendar, surface)
        for seed in sorted({seed for _, seed, _ in surface})
    }


def frozen_replicate_bundles() -> dict[str, dict[str, str]]:
    """Read Gate-A's ordinal seed pairings; no source seed may be substituted."""
    result: dict[str, dict[str, str]] = {}
    for row in read_csv(GATE_A / "replicate_bundle_registry.csv"):
        members = json.loads(row["candidate_seed_map_json"])
        if canonical_hash(members) != row["candidate_seed_map_sha256"]:
            raise RuntimeError(f"replicate bundle hash drift: {row['deployment_replicate_bundle_id']}")
        result[row["deployment_replicate_bundle_id"]] = members
    if set(result) != {"BUNDLE_ORDINAL_001", "BUNDLE_ORDINAL_002", "BUNDLE_ORDINAL_003"}:
        raise RuntimeError("replicate bundle denominator drift")
    return result


def build_bundle_bridges(
    candidates: Sequence[str],
    bundle_id: str,
    calendar: Sequence[dict[str, str]] | None = None,
) -> tuple[dict[tuple[str, str], IssueSleeve], list[dict[str, object]]]:
    """Materialize the exact Gate-A paired-seed path for one portfolio bundle."""
    bundles = frozen_replicate_bundles()
    seed_map = bundles.get(bundle_id)
    if seed_map is None or any(candidate not in seed_map for candidate in candidates):
        raise RuntimeError(f"candidate absent from frozen bundle: {bundle_id}")
    bridges: list[dict[tuple[str, str], IssueSleeve]] = []
    selected_rows: list[dict[str, object]] = []
    for candidate in candidates:
        source_seed = "NA" if seed_map[candidate] == "DETERMINISTIC" else seed_map[candidate]
        paths = walk_forward_candidate_paths(candidate, calendar)
        bridge, selected = paths.get(source_seed, (None, None))
        if bridge is None or selected is None:
            raise RuntimeError(f"frozen bundle seed unavailable: {candidate}/{source_seed}")
        for row in selected:
            row["deployment_replicate_bundle_id"] = bundle_id
        bridges.append(bridge)
        selected_rows.extend(selected)
    return merge_candidate_bridges(*bridges), selected_rows


class CandidatePathCache:
    """Memoize selected 348-row paths, never an outcome-rescaled aggregate.

    A dense source M surface is materialized once per candidate to derive its
    frozen walk-forward paths, then only the selected immutable issue sleeves
    remain referenced.  This makes the all-pair replay practical without
    retaining the full raw dense grid for every candidate in RAM.
    """

    def __init__(self, calendar: Sequence[dict[str, str]] | None = None) -> None:
        self.calendar = list(calendar or read_csv(GATE_A / "full_calendar.csv"))
        self._paths: dict[str, dict[str, tuple[dict[tuple[str, str], IssueSleeve], list[dict[str, object]]]]] = {}
        self._native_observations: dict[str, dict[str, dict[str, dict[str, float | int | bool]]]] = {}

    def paths(self, candidate_id: str) -> dict[str, tuple[dict[tuple[str, str], IssueSleeve], list[dict[str, object]]]]:
        if candidate_id not in self._paths:
            surface = materialize_candidate_m_surface(candidate_id)
            self._paths[candidate_id] = {
                seed: build_walk_forward_candidate_bridge(candidate_id, seed, self.calendar, surface)
                for seed in sorted({seed for _, seed, _ in surface})
            }
        return self._paths[candidate_id]

    def native_observations(self, candidate_id: str, deployment_seed: str) -> dict[str, dict[str, float | int | bool]]:
        """Memoize every selected native issue settlement for the full pair screen.

        The native lots are settled once per canonical family/replica and then
        reused by all pair combinations.  This is especially material for the
        2,187-ticket FULL sleeve: repeatedly summing its tax lots per pair
        would be both wasteful and a hidden re-settlement of an identical
        frozen ticket outcome.
        """
        by_seed = self._native_observations.setdefault(candidate_id, {})
        if deployment_seed not in by_seed:
            bridge, _ = self.paths(candidate_id).get(deployment_seed, (None, None))
            if bridge is None:
                raise RuntimeError(f"selected-M path unavailable for native observation: {candidate_id}/{deployment_seed}")
            by_seed[deployment_seed] = {
                row["issue_instance"]: _native_observation(bridge[(candidate_id, row["issue_instance"])])
                for row in self.calendar
            }
        return by_seed[deployment_seed]

    def inject_native_observations(self, rows: Iterable[dict[str, object]]) -> None:
        """Load the Phase-0 aggregate ticket settlement cache without tickets."""
        for row in rows:
            candidate_id = str(row["candidate_id"])
            seed = str(row["deployment_seed"])
            issue = str(row["issue_instance"])
            self._native_observations.setdefault(candidate_id, {}).setdefault(seed, {})[issue] = {
                "return": float(row["native_pre_tax_return"]),
                "stake": float(row["native_actual_stake_yuan"]),
                "gross": float(row["native_pre_tax_gross_yuan"]),
                "hits": int(row["native_hit_ticket_count"]),
                "available": bool(row["native_outcome_available"]),
            }

    def release_candidate_paths(self, candidate_id: str, *, release_h1: bool = False) -> None:
        """Drop temporary ticket-lot objects after their aggregate cache is bound."""
        self._paths.pop(candidate_id, None)
        if release_h1:
            global _H1_TICKET_BRIDGE
            _H1_TICKET_BRIDGE = None
        gc.collect()

    def bundle(self, candidates: Sequence[str], bundle_id: str) -> tuple[dict[tuple[str, str], IssueSleeve], list[dict[str, object]]]:
        bundles = frozen_replicate_bundles()
        seed_map = bundles.get(bundle_id)
        if seed_map is None or any(candidate not in seed_map for candidate in candidates):
            raise RuntimeError(f"candidate absent from frozen bundle: {bundle_id}")
        bridges: list[dict[tuple[str, str], IssueSleeve]] = []
        selected_rows: list[dict[str, object]] = []
        for candidate in candidates:
            seed = "NA" if seed_map[candidate] == "DETERMINISTIC" else seed_map[candidate]
            bridge, selected = self.paths(candidate).get(seed, (None, None))
            if bridge is None or selected is None:
                raise RuntimeError(f"frozen bundle seed unavailable: {candidate}/{seed}")
            bridges.append(bridge)
            selected_rows.extend([{**row, "deployment_replicate_bundle_id": bundle_id} for row in selected])
        return merge_candidate_bridges(*bridges), selected_rows


def materialize_phase_zero_selection_checkpoint(
    checkpoint: Path,
    *,
    cache: CandidatePathCache | None = None,
) -> dict[str, object]:
    """Persist all frozen selected-M paths before Phase-1 pair screening."""
    cache = cache or CandidatePathCache()
    selected: list[dict[str, object]] = []
    native: list[dict[str, object]] = []
    expected = 0
    h1_remaining = set(H1_SLEEVES)
    catalog = canonical_economic_catalog()
    # Process the three shared #170 ticket-ledger sleeves together so their
    # million-ish lot objects can be released before the expanded catalog.
    candidate_order = [*H1_SLEEVES, *sorted(set(catalog) - set(H1_SLEEVES))]
    for candidate_id in candidate_order:
        paths = cache.paths(candidate_id)
        for seed, (_, rows) in paths.items():
            # Materialize every ticket-level native source outcome once while
            # this Phase-0 cache owns the selected source surface.
            observations = cache.native_observations(candidate_id, seed)
            expected += len(rows)
            for row in rows:
                issue = str(row["issue_instance"])
                observation = observations[issue]
                selected.append({"record_type": "SELECTED_M_PATH", "candidate_id": candidate_id, "deployment_seed": seed,
                    "issue_instance": row["issue_instance"], "calendar_index": row["calendar_index"],
                    "selected_M": row["selected_M"], "selection_variant": row["selection_variant"],
                    "prior_training_input_sha256": row["prior_training_input_sha256"]})
                native.append({"record_type": "NATIVE_ISSUE_SETTLEMENT", "candidate_id": candidate_id,
                    "deployment_seed": seed, "issue_instance": issue,
                    "native_pre_tax_return": observation["return"],
                    "native_actual_stake_yuan": observation["stake"],
                    "native_pre_tax_gross_yuan": observation["gross"],
                    "native_hit_ticket_count": observation["hits"],
                    "native_outcome_available": observation["available"]})
        if candidate_id in h1_remaining:
            h1_remaining.remove(candidate_id)
        # Native outcomes and selected-M decisions above are sufficient for
        # Phase-1.  Retaining source ticket lots across 104 families breaches
        # the resource envelope without adding scientific information.
        cache.release_candidate_paths(candidate_id, release_h1=not h1_remaining)
    if len(selected) != expected:
        raise RuntimeError(f"Phase-0 selected-path count drift: {len(selected)} != {expected}")
    if len(native) != expected:
        raise RuntimeError(f"Phase-0 native-outcome count drift: {len(native)} != {expected}")
    binding = {"gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
        "gate_a_content_sha256": EXPECTED_GATE_A_CONTENT,
        "settled_source_bindings": verify_gate_a_source_bindings(),
        "h1_ticket_cache_identity": _h1_ticket_cache_identity(),
        "phase0_materializer_contract": PHASE0_MATERIALIZER_CONTRACT,
        "phase": "PHASE_0_SELECTED_M_PATHS"}
    return write_surface_checkpoint(checkpoint, binding=binding, completed_path_keys=[*selected, *native])


def _native_observation(sleeve: IssueSleeve) -> dict[str, float | int | bool]:
    """Return one immutable native-flow observation without rescaling a ticket.

    A zero-flow issue remains an observation.  This is important for the
    complete holding calendar: dropping it would turn an abstention or an
    unavailable source outcome into an apparent correlation improvement.
    """
    executable = sleeve.status == "SETTLED" and sleeve.requested_ticket_count > 0
    settled = sleeve.settle_prefix(sleeve.requested_ticket_count) if executable else sleeve.settle_prefix(0)
    stake = float(settled["actual_stake_yuan"])
    return {
        "return": float(settled["pre_tax_net_yuan"]) / stake if stake else 0.0,
        "stake": stake,
        "gross": float(settled["gross_yuan"]),
        "hits": int(settled["hit_ticket_count"]),
        "available": sleeve.status == "SETTLED",
    }


def _worst_decile_overlap(left: Sequence[float], right: Sequence[float]) -> float | None:
    """Jaccard overlap of deterministic lower-return deciles for one panel."""
    if not left or len(left) != len(right):
        return None
    count = max(1, math.ceil(len(left) * 0.10))
    left_bottom = set(sorted(range(len(left)), key=lambda idx: (left[idx], idx))[:count])
    right_bottom = set(sorted(range(len(right)), key=lambda idx: (right[idx], idx))[:count])
    union = left_bottom | right_bottom
    return len(left_bottom & right_bottom) / len(union) if union else None


def intrinsic_native_pair_dependence(
    left_id: str,
    right_id: str,
    bundle_id: str,
    *,
    path_cache: CandidatePathCache,
) -> list[dict[str, object]]:
    """Compute the bounded Phase-1 intrinsic native-flow pair screen.

    This is deliberately not a Stage-4 capital replay.  Each family supplies
    the outcome-settled, strictly-prior selected-M sleeve frozen in Phase 0;
    the output simply describes its matched native issue flows under one
    frozen ordinal replicate bundle.  The bundle is retained in every key so
    stochastic seed replicas never become a selectable mean path.
    """
    if left_id == right_id:
        raise ValueError("intrinsic pair needs two distinct economic families")
    catalog = canonical_economic_catalog()
    left_family = catalog[left_id]["economic_family_id"]
    right_family = catalog[right_id]["economic_family_id"]
    bundles = frozen_replicate_bundles()
    seed_map = bundles.get(bundle_id)
    if seed_map is None:
        raise RuntimeError(f"unknown frozen replicate bundle: {bundle_id}")
    left_seed = "NA" if seed_map[left_id] == "DETERMINISTIC" else seed_map[left_id]
    right_seed = "NA" if seed_map[right_id] == "DETERMINISTIC" else seed_map[right_id]
    left_observations = path_cache.native_observations(left_id, left_seed)
    right_observations = path_cache.native_observations(right_id, right_seed)
    observations: list[dict[str, object]] = []
    for row in sorted(path_cache.calendar, key=lambda item: (item["first_kickoff_ts"], item["issue_instance"])):
        issue = row["issue_instance"]
        left = left_observations[issue]
        right = right_observations[issue]
        observations.append({"issue_instance": issue, "left": left, "right": right})
    pair_id = canonical_hash({"left": left_id, "right": right_id})
    base = {
        "portfolio_id": pair_id,
        "mode": "NATIVE_REQUEST_CONTROL",
        "position_fraction": "1.00",
        "weight_method": "NOT_APPLICABLE_INTRINSIC_NATIVE_FLOW",
        "normalization_method": "NOT_APPLICABLE_INTRINSIC_NATIVE_FLOW",
        "deployment_replicate_bundle_id": bundle_id,
        "economic_family_left": left_family,
        "economic_family_right": right_family,
        "native_return_basis": "PRE_TAX_NET_OVER_NATIVE_STAKE;ZERO_FOR_CALENDAR_NO_BET_OR_UNAVAILABLE",
    }
    rows: list[dict[str, object]] = []
    denominators = (
        ("FULL_CALENDAR_ZERO_FLOW", observations),
        ("UNION_ACTIVE", [item for item in observations if item["left"]["stake"] > 0 or item["right"]["stake"] > 0]),
        ("INTERSECTION_ACTIVE", [item for item in observations if item["left"]["stake"] > 0 and item["right"]["stake"] > 0]),
    )
    for denominator_id, selected in denominators:
        left_values = [float(item["left"]["return"]) for item in selected]
        right_values = [float(item["right"]["return"]) for item in selected]
        metrics: dict[str, float | None] = {
            "PEARSON_RETURN": _pearson(left_values, right_values),
            "SPEARMAN_RETURN": _pearson(_average_ranks(left_values), _average_ranks(right_values)) if selected else None,
            "DOWNSIDE_CORRELATION": _pearson([min(value, 0.0) for value in left_values], [min(value, 0.0) for value in right_values]),
            "JOINT_LOSS_RATE": sum(a < 0.0 and b < 0.0 for a, b in zip(left_values, right_values, strict=True)) / len(selected) if selected else None,
            "WORST_DECILE_OVERLAP_RATE": _worst_decile_overlap(left_values, right_values),
            "PAYOUT_OVERLAP_RATE": sum(item["left"]["gross"] > 0.0 and item["right"]["gross"] > 0.0 for item in selected) / len(selected) if selected else None,
            "HIT_OVERLAP_RATE": sum(item["left"]["hits"] > 0 and item["right"]["hits"] > 0 for item in selected) / len(selected) if selected else None,
        }
        support_hash = canonical_hash([item["issue_instance"] for item in selected])
        for metric, value in metrics.items():
            rows.append({
                **base,
                "denominator_id": denominator_id,
                "panel_type": "OVERALL",
                "panel_id": "STRICTLY_PRIOR_SELECTED_M",
                "window_issues": "",
                "exclusion_id": "",
                "metric": metric,
                "value": value,
                "observation_count": len(selected),
                "undefined_reason": "LT2_OR_ZERO_VARIANCE" if value is None else "",
                "matched_support_hash": support_hash,
            })
    return rows


def phase_one_intrinsic_screen(
    checkpoint: Path,
    *,
    path_cache: CandidatePathCache | None = None,
    candidate_pairs: Sequence[tuple[str, str]] | None = None,
) -> dict[str, object]:
    """Persist the complete/bounded Phase-1 native screening surface.

    The phase has no Stage-4 capital-grid cross product: all standalone M
    curves are native aggregates and pairs are only intrinsic matched-flow
    diagnostics.  The output stays in `.scratch` as a hash-bound checkpoint
    until the later detailed core frontier has completed successfully.
    """
    cache = path_cache or CandidatePathCache()
    catalog = canonical_economic_catalog()
    expected_phase0 = {
        "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
        "gate_a_content_sha256": EXPECTED_GATE_A_CONTENT,
        "settled_source_bindings": verify_gate_a_source_bindings(),
        "h1_ticket_cache_identity": _h1_ticket_cache_identity(),
        "phase0_materializer_contract": PHASE0_MATERIALIZER_CONTRACT,
        "phase": "PHASE_0_SELECTED_M_PATHS",
    }
    # The checkpoint is a binding guard plus the immutable aggregate outcome
    # cache.  Pair screening therefore never re-enumerates a source ticket.
    phase0_checkpoint = ROOT / PHASE0_CHECKPOINT
    phase0_rows = load_surface_checkpoint(phase0_checkpoint, binding=expected_phase0)
    selected_paths = [row for row in phase0_rows if row.get("record_type") == "SELECTED_M_PATH"]
    native_paths = [row for row in phase0_rows if row.get("record_type") == "NATIVE_ISSUE_SETTLEMENT"]
    if len(selected_paths) != len(native_paths) or not selected_paths:
        raise RuntimeError("Phase-0 selected/native cache denominator drift")
    cache.inject_native_observations(native_paths)
    curves: list[dict[str, object]] = []
    h1_remaining = set(H1_SLEEVES)
    candidate_order = [*H1_SLEEVES, *sorted(set(catalog) - set(H1_SLEEVES))]
    for candidate_id in candidate_order:
        curves.extend(standalone_m_curve(candidate_id))
        if candidate_id in h1_remaining:
            h1_remaining.remove(candidate_id)
        if not h1_remaining:
            # Phase-1 pair rows consume the aggregate cache above, not the
            # source tax lots.  Release the expensive H1 ticket bridge before
            # reading the expanded source families.
            global _H1_TICKET_BRIDGE
            _H1_TICKET_BRIDGE = None
            gc.collect()
    pairs = list(candidate_pairs or frozen_portfolio_sets()["pairwise"])
    if len({tuple(sorted(pair)) for pair in pairs}) != len(pairs):
        raise RuntimeError("Phase-1 intrinsic pair duplication")
    intrinsic = [
        row
        for left_id, right_id in pairs
        for bundle_id in sorted(frozen_replicate_bundles())
        for row in intrinsic_native_pair_dependence(left_id, right_id, bundle_id, path_cache=cache)
    ]
    binding = {
        "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
        "gate_a_content_sha256": EXPECTED_GATE_A_CONTENT,
        "settled_source_bindings": verify_gate_a_source_bindings(),
        "phase": "PHASE_1_NATIVE_CURVES_AND_INTRINSIC_PAIRS",
        "phase0_checkpoint_sha256": sha256_file(phase0_checkpoint),
        "pair_count": len(pairs),
    }
    payload = [
        *({"table": "standalone_m_curve", **row} for row in curves),
        *({"table": "intrinsic_native_dependence", **row} for row in intrinsic),
        *({"table": "selected_m_path", **row} for row in selected_paths),
    ]
    return write_surface_checkpoint(checkpoint, binding=binding, completed_path_keys=payload)


def replay_bundle_path(
    candidates: Sequence[str],
    bundle_id: str,
    *,
    mode: str,
    fraction: float,
    weight_method: str,
    normalization_method: str,
    calendar: Sequence[dict[str, str]] | None = None,
    path_cache: CandidatePathCache | None = None,
) -> dict[str, object]:
    """Replay one fixed candidate set under its exact replicate-bundle map."""
    calendar = list(calendar or read_csv(GATE_A / "full_calendar.csv"))
    candidates = tuple(sorted(candidates))
    bridge, selected_m = (
        path_cache.bundle(candidates, bundle_id)
        if path_cache is not None
        else build_bundle_bridges(candidates, bundle_id, calendar)
    )
    trace_identity = canonical_hash({
        "candidates": candidates,
        "bundle": bundle_id,
        "selected_m_path": selected_m,
    })
    path = replay_path(
        sleeves=candidates,
        mode=mode,
        fraction=fraction,
        weight_method=weight_method,
        normalization_method=normalization_method,
        bridge=bridge,
        calendar=calendar,
        bundle_id=bundle_id,
        sleeve_trace_identity=trace_identity,
    )
    tables = path_output_tables(path, bridge)
    tables["selected_m_path"] = selected_m
    return {"bridge": bridge, "path": path, "tables": tables, "sleeve_trace_identity": trace_identity}


def candidate_aliases(candidate_id: str) -> tuple[str, ...]:
    catalog = canonical_economic_catalog()
    canonical = catalog.get(candidate_id)
    if canonical is None:
        raise RuntimeError(f"unknown canonical candidate: {candidate_id}")
    family = canonical["economic_family_id"]
    return tuple(sorted(
        row["candidate_id"]
        for row in read_csv(GATE_A / "economic_family_registry.csv")
        if row["economic_family_id"] == family
    ))


def standalone_m_curve(candidate_id: str) -> list[dict[str, object]]:
    """Aggregate every frozen native M/seed sleeve before Stage-4 positioning."""
    catalog = canonical_economic_catalog()
    family = catalog.get(candidate_id)
    if family is None:
        raise RuntimeError(f"unknown canonical candidate: {candidate_id}")
    surface = materialize_candidate_m_surface(candidate_id)
    groups: dict[tuple[int, str], list[IssueSleeve]] = defaultdict(list)
    for (m_value, seed, _), sleeve in surface.items():
        groups[(m_value, seed)].append(sleeve)
    support = sorted({issue for _, _, issue in surface})
    alias_hash = canonical_hash(candidate_aliases(candidate_id))
    rows: list[dict[str, object]] = []
    for (m_value, seed), sleeves in sorted(groups.items()):
        if len(sleeves) != 348:
            raise RuntimeError(f"standalone curve support drift: {candidate_id}@{m_value}@{seed}")
        settlements = [sleeve.settle_prefix(sleeve.requested_ticket_count if sleeve.status == "SETTLED" else 0) for sleeve in sleeves]
        stake = sum(float(row["actual_stake_yuan"]) for row in settlements)
        net = sum(float(row["pre_tax_net_yuan"]) for row in settlements)
        rows.append({
            "economic_family_id": family["economic_family_id"],
            "canonical_candidate_id": candidate_id,
            "candidate_aliases_sha256": alias_hash,
            "M": m_value,
            "deployment_replicate_bundle_id": "NATIVE_SOURCE_CURVE",
            "deployment_seed": seed,
            "support_hash": canonical_hash(support),
            "requested_ticket_count": sum(sleeve.requested_ticket_count for sleeve in sleeves),
            "actual_ticket_count": sum(int(row["actual_ticket_count"]) for row in settlements),
            "pre_tax_net_yuan": net,
            "pre_tax_roi": net / stake if stake else None,
            "selection_eligible": int(stake > 0),
            "undefined_reason": "" if stake else "ZERO_NATIVE_STAKE",
        })
    return rows


def fixed_m_candidate_bridge(
    candidate_id: str,
    deployment_seed: str,
    calendar: Sequence[dict[str, str]] | None = None,
) -> dict[tuple[str, str], IssueSleeve]:
    """Return the immutable fixed-M comparator path required alongside WFO M."""
    calendar = list(calendar or read_csv(GATE_A / "full_calendar.csv"))
    fixed_m = frozen_m_grid(candidate_id)[0] if canonical_economic_catalog()[candidate_id]["source_kind"] == "H1_FIXED" else fixed_m_comparator(candidate_id)
    return materialize_candidate_bridge(candidate_id, fixed_m, deployment_seed)


def frozen_portfolio_sets() -> dict[str, list[tuple[str, ...]]]:
    """Enumerate the Gate-A standalone, all-pair and robust K surfaces exactly."""
    from itertools import combinations

    frontier = json.loads((GATE_A / "frontier_contract.json").read_text(encoding="utf-8"))
    candidates = tuple(sorted(frontier["eligible_candidate_sources"]))
    if set(candidates) != set(canonical_economic_catalog()):
        raise RuntimeError("frontier/catalog canonical family mismatch")
    pairwise = [tuple(sorted(pair)) for pair in frontier["pairwise_surface"]]
    if len(pairwise) != len(set(pairwise)) or set(pairwise) != set(combinations(candidates, 2)):
        raise RuntimeError("all-pairs frozen surface mismatch")
    higher: list[tuple[str, ...]] = []
    for serialized in frontier["robust_higher_order_shortlist"]:
        shortlist = tuple(serialized.split("|"))
        if any(candidate not in candidates for candidate in shortlist):
            raise RuntimeError("robust shortlist outside canonical catalog")
        higher.extend(tuple(combo) for size in range(1, len(shortlist) + 1) for combo in combinations(shortlist, size))
    return {
        "standalone": [(candidate,) for candidate in candidates],
        "pairwise": pairwise,
        "higher_order": higher,
    }


def frozen_execution_axes() -> list[dict[str, object]]:
    """Materialize every valid Stage-4 execution axis from the Gate-A contract.

    This is intentionally a contract reader rather than a hand-written grid:
    adding or dropping a mode, fraction, weight, or normalization requires a
    new immutable Gate-A package.  ``EQUAL_CAPITAL`` is valid only for the
    equal-weight branch, as specified by the normalization contract.
    """
    card = json.loads((GATE_A / "gate_a_card.json").read_text(encoding="utf-8"))
    funding = json.loads((GATE_A / "funding_algorithm.json").read_text(encoding="utf-8"))
    normalization = json.loads((GATE_A / "normalization_contract.json").read_text(encoding="utf-8"))
    weights = tuple(card["methodology_contract"]["weight_methods"])
    modes = tuple(sorted(funding["modes"]))
    fractions = tuple(float(value) for value in funding["position_budget_fractions"])
    methods = tuple(sorted(normalization["methods"]))
    rows: list[dict[str, object]] = []
    for mode in modes:
        allowed_fractions = (1.0,) if mode == "NATIVE_REQUEST_CONTROL" else fractions
        for fraction in allowed_fractions:
            for weight_method in weights:
                for normalization_method in methods:
                    if normalization_method == "EQUAL_CAPITAL" and weight_method != "EQUAL_WEIGHT":
                        continue
                    rows.append({
                        "mode": mode,
                        "position_fraction": fraction,
                        "weight_method": weight_method,
                        "normalization_method": normalization_method,
                    })
    if not rows or len({canonical_hash(row) for row in rows}) != len(rows):
        raise RuntimeError("invalid frozen execution axis enumeration")
    return rows


def bounded_core_memberships() -> dict[str, tuple[tuple[str, ...], ...]]:
    """Return exactly the PI-authorized Phase-1 executable memberships."""
    h1_triple = tuple(sorted(H1_SLEEVES))
    robust_prefixes = tuple(tuple(sorted(ROBUST_SLEEVES[:size])) for size in (3, 4, 5))
    result = {
        "STANDALONE": tuple((candidate,) for candidate in CORE_SLEEVES),
        "PAIR": tuple(tuple(pair) for pair in combinations(sorted(CORE_SLEEVES), 2)),
        "H1_TRIPLE": (h1_triple,),
        "ROBUST_PREFIX": robust_prefixes,
    }
    flattened = [membership for groups in result.values() for membership in groups]
    if len(flattened) != 40 or len(set(flattened)) != len(flattened):
        raise RuntimeError("bounded core membership contract drift")
    return result


def bounded_core_execution_axes() -> tuple[dict[str, object], ...]:
    """Filter the frozen gate-A axes to the bounded Phase-1 landmarks only."""
    valid = {
        canonical_hash(row): row
        for row in frozen_execution_axes()
    }
    rows: list[dict[str, object]] = []
    for mode in ("NATIVE_REQUEST_CONTROL", "FIXED_100K_NOTIONAL", "COMPOUNDING_BANKROLL"):
        fractions = (1.0,) if mode == "NATIVE_REQUEST_CONTROL" else (0.10, 0.25, 0.50, 1.00)
        for fraction in fractions:
            for weight_method in CORE_WEIGHT_METHODS:
                for normalization_method in CORE_NORMALIZATION_METHODS:
                    row = {
                        "mode": mode,
                        "position_fraction": fraction,
                        "weight_method": weight_method,
                        "normalization_method": normalization_method,
                    }
                    if canonical_hash(row) not in valid:
                        raise RuntimeError(f"bounded core axis absent from Gate A: {row}")
                    rows.append(row)
    if len(rows) != 72 or len({canonical_hash(row) for row in rows}) != 72:
        raise RuntimeError("bounded core landmark grid drift")
    return tuple(rows)


def minimal_stage4_memberships() -> tuple[tuple[str, ...], ...]:
    """Return the seven and only seven memberships of the final #192 closure.

    The 2026-08-06 minimal-closure amendment supersedes the earlier broad
    catalog screen.  These are not a post-outcome shortlist: every member is
    a deterministic H1 sleeve already frozen in the accepted Gate-A package.
    """
    members = tuple((sleeve,) for sleeve in H1_SLEEVES) + tuple(
        tuple(pair) for pair in combinations(sorted(H1_SLEEVES), 2)
    ) + (tuple(sorted(H1_SLEEVES)),)
    if len(members) != 7 or len(set(members)) != 7:
        raise RuntimeError("minimal Stage-4 membership contract drift")
    return members


def minimal_stage4_execution_axes() -> tuple[dict[str, object], ...]:
    """Read the final minimal capital grid from the immutable Gate-A axes.

    NATIVE remains at 1.0.  FIXED and COMPOUNDING retain only the four
    authorized fractions.  Both declared weighting and normalization methods
    are exercised; no historical search or additional normalization branch is
    admitted here.
    """
    valid = {canonical_hash(row): row for row in frozen_execution_axes()}
    rows: list[dict[str, object]] = []
    for mode in ("NATIVE_REQUEST_CONTROL", "FIXED_100K_NOTIONAL", "COMPOUNDING_BANKROLL"):
        fractions = (1.0,) if mode == "NATIVE_REQUEST_CONTROL" else (0.10, 0.25, 0.50, 1.00)
        for fraction in fractions:
            for weight_method in MINIMAL_WEIGHT_METHODS:
                for normalization_method in MINIMAL_NORMALIZATION_METHODS:
                    row = {
                        "mode": mode,
                        "position_fraction": fraction,
                        "weight_method": weight_method,
                        "normalization_method": normalization_method,
                    }
                    if canonical_hash(row) not in valid:
                        raise RuntimeError(f"minimal Stage-4 axis absent from Gate A: {row}")
                    rows.append(row)
    if len(rows) != 36 or len({canonical_hash(row) for row in rows}) != 36:
        raise RuntimeError("minimal Stage-4 capital grid drift")
    return tuple(rows)


def minimal_stage4_replay(
    checkpoint: Path,
    *,
    memberships: Sequence[tuple[str, ...]] | None = None,
    axes: Sequence[dict[str, object]] | None = None,
    bundles: Sequence[str] | None = None,
) -> dict[str, object]:
    """Settle the amended #192 Stage-4 closure once, exactly and atomically.

    This deliberately has no relationship to the earlier exploratory Phase-1
    or Phase-2 checkpoints.  It starts from immutable Gate-A ticket inputs,
    writes only its own resumable checkpoint and retains all per-issue path
    state necessary for the package finalizer.
    """
    selected_memberships = list(memberships or minimal_stage4_memberships())
    selected_axes = list(axes or minimal_stage4_execution_axes())
    selected_bundles = list(bundles or sorted(frozen_replicate_bundles()))
    if set(selected_memberships) - set(minimal_stage4_memberships()):
        raise RuntimeError("minimal Stage-4 contains an unauthorized membership")
    valid_axes = {canonical_hash(row) for row in minimal_stage4_execution_axes()}
    if any(canonical_hash(row) not in valid_axes for row in selected_axes):
        raise RuntimeError("minimal Stage-4 contains an unauthorized execution axis")
    if set(selected_bundles) - set(frozen_replicate_bundles()):
        raise RuntimeError("minimal Stage-4 contains an unknown replicate bundle")
    cache = CandidatePathCache()
    summaries: list[dict[str, object]] = []
    stability: list[dict[str, object]] = []
    for membership in selected_memberships:
        membership = tuple(sorted(membership))
        membership_id = canonical_hash({"membership": membership})
        for bundle_id in selected_bundles:
            bridge, selected_m = cache.bundle(membership, bundle_id)
            trace = canonical_hash({"membership": membership, "bundle": bundle_id, "selected_m": selected_m})
            for axis in selected_axes:
                replay_axis = {**axis, "fraction": axis["position_fraction"]}
                replay_axis.pop("position_fraction")
                path = replay_path(
                    sleeves=membership, bridge=bridge, calendar=cache.calendar,
                    bundle_id=bundle_id, sleeve_trace_identity=trace, **replay_axis,
                )
                holding = summarize_holding_path(path)["summary"]
                capital = capital_summary(path, holding)
                summaries.append({
                    "record_type": "MINIMAL_STAGE4_PATH_SUMMARY", "membership_id": membership_id,
                    "membership_json": json.dumps(membership, separators=(",", ":")),
                    "membership_size": len(membership),
                    "selected_m_path_sha256": canonical_hash(selected_m),
                    **capital,
                    **{key: holding[key] for key in (
                        "max_drawdown_yuan", "max_drawdown_fraction", "loss_streak_calendar",
                        "loss_streak_active", "miss_streak_calendar", "miss_streak_active",
                        "recovery_duration_max_issues", "time_under_water_issues", "sharpe",
                        "sortino", "calmar",
                    )},
                })
                stability.extend({
                    "record_type": "MINIMAL_STAGE4_REALIZED_STABILITY", **row,
                } for row in _realized_stability_rows(path, membership_id))
    binding = {
        "phase": "FINAL_GATE_B_MINIMAL_STAGE4_CLOSURE",
        "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
        "gate_a_content_sha256": EXPECTED_GATE_A_CONTENT,
        "membership_count": len(selected_memberships),
        "axis_count": len(selected_axes),
        "bundle_count": len(selected_bundles),
        "membership_contract_sha256": canonical_hash(minimal_stage4_memberships()),
        "axis_contract_sha256": canonical_hash(minimal_stage4_execution_axes()),
    }
    return write_surface_checkpoint(checkpoint, binding=binding, completed_path_keys=[*summaries, *stability])


def _realized_stability_rows(path: Sequence[dict[str, object]], membership_id: str) -> list[dict[str, object]]:
    """Subset diagnostics on one realized path; they never re-fit prior state."""
    rows: list[dict[str, object]] = []
    years = sorted({str(row["year"]) for row in path})
    panels = [("YEAR", year, [row for row in path if str(row["year"]) == year]) for year in years]
    panels += [("LOYO", year, [row for row in path if str(row["year"]) != year]) for year in years]
    largest = max(path, key=lambda row: (float(row["pre_tax_net_yuan"]), str(row["issue_instance"])))
    panels.append(("EX_LARGEST_ISSUE", str(largest["issue_instance"]), [row for row in path if row is not largest]))
    net_by_year = {year: sum(float(row["pre_tax_net_yuan"]) for row in path if str(row["year"]) == year) for year in years}
    largest_year = max(years, key=lambda year: (net_by_year[year], year))
    panels.append(("EX_LARGEST_YEAR", largest_year, [row for row in path if str(row["year"]) != largest_year]))
    for panel_type, panel_id, selected in panels:
        stake = sum(float(row["actual_stake_yuan"]) for row in selected)
        net = sum(float(row["pre_tax_net_yuan"]) for row in selected)
        rows.append({
            **{field: path[0][field] for field in PATH_IDENTITY}, "membership_id": membership_id,
            "panel_type": panel_type, "panel_id": panel_id, "issue_count": len(selected),
            "stake_yuan": stake, "pre_tax_net_yuan": net, "pre_tax_roi": net / stake if stake else None,
            "undefined_reason": "ZERO_STAKE" if not stake else "",
        })
    return rows


def phase_one_core_replay(
    checkpoint: Path,
    *,
    memberships: Sequence[tuple[str, ...]] | None = None,
    axes: Sequence[dict[str, object]] | None = None,
    bundles: Sequence[str] | None = None,
) -> dict[str, object]:
    """Run the bounded Stage-4 core frontier and atomically checkpoint summaries."""
    phase1 = ROOT / ".scratch" / "bj192_phase1_native_screen_checkpoint_v2.json"
    if not phase1.exists():
        raise RuntimeError("Phase-1 intrinsic screen checkpoint unavailable")
    group_map = bounded_core_memberships()
    selected_memberships = list(memberships or [item for group in group_map.values() for item in group])
    selected_axes = list(axes or bounded_core_execution_axes())
    selected_bundles = list(bundles or sorted(frozen_replicate_bundles()))
    cache = CandidatePathCache()
    summaries: list[dict[str, object]] = []
    stability: list[dict[str, object]] = []
    for membership in selected_memberships:
        membership = tuple(sorted(membership))
        membership_id = canonical_hash({"membership": membership})
        for bundle_id in selected_bundles:
            bridge, selected_m = cache.bundle(membership, bundle_id)
            trace = canonical_hash({"membership": membership, "bundle": bundle_id, "selected_m": selected_m})
            for axis in selected_axes:
                replay_axis = {**axis, "fraction": axis["position_fraction"]}
                replay_axis.pop("position_fraction")
                path = replay_path(sleeves=membership, bridge=bridge, calendar=cache.calendar, bundle_id=bundle_id,
                    sleeve_trace_identity=trace, **replay_axis)
                holding = summarize_holding_path(path)["summary"]
                capital = capital_summary(path, holding)
                summaries.append({
                    "record_type": "CORE_PATH_SUMMARY", "membership_id": membership_id,
                    "membership_json": json.dumps(membership, separators=(",", ":")),
                    "membership_size": len(membership), "selected_m_path_sha256": canonical_hash(selected_m),
                    **capital, **{key: holding[key] for key in ("max_drawdown_yuan", "max_drawdown_fraction", "loss_streak_calendar", "loss_streak_active", "miss_streak_calendar", "miss_streak_active", "recovery_duration_max_issues", "time_under_water_issues", "sharpe", "sortino", "calmar")},
                })
                stability.extend({"record_type": "CORE_REALIZED_STABILITY", **row} for row in _realized_stability_rows(path, membership_id))
    binding = {"phase": "PHASE_1_BOUNDED_CORE", "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
        "gate_a_content_sha256": EXPECTED_GATE_A_CONTENT,
        "phase0_checkpoint_sha256": sha256_file(ROOT / PHASE0_CHECKPOINT), "phase1_screen_sha256": sha256_file(phase1),
        "membership_count": len(selected_memberships), "axis_count": len(selected_axes), "bundle_count": len(selected_bundles)}
    return write_surface_checkpoint(checkpoint, binding=binding, completed_path_keys=[*summaries, *stability])


def phase_two_execution_axes() -> tuple[dict[str, object], ...]:
    """Return the complete frozen Phase-2 capital sensitivity axes.

    Phase 2 deliberately excludes the native-control and scaled-native rows:
    it expands only the two capital modes named by the bounded-execution
    amendment, across every frozen fraction/weight/normalization combination.
    """
    rows = tuple(
        row for row in frozen_execution_axes()
        if row["mode"] in {"FIXED_100K_NOTIONAL", "COMPOUNDING_BANKROLL"}
    )
    # EQUAL_CAPITAL is legal only for EQUAL_WEIGHT: 4 legal normalizations
    # there, plus 3 for each of the other five frozen weight methods.
    expected = 2 * 20 * 19
    if len(rows) != expected or len({canonical_hash(row) for row in rows}) != len(rows):
        raise RuntimeError("Phase-2 frozen capital sensitivity grid drift")
    return rows


def _phase_one_core_binding() -> dict[str, object]:
    phase1 = ROOT / ".scratch" / "bj192_phase1_native_screen_checkpoint_v2.json"
    return {
        "phase": "PHASE_1_BOUNDED_CORE",
        "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
        "gate_a_content_sha256": EXPECTED_GATE_A_CONTENT,
        "phase0_checkpoint_sha256": sha256_file(ROOT / PHASE0_CHECKPOINT),
        "phase1_screen_sha256": sha256_file(phase1),
        "membership_count": 40,
        "axis_count": len(bounded_core_execution_axes()),
        "bundle_count": len(frozen_replicate_bundles()),
    }


def _rank_descending(rows: Sequence[dict[str, object]], field: str) -> dict[str, int]:
    ordered = sorted(rows, key=lambda row: (-float(row[field]), str(row["membership_json"])))
    return {str(row["membership_json"]): index + 1 for index, row in enumerate(ordered)}


def _rank_ascending(rows: Sequence[dict[str, object]], field: str) -> dict[str, int]:
    ordered = sorted(rows, key=lambda row: (float(row[field]), str(row["membership_json"])))
    return {str(row["membership_json"]): index + 1 for index, row in enumerate(ordered)}


def select_phase_two_memberships(core_checkpoint: Path) -> list[dict[str, object]]:
    """Freeze the bounded Phase-2 membership set from the complete core panel.

    This is intentionally an outcome-sensitive *descriptive* screen.  It is
    not an edge claim: the selection rule is published with the result and
    uses six path/capital criteria jointly, never a single best ROI cell.
    """
    rows = load_surface_checkpoint(core_checkpoint, binding=_phase_one_core_binding())
    summaries = [row for row in rows if row.get("record_type") == "CORE_PATH_SUMMARY"]
    if len(summaries) != 40 * len(bounded_core_execution_axes()) * len(frozen_replicate_bundles()):
        raise RuntimeError("Phase-1 core summary denominator drift")
    by_identity = {
        (
            row["membership_json"], row["mode"], row["position_fraction"], row["weight_method"],
            row["normalization_method"], row["deployment_replicate_bundle_id"],
        ): row
        for row in summaries
    }
    full_json = json.dumps(("BEST_FULL_FULL",), separators=(",", ":"))
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in summaries:
        grouped[str(row["membership_json"])].append(row)
    screen: list[dict[str, object]] = []
    for membership_json, group in sorted(grouped.items()):
        lifts = []
        for row in group:
            comparator = by_identity.get((
                full_json, row["mode"], row["position_fraction"], row["weight_method"],
                row["normalization_method"], row["deployment_replicate_bundle_id"],
            ))
            if comparator is None:
                raise RuntimeError("matched BEST_FULL core comparator unavailable")
            lifts.append(float(row["ending_bankroll_yuan"]) - float(comparator["ending_bankroll_yuan"]))
        screen.append({
            "membership_json": membership_json,
            "membership_id": canonical_hash({"membership": tuple(json.loads(membership_json))}),
            "membership_size": len(json.loads(membership_json)),
            "core_cell_count": len(group),
            "median_ending_bankroll_yuan": _quantile([float(row["ending_bankroll_yuan"]) for row in group], 0.5),
            "worst_ending_bankroll_yuan": min(float(row["ending_bankroll_yuan"]) for row in group),
            "median_matched_full_lift_yuan": _quantile(lifts, 0.5),
            "median_max_drawdown_yuan": _quantile([float(row["max_drawdown_yuan"]) for row in group], 0.5),
            "median_recovery_duration_max_issues": _quantile([float(row["recovery_duration_max_issues"]) for row in group], 0.5),
            "median_turnover_yuan": _quantile([float(row["turnover_yuan"]) for row in group], 0.5),
            "bundle_min_ending_bankroll_yuan": min(
                _quantile([float(row["ending_bankroll_yuan"]) for row in group if row["deployment_replicate_bundle_id"] == bundle], 0.5)
                for bundle in frozen_replicate_bundles()
            ),
        })
    for field in ("median_ending_bankroll_yuan", "worst_ending_bankroll_yuan", "median_matched_full_lift_yuan", "bundle_min_ending_bankroll_yuan"):
        ranks = _rank_descending(screen, field)
        for row in screen:
            row[f"rank_{field}"] = ranks[str(row["membership_json"])]
    for field in ("median_max_drawdown_yuan", "median_recovery_duration_max_issues", "median_turnover_yuan"):
        ranks = _rank_ascending(screen, field)
        for row in screen:
            row[f"rank_{field}"] = ranks[str(row["membership_json"])]
    rank_fields = [field for field in screen[0] if field.startswith("rank_")]
    for row in screen:
        row["joint_path_rank_sum"] = sum(int(row[field]) for field in rank_fields)
    mandatory = {
        json.dumps(tuple(sorted(H1_SLEEVES)), separators=(",", ":")),
        json.dumps(tuple(sorted(ROBUST_SLEEVES)), separators=(",", ":")),
    }
    if not mandatory <= {str(row["membership_json"]) for row in screen}:
        raise RuntimeError("mandatory Phase-2 membership absent from core panel")
    metric_pairs = (
        ("median_ending_bankroll_yuan", True),
        ("worst_ending_bankroll_yuan", True),
        ("median_matched_full_lift_yuan", True),
        ("bundle_min_ending_bankroll_yuan", True),
        ("median_max_drawdown_yuan", False),
        ("median_recovery_duration_max_issues", False),
        ("median_turnover_yuan", False),
    )
    def dominates(left: dict[str, object], right: dict[str, object]) -> bool:
        comparisons = [
            float(left[field]) >= float(right[field]) if higher else float(left[field]) <= float(right[field])
            for field, higher in metric_pairs
        ]
        strict = [
            float(left[field]) > float(right[field]) if higher else float(left[field]) < float(right[field])
            for field, higher in metric_pairs
        ]
        return all(comparisons) and any(strict)
    nonmandatory = [row for row in screen if str(row["membership_json"]) not in mandatory]
    nondominated = [
        row for row in nonmandatory
        if not any(dominates(other, row) for other in nonmandatory if other is not row)
    ]
    selected_extras = sorted(
        nondominated,
        key=lambda row: (int(row["joint_path_rank_sum"]), -float(row["median_ending_bankroll_yuan"]), str(row["membership_json"])),
    )[:4]
    selected = mandatory | {str(row["membership_json"]) for row in selected_extras}
    for row in screen:
        row["record_type"] = "PHASE2_MEMBERSHIP_SELECTION"
        row["phase2_selected"] = int(str(row["membership_json"]) in selected)
        row["selection_status"] = (
            "MANDATORY_H1_OR_ROBUST_K5" if str(row["membership_json"]) in mandatory
            else "NONDOMINATED_JOINT_PATH_TOP4" if str(row["membership_json"]) in {str(item["membership_json"]) for item in selected_extras}
            else "NOT_SELECTED_BOUNDED_PHASE2"
        )
        row["selection_rule"] = "JOINT_BORDA_ENDING_LIFT_DRAWDOWN_RECOVERY_TURNOVER_BUNDLE_MIN;_NONDOMINATED_ONLY"
    result = sorted(screen, key=lambda row: (not bool(row["phase2_selected"]), int(row["joint_path_rank_sum"]), str(row["membership_json"])))
    if sum(int(row["phase2_selected"]) for row in result) > 6:
        raise RuntimeError("Phase-2 membership cap exceeded")
    return result


def phase_two_replay(
    checkpoint: Path,
    *,
    core_checkpoint: Path | None = None,
    memberships: Sequence[tuple[str, ...]] | None = None,
    axes: Sequence[dict[str, object]] | None = None,
    bundles: Sequence[str] | None = None,
) -> dict[str, object]:
    """Run every frozen Phase-2 capital axis for the bounded finalist set."""
    core_checkpoint = core_checkpoint or ROOT / ".scratch" / "bj192_phase1_core_checkpoint.json"
    selection = select_phase_two_memberships(core_checkpoint)
    selected_memberships = list(memberships or [tuple(json.loads(str(row["membership_json"]))) for row in selection if row["phase2_selected"]])
    selected_axes = list(axes or phase_two_execution_axes())
    selected_bundles = list(bundles or sorted(frozen_replicate_bundles()))
    if len(selected_memberships) > 6:
        raise RuntimeError("Phase-2 membership cap exceeded")
    cache = CandidatePathCache()
    summaries: list[dict[str, object]] = []
    stability: list[dict[str, object]] = []
    for membership in selected_memberships:
        membership = tuple(sorted(membership))
        membership_id = canonical_hash({"membership": membership})
        for bundle_id in selected_bundles:
            bridge, selected_m = cache.bundle(membership, bundle_id)
            trace = canonical_hash({"membership": membership, "bundle": bundle_id, "selected_m": selected_m})
            for axis in selected_axes:
                replay_axis = {**axis, "fraction": axis["position_fraction"]}
                replay_axis.pop("position_fraction")
                path = replay_path(sleeves=membership, bridge=bridge, calendar=cache.calendar, bundle_id=bundle_id,
                    sleeve_trace_identity=trace, **replay_axis)
                holding = summarize_holding_path(path)["summary"]
                capital = capital_summary(path, holding)
                summaries.append({
                    "record_type": "PHASE2_PATH_SUMMARY", "membership_id": membership_id,
                    "membership_json": json.dumps(membership, separators=(",", ":")),
                    "membership_size": len(membership), "selected_m_path_sha256": canonical_hash(selected_m),
                    **capital, **{key: holding[key] for key in ("max_drawdown_yuan", "max_drawdown_fraction", "loss_streak_calendar", "loss_streak_active", "miss_streak_calendar", "miss_streak_active", "recovery_duration_max_issues", "time_under_water_issues", "sharpe", "sortino", "calmar")},
                })
                stability.extend({"record_type": "PHASE2_REALIZED_STABILITY", **row} for row in _realized_stability_rows(path, membership_id))
    binding = {
        "phase": "PHASE_2_FULL_FROZEN_SENSITIVITY",
        "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
        "gate_a_content_sha256": EXPECTED_GATE_A_CONTENT,
        "phase1_core_checkpoint_sha256": sha256_file(core_checkpoint),
        "selection_sha256": canonical_hash(selection),
        "membership_count": len(selected_memberships),
        "axis_count": len(selected_axes),
        "bundle_count": len(selected_bundles),
    }
    return write_surface_checkpoint(checkpoint, binding=binding, completed_path_keys=[*selection, *summaries, *stability])


def surface_preflight_receipt() -> dict[str, object]:
    """Quantify the exact frozen Cartesian request before allocating output.

    This is a no-outcome, no-ticket-execution preflight.  It intentionally
    refuses to turn the requested all-pairs wording into an unreported grid
    reduction; callers can persist this receipt with a proposed run plan for
    PI review.
    """
    portfolios = frozen_portfolio_sets()
    bundles = frozen_replicate_bundles()
    calendar_count = len(read_csv(GATE_A / "full_calendar.csv"))
    axis_count = len(frozen_execution_axes())
    counts = {}
    for name, sets in portfolios.items():
        paths = len(sets) * axis_count * len(bundles)
        counts[name] = {
            "portfolio_set_count": len(sets),
            "capital_path_count": paths,
            "issue_path_row_count": paths * calendar_count,
        }
    return {
        "contract": CONTRACT,
        "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
        "gate_a_content_sha256": EXPECTED_GATE_A_CONTENT,
        "calendar_issue_count": calendar_count,
        "execution_axis_count": axis_count,
        "replicate_bundle_count": len(bundles),
        "surface": counts,
        "total_capital_path_count": sum(row["capital_path_count"] for row in counts.values()),
        "total_issue_path_row_count": sum(row["issue_path_row_count"] for row in counts.values()),
        "status": "PREFLIGHT_REQUIRES_EXPLICIT_EXECUTION_PLAN",
        "reason": "Gate-A schema says every pair/mode/fraction/weight/normalization/bundle row; no unapproved Cartesian reduction is applied.",
    }


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    left_ss = sum((value - left_mean) ** 2 for value in left)
    right_ss = sum((value - right_mean) ** 2 for value in right)
    if left_ss <= 0 or right_ss <= 0:
        return None
    return sum((a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True)) / math.sqrt(left_ss * right_ss)


def _average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (values[index], index))
    ranks = [0.0] * len(values)
    offset = 0
    while offset < len(order):
        end = offset + 1
        while end < len(order) and values[order[end]] == values[order[offset]]:
            end += 1
        rank = (offset + 1 + end) / 2.0
        for index in order[offset:end]:
            ranks[index] = rank
        offset = end
    return ranks


def _dependence_panel_specs(path_rows: Sequence[dict[str, object]]) -> list[tuple[str, str, str, int | str, list[dict[str, object]]]]:
    """Return the frozen, denominator-neutral chronology panels for one path.

    These panels deliberately retain zero-flow issues.  The caller applies the
    requested flow denominator afterwards, so an apparent correlation change
    cannot silently be caused by filtering out cash/no-bet periods.
    """
    ordered = sorted(path_rows, key=lambda row: (row["calendar_index"], row["issue_instance"]))
    panels: list[tuple[str, str, str, int | str, list[dict[str, object]]]] = [
        ("OVERALL", "FULL_PATH", "", "", ordered),
    ]
    for field, panel_type in (("year", "YEAR"), ("fold", "FOLD")):
        values = sorted({str(row[field]) for row in ordered})
        panels.extend((panel_type, value, "", "", [row for row in ordered if str(row[field]) == value]) for value in values)

    regime_by_issue = {
        row["issue_instance"]: row["regime_panel_id"]
        for row in read_csv(GATE_A / "regime_map.csv")
    }
    regimes = sorted({regime_by_issue.get(str(row["issue_instance"]), "UNMAPPED") for row in ordered})
    panels.extend(("REGIME", regime, "", "", [row for row in ordered if regime_by_issue.get(str(row["issue_instance"]), "UNMAPPED") == regime]) for regime in regimes)

    for width in (5, 10, 20):
        for start in range(0, max(0, len(ordered) - width + 1)):
            selected = ordered[start:start + width]
            panels.append(("ROLLING", f"{selected[0]['calendar_index']}:{selected[-1]['calendar_index']}", width, "", selected))

    # LOYO and ex-largest panels re-use the original chronological rows and
    # never reset/re-order capital state.  They are dependence diagnostics,
    # not a counterfactual funded replay.
    for year in sorted({str(row["year"]) for row in ordered}):
        panels.append(("LOYO", year, "", year, [row for row in ordered if str(row["year"]) != year]))
    largest_issue = max(ordered, key=lambda row: (float(row["pre_tax_net_yuan"]), str(row["issue_instance"])))
    panels.append(("EX_LARGEST_ISSUE", str(largest_issue["issue_instance"]), "", str(largest_issue["issue_instance"]), [row for row in ordered if row is not largest_issue]))
    year_net = {year: sum(float(row["pre_tax_net_yuan"]) for row in ordered if str(row["year"]) == year) for year in {str(row["year"]) for row in ordered}}
    largest_year = max(year_net, key=lambda year: (year_net[year], year))
    panels.append(("EX_LARGEST_YEAR", largest_year, "", largest_year, [row for row in ordered if str(row["year"]) != largest_year]))
    return panels


def realized_funded_flow_dependence(path_rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    """Emit denominator-explicit funded-flow dependence for every frozen panel."""
    if not path_rows:
        return []
    catalog = canonical_economic_catalog()
    sleeves = tuple(sorted(path_rows[0]["sleeve_settlements"]))
    result: list[dict[str, object]] = []
    for left_id, right_id in __import__("itertools").combinations(sleeves, 2):
        left_family = catalog[left_id]["economic_family_id"]
        right_family = catalog[right_id]["economic_family_id"]
        for panel_type, panel_id, window_issues, exclusion_id, panel_rows in _dependence_panel_specs(path_rows):
            observations: list[dict[str, float]] = []
            for row in panel_rows:
                left = row["sleeve_settlements"][left_id]
                right = row["sleeve_settlements"][right_id]
                left_stake, right_stake = float(left["actual_stake_yuan"]), float(right["actual_stake_yuan"])
                observations.append({
                    "left_return": float(left["pre_tax_net_yuan"]) / left_stake if left_stake else 0.0,
                    "right_return": float(right["pre_tax_net_yuan"]) / right_stake if right_stake else 0.0,
                    "left_stake": left_stake, "right_stake": right_stake,
                    "left_gross": float(left["gross_yuan"]), "right_gross": float(right["gross_yuan"]),
                    "left_hits": float(left["hit_ticket_count"]), "right_hits": float(right["hit_ticket_count"]),
                })
            for denominator, selected in (
                ("FULL_CALENDAR_ZERO_FLOW", observations),
                ("UNION_ACTIVE", [row for row in observations if row["left_stake"] > 0 or row["right_stake"] > 0]),
                ("INTERSECTION_ACTIVE", [row for row in observations if row["left_stake"] > 0 and row["right_stake"] > 0]),
            ):
                left_values = [row["left_return"] for row in selected]
                right_values = [row["right_return"] for row in selected]
                downside_left = [min(value, 0.0) for value in left_values]
                downside_right = [min(value, 0.0) for value in right_values]
                metrics: dict[str, float | None] = {
                    "PEARSON": _pearson(left_values, right_values),
                    "SPEARMAN": _pearson(_average_ranks(left_values), _average_ranks(right_values)) if selected else None,
                    "DOWNSIDE_CORRELATION": _pearson(downside_left, downside_right),
                    "JOINT_LOSS_RATE": sum(a < 0 and b < 0 for a, b in zip(left_values, right_values, strict=True)) / len(selected) if selected else None,
                    "PAYOUT_OVERLAP_COUNT": float(sum(row["left_gross"] > 0 and row["right_gross"] > 0 for row in selected)),
                    "HIT_OVERLAP_COUNT": float(sum(row["left_hits"] > 0 and row["right_hits"] > 0 for row in selected)),
                }
                for metric, value in metrics.items():
                    result.append({
                        **{field: path_rows[0][field] for field in PATH_IDENTITY},
                        "economic_family_left": left_family,
                        "economic_family_right": right_family,
                        "denominator_id": denominator,
                        "panel_type": panel_type,
                        "panel_id": panel_id,
                        "window_issues": window_issues,
                        "exclusion_id": exclusion_id,
                        "metric": metric,
                        "value": value,
                        "observation_count": len(selected),
                        "active_observation_count": len(selected),
                        "undefined_reason": "" if value is not None else "LT2_OR_ZERO_VARIANCE",
                        "first_calendar_index": panel_rows[0]["calendar_index"] if selected else "",
                        "last_calendar_index": panel_rows[-1]["calendar_index"] if selected else "",
                    })
    return result


def merge_candidate_bridges(
    *bridges: dict[tuple[str, str], IssueSleeve],
) -> dict[tuple[str, str], IssueSleeve]:
    """Combine disjoint frozen candidate paths without replacing a sleeve."""
    result: dict[tuple[str, str], IssueSleeve] = {}
    for bridge in bridges:
        for key, sleeve in bridge.items():
            if key in result:
                raise RuntimeError(f"duplicate candidate bridge key: {key}")
            result[key] = sleeve
    return result


def _h1_ticket_cache_path() -> Path:
    return ROOT / ".scratch" / "bj192_h1_ticket_lots_v1.sqlite"


def _h1_ticket_cache_identity() -> str:
    return canonical_hash({
        "schema": H1_TICKET_CACHE_SCHEMA,
        "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
        "gate_a_content_sha256": EXPECTED_GATE_A_CONTENT,
        "bj170_runner_sha256": EXPECTED_BJ170_RUNNER,
        "source_binding": verify_gate_a_source_bindings()["bj170_gate_b_selector_allocator_stack_v1"],
    })


def _load_h1_ticket_cache() -> dict[tuple[str, str], NativeIssueSleeve] | None:
    """Rehydrate ordered H1 tax lots without invoking the #170 settler again."""
    path = _h1_ticket_cache_path()
    if not path.exists():
        return None
    connection = sqlite3.connect(path)
    try:
        meta = dict(connection.execute("SELECT key, value FROM cache_meta"))
        if meta.get("identity") != _h1_ticket_cache_identity():
            raise RuntimeError("H1 ticket cache binding drift")
        requests = {
            (row["sleeve_id"], row["issue_instance"]): row
            for row in read_csv(GATE_A / "frozen_native_sleeve_requests.csv")
            if row["sleeve_id"] in H1_SLEEVES
        }
        policy = {
            (row["sleeve_id"], row["issue_instance"]): row
            for row in read_csv(GATE_A / "ticket_prefix_policy_registry.csv")
            if row["sleeve_id"] in H1_SLEEVES
        }
        lots: dict[tuple[str, str], list[TicketLot]] = defaultdict(list)
        for sleeve, issue, rank, tax_lot_id, portfolio_id, ticket_ordinal, available, truth, payout in connection.execute(
            "SELECT sleeve_id, issue_instance, rank, tax_lot_id, portfolio_id, ticket_ordinal, outcome_available, truth_ordinal, payout_yuan FROM ticket_lots ORDER BY sleeve_id, issue_instance, rank"
        ):
            lots[(sleeve, issue)].append(TicketLot(
                rank=int(rank), tax_lot_id=tax_lot_id, portfolio_id=portfolio_id,
                ticket_ordinal=int(ticket_ordinal), outcome_available=bool(available),
                truth_ordinal=int(truth), payout_yuan=float(payout),
            ))
        bridge: dict[tuple[str, str], NativeIssueSleeve] = {}
        for key, request in requests.items():
            ordered = tuple(lots.get(key, ()))
            requested = int(request["native_requested_ticket_count"])
            if len(ordered) != requested or [lot.rank for lot in ordered] != list(range(1, requested + 1)):
                raise RuntimeError(f"H1 cached tax-lot denominator drift: {key}")
            status = request["native_policy_status"]
            if any(not lot.outcome_available for lot in ordered) and status == "SELECTED_PREOUTCOME":
                status = "UNAVAILABLE_CANONICAL_OUTCOME"
            bridge[key] = NativeIssueSleeve(
                sleeve_id=key[0], issue_instance=key[1], status="SETTLED" if status == "SELECTED_PREOUTCOME" else status,
                requested_ticket_count=requested,
                atomic=any(item["prefix_status"] == "WHOLE_NATIVE_OR_NO_BET" for pkey, item in policy.items() if pkey[:2] == key),
                lots=ordered,
            )
        if len(bridge) != 3 * 348:
            raise RuntimeError("H1 cached bridge denominator drift")
        return bridge
    finally:
        connection.close()


def _write_h1_ticket_cache(bridge: dict[tuple[str, str], NativeIssueSleeve]) -> None:
    """Atomically retain the exact #170-settled H1 ticket lots in `.scratch`."""
    path = _h1_ticket_cache_path()
    stage = path.with_name(f".{path.name}.stage")
    if path.exists():
        return
    if stage.exists():
        raise RuntimeError(f"H1 ticket cache stage already exists: {stage}")
    connection = sqlite3.connect(stage)
    try:
        connection.execute("CREATE TABLE cache_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("CREATE TABLE ticket_lots (sleeve_id TEXT, issue_instance TEXT, rank INTEGER, tax_lot_id TEXT, portfolio_id TEXT, ticket_ordinal INTEGER, outcome_available INTEGER, truth_ordinal INTEGER, payout_yuan REAL, PRIMARY KEY(sleeve_id, issue_instance, rank))")
        connection.executemany("INSERT INTO cache_meta(key, value) VALUES (?, ?)", [
            ("identity", _h1_ticket_cache_identity()),
            ("schema", H1_TICKET_CACHE_SCHEMA),
            ("ticket_lot_count", str(sum(len(item.lots) for item in bridge.values()))),
        ])
        connection.executemany(
            "INSERT INTO ticket_lots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                (sleeve_id, issue, lot.rank, lot.tax_lot_id, lot.portfolio_id, lot.ticket_ordinal,
                 int(lot.outcome_available), lot.truth_ordinal, lot.payout_yuan)
                for (sleeve_id, issue), sleeve in sorted(bridge.items())
                for lot in sleeve.lots
            ),
        )
        connection.commit()
        connection.close()
        os.replace(stage, path)
    except Exception:
        connection.close()
        stage.unlink(missing_ok=True)
        raise


def h1_ticket_bridge() -> dict[tuple[str, str], NativeIssueSleeve]:
    """Recreate Gate-A's H1 prefix ledger from the accepted #170 ticket replay.

    The rows in ``ticket_prefix_registry`` are immutable ordered tax lots.
    Their winning status/payout is reconstructed with #170's manifest-covered
    ticket settler rather than by rescaling an issue ROI.
    """
    global _H1_TICKET_BRIDGE
    if _H1_TICKET_BRIDGE is not None:
        return _H1_TICKET_BRIDGE
    cached = _load_h1_ticket_cache()
    if cached is not None:
        _H1_TICKET_BRIDGE = cached
        return cached
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
    _write_h1_ticket_cache(bridge)
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
    sleeve_trace_identity: str | None = None,
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
    portfolio_id = canonical_hash({
        "sleeves": sleeves,
        "stage": "STAGE4",
        "sleeve_trace_identity": sleeve_trace_identity or canonical_hash(list(sleeves)),
    })
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
        if native_stake == 0.0:
            funding = {"actual_ticket_count_by_sleeve": {s: 0 for s in sleeves}, "reason_codes": "NO_NATIVE_REQUEST", "mode_notional_yuan": raw_notional, "issue_budget_yuan": 0.0, "retained_cash_yuan": bankroll, "actual_total_stake_yuan": 0.0}
        elif bankroll < TICKET_STAKE_YUAN:
            funding = {"actual_ticket_count_by_sleeve": {s: 0 for s in sleeves}, "reason_codes": "RUIN_NO_BET", "mode_notional_yuan": raw_notional, "issue_budget_yuan": 0.0, "retained_cash_yuan": bankroll, "actual_total_stake_yuan": 0.0}
        elif normalization["normalization_executable"]:
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
            if capped_tickets <= 0:
                # The frozen allocator intentionally rejects a zero fraction.
                # A positive native request can nevertheless be reduced below
                # one ¥2 ticket by the pre-outcome normalization cap.  This is
                # an executable cash row, not an allocator error or a hidden
                # fractional ticket.
                funding = {
                    "actual_ticket_count_by_sleeve": {s: 0 for s in sleeves},
                    "reason_codes": "NO_BET_NORMALIZED_BUDGET_LT_TICKET",
                    "mode_notional_yuan": raw_notional,
                    "issue_budget_yuan": 0.0,
                    "retained_cash_yuan": bankroll,
                    "actual_total_stake_yuan": 0.0,
                }
            else:
                funding = gate.allocate_integer_tickets(
                    "SCALED_NATIVE_REQUEST",
                    min(1.0, capped_tickets * TICKET_STAKE_YUAN / native_stake),
                    int(math.floor(bankroll)),
                    requested_caps,
                    weights,
                    {sleeve: item.atomic for sleeve, item in issue_sleeves.items()},
                )
            # Allocation is invoked through the frozen scaled-native primitive
            # only to express the already-computed normalized budget in whole
            # tickets.  Preserve the original capital-mode accounting in the
            # ledger: a FIXED/COMPOUNDING/NATIVE request did not become a new
            # Stage-4 mode merely because normalization scaled it down.
            funding["mode_notional_yuan"] = raw_notional
            funding["issue_budget_yuan"] = capped_budget
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
            "year": calendar_row["year"],
            "fold": calendar_row["fold"],
            "first_kickoff_ts": calendar_row["first_kickoff_ts"],
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
            "weights": weights,
            "weight_status": weight_status,
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


def fixed_m_comparator(candidate_id: str) -> int:
    """Return the exact Gate-A fallback M for one economic family."""
    contract = json.loads((GATE_A / "m_selection_contract.json").read_text(encoding="utf-8"))
    matches = [row for row in contract["fixed_m_comparator"] if row["candidate_id"] == candidate_id]
    if len(matches) != 1:
        raise RuntimeError(f"missing fixed-M contract row: {candidate_id}")
    return int(matches[0]["M"])


def choose_prior_m(
    candidate_id: str,
    history_by_m_seed: dict[int, dict[str, Sequence[tuple[float, float]]]],
) -> dict[str, object]:
    """Apply the frozen expanding-window M rule to strictly prior observations.

    ``history_by_m_seed`` stores `(pre_tax_net, actual_stake)` in chronological
    order through *the previous issue only*.  Seed arithmetic is used here
    solely to score an M during training; it is never a capital-path payout
    average or deployable action.
    """
    minimum = 52
    scores: dict[int, float] = {}
    active_counts: dict[int, int] = {}
    for m_value, seed_rows in history_by_m_seed.items():
        seed_scores: list[float] = []
        active_counts[m_value] = 0
        for records in seed_rows.values():
            stake = sum(value[1] for value in records)
            net = sum(value[0] for value in records)
            active = sum(value[1] > 0 for value in records)
            active_counts[m_value] += active
            if stake > 0:
                seed_scores.append(net / stake)
        if seed_scores:
            scores[m_value] = sum(seed_scores) / len(seed_scores)
    # A family support is not eligible merely because another M or another
    # seed has history.  The required 52 active observations must exist for
    # every deployable replica of the candidate M being considered.
    eligible = [
        m_value for m_value, seed_rows in history_by_m_seed.items()
        if len(seed_rows) > 0
        and all(sum(stake > 0 for _, stake in rows) >= minimum for rows in seed_rows.values())
        and m_value in scores
    ]
    if not eligible:
        return {
            "selected_M": fixed_m_comparator(candidate_id),
            "fallback_reason": "INSUFFICIENT_PRIOR_52_ACTIVE",
            "prior_active_issue_count": max(active_counts.values(), default=0),
            "training_scores": scores,
        }
    selected = min(eligible, key=lambda m_value: (-scores[m_value], m_value, candidate_id))
    return {
        "selected_M": selected,
        "fallback_reason": "",
        "prior_active_issue_count": min(active_counts[m_value] for m_value in eligible),
        "training_scores": scores,
    }


def sleeve_funding_rows(
    path_rows: Sequence[dict[str, object]],
    bridge: dict[tuple[str, str], IssueSleeve],
) -> list[dict[str, object]]:
    """Expand a portfolio path into the schema-bound per-sleeve funding ledger."""
    records: list[dict[str, object]] = []
    for row in path_rows:
        issue = str(row["issue_instance"])
        funded_total = 0.0
        for sleeve_id, settlement in sorted(row["sleeve_settlements"].items()):
            sleeve = bridge[(sleeve_id, issue)]
            actual_count = int(settlement["actual_ticket_count"])
            if sleeve.atomic and actual_count not in (0, sleeve.requested_ticket_count):
                raise RuntimeError(f"atomic funding invariant broken: {sleeve_id}/{issue}")
            funded_total += float(settlement["actual_stake_yuan"])
            if isinstance(sleeve, NativeIssueSleeve) and actual_count:
                ticket_list = canonical_hash([lot.tax_lot_id for lot in sleeve.lots[:actual_count]])
            else:
                ticket_list = str(settlement["funded_tax_lot_sha256"])
            records.append({
                **{field: row[field] for field in PATH_IDENTITY},
                "calendar_index": row["calendar_index"],
                "issue_instance": issue,
                "sleeve_or_family_id": sleeve_id,
                "requested_native_ticket_count": sleeve.requested_ticket_count,
                "actual_ticket_count": actual_count,
                "funded_prefix_length": actual_count,
                "funded_global_rank_start": 1 if actual_count else "",
                "funded_global_rank_end": actual_count if actual_count else "",
                "funded_ticket_list_sha256": ticket_list,
                "funded_tax_lot_sha256": settlement["funded_tax_lot_sha256"],
                "prefix_execution_status": "WHOLE_NATIVE_OR_NO_BET" if sleeve.atomic else "GLOBAL_PREFIX",
                "atomic_or_no_bet_reason": "" if actual_count or not sleeve.atomic else "ATOMIC_OR_CASH_NO_BET",
                "actual_stake_yuan": settlement["actual_stake_yuan"],
                "pre_tax_gross_yuan": settlement["gross_yuan"],
                "pre_tax_net_yuan": settlement["pre_tax_net_yuan"],
                "tax_yuan": settlement["tax_yuan"],
            })
        if not math.isclose(funded_total, float(row["actual_stake_yuan"]), abs_tol=1e-9):
            raise RuntimeError(f"portfolio/sleeve funding reconciliation failed: {issue}")
    return records


def capital_summary(path_rows: Sequence[dict[str, object]], holding: dict[str, object]) -> dict[str, object]:
    """Return controlling capital and secondary stake-ROI totals for one path."""
    if not path_rows:
        raise ValueError("cannot summarize empty capital path")
    stake = sum(float(row["actual_stake_yuan"]) for row in path_rows)
    net = sum(float(row["pre_tax_net_yuan"]) for row in path_rows)
    tax = sum(float(row["tax_yuan"]) for row in path_rows)
    ending = float(path_rows[-1]["postissue_bankroll_yuan"])
    growth = ending / INITIAL_BANKROLL_YUAN - 1.0
    turnover = stake / INITIAL_BANKROLL_YUAN
    mode = str(path_rows[0]["mode"])
    return {
        **{field: path_rows[0][field] for field in PATH_IDENTITY},
        "starting_bankroll_yuan": INITIAL_BANKROLL_YUAN,
        "ending_bankroll_yuan": ending,
        "minimum_bankroll_yuan": holding["minimum_bankroll_yuan"],
        "minimum_required_start_yuan": "" if mode == "COMPOUNDING_BANKROLL" else "PENDING_BISECTION",
        "fundable_issue_count": sum(float(row["actual_stake_yuan"]) > 0 for row in path_rows),
        "first_unfundable_issue": next((row["issue_instance"] for row in path_rows if float(row["requested_stake_yuan"]) > 0 and float(row["actual_stake_yuan"]) == 0), ""),
        "scaled_stake_yuan": sum(float(row["scaled_stake_yuan"]) for row in path_rows),
        "skipped_stake_yuan": sum(float(row["skipped_stake_yuan"]) for row in path_rows),
        "cash_yuan": float(path_rows[-1]["retained_cash_yuan"]),
        "turnover_yuan": stake,
        "pre_tax_roi": net / stake if stake else None,
        "tax_adjusted_roi": (net - tax) / stake if stake else None,
        "cumulative_pre_tax_roi": net / stake if stake else None,
        "capital_growth": growth,
        "capital_turnover": turnover,
        "capital_growth_audit_delta": growth - (net / stake * turnover) if mode == "FIXED_100K_NOTIONAL" and stake else None,
        "ruin_flag": holding["ruin_flag"],
    }


def risk_decomposition_rows(
    path_rows: Sequence[dict[str, object]],
    bridge: dict[tuple[str, str], IssueSleeve],
) -> list[dict[str, object]]:
    """Emit funded-flow risk diagnostics without assigning invented P&L.

    The frozen normalization engine may supply an ex-ante covariance estimate,
    but it does not make covariance an outcome cashflow.  Accordingly this
    table exposes exactly funded per-sleeve money and leaves Euler quantities
    blank when the per-issue covariance matrix was intentionally not retained
    in the Gate-B state row.
    """
    rows: list[dict[str, object]] = []
    for path_row in path_rows:
        settlements = path_row["sleeve_settlements"]
        portfolio_net = float(path_row["pre_tax_net_yuan"])
        sleeve_net = sum(float(value["pre_tax_net_yuan"]) for value in settlements.values())
        if not math.isclose(portfolio_net, sleeve_net, abs_tol=1e-9):
            raise RuntimeError(f"funded sleeve P&L mismatch: {path_row['issue_instance']}")
        requested = sum(
            bridge[(sleeve_id, str(path_row["issue_instance"]))].requested_ticket_count * TICKET_STAKE_YUAN
            for sleeve_id in settlements
        )
        actual = float(path_row["actual_stake_yuan"])
        for sleeve_id, settlement in sorted(settlements.items()):
            family = canonical_economic_catalog()[sleeve_id]["economic_family_id"]
            native_stake = bridge[(sleeve_id, str(path_row["issue_instance"]))].requested_ticket_count * TICKET_STAKE_YUAN
            funded = float(settlement["actual_stake_yuan"])
            rows.append({
                **{field: path_row[field] for field in PATH_IDENTITY},
                "calendar_index": path_row["calendar_index"],
                "issue_instance": path_row["issue_instance"],
                "economic_family_id": family,
                "marginal_variance_contribution": "",
                "euler_variance_contribution": "",
                "matched_drawdown_delta_yuan": "",
                "matched_tail_loss_delta_yuan": "",
                "capital_utilization_yuan": funded,
                "retained_cash_yuan": float(path_row["retained_cash_yuan"]),
                "rounding_delta_yuan": funded - float(path_row["weights"][sleeve_id]) * actual,
                "exposure_size_delta_yuan": funded - native_stake,
                "portfolio_pnl_reconciliation_yuan": portfolio_net - sleeve_net,
                "requested_native_stake_yuan": native_stake,
                "portfolio_requested_native_stake_yuan": requested,
                "undefined_reason": "COVARIANCE_MATRIX_NOT_RETAINED_IN_PATH_STATE",
            })
    return rows


def path_output_tables(
    path_rows: Sequence[dict[str, object]],
    bridge: dict[tuple[str, str], IssueSleeve],
) -> dict[str, list[dict[str, object]]]:
    """Create the core, uniquely keyed Gate-B tables for one capital path."""
    holding_result = summarize_holding_path(path_rows)
    enriched = holding_result["issue_rows"]
    holding = holding_result["summary"]
    issue_ledger: list[dict[str, object]] = []
    weight_history: list[dict[str, object]] = []
    stage_attribution: list[dict[str, object]] = []
    for row in enriched:
        path_identity = {field: row[field] for field in PATH_IDENTITY}
        issue_ledger.append({
            **path_identity,
            **{field: row[field] for field in (
                "calendar_index", "issue_instance", "year", "fold", "first_kickoff_ts",
                "preissue_bankroll_yuan", "normalization_method", "normalization_status",
                "normalization_executable", "covariance_sleeve_order_json", "covariance_input_sha256",
                "ex_ante_volatility", "target_volatility", "realized_capital_multiplier",
                "risk_budget_yuan", "pre_normalization_mode_notional_yuan",
                "normalized_mode_notional_yuan", "mode_notional_yuan", "issue_budget_yuan",
                "requested_stake_yuan", "actual_stake_yuan", "scaled_stake_yuan",
                "skipped_stake_yuan", "retained_cash_yuan", "reason_codes", "pre_tax_gross_yuan",
                "pre_tax_net_yuan", "tax_yuan", "postissue_bankroll_yuan", "ruin_flag",
                "running_peak_yuan", "drawdown_yuan", "drawdown_fraction",
            )},
        })
        for sleeve_id, weight in sorted(row["weights"].items()):
            sleeve = bridge[(sleeve_id, str(row["issue_instance"]))]
            settlement = row["sleeve_settlements"][sleeve_id]
            trace = canonical_hash({
                "sleeve": sleeve_id,
                "issue": row["issue_instance"],
                "native_ticket_count": sleeve.requested_ticket_count,
                "atomic": sleeve.atomic,
            })
            weight_history.append({
                **path_identity,
                "calendar_index": row["calendar_index"],
                "issue_instance": row["issue_instance"],
                "sleeve_id": sleeve_id,
                "weight": weight,
                "history_active_observation_count": "" if "INSUFFICIENT_52" in str(row["weight_status"]) else 52,
                "estimator_status": row["weight_status"],
                "fallback_reason": row["weight_status"] if str(row["weight_status"]).startswith("FALLBACK_") else "",
                "covariance_hash": row["covariance_input_sha256"],
            })
            for stage_id in ("STAGE_1_SELECTION", "STAGE_2_DIRECTION", "STAGE_3_TICKET_CONSTRUCTION", "STAGE_4_POSITIONING"):
                stage_attribution.append({
                    **path_identity,
                    "calendar_index": row["calendar_index"],
                    "issue_instance": row["issue_instance"],
                    "sleeve_id": sleeve_id,
                    "stage_id": stage_id,
                    "attribution_status": "EXACT_SAME_TICKET_FUNDING" if stage_id == "STAGE_4_POSITIONING" else "NOT_IDENTIFIABLE_WITHOUT_SPLICE",
                    "upstream_trace_sha256": trace,
                    "native_requested_ticket_count": sleeve.requested_ticket_count,
                    "normalization_multiplier": row["realized_capital_multiplier"],
                    "portfolio_weight": weight,
                    "actual_ticket_count": settlement["actual_ticket_count"],
                    "retained_cash_yuan": row["retained_cash_yuan"],
                    "same_ticket_stage4_funding_delta_yuan": float(settlement["actual_stake_yuan"]) - sleeve.requested_ticket_count * TICKET_STAKE_YUAN,
                    "undefined_reason": "UPSTREAM_STAGE_SPLICE_FORBIDDEN" if stage_id != "STAGE_4_POSITIONING" else "",
                })
    rolling = []
    for row in holding_result["rolling_rows"]:
        rolling.append({
            **{field: path_rows[0][field] for field in PATH_IDENTITY},
            **row,
        })
    return {
        "issue_ledger": issue_ledger,
        "sleeve_funding_ledger": sleeve_funding_rows(path_rows, bridge),
        "capital_summary": [capital_summary(path_rows, holding)],
        "holding_metrics": [{
            **{field: path_rows[0][field] for field in PATH_IDENTITY},
            **holding,
        }],
        "rolling_window_metrics": rolling,
        "risk_decomposition": risk_decomposition_rows(path_rows, bridge),
        "weight_history": weight_history,
        "stage_attribution": stage_attribution,
    }
