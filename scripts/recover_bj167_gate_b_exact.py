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

def canonical_s1_support(issue, mids, roles, outcomes):
    """Build one exact S1 canonical support from retained Gate-A role rows."""
    if len(mids) != 7 or [x["match_id"] for x in roles] != mids:
        raise RuntimeError("S1 support role mismatch")
    missing = tuple(x for x in mids if x not in outcomes)
    truth_codes = tuple(outcomes[x][0] for x in mids) if not missing else tuple(-1 for _ in mids)
    payout = 2.0 * .65 * math.prod(outcomes[x][1] for x in mids) if not missing else 0.0
    return {"issue": issue, "mids": mids, "roles": roles,
            "truth": sum(max(t, 0) * (3 ** (6-i)) for i,t in enumerate(truth_codes)),
            "payout": payout, "available": not missing}

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
                supports[key] = canonical_s1_support(row["issue_instance"], mids, roles, outcomes)
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

def recovery_policy_status(supports):
    status = {}
    with (R.GA / "selector_census.csv").open(newline="") as f:
        for row in csv.DictReader(f):
            if row["selector_id"] == SELECTOR:
                status[row["issue_instance"]] = "SETTLED" if int(row["selected_identity_count"]) and row.get("selection_status", "AVAILABLE") in ("AVAILABLE", "") else "NO_BET_FROZEN"
    for s in supports.values():
        if not s["available"] and status.get(s["issue"]) == "SETTLED": status[s["issue"]] = "UNAVAILABLE_CANONICAL_OUTCOME"
    return status

def load_issue_order(archive):
    with (archive / "issue_order.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, {r["issue_instance"]: i for i,r in enumerate(rows)}

def validate_archive_policy_boundary(status, supports, archive_issues):
    """Return the policy map restricted to the archived identity chronology.

    The exact screen's chronology was built from actual Gate-A identities. A
    selector census can additionally contain an explicit K-unsatisfied
    no-bet row, which has no identity and therefore no issue-array position.
    That narrow difference is safe only if it is proved to be zero-support and
    already frozen as a no-bet. Every other mismatch is scientific drift.
    """
    archive_issues = set(archive_issues)
    support_issues = {s["issue"] for s in supports.values()}
    extra = set(status) - archive_issues
    invalid_extra = sorted(
        issue for issue in extra
        if status[issue] != "NO_BET_FROZEN" or issue in support_issues
    )
    if invalid_extra:
        raise RuntimeError(
            "S1 census/archive chronology mismatch is not an explicit zero-support "
            f"frozen no-bet: {invalid_extra[:3]}"
        )
    for issue in archive_issues:
        status.setdefault(issue, "NO_BET_FROZEN")
    return {issue: status[issue] for issue in archive_issues}

def archive_target_rows(archive, selector_index):
    target = selector_index * R.NCELL
    for p in sorted(archive.glob("cell_metrics-*.csv.gz")):
        with gzip.open(p, "rt", newline="") as f:
            rows = csv.DictReader(f)
            first = next(rows, None)
            if first is None or first["selector_id"] != SELECTOR: continue
            out = {int(first["global_cell"]): first}
            out.update({int(r["global_cell"]): r for r in rows})
            if min(out) != target or len(out) != R.NCELL: raise RuntimeError("archive S1 shard/global-cell binding drift")
            return out
    raise RuntimeError("archive lacks S1 cell shard")

def configure_profile():
    lib = R.compile_engine(ROOT, "bj167_recovery_sparse.so")
    pd, pi = ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int)
    lib.bj167_profile_allocation.argtypes = [pd, ctypes.c_int, ctypes.c_char_p, pi, pi, pi, pi, pi, pi]
    return lib

