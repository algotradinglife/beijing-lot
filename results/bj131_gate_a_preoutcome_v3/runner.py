#!/usr/bin/env python3
"""Freeze #131's outcome-unexposed N7 soft-coverage sleeve matrix.

The only input is #127's accepted Gate-A v2 package.  It contains selector
identities and calibrated pre-outcome probabilities, but no results, final SP,
payout, tax, or ROI data.  The program freezes nested subsets of the 729-ticket
omitted-code slab without opening any outcome-bearing source.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import shutil
import tempfile
from collections import Counter
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


CODES = ("3", "1", "0")
CONTRACT = "BJ-HIST-SOFT-COVER-N7-001"
VERSION = "bj131-gatea-v3"
INPUT_MANIFEST = "a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da"
INPUT = "results/bj127_gate_a_preoutcome_v2"
OUTPUT = "results/bj131_gate_a_preoutcome_v3"
FULL_K, HARD_PRUNE_K, SLAB_K, UNIT_STAKE = 2187, 1458, 729, 2
SEEDS = (("PRIMARY", "131001"), ("SENS_A", "131017"), ("SENS_B", "131031"))
SLEEVE_FRACTIONS = (Decimal("0.00"), Decimal("0.05"), Decimal("0.10"), Decimal("0.20"),
                    Decimal("0.33"), Decimal("0.50"), Decimal("1.00"))

BASE = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder", "variant_id", "portfolio_id",
    "selected_match_ids", "deleted_match_id", "deleted_code", "deleted_probability",
    "descriptor_sha256",
)
ACTIVE_FIELDS = BASE + ("hard_prune_k", "hard_prune_stake_yuan", "full_k", "full_stake_yuan")
ORDER_FIELDS = (
    "variant_id", "portfolio_id", "seed_role", "seed", "ticket_order_scheme",
    "ticket_order_multiplier", "ticket_order_offset", "ticket_order_commitment",
)
NO_BET_FIELDS = BASE + ("reason",)
MATRIX_FIELDS = (
    "seed_role", "seed", "sleeve_label", "sleeve_fraction_nominal", "slab_tickets",
    "sleeve_tickets", "formula_k", "stake_yuan", "stake_retention_vs_full",
    "ticket_order_scheme", "expected_active_rows", "expected_no_bet_rows",
)
ROLE_FIELDS = (
    "variant_id", "portfolio_id", "issue", "fold", "year", "pool_id", "match_id", "match_idx",
    "selection_rank", "e_sp", "p_min", "p3", "p1", "p0", "is_deletion_candidate",
    "is_global_deleted_code_match", "global_deleted_code", "global_deleted_probability",
    "full_allowed_codes", "prune_allowed_codes",
)
FRONTIER_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder", "variant_id", "arm", "portfolio_id",
    "deletion_candidate_match_id", "deletion_candidate_p_min", "selected_match_ids", "selected_n",
    "gm_e_sp", "deleted_match_id", "deleted_code", "deleted_probability", "formula_k", "stake_yuan",
    "matched_full_k", "matched_full_stake_yuan", "stake_reduction_fraction", "disposition", "reason",
    "descriptor_sha256",
)
EXPECTED_ACTIVE, EXPECTED_NO_BET = 90_215, 23_931


def repo_root(path: Path) -> Path:
    for candidate in (path.resolve().parent, *path.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root(Path(__file__))
SOURCE = ROOT / INPUT
OUT = ROOT / OUTPUT


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fixed(value: Decimal) -> str:
    return format(value, ".12f")


def gzip_writer(path: Path, fields: tuple[str, ...]):
    raw = path.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    return raw, compressed, text, writer


def close_gzip(handles) -> None:
    raw, compressed, text, _ = handles
    text.flush()
    text.detach()
    compressed.close()
    raw.close()


def accepted_manifest() -> dict[str, str]:
    manifest = SOURCE / "SHA256SUMS.json"
    if sha256(manifest) != INPUT_MANIFEST:
        raise RuntimeError("#127 Gate-A v2 manifest is not the accepted input")
    declared = json.loads(manifest.read_text(encoding="utf-8"))
    actual = {path.name: sha256(path) for path in SOURCE.iterdir()
              if path.is_file() and path.name != "SHA256SUMS.json"}
    if declared != actual:
        raise RuntimeError("#127 Gate-A manifest coverage drift")
    return declared


def sleeve_tickets(fraction: Decimal) -> int:
    """Nearest integer slab ticket count, with exact endpoints and .5 upward."""
    if fraction == Decimal("0.00"):
        return 0
    if fraction == Decimal("1.00"):
        return SLAB_K
    return int((fraction * SLAB_K).to_integral_value(rounding=ROUND_HALF_UP))


def sleeve_label(fraction: Decimal) -> str:
    if fraction == Decimal("0.00"):
        return "S00_HARD_PRUNE"
    if fraction == Decimal("1.00"):
        return "S100_FULL"
    return f"S{int(fraction * 100):02d}_SOFT_COVER"


def arm(fraction: Decimal) -> str:
    if fraction == Decimal("0.00"):
        return "HARD_PRUNE_N7"
    if fraction == Decimal("1.00"):
        return "MATCHED_FULL_N7"
    return "SOFT_COVER_N7"


def role_groups():
    with gzip.open(SOURCE / "portfolio_role_assignments.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ROLE_FIELDS:
            raise RuntimeError("#127 role schema drift")
        current = None
        rows: list[dict[str, str]] = []
        for row in reader:
            key = (row["variant_id"], row["portfolio_id"])
            if current is not None and key != current:
                if len(rows) != 7:
                    raise RuntimeError("#127 role cardinality drift")
                yield current, rows
                rows = []
            current = key
            rows.append(row)
        if current is not None:
            if len(rows) != 7:
                raise RuntimeError("#127 terminal role cardinality drift")
            yield current, rows


def slab_permutation(portfolio_id: str, seed: str) -> tuple[int, int, str]:
    """A seed-specific bijection of the fixed 0..728 slab-ticket lexicographic index.

    ``rank=(multiplier*lex_index+offset) mod 729`` is a full permutation when
    the multiplier is coprime to 729. Prefixes are therefore nested,
    deterministic and outcome-unexposed without materialising 729 tickets for
    every frozen identity.
    """
    raw = int(hashlib.sha256(f"multiplier|{seed}|{portfolio_id}".encode()).hexdigest(), 16)
    multiplier = 1 + raw % (SLAB_K - 1)
    while math.gcd(multiplier, SLAB_K) != 1:
        multiplier = multiplier % (SLAB_K - 1) + 1
    offset = int(hashlib.sha256(f"offset|{seed}|{portfolio_id}".encode()).hexdigest(), 16) % SLAB_K
    commitment = identity({"scheme": "affine_rank_mod_729_v1", "seed": seed,
                           "portfolio_id": portfolio_id, "multiplier": multiplier, "offset": offset})
    return multiplier, offset, commitment


def source_rows():
    role_iter = role_groups()
    next_role = next(role_iter, None)
    active = no_bet = 0
    with gzip.open(SOURCE / "matched_frontier.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FRONTIER_FIELDS:
            raise RuntimeError("#127 frontier schema drift")
        for row in reader:
            if row["arm"] == "MATCHED_FULL_N7":
                key = (row["variant_id"], row["portfolio_id"])
                if next_role is None or next_role[0] != key:
                    raise RuntimeError("#127 frontier/role order drift")
                roles = next_role[1]
                next_role = next(role_iter, None)
                active += 1
                yield "ACTIVE", row, roles
            elif row["arm"] == "NO_BET_CONTROL":
                no_bet += 1
                yield "NO_BET", row, None
            elif row["arm"] != "PRUNE_ONE_GLOBAL_N7":
                raise RuntimeError(f"unknown #127 arm {row['arm']}")
    if next_role is not None or (active, no_bet) != (EXPECTED_ACTIVE, EXPECTED_NO_BET):
        raise RuntimeError("#127 frozen denominator drift")


def base_row(row: dict[str, str]) -> dict[str, str]:
    return {field: row.get(field, "") for field in BASE}


def build(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    accepted_manifest()
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj131_gatea_", dir=output.parent))
    try:
        active_handles = gzip_writer(stage / "portfolio_base.csv.gz", ACTIVE_FIELDS)
        order_handles = gzip_writer(stage / "portfolio_seed_order.csv.gz", ORDER_FIELDS)
        no_bet_handles = gzip_writer(stage / "no_bet_control.csv.gz", NO_BET_FIELDS)
        active_writer, order_writer, no_bet_writer = active_handles[-1], order_handles[-1], no_bet_handles[-1]
        active_rows = no_bet_rows = order_rows = 0
        for kind, source, roles in source_rows():
            if kind == "NO_BET":
                no_bet_writer.writerow({**base_row(source), "reason": source["reason"]})
                no_bet_rows += 1
                continue
            active_writer.writerow({**base_row(source), "hard_prune_k": str(HARD_PRUNE_K),
                                  "hard_prune_stake_yuan": str(HARD_PRUNE_K * UNIT_STAKE),
                                  "full_k": str(FULL_K), "full_stake_yuan": str(FULL_K * UNIT_STAKE)})
            active_rows += 1
            for seed_role, seed in SEEDS:
                multiplier, offset, commitment = slab_permutation(source["portfolio_id"], seed)
                order_writer.writerow({"variant_id": source["variant_id"], "portfolio_id": source["portfolio_id"],
                                       "seed_role": seed_role, "seed": seed,
                                       "ticket_order_scheme": "rank=(a*lex_index+b) mod 729; ascending-rank prefix",
                                       "ticket_order_multiplier": str(multiplier), "ticket_order_offset": str(offset),
                                       "ticket_order_commitment": commitment})
                order_rows += 1
        close_gzip(active_handles); close_gzip(order_handles); close_gzip(no_bet_handles)
        expected_active = EXPECTED_ACTIVE * len(SEEDS) * len(SLEEVE_FRACTIONS)
        expected_no_bet = EXPECTED_NO_BET * len(SEEDS) * len(SLEEVE_FRACTIONS)
        if (active_rows, no_bet_rows, order_rows) != (EXPECTED_ACTIVE, EXPECTED_NO_BET, EXPECTED_ACTIVE * len(SEEDS)):
            raise RuntimeError("#131 sleeve matrix cardinality drift")
        matrix = []
        for seed_role, seed in SEEDS:
            for fraction in SLEEVE_FRACTIONS:
                added = sleeve_tickets(fraction)
                k = HARD_PRUNE_K + added
                matrix.append({"seed_role": seed_role, "seed": seed, "sleeve_label": sleeve_label(fraction),
                               "sleeve_fraction_nominal": fixed(fraction), "slab_tickets": str(SLAB_K),
                               "sleeve_tickets": str(added), "formula_k": str(k),
                               "stake_yuan": fixed(Decimal(k * UNIT_STAKE)),
                               "stake_retention_vs_full": fixed(Decimal(k) / Decimal(FULL_K)),
                               "ticket_order_scheme": "rank=(a*lex_index+b) mod 729; ascending-rank prefix",
                               "expected_active_rows": str(EXPECTED_ACTIVE), "expected_no_bet_rows": str(EXPECTED_NO_BET)})
        with (stage / "sleeve_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=MATRIX_FIELDS, lineterminator="\n")
            writer.writeheader(); writer.writerows(matrix)
        card = {"issue": 131, "contract": CONTRACT, "version": VERSION,
                "stage": "GATE_A_OUTCOME_UNEXPOSED_SOFT_COVER_FREEZE",
                "source": {"package": INPUT, "manifest_sha256": INPUT_MANIFEST},
                "selection_boundary": "#127 selected seven matches, global omitted code, pool/window, and selector rows are copied without re-selection.",
                "sleeves": {"fractions_nominal": [str(value) for value in SLEEVE_FRACTIONS],
                            "ticket_rounding": "nearest integer of 729*s, .5 upward; endpoints exact",
                            "hard_prune_tickets": HARD_PRUNE_K, "omitted_code_slab_tickets": SLAB_K,
                            "full_tickets": FULL_K, "unit_stake_yuan": UNIT_STAKE},
                "seeds": [{"role": role, "seed": seed} for role, seed in SEEDS],
                "nested_order": "For each portfolio+seed, apply rank=(a*lex_index+b) mod 729 to the fixed omitted-code-slab lexicographic index, with coprime a and b derived from SHA256 seed/portfolio hashes; each sleeve is the ascending-rank prefix of this frozen permutation.",
                "normalization": "portfolio_base + portfolio_seed_order + sleeve_matrix + no_bet_control materialize the logical active/no-bet cross-product without repeating base metadata per sleeve.",
                "outcome_boundary": "This stage opens only #127 Gate-A v2 metadata/role inputs. It does not open results, final SP, payout, tax, ROI, #127 Gate-B, or any settlement output.",
                "denominator": {"source_active_identities": EXPECTED_ACTIVE, "source_no_bet_rows": EXPECTED_NO_BET,
                                "seed_count": len(SEEDS), "sleeve_count": len(SLEEVE_FRACTIONS),
                                "active_base_rows": active_rows, "no_bet_base_rows": no_bet_rows,
                                "portfolio_seed_order_rows": order_rows,
                                "logical_active_matrix_rows": expected_active, "logical_no_bet_matrix_rows": expected_no_bet}}
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "runner.py")
        (stage / "README.md").write_text(
            "# #131 Gate A\n\nOutcome-unexposed freeze of nested soft-coverage sleeves over #127's globally omitted-code slab. "
            "Run `python runner.py --output <new-dir>` from a compatible checkout. Verify portable content identity, not gzip bytes.\n",
            encoding="utf-8")
        def decompressed(path: Path) -> tuple[str, int]:
            digest, size = hashlib.sha256(), 0
            with gzip.open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block); size += len(block)
            return digest.hexdigest(), size
        gzip_content = {}
        for name in ("portfolio_base.csv.gz", "portfolio_seed_order.csv.gz", "no_bet_control.csv.gz"):
            digest, size = decompressed(stage / name)
            gzip_content[name] = {"canonical_decompressed_sha256": digest, "canonical_decompressed_bytes": size}
        content = {"contract_version": "bj131-portable-content-v1",
                   "gzip_payloads": gzip_content,
                   "non_compressed_controls": {path.name: sha256(path) for path in sorted(stage.iterdir())
                                               if path.is_file() and path.suffix != ".gz"}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sums = {path.name: sha256(path) for path in sorted(stage.iterdir()) if path.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha256(output / "SHA256SUMS.json"),
                "content_identity_sha256": sha256(output / "CONTENT_IDENTITY.json"),
                "active_rows": active_rows, "no_bet_rows": no_bet_rows}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    print(json.dumps(build(parser.parse_args().output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
