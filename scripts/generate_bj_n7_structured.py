#!/usr/bin/env python3
"""Outcome-free structured N7 feasibility freeze for Issue #67."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import itertools
import math
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / "generate_bj_n7_combinations.py"
_spec = importlib.util.spec_from_file_location("bj_n7_base", BASE_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError("audited base generator unavailable")
base = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = base
_spec.loader.exec_module(base)

STRUCTURES = (
    ("STRUCTURED_2F_5D_288", 2, 5, 288, 576),
    ("STRUCTURED_3F_4D_432", 3, 4, 432, 864),
    ("STRUCTURED_4F_3D_648", 4, 3, 648, 1296),
)
THRESHOLDS = (0.75, 0.80, 0.85)


@dataclass(frozen=True)
class Pair:
    codes: tuple[str, str]
    excluded: str
    excluded_q: float
    coverage: float
    value: float
    conditional_sp: float
    min_sp: float
    gm_sp: float


def leg_q(leg: base.Leg) -> dict[str, float]:
    inv = {code: 1.0 / leg.price(code) for code in base.CODE_ORDER}
    total = sum(inv.values())
    return {code: inv[code] / total for code in base.CODE_ORDER}


def pair_options(leg: base.Leg, threshold: float) -> list[Pair]:
    q = leg_q(leg)
    output = []
    for excluded in base.CODE_ORDER:
        codes = tuple(code for code in base.CODE_ORDER if code != excluded)
        prices = [leg.price(code) for code in codes]
        coverage = sum(q[code] for code in codes)
        if coverage + 1e-15 < threshold or not all(
            base.BAND[0] <= price <= base.BAND[1] for price in prices
        ):
            continue
        value = sum(q[code] * leg.price(code) for code in codes)
        output.append(
            Pair(
                codes,
                excluded,
                q[excluded],
                coverage,
                value,
                value / coverage,
                min(prices),
                math.sqrt(prices[0] * prices[1]),
            )
        )
    return output


def assignment_key(
    item: dict[str, object],
) -> tuple[float, float, float, tuple[int, ...], tuple[int, ...]]:
    excluded_rank = tuple(
        base.CODE_ORDER.index(code) for code in item["excluded_codes"]
    )
    return (
        -float(item["package_coverage"]),
        -float(item["double_h_product"]),
        -float(item["min_retained_sp"]),
        tuple(item["full_positions"]),
        excluded_rank,
    )


def choose_assignment(
    legs: tuple[base.Leg, ...], full_count: int, threshold: float
) -> dict[str, object] | None:
    best = None
    for full_positions in itertools.combinations(range(7), full_count):
        doubles = tuple(index for index in range(7) if index not in full_positions)
        options = [pair_options(legs[index], threshold) for index in doubles]
        if any(not values for values in options):
            continue
        for selected_pairs in itertools.product(*options):
            values = []
            for index, leg in enumerate(legs):
                q = leg_q(leg)
                if index in full_positions:
                    values.append(
                        sum(q[code] * leg.price(code) for code in base.CODE_ORDER)
                    )
                else:
                    values.append(selected_pairs[doubles.index(index)].value)
            combinations = (3**full_count) * (2 ** len(doubles))
            expected_gross = 2.0 * base.PAYOUT_FACTOR * math.prod(values)
            candidate = {
                "full_positions": full_positions,
                "double_positions": doubles,
                "pairs": selected_pairs,
                "excluded_codes": tuple(pair.excluded for pair in selected_pairs),
                "package_coverage": math.prod(pair.coverage for pair in selected_pairs),
                "double_h_product": math.prod(
                    pair.conditional_sp for pair in selected_pairs
                ),
                "min_retained_sp": min(pair.min_sp for pair in selected_pairs),
                "expected_gross": expected_gross,
                "expected_roi": expected_gross / (2 * combinations) - 1.0,
            }
            if best is None or assignment_key(candidate) < assignment_key(best):
                best = candidate
    return best


def physical_pool(
    legs: tuple[base.Leg, ...], assignment: dict[str, object]
) -> list[base.Candidate]:
    full = set(assignment["full_positions"])
    doubles = tuple(assignment["double_positions"])
    pairs = tuple(assignment["pairs"])
    choices = [
        base.CODE_ORDER if index in full else pairs[doubles.index(index)].codes
        for index in range(7)
    ]
    pool = []
    for sequence in itertools.product(*choices):
        coverage = 1.0
        product = 1.0
        for leg, code in zip(legs, sequence):
            coverage *= leg_q(leg)[code]
            product *= leg.price(code)
        counts = (sequence.count("3"), sequence.count("0"), sequence.count("1"))
        pool.append(
            base.Candidate(
                sequence,
                tuple(base.CODE_ORDER.index(code) for code in sequence),
                counts,
                coverage,
                product,
                2 * base.PAYOUT_FACTOR * product,
            )
        )
    return base.candidate_order(pool)


def top256(pool: list[base.Candidate]) -> list[base.Candidate] | None:
    try:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
    except ImportError as exc:
        raise base.FreezeError("structured optimizer dependency unavailable") from exc
    size = len(pool)
    k = 256
    total = 7 * k
    counts = [
        np.array([item.counts[index] for item in pool], dtype=float)
        for index in range(3)
    ]
    constraints = [LinearConstraint(np.ones(size), k, k)]
    for values, target, tol in zip(counts, (0.35, 0.35, 0.30), (0.05, 0.05, 0.05)):
        constraints.append(
            LinearConstraint(
                values,
                math.ceil((target - tol) * total),
                math.floor((target + tol) * total),
            )
        )
    units = np.array(
        [round(item.coverage * base.COVERAGE_SCORE_SCALE) for item in pool], dtype=float
    )
    lower = np.zeros(size)
    upper = np.ones(size)
    integrality = np.ones(size)
    options = {"mip_rel_gap": 0.0, "presolve": True}
    result = milp(
        c=-units,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=constraints,
        options=options,
    )
    if result.status == 2:
        return None
    if not result.success or result.x is None:
        raise base.FreezeError("structured TOP256 optimizer failed")
    bits = np.rint(result.x).astype(int)
    best_units = int(sum(units[index] for index, bit in enumerate(bits) if bit))
    exact = [*constraints, LinearConstraint(units, best_units, best_units)]
    for start in range(0, size, 32):
        stop = min(start + 32, size)
        objective = np.zeros(size)
        for offset, index in enumerate(range(start, stop)):
            objective[index] = -(2 ** (stop - start - offset - 1))
        lex = milp(
            c=objective,
            integrality=integrality,
            bounds=Bounds(lower, upper),
            constraints=exact,
            options=options,
        )
        if not lex.success or lex.x is None:
            raise base.FreezeError("structured TOP256 tie-break failed")
        for index, bit in zip(
            range(start, stop), np.rint(lex.x[start:stop]).astype(int)
        ):
            lower[index] = float(bit)
            upper[index] = float(bit)
    final = milp(
        c=np.zeros(size),
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=exact,
        options=options,
    )
    if not final.success or final.x is None:
        raise base.FreezeError("structured TOP256 verification failed")
    final_bits = np.rint(final.x).astype(int)
    if not np.allclose(final.x, final_bits, rtol=0.0, atol=1e-7):
        raise base.FreezeError("structured TOP256 returned non-integral selection")
    chosen = [item for item, bit in zip(pool, final_bits) if bit]
    if len(chosen) != k:
        raise base.FreezeError("structured TOP256 selected count mismatch")
    final_counts = [sum(item.counts[index] for item in chosen) for index in range(3)]
    bounds = tuple(
        (math.ceil((target - 0.05) * total), math.floor((target + 0.05) * total))
        for target in (0.35, 0.35, 0.30)
    )
    if any(
        not (low <= value <= high) for value, (low, high) in zip(final_counts, bounds)
    ):
        raise base.FreezeError("structured TOP256 ratio invariant failed")
    if (
        sum(round(item.coverage * base.COVERAGE_SCORE_SCALE) for item in chosen)
        != best_units
    ):
        raise base.FreezeError("structured TOP256 coverage optimum changed")
    return base.candidate_order(chosen)


def generate(legs: list[base.Leg]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    combos = []
    summary = []
    for issue in base.ISSUES:
        selected = base.select_legs(legs, issue)
        if selected is None:
            continue
        for threshold in THRESHOLDS:
            for arm, full_count, _double_count, expected_count, stake in STRUCTURES:
                assignment = choose_assignment(selected, full_count, threshold)
                if assignment is None:
                    summary.append(
                        {
                            "issue": issue,
                            "threshold": f"{threshold:.2f}",
                            "arm": arm,
                            "disposition": "NO_BET_THRESHOLD_UNAVAILABLE",
                            "combinations": "0",
                            "stake_yuan": str(stake),
                        }
                    )
                    if arm == "STRUCTURED_2F_5D_288":
                        summary.append(
                            {
                                "issue": issue,
                                "threshold": f"{threshold:.2f}",
                                "arm": "STRUCTURED_2F_5D_TOP256",
                                "disposition": "NO_BET_PARENT_THRESHOLD_UNAVAILABLE",
                                "combinations": "0",
                                "stake_yuan": "512",
                            }
                        )
                    continue
                pool = physical_pool(selected, assignment)
                if len(pool) != expected_count:
                    raise base.FreezeError("structured pool size mismatch")
                _append(combos, issue, threshold, arm, selected, pool)
                summary.append(
                    _summary(issue, threshold, arm, stake, assignment, pool, pool)
                )
                if arm == "STRUCTURED_2F_5D_288":
                    retained = top256(pool)
                    if retained is None:
                        summary.append(
                            {
                                "issue": issue,
                                "threshold": f"{threshold:.2f}",
                                "arm": "STRUCTURED_2F_5D_TOP256",
                                "disposition": "NO_BET_RATIO_FEASIBILITY_NOT_ESTABLISHED",
                                "combinations": "0",
                                "stake_yuan": "512",
                            }
                        )
                    else:
                        _append(
                            combos,
                            issue,
                            threshold,
                            "STRUCTURED_2F_5D_TOP256",
                            selected,
                            retained,
                        )
                        summary.append(
                            _summary(
                                issue,
                                threshold,
                                "STRUCTURED_2F_5D_TOP256",
                                512,
                                assignment,
                                pool,
                                retained,
                            )
                        )
    return combos, summary


def _summary(issue, threshold, arm, stake, assignment, full_pool, retained):
    full_mass = sum(item.coverage for item in full_pool)
    retained_mass = sum(item.coverage for item in retained)
    expected_gross = sum(item.coverage * item.gross_payout for item in retained)
    counts = [sum(item.counts[index] for item in retained) for index in range(3)]
    den = 7 * len(retained)
    details = ";".join(
        f"{position + 1}:{''.join(pair.codes)}:x{pair.excluded}:q{pair.excluded_q:.10f}:C{pair.coverage:.10f}:V{pair.value:.10f}:H{pair.conditional_sp:.10f}:min{pair.min_sp:.8f}:gm{pair.gm_sp:.8f}"
        for position, pair in zip(assignment["double_positions"], assignment["pairs"])
    )
    ids = (
        "\n".join(
            f"{issue}:{threshold:.2f}:{arm}:{ordinal:04d}:{''.join(item.sequence)}"
            for ordinal, item in enumerate(retained, 1)
        )
        + "\n"
    )
    return {
        "issue": issue,
        "threshold": f"{threshold:.2f}",
        "arm": arm,
        "disposition": "DIAGNOSTIC",
        "combinations": str(len(retained)),
        "stake_yuan": str(stake),
        "full_positions": "+".join(str(i + 1) for i in assignment["full_positions"]),
        "excluded_codes": "+".join(assignment["excluded_codes"]),
        "double_details": details,
        "package_coverage": f"{retained_mass:.12f}",
        "parent_package_coverage": f"{full_mass:.12f}",
        "expected_gross": f"{expected_gross:.12f}",
        "expected_roi": f"{expected_gross / stake - 1:.12f}",
        "probability_mass": f"{retained_mass:.12f}",
        "probability_mass_lost": f"{full_mass - retained_mass:.12f}",
        "n3": str(counts[0]),
        "n0": str(counts[1]),
        "n1": str(counts[2]),
        "pct3": f"{counts[0] / den:.10f}",
        "pct0": f"{counts[1] / den:.10f}",
        "pct1": f"{counts[2] / den:.10f}",
        "combination_ids_sha256": hashlib.sha256(ids.encode()).hexdigest(),
    }


def _append(output, issue, threshold, arm, legs, pool):
    for ordinal, item in enumerate(pool, 1):
        seq = "".join(item.sequence)
        cid = f"{issue}:{threshold:.2f}:{arm}:{ordinal:04d}:{seq}"
        output.append(
            {
                "combination_id": cid,
                "issue": issue,
                "threshold": f"{threshold:.2f}",
                "arm": arm,
                "ordinal": str(ordinal),
                "match_ids": "+".join(leg.match_id for leg in legs),
                "sequence": seq,
                "probability": f"{item.coverage:.12f}",
                "quoted_sp_product": f"{item.quoted_product:.12f}",
                "gross_payout": f"{item.gross_payout:.12f}",
            }
        )


def write(output_dir: Path, combos, summary, git_head: str):
    if output_dir.exists():
        raise base.FreezeError("output directory already exists")
    output_dir.mkdir(parents=True)
    files = []
    combo_fields = (
        "combination_id",
        "issue",
        "threshold",
        "arm",
        "ordinal",
        "match_ids",
        "sequence",
        "probability",
        "quoted_sp_product",
        "gross_payout",
    )
    summary_fields = (
        "issue",
        "threshold",
        "arm",
        "disposition",
        "combinations",
        "stake_yuan",
        "full_positions",
        "excluded_codes",
        "double_details",
        "package_coverage",
        "parent_package_coverage",
        "expected_gross",
        "expected_roi",
        "probability_mass",
        "probability_mass_lost",
        "n3",
        "n0",
        "n1",
        "pct3",
        "pct0",
        "pct1",
        "combination_ids_sha256",
    )
    for name, rows, fields in (
        ("structured_combinations.csv", combos, combo_fields),
        ("structured_summary.csv", summary, summary_fields),
    ):
        path = output_dir / name
        files.append(path)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    manifest = {
        "experiment": base.EXPERIMENT,
        "git_head": git_head,
        "base_generator_sha256": base.sha256_file(BASE_PATH),
        "structured_generator_sha256": base.sha256_file(Path(__file__)),
        "safe_input_sha256": base.AUTHORIZED_SAFE_INPUT_SHA256,
        "thresholds": list(THRESHOLDS),
        "outputs": {path.name: base.sha256_file(path) for path in files},
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_bytes(base.canonical_json(manifest))
    files.append(manifest_path)
    (output_dir / "SHA256SUMS").write_text(
        "".join(f"{base.sha256_file(path)}  {path.name}\n" for path in sorted(files)),
        encoding="utf-8",
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--git-head", required=True)
    args = parser.parse_args(argv)
    if len(args.git_head) != 40 or any(
        char not in "0123456789abcdef" for char in args.git_head
    ):
        raise base.FreezeError("invalid git head")
    config = base.read_config(args.config)
    legs = base.read_safe_projection(args.input, config)
    combos, summary = generate(legs)
    write(args.output_dir, combos, summary, args.git_head)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except base.FreezeError as exc:
        print(f"structured_freeze_failed={exc}", file=sys.stderr)
        raise SystemExit(2)
