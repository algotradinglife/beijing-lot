#!/usr/bin/env python3
"""Exact all-scientific-cell stability companion for #167 Gate B v3r1.

This does not re-open or alter the completed full screen.  It reduces the
frozen 100-seed WR/WOR families to their intended scientific units and settles
YEAR/FOLD/LOYO and signed-largest exclusions for every selector/allocation
science cell.  Seed-level rows remain diagnostics, never football histories.
"""
from __future__ import annotations

import argparse, array, csv, ctypes, gzip, importlib.util, json, math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("bj167_runner",ROOT/"scripts"/"settle_bj167_strategy_atlas_gate_b_exact.py")
R=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(R)
CELLS_PER_SELECTOR=963


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


def configure():
    lib=R.compile_engine(ROOT,"bj167_scientific_stability_exact.so")
    pd=ctypes.POINTER(ctypes.c_double); pi=ctypes.POINTER(ctypes.c_int)
    lib.bj167_scientific_set_buffers.argtypes=[pd,pd,pd,pd,pd,ctypes.POINTER(ctypes.c_ubyte),pi,pd,pd,pd,pd,pd,pd,pd,pd,pd,pd,pi,pd,pd,ctypes.c_int,ctypes.c_int,ctypes.c_int]
    lib.bj167_scientific_begin_issue.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int]
    lib.bj167_scientific_process_source.argtypes=[pd,ctypes.c_int,ctypes.c_char_p,ctypes.c_double,pi,ctypes.c_int,ctypes.c_int]
    lib.bj167_scientific_add_structural.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_double]
    return lib


