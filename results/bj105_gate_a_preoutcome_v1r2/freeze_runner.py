#!/usr/bin/env python3
"""Freeze outcome-unexposed joint N7 match/role/pruning portfolios for #105.

The program intentionally consumes only the accepted #101 pool/probability
freeze and #90 deployed final-SP *prediction* projection.  It never opens a
result, winning-SP, payout, or settlement source.  A frontier row is an
analytic portfolio definition: its allowed-code sets are sufficient to derive
the exact ticket count without materialising physical tickets.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

CODES = ("3", "1", "0")
THRESHOLDS = (0.05, 0.10, 0.15, 0.20)
GM_THRESHOLDS = (2.90, 3.00, 3.10, 3.20)
DEPTHS = (0, 1, 2, 3)
STAKE_PER_SEQUENCE = 2
CONTRACT = "BJ-HIST-JOINT-N7-001"
GENERATOR_VERSION = "bj105-joint-analytic-v1"
BJ101_MANIFEST = "86e37682a95fad2a2a67187f1ee528f665d371583c621dc9d14af58f74302447"
BJ90_MANIFEST = "4a1107ca64d169bf0171a394d1e450a14ee5386005fce34f6ca7ebb70bd720b2"

MEMBERSHIP_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "match_id", "match_idx", "kickoff_ts", "p3", "p1", "p0", "deleted_code",
    "p_min", "p_min_rank", "p_min_bucket", "eligible_t05", "eligible_t10",
    "eligible_t15", "eligible_t20",
)
POOL_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder",
)
SP_FIELDS = (
    "match_id", "issue", "match_idx", "year", "fold", "deployed_method",
    "deployed_sp_3", "deployed_sp_1", "deployed_sp_0", "m2_conservative_sp_3",
    "m2_conservative_sp_1", "m2_conservative_sp_0",
)
SCATTER_FIELDS = (
    "issue", "fold", "year", "pool_id", "match_id", "match_idx", "kickoff_ts",
    "p3", "p1", "p0", "p_min", "p_max", "argmin_code", "argmax_code", "entropy",
    "uncertainty_1_minus_pmax", "e_sp", "q3", "q1", "q0", "q_max", "d_ratio",
    "predicted_top_sp", "joint_match_rank_value", "selection_rank",
)
FRONTIER_FIELDS = (
    "issue", "fold", "year", "pool_id", "threshold", "gm_threshold", "depth",
    "arm", "disposition", "selected_match_ids", "role_codes", "full_legs", "double_legs",
    "single_legs", "eligible_double_candidates", "gm_e_sp", "gm_top_predicted_sp",
    "expected_portfolio_mass", "formula_k", "candidate_stake_yuan", "active_k",
    "stake_yuan", "g_be_pre_tax", "descriptor_sha256",
)
ROLE_FIELDS = (
    "issue", "fold", "year", "pool_id", "threshold", "gm_threshold", "depth", "arm",
    "match_id", "match_idx", "role", "allowed_codes", "omitted_codes", "p_min", "p_max",
    "e_sp", "d_ratio", "q_max", "predicted_top_sp", "role_rank",
)
SUMMARY_FIELDS = ("threshold", "gm_threshold", "depth", "arm", "disposition", "portfolios", "total_tickets", "total_stake_yuan")
SOURCE_FIELDS = ("source", "role", "manifest_sha256", "payload", "payload_sha256", "rows", "join_status")


def repo_root(anchor: Path) -> Path:
    for item in (anchor.resolve().parent, *anchor.resolve().parents):
        if (item / ".git").exists():
            return item
    raise RuntimeError("repository root not found")


ROOT = repo_root(Path(__file__))
BJ101 = ROOT / "results" / "bj101_gate_a_preoutcome_v1r1"
BJ90 = ROOT / "results" / "bj90_downstream_safe_projection_v1r1"
OUT = ROOT / "results" / "bj105_gate_a_preoutcome_v1r2"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_bundle(path: Path, expected_manifest: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if sha256(manifest_path) != expected_manifest:
        raise RuntimeError(f"unaccepted input manifest: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha256(item) for item in path.iterdir() if item.is_file() and item.name != manifest_path.name}
    if not isinstance(declared, dict) or actual != declared:
        raise RuntimeError(f"input manifest coverage drift: {path}")
    return declared


def copy_authenticated(stage: Path, source: Path, expected: str, name: str) -> Path:
    target = stage / name
    shutil.copyfile(source, target)
    if sha256(target) != expected:
        raise RuntimeError(f"authenticated copy changed: {source}")
    return target


def schema(reader: csv.DictReader, expected: tuple[str, ...], label: str) -> None:
    if tuple(reader.fieldnames or ()) != expected:
        raise RuntimeError(f"schema mismatch for {label}: {reader.fieldnames}")


def finite(raw: str, label: str) -> float:
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError(f"invalid {label}: {raw!r}") from error
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"non-positive {label}: {raw!r}")
    return value


def fmt(value: float) -> str:
    if not math.isfinite(value):
        raise RuntimeError("non-finite output")
    return format(value, ".12f")


def h(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def unit(*parts: object) -> float:
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest(), "big") / 2**256


def argmin(p: dict[str, float]) -> str:
    return min(CODES, key=lambda code: (p[code], CODES.index(code)))


def argmax(p: dict[str, float]) -> str:
    return min(CODES, key=lambda code: (-p[code], CODES.index(code)))


def weighted_code(row: dict[str, object], depth: int) -> str:
    u = unit(CONTRACT, "WEIGHTED_SAMPLING", row["pool_id"], row["match_id"], depth)
    weights = {code: 1.0 - row["p"][code] for code in CODES}  # type: ignore[index]
    total = sum(weights.values())
    running = 0.0
    for code in CODES:
        running += weights[code] / total
        if u < running:
            return code
    return CODES[-1]


def hash_code(row: dict[str, object], depth: int) -> str:
    return CODES[int(unit(CONTRACT, "HASH_DELETION", row["pool_id"], row["match_id"], depth) * 3) % 3]


def allowed(role: str, omitted: str) -> tuple[str, str]:
    if role == "FULL":
        return "310", ""
    if role == "DOUBLE":
        return "".join(code for code in CODES if code != omitted), omitted
    if role == "SINGLE":
        return omitted, "".join(code for code in CODES if code != omitted)
    raise RuntimeError(f"bad role {role}")


def geometric(values: list[float]) -> float:
    if not values:
        raise RuntimeError("empty geometric mean")
    return math.exp(sum(math.log(value) for value in values) / len(values))


def make_portfolio(
    selected: list[dict[str, object]], threshold: float, gm_threshold: float, depth: int, arm: str,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Create one outcome-free analytic N7 definition, or a transparent failure row."""
    selected = sorted(selected, key=lambda row: int(row["match_idx"]))
    candidates = sorted(
        (row for row in selected if row["p_min"] <= threshold),
        key=lambda row: (row["d_ratio"], row["p_min"], int(row["match_idx"])),
    )
    roles = {str(row["match_id"]): "FULL" for row in selected}
    omitted: dict[str, str] = {}
    if arm == "FULL_COVER_CONTROL":
        required = 0
    elif arm == "JOINT_ROLE":
        required = depth
        if depth:
            single = max(selected, key=lambda row: (row["p_max"], row["q_max"], -int(row["match_idx"])))
            roles[str(single["match_id"])] = "SINGLE"
            omitted[str(single["match_id"])] = str(single["argmax_code"])
            candidates = [row for row in candidates if row["match_id"] != single["match_id"]]
    else:
        required = depth
    if len(candidates) < required:
        disposition = "UNAVAILABLE_THRESHOLD"
    else:
        disposition = "AVAILABLE"
        for row in candidates[:required]:
            match_id = str(row["match_id"])
            roles[match_id] = "DOUBLE"
            if arm in ("FIXED_ARGMIN", "JOINT_ROLE"):
                omitted[match_id] = str(row["argmin_code"])
            elif arm == "HASH_DELETION_CONTROL":
                omitted[match_id] = hash_code(row, depth)
            elif arm == "PROBABILITY_WEIGHTED_SAMPLING":
                omitted[match_id] = weighted_code(row, depth)
            else:
                raise RuntimeError(f"unsupported arm {arm}")
    gm_e = geometric([float(row["e_sp"]) for row in selected])
    gm_top = geometric([float(row["predicted_top_sp"]) for row in selected])
    if disposition == "AVAILABLE" and gm_e < gm_threshold:
        disposition = "FAIL_GM_GATE"
    nominal_k = 3**7 if arm == "FULL_COVER_CONTROL" else (
        3 ** (6 - depth) * 2**depth if arm == "JOINT_ROLE" else 3 ** (7 - depth) * 2**depth
    )
    if disposition == "UNAVAILABLE_THRESHOLD":
        frontier = {
            "issue": selected[0]["issue"], "fold": selected[0]["fold"], "year": selected[0]["year"], "pool_id": selected[0]["pool_id"],
            "threshold": fmt(threshold), "gm_threshold": fmt(gm_threshold), "depth": depth, "arm": arm,
            "disposition": disposition, "selected_match_ids": ";".join(str(row["match_id"]) for row in selected),
            "role_codes": "", "full_legs": "", "double_legs": "", "single_legs": "",
            "eligible_double_candidates": len(candidates), "gm_e_sp": fmt(gm_e),
            "gm_top_predicted_sp": fmt(gm_top), "expected_portfolio_mass": "", "formula_k": nominal_k,
            "candidate_stake_yuan": fmt(STAKE_PER_SEQUENCE * nominal_k), "active_k": 0,
            "stake_yuan": fmt(0), "g_be_pre_tax": "",
            "descriptor_sha256": h({"contract": CONTRACT, "threshold": threshold, "gm": gm_threshold, "depth": depth, "arm": arm, "disposition": disposition, "selected_match_ids": [row["match_id"] for row in selected]}),
        }
        return frontier, []
    role_rows: list[dict[str, object]] = []
    mass = 1.0
    k = 1
    for rank, row in enumerate(selected, 1):
        match_id = str(row["match_id"])
        role = roles[match_id]
        chosen = omitted.get(match_id, "")
        codes, omitted_codes = allowed(role, chosen)
        if role == "FULL":
            k *= 3
            retained = 1.0
        elif role == "DOUBLE":
            k *= 2
            retained = 1.0 - row["p"][chosen]  # type: ignore[index]
        else:
            retained = row["p"][chosen]  # type: ignore[index]
        mass *= retained
        role_rows.append({
            "issue": row["issue"], "fold": row["fold"], "year": row["year"], "pool_id": row["pool_id"],
            "threshold": fmt(threshold), "gm_threshold": fmt(gm_threshold), "depth": depth, "arm": arm,
            "match_id": match_id, "match_idx": row["match_idx"], "role": role, "allowed_codes": codes,
            "omitted_codes": omitted_codes, "p_min": fmt(row["p_min"]), "p_max": fmt(row["p_max"]),
            "e_sp": fmt(row["e_sp"]), "d_ratio": fmt(row["d_ratio"]), "q_max": fmt(row["q_max"]),
            "predicted_top_sp": fmt(row["predicted_top_sp"]), "role_rank": rank,
        })
    full = sum(role == "FULL" for role in roles.values())
    double = sum(role == "DOUBLE" for role in roles.values())
    single = sum(role == "SINGLE" for role in roles.values())
    if k != nominal_k:
        raise RuntimeError(f"role/K mismatch for {arm} depth {depth}: {k} != {nominal_k}")
    h_mass = mass
    g_be = (k / (0.65 * h_mass)) ** (1 / 7) if h_mass > 0 else float("inf")
    active_k = k if disposition == "AVAILABLE" else 0
    payload = [{key: item[key] for key in ("match_id", "role", "allowed_codes", "omitted_codes")} for item in role_rows]
    frontier = {
        "issue": selected[0]["issue"], "fold": selected[0]["fold"], "year": selected[0]["year"], "pool_id": selected[0]["pool_id"],
        "threshold": fmt(threshold), "gm_threshold": fmt(gm_threshold), "depth": depth, "arm": arm, "disposition": disposition,
        "selected_match_ids": ";".join(str(row["match_id"]) for row in selected), "role_codes": ";".join(str(item["role"]) for item in role_rows),
        "full_legs": full, "double_legs": double, "single_legs": single, "eligible_double_candidates": len(candidates),
        "gm_e_sp": fmt(gm_e), "gm_top_predicted_sp": fmt(gm_top), "expected_portfolio_mass": fmt(mass),
        "formula_k": k, "candidate_stake_yuan": fmt(STAKE_PER_SEQUENCE * k), "active_k": active_k,
        "stake_yuan": fmt(STAKE_PER_SEQUENCE * active_k), "g_be_pre_tax": fmt(g_be),
        "descriptor_sha256": h({"contract": CONTRACT, "threshold": threshold, "gm": gm_threshold, "depth": depth, "arm": arm, "roles": payload}),
    }
    return frontier, role_rows


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def build(out: Path, bj101: Path = BJ101, bj90: Path = BJ90) -> dict[str, int]:
    if out.exists():
        raise RuntimeError(f"refusing immutable overwrite: {out}")
    m101, m90 = exact_bundle(bj101, BJ101_MANIFEST), exact_bundle(bj90, BJ90_MANIFEST)
    with tempfile.TemporaryDirectory(prefix=".bj105_gate_a_", dir=out.parent) as temp:
        stage = Path(temp); private = stage / "_authenticated_inputs"; private.mkdir()
        membership_path = copy_authenticated(private, bj101 / "issue_pool_membership.csv", m101["issue_pool_membership.csv"], "membership.csv")
        census_path = copy_authenticated(private, bj101 / "issue_pool_census.csv", m101["issue_pool_census.csv"], "census.csv")
        sp_path = copy_authenticated(private, bj90 / "oos_prediction_vectors.csv.gz", m90["oos_prediction_vectors.csv.gz"], "sp.csv.gz")
        with membership_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle); schema(reader, MEMBERSHIP_FIELDS, "#101 membership"); membership = list(reader)
        with census_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle); schema(reader, POOL_FIELDS, "#101 census"); census = list(reader)
        sp: dict[tuple[str, str, str, str, str], dict[str, float]] = {}
        with gzip.open(sp_path, "rt", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle); schema(reader, SP_FIELDS, "#90 projection")
            for row in reader:
                key = (row["match_id"], row["issue"], row["match_idx"], row["year"], row["fold"])
                if key in sp: raise RuntimeError(f"duplicate SP identity {key}")
                sp[key] = {code: finite(row[f"deployed_sp_{code}"], f"SP {key} {code}") for code in CODES}
        pools: dict[str, list[dict[str, object]]] = defaultdict(list)
        scatter: list[dict[str, object]] = []
        for raw in membership:
            key = (raw["match_id"], raw["issue"], raw["match_idx"], raw["year"], raw["fold"])
            s = sp.get(key)
            if s is None: raise RuntimeError(f"missing safe SP projection {key}")
            p = {code: finite(raw[f"p{code}"], f"probability {key} {code}") for code in CODES}
            if abs(sum(p.values()) - 1.0) > 1e-6: raise RuntimeError(f"probability mass drift {key}")
            low, high = argmin(p), argmax(p)
            q = {code: p[code] * s[code] for code in CODES}
            others = [q[code] for code in CODES if code != low]
            row: dict[str, object] = {**raw, "p": p, "s": s, "p_min": p[low], "p_max": p[high], "argmin_code": low, "argmax_code": high,
                "entropy": -sum(value * math.log(value) for value in p.values()), "e_sp": sum(q.values()), "q": q, "q_max": q[high],
                "d_ratio": q[low] / (sum(others) / 2), "predicted_top_sp": s[high]}
            row["joint_match_rank_value"] = row["q_max"] * (1 - row["entropy"] / math.log(3))
            pools[raw["pool_id"]].append(row)
        for pool_id, rows in pools.items():
            ranked = sorted(rows, key=lambda row: (-row["joint_match_rank_value"], -row["q_max"], int(row["match_idx"])))
            for rank, row in enumerate(ranked, 1):
                row["selection_rank"] = rank
                scatter.append({"issue": row["issue"], "fold": row["fold"], "year": row["year"], "pool_id": pool_id, "match_id": row["match_id"], "match_idx": row["match_idx"], "kickoff_ts": row["kickoff_ts"],
                    "p3": fmt(row["p"]["3"]), "p1": fmt(row["p"]["1"]), "p0": fmt(row["p"]["0"]), "p_min": fmt(row["p_min"]), "p_max": fmt(row["p_max"]), "argmin_code": row["argmin_code"], "argmax_code": row["argmax_code"],
                    "entropy": fmt(row["entropy"]), "uncertainty_1_minus_pmax": fmt(1-row["p_max"]), "e_sp": fmt(row["e_sp"]), "q3": fmt(row["q"]["3"]), "q1": fmt(row["q"]["1"]), "q0": fmt(row["q"]["0"]), "q_max": fmt(row["q_max"]), "d_ratio": fmt(row["d_ratio"]), "predicted_top_sp": fmt(row["predicted_top_sp"]), "joint_match_rank_value": fmt(row["joint_match_rank_value"]), "selection_rank": rank})
        available = {row["pool_id"] for row in census if row["pool_disposition"] == "AVAILABLE"}
        arms = ("FULL_COVER_CONTROL", "FIXED_ARGMIN", "HASH_DELETION_CONTROL", "PROBABILITY_WEIGHTED_SAMPLING", "JOINT_ROLE")
        summary: dict[tuple[str, ...], dict[str, float]] = defaultdict(lambda: {"portfolios": 0, "total_tickets": 0, "total_stake_yuan": 0})
        frontier_count = 0
        role_count = 0
        frontier_path = stage / "joint_n7_frontier.csv.gz"
        role_path = stage / "role_assignments.csv.gz"
        with (
            frontier_path.open("wb") as frontier_raw,
            gzip.GzipFile(filename="", mode="wb", fileobj=frontier_raw, mtime=0) as frontier_gzip,
            io.TextIOWrapper(frontier_gzip, encoding="utf-8", newline="") as frontier_text,
            role_path.open("wb") as role_raw,
            gzip.GzipFile(filename="", mode="wb", fileobj=role_raw, mtime=0) as role_gzip,
            io.TextIOWrapper(role_gzip, encoding="utf-8", newline="") as role_text,
        ):
            frontier_writer = csv.DictWriter(frontier_text, fieldnames=FRONTIER_FIELDS, lineterminator="\n")
            role_writer = csv.DictWriter(role_text, fieldnames=ROLE_FIELDS, lineterminator="\n")
            frontier_writer.writeheader()
            role_writer.writeheader()
            for pool_id in sorted(available):
                selected = sorted(pools[pool_id], key=lambda row: row["selection_rank"])[:7]
                if len(selected) != 7:
                    raise RuntimeError(f"available pool lacks seven rows: {pool_id}")
                for threshold in THRESHOLDS:
                    for gm in GM_THRESHOLDS:
                        for depth in DEPTHS:
                            for arm in arms:
                                if depth == 0 and arm != "FULL_COVER_CONTROL":
                                    continue
                                if depth and arm == "FULL_COVER_CONTROL":
                                    continue
                                record, role_rows = make_portfolio(selected, threshold, gm, depth, arm)
                                frontier_writer.writerow(record)
                                role_writer.writerows(role_rows)
                                frontier_count += 1
                                role_count += len(role_rows)
                                key = (str(record["threshold"]), str(record["gm_threshold"]), str(record["depth"]), str(record["arm"]), str(record["disposition"]))
                                summary[key]["portfolios"] += 1
                                summary[key]["total_tickets"] += float(record["active_k"])
                                summary[key]["total_stake_yuan"] += float(record["stake_yuan"])
        write_csv(stage / "candidate_scatter.csv", SCATTER_FIELDS, scatter)
        write_csv(stage / "pool_census.csv", POOL_FIELDS, census)
        write_csv(stage / "frontier_summary.csv", SUMMARY_FIELDS, [{"threshold": a, "gm_threshold": b, "depth": c, "arm": d, "disposition": e, **{k: fmt(v) if k == "total_stake_yuan" else int(v) for k,v in values.items()}} for (a,b,c,d,e), values in sorted(summary.items())])
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj101_gate_a_preoutcome_v1r1", "role": "accepted issue segmentation and calibrated probability", "manifest_sha256": BJ101_MANIFEST, "payload": "issue_pool_membership.csv", "payload_sha256": m101["issue_pool_membership.csv"], "rows": len(membership), "join_status": "all rows joined to #90 prediction"},
            {"source": "bj90_downstream_safe_projection_v1r1", "role": "as-of final-SP prediction", "manifest_sha256": BJ90_MANIFEST, "payload": "oos_prediction_vectors.csv.gz", "payload_sha256": m90["oos_prediction_vectors.csv.gz"], "rows": len(sp), "join_status": "all #101 membership rows joined"},
        ])
        card = {"issue": 105, "contract": CONTRACT, "generator_version": GENERATOR_VERSION, "stage": "GATE_A_OUTCOME_UNEXPOSED_JOINT_N7_FREEZE", "input_manifests": {"bj101": BJ101_MANIFEST, "bj90": BJ90_MANIFEST}, "output_rows": {"candidate_scatter": len(scatter), "portfolio_frontier": frontier_count, "role_assignments": role_count}, "outcome_boundary": "No result, winning SP, payout, tax, ROI, or settlement input is read or emitted.", "selection": "Within each accepted #101 AVAILABLE pool, select seven highest joint_match_rank_value = q_max * (1 - entropy/log(3)); ties q_max descending then match_idx ascending.", "features": "E_SP=sum(p*s_hat); q=p*s_hat; D=q_argmin/mean(q_other_two); scatter contains p_min, E_SP, D, entropy and uncertainty.", "grid": {"depths": DEPTHS, "p_min_thresholds": THRESHOLDS, "gm_expected_sp_thresholds": GM_THRESHOLDS, "arms": arms}, "gm_gate": "Apply threshold to the geometric mean of seven E_SP values. Geometric mean of predicted top-code SP is diagnostic only.", "roles": "FIXED/HASH/WEIGHTED use m DOUBLE plus 7-m FULL. JOINT_ROLE uses one deterministic SINGLE (highest p_max/q_max) plus m DOUBLE and remaining FULL; m=0 is represented by full-cover control.", "accounting": "K=3^full*2^double; exact tax-aware payout is Gate-B-only. G_BE=[K/(0.65*H)]^(1/7) is reported only as first-order pre-tax diagnostic.", "gate_b": "UNAUTHORIZED pending independent EV and PI acceptance of this exact Gate-A package.", "scope": "paper-only historical research; no purchase, production, frontend, or ROI promotion."}
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(Path(__file__), stage / "freeze_runner.py")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.rmtree(private); shutil.copytree(stage, out)
    return {"membership_rows": len(membership), "available_pools": len(available), "frontier_rows": frontier_count, "role_rows": role_count}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT); parser.add_argument("--bj101", type=Path, default=BJ101); parser.add_argument("--bj90", type=Path, default=BJ90)
    args = parser.parse_args(); print(json.dumps(build(args.output.resolve(), args.bj101.resolve(), args.bj90.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
