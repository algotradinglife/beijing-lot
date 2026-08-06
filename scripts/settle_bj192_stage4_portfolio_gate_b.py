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
import datetime
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
import shutil
import sqlite3
import statistics
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


CONTRACT = "BJ-HIST-N7-STRATEGY-ENSEMBLE-001"
VERSION = "bj192-gate-b-v4"
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
    max_package_bytes: int | None = None,
    artifact_writer: Callable[[Path, dict[str, Sequence[dict[str, object]]]], dict[str, dict[str, object]]] | None = None,
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
            # The minimal Stage-4 contract retains every issue-level audit row.
            # Keep the science bytes intact while compressing the wide ledgers so
            # the canonical package remains within its committed size ceiling.
            compressed = table in {
                "issue_ledger", "sleeve_funding_ledger", "weight_history",
                "selected_m_path", "standalone_m_curve", "stage_attribution",
                "rolling_window_metrics", "risk_decomposition", "dependence_panel",
                "realized_funded_flow_dependence", "intrinsic_native_dependence",
            }
            filename = f"{table}.csv.gz" if compressed else f"{table}.csv"
            spec = schema[table]
            fields = write_csv_rows(
                stage / filename,
                list(rows),
                compressed=compressed,
                declared_fields=[*spec["key"], *spec["fields"]],
            )
            table_manifest[table] = {"filename": filename, "row_count": len(rows), "fields": fields}
        if artifact_writer is not None:
            ancillary = artifact_writer(stage, tables)
            if set(ancillary) & set(table_manifest):
                raise RuntimeError("ancillary artifact name collides with Gate-A table")
            table_manifest.update(ancillary)
        (stage / "source_binding.json").write_text(json.dumps(source_binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (stage / "table_manifest.json").write_text(json.dumps(table_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (stage / "README.md").write_text(package_note.rstrip() + "\n", encoding="utf-8")
        staged_files = sorted(path for path in stage.rglob("*") if path.is_file())
        staged_bytes = sum(path.stat().st_size for path in staged_files)
        if max_package_bytes is not None and staged_bytes > max_package_bytes:
            raise RuntimeError(
                f"package size ceiling exceeded: {staged_bytes} > {max_package_bytes} bytes"
            )
        archive_transport = {str(path.relative_to(stage)): sha256_file(path) for path in staged_files}
        scientific = {str(path.relative_to(stage)): canonical_scientific_sha256(path) for path in staged_files}
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
        manifest_files = sorted(path for path in stage.rglob("*") if path.is_file())
        manifest = {str(path.relative_to(stage)): sha256_file(path) for path in manifest_files}
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
    actual = sorted(
        str(path.relative_to(directory))
        for path in directory.rglob("*")
        if path.is_file()
        and path.name != "SHA256SUMS.json"
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    )
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
    issue_paths: list[dict[str, object]] = []
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
                # The checkpoint is the only permitted hand-off between exact
                # ticket settlement and package finalization.  Retain the
                # complete per-issue state (including funded tax-lot results
                # and weights) so the finalizer never replays a ticket just to
                # reconstruct a report table.
                issue_paths.extend({
                    "record_type": "MINIMAL_STAGE4_ISSUE_PATH",
                    "membership_id": membership_id,
                    "membership_json": json.dumps(membership, separators=(",", ":")),
                    "membership_size": len(membership),
                    **row,
                } for row in path)
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
    return write_surface_checkpoint(
        checkpoint, binding=binding,
        completed_path_keys=[*issue_paths, *summaries, *stability],
    )


def load_minimal_stage4_checkpoint(
    checkpoint: Path,
) -> tuple[dict[str, object], dict[tuple[object, ...], list[dict[str, object]]]]:
    """Load the finalizable #192 closure checkpoint without ticket replay.

    Only the H1 deterministic sleeves are legal in the minimal closure, so a
    finalizer can use the saved issue state together with immutable prefix
    metadata.  It must never invoke a settlement runner or reconstruct an
    outcome from a scalar return.
    """
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    expected = dict(payload)
    digest = expected.pop("payload_sha256", None)
    if digest != canonical_hash(expected):
        raise RuntimeError("minimal Stage-4 checkpoint payload digest drift")
    binding = dict(payload.get("binding", {}))
    required = {
        "phase": "FINAL_GATE_B_MINIMAL_STAGE4_CLOSURE",
        "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
        "gate_a_content_sha256": EXPECTED_GATE_A_CONTENT,
        "membership_contract_sha256": canonical_hash(minimal_stage4_memberships()),
        "axis_contract_sha256": canonical_hash(minimal_stage4_execution_axes()),
    }
    if any(binding.get(key) != value for key, value in required.items()):
        raise RuntimeError("minimal Stage-4 checkpoint binding drift")
    groups: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for record in payload["completed_path_keys"]:
        if record.get("record_type") != "MINIMAL_STAGE4_ISSUE_PATH":
            continue
        identity = tuple(record[field] for field in PATH_IDENTITY)
        groups[identity].append({key: value for key, value in record.items() if key not in {
            "record_type", "membership_id", "membership_json", "membership_size",
        }})
    expected_path_count = int(binding["membership_count"]) * int(binding["axis_count"]) * int(binding["bundle_count"])
    calendar_count = len(read_csv(GATE_A / "full_calendar.csv"))
    if len(groups) != expected_path_count:
        raise RuntimeError("minimal Stage-4 checkpoint path denominator drift")
    for identity, rows in groups.items():
        ordered = sorted(rows, key=lambda row: (int(row["calendar_index"]), str(row["issue_instance"])))
        if len(ordered) != calendar_count or len({row["issue_instance"] for row in ordered}) != calendar_count:
            raise RuntimeError(f"minimal Stage-4 issue-calendar drift: {identity}")
        groups[identity] = ordered
    # The final amendment declares the three H1 sleeves deterministic.  Gate A
    # retains ordinal bundle maps for the broader catalogue, but those maps
    # must not multiply identical deterministic economics into selectable
    # observations.  Prove equality from saved settlement state, then retain
    # BUNDLE_ORDINAL_001 as the one executable representation.
    return binding, collapse_minimal_stage4_deterministic_paths(groups)


def collapse_minimal_stage4_deterministic_paths(
    groups: dict[tuple[object, ...], list[dict[str, object]]],
) -> dict[tuple[object, ...], list[dict[str, object]]]:
    """Collapse only byte-identical deterministic replicate bundles.

    This deliberately operates on already-settled checkpoint rows.  It makes
    the bundle-equivalence rule independently unit-testable without relying
    on an author-local production checkpoint, and never reruns tickets.
    """
    logical: dict[tuple[object, ...], list[tuple[tuple[object, ...], list[dict[str, object]]]]] = defaultdict(list)
    for identity, rows in groups.items():
        # portfolio_id incorporates Gate-A's bundle identity; it is not a
        # logical path coordinate for the deterministic closure.
        logical[(tuple(sorted(rows[0]["sleeve_settlements"])), *identity[1:-1])].append((identity, rows))
    collapsed: dict[tuple[object, ...], list[dict[str, object]]] = {}
    for logical_identity, variants in logical.items():
        if len(variants) == 1:
            identity, rows = variants[0]
            collapsed[identity] = rows
            continue
        if {identity[-1] for identity, _ in variants} != set(frozen_replicate_bundles()):
            raise RuntimeError("minimal Stage-4 replicate-bundle denominator drift")
        signatures = {
            canonical_hash([{key: value for key, value in row.items() if key not in {"portfolio_id", "deployment_replicate_bundle_id"}} for row in rows])
            for _, rows in variants
        }
        if len(signatures) != 1:
            raise RuntimeError("deterministic minimal Stage-4 bundle economics drift")
        identity, rows = next((pair for pair in variants if pair[0][-1] == "BUNDLE_ORDINAL_001"))
        collapsed[identity] = rows
    return collapsed


def minimal_stage4_path_bridge(path_rows: Sequence[dict[str, object]]) -> dict[tuple[str, str], IssueSleeve]:
    """Bind saved minimal path state to immutable H1 prefix metadata only."""
    if not path_rows:
        raise ValueError("empty minimal Stage-4 path")
    sleeves = tuple(sorted(path_rows[0]["sleeve_settlements"]))
    if sleeves not in minimal_stage4_memberships():
        raise RuntimeError("checkpoint path contains an unauthorized minimal sleeve set")
    source = h1_ticket_bridge()
    result = {
        (sleeve, str(row["issue_instance"])): source[(sleeve, str(row["issue_instance"]))]
        for sleeve in sleeves
        for row in path_rows
    }
    if len(result) != len(sleeves) * len(path_rows):
        raise RuntimeError("minimal Stage-4 bridge denominator drift")
    return result


def minimal_stage4_core_tables(
    checkpoint: Path,
) -> tuple[dict[str, list[dict[str, object]]], dict[tuple[object, ...], dict[str, str]]]:
    """Materialize core outcome tables from checkpoint rows, never tickets.

    The returned hashes are used by the comparison/final-decision layer.  A
    support hash always spans the complete issue calendar; an actual-funding
    hash binds the issue-by-issue funded tax-lot identities and stakes.
    """
    _, paths = load_minimal_stage4_checkpoint(checkpoint)
    table_names = (
        "issue_ledger", "sleeve_funding_ledger", "capital_summary", "holding_metrics",
        "rolling_window_metrics", "risk_decomposition", "weight_history", "stage_attribution",
    )
    tables = {name: [] for name in table_names}
    identities: dict[tuple[object, ...], dict[str, str]] = {}
    full_control_by_axis = {
        identity[1:]: path
        for identity, path in paths.items()
        if tuple(sorted(path[0]["sleeve_settlements"])) == ("BEST_FULL_FULL",)
    }
    for identity, path in sorted(paths.items(), key=lambda item: canonical_hash(item[0])):
        bridge = minimal_stage4_path_bridge(path)
        matched_control = full_control_by_axis.get(identity[1:])
        if matched_control is None:
            raise RuntimeError("minimal Stage-4 matched FULL path unavailable")
        output = path_output_tables(path, bridge, matched_control_rows=matched_control)
        stake = sum(float(row["actual_stake_yuan"]) for row in path)
        net = sum(float(row["pre_tax_net_yuan"]) for row in path)
        gross = [float(row["pre_tax_gross_yuan"]) for row in path]
        gross_total = sum(gross)
        largest_index = max(range(len(path)), key=lambda index: float(path[index]["pre_tax_net_yuan"]))
        year_net: dict[str, float] = defaultdict(float)
        year_stake: dict[str, float] = defaultdict(float)
        for row in path:
            year_net[str(row["year"])] += float(row["pre_tax_net_yuan"])
            year_stake[str(row["year"])] += float(row["actual_stake_yuan"])
        largest_year = max(year_net, key=year_net.get)
        ex_issue_stake = stake - float(path[largest_index]["actual_stake_yuan"])
        ex_year_stake = stake - year_stake[largest_year]
        output["holding_metrics"][0].update({
            "gross_issue_hhi": sum((value / gross_total) ** 2 for value in gross) if gross_total else None,
            "gross_top_issue_share": max(gross) / gross_total if gross_total else None,
            "largest_signed_issue": path[largest_index]["issue_instance"],
            "largest_signed_year": largest_year,
            "ex_largest_issue_pre_tax_roi": (net - float(path[largest_index]["pre_tax_net_yuan"])) / ex_issue_stake if ex_issue_stake else None,
            "ex_largest_year_pre_tax_roi": (net - year_net[largest_year]) / ex_year_stake if ex_year_stake else None,
        })
        for name in table_names:
            tables[name].extend(output[name])
        identities[identity] = {
            "support_hash": canonical_hash([row["issue_instance"] for row in path]),
            "actual_funding_hash": canonical_hash([
                {
                    "issue_instance": row["issue_instance"],
                    "actual_stake_yuan": row["actual_stake_yuan"],
                    "sleeve_settlements": {
                        sleeve: {
                            "actual_ticket_count": item["actual_ticket_count"],
                            "actual_stake_yuan": item["actual_stake_yuan"],
                            "funded_tax_lot_sha256": item["funded_tax_lot_sha256"],
                        }
                        for sleeve, item in sorted(row["sleeve_settlements"].items())
                    },
                }
                for row in path
            ]),
        }
    if len(tables["capital_summary"]) != len(paths):
        raise RuntimeError("minimal Stage-4 core table path denominator drift")
    return tables, identities


def minimal_stage4_comparison_tables(
    checkpoint: Path,
    *,
    core_tables: dict[str, list[dict[str, object]]] | None = None,
    identities: dict[tuple[object, ...], dict[str, str]] | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Build matched FULL lifts and the bounded pair/K/pareto decision views.

    This is deliberately a reporting transformation over saved outcome paths.
    It does not choose an action from seed noise and it does not create a
    cash-only comparison: every lift is matched by mode, fraction, weighting,
    normalization, bundle, starting bankroll and complete calendar.
    """
    # Package finalization already materializes the large core ledgers.  Reuse
    # them there rather than retaining a second full checkpoint expansion.
    if core_tables is None or identities is None:
        core, identities = minimal_stage4_core_tables(checkpoint)
    else:
        core = core_tables
    capital_by_identity = {
        tuple(row[field] for field in PATH_IDENTITY): row for row in core["capital_summary"]
    }
    holdings_by_identity = {
        tuple(row[field] for field in PATH_IDENTITY): row for row in core["holding_metrics"]
    }
    outputs = {name: [] for name in (
        "baseline_lift", "all_pairs_risk_return_surface", "portfolio_k_saturation",
        "higher_order_pareto_frontier",
    )}
    funding_by_identity: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in core["sleeve_funding_ledger"]:
        funding_by_identity[tuple(row[field] for field in PATH_IDENTITY)].append(row)
    full_by_axis = {
        identity[1:]: capital_by_identity[identity]
        for identity, rows in funding_by_identity.items()
        if tuple(sorted({row["sleeve_or_family_id"] for row in rows})) == ("BEST_FULL_FULL",)
    }
    membership_by_identity = {
        identity: tuple(sorted({row["sleeve_or_family_id"] for row in rows}))
        for identity, rows in funding_by_identity.items()
    }
    for identity, capital in sorted(capital_by_identity.items(), key=lambda item: canonical_hash(item[0])):
        portfolio_id, mode, fraction, weight, normalization, bundle = identity
        membership = tuple(sorted({row["sleeve_or_family_id"] for row in funding_by_identity[identity]}))
        support = identities[identity]["support_hash"]
        funding = identities[identity]["actual_funding_hash"]
        control = full_by_axis.get(identity[1:])
        if control is None:
            raise RuntimeError("minimal Stage-4 matched FULL control unavailable")
        control_identity = (
            control["portfolio_id"], control["mode"], control["position_fraction"],
            control["weight_method"], control["normalization_method"],
            control["deployment_replicate_bundle_id"],
        )
        if support != identities[control_identity]["support_hash"]:
            raise RuntimeError("minimal Stage-4 matched support drift")
        outputs["baseline_lift"].append({
            **{field: capital[field] for field in PATH_IDENTITY},
            "candidate_id": portfolio_id, "control_id": control["portfolio_id"],
            "support_hash": support, "actual_funding_hash": funding,
            "absolute_ending_bankroll_yuan": capital["ending_bankroll_yuan"],
            "absolute_pre_tax_roi": capital["pre_tax_roi"],
            "candidate_minus_control_bankroll_yuan": float(capital["ending_bankroll_yuan"]) - float(control["ending_bankroll_yuan"]),
            "candidate_minus_control_pre_tax_roi": (
                float(capital["pre_tax_roi"]) - float(control["pre_tax_roi"])
                if capital["pre_tax_roi"] is not None and control["pre_tax_roi"] is not None else None
            ),
            "ladder_decision": "NOT_ADVANCED_PENDING_STRICT_EV_IF_MATERIALLY_POSITIVE",
        })
        shares = defaultdict(float)
        total_stake = 0.0
        for row in funding_by_identity[identity]:
            shares[str(row["sleeve_or_family_id"])] += float(row["actual_stake_yuan"])
            total_stake += float(row["actual_stake_yuan"])
        hhi = sum((value / total_stake) ** 2 for value in shares.values()) if total_stake else None
        family_set = canonical_hash([
            canonical_economic_catalog()[sleeve]["economic_family_id"] for sleeve in membership
        ])
        if len(membership) == 2:
            outputs["all_pairs_risk_return_surface"].append({
                **{field: capital[field] for field in PATH_IDENTITY},
                "economic_family_set_sha256": family_set, "pair_id": "|".join(membership),
                "pre_tax_roi": capital["pre_tax_roi"], "sharpe": holdings_by_identity[identity]["sharpe"],
                "sortino": holdings_by_identity[identity]["sortino"], "calmar": holdings_by_identity[identity]["calmar"],
                "max_drawdown_yuan": holdings_by_identity[identity]["max_drawdown_yuan"],
                "capital_growth": capital["capital_growth"], "capital_turnover": capital["capital_turnover"],
                "tax_adjusted_roi": capital["tax_adjusted_roi"], "support_hash": support,
                "undefined_reason": "" if capital["pre_tax_roi"] is not None else "ZERO_STAKE",
            })
        outputs["portfolio_k_saturation"].append({
            **{field: capital[field] for field in PATH_IDENTITY},
            "ordered_shortlist_id": "MINIMAL_H1_DETERMINISTIC", "K": len(membership),
            "economic_family_set_sha256": family_set,
            "candidate_aliases_sha256": canonical_hash(membership),
            "ending_bankroll_yuan": capital["ending_bankroll_yuan"], "pre_tax_roi": capital["pre_tax_roi"],
            "max_drawdown_yuan": holdings_by_identity[identity]["max_drawdown_yuan"],
            "contribution_hhi": hhi, "retained_cash_yuan": capital["cash_yuan"],
            "marginal_vs_K_minus_1_yuan": "", "undefined_reason": "",
        })
        outputs["higher_order_pareto_frontier"].append({
            **{field: capital[field] for field in PATH_IDENTITY},
            "economic_family_set_sha256": family_set, "frontier_id": "MINIMAL_STAGE4_RAW",
            "pre_tax_roi": capital["pre_tax_roi"], "capital_growth": capital["capital_growth"],
            "max_drawdown_yuan": holdings_by_identity[identity]["max_drawdown_yuan"],
            "contribution_hhi": hhi, "tax_adjusted_roi": capital["tax_adjusted_roi"],
            "dominance_status": "UNSCREENED_MINIMAL_CLOSURE", "support_hash": support,
        })
    # The minimal contract requires each combination to be read against its
    # strongest component and its equal-weight counterpart as well as FULL.
    # These are descriptive matched controls, never a selection rule.
    for identity, capital in sorted(capital_by_identity.items(), key=lambda item: canonical_hash(item[0])):
        membership = membership_by_identity[identity]
        if len(membership) < 2:
            continue
        candidates = []
        for sleeve in membership:
            # ``portfolio_id`` hashes the complete membership, so it can
            # never equal a sleeve name.  Join the single-sleeve component by
            # its actual frozen membership on the same execution axis.
            candidate = next(
                (
                    other
                    for other, other_membership in membership_by_identity.items()
                    if other_membership == (sleeve,) and other[1:] == identity[1:]
                ),
                None,
            )
            if candidate is not None:
                candidates.append(candidate)
        controls = []
        if candidates:
            strongest = max(candidates, key=lambda item: float(capital_by_identity[item]["ending_bankroll_yuan"]))
            controls.append((f"STRONGEST_COMPONENT:{strongest[0]}", strongest))
        if identity[3] != "EQUAL_WEIGHT":
            equal_identity = (identity[0], identity[1], identity[2], "EQUAL_WEIGHT", identity[4], identity[5])
            if equal_identity in capital_by_identity:
                controls.append(("EQUAL_WEIGHT_SAME_MEMBERSHIP", equal_identity))
        for control_id, control_identity in controls:
            control = capital_by_identity[control_identity]
            outputs["baseline_lift"].append({
                **{field: capital[field] for field in PATH_IDENTITY},
                "candidate_id": identity[0], "control_id": control_id,
                "support_hash": identities[identity]["support_hash"],
                "actual_funding_hash": identities[identity]["actual_funding_hash"],
                "absolute_ending_bankroll_yuan": capital["ending_bankroll_yuan"],
                "absolute_pre_tax_roi": capital["pre_tax_roi"],
                "candidate_minus_control_bankroll_yuan": float(capital["ending_bankroll_yuan"]) - float(control["ending_bankroll_yuan"]),
                "candidate_minus_control_pre_tax_roi": float(capital["pre_tax_roi"]) - float(control["pre_tax_roi"]),
                "ladder_decision": "DESCRIPTIVE_MATCHED_COMPONENT_OR_EQUAL_WEIGHT_CONTROL",
            })
    return outputs


def path_support_and_funding_identities(path: Sequence[dict[str, object]]) -> dict[str, str]:
    """Return distinct immutable support and actual-funding identities.

    A common issue calendar does not make two realised capital paths funding
    comparable.  The funding hash binds every issue's executed stake and the
    exact sleeve/tax-lot funding identities; it therefore distinguishes cash,
    turnover, caps, and atomic NO_BET behaviour from ticket economics.
    """
    ordered = sorted(path, key=lambda row: int(row["calendar_index"]))
    return {
        "support_hash": canonical_hash([
            {"calendar_index": row["calendar_index"], "issue_instance": row["issue_instance"]}
            for row in ordered
        ]),
        "actual_funding_hash": canonical_hash([
            {
                "calendar_index": row["calendar_index"],
                "issue_instance": row["issue_instance"],
                "actual_stake_yuan": row["actual_stake_yuan"],
                "sleeves": {
                    sleeve: {
                        "actual_ticket_count": value["actual_ticket_count"],
                        "actual_stake_yuan": value["actual_stake_yuan"],
                        "funded_tax_lot_sha256": value["funded_tax_lot_sha256"],
                    }
                    for sleeve, value in sorted(row["sleeve_settlements"].items())
                },
            }
            for row in ordered
        ]),
    }


def comparison_row(
    *,
    candidate_identity: tuple[object, ...],
    control_identity: tuple[object, ...],
    control_id: str,
    capital_by_identity: dict[tuple[object, ...], dict[str, object]],
    identities: dict[tuple[object, ...], dict[str, str]],
) -> dict[str, object]:
    """Make a funding-aware comparison without manufacturing a matched lift."""
    candidate = capital_by_identity[candidate_identity]
    control = capital_by_identity[control_identity]
    candidate_ids = identities[candidate_identity]
    control_ids = identities[control_identity]
    support_equal = candidate_ids["support_hash"] == control_ids["support_hash"]
    if not support_equal:
        raise RuntimeError("minimal Stage-4 comparison support mismatch")
    funding_equal = candidate_ids["actual_funding_hash"] == control_ids["actual_funding_hash"]
    raw_yuan = float(candidate["ending_bankroll_yuan"]) - float(control["ending_bankroll_yuan"])
    candidate_roi = candidate["pre_tax_roi"]
    control_roi = control["pre_tax_roi"]
    raw_roi = (
        float(candidate_roi) - float(control_roi)
        if candidate_roi not in (None, "") and control_roi not in (None, "")
        else ""
    )
    semantics = "MATCHED_ACTUAL_FUNDING" if funding_equal else "UNMATCHED_RAW_PATH_DIFFERENCE"
    return {
        **{field: candidate[field] for field in PATH_IDENTITY},
        "candidate_id": candidate_identity[0],
        "control_id": control_id,
        "support_hash": candidate_ids["support_hash"],
        "actual_funding_hash": candidate_ids["actual_funding_hash"],
        "candidate_support_hash": candidate_ids["support_hash"],
        "control_support_hash": control_ids["support_hash"],
        "support_equal": support_equal,
        "candidate_actual_funding_hash": candidate_ids["actual_funding_hash"],
        "control_actual_funding_hash": control_ids["actual_funding_hash"],
        "actual_funding_equal": funding_equal,
        "comparison_semantics": semantics,
        "absolute_ending_bankroll_yuan": candidate["ending_bankroll_yuan"],
        "absolute_pre_tax_roi": candidate_roi,
        "matched_lift_yuan": raw_yuan if funding_equal else "",
        "matched_lift_pre_tax_roi": raw_roi if funding_equal else "",
        "candidate_minus_control_bankroll_yuan": raw_yuan if funding_equal else "",
        "candidate_minus_control_pre_tax_roi": raw_roi if funding_equal else "",
        "unmatched_raw_path_difference_yuan": raw_yuan if not funding_equal else "",
        "unmatched_raw_path_roi_difference": raw_roi if not funding_equal else "",
        "strict_inference_status": (
            "ELIGIBLE_MATCHED_ACTUAL_FUNDING" if funding_equal
            else "NOT_ELIGIBLE_UNMATCHED_ACTUAL_FUNDING"
        ),
        "ladder_decision": (
            "DESCRIPTIVE_MATCHED_CONTROL_NO_PROMOTION" if funding_equal
            else "DESCRIPTIVE_UNMATCHED_RAW_PATH_DIAGNOSTIC_NO_PROMOTION"
        ),
    }


def minimal_stage4_comparisons_from_paths(
    paths: dict[tuple[object, ...], list[dict[str, object]]],
    capital_rows: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    """Rebuild all minimal comparison rows using real membership joins.

    This package-derived reducer never replays tickets.  It preserves the
    frozen 252 realised paths, publishes all control identities separately,
    and leaves any non-identical-funding contrast explicitly unmatched.
    """
    capital_by_identity = {
        tuple(row[field] for field in PATH_IDENTITY): dict(row) for row in capital_rows
    }
    if set(capital_by_identity) != set(paths):
        raise RuntimeError("minimal Stage-4 comparison/capital path set drift")
    memberships = {
        identity: tuple(sorted(path[0]["sleeve_settlements"]))
        for identity, path in paths.items()
    }
    identities = {identity: path_support_and_funding_identities(path) for identity, path in paths.items()}
    full_by_axis = {
        identity[1:]: identity
        for identity, membership in memberships.items()
        if membership == ("BEST_FULL_FULL",)
    }
    rows: list[dict[str, object]] = []
    for identity in sorted(paths, key=canonical_hash):
        full_identity = full_by_axis.get(identity[1:])
        if full_identity is None:
            raise RuntimeError("minimal Stage-4 matched FULL control unavailable")
        rows.append(comparison_row(
            candidate_identity=identity,
            control_identity=full_identity,
            control_id=str(full_identity[0]),
            capital_by_identity=capital_by_identity,
            identities=identities,
        ))
    for identity in sorted(paths, key=canonical_hash):
        membership = memberships[identity]
        if len(membership) < 2:
            continue
        components = [
            other for other, other_membership in memberships.items()
            if len(other_membership) == 1 and other_membership[0] in membership and other[1:] == identity[1:]
        ]
        if len(components) != len(membership):
            raise RuntimeError("minimal Stage-4 strongest-component membership join drift")
        strongest = max(
            components,
            key=lambda other: (float(capital_by_identity[other]["ending_bankroll_yuan"]), str(other[0])),
        )
        rows.append(comparison_row(
            candidate_identity=identity,
            control_identity=strongest,
            control_id=f"STRONGEST_COMPONENT:{strongest[0]}",
            capital_by_identity=capital_by_identity,
            identities=identities,
        ))
        if identity[3] != "EQUAL_WEIGHT":
            equal_identity = (identity[0], identity[1], identity[2], "EQUAL_WEIGHT", identity[4], identity[5])
            if equal_identity not in paths:
                raise RuntimeError("minimal Stage-4 equal-weight control unavailable")
            rows.append(comparison_row(
                candidate_identity=identity,
                control_identity=equal_identity,
                control_id="EQUAL_WEIGHT_SAME_MEMBERSHIP",
                capital_by_identity=capital_by_identity,
                identities=identities,
            ))
    if sum(row["control_id"].startswith("STRONGEST_COMPONENT:") for row in rows) != 144:
        raise RuntimeError("minimal Stage-4 strongest-component row denominator drift")
    return rows


def _common_schedule_ticket_counts(
    sleeves: Sequence[str],
    issue: str,
    count: int,
    weights: dict[str, object],
    bridge: dict[tuple[str, str], NativeIssueSleeve],
) -> dict[str, int]:
    """Allocate one fixed common schedule count to frozen sleeve prefixes."""
    available = {sleeve: bridge[(sleeve, issue)] for sleeve in sleeves}
    if any(value.status != "SETTLED" for value in available.values()):
        if count:
            raise RuntimeError("common schedule requests unavailable ticket prefix")
        return {sleeve: 0 for sleeve in sleeves}
    capacities = {sleeve: value.requested_ticket_count for sleeve, value in available.items()}
    if len(sleeves) == 1:
        sleeve = sleeves[0]
        if available[sleeve].atomic and count not in (0, capacities[sleeve]):
            raise RuntimeError("common schedule attempts partial atomic ticket stream")
        if count > capacities[sleeve]:
            raise RuntimeError("common schedule exceeds frozen ticket capacity")
        return {sleeve: count}
    if any(value.atomic for value in available.values()):
        raise RuntimeError("minimal matched-capital pair contains unsupported atomic mix")
    if count > sum(capacities.values()):
        raise RuntimeError("common schedule aggregate capacity drift")
    raw_weights = {sleeve: max(float(weights.get(sleeve, 0.0)), 0.0) for sleeve in sleeves}
    denominator = sum(raw_weights.values())
    if denominator <= 0:
        raw_weights = {sleeve: 1.0 for sleeve in sleeves}
        denominator = float(len(sleeves))
    allocation = {
        sleeve: min(capacities[sleeve], int(math.floor(count * raw_weights[sleeve] / denominator)))
        for sleeve in sleeves
    }
    while sum(allocation.values()) < count:
        choices = [
            sleeve for sleeve in sleeves if allocation[sleeve] < capacities[sleeve]
        ]
        if not choices:
            raise RuntimeError("common schedule allocation rounding drift")
        sleeve = max(
            choices,
            key=lambda item: (
                count * raw_weights[item] / denominator - allocation[item],
                -ord(item[0]),
                item,
            ),
        )
        allocation[sleeve] += 1
    return allocation


def _maximum_common_ticket_count(
    candidate_sleeves: Sequence[str],
    control_sleeves: Sequence[str],
    issue: str,
    candidate_cash: float,
    control_cash: float,
    bridge: dict[tuple[str, str], NativeIssueSleeve],
) -> tuple[int, str]:
    """Find the maximal equal-yuan executable schedule for a single issue."""
    candidate_values = [bridge[(sleeve, issue)] for sleeve in candidate_sleeves]
    control_values = [bridge[(sleeve, issue)] for sleeve in control_sleeves]
    if any(value.status != "SETTLED" for value in (*candidate_values, *control_values)):
        return 0, "UNAVAILABLE_FROZEN_TICKET_PREFIX"
    upper = min(
        sum(value.requested_ticket_count for value in candidate_values),
        sum(value.requested_ticket_count for value in control_values),
        int(math.floor(min(candidate_cash, control_cash) / TICKET_STAKE_YUAN)),
    )
    atomic_counts = {
        value.requested_ticket_count
        for value in (*candidate_values, *control_values)
        if value.atomic
    }
    if not atomic_counts:
        return upper, "" if upper else "ZERO_COMMON_CAPITAL"
    # The only frozen atomic member in this bounded comparison is FULL.  It
    # can participate only at its full issue request, never at a proportional
    # synthetic prefix.
    if len(atomic_counts) != 1:
        raise RuntimeError("incompatible atomic common schedule")
    atomic_count = next(iter(atomic_counts))
    if upper >= atomic_count:
        return atomic_count, ""
    return 0, "ATOMIC_FULL_NOT_COMMONLY_EXECUTABLE"


def replay_common_capital_contrast(
    *,
    contrast_id: str,
    candidate_identity: tuple[object, ...],
    control_identity: tuple[object, ...],
    paths: dict[tuple[object, ...], list[dict[str, object]]],
) -> tuple[list[dict[str, object]], dict[str, object], list[dict[str, object]]]:
    """Replay one frozen pair under a common chronological yuan schedule.

    The schedule is selected only from frozen per-issue capacity and the two
    pre-issue bankrolls, then both sides settle their own immutable prefixes.
    It is intentionally a two-contrast bounded replay, not a new policy grid.
    """
    candidate_path = sorted(paths[candidate_identity], key=lambda row: int(row["calendar_index"]))
    control_path = sorted(paths[control_identity], key=lambda row: int(row["calendar_index"]))
    if [row["issue_instance"] for row in candidate_path] != [row["issue_instance"] for row in control_path]:
        raise RuntimeError("common capital contrast calendar mismatch")
    candidate_sleeves = tuple(sorted(candidate_path[0]["sleeve_settlements"]))
    control_sleeves = tuple(sorted(control_path[0]["sleeve_settlements"]))
    bridge = h1_ticket_bridge()
    candidate_bankroll = control_bankroll = INITIAL_BANKROLL_YUAN
    schedule: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    unavailable: list[dict[str, object]] = []
    candidate_ticket_identity: list[dict[str, object]] = []
    control_ticket_identity: list[dict[str, object]] = []
    for candidate_row, control_row in zip(candidate_path, control_path, strict=True):
        issue = str(candidate_row["issue_instance"])
        target_count, unavailable_reason = _maximum_common_ticket_count(
            candidate_sleeves, control_sleeves, issue, candidate_bankroll, control_bankroll, bridge,
        )
        candidate_counts = _common_schedule_ticket_counts(
            candidate_sleeves, issue, target_count, candidate_row["weights"], bridge,
        )
        control_counts = _common_schedule_ticket_counts(
            control_sleeves, issue, target_count, control_row["weights"], bridge,
        )
        candidate_settlements = {
            sleeve: bridge[(sleeve, issue)].settle_prefix(count)
            for sleeve, count in candidate_counts.items()
        }
        control_settlements = {
            sleeve: bridge[(sleeve, issue)].settle_prefix(count)
            for sleeve, count in control_counts.items()
        }
        target_stake = target_count * TICKET_STAKE_YUAN
        candidate_stake = sum(float(value["actual_stake_yuan"]) for value in candidate_settlements.values())
        control_stake = sum(float(value["actual_stake_yuan"]) for value in control_settlements.values())
        if not (math.isclose(candidate_stake, target_stake, abs_tol=1e-9) and math.isclose(control_stake, target_stake, abs_tol=1e-9)):
            raise RuntimeError("common capital schedule stake equality drift")
        candidate_net = sum(float(value["pre_tax_net_yuan"]) for value in candidate_settlements.values())
        control_net = sum(float(value["pre_tax_net_yuan"]) for value in control_settlements.values())
        base = {
            "contrast_id": contrast_id,
            "calendar_index": candidate_row["calendar_index"],
            "issue_instance": issue,
            "year": candidate_row["year"],
            "first_kickoff_ts": candidate_row["first_kickoff_ts"],
            "common_schedule_ticket_count": target_count,
            "common_schedule_yuan": target_stake,
            "atomic_rounding_reason": unavailable_reason,
        }
        schedule.append(dict(base))
        if not target_count:
            unavailable.append({**base, "unavailable_reason": unavailable_reason})
        for side, identity, preissue, settlement, counts, net in (
            ("CANDIDATE", candidate_identity, candidate_bankroll, candidate_settlements, candidate_counts, candidate_net),
            ("CONTROL", control_identity, control_bankroll, control_settlements, control_counts, control_net),
        ):
            ticket_identity = {
                "calendar_index": candidate_row["calendar_index"],
                "issue_instance": issue,
                "counts": counts,
                "funded_tax_lot_sha256": {sleeve: value["funded_tax_lot_sha256"] for sleeve, value in sorted(settlement.items())},
            }
            (candidate_ticket_identity if side == "CANDIDATE" else control_ticket_identity).append(ticket_identity)
            rows.append({
                **base,
                "side": side,
                **{field: identity[index] for index, field in enumerate(PATH_IDENTITY)},
                "preissue_bankroll_yuan": preissue,
                "actual_stake_yuan": target_stake,
                "pre_tax_net_yuan": net,
                "postissue_bankroll_yuan": preissue + net,
                "ticket_prefix_identity_sha256": canonical_hash(ticket_identity),
                "ticket_prefix_counts_json": json.dumps(counts, sort_keys=True, separators=(",", ":")),
            })
        candidate_bankroll += candidate_net
        control_bankroll += control_net
    schedule_hash = canonical_hash(schedule)
    for row in rows:
        row["capital_schedule_hash"] = schedule_hash
    for row in unavailable:
        row["capital_schedule_hash"] = schedule_hash
    stake = sum(float(row["common_schedule_yuan"]) for row in schedule)
    active = [row for row in schedule if float(row["common_schedule_yuan"]) > 0]
    summary = {
        "contrast_id": contrast_id,
        "candidate_id": candidate_identity[0],
        "control_id": control_identity[0],
        "capital_schedule_hash": schedule_hash,
        "candidate_ticket_funding_hash": canonical_hash(candidate_ticket_identity),
        "control_ticket_funding_hash": canonical_hash(control_ticket_identity),
        "capital_schedule_equal": True,
        "common_executable_support_hash": canonical_hash([row["issue_instance"] for row in active]),
        "common_executable_issue_count": len(active),
        "unavailable_issue_count": len(unavailable),
        "common_stake_yuan": stake,
        "candidate_ending_bankroll_yuan": candidate_bankroll,
        "control_ending_bankroll_yuan": control_bankroll,
        "matched_lift_yuan": candidate_bankroll - control_bankroll,
        "candidate_pre_tax_roi": (candidate_bankroll - INITIAL_BANKROLL_YUAN) / stake if stake else "",
        "control_pre_tax_roi": (control_bankroll - INITIAL_BANKROLL_YUAN) / stake if stake else "",
        "matched_lift_pre_tax_roi": (candidate_bankroll - control_bankroll) / stake if stake else "",
        "strict_inference_status": "DESCRIPTIVE_MATCHED_CAPITAL_NO_BOOTSTRAP_RERUN",
        "atomic_rounding_contract": "MAXIMAL_COMMON_EXECUTABLE_WHOLE_TICKET_SCHEDULE",
    }
    if any(float(row["actual_stake_yuan"]) != float(row["common_schedule_yuan"]) for row in rows):
        raise RuntimeError("common schedule ledger equality assertion failed")
    return rows, summary, unavailable


def minimal_stage4_matched_capital_tables(
    paths: dict[tuple[object, ...], list[dict[str, object]]],
) -> dict[str, list[dict[str, object]]]:
    """Run exactly the two PI-authorized common-capital contrasts."""
    selected = _minimal_decision_identities({
        "sleeve_funding_ledger": [
            {
                **{field: identity[index] for index, field in enumerate(PATH_IDENTITY)},
                "sleeve_or_family_id": sleeve,
            }
            for identity, path in paths.items()
            for sleeve in path[0]["sleeve_settlements"]
        ],
        "capital_summary": [
            {
                **{field: identity[index] for index, field in enumerate(PATH_IDENTITY)},
                "ending_bankroll_yuan": path[-1]["postissue_bankroll_yuan"],
            }
            for identity, path in paths.items()
        ],
    })
    by_label = dict(selected)
    model_q = by_label["STRONGEST_PAIR"]
    q = by_label["Q_SOURCE_Q_TOP_MASS_M192"]
    full = by_label["BEST_FULL_FULL"]
    outputs = {"matched_capital_issue_ledger": [], "matched_capital_comparisons": [], "matched_capital_unavailable_issues": []}
    for contrast_id, candidate, control in (
        ("MODEL_PLUS_Q_VS_Q", model_q, q),
        ("Q_VS_FULL", q, full),
    ):
        rows, summary, unavailable = replay_common_capital_contrast(
            contrast_id=contrast_id, candidate_identity=candidate, control_identity=control, paths=paths,
        )
        outputs["matched_capital_issue_ledger"].extend(rows)
        outputs["matched_capital_comparisons"].append(summary)
        outputs["matched_capital_unavailable_issues"].extend(unavailable)
    return outputs


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
    """Use the maintained inclusive percentile primitive, never hand-roll it."""
    if not values:
        return None
    if not 0.0 <= probability <= 1.0:
        raise ValueError("quantile probability outside [0, 1]")
    ordered = sorted(values)
    if probability == 0.0:
        return ordered[0]
    if probability == 1.0:
        return ordered[-1]
    # ``inclusive`` is the same (n - 1) linear interpolation convention used
    # in the released v2 package, while delegating the generic statistic to
    # Python's maintained standard-library implementation.
    thousandths = int(round(probability * 1000))
    if not math.isclose(probability, thousandths / 1000.0, abs_tol=1e-12):
        raise ValueError("frozen report quantile must lie on the 0.001 grid")
    return statistics.quantiles(ordered, n=1000, method="inclusive")[thousandths - 1]


def minimal_stage4_dependence_tables(checkpoint: Path) -> dict[str, list[dict[str, object]]]:
    """Emit non-duplicative realized dependence on the common native baseline."""
    _, paths = load_minimal_stage4_checkpoint(checkpoint)
    axis = ("NATIVE_REQUEST_CONTROL", "1.00", "EQUAL_WEIGHT", "UNIT_CAPITAL", "BUNDLE_ORDINAL_001")
    realized: list[dict[str, object]] = []
    for identity, path in paths.items():
        if tuple(identity[1:]) != axis or len(path[0]["sleeve_settlements"]) < 2:
            continue
        realized.extend(realized_funded_flow_dependence(path))
    panels = list(realized)
    wide: dict[tuple[object, ...], dict[str, object]] = {}
    metric_map = {
        "PEARSON": "pearson_correlation", "SPEARMAN": "spearman_rank_correlation",
        "DOWNSIDE_CORRELATION": "downside_correlation", "PAYOUT_OVERLAP_COUNT": "payout_overlap_count",
        "HIT_OVERLAP_COUNT": "hit_overlap_count", "JOINT_LOSS_RATE": "full_calendar_joint_loss_rate",
    }
    for row in realized:
        if row["panel_type"] != "OVERALL" or row["denominator_id"] != "FULL_CALENDAR_ZERO_FLOW":
            continue
        key = tuple(row[field] for field in PATH_IDENTITY) + (row["economic_family_left"], row["economic_family_right"])
        target = wide.setdefault(key, {
            **{field: row[field] for field in PATH_IDENTITY},
            "sleeve_left": row["economic_family_left"], "sleeve_right": row["economic_family_right"],
            "prior_covariance": "", "prior_correlation": "", "pearson_correlation": "", "spearman_rank_correlation": "",
            "rolling_correlation_20": "", "payout_overlap_count": "", "hit_overlap_count": "", "contribution_hhi": "",
            "downside_correlation": "", "tail_co_loss_count": "", "full_calendar_zero_flow_count": row["observation_count"],
            "union_active_count": "", "intersection_active_count": "", "full_calendar_joint_loss_rate": "",
            "union_active_joint_loss_rate": "", "intersection_active_joint_loss_rate": "",
            "concurrent_issue_count": row["observation_count"], "portfolio_pnl_reconciliation_yuan": 0.0,
        })
        field = metric_map.get(str(row["metric"]))
        if field:
            target[field] = row["value"]
    intrinsic = [{
        **{field: row[field] for field in PATH_IDENTITY},
        "economic_family_left": row["economic_family_left"], "economic_family_right": row["economic_family_right"],
        "denominator_id": row["denominator_id"], "panel_type": row["panel_type"], "panel_id": row["panel_id"],
        "window_issues": row["window_issues"], "exclusion_id": row["exclusion_id"], "metric": row["metric"],
        "native_return_basis": "FROZEN_NATIVE_TICKET_PNL", "value": row["value"],
        "observation_count": row["observation_count"], "undefined_reason": row["undefined_reason"],
        "matched_support_hash": canonical_hash(["COMPLETE_348_ISSUE_CALENDAR"]),
    } for row in realized]
    return {"dependence": list(wide.values()), "dependence_panel": panels,
            "realized_funded_flow_dependence": realized, "intrinsic_native_dependence": intrinsic}


def _minimal_decision_identities(tables: dict[str, Sequence[dict[str, object]]]) -> list[tuple[str, tuple[object, ...]]]:
    """Return the three standalones, strongest pair and triple on one fixed axis."""
    axis = ("NATIVE_REQUEST_CONTROL", "1.00", "EQUAL_WEIGHT", "UNIT_CAPITAL", "BUNDLE_ORDINAL_001")
    funding: dict[tuple[object, ...], set[str]] = defaultdict(set)
    for row in tables["sleeve_funding_ledger"]:
        identity = tuple(row[field] for field in PATH_IDENTITY)
        if tuple(identity[1:]) == axis:
            funding[identity].add(str(row["sleeve_or_family_id"]))
    capital = {tuple(row[field] for field in PATH_IDENTITY): row for row in tables["capital_summary"]}
    selected: list[tuple[str, tuple[object, ...]]] = []
    for sleeve in H1_SLEEVES:
        identity = next((item for item, members in funding.items() if members == {sleeve}), None)
        if identity is None:
            raise RuntimeError(f"decision chart standalone absent: {sleeve}")
        selected.append((sleeve, identity))
    pairs = [(identity, capital[identity]) for identity, members in funding.items() if len(members) == 2]
    if len(pairs) != 3:
        raise RuntimeError("decision chart pair denominator drift")
    strongest_pair = max(pairs, key=lambda item: (float(item[1]["ending_bankroll_yuan"]), str(item[0][0])))[0]
    selected.append(("STRONGEST_PAIR", strongest_pair))
    triple = next((identity for identity, members in funding.items() if members == set(H1_SLEEVES)), None)
    if triple is None:
        raise RuntimeError("decision chart triple absent")
    selected.append(("TRIPLE", triple))
    return selected


def render_minimal_stage4_charts(
    chart_dir: Path, series: Sequence[tuple[str, Sequence[dict[str, object]]]],
) -> None:
    """Render the one source table with the pinned matplotlib backend.

    SVG, PNG, and PDF must be actual charts with the same title, axes, and
    legend.  The library import is deliberately lazy so package verification
    remains dependency-free; rendering requires the repository-pinned
    ``matplotlib==3.10.9`` environment.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
    except ImportError as exc:  # pragma: no cover - exercised in clean envs
        raise RuntimeError("matplotlib==3.10.9 is required to render #192 charts") from exc
    matplotlib.rcParams.update({"svg.hashsalt": "bj192-stage4-v4", "font.family": "DejaVu Sans"})
    figure, axis = plt.subplots(figsize=(11, 5.6), layout="constrained")
    for label, rows in series:
        axis.plot(
            [int(row["calendar_index"]) for row in rows],
            [float(row["postissue_bankroll_yuan"]) for row in rows],
            linewidth=1.4,
            label=label,
        )
    axis.axhline(INITIAL_BANKROLL_YUAN, color="#555555", linestyle="--", linewidth=0.8, label="START ¥100,000")
    axis.set_title("#192 Stage-4 fixed native decision paths — descriptive, unmatched funding")
    axis.set_xlabel("Chronological issue index")
    axis.set_ylabel("Ending bankroll (¥)")
    axis.grid(alpha=0.25)
    axis.legend(ncol=2, fontsize=8)
    metadata = {"Creator": "beijing-lot #192", "Title": "#192 Stage-4 decision paths"}
    for suffix in ("svg", "png", "pdf"):
        format_metadata = dict(metadata)
        if suffix == "svg":
            format_metadata["Date"] = "2026-08-06T00:00:00Z"
        elif suffix == "pdf":
            fixed_date = datetime.datetime(2026, 8, 6, tzinfo=datetime.UTC)
            format_metadata["CreationDate"] = fixed_date
            format_metadata["ModDate"] = fixed_date
        figure.savefig(
            chart_dir / f"decision_paths.{suffix}",
            dpi=160 if suffix == "png" else None,
            metadata=format_metadata,
        )
    plt.close(figure)


def minimal_stage4_decision_artifacts(
    stage: Path,
    tables: dict[str, Sequence[dict[str, object]]],
    *,
    matched_capital_comparisons: Sequence[dict[str, object]] = (),
) -> dict[str, dict[str, object]]:
    """Write manifest-covered chart sources and a concise decision guide."""
    selected = _minimal_decision_identities(tables)
    capital = {tuple(row[field] for field in PATH_IDENTITY): row for row in tables["capital_summary"]}
    holding = {tuple(row[field] for field in PATH_IDENTITY): row for row in tables["holding_metrics"]}
    ledger: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in tables["issue_ledger"]:
        ledger[tuple(row[field] for field in PATH_IDENTITY)].append(row)
    full_raw_comparison_by_identity: dict[tuple[object, ...], dict[str, object]] = {}
    for row in tables["baseline_lift"]:
        identity = tuple(row[field] for field in PATH_IDENTITY)
        if row["control_id"] == next(identity[0] for label, identity in selected if label == "BEST_FULL_FULL"):
            full_raw_comparison_by_identity[identity] = row
    chart_source: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []
    series: list[tuple[str, Sequence[dict[str, object]]]] = []
    for label, identity in selected:
        path = sorted(ledger[identity], key=lambda row: int(row["calendar_index"]))
        if len(path) != len(read_csv(GATE_A / "full_calendar.csv")):
            raise RuntimeError("decision chart path denominator drift")
        series.append((label, path))
        capital_row, holding_row = capital[identity], holding[identity]
        comparison = full_raw_comparison_by_identity.get(identity)
        summary.append({
            "label": label, "portfolio_id": identity[0], "mode": identity[1], "position_fraction": identity[2],
            "weight_method": identity[3], "normalization_method": identity[4], "deployment_replicate_bundle_id": identity[5],
            "ending_bankroll_yuan": capital_row["ending_bankroll_yuan"],
            "matched_full_lift_yuan": "" if comparison is None else comparison["matched_lift_yuan"],
            "unmatched_full_raw_path_difference_yuan": "" if comparison is None else comparison["unmatched_raw_path_difference_yuan"],
            "full_actual_funding_equal": "" if comparison is None else comparison["actual_funding_equal"],
            "pre_tax_roi": capital_row["pre_tax_roi"], "turnover_yuan": capital_row["turnover_yuan"], "retained_cash_yuan": capital_row["cash_yuan"],
            "max_drawdown_yuan": holding_row["max_drawdown_yuan"], "loss_streak_calendar": holding_row["loss_streak_calendar"],
            "miss_streak_calendar": holding_row["miss_streak_calendar"], "recovery_duration_max_issues": holding_row["recovery_duration_max_issues"],
            "time_under_water_issues": holding_row["time_under_water_issues"],
            "interpretation": "REALIZED_PATH;_FULL_COMPARISON_IS_UNMATCHED_UNLESS_ACTUAL_FUNDING_EQUAL;_CASH_AND_TURNOVER_ARE_NOT_TICKET_EDGE",
        })
        for row in path:
            chart_source.append({
                "label": label, "portfolio_id": identity[0], "calendar_index": row["calendar_index"], "issue_instance": row["issue_instance"],
                "preissue_bankroll_yuan": row["preissue_bankroll_yuan"], "postissue_bankroll_yuan": row["postissue_bankroll_yuan"],
                "pre_tax_net_yuan": row["pre_tax_net_yuan"], "actual_stake_yuan": row["actual_stake_yuan"],
                "retained_cash_yuan": row["retained_cash_yuan"], "drawdown_yuan": row["drawdown_yuan"],
            })
    chart_dir = stage / "charts"
    chart_dir.mkdir(exist_ok=True)
    summary_fields = write_csv_rows(stage / "decision_path_summary.csv", summary, compressed=False)
    source_fields = write_csv_rows(stage / "decision_chart_source.csv", chart_source, compressed=False)
    render_minimal_stage4_charts(chart_dir, series)
    svg = (chart_dir / "decision_paths.svg").read_text(encoding="utf-8")
    (chart_dir / "decision_paths.html").write_text("<!doctype html><meta charset=\"utf-8\"><title>#192 decision paths</title>" + svg, encoding="utf-8")
    decisions = "\n".join(
        f"- {row['label']}: ending ¥{float(row['ending_bankroll_yuan']):,.2f}; ROI {float(row['pre_tax_roi']):.2%}; turnover ¥{float(row['turnover_yuan']):,.2f}; max drawdown ¥{float(row['max_drawdown_yuan']):,.2f}; FULL raw-path difference {('¥' + format(float(row['unmatched_full_raw_path_difference_yuan']), ',.2f')) if row['unmatched_full_raw_path_difference_yuan'] not in ('', None) else 'not applicable'} ({'matched funding' if row['full_actual_funding_equal'] else 'unmatched funding'})."
        for row in summary
    )
    matched_capital_text = "\n".join(
        f"- {row['contrast_id']}: {int(row['common_executable_issue_count'])} common executable issues; "
        f"¥{float(row['common_stake_yuan']):,.2f} identical schedule; candidate ROI {float(row['candidate_pre_tax_roi']):.2%}; "
        f"control ROI {float(row['control_pre_tax_roi']):.2%}; matched-capital lift ¥{float(row['matched_lift_yuan']):,.2f}; "
        f"{int(row['unavailable_issue_count'])} unavailable/atomic-rounding issues."
        if float(row["common_stake_yuan"] or 0) > 0 else
        f"- {row['contrast_id']}: no common executable capital schedule; {int(row['unavailable_issue_count'])} unavailable issues."
        for row in matched_capital_comparisons
    ) or "- No matched-capital comparison was materialized."
    report = f"""# #192 Stage-4 decision guide

The three frozen standalones, the strongest realized pair, and the frozen
triple below share the NATIVE / 100% / EQUAL_WEIGHT / UNIT_CAPITAL /
BUNDLE_ORDINAL_001 execution axis.  They do **not** generally share realised
funding with FULL.  Their raw path differences are therefore explicitly
unmatched diagnostics, not matched-FULL lift or strict inference.

{decisions}

The Q sleeve has the strongest standalone ROI.  MODEL+Q can raise ending
capital by taking more turnover but lowers ROI relative to Q; the triple adds
substantially more turnover and worsens both ROI and drawdown.  Because the
raw FULL comparisons have unequal actual funding, they remain descriptive.

## Bounded matched-capital replays

{matched_capital_text}

These use the same deterministic issue-level yuan schedule on both sides, but
retain each side's own frozen ticket-prefix identity.  They are not a new
strategy search or a bootstrap rerun.  The terminal finding remains
**NO_PROMOTION**.
"""
    (stage / "DECISION_REPORT.md").write_text(report, encoding="utf-8")
    return {
        "decision_path_summary": {"filename": "decision_path_summary.csv", "row_count": len(summary), "fields": summary_fields},
        "decision_chart_source": {"filename": "decision_chart_source.csv", "row_count": len(chart_source), "fields": source_fields},
        "decision_charts": {"filename": "charts/decision_paths.svg|html|png|pdf", "row_count": len(series), "fields": ["manifest_covered_reproducible_artifacts"]},
    }


def _package_table_rows(package: Path, manifest: dict[str, object], name: str) -> list[dict[str, str]]:
    entry = manifest[name]
    if not isinstance(entry, dict):
        raise RuntimeError(f"invalid package table manifest entry: {name}")
    filename = str(entry["filename"])
    path = package / filename
    return read_gzip(path) if filename.endswith(".gz") else read_csv(path)


def _minimal_paths_from_package(
    package: Path, manifest: dict[str, object],
) -> tuple[dict[tuple[object, ...], list[dict[str, object]]], dict[str, list[dict[str, str]]]]:
    """Rehydrate the minimum state needed for v3 corrections from v2 bytes.

    This reader is deliberately narrower than the old author checkpoint: it
    joins only committed issue, sleeve-funding and weight ledgers, and never
    invokes a ticket settler.  It provides an auditable, bounded recovery
    path for the capital and attribution corrections.
    """
    issue_rows = _package_table_rows(package, manifest, "issue_ledger")
    funding_rows = _package_table_rows(package, manifest, "sleeve_funding_ledger")
    weight_rows = _package_table_rows(package, manifest, "weight_history")
    paths: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    issue_by_key: dict[tuple[object, ...], dict[str, object]] = {}
    for source in issue_rows:
        row: dict[str, object] = dict(source)
        identity = tuple(row[field] for field in PATH_IDENTITY)
        key = (*identity, row["calendar_index"])
        if key in issue_by_key:
            raise RuntimeError("package issue-ledger primary key drift")
        row["weights"] = {}
        row["sleeve_settlements"] = {}
        issue_by_key[key] = row
        paths[identity].append(row)
    for source in funding_rows:
        identity = tuple(source[field] for field in PATH_IDENTITY)
        row = issue_by_key.get((*identity, source["calendar_index"]))
        if row is None:
            raise RuntimeError("package sleeve-funding join drift")
        sleeve = str(source["sleeve_or_family_id"])
        if sleeve in row["sleeve_settlements"]:
            raise RuntimeError("package duplicate sleeve-funding join")
        row["sleeve_settlements"][sleeve] = {
            "actual_ticket_count": int(source["actual_ticket_count"]),
            "actual_stake_yuan": source["actual_stake_yuan"],
            "gross_yuan": source["pre_tax_gross_yuan"],
            "pre_tax_net_yuan": source["pre_tax_net_yuan"],
            "tax_yuan": source["tax_yuan"],
            "funded_tax_lot_sha256": source["funded_tax_lot_sha256"],
        }
    for source in weight_rows:
        identity = tuple(source[field] for field in PATH_IDENTITY)
        row = issue_by_key.get((*identity, source["calendar_index"]))
        if row is None:
            raise RuntimeError("package weight-history join drift")
        sleeve = str(source["sleeve_id"])
        if sleeve in row["weights"]:
            raise RuntimeError("package duplicate weight-history join")
        row["weights"][sleeve] = source["weight"]
    calendar_count = len(read_csv(GATE_A / "full_calendar.csv"))
    for identity, rows in paths.items():
        rows.sort(key=lambda row: int(row["calendar_index"]))
        if len(rows) != calendar_count or any(set(row["weights"]) != set(row["sleeve_settlements"]) for row in rows):
            raise RuntimeError(f"package Stage-4 path rehydration drift: {identity}")
    extra = {
        name: _package_table_rows(package, manifest, name)
        for name in ("capital_summary", "holding_metrics", "baseline_lift")
    }
    return paths, extra


def _write_existing_package_metadata(stage: Path, *, source_binding: dict[str, object], package_note: str) -> dict[str, str]:
    """Finish a staged correction package with recursive immutable hashes."""
    (stage / "source_binding.json").write_text(json.dumps(source_binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (stage / "README.md").write_text(package_note.rstrip() + "\n", encoding="utf-8")
    files = sorted(path for path in stage.rglob("*") if path.is_file())
    archive = {str(path.relative_to(stage)): sha256_file(path) for path in files}
    scientific = {str(path.relative_to(stage)): canonical_scientific_sha256(path) for path in files}
    content = {
        "contract": CONTRACT, "version": VERSION,
        "canonical_scientific_payload_sha256": scientific,
        "canonical_scientific_identity_sha256": canonical_hash(scientific),
        "archive_transport_payload_sha256": archive,
        "archive_transport_contract": {"gzip": "gzip.GzipFile(filename='', mtime=0)", "scientific_identity": "gzip payloads SHA-256 after decompression"},
    }
    (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_files = sorted(path for path in stage.rglob("*") if path.is_file())
    manifest = {str(path.relative_to(stage)): sha256_file(path) for path in manifest_files}
    (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"manifest_sha256": sha256_file(stage / "SHA256SUMS.json"), "content_sha256": sha256_file(stage / "CONTENT_IDENTITY.json")}


def finalize_minimal_stage4_authoritative_from_package(source: Path, output: Path) -> dict[str, object]:
    """Create one final package from a verified prior delivery package.

    This bounded delivery reducer does not replay tickets, bootstrap, or
    search.  It only corrects comparison labels, capital semantics, and chart
    rendering while retaining the settled ledgers that are scientifically
    unaffected.  The source hash is retained as provenance; only ``output``
    is intended to be shipped in the final tree.
    """
    source, output = source.resolve(), output.resolve()
    if output.exists():
        raise RuntimeError(f"immutable correction target already exists: {output}")
    stage = output.with_name(f".{output.name}.stage")
    if stage.exists():
        raise RuntimeError(f"immutable correction stage already exists: {stage}")
    source_manifest_sha = sha256_file(source / "SHA256SUMS.json")
    source_content_sha = sha256_file(source / "CONTENT_IDENTITY.json")
    verify_package(source, source_manifest_sha, source_content_sha)
    manifest = json.loads((source / "table_manifest.json").read_text(encoding="utf-8"))
    paths, extra = _minimal_paths_from_package(source, manifest)
    full_by_axis = {
        identity[1:]: path for identity, path in paths.items()
        if tuple(sorted(path[0]["sleeve_settlements"])) == ("BEST_FULL_FULL",)
    }
    corrected_capital: list[dict[str, object]] = []
    for identity, path in sorted(paths.items(), key=lambda item: canonical_hash(item[0])):
        control = full_by_axis.get(identity[1:])
        if control is None:
            raise RuntimeError("authoritative matched FULL recovery control unavailable")
        original = next((row for row in extra["capital_summary"] if tuple(row[field] for field in PATH_IDENTITY) == identity), None)
        if original is None:
            raise RuntimeError("authoritative capital-summary recovery join drift")
        capital = dict(original)
        capital["minimum_required_start_yuan"] = "" if identity[1] == "COMPOUNDING_BANKROLL" else minimum_required_start_yuan(path)
        capital["minimum_required_start_definition"] = (
            "SMALLEST_WHOLE_YUAN_START_REPRODUCING_SAVED_EXACT_FUNDED_SCHEDULE"
            if identity[1] != "COMPOUNDING_BANKROLL" else "NOT_MONOTONE_COMPOUNDING_BANKROLL"
        )
        capital["first_unfundable_issue"] = first_capital_unfundable_issue(path)
        corrected_capital.append(capital)
    if len(corrected_capital) != len(paths):
        raise RuntimeError("authoritative capital path denominator drift")
    stage.mkdir(parents=False)
    try:
        skip = {"SHA256SUMS.json", "CONTENT_IDENTITY.json", "source_binding.json", "table_manifest.json", "README.md"}
        for path in source.rglob("*"):
            if path.is_file() and path.name not in skip and "__pycache__" not in path.parts:
                destination = stage / path.relative_to(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
        schema = json.loads((GATE_A / "output_schema.json").read_text(encoding="utf-8"))
        manifest["capital_summary"] = {
            "filename": "capital_summary.csv", "row_count": len(corrected_capital),
            "fields": write_csv_rows(stage / "capital_summary.csv", corrected_capital, compressed=False, declared_fields=[*schema["capital_summary"]["key"], *schema["capital_summary"]["fields"]]),
        }
        # v3's 150,336-row ex-ante covariance and matched-risk ledger already
        # passed PI audit and is scientifically unaffected by this bounded
        # capital-comparison correction.  It was byte-copied with the other
        # protected settlement ledgers above; do not rehydrate it in memory.
        corrected_baseline = minimal_stage4_comparisons_from_paths(paths, corrected_capital)
        manifest["baseline_lift"] = {
            "filename": "baseline_lift.csv", "row_count": len(corrected_baseline),
            "fields": write_csv_rows(stage / "baseline_lift.csv", corrected_baseline, compressed=False),
        }
        matched_capital = minimal_stage4_matched_capital_tables(paths)
        for name, rows in matched_capital.items():
            filename = f"{name}.csv"
            manifest[name] = {
                "filename": filename,
                "row_count": len(rows),
                "fields": write_csv_rows(stage / filename, rows, compressed=False),
            }
        chart_tables: dict[str, Sequence[dict[str, object]]] = {
            "issue_ledger": [row for path in paths.values() for row in path],
            "sleeve_funding_ledger": _package_table_rows(source, manifest, "sleeve_funding_ledger"),
            "capital_summary": corrected_capital,
            "holding_metrics": extra["holding_metrics"],
            "baseline_lift": corrected_baseline,
        }
        ancillary = minimal_stage4_decision_artifacts(
            stage,
            chart_tables,
            matched_capital_comparisons=matched_capital["matched_capital_comparisons"],
        )
        manifest.update(ancillary)
        (stage / "table_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        source_binding = {
            "gate_a": {"package": GATE_A.name, "manifest_sha256": EXPECTED_GATE_A_MANIFEST, "content_identity_sha256": EXPECTED_GATE_A_CONTENT},
            "prior_delivery_package": {"package": source.name, "manifest_sha256": source_manifest_sha, "content_identity_sha256": source_content_sha},
            "correction_scope": "ACTUAL_FUNDING_COMPARISON_SEMANTICS;_TWO_COMMON_CAPITAL_PREFIX_REPLAYS;_CAPITAL_CONSTRAINT_LABEL;_MATPLOTLIB_DECISION_CHARTS",
            "settlement_boundary": "VERIFIED_PRIOR_PACKAGE_PLUS_TWO_348_ISSUE_COMMON_CAPITAL_PREFIX_REPLAYS_NO_BOOTSTRAP_RERUN",
            "reproducibility": "CLEAN_CLONE_VERIFIES_THE_SINGLE_AUTHORITATIVE_PACKAGE_WITHOUT_AUTHOR_SCRATCH_OR_PRIOR_PACKAGE",
        }
        receipt = _write_existing_package_metadata(stage, source_binding=source_binding, package_note="""# #192 Gate B — minimal Stage-4 final package

This is the one authoritative #192 Gate-B delivery package.  It preserves
unaffected settled ledgers from a verified prior package, corrects comparison
semantics so unequal actual funding is never called matched lift, derives
capital failure labels from allocator constraints, and renders all decision
charts with the repository-pinned matplotlib version.  It does not replay
tickets or rerun bootstrap inference.  Terminal disposition remains
**NO_PROMOTION**.
""")
        verify_package(stage, receipt["manifest_sha256"], receipt["content_sha256"])
        os.replace(stage, output)
        return {"output": str(output), **receipt, "path_count": len(paths), "risk_row_count": manifest["risk_decomposition"]["row_count"]}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


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
        # The frozen capital contract defines fundability on whole-yuan
        # pre-issue balances.  The saved path is the exact executable
        # schedule: this bisection reproduces its funded ticket vector, not a
        # hypothetical smaller allocation or a fresh ticket replay.
        "minimum_required_start_yuan": "" if mode == "COMPOUNDING_BANKROLL" else minimum_required_start_yuan(path_rows),
        "minimum_required_start_definition": (
            "SMALLEST_WHOLE_YUAN_START_REPRODUCING_SAVED_EXACT_FUNDED_SCHEDULE"
            if mode != "COMPOUNDING_BANKROLL" else "NOT_MONOTONE_COMPOUNDING_BANKROLL"
        ),
        "fundable_issue_count": sum(float(row["actual_stake_yuan"]) > 0 for row in path_rows),
        "first_unfundable_issue": first_capital_unfundable_issue(path_rows),
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


def first_capital_unfundable_issue(path_rows: Sequence[dict[str, object]]) -> str:
    """Return only genuine bankroll-constrained NO_BET, not risk/cap NO_BET.

    An atomic block can be intentionally excluded because the ex-ante risk
    budget is smaller than its executable stake while the account has ample
    cash.  That is a policy NO_BET, not a failure of bankroll fundability.
    The frozen allocator records a genuine balance constraint with
    ``SCALED_BY_PREISSUE_BANKROLL`` (or ``RUIN_NO_BET``).
    """
    for row in sorted(path_rows, key=lambda item: int(item["calendar_index"])):
        if float(row["requested_stake_yuan"]) <= 0 or float(row["actual_stake_yuan"]) > 0:
            continue
        reasons = str(row.get("reason_codes", ""))
        if "SCALED_BY_PREISSUE_BANKROLL" in reasons or "RUIN_NO_BET" in reasons:
            return str(row["issue_instance"])
    return ""


def is_fundable_from_start(path_rows: Sequence[dict[str, object]], starting_yuan: int) -> bool:
    """Check exact saved funding at an integer initial bankroll.

    For a fixed/native path, holding the saved ticket vector fixed makes each
    next balance ``starting + prior exact net``.  The allocator is constrained
    by the integer pre-issue balance, so this is the contract predicate for
    the deterministic bisection below.  A lower start must not be credited
    with a different, smaller ticket prefix.
    """
    if starting_yuan < 0:
        return False
    bankroll = float(starting_yuan)
    for row in sorted(path_rows, key=lambda item: int(item["calendar_index"])):
        if math.floor(bankroll + 1e-9) < float(row["actual_stake_yuan"]):
            return False
        bankroll += float(row["pre_tax_net_yuan"])
    return True


def minimum_required_start_yuan(path_rows: Sequence[dict[str, object]]) -> int:
    """Return the frozen minimum whole-yuan start by monotone bisection."""
    if not path_rows:
        raise ValueError("cannot bisect an empty capital path")
    # The released ¥100k path is itself a proven upper bound.  Keep the bound
    # explicit so a corrupted path fails closed instead of expanding to an
    # uncontracted capital range.
    upper = int(INITIAL_BANKROLL_YUAN)
    if not is_fundable_from_start(path_rows, upper):
        raise RuntimeError("released ¥100k path is not a fundability upper bound")
    lower = 0
    while lower < upper:
        middle = (lower + upper) // 2
        if is_fundable_from_start(path_rows, middle):
            upper = middle
        else:
            lower = middle + 1
    if lower and is_fundable_from_start(path_rows, lower - 1):
        raise RuntimeError("integer fundability bisection boundary drift")
    return lower


def risk_decomposition_rows(
    path_rows: Sequence[dict[str, object]],
    bridge: dict[tuple[str, str], IssueSleeve],
    *,
    matched_control_rows: Sequence[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Emit exact ex-ante variance and matched realized-loss diagnostics.

    The saved path intentionally stores a covariance hash rather than a wide
    matrix.  Reconstructing it from the same strictly-prior frozen H1 return
    history is deterministic and gives a genuine ex-ante marginal/Euler
    decomposition.  It never treats covariance as cash P&L.  Matched FULL
    drawdown and per-issue loss-tail deltas remain realized path diagnostics.
    """
    ordered = sorted(path_rows, key=lambda item: int(item["calendar_index"]))
    control_by_index: dict[int, dict[str, object]] = {}
    if matched_control_rows is not None:
        control_holding = summarize_holding_path(matched_control_rows)["issue_rows"]
        control_by_index = {int(row["calendar_index"]): row for row in control_holding}
        if len(control_by_index) != len(ordered):
            raise RuntimeError("matched FULL risk-calendar denominator drift")
    sleeves = tuple(sorted(ordered[0]["sleeve_settlements"]))
    gate = frozen_gate_a()
    history: list[dict[str, float | None]] = []
    rows: list[dict[str, object]] = []
    candidate_holding = summarize_holding_path(ordered)["issue_rows"]
    for path_row in candidate_holding:
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
        observations = gate.active_common_history(history, list(sleeves))
        covariance = gate.covariance_matrix(observations, list(sleeves)) if len(observations) >= 52 else None
        weights = [float(path_row["weights"][sleeve]) for sleeve in sleeves]
        covariance_times_weights = (
            [sum(covariance[index][other] * weights[other] for other in range(len(sleeves))) for index in range(len(sleeves))]
            if covariance is not None else []
        )
        control = control_by_index.get(int(path_row["calendar_index"]))
        if control is not None:
            matched_drawdown_delta = float(path_row["drawdown_yuan"]) - float(control["drawdown_yuan"])
            matched_tail_loss_delta = max(-portfolio_net, 0.0) - max(-float(control["pre_tax_net_yuan"]), 0.0)
        else:
            matched_drawdown_delta = None
            matched_tail_loss_delta = None
        for sleeve_id, settlement in sorted(settlements.items()):
            sleeve_index = sleeves.index(sleeve_id)
            family = canonical_economic_catalog()[sleeve_id]["economic_family_id"]
            native_stake = bridge[(sleeve_id, str(path_row["issue_instance"]))].requested_ticket_count * TICKET_STAKE_YUAN
            funded = float(settlement["actual_stake_yuan"])
            rows.append({
                **{field: path_row[field] for field in PATH_IDENTITY},
                "calendar_index": path_row["calendar_index"],
                "issue_instance": path_row["issue_instance"],
                "economic_family_id": family,
                "marginal_variance_contribution": covariance_times_weights[sleeve_index] if covariance is not None else "",
                "euler_variance_contribution": weights[sleeve_index] * covariance_times_weights[sleeve_index] if covariance is not None else "",
                "matched_drawdown_delta_yuan": matched_drawdown_delta if matched_drawdown_delta is not None else "",
                "matched_tail_loss_delta_yuan": matched_tail_loss_delta if matched_tail_loss_delta is not None else "",
                "capital_utilization_yuan": funded,
                "retained_cash_yuan": float(path_row["retained_cash_yuan"]),
                "rounding_delta_yuan": funded - float(path_row["weights"][sleeve_id]) * actual,
                "exposure_size_delta_yuan": funded - native_stake,
                "portfolio_pnl_reconciliation_yuan": portfolio_net - sleeve_net,
                "requested_native_stake_yuan": native_stake,
                "portfolio_requested_native_stake_yuan": requested,
                "undefined_reason": (
                    "INSUFFICIENT_PRIOR_52_COMMON_ACTIVE_FOR_EX_ANTE_COVARIANCE"
                    if covariance is None
                    else ""
                ),
            })
        history.append({sleeve: source_native_return(bridge[(sleeve, str(path_row["issue_instance"]))]) for sleeve in sleeves})
    return rows


def path_output_tables(
    path_rows: Sequence[dict[str, object]],
    bridge: dict[tuple[str, str], IssueSleeve],
    *,
    matched_control_rows: Sequence[dict[str, object]] | None = None,
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
        "risk_decomposition": risk_decomposition_rows(
            path_rows, bridge, matched_control_rows=matched_control_rows,
        ),
        "weight_history": weight_history,
        "stage_attribution": stage_attribution,
    }
