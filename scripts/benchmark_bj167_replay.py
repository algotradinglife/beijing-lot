#!/usr/bin/env python3
"""Bounded serial replay benchmark; never starts the full #167 atlas."""
from __future__ import annotations
import argparse, array, ctypes, hashlib, importlib.util, os, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNNER=ROOT/"scripts"/"settle_bj167_strategy_atlas_gate_b_exact.py"

def load(path):
    spec=importlib.util.spec_from_file_location("bj167_runner",path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
def ptr(a,t): return ctypes.cast((t*len(a)).from_buffer(a),ctypes.POINTER(t))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--supports",type=int,default=8); ap.add_argument("--threads",type=int,default=1); args=ap.parse_args()
    if args.supports <= 0 or args.supports > 64: raise SystemExit("bounded fixture supports must be 1..64")
    if args.threads <= 0 or args.threads > 64: raise SystemExit("threads must be 1..64")
    os.environ["OMP_NUM_THREADS"] = str(args.threads)
    r=load(RUNNER); r.verify_ga(); outcomes=r.load_outcomes(); selectors,selector_idx,alloc,cell_meta,maps=r.load_surface()
    # Read only a bounded prefix of the immutable identity/role shards.  The
    # fixture deliberately does not materialise the 1.3M identity support map.
    idr=r.GzipRows(sorted(r.GA.glob("selector_identities-*.csv.gz"))); rvr=r.GzipRows(sorted(r.GA.glob("selector_role_vectors-*.csv.gz")))
    chosen=[]; row=idr.next()
    while row and len(chosen)<args.supports:
        roles=[]
        for _ in range(7): roles.append(r.role_values(rvr.next()))
        mids=row["selected_match_ids"].split("|"); missing=[m for m in mids if m not in outcomes]
        if not missing:
            truth=sum(outcomes[m][0]*(3**(6-i)) for i,m in enumerate(mids)); payout=2*.65
            for m in mids: payout*=outcomes[m][1]
            chosen.append({"roles":roles,"mids":mids,"truth":truth,"payout":payout})
        row=idr.next()
    if len(chosen)!=args.supports: raise RuntimeError("bounded fixture could not find enough settled identities")
    # Each benchmark process gets a distinct shared-object path; this keeps
    # concurrent thread sweeps from truncating one another's loader target.
    lib=r.compile_engine(ROOT, f"bj167_exact_atlas_benchmark_{args.threads}.so")
    lib.bj167_process_source.argtypes=[ctypes.POINTER(ctypes.c_double),ctypes.c_int,ctypes.c_char_p,ctypes.c_double,ctypes.POINTER(ctypes.c_int),ctypes.c_int]+[ctypes.POINTER(ctypes.c_int)]*5+[ctypes.c_int]+[ctypes.POINTER(ctypes.c_double)]*8
    n=r.NCELL; metrics=[array.array("d",[0.0])*n for _ in range(8)]; dptr=[ptr(x,ctypes.c_double) for x in metrics]
    map_arrays={src:{k:array.array("i",v) for k,v in maps[src].items()} for src in r.SOURCES}; map_ptrs={src:{k:ptr(v,ctypes.c_int) for k,v in map_arrays[src].items()} for src in r.SOURCES}
    t0=time.perf_counter(); calls=0
    for s in chosen:
        # This is a one-selector core timing fixture.  Remap any canonical
        # selector occurrence to local selector 0 because metrics has only one
        # NCELL slab; never pass the original global selector index here.
        occ=array.array("i",[0]); occp=ptr(occ,ctypes.c_int)
        assert 0 <= occ[0] < 1
        role_values={src:array.array("d",[v for role in s["roles"] for v in role["source"][src]]) for src in r.SOURCES}
        sig="|".join(s["mids"]).encode()
        for src_i,src in enumerate(r.SOURCES):
            lib.bj167_process_source(ptr(role_values[src],ctypes.c_double),s["truth"],sig,s["payout"],occp,1,map_ptrs[src]["wr"],map_ptrs[src]["wor"],map_ptrs[src]["residual"],map_ptrs[src]["capped"],map_ptrs[src]["top"],maps["struct"]["full"] if src_i==0 else -1,*dptr); calls+=1
    elapsed=time.perf_counter()-t0
    scale=r.NSUPPORT/len(chosen)
    metrics_sha256=hashlib.sha256(b"".join(x.tobytes() for x in metrics)).hexdigest()
    print({"fixture_supports":len(chosen),"source_calls":calls,"omp_threads":args.threads,"elapsed_seconds":round(elapsed,3),"serial_estimated_full_seconds":round(elapsed*scale,1),"serial_estimated_full_hours":round(elapsed*scale/3600,2),"metrics_sha256":metrics_sha256,"method":"exact native ticket replay; 100 WR/WOR seeds, shared max-M prefixes, six sources; serial aggregation","full_run_started":False})

if __name__=="__main__": main()
