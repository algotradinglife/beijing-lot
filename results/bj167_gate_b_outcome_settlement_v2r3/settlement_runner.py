#!/usr/bin/env python3
"""One-shot Gate-B settlement for #167's controlling #137/#151 cohort.

The candidate arm is exact Q-informed WOR on the frozen NO_GATE/K4 identities;
the FULL row is an exact-K4 economic control on the identical support.  Seeds
are allocator Monte Carlo draws, never football histories.  All tax is applied
to each independent winning ticket before any aggregation.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import itertools
import json
import math
import random
import shutil
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path

getcontext().prec = 96

CONTRACT = "BJ-HIST-N7-SEED-ENSEMBLE-002"
GATE_A_MANIFEST = "7d6698705a61c416387ae6aee713751b05f337147943e9d781a46252317076d4"
GATE_A_CONTENT = "0c4c3a6103d37e94707ac4837480af16d8e1bbc27472821edc106920fd66288f"
GATE_A_151_MANIFEST = "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6"
OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
N, FULL_TICKETS, TOP_K = 7, 2187, 128
M_GRID = (32, 64, 128)
SEEDS = tuple(f"137{i:03d}" for i in range(1, 101))
PREFIXES = (3, 10, 25, 50, 100)
CODES = ("3", "1", "0")
STAKE = Decimal("2")
FACTOR = Decimal("0.65")
TAX_RATE = Decimal("0.20")
TAX_THRESHOLD = Decimal("10000")
MONEY_Q = Decimal("0.000001")
BOOTSTRAP_REPLICATES = 20_000


def repo_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root(Path(__file__))
GATE_A = ROOT / "results/bj167_gate_a_preoutcome_v2"
OUTCOME = ROOT / "results/bj95_gate_b_outcome_settlement_v2r8"
REFERENCE_151 = ROOT / "results/bj151_gate_b_outcome_settlement_v1"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_bundle(path: Path, expected: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if sha(manifest_path) != expected:
        raise RuntimeError(f"manifest mismatch: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha(item) for item in path.iterdir() if item.is_file() and item.name != manifest_path.name}
    if declared != actual:
        raise RuntimeError(f"manifest coverage drift: {path}")
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


def dec(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise RuntimeError(f"invalid {label}: {value!r}") from error
    if not result.is_finite():
        raise RuntimeError(f"non-finite {label}: {value!r}")
    return result


def money(value: Decimal | None) -> str:
    return "" if value is None else format(value.quantize(MONEY_Q), "f")


def ratio(value: Decimal | float | None) -> str:
    return "" if value is None else f"{float(value):.12f}"


def ticket_tax(gross: Decimal) -> Decimal:
    return gross * TAX_RATE if gross >= TAX_THRESHOLD else Decimal(0)


def stable_uniform(*parts: object) -> float:
    token = "|".join(str(part) for part in parts).encode("utf-8")
    return (int.from_bytes(hashlib.sha256(token).digest()[:8], "big") + 0.5) / (2 ** 64)


def truth_ordinal(code: str) -> int:
    value = 0
    for char in code:
        value = value * 3 + CODES.index(char)
    return value


def q_weights(roles: list[dict[str, str]]) -> tuple[float, ...]:
    weights = tuple(math.prod(float(roles[index][f"q_weight{code}"]) for index, code in enumerate(CODES)) for _ in ())
    # The explicit product below keeps the ticket order byte-compatible with
    # #137/#151 (itertools.product(CODES, repeat=7), ordinal 0..2186).
    weights = tuple(math.prod(float(roles[index][f"q_weight{code}"]) for index, code in enumerate(ticket)) for ticket in itertools.product(CODES, repeat=N))
    if abs(sum(weights) - 1.0) > 2e-8:
        raise RuntimeError("Q ticket-space mass drift")
    return weights


def truth_rank(weights: tuple[float, ...], truth_idx: int, seed: str, signature: str) -> int:
    target_weight = weights[truth_idx]
    target = math.inf if target_weight <= 0 else -math.log(max(stable_uniform("bj137", "WOR", seed, signature, truth_idx), 1e-18)) / target_weight
    rank = 1
    for ordinal, weight in enumerate(weights):
        if ordinal == truth_idx:
            continue
        key = math.inf if weight <= 0 else -math.log(max(stable_uniform("bj137", "WOR", seed, signature, ordinal), 1e-18)) / weight
        rank += int((key, ordinal) < (target, truth_idx))
    return rank


def percentile(values: list[float], q: float) -> float:
    return sorted(values)[max(0, math.ceil(len(values) * q) - 1)]


def signed_metrics(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        raise RuntimeError("empty metric slice")
    stake = sum((dec(row["stake_yuan"], "stake") for row in rows), Decimal(0))
    gross = sum((dec(row["gross_pre_tax_yuan"], "gross") for row in rows), Decimal(0))
    tax = sum((dec(row["tax_yuan"], "tax") for row in rows), Decimal(0))
    pre = sum((dec(row["pre_tax_net_yuan"], "pre net") for row in rows), Decimal(0))
    after = sum((dec(row["after_tax_gross_yuan"], "after gross") for row in rows), Decimal(0))
    tax_net = sum((dec(row["tax_adjusted_net_yuan"], "tax net") for row in rows), Decimal(0))
    issue_net = defaultdict(Decimal); issue_stake = defaultdict(Decimal); issue_gross = defaultdict(Decimal)
    year_net = defaultdict(Decimal); year_stake = defaultdict(Decimal); year_gross = defaultdict(Decimal)
    for row in rows:
        issue = str(row["issue_instance"]); year = str(row["year"])
        issue_net[issue] += dec(row["pre_tax_net_yuan"], "issue net"); issue_stake[issue] += dec(row["stake_yuan"], "issue stake"); issue_gross[issue] += dec(row["gross_pre_tax_yuan"], "issue gross")
        year_net[year] += dec(row["pre_tax_net_yuan"], "year net"); year_stake[year] += dec(row["stake_yuan"], "year stake"); year_gross[year] += dec(row["gross_pre_tax_yuan"], "year gross")
    largest_issue, largest_issue_net = max(issue_net.items(), key=lambda x: (x[1], x[0]), default=("", Decimal(0)))
    largest_year, largest_year_net = max(year_net.items(), key=lambda x: (x[1], x[0]), default=("", Decimal(0)))
    total_gross = sum(issue_gross.values(), Decimal(0)); top_issue = max(issue_gross, key=issue_gross.get, default="")
    hhi = sum((value / total_gross) ** 2 for value in issue_gross.values()) if total_gross else Decimal(0)
    ordered = sorted(rows, key=lambda row: (str(row.get("first_kickoff_ts", "")), str(row["issue_instance"])))
    cumulative = Decimal(0); peak = Decimal(0); drawdown = Decimal(0); miss = 0; longest = 0
    for row in ordered:
        if dec(row["stake_yuan"], "stake") <= 0:
            continue
        cumulative += dec(row["pre_tax_net_yuan"], "net"); peak = max(peak, cumulative); drawdown = max(drawdown, peak - cumulative)
        if int(row["coverage_hits"]) > 0: miss = 0
        else: miss += 1; longest = max(longest, miss)
    ex_issue_stake = stake - issue_stake.get(largest_issue, Decimal(0)); ex_year_stake = stake - year_stake.get(largest_year, Decimal(0))
    return {
        "frozen_issue_count": len(rows), "settled_issue_count": sum(int(row["settlement_status"] == "SETTLED") for row in rows),
        "unavailable_issue_count": sum(int(row["settlement_status"] == "UNAVAILABLE_CANONICAL_OUTCOME") for row in rows), "no_bet_issue_count": sum(int(row["settlement_status"] == "NO_BET_SOURCE_K4_INSUFFICIENT_IDENTITIES") for row in rows),
        "stake_yuan": money(stake), "gross_pre_tax_yuan": money(gross), "tax_yuan": money(tax), "after_tax_gross_yuan": money(after), "pre_tax_net_yuan": money(pre), "tax_adjusted_net_yuan": money(tax_net),
        "no_tax_roi": ratio(pre / stake if stake else None), "tax_adjusted_roi": ratio(tax_net / stake if stake else None),
        "planned_draw_count": sum(int(row["planned_draw_count"]) for row in rows), "executed_draw_count": sum(int(row["executed_draw_count"]) for row in rows),
        "winning_ticket_count": sum(int(row["winning_ticket_count"]) for row in rows), "coverage_hits": sum(int(row["coverage_hits"]) for row in rows),
        "coverage_hit_rate": ratio(Decimal(sum(int(row["coverage_hits"]) for row in rows)) / len(rows)), "unique_ticket_count": sum(int(row["unique_ticket_count"]) for row in rows), "duplicate_ticket_count": sum(int(row["duplicate_ticket_count"]) for row in rows),
        "gross_top_issue": top_issue, "gross_top_issue_share": ratio(issue_gross.get(top_issue, Decimal(0)) / total_gross if total_gross else None), "gross_issue_hhi": ratio(hhi),
        "largest_signed_issue": largest_issue, "largest_signed_issue_net_yuan": money(largest_issue_net), "largest_signed_year": largest_year, "largest_signed_year_net_yuan": money(largest_year_net),
        "ex_largest_issue_no_tax_roi": ratio((pre - largest_issue_net) / ex_issue_stake if ex_issue_stake else None), "ex_largest_year_no_tax_roi": ratio((pre - largest_year_net) / ex_year_stake if ex_year_stake else None),
        "drawdown_no_tax_yuan": money(drawdown), "longest_miss_streak": longest, "first_kickoff_ts": min((str(row["first_kickoff_ts"]) for row in rows if row.get("first_kickoff_ts")), default=""),
    }


def lift_value(candidate: dict[str, object], full: dict[str, object], field: str = "no_tax_roi") -> str:
    return ratio(dec(candidate[field], field) - dec(full[field], field))


def make_svg(path: Path, title: str, series: list[tuple[str, list[tuple[float, float]]]], y_label: str) -> None:
    width, height, left, right, top, bottom = 900, 460, 80, 30, 50, 80
    vals = [y for _, points in series for _, y in points]; low = min(vals, default=0); high = max(vals, default=1); pad = max((high-low)*0.1, 0.03); low -= pad; high += pad
    if high <= low: high = low + 1
    xs = sorted({x for _, points in series for x, _ in points}); xpos = lambda x: left + xs.index(x) * (width-left-right) / max(1, len(xs)-1); ypos = lambda y: top + (high-y)/(high-low)*(height-top-bottom)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="100%" height="100%" fill="white"/><text x="450" y="26" text-anchor="middle" font-family="sans-serif" font-size="16">{title}</text>']
    for i in range(5):
        value = low + (high-low)*i/4; yy = ypos(value); lines += [f'<line x1="{left}" y1="{yy:.2f}" x2="{width-right}" y2="{yy:.2f}" stroke="#e5e7eb"/>', f'<text x="{left-8}" y="{yy+4:.2f}" text-anchor="end" font-family="monospace" font-size="10">{value:.3f}</text>']
    lines.append(f'<text x="18" y="230" transform="rotate(-90 18 230)" text-anchor="middle" font-family="sans-serif" font-size="12">{y_label}</text>')
    colors = ("#2563eb", "#dc2626", "#059669", "#9333ea", "#ea580c")
    for idx, (name, points) in enumerate(series):
        points = sorted(points); lines.append(f'<polyline points="{" ".join(f"{xpos(x):.2f},{ypos(y):.2f}" for x,y in points)}" fill="none" stroke="{colors[idx%len(colors)]}" stroke-width="2"/><text x="{width-right-100}" y="{top+16+idx*16}" font-family="sans-serif" font-size="11" fill="{colors[idx%len(colors)]}">{name}</text>')
    lines.append(f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#111827"/><line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#111827"/>')
    for x in xs: lines.append(f'<text x="{xpos(x):.2f}" y="{height-bottom+22}" text-anchor="middle" font-family="sans-serif" font-size="11">{x:g}</text>')
    lines.append("</svg>\n"); path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, default=ROOT / "results/bj167_gate_b_outcome_settlement_v2"); parser.add_argument("--head-start", default=""); parser.add_argument("--head-end", default="")
    args = parser.parse_args(); output = args.output.resolve()
    if output.exists(): raise RuntimeError(f"refusing overwrite: {output}")
    gate = verify_bundle(GATE_A, GATE_A_MANIFEST); verify_bundle(OUTCOME, OUTCOME_MANIFEST); reference = verify_bundle(REFERENCE_151, "7b88be8af887674875f831f2da0951a1bf7664041f40c10be00d09194ce6fbe2")
    if gate.get("CONTENT_IDENTITY.json") != GATE_A_CONTENT or gate.get("candidate_identities.csv.gz") is None or gate.get("candidate_role_vectors.csv.gz") is None or gate.get("allocation_catalog.csv.gz") is None: raise RuntimeError("Gate-A v2 content drift")
    if reference.get("m_grid_surface_summary.csv") is None: raise RuntimeError("#151 reference output unavailable")
    cohort = read_csv(GATE_A / "candidate_cohort.csv"); identities = read_gzip(GATE_A / "candidate_identities.csv.gz"); roles = read_gzip(GATE_A / "candidate_role_vectors.csv.gz"); allocations = read_gzip(GATE_A / "allocation_catalog.csv.gz"); outcomes_rows = read_csv(OUTCOME / "canonical_outcome_join.csv"); outcomes = {row["match_id"]: row for row in outcomes_rows}
    if len(cohort) != 348 or len(identities) != 1356 or len(roles) != 9492 or len(allocations) != 135600: raise RuntimeError("Gate-A v2 denominator drift")
    if len(outcomes) != len(outcomes_rows): raise RuntimeError("duplicate canonical outcome")
    for row in outcomes.values():
        if row["result_code"] not in CODES or row["settlement_quality"] != "trusted" or row["has_trusted_settlement"] != "1" or dec(row["winning_sp"], "winning SP") <= 0: raise RuntimeError("untrusted outcome")
    role_map: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in roles: role_map[row["portfolio_id"]].append(row)
    allocation_map = {(row["portfolio_id"], row["seed"]): tuple(int(x) for x in row["allocation_ordinals"].split("|")) for row in allocations}
    identity_map = {row["portfolio_id"]: row for row in identities}; issue_identities: dict[str, list[dict[str, object]]] = defaultdict(list)
    for identity in identities:
        ordered = sorted(role_map[identity["portfolio_id"]], key=lambda row: int(row["selection_rank"]))
        if len(ordered) != N or "|".join(row["match_id"] for row in ordered) != identity["selected_match_ids"]: raise RuntimeError("identity role drift")
        missing = [row for row in ordered if row["match_id"] not in outcomes]; truth = "" if missing else "".join(outcomes[row["match_id"]]["result_code"] for row in ordered); product = Decimal(1)
        if not missing:
            for row in ordered: product *= dec(outcomes[row["match_id"]]["winning_sp"], "winning SP")
        issue_identities[identity["issue_instance"]].append({"identity": identity, "roles": ordered, "truth": truth, "truth_idx": truth_ordinal(truth) if truth else None, "product": product, "gap_count": len(missing)})
    cohort_map = {row["issue_instance"]: row for row in cohort}
    if set(cohort_map) != set(issue_identities) | {row["issue_instance"] for row in cohort if row["selection_status"] != "AVAILABLE"}: raise RuntimeError("cohort membership drift")
    output.mkdir(parents=True)
    identity_rows: list[dict[str, object]] = []
    issue_rows: list[dict[str, object]] = []
    ticket_rows: list[dict[str, object]] = []
    candidate_by_key: dict[tuple[int, str], list[dict[str, object]]] = defaultdict(list); full_rows: list[dict[str, object]] = []
    truth_counter: Counter[str] = Counter()
    rank_cache: dict[tuple[str, str], int | None] = {}
    # Gate-A already persisted the exact first 128 WOR ordinals.  For this
    # M-grid the rank is exact when it is in that prefix; otherwise the only
    # required rank bin is >128.  This avoids re-running the 2,187-ticket
    # scorer during settlement and is byte-compatible with the frozen sampler.
    for members in issue_identities.values():
        for item in members:
            for seed in SEEDS:
                ordinals = allocation_map[(item["identity"]["portfolio_id"], seed)]
                truth = item["truth_idx"]
                rank_cache[(item["identity"]["portfolio_id"], seed)] = (ordinals.index(int(truth)) + 1) if truth is not None and int(truth) in ordinals else (TOP_K + 1 if truth is not None else None)
    # Build issue and identity ledgers from the frozen cohort exactly once.
    for sample in sorted(cohort, key=lambda row: (int(row["year"]), int(row["issue"]), row["fold"])):
        issue_instance = sample["issue_instance"]; members = issue_identities.get(issue_instance, []); no_bet = sample["selection_status"] != "AVAILABLE"; gap_count = sum(int(item["gap_count"]) for item in members)
        status = "NO_BET_SOURCE_K4_INSUFFICIENT_IDENTITIES" if no_bet else ("UNAVAILABLE_CANONICAL_OUTCOME" if gap_count else "SETTLED")
        first_kickoff = min((str(item["roles"][0]["kickoff_ts"]) for item in members), default="")
        for m in M_GRID:
            for seed in SEEDS:
                row = {"issue": sample["issue"], "fold": sample["fold"], "year": sample["year"], "issue_instance": issue_instance, "arm": "CANDIDATE", "mechanism": "Q_INFORMED_WOR_DISTINCT", "seed": seed, "M": m, "settlement_status": status, "candidate_identity_count": int(sample["selected_identity_count"]), "first_kickoff_ts": first_kickoff, "frozen_planned_draw_count": int(sample["selected_identity_count"]) * m if not no_bet else 0, "frozen_planned_stake_yuan": money(STAKE * int(sample["selected_identity_count"]) * m) if not no_bet else "0.000000", "planned_draw_count": 0, "executed_draw_count": 0, "stake_yuan": "0.000000", "unique_ticket_count": 0, "duplicate_ticket_count": 0, "winning_ticket_count": 0, "coverage_hits": 0, "gross_pre_tax_yuan": "0.000000", "tax_yuan": "0.000000", "after_tax_gross_yuan": "0.000000", "pre_tax_net_yuan": "0.000000", "tax_adjusted_net_yuan": "0.000000", "no_tax_roi": "", "tax_adjusted_roi": "", "outcome_gap_count": gap_count}
                if status == "SETTLED":
                    gross = tax = Decimal(0); hits = coverage = 0
                    for item in members:
                        rank = rank_cache[(item["identity"]["portfolio_id"], seed)]; selected = allocation_map[(item["identity"]["portfolio_id"], seed)][:m]; hit = int(int(item["truth_idx"]) in selected); truth_counter[f"M{m}:{'HIT' if hit else 'MISS'}"] += 1
                        per = (STAKE * FACTOR * item["product"]).quantize(MONEY_Q); per_tax = ticket_tax(per).quantize(MONEY_Q); hits += hit; coverage += hit
                        identity_rows.append({"portfolio_id": item["identity"]["portfolio_id"], "issue_instance": issue_instance, "issue": sample["issue"], "year": sample["year"], "fold": sample["fold"], "M": m, "seed": seed, "truth_rank": rank, "coverage_hit": hit, "stake_yuan": money(STAKE*m), "gross_pre_tax_yuan": money(per*hit), "tax_yuan": money(per_tax*hit), "pre_tax_net_yuan": money(STAKE*(per*0+0) + per*hit - STAKE*m), "tax_adjusted_net_yuan": money(per*hit-per_tax*hit-STAKE*m), "allocation_fingerprint": hashlib.sha256(json.dumps(selected, separators=(",", ":")).encode()).hexdigest()})
                        if hit: ticket_rows.append({"issue": sample["issue"], "fold": sample["fold"], "year": sample["year"], "issue_instance": issue_instance, "arm": "CANDIDATE", "mechanism": "Q_INFORMED_WOR_DISTINCT", "seed": seed, "M": m, "portfolio_id": item["identity"]["portfolio_id"], "winning_ticket_gross_yuan": money(per), "winning_ticket_count": 1, "per_ticket_tax_yuan": money(per_tax), "tax_yuan": money(per_tax), "tax_rule": "20pct_if_each_ticket_gross_gte_10000_no_aggregate_pooling"})
                        gross += per*hit; tax += per_tax*hit
                    stake = STAKE * int(sample["selected_identity_count"]) * m; row.update({"planned_draw_count": int(sample["selected_identity_count"])*m, "executed_draw_count": int(sample["selected_identity_count"])*m, "stake_yuan": money(stake), "unique_ticket_count": int(sample["selected_identity_count"])*m, "winning_ticket_count": hits, "coverage_hits": coverage, "gross_pre_tax_yuan": money(gross), "tax_yuan": money(tax), "after_tax_gross_yuan": money(gross-tax), "pre_tax_net_yuan": money(gross-stake), "tax_adjusted_net_yuan": money(gross-tax-stake), "no_tax_roi": ratio((gross-stake)/stake), "tax_adjusted_roi": ratio((gross-tax-stake)/stake)})
                issue_rows.append(row); candidate_by_key[(m, seed)].append(row)
        full = {"issue": sample["issue"], "fold": sample["fold"], "year": sample["year"], "issue_instance": issue_instance, "arm": "FULL_CONTROL", "mechanism": "FULL_ENUMERATED", "seed": "NA", "M": FULL_TICKETS, "settlement_status": status, "candidate_identity_count": int(sample["selected_identity_count"]), "first_kickoff_ts": first_kickoff, "frozen_planned_draw_count": int(sample["selected_identity_count"])*FULL_TICKETS if not no_bet else 0, "frozen_planned_stake_yuan": money(STAKE*int(sample["selected_identity_count"])*FULL_TICKETS) if not no_bet else "0.000000", "planned_draw_count": 0, "executed_draw_count": 0, "stake_yuan": "0.000000", "unique_ticket_count": 0, "duplicate_ticket_count": 0, "winning_ticket_count": 0, "coverage_hits": 0, "gross_pre_tax_yuan": "0.000000", "tax_yuan": "0.000000", "after_tax_gross_yuan": "0.000000", "pre_tax_net_yuan": "0.000000", "tax_adjusted_net_yuan": "0.000000", "no_tax_roi": "", "tax_adjusted_roi": "", "outcome_gap_count": gap_count}
        if status == "SETTLED":
            gross = tax = Decimal(0); hits = 0
            for item in members:
                per = (STAKE*FACTOR*item["product"]).quantize(MONEY_Q); per_tax = ticket_tax(per).quantize(MONEY_Q); hits += 1; gross += per; tax += per_tax
                identity_rows.append({"portfolio_id": item["identity"]["portfolio_id"], "issue_instance": issue_instance, "issue": sample["issue"], "year": sample["year"], "fold": sample["fold"], "M": FULL_TICKETS, "seed": "NA", "truth_rank": 1, "coverage_hit": 1, "stake_yuan": money(STAKE*FULL_TICKETS), "gross_pre_tax_yuan": money(per), "tax_yuan": money(per_tax), "pre_tax_net_yuan": money(per-STAKE*FULL_TICKETS), "tax_adjusted_net_yuan": money(per-per_tax-STAKE*FULL_TICKETS), "allocation_fingerprint": "FULL"})
                ticket_rows.append({"issue": sample["issue"], "fold": sample["fold"], "year": sample["year"], "issue_instance": issue_instance, "arm": "FULL_CONTROL", "mechanism": "FULL_ENUMERATED", "seed": "NA", "M": FULL_TICKETS, "portfolio_id": item["identity"]["portfolio_id"], "winning_ticket_gross_yuan": money(per), "winning_ticket_count": 1, "per_ticket_tax_yuan": money(per_tax), "tax_yuan": money(per_tax), "tax_rule": "20pct_if_each_ticket_gross_gte_10000_no_aggregate_pooling"})
            stake = STAKE*int(sample["selected_identity_count"])*FULL_TICKETS; full.update({"planned_draw_count": int(sample["selected_identity_count"])*FULL_TICKETS, "executed_draw_count": int(sample["selected_identity_count"])*FULL_TICKETS, "stake_yuan": money(stake), "unique_ticket_count": int(sample["selected_identity_count"])*FULL_TICKETS, "winning_ticket_count": hits, "coverage_hits": hits, "gross_pre_tax_yuan": money(gross), "tax_yuan": money(tax), "after_tax_gross_yuan": money(gross-tax), "pre_tax_net_yuan": money(gross-stake), "tax_adjusted_net_yuan": money(gross-tax-stake), "no_tax_roi": ratio((gross-stake)/stake), "tax_adjusted_roi": ratio((gross-tax-stake)/stake)})
        issue_rows.append(full); full_rows.append(full)
    issue_rows.sort(key=lambda row: (int(row["year"]), int(row["issue"]), str(row["arm"]), int(row["M"]), str(row["seed"])))
    identity_rows.sort(key=lambda row: (int(row["year"]), int(row["issue"]), str(row["portfolio_id"]), int(row["M"]), str(row["seed"])))
    ticket_rows.sort(key=lambda row: (int(row["year"]), int(row["issue"]), str(row["arm"]), int(row["M"]), str(row["seed"]), str(row["portfolio_id"])))
    identity_fields = tuple(identity_rows[0].keys()); issue_fields = tuple(issue_rows[0].keys()); ticket_fields = tuple(ticket_rows[0].keys())
    write_gzip(output / "identity_settlement.csv.gz", identity_rows, identity_fields); write_csv(output / "issue_settlement.csv", issue_rows, issue_fields); write_gzip(output / "winning_ticket_tax_ledger.csv.gz", ticket_rows, ticket_fields)
    ticket_tax_totals = defaultdict(Decimal); ticket_hits = Counter(); issue_tax = defaultdict(Decimal)
    for row in ticket_rows:
        key = (str(row["arm"]), str(row["mechanism"]), int(row["M"]), str(row["seed"]))
        ticket_tax_totals[key] += dec(row["tax_yuan"], "ticket tax"); ticket_hits[key] += int(row["winning_ticket_count"])
    for row in issue_rows:
        key = (str(row["arm"]), str(row["mechanism"]), int(row["M"]), str(row["seed"]))
        issue_tax[key] += dec(row["tax_yuan"], "issue tax")
    tax_reconciliation = []
    for key in sorted(issue_tax):
        difference = ticket_tax_totals[key] - issue_tax[key]
        if abs(difference) > MONEY_Q:
            raise RuntimeError(f"per-ticket tax reconciliation drift: {key}: {difference}")
        tax_reconciliation.append({"arm": key[0], "mechanism": key[1], "M": key[2], "seed": key[3], "ticket_ledger_hit_count": ticket_hits[key], "ticket_ledger_tax_yuan": money(ticket_tax_totals[key]), "issue_ledger_tax_yuan": money(issue_tax[key]), "difference_yuan": money(difference), "tax_rule": "20pct_if_each_ticket_gross_gte_10000_no_aggregate_pooling"})
    write_csv(output / "ticket_tax_reconciliation.csv", tax_reconciliation, tuple(tax_reconciliation[0].keys()))
    # Candidate and FULL summaries, plus paired absolute/lift attribution.
    seed_rows = []; summary_index = {}
    for m in M_GRID:
        full = signed_metrics([row for row in full_rows])
        for seed in SEEDS:
            candidate = signed_metrics(candidate_by_key[(m, seed)])
            summary_index[(m, seed)] = (candidate, full)
            row = {"M": m, "seed": seed, **{f"candidate_{key}": value for key, value in candidate.items()}, **{f"full_{key}": value for key, value in full.items() if key in ("stake_yuan", "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan", "no_tax_roi", "tax_adjusted_roi", "coverage_hit_rate", "gross_issue_hhi", "drawdown_no_tax_yuan", "longest_miss_streak")}}
            row.update({"lift_no_tax_roi": lift_value(candidate, full), "lift_tax_adjusted_roi": lift_value(candidate, full, "tax_adjusted_roi"), "candidate_minus_full_stake_yuan": money(dec(candidate["stake_yuan"], "candidate stake")-dec(full["stake_yuan"], "full stake"))})
            row.update({"candidate_ex_largest_issue_no_tax_roi": candidate["ex_largest_issue_no_tax_roi"], "candidate_ex_largest_year_no_tax_roi": candidate["ex_largest_year_no_tax_roi"]})
            # Paired exclusions remove the same issue/year from both arms.
            candidate_rows = candidate_by_key[(m, seed)]
            full_lookup = {row["issue_instance"]: row for row in full_rows}
            issue_names = [str(row["issue_instance"]) for row in candidate_rows]; year_names = [str(row["year"]) for row in candidate_rows]
            largest_issue = str(candidate["largest_signed_issue"]); largest_year = str(candidate["largest_signed_year"])
            for label, predicate in (("issue", lambda r: str(r["issue_instance"]) != largest_issue), ("year", lambda r: str(r["year"]) != largest_year)):
                c_ex = signed_metrics([r for r in candidate_rows if predicate(r)]); f_ex = signed_metrics([r for r in full_rows if predicate(r)]); row[f"lift_ex_largest_{label}_no_tax_roi"] = lift_value(c_ex, f_ex)
            seed_rows.append(row)
    seed_fields = tuple(seed_rows[0].keys()); write_csv(output / "seed_summary.csv", seed_rows, seed_fields)
    ensemble_rows = []
    for m in M_GRID:
        values = [float(row["candidate_no_tax_roi"]) for row in seed_rows if int(row["M"]) == m]; lifts = [float(row["lift_no_tax_roi"]) for row in seed_rows if int(row["M"]) == m]; full = signed_metrics(full_rows)
        pooled_candidate = signed_metrics([r for r in candidate_by_key[(m, SEEDS[0])]])
        pooled_net = sum(dec(row["candidate_pre_tax_net_yuan"], "net") for row in seed_rows if int(row["M"]) == m); pooled_stake = sum(dec(row["candidate_stake_yuan"], "stake") for row in seed_rows if int(row["M"]) == m)
        sd = statistics.stdev(values); lift_sd = statistics.stdev(lifts); mean = statistics.fmean(values); lift_mean = statistics.fmean(lifts)
        ensemble_rows.append({"M": m, "seed_count": len(values), "candidate_mean_roi": f"{mean:.12f}", "candidate_pooled_roi": ratio(pooled_net/pooled_stake), "candidate_pooled_minus_arithmetic": f"{float(pooled_net/pooled_stake)-mean:.12f}", "candidate_median_roi": f"{statistics.median(values):.12f}", "candidate_sd_roi": f"{sd:.12f}", "candidate_mcse_roi": f"{sd/math.sqrt(len(values)):.12f}", "candidate_mc95_low": f"{mean-1.96*sd/math.sqrt(len(values)):.12f}", "candidate_mc95_high": f"{mean+1.96*sd/math.sqrt(len(values)):.12f}", "candidate_min_roi": f"{min(values):.12f}", "candidate_max_roi": f"{max(values):.12f}", "candidate_p10_roi": f"{percentile(values,.10):.12f}", "candidate_p25_roi": f"{percentile(values,.25):.12f}", "candidate_p75_roi": f"{percentile(values,.75):.12f}", "candidate_p90_roi": f"{percentile(values,.90):.12f}", "candidate_positive_fraction": f"{sum(x>0 for x in values)/len(values):.12f}", "lift_mean_roi": f"{lift_mean:.12f}", "lift_median_roi": f"{statistics.median(lifts):.12f}", "lift_sd_roi": f"{lift_sd:.12f}", "lift_mcse_roi": f"{lift_sd/math.sqrt(len(lifts)):.12f}", "lift_mc95_low": f"{lift_mean-1.96*lift_sd/math.sqrt(len(lifts)):.12f}", "lift_mc95_high": f"{lift_mean+1.96*lift_sd/math.sqrt(len(lifts)):.12f}", "lift_min_roi": f"{min(lifts):.12f}", "lift_max_roi": f"{max(lifts):.12f}", "lift_p10_roi": f"{percentile(lifts,.10):.12f}", "lift_p25_roi": f"{percentile(lifts,.25):.12f}", "lift_p75_roi": f"{percentile(lifts,.75):.12f}", "lift_p90_roi": f"{percentile(lifts,.90):.12f}", "lift_positive_fraction": f"{sum(x>0 for x in lifts)/len(lifts):.12f}", "full_roi": full["no_tax_roi"], "full_tax_adjusted_roi": full["tax_adjusted_roi"], "primary_metric": "candidate absolute pre-tax ROI; paired candidate-minus-FULL lift secondary"})
    write_csv(output / "ensemble_summary.csv", ensemble_rows, tuple(ensemble_rows[0].keys()))
    prefix_rows = []
    for m in M_GRID:
        for prefix in PREFIXES:
            rows = [row for row in seed_rows if int(row["M"]) == m][:prefix]; prefix_rows.append({"M": m, "prefix_n": prefix, "candidate_mean_roi": f"{statistics.fmean(float(row['candidate_no_tax_roi']) for row in rows):.12f}", "lift_mean_roi": f"{statistics.fmean(float(row['lift_no_tax_roi']) for row in rows):.12f}", "candidate_positive_fraction": f"{sum(float(row['candidate_no_tax_roi'])>0 for row in rows)/len(rows):.12f}", "lift_positive_fraction": f"{sum(float(row['lift_no_tax_roi'])>0 for row in rows)/len(rows):.12f}"})
    write_csv(output / "prefix_convergence.csv", prefix_rows, tuple(prefix_rows[0].keys()))
    # Controlling equal-seed ensemble chronology and paired exclusions.
    chronology = []
    for m in M_GRID:
        candidates = [row for row in issue_rows if row["arm"] == "CANDIDATE" and int(row["M"]) == m]; full = full_rows
        years = sorted({str(row["year"]) for row in candidates}); folds = sorted({str(row["fold"]) for row in candidates})
        for scope, value, predicate in [("ALL", "ALL", lambda row: True)] + [("YEAR", y, lambda row, y=y: str(row["year"]) == y) for y in years] + [("FOLD", f, lambda row, f=f: str(row["fold"]) == f) for f in folds] + [("LOYO", y, lambda row, y=y: str(row["year"]) != y) for y in years]:
            c_metrics = signed_metrics([row for row in candidates if predicate(row)]); f_metrics = signed_metrics([row for row in full if predicate(row)]); chronology.append({"M": m, "scope": scope, "scope_value": value, "seed": "ENSEMBLE_100", "candidate_no_tax_roi": c_metrics["no_tax_roi"], "full_no_tax_roi": f_metrics["no_tax_roi"], "lift_no_tax_roi": lift_value(c_metrics, f_metrics), "candidate_tax_adjusted_roi": c_metrics["tax_adjusted_roi"], "full_tax_adjusted_roi": f_metrics["tax_adjusted_roi"], "lift_tax_adjusted_roi": lift_value(c_metrics, f_metrics, "tax_adjusted_roi"), "candidate_ex_largest_issue_no_tax_roi": c_metrics["ex_largest_issue_no_tax_roi"], "candidate_ex_largest_year_no_tax_roi": c_metrics["ex_largest_year_no_tax_roi"], "candidate_gross_issue_hhi": c_metrics["gross_issue_hhi"], "candidate_drawdown_no_tax_yuan": c_metrics["drawdown_no_tax_yuan"], "candidate_longest_miss_streak": c_metrics["longest_miss_streak"], "frozen_issue_count": c_metrics["frozen_issue_count"], "settled_issue_count": c_metrics["settled_issue_count"]})
    write_csv(output / "ensemble_year_fold_loyo.csv", chronology, tuple(chronology[0].keys()))
    # Paired block bootstrap: each draw resamples an issue and carries all 100
    # candidate seed rows together with its one matched FULL row.
    issue_keys = sorted({row["issue_instance"] for row in full_rows}); full_by_issue = {row["issue_instance"]: row for row in full_rows}; bootstrap_summary = []; bootstrap_reps = []
    rng_seed_base = 167002
    for m in M_GRID:
        candidate_by_issue = {issue: [row for row in issue_rows if row["arm"] == "CANDIDATE" and int(row["M"]) == m and row["issue_instance"] == issue] for issue in issue_keys}
        block_candidate = {issue: (sum((dec(row["pre_tax_net_yuan"], "candidate net") for row in candidate_by_issue[issue]), Decimal(0)), sum((dec(row["stake_yuan"], "candidate stake") for row in candidate_by_issue[issue]), Decimal(0))) for issue in issue_keys}
        block_full = {issue: (dec(full_by_issue[issue]["pre_tax_net_yuan"], "full net"), dec(full_by_issue[issue]["stake_yuan"], "full stake")) for issue in issue_keys}
        point_candidate = sum((x[0] for x in block_candidate.values()), Decimal(0))/sum((x[1] for x in block_candidate.values()), Decimal(0)); point_full = sum((x[0] for x in block_full.values()), Decimal(0))/sum((x[1] for x in block_full.values()), Decimal(0)); point_lift = point_candidate-point_full
        rng = random.Random(rng_seed_base+m); values_c=[]; values_f=[]; values_l=[]
        for replicate in range(BOOTSTRAP_REPLICATES):
            cnet=cstake=fnet=fstake=Decimal(0)
            for _ in issue_keys:
                issue = issue_keys[rng.randrange(len(issue_keys))]; cn,cs=block_candidate[issue]; fn,fs=block_full[issue]; cnet+=cn; cstake+=cs; fnet+=fn; fstake+=fs
            cr=float(cnet/cstake if cstake else 0); fr=float(fnet/fstake if fstake else 0); lr=cr-fr; values_c.append(cr); values_f.append(fr); values_l.append(lr); bootstrap_reps.append({"M": m, "replicate": replicate+1, "candidate_roi": f"{cr:.12f}", "full_roi": f"{fr:.12f}", "lift_roi": f"{lr:.12f}"})
        values_c.sort(); values_f.sort(); values_l.sort(); bootstrap_summary.append({"M": m, "replicates": BOOTSTRAP_REPLICATES, "candidate_point_roi": f"{float(point_candidate):.12f}", "candidate_ci95_low": f"{values_c[500]:.12f}", "candidate_ci95_high": f"{values_c[-501]:.12f}", "candidate_positive_fraction": f"{sum(x>0 for x in values_c)/len(values_c):.12f}", "full_point_roi": f"{float(point_full):.12f}", "full_ci95_low": f"{values_f[500]:.12f}", "full_ci95_high": f"{values_f[-501]:.12f}", "full_positive_fraction": f"{sum(x>0 for x in values_f)/len(values_f):.12f}", "lift_point_roi": f"{float(point_lift):.12f}", "lift_ci95_low": f"{values_l[500]:.12f}", "lift_ci95_high": f"{values_l[-501]:.12f}", "lift_positive_fraction": f"{sum(x>0 for x in values_l)/len(values_l):.12f}", "bootstrap_rule": "issue_instance block resample carries all 100 candidate seeds and matched FULL row together"})
    write_csv(output / "paired_issue_bootstrap_summary.csv", bootstrap_summary, tuple(bootstrap_summary[0].keys())); write_csv(output / "paired_issue_bootstrap_replicates.csv", bootstrap_reps, tuple(bootstrap_reps[0].keys()))
    # Seed overlap and truth-rank/coverage against uniform ticket-space mass.
    overlap_values=[]; identity_ids=[row["portfolio_id"] for row in identities]
    for portfolio_id in identity_ids:
        sets={seed:set(allocation_map[(portfolio_id,seed)][:64]) for seed in SEEDS}
        for left_index in range(len(SEEDS)):
            for right_index in range(left_index+1,len(SEEDS)): overlap_values.append(len(sets[SEEDS[left_index]] & sets[SEEDS[right_index]])/64)
    overlap_values.sort(); write_csv(output / "seed_overlap_distribution.csv", [{"M":64,"seed_pair_count":len(overlap_values),"identity_count":len(identity_ids),"mean_shared_fraction":f"{statistics.fmean(overlap_values):.12f}","p10":f"{percentile(overlap_values,.10):.12f}","p25":f"{percentile(overlap_values,.25):.12f}","median":f"{statistics.median(overlap_values):.12f}","p75":f"{percentile(overlap_values,.75):.12f}","p90":f"{percentile(overlap_values,.90):.12f}","min":f"{min(overlap_values):.12f}","max":f"{max(overlap_values):.12f}","dependence_note":"seed draws share frozen identities/q vectors and are not independent football histories"}], tuple(["M","seed_pair_count","identity_count","mean_shared_fraction","p10","p25","median","p75","p90","min","max","dependence_note"]))
    rank_rows=[]
    for m in M_GRID:
        counts=Counter(); available_count=0
        for item in identities:
            members=issue_identities[item["issue_instance"]]; current=next(x for x in members if x["identity"]["portfolio_id"]==item["portfolio_id"])
            if current["truth_idx"] is None: continue
            available_count += len(SEEDS)
            for seed in SEEDS:
                rank=rank_cache[(item["portfolio_id"], seed)]; counts["1-32" if rank<=32 else "33-64" if rank<=64 else "65-128" if rank<=128 else ">128"] += 1
        for bin_name,count in sorted(counts.items()): rank_rows.append({"M":m,"rank_bin":bin_name,"identity_seed_count":count,"available_identity_seed_count":available_count,"realized_fraction":f"{count/available_count:.12f}","uniform_ticket_space_fraction":f"{m/FULL_TICKETS:.12f}","coverage_dependence_note":"truth rank is evaluated after canonical outcome join; seeds share frozen identities and q vectors"})
    write_csv(output / "truth_rank_distribution.csv", rank_rows, tuple(rank_rows[0].keys()))
    # Reconcile allocator variance to paired historical block uncertainty.
    variance_rows=[]
    for m, ensemble, boot in zip(M_GRID, ensemble_rows, bootstrap_summary): variance_rows.append({"M":m,"candidate_allocator_seed_sd":ensemble["candidate_sd_roi"],"candidate_allocator_seed_variance":f"{float(ensemble['candidate_sd_roi'])**2:.12f}","candidate_mcse":ensemble["candidate_mcse_roi"],"candidate_bootstrap_sd_proxy":f"{(float(boot['candidate_ci95_high'])-float(boot['candidate_ci95_low']))/3.92:.12f}","lift_allocator_seed_sd":ensemble["lift_sd_roi"],"lift_mcse":ensemble["lift_mcse_roi"],"lift_bootstrap_sd_proxy":f"{(float(boot['lift_ci95_high'])-float(boot['lift_ci95_low']))/3.92:.12f}","variance_note":"allocator seed variation and historical issue/outcome bootstrap are separate; seeds are not football histories"})
    write_csv(output / "variance_decomposition.csv", variance_rows, tuple(variance_rows[0].keys()))
    # Reproduce the accepted three-seed #151 M64 values and paired FULL lifts.
    ref_rows=read_csv(REFERENCE_151/"m_grid_surface_summary.csv"); reference={row["seed"]: row for row in ref_rows if row["scope"]=="ALL" and row["sampling_role"]=="SENSITIVITY_WOR_FIXED_CANDIDATE" and row["M"]=="64"}; reproduction=[]
    full_ref=next(row for row in ref_rows if row["scope"]=="ALL" and row["sampling_role"]=="FULL_ECONOMIC_CONTROL")
    for seed in SEEDS[:3]: reproduction.append({"seed":seed,"recomputed_candidate_roi":next(row["candidate_no_tax_roi"] for row in seed_rows if row["M"]==64 and row["seed"]==seed),"reference_151_candidate_roi":reference[seed]["no_tax_roi"],"candidate_abs_difference":f"{float(next(row['candidate_no_tax_roi'] for row in seed_rows if row['M']==64 and row['seed']==seed))-float(reference[seed]['no_tax_roi']):.12f}","recomputed_full_roi":next(row["full_no_tax_roi"] for row in seed_rows if row["M"]==64 and row["seed"]==seed),"reference_151_full_roi":full_ref["no_tax_roi"],"recomputed_lift":next(row["lift_no_tax_roi"] for row in seed_rows if row["M"]==64 and row["seed"]==seed),"reference_151_lift":f"{float(reference[seed]['no_tax_roi'])-float(full_ref['no_tax_roi']):.12f}"})
    if any(abs(float(row["candidate_abs_difference"])) > 1e-10 for row in reproduction): raise RuntimeError("first-three #151 reproduction drift")
    write_csv(output / "three_seed_reproduction.csv", reproduction, tuple(reproduction[0].keys()))
    # Decision boundary is evaluated only on M64 and remains descriptive.
    m64=next(row for row in ensemble_rows if int(row["M"])==64); b64=next(row for row in bootstrap_summary if int(row["M"])==64); seed64=[row for row in seed_rows if int(row["M"])==64]; ex_issue=min(float(row["candidate_ex_largest_issue_no_tax_roi"]) for row in seed64); ex_year=min(float(row["candidate_ex_largest_year_no_tax_roi"]) for row in seed64)
    if float(m64["candidate_mean_roi"])>0 and float(m64["lift_mean_roi"])>0 and float(m64["candidate_mc95_low"])>0 and float(m64["lift_mc95_low"])>0 and float(b64["candidate_ci95_low"])>0 and float(b64["lift_ci95_low"])>0 and ex_issue>0 and ex_year>0: terminal="ABSOLUTE_EDGE_SUPPORTED"
    elif float(m64["lift_mean_roi"])>0 and float(b64["lift_ci95_low"])>0: terminal="RELATIVE_LIFT_ONLY"
    else: terminal="NO_STABLE_LIFT"
    decision={"terminal_state":terminal,"primary_M":64,"promotion_authorized":False,"absolute_edge_rule":"candidate absolute pre-tax ROI, allocator MC lower bound, paired issue-bootstrap lower bound, and ex-largest issue/year controls must all remain positive; this package does not authorize promotion","next_step":"separate strict EV/forward validation only if the controlling PI boundary is satisfied; otherwise treat as descriptive evidence"}
    (output/"decision.json").write_text(json.dumps(decision,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    generated=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")
    card={"issue":167,"contract":CONTRACT,"stage":"GATE_B_ONE_SHOT_FIXED_137_CANDIDATE_AND_MATCHED_FULL_100_SEED_SETTLEMENT","generated_at_utc":generated,"head_start":args.head_start,"head_end":args.head_end,"gate_a_manifest":GATE_A_MANIFEST,"gate_a_content_identity":GATE_A_CONTENT,"gate_a_151_manifest":GATE_A_151_MANIFEST,"outcome_manifest":OUTCOME_MANIFEST,"outcome_payload":OUTCOME_PAYLOAD,"n":N,"primary_arm":"NO_GATE/K4/Q_INFORMED_WOR_DISTINCT/M64/Q_WEIGHT","matched_control":"exact-K4 FULL on identical issue/identity/outcome support","M_grid":list(M_GRID),"seed_panel":list(SEEDS),"identity_count":len(identities),"role_count":len(roles),"cohort_issue_count":len(cohort),"available_issue_count":sum(row["selection_status"]=="AVAILABLE" for row in cohort),"no_bet_issue_count":sum(row["selection_status"]!="AVAILABLE" for row in cohort),"identity_settlement_rows":len(identity_rows),"issue_settlement_rows":len(issue_rows),"tax_reconciliation_rows":len(tax_reconciliation),"paired_bootstrap_replicates_per_M":BOOTSTRAP_REPLICATES,"primary_metric":"candidate absolute pre-tax no_tax_roi; paired candidate-minus-FULL lift reported separately; tax secondary","tax_rule":"20% iff each individual winning ticket gross >= 10000; no issue/policy/identity pooling","terminal_state":terminal,"superseded_transfer_diagnostic":{"package":"bj167_gate_b_outcome_settlement_v1r2","manifest":"6946ea6c92a871fe97159980e5a8440e5927cf789b272c227b7d3c4175e96758","content_identity":"6a86977a004b3a96c3b0eb9c488d4da2f272157af02051e01d4ff928f9dcee2f","role":"#159 complete-issue transfer/generalization diagnostic only; not controlling"},"promotion_authorized":False,"no_purchase_production_or_betting_authority":True,"outcome_boundary":"canonical outcome joined once after Gate-A freeze; no selection or sampler change"}
    binding={"issue":167,"contract":CONTRACT,"gate_a_manifest":GATE_A_MANIFEST,"gate_a_content_identity":GATE_A_CONTENT,"canonical_outcome_manifest":OUTCOME_MANIFEST,"canonical_outcome_payload":OUTCOME_PAYLOAD,"reference_151_gate_b_manifest":"7b88be8af887674875f831f2da0951a1bf7664041f40c10be00d09194ce6fbe2","runner_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()}
    interpretation=f"""# #167 controlling fixed-candidate N7/M64 multi-seed settlement