def replay_bounded_targets(archive):
    R.verify_ga(); outcomes = R.load_outcomes()
    selectors, selector_idx, _, cells, maps = R.load_surface(); si = selector_idx[SELECTOR]
    support = iter_s1_supports(outcomes, selector_idx); status = recovery_policy_status(support)
    issue_rows, issue_index = load_issue_order(archive)
    status = validate_archive_policy_boundary(status, support, issue_index)
    specs = target_specs({(r["weight_source"],r["mechanism"],r["cap"],r["M"],r["seed"]):i for i,r in enumerate(cells)}, maps, si)
    nissue, ntarget = len(issue_rows), len(specs); net = [[0.0]*nissue for _ in range(ntarget)]; stake = [[0.0]*nissue for _ in range(ntarget)]
    cell_to_target = {cell:i for i,(_,cell) in enumerate(specs)}; mpos={m:i for i,m in enumerate(R.M_GRID)}
    lib = configure_profile()
    wr=array.array("i",[0])*(100*20*4); wor=array.array("i",[0])*(100*20*4); residual=array.array("i",[0])*(20*4); capped=array.array("i",[0])*(4*20*4); top=array.array("i",[0])*(20*4); full=array.array("i",[0])*4
    for s in support.values():
        ii=issue_index[s["issue"]]
        if status[s["issue"]] != "SETTLED": continue
        q=array.array("d",[v for role in s["roles"] for v in role["source"]["Q_WEIGHT"]])
        lib.bj167_profile_allocation(ptr(q,ctypes.c_double),s["truth"],"|".join(s["mids"]).encode(),ptr(wr,ctypes.c_int),ptr(wor,ctypes.c_int),ptr(residual,ctypes.c_int),ptr(capped,ctypes.c_int),ptr(top,ctypes.c_int),ptr(full,ctypes.c_int))
        pl,pc,ql,qc=R.derive_delete(s["roles"])
        for cell,ti in cell_to_target.items():
            c=cells[cell]; me=c["mechanism"]; m=int(c["M"]) if c["M"] != "NA" else 0
            if me == "WOR_DISTINCT": metric=wor[(R.SEEDS.index(c["seed"])*20+mpos[m])*4:(R.SEEDS.index(c["seed"])*20+mpos[m]+1)*4]
            elif me == "RESIDUAL_SYSTEMATIC": metric=residual[mpos[m]*4:(mpos[m]+1)*4]
            elif me == "CAPPED_REPEAT": metric=capped[(R.CAPS.index(int(c["cap"]))*20+mpos[m])*4:(R.CAPS.index(int(c["cap"]))*20+mpos[m]+1)*4]
            elif me == "DETERMINISTIC_TOP_MASS": metric=top[mpos[m]*4:(mpos[m]+1)*4]
            elif me == "FULL_ENUMERATED": metric=full
            elif me == "P_MIN_GLOBAL_DELETE": metric=(int(((s["truth"] // (3**(6-pl))) % 3) != pc),1458,0,0)
            elif me == "Q_MIN_GLOBAL_DELETE": metric=(int(((s["truth"] // (3**(6-ql))) % 3) != qc),1458,0,0)
            else: raise RuntimeError(f"unexpected bounded mechanism {me}")
            st=2.0*(metric[1]+metric[2]); stake[ti][ii] += st; net[ti][ii] += s["payout"]*metric[0]-st
    archived = archive_target_rows(archive, si)
    for ti,(_,cell) in enumerate(specs):
        row=archived[si*R.NCELL+cell]; got_st=sum(stake[ti]); got_net=sum(net[ti])
        if abs(got_st-float(row["stake_yuan"])) > 1e-6 or abs(got_net-float(row["pre_tax_net_yuan"])) > 1e-6:
            raise RuntimeError(f"bounded target replay drift for global cell {si*R.NCELL+cell}")
    return specs, issue_rows, net, stake, status

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--archive",type=Path,default=ARCHIVE_DEFAULT); ap.add_argument("--verify-only",action="store_true"); args=ap.parse_args()
    census=archive_census(args.archive); print(json.dumps(census,sort_keys=True),flush=True)
    if args.verify_only: return
    specs, issue_rows, net, stake, status = replay_bounded_targets(args.archive)
    print(json.dumps({"bounded_target_count":len(specs),"issue_count":len(issue_rows),"policy_status_counts":{k:list(status.values()).count(k) for k in sorted(set(status.values()))}},sort_keys=True),flush=True)

if __name__ == "__main__": main()
