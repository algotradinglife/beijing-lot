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
from collections import defaultdict
from dataclasses import dataclass
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
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeError("invalid freeze config") from exc
    if tuple(config.get("safe_input_schema", ())) != SAFE_SCHEMA:
        raise FreezeError("safe config schema mismatch")
    if not isinstance(config.get("safe_input_sha256"), str) or len(config["safe_input_sha256"]) != 64:
        raise FreezeError("safe config checksum missing")
    return config


def read_safe_projection(path: Path, config: dict[str, object]) -> list[Leg]:
    if path.name != config.get("safe_input_filename"):
        raise FreezeError("unauthorized safe input filename")
    if sha256_file(path) != config["safe_input_sha256"]:
        raise FreezeError("safe input SHA-256 mismatch")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != SAFE_SCHEMA:
            raise FreezeError("safe input schema mismatch")
        legs: list[Leg] = []
        identities: set[tuple[str, int, str]] = set()
        for row in reader:
            try:
                issue = str(int(row["issue"]))
                idx = int(row["match_idx"])
                sp = tuple(float(row[f"quoted_sp_{code}"]) for code in CODE_ORDER)
            except (KeyError, TypeError, ValueError) as exc:
                raise FreezeError("invalid safe input row") from exc
            if issue not in ISSUES or idx < 1 or any(value <= 0.0 for value in sp):
                raise FreezeError("invalid safe input row")
            identity = (issue, idx, row["match_id"])
            if not row["match_id"] or identity in identities:
                raise FreezeError("missing or duplicate safe identity")
            identities.add(identity)
            legs.append(Leg(issue, idx, row["match_id"], row["kickoff_ts"], row["decision_cutoff_ts"], row["snapshot_ts"], sp))
    if not legs:
        raise FreezeError("safe input has no rows")
    return legs


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


def _prefix_scores(group: list[Candidate]) -> list[float]:
    scores = [0.0]
    for item in group:
        scores.append(scores[-1] + item.coverage)
    return scores


def _best_exact_quota(pool: list[Candidate], k: int) -> list[Candidate] | None:
    """Exact sparse DP for the R2 quota objective and deterministic tie-break.

    R2's two lower bounds make the target-deviation minimum occur first at
    ``quota_targets(k)``.  If that integer triple is unavailable, this routine
    expands total (n3+n0) by one at a time and evaluates every split; the first
    feasible total is the minimum-deviation shell.
    """
    if len(pool) < k:
        return None
    ordered = candidate_order(pool)
    by_counts: dict[tuple[int, int, int], list[tuple[int, Candidate]]] = defaultdict(list)
    for rank, item in enumerate(ordered):
        by_counts[item.counts].append((rank, item))
    groups = []
    for counts, members in sorted(by_counts.items()):
        members.sort(key=lambda pair: pair[0])
        groups.append((counts, members, _prefix_scores([item for _rank, item in members])))

    n3_min, n0_min, _n1_target = quota_targets(k)
    total_legs = 7 * k
    # The loop order is the exact D objective; for a fixed n3+n0 every split
    # has equal D, so coverage then lexicographic selection decides it.
    for sum_30 in range(n3_min + n0_min, total_legs + 1):
        targets = [(n3, sum_30 - n3) for n3 in range(n3_min, sum_30 - n0_min + 1) if sum_30 - n3 >= n0_min]
        best: tuple[float, tuple[int, ...], tuple[int, int]] | None = None
        for target3, target0 in targets:
            # state -> (coverage, globally sorted candidate ranks).  Process a
            # count-pattern group at once, selecting its coverage-best prefix.
            states: dict[tuple[int, int, int], tuple[float, tuple[int, ...]]] = {(0, 0, 0): (0.0, ())}
            for (c3, c0, _c1), members, prefix in groups:
                next_states = dict(states)
                limit = len(members)
                for (used, got3, got0), (score, ranks) in states.items():
                    for take in range(1, min(limit, k - used) + 1):
                        next3, next0 = got3 + take * c3, got0 + take * c0
                        if next3 > target3 or next0 > target0:
                            break
                        taken_ranks = tuple(rank for rank, _item in members[:take])
                        key = (used + take, next3, next0)
                        candidate_value = (score + prefix[take], tuple(sorted(ranks + taken_ranks)))
                        current = next_states.get(key)
                        if current is None or candidate_value[0] > current[0] + 1e-15 or (abs(candidate_value[0] - current[0]) <= 1e-15 and candidate_value[1] < current[1]):
                            next_states[key] = candidate_value
                states = next_states
            value = states.get((k, target3, target0))
            if value is not None:
                candidate_value = (value[0], value[1], (target3, target0))
                if best is None or candidate_value[0] > best[0] + 1e-15 or (abs(candidate_value[0] - best[0]) <= 1e-15 and candidate_value[1] < best[1]):
                    best = candidate_value
        if best is not None:
            return [ordered[rank] for rank in best[1]]
    return None


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
                summary.append(_row(issue, arm, "", "NO_BET_INSUFFICIENT_ELIGIBLE_MATCHES", None, diagnostic=arm in {"FULL_2187", "SP_BAND_ONLY", "PATTERN_322"}, selected_ids=""))
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
            summary.append(_row(issue, "MARKET_IMPLIED_COVERAGE_DIAGNOSTIC", str(k), "PASS" if coverage else "NO_BET_INSUFFICIENT_CANDIDATES", coverage, diagnostic=False, selected_ids=coverage_ids))
            for arm, pool in (("TOPK_RATIO_CONSTRAINED", band), ("TOPK_RATIO_PAYOUT_CAPPED", capped)):
                chosen = _best_exact_quota(pool, k)
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


def write_freeze(output_dir: Path, combinations: list[dict[str, str]], summary: list[dict[str, str]], *, input_path: Path, config_path: Path, git_head: str) -> None:
    if output_dir.exists():
        raise FreezeError("output directory already exists")
    output_dir.mkdir(parents=True)
    def write_csv(name: str, rows: list[dict[str, str]], fields: tuple[str, ...]) -> Path:
        path = output_dir / name
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
        return path
    combos_path = write_csv("combinations.csv", combinations, ("combination_id", "issue", "arm", "k", "ordinal", "match_ids", "sequence", "n3", "n0", "n1", "coverage_score", "quoted_sp_product", "gross_pre_tax_payout_yuan"))
    summary_path = write_csv("summary.csv", summary, ("issue", "arm", "k", "disposition", "diagnostic_only", "sequence_count", "n3", "n0", "n1", "pct_3", "pct_0", "pct_1", "combination_ids_sha256"))
    manifest = {"experiment": "BJ-N7-COMPRESS-001", "safe_input_sha256": sha256_file(input_path), "config_sha256": sha256_file(config_path), "generator_sha256": sha256_file(Path(__file__)), "git_head": git_head, "parameters": {"code_order": list(CODE_ORDER), "k_values": list(KS), "sp_band": list(BAND), "payout_factor": PAYOUT_FACTOR, "payout_cap": PAYOUT_CAP}, "outputs": {"combinations.csv": sha256_file(combos_path), "summary.csv": sha256_file(summary_path)}}
    manifest_path = output_dir / "manifest.json"; manifest_path.write_bytes(canonical_json(manifest))
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
    write_freeze(args.output_dir, combinations, summary, input_path=args.input, config_path=args.config, git_head=args.git_head)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FreezeError as exc:
        print(f"freeze_failed={exc}", file=sys.stderr)
        raise SystemExit(2)