The controlling contract is the exact #137/#151 NO_GATE/K4 cohort, not the earlier #159 transfer diagnostic. N=7, Q-informed WOR, M64 primary, M32/M128 secondary, seeds 137001..137100. The matched FULL arm enumerates all 2,187 tickets on the same issue/identity/outcome support.

Terminal state: **{terminal}**. Candidate absolute pre-tax ROI, candidate-minus-FULL lift, and tax-adjusted values are separate. Seeds are allocator Monte Carlo draws, not football histories; the 100-seed estimand is pooled candidate net divided by pooled candidate stake and reconciles to the arithmetic seed mean because executed stake is equal by seed.

The package reports the first-three #151 reproduction, seed-level candidate/full/lift distributions, fixed prefixes, YEAR/FOLD/LOYO equal-seed chronology, 20,000 paired issue-block bootstrap replicates per M, signed-largest issue/year exclusions, HHI and drawdown, ticket overlap, truth-rank versus the uniform ticket-space fraction, and allocator-versus-outcome variance decomposition. The bootstrap carries all 100 candidate seed rows and the matched FULL row together for every sampled issue.

Tax is per independent winning ticket only (20% when that ticket's gross is at least ¥10,000); no issue/policy/identity pooling is used. This remains paper research: no purchase, production, betting or promotion authority.
"""
    (output/"validation_card.json").write_text(json.dumps(card,indent=2,sort_keys=True)+"\n",encoding="utf-8"); (output/"source_binding.json").write_text(json.dumps(binding,indent=2,sort_keys=True)+"\n",encoding="utf-8"); (output/"interpretation.md").write_text(interpretation,encoding="utf-8")
    (output/"README.md").write_text("# #167 Gate B v2\n\nOne-shot exact #137/#151 fixed-candidate Q-WOR versus matched-K4 FULL settlement over 100 allocator seeds. Candidate absolute ROI is primary; paired lift is separate; tax is per winning ticket. No promotion authority.\n",encoding="utf-8")
    make_svg(output/"seed_roi_lift.svg","#167 seed candidate ROI and paired lift",[("candidate",[(int(r["M"]),float(r["candidate_mean_roi"])) for r in ensemble_rows]),("lift",[(int(r["M"]),float(r["lift_mean_roi"])) for r in ensemble_rows])],"ROI")
    make_svg(output/"prefix_convergence.svg","#167 prefix convergence",[("candidate",[(int(r["prefix_n"]),float(r["candidate_mean_roi"])) for r in prefix_rows if int(r["M"])==64]),("lift",[(int(r["prefix_n"]),float(r["lift_mean_roi"])) for r in prefix_rows if int(r["M"])==64])],"ROI")
    make_svg(output/"m_seed_dispersion.svg","#167 M seed dispersion",[("candidate SD",[(int(r["M"]),float(r["candidate_sd_roi"])) for r in ensemble_rows]),("lift SD",[(int(r["M"]),float(r["lift_sd_roi"])) for r in ensemble_rows])],"SD")
    make_svg(output/"bootstrap_absolute_vs_lift.svg","#167 paired issue bootstrap intervals",[("candidate",[(int(r["M"]),float(r["candidate_point_roi"])) for r in bootstrap_summary]),("lift",[(int(r["M"]),float(r["lift_point_roi"])) for r in bootstrap_summary])],"ROI")
    make_svg(output/"concentration_exclusions.svg","#167 candidate concentration HHI",[("HHI",[(int(r["M"]),statistics.fmean(float(x["candidate_gross_issue_hhi"]) for x in chronology if int(x["M"])==int(r["M"]) and x["scope"]=="ALL")) for r in ensemble_rows])],"HHI")
    shutil.copy2(Path(__file__), output/"settlement_runner.py")
    content={"package":output.name,"contract":CONTRACT,"files":{item.name:sha(item) for item in sorted(output.iterdir()) if item.is_file()}}
    (output/"CONTENT_IDENTITY.json").write_text(json.dumps(content,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    manifest={item.name:sha(item) for item in sorted(output.iterdir()) if item.is_file()}; (output/"SHA256SUMS.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"output":str(output),"manifest_sha256":sha(output/"SHA256SUMS.json"),"content_sha256":sha(output/"CONTENT_IDENTITY.json"),"issue_rows":len(issue_rows),"identity_rows":len(identity_rows),"bootstrap_rows":len(bootstrap_reps),"terminal_state":terminal},sort_keys=True))


if __name__ == "__main__":
    main()
