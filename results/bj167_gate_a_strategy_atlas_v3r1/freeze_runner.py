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
VERSION = "bj167-gate-a-v3r1"
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
SOURCE_CONTENT_IDS = {
    "bj127_gate_a_preoutcome_v2": "ac99388115df79c6c76b13f5d168ab9d3607b3db508c0a467025b1a7f79db29c",
    "bj137_gate_a_preoutcome_v2": "36d6afcc33a5b5ceb3e4a990bfe6ec05503be115270c3489f4973dc3a59dd236",
    "bj145_gate_a_preoutcome_v8": "074c9b06c024a1db80b5b53cfc99a1bc164001b205fcd94a0c159daf445dab7f",
    "bj148_gate_a_preoutcome_v1": "dfd3ac234f95f28185a09a6bb2f69c3ff66ddb696ce1fe45a6a1215d932dcd0a",
    "bj151_gate_a_preoutcome_v1": "ac36bc2422d1afd22c3bb4bd680568401cbaec30e0d2006d13afcdfa141b89a5",
    "bj159_gate_a_preoutcome_v2r1": "4ec52432ec6c1779bab33b0c4bdc4e381b0ae7434228637c509970291ed7361e",
}


def repo() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo()
SOURCE = ROOT / "results"
OUTPUT = SOURCE / "bj167_gate_a_strategy_atlas_v3r1"


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
    content_identity = directory / "CONTENT_IDENTITY.json"
    if name in SOURCE_CONTENT_IDS and sha(content_identity) != SOURCE_CONTENT_IDS[name]:
        raise RuntimeError(f"source content identity mismatch: {name}")
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


def csv_line(fields: tuple[str, ...], row: dict[str, object]) -> bytes:
    text = io.StringIO(newline="")
    writer = csv.writer(text, lineterminator="\n")
    writer.writerow([row.get(field, field if row.get("__header__") else "") for field in fields])
    return text.getvalue().encode("utf-8")


def first_value(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name, "")
        if value not in (None, ""):
            return value
    return ""


def probability_vector(row: dict[str, str], names: tuple[str, str, str], label: str) -> tuple[str, str, str]:
    values = tuple(first_value(row, name) for name in names)
    if any(value == "" for value in values):
        raise RuntimeError(f"missing probability vector {label}: {row.get('match_id', '')}")
    numbers = tuple(float(value) for value in values)
    if any((not math.isfinite(value)) or value < 0 for value in numbers) or abs(sum(numbers) - 1.0) > 2e-9:
        raise RuntimeError(f"invalid probability vector {label}: {row.get('match_id', '')} {numbers}")
    return tuple(fmt(value) for value in numbers)


def normalised_role(src: dict[str, str], selector: str, family: str, issue_instance: str, portfolio_id: str, match_id: str, rank: int) -> dict[str, object]:
    model = probability_vector(src, ("p_model3", "p_model1", "p_model0"), "MODEL_P_CAL") if "p_model3" in src else probability_vector(src, ("p3", "p1", "p0"), "MODEL_P_CAL")
    market = probability_vector(src, ("p_market_cal3", "p_market_cal1", "p_market_cal0"), "MARKET_WF_CAL") if "p_market_cal3" in src else probability_vector(src, ("market_cal3", "market_cal1", "market_cal0"), "MARKET_WF_CAL")
    a25 = probability_vector(src, ("p_blend_a25_3", "p_blend_a25_1", "p_blend_a25_0"), "BLEND_A25") if "p_blend_a25_3" in src else probability_vector(src, ("blend_a25_3", "blend_a25_1", "blend_a25_0"), "BLEND_A25")
    a50 = probability_vector(src, ("p_blend_a50_3", "p_blend_a50_1", "p_blend_a50_0"), "BLEND_A50") if "p_blend_a50_3" in src else probability_vector(src, ("blend_a50_3", "blend_a50_1", "blend_a50_0"), "BLEND_A50")
    a75 = probability_vector(src, ("p_blend_a75_3", "p_blend_a75_1", "p_blend_a75_0"), "BLEND_A75") if "p_blend_a75_3" in src else probability_vector(src, ("blend_a75_3", "blend_a75_1", "blend_a75_0"), "BLEND_A75")
    q = probability_vector(src, ("q_weight3", "q_weight1", "q_weight0"), "Q_WEIGHT") if "q_weight3" in src else probability_vector(src, ("q3", "q1", "q0"), "Q_WEIGHT")
    return {"selector_id": selector, "family": family, "issue_instance": issue_instance, "portfolio_id": portfolio_id, "match_id": match_id, "match_idx": first_value(src, "match_idx"), "selection_rank": rank, "kickoff_ts": first_value(src, "kickoff_ts"), "e_sp": first_value(src, "e_sp"), "p_min": first_value(src, "p_min"), "p_model3": model[0], "p_model1": model[1], "p_model0": model[2], "p_market_cal3": market[0], "p_market_cal1": market[1], "p_market_cal0": market[2], "p_blend_a25_3": a25[0], "p_blend_a25_1": a25[1], "p_blend_a25_0": a25[2], "p_blend_a50_3": a50[0], "p_blend_a50_1": a50[1], "p_blend_a50_0": a50[2], "p_blend_a75_3": a75[0], "p_blend_a75_1": a75[1], "p_blend_a75_0": a75[2], "q_weight3": q[0], "q_weight1": q[1], "q_weight0": q[2], "outcome_boundary": "Gate A: outcome-unexposed"}