def write_gz(path, fields, emit):
    with gzip.GzipFile(filename=str(path),mode="wb",mtime=0) as gb, __import__("io").TextIOWrapper(gb,newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader(); emit(w)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--screening-output",default="results/bj167_gate_b_strategy_atlas_v3r1_exact"); ap.add_argument("--output",default="results/bj167_gate_b_strategy_atlas_v3r1_scientific_stability_exact"); args=ap.parse_args()
    screen, final=ROOT/args.screening_output, ROOT/args.output
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
    R.verify_ga(); outcomes=R.load_outcomes(); selectors,selector_idx,*_=R.load_surface(); supports,by_issue,_,_=R.build_supports(outcomes,selector_idx)
    with (R.GA/"selector_census.csv").open(newline="") as f: census=list(csv.DictReader(f))
    R.build_policy_status(census,supports,selector_idx)
    if set(issues)!=set(by_issue): raise RuntimeError("screening and canonical issue universes differ")
    cells=science_cells(); ncell=len(cells); total=len(selectors)*ncell
    zeros=lambda:array.array("d",[0.0])*total
    tmp=[zeros() for _ in range(5)]; allv=[zeros() for _ in range(5)]
    mark=array.array("B",[0])*total; touched=array.array("i",[0])*total
    yn=array.array("d",[0.0])*(total*len(years)); ys=array.array("d",[0.0])*(total*len(years)); fn=array.array("d",[0.0])*(total*len(folds)); fs=array.array("d",[0.0])*(total*len(folds))
    largest=array.array("d",[-math.inf])*total; largest_stake=zeros(); largest_issue=array.array("i",[-1])*total
    full_issue_net=array.array("d",[0.0])*(len(selectors)*nissue); full_issue_stake=array.array("d",[0.0])*(len(selectors)*nissue)
    lib=configure(); pd=ctypes.c_double; pi=ctypes.c_int
    lib.bj167_scientific_set_buffers(*(R.ptr(x,pd) for x in tmp),R.ptr(mark,ctypes.c_ubyte),R.ptr(touched,pi),*(R.ptr(x,pd) for x in allv),R.ptr(yn,pd),R.ptr(ys,pd),R.ptr(fn,pd),R.ptr(fs,pd),R.ptr(largest,pd),R.ptr(largest_stake,pd),R.ptr(largest_issue,pi),R.ptr(full_issue_net,pd),R.ptr(full_issue_stake,pd),len(years),len(folds),nissue)
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
    fields=["global_science_cell","selector_id","weight_source","mechanism","cap","M","seed_scope","coverage_scope","coverage_status","no_tax_roi","matched_full_no_tax_roi","paired_lift","ex_largest_issue_no_tax_roi","ex_largest_issue_full_roi","ex_largest_issue_lift","ex_largest_year_no_tax_roi","ex_largest_year_full_roi","ex_largest_year_lift","largest_signed_issue","largest_signed_issue_net_yuan","largest_signed_year","gross_issue_hhi_unavailable","year_slice_count","fold_slice_count","loyo_slice_count"]
    def summary_emit(w):
        for si,sel in enumerate(selectors):
            full_at=si*ncell+960; fnet,fstake=allv[0][full_at],allv[1][full_at]
            for ci,(src,me,cap,m,scope) in enumerate(cells):
                at=si*ncell+ci; net,stake=allv[0][at],allv[1][at]; roi=net/stake if stake else None; froi=fnet/fstake if fstake else None; lift=roi-froi if roi is not None and froi is not None else None
                li=largest_issue[at]; ex_stake=stake-(largest_stake[at] if li>=0 else 0); ex_net=net-(largest[at] if li>=0 else 0); fex_net=fnet-(full_issue_net[si*nissue+li] if li>=0 else 0); fex_stake=fstake-(full_issue_stake[si*nissue+li] if li>=0 else 0); exroi=ex_net/ex_stake if ex_stake else None; fexroi=fex_net/fex_stake if fex_stake else None
                byyear=[(yn[at*len(years)+yi],ys[at*len(years)+yi]) for yi in range(len(years))]; ly=max(range(len(years)),key=lambda yi:byyear[yi][0]); ynet=net-byyear[ly][0]; ystake=stake-byyear[ly][1]; fy_net=fnet-yn[full_at*len(years)+ly]; fy_stake=fstake-ys[full_at*len(years)+ly]; yroi=ynet/ystake if ystake else None; fyroi=fy_net/fy_stake if fy_stake else None
                w.writerow({"global_science_cell":at,"selector_id":sel["selector_id"],"weight_source":src,"mechanism":me,"cap":cap,"M":m,"seed_scope":scope,"coverage_scope":"ALL_ATLAS_SCIENTIFIC_CELLS","coverage_status":"EXACT_YEAR_FOLD_LOYO_AND_EXCLUSIONS","no_tax_roi":"" if roi is None else f"{roi:.12f}","matched_full_no_tax_roi":"" if froi is None else f"{froi:.12f}","paired_lift":"" if lift is None else f"{lift:.12f}","ex_largest_issue_no_tax_roi":"" if exroi is None else f"{exroi:.12f}","ex_largest_issue_full_roi":"" if fexroi is None else f"{fexroi:.12f}","ex_largest_issue_lift":"" if exroi is None or fexroi is None else f"{exroi-fexroi:.12f}","ex_largest_year_no_tax_roi":"" if yroi is None else f"{yroi:.12f}","ex_largest_year_full_roi":"" if fyroi is None else f"{fyroi:.12f}","ex_largest_year_lift":"" if yroi is None or fyroi is None else f"{yroi-fyroi:.12f}","largest_signed_issue":issues[li] if li>=0 else "","largest_signed_issue_net_yuan":"" if li<0 else f"{largest[at]:.6f}","largest_signed_year":years[ly],"gross_issue_hhi_unavailable":"see candidate exact contribution companion for 20k candidate diagnostics","year_slice_count":len(years),"fold_slice_count":len(folds),"loyo_slice_count":len(years)})
    write_gz(out/"scientific_cell_stability_summary.csv.gz",fields,summary_emit)
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
                        w.writerow({"global_science_cell":at,"selector_id":sel["selector_id"],"weight_source":src,"mechanism":me,"cap":cap,"M":m,"seed_scope":scope,"coverage_scope":"ALL_ATLAS_SCIENTIFIC_CELLS","slice_type":typ,"slice":name,"retained_issue_count":nissue-(sum(1 for x in issues if meta[x]["year"]==name) if typ=="LOYO" else (sum(1 for x in issues if meta[x]["year"]==name) if typ=="YEAR" else sum(1 for x in issues if meta[x]["fold"]==name))),"candidate_no_tax_roi":"" if roi is None else f"{roi:.12f}","matched_full_no_tax_roi":"" if froi is None else f"{froi:.12f}","paired_lift":"" if roi is None or froi is None else f"{roi-froi:.12f}"})
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
    coverage={"contract":"bj167-gate-b-v3r1-scientific-stability","scientific_cell_count":total,"selector_count":len(selectors),"science_cells_per_selector":ncell,"stochastic_unit":"100-seed pooled ensemble","deterministic_unit":"one arm","year_count":len(years),"fold_count":len(folds),"coverage":"all scientific cells receive YEAR/FOLD/LOYO, signed-largest issue/year and paired selector FULL exclusions"}
    (out/"scientific_stability_coverage.json").write_text(json.dumps(coverage,sort_keys=True,indent=2)+"\n")
    R.write_file_census(out);R.finalize_package_identity(out,"bj167-gate-b-v3r1-scientific-stability",{"screening_manifest_sha256":R.sha(screen/"SHA256SUMS.json"),"allocator_sha256":R.EXPECTED_ALLOCATOR_SHA256,"scientific_cell_count":total});R.atomic_publish(stage,final);print(f"WROTE {final}",flush=True)

if __name__=="__main__": main()
