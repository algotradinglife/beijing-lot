#!/usr/bin/env python3
"""Exact all-scientific-cell stability companion for #167 Gate B v3r1.

This does not re-open or alter the completed full screen.  It reduces the
frozen 100-seed WR/WOR families to their intended scientific units and settles
YEAR/FOLD/LOYO and signed-largest exclusions for every selector/allocation
science cell.  Seed-level rows remain diagnostics, never football histories.
"""
from __future__ import annotations

import argparse, array, csv, ctypes, gzip, importlib.util, json, math, shutil, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("bj167_runner",ROOT/"scripts"/"settle_bj167_strategy_atlas_gate_b_exact.py")
R=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(R)
CELLS_PER_SELECTOR=963
# The completed screen serializes every seed-level monetary total with
# ``money(...)=%.6f`` before it sums the 100 stochastic rows.  The companion
# instead pools those same ticket totals before it writes its comparison.
# These are therefore the only permitted reconciliation differences: half a
# decimal quantum for each serialized seed (or one deterministic row).
MONEY_QUANTUM = 1e-6
RATIO_QUANTUM = 1e-12
NATIVE_WRAPPER_PATH = ROOT / "scripts" / "bj167_exact_atlas.cpp"


def git_head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, text=True,
                          stdout=subprocess.PIPE).stdout.strip()


def execution_snapshot() -> dict:
    """Identity of this independent all-scientific executable."""
    return {"git_head": git_head(), "runner_path": str(Path(__file__).relative_to(ROOT)),
            "runner_sha256": R.sha(Path(__file__)),
            "native_wrapper_path": str(NATIVE_WRAPPER_PATH.relative_to(ROOT)),
            "native_wrapper_sha256": R.sha(NATIVE_WRAPPER_PATH),
            "frozen_allocator_path": "scripts/bj145_fast_alloc.cpp",
            "frozen_allocator_sha256": R.sha(ROOT / "scripts" / "bj145_fast_alloc.cpp")}


def write_execution_provenance(out: Path, screen: Path, start: dict, end: dict) -> None:
    """Persist both real boundaries; source drift in flight invalidates output."""
    if start != end:
        raise RuntimeError("all-scientific executable identity changed during run")
    content = screen / "CONTENT_IDENTITY.json"
    if not content.exists():
        raise RuntimeError("completed screen content identity required")
    payload = {"contract": "bj167-gate-b-v3r1-scientific-stability",
               "consumed_screening": {"package": screen.name,
                                      "manifest_sha256": R.sha(screen / "SHA256SUMS.json"),
                                      "content_identity_sha256": R.sha(content)},
               "all_scientific_execution_start": start,
               "all_scientific_execution_end": end}
    (out / "execution_provenance.json").write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")


def science_cells():
    rows=[]
    for src in R.SOURCES:
        for m in R.M_GRID: rows.append((src,"WR_DUPLICATE_STAKE","NA",str(m),"ENSEMBLE_100"))
        for m in R.M_GRID: rows.append((src,"WOR_DISTINCT","NA",str(m),"ENSEMBLE_100"))
        for m in R.M_GRID: rows.append((src,"RESIDUAL_SYSTEMATIC","NA",str(m),"DETERMINISTIC"))
        for cap in R.CAPS:
            for m in R.M_GRID: rows.append((src,"CAPPED_REPEAT",str(cap),str(m),"DETERMINISTIC"))
        for m in R.M_GRID: rows.append((src,"DETERMINISTIC_TOP_MASS","NA",str(m),"DETERMINISTIC"))
    rows += [("NA","FULL_ENUMERATED","NA","2187","DETERMINISTIC"),("NA","P_MIN_GLOBAL_DELETE","NA","1458","DETERMINISTIC"),("NA","Q_MIN_GLOBAL_DELETE","NA","1458","DETERMINISTIC")]
    if len(rows)!=CELLS_PER_SELECTOR: raise RuntimeError(f"science-cell layout drift: {len(rows)}")
    return rows


def science_key(selector_id: str, cell: tuple[str, str, str, str, str]) -> tuple[str, str, str, str, str, str]:
    return (selector_id, *cell)