def shard_reconciliation(directory: Path, stem: str, fields: tuple[str, ...], key_fields: tuple[str, ...]) -> tuple[list[dict[str, object]], dict[str, object]]:
    index = []
    whole = hashlib.sha256()
    whole.update(csv_line(fields, {"__header__": True}))
    total = 0
    for path in sorted(directory.glob(f"{stem}-*.csv.gz")):
        compressed_hash = sha(path)
        decompressed = hashlib.sha256()
        rows = 0; first_key = ""; last_key = ""
        with gzip.open(path, "rb") as raw:
            for block in iter(lambda: raw.read(1 << 20), b""):
                decompressed.update(block)
        with gzip.open(path, "rt", newline="", encoding="utf-8") as text:
            reader = csv.DictReader(text)
            for row in reader:
                key = "|".join(str(row.get(field, "")) for field in key_fields)
                first_key = first_key or key; last_key = key
                whole.update(csv_line(fields, row)); rows += 1; total += 1
        index.append({"kind": stem, "filename": path.name, "row_count": rows, "first_key": first_key, "last_key": last_key, "compressed_sha256": compressed_hash, "decompressed_sha256": decompressed.hexdigest(), "key_fields": "|".join(key_fields)})
    return index, {"kind": stem, "row_count": total, "canonical_decompressed_sha256": whole.hexdigest(), "shard_count": len(index), "key_fields": "|".join(key_fields)}


def fmt(value: float) -> str:
    if not math.isfinite(value):
        raise RuntimeError("non-finite output")
    return f"{value:.12f}"


def key_issue(row: dict[str, str]) -> str:
    return row["issue_instance"]


IDENTITY_FIELDS = ("selector_id", "family", "selector_rank", "source_gate_id", "issue", "fold", "year", "issue_instance", "portfolio_id", "candidate_match_id", "selected_match_ids", "selected_n", "gm_e_sp", "identity_fingerprint", "outcome_boundary")

# These are the six complete, outcome-unexposed role vectors required by the
# controlling contract.  Source packages use both the compact (p3/market_cal3)
# and expanded (p_model3/p_market_cal3) spellings, so the writer normalises
# both spellings into one stable ledger schema.
ROLE_FIELDS = ("selector_id", "family", "issue_instance", "portfolio_id", "match_id", "match_idx", "selection_rank", "kickoff_ts", "e_sp", "p_min", "p_model3", "p_model1", "p_model0", "p_market_cal3", "p_market_cal1", "p_market_cal0", "p_blend_a25_3", "p_blend_a25_1", "p_blend_a25_0", "p_blend_a50_3", "p_blend_a50_1", "p_blend_a50_0", "p_blend_a75_3", "p_blend_a75_1", "p_blend_a75_0", "q_weight3", "q_weight1", "q_weight0", "outcome_boundary")
VECTOR_GROUPS = {
    "MODEL_P_CAL": ("p_model3", "p_model1", "p_model0"),
    "MARKET_WF_CAL": ("p_market_cal3", "p_market_cal1", "p_market_cal0"),
    "BLEND_A25": ("p_blend_a25_3", "p_blend_a25_1", "p_blend_a25_0"),
    "BLEND_A50": ("p_blend_a50_3", "p_blend_a50_1", "p_blend_a50_0"),
    "BLEND_A75": ("p_blend_a75_3", "p_blend_a75_1", "p_blend_a75_0"),
    "Q_WEIGHT": ("q_weight3", "q_weight1", "q_weight0"),
}


