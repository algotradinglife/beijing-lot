#!/usr/bin/env python3
"""Exact all-scientific-cell stability companion for #167 Gate B v3r1.

This does not re-open or alter the completed full screen.  It reduces the
frozen 100-seed WR/WOR families to their intended scientific units and settles
YEAR/FOLD/LOYO and signed-largest exclusions for every selector/allocation
science cell.  Seed-level rows remain diagnostics, never football histories.
"""
from __future__ import annotations

import argparse, array, csv, ctypes, gzip, importlib.util, json, math, os, shutil, subprocess, uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("bj167_runner",ROOT/"scripts"/"settle_bj167_strategy_atlas_gate_b_exact.py")
R=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(R)
CELLS_PER_SELECTOR=963
CHECKPOINT_CONTRACT="bj167-gate-b-v3r1-shared-science-candidate-checkpoint-v1"
# The completed screen serializes every seed-level monetary total with
# ``money(...)=%.6f`` before it sums the 100 stochastic rows.  The companion
# instead pools those same ticket totals before it writes its comparison.
# These are therefore the only permitted reconciliation differences: half a
# decimal quantum for each serialized seed (or one deterministic row).
MONEY_QUANTUM = 1e-6
RATIO_QUANTUM = 1e-12
NATIVE_WRAPPER_PATH = ROOT / "scripts" / "bj167_exact_atlas.cpp"
STRUCTURAL_DELETE_MECHANISMS = frozenset({"P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE"})


