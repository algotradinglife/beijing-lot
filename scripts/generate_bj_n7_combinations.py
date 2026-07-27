#!/usr/bin/env python3
"""Blind Stage-2 deterministic combination generator for BJ-N7-COMPRESS-001.

This program accepts a checksum-bound, outcome-free projection only.  It has no
discovery, database, network, projector fallback, or settlement code.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import sys
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

CODE_ORDER = ("3", "1", "0")
SAFE_SCHEMA = (
    "issue", "match_idx", "match_id", "kickoff_ts", "decision_cutoff_ts",
    "snapshot_ts", "quoted_sp_3", "quoted_sp_1", "quoted_sp_0",
)
ISSUES = tuple(str(value) for value in range(26071, 26078))
KS = (32, 64, 128, 256)
BAND = (2.5, 4.5)
PAYOUT_FACTOR = 0.65
PAYOUT_CAP = 10000.0
EXPERIMENT = "BJ-N7-COMPRESS-001"
AUTHORIZED_CONFIG_FILENAME = "freeze_config_v1.json"
AUTHORIZED_CONFIG_SHA256 = "b56f9ec8ced0ac84168fae8cba4714f461b3b94464533008cf146b67d2c956a2"
AUTHORIZED_CONFIG_SIZE = 460
AUTHORIZED_SAFE_INPUT_FILENAME = "safe_input_v1.csv"
AUTHORIZED_SAFE_INPUT_SHA256 = "03514b097b0ce4fe54a0129862b2ce0cd3963801afbf74901daa6a9a141678eb"
AUTHORIZED_SAFE_INPUT_SIZE = 38570
AUTHORIZED_SOURCE_SHA256 = "2f04f50d7fe6085f1353b6690c5e69bc6fb9befc2180fae780aa0bbd056b0233"
COVERAGE_SCORE_SCALE = 10**8


class FreezeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Leg:
    issue: str
    match_idx: int
    match_id: str
    kickoff_ts: str
    decision_cutoff_ts: str
    snapshot_ts: str
    sp: tuple[float, float, float]

    def price(self, code: str) -> float:
        return self.sp[CODE_ORDER.index(code)]

    def band_codes(self) -> tuple[str, ...]:
        return tuple(code for code in CODE_ORDER if BAND[0] <= self.price(code) <= BAND[1])

    def midpoint_distance(self) -> float:
        return sum(abs(price - 3.5) for price in self.sp)


@dataclass(frozen=True)
class Candidate:
    sequence: tuple[str, ...]
    rank: tuple[int, ...]
    counts: tuple[int, int, int]  # n3, n0, n1
    coverage: float
    quoted_product: float
    gross_payout: float


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def read_config(path: Path) -> dict[str, object]:
    if path.name != AUTHORIZED_CONFIG_FILENAME or path.is_symlink():
        raise FreezeError("unauthorized freeze config")
    try:
        if path.stat().st_size != AUTHORIZED_CONFIG_SIZE:
            raise FreezeError("unauthorized freeze config")
        config_bytes = path.read_bytes()
        config_sha256 = hashlib.sha256(config_bytes).hexdigest()
        config = json.loads(config_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FreezeError("invalid freeze config") from exc
    if config_sha256 != AUTHORIZED_CONFIG_SHA256:
        raise FreezeError("unauthorized freeze config")
    expected = {
        "experiment": EXPERIMENT,
        "safe_input_filename": AUTHORIZED_SAFE_INPUT_FILENAME,
        "safe_input_sha256": AUTHORIZED_SAFE_INPUT_SHA256,
        "safe_input_schema": list(SAFE_SCHEMA),
        "source_sha256": AUTHORIZED_SOURCE_SHA256,
    }
    if config != expected:
        raise FreezeError("freeze config identity mismatch")
    return config


def read_safe_projection(path: Path, config: dict[str, object]) -> list[Leg]:
    if config.get("experiment") != EXPERIMENT or config.get("source_sha256") != AUTHORIZED_SOURCE_SHA256:
        raise FreezeError("freeze config provenance mismatch")
    if path.name != AUTHORIZED_SAFE_INPUT_FILENAME or path.is_symlink():
        raise FreezeError("unauthorized safe input filename")
    try:
        if path.stat().st_size != AUTHORIZED_SAFE_INPUT_SIZE:
            raise FreezeError("safe input SHA-256 mismatch")
        safe_input_bytes = path.read_bytes()
        safe_input_sha256 = hashlib.sha256(safe_input_bytes).hexdigest()
        safe_input_text = safe_input_bytes.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise FreezeError("invalid safe input") from exc
    if safe_input_sha256 != AUTHORIZED_SAFE_INPUT_SHA256:
        raise FreezeError("safe input SHA-256 mismatch")
    with StringIO(safe_input_text, newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != SAFE_SCHEMA:
            raise FreezeError("safe input schema mismatch")
        legs: list[Leg] = []
        identities: set[tuple[str, int, str]] = set()
        for row in reader:
            try:
                issue = str(int(row["issue"]))
                idx = int(row["match_idx"])
                sp = _parse_sp(row)
            except (KeyError, TypeError, ValueError) as exc:
                raise FreezeError("invalid safe input row") from exc
            if issue not in ISSUES or idx < 1:
                raise FreezeError("invalid safe input row")
            identity = (issue, idx, row["match_id"])
            if not row["match_id"] or identity in identities:
                raise FreezeError("missing or duplicate safe identity")
            identities.add(identity)
            legs.append(Leg(issue, idx, row["match_id"], row["kickoff_ts"], row["decision_cutoff_ts"], row["snapshot_ts"], sp))
    if not legs:
        raise FreezeError("safe input has no rows")
    return legs


def _parse_sp(row: dict[str, str]) -> tuple[float, float, float]:
    sp = tuple(float(row[f"quoted_sp_{code}"]) for code in CODE_ORDER)
    if any(not math.isfinite(value) or value <= 0.0 for value in sp):
        raise FreezeError("invalid safe input row")
    return sp


def select_legs(legs: list[Leg], issue: str) -> tuple[Leg, ...] | None:
    eligible = [leg for leg in legs if leg.issue == issue and len(leg.band_codes()) >= 2]
    ranked = sorted(eligible, key=lambda leg: (-len(leg.band_codes()), leg.midpoint_distance(), leg.match_idx))
    if len(ranked) < 7:
        return None
    return tuple(sorted(ranked[:7], key=lambda leg: leg.match_idx))


def candidates(legs: tuple[Leg, ...], *, universe: str) -> list[Candidate]:
    if universe == "FULL_2187":
        choices = [CODE_ORDER] * 7
    elif universe == "SP_BAND_ONLY":
        choices = [leg.band_codes() for leg in legs]
    else:
        raise FreezeError("unknown candidate universe")
    output: list[Candidate] = []
    for sequence in itertools.product(*choices):
        coverage = 1.0
        quoted_product = 1.0
        for leg, code in zip(legs, sequence):
            inv = [1.0 / leg.price(item) for item in CODE_ORDER]
            coverage *= (1.0 / leg.price(code)) / sum(inv)
            quoted_product *= leg.price(code)
        counts = (sequence.count("3"), sequence.count("0"), sequence.count("1"))
        output.append(Candidate(sequence, tuple(CODE_ORDER.index(code) for code in sequence), counts, coverage, quoted_product, 2.0 * PAYOUT_FACTOR * quoted_product))
    if len({item.sequence for item in output}) != len(output):
        raise FreezeError("non-unique candidate universe")
    return output


def candidate_order(pool: list[Candidate]) -> list[Candidate]:
    return sorted(pool, key=lambda item: (-item.coverage, item.rank))


def quota_targets(k: int) -> tuple[int, int, int]:
    legs = 7 * k
    floor = math.ceil(0.35 * legs)
    return floor, floor, legs - 2 * floor


def _best_exact_quota(pool: list[Candidate], k: int) -> list[Candidate] | None:
    """Bounded deterministic MILP for the exact R2 quota objective.

    With both hard floors satisfied, R2's absolute target deviation is exactly
    twice the excess ``n3+n0`` above its 70% target.  The solver therefore
    minimizes ``n3+n0``, then maximizes the fixed-point aggregate coverage
    score, then fixes blocks of candidate-rank bits from lowest rank upward.
    The final block pass implements the accepted full lexicographic tie-break.
    """
    if len(pool) < k:
        return None
    ordered = candidate_order(pool)
    try:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
    except ImportError as exc:
        raise FreezeError("ratio optimizer dependency unavailable") from exc

    size = len(ordered)
    ones = np.ones(size)
    n3 = np.array([item.counts[0] for item in ordered], dtype=float)
    n0 = np.array([item.counts[1] for item in ordered], dtype=float)
    sum30 = n3 + n0
    coverage_units = np.array(
        [round(item.coverage * COVERAGE_SCORE_SCALE) for item in ordered],
        dtype=float,
    )
    need3, need0, _need1 = quota_targets(k)
    base_constraints = [
        LinearConstraint(ones, k, k),
        LinearConstraint(n3, need3, np.inf),
        LinearConstraint(n0, need0, np.inf),
    ]
    integrality = np.ones(size)
    lower = np.zeros(size)
    upper = np.ones(size)
    options = {"mip_rel_gap": 0.0, "presolve": True}

    def solve(objective, constraints, lo=lower, hi=upper):
        return milp(
            c=objective,
            integrality=integrality,
            bounds=Bounds(lo, hi),
            constraints=constraints,
            options=options,
        )

    deviation_result = solve(sum30, base_constraints)
    if deviation_result.status == 2:
        return None
    if not deviation_result.success or deviation_result.x is None:
        raise FreezeError("ratio optimizer failed during deviation minimization")
    deviation_bits = np.rint(deviation_result.x).astype(int)
    best_sum30 = int(sum(sum30[index] for index, bit in enumerate(deviation_bits) if bit))
    exact_constraints = [*base_constraints, LinearConstraint(sum30, best_sum30, best_sum30)]

    coverage_result = solve(-coverage_units, exact_constraints)
    if not coverage_result.success or coverage_result.x is None:
        raise FreezeError("ratio optimizer failed during coverage maximization")
    coverage_bits = np.rint(coverage_result.x).astype(int)
    best_coverage_units = int(
        sum(coverage_units[index] for index, bit in enumerate(coverage_bits) if bit)
    )
    lex_constraints = [
        *exact_constraints,
        LinearConstraint(coverage_units, best_coverage_units, best_coverage_units),
    ]

    # A 32-bit block objective is exactly representable as a float.  Fixing
    # blocks from the lowest candidate rank upward is the full rank-vector
    # lexicographic tie-break, without an unbounded epsilon objective.
    fixed_lower = lower.copy()
    fixed_upper = upper.copy()
    fixed_ones = 0
    block_size = 32
    for start in range(0, size, block_size):
        if fixed_ones == k:
            fixed_upper[start:] = 0.0
            break
        if size - start == k - fixed_ones:
            fixed_lower[start:] = 1.0
            break
        stop = min(start + block_size, size)
        objective = np.zeros(size)
        for offset, index in enumerate(range(start, stop)):
            objective[index] = -(2 ** (stop - start - offset - 1))
        lex_result = solve(objective, lex_constraints, fixed_lower, fixed_upper)
        if not lex_result.success or lex_result.x is None:
            raise FreezeError("ratio optimizer failed during lexicographic tie-break")
        block_bits = np.rint(lex_result.x[start:stop]).astype(int)
        for offset, bit in enumerate(block_bits):
            index = start + offset
            fixed_lower[index] = float(bit)
            fixed_upper[index] = float(bit)
            fixed_ones += int(bit)

    final_result = solve(np.zeros(size), lex_constraints, fixed_lower, fixed_upper)
    if not final_result.success or final_result.x is None:
        raise FreezeError("ratio optimizer failed during final verification")
    bits = np.rint(final_result.x).astype(int)
    chosen = [item for item, bit in zip(ordered, bits) if bit]
    if len(chosen) != k:
        raise FreezeError("ratio optimizer returned non-integral selection")
    if sum(item.counts[0] + item.counts[1] for item in chosen) != best_sum30:
        raise FreezeError("ratio optimizer changed the deviation optimum")
    if sum(round(item.coverage * COVERAGE_SCORE_SCALE) for item in chosen) != best_coverage_units:
        raise FreezeError("ratio optimizer changed the coverage optimum")
    return chosen


def _row(issue: str, arm: str, k: str, disposition: str, chosen: list[Candidate] | None, *, diagnostic: bool, selected_ids: str) -> dict[str, str]:
    items = chosen or []
    n3 = sum(item.counts[0] for item in items)
    n0 = sum(item.counts[1] for item in items)
    n1 = sum(item.counts[2] for item in items)
    total = max(1, n3 + n0 + n1)
    return {
        "issue": issue, "arm": arm, "k": k, "disposition": disposition,
        "diagnostic_only": "YES" if diagnostic else "NO",
        "sequence_count": str(len(items)), "n3": str(n3), "n0": str(n0), "n1": str(n1),
        "pct_3": f"{n3 / total:.10f}", "pct_0": f"{n0 / total:.10f}", "pct_1": f"{n1 / total:.10f}",
        "combination_ids_sha256": hashlib.sha256(selected_ids.encode("utf-8")).hexdigest() if items else "",
    }


def assert_selected(arm: str, pool: list[Candidate], chosen: list[Candidate] | None, k: int | None) -> None:
    """Runtime invariants required by the audited freeze contract."""
    if chosen is None:
        return
    if len({item.sequence for item in chosen}) != len(chosen):
        raise FreezeError("selected combinations are not unique")
    if k is not None and len(chosen) != k:
        raise FreezeError("selected combination count mismatch")
    if any(item not in pool for item in chosen):
        raise FreezeError("selected combination outside candidate pool")
    if arm == "TOPK_RATIO_PAYOUT_CAPPED" and any(item.gross_payout > PAYOUT_CAP for item in chosen):
        raise FreezeError("payout-capped selection exceeds cap")
    if arm.startswith("TOPK_RATIO") and k is not None:
        need3, need0, _need1 = quota_targets(k)
        if sum(item.counts[0] for item in chosen) < need3 or sum(item.counts[1] for item in chosen) < need0:
            raise FreezeError("ratio quota floor violated")


def generate(legs: list[Leg]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    combinations: list[dict[str, str]] = []
    summary: list[dict[str, str]] = []
    for issue in ISSUES:
        selected = select_legs(legs, issue)
        if selected is None:
            for arm in ("FULL_2187", "SP_BAND_ONLY", "PATTERN_322", "MARKET_IMPLIED_COVERAGE_DIAGNOSTIC", "TOPK_RATIO_CONSTRAINED", "TOPK_RATIO_PAYOUT_CAPPED", "TOPK_VALUE"):
                summary.append(_row(issue, arm, "", "NO_BET_INSUFFICIENT_ELIGIBLE_MATCHES", None, diagnostic=arm in {"FULL_2187", "SP_BAND_ONLY", "PATTERN_322", "MARKET_IMPLIED_COVERAGE_DIAGNOSTIC"}, selected_ids=""))
            continue
        full = candidates(selected, universe="FULL_2187")
        band = candidates(selected, universe="SP_BAND_ONLY")
        pattern = [item for item in full if sorted(item.counts) == [2, 2, 3]]
        capped = [item for item in band if item.gross_payout <= PAYOUT_CAP]
        arm_pools = (("FULL_2187", "ALL", full, True), ("SP_BAND_ONLY", "ALL", band, True), ("PATTERN_322", "ALL", pattern, True))
        for arm, k, pool, diagnostic in arm_pools:
            assert_selected(arm, pool, pool, None)
            rows = _append_combinations(combinations, issue, arm, k, selected, pool)
            summary.append(_row(issue, arm, k, "DIAGNOSTIC", pool, diagnostic=diagnostic, selected_ids=rows))
        for k in KS:
            coverage = candidate_order(band)[:k] if len(band) >= k else None
            assert_selected("MARKET_IMPLIED_COVERAGE_DIAGNOSTIC", band, coverage, k)
            coverage_ids = _append_combinations(combinations, issue, "MARKET_IMPLIED_COVERAGE_DIAGNOSTIC", str(k), selected, coverage or [])
            summary.append(_row(issue, "MARKET_IMPLIED_COVERAGE_DIAGNOSTIC", str(k), "DIAGNOSTIC" if coverage else "NO_BET_INSUFFICIENT_CANDIDATES", coverage, diagnostic=True, selected_ids=coverage_ids))
            ratio_chosen = _best_exact_quota(band, k)
            capped_is_band = len(capped) == len(band) and all(left is right for left, right in zip(capped, band))
            for arm, pool in (("TOPK_RATIO_CONSTRAINED", band), ("TOPK_RATIO_PAYOUT_CAPPED", capped)):
                chosen = ratio_chosen if arm == "TOPK_RATIO_CONSTRAINED" or capped_is_band else _best_exact_quota(pool, k)
                assert_selected(arm, pool, chosen, k)
                ids = _append_combinations(combinations, issue, arm, str(k), selected, chosen or [])
                summary.append(_row(issue, arm, str(k), "PASS" if chosen else "NO_BET_RATIO_FEASIBILITY_NOT_ESTABLISHED", chosen, diagnostic=False, selected_ids=ids))
            summary.append(_row(issue, "TOPK_VALUE", str(k), "UNAVAILABLE_NO_IDENTITY_MATCHED_PRE_CUTOFF_V333_Q", None, diagnostic=False, selected_ids=""))
    return combinations, summary


def _append_combinations(output: list[dict[str, str]], issue: str, arm: str, k: str, legs: tuple[Leg, ...], pool: list[Candidate]) -> str:
    ids: list[str] = []
    for ordinal, item in enumerate(pool, 1):
        sequence = "".join(item.sequence)
        combo_id = f"{issue}:{arm}:{k}:{ordinal:04d}:{sequence}"
        ids.append(combo_id)
        output.append({
            "combination_id": combo_id, "issue": issue, "arm": arm, "k": k, "ordinal": str(ordinal),
            "match_ids": "+".join(leg.match_id for leg in legs), "sequence": sequence,
            "n3": str(item.counts[0]), "n0": str(item.counts[1]), "n1": str(item.counts[2]),
            "coverage_score": f"{item.coverage:.12f}", "quoted_sp_product": f"{item.quoted_product:.12f}",
            "gross_pre_tax_payout_yuan": f"{item.gross_payout:.12f}",
        })
    return "\n".join(ids) + ("\n" if ids else "")


def write_freeze(output_dir: Path, combinations: list[dict[str, str]], summary: list[dict[str, str]], *, git_head: str) -> None:
    if output_dir.exists():
        raise FreezeError("output directory already exists")
    output_dir.mkdir(parents=True)
    def write_csv(name: str, rows: list[dict[str, str]], fields: tuple[str, ...]) -> Path:
        path = output_dir / name
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return path
    combos_path = write_csv("combinations.csv", combinations, ("combination_id", "issue", "arm", "k", "ordinal", "match_ids", "sequence", "n3", "n0", "n1", "coverage_score", "quoted_sp_product", "gross_pre_tax_payout_yuan"))
    summary_path = write_csv("summary.csv", summary, ("issue", "arm", "k", "disposition", "diagnostic_only", "sequence_count", "n3", "n0", "n1", "pct_3", "pct_0", "pct_1", "combination_ids_sha256"))
    manifest = {"experiment": EXPERIMENT, "source_sha256": AUTHORIZED_SOURCE_SHA256, "safe_input_filename": AUTHORIZED_SAFE_INPUT_FILENAME, "safe_input_schema": list(SAFE_SCHEMA), "safe_input_sha256": AUTHORIZED_SAFE_INPUT_SHA256, "config_sha256": AUTHORIZED_CONFIG_SHA256, "generator_sha256": sha256_file(Path(__file__)), "git_head": git_head, "parameters": {"code_order": list(CODE_ORDER), "k_values": list(KS), "sp_band": list(BAND), "payout_factor": PAYOUT_FACTOR, "payout_cap": PAYOUT_CAP, "coverage_score_scale": COVERAGE_SCORE_SCALE}, "outputs": {"combinations.csv": sha256_file(combos_path), "summary.csv": sha256_file(summary_path)}}
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_bytes(canonical_json(manifest))
    checksum_paths = (combos_path, manifest_path, summary_path)
    (output_dir / "SHA256SUMS").write_text("".join(f"{sha256_file(path)}  {path.name}\n" for path in checksum_paths), encoding="utf-8", newline="\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BJ-N7 blind Stage-2 combination generator")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--git-head", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if len(args.git_head) != 40 or any(char not in "0123456789abcdef" for char in args.git_head):
        raise FreezeError("git head must be a lowercase 40-character SHA-1")
    config = read_config(args.config)
    legs = read_safe_projection(args.input, config)
    combinations, summary = generate(legs)
    write_freeze(args.output_dir, combinations, summary, git_head=args.git_head)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FreezeError as exc:
        print(f"freeze_failed={exc}", file=sys.stderr)
        raise SystemExit(2)
