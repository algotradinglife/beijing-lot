#!/usr/bin/env python3
"""Freeze #167's complete N7 selector x allocation atlas (Gate A).

The runner consumes only accepted outcome-unexposed packages.  It deliberately
does not open the canonical outcome join or any settlement/payout/tax field.
The matrix is represented as immutable selector/allocation/seed grids plus
deduplicated selector identities and roles; Gate B must consume these exact
identities without re-selection.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

N = 7
FULL_K = 3 ** N
STAKE = 2
CODES = ("3", "1", "0")
CONTRACT = "BJ-HIST-N7-STRATEGY-ATLAS-001"
VERSION = "bj167-gate-a-v3"
M_GRID = tuple(range(16, 257, 16)) + (512, 1024, 1458, FULL_K)
SEEDS = tuple(f"137{i:03d}" for i in range(1, 101))
WEIGHTS = ("MODEL_P_CAL", "MARKET_WF_CAL", "BLEND_A25", "BLEND_A50", "BLEND_A75", "Q_WEIGHT")
S1_GATES = ("NO_GATE", "ESP280_GM290", "ESP280_GM300", "ESP280_GM305", "ESP290_GM290", "ESP290_GM300", "ESP290_GM305", "ESP300_GM290", "ESP300_GM300", "ESP300_GM305")
TOP_K = (1, 2, 4, 8, 16, "ALL")
REGIMES = (("ESP280_GM290", 2.80, 2.90), ("ESP290_GM300", 2.90, 3.00), ("ESP300_GM305", 3.00, 3.05))
LOWP_SOURCES = ("P_MIN", "MARKET_WF_CAL_MIN", "BLEND_A50_MIN")
LOWP_THRESHOLDS = (0.15, 0.20, 0.25, 0.30)
RANKERS = ("COLD_FIRST", "VALUE_FIRST")
MECHANISMS = ("WR_DUPLICATE_STAKE", "WOR_DISTINCT", "RESIDUAL_SYSTEMATIC", "CAPPED_REPEAT", "DETERMINISTIC_TOP_MASS", "FULL_ENUMERATED", "P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE")
CAPS = (1, 2, 4, 8)

SOURCE_MANIFESTS = {
    "bj127_gate_a_preoutcome_v2": "a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da",
    "bj137_gate_a_preoutcome_v2": "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df",
    "bj145_gate_a_preoutcome_v8": "da1165d3d2be49deac85a494443ba04606d176ca059c265857573ce24360114c",
    "bj148_gate_a_preoutcome_v1": "fd4a0f4dc0ab5ef97f3c260a082515aa7874a60a1ac1e5e0ecd865fdb1eeafd6",
    "bj151_gate_a_preoutcome_v1": "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6",
    "bj159_gate_a_preoutcome_v2r1": "a15c585fc1836da4f558d07ce19c925561bfd1c240e834b7e3e0da22701cd325",
}


def repo() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo()
SOURCE = ROOT / "results"
OUTPUT = SOURCE / "bj167_gate_a_strategy_atlas_v3"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def compact(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verified_bundle(name: str) -> dict[str, str]:
    directory = SOURCE / name
    manifest = directory / "SHA256SUMS.json"
    if sha(manifest) != SOURCE_MANIFESTS[name]:
        raise RuntimeError(f"source manifest mismatch: {name}")
    declared = json.loads(manifest.read_text(encoding="utf-8"))
    actual = {p.name: sha(p) for p in directory.iterdir() if p.is_file() and p.name != manifest.name}
    if declared != actual:
        raise RuntimeError(f"source coverage drift: {name}")
    return declared


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fields: tuple[str, ...], rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader(); writer.writerows(rows)


def write_gzip(path: Path, fields: tuple[str, ...], rows) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
            writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n", extrasaction="raise")
            writer.writeheader(); writer.writerows(rows); text.flush(); text.detach()


SHARD_ROWS = 200_000


class ShardWriter:
    def __init__(self, directory: Path, stem: str, fields: tuple[str, ...], rows_per_shard: int = SHARD_ROWS):
        self.directory, self.stem, self.fields = directory, stem, rows_per_shard and fields
        self.rows_per_shard = rows_per_shard
        self.part = -1
        self.count = 0
        self.raw = self.zipped = self.text = self.writer = None
        self._open()

    def _open(self):
        self.part += 1; self.count = 0
        path = self.directory / f"{self.stem}-{self.part:03d}.csv.gz"
        self.raw = path.open("wb")
        self.zipped = gzip.GzipFile(filename="", mode="wb", fileobj=self.raw, mtime=0)
        self.text = io.TextIOWrapper(self.zipped, encoding="utf-8", newline="")
        self.writer = csv.DictWriter(self.text, fieldnames=self.fields, lineterminator="\n", extrasaction="raise")
        self.writer.writeheader()

    def writerow(self, row):
        if self.count >= self.rows_per_shard:
            self._close(); self._open()
        self.writer.writerow(row); self.count += 1

    def _close(self):
        if self.text is not None:
            self.text.flush(); self.text.detach(); self.zipped.close(); self.raw.close()
            self.raw = self.zipped = self.text = self.writer = None

    def close(self):
        self._close()


def iter_gzip_shards(directory: Path, stem: str):
    for path in sorted(directory.glob(f"{stem}-*.csv.gz")):
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            yield from csv.DictReader(handle)


def fmt(value: float) -> str:
    if not math.isfinite(value):
        raise RuntimeError("non-finite output")
    return f"{value:.12f}"


def key_issue(row: dict[str, str]) -> str:
    return row["issue_instance"]


IDENTITY_FIELDS = ("selector_id", "family", "selector_rank", "issue", "fold", "year", "issue_instance", "portfolio_id", "candidate_match_id", "selected_match_ids", "selected_n", "gm_e_sp", "identity_fingerprint", "outcome_boundary")


def identity_row(selector_id: str, family: str, selector_rank: int, source: dict[str, str], roles: list[dict[str, str]]) -> dict[str, object]:
    selected = tuple(r["match_id"] for r in roles) if roles else tuple(filter(None, source.get("selected_match_ids", "").split("|")))
    return {
        "selector_id": selector_id, "family": family, "selector_rank": selector_rank,
        "issue": source["issue"], "fold": source["fold"], "year": source["year"], "issue_instance": source["issue_instance"],
        "portfolio_id": source["portfolio_id"], "candidate_match_id": source.get("candidate_match_id", ""),
        "selected_match_ids": "|".join(selected), "selected_n": len(selected),
        "gm_e_sp": fmt(math.exp(sum(math.log(max(float(r["e_sp"]), 1e-12)) for r in roles) / len(roles))) if roles else source.get("gm_e_sp", ""),
        "identity_fingerprint": compact([selector_id, source["portfolio_id"], selected]),
        "outcome_boundary": "Gate A: no outcome/final-SP/payout/tax/ROI/settlement input read or emitted",
    }


def build_s1(identities: list[dict[str, str]], participation: list[dict[str, str]]):
    ids_by_gate_issue: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in identities:
        ids_by_gate_issue[(row["gate_id"], row["issue_instance"])].append(row)
    census, output = [], []
    for gate in S1_GATES:
        for k in TOP_K:
            selector = f"S1_{gate}_{'K_ALL' if k == 'ALL' else 'K'+str(k)}"
            for issue in sorted({key_issue(r) for r in participation}):
                candidates = sorted(ids_by_gate_issue.get((gate, issue), []), key=lambda r: (int(r.get("candidate_rank_in_complete_issue", "999999")), r["portfolio_id"]))
                selected = candidates if k == "ALL" else [r for r in candidates if int(r.get("candidate_rank_in_complete_issue", "999999")) <= int(k)]
                # Use the participation row for complete issue metadata and explicit no-bet retention.
                meta = next(r for r in participation if r["issue_instance"] == issue and r["gate_id"] == gate and r["top_k_id"] == "K_ALL")
                status = "AVAILABLE" if len(selected) >= (1 if k == 1 else int(k) if k != "ALL" else 1) else "NO_BET_K_UNSATISFIED"
                if not selected:
                    status = "NO_BET_K_UNSATISFIED"
                selected_ids = {r["portfolio_id"] for r in selected}
                for rank, identity in enumerate(selected, 1):
                    output.append(identity_row(selector, "S1_GATE_TOPK", rank, identity, []))
                census.append({
                    "selector_id": selector, "family": "S1_GATE_TOPK", "gate_id": gate, "top_k": k,
                    "issue": meta["issue"], "fold": meta["fold"], "year": meta["year"], "issue_instance": issue,
                    "selection_status": status, "candidate_identity_count": len(candidates), "selected_identity_count": len(selected),
                    "selected_portfolio_ids_sha256": compact(sorted(selected_ids)), "selection_scope": "COMPLETE_ISSUE",
                    "no_bet_reason": "" if selected else "INSUFFICIENT_IDENTITIES_FOR_TOP_K", "outcome_boundary": "outcome-unexposed",
                })
    return census, output


def build_s2(match_vectors: list[dict[str, str]], issues: list[dict[str, str]], identity_path: Path):
    by_issue: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in match_vectors:
        by_issue[row["issue_instance"]].append(row)
    census = []
    tmp = identity_path.with_suffix(".csv")
    text = tmp.open("w", newline="", encoding="utf-8")
    writer = csv.DictWriter(text, fieldnames=IDENTITY_FIELDS, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    issue_keys = sorted({r["issue_instance"] for r in issues})
    for regime, e_floor, gm_floor in REGIMES:
        for lowp in LOWP_SOURCES:
            for threshold in LOWP_THRESHOLDS:
                for ranker in RANKERS:
                    base = f"S2_{regime}_{lowp}_LOWP{int(threshold*100):02d}_{ranker}"
                    for issue in issue_keys:
                        rows = by_issue.get(issue, [])
                        def pmin(r):
                            if lowp == "P_MIN": return float(r["p_min"])
                            cols = ("market_cal3", "market_cal1", "market_cal0") if lowp == "MARKET_WF_CAL_MIN" else ("blend_a50_3", "blend_a50_1", "blend_a50_0")
                            return min(float(r[c]) for c in cols)
                        anchors = [r for r in rows if pmin(r) <= threshold]
                        identities: list[dict[str, object]] = []
                        seen: set[str] = set()
                        for anchor in sorted(anchors, key=lambda r: ((pmin(r), -float(r["e_sp"]), int(r["match_idx"]), r["match_id"]) if ranker == "COLD_FIRST" else (-float(r["e_sp"]), pmin(r), int(r["match_idx"]), r["match_id"]))):
                            companions = [r for r in rows if r["match_id"] != anchor["match_id"] and float(r["e_sp"]) >= e_floor]
                            companions = sorted(companions, key=lambda r: (-float(r["e_sp"]), float(r["p_min"]), int(r["match_idx"]), r["match_id"]))[:6]
                            selected = sorted([anchor, *companions], key=lambda r: (-float(r["e_sp"]), float(r["p_min"]), int(r["match_idx"]), r["match_id"]))
                            if len(selected) != N:
                                continue
                            gm = math.exp(sum(math.log(max(float(r["e_sp"]), 1e-12)) for r in selected) / N)
                            if gm < gm_floor:
                                continue
                            sig = "|".join(r["match_id"] for r in selected)
                            if sig in seen:
                                continue
                            seen.add(sig)
                            pseudo = {"portfolio_id": compact([base, issue, sig]), "candidate_match_id": anchor["match_id"], **next(r for r in issues if r["issue_instance"] == issue)}
                            pseudo["portfolio_id"] = compact([base, issue, sig])
                            identities.append({"source": pseudo, "roles": selected, "anchor_rank": len(identities) + 1, "gm": gm})
                        for k in TOP_K:
                            selector = f"{base}_{'K_ALL' if k == 'ALL' else 'K'+str(k)}"
                            chosen = identities if k == "ALL" else identities[:int(k)]
                            meta = next(r for r in issues if r["issue_instance"] == issue)
                            status = "AVAILABLE" if chosen else "NO_BET_K_UNSATISFIED"
                            for rank, item in enumerate(chosen, 1):
                                source = item["source"]
                                row = identity_row(selector, "S2_COMPLETE_ISSUE_LOWP", rank, source, item["roles"])
                                row["candidate_match_id"] = source["candidate_match_id"]; row["gm_e_sp"] = fmt(item["gm"])
                                writer.writerow(row)
                            census.append({
                                "selector_id": selector, "family": "S2_COMPLETE_ISSUE_LOWP", "gate_id": regime,
                                "top_k": k, "lowp_source": lowp, "lowp_threshold": fmt(threshold), "ranker": ranker,
                                "e_sp_min": fmt(e_floor), "gm_e_sp_min": fmt(gm_floor), "issue": meta["issue"], "fold": meta["fold"], "year": meta["year"], "issue_instance": issue,
                                "selection_status": status, "candidate_identity_count": len(identities), "selected_identity_count": len(chosen),
                                "selected_portfolio_ids_sha256": compact([item["source"]["portfolio_id"] for item in chosen]), "selection_scope": "COMPLETE_ISSUE",
                                "no_bet_reason": "" if chosen else "NO_QUALIFYING_COLD_ANCHOR", "outcome_boundary": "outcome-unexposed",
                            })
    text.close()
    with tmp.open("rb") as source_file, identity_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            shutil.copyfileobj(source_file, zipped)
    tmp.unlink(missing_ok=True)
    return census


def allocation_grid():
    rows = []
    for weight in WEIGHTS:
        for mechanism in MECHANISMS:
            ms = (FULL_K,) if mechanism == "FULL_ENUMERATED" else M_GRID
            caps = CAPS if mechanism == "CAPPED_REPEAT" else ("NA",)
            seeds = SEEDS if mechanism in {"WR_DUPLICATE_STAKE", "WOR_DISTINCT"} else ("NA",)
            for cap in caps:
                for m in ms:
                    for seed in seeds:
                        rows.append({"cell_id": compact([weight, mechanism, cap, m, seed]), "weight_source": weight, "mechanism": mechanism, "cap": cap, "M": m, "seed": seed, "seed_role": "STOCHASTIC_100" if seed != "NA" else "DETERMINISTIC", "ticket_space_k": FULL_K, "per_ticket_stake_yuan": STAKE, "duplicate_policy": "each ¥2 copy is an independent ticket/tax unit; no pooling", "outcome_boundary": "pre-outcome allocation specification only"})
    return rows


def baseline_rows():
    return [
        {"baseline_id":"B127_ESP300_GM305_LOWP20", "source_issue":"#127", "manifest":SOURCE_MANIFESTS["bj127_gate_a_preoutcome_v2"], "cohort":"segment-scoped legacy reference", "selector":"ESP300_GM305_LOWP20", "pre_tax_roi":"-0.0835", "matched_full_lift":"", "evidence_grade":"LEGACY_REFERENCE", "decision":"reference_only", "reason":"segment denominator; not comparable complete-issue FULL"},
        {"baseline_id":"B137_151_DISCOVERY", "source_issue":"#137/#151", "manifest":SOURCE_MANIFESTS["bj151_gate_a_preoutcome_v1"], "cohort":"NO_GATE/K4/Q-WOR/M64 three-seed anchor", "selector":"NO_GATE/K4", "pre_tax_roi":"0.1027", "matched_full_lift":"", "evidence_grade":"DISCOVERY", "decision":"challenger_not_baseline", "reason":"three seeds; discovery not robust"},
        {"baseline_id":"B159_TRANSFER", "source_issue":"#159", "manifest":SOURCE_MANIFESTS["bj159_gate_a_preoutcome_v2r1"], "cohort":"complete-issue ESP transfer", "selector":"ESP transfer", "pre_tax_roi":"-0.20", "matched_full_lift":"", "evidence_grade":"DISCOVERY", "decision":"diagnostic_only", "reason":"transfer diagnostic; does not demote stronger scoped incumbent"},
    ]


def freeze(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing overwrite: {output}")
    for name in SOURCE_MANIFESTS:
        verified_bundle(name)
    gate137 = SOURCE / "bj137_gate_a_preoutcome_v2"
    issues = read_csv(gate137 / "issue_census.csv")
    participation = read_csv(gate137 / "issue_participation_grid.csv")
    identities = read_gzip(gate137 / "n7_identities.csv.gz")
    match_vectors = read_csv(gate137 / "match_vectors.csv")
    if len(issues) != 348 or len(match_vectors) != 47819 or len(identities) != 71704:
        raise RuntimeError("#137 denominator drift")
    stage = Path(tempfile.mkdtemp(prefix=".bj167_gate_a_v3_", dir=SOURCE))
    try:
        s1_census, s1_ids = build_s1(identities, participation)
        s2_identity_tmp = stage / "s2_identity.tmp.csv.gz"
        s2_census = build_s2(match_vectors, issues, s2_identity_tmp)
        census = s1_census + s2_census
        census_fields = tuple(sorted({k for row in census for k in row}))
        write_csv(stage / "selector_census.csv", census_fields, census)
        role_fields = ("selector_id","family","issue_instance","portfolio_id","match_id","match_idx","selection_rank","kickoff_ts","e_sp","p_min","p_model3","p_model1","p_model0","p_market_cal3","p_market_cal1","p_market_cal0","p_blend_a50_3","p_blend_a50_1","p_blend_a50_0","q_weight3","q_weight1","q_weight0","outcome_boundary")
        identity_sink = ShardWriter(stage, "selector_identities", IDENTITY_FIELDS)
        try:
            for row in s1_ids: identity_sink.writerow(row)
            with gzip.open(s2_identity_tmp, "rt", newline="", encoding="utf-8") as s2f:
                for row in csv.DictReader(s2f): identity_sink.writerow(row)
        finally:
            identity_sink.close()
        vector_by_id = {r["match_id"]: r for r in match_vectors}
        selected_keys = {(r["gate_id"], r["portfolio_id"]) for r in identities if r["portfolio_id"]}
        role_lookup: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        with gzip.open(gate137 / "n7_role_vectors.csv.gz", "rt", newline="", encoding="utf-8") as rf:
            for role in csv.DictReader(rf):
                if (role["gate_id"], role["portfolio_id"]) in selected_keys:
                    role_lookup[(role["gate_id"], role["portfolio_id"])].append(role)
        role_count = 0
        role_sink = ShardWriter(stage, "selector_role_vectors", role_fields)
        try:
            for identity in iter_gzip_shards(stage, "selector_identities"):
                    source_roles = role_lookup.get(("NO_GATE", identity["portfolio_id"]), [])
                    by_match = {r["match_id"]: r for r in source_roles}
                    for rank, match_id in enumerate(filter(None, identity["selected_match_ids"].split("|")), 1):
                        src = by_match.get(match_id, vector_by_id[match_id])
                        role_sink.writerow({"selector_id":identity["selector_id"],"family":identity["family"],"issue_instance":identity["issue_instance"],"portfolio_id":identity["portfolio_id"],"match_id":match_id,"match_idx":src.get("match_idx",""),"selection_rank":rank,"kickoff_ts":src.get("kickoff_ts",""),"e_sp":src.get("e_sp",""),"p_min":src.get("p_min",""),"p_model3":src.get("p_model3",src.get("p3","")),"p_model1":src.get("p_model1",src.get("p1","")),"p_model0":src.get("p_model0",src.get("p0","")),"p_market_cal3":src.get("p_market_cal3",""),"p_market_cal1":src.get("p_market_cal1",""),"p_market_cal0":src.get("p_market_cal0",""),"p_blend_a50_3":src.get("p_blend_a50_3",""),"p_blend_a50_1":src.get("p_blend_a50_1",""),"p_blend_a50_0":src.get("p_blend_a50_0",""),"q_weight3":src.get("q_weight3",src.get("q3","")),"q_weight1":src.get("q_weight1",src.get("q1","")),"q_weight0":src.get("q_weight0",src.get("q0","")),"outcome_boundary":"Gate A: outcome-unexposed"})
                        role_count += 1
        finally:
            role_sink.close()
        s2_identity_tmp.unlink(missing_ok=True)
        write_csv(stage / "selector_grid.csv", ("selector_id","family","gate_id","top_k","lowp_source","lowp_threshold","ranker","e_sp_min","gm_e_sp_min","selection_scope","outcome_boundary"), [
            {"selector_id": row["selector_id"], "family": row["family"], "gate_id": row.get("gate_id", ""), "top_k": row.get("top_k", ""), "lowp_source": row.get("lowp_source", ""), "lowp_threshold": row.get("lowp_threshold", ""), "ranker": row.get("ranker", ""), "e_sp_min": row.get("e_sp_min", ""), "gm_e_sp_min": row.get("gm_e_sp_min", ""), "selection_scope":"COMPLETE_ISSUE", "outcome_boundary":"outcome-unexposed"} for row in census if row["issue_instance"] == issues[0]["issue_instance"]
        ])
        grid = allocation_grid()
        write_csv(stage / "allocation_grid.csv", tuple(grid[0].keys()), grid)
        write_csv(stage / "baseline_registry.csv", tuple(baseline_rows()[0].keys()), baseline_rows())
        write_csv(stage / "source_census.csv", ("source","manifest_sha256","role","outcome_boundary"), [{"source":name,"manifest_sha256":SOURCE_MANIFESTS[name],"role":"accepted immutable outcome-unexposed upstream or historical anchor","outcome_boundary":"no outcomes opened in Gate A"} for name in SOURCE_MANIFESTS])
        card = {"issue":167,"contract":CONTRACT,"generator_version":VERSION,"stage":"GATE_A_OUTCOME_UNEXPOSED_COMPLETE_SELECTOR_ALLOCATION_ATLAS","selector_families":{"S1_GATE_TOPK": {"selectors":len(S1_GATES)*len(TOP_K),"gates":list(S1_GATES),"top_k":list(TOP_K)},"S2_COMPLETE_ISSUE_LOWP":{"selectors":len(REGIMES)*len(LOWP_SOURCES)*len(LOWP_THRESHOLDS)*len(RANKERS)*len(TOP_K),"regimes":[r[0] for r in REGIMES],"lowp_sources":list(LOWP_SOURCES),"thresholds":list(LOWP_THRESHOLDS),"rankers":list(RANKERS),"top_k":list(TOP_K)}},"allocation":{"weights":list(WEIGHTS),"mechanisms":list(MECHANISMS),"M_grid":list(M_GRID),"caps":list(CAPS),"seed_count":len(SEEDS),"seeds":list(SEEDS),"ticket_space_k":FULL_K},"denominator":{"issue_rows":len(issues),"match_rows":len(match_vectors),"source_identity_rows":len(identities),"selector_census_rows":len(census),"selector_identity_rows":sum(int(row["selected_identity_count"]) for row in census),"selector_role_rows":role_count,"allocation_grid_rows":len(grid)},"source_manifests":SOURCE_MANIFESTS,"outcome_boundary":"No result code, final SP, payout, tax, ROI, settlement, or post-outcome input read or emitted; Gate B unauthorized until PI accepts this exact package.","baseline_ratchet":"baseline_registry.csv retains #127 legacy, #137/#151 discovery, and #159 transfer diagnostics without replacing the comparable incumbent."}
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True)+"\n",encoding="utf-8")
        (stage / "README.md").write_text("#167 Gate A v3 freezes the complete finite N7 selector × allocation atlas. It contains no outcomes. Selector identities are complete-issue and are not reselected at Gate B. Every ¥2 ticket/repeat remains an independent future tax unit; no issue/policy pooling is allowed. Gate B must consume this package exactly. Temporary staging is under results/.scratch, never /tmp.\n",encoding="utf-8")
        shutil.copy2(__file__, stage / "freeze_runner.py")
        shard_names = sorted(p.name for p in stage.iterdir() if p.name.startswith("selector_identities-") or p.name.startswith("selector_role_vectors-"))
        content = {"contract_version":"bj167-gate-a-content-v3","gzip_payloads": {name:{"canonical_compressed_sha256": sha(stage/name)} for name in shard_names},"controls": {p.name:sha(p) for p in stage.iterdir() if p.is_file() and p.name not in {"SHA256SUMS.json","CONTENT_IDENTITY.json",*shard_names}}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        manifest = {p.name:sha(p) for p in sorted(stage.iterdir()) if p.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        os.replace(stage, output)
        return {"output":str(output),"manifest_sha256":sha(output/"SHA256SUMS.json"),"content_identity_sha256":sha(output/"CONTENT_IDENTITY.json"),"counts":card["denominator"]}
    except Exception:
        shutil.rmtree(stage,ignore_errors=True); raise


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path,default=OUTPUT)
    print(json.dumps(freeze(parser.parse_args().output.resolve()),sort_keys=True))
