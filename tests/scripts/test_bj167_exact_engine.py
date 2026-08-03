from __future__ import annotations

import array, ctypes, gc, hashlib, importlib.util, json, os, subprocess, csv, gzip, math, itertools
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "settle_bj167_strategy_atlas_gate_b_exact.py"
ALLOC = ROOT / "scripts" / "bj145_allocation_engine.py"

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

def engine():
    so = ROOT / ".scratch" / "bj167_exact_atlas.so"; so.parent.mkdir(exist_ok=True)
    compile_tmp=ROOT/".scratch"/"bj167_compile_tmp"; compile_tmp.mkdir(exist_ok=True)
    compile_env=dict(os.environ,TMPDIR=str(compile_tmp),TEMP=str(compile_tmp),TMP=str(compile_tmp))
    subprocess.run(["g++","-O3","-std=c++17","-fopenmp","-shared","-fPIC",str(ROOT/"scripts"/"bj167_exact_atlas.cpp"),"-o",str(so)], check=True,env=compile_env)
    lib=ctypes.CDLL(str(so))
    lib.bj167_process_source.argtypes=[ctypes.POINTER(ctypes.c_double),ctypes.c_int,ctypes.c_char_p,ctypes.c_double,ctypes.POINTER(ctypes.c_int),ctypes.c_int]+[ctypes.POINTER(ctypes.c_int)]*5+[ctypes.c_int]+[ctypes.POINTER(ctypes.c_double)]*8
    lib.bj167_add_delete.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_double]+[ctypes.POINTER(ctypes.c_double)]*8
    lib.bj145_profile.argtypes=[ctypes.POINTER(ctypes.c_double),ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.POINTER(ctypes.c_int),ctypes.c_int,ctypes.POINTER(ctypes.c_int)]
    return lib

def p(a, typ): return ctypes.cast((typ*len(a)).from_buffer(a), ctypes.POINTER(typ))

def test_surface_maps_are_source_specific_and_numeric():
    mod=load("runner", SCRIPT); _,_,_,_,maps=mod.load_surface()
    cells=[]
    for src in mod.SOURCES:
        cells.append(tuple(maps[src]["wr"][:20]))
    assert len(set(cells)) == len(mod.SOURCES), "source maps collapsed"
    # Explicit numeric allocation-grid assertions (not placeholder metadata).
    for src in mod.SOURCES:
        for name in ("wr","wor","residual","top","capped"):
            assert all(x >= 0 for x in maps[src][name]), (src,name)
        assert len(set(maps[src]["wor"])) == 2000
    assert mod.CAPS == (1,2,4,8)
    assert mod.M_GRID[-4:] == (512,1024,1458,2187)

def test_stability_metadata_never_parses_short_delete_labels():
    mod=load("runner_stability_metadata", SCRIPT)
    cells=[{"mechanism":"P_MIN_GLOBAL_DELETE","M":"2187"}, {"mechanism":"CAPPED_REPEAT","M":"64"}]
    # Delete labels deliberately lack the old assumed third slash component.
    assert mod.stability_mechanism_m({"role":"DELETE_CONTROL_SCREEN","global_cell":0,"label":"S1_NO_GATE_K4/P_MIN_GLOBAL_DELETE"}, cells) == ("P_MIN_GLOBAL_DELETE","2187")
    assert mod.stability_mechanism_m({"role":"ALLOCATION_FAMILY_SCREEN","global_cell":1,"label":"S1/Q/CAPPED"}, cells) == ("CAPPED_REPEAT","64")
    assert mod.stability_mechanism_m({"role":"MATCHED_FULL_CONFIRMATORY","global_cell":0,"label":"S1_NO_GATE_K4/FULL_ENUMERATED"}, cells) == ("MATCHED_FULL","2187")
    assert mod.stability_mechanism_m({"role":"CONFIRMATORY_INCUMBENT_100_SEED","global_cell":-1,"label":"S1/Q/WOR/M64/ENSEMBLE_100"}, cells) == ("WOR_DISTINCT","64")

