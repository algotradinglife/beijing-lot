#!/usr/bin/env python3
"""Fail-closed bounded recovery for the interrupted #167 v3r1 Gate-B screen.

The archived screen is never modified.  This executable verifies every
archived cell shard, streams only S1_NO_GATE_K4 identities from Gate A, and
replays the preregistered bootstrap/stability target registry with the frozen
native allocator.  It deliberately has no path that evaluates the 492x24723
surface again.
"""
from __future__ import annotations

import argparse, array, csv, ctypes, gzip, hashlib, importlib.util, json, math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "scripts" / "settle_bj167_strategy_atlas_gate_b_exact.py"
ARCHIVE_DEFAULT = ROOT / "results" / "bj167_gate_b_strategy_atlas_v3r1_exact.failed-stability-label-20260803T2247"
SELECTOR = "S1_NO_GATE_K4"

spec = importlib.util.spec_from_file_location("bj167_exact", RUNNER_PATH)
R = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(R)

def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def ptr(a, typ):
    return ctypes.cast((typ * len(a)).from_buffer(a), ctypes.POINTER(typ))

def archive_census(archive: Path) -> dict:
    shards = sorted(archive.glob("cell_metrics-*.csv.gz"))
    if len(shards) != R.NSEL: raise RuntimeError(f"archive needs {R.NSEL} cell shards, found {len(shards)}")
    hashes, rows = {}, 0
    for p in shards:
        hashes[p.name] = sha(p)
        with gzip.open(p, "rt", newline="") as f:
            n = sum(1 for _ in csv.DictReader(f))
        if n != R.NCELL: raise RuntimeError(f"archive cell census drift {p.name}: {n}")
        rows += n
    for name in ("ensemble_metrics.csv.gz", "seed_prefix_summaries.csv.gz", "issue_cluster_bootstrap.csv", "bootstrap_target_registry.csv", "issue_order.csv"):
        p = archive / name
        if not p.exists(): raise RuntimeError(f"archive missing {name}")
        hashes[name] = sha(p)
    if rows != R.NSEL * R.NCELL: raise RuntimeError("archive total cell census drift")
    anchor = None
    with gzip.open(archive / "ensemble_metrics.csv.gz", "rt", newline="") as f:
        for row in csv.DictReader(f):
            if (row["selector_id"], row["weight_source"], row["mechanism"], row["M"], row["seed_scope"]) == (SELECTOR, "Q_WEIGHT", "WOR_DISTINCT", "64", "ENSEMBLE_100"):
                anchor = row; break
    if anchor is None: raise RuntimeError("archive lacks S1 Q/WOR/M64 ensemble anchor")
    if abs(float(anchor["no_tax_roi"]) - float(R.COMMON_SUPPORT_INCUMBENT_ROI)) > 1e-10: raise RuntimeError("archive S1 incumbent ROI anchor drift")
    if abs(float(anchor["matched_full_lift"]) - float(R.COMMON_SUPPORT_INCUMBENT_LIFT)) > 1e-10: raise RuntimeError("archive S1 matched-FULL lift anchor drift")
    return {"archive": archive.name, "cell_shards": len(shards), "cell_rows": rows, "payload_sha256": hashes,
            "anchor": {"no_tax_roi": anchor["no_tax_roi"], "matched_full_lift": anchor["matched_full_lift"]}}

def iter_s1_supports(outcomes, selector_idx):
    """Stream the identity/role lockstep, retaining only one selector."""
    idr = R.GzipRows(sorted(R.GA.glob("selector_identities-*.csv.gz")))
    rvr = R.GzipRows(sorted(R.GA.glob("selector_role_vectors-*.csv.gz")))
    supports = {}
    row = idr.next()
    while row:
        roles = []
        for _ in range(7):
            rr = rvr.next()
            if rr is None or (rr["selector_id"], rr["issue_instance"], rr["portfolio_id"]) != (row["selector_id"], row["issue_instance"], row["portfolio_id"]):
                raise RuntimeError("Gate-A identity/role lockstep mismatch")
            roles.append(R.role_values(rr))
        if row["selector_id"] == SELECTOR:
            key = (row["issue_instance"], row["selected_match_ids"])
            if key not in supports:
                mids = row["selected_match_ids"].split("|")
                if len(mids) != 7 or [x["match_id"] for x in roles] != mids: raise RuntimeError("S1 support role mismatch")
                missing = tuple(x for x in mids if x not in outcomes)
                truth_codes = tuple(outcomes[x][0] for x in mids) if not missing else tuple(-1 for _ in mids)
                payout = 2.0 * .65 * math.prod(outcomes[x][1] for x in mids) if not missing else 0.0
                supports[key] = {"issue": row["issue_instance"], "mids": mids, "roles": roles,
                                 "truth": sum(max(t, 0) * (3 ** (6-i)) for i,t in enumerate(truth_codes)),
                                 "available": not missing}
        row = idr.next()
    if not supports: raise RuntimeError("S1 stream empty")
    return supports

def target_specs(cell_by_key, maps, selector_index):
    out=[]
    for m in (64,128):
        for seed in R.SEEDS:
            out.append((f"{SELECTOR}/Q_WEIGHT/WOR_DISTINCT/M{m}/{seed}", cell_by_key[("Q_WEIGHT","WOR_DISTINCT","NA",str(m),seed)]))
    for ws,me,cap,m,label in (("Q_WEIGHT","RESIDUAL_SYSTEMATIC","NA",64,"Q_WEIGHT/RESIDUAL_SYSTEMATIC/M64"), ("Q_WEIGHT","CAPPED_REPEAT","1",64,"Q_WEIGHT/CAPPED_REPEAT/cap1/M64"), ("Q_WEIGHT","CAPPED_REPEAT","2",64,"Q_WEIGHT/CAPPED_REPEAT/cap2/M64"), ("Q_WEIGHT","CAPPED_REPEAT","4",64,"Q_WEIGHT/CAPPED_REPEAT/cap4/M64"), ("Q_WEIGHT","CAPPED_REPEAT","8",64,"Q_WEIGHT/CAPPED_REPEAT/cap8/M64"), ("Q_WEIGHT","DETERMINISTIC_TOP_MASS","NA",64,"Q_WEIGHT/DETERMINISTIC_TOP_MASS/M64")):
        out.append((f"{SELECTOR}/{label}",cell_by_key[(ws,me,cap,str(m),"NA")]))
    out += [(f"{SELECTOR}/FULL_ENUMERATED", maps["struct"]["full"]), (f"{SELECTOR}/P_MIN_GLOBAL_DELETE",maps["struct"]["p"]), (f"{SELECTOR}/Q_MIN_GLOBAL_DELETE",maps["struct"]["q"])]
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--archive",type=Path,default=ARCHIVE_DEFAULT); ap.add_argument("--verify-only",action="store_true"); args=ap.parse_args()
    census=archive_census(args.archive); print(json.dumps(census,sort_keys=True),flush=True)
    if args.verify_only: return
    # The sparse replay/finalizer is intentionally not enabled until its
    # target-array aggregation is covered by a production-path fixture.
    raise RuntimeError("bounded replay not yet enabled; archive verification completed fail-closed")

if __name__ == "__main__": main()
