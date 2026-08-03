#!/usr/bin/env python3
"""Finalize a completed #145 Gate-B SQLite stage without rereading outcomes."""
from __future__ import annotations
import argparse, csv, ctypes, hashlib, importlib.util, json, os, shutil, sqlite3, subprocess, sys, tempfile, gzip
from pathlib import Path
from decimal import Decimal

SPEC = importlib.util.spec_from_file_location("bj145_settle", Path(__file__).with_name("settle_bj145_ticket_allocation_gate_b.py"))
MOD = importlib.util.module_from_spec(SPEC); sys.modules["bj145_settle"] = MOD; SPEC.loader.exec_module(MOD)

BOOT_FIELDS = MOD.BOOTSTRAP_FIELDS
MC_FIELDS = MOD.MC_FIELDS

def load_rows(conn, key):
    """Load one frozen configuration through the indexed config key."""
    if len(key) != 7:
        raise RuntimeError(f"configuration key must include sampling_role: {key!r}")
    config = "|".join(str(part) for part in key)
    rows = [json.loads(v[0]) for v in conn.execute(
        "SELECT payload FROM issue_rows WHERE config=? ORDER BY year,issue_instance",
        (config,))]
    if len(rows) != 348: raise RuntimeError((key, len(rows)))
    return rows

def load_fast():
    source = Path(MOD.__file__).with_name("bj145_fast_alloc.cpp")
    so = MOD.ROOT / ".scratch" / "bj145_fast_alloc.so"
    if not so.exists() or so.stat().st_mtime < source.stat().st_mtime:
        subprocess.run(["g++","-O3","-std=c++17","-shared","-fPIC",str(source),"-o",str(so)],check=True)
    lib=ctypes.CDLL(str(so)); lib.bj145_bootstrap.argtypes=[ctypes.POINTER(ctypes.c_double)]*4+[ctypes.c_int,ctypes.c_int,ctypes.c_uint64,ctypes.POINTER(ctypes.c_double)]
    lib.bj145_bootstrap.restype=None; return lib