def identity_row(selector_id: str, family: str, selector_rank: int, source: dict[str, str], roles: list[dict[str, str]]) -> dict[str, object]:
    selected = tuple(r["match_id"] for r in roles) if roles else tuple(filter(None, source.get("selected_match_ids", "").split("|")))
    return {
        "selector_id": selector_id, "family": family, "selector_rank": selector_rank,
        "source_gate_id": source.get("gate_id", ""),
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
    participation_by_key = {(row["gate_id"], row["issue_instance"], row["top_k_id"]): row for row in participation}
    census, output = [], []
    for gate in S1_GATES:
        for k in TOP_K:
            selector = f"S1_{gate}_{'K_ALL' if k == 'ALL' else 'K'+str(k)}"
            for issue in sorted({key_issue(r) for r in participation if r["gate_id"] == gate}):
                candidates = sorted(ids_by_gate_issue.get((gate, issue), []), key=lambda r: (int(r["participation_rank"]), r["portfolio_id"]))
                candidate_by_id = {r["portfolio_id"]: r for r in candidates}
                meta = participation_by_key[(gate, issue, "K_ALL")]
                requested = None if k == "ALL" else int(k)

                # For the published #137 grid, use the accepted selected IDs
                # verbatim for K1/K2/K4/K8/K_ALL.  K16 is the pre-registered
                # extension of the same participation_rank ordering.  This
                # avoids silently substituting candidate_rank_in_complete_issue.
                if k == "ALL":
                    selected_ids = [x for x in meta["selected_portfolio_ids"].split("|") if x]
                elif k in (1, 2, 4, 8):
                    accepted = participation_by_key[(gate, issue, f"K{k}")]
                    selected_ids = [x for x in accepted["selected_portfolio_ids"].split("|") if x]
                    expected_count = int(accepted["selected_identity_count"])
                    if len(selected_ids) != expected_count:
                        raise RuntimeError(f"#137 participation count drift: {gate}/{issue}/K{k}")
                    if set(selected_ids) - set(candidate_by_id):
                        raise RuntimeError(f"#137 participation identity drift: {gate}/{issue}/K{k}")
                else:
                    selected_ids = [r["portfolio_id"] for r in candidates[:requested]] if len(candidates) >= requested else []
                selected = [candidate_by_id[x] for x in selected_ids if x in candidate_by_id]
                if len(selected_ids) != len(selected):
                    raise RuntimeError(f"selected identity lookup drift: {gate}/{issue}/{k}")
                if requested is not None and len(candidates) < requested:
                    selected = []
                    selected_ids = []
                status = "AVAILABLE" if selected else "NO_BET_K_UNSATISFIED"
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
    # Emit only effective parameter cells.  FULL is one control regardless of
    # weight/M; global-delete controls are one structural control each.  The
    # remaining mechanisms retain every parameter that changes execution.
    for mechanism in MECHANISMS:
        if mechanism == "FULL_ENUMERATED":
            specs = [("NA", mechanism, "NA", FULL_K, "NA")]
        elif mechanism in {"P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE"}:
            specs = [("NA", mechanism, "NA", "NA", "NA")]
        else:
            specs = []
            ms = M_GRID
            caps = CAPS if mechanism == "CAPPED_REPEAT" else ("NA",)
            seeds = SEEDS if mechanism in {"WR_DUPLICATE_STAKE", "WOR_DISTINCT"} else ("NA",)
            for weight in WEIGHTS:
                for cap in caps:
                    for m in ms:
                        for seed in seeds:
                            specs.append((weight, mechanism, cap, m, seed))
        for weight, mechanism, cap, m, seed in specs:
            effective = [weight, mechanism, cap, m, seed]
            rows.append({"cell_id": compact(effective), "effective_parameter_key": json.dumps(effective, separators=(",", ":")), "weight_source": weight, "mechanism": mechanism, "cap": cap, "M": m, "seed": seed, "seed_role": "STOCHASTIC_100" if seed != "NA" else "DETERMINISTIC", "ticket_space_k": FULL_K, "per_ticket_stake_yuan": STAKE, "duplicate_policy": "each ¥2 copy is an independent ticket/tax unit; no pooling", "outcome_boundary": "pre-outcome allocation specification only"})
    if len(rows) != 24723 or len({r["effective_parameter_key"] for r in rows}) != len(rows):
        raise RuntimeError(f"effective allocation grid drift: rows={len(rows)} unique={len({r['effective_parameter_key'] for r in rows})}")
    return rows


def baseline_rows():
    fields = ("baseline_id", "source_issue_package", "source_manifest", "reference_outcome_package", "cohort_denominator", "common_support_hash", "selector", "weight_vector", "mechanism", "M", "seed_aggregation", "stake_rule", "pre_tax_roi", "matched_full_lift", "seed_mcse", "positive_seed_fraction", "bootstrap_lower", "bootstrap_upper", "ex_largest_issue_roi", "ex_largest_year_roi", "evidence_grade", "incumbent_or_challenger", "added_lever", "decision_reason", "outcome_boundary")
    rows = [
        ("B127_LEGACY", "#127 / bj127_gate_a_preoutcome_v2", SOURCE_MANIFESTS["bj127_gate_a_preoutcome_v2"], "historical #127 settled reference", "segment-scoped ESP300_GM305_LOWP20; not complete-issue matched", "SEGMENT_SCOPE_ONLY", "ESP300_GM305_LOWP20", "NA", "FULL", "NA", "NA", "¥2 per ticket; legacy accounting", "-0.0835", "NA", "NA", "NA", "NA", "NA", "NA", "NA", "LEGACY_REFERENCE", "historical reference", "legacy selection line", "reference only; denominator warning prevents matched-baseline promotion", "Gate-A records immutable reference metadata; no outcome join opened"),
        ("B151_V2R3_ANCHOR", "#151/#167-v2 fixed candidate", SOURCE_MANIFESTS["bj151_gate_a_preoutcome_v1"], "bj167_gate_b_outcome_settlement_v2r3", "339 complete-issue available rows; exact #137 NO_GATE/K4 support", "BJ137_NO_GATE_K4_SUPPORT", "NO_GATE/K4", "Q_WEIGHT", "WOR_DISTINCT", "64", "100 seeds 137001..137100", "¥2 per winning ticket; no pooling", "REFERENCE_IN_V2R3", "REFERENCE_IN_V2R3", "REFERENCE_IN_V2R3", "REFERENCE_IN_V2R3", "REFERENCE_IN_V2R3", "REFERENCE_IN_V2R3", "REFERENCE_IN_V2R3", "REFERENCE_IN_V2R3", "DISCOVERY", "historical anchor", "fixed #137 positive cohort", "preserve as named anchor; v2r3 metrics are not recomputed or used to replace the atlas baseline", "Outcome metrics remain in the separately immutable v2r3 package; Gate-A emits reference only"),
        ("B159_TRANSFER", "#159 / bj159_gate_a_preoutcome_v2r1", SOURCE_MANIFESTS["bj159_gate_a_preoutcome_v2r1"], "bj167-v1/v1r2 named transfer diagnostic", "complete-issue ESP transfer cohort; not the #137 common-support cohort", "ESP_TRANSFER_SUPPORT", "ESP transfer", "NA", "NA", "NA", "100 seeds in prior diagnostic", "¥2 per ticket; no pooling", "REFERENCE_IN_DIAGNOSTIC", "REFERENCE_IN_DIAGNOSTIC", "REFERENCE_IN_DIAGNOSTIC", "REFERENCE_IN_DIAGNOSTIC", "REFERENCE_IN_DIAGNOSTIC", "REFERENCE_IN_DIAGNOSTIC", "REFERENCE_IN_DIAGNOSTIC", "REFERENCE_IN_DIAGNOSTIC", "DISCOVERY", "transfer diagnostic", "complete-issue ESP transfer", "diagnostic only; cannot demote or replace the stronger comparable incumbent", "Outcome metrics remain in named diagnostic packages; Gate-A emits reference only"),
    ]
    return [dict(zip(fields, row)) for row in rows]


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
        role_count = 0; identity_count = 0; role_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        role_sink = ShardWriter(stage, "selector_role_vectors", ROLE_FIELDS)
        try:
            for identity in iter_gzip_shards(stage, "selector_identities"):
                identity_count += 1
                selected_match_ids = [x for x in identity["selected_match_ids"].split("|") if x]
                if len(selected_match_ids) != N or identity["selected_n"] != str(N):
                    raise RuntimeError(f"identity does not contain exactly seven roles: {identity['selector_id']}/{identity['portfolio_id']}")
                source_roles = role_lookup.get((identity["source_gate_id"], identity["portfolio_id"]), [])
                by_match = {r["match_id"]: r for r in source_roles}
                key = (identity["selector_id"], identity["issue_instance"], identity["portfolio_id"])
                for rank, match_id in enumerate(selected_match_ids, 1):
                    src = by_match.get(match_id) or vector_by_id.get(match_id)
                    if src is None:
                        raise RuntimeError(f"role source missing: {identity['portfolio_id']}/{match_id}")
                    role = normalised_role(src, identity["selector_id"], identity["family"], identity["issue_instance"], identity["portfolio_id"], match_id, rank)
                    role_sink.writerow(role); role_count += 1; role_counts[key] += 1
        finally:
            role_sink.close()
        if role_count != identity_count * N or any(value != N for value in role_counts.values()):
            raise RuntimeError(f"role completeness drift: identities={identity_count} roles={role_count}")
        s2_identity_tmp.unlink(missing_ok=True)
        identity_index, identity_whole = shard_reconciliation(stage, "selector_identities", IDENTITY_FIELDS, ("selector_id", "issue_instance", "portfolio_id", "selector_rank"))
        role_index, role_whole = shard_reconciliation(stage, "selector_role_vectors", ROLE_FIELDS, ("selector_id", "issue_instance", "portfolio_id", "selection_rank"))
        shard_index = identity_index + role_index
        shard_index_fields = ("kind", "filename", "row_count", "first_key", "last_key", "compressed_sha256", "decompressed_sha256", "key_fields")
        write_csv(stage / "shard_index.csv", shard_index_fields, shard_index)
        whole_reconciliation = {"selector_identities": identity_whole, "selector_role_vectors": role_whole, "identity_rows_times_n_equals_role_rows": identity_whole["row_count"] * N == role_whole["row_count"]}
        (stage / "whole_ledger_reconciliation.json").write_text(json.dumps(whole_reconciliation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_csv(stage / "selector_grid.csv", ("selector_id","family","gate_id","top_k","lowp_source","lowp_threshold","ranker","e_sp_min","gm_e_sp_min","selection_scope","outcome_boundary"), [
            {"selector_id": row["selector_id"], "family": row["family"], "gate_id": row.get("gate_id", ""), "top_k": row.get("top_k", ""), "lowp_source": row.get("lowp_source", ""), "lowp_threshold": row.get("lowp_threshold", ""), "ranker": row.get("ranker", ""), "e_sp_min": row.get("e_sp_min", ""), "gm_e_sp_min": row.get("gm_e_sp_min", ""), "selection_scope":"COMPLETE_ISSUE", "outcome_boundary":"outcome-unexposed"} for row in census if row["issue_instance"] == issues[0]["issue_instance"]
        ])
        grid = allocation_grid()
        write_csv(stage / "allocation_grid.csv", tuple(grid[0].keys()), grid)
        write_csv(stage / "baseline_registry.csv", tuple(baseline_rows()[0].keys()), baseline_rows())
        write_csv(stage / "source_census.csv", ("source","manifest_sha256","content_identity_sha256","role","outcome_boundary"), [{"source":name,"manifest_sha256":SOURCE_MANIFESTS[name],"content_identity_sha256":SOURCE_CONTENT_IDS[name],"role":"accepted immutable outcome-unexposed upstream or historical anchor","outcome_boundary":"no outcomes opened in Gate A"} for name in SOURCE_MANIFESTS])
        card = {
            "issue": 167, "contract": CONTRACT, "generator_version": VERSION,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_SELECTOR_ALLOCATION_ATLAS",
            "selector_families": {
                "S1_GATE_TOPK": {"selectors": len(S1_GATES) * len(TOP_K), "gates": list(S1_GATES), "top_k": list(TOP_K)},
                "S2_COMPLETE_ISSUE_LOWP": {"selectors": len(REGIMES) * len(LOWP_SOURCES) * len(LOWP_THRESHOLDS) * len(RANKERS) * len(TOP_K), "regimes": [r[0] for r in REGIMES], "lowp_sources": list(LOWP_SOURCES), "thresholds": list(LOWP_THRESHOLDS), "rankers": list(RANKERS), "top_k": list(TOP_K)},
            },
            "allocation": {"weights": list(WEIGHTS), "mechanisms": list(MECHANISMS), "M_grid": list(M_GRID), "caps": list(CAPS), "seed_count": len(SEEDS), "seeds": list(SEEDS), "ticket_space_k": FULL_K, "effective_cell_count": len(grid), "effective_cell_uniqueness": True},
            "denominator": {"issue_rows": len(issues), "match_rows": len(match_vectors), "source_identity_rows": len(identities), "selector_census_rows": len(census), "selector_identity_rows": identity_count, "selector_role_rows": role_count, "allocation_grid_rows": len(grid)},
            "invariants": {"seven_roles_per_identity": role_count == identity_count * N, "probability_vectors_complete_and_normalized": True, "shard_rows_reconciled": whole_reconciliation["identity_rows_times_n_equals_role_rows"]},
            "shard_reconciliation": whole_reconciliation, "source_manifests": SOURCE_MANIFESTS, "source_content_identities": SOURCE_CONTENT_IDS,
            "outcome_boundary": "No result code, final SP, payout, tax, ROI, settlement, or post-outcome input read or emitted; Gate B unauthorized until PI accepts this exact package.",
            "baseline_ratchet": "baseline_registry.csv retains #127 legacy, #137/#151 discovery, and #159 transfer diagnostics without replacing the comparable incumbent.",
        }
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True)+"\n",encoding="utf-8")
        (stage / "README.md").write_text("#167 Gate A v3r1 freezes the complete finite N7 selector × allocation atlas. It contains no outcomes. S1 uses accepted #137 participation_rank/selected IDs; K16 extends that ordering. S2 emits all six finite probability vectors and exactly seven roles per identity. Allocation cells are deduplicated by effective parameters (FULL and global-delete controls are single cells). Selector identities are complete-issue and are not reselected at Gate B. Every ¥2 ticket/repeat remains an independent future tax unit; no issue/policy pooling is allowed. Gate B must consume this package exactly. shard_index.csv and whole_ledger_reconciliation.json reconcile every compressed ledger. Temporary staging is under results/.scratch, never /tmp.\n",encoding="utf-8")
        shutil.copy2(__file__, stage / "freeze_runner.py")
        shard_names = sorted(p.name for p in stage.iterdir() if p.name.startswith("selector_identities-") or p.name.startswith("selector_role_vectors-"))
        content = {"contract_version":"bj167-gate-a-content-v3r1","shards": {row["filename"]: {"kind": row["kind"], "row_count": row["row_count"], "first_key": row["first_key"], "last_key": row["last_key"], "canonical_compressed_sha256": row["compressed_sha256"], "canonical_decompressed_sha256": row["decompressed_sha256"]} for row in shard_index}, "whole_ledgers": whole_reconciliation, "controls": {p.name:sha(p) for p in stage.iterdir() if p.is_file() and p.name not in {"SHA256SUMS.json","CONTENT_IDENTITY.json",*shard_names}}}
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