def unique_stage(target: Path) -> Path:
    """Create a fresh retry-safe staging directory beside ``target``.

    A failed immutable-package attempt must never block its retry by retaining
    a fixed ``.stage`` directory. Each attempt gets a fresh unmanifested
    directory; only a successful atomic publish claims the immutable target.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    while True:
        stage = target.with_name(f"{target.name}.stage-{uuid.uuid4().hex}")
        try:
            stage.mkdir()
            return stage
        except FileExistsError:
            continue


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


def write_execution_provenance(out: Path, screen: Path, start: dict, end: dict, checkpoint: Path | None = None) -> None:
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
    if checkpoint is not None:
        payload["shared_science_checkpoint"]={"package":checkpoint.name,"manifest_sha256":R.sha(checkpoint/"SHA256SUMS.json"),"mode":"RESUME_NO_TICKET_REPLAY"}
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


def reporting_science_cell(cell: tuple[str, str, str, str, str]) -> tuple[str, str, str, str, str]:
    """Map an internal science cell to its frozen reporting identity.

    Structural P/Q deletion has an economic support of 1,458 tickets in the
    pooled companion, but it is not an M-grid sampling arm. The immutable
    screen therefore reports those two controls as M=NA. No other M value is
    normalized here.
    """
    source, mechanism, cap, m, seed_scope = cell
    if mechanism in STRUCTURAL_DELETE_MECHANISMS:
        if m not in {"1458", "NA"}:
            raise RuntimeError(f"structural delete internal M drift: {mechanism} M={m}")
        m = "NA"
    return source, mechanism, cap, m, seed_scope


def science_key(selector_id: str, cell: tuple[str, str, str, str, str]) -> tuple[str, str, str, str, str, str]:
    return (selector_id, *reporting_science_cell(cell))


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
        [pd] * 6 + [ctypes.POINTER(ctypes.c_ubyte), pi] + [pd] * 7 +
        [pd] * 3 + [pi] * 2 + [pd] * 4 + [pd] * 2 + [pi] +
        [pd] * 2 + [ctypes.c_int] * 3
    )
    lib.bj167_scientific_begin_issue.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int]
    lib.bj167_scientific_process_source.argtypes=[pd,ctypes.c_int,ctypes.c_char_p,ctypes.c_double,pi,ctypes.c_int,ctypes.c_int]
    lib.bj167_scientific_add_structural.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_double]
    lib.bj167_scientific_set_candidate_issue_buffers.argtypes=[pi,ctypes.c_int]+[pd]*11
    return lib


def candidate_science_mapping(screen: Path, selectors: list[dict], selector_idx: dict[str, int], cells: list[tuple]) -> tuple[list[dict], array.array]:
    """Bind every immutable frozen candidate to one pooled science cell.

    The recovered screen's ``global_cell`` is a display/address in the wide
    24,723-cell screen.  This mapping deliberately preserves it as provenance
    while deriving the distinct 963-cell pooled address from the immutable
    candidate identity.  No positional or label heuristic is permitted.
    """
    post_path=ROOT/"scripts"/"settle_bj167_atlas_postscreen_exact.py"
    spec=importlib.util.spec_from_file_location("bj167_postscreen_checkpoint",post_path)
    post=importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(post)
    recovered=post.verify_recovered_screen(screen)
    rows=post.load_recovered_frozen_candidates(screen,recovered)
    local={cell:i for i,cell in enumerate(cells)}
    mapping=[]; addresses=array.array("i")
    for row in rows:
        cell,science_m=scientific_cell_identity(row)
        if row["selector_id"] not in selector_idx or cell not in local:
            raise RuntimeError(f"frozen candidate cannot map to scientific cell: {row['candidate_index']}")
        at=selector_idx[row["selector_id"]]*len(cells)+local[cell]
        mapping.append({"candidate_index":row["candidate_index"],"selector_id":row["selector_id"],"weight_source":row["weight_source"],"mechanism":row["mechanism"],"cap":row["cap"],"M":row["M"],"science_M":science_m,"seed_scope":row["seed_scope"],"screen_global_cell":row.get("global_cell",""),"global_science_cell":at,"candidate_inclusion":row["candidate_inclusion"],"screen_stake_yuan":row["screen_stake_yuan"],"screen_no_tax_roi":row["screen_no_tax_roi"],"screen_matched_full_lift":row["screen_matched_full_lift"]})
        addresses.append(at)
    if [r["candidate_index"] for r in mapping] != list(range(len(mapping))):
        raise RuntimeError("candidate checkpoint mapping index drift")
    return mapping, addresses


def scientific_cell_identity(row: dict) -> tuple[tuple[str,str,str,str,str], str]:
    """Return the explicit 963-cell identity while retaining the frozen key."""
    # The wide screen stored global P/Q-delete controls with M=NA because
    # they are structural rather than sampled.  The immutable 963-cell
    # science layout represents the same 3^7-3^6 support explicitly as
    # M=1458; callers retain the original frozen M beside this mapping.
    science_m="1458" if row["mechanism"] in {"P_MIN_GLOBAL_DELETE","Q_MIN_GLOBAL_DELETE"} and row["M"]=="NA" else row["M"]
    return (row["weight_source"],row["mechanism"],row["cap"],science_m,row["seed_scope"]),science_m


def checkpoint_array_specs(candidate_values: dict[str, array.array], nissue: int) -> dict[str, dict]:
    return {name:{"path":f"candidate_issue_arrays/{name}.f64","typecode":"d","shape":[len(candidate_values[name])//nissue,nissue]} for name in sorted(candidate_values)}


def aggregate_array_specs(science_values: dict[str, tuple[array.array, list[int]]]) -> dict[str, dict]:
    return {name:{"path":f"science_aggregate_arrays/{name}.{value.typecode}","typecode":value.typecode,"shape":shape} for name,(value,shape) in sorted(science_values.items())}


def write_candidate_checkpoint(checkpoint: Path, screen: Path, mapping: list[dict], issue_rows: list[dict], selectors: list[dict], cells: list[tuple], candidate_values: dict[str, array.array], science_values: dict[str, tuple[array.array, list[int]]], execution_start: dict, execution_end: dict) -> None:
    """Atomically persist the one native replay's candidate issue ledger."""
    if execution_start != execution_end: raise RuntimeError("scientific replay executable identity changed during run")
    if checkpoint.exists(): raise RuntimeError("refusing to replace immutable shared checkpoint")
    stage=unique_stage(checkpoint)
    try:
        with (stage/"candidate_science_mapping.csv").open("w",newline="") as f:
            fields=["candidate_index","selector_id","weight_source","mechanism","cap","M","science_M","seed_scope","screen_global_cell","global_science_cell","candidate_inclusion","screen_stake_yuan","screen_no_tax_roi","screen_matched_full_lift"]
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(mapping)
        with (stage/"issue_order.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(issue_rows[0]));w.writeheader();w.writerows(issue_rows)
        with (stage/"selector_grid.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(selectors[0]));w.writeheader();w.writerows(selectors)
        with (stage/"science_cells.csv").open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=["science_cell","weight_source","mechanism","cap","M","seed_scope"]);w.writeheader()
            for i,cell in enumerate(cells): w.writerow({"science_cell":i,"weight_source":cell[0],"mechanism":cell[1],"cap":cell[2],"M":cell[3],"seed_scope":cell[4]})
        shutil.copyfile(screen/"candidate_freeze.csv",stage/"candidate_freeze.csv")
        shutil.copyfile(screen/"candidate_freeze.json",stage/"candidate_freeze.json")
        specs=checkpoint_array_specs(candidate_values,len(issue_rows))
        for name,spec in specs.items():
            p=stage/spec["path"];p.parent.mkdir(parents=True,exist_ok=True)
            with p.open("wb") as f: candidate_values[name].tofile(f)
        science_specs=aggregate_array_specs(science_values)
        for name,spec in science_specs.items():
            p=stage/spec["path"];p.parent.mkdir(parents=True,exist_ok=True)
            with p.open("wb") as f: science_values[name][0].tofile(f)
        metadata={"contract":CHECKPOINT_CONTRACT,"screening_package":screen.name,"screening_manifest_sha256":R.sha(screen/"SHA256SUMS.json"),"screening_content_identity_sha256":R.sha(screen/"CONTENT_IDENTITY.json"),"candidate_freeze_sha256":R.sha(screen/"candidate_freeze.csv"),"candidate_count":len(mapping),"issue_count":len(issue_rows),"selector_count":len(selectors),"science_cell_count":len(cells),"candidate_science_mapping_sha256":R.sha(stage/"candidate_science_mapping.csv"),"issue_order_sha256":R.sha(stage/"issue_order.csv"),"selector_grid_sha256":R.sha(stage/"selector_grid.csv"),"science_cells_sha256":R.sha(stage/"science_cells.csv"),"array_specs":specs,"science_aggregate_specs":science_specs,"native_execution_start":execution_start,"native_execution_end":execution_end,"frozen_allocator_sha256":R.sha(ROOT/"scripts"/"bj145_fast_alloc.cpp"),"native_wrapper_sha256":R.sha(NATIVE_WRAPPER_PATH)}
        (stage/"checkpoint_metadata.json").write_text(json.dumps(metadata,sort_keys=True,indent=2)+"\n")
        R.write_file_census(stage)
        R.finalize_package_identity(stage,CHECKPOINT_CONTRACT,{"candidate_count":len(mapping),"issue_count":len(issue_rows),"candidate_freeze_sha256":metadata["candidate_freeze_sha256"],"screening_manifest_sha256":metadata["screening_manifest_sha256"],"candidate_science_mapping_sha256":metadata["candidate_science_mapping_sha256"]})
        R.atomic_publish(stage,checkpoint)
    except Exception:
        # Keep a failed stage for diagnosis; atomic publication ensures it can
        # never be mistaken for an immutable checkpoint.
        raise


def verify_candidate_checkpoint(checkpoint: Path, screen: Path) -> tuple[dict, list[dict], list[dict], list[dict], list[tuple], dict[str,array.array], dict[str,array.array]]:
    """Load a complete atomic checkpoint; no ticket replay is available here."""
    meta=json.loads((checkpoint/"checkpoint_metadata.json").read_text())
    if meta.get("contract")!=CHECKPOINT_CONTRACT: raise RuntimeError("shared checkpoint contract mismatch")
    if meta.get("screening_manifest_sha256")!=R.sha(screen/"SHA256SUMS.json"): raise RuntimeError("shared checkpoint screen manifest drift")
    sums=json.loads((checkpoint/"SHA256SUMS.json").read_text())
    for name,digest in sums.items():
        if R.sha(checkpoint/name)!=digest: raise RuntimeError(f"shared checkpoint payload drift: {name}")
    mapping=list(csv.DictReader((checkpoint/"candidate_science_mapping.csv").open(newline="")))
    issues=list(csv.DictReader((checkpoint/"issue_order.csv").open(newline="")))
    selectors=list(csv.DictReader((checkpoint/"selector_grid.csv").open(newline="")))
    with (checkpoint/"science_cells.csv").open(newline="") as f: cells=[(r["weight_source"],r["mechanism"],r["cap"],r["M"],r["seed_scope"]) for r in csv.DictReader(f)]
    for field,path in (("candidate_science_mapping_sha256","candidate_science_mapping.csv"),("issue_order_sha256","issue_order.csv"),("selector_grid_sha256","selector_grid.csv"),("science_cells_sha256","science_cells.csv")):
        if meta.get(field)!=R.sha(checkpoint/path): raise RuntimeError(f"shared checkpoint frozen metadata drift: {field}")
    if len(mapping)!=int(meta["candidate_count"]) or len(issues)!=int(meta["issue_count"]) or len(selectors)!=int(meta["selector_count"]) or len(cells)!=int(meta["science_cell_count"]): raise RuntimeError("shared checkpoint dimension drift")
    values={}
    for name,spec in meta["array_specs"].items():
        a=array.array(spec["typecode"])
        with (checkpoint/spec["path"]).open("rb") as f:a.fromfile(f,(checkpoint/spec["path"]).stat().st_size//a.itemsize)
        if len(a)!=math.prod(spec["shape"]): raise RuntimeError(f"shared checkpoint array shape drift: {name}")
        values[name]=a
    science={}
    for name,spec in meta.get("science_aggregate_specs",{}).items():
        a=array.array(spec["typecode"])
        with (checkpoint/spec["path"]).open("rb") as f:a.fromfile(f,(checkpoint/spec["path"]).stat().st_size//a.itemsize)
        if len(a)!=math.prod(spec["shape"]): raise RuntimeError(f"shared checkpoint scientific array shape drift: {name}")
        science[name]=a
    if not science: raise RuntimeError("shared checkpoint lacks resumable scientific aggregates")
    return meta,mapping,issues,selectors,cells,values,science


def write_gz(path, fields, emit):
    with gzip.GzipFile(filename=str(path),mode="wb",mtime=0) as gb, __import__("io").TextIOWrapper(gb,newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader(); emit(w)


def scientific_checkpoint_values(allv, cumulative, peak, drawdown, miss, longest_miss, yn, ys, fn, fs, largest, largest_stake, largest_issue, full_issue_net, full_issue_stake, total, year_count, fold_count, selector_count, issue_count):
    """Named aggregate state required by the no-replay scientific finalizer."""
    values={f"allv_{i}":(v,[total]) for i,v in enumerate(allv)}
    values.update({"cumulative":(cumulative,[total]),"peak":(peak,[total]),"drawdown":(drawdown,[total]),"miss":(miss,[total]),"longest_miss":(longest_miss,[total]),"year_net":(yn,[total,year_count]),"year_stake":(ys,[total,year_count]),"fold_net":(fn,[total,fold_count]),"fold_stake":(fs,[total,fold_count]),"largest":(largest,[total]),"largest_stake":(largest_stake,[total]),"largest_issue":(largest_issue,[total]),"full_issue_net":(full_issue_net,[selector_count,issue_count]),"full_issue_stake":(full_issue_stake,[selector_count,issue_count])})
    return values


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
                report_cell=reporting_science_cell(cell)
                w.writerow({"global_science_cell":at,"selector_id":sel["selector_id"],"weight_source":report_cell[0],"mechanism":report_cell[1],"cap":report_cell[2],"M":report_cell[3],"seed_scope":report_cell[4],"screen_stake_yuan":e_s,"replay_stake_yuan":a_s,"stake_delta_yuan":delta(a_s,e_s),"screen_stake_tolerance_yuan":f"{money_tol:.12f}","screen_gross_yuan":e_g,"replay_gross_yuan":a_g,"gross_delta_yuan":delta(a_g,e_g),"screen_gross_tolerance_yuan":f"{money_tol:.12f}","screen_no_tax_roi":e_r,"replay_no_tax_roi":a_r,"roi_delta":delta(a_r,e_r),"roi_tolerance":f"{roi_tol:.12f}","screen_matched_full_no_tax_roi":e_f,"replay_matched_full_no_tax_roi":a_f,"full_roi_delta":delta(a_f,e_f),"full_roi_tolerance":f"{full_roi_tol:.12f}","screen_matched_full_lift":e_l,"replay_matched_full_lift":a_l,"lift_delta":delta(a_l,e_l),"lift_tolerance":f"{lift_tol:.12f}","serialization_precision_envelope":"100x_half_1e-6_seed_money + adaptive_roi" if cell[4] == "ENSEMBLE_100" else "one_half_1e-6_money + adaptive_roi","reconciliation_status":"PASS" if ok else "FAIL"})
    write_gz(out/"scientific_screen_reconciliation.csv.gz",fields,emit)
    if screened: raise RuntimeError(f"unmapped immutable screening scientific rows: {len(screened)}")
    if mismatch: raise RuntimeError(f"scientific screen reconciliation mismatch count={mismatch}")


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--screening-output",default="results/bj167_gate_b_strategy_atlas_v3r1_recovered_final_v1"); ap.add_argument("--output",default="results/bj167_gate_b_strategy_atlas_v3r1_scientific_stability_exact"); ap.add_argument("--checkpoint-output",default="results/bj167_gate_b_strategy_atlas_v3r1_shared_science_checkpoint_v1"); ap.add_argument("--replay-to-checkpoint","--replay-only",dest="replay_to_checkpoint",action="store_true"); ap.add_argument("--finalize-checkpoint","--scientific-finalize",dest="finalize_checkpoint",action="store_true"); ap.add_argument("--preflight",action="store_true"); args=ap.parse_args()
    screen, final, checkpoint=ROOT/args.screening_output, ROOT/args.output, ROOT/args.checkpoint_output
    if sum((args.replay_to_checkpoint,args.finalize_checkpoint,args.preflight)) != 1: raise RuntimeError("choose exactly one of --replay-to-checkpoint, --finalize-checkpoint, --preflight")
    if os.environ.get("BJ167_TEST_FORBID_OUTCOME_SUPPORT") == "1":
        def forbidden(*_args, **_kwargs): raise RuntimeError("test guard: finalizer opened outcome/support path")
        R.load_outcomes=forbidden; R.build_supports=forbidden
    if not (screen/"SHA256SUMS.json").exists(): raise RuntimeError("completed immutable screen required")
    sums=json.loads((screen/"SHA256SUMS.json").read_text())
    for name,digest in sums.items():
        if R.sha(screen/name)!=digest: raise RuntimeError(f"screening payload drift: {name}")
    if args.preflight:
        selectors,selector_idx,*_=R.load_surface()
        mapping,_addresses=candidate_science_mapping(screen,selectors,selector_idx,science_cells())
        issue_count=sum(1 for _ in csv.DictReader((screen/"issue_order.csv").open(newline="")))
        print(json.dumps({"contract":CHECKPOINT_CONTRACT,"mode":"PREFLIGHT_ONLY_NO_TICKET_REPLAY","candidate_count":len(mapping),"science_cells_per_selector":CELLS_PER_SELECTOR,"selector_count":len(selectors),"issue_count":issue_count,"candidate_issue_array_rows":len(mapping)*issue_count,"candidate_issue_array_bytes":len(mapping)*issue_count*11*8,"scientific_aggregate_checkpoint":"required for --finalize-checkpoint","screen_manifest_sha256":R.sha(screen/"SHA256SUMS.json")},sort_keys=True),flush=True)
        return
    if args.replay_to_checkpoint:
        execution_start=execution_snapshot()
        order_rows=list(csv.DictReader((screen/"issue_order.csv").open(newline="")))
        issues=[r["issue_instance"] for r in order_rows]; meta={r["issue_instance"]:r for r in order_rows}; nissue=len(issues)
        years=sorted({meta[x]["year"] for x in issues}); folds=sorted({meta[x]["fold"] for x in issues}); year_i={x:i for i,x in enumerate(years)}; fold_i={x:i for i,x in enumerate(folds)}
        R.verify_ga(); outcomes=R.load_outcomes(); selectors,selector_idx,*_=R.load_surface(); supports,by_issue,_,_=R.build_supports(outcomes,selector_idx)
        with (R.GA/"selector_census.csv").open(newline="") as f: census=list(csv.DictReader(f))
        R.build_policy_status(census,supports,selector_idx)
        if set(issues)!=set(by_issue): raise RuntimeError("screening and canonical issue universes differ")
        cells=science_cells(); ncell=len(cells); total=len(selectors)*ncell
        frozen_mapping,candidate_addresses=candidate_science_mapping(screen,selectors,selector_idx,cells)
        zeros=lambda:array.array("d",[0.0])*total
        tmp=[zeros() for _ in range(6)]; allv=[zeros() for _ in range(7)]
        mark=array.array("B",[0])*total; touched=array.array("i",[0])*total
        cumulative=zeros(); peak=zeros(); drawdown=zeros(); miss=array.array("i",[0])*total; longest_miss=array.array("i",[0])*total
        yn=array.array("d",[0.0])*(total*len(years)); ys=array.array("d",[0.0])*(total*len(years)); fn=array.array("d",[0.0])*(total*len(folds)); fs=array.array("d",[0.0])*(total*len(folds))
        largest=array.array("d",[-math.inf])*total; largest_stake=zeros(); largest_issue=array.array("i",[-1])*total
        full_issue_net=array.array("d",[0.0])*(len(selectors)*nissue); full_issue_stake=array.array("d",[0.0])*(len(selectors)*nissue)
        candidate_values={name:array.array("d",[0.0])*(len(frozen_mapping)*nissue) for name in ("net","stake","gross","tax","hit","tax_line_hit","full_net","full_stake","full_gross","full_tax","full_hit")}
        lib=configure(); pd=ctypes.c_double; pi=ctypes.c_int
        lib.bj167_scientific_set_buffers(*(R.ptr(x,pd) for x in tmp),R.ptr(mark,ctypes.c_ubyte),R.ptr(touched,pi),*(R.ptr(x,pd) for x in allv),R.ptr(cumulative,pd),R.ptr(peak,pd),R.ptr(drawdown,pd),R.ptr(miss,pi),R.ptr(longest_miss,pi),R.ptr(yn,pd),R.ptr(ys,pd),R.ptr(fn,pd),R.ptr(fs,pd),R.ptr(largest,pd),R.ptr(largest_stake,pd),R.ptr(largest_issue,pi),R.ptr(full_issue_net,pd),R.ptr(full_issue_stake,pd),len(years),len(folds),nissue)
        lib.bj167_scientific_set_candidate_issue_buffers(R.ptr(candidate_addresses,pi),len(frozen_mapping),*(R.ptr(candidate_values[name],pd) for name in ("net","stake","gross","tax","hit","tax_line_hit","full_net","full_stake","full_gross","full_tax","full_hit")))
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
            if (ii+1)%10==0: print(f"scientific replay issues {ii+1}/{nissue}",flush=True)
        execution_end=execution_snapshot()
        write_candidate_checkpoint(checkpoint,screen,frozen_mapping,order_rows,selectors,cells,candidate_values,scientific_checkpoint_values(allv,cumulative,peak,drawdown,miss,longest_miss,yn,ys,fn,fs,largest,largest_stake,largest_issue,full_issue_net,full_issue_stake,total,len(years),len(folds),len(selectors),nissue),execution_start,execution_end)
        print(f"WROTE CHECKPOINT {checkpoint}",flush=True); return
    # Finalization is intentionally disk-only: it must not open outcomes,
    # construct supports, or invoke any ticket allocator after replay success.
    execution_start=execution_snapshot()
    checkpoint_meta,_checkpoint_mapping,order_rows,selectors,cells,_checkpoint_candidates,checkpoint_saved=verify_candidate_checkpoint(checkpoint,screen)
    if final.exists(): raise RuntimeError("refusing to replace immutable stability companion")
    stage=unique_stage(final); out=stage
    issues=[r["issue_instance"] for r in order_rows]; meta={r["issue_instance"]:r for r in order_rows}; nissue=len(issues)
    years=sorted({meta[x]["year"] for x in issues}); folds=sorted({meta[x]["fold"] for x in issues}); year_i={x:i for i,x in enumerate(years)}; fold_i={x:i for i,x in enumerate(folds)}
    year_issue_count={name: sum(meta[x]["year"] == name for x in issues) for name in years}
    fold_issue_count={name: sum(meta[x]["fold"] == name for x in issues) for name in folds}
    ncell=len(cells); total=len(selectors)*ncell
    if ncell != CELLS_PER_SELECTOR: raise RuntimeError("checkpoint scientific cell layout drift")
    required=[*(f"allv_{i}" for i in range(7)),"cumulative","peak","drawdown","miss","longest_miss","year_net","year_stake","fold_net","fold_stake","largest","largest_stake","largest_issue","full_issue_net","full_issue_stake"]
    if set(required)!=set(checkpoint_saved): raise RuntimeError("shared checkpoint scientific aggregate schema drift")
    allv=[checkpoint_saved[f"allv_{i}"] for i in range(7)]; cumulative=checkpoint_saved["cumulative"]; peak=checkpoint_saved["peak"]; drawdown=checkpoint_saved["drawdown"]; miss=checkpoint_saved["miss"]; longest_miss=checkpoint_saved["longest_miss"]; yn=checkpoint_saved["year_net"]; ys=checkpoint_saved["year_stake"]; fn=checkpoint_saved["fold_net"]; fs=checkpoint_saved["fold_stake"]; largest=checkpoint_saved["largest"]; largest_stake=checkpoint_saved["largest_stake"]; largest_issue=checkpoint_saved["largest_issue"]; full_issue_net=checkpoint_saved["full_issue_net"]; full_issue_stake=checkpoint_saved["full_issue_stake"]
    # The scalar summary is the keyed all-cell coverage census.  Slices below
    # are derived from exact cell/year/fold totals, never seed pseudo-history.
    fields=["global_science_cell","selector_id","weight_source","mechanism","cap","M","seed_scope","coverage_scope","coverage_status","no_tax_roi","matched_full_no_tax_roi","paired_lift","ex_largest_issue_no_tax_roi","ex_largest_issue_full_roi","ex_largest_issue_lift","ex_largest_year_no_tax_roi","ex_largest_year_full_roi","ex_largest_year_lift","largest_signed_issue","largest_signed_issue_net_yuan","largest_signed_year","gross_issue_hhi","gross_top_issue_share","drawdown_no_tax_yuan","longest_miss_streak","year_slice_count","fold_slice_count","loyo_slice_count"]
    def summary_emit(w):
        for si,sel in enumerate(selectors):
            full_at=si*ncell+960; fnet,fstake=allv[0][full_at],allv[1][full_at]
            for ci,(src,me,cap,m,scope) in enumerate(cells):
                report_m=reporting_science_cell((src,me,cap,m,scope))[3]
                at=si*ncell+ci; net,stake=allv[0][at],allv[1][at]; roi=net/stake if stake else None; froi=fnet/fstake if fstake else None; lift=roi-froi if roi is not None and froi is not None else None
                no_bet = stake == 0.0
                li=largest_issue[at] if not no_bet else -1; ex_stake=stake-(largest_stake[at] if li>=0 else 0); ex_net=net-(largest[at] if li>=0 else 0); fex_net=fnet-(full_issue_net[si*nissue+li] if li>=0 else 0); fex_stake=fstake-(full_issue_stake[si*nissue+li] if li>=0 else 0); exroi=ex_net/ex_stake if ex_stake else None; fexroi=fex_net/fex_stake if fex_stake else None
                byyear=[(yn[at*len(years)+yi],ys[at*len(years)+yi]) for yi in range(len(years))]
                ly=max(range(len(years)),key=lambda yi:byyear[yi][0]) if not no_bet else -1
                ynet=net-byyear[ly][0] if ly>=0 else 0.0; ystake=stake-byyear[ly][1] if ly>=0 else 0.0; fy_net=fnet-yn[full_at*len(years)+ly] if ly>=0 else 0.0; fy_stake=fstake-ys[full_at*len(years)+ly] if ly>=0 else 0.0; yroi=ynet/ystake if ystake else None; fyroi=fy_net/fy_stake if fy_stake else None
                gross=allv[2][at]; hhi=allv[5][at]/(gross*gross) if gross else 0.0; top=allv[6][at]/gross if gross else 0.0
                w.writerow({"global_science_cell":at,"selector_id":sel["selector_id"],"weight_source":src,"mechanism":me,"cap":cap,"M":report_m,"seed_scope":scope,"coverage_scope":"ALL_ATLAS_SCIENTIFIC_CELLS","coverage_status":"NO_BET_ZERO_STAKE" if no_bet else "EXACT_YEAR_FOLD_LOYO_AND_EXCLUSIONS","no_tax_roi":"" if roi is None else f"{roi:.12f}","matched_full_no_tax_roi":"" if froi is None else f"{froi:.12f}","paired_lift":"" if lift is None else f"{lift:.12f}","ex_largest_issue_no_tax_roi":"" if exroi is None else f"{exroi:.12f}","ex_largest_issue_full_roi":"" if fexroi is None else f"{fexroi:.12f}","ex_largest_issue_lift":"" if exroi is None or fexroi is None else f"{exroi-fexroi:.12f}","ex_largest_year_no_tax_roi":"" if yroi is None else f"{yroi:.12f}","ex_largest_year_full_roi":"" if fyroi is None else f"{fyroi:.12f}","ex_largest_year_lift":"" if yroi is None or fyroi is None else f"{yroi-fyroi:.12f}","largest_signed_issue":issues[li] if li>=0 else "","largest_signed_issue_net_yuan":"" if li<0 else f"{largest[at]:.6f}","largest_signed_year":years[ly] if ly>=0 else "","gross_issue_hhi":"" if no_bet else f"{hhi:.12f}","gross_top_issue_share":"" if no_bet else f"{top:.12f}","drawdown_no_tax_yuan":"" if no_bet else f"{drawdown[at]:.6f}","longest_miss_streak":"" if no_bet else longest_miss[at],"year_slice_count":len(years),"fold_slice_count":len(folds),"loyo_slice_count":len(years)})
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
                report_m=reporting_science_cell((src,me,cap,m,scope))[3]
                at=si*ncell+ci
                for typ,names,nets,stakes,subtract in (("YEAR",years,yn,ys,False),("FOLD",folds,fn,fs,False),("LOYO",years,yn,ys,True)):
                    count=len(years) if typ!="FOLD" else len(folds)
                    for k,name in enumerate(names):
                        net,stake=nets[at*count+k],stakes[at*count+k]; fnet,fstake=nets[full_at*count+k],stakes[full_at*count+k]
                        if subtract: net,stake=allv[0][at]-net,allv[1][at]-stake; fnet,fstake=allv[0][full_at]-fnet,allv[1][full_at]-fstake
                        roi=net/stake if stake else None; froi=fnet/fstake if fstake else None
                        included = retained_issue_count(typ,name,nissue,year_issue_count,fold_issue_count)
                        w.writerow({"global_science_cell":at,"selector_id":sel["selector_id"],"weight_source":src,"mechanism":me,"cap":cap,"M":report_m,"seed_scope":scope,"coverage_scope":"ALL_ATLAS_SCIENTIFIC_CELLS","slice_type":typ,"slice":name,"retained_issue_count":included,"candidate_no_tax_roi":"" if roi is None else f"{roi:.12f}","matched_full_no_tax_roi":"" if froi is None else f"{froi:.12f}","paired_lift":"" if roi is None or froi is None else f"{roi-froi:.12f}"})
    write_gz(out/"chart_source_chronology_slices_all_scientific.csv.gz",slice_fields,slice_emit)
    # Gate-A requires exact M2187 reconciliation versus selector-matched FULL.
    rec_fields=["selector_id","weight_source","mechanism","M","seed_scope","candidate_scale","normalized_candidate_stake_yuan","matched_full_stake_yuan","stake_difference_yuan","normalized_candidate_gross_yuan","matched_full_gross_yuan","gross_difference_yuan","normalized_candidate_net_yuan","matched_full_net_yuan","net_difference_yuan","reconciliation_status"]
    with (out/"m2187_full_reconciliation.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rec_fields);w.writeheader()
        for si,sel in enumerate(selectors):
            full_at=si*ncell+960
            sources=list(dict.fromkeys(cell[0] for cell in cells if cell[0] != "NA"))
            for src_i,src in enumerate(sources):
                for local,me,scale in ((src_i*160+20+19,"WOR_DISTINCT",100),(src_i*160+140+19,"DETERMINISTIC_TOP_MASS",1)):
                    at=si*ncell+local; vals=[allv[j][at]/scale for j in range(3)]; full=[allv[j][full_at] for j in range(3)]; dif=[vals[j]-full[j] for j in range(3)]
                    ok=all(abs(x)<1e-6 for x in dif)
                    w.writerow({"selector_id":sel["selector_id"],"weight_source":src,"mechanism":me,"M":2187,"seed_scope":"ENSEMBLE_100" if scale==100 else "DETERMINISTIC","candidate_scale":scale,"normalized_candidate_stake_yuan":f"{vals[1]:.6f}","matched_full_stake_yuan":f"{full[1]:.6f}","stake_difference_yuan":f"{dif[1]:.6f}","normalized_candidate_gross_yuan":f"{vals[2]:.6f}","matched_full_gross_yuan":f"{full[2]:.6f}","gross_difference_yuan":f"{dif[2]:.6f}","normalized_candidate_net_yuan":f"{vals[0]:.6f}","matched_full_net_yuan":f"{full[0]:.6f}","net_difference_yuan":f"{dif[0]:.6f}","reconciliation_status":"EXACT_EQUIVALENT" if ok else "FAIL"})
                    if not ok: raise RuntimeError(f"M2187 reconciliation drift {sel['selector_id']} {src} {me}")
    coverage={"contract":"bj167-gate-b-v3r1-scientific-stability","scientific_cell_count":total,"selector_count":len(selectors),"science_cells_per_selector":ncell,"stochastic_unit":"100-seed pooled ensemble","deterministic_unit":"one arm","year_count":len(years),"fold_count":len(folds),"screen_reconciliation":"scientific_screen_reconciliation.csv.gz exact PASS required","coverage":"all scientific cells receive YEAR/FOLD/LOYO, signed-largest issue/year, paired selector FULL exclusions, pooled HHI/top share/drawdown/miss streak"}
    (out/"scientific_stability_coverage.json").write_text(json.dumps(coverage,sort_keys=True,indent=2)+"\n")
    execution_end=execution_snapshot()
    write_execution_provenance(out,screen,execution_start,execution_end,checkpoint)
    R.write_file_census(out);R.finalize_package_identity(out,"bj167-gate-b-v3r1-scientific-stability",{"screening_manifest_sha256":R.sha(screen/"SHA256SUMS.json"),"screening_content_identity_sha256":R.sha(screen/"CONTENT_IDENTITY.json"),"shared_science_checkpoint_manifest_sha256":R.sha(checkpoint/"SHA256SUMS.json"),"scientific_finalizer_head":execution_start["git_head"],"scientific_finalizer_runner_sha256":execution_start["runner_sha256"],"scientific_finalizer_native_wrapper_sha256":execution_start["native_wrapper_sha256"],"allocator_sha256":R.EXPECTED_ALLOCATOR_SHA256,"scientific_cell_count":total});R.atomic_publish(stage,final);print(f"WROTE {final}",flush=True)

if __name__=="__main__": main()
