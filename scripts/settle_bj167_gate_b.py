#!/usr/bin/env python3
"""Canonical Gate-B settlement and 100-seed ensemble report for #167."""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import gzip
import hashlib
import heapq
import itertools
import json
import math
import os
import random
import statistics
from collections import defaultdict, Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path

getcontext().prec = 96

CONTRACT = "BJ-HIST-N7-SEED-ENSEMBLE-001"
GA_MANIFEST = "3e9cd84d8714ee52c979da26b174bb32e0c1d1cdb5e72bca9e34cc80deeaa519"
GA_CONTENT = "3fb79bf49f15484067b8934e96c1b7a4a831762929c5892b15679d38b87d443b"
OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
N = 7
M_GRID = (32, 64, 128)
SEEDS = tuple(f"137{i:03d}" for i in range(1, 101))
PREFIXES = (3, 10, 25, 50, 100)
CODES = ("3", "1", "0")
STAKE = Decimal("2")
FACTOR = Decimal("0.65")
TAX_RATE = Decimal("0.20")
TAX_THRESHOLD = Decimal("10000")
MONEY_Q = Decimal("0.000001")
BOOTSTRAP_REPLICATES = 2000


def repo_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root(Path(__file__))
GATE_A = ROOT / "results/bj167_gate_a_preoutcome_v1"
OUTCOME = ROOT / "results/bj95_gate_b_outcome_settlement_v2r8"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_bundle(path: Path, expected_manifest: str, expected_content: str | None = None) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if sha(manifest_path) != expected_manifest:
        raise RuntimeError(f"manifest mismatch: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha(item) for item in path.iterdir() if item.is_file() and item.name != manifest_path.name}
    if declared != actual:
        raise RuntimeError(f"manifest coverage drift: {path}")
    if expected_content is not None and sha(path / "CONTENT_IDENTITY.json") != expected_content:
        raise RuntimeError(f"content identity mismatch: {path}")
    return declared


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: tuple[str, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader(); writer.writerows(rows)


def write_gzip(path: Path, rows: list[dict[str, object]], fields: tuple[str, ...]) -> None:
    import io
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            stream = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="raise")
            writer.writeheader(); writer.writerows(rows); stream.flush(); stream.detach()


def money(value: Decimal) -> str:
    return format(value.quantize(MONEY_Q), "f")


def ratio(value: Decimal | float | None) -> str:
    return "" if value is None else f"{float(value):.12f}"


def dec(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise RuntimeError(f"invalid {label}: {value!r}") from error
    if not result.is_finite():
        raise RuntimeError(f"non-finite {label}: {value!r}")
    return result


def stable_uniform(*parts: object) -> float:
    value = int.from_bytes(hashlib.sha256("|".join(str(part) for part in parts).encode()).digest()[:8], "big")
    return (value + 0.5) / (2 ** 64)


def truth_ordinal(code: str) -> int:
    value = 0
    for char in code:
        value = value * 3 + CODES.index(char)
    return value


def ticket_tax(gross: Decimal) -> Decimal:
    return gross * TAX_RATE if gross >= TAX_THRESHOLD else Decimal(0)


def rank_task(spec: tuple[str, str, tuple[tuple[float, float, float], ...], int]) -> tuple[str, dict[str, int]]:
    identity_id, signature, q_vectors, truth_idx = spec
    weights = tuple(math.prod(q_vectors[index][CODES.index(code)] for index, code in enumerate(ticket)) for ticket in itertools.product(CODES, repeat=N))
    if abs(sum(weights) - 1.0) > 2e-8:
        raise RuntimeError(f"Q mass drift: {identity_id}")
    ranks = {}
    for seed in SEEDS:
        truth_weight = weights[truth_idx]
        truth_key = math.inf if truth_weight <= 0 else -math.log(max(stable_uniform("bj137", "WOR", seed, signature, truth_idx), 1e-18)) / truth_weight
        rank = 1
        for ordinal, weight in enumerate(weights):
            if ordinal == truth_idx:
                continue
            key = math.inf if weight <= 0 else -math.log(max(stable_uniform("bj137", "WOR", seed, signature, ordinal), 1e-18)) / weight
            rank += int((key, ordinal) < (truth_key, truth_idx))
        ranks[seed] = rank
    return identity_id, ranks


IDENTITY_FIELDS = (
    "identity_id", "issue", "fold", "year", "issue_instance", "n", "M", "nominal_M", "effective_M", "seed",
    "saturation_status", "truth_sequence", "truth_ordinal", "truth_rank", "coverage_hit", "winning_ticket_count",
    "planned_draw_count", "executed_draw_count", "stake_yuan", "unique_ticket_count", "duplicate_ticket_count",
    "expected_sp_product_q", "actual_winning_sp_product", "gross_pre_tax_yuan", "taxable_winning_ticket_count",
    "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan", "no_tax_roi",
    "tax_adjusted_roi", "allocation_fingerprint", "winning_sp_sources", "settlement_status",
)
ISSUE_FIELDS = (
    "issue", "fold", "year", "issue_instance", "n", "M", "nominal_M", "effective_M", "seed", "selection_status",
    "planned_identity_count", "settled_identity_count", "planned_draw_count", "executed_draw_count", "stake_yuan",
    "full_control_stake_yuan", "winning_ticket_count", "hit_identity_count", "coverage_hit_rate", "gross_pre_tax_yuan",
    "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan", "no_tax_roi", "tax_adjusted_roi",
    "largest_signed_identity_net_yuan", "first_kickoff_ts",
)


def aggregate_template(part: dict[str, str], m: int, seed: str) -> dict[str, object]:
    return {"issue": part["issue"], "fold": part["fold"], "year": part["year"], "issue_instance": part["issue_instance"], "n": N, "M": m, "nominal_M": m, "effective_M": m, "seed": seed, "selection_status": part["selection_status"], "planned_identity_count": int(part["selected_identity_count"]), "settled_identity_count": 0, "planned_draw_count": int(part["selected_identity_count"]) * m, "executed_draw_count": 0, "stake_yuan": Decimal(0), "full_control_stake_yuan": Decimal(int(part["selected_identity_count"]) * (3 ** N) * 2), "winning_ticket_count": 0, "hit_identity_count": 0, "gross_pre_tax_yuan": Decimal(0), "tax_yuan": Decimal(0), "after_tax_gross_yuan": Decimal(0), "pre_tax_net_yuan": Decimal(0), "tax_adjusted_net_yuan": Decimal(0), "largest_signed_identity_net_yuan": Decimal(0), "first_kickoff_ts": ""}


def update_aggregate(agg: dict[str, object], row: dict[str, object]) -> None:
    agg["settled_identity_count"] = int(agg["settled_identity_count"]) + 1
    agg["executed_draw_count"] = int(agg["executed_draw_count"]) + int(row["executed_draw_count"])
    for field in ("stake_yuan", "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan"):
        agg[field] = dec(agg[field], field) + dec(row[field], field)
    agg["winning_ticket_count"] = int(agg["winning_ticket_count"]) + int(row["winning_ticket_count"])
    agg["hit_identity_count"] = int(agg["hit_identity_count"]) + int(row["coverage_hit"] == "YES")
    agg["largest_signed_identity_net_yuan"] = max(dec(agg["largest_signed_identity_net_yuan"], "largest"), dec(row["pre_tax_net_yuan"], "pre net"))
    kickoff = str(row.get("kickoff_ts", ""))
    if kickoff and (not agg["first_kickoff_ts"] or kickoff < agg["first_kickoff_ts"]):
        agg["first_kickoff_ts"] = kickoff


def finalize_aggregate(agg: dict[str, object]) -> dict[str, object]:
    stake = dec(agg["stake_yuan"], "stake")
    settled = int(agg["settled_identity_count"])
    out = dict(agg)
    for field in ("stake_yuan", "full_control_stake_yuan", "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan", "largest_signed_identity_net_yuan"):
        out[field] = money(dec(out[field], field))
    out["coverage_hit_rate"] = ratio(Decimal(int(agg["hit_identity_count"])) / settled if settled else None)
    out["no_tax_roi"] = ratio(dec(agg["pre_tax_net_yuan"], "pre net") / stake if stake else None)
    out["tax_adjusted_roi"] = ratio(dec(agg["tax_adjusted_net_yuan"], "tax net") / stake if stake else None)
    return out


def summarize(issue_rows: list[dict[str, object]], scope: str, scope_value: str) -> dict[str, object]:
    first = issue_rows[0]
    stake = sum((dec(row["stake_yuan"], "stake") for row in issue_rows), Decimal(0))
    gross = sum((dec(row["gross_pre_tax_yuan"], "gross") for row in issue_rows), Decimal(0))
    tax_net = sum((dec(row["tax_adjusted_net_yuan"], "tax net") for row in issue_rows), Decimal(0))
    pre = sum((dec(row["pre_tax_net_yuan"], "pre net") for row in issue_rows), Decimal(0))
    gross_by_issue = {str(row["issue_instance"]): dec(row["gross_pre_tax_yuan"], "gross") for row in issue_rows}
    signed_by_issue = {str(row["issue_instance"]): dec(row["pre_tax_net_yuan"], "pre net") for row in issue_rows}
    largest_issue, largest_signed = max(signed_by_issue.items(), key=lambda item: (item[1], item[0]), default=("", Decimal(0)))
    largest_gross = max(gross_by_issue.values(), default=Decimal(0)); total_gross = sum(gross_by_issue.values(), Decimal(0))
    hhi = sum((value / total_gross) ** 2 for value in gross_by_issue.values()) if total_gross else Decimal(0)
    ex_stake = stake - next((dec(row["stake_yuan"], "stake") for row in issue_rows if row["issue_instance"] == largest_issue), Decimal(0))
    out = {"scope": scope, "scope_value": scope_value, "n": N, "M": first["M"], "seed": first["seed"], "frozen_issue_count": len(issue_rows), "settled_issue_count": sum(int(row["settled_identity_count"]) > 0 for row in issue_rows), "planned_identity_count": sum(int(row["planned_identity_count"]) for row in issue_rows), "settled_identity_count": sum(int(row["settled_identity_count"]) for row in issue_rows), "planned_draw_count": sum(int(row["planned_draw_count"]) for row in issue_rows), "executed_draw_count": sum(int(row["executed_draw_count"]) for row in issue_rows), "stake_yuan": money(stake), "gross_pre_tax_yuan": money(gross), "tax_adjusted_net_yuan": money(tax_net), "pre_tax_net_yuan": money(pre), "no_tax_roi": ratio(pre / stake if stake else None), "tax_adjusted_roi": ratio(tax_net / stake if stake else None), "winning_ticket_count": sum(int(row["winning_ticket_count"]) for row in issue_rows), "hit_identity_count": sum(int(row["hit_identity_count"]) for row in issue_rows), "coverage_hit_rate": ratio(Decimal(sum(int(row["hit_identity_count"]) for row in issue_rows)) / sum(int(row["settled_identity_count"]) for row in issue_rows)) if sum(int(row["settled_identity_count"]) for row in issue_rows) else "", "gross_top_issue": max(gross_by_issue, key=gross_by_issue.get, default=""), "gross_top_issue_share": ratio(largest_gross / total_gross if total_gross else None), "gross_issue_hhi": ratio(hhi), "largest_signed_issue": largest_issue, "largest_signed_issue_net_yuan": money(largest_signed), "ex_largest_issue_no_tax_roi": ratio((pre - largest_signed) / ex_stake if ex_stake else None), "first_kickoff_ts": min((str(row["first_kickoff_ts"]) for row in issue_rows if row["first_kickoff_ts"]), default="")}
    return out


def svg_lines(path: Path, rows: list[dict[str, object]], title: str, field: str, y_label: str) -> None:
    width, height, left, right, top, bottom = 800, 430, 70, 30, 45, 75
    ns = [1, 2, 3, 4, 5] if field == "prefix_mean_roi" else list(M_GRID)
    values = [float(row[field]) for row in rows if row.get(field, "") not in ("", None)]
    low, high = (min(values, default=0), max(values, default=1)); pad = max((high - low) * .1, .03); low -= pad; high += pad
    if high <= low: high = low + 1
    def x(i: int) -> float: return left + i * (width - left - right) / max(1, len(ns) - 1)
    def y(v: float) -> float: return top + (high - v) / (high - low) * (height - top - bottom)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">', '<rect width="100%" height="100%" fill="white"/>', f'<text x="400" y="24" text-anchor="middle" font-family="sans-serif" font-size="16">{title}</text>']
    for idx in range(5):
        value = low + (high - low) * idx / 4; yy = y(value); lines.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{width-right}" y2="{yy:.2f}" stroke="#e5e7eb"/>'); lines.append(f'<text x="{left-8}" y="{yy+4:.2f}" text-anchor="end" font-family="monospace" font-size="10">{value:.3f}</text>')
    lines.append(f'<text x="16" y="220" transform="rotate(-90 16 220)" text-anchor="middle" font-family="sans-serif" font-size="12">{y_label}</text>')
    groups = defaultdict(list)
    for row in rows: groups[str(row.get("seed", "ensemble"))].append(row)
    colours = ("#2563eb", "#dc2626", "#059669", "#9333ea", "#ea580c")
    for gi, (group, items) in enumerate(sorted(groups.items())):
        items = sorted(items, key=lambda row: int(row.get("prefix_n", row.get("M", 0))))
        points = " ".join(f"{x(i):.2f},{y(float(row[field])):.2f}" for i, row in enumerate(items))
        lines.append(f'<polyline points="{points}" fill="none" stroke="{colours[gi % len(colours)]}" stroke-width="2"/>')
    lines.append(f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#111827"/><line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#111827"/>')
    for i, label in enumerate(ns): lines.append(f'<text x="{x(i):.2f}" y="{height-bottom+22}" text-anchor="middle" font-family="sans-serif" font-size="11">{label}</text>')
    lines.append("</svg>\n"); path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, default=ROOT / "results/bj167_gate_b_outcome_settlement_v1"); parser.add_argument("--head-start", default=""); parser.add_argument("--head-end", default="")
    args = parser.parse_args(); output = args.output.resolve()
    if output.exists(): raise RuntimeError(f"refusing overwrite: {output}")
    gate_manifest = verify_bundle(GATE_A, GA_MANIFEST, GA_CONTENT)
    outcome_manifest = verify_bundle(OUTCOME, OUTCOME_MANIFEST)
    if outcome_manifest.get("canonical_outcome_join.csv") != OUTCOME_PAYLOAD: raise RuntimeError("canonical outcome payload drift")
    identities = read_gzip(GATE_A / "identity_catalog.csv.gz"); roles = read_gzip(GATE_A / "role_vectors.csv.gz"); participation = read_csv(GATE_A / "issue_participation.csv"); allocations = read_gzip(GATE_A / "allocation_catalog.csv.gz")
    outcomes_rows = read_csv(OUTCOME / "canonical_outcome_join.csv"); outcomes = {row["match_id"]: row for row in outcomes_rows}
    if len(outcomes) != len(outcomes_rows): raise RuntimeError("duplicate canonical outcome match")
    for row in outcomes.values():
        if row["result_code"] not in CODES or row["settlement_quality"] != "trusted" or row["has_trusted_settlement"] != "1" or dec(row["winning_sp"], "winning SP") <= 0: raise RuntimeError("untrusted canonical outcome")
    identity_map = {row["identity_id"]: row for row in identities}; role_map = defaultdict(list)
    for row in roles: role_map[row["identity_id"]].append(row)
    allocation_map = {(row["identity_id"], row["seed"]): tuple(int(value) for value in row["allocation_ordinals"].split("|")) for row in allocations}
    rank_specs = []
    truth_by_identity = {}
    for identity in identities:
        ordered = sorted(role_map[identity["identity_id"]], key=lambda row: int(row["selection_rank"]))
        truth = "".join(outcomes[row["match_id"]]["result_code"] for row in ordered); truth_idx = truth_ordinal(truth); truth_by_identity[identity["identity_id"]] = truth
        q_vectors = tuple(tuple(float(row[f"q_weight{code}"]) for code in CODES) for row in ordered)
        rank_specs.append((identity["identity_id"], identity["selected_match_ids"], q_vectors, truth_idx))
    ranks: dict[tuple[str, str], int] = {}
    workers = max(1, min(8, os.cpu_count() or 1))
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        for identity_id, values in executor.map(rank_task, rank_specs, chunksize=1):
            for seed, rank in values.items(): ranks[(identity_id, seed)] = rank
    output.mkdir(parents=True)
    issue_meta = {(row["issue_instance"], int(row["n"])): row for row in participation}
    groups = {(row["issue_instance"], m, seed): aggregate_template(row, m, seed) for row in participation for m in M_GRID for seed in SEEDS}
    identity_rows = []
    truth_bins = Counter()
    for identity in identities:
        iid = identity["identity_id"]; ordered = sorted(role_map[iid], key=lambda row: int(row["selection_rank"])); truth = truth_by_identity[iid]; truth_idx = truth_ordinal(truth)
        product = Decimal(1); expected_product = Decimal(1); sources = set()
        for role in ordered:
            outcome = outcomes[role["match_id"]]; product *= dec(outcome["winning_sp"], "winning SP"); sources.add(outcome["winning_sp_source"]); expected_product *= sum(dec(role[f"q_weight{code}"], "q") * dec(role[f"predicted_sp{code}"], "predicted SP") for code in CODES)
        for seed in SEEDS:
            rank = ranks[(iid, seed)]; truth_bins["1-32" if rank <= 32 else "33-64" if rank <= 64 else "65-128" if rank <= 128 else ">128"] += 1
            ordinals = allocation_map[(iid, seed)]
            for m in M_GRID:
                selected = ordinals[:m]; hit = rank <= m; gross = STAKE * FACTOR * product if hit else Decimal(0); tax = ticket_tax(gross) if hit else Decimal(0); stake = STAKE * m; after = gross - tax
                row = {"identity_id": iid, "issue": identity["issue"], "fold": identity["fold"], "year": identity["year"], "issue_instance": identity["issue_instance"], "n": N, "M": m, "nominal_M": m, "effective_M": m, "seed": seed, "saturation_status": "PARTIAL_WOR", "truth_sequence": truth, "truth_ordinal": truth_idx, "truth_rank": rank, "coverage_hit": "YES" if hit else "NO", "winning_ticket_count": int(hit), "planned_draw_count": m, "executed_draw_count": m, "stake_yuan": money(stake), "unique_ticket_count": m, "duplicate_ticket_count": 0, "expected_sp_product_q": money(expected_product), "actual_winning_sp_product": money(product) if hit else "", "gross_pre_tax_yuan": money(gross), "taxable_winning_ticket_count": int(bool(tax)), "tax_yuan": money(tax), "after_tax_gross_yuan": money(after), "pre_tax_net_yuan": money(gross - stake), "tax_adjusted_net_yuan": money(after - stake), "no_tax_roi": ratio((gross - stake) / stake), "tax_adjusted_roi": ratio((after - stake) / stake), "allocation_fingerprint": hashlib.sha256(json.dumps(selected, separators=(",", ":")).encode()).hexdigest(), "winning_sp_sources": ";".join(sorted(sources)), "settlement_status": "SETTLED"}
                identity_rows.append(row)
                update_aggregate(groups[(identity["issue_instance"], m, seed)], {**row, "kickoff_ts": ordered[0]["kickoff_ts"]})
    identity_rows.sort(key=lambda row: (int(row["year"]), int(row["issue"]), str(row["seed"]), int(row["M"]), row["identity_id"]))
    write_gzip(output / "identity_settlement.csv.gz", identity_rows, IDENTITY_FIELDS)
    issue_rows = [finalize_aggregate(groups[key]) for key in sorted(groups, key=lambda key: (int(key[0].split("@")[0]), key[0], int(key[1]), key[2]))]
    write_csv(output / "issue_settlement.csv", issue_rows, ISSUE_FIELDS)
    seed_rows = []
    for m in M_GRID:
        for seed in SEEDS:
            support = [row for row in issue_rows if int(row["M"]) == m and row["seed"] == seed]
            seed_rows.append(summarize(support, "SEED", seed))
    seed_fields = tuple(seed_rows[0].keys()); write_csv(output / "seed_summary.csv", seed_rows, seed_fields)
    ensemble_rows = []
    for m in M_GRID:
        values = [float(row["no_tax_roi"]) for row in seed_rows if int(row["M"]) == m]
        ordered_values = sorted(values); mean = statistics.fmean(values); sd = statistics.stdev(values) if len(values) > 1 else 0.0
        ensemble_rows.append({"n": N, "M": m, "seed_count": len(values), "mean_roi": f"{mean:.12f}", "median_roi": f"{statistics.median(values):.12f}", "sd_roi": f"{sd:.12f}", "mcse_roi": f"{sd / math.sqrt(len(values)):.12f}", "min_roi": f"{min(values):.12f}", "max_roi": f"{max(values):.12f}", "p10_roi": f"{ordered_values[max(0, math.ceil(len(values)*.10)-1)]:.12f}", "p25_roi": f"{ordered_values[max(0, math.ceil(len(values)*.25)-1)]:.12f}", "p75_roi": f"{ordered_values[max(0, math.ceil(len(values)*.75)-1)]:.12f}", "p90_roi": f"{ordered_values[max(0, math.ceil(len(values)*.90)-1)]:.12f}", "positive_seed_fraction": f"{sum(v > 0 for v in values)/len(values):.12f}", "primary_metric": "pre-tax no_tax_roi"})
    write_csv(output / "ensemble_summary.csv", ensemble_rows, tuple(ensemble_rows[0].keys()))
    prefix_rows = []
    for m in M_GRID:
        values = {row["seed"]: float(row["no_tax_roi"]) for row in seed_rows if int(row["M"]) == m}
        for prefix in PREFIXES:
            selected = [values[seed] for seed in SEEDS[:prefix]]; prefix_rows.append({"M": m, "prefix_n": prefix, "prefix_mean_roi": f"{statistics.fmean(selected):.12f}", "prefix_median_roi": f"{statistics.median(selected):.12f}", "prefix_positive_fraction": f"{sum(v > 0 for v in selected)/len(selected):.12f}"})
    write_csv(output / "prefix_convergence.csv", prefix_rows, tuple(prefix_rows[0].keys()))
    # Fixed three-seed reference and 100-seed delta, with no retuning.
    ref = {m: statistics.fmean(float(row["no_tax_roi"]) for row in seed_rows if int(row["M"]) == m and row["seed"] in SEEDS[:3]) for m in M_GRID}
    deltas = [{"M": m, "three_seed_mean_roi": f"{ref[m]:.12f}", "hundred_seed_mean_roi": ensemble_rows[index]["mean_roi"], "delta_roi": f"{float(ensemble_rows[index]['mean_roi'])-ref[m]:.12f}"} for index, m in enumerate(M_GRID)]
    write_csv(output / "three_vs_hundred_seed_delta.csv", deltas, tuple(deltas[0].keys()))
    bootstrap_rows = []
    rng = random.Random(167159)
    for m in M_GRID:
        support = [row for row in issue_rows if int(row["M"]) == m and row["seed"] == "137064" and float(row["stake_yuan"]) > 0]
        values = []
        for _ in range(BOOTSTRAP_REPLICATES):
            sample = [support[rng.randrange(len(support))] for _ in support]; stake = sum((dec(row["stake_yuan"], "stake") for row in sample), Decimal(0)); net = sum((dec(row["pre_tax_net_yuan"], "net") for row in sample), Decimal(0)); values.append(float(net / stake if stake else 0))
        values.sort(); bootstrap_rows.append({"M": m, "seed": "137064", "cluster": "issue_instance", "replicates": BOOTSTRAP_REPLICATES, "point_estimate": f"{float(next(row['no_tax_roi'] for row in seed_rows if int(row['M']) == m and row['seed']=='137064')):.12f}", "ci95_low": f"{values[50]:.12f}", "ci95_high": f"{values[1949]:.12f}", "positive_fraction": f"{sum(value > 0 for value in values)/len(values):.12f}"})
    write_csv(output / "issue_cluster_bootstrap.csv", bootstrap_rows, tuple(bootstrap_rows[0].keys()))
    variance_rows = []
    for m, ensemble in zip(M_GRID, ensemble_rows):
        boot = next(row for row in bootstrap_rows if int(row["M"]) == m); seed_var = float(ensemble["sd_roi"]) ** 2; boot_half = (float(boot["ci95_high"]) - float(boot["ci95_low"])) / 3.92; variance_rows.append({"M": m, "allocator_seed_variance": f"{seed_var:.12f}", "allocator_seed_sd": ensemble["sd_roi"], "issue_outcome_bootstrap_sd_proxy": f"{boot_half:.12f}", "variance_note": "seed variation is Monte Carlo allocation uncertainty; issue bootstrap is historical outcome/issue uncertainty; seeds are not football histories"})
    write_csv(output / "variance_decomposition.csv", variance_rows, tuple(variance_rows[0].keys()))
    rank_rows = [{"rank_bin": key, "identity_seed_count": count, "fraction": f"{count/(len(identities)*len(SEEDS)):.12f}"} for key, count in sorted(truth_bins.items())]; write_csv(output / "truth_rank_distribution.csv", rank_rows, tuple(rank_rows[0].keys()))
    overlap_rows = []
    allocation_sets = {(row["identity_id"], row["seed"]): set(row["allocation_ordinals"].split("|")[:64]) for row in allocations}
    for left_index in (0, 1, 2, 3, 4):
        right_index = left_index + 1 if left_index < 4 else 99
        left_seed, right_seed = SEEDS[left_index], SEEDS[right_index]; shares = []
        for identity in identities:
            left = allocation_sets[(identity["identity_id"], left_seed)]; right = allocation_sets[(identity["identity_id"], right_seed)]; shares.append(len(left & right) / 64)
        overlap_rows.append({"M": 64, "seed_left": left_seed, "seed_right": right_seed, "identity_count": len(shares), "mean_shared_ticket_fraction": f"{statistics.fmean(shares):.12f}", "min_shared_ticket_fraction": f"{min(shares):.12f}", "max_shared_ticket_fraction": f"{max(shares):.12f}"})
    write_csv(output / "seed_overlap_summary.csv", overlap_rows, tuple(overlap_rows[0].keys()))
    svg_lines(output / "seed_ensemble_roi.svg", [{"seed": "ensemble", "M": int(row["M"]), "prefix_n": int(row["M"]), "prefix_mean_roi": row["mean_roi"]} for row in ensemble_rows], "#167 N7 seed-ensemble ROI by M", "prefix_mean_roi", "mean pre-tax ROI")
    svg_lines(output / "prefix_convergence.svg", [row for row in prefix_rows if int(row["M"]) == 64], "#167 N7 M64 prefix convergence", "prefix_mean_roi", "prefix mean pre-tax ROI")
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    card = {"issue": 167, "contract": CONTRACT, "stage": "GATE_B_OUTCOME_SETTLEMENT_N7_SEED_ENSEMBLE", "generated_at_utc": generated, "head_start": args.head_start, "head_end": args.head_end, "gate_a_manifest": GA_MANIFEST, "gate_a_content_identity": GA_CONTENT, "outcome_manifest": OUTCOME_MANIFEST, "outcome_payload": OUTCOME_PAYLOAD, "n": N, "M_grid": list(M_GRID), "seed_count": len(SEEDS), "identity_count": len(identities), "identity_settlement_rows": len(identity_rows), "issue_settlement_rows": len(issue_rows), "bootstrap_replicates": BOOTSTRAP_REPLICATES, "primary_metric": "pre-tax no_tax_roi", "tax_secondary": True, "tax_rule": "20% per independent winning ¥2 ticket gross >= ¥10000; no pooling", "promotion_authorized": False, "no_purchase_production_or_betting_authority": True}
    binding = {"issue": 167, "contract": CONTRACT, "gate_a_manifest": GA_MANIFEST, "gate_a_content_identity": GA_CONTENT, "canonical_outcome_manifest": OUTCOME_MANIFEST, "canonical_outcome_payload": OUTCOME_PAYLOAD, "outcome_loader": "read-only canonical_outcome_join.csv", "runner_head": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    interpretation = "# #167 N7 100-seed ensemble\n\nN=7 is fixed. M64 is primary; M32/M128 are sensitivities. The 100 seeds are allocator Monte Carlo draws, not 100 independent football histories. The ensemble mean/median and issue-cluster bootstrap must be read together; a positive seed mean alone is descriptive and does not authorize promotion.\n\nEach winning ¥2 ticket is taxed independently at the frozen rule; no issue/policy pooling is used. Prefix convergence is descriptive only. Any positive cluster remains subject to signed-largest issue/year exclusions and held-out validation.\n"
    output.mkdir(parents=True, exist_ok=True)
    (output / "validation_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "source_binding.json").write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "interpretation.md").write_text(interpretation, encoding="utf-8")
    (output / "README.md").write_text("# #167 Gate B\n\nCanonical settlement of the immutable N7/100-seed Gate-A freeze. Pre-tax ROI is primary, tax secondary, and no promotion or purchase authority is granted.\n", encoding="utf-8")
    import shutil
    shutil.copy2(Path(__file__), output / "settlement_runner.py")
    content = {"package": output.name, "contract": CONTRACT, "files": {item.name: sha(item) for item in sorted(output.iterdir()) if item.is_file()}}
    (output / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {item.name: sha(item) for item in sorted(output.iterdir()) if item.is_file()}
    (output / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "manifest_sha256": sha(output / "SHA256SUMS.json"), "content_sha256": sha(output / "CONTENT_IDENTITY.json"), "identity_rows": len(identity_rows), "issue_rows": len(issue_rows), "ensemble_rows": len(ensemble_rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