def screening_science_rows(screen: Path) -> dict[tuple[str, str, str, str, str, str], dict]:
    """Load the immutable scientific (not seed-ledger) primary surface."""
    rows = {}
    with gzip.open(screen / "ensemble_metrics.csv.gz", "rt", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["selector_id"], row["weight_source"], row["mechanism"], row["cap"], row["M"], row["seed_scope"])
            if key in rows: raise RuntimeError(f"duplicate screening scientific key: {key}")
            rows[key] = row
    return rows


def same_or_blank(actual: float | None, expected: str, tol: float) -> tuple[bool, str, str]:
    if expected == "": return actual is None, "" if actual is None else f"{actual:.12f}", expected
    if actual is None: return False, "", expected
    return abs(actual - float(expected)) <= tol, f"{actual:.12f}", expected


def serialization_money_envelope(seed_scope: str) -> float:
    """Maximum declared screen-rounding error for a pooled money total."""
    return 0.5 * MONEY_QUANTUM * (100 if seed_scope == "ENSEMBLE_100" else 1)


def serialization_roi_envelope(screen_gross: str, screen_stake: str, seed_scope: str) -> float:
    """Conservative ROI error induced by the declared six-decimal path.

    It evaluates the two monotone gross/stake interval endpoints rather than
    applying a fixed ratio epsilon, so small-stake cells receive the larger
    mathematically necessary tolerance.  The final half ratio quantum covers
    the screen's twelve-decimal ROI text serialization.
    """
    if screen_gross == "" or screen_stake == "":
        return 0.0
    gross, stake = float(screen_gross), float(screen_stake)
    # Zero-stake rows have blank ROI/lift by contract; their money totals are
    # still checked below, but no ratio envelope is needed.
    if stake == 0.0:
        return 0.0
    money_error = serialization_money_envelope(seed_scope)
    if stake <= money_error:
        # A nonblank ROI cannot be meaningfully reconstructed if its printed
        # denominator is inside the money envelope.  This is a malformed
        # immutable screen, not a reason to accept an unbounded mismatch.
        raise RuntimeError("screen ROI denominator is inside rounding envelope")
    reported = (gross - stake) / stake
    lo = ((gross - money_error) - (stake + money_error)) / (stake + money_error)
    hi = ((gross + money_error) - (stake - money_error)) / (stake - money_error)
    return max(abs(reported - lo), abs(hi - reported)) + 0.5 * RATIO_QUANTUM


def retained_issue_count(slice_type: str, name: str, nissue: int, year_counts: dict[str, int], fold_counts: dict[str, int]) -> int:
    if slice_type == "YEAR": return year_counts[name]
    if slice_type == "FOLD": return fold_counts[name]
    if slice_type == "LOYO": return nissue - year_counts[name]
    raise ValueError(f"unknown slice type: {slice_type}")


def configure():
    lib=R.compile_engine(ROOT,"bj167_scientific_stability_exact.so")
    pd=ctypes.POINTER(ctypes.c_double); pi=ctypes.POINTER(ctypes.c_int)
    lib.bj167_scientific_set_buffers.argtypes = (
        [pd] * 5 + [ctypes.POINTER(ctypes.c_ubyte), pi] + [pd] * 7 +
        [pd] * 3 + [pi] * 2 + [pd] * 4 + [pd] * 2 + [pi] +
        [pd] * 2 + [ctypes.c_int] * 3
    )
    lib.bj167_scientific_begin_issue.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int]
    lib.bj167_scientific_process_source.argtypes=[pd,ctypes.c_int,ctypes.c_char_p,ctypes.c_double,pi,ctypes.c_int,ctypes.c_int]
    lib.bj167_scientific_add_structural.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_double]
    return lib