def test_cpp_real_prefix_golden_and_backing_lifetime():
    mod=load("runner2", SCRIPT); alloc=load("alloc", ALLOC); lib=engine()
    assert hashlib.sha256((ROOT/"scripts"/"bj145_fast_alloc.cpp").read_bytes()).hexdigest() == mod.EXPECTED_ALLOCATOR_SHA256
    # Synthetic but numeric seven-leg vector; Python frozen engine is the
    # oracle for every mechanism and every M prefix in this golden call.
    # Use an actual frozen #167 role-vector support, not a synthetic uniform
    # vector (uniform sums have a known Python/native tie pathology at
    # CAPPED_REPEAT M=2187).
    idr=mod.GzipRows(sorted(mod.GA.glob("selector_identities-*.csv.gz"))); rvr=mod.GzipRows(sorted(mod.GA.glob("selector_role_vectors-*.csv.gz")))
    # Skip the first nearly uniform production supports: they intentionally
    # exercise the accepted C++/Python tie pathology at dense capped M, not a
    # useful parity oracle.  Select the first real #167 support with a
    # materially non-uniform Q vector and keep its identity/role rows paired.
    identity=None; role_rows=None
    while True:
        identity=idr.next(); role_rows=[rvr.next() for _ in range(7)]
        if identity is None or any(rr is None for rr in role_rows): raise AssertionError("Gate-A role-vector sample exhausted")
        assert all((rr["selector_id"], rr["issue_instance"], rr["portfolio_id"]) == (identity["selector_id"], identity["issue_instance"], identity["portfolio_id"]) for rr in role_rows), "identity/role sample key mismatch"
        qvals=[float(rr[f"q_weight{code}"]) for rr in role_rows for code in ("3","1","0")]
        if max(qvals)-min(qvals)>1e-4: break
    assert max(qvals)-min(qvals)>1e-4, "production capped golden must be non-uniform"
    parsed_roles=[mod.role_values(rr) for rr in role_rows]
    assert all(role["q_weight"] == role["source"]["Q_WEIGHT"] for role in parsed_roles)
    _,_,q_leg,q_code=mod.derive_delete(parsed_roles)
    expected_q_leg,expected_q_code=min(
        ((leg,code) for leg in range(7) for code in range(3)),
        key=lambda x: (parsed_roles[x[0]]["source"]["Q_WEIGHT"][x[1]],x[0],x[1]))
    assert (q_leg,q_code)==(expected_q_leg,expected_q_code)
    role=array.array("d", [v for rr in role_rows for v in mod.role_values(rr)["source"]["Q_WEIGHT"]])
    signature=identity["selected_match_ids"]
    # Construct the role-product vector with the same level-by-level
    # multiplication order as the frozen C++ allocator.  Recomputing each
    # ticket independently can move floating-point ties at the dense M=2187
    # boundary even though the mathematical products are identical.
    weights=[1.0]
    for leg in range(7):
        next_weights=[]
        for prefix in weights:
            for code in range(3):
                next_weights.append(prefix * role[leg*3+code])
        weights=next_weights
    weights=tuple(weights)
    occ=array.array("i",[0]); n=24723; maps=[]
    wr=[0]*2000; wor=[0]*2000; residual=[0]*20; capped=[0]*80; top=[0]*20
    for i in range(len(wr)): wr[i]=i+1
    for i in range(len(wor)): wor[i]=3000+i
    for i in range(20): residual[i]=5000+i; top[i]=6000+i
    for i in range(80): capped[i]=7000+i
    # Keep these arrays in a named list; this is the lifetime assertion that
    # the former temporary-comprehension implementation failed.
    map_arrays=[array.array("i",x) for x in (wr,wor,residual,capped,top)]
    metrics=[array.array("d",[0.0])*n for _ in range(8)]
    dptr=[p(x,ctypes.c_double) for x in metrics]
    lib.bj167_process_source(p(role,ctypes.c_double),0,signature.encode(),10.0,p(occ,ctypes.c_int),1,*[p(x,ctypes.c_int) for x in map_arrays],8000,*dptr)
    gc.collect()
    # Exact numeric golden assertions cover every frozen M, all four caps,
    # and multiple real seeds.  The native runner's shared max-M prefixes are
    # compared against the Python allocator, not merely against row counts.
    capped_mismatches=[]
    for seed_idx in range(3):
        seed=f"137{seed_idx+1:03d}"
        for mi,m in enumerate(mod.M_GRID):
            for cell,me,kwargs in ((wr[seed_idx*20+mi],"WR_DUPLICATE_STAKE",{"seed":seed,"identity_signature":"golden-support"}),(wor[seed_idx*20+mi],"WOR_DISTINCT",{"seed":seed,"identity_signature":"golden-support"})):
                if me.startswith("WR") or me.startswith("WOR"): kwargs["identity_signature"]=signature
                counts=alloc.allocate(me,weights,m,**kwargs)
                assert metrics[1][cell] == 2.0*m
                assert metrics[2][cell] == 10.0*counts[0]
                assert metrics[4][cell] == float(sum(x>0 for x in counts))
                assert metrics[5][cell] == float(sum(max(x-1,0) for x in counts))
            for cell,me,kwargs in ((residual[mi],"RESIDUAL_SYSTEMATIC",{}),(top[mi],"DETERMINISTIC_TOP_MASS",{})):
                counts=alloc.allocate(me,weights,m,**kwargs); assert metrics[1][cell] == 2.0*m; assert metrics[2][cell] == 10.0*counts[0]
            for cap_idx,cap in enumerate(mod.CAPS):
                cell=capped[cap_idx*20+mi]
                counts=alloc.allocate("CAPPED_REPEAT",weights,m,cap=cap)
                assert metrics[1][cell] == 2.0*sum(counts)
                assert metrics[2][cell] == 10.0*counts[0]
                got=(metrics[4][cell], metrics[5][cell]); want=(float(sum(x>0 for x in counts)), float(sum(max(x-1,0) for x in counts)))
                if got != want: capped_mismatches.append((seed,cap,m,got,want))
    assert not capped_mismatches, f"non-boundary production capped parity drift: {capped_mismatches}"
    assert metrics[1][8000] == 4374.0 and metrics[2][8000] == 10.0