def boot(lib, candidate, baseline, field, token):
    pairs=[(a,b) for a,b in zip(candidate,baseline) if float(a["planned_stake_yuan"])>0 and float(b["planned_stake_yuan"])>0]
    if not pairs: return (0,None,None,None,None,None)
    cn=(ctypes.c_double*len(pairs))(*[float(a[field]) for a,b in pairs]); cs=(ctypes.c_double*len(pairs))(*[float(a["planned_stake_yuan"]) for a,b in pairs])
    bn=(ctypes.c_double*len(pairs))(*[float(b[field]) for a,b in pairs]); bs=(ctypes.c_double*len(pairs))(*[float(b["planned_stake_yuan"]) for a,b in pairs]); out=(ctypes.c_double*5)()
    seed=int.from_bytes(hashlib.sha256(token.encode()).digest()[:8],"big")
    lib.bj145_bootstrap(cn,cs,bn,bs,len(pairs),MOD.BOOTSTRAP_REPLICATES,seed,out)
    return (len(pairs),*out)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("stage",type=Path); ap.add_argument("--output",type=Path,default=MOD.ROOT/"results"/"bj145_gate_b_outcome_settlement_v1"); args=ap.parse_args()
    stage=args.stage.resolve(); output=args.output.resolve()
    if output.exists(): raise RuntimeError(f"immutable output exists: {output}")
    conn=sqlite3.connect(stage/"issue_allocation_index.sqlite")
    if conn.execute("SELECT count(*) FROM issue_rows").fetchone()[0] != 1006416: raise RuntimeError("issue-row denominator")
    final=Path(tempfile.mkdtemp(prefix=".bj145_final_",dir=output.parent)); output.parent.mkdir(parents=True,exist_ok=True)
    try:
        names=("issue_allocation_settlement.csv.gz","winning_ticket_tax_ledger.csv.gz","mechanism_weight_surface_summary.csv","full_control_deltas.csv","mechanism_pairwise_deltas.csv","weight_pairwise_deltas.csv")
        for name in names: shutil.copy2(stage/name,final/name)
        # The code-frequency table is large but highly compressible.  Keep it
        # as a deterministic gzip payload so no individual GitHub artifact
        # exceeds the repository's file-size limit.
        with (stage/"outcome_code_frequency.csv").open("rb") as source, (final/"outcome_code_frequency.csv.gz").open("wb") as raw:
            target=gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0)
            try:
                shutil.copyfileobj(source, target)
            finally:
                target.close()
        with (final/"mechanism_weight_surface_summary.csv").open(newline="",encoding="utf-8") as h: summaries=list(csv.DictReader(h))
        with (final/"full_control_deltas.csv").open(newline="",encoding="utf-8") as h: full=list(csv.DictReader(h))
        lib=load_fast(); boot_rows=[]; mc_rows=[]
        baseline_cache={}
        for row in full:
            if row["scope"]!="ALL" or not row["no_tax_roi"]: continue
            ck=(row["arm_id"],row["weight_source"],row["mechanism"],row["sampling_role"],row["cap"],str(row["M"]),row["seed"])
            bk=(row["arm_id"],row["weight_source"],"FULL_ENUMERATED","FULL_CONTROL","NA",str(MOD.FULL_TICKETS),"NA")
            cand=load_rows(conn,ck); base=baseline_cache.setdefault(bk,load_rows(conn,bk))
            for field,metric in (("pre_tax_net_yuan","no_tax_roi_delta"),("tax_adjusted_net_yuan","tax_adjusted_roi_delta")):
                result=boot(lib,cand,base,field,f"{MOD.CONTRACT}|BOOTSTRAP|{field}|{ck}")
                boot_rows.append({"comparison":"VS_FULL","scope":"ALL","scope_value":"ALL","arm_id":row["arm_id"],"weight_source":row["weight_source"],"mechanism":row["mechanism"],"cap":row["cap"],"M":row["M"],"seed":row["seed"],"baseline_mechanism":"FULL_ENUMERATED","baseline_cap":"NA","baseline_seed":"NA","metric":metric,"support_issue_count":result[0],"replicates":MOD.BOOTSTRAP_REPLICATES,"point_estimate":MOD.ratio(result[1]),"ci95_low":MOD.ratio(result[2]),"ci95_high":MOD.ratio(result[3]),"one_sided_positive_p":MOD.ratio(result[4]),"two_sided_sign_p":MOD.ratio(result[5])})
            vals=[Decimal(a["no_tax_roi"])-Decimal(b["no_tax_roi"]) for a,b in zip(cand,base) if a["planned_stake_yuan"]!="0.000000" and b["planned_stake_yuan"]!="0.000000"]
            raw,pos,neg,zero=MOD.p_sign(vals)
            mc_rows.append({"family":"ALL_FULL_NO_TAX_ROI","family_count":"","comparison":"VS_FULL","arm_id":row["arm_id"],"weight_source":row["weight_source"],"mechanism":row["mechanism"],"cap":row["cap"],"M":row["M"],"seed":row["seed"],"raw_p":raw,"holm_rank":"","holm_p":"","positive_issue_count":pos,"negative_issue_count":neg,"zero_issue_count":zero,"support_issue_count":len(vals),"multiplicity_rule":"two-sided paired issue sign test; Holm-Bonferroni over complete ALL-scope surface"})
        MOD.holm(mc_rows,"ALL_FULL_NO_TAX_ROI")
        MOD.write_csv(final/"issue_bootstrap.csv",BOOT_FIELDS,boot_rows); MOD.write_csv(final/"multiple_comparison.csv",MC_FIELDS,mc_rows)
        # Tax reconciliation is streamed from the two immutable ledgers; no
        # issue-level JSON payload matrix is retained in memory.
        ledger={}
        with gzip.open(final/"winning_ticket_tax_ledger.csv.gz","rt",newline="",encoding="utf-8") as h:
            for r in csv.DictReader(h):
                k=(r["arm_id"],r["weight_source"],r["mechanism"],r["sampling_role"],r["cap"],r["M"],r["seed"]); ledger[k]=ledger.get(k,Decimal(0))+Decimal(r["tax_yuan"])
        audit=[]
        all_tax_configs = [tuple(str(v) for v in row) for row in conn.execute(
            "SELECT DISTINCT arm_id,weight_source,mechanism,sampling_role,cap,m_value,seed FROM issue_rows ORDER BY arm_id,weight_source,mechanism,sampling_role,cap,m_value,seed"
        )]
        for k in all_tax_configs:
            expected=ledger.get(k, Decimal(0)); arm,w,m,role,c,mv,s=k; config="|".join(k); actual=Decimal(str(conn.execute("SELECT coalesce(sum(cast(json_extract(payload,'$.tax_yuan') as real)),0) FROM issue_rows WHERE config=?",(config,)).fetchone()[0])).quantize(MOD.MONEY_QUANTUM)
            audit.append({"arm_id":arm,"weight_source":w,"mechanism":m,"sampling_role":role,"cap":c,"M":mv,"seed":s,"ledger_tax_yuan":MOD.money(expected),"issue_tax_yuan":MOD.money(actual),"delta_yuan":MOD.money(actual-expected),"status":"PASS" if abs(actual-expected)<=MOD.MONEY_QUANTUM else "FAIL"})
        MOD.write_csv(final/"tax_reconciliation.csv",tuple(audit[0]) if audit else ("status",),audit)
        with (final/"source_census.csv").open("w",newline="",encoding="utf-8") as h:
            w=csv.DictWriter(h,fieldnames=MOD.SOURCE_FIELDS,lineterminator="\n"); w.writeheader(); w.writerows([
                {"source":"bj145_gate_a_preoutcome_v8","role":"immutable allocation freeze","identity":"SHA256SUMS.json","sha256":MOD.GATE_A_MANIFEST,"rows":1006416,"join_status":"verified before outcome read"},
                {"source":"bj95_gate_b_outcome_settlement_v2r8","role":"canonical trusted final-SP/result join","identity":"canonical_outcome_join.csv","sha256":MOD.OUTCOME_PAYLOAD,"rows":len(MOD.load_outcomes()),"join_status":"trusted complete issue settlement; incomplete zero stake"},
            ])
        top=sorted((r for r in full if r["scope"]=="ALL" and r["no_tax_roi_delta"]),key=lambda r:float(r["no_tax_roi_delta"]),reverse=True)[:20]
        decision={"decision":"DESCRIPTIVE_SURFACE_ONLY_NO_PROMOTION","promotion_authorized":False,"primary_metric":"pre-tax no_tax_roi including 0.65 BJ Single Match factor","tax_secondary":"individual winning ticket tax; no pooling","positive_same_window_rule":"descriptive only; strict independent EV and held-out/forward validation required","top_pre_tax_full_deltas":top,"negative_control":"No purchase, production, betting or promotion authority"}
        (final/"decision.json").write_text(json.dumps(decision,indent=2,sort_keys=True)+"\n")
        settlement_card={
            "issue": 145,
            "contract": MOD.CONTRACT,
            "version": "bj145-gate-b-v1-outcome-settlement",
            "gate_a_manifest_sha256": MOD.GATE_A_MANIFEST,
            "outcome_manifest_sha256": MOD.OUTCOME_MANIFEST,
            "outcome_payload_sha256": MOD.OUTCOME_PAYLOAD,
            "source_manifests_transitive": {
                "bj137": MOD.SOURCE_137_MANIFEST, "bj148": MOD.SOURCE_148_MANIFEST,
                "bj151": MOD.SOURCE_151_MANIFEST, "bj154": MOD.SOURCE_154_MANIFEST,
            },
            "surface": {"issue_rows": 1006416, "configuration_count": 2892,
                        "summary_rows": len(summaries), "full_control_delta_rows": len(full),
                        "bootstrap_rows": len(boot_rows), "holm_rows": len(mc_rows),
                        "tax_reconciliation_rows": len(audit)},
            "primary_arm": "PRIMARY_NO_GATE_K4",
            "secondary_arm": "SECONDARY_ESP300_GM290_K8",
            "m_grid": list(range(16,257,16)) + [512,1024,1458,2187],
            "tax_rule": "20pct if each individual winning ticket gross >= 10000 yuan; no pooling or aggregation",
            "settlement_scope": "all frozen issue/configuration rows; unavailable outcomes remain zero-stake and are not imputed",
            "decision": decision["decision"],
            "promotion_authorized": False,
        }
        (final/"settlement_card.json").write_text(json.dumps(settlement_card,indent=2,sort_keys=True)+"\n")
        (final/"report.md").write_text("\n".join(["# #145 Gate B — calibrated ticket allocation settlement","",f"Gate-A manifest `{MOD.GATE_A_MANIFEST}`; canonical outcome manifest `{MOD.OUTCOME_MANIFEST}` / payload `{MOD.OUTCOME_PAYLOAD}`.","","The complete mechanism × weight × M/cap/seed surface is retained. Pre-tax `no_tax_roi` is primary; individual-ticket tax is secondary and never pooled. Tax reconciliation covers every frozen configuration, including zero-winning-ticket configurations.","","This historical settlement is descriptive only. Positive same-window surfaces are not promotion evidence; strict independent EV and held-out/forward validation are required. No purchase, production, betting, or promotion authority.",""]) + "\n")
        for name in ("allocation_binding.json", "m_grid.csv", "mechanism_contract.csv", "gate_a_card.json", "allocation_golden_vectors.json"):
            shutil.copy2(MOD.GATE_A / name, final / name)
        shutil.copy2(MOD.__file__,final/"settlement_runner.py"); shutil.copy2(MOD.GATE_A/"bj145_allocation_engine.py",final/"bj145_allocation_engine.py"); shutil.copy2(Path(MOD.__file__).with_name("bj145_fast_alloc.cpp"),final/"bj145_fast_alloc.cpp")
        compressed=("issue_allocation_settlement.csv.gz","winning_ticket_tax_ledger.csv.gz","outcome_code_frequency.csv.gz")
        ident={"contract_version":"bj145-gate-b-portable-content-v1","gzip_payloads":{n:{"canonical_decompressed_sha256":MOD.decompressed_digest(final/n)[0],"canonical_decompressed_bytes":MOD.decompressed_digest(final/n)[1]} for n in compressed},"non_compressed_controls":{p.name:MOD.sha256(p) for p in sorted(final.iterdir()) if p.is_file() and p.name not in compressed}}
        (final/"CONTENT_IDENTITY.json").write_text(json.dumps(ident,indent=2,sort_keys=True)+"\n"); manifest={p.name:MOD.sha256(p) for p in sorted(final.iterdir()) if p.is_file()}; (final/"SHA256SUMS.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
        os.replace(final,output); print(json.dumps({"output":str(output),"manifest_sha256":MOD.sha256(output/"SHA256SUMS.json"),"issue_rows":1006416,"configs":2892,"decision":decision["decision"]},sort_keys=True))
    except Exception:
        shutil.rmtree(final,ignore_errors=True); raise
    finally: conn.close()

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("stage",type=Path); ap.add_argument("--output",type=Path,required=True); x=ap.parse_args(); sys.argv=[sys.argv[0],str(x.stage),"--output",str(x.output)]; main()
