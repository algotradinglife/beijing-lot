"""Small output-builder contract fixture; never invokes the full atlas."""
from __future__ import annotations
import array, csv, gzip, hashlib, json, os, shutil, importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
FIXTURE=ROOT/".scratch"/"bj167_output_builder_fixture"
spec=importlib.util.spec_from_file_location("bj167_runner_fixture",ROOT/"scripts"/"settle_bj167_strategy_atlas_gate_b_exact.py"); RUNNER=importlib.util.module_from_spec(spec); spec.loader.exec_module(RUNNER)

def gz(path, rows, fields):
    with gzip.GzipFile(filename=str(path),mode="wb",mtime=0) as gf, __import__("io").TextIOWrapper(gf,newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)

def roi(net,stake): return "" if stake==0 else f"{net/stake:.12f}"

def test_small_output_builder_fixture():
    if FIXTURE.exists(): shutil.rmtree(FIXTURE)
    stage=Path(str(FIXTURE)+".stage")
    if stage.exists(): shutil.rmtree(stage)
    stage.mkdir(parents=True)
    fields=["selector_id","weight_source","mechanism","cap","M","seed","stake_yuan","gross_pre_tax_yuan","no_tax_roi","matched_full_no_tax_roi","matched_full_lift","tax_yuan","coverage_hits","identity_count","hit_ticket_count","unique_ticket_count","duplicate_ticket_count","gross_issue_hhi","gross_top_issue_share","drawdown_no_tax_yuan","longest_miss_streak","global_cell"]
    rows=[]
    for i in range(100):
        rows.append(dict(selector_id="S0",weight_source="Q_WEIGHT",mechanism="WOR_DISTINCT",cap="NA",M="64",seed=f"137{i+1:03d}",global_cell="",stake_yuan="4",gross_pre_tax_yuan="8" if i<50 else "0",no_tax_roi="",matched_full_no_tax_roi="-0.500000000000",matched_full_lift="",tax_yuan="0",coverage_hits="1",identity_count="1",hit_ticket_count="1" if i<50 else "0",unique_ticket_count="2",duplicate_ticket_count="0",gross_issue_hhi="1",gross_top_issue_share="1",drawdown_no_tax_yuan="2",longest_miss_streak="1"))
    rows += [dict(selector_id="S0",weight_source="Q_WEIGHT",mechanism="CAPPED_REPEAT",cap="1",M="64",seed="NA",global_cell="123",stake_yuan="0",gross_pre_tax_yuan="0",no_tax_roi="",matched_full_no_tax_roi="-0.500000000000",matched_full_lift="",tax_yuan="0",coverage_hits="0",identity_count="0",hit_ticket_count="0",unique_ticket_count="0",duplicate_ticket_count="0",gross_issue_hhi="0",gross_top_issue_share="0",drawdown_no_tax_yuan="0",longest_miss_streak="0"),dict(selector_id="S0",weight_source="NA",mechanism="FULL_ENUMERATED",cap="NA",M="2187",seed="NA",global_cell="456",stake_yuan="8",gross_pre_tax_yuan="4",no_tax_roi="-0.5",matched_full_no_tax_roi="-0.500000000000",matched_full_lift="0",tax_yuan="0",coverage_hits="1",identity_count="1",hit_ticket_count="1",unique_ticket_count="1",duplicate_ticket_count="0",gross_issue_hhi="1",gross_top_issue_share="1",drawdown_no_tax_yuan="1",longest_miss_streak="0")]
    gz(stage/"cell_metrics-000.csv.gz",rows,fields)
    # Ensemble grouping is pooled monetary accounting; zero stake stays blank.
    stochastic=rows[:100]; aggregate=RUNNER.aggregate_ensemble_group(stochastic,8.0)
    assert aggregate["seed_scope"]=="ENSEMBLE_100" and aggregate["no_tax_roi"]=="0.000000000000"
    zero=RUNNER.aggregate_ensemble_group([rows[100]],8.0); assert zero["no_tax_roi"]=="" and zero["global_cell"]=="123"
    assert roi(0,0)==""
    # Exercise the exact production helpers for the shared draw matrix and
    # raw/robust chart-source table, rather than reproducing miniature logic.
    draws,digest=RUNNER.write_common_draw_matrix(stage/"bootstrap_draw_matrix.json",3,4,seed=167137)
    assert json.loads((stage/"bootstrap_draw_matrix.json").read_text())["sha256"]==digest
    raw=stage/"raw_pareto_front.csv"; raw.write_text("selector_id,weight_source,mechanism,cap,M,seed,seed_scope,no_tax_roi,matched_full_lift,seed_mean_drawdown_no_tax_yuan,seed_gross_weighted_mean_issue_hhi,global_cell,front_definition\nS0,Q_WEIGHT,CAPPED_REPEAT,1,64,ENSEMBLE_100,ENSEMBLE_100,0.1,0.2,1.0,0.3,5,fixture\n")
    robust=stage/"robust_pareto_front.csv"; robust.write_text("selector_id,weight_source,mechanism,cap,M,seed,bootstrap_ci95_low,ex_largest_issue_no_tax_roi,ex_largest_year_no_tax_roi,ex_largest_year,drawdown_no_tax_yuan,gross_issue_hhi,global_cell,target_role,front_definition\nS0,Q_WEIGHT,CAPPED_REPEAT,1,64,ENSEMBLE_100,0.01,0.02,0.03,2024,1.0,0.3,5,fixture,fixture\n")
    RUNNER.write_chart_source_pareto(stage/"chart_source_pareto.csv",raw,robust)
    chart=stage/"chart_source_pareto.csv"; assert "Q_WEIGHT" in chart.read_text() and ",1,64," in chart.read_text()
    assert RUNNER.robust_dominates((.2,.1,.1,1,.1),(.1,.1,0,2,.2))
    # Atomic publication: final path is absent until all staged files/hash are
    # complete, then one explicit rename exposes the package.
    RUNNER.finalize_package_identity(stage,"fixture-v1",{"fixture":True,"sqlite_used":False})
    assert not FIXTURE.exists(); RUNNER.atomic_publish(stage,FIXTURE); assert FIXTURE.exists()
    assert hashlib.sha256((FIXTURE/"SHA256SUMS.json").read_bytes()).hexdigest()
    shutil.rmtree(FIXTURE)