def test_frozen_golden_weights_native_caps_all_m():
    mod=load("runner_golden_weights", SCRIPT); alloc=load("alloc_golden_weights", ALLOC); lib=engine()
    weights=alloc.golden_weights(2187); wbuf=array.array("d",weights); out=array.array("i",[0,0,0,0])
    for cap in mod.CAPS:
        for m in mod.M_GRID:
            ms=array.array("i",[m]); lib.bj145_profile(p(wbuf,ctypes.c_double),2187,0,cap,p(ms,ctypes.c_int),1,p(out,ctypes.c_int))
            expected=alloc.allocate("CAPPED_REPEAT",weights,m,cap=cap)
            assert tuple(out)==(expected[0],sum(x>0 for x in expected),sum(max(x-1,0) for x in expected),sum(x>1 for x in expected))

def test_delete_uses_full_base3_truth_ordinal_for_all_legs_codes():
    lib=engine(); n=24723
    for truth in (0,1,17,100,1093,2186):
        digits=[(truth//(3**(6-leg)))%3 for leg in range(7)]
        for leg in range(7):
            for code in range(3):
                arr=[array.array("d",[0.0])*n for _ in range(8)]; ptrs=[p(x,ctypes.c_double) for x in arr]
                lib.bj167_add_delete(0,5,truth,leg,code,2.0,*ptrs)
                hit=int(digits[leg] != code)
                assert arr[0][5] == 1.0 and arr[1][5] == 2916.0 and arr[2][5] == 2.0*hit and arr[6][5] == float(hit)

def test_mixed_available_missing_identity_closes_selector_issue_policy():
    mod=load("runner_policy", SCRIPT)
    census=[{"selector_id":"S","issue_instance":"I","selected_identity_count":"2","selection_status":"AVAILABLE"},
            {"selector_id":"S","issue_instance":"J","selected_identity_count":"1","selection_status":"AVAILABLE"}]
    supports={
        ("I","a"): {"issue_instance":"I","available":True,"selectors":[0]},
        ("I","b"): {"issue_instance":"I","available":False,"selectors":[0]},
        ("J","c"): {"issue_instance":"J","available":True,"selectors":[0]},
    }
    status,_=mod.build_policy_status(census,supports,{"S":0})
    assert status[(0,"I")] == "UNAVAILABLE_CANONICAL_OUTCOME"
    assert status[(0,"J")] == "SETTLED"
    for s in supports.values():
        # The available identity in I is not partially settled.
        assert s["eligible_selectors"] == ([] if s["issue_instance"]=="I" else [0])

def test_recovery_accepts_only_zero_support_frozen_no_bets_outside_identity_chronology():
    recovery = load("bj167_recovery_policy_boundary", ROOT / "scripts" / "recover_bj167_gate_b_exact.py")
    status = {"I": "SETTLED", "J": "NO_BET_FROZEN", "K": "NO_BET_FROZEN"}
    supports = {("I", "a"): {"issue": "I"}, ("K", "b"): {"issue": "K"}}
    # J exists only in the selector census (K-unsatisfied) and is correctly
    # absent from the archived identity chronology.
    assert recovery.validate_archive_policy_boundary(status, supports, {"I", "K"}) == {
        "I": "SETTLED", "K": "NO_BET_FROZEN"
    }
    try:
        recovery.validate_archive_policy_boundary({"I": "SETTLED", "J": "SETTLED"}, supports, {"I"})
        assert False, "settling a census-only issue must fail closed"
    except RuntimeError as exc:
        assert "zero-support" in str(exc)
    try:
        recovery.validate_archive_policy_boundary({"I": "SETTLED", "K": "NO_BET_FROZEN"}, supports, {"I"})
        assert False, "a support outside archived chronology must fail closed"
    except RuntimeError as exc:
        assert "zero-support" in str(exc)

def test_recovery_support_persists_production_payout_before_replay():
    runner = load("runner_recovery_payout", SCRIPT)
    recovery = load("bj167_recovery_payout", ROOT / "scripts" / "recover_bj167_gate_b_exact.py")
    idr = runner.GzipRows(sorted(runner.GA.glob("selector_identities-*.csv.gz")))
    rvr = runner.GzipRows(sorted(runner.GA.glob("selector_role_vectors-*.csv.gz")))
    identity = idr.next()
    role_rows = [rvr.next() for _ in range(7)]
    assert identity is not None and all(row is not None for row in role_rows)
    roles = [runner.role_values(row) for row in role_rows]
    outcomes = runner.load_outcomes()
    record = recovery.canonical_s1_support(
        identity["issue_instance"], identity["selected_match_ids"].split("|"), roles, outcomes
    )
    assert "payout" in record
    if record["available"]:
        expected = 2.0 * .65 * math.prod(outcomes[mid][1] for mid in record["mids"])
        assert record["payout"] == expected
    else:
        assert record["payout"] == 0.0

def test_common_support_hash_tokens_are_selector_scoped():
    mod=load("runner_common_scope", SCRIPT)
    # The same canonical support may be reused by multiple selectors, but a
    # bridge hash must include only the selected identities of its selector.
    supports={
        ("I","m"): {"issue_instance":"I","eligible_selectors":[0,1],"portfolio_ids_by_selector":{0:["s1-id"],1:["s2-id"]}},
        ("J","n"): {"issue_instance":"J","eligible_selectors":[0],"portfolio_ids_by_selector":{0:["s1-id-2"],1:["other-id"]}},
    }
    assert mod.common_support_identity_tokens(supports,0)==["I|s1-id","J|s1-id-2"]
    assert mod.common_support_identity_tokens(supports,1)==["I|s2-id"]
    totals=defaultdict(int,{0:2,1:1}); identity_totals=defaultdict(int,{0:2,1:1})
    available_issues=defaultdict(set,{0:{"I","J"},1:{"I"}})
    unavailable_issues=defaultdict(set); no_bet_issues=defaultdict(set)
    available_ids=defaultdict(int,{0:2,1:1}); unavailable_ids=defaultdict(int); no_bet_ids=defaultdict(int)
    s1_denominator,s1_hash=mod.matched_full_denominator_metadata(
        supports,0,totals,available_issues,unavailable_issues,no_bet_issues,
        identity_totals,available_ids,unavailable_ids,no_bet_ids)
    s2_denominator,s2_hash=mod.matched_full_denominator_metadata(
        supports,1,totals,available_issues,unavailable_issues,no_bet_issues,
        identity_totals,available_ids,unavailable_ids,no_bet_ids)
    assert "SETTLED=2" in s1_denominator and "SETTLED=1" in s2_denominator
    assert s1_hash != s2_hash

def test_accepted_bj137_numeric_anchor_is_not_a_placeholder():
    # Recompute (do not reread) the first three accepted #137/#151 M64
    # numeric anchors through the new C++ allocator itself.  This uses the
    # immutable #151 K4 roles/cohort and the canonical #95 outcome payload.
    # These are the accepted v2r3 numeric anchors.  The test intentionally
    # does not load the old CSV as its oracle: it recomputes the complete
    # candidate/full/lift triples through the current native allocator, then
    # compares against these immutable numbers.  A file-only reread would
    # allow a broken runner to pass without executing any ticket logic.
    expected = {
        "137001": (0.163755668115, -0.157696718701, 0.321452386816),
        "137002": (0.117735771069, -0.157696718701, 0.275432489770),
        "137003": (0.026680342104, -0.157696718701, 0.184377060805),
    }
    cohort = {}
    with (ROOT/"results/bj151_gate_a_preoutcome_v1/candidate_cohort.csv").open(newline="") as f:
        for r in csv.DictReader(f): cohort[r["issue_instance"]] = r
    roles = {}
    with gzip.open(ROOT/"results/bj151_gate_a_preoutcome_v1/candidate_role_vectors.csv.gz","rt",newline="") as f:
        for r in csv.DictReader(f): roles.setdefault(r["portfolio_id"], []).append(r)
    signatures = {}
    with gzip.open(ROOT/"results/bj151_gate_a_preoutcome_v1/candidate_identities.csv.gz","rt",newline="") as f:
        for r in csv.DictReader(f): signatures[r["portfolio_id"]] = r["selected_match_ids"]
    outcomes = {}
    with (ROOT/"results/bj95_gate_b_outcome_settlement_v2r8/canonical_outcome_join.csv").open(newline="") as f:
        for r in csv.DictReader(f): outcomes[r["match_id"]] = r
    lib=engine();
    lib.bj145_wor_profile.argtypes=[ctypes.POINTER(ctypes.c_double),ctypes.c_int,ctypes.c_int,ctypes.c_char_p,ctypes.c_char_p,ctypes.POINTER(ctypes.c_int),ctypes.c_int,ctypes.POINTER(ctypes.c_int)]
    lib.bj145_profile.argtypes=[ctypes.POINTER(ctypes.c_double),ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.POINTER(ctypes.c_int),ctypes.c_int,ctypes.POINTER(ctypes.c_int)]
    ms=array.array("i",[64]); seeds=("137001","137002","137003"); sums={s:[0.0,0.0] for s in seeds}; full=[0.0,0.0]
    codes={"3":0,"1":1,"0":2}
    for issue, c in cohort.items():
        if c["selection_status"] != "AVAILABLE": continue
        ids=c["selected_portfolio_ids"].split("|")
        members=[]; missing=False
        for pid in ids:
            rr=sorted(roles[pid],key=lambda x:int(x["selection_rank"])); members.append(rr)
            missing |= any(x["match_id"] not in outcomes for x in rr)
        if missing: continue  # selector×issue policy fail-closed
        for rr in members:
            truth_codes=[codes[outcomes[x["match_id"]]["result_code"]] for x in rr]; truth=sum(v*3**(6-i) for i,v in enumerate(truth_codes)); payout=2*.65*math.prod(float(outcomes[x["match_id"]]["winning_sp"]) for x in rr)
            weights=array.array("d",[math.prod(float(rr[i][f"q_weight{code}"]) for i,code in enumerate(ticket)) for ticket in __import__("itertools").product(("3","1","0"),repeat=7)])
            for seed in seeds:
                    out=array.array("i",[0,0,0,0]); lib.bj145_wor_profile(p(weights,ctypes.c_double),2187,truth,seed.encode(),signatures[rr[0]["portfolio_id"]].encode(),p(ms,ctypes.c_int),1,p(out,ctypes.c_int)); sums[seed][0]+=payout*out[0]; sums[seed][1]+=128.0
            full[0]+=payout; full[1]+=4374.0
    full_roi=(full[0]-full[1])/full[1]
    for seed in seeds:
        roi=(sums[seed][0]-sums[seed][1])/sums[seed][1]; lift=roi-full_roi
        exp_candidate, exp_full, exp_lift = expected[seed]
        assert abs(roi-exp_candidate) < 2e-9
        assert abs(full_roi-exp_full) < 2e-9
        assert abs(lift-exp_lift) < 2e-9
    mod=load("runner_incumbent_anchor", SCRIPT)
    accepted={"no_tax_roi":"-0.132793126135","matched_full_no_tax_roi":"-0.157696718701","matched_full_lift":"0.024903592566"}
    mod.assert_s1_incumbent_anchors(accepted)
    for key in accepted:
        broken=dict(accepted); broken[key]="0.000000000000"
        try:
            mod.assert_s1_incumbent_anchors(broken)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"accepted S1 bridge did not guard {key}")
