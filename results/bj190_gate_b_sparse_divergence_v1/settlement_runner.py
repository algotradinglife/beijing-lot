#!/usr/bin/env python3
"""Settle #190's immutable sparse-divergence N7 Gate-A surface.

The controlling outcome source is the exact SQLite file already SHA-bound by
Gate A.  The older #95 ledger is used only as an overlap consistency oracle.
Every seven-leg identity fails closed when any selected match lacks a trusted
result code or winning SP.  Such rows execute zero stake and are never losses.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
import random
import shutil
import sqlite3
import statistics
import subprocess
import tempfile
from array import array
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape


CONTRACT = "BJ-HIST-SPARSE-DIVERGENCE-N7-001"
VERSION = "bj190-gate-b-v1"
PACKAGE_NAME = "bj190_gate_b_sparse_divergence_v1"
ARMS = (
    "B0_BEST_FULL",
    "D_MATCH_ONLY_FULL",
    "D_DIRECTION_ONLY",
    "D_JOINT_SPARSE",
)
CODES = ("3", "1", "0")
STAKE_PER_TICKET = 2.0
PAYOUT_FACTOR = 0.65
TAX_RATE = 0.20
TAX_LINE_YUAN = 10_000.0
FULL_TICKETS = 2187
FULL_STAKE = 4374.0
BOOTSTRAP_DRAWS = 20_000
BOOTSTRAP_SEED = 190_001
MASTER_ISSUE_COUNT = 344

EXPECTED_GATE_A_MANIFEST = (
    "490579f7813d260d11965377462f7aa3b20161dd4672e2b42b600b493d24f1bc"
)
EXPECTED_GATE_A_CONTENT = (
    "f88a3dc7d010c69e5a1e50274f979f62e95cec47702f0aa842e30d7ffb024cb8"
)
EXPECTED_DATABASE_SHA256 = (
    "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"
)
EXPECTED_LEGACY_MANIFEST = (
    "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
)
EXPECTED_LEGACY_PAYLOAD = (
    "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
)
EXPECTED_LEDGER_ROWS = 101_970
EXPECTED_TRUSTED_ROWS = 100_906
EXPECTED_UNAVAILABLE_ROWS = 1_064
EXPECTED_IDENTITY_DISTRIBUTION = {3: 1, 4: 4, 5: 19, 6: 211, 7: 2_946}
EXPECTED_LEGACY_OVERLAP = 46_802
EXPECTED_MULTIPLICITY_VECTOR_COUNT = 3_563
EXPECTED_B0_LEGACY_SETTLED = 163
EXPECTED_B0_LEGACY_STAKE = 712_962.0
EXPECTED_B0_LEGACY_GROSS = 645_459.393809
EXPECTED_B0_LEGACY_ROI = -0.094679107990
EXPECTED_MASTER_DRAW_SHA256 = (
    "3945f56b6d8e059e93dbaae2e6de58fb3912760abaeeabf826690dc6550204d7"
)
FULL_VECTOR_SHA256 = "ea173936f013beddef4c63c889e3f5a1fd9a54fb55a5efa4543daa7630b62f2b"


def repo_root() -> Path:
    for candidate in (
        Path(__file__).resolve().parent,
        *Path(__file__).resolve().parents,
    ):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
GATE_A = ROOT / "results" / "bj190_gate_a_preoutcome_v3r1"
LEGACY_DIR = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
LEGACY_LEDGER = LEGACY_DIR / "canonical_outcome_join.csv"
DEFAULT_OUTPUT = ROOT / "results" / PACKAGE_NAME


def load_accepted_base():
    path = ROOT / "scripts" / "settle_bj179_hierarchical_league_gate_b.py"
    spec = importlib.util.spec_from_file_location("bj190_bj179_settlement_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load accepted settlement base: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = load_accepted_base()


def sha256_file(path: Path) -> str:
    return B.sha256_file(path)


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def fmt_money(value: float) -> str:
    return f"{value:.6f}"


def fmt_ratio(value: float | None) -> str:
    return "" if value is None or not math.isfinite(value) else f"{value:.12f}"


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def gzip_writer(path: Path, fields: Sequence[str]):
    raw = path.open("wb")
    zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
    writer = csv.DictWriter(
        text, fieldnames=fields, lineterminator="\n", extrasaction="raise"
    )
    writer.writeheader()
    return raw, zipped, text, writer


def write_csv(
    path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]
) -> None:
    B.write_csv(path, fields, rows)


def write_gzip(
    path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]
) -> None:
    B.write_gzip(path, fields, rows)


def verify_package(
    directory: Path, manifest_hash: str, content_hash: str | None = None
) -> dict[str, str]:
    manifest_path = directory / "SHA256SUMS.json"
    if sha256_file(manifest_path) != manifest_hash:
        raise RuntimeError(f"manifest drift: {directory.name}")
    content_path = directory / "CONTENT_IDENTITY.json"
    if content_hash and sha256_file(content_path) != content_hash:
        raise RuntimeError(f"content identity drift: {directory.name}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_files = set(manifest)
    # Gate A binds CONTENT_IDENTITY independently rather than listing it in
    # SHA256SUMS.  Preserve that accepted layout while rejecting every other
    # uncovered or absent file.
    if content_hash and "CONTENT_IDENTITY.json" not in expected_files:
        expected_files.add("CONTENT_IDENTITY.json")
    actual_files = {
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    if expected_files != actual_files:
        raise RuntimeError(f"manifest coverage drift: {directory.name}")
    for name, expected_hash in manifest.items():
        if sha256_file(directory / name) != expected_hash:
            raise RuntimeError(f"payload drift: {directory.name}/{name}")
    return manifest


def resolve_database(explicit: Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    if os.environ.get("BJ190_SOURCE_DATABASE"):
        candidates.append(Path(os.environ["BJ190_SOURCE_DATABASE"]).expanduser())
    relative = Path("data/derived/beidan_xlsm/beidan_xlsm.sqlite")
    candidates.extend(candidate / relative for candidate in (ROOT, *ROOT.parents))
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            if sha256_file(resolved) != EXPECTED_DATABASE_SHA256:
                raise RuntimeError(f"source database hash drift: {resolved}")
            return resolved
    raise RuntimeError("hash-bound #190 source database unavailable")


@dataclass(frozen=True)
class Outcome:
    match_id: str
    issue: str
    match_idx: str
    result_code: str
    winning_sp: float
    winning_sp_source: str
    settlement_quality: str


def build_canonical_outcome_ledger(
    database: Path,
    estimator_rows: Sequence[Mapping[str, str]],
    output: Path,
) -> tuple[dict[str, Outcome], dict[str, object]]:
    """Build the controlling ledger and fail closed against legacy overlap."""

    eligible = {str(row["match_id"]): row for row in estimator_rows}
    if len(eligible) != EXPECTED_LEDGER_ROWS:
        raise RuntimeError(f"Gate-A eligible denominator drift: {len(eligible)}")
    legacy_manifest = verify_package(LEGACY_DIR, EXPECTED_LEGACY_MANIFEST)
    if legacy_manifest.get(LEGACY_LEDGER.name) != EXPECTED_LEGACY_PAYLOAD:
        raise RuntimeError("legacy #95 canonical ledger payload drift")
    legacy = {row["match_id"]: row for row in read_csv(LEGACY_LEDGER)}

    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    by_match: dict[str, sqlite3.Row] = {}
    query = """
        SELECT match_id, issue, match_idx, result_code, winning_sp,
               winning_sp_source, settlement_quality, has_trusted_settlement
        FROM match_features
        ORDER BY match_id
    """
    try:
        for row in connection.execute(query):
            match_id = str(row["match_id"])
            if match_id not in eligible:
                continue
            if match_id in by_match:
                raise RuntimeError(f"duplicate match_features identity: {match_id}")
            by_match[match_id] = row
    finally:
        connection.close()
    if set(by_match) != set(eligible):
        missing = sorted(set(eligible) - set(by_match), key=int)
        raise RuntimeError(
            f"eligible matches absent from match_features: {missing[:10]}"
        )

    fields = (
        "match_id",
        "issue",
        "match_idx",
        "result_code",
        "winning_sp",
        "winning_sp_source",
        "settlement_quality",
        "has_trusted_settlement",
        "availability_status",
        "unavailable_reason",
        "legacy_overlap",
        "legacy_crosscheck_status",
        "source_database_sha256",
    )
    rows: list[dict[str, object]] = []
    outcomes: dict[str, Outcome] = {}
    quality_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    overlap_count = disagreement_count = 0
    for match_id in sorted(eligible, key=int):
        source = by_match[match_id]
        trusted = (
            str(source["has_trusted_settlement"]) == "1"
            and source["result_code"] not in (None, "")
            and source["winning_sp"] not in (None, "")
            and float(source["winning_sp"]) > 0
        )
        reason = ""
        if not trusted:
            if str(source["has_trusted_settlement"]) != "1":
                reason = f"UNTRUSTED_{source['settlement_quality'] or 'UNKNOWN'}"
            elif source["result_code"] in (None, ""):
                reason = "MISSING_RESULT_CODE"
            else:
                reason = "MISSING_OR_INVALID_WINNING_SP"
        old = legacy.get(match_id)
        crosscheck = "NOT_IN_LEGACY"
        if old is not None:
            overlap_count += 1
            same = (
                str(source["result_code"]) == old["result_code"]
                and source["winning_sp"] not in (None, "")
                and abs(float(source["winning_sp"]) - float(old["winning_sp"])) <= 1e-12
                and str(source["has_trusted_settlement"])
                == old["has_trusted_settlement"]
            )
            crosscheck = "PASS" if same else "FAIL"
            disagreement_count += not same
        row = {
            "match_id": match_id,
            "issue": str(source["issue"]),
            "match_idx": str(source["match_idx"]),
            "result_code": str(source["result_code"] or ""),
            "winning_sp": ""
            if source["winning_sp"] is None
            else f"{float(source['winning_sp']):.12f}",
            "winning_sp_source": str(source["winning_sp_source"] or ""),
            "settlement_quality": str(source["settlement_quality"] or ""),
            "has_trusted_settlement": int(trusted),
            "availability_status": "TRUSTED" if trusted else "UNAVAILABLE",
            "unavailable_reason": reason,
            "legacy_overlap": int(old is not None),
            "legacy_crosscheck_status": crosscheck,
            "source_database_sha256": EXPECTED_DATABASE_SHA256,
        }
        rows.append(row)
        quality_counts[str(source["settlement_quality"] or "NULL")] += 1
        source_counts[str(source["winning_sp_source"] or "NULL")] += 1
        if trusted:
            outcomes[match_id] = Outcome(
                match_id=match_id,
                issue=str(source["issue"]),
                match_idx=str(source["match_idx"]),
                result_code=str(source["result_code"]),
                winning_sp=float(source["winning_sp"]),
                winning_sp_source=str(source["winning_sp_source"]),
                settlement_quality=str(source["settlement_quality"]),
            )
    if len(rows) != EXPECTED_LEDGER_ROWS or len(outcomes) != EXPECTED_TRUSTED_ROWS:
        raise RuntimeError(
            f"canonical ledger census drift: rows={len(rows)} trusted={len(outcomes)}"
        )
    if len(rows) - len(outcomes) != EXPECTED_UNAVAILABLE_ROWS:
        raise RuntimeError("canonical unavailable denominator drift")
    if overlap_count != EXPECTED_LEGACY_OVERLAP or disagreement_count:
        raise RuntimeError(
            f"#95 overlap drift: overlap={overlap_count} disagreement={disagreement_count}"
        )
    write_gzip(output, fields, rows)
    return outcomes, {
        "eligible_match_count": len(rows),
        "trusted_match_count": len(outcomes),
        "unavailable_match_count": len(rows) - len(outcomes),
        "legacy_overlap_count": overlap_count,
        "legacy_disagreement_count": disagreement_count,
        "quality_counts": dict(sorted(quality_counts.items())),
        "winning_sp_source_counts": dict(sorted(source_counts.items())),
        "ledger_sha256": sha256_file(output),
    }


def result_ordinal(codes: Sequence[str]) -> int:
    if len(codes) != 7 or any(code not in CODES for code in codes):
        raise RuntimeError(f"invalid seven-leg result vector: {codes}")
    ordinal = 0
    for code in codes:
        ordinal = ordinal * 3 + CODES.index(code)
    return ordinal


@dataclass(frozen=True)
class IdentitySettlement:
    available_leg_count: int
    missing_match_ids: tuple[str, ...]
    winning_ordinal: int | None
    payout_per_winning_ticket: float


def prepare_identity_settlements(
    identities: Mapping[str, tuple[str, tuple[str, ...]]],
    outcomes: Mapping[str, Outcome],
) -> tuple[dict[str, IdentitySettlement], Counter[int]]:
    settlements: dict[str, IdentitySettlement] = {}
    distribution: Counter[int] = Counter()
    for identity, (issue, mids) in identities.items():
        present = [mid for mid in mids if mid in outcomes]
        distribution[len(present)] += 1
        missing = tuple(mid for mid in mids if mid not in outcomes)
        if missing:
            settlements[identity] = IdentitySettlement(
                available_leg_count=len(present),
                missing_match_ids=missing,
                winning_ordinal=None,
                payout_per_winning_ticket=0.0,
            )
            continue
        if any(outcomes[mid].issue != issue for mid in mids):
            raise RuntimeError(f"identity outcome issue mismatch: {identity}")
        codes = [outcomes[mid].result_code for mid in mids]
        payout = (
            STAKE_PER_TICKET
            * PAYOUT_FACTOR
            * math.prod(outcomes[mid].winning_sp for mid in mids)
        )
        settlements[identity] = IdentitySettlement(
            available_leg_count=7,
            missing_match_ids=(),
            winning_ordinal=result_ordinal(codes),
            payout_per_winning_ticket=payout,
        )
    if dict(sorted(distribution.items())) != EXPECTED_IDENTITY_DISTRIBUTION:
        raise RuntimeError(f"fully settled identity distribution drift: {distribution}")
    return settlements, distribution


def settle_ticket_vector(
    identity: IdentitySettlement,
    multiplicity_vector: bytes,
) -> dict[str, float | int]:
    if identity.winning_ordinal is None:
        return {
            "executed_ticket_count": 0,
            "stake_yuan": 0.0,
            "gross_pre_tax_yuan": 0.0,
            "tax_yuan": 0.0,
            "hit_ticket_count": 0,
        }
    if len(multiplicity_vector) != FULL_TICKETS:
        raise RuntimeError("ticket multiplicity-vector length drift")
    executed = sum(multiplicity_vector)
    if executed != FULL_TICKETS:
        raise RuntimeError(f"executed ticket denominator drift: {executed}")
    multiplicity = multiplicity_vector[identity.winning_ordinal]
    gross = multiplicity * identity.payout_per_winning_ticket
    tax_per_ticket = (
        identity.payout_per_winning_ticket * TAX_RATE
        if identity.payout_per_winning_ticket >= TAX_LINE_YUAN
        else 0.0
    )
    return {
        "executed_ticket_count": executed,
        "stake_yuan": executed * STAKE_PER_TICKET,
        "gross_pre_tax_yuan": gross,
        "tax_yuan": multiplicity * tax_per_ticket,
        "hit_ticket_count": multiplicity,
    }


def load_gate_a() -> dict[str, object]:
    manifest = verify_package(GATE_A, EXPECTED_GATE_A_MANIFEST, EXPECTED_GATE_A_CONTENT)
    grid = read_csv(GATE_A / "detector_grid.csv")
    if len(grid) != 2_424 or len({row["policy_id"] for row in grid}) != len(grid):
        raise RuntimeError("detector-grid denominator drift")
    issues = read_csv(GATE_A / "issue_census.csv")
    issues.sort(
        key=lambda row: (int(row["year"]), int(row["issue"]), row["issue_instance"])
    )
    if len(issues) != MASTER_ISSUE_COUNT:
        raise RuntimeError("canonical issue denominator drift")
    estimators = read_gzip(GATE_A / "estimator_match_freeze.csv.gz")
    if len(estimators) != EXPECTED_LEDGER_ROWS:
        raise RuntimeError("estimator-match denominator drift")
    identities: dict[str, tuple[str, tuple[str, ...]]] = {}
    for row in read_gzip(GATE_A / "n7_identity_catalog.csv.gz"):
        mids = tuple(str(value) for value in json.loads(row["ordered_match_ids_json"]))
        if len(mids) != 7:
            raise RuntimeError("N7 identity width drift")
        identities[row["identity_sha256"]] = (row["issue"], mids)
    if len(identities) != 3_181:
        raise RuntimeError("N7 identity denominator drift")
    vectors: dict[str, bytes] = {FULL_VECTOR_SHA256: bytes([1]) * FULL_TICKETS}
    if hashlib.sha256(vectors[FULL_VECTOR_SHA256]).hexdigest() != FULL_VECTOR_SHA256:
        raise RuntimeError("FULL multiplicity-vector identity drift")
    for row in read_gzip(GATE_A / "ticket_multiplicity_vector_catalog.csv.gz"):
        vector = bytes.fromhex(row["multiplicity_vector_hex"])
        if hashlib.sha256(vector).hexdigest() != row["multiplicity_vector_sha256"]:
            raise RuntimeError("directional multiplicity-vector hash drift")
        if len(vector) != FULL_TICKETS or sum(vector) != FULL_TICKETS:
            raise RuntimeError("directional multiplicity-vector accounting drift")
        vectors[row["multiplicity_vector_sha256"]] = vector
    # The catalog's 3,563 rows already include the FULL all-ones vector.
    if len(vectors) != EXPECTED_MULTIPLICITY_VECTOR_COUNT:
        raise RuntimeError(f"multiplicity-vector denominator drift: {len(vectors)}")
    return {
        "manifest": manifest,
        "grid": grid,
        "grid_by_policy": {row["policy_id"]: row for row in grid},
        "issues": issues,
        "issue_by_id": {row["issue"]: row for row in issues},
        "estimators": estimators,
        "estimator_by_match": {row["match_id"]: row for row in estimators},
        "identities": identities,
        "vectors": vectors,
    }


def code_features(delta: Mapping[str, float]) -> dict[str, object]:
    favored = min(CODES, key=lambda code: (-delta[code], CODES.index(code)))
    omitted = min(CODES, key=lambda code: (delta[code], CODES.index(code)))
    extreme = min(CODES, key=lambda code: (-abs(delta[code]), CODES.index(code)))
    return {
        "favored_code": favored,
        "omitted_code": omitted,
        "extreme_code": extreme,
        "magnitude": abs(delta[extreme]),
    }


def selected_probability_view(
    row: Mapping[str, str], policy: Mapping[str, str]
) -> tuple[str, tuple[float, float, float], str, str, float] | None:
    """Reconstruct the exact frozen per-match estimator/source decision."""

    fundamental_delta = {
        code: float(row[f"fundamental_delta_p{code}"]) for code in CODES
    }
    calibrated_delta = {code: float(row[f"calibrated_delta_p{code}"]) for code in CODES}
    fundamental_features = code_features(fundamental_delta)
    calibrated_features = code_features(calibrated_delta)
    fundamental = (
        "FUNDAMENTAL_T1_SCORE_DISTRIBUTION",
        tuple(float(row[f"fundamental_p{code}"]) for code in CODES),
        str(fundamental_features["favored_code"]),
        str(fundamental_features["omitted_code"]),
        float(fundamental_features["magnitude"]),
    )
    calibrated = (
        "CALIBRATED_MARKET_ESTIMATOR",
        tuple(float(row[f"calibrated_p{code}"]) for code in CODES),
        str(calibrated_features["favored_code"]),
        str(calibrated_features["omitted_code"]),
        float(calibrated_features["magnitude"]),
    )
    if policy["detector_family"] == "LINE_RESIDUAL_MU":
        value = float(row["line_residual_mu"])
        return (
            fundamental[0],
            fundamental[1],
            "3" if value > 0 else "0",
            "0" if value > 0 else "3",
            abs(value),
        )
    if policy["detector_family"] != "DELTA_P":
        return None
    variant = policy["estimator_variant"]
    if variant == "FUNDAMENTAL_INDEPENDENT":
        return fundamental
    if variant == "CALIBRATED_MARKET_ESTIMATOR":
        return calibrated
    if variant == "UNION":
        return min(
            (fundamental, calibrated),
            key=lambda item: (-item[4], 0 if item[0].startswith("FUNDAMENTAL") else 1),
        )
    if variant == "MODEL_AGREEMENT":
        if fundamental[2:4] != calibrated[2:4]:
            return None
        weaker = min(
            (fundamental, calibrated),
            key=lambda item: (item[4], 0 if item[0].startswith("FUNDAMENTAL") else 1),
        )
        return (
            f"STRICT_AGREEMENT_WEAKER::{weaker[0]}",
            weaker[1],
            weaker[2],
            weaker[3],
            min(fundamental[4], calibrated[4]),
        )
    raise RuntimeError(f"unknown estimator variant: {variant}")


def probability_loss(
    probabilities: Sequence[float], truth: str
) -> tuple[float, float, float, int]:
    if truth not in CODES or len(probabilities) != 3:
        raise RuntimeError("invalid probability settlement row")
    index = CODES.index(truth)
    p = max(1e-15, min(1.0, float(probabilities[index])))
    log_loss = -math.log(p)
    brier = sum(
        (float(value) - (1.0 if i == index else 0.0)) ** 2
        for i, value in enumerate(probabilities)
    )
    confidence = max(float(value) for value in probabilities)
    predicted = max(range(3), key=lambda i: (float(probabilities[i]), -i))
    return log_loss, brier, confidence, int(predicted == index)


class ProbabilityAccumulator:
    def __init__(self) -> None:
        self.count = 0
        self.log_loss = 0.0
        self.brier = 0.0
        self.bins = [[0, 0.0, 0] for _ in range(10)]

    def add(self, probabilities: Sequence[float], truth: str) -> None:
        log_loss, brier, confidence, correct = probability_loss(probabilities, truth)
        self.count += 1
        self.log_loss += log_loss
        self.brier += brier
        index = min(9, int(confidence * 10))
        self.bins[index][0] += 1
        self.bins[index][1] += confidence
        self.bins[index][2] += correct

    def metrics(self) -> dict[str, object]:
        ece = 0.0
        if self.count:
            for count, confidence, correct in self.bins:
                if count:
                    ece += (
                        count / self.count * abs(confidence / count - correct / count)
                    )
        return {
            "settled_match_count": self.count,
            "multiclass_log_loss": fmt_ratio(
                self.log_loss / self.count if self.count else None
            ),
            "multiclass_brier": fmt_ratio(
                self.brier / self.count if self.count else None
            ),
            "confidence_ece": fmt_ratio(ece if self.count else None),
        }


def totals(rows: Sequence[Mapping[str, object]]) -> dict[str, float]:
    fields = (
        "planned_ticket_count",
        "executed_ticket_count",
        "planned_stake_yuan",
        "stake_yuan",
        "gross_pre_tax_yuan",
        "tax_yuan",
        "pre_tax_net_yuan",
        "tax_adjusted_net_yuan",
        "hit_ticket_count",
    )
    return {field: math.fsum(float(row[field]) for row in rows) for field in fields}


def quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise RuntimeError("quantile on empty sample")
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def build_master_draws(draws: int = BOOTSTRAP_DRAWS) -> tuple[array, str]:
    rng = random.Random(BOOTSTRAP_SEED)
    values = array("Q")
    digest = hashlib.sha256()
    for _ in range(draws):
        row = [rng.getrandbits(64) for _ in range(MASTER_ISSUE_COUNT)]
        values.extend(row)
        digest.update(canonical_json(row))
        digest.update(b"\n")
    return values, digest.hexdigest()


def bootstrap_pair(
    policy_id: str,
    arm: str,
    candidate: Sequence[Mapping[str, object]],
    baseline: Sequence[Mapping[str, object]],
    master_draws: array,
    draws: int,
) -> dict[str, object]:
    if len(candidate) != len(baseline):
        raise RuntimeError("paired bootstrap denominator mismatch")
    n = len(candidate)
    if not n:
        return {
            "policy_id": policy_id,
            "arm": arm,
            "common_issue_count": 0,
            "draw_count": draws,
            "candidate_roi_mean": "",
            "candidate_roi_ci_low": "",
            "candidate_roi_ci_high": "",
            "lift_mean": "",
            "lift_ci_low": "",
            "lift_ci_high": "",
            "probability_lift_positive": "",
            "monte_carlo_se_lift": "",
        }
    candidate_net = [float(row["pre_tax_net_yuan"]) for row in candidate]
    baseline_net = [float(row["pre_tax_net_yuan"]) for row in baseline]
    stake = n * FULL_STAKE
    candidate_values: list[float] = []
    lift_values: list[float] = []
    for draw in range(draws):
        offset = draw * MASTER_ISSUE_COUNT
        csum = bsum = 0.0
        for position in range(n):
            index = (master_draws[offset + position] * n) >> 64
            csum += candidate_net[index]
            bsum += baseline_net[index]
        candidate_values.append(csum / stake)
        lift_values.append((csum - bsum) / stake)
    return {
        "policy_id": policy_id,
        "arm": arm,
        "common_issue_count": n,
        "draw_count": draws,
        "candidate_roi_mean": fmt_ratio(statistics.fmean(candidate_values)),
        "candidate_roi_ci_low": fmt_ratio(quantile(candidate_values, 0.025)),
        "candidate_roi_ci_high": fmt_ratio(quantile(candidate_values, 0.975)),
        "lift_mean": fmt_ratio(statistics.fmean(lift_values)),
        "lift_ci_low": fmt_ratio(quantile(lift_values, 0.025)),
        "lift_ci_high": fmt_ratio(quantile(lift_values, 0.975)),
        "probability_lift_positive": fmt_ratio(
            sum(value > 0 for value in lift_values) / draws
        ),
        "monte_carlo_se_lift": fmt_ratio(
            statistics.pstdev(lift_values) / math.sqrt(draws)
        ),
    }


SETTLEMENT_FIELDS = (
    "policy_id",
    "issue",
    "year",
    "fold",
    "issue_instance",
    "first_kickoff_ts",
    "arm",
    "gate_a_policy_status",
    "settlement_status",
    "n7_identity_sha256",
    "multiplicity_vector_sha256",
    "ticket_identity_sha256",
    "available_leg_count",
    "missing_match_ids",
    "planned_ticket_count",
    "executed_ticket_count",
    "planned_stake_yuan",
    "stake_yuan",
    "gross_pre_tax_yuan",
    "tax_yuan",
    "pre_tax_net_yuan",
    "tax_adjusted_net_yuan",
    "hit_ticket_count",
    "winning_ticket_multiplicity",
    "winning_ticket_payout_yuan",
)


def settle_ledger_row(
    source: Mapping[str, str],
    arm: str,
    issue_by_id: Mapping[str, Mapping[str, str]],
    identity_settlements: Mapping[str, IdentitySettlement],
    vectors: Mapping[str, bytes],
    economics_cache: dict[tuple[str, str], tuple[dict[str, float | int], int, float]],
) -> dict[str, object]:
    if source["arm"] != arm:
        raise RuntimeError(f"arm ledger mismatch: {source['arm']} != {arm}")
    issue = source["issue"]
    census = issue_by_id[issue]
    identity_hash = source["n7_identity_sha256"]
    vector_hash = source["multiplicity_vector_sha256"]
    gate_status = source["policy_status"]
    planned_tickets = int(source["executed_ticket_count"] or 0)
    planned_stake = float(source["planned_stake_yuan"] or 0)
    if bool(identity_hash) != bool(vector_hash):
        raise RuntimeError("identity/vector nullability mismatch")
    if identity_hash:
        if identity_hash not in identity_settlements or vector_hash not in vectors:
            raise RuntimeError("ticket ledger references unknown frozen identity")
        identity = identity_settlements[identity_hash]
        cache_key = (identity_hash, vector_hash)
        if cache_key not in economics_cache:
            vector = vectors[vector_hash]
            economics = settle_ticket_vector(identity, vector)
            winning_multiplicity = (
                vector[identity.winning_ordinal]
                if identity.winning_ordinal is not None
                else 0
            )
            winning_payout = (
                identity.payout_per_winning_ticket if winning_multiplicity else 0.0
            )
            economics_cache[cache_key] = (
                economics,
                winning_multiplicity,
                winning_payout,
            )
        economics, winning_multiplicity, winning_payout = economics_cache[cache_key]
        if identity.winning_ordinal is None:
            status = "UNAVAILABLE_CANONICAL_OUTCOME"
        else:
            status = "SETTLED"
        available_legs = identity.available_leg_count
        missing = "|".join(identity.missing_match_ids)
    else:
        status = (
            "DIAGNOSTIC_UNAVAILABLE"
            if gate_status == "DIAGNOSTIC_UNAVAILABLE"
            else "NO_BET"
        )
        available_legs = 0
        missing = ""
        winning_multiplicity = 0
        winning_payout = 0.0
        economics = {
            "executed_ticket_count": 0,
            "stake_yuan": 0.0,
            "gross_pre_tax_yuan": 0.0,
            "tax_yuan": 0.0,
            "hit_ticket_count": 0,
        }
    stake = float(economics["stake_yuan"])
    gross = float(economics["gross_pre_tax_yuan"])
    tax = float(economics["tax_yuan"])
    if status == "SETTLED":
        if planned_tickets != FULL_TICKETS or abs(planned_stake - FULL_STAKE) > 1e-9:
            raise RuntimeError("settled Gate-A accounting drift")
    elif stake or gross or tax:
        raise RuntimeError("unavailable/no-bet row executed economics")
    return {
        "policy_id": source["policy_id"],
        "issue": issue,
        "year": source["year"],
        "fold": source["fold"],
        "issue_instance": source["issue_instance"],
        "first_kickoff_ts": census["feature_cutoff_ts"],
        "arm": arm,
        "gate_a_policy_status": gate_status,
        "settlement_status": status,
        "n7_identity_sha256": identity_hash,
        "multiplicity_vector_sha256": vector_hash,
        "ticket_identity_sha256": source["ticket_identity_sha256"],
        "available_leg_count": available_legs,
        "missing_match_ids": missing,
        "planned_ticket_count": planned_tickets,
        "executed_ticket_count": int(economics["executed_ticket_count"]),
        "planned_stake_yuan": fmt_money(planned_stake),
        "stake_yuan": fmt_money(stake),
        "gross_pre_tax_yuan": fmt_money(gross),
        "tax_yuan": fmt_money(tax),
        "pre_tax_net_yuan": fmt_money(gross - stake),
        "tax_adjusted_net_yuan": fmt_money(gross - tax - stake),
        "hit_ticket_count": int(economics["hit_ticket_count"]),
        "winning_ticket_multiplicity": winning_multiplicity,
        "winning_ticket_payout_yuan": fmt_money(winning_payout),
    }


def native_summary(
    policy_id: str, arm: str, records: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    settled = [row for row in records if row["settlement_status"] == "SETTLED"]
    aggregate = totals(settled)
    selected = [row for row in records if row["n7_identity_sha256"]]
    unavailable = [
        row
        for row in records
        if row["settlement_status"] == "UNAVAILABLE_CANONICAL_OUTCOME"
    ]
    no_bet = [row for row in records if row["settlement_status"] == "NO_BET"]
    diagnostic = [
        row for row in records if row["settlement_status"] == "DIAGNOSTIC_UNAVAILABLE"
    ]
    return {
        "policy_id": policy_id,
        "arm": arm,
        "canonical_issue_count": len(records),
        "selected_issue_count": len(selected),
        "settled_issue_count": len(settled),
        "unavailable_issue_count": len(unavailable),
        "no_bet_issue_count": len(no_bet),
        "diagnostic_unavailable_issue_count": len(diagnostic),
        "planned_ticket_count": int(
            sum(float(row["planned_ticket_count"]) for row in records)
        ),
        "executed_ticket_count": int(aggregate["executed_ticket_count"]),
        "planned_stake_yuan": fmt_money(
            sum(float(row["planned_stake_yuan"]) for row in records)
        ),
        "stake_yuan": fmt_money(aggregate["stake_yuan"]),
        "gross_pre_tax_yuan": fmt_money(aggregate["gross_pre_tax_yuan"]),
        "tax_yuan": fmt_money(aggregate["tax_yuan"]),
        "net_pre_tax_yuan": fmt_money(aggregate["pre_tax_net_yuan"]),
        "net_tax_adjusted_yuan": fmt_money(aggregate["tax_adjusted_net_yuan"]),
        "pre_tax_roi": fmt_ratio(
            safe_ratio(aggregate["pre_tax_net_yuan"], aggregate["stake_yuan"])
        ),
        "tax_adjusted_roi": fmt_ratio(
            safe_ratio(aggregate["tax_adjusted_net_yuan"], aggregate["stake_yuan"])
        ),
        "hit_issue_count": sum(int(row["hit_ticket_count"]) > 0 for row in settled),
        "hit_ticket_count": int(aggregate["hit_ticket_count"]),
        "hit_issue_rate": fmt_ratio(
            safe_ratio(
                sum(int(row["hit_ticket_count"]) > 0 for row in settled), len(settled)
            )
        ),
    }


def pairwise_summary(
    policy_id: str,
    arm: str,
    candidate: Sequence[Mapping[str, object]],
    baseline: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], list[Mapping[str, object]], list[Mapping[str, object]]]:
    base_by_issue = {str(row["issue"]): row for row in baseline}
    pairs = [
        (row, base_by_issue[str(row["issue"])])
        for row in candidate
        if row["settlement_status"] == "SETTLED"
        and base_by_issue[str(row["issue"])]["settlement_status"] == "SETTLED"
    ]
    candidate_common = [pair[0] for pair in pairs]
    baseline_common = [pair[1] for pair in pairs]
    candidate_totals = totals(candidate_common)
    baseline_totals = totals(baseline_common)
    candidate_roi = safe_ratio(
        candidate_totals["pre_tax_net_yuan"], candidate_totals["stake_yuan"]
    )
    baseline_roi = safe_ratio(
        baseline_totals["pre_tax_net_yuan"], baseline_totals["stake_yuan"]
    )
    return (
        {
            "policy_id": policy_id,
            "arm": arm,
            "common_issue_count": len(pairs),
            "equal_budget_stake_yuan": fmt_money(candidate_totals["stake_yuan"]),
            "candidate_gross_yuan": fmt_money(candidate_totals["gross_pre_tax_yuan"]),
            "matched_b0_gross_yuan": fmt_money(baseline_totals["gross_pre_tax_yuan"]),
            "candidate_pre_tax_roi": fmt_ratio(candidate_roi),
            "matched_b0_pre_tax_roi": fmt_ratio(baseline_roi),
            "candidate_minus_b0_lift": fmt_ratio(
                None
                if candidate_roi is None or baseline_roi is None
                else candidate_roi - baseline_roi
            ),
            "candidate_tax_adjusted_roi": fmt_ratio(
                safe_ratio(
                    candidate_totals["tax_adjusted_net_yuan"],
                    candidate_totals["stake_yuan"],
                )
            ),
            "matched_b0_tax_adjusted_roi": fmt_ratio(
                safe_ratio(
                    baseline_totals["tax_adjusted_net_yuan"],
                    baseline_totals["stake_yuan"],
                )
            ),
        },
        candidate_common,
        baseline_common,
    )


def factorial_summary(
    policy_id: str,
    records: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str, object]:
    by_arm = {arm: {str(row["issue"]): row for row in records[arm]} for arm in ARMS}
    common = [
        issue
        for issue in by_arm[ARMS[0]]
        if all(by_arm[arm][issue]["settlement_status"] == "SETTLED" for arm in ARMS)
    ]
    aggregates = {arm: totals([by_arm[arm][issue] for issue in common]) for arm in ARMS}
    rois = {
        arm: safe_ratio(value["pre_tax_net_yuan"], value["stake_yuan"])
        for arm, value in aggregates.items()
    }
    b0, match, direction, joint = (rois[arm] for arm in ARMS)
    valid = all(value is not None for value in (b0, match, direction, joint))
    return {
        "policy_id": policy_id,
        "four_way_common_issue_count": len(common),
        "equal_budget_stake_yuan_each": fmt_money(aggregates[ARMS[0]]["stake_yuan"]),
        "b0_pre_tax_roi": fmt_ratio(b0),
        "match_only_pre_tax_roi": fmt_ratio(match),
        "direction_only_pre_tax_roi": fmt_ratio(direction),
        "joint_sparse_pre_tax_roi": fmt_ratio(joint),
        "match_selection_lift": fmt_ratio(match - b0 if valid else None),
        "direction_lift": fmt_ratio(direction - b0 if valid else None),
        "joint_total_lift": fmt_ratio(joint - b0 if valid else None),
        "joint_interaction": fmt_ratio(
            joint - match - direction + b0 if valid else None
        ),
    }


def stability_rows(
    policy_id: str, arm: str, records: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    settled = [row for row in records if row["settlement_status"] == "SETTLED"]
    for dimension, field in (("YEAR", "year"), ("FOLD", "fold")):
        for value in sorted({str(row[field]) for row in records}):
            subset = [row for row in settled if str(row[field]) == value]
            aggregate = totals(subset)
            output.append(
                {
                    "policy_id": policy_id,
                    "arm": arm,
                    "view": dimension,
                    "included_value": value,
                    "excluded_value": "",
                    "settled_issue_count": len(subset),
                    "stake_yuan": fmt_money(aggregate["stake_yuan"]),
                    "pre_tax_roi": fmt_ratio(
                        safe_ratio(
                            aggregate["pre_tax_net_yuan"], aggregate["stake_yuan"]
                        )
                    ),
                    "tax_adjusted_roi": fmt_ratio(
                        safe_ratio(
                            aggregate["tax_adjusted_net_yuan"], aggregate["stake_yuan"]
                        )
                    ),
                }
            )
    for year in sorted({str(row["year"]) for row in records}):
        subset = [row for row in settled if str(row["year"]) != year]
        aggregate = totals(subset)
        output.append(
            {
                "policy_id": policy_id,
                "arm": arm,
                "view": "LOYO",
                "included_value": "",
                "excluded_value": year,
                "settled_issue_count": len(subset),
                "stake_yuan": fmt_money(aggregate["stake_yuan"]),
                "pre_tax_roi": fmt_ratio(
                    safe_ratio(aggregate["pre_tax_net_yuan"], aggregate["stake_yuan"])
                ),
                "tax_adjusted_roi": fmt_ratio(
                    safe_ratio(
                        aggregate["tax_adjusted_net_yuan"], aggregate["stake_yuan"]
                    )
                ),
            }
        )
    return output


def risk_rows(
    policy_id: str, arm: str, records: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    compatible = [
        {
            **row,
            "policy_status": "SETTLED"
            if row["settlement_status"] == "SETTLED"
            else row["settlement_status"],
        }
        for row in records
    ]
    output = []
    for basis in ("PRE_TAX", "TAX_ADJUSTED"):
        result = B.risk_row(compatible, basis, "ALL", arm)
        output.append({"policy_id": policy_id, **result})
    return output


DIVERGENCE_BUCKETS = (
    ("B000_025", 0.0, 0.025),
    ("B025_050", 0.025, 0.050),
    ("B050_075", 0.050, 0.075),
    ("B075_100", 0.075, 0.100),
    ("B100_150", 0.100, 0.150),
    ("B150_PLUS", 0.150, math.inf),
)


def divergence_bucket(value: float) -> str:
    for label, low, high in DIVERGENCE_BUCKETS:
        if low <= value < high:
            return label
    raise RuntimeError(f"invalid divergence magnitude: {value}")


def write_probability_settlement(
    stage: Path,
    estimator_rows: Sequence[Mapping[str, str]],
    outcomes: Mapping[str, Outcome],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    population = {
        source: ProbabilityAccumulator()
        for source in (
            "HANDICAP_CONSENSUS",
            "FUNDAMENTAL_INDEPENDENT",
            "CALIBRATED_MARKET_ESTIMATOR",
        )
    }
    bucket_accumulators: dict[tuple[str, str], ProbabilityAccumulator] = defaultdict(
        ProbabilityAccumulator
    )
    bucket_favored_probability: Counter[tuple[str, str]] = Counter()
    bucket_favored_hits: Counter[tuple[str, str]] = Counter()
    bucket_magnitude: Counter[tuple[str, str]] = Counter()
    fields = (
        "match_id",
        "issue",
        "year",
        "fold",
        "league",
        "line_stratum",
        "outcome_status",
        "result_code",
        "winning_sp",
        "consensus_log_loss",
        "consensus_brier",
        "fundamental_log_loss",
        "fundamental_brier",
        "calibrated_log_loss",
        "calibrated_brier",
        "fundamental_divergence_bucket",
        "calibrated_divergence_bucket",
    )

    def rows() -> Iterable[dict[str, object]]:
        for source in estimator_rows:
            outcome = outcomes.get(source["match_id"])
            output: dict[str, object] = {
                "match_id": source["match_id"],
                "issue": source["issue"],
                "year": source["year"],
                "fold": source["fold"],
                "league": source["league"],
                "line_stratum": source["line_stratum"],
                "outcome_status": "SETTLED"
                if outcome
                else "UNAVAILABLE_CANONICAL_OUTCOME",
                "result_code": outcome.result_code if outcome else "",
                "winning_sp": f"{outcome.winning_sp:.12f}" if outcome else "",
                "consensus_log_loss": "",
                "consensus_brier": "",
                "fundamental_log_loss": "",
                "fundamental_brier": "",
                "calibrated_log_loss": "",
                "calibrated_brier": "",
                "fundamental_divergence_bucket": "",
                "calibrated_divergence_bucket": "",
            }
            views = {
                "HANDICAP_CONSENSUS": tuple(
                    float(source[f"consensus_p{code}"]) for code in CODES
                ),
                "FUNDAMENTAL_INDEPENDENT": tuple(
                    float(source[f"fundamental_p{code}"]) for code in CODES
                ),
                "CALIBRATED_MARKET_ESTIMATOR": tuple(
                    float(source[f"calibrated_p{code}"]) for code in CODES
                ),
            }
            if outcome:
                for name, probabilities in views.items():
                    log_loss, brier, _, _ = probability_loss(
                        probabilities, outcome.result_code
                    )
                    population[name].add(probabilities, outcome.result_code)
                    prefix = {
                        "HANDICAP_CONSENSUS": "consensus",
                        "FUNDAMENTAL_INDEPENDENT": "fundamental",
                        "CALIBRATED_MARKET_ESTIMATOR": "calibrated",
                    }[name]
                    output[f"{prefix}_log_loss"] = fmt_ratio(log_loss)
                    output[f"{prefix}_brier"] = fmt_ratio(brier)
                for source_name, prefix in (
                    ("FUNDAMENTAL_INDEPENDENT", "fundamental"),
                    ("CALIBRATED_MARKET_ESTIMATOR", "calibrated"),
                ):
                    delta = {
                        code: float(source[f"{prefix}_delta_p{code}"]) for code in CODES
                    }
                    features = code_features(delta)
                    bucket = divergence_bucket(float(features["magnitude"]))
                    output[f"{prefix}_divergence_bucket"] = bucket
                    key = (source_name, bucket)
                    probabilities = views[source_name]
                    bucket_accumulators[key].add(probabilities, outcome.result_code)
                    favored = str(features["favored_code"])
                    bucket_favored_probability[key] += probabilities[
                        CODES.index(favored)
                    ]
                    bucket_favored_hits[key] += outcome.result_code == favored
                    bucket_magnitude[key] += float(features["magnitude"])
            yield output

    write_gzip(stage / "probability_match_settlement.csv.gz", fields, rows())
    population_rows = [
        {
            "region": "FULL_ELIGIBLE_SETTLED",
            "probability_source": source,
            **acc.metrics(),
        }
        for source, acc in population.items()
    ]
    bucket_rows: list[dict[str, object]] = []
    for source in ("FUNDAMENTAL_INDEPENDENT", "CALIBRATED_MARKET_ESTIMATOR"):
        for bucket, _, _ in DIVERGENCE_BUCKETS:
            key = (source, bucket)
            acc = bucket_accumulators[key]
            count = acc.count
            bucket_rows.append(
                {
                    "probability_source": source,
                    "divergence_bucket": bucket,
                    **acc.metrics(),
                    "mean_abs_delta": fmt_ratio(
                        bucket_magnitude[key] / count if count else None
                    ),
                    "mean_favored_probability": fmt_ratio(
                        bucket_favored_probability[key] / count if count else None
                    ),
                    "observed_favored_rate": fmt_ratio(
                        bucket_favored_hits[key] / count if count else None
                    ),
                }
            )
    return population_rows, bucket_rows


def candidate_coverage(
    policy: Mapping[str, str],
    arm: str,
    match_records: Sequence[Mapping[str, object]],
    identities: Mapping[str, tuple[str, tuple[str, ...]]],
    estimator_by_match: Mapping[str, Mapping[str, str]],
) -> list[dict[str, object]]:
    coverage: Counter[tuple[str, str]] = Counter()
    selected = [row for row in match_records if row["n7_identity_sha256"]]
    for record in selected:
        coverage[("ISSUE_YEAR", str(record["year"]))] += 1
        identity = str(record["n7_identity_sha256"])
        for match_id in identities[identity][1]:
            estimator = estimator_by_match[match_id]
            coverage[("MATCH_YEAR", estimator["year"])] += 1
            coverage[("LEAGUE", estimator["league"])] += 1
            coverage[("LINE_STRATUM", estimator["line_stratum"])] += 1
            view = selected_probability_view(estimator, policy)
            if view is None:
                continue
            source, _, favored, omitted, _ = view
            coverage[("FAVORED_CODE", favored)] += 1
            coverage[("OMITTED_CODE", omitted)] += 1
            coverage[("PROBABILITY_SOURCE", source)] += 1
    return [
        {
            "policy_id": policy["policy_id"],
            "arm": arm,
            "dimension": dimension,
            "value": value,
            "selected_count": count,
        }
        for (dimension, value), count in sorted(coverage.items())
    ]


def candidate_diagnostics(
    policy: Mapping[str, str],
    arm: str,
    match_records: Sequence[Mapping[str, object]],
    identities: Mapping[str, tuple[str, tuple[str, ...]]],
    estimator_by_match: Mapping[str, Mapping[str, str]],
    outcomes: Mapping[str, Outcome],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    rows = candidate_coverage(
        policy, arm, match_records, identities, estimator_by_match
    )
    selected = [row for row in match_records if row["n7_identity_sha256"]]
    accumulator = ProbabilityAccumulator()
    missing_outcomes = selected_legs = 0
    for record in selected:
        identity = str(record["n7_identity_sha256"])
        for match_id in identities[identity][1]:
            selected_legs += 1
            estimator = estimator_by_match[match_id]
            view = selected_probability_view(estimator, policy)
            if view is None:
                raise RuntimeError(
                    f"selected match has no frozen estimator view: {policy['policy_id']} {match_id}"
                )
            _, probabilities, _, _, _ = view
            outcome = outcomes.get(match_id)
            if outcome:
                accumulator.add(probabilities, outcome.result_code)
            else:
                missing_outcomes += 1
    return rows, {
        "policy_id": policy["policy_id"],
        "arm": arm,
        "estimator_variant": policy["estimator_variant"],
        "detector_family": policy["detector_family"],
        "selected_issue_count": len(selected),
        "selected_leg_occurrence_count": selected_legs,
        "missing_outcome_leg_occurrence_count": missing_outcomes,
        **accumulator.metrics(),
    }


def legacy_baseline_bridge(
    b0_records: Sequence[Mapping[str, object]],
    identities: Mapping[str, tuple[str, tuple[str, ...]]],
) -> list[dict[str, object]]:
    legacy_ids = {row["match_id"] for row in read_csv(LEGACY_LEDGER)}
    legacy = [
        row
        for row in b0_records
        if row["n7_identity_sha256"]
        and all(
            mid in legacy_ids for mid in identities[str(row["n7_identity_sha256"])][1]
        )
        and row["settlement_status"] == "SETTLED"
    ]
    legacy_totals = totals(legacy)
    legacy_roi = safe_ratio(
        legacy_totals["pre_tax_net_yuan"], legacy_totals["stake_yuan"]
    )
    if (
        len(legacy) != EXPECTED_B0_LEGACY_SETTLED
        or abs(legacy_totals["stake_yuan"] - EXPECTED_B0_LEGACY_STAKE) > 5e-7
        or abs(legacy_totals["gross_pre_tax_yuan"] - EXPECTED_B0_LEGACY_GROSS) > 5e-6
        or legacy_roi is None
        or abs(legacy_roi - EXPECTED_B0_LEGACY_ROI) > 1e-10
    ):
        raise RuntimeError(
            "accepted -9.47% B0 legacy bridge drift: "
            f"n={len(legacy)} stake={legacy_totals['stake_yuan']} "
            f"gross={legacy_totals['gross_pre_tax_yuan']} roi={legacy_roi}"
        )
    expanded = [row for row in b0_records if row["settlement_status"] == "SETTLED"]
    expanded_totals = totals(expanded)
    return [
        {
            "support": "ACCEPTED_LEGACY_95_OVERLAP",
            "settled_issue_count": len(legacy),
            "stake_yuan": fmt_money(legacy_totals["stake_yuan"]),
            "gross_yuan": fmt_money(legacy_totals["gross_pre_tax_yuan"]),
            "pre_tax_roi": fmt_ratio(legacy_roi),
            "expected_pre_tax_roi": fmt_ratio(EXPECTED_B0_LEGACY_ROI),
            "reconciliation_status": "PASS",
            "interpretation": "accepted baseline ladder bridge; remains authoritative and is not demoted",
        },
        {
            "support": "EXPANDED_HASH_BOUND_SQLITE",
            "settled_issue_count": len(expanded),
            "stake_yuan": fmt_money(expanded_totals["stake_yuan"]),
            "gross_yuan": fmt_money(expanded_totals["gross_pre_tax_yuan"]),
            "pre_tax_roi": fmt_ratio(
                safe_ratio(
                    expanded_totals["pre_tax_net_yuan"], expanded_totals["stake_yuan"]
                )
            ),
            "expected_pre_tax_roi": "",
            "reconciliation_status": "DESCRIPTIVE_NEW_SUPPORT",
            "interpretation": "#190 expanded settlement support; does not replace the accepted ladder",
        },
    ]


def settle_surface(
    stage: Path,
    gate: Mapping[str, object],
    identity_settlements: Mapping[str, IdentitySettlement],
    outcomes: Mapping[str, Outcome],
) -> dict[str, object]:
    grid = gate["grid"]
    grid_by_policy = gate["grid_by_policy"]
    issues = gate["issues"]
    issue_by_id = gate["issue_by_id"]
    identities = gate["identities"]
    vectors = gate["vectors"]
    estimator_by_match = gate["estimator_by_match"]
    assert isinstance(grid, list)
    assert isinstance(grid_by_policy, dict)
    assert isinstance(issues, list)
    assert isinstance(issue_by_id, dict)
    assert isinstance(identities, dict)
    assert isinstance(vectors, dict)
    assert isinstance(estimator_by_match, dict)

    input_paths = {
        "B0_BEST_FULL": GATE_A / "ticket_arm_b0_best_full.csv.gz",
        "D_MATCH_ONLY_FULL": GATE_A / "ticket_arm_d_match_only_full.csv.gz",
        "D_DIRECTION_ONLY": GATE_A / "ticket_arm_d_direction_only.csv.gz",
        "D_JOINT_SPARSE": GATE_A / "ticket_arm_d_joint_sparse.csv.gz",
    }
    output_paths = {
        arm: stage / f"issue_arm_settlement_{arm.lower()}.csv.gz" for arm in ARMS
    }
    native: list[dict[str, object]] = []
    pairwise: list[dict[str, object]] = []
    factorial: list[dict[str, object]] = []
    stability: list[dict[str, object]] = []
    risk: list[dict[str, object]] = []
    coverage: list[dict[str, object]] = []
    selected_probability: list[dict[str, object]] = []
    bootstrap_targets: list[dict[str, object]] = []
    bridge: list[dict[str, object]] = []
    economics_cache: dict[
        tuple[str, str], tuple[dict[str, float | int], int, float]
    ] = {}
    reference_b0_signature: tuple[tuple[object, ...], ...] | None = None
    expected_policy_order = [str(row["policy_id"]) for row in grid]
    observed_policy_order: list[str] = []

    def finalize_policy(
        policy_id: str,
        records: Mapping[str, Sequence[Mapping[str, object]]],
    ) -> None:
        nonlocal reference_b0_signature
        if any(len(records[arm]) != MASTER_ISSUE_COUNT for arm in ARMS):
            raise RuntimeError(f"policy issue width drift: {policy_id}")
        expected_issues = [str(row["issue"]) for row in issues]
        for arm in ARMS:
            if [str(row["issue"]) for row in records[arm]] != expected_issues:
                raise RuntimeError(f"policy issue order drift: {policy_id}/{arm}")
        policy = grid_by_policy[policy_id]
        for arm in ARMS:
            native.append(native_summary(policy_id, arm, records[arm]))
            stability.extend(stability_rows(policy_id, arm, records[arm]))
            risk.extend(risk_rows(policy_id, arm, records[arm]))
        for arm in ARMS[1:]:
            summary, candidate_common, baseline_common = pairwise_summary(
                policy_id, arm, records[arm], records["B0_BEST_FULL"]
            )
            pairwise.append(summary)
            bootstrap_targets.append(
                {
                    "policy_id": policy_id,
                    "arm": arm,
                    "candidate_net": [
                        float(row["pre_tax_net_yuan"]) for row in candidate_common
                    ],
                    "baseline_net": [
                        float(row["pre_tax_net_yuan"]) for row in baseline_common
                    ],
                    "candidate_tax_net": [
                        float(row["tax_adjusted_net_yuan"]) for row in candidate_common
                    ],
                    "baseline_tax_net": [
                        float(row["tax_adjusted_net_yuan"]) for row in baseline_common
                    ],
                    "issues": [str(row["issue"]) for row in candidate_common],
                }
            )
        factorial.append(factorial_summary(policy_id, records))
        for arm in ARMS:
            policy_coverage = candidate_coverage(
                policy,
                arm,
                records[arm],
                identities,
                estimator_by_match,
            )
            coverage.extend(policy_coverage)
        _, probability = candidate_diagnostics(
            policy,
            "D_MATCH_ONLY_FULL",
            records["D_MATCH_ONLY_FULL"],
            identities,
            estimator_by_match,
            outcomes,
        )
        selected_probability.append(probability)

        signature = tuple(
            (
                row["issue"],
                row["settlement_status"],
                row["n7_identity_sha256"],
                row["stake_yuan"],
                row["gross_pre_tax_yuan"],
                row["tax_yuan"],
            )
            for row in records["B0_BEST_FULL"]
        )
        if reference_b0_signature is None:
            reference_b0_signature = signature
            bridge.extend(legacy_baseline_bridge(records["B0_BEST_FULL"], identities))
        elif signature != reference_b0_signature:
            raise RuntimeError(f"B0 must be invariant across policy grid: {policy_id}")

    with ExitStack() as stack:
        readers = []
        writers: dict[str, csv.DictWriter] = {}
        for arm in ARMS:
            handle = stack.enter_context(
                gzip.open(input_paths[arm], "rt", newline="", encoding="utf-8")
            )
            readers.append(csv.DictReader(handle))
            raw, zipped, text, writer = gzip_writer(
                output_paths[arm], SETTLEMENT_FIELDS
            )
            del raw, zipped
            stack.callback(text.close)
            writers[arm] = writer

        current_policy = ""
        current_records: dict[str, list[dict[str, object]]] = {arm: [] for arm in ARMS}
        row_count = 0
        for source_rows in zip(*readers, strict=True):
            keys = {
                (
                    row["policy_id"],
                    row["issue"],
                    row["year"],
                    row["fold"],
                    row["issue_instance"],
                )
                for row in source_rows
            }
            if len(keys) != 1:
                raise RuntimeError(f"four-arm ledger key mismatch: {keys}")
            policy_id = source_rows[0]["policy_id"]
            if current_policy and policy_id != current_policy:
                finalize_policy(current_policy, current_records)
                observed_policy_order.append(current_policy)
                current_records = {arm: [] for arm in ARMS}
            current_policy = policy_id
            for arm, source in zip(ARMS, source_rows, strict=True):
                settled = settle_ledger_row(
                    source,
                    arm,
                    issue_by_id,
                    identity_settlements,
                    vectors,
                    economics_cache,
                )
                writers[arm].writerow(settled)
                current_records[arm].append(settled)
            row_count += 1
        if current_policy:
            finalize_policy(current_policy, current_records)
            observed_policy_order.append(current_policy)
    if observed_policy_order != expected_policy_order:
        raise RuntimeError("policy order/surface drift")
    if row_count != len(grid) * MASTER_ISSUE_COUNT:
        raise RuntimeError(f"four-arm ledger row denominator drift: {row_count}")
    return {
        "native": native,
        "pairwise": pairwise,
        "factorial": factorial,
        "stability": stability,
        "risk": risk,
        "coverage": coverage,
        "selected_probability": selected_probability,
        "bootstrap_targets": bootstrap_targets,
        "baseline_bridge": bridge,
        "row_count_each_arm": row_count,
        "economics_cache_count": len(economics_cache),
    }


def run_bootstrap_engine(
    stage: Path,
    targets: Sequence[Mapping[str, object]],
    *,
    draws: int = BOOTSTRAP_DRAWS,
    threads: int = 16,
) -> dict[str, object]:
    # Keep the canonical surface exact while allowing bounded tests to execute
    # this same production path with a small draw/target fixture.
    if draws == BOOTSTRAP_DRAWS and len(targets) != 2_424 * 3:
        raise RuntimeError(f"bootstrap target surface drift: {len(targets)}")
    master, draw_hash = build_master_draws(draws)
    if draws == BOOTSTRAP_DRAWS and draw_hash != EXPECTED_MASTER_DRAW_SHA256:
        raise RuntimeError(f"master bootstrap draw identity drift: {draw_hash}")
    target_path = stage / ".bootstrap_targets.tsv"
    draw_path = stage / ".bootstrap_draws.u64"
    binary_path = stage / ".bj190_bootstrap_exact"
    output_path = stage / "bootstrap_paired_lift_20000.csv"
    registry_rows: list[dict[str, object]] = []
    contribution_fields = (
        "policy_id",
        "arm",
        "common_issue_index",
        "issue",
        "candidate_pre_tax_net_yuan",
        "matched_b0_pre_tax_net_yuan",
        "candidate_tax_adjusted_net_yuan",
        "matched_b0_tax_adjusted_net_yuan",
    )
    contribution_count = 0
    raw, zipped, text, contribution_writer = gzip_writer(
        stage / "bootstrap_target_issue_contributions.csv.gz", contribution_fields
    )
    del raw, zipped
    with target_path.open("w", encoding="utf-8", newline="") as handle, text:
        for target in targets:
            n = len(target["candidate_net"])
            vectors = (
                target["candidate_net"],
                target["baseline_net"],
                target["candidate_tax_net"],
                target["baseline_tax_net"],
            )
            if (
                any(len(vector) != n for vector in vectors)
                or len(target["issues"]) != n
            ):
                raise RuntimeError("bootstrap target contribution width drift")
            vector_hash = canonical_hash(
                {
                    "issues": target["issues"],
                    "candidate_net": target["candidate_net"],
                    "baseline_net": target["baseline_net"],
                    "candidate_tax_net": target["candidate_tax_net"],
                    "baseline_tax_net": target["baseline_tax_net"],
                }
            )
            registry_rows.append(
                {
                    "policy_id": target["policy_id"],
                    "arm": target["arm"],
                    "common_issue_count": n,
                    "common_issue_sha256": canonical_hash(target["issues"]),
                    "contribution_vector_sha256": vector_hash,
                }
            )
            for index, issue in enumerate(target["issues"]):
                contribution_writer.writerow(
                    {
                        "policy_id": target["policy_id"],
                        "arm": target["arm"],
                        "common_issue_index": index,
                        "issue": issue,
                        "candidate_pre_tax_net_yuan": fmt_money(
                            target["candidate_net"][index]
                        ),
                        "matched_b0_pre_tax_net_yuan": fmt_money(
                            target["baseline_net"][index]
                        ),
                        "candidate_tax_adjusted_net_yuan": fmt_money(
                            target["candidate_tax_net"][index]
                        ),
                        "matched_b0_tax_adjusted_net_yuan": fmt_money(
                            target["baseline_tax_net"][index]
                        ),
                    }
                )
                contribution_count += 1
            handle.write(
                "\t".join(
                    [
                        str(target["policy_id"]),
                        str(target["arm"]),
                        str(n),
                        ",".join(
                            repr(float(value)) for value in target["candidate_net"]
                        ),
                        ",".join(
                            repr(float(value)) for value in target["baseline_net"]
                        ),
                        ",".join(
                            repr(float(value)) for value in target["candidate_tax_net"]
                        ),
                        ",".join(
                            repr(float(value)) for value in target["baseline_tax_net"]
                        ),
                    ]
                )
                + "\n"
            )
    with draw_path.open("wb") as handle:
        master.tofile(handle)
    source = ROOT / "scripts" / "bj190_bootstrap_exact.cpp"
    compile_result = subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-O3",
            "-fopenmp",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(source),
            "-o",
            str(binary_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if compile_result.returncode:
        raise RuntimeError(f"bootstrap engine compile failed: {compile_result.stderr}")
    environment = dict(os.environ)
    environment["OMP_NUM_THREADS"] = str(max(1, threads))
    run = subprocess.run(
        [
            str(binary_path),
            str(target_path),
            str(draw_path),
            str(output_path),
            str(draws),
            str(MASTER_ISSUE_COUNT),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if run.returncode:
        raise RuntimeError(f"bootstrap engine failed: {run.stderr}")
    bootstrap_rows = read_csv(output_path)
    if len(bootstrap_rows) != len(targets):
        raise RuntimeError("bootstrap output denominator drift")

    nonempty = next((target for target in targets if target["candidate_net"]), None)
    if nonempty is not None:
        candidate = [
            {
                "pre_tax_net_yuan": value,
                "tax_adjusted_net_yuan": tax,
            }
            for value, tax in zip(
                nonempty["candidate_net"], nonempty["candidate_tax_net"], strict=True
            )
        ]
        baseline = [
            {
                "pre_tax_net_yuan": value,
                "tax_adjusted_net_yuan": tax,
            }
            for value, tax in zip(
                nonempty["baseline_net"], nonempty["baseline_tax_net"], strict=True
            )
        ]
        oracle = bootstrap_pair(
            str(nonempty["policy_id"]),
            str(nonempty["arm"]),
            candidate,
            baseline,
            master,
            draws,
        )
        actual = next(
            row
            for row in bootstrap_rows
            if row["policy_id"] == nonempty["policy_id"]
            and row["arm"] == nonempty["arm"]
        )
        for field in (
            "candidate_roi_mean",
            "candidate_roi_ci_low",
            "candidate_roi_ci_high",
            "lift_mean",
            "lift_ci_low",
            "lift_ci_high",
            "probability_lift_positive",
            "monte_carlo_se_lift",
        ):
            if abs(float(actual[field]) - float(oracle[field])) > 1e-11:
                raise RuntimeError(f"native/Python bootstrap parity drift: {field}")

    write_gzip(
        stage / "bootstrap_target_registry.csv.gz",
        tuple(registry_rows[0]),
        registry_rows,
    )
    shutil.copy2(source, stage / "bootstrap_engine.cpp")
    (stage / "bootstrap_draw_contract.json").write_text(
        json.dumps(
            {
                "draw_count": draws,
                "seed": BOOTSTRAP_SEED,
                "rng": "Python random.Random MT19937",
                "master_issue_count": MASTER_ISSUE_COUNT,
                "master_draw_matrix_sha256": draw_hash,
                "mapping": "for support n, first n uint64 values map by floor(u*n/2^64)",
                "target_count": len(targets),
                "parallel_threads": max(1, threads),
                "native_engine_sha256": sha256_file(source),
                "python_native_parity": "PASS",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    for temporary in (target_path, draw_path, binary_path):
        temporary.unlink()
    return {
        "draw_count": draws,
        "draw_matrix_sha256": draw_hash,
        "target_count": len(targets),
        "nonempty_target_count": sum(
            bool(target["candidate_net"]) for target in targets
        ),
        "contribution_row_count": contribution_count,
        "engine_sha256": sha256_file(source),
    }


def join_frontier(
    gate: Mapping[str, object],
    surface: Mapping[str, object],
    bootstrap_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, object]]:
    grid_by_policy = gate["grid_by_policy"]
    assert isinstance(grid_by_policy, dict)
    pair_map = {
        (str(row["policy_id"]), str(row["arm"])): row for row in surface["pairwise"]
    }
    bootstrap_map = {(row["policy_id"], row["arm"]): row for row in bootstrap_rows}
    output: list[dict[str, object]] = []
    descriptor_fields = (
        "detector_family",
        "estimator_variant",
        "threshold_rule",
        "abs_delta_p_min",
        "abs_z_min",
        "top_k",
        "min_history_n",
        "coverage_gate",
        "uncertainty_gate",
        "abs_delta_mu_min",
        "abs_line_residual_mu_min",
        "availability",
        "unavailable_reason",
    )
    for native in surface["native"]:
        policy_id = str(native["policy_id"])
        arm = str(native["arm"])
        policy = grid_by_policy[policy_id]
        pair = pair_map.get((policy_id, arm), {})
        bootstrap = bootstrap_map.get((policy_id, arm), {})
        row = {
            "policy_id": policy_id,
            **{field: policy[field] for field in descriptor_fields},
            "arm": arm,
            **{
                key: value
                for key, value in native.items()
                if key not in {"policy_id", "arm"}
            },
            "common_issue_count": pair.get("common_issue_count", ""),
            "equal_budget_stake_yuan": pair.get("equal_budget_stake_yuan", ""),
            "candidate_pre_tax_roi_common": pair.get("candidate_pre_tax_roi", ""),
            "matched_b0_pre_tax_roi": pair.get("matched_b0_pre_tax_roi", ""),
            "candidate_minus_b0_lift": pair.get("candidate_minus_b0_lift", ""),
            "bootstrap_lift_ci_low": bootstrap.get("lift_ci_low", ""),
            "bootstrap_lift_ci_high": bootstrap.get("lift_ci_high", ""),
            "bootstrap_probability_lift_positive": bootstrap.get(
                "probability_lift_positive", ""
            ),
        }
        output.append(row)
    return output


def failure_attribution_rows(
    frontier: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for row in frontier:
        selected = int(row["selected_issue_count"])
        settled = int(row["settled_issue_count"])
        unavailable = int(row["unavailable_issue_count"])
        no_bet = int(row["no_bet_issue_count"])
        diagnostic = int(row["diagnostic_unavailable_issue_count"])
        if diagnostic:
            dominant = "DETECTOR_SEMANTIC_UNAVAILABLE"
        elif not selected:
            dominant = "SPARSE_GATE_ZERO_CANDIDATE"
        elif unavailable:
            dominant = "OUTCOME_SUPPORT_INCOMPLETE"
        elif row["pre_tax_roi"] == "":
            dominant = "ZERO_EXECUTED_STAKE"
        elif float(row["pre_tax_roi"]) < 0:
            dominant = "NEGATIVE_REALIZED_ECONOMICS"
        else:
            dominant = "POSITIVE_SCREEN_REQUIRES_STABILITY_AND_EV"
        output.append(
            {
                "policy_id": row["policy_id"],
                "arm": row["arm"],
                "selected_issue_count": selected,
                "settled_issue_count": settled,
                "unavailable_issue_count": unavailable,
                "no_bet_issue_count": no_bet,
                "diagnostic_unavailable_issue_count": diagnostic,
                "dominant_failure_or_disposition": dominant,
                "market_mapping_limitation": "DELTA_MU_UNAVAILABLE"
                if row["detector_family"] == "DELTA_MU"
                else "NONE",
                "price_availability_limitation": unavailable,
                "portfolio_construction": "FULL"
                if row["arm"] in {"B0_BEST_FULL", "D_MATCH_ONLY_FULL"}
                else "ONE_CODE_DELETE_PLUS_729_REPEATS",
            }
        )
    return output


def candidate_freeze(
    frontier: Sequence[Mapping[str, object]],
    risk_rows_: Sequence[Mapping[str, object]],
    stability: Sequence[Mapping[str, object]],
    coverage: Sequence[Mapping[str, object]],
    bootstrap_rows: Sequence[Mapping[str, str]],
) -> dict[str, object]:
    risk_map = {
        (str(row["policy_id"]), str(row["arm"])): row
        for row in risk_rows_
        if row["basis"] == "PRE_TAX"
    }
    bootstrap_map = {(row["policy_id"], row["arm"]): row for row in bootstrap_rows}
    years_positive: Counter[tuple[str, str]] = Counter()
    for row in stability:
        if (
            row["view"] == "YEAR"
            and row["pre_tax_roi"] not in ("", None)
            and float(row["pre_tax_roi"]) > 0
        ):
            years_positive[(str(row["policy_id"]), str(row["arm"]))] += 1
    strata: defaultdict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in coverage:
        if (
            row["dimension"] in {"LEAGUE", "LINE_STRATUM"}
            and int(row["selected_count"]) > 0
        ):
            strata[
                (
                    str(row["policy_id"]),
                    str(row["arm"]),
                    str(row["dimension"]),
                )
            ].add(str(row["value"]))
    positives: list[dict[str, object]] = []
    promotable: list[dict[str, object]] = []
    for row in frontier:
        if (
            row["arm"] == "B0_BEST_FULL"
            or row["pre_tax_roi"] in ("", None)
            or row["candidate_minus_b0_lift"] in ("", None)
        ):
            continue
        if float(row["pre_tax_roi"]) <= 0 or float(row["candidate_minus_b0_lift"]) <= 0:
            continue
        key = (str(row["policy_id"]), str(row["arm"]))
        risk = risk_map[key]
        bootstrap = bootstrap_map[key]
        record = {
            "policy_id": row["policy_id"],
            "arm": row["arm"],
            "detector_family": row["detector_family"],
            "estimator_variant": row["estimator_variant"],
            "threshold_rule": row["threshold_rule"],
            "top_k": row["top_k"],
            "selected_issue_count": row["selected_issue_count"],
            "settled_issue_count": row["settled_issue_count"],
            "common_issue_count": row["common_issue_count"],
            "native_pre_tax_roi": row["pre_tax_roi"],
            "matched_b0_lift": row["candidate_minus_b0_lift"],
            "bootstrap_lift_ci_low": bootstrap["lift_ci_low"],
            "bootstrap_lift_ci_high": bootstrap["lift_ci_high"],
            "ex_largest_issue_roi": risk["ex_largest_issue_roi"],
            "ex_largest_year_roi": risk["ex_largest_year_roi"],
            "positive_year_count": years_positive[key],
            "league_count": len(
                strata[(str(row["policy_id"]), str(row["arm"]), "LEAGUE")]
            ),
            "line_stratum_count": len(
                strata[(str(row["policy_id"]), str(row["arm"]), "LINE_STRATUM")]
            ),
            "exact_surface_identity": canonical_hash(
                {
                    "gate_a_manifest": EXPECTED_GATE_A_MANIFEST,
                    "policy_id": row["policy_id"],
                    "arm": row["arm"],
                }
            ),
            "strict_independent_ev_status": "REQUIRED_BEFORE_ANY_PROMOTION",
        }
        positives.append(record)
        robust = (
            bootstrap["lift_ci_low"] not in ("", None)
            and float(bootstrap["lift_ci_low"]) > 0
            and risk["ex_largest_issue_roi"] not in ("", None)
            and float(risk["ex_largest_issue_roi"]) > 0
            and risk["ex_largest_year_roi"] not in ("", None)
            and float(risk["ex_largest_year_roi"]) > 0
            and years_positive[key] >= 2
            and record["league_count"] >= 2
            and record["line_stratum_count"] >= 2
        )
        if robust:
            promotable.append(record)
    return {
        "screen_rule": "absolute pre-tax ROI > 0 and pairwise-common matched-B0 lift > 0",
        "strict_stability_rule": (
            "performance: paired bootstrap lift low > 0, ex-largest issue/year ROI > 0, "
            "positive-year count >=2; coverage: candidate-arm own covered league count >=2 "
            "and line-stratum count >=2"
        ),
        "positive_screen_count": len(positives),
        "strict_stability_candidate_count": len(promotable),
        "positive_screen_rows": positives,
        "strict_stability_rows": promotable,
        "promotion_authority": False,
        "strict_independent_ev_required": bool(positives),
    }


def svg_scatter(
    path: Path,
    title: str,
    rows: Sequence[Mapping[str, object]],
    x_field: str,
    y_field: str,
) -> None:
    points = [
        (float(row[x_field]), float(row[y_field]), str(row["arm"]))
        for row in rows
        if row[x_field] not in ("", None) and row[y_field] not in ("", None)
    ]
    width, height = 1200, 720
    left, right, top, bottom = 95, 40, 70, 90
    if not points:
        points = [(0.0, 0.0, "NONE")]
    xmin, xmax = min(x for x, _, _ in points), max(x for x, _, _ in points)
    ymin, ymax = (
        min(min(y for _, y, _ in points), 0),
        max(max(y for _, y, _ in points), 0),
    )
    xspan, yspan = xmax - xmin or 1.0, ymax - ymin or 1.0
    colors = {
        "B0_BEST_FULL": "#111827",
        "D_MATCH_ONLY_FULL": "#2563eb",
        "D_DIRECTION_ONLY": "#d97706",
        "D_JOINT_SPARSE": "#059669",
        "NONE": "#6b7280",
    }

    def xp(value: float) -> float:
        return left + (width - left - right) * (value - xmin) / xspan

    def yp(value: float) -> float:
        return top + (height - top - bottom) * (ymax - value) / yspan

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="35" font-size="22" font-family="sans-serif">{escape(title)}</text>',
        f'<line x1="{left}" y1="{yp(0):.2f}" x2="{width - right}" y2="{yp(0):.2f}" stroke="#9ca3af"/>',
    ]
    for x, y, arm in points:
        parts.append(
            f'<circle cx="{xp(x):.2f}" cy="{yp(y):.2f}" r="2.2" fill="{colors.get(arm, "#6b7280")}" fill-opacity="0.55"/>'
        )
    parts.append(
        f'<text x="{width / 2}" y="{height - 20}" text-anchor="middle" font-size="14">{escape(x_field)}</text>'
    )
    parts.append(
        f'<text x="20" y="{height / 2}" transform="rotate(-90 20 {height / 2})" text-anchor="middle" font-size="14">{escape(y_field)}</text>'
    )
    parts.append("</svg>\n")
    path.write_text("\n".join(parts), encoding="utf-8")


def svg_heatmap(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    thresholds = list(dict.fromkeys(str(row["threshold_rule"]) for row in rows))
    topks = ("1", "2", "4", "ALL")
    values = {
        (str(row["threshold_rule"]), str(row["top_k"])): float(row["pre_tax_roi"])
        for row in rows
        if row["pre_tax_roi"] not in ("", None)
    }
    width, height = 1100, 430
    left, top, cell_w, cell_h = 150, 75, 72, 64
    low = min(values.values(), default=-1.0)
    high = max(values.values(), default=1.0)
    scale = max(abs(low), abs(high), 1e-12)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<text x="40" y="35" font-size="21">#190 fixed-slice threshold × Top-K pre-tax ROI</text>',
    ]
    for x, threshold in enumerate(thresholds):
        parts.append(
            f'<text x="{left + x * cell_w + cell_w / 2:.1f}" y="{top - 10}" text-anchor="middle" font-size="10" transform="rotate(-45 {left + x * cell_w + cell_w / 2:.1f} {top - 10})">{escape(threshold)}</text>'
        )
        for y, topk in enumerate(topks):
            value = values.get((threshold, topk))
            if value is None:
                color = "#e5e7eb"
                label = "NA"
            elif value >= 0:
                intensity = int(220 - 150 * min(value / scale, 1))
                color = f"rgb({intensity},235,{intensity})"
                label = f"{value:+.1%}"
            else:
                intensity = int(235 - 150 * min(-value / scale, 1))
                color = f"rgb(235,{intensity},{intensity})"
                label = f"{value:+.1%}"
            parts.extend(
                [
                    f'<rect x="{left + x * cell_w}" y="{top + y * cell_h}" width="{cell_w - 2}" height="{cell_h - 2}" fill="{color}"/>',
                    f'<text x="{left + x * cell_w + cell_w / 2:.1f}" y="{top + y * cell_h + cell_h / 2:.1f}" text-anchor="middle" font-size="11">{label}</text>',
                ]
            )
    for y, topk in enumerate(topks):
        parts.append(
            f'<text x="{left - 15}" y="{top + y * cell_h + cell_h / 2:.1f}" text-anchor="end" font-size="13">K={topk}</text>'
        )
    parts.append("</svg>\n")
    path.write_text("\n".join(parts), encoding="utf-8")


def report_markdown(
    ledger: Mapping[str, object],
    identity_distribution: Mapping[int, int],
    bridge: Sequence[Mapping[str, object]],
    population: Sequence[Mapping[str, object]],
    frontier: Sequence[Mapping[str, object]],
    freeze: Mapping[str, object],
) -> str:
    arm_stats = []
    for arm in ARMS:
        rows = [row for row in frontier if row["arm"] == arm]
        roi_rows = [
            float(row["pre_tax_roi"])
            for row in rows
            if row["pre_tax_roi"] not in ("", None)
        ]
        lift_rows = [
            float(row["candidate_minus_b0_lift"])
            for row in rows
            if row["candidate_minus_b0_lift"] not in ("", None)
        ]
        arm_stats.append(
            (
                arm,
                len(rows),
                len(roi_rows),
                statistics.median(roi_rows) if roi_rows else None,
                sum(value > 0 for value in roi_rows),
                sum(value > 0 for value in lift_rows),
            )
        )
    positive = sorted(
        freeze["positive_screen_rows"],
        key=lambda row: (
            -float(row["native_pre_tax_roi"]),
            str(row["policy_id"]),
            str(row["arm"]),
        ),
    )
    lines = [
        "# #190 Gate B — sparse independent-model divergence for N7",
        "",
        "## Executive decision",
        "",
        (
            "The complete preregistered 2,424-policy × four-arm surface was settled once. "
            f"There are **{freeze['positive_screen_count']}** positive absolute-ROI plus matched-B0-lift screen rows and "
            f"**{freeze['strict_stability_candidate_count']}** rows passing both the stricter performance screen "
            "(bootstrap, ex-largest and positive-year checks) and candidate-arm-own coverage screen "
            "(at least two leagues and two line strata). Every positive row remains retrospective research only."
        ),
        "",
        "Pre-tax ROI is controlling. Tax-adjusted results are reference-only and apply tax per individual winning ¥2 ticket, never after issue/person aggregation. The accepted -9.47% baseline ladder is retained unchanged.",
        "",
        "## Canonical settlement source",
        "",
        f"- Gate-A eligible matches: {ledger['eligible_match_count']:,}",
        f"- trusted SQLite settlements: {ledger['trusted_match_count']:,}",
        f"- unavailable (zero stake, not loss): {ledger['unavailable_match_count']:,}",
        f"- #95 overlap: {ledger['legacy_overlap_count']:,}; disagreements: {ledger['legacy_disagreement_count']}",
        f"- fully settled N7 identities: {identity_distribution.get(7, 0):,} / {sum(identity_distribution.values()):,}",
        "",
        "The controlling ledger is built from the exact Gate-A SHA-bound SQLite `match_features` table. The legacy #95 ledger is only an overlap oracle.",
        "",
        "## Baseline bridge",
        "",
        "| Support | Settled issues | Stake | Gross | Pre-tax ROI | Status |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for row in bridge:
        lines.append(
            f"| {row['support']} | {row['settled_issue_count']} | ¥{float(row['stake_yuan']):,.0f} | ¥{float(row['gross_yuan']):,.2f} | {float(row['pre_tax_roi']):+.2%} | {row['reconciliation_status']} |"
        )
    lines += [
        "",
        "The expanded-SQLite row is descriptive #190 support. It does not replace or demote the accepted baseline ladder.",
        "",
        "## Full surface summary",
        "",
        "| Arm | Frozen policy rows | Rows with stake | Median native ROI | Positive native ROI | Positive matched lift |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for arm, count, stake_rows, median_roi, positive_roi, positive_lift in arm_stats:
        lines.append(
            f"| {arm} | {count:,} | {stake_rows:,} | {median_roi:+.2%} | {positive_roi:,} | {positive_lift:,} |"
            if median_roi is not None
            else f"| {arm} | {count:,} | 0 | NA | 0 | {positive_lift:,} |"
        )
    lines += [
        "",
        "`D_MATCH_ONLY_FULL` isolates match selection; `D_DIRECTION_ONLY` isolates direction/allocation on B0 identities; `D_JOINT_SPARSE` is the combined cell. `four_arm_attribution.csv.gz` publishes match lift, direction lift and their factorial interaction on exact four-way common support.",
        "",
        "## Probability and calibration",
        "",
        "| Source | Settled matches | LogLoss | Brier | ECE |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in population:
        lines.append(
            f"| {row['probability_source']} | {row['settled_match_count']:,} | {float(row['multiclass_log_loss']):.6f} | {float(row['multiclass_brier']):.6f} | {float(row['confidence_ece']):.6f} |"
        )
    lines += [
        "",
        "The manifest-covered selected-region table compares every frozen policy's sparse region with these full-population references. Divergence-bucket calibration is reported for both fundamental and calibrated-market estimates.",
        "",
        "## Positive screen rows (descriptive only)",
        "",
        "| Policy | Arm | Settled | Native ROI | Matched lift | Bootstrap low | Ex-largest issue | Ex-largest year |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in positive[:20]:

        def ratio(value: object) -> str:
            return "NA" if value in ("", None) else f"{float(value):+.2%}"

        lines.append(
            f"| {row['policy_id']} | {row['arm']} | {row['settled_issue_count']} | {ratio(row['native_pre_tax_roi'])} | {ratio(row['matched_b0_lift'])} | {ratio(row['bootstrap_lift_ci_low'])} | {ratio(row['ex_largest_issue_roi'])} | {ratio(row['ex_largest_year_roi'])} |"
        )
    if len(positive) > 20:
        lines.append(
            f"\nOnly the first 20 of {len(positive):,} screen rows are rendered here; the exact full freeze is machine-readable."
        )
    lines += [
        "",
        "The direction-only positive cluster is line-0-only evidence when coverage is derived from each candidate arm's own selected N7 identities. It therefore does not pass the declared cross-line coverage requirement and is not a strict-stability candidate.",
        "",
        "## Stability, risk and failure attribution",
        "",
        "The package includes YEAR/FOLD/LOYO rows for every policy×arm, 20,000 paired issue bootstraps on each pairwise-common support, ex-largest issue/year ROI, drawdown, payout concentration, miss streak, coverage by line/direction/league/year, and a row-level failure taxonomy. Blank ROI always means zero executed stake; it is never encoded as zero or a loss.",
        "",
        "Main limitations are separated rather than pooled: unavailable DELTA_MU mapping, sparse zero-candidate gates, the 1,064 unavailable target settlements, probability/model error, and directional portfolio construction. No threshold was selected from realized ROI.",
        "",
        "## Recommendation",
        "",
        "Keep the positive-screen rows as descriptive line-0 evidence, with zero strict-stability candidates. Any future claim needs new cross-line evidence under an outcome-unexposed freeze. Keep BEST_FULL as the accepted baseline ladder, and do not rescue a weak joint row by blending estimators or retuning thresholds on these outcomes.",
        "",
        "Paper research only; no betting, production or selector-release authority.",
        "",
    ]
    return "\n".join(lines)


def package_identity(stage: Path, controls: Mapping[str, object]) -> tuple[str, str]:
    payloads = {
        path.name: sha256_file(path)
        for path in sorted(stage.iterdir(), key=lambda value: value.name)
        if path.is_file()
        and path.name not in {"CONTENT_IDENTITY.json", "SHA256SUMS.json"}
    }
    content = {
        "contract_version": VERSION,
        "controls": dict(controls),
        "payloads": payloads,
    }
    (stage / "CONTENT_IDENTITY.json").write_text(
        json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        path.name: sha256_file(path)
        for path in sorted(stage.iterdir(), key=lambda value: value.name)
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (stage / "SHA256SUMS.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return sha256_file(stage / "SHA256SUMS.json"), sha256_file(
        stage / "CONTENT_IDENTITY.json"
    )


def build(
    output: Path = DEFAULT_OUTPUT,
    *,
    database: Path | None = None,
    bootstrap_draws: int = BOOTSTRAP_DRAWS,
    bootstrap_threads: int = 16,
) -> dict[str, object]:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise RuntimeError(f"immutable output already exists: {output}")
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    try:
        gate = load_gate_a()
        database_path = resolve_database(database)
        ledger_path = stage / "canonical_outcome_ledger.csv.gz"
        outcomes, ledger_receipt = build_canonical_outcome_ledger(
            database_path,
            gate["estimators"],
            ledger_path,
        )
        identities = gate["identities"]
        assert isinstance(identities, dict)
        identity_settlements, identity_distribution = prepare_identity_settlements(
            identities, outcomes
        )
        (stage / "canonical_outcome_ledger_binding.json").write_text(
            json.dumps(
                {
                    "contract": CONTRACT,
                    "source_database_path_contract": "data/derived/beidan_xlsm/beidan_xlsm.sqlite",
                    "source_database_sha256": EXPECTED_DATABASE_SHA256,
                    "source_table": "match_features",
                    "availability_rule": "has_trusted_settlement=1 AND result_code IS NOT NULL AND winning_sp IS NOT NULL AND winning_sp>0",
                    "missing_rule": "unavailable; zero tickets/stake; never infer and never count as loss",
                    "legacy_crosscheck": {
                        "package": LEGACY_DIR.name,
                        "manifest_sha256": EXPECTED_LEGACY_MANIFEST,
                        "payload_sha256": EXPECTED_LEGACY_PAYLOAD,
                        "role": "overlap consistency oracle only; not controlling denominator",
                    },
                    "receipt": ledger_receipt,
                    "identity_available_leg_distribution": {
                        str(key): value
                        for key, value in sorted(identity_distribution.items())
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        population, divergence_buckets = write_probability_settlement(
            stage, gate["estimators"], outcomes
        )
        surface = settle_surface(stage, gate, identity_settlements, outcomes)
        bootstrap_receipt = run_bootstrap_engine(
            stage,
            surface["bootstrap_targets"],
            draws=bootstrap_draws,
            threads=bootstrap_threads,
        )
        bootstrap_rows = read_csv(stage / "bootstrap_paired_lift_20000.csv")
        frontier = join_frontier(gate, surface, bootstrap_rows)
        failures = failure_attribution_rows(frontier)
        freeze = candidate_freeze(
            frontier,
            surface["risk"],
            surface["stability"],
            surface["coverage"],
            bootstrap_rows,
        )

        tables: tuple[tuple[str, Sequence[Mapping[str, object]], bool], ...] = (
            ("policy_arm_summary.csv.gz", surface["native"], True),
            ("pairwise_common_lift.csv.gz", surface["pairwise"], True),
            ("four_arm_attribution.csv.gz", surface["factorial"], True),
            ("stability_year_fold_loyo.csv.gz", surface["stability"], True),
            ("risk_concentration.csv.gz", surface["risk"], True),
            ("candidate_coverage_breakdown.csv.gz", surface["coverage"], True),
            (
                "selected_region_probability_metrics.csv.gz",
                surface["selected_probability"],
                True,
            ),
            ("full_population_probability_metrics.csv", population, False),
            ("divergence_bucket_calibration.csv", divergence_buckets, False),
            ("baseline_bridge.csv", surface["baseline_bridge"], False),
            ("full_frontier.csv.gz", frontier, True),
            ("failure_attribution.csv.gz", failures, True),
        )
        for name, rows, compressed in tables:
            if not rows:
                raise RuntimeError(f"required output table is empty: {name}")
            if compressed:
                write_gzip(stage / name, tuple(rows[0]), rows)
            else:
                write_csv(stage / name, tuple(rows[0]), rows)

        heatmap = [
            row
            for row in frontier
            if row["arm"] == "D_JOINT_SPARSE"
            and row["detector_family"] == "DELTA_P"
            and row["estimator_variant"] == "FUNDAMENTAL_INDEPENDENT"
            and row["min_history_n"] == "0"
            and row["coverage_gate"] == "TARGET_SAFE_PRICE"
            and row["uncertainty_gate"] == "NONE"
        ]
        if len(heatmap) != 12 * 4:
            raise RuntimeError(f"fixed heatmap slice drift: {len(heatmap)}")
        chart_frontier = [
            {
                "policy_id": row["policy_id"],
                "arm": row["arm"],
                "detector_family": row["detector_family"],
                "estimator_variant": row["estimator_variant"],
                "threshold_rule": row["threshold_rule"],
                "top_k": row["top_k"],
                "selected_issue_count": row["selected_issue_count"],
                "settled_issue_count": row["settled_issue_count"],
                "pre_tax_roi": row["pre_tax_roi"],
                "common_issue_count": row["common_issue_count"],
                "candidate_minus_b0_lift": row["candidate_minus_b0_lift"],
            }
            for row in frontier
            if row["arm"] != "B0_BEST_FULL"
        ]
        write_gzip(
            stage / "chart_source_coverage_roi_frontier.csv.gz",
            tuple(chart_frontier[0]),
            chart_frontier,
        )
        write_csv(
            stage / "chart_source_threshold_topk_heatmap.csv",
            tuple(heatmap[0]),
            heatmap,
        )
        write_gzip(
            stage / "chart_source_four_arm_attribution.csv.gz",
            tuple(surface["factorial"][0]),
            surface["factorial"],
        )
        write_csv(
            stage / "chart_source_divergence_calibration.csv",
            tuple(divergence_buckets[0]),
            divergence_buckets,
        )
        write_gzip(
            stage / "chart_source_risk_concentration.csv.gz",
            tuple(surface["risk"][0]),
            surface["risk"],
        )
        write_gzip(
            stage / "chart_source_candidate_coverage.csv.gz",
            tuple(surface["coverage"][0]),
            surface["coverage"],
        )
        svg_scatter(
            stage / "coverage_roi_frontier.svg",
            "#190 full sparse-divergence coverage vs pre-tax ROI surface",
            chart_frontier,
            "settled_issue_count",
            "pre_tax_roi",
        )
        svg_scatter(
            stage / "matched_lift_frontier.svg",
            "#190 pairwise-common matched-B0 lift surface",
            chart_frontier,
            "common_issue_count",
            "candidate_minus_b0_lift",
        )
        svg_heatmap(stage / "threshold_topk_heatmap.svg", heatmap)

        decision_status = (
            "STRICT_INDEPENDENT_EV_REQUIRED"
            if freeze["strict_stability_candidate_count"]
            else "NO_PROMOTION_FROM_GATE_B"
        )
        decision = {
            "contract": CONTRACT,
            "version": VERSION,
            "decision": decision_status,
            "pre_tax_primary": True,
            "tax_reference_only": True,
            "accepted_baseline_ladder_demoted": False,
            "positive_screen_count": freeze["positive_screen_count"],
            "strict_stability_candidate_count": freeze[
                "strict_stability_candidate_count"
            ],
            "strict_independent_ev_required": freeze["strict_independent_ev_required"],
            "promotion_authority": False,
            "paper_research_only": True,
            "interpretation": "complete frozen frontier settled; match, direction and joint interaction remain separately attributable",
        }
        (stage / "decision.json").write_text(
            json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (stage / "strict_ev_candidate_freeze.json").write_text(
            json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        source_binding = {
            "contract": CONTRACT,
            "gate_a": {
                "package": GATE_A.name,
                "manifest_sha256": EXPECTED_GATE_A_MANIFEST,
                "content_identity_sha256": EXPECTED_GATE_A_CONTENT,
                "payload_count": len(gate["manifest"]),
            },
            "canonical_outcomes": {
                "source": "hash-bound SQLite match_features",
                "database_sha256": EXPECTED_DATABASE_SHA256,
                "ledger_payload": "canonical_outcome_ledger.csv.gz",
                "ledger_sha256": ledger_receipt["ledger_sha256"],
                "trusted_match_count": ledger_receipt["trusted_match_count"],
                "unavailable_match_count": ledger_receipt["unavailable_match_count"],
            },
            "legacy_overlap_oracle": {
                "package": LEGACY_DIR.name,
                "manifest_sha256": EXPECTED_LEGACY_MANIFEST,
                "payload_sha256": EXPECTED_LEGACY_PAYLOAD,
                "overlap_count": ledger_receipt["legacy_overlap_count"],
                "disagreement_count": ledger_receipt["legacy_disagreement_count"],
            },
            "accepted_settlement_base": {
                "script": "scripts/settle_bj179_hierarchical_league_gate_b.py",
                "sha256": sha256_file(
                    ROOT / "scripts" / "settle_bj179_hierarchical_league_gate_b.py"
                ),
            },
            "outcome_access_authorization": "Issue #190 comment 5182419720 after Gate-A merge",
        }
        (stage / "source_binding.json").write_text(
            json.dumps(source_binding, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        card = {
            "contract": CONTRACT,
            "version": VERSION,
            "stage": "GATE_B_CANONICAL_OUTCOME_SETTLEMENT",
            "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
            "gate_a_content_identity_sha256": EXPECTED_GATE_A_CONTENT,
            "source_database_sha256": EXPECTED_DATABASE_SHA256,
            "canonical_outcome_ledger_sha256": ledger_receipt["ledger_sha256"],
            "eligible_match_count": ledger_receipt["eligible_match_count"],
            "trusted_match_count": ledger_receipt["trusted_match_count"],
            "unavailable_match_count": ledger_receipt["unavailable_match_count"],
            "fully_settled_n7_identity_count": identity_distribution[7],
            "n7_identity_count": sum(identity_distribution.values()),
            "policy_count": len(gate["grid"]),
            "arm_count": len(ARMS),
            "canonical_issue_count": MASTER_ISSUE_COUNT,
            "issue_arm_settlement_rows_each": surface["row_count_each_arm"],
            "pre_tax_primary": True,
            "tax_reference_only": True,
            "tax_rule": "per winning CNY2 ticket; no issue/person aggregation",
            "payout_factor": PAYOUT_FACTOR,
            "bootstrap": bootstrap_receipt,
            "required_frontier_complete": True,
            "retuning_permitted": False,
            "strict_independent_ev_required_for_positive_claim": True,
            "promotion_authority": False,
        }
        (stage / "settlement_card.json").write_text(
            json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        report = report_markdown(
            ledger_receipt,
            identity_distribution,
            surface["baseline_bridge"],
            population,
            frontier,
            freeze,
        )
        (stage / "REPORT.md").write_text(report, encoding="utf-8")
        wiki_entry = "\n".join(
            [
                "# #190 sparse divergence Gate B",
                "",
                f"- Decision: `{decision_status}`.",
                f"- Canonical support: {ledger_receipt['trusted_match_count']:,}/{ledger_receipt['eligible_match_count']:,} trusted matches; {identity_distribution[7]:,}/{sum(identity_distribution.values()):,} fully settled N7 identities.",
                f"- Positive screen rows: {freeze['positive_screen_count']}; strict-stability candidates: {freeze['strict_stability_candidate_count']}.",
                "- The accepted BEST_FULL baseline ladder is retained. Pre-tax ROI controls; tax is per winning ¥2 ticket and reference-only.",
                "- Match-selection, direction and factorial interaction remain separate. No threshold was retuned after outcomes.",
                "- See the immutable Gate-B package REPORT and chart-source tables for the complete frontier and failure analysis.",
                "",
            ]
        )
        (stage / "RESEARCH_WIKI_ENTRY.md").write_text(wiki_entry, encoding="utf-8")
        (stage / "README.md").write_text(
            "# #190 Gate B immutable sparse-divergence settlement\n\n"
            "The package contains the hash-bound SQLite outcome ledger, complete four-arm surface, full frontier, paired bootstrap/stability/risk diagnostics, figures, decision report and Wiki entry.\n",
            encoding="utf-8",
        )
        shutil.copy2(Path(__file__), stage / "settlement_runner.py")
        controls = {
            "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
            "database_sha256": EXPECTED_DATABASE_SHA256,
            "canonical_ledger_sha256": ledger_receipt["ledger_sha256"],
            "eligible_match_count": EXPECTED_LEDGER_ROWS,
            "trusted_match_count": EXPECTED_TRUSTED_ROWS,
            "unavailable_match_count": EXPECTED_UNAVAILABLE_ROWS,
            "fully_settled_identity_count": EXPECTED_IDENTITY_DISTRIBUTION[7],
            "policies": len(gate["grid"]),
            "arms": list(ARMS),
            "issues": MASTER_ISSUE_COUNT,
            "bootstrap_draws": bootstrap_draws,
            "bootstrap_draw_sha256": bootstrap_receipt["draw_matrix_sha256"],
            "accepted_b0_legacy_bridge": "PASS",
            "retuning_permitted": False,
            "promotion_authority": False,
        }
        manifest_hash, content_hash = package_identity(stage, controls)
        os.replace(stage, output)
        return {
            "output": str(output),
            "manifest_sha256": manifest_hash,
            "content_identity_sha256": content_hash,
            "payload_count": len(json.loads((output / "SHA256SUMS.json").read_text())),
            "trusted_match_count": ledger_receipt["trusted_match_count"],
            "unavailable_match_count": ledger_receipt["unavailable_match_count"],
            "fully_settled_identity_count": identity_distribution[7],
            "positive_screen_count": freeze["positive_screen_count"],
            "strict_stability_candidate_count": freeze[
                "strict_stability_candidate_count"
            ],
            "decision": decision_status,
        }
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--bootstrap-draws", type=int, default=BOOTSTRAP_DRAWS)
    parser.add_argument("--bootstrap-threads", type=int, default=16)
    args = parser.parse_args()
    if args.bootstrap_draws <= 0 or args.bootstrap_threads <= 0:
        raise SystemExit("bootstrap draws/threads must be positive")
    print(
        json.dumps(
            build(
                args.output,
                database=args.database,
                bootstrap_draws=args.bootstrap_draws,
                bootstrap_threads=args.bootstrap_threads,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
