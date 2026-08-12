#!/usr/bin/env python3
"""Freeze #127's outcome-unexposed matched FULL N7 / one-global-prune study.

This program uses only #101's native issue/segment membership and #106's
outcome-unexposed calibrated probability/SP atlas.  It cannot settle tickets:
there is no result, final-SP, payout, tax, or ROI input in this stage.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import html
import io
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

CODES = ("3", "1", "0")
CONTRACT = "BJ-HIST-PRUNE-ONE-GLOBAL-N7-001"
VERSION = "bj127-gatea-v1"
CONTENT_VERSION = "bj127-portable-content-v1"
BJ106_MANIFEST = "fb45cacccb4c9ab2b52c8a538f489fb3e3197fa138245f0d83cf98a3cbb0db5d"
BJ101_MANIFEST = "86e37682a95fad2a2a67187f1ee528f665d371583c621dc9d14af58f74302447"
FULL_K = 3 ** 7
PRUNE_K = 2 * 3 ** 6
UNIT_STAKE = 2

# Frozen from outcome-unexposed distributions; match floors and GM floors are
# paired exactly as #121, crossed with a bounded global-deletion p_min grid.
REGIMES = ((2.80, 2.90), (2.90, 3.00), (3.00, 3.05))
LOW_P = (0.20, 0.25, 0.30)
VARIANTS = {
    f"ESP{int(e * 100):03d}_GM{int(g * 100):03d}_LOWP{int(p * 100):02d}":
    {"e_sp_min": e, "gm_e_sp_min": g, "p_min_max": p}
    for e, g in REGIMES for p in LOW_P
}

POOL_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder",
)
SCATTER_FIELDS = POOL_FIELDS + (
    "match_id", "match_idx", "p_min", "e_sp", "p3", "p1", "p0", "q3", "q1", "q0",
)
FRONTIER_FIELDS = POOL_FIELDS + (
    "variant_id", "arm", "portfolio_id", "deletion_candidate_match_id", "deletion_candidate_p_min",
    "selected_match_ids", "selected_n", "gm_e_sp", "deleted_match_id", "deleted_code",
    "deleted_probability", "formula_k", "stake_yuan", "matched_full_k", "matched_full_stake_yuan",
    "stake_reduction_fraction", "disposition", "reason", "descriptor_sha256",
)
ROLE_FIELDS = (
    "variant_id", "portfolio_id", "issue", "fold", "year", "pool_id", "match_id", "match_idx",
    "selection_rank", "e_sp", "p_min", "p3", "p1", "p0", "is_deletion_candidate",
    "is_global_deleted_code_match", "global_deleted_code", "global_deleted_probability",
    "full_allowed_codes", "prune_allowed_codes",
)
SUMMARY_FIELDS = (
    "variant_id", "native_pools", "no_bet_control_rows", "pools_with_portfolio", "candidate_matches",
    "deduplicated_portfolios", "matched_full_rows", "prune_one_rows", "full_tickets", "prune_tickets",
    "full_stake_yuan", "prune_stake_yuan", "exact_stake_reduction_fraction",
)
HEX_FIELDS = ("p_min_bin_low", "p_min_bin_high", "e_sp_bin_low", "e_sp_bin_high", "match_count")


def root(path: Path) -> Path:
    for candidate in (path.resolve().parent, *path.resolve().parents):
        if (candidate / ".git").exists(): return candidate
    raise RuntimeError("repository root unavailable")


ROOT = root(Path(__file__))
BJ106 = ROOT / "results" / "bj106_gate_a_preoutcome_v2r1"
BJ101 = ROOT / "results" / "bj101_gate_a_preoutcome_v1r1"
OUTPUT = ROOT / "results" / "bj127_gate_a_preoutcome_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def exact_manifest(directory: Path, expected: str) -> dict[str, str]:
    manifest_path = directory / "SHA256SUMS.json"
    if sha256(manifest_path) != expected: raise RuntimeError(f"unaccepted input: {directory}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {path.name: sha256(path) for path in directory.iterdir()
              if path.is_file() and path.name != "SHA256SUMS.json"}
    if declared != actual: raise RuntimeError(f"manifest coverage drift: {directory}")
    return declared


def fmt(value: float) -> str:
    if not math.isfinite(value): raise RuntimeError("non-finite output")
    return format(value, ".12f")


def geometric(values: list[float]) -> float:
    if not values or any(value <= 0 or not math.isfinite(value) for value in values):
        raise RuntimeError("invalid geometric mean")
    return math.exp(sum(math.log(value) for value in values) / len(values))


def identity(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def gzip_writer(path: Path, fields: tuple[str, ...]):
    raw = path.open("wb")
    zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    return raw, zipped, text, writer


def close_gzip(handles) -> None:
    raw, zipped, text, _ = handles
    text.flush(); text.detach(); zipped.close(); raw.close()


def match_feature(rows: list[dict[str, str]]) -> dict[str, object]:
    if len(rows) != 3 or {row["candidate_code"] for row in rows} != set(CODES):
        raise RuntimeError("expected exactly 3/1/0 atlas outcomes")
    by_code = {row["candidate_code"]: row for row in rows}
    p = {code: float(by_code[code]["p_cal"]) for code in CODES}
    sp = {code: float(by_code[code]["predicted_sp"]) for code in CODES}
    if any(value <= 0 or not math.isfinite(value) for value in (*p.values(), *sp.values())):
        raise RuntimeError("invalid p/SP vector")
    if abs(sum(p.values()) - 1.0) > 1e-6: raise RuntimeError("probability mass drift")
    low = min(CODES, key=lambda code: (p[code], CODES.index(code)))
    return {"p": p, "q": {code: p[code] * sp[code] for code in CODES},
            "p_min": p[low], "e_sp": sum(p[code] * sp[code] for code in CODES)}


def load_sources() -> tuple[dict[str, str], list[dict[str, str]], dict[str, list[dict[str, object]]], list[dict[str, object]]]:
    manifest106 = exact_manifest(BJ106, BJ106_MANIFEST)
    manifest101 = exact_manifest(BJ101, BJ101_MANIFEST)
    with (BJ101 / "issue_pool_census.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != POOL_FIELDS: raise RuntimeError("#101 census schema drift")
        pools = list(reader)
    if len(pools) != 2659 or len({row["issue"] for row in pools}) != 344:
        raise RuntimeError("native denominator drift")
    with (BJ101 / "issue_pool_membership.csv").open(newline="", encoding="utf-8") as handle:
        membership = {row["match_id"]: row for row in csv.DictReader(handle)}
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with gzip.open(BJ106 / "q_atlas.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["match_id"] in membership: grouped[row["match_id"]].append(row)
    by_pool: dict[str, list[dict[str, object]]] = defaultdict(list)
    scatter: list[dict[str, object]] = []
    for match_id, outcome_rows in grouped.items():
        feature = match_feature(outcome_rows)
        member = membership[match_id]
        row = {**member, **feature, "match_id": match_id}
        by_pool[str(row["pool_id"])].append(row)
        p = feature["p"]; q = feature["q"]
        assert isinstance(p, dict) and isinstance(q, dict)
        scatter.append({**member, "match_id": match_id, "p_min": float(feature["p_min"]), "e_sp": float(feature["e_sp"]),
                        "p3": p["3"], "p1": p["1"], "p0": p["0"], "q3": q["3"], "q1": q["1"], "q0": q["0"]})
    if sum(len(rows) for rows in by_pool.values()) != len(membership): raise RuntimeError("#101/#106 join drift")
    for rows in by_pool.values():
        rows.sort(key=lambda row: (-float(row["e_sp"]), float(row["p_min"]), int(str(row["match_idx"]))))
    provenance = {"bj106_manifest_sha256": BJ106_MANIFEST, "bj106_q_atlas_sha256": manifest106["q_atlas.csv.gz"],
                  "bj101_manifest_sha256": BJ101_MANIFEST, "bj101_census_sha256": manifest101["issue_pool_census.csv"],
                  "bj101_membership_sha256": manifest101["issue_pool_membership.csv"]}
    return provenance, pools, by_pool, scatter


def global_minimum(selected: list[dict[str, object]]) -> tuple[dict[str, object], str, float]:
    values: list[tuple[float, int, int, dict[str, object], str]] = []
    for match in selected:
        probabilities = match["p"]; assert isinstance(probabilities, dict)
        for code in CODES:
            values.append((float(probabilities[code]), int(str(match["match_idx"])), CODES.index(code), match, code))
    probability, _, _, match, code = min(values)
    return match, code, probability


def hexbin(scatter: list[dict[str, object]]) -> list[dict[str, object]]:
    bins: dict[tuple[int, int], int] = defaultdict(int)
    for row in scatter:
        p_bin = min(19, int(float(row["p_min"]) / 0.025))
        e_bin = min(19, max(0, int((float(row["e_sp"]) - 1.0) / 0.25)))
        bins[(p_bin, e_bin)] += 1
    return [{"p_min_bin_low": fmt(p * .025), "p_min_bin_high": fmt((p + 1) * .025),
             "e_sp_bin_low": fmt(1 + e * .25), "e_sp_bin_high": fmt(1 + (e + 1) * .25), "match_count": count}
            for (p, e), count in sorted(bins.items())]


def scatter_svg(issue: str, rows: list[dict[str, object]], selected_ids: set[str]) -> str:
    width, height, left, bottom = 720, 440, 60, 50
    chart_w, chart_h = width - left - 30, height - 40 - bottom
    p_max = max(.35, max(float(row["p_min"]) for row in rows) * 1.05)
    e_min, e_max = min(float(row["e_sp"]) for row in rows), max(float(row["e_sp"]) for row in rows)
    e_min = min(2.0, math.floor(e_min * 10) / 10); e_max = max(3.5, math.ceil(e_max * 10) / 10)
    def x(value: float) -> float: return left + chart_w * value / p_max
    def y(value: float) -> float: return 40 + chart_h * (e_max - value) / (e_max - e_min)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>', f'<text x="{left}" y="22" font-family="sans-serif" font-size="16">Issue {html.escape(issue)} — outcome-unexposed p_min × E_SP</text>',
             f'<line x1="{left}" y1="{height-bottom}" x2="{width-30}" y2="{height-bottom}" stroke="#333"/>',
             f'<line x1="{left}" y1="40" x2="{left}" y2="{height-bottom}" stroke="#333"/>',
             f'<line x1="{x(.30):.2f}" y1="40" x2="{x(.30):.2f}" y2="{height-bottom}" stroke="#a66" stroke-dasharray="4"/>',
             f'<line x1="{left}" y1="{y(3.00):.2f}" x2="{width-30}" y2="{y(3.00):.2f}" stroke="#a66" stroke-dasharray="4"/>',
             f'<text x="{x(.30)+4:.2f}" y="{height-bottom-5}" font-size="11">p_min=.30</text>',
             f'<text x="{left+4}" y="{y(3.00)-4:.2f}" font-size="11">E_SP=3.00</text>']
    for row in rows:
        color = "#d62728" if str(row["match_id"]) in selected_ids else "#4c78a8"
        radius = 5 if color == "#d62728" else 3
        lines.append(f'<circle cx="{x(float(row["p_min"])):.2f}" cy="{y(float(row["e_sp"])):.2f}" r="{radius}" fill="{color}" fill-opacity=".75"><title>match {html.escape(str(row["match_id"]))}</title></circle>')
    lines.append(f'<text x="{left}" y="{height-12}" font-size="12">p_min</text><text x="8" y="{height/2:.2f}" font-size="12" transform="rotate(-90 8 {height/2:.2f})">E_SP</text></svg>')
    return "\n".join(lines) + "\n"


def freeze(output: Path) -> dict[str, object]:
    if output.exists(): raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj127_gatea_", dir=output.parent))
    try:
        provenance, pools, by_pool, scatter = load_sources()
        scatter_handles = gzip_writer(stage / "scatter_coordinates.csv.gz", SCATTER_FIELDS)
        frontier_handles = gzip_writer(stage / "matched_frontier.csv.gz", FRONTIER_FIELDS)
        role_handles = gzip_writer(stage / "portfolio_role_assignments.csv.gz", ROLE_FIELDS)
        scatter_writer, frontier_writer, role_writer = scatter_handles[-1], frontier_handles[-1], role_handles[-1]
        pool_by_id = {pool["pool_id"]: pool for pool in pools}
        for row in sorted(scatter, key=lambda item: (int(str(item["issue"])), item["pool_id"], int(str(item["match_idx"])))):
            combined = {**pool_by_id[str(row["pool_id"])], **row}
            scatter_writer.writerow({field: fmt(float(combined[field])) if field in {"p_min", "e_sp", "p3", "p1", "p0", "q3", "q1", "q0"} else combined[field] for field in SCATTER_FIELDS})
        summary = {variant: defaultdict(int) for variant in VARIANTS}
        portfolio_count = role_count = frontier_count = 0
        representative: dict[str, set[str]] = defaultdict(set)
        issue_scatter: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in scatter: issue_scatter[str(row["issue"])].append(row)
        for variant, rule in VARIANTS.items():
            for pool in pools:
                # #101's native census retains unavailable windows in the
                # denominator.  They are explicit NO_BET observations, never
                # an invitation to reach through to their raw memberships.
                pool_is_available = pool["pool_disposition"] == "AVAILABLE"
                matches = by_pool.get(pool["pool_id"], []) if pool_is_available else []
                eligible = [match for match in matches if float(match["e_sp"]) >= rule["e_sp_min"]]
                candidates = [match for match in eligible if float(match["p_min"]) <= rule["p_min_max"]]
                unique: dict[str, tuple[dict[str, object], list[dict[str, object]], dict[str, object], str, float]] = {}
                for candidate in candidates:
                    companions = [match for match in eligible if match["match_id"] != candidate["match_id"]][:6]
                    selected = [candidate, *companions]
                    selected.sort(key=lambda match: (-float(match["e_sp"]), float(match["p_min"]), int(str(match["match_idx"]))))
                    if len(selected) != 7: continue
                    gm = geometric([float(match["e_sp"]) for match in selected])
                    if gm < rule["gm_e_sp_min"]: continue
                    deleted_match, deleted_code, deleted_probability = global_minimum(selected)
                    signature = identity({"variant": variant, "pool": pool["pool_id"], "matches": [match["match_id"] for match in selected], "deleted_match": deleted_match["match_id"], "deleted_code": deleted_code})
                    unique[signature] = (candidate, selected, deleted_match, deleted_code, deleted_probability)
                no_bet_reason = ("PORTFOLIOS_AVAILABLE" if unique else ("POOL_NOT_AVAILABLE" if not pool_is_available else ("NO_DELETION_CANDIDATE" if not candidates else "INSUFFICIENT_ELIGIBLE_OR_GM")))
                frontier_writer.writerow({**pool, "variant_id": variant, "arm": "NO_BET_CONTROL", "portfolio_id": "", "deletion_candidate_match_id": "", "deletion_candidate_p_min": "", "selected_match_ids": "", "selected_n": 0, "gm_e_sp": "", "deleted_match_id": "", "deleted_code": "", "deleted_probability": "", "formula_k": 0, "stake_yuan": 0, "matched_full_k": FULL_K, "matched_full_stake_yuan": FULL_K * UNIT_STAKE, "stake_reduction_fraction": fmt(1/3), "disposition": "NO_BET", "reason": no_bet_reason, "descriptor_sha256": identity({"variant": variant, "pool": pool["pool_id"], "arm": "NO_BET_CONTROL", "reason": no_bet_reason})})
                frontier_count += 1; summary[variant]["native_pools"] += 1; summary[variant]["no_bet_control_rows"] += 1; summary[variant]["candidate_matches"] += len(candidates)
                if unique: summary[variant]["pools_with_portfolio"] += 1
                for portfolio_id, (candidate, selected, deleted_match, deleted_code, deleted_probability) in sorted(unique.items()):
                    selected_ids = ";".join(str(match["match_id"]) for match in selected)
                    base = {**pool, "variant_id": variant, "portfolio_id": portfolio_id, "deletion_candidate_match_id": candidate["match_id"], "deletion_candidate_p_min": fmt(float(candidate["p_min"])), "selected_match_ids": selected_ids, "selected_n": 7, "gm_e_sp": fmt(geometric([float(match["e_sp"]) for match in selected])), "deleted_match_id": deleted_match["match_id"], "deleted_code": deleted_code, "deleted_probability": fmt(deleted_probability), "matched_full_k": FULL_K, "matched_full_stake_yuan": FULL_K * UNIT_STAKE, "stake_reduction_fraction": fmt(1/3), "disposition": "AVAILABLE", "reason": "MATCHED_FROZEN_PAIR"}
                    for arm, k in (("MATCHED_FULL_N7", FULL_K), ("PRUNE_ONE_GLOBAL_N7", PRUNE_K)):
                        frontier_writer.writerow({**base, "arm": arm, "formula_k": k, "stake_yuan": k * UNIT_STAKE, "descriptor_sha256": identity({"contract": CONTRACT, "variant": variant, "arm": arm, "portfolio": portfolio_id, "matches": selected_ids, "deleted_match": deleted_match["match_id"], "deleted_code": deleted_code})})
                        frontier_count += 1
                    for rank, match in enumerate(selected, 1):
                        p = match["p"]; assert isinstance(p, dict)
                        prune_codes = "".join(code for code in CODES if not (match["match_id"] == deleted_match["match_id"] and code == deleted_code))
                        role_writer.writerow({"variant_id": variant, "portfolio_id": portfolio_id, "issue": pool["issue"], "fold": pool["fold"], "year": pool["year"], "pool_id": pool["pool_id"], "match_id": match["match_id"], "match_idx": match["match_idx"], "selection_rank": rank, "e_sp": fmt(float(match["e_sp"])), "p_min": fmt(float(match["p_min"])), "p3": fmt(float(p["3"])), "p1": fmt(float(p["1"])), "p0": fmt(float(p["0"])), "is_deletion_candidate": int(match["match_id"] == candidate["match_id"]), "is_global_deleted_code_match": int(match["match_id"] == deleted_match["match_id"]), "global_deleted_code": deleted_code, "global_deleted_probability": fmt(deleted_probability), "full_allowed_codes": "310", "prune_allowed_codes": prune_codes})
                        representative[str(pool["issue"])].add(str(match["match_id"])); role_count += 1
                    portfolio_count += 1; summary[variant]["deduplicated_portfolios"] += 1; summary[variant]["matched_full_rows"] += 1; summary[variant]["prune_one_rows"] += 1; summary[variant]["full_tickets"] += FULL_K; summary[variant]["prune_tickets"] += PRUNE_K; summary[variant]["full_stake_yuan"] += FULL_K * UNIT_STAKE; summary[variant]["prune_stake_yuan"] += PRUNE_K * UNIT_STAKE
        for handles in (scatter_handles, frontier_handles, role_handles): close_gzip(handles)
        with (stage / "threshold_census.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, lineterminator="\n"); writer.writeheader()
            for variant in VARIANTS:
                writer.writerow({"variant_id": variant, **summary[variant], "exact_stake_reduction_fraction": fmt(1/3)})
        with (stage / "scatter_hexbin_density.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEX_FIELDS, lineterminator="\n"); writer.writeheader(); writer.writerows(hexbin(scatter))
        representatives = sorted(representative)
        selected_issues = [representatives[0], representatives[len(representatives)//2], representatives[-1]] if representatives else []
        for issue in dict.fromkeys(selected_issues):
            (stage / f"scatter_issue_{issue}.svg").write_text(scatter_svg(issue, issue_scatter[issue], representative[issue]), encoding="utf-8")
        card = {"issue": 127, "contract": CONTRACT, "generator_version": VERSION, "stage": "GATE_A_OUTCOME_UNEXPOSED_MATCHED_FREEZE", "provenance": provenance,
                "denominator": {"native_issues": 344, "native_pools": 2659, "frontier_rows": frontier_count, "portfolio_identities": portfolio_count, "role_rows": role_count},
                "variants": VARIANTS, "matched_pair": {"MATCHED_FULL_N7": {"tickets": FULL_K, "stake_yuan": FULL_K * UNIT_STAKE}, "PRUNE_ONE_GLOBAL_N7": {"tickets": PRUNE_K, "stake_yuan": PRUNE_K * UNIT_STAKE}, "stake_reduction_fraction": "1/3"},
                "selection": "Only #101 AVAILABLE native pools can construct a portfolio; every unavailable pool remains an explicit NO_BET row. For each p_min deletion candidate with E_SP floor, include it plus six highest-E_SP other eligible matches in its native pool. Require GM_E_SP. Select exactly one global minimum probability among all 21 selected outcome codes, with p then match_idx then code deterministic tie-breaks; remove only that code.",
                "scatter": {"coordinates": "one row per native #101 member with p_min and E_SP", "hexbin": "fixed .025 p_min × .25 E_SP bins", "representative_issue_rule": "lowest, median and highest issue with a frozen portfolio; SVG uses strict p_min=.30 / E_SP=3.00 reference lines and highlights selected matches"},
                "outcome_boundary": "No result, final SP, payout, tax, ROI, or settlement source is read or emitted. Gate B is NOT_RUN and NOT_AUTHORIZED.", "scope": "historical paper-only research; no purchase, production, or promotion"}
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "runner.py")
        (stage / "README.md").write_text("# #127 Gate A\n\nOutcome-unexposed matched FULL N7 / one-global-code-prune freeze. Run `python runner.py --output <new-dir>`; Gate B is not run.\n", encoding="utf-8")
        gzip_names = ("scatter_coordinates.csv.gz", "matched_frontier.csv.gz", "portfolio_role_assignments.csv.gz")
        controls = tuple(item.name for item in stage.iterdir() if item.is_file() and item.name not in gzip_names)
        def decompressed(path: Path) -> tuple[str, int]:
            digest = hashlib.sha256(); size = 0
            with gzip.open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""): digest.update(block); size += len(block)
            return digest.hexdigest(), size
        content = {"contract_version": CONTENT_VERSION, "gzip_payloads": {name: {"canonical_decompressed_sha256": decompressed(stage / name)[0], "canonical_decompressed_bytes": decompressed(stage / name)[1]} for name in gzip_names}, "non_compressed_controls": {name: sha256(stage / name) for name in controls}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha256(output / "SHA256SUMS.json"), "frontier_rows": frontier_count, "portfolio_identities": portfolio_count, "role_rows": role_count, "representative_issues": selected_issues}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True); raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", type=Path, default=OUTPUT)
    print(json.dumps(freeze(parser.parse_args().output.resolve()), sort_keys=True))


if __name__ == "__main__": main()
