#!/usr/bin/env python3
"""Independent read-only validation of #151's fixed-candidate WOR cluster."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import random
import shutil
import subprocess
from collections import defaultdict
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 80
MONEY = Decimal("0.000001")
STAKE = Decimal("2")
FACTOR = Decimal("0.65")
TAX_RATE = Decimal("0.20")
TAX_THRESHOLD = Decimal("10000")
FULL = 2187
SEEDS = ("137001", "137002", "137003")
CODES = ("3", "1", "0")
GA_MANIFEST = "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6"
GB_MANIFEST = "7b88be8af887674875f831f2da0951a1bf7664041f40c10be00d09194ce6fbe2"
OUTCOME_SHA = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_package(path: Path, expected: str) -> None:
    manifest_path = path / "SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {name: sha(path / name) for name in manifest}
    if actual != manifest or sha(manifest_path) != expected:
        raise RuntimeError(f"immutable package mismatch: {path}")


def stable_uniform(*parts: object) -> float:
    token = "|".join(str(part) for part in parts).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
    return (value + 0.5) / (2 ** 64)


def rank(weights: list[float], truth: int, seed: str, signature: str) -> int:
    target = -math.log(max(stable_uniform("bj137", "WOR", seed, signature, truth), 1e-18)) / weights[truth]
    return 1 + sum(
        -math.log(max(stable_uniform("bj137", "WOR", seed, signature, ordinal), 1e-18)) / weight < target
        for ordinal, weight in enumerate(weights) if ordinal != truth
    )


def weights(roles: list[dict[str, str]]) -> list[float]:
    output = [1.0]
    for role in roles:
        vector = [float(role[f"q_weight{code}"]) for code in CODES]
        if any(value <= 0 or not math.isfinite(value) for value in vector) or abs(sum(vector) - 1) > 1e-8:
            raise RuntimeError("invalid frozen Q vector")
        output = [prefix * value for prefix in output for value in vector]
    if len(output) != FULL or abs(sum(output) - 1) > 1e-8:
        raise RuntimeError("Q ticket normalization drift")
    return output


def ticket_tax(gross: Decimal) -> Decimal:
    return (gross * TAX_RATE).quantize(MONEY) if gross >= TAX_THRESHOLD else Decimal(0)


def load_items(root: Path) -> tuple[dict[str, dict[str, str]], list[dict[str, object]], list[int]]:
    gate_a = root / "results/bj151_gate_a_preoutcome_v1"
    with (gate_a / "candidate_cohort.csv").open(newline="", encoding="utf-8") as handle:
        cohort = {row["issue_instance"]: row for row in csv.DictReader(handle)}
    role_map: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with gzip.open(gate_a / "candidate_role_vectors.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            role_map[(row["issue_instance"], row["portfolio_id"])].append(row)
    with (root / "results/bj95_gate_b_outcome_settlement_v2r8/canonical_outcome_join.csv").open(newline="", encoding="utf-8") as handle:
        outcomes = {row["match_id"]: row for row in csv.DictReader(handle)}
    with gzip.open(gate_a / "candidate_identities.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        identity_rows = list(csv.DictReader(handle))
    items: list[dict[str, object]] = []
    for identity in identity_rows:
        key = identity["issue_instance"], identity["portfolio_id"]
        roles = sorted(role_map[key], key=lambda row: int(row["selection_rank"]))
        truth = 0
        product = Decimal(1)
        complete = True
        for role in roles:
            outcome = outcomes.get(role["match_id"])
            if outcome is None:
                complete = False
                continue
            if outcome["result_code"] not in CODES or outcome["settlement_quality"] != "trusted" or outcome["has_trusted_settlement"] != "1":
                raise RuntimeError("untrusted final outcome")
            truth = truth * 3 + CODES.index(outcome["result_code"])
            product *= Decimal(outcome["winning_sp"])
        items.append({
            "issue": identity["issue_instance"], "portfolio": identity["portfolio_id"],
            "year": cohort[identity["issue_instance"]]["year"], "fold": cohort[identity["issue_instance"]]["fold"],
            "roles": roles, "signature": identity["selected_match_ids"], "complete": complete,
            "truth": truth if complete else None,
            "gross": (STAKE * FACTOR * product).quantize(MONEY) if complete else None,
        })
    counts = defaultdict(int); complete_counts = defaultdict(int)
    for item in items:
        counts[item["issue"]] += 1
        complete_counts[item["issue"]] += int(item["complete"])
    complete_issues = {issue for issue in counts if counts[issue] == complete_counts[issue] == 4}
    if len(cohort) != 348 or len(items) != 1356 or len(complete_issues) != 254:
        raise RuntimeError("support denominator drift")
    for item in items:
        item["issue_complete"] = item["issue"] in complete_issues
    with (gate_a / "dense_m_grid.csv").open(newline="", encoding="utf-8") as handle:
        grid = [int(row["M"]) for row in csv.DictReader(handle)]
    if len(grid) != 58 or grid[-1] != FULL:
        raise RuntimeError("dense M grid drift")
    return cohort, items, grid


RANKS: dict[tuple[str, str], int] = {}


def issue_surface(items: list[dict[str, object]], m_value: int, seed: str) -> tuple[dict[str, object], list[dict[str, object]]]:
    by_issue: dict[str, dict[str, object]] = defaultdict(lambda: {"gross": Decimal(0), "stake": Decimal(0), "hits": 0, "year": None, "fold": None})
    for item in items:
        if not item["issue_complete"]:
            continue
        key = (str(item["portfolio"]), seed)
        if key not in RANKS:
            RANKS[key] = rank(weights(item["roles"]), int(item["truth"]), seed, str(item["signature"]))
        bucket = by_issue[str(item["issue"])]
        bucket["year"], bucket["fold"] = item["year"], item["fold"]
        bucket["stake"] += STAKE * m_value
        if RANKS[key] <= m_value:
            bucket["hits"] += 1
            bucket["gross"] += item["gross"]
    rows = [{"issue": issue, **bucket} for issue, bucket in by_issue.items()]
    stake = sum((row["stake"] for row in rows), Decimal(0))
    gross = sum((row["gross"] for row in rows), Decimal(0))
    tax = Decimal(0)
    hit_tickets = 0
    for item in items:
        if item["issue_complete"] and RANKS[(str(item["portfolio"]), seed)] <= m_value:
            hit_tickets += 1
            tax += ticket_tax(item["gross"])
    top = max(rows, key=lambda row: row["gross"])
    ex_stake = stake - top["stake"]
    ex_roi = (gross - top["gross"] - ex_stake) / ex_stake
    shares = [(row["gross"] / gross) if gross else Decimal(0) for row in rows]
    return ({
        "seed": seed, "M": m_value, "issue_count": len(rows), "stake_yuan": stake, "gross_yuan": gross,
        "tax_yuan": tax, "no_tax_roi": (gross - stake) / stake, "tax_adjusted_roi": (gross - stake - tax) / stake,
        "coverage_rate": Decimal(sum(row["hits"] > 0 for row in rows)) / len(rows), "winning_ticket_count": hit_tickets,
        "top_issue_share": top["gross"] / gross if gross else Decimal(0), "issue_hhi": sum(value * value for value in shares),
        "largest_issue_excluded_roi": ex_roi,
    }, rows)


def bootstrap(rows: list[dict[str, object]], seed: str, m_value: int) -> dict[str, object]:
    token = hashlib.sha256(f"BJ-EV-151-WOR-M64-001|BOOTSTRAP|{seed}|{m_value}".encode()).digest()[:8]
    rng = random.Random(int.from_bytes(token, "big")); n = len(rows); samples = []
    for _ in range(1000):
        drawn = [rows[rng.randrange(n)] for _ in range(n)]
        stake = sum((row["stake"] for row in drawn), Decimal(0)); gross = sum((row["gross"] for row in drawn), Decimal(0))
        samples.append((gross - stake) / stake)
    samples.sort()
    return {"seed": seed, "M": m_value, "replicates": 1000, "ci95_low": samples[24], "ci95_high": samples[974], "positive_fraction": Decimal(sum(value > 0 for value in samples)) / 1000}


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader()
        for row in rows:
            writer.writerow({key: str(value) if isinstance(value, Decimal) else value for key, value in row.items()})


def default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, default=None); parser.add_argument("--head-start", default=""); parser.add_argument("--head-end", default="")
    args = parser.parse_args()
    candidates = [Path(__file__).resolve().parents[1], Path(__file__).resolve().parents[2]]
    root = next((candidate for candidate in candidates if (candidate / ".git").exists() and (candidate / "results").is_dir()), None)
    if root is None:
        raise RuntimeError("repository root unavailable")
    output = args.output.resolve() if args.output else root / "results/bj154_independent_ev_v1"
    if output.exists():
        raise RuntimeError(f"refusing overwrite: {output}")
    output.mkdir(parents=True)
    gate_a = root / "results/bj151_gate_a_preoutcome_v1"; gate_b = root / "results/bj151_gate_b_outcome_settlement_v1"; outcome = root / "results/bj95_gate_b_outcome_settlement_v2r8/canonical_outcome_join.csv"
    verify_package(gate_a, GA_MANIFEST); verify_package(gate_b, GB_MANIFEST)
    if sha(outcome) != OUTCOME_SHA:
        raise RuntimeError("outcome payload drift")
    sampler = (root / "scripts/settle_bj137_sampling_gate_b.py").read_text(encoding="utf-8")
    sampler_checks = all(text in sampler for text in (
        'stable_uniform("bj137", "WR", seed, key, draw - 1)',
        'stable_uniform("bj137", "WOR", seed, key, truth)',
        'stable_uniform("bj137", "WOR", seed, key, ordinal)',
        "(value + 0.5) / (2 ** 64)",
    ))
    if not sampler_checks:
        raise RuntimeError("#137 sampler source contract drift")
    cohort, items, grid = load_items(root); curve = []; m64 = []; issue_rows = []; scope_rows = []; boot_rows = []
    for m_value in grid[:-1]:
        for seed in SEEDS:
            summary, issues = issue_surface(items, m_value, seed); curve.append(summary)
            if m_value == 64:
                m64.append(summary); issue_rows.extend({**row, "seed": seed, "M": m_value} for row in issues); boot_rows.append(bootstrap(issues, seed, m_value))
                for scope in ("year", "fold"):
                    for value in sorted({row[scope] for row in issues}):
                        selected = [row for row in issues if row[scope] == value]; stake = sum((row["stake"] for row in selected), Decimal(0)); gross = sum((row["gross"] for row in selected), Decimal(0))
                        scope_rows.append({"scope": scope, "scope_value": value, "seed": seed, "M": m_value, "issue_count": len(selected), "stake_yuan": stake, "gross_yuan": gross, "no_tax_roi": (gross - stake) / stake})
                for value in sorted({row["year"] for row in issues}):
                    selected = [row for row in issues if row["year"] != value]; stake = sum((row["stake"] for row in selected), Decimal(0)); gross = sum((row["gross"] for row in selected), Decimal(0))
                    scope_rows.append({"scope": "LOYO", "scope_value": value, "seed": seed, "M": m_value, "issue_count": len(selected), "stake_yuan": stake, "gross_yuan": gross, "no_tax_roi": (gross - stake) / stake})
    package_rows = {(row["M"], row["seed"]): Decimal(row["no_tax_roi"]) for row in csv.DictReader((gate_b / "m_grid_surface_summary.csv").open(newline="", encoding="utf-8")) if row["scope"] == "ALL" and row["sampling_role"] == "SENSITIVITY_WOR_FIXED_CANDIDATE"}
    mismatches = [{"M": row["M"], "seed": row["seed"]} for row in curve if abs(row["no_tax_roi"] - package_rows[(str(row["M"]), row["seed"])]) > Decimal("0.000000000002")]
    if mismatches:
        raise RuntimeError(f"independent/package mismatch: {mismatches[:3]}")
    write_csv(output / "wor_dense_curve.csv", curve); write_csv(output / "m64_issue_metrics.csv", issue_rows); write_csv(output / "m64_scope_metrics.csv", scope_rows); write_csv(output / "m64_bootstrap.csv", boot_rows)
    means = {str(m): sum((row["no_tax_roi"] for row in curve if row["M"] == m), Decimal(0)) / 3 for m in (48, 64, 80, 128)}
    complete_items = [item for item in items if item["issue_complete"]]
    full_stake = STAKE * FULL * len(complete_items)
    full_gross = sum((item["gross"] for item in complete_items), Decimal(0))
    summary = {
        "contract": "BJ-EV-151-WOR-M64-001", "target_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(), "head_start": args.head_start, "head_end": args.head_end,
        "gate_a_manifest": GA_MANIFEST, "gate_b_manifest": GB_MANIFEST, "outcome_payload": OUTCOME_SHA, "frozen_issue_count": len(cohort), "frozen_identity_count": len(items), "settled_issue_count": 254,
        "sampler_namespace_verified": sampler_checks, "m64_no_tax_roi_by_seed": {row["seed"]: row["no_tax_roi"] for row in m64}, "m64_tax_adjusted_roi_by_seed": {row["seed"]: row["tax_adjusted_roi"] for row in m64},
        "m64_mean_no_tax_roi": sum((row["no_tax_roi"] for row in m64), Decimal(0)) / 3, "nearby_mean_no_tax_roi": means, "package_surface_mismatches": len(mismatches),
        "independent_full_no_tax_roi": (full_gross - full_stake) / full_stake,
        "tax_rule": "20pct per individual winning ticket gross >= 10000; no aggregate pooling", "multiple_testing_rule": "58 M points x 3 seeds are descriptive; no post-outcome promotion", "decision": "PASS_REPRODUCTION_ONLY_STRICT_EV_REQUIRED",
    }
    (output / "validation_card.json").write_text(json.dumps(summary, default=default, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "source_census.csv").write_text("source,sha256\nbj151_gate_a_preoutcome_v1," + GA_MANIFEST + "\nbj151_gate_b_outcome_settlement_v1," + GB_MANIFEST + "\nbj95 canonical_outcome_join.csv," + OUTCOME_SHA + "\n", encoding="utf-8")
    (output / "README.md").write_text("# #154 independent EV validation\n\nIndependent detached-checkout recomputation of fixed #137 Q-weighted WOR ranks. No candidate, M, seed, sampler, outcome, or tax rule is changed. PASS means reproduction only; strict EV remains required. Replay with `python3 validation_runner.py --output <new-dir>`.\n", encoding="utf-8")
    shutil.copy2(__file__, output / "validation_runner.py")
    manifest = {path.name: sha(path) for path in sorted(output.iterdir()) if path.is_file()}
    (output / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "manifest_sha256": sha(output / "SHA256SUMS.json"), "summary": summary}, default=default, sort_keys=True))


if __name__ == "__main__":
    main()