def write_gz(path, fields, emit):
    with gzip.GzipFile(filename=str(path),mode="wb",mtime=0) as gb, __import__("io").TextIOWrapper(gb,newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader(); emit(w)


def reconcile_scientific_screen(out: Path, screen: Path, selectors: list[dict], cells: list[tuple],
                                allv: list[array.array]) -> None:
    """Fail closed unless all 492 x 963 scientific cells reproduce screen."""
    screened = screening_science_rows(screen)
    expected = len(selectors) * len(cells)
    if len(screened) != expected:
        raise RuntimeError(f"immutable screen scientific-row count {len(screened)} != {expected}")
    fields=["global_science_cell","selector_id","weight_source","mechanism","cap","M","seed_scope","screen_stake_yuan","replay_stake_yuan","stake_delta_yuan","screen_stake_tolerance_yuan","screen_gross_yuan","replay_gross_yuan","gross_delta_yuan","screen_gross_tolerance_yuan","screen_no_tax_roi","replay_no_tax_roi","roi_delta","roi_tolerance","screen_matched_full_no_tax_roi","replay_matched_full_no_tax_roi","full_roi_delta","full_roi_tolerance","screen_matched_full_lift","replay_matched_full_lift","lift_delta","lift_tolerance","serialization_precision_envelope","reconciliation_status"]
    mismatch=0
    def emit(w):
        nonlocal mismatch
        for si,sel in enumerate(selectors):
            full_at=si*len(cells)+960; fnet,fstake=allv[0][full_at],allv[1][full_at]; froi=fnet/fstake if fstake else None
            full_key=science_key(sel["selector_id"],cells[960]); full_screen=screened.get(full_key)
            if full_screen is None: raise RuntimeError(f"scientific FULL control not present in screen: {full_key}")
            full_money_tol=serialization_money_envelope(cells[960][4])
            full_roi_tol=serialization_roi_envelope(full_screen["gross_pre_tax_yuan"],full_screen["stake_yuan"],cells[960][4])
            for ci,cell in enumerate(cells):
                at=si*len(cells)+ci; key=science_key(sel["selector_id"],cell); screen_row=screened.pop(key,None)
                if screen_row is None: raise RuntimeError(f"scientific cell not present in screen: {key}")
                net,stake,gross=allv[0][at],allv[1][at],allv[2][at]; roi=net/stake if stake else None; lift=roi-froi if roi is not None and froi is not None else None
                money_tol=serialization_money_envelope(cell[4])
                roi_tol=serialization_roi_envelope(screen_row["gross_pre_tax_yuan"],screen_row["stake_yuan"],cell[4])
                lift_tol=roi_tol + full_roi_tol + RATIO_QUANTUM
                ok_s, a_s, e_s=same_or_blank(stake,screen_row["stake_yuan"],money_tol)
                ok_g, a_g, e_g=same_or_blank(gross,screen_row["gross_pre_tax_yuan"],money_tol)
                ok_r, a_r, e_r=same_or_blank(roi,screen_row["no_tax_roi"],roi_tol)
                ok_f, a_f, e_f=same_or_blank(froi,screen_row["matched_full_no_tax_roi"],full_roi_tol)
                ok_l, a_l, e_l=same_or_blank(lift,screen_row["matched_full_lift"],lift_tol)
                ok=ok_s and ok_g and ok_r and ok_f and ok_l
                mismatch += not ok
                def delta(a,e): return "" if a=="" or e=="" else f"{float(a)-float(e):.12f}"
                w.writerow({"global_science_cell":at,"selector_id":sel["selector_id"],"weight_source":cell[0],"mechanism":cell[1],"cap":cell[2],"M":cell[3],"seed_scope":cell[4],"screen_stake_yuan":e_s,"replay_stake_yuan":a_s,"stake_delta_yuan":delta(a_s,e_s),"screen_stake_tolerance_yuan":f"{money_tol:.12f}","screen_gross_yuan":e_g,"replay_gross_yuan":a_g,"gross_delta_yuan":delta(a_g,e_g),"screen_gross_tolerance_yuan":f"{money_tol:.12f}","screen_no_tax_roi":e_r,"replay_no_tax_roi":a_r,"roi_delta":delta(a_r,e_r),"roi_tolerance":f"{roi_tol:.12f}","screen_matched_full_no_tax_roi":e_f,"replay_matched_full_no_tax_roi":a_f,"full_roi_delta":delta(a_f,e_f),"full_roi_tolerance":f"{full_roi_tol:.12f}","screen_matched_full_lift":e_l,"replay_matched_full_lift":a_l,"lift_delta":delta(a_l,e_l),"lift_tolerance":f"{lift_tol:.12f}","serialization_precision_envelope":"100x_half_1e-6_seed_money + adaptive_roi" if cell[4] == "ENSEMBLE_100" else "one_half_1e-6_money + adaptive_roi","reconciliation_status":"PASS" if ok else "FAIL"})
    write_gz(out/"scientific_screen_reconciliation.csv.gz",fields,emit)
    if screened: raise RuntimeError(f"unmapped immutable screening scientific rows: {len(screened)}")
    if mismatch: raise RuntimeError(f"scientific screen reconciliation mismatch count={mismatch}")


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--screening-output",default="results/bj167_gate_b_strategy_atlas_v3r1_exact"); ap.add_argument("--output",default="results/bj167_gate_b_strategy_atlas_v3r1_scientific_stability_exact"); args=ap.parse_args()
    screen, final=ROOT/args.screening_output, ROOT/args.output
    execution_start=execution_snapshot()
    if final.exists(): raise RuntimeError("refusing to replace immutable stability companion")
    if not (screen/"SHA256SUMS.json").exists(): raise RuntimeError("completed immutable screen required")
    sums=json.loads((screen/"SHA256SUMS.json").read_text())
    for name,digest in sums.items():
        if R.sha(screen/name)!=digest: raise RuntimeError(f"screening payload drift: {name}")
    stage=Path(str(final)+".stage")
    if stage.exists(): raise RuntimeError("stale stability stage exists")
    stage.mkdir(parents=True); out=stage
    order_rows=list(csv.DictReader((screen/"issue_order.csv").open(newline="")))
    issues=[r["issue_instance"] for r in order_rows]; meta={r["issue_instance"]:r for r in order_rows}; nissue=len(issues)
    years=sorted({meta[x]["year"] for x in issues}); folds=sorted({meta[x]["fold"] for x in issues}); year_i={x:i for i,x in enumerate(years)}; fold_i={x:i for i,x in enumerate(folds)}
    year_issue_count={name: sum(meta[x]["year"] == name for x in issues) for name in years}
    fold_issue_count={name: sum(meta[x]["fold"] == name for x in issues) for name in folds}
    R.verify_ga(); outcomes=R.load_outcomes(); selectors,selector_idx,*_=R.load_surface(); supports,by_issue,_,_=R.build_supports(outcomes,selector_idx)
    with (R.GA/"selector_census.csv").open(newline="") as f: census=list(csv.DictReader(f))
    R.build_policy_status(census,supports,selector_idx)
    if set(issues)!=set(by_issue): raise RuntimeError("screening and canonical issue universes differ")
    cells=science_cells(); ncell=len(cells); total=len(selectors)*ncell
    zeros=lambda:array.array("d",[0.0])*total
    tmp=[zeros() for _ in range(5)]; allv=[zeros() for _ in range(7)]
    mark=array.array("B",[0])*total; touched=array.array("i",[0])*total
    cumulative=zeros(); peak=zeros(); drawdown=zeros(); miss=array.array("i",[0])*total; longest_miss=array.array("i",[0])*total
    yn=array.array("d",[0.0])*(total*len(years)); ys=array.array("d",[0.0])*(total*len(years)); fn=array.array("d",[0.0])*(total*len(folds)); fs=array.array("d",[0.0])*(total*len(folds))
    largest=array.array("d",[-math.inf])*total; largest_stake=zeros(); largest_issue=array.array("i",[-1])*total
    full_issue_net=array.array("d",[0.0])*(len(selectors)*nissue); full_issue_stake=array.array("d",[0.0])*(len(selectors)*nissue)
    lib=configure(); pd=ctypes.c_double; pi=ctypes.c_int
    lib.bj167_scientific_set_buffers(*(R.ptr(x,pd) for x in tmp),R.ptr(mark,ctypes.c_ubyte),R.ptr(touched,pi),*(R.ptr(x,pd) for x in allv),R.ptr(cumulative,pd),R.ptr(peak,pd),R.ptr(drawdown,pd),R.ptr(miss,pi),R.ptr(longest_miss,pi),R.ptr(yn,pd),R.ptr(ys,pd),R.ptr(fn,pd),R.ptr(fs,pd),R.ptr(largest,pd),R.ptr(largest_stake,pd),R.ptr(largest_issue,pi),R.ptr(full_issue_net,pd),R.ptr(full_issue_stake,pd),len(years),len(folds),nissue)
    for ii,issue in enumerate(issues):
        lib.bj167_scientific_begin_issue(ii,year_i[meta[issue]["year"]],fold_i[meta[issue]["fold"]])
        for s in by_issue[issue]:
            occ=array.array("i",s["eligible_selectors"])
            if not occ: continue
            signature="|".join(s["mids"]).encode()
            for src_i,src in enumerate(R.SOURCES):
                role=array.array("d",[v for rr in s["roles"] for v in rr["source"][src]])
                lib.bj167_scientific_process_source(R.ptr(role,pd),s["truth"],signature,s["payout"],R.ptr(occ,pi),len(occ),src_i*160)
            pl,pc,ql,qc=R.derive_delete(s["roles"])
            for si in occ: lib.bj167_scientific_add_structural(si,s["truth"],pl,pc,ql,qc,s["payout"])
        lib.bj167_scientific_end_issue()
        if (ii+1)%10==0: print(f"scientific stability issues {ii+1}/{nissue}",flush=True)
    # The scalar summary is the keyed all-cell coverage census.  Slices below
    # are derived from exact cell/year/fold totals, never seed pseudo-history.
    fields=["global_science_cell","selector_id","weight_source","mechanism","cap","M","seed_scope","coverage_scope","coverage_status","no_tax_roi","matched_full_no_tax_roi","paired_lift","ex_largest_issue_no_tax_roi","ex_largest_issue_full_roi","ex_largest_issue_lift","ex_largest_year_no_tax_roi","ex_largest_year_full_roi","ex_largest_year_lift","largest_signed_issue","largest_signed_issue_net_yuan","largest_signed_year","gross_issue_hhi","gross_top_issue_share","drawdown_no_tax_yuan","longest_miss_streak","year_slice_count","fold_slice_count","loyo_slice_count"]
    def summary_emit(w):
        for si,sel in enumerate(selectors):
            full_at=si*ncell+960; fnet,fstake=allv[0][full_at],allv[1][full_at]
            for ci,(src,me,cap,m,scope) in enumerate(cells):
                at=si*ncell+ci; net,stake=allv[0][at],allv[1][at]; roi=net/stake if stake else None; froi=fnet/fstake if fstake else None; lift=roi-froi if roi is not None and froi is not None else None
                no_bet = stake == 0.0
                li=largest_issue[at] if not no_bet else -1; ex_stake=stake-(largest_stake[at] if li>=0 else 0); ex_net=net-(largest[at] if li>=0 else 0); fex_net=fnet-(full_issue_net[si*nissue+li] if li>=0 else 0); fex_stake=fstake-(full_issue_stake[si*nissue+li] if li>=0 else 0); exroi=ex_net/ex_stake if ex_stake else None; fexroi=fex_net/fex_stake if fex_stake else None
                byyear=[(yn[at*len(years)+yi],ys[at*len(years)+yi]) for yi in range(len(years))]
                ly=max(range(len(years)),key=lambda yi:byyear[yi][0]) if not no_bet else -1
                ynet=net-byyear[ly][0] if ly>=0 else 0.0; ystake=stake-byyear[ly][1] if ly>=0 else 0.0; fy_net=fnet-yn[full_at*len(years)+ly] if ly>=0 else 0.0; fy_stake=fstake-ys[full_at*len(years)+ly] if ly>=0 else 0.0; yroi=ynet/ystake if ystake else None; fyroi=fy_net/fy_stake if fy_stake else None
                gross=allv[2][at]; hhi=allv[5][at]/(gross*gross) if gross else 0.0; top=allv[6][at]/gross if gross else 0.0
                w.writerow({"global_science_cell":at,"selector_id":sel["selector_id"],"weight_source":src,"mechanism":me,"cap":cap,"M":m,"seed_scope":scope,"coverage_scope":"ALL_ATLAS_SCIENTIFIC_CELLS","coverage_status":"NO_BET_ZERO_STAKE" if no_bet else "EXACT_YEAR_FOLD_LOYO_AND_EXCLUSIONS","no_tax_roi":"" if roi is None else f"{roi:.12f}","matched_full_no_tax_roi":"" if froi is None else f"{froi:.12f}","paired_lift":"" if lift is None else f"{lift:.12f}","ex_largest_issue_no_tax_roi":"" if exroi is None else f"{exroi:.12f}","ex_largest_issue_full_roi":"" if fexroi is None else f"{fexroi:.12f}","ex_largest_issue_lift":"" if exroi is None or fexroi is None else f"{exroi-fexroi:.12f}","ex_largest_year_no_tax_roi":"" if yroi is None else f"{yroi:.12f}","ex_largest_year_full_roi":"" if fyroi is None else f"{fyroi:.12f}","ex_largest_year_lift":"" if yroi is None or fyroi is None else f"{yroi-fyroi:.12f}","largest_signed_issue":issues[li] if li>=0 else "","largest_signed_issue_net_yuan":"" if li<0 else f"{largest[at]:.6f}","largest_signed_year":years[ly] if ly>=0 else "","gross_issue_hhi":"" if no_bet else f"{hhi:.12f}","gross_top_issue_share":"" if no_bet else f"{top:.12f}","drawdown_no_tax_yuan":"" if no_bet else f"{drawdown[at]:.6f}","longest_miss_streak":"" if no_bet else longest_miss[at],"year_slice_count":len(years),"fold_slice_count":len(folds),"loyo_slice_count":len(years)})
    write_gz(out/"scientific_cell_stability_summary.csv.gz",fields,summary_emit)
    # Explicit all-surface read-back prevents the compact positional layout
    # from being mistaken for evidence of a correct selector/cell join.
    reconcile_scientific_screen(out,screen,selectors,cells,allv)
    shutil.copyfile(out/"scientific_cell_stability_summary.csv.gz",out/"chart_source_scientific_risk.csv.gz")
    # This large chart source deliberately has one aggregate scientific cell
    # per slice; stochastic seeds are pooled before this point.
    slice_fields=["global_science_cell","selector_id","weight_source","mechanism","cap","M","seed_scope","coverage_scope","slice_type","slice","retained_issue_count","candidate_no_tax_roi","matched_full_no_tax_roi","paired_lift"]
    def slice_emit(w):
        for si,sel in enumerate(selectors):
            full_at=si*ncell+960
            for ci,(src,me,cap,m,scope) in enumerate(cells):
                at=si*ncell+ci
                for typ,names,nets,stakes,subtract in (("YEAR",years,yn,ys,False),("FOLD",folds,fn,fs,False),("LOYO",years,yn,ys,True)):
                    count=len(years) if typ!="FOLD" else len(folds)
                    for k,name in enumerate(names):
                        net,stake=nets[at*count+k],stakes[at*count+k]; fnet,fstake=nets[full_at*count+k],stakes[full_at*count+k]
                        if subtract: net,stake=allv[0][at]-net,allv[1][at]-stake; fnet,fstake=allv[0][full_at]-fnet,allv[1][full_at]-fstake
                        roi=net/stake if stake else None; froi=fnet/fstake if fstake else None
                        included = retained_issue_count(typ,name,nissue,year_issue_count,fold_issue_count)
                        w.writerow({"global_science_cell":at,"selector_id":sel["selector_id"],"weight_source":src,"mechanism":me,"cap":cap,"M":m,"seed_scope":scope,"coverage_scope":"ALL_ATLAS_SCIENTIFIC_CELLS","slice_type":typ,"slice":name,"retained_issue_count":included,"candidate_no_tax_roi":"" if roi is None else f"{roi:.12f}","matched_full_no_tax_roi":"" if froi is None else f"{froi:.12f}","paired_lift":"" if roi is None or froi is None else f"{roi-froi:.12f}"})
    write_gz(out/"chart_source_chronology_slices_all_scientific.csv.gz",slice_fields,slice_emit)
    # Gate-A requires exact M2187 reconciliation versus selector-matched FULL.
    rec_fields=["selector_id","weight_source","mechanism","M","seed_scope","candidate_scale","normalized_candidate_stake_yuan","matched_full_stake_yuan","stake_difference_yuan","normalized_candidate_gross_yuan","matched_full_gross_yuan","gross_difference_yuan","normalized_candidate_net_yuan","matched_full_net_yuan","net_difference_yuan","reconciliation_status"]
    with (out/"m2187_full_reconciliation.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rec_fields);w.writeheader()
        for si,sel in enumerate(selectors):
            full_at=si*ncell+960
            for src_i,src in enumerate(R.SOURCES):
                for local,me,scale in ((src_i*160+20+19,"WOR_DISTINCT",100),(src_i*160+140+19,"DETERMINISTIC_TOP_MASS",1)):
                    at=si*ncell+local; vals=[allv[j][at]/scale for j in range(3)]; full=[allv[j][full_at] for j in range(3)]; dif=[vals[j]-full[j] for j in range(3)]
                    ok=all(abs(x)<1e-6 for x in dif)
                    w.writerow({"selector_id":sel["selector_id"],"weight_source":src,"mechanism":me,"M":2187,"seed_scope":"ENSEMBLE_100" if scale==100 else "DETERMINISTIC","candidate_scale":scale,"normalized_candidate_stake_yuan":f"{vals[1]:.6f}","matched_full_stake_yuan":f"{full[1]:.6f}","stake_difference_yuan":f"{dif[1]:.6f}","normalized_candidate_gross_yuan":f"{vals[2]:.6f}","matched_full_gross_yuan":f"{full[2]:.6f}","gross_difference_yuan":f"{dif[2]:.6f}","normalized_candidate_net_yuan":f"{vals[0]:.6f}","matched_full_net_yuan":f"{full[0]:.6f}","net_difference_yuan":f"{dif[0]:.6f}","reconciliation_status":"EXACT_EQUIVALENT" if ok else "FAIL"})
                    if not ok: raise RuntimeError(f"M2187 reconciliation drift {sel['selector_id']} {src} {me}")
    coverage={"contract":"bj167-gate-b-v3r1-scientific-stability","scientific_cell_count":total,"selector_count":len(selectors),"science_cells_per_selector":ncell,"stochastic_unit":"100-seed pooled ensemble","deterministic_unit":"one arm","year_count":len(years),"fold_count":len(folds),"screen_reconciliation":"scientific_screen_reconciliation.csv.gz exact PASS required","coverage":"all scientific cells receive YEAR/FOLD/LOYO, signed-largest issue/year, paired selector FULL exclusions, pooled HHI/top share/drawdown/miss streak"}
    (out/"scientific_stability_coverage.json").write_text(json.dumps(coverage,sort_keys=True,indent=2)+"\n")
    execution_end=execution_snapshot()
    write_execution_provenance(out,screen,execution_start,execution_end)
    R.write_file_census(out);R.finalize_package_identity(out,"bj167-gate-b-v3r1-scientific-stability",{"screening_manifest_sha256":R.sha(screen/"SHA256SUMS.json"),"screening_content_identity_sha256":R.sha(screen/"CONTENT_IDENTITY.json"),"all_scientific_execution_head":execution_start["git_head"],"all_scientific_runner_sha256":execution_start["runner_sha256"],"all_scientific_native_wrapper_sha256":execution_start["native_wrapper_sha256"],"allocator_sha256":R.EXPECTED_ALLOCATOR_SHA256,"scientific_cell_count":total});R.atomic_publish(stage,final);print(f"WROTE {final}",flush=True)

if __name__=="__main__": main()
