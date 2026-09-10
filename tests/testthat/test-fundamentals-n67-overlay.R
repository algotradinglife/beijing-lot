source('../../r/fundamentals_n7_baseline.R')
source('../../r/fundamentals_n67_overlay.R')
testthat::test_that('overlay R interfaces preserve NO_BET, pending cash and common arms', {
  root <- normalizePath('../..');p <- tempfile();dir.create(p)
  for(f in c('python_bridge','fundamentals_returns','nowscore_query')) source(file.path(root,'r',paste0(f,'.R')))
  source('helper-nowscore-query.R')
  py <- Sys.getenv('FUNDAMENTALS_PYTHON',unset=Sys.getenv('RETICULATE_PYTHON'))
  module <- project_python_module('src.fundamentals_n67_overlay',root,py,FALSE)
  main <- reticulate::import_main(convert=FALSE);main$overlay_fixture_dir <- p;main$overlay_fixture_root <- root
  reticulate::py_run_string(paste(
    "import json,pandas as pd",
    "from pathlib import Path",
    "from src.temporal_learning import Cutoff",
    "from src.temporal_learning.provenance import implementation_closure",
    "from src.fundamentals_n67_overlay import n67_overlay_plan",
    "plans=[];labels=[];clocks={}",
    "for issue,n in [('100101',5),('100102',7)]:",
    " f=pd.DataFrame(dict(issue=[issue]*n,slot=range(1,n+1),provider_id=[str(i) for i in range(n)],handicap=0,p_W=.5,p_D=.3,p_L=.2,q_W=.4,q_D=.3,q_L=.3))",
    " clocks[issue]={str(i):'2010-01-01T00:00:00Z' for i in f.slot}",
    " cuts={str(i):Cutoff.decision_epoch(issue,clocks[issue][str(i)]) for i in f.slot}",
    " plans.extend(n67_overlay_plan(f,cutoffs=cuts,strategy=s,funding=m,max_n6=7,max_n7=6,unit_cny=2,payout_factor=.65,allocation_seed=417) for s in ['N7','N6','DIRECT','CROSS'] for m in ['UNIT','MATCHED'])",
    " labels.extend(f[['issue','slot','provider_id','handicap']].assign(home='H',away='A',actual_home=1,actual_away=0).to_dict('records'))",
    "inputs=dict(historical_admission=False,source_hashes={},implementation=implementation_closure(Path(overlay_fixture_root),['src.fundamentals_n67_overlay'],distributions=['numpy','pandas']),labels=labels,cutoffs=clocks)",
    "Path(overlay_fixture_dir,'plans.json').write_text(json.dumps(plans))",
    "Path(overlay_fixture_dir,'inputs.json').write_text(json.dumps(inputs))",
    "Path(overlay_fixture_dir,'contract.json').write_text(json.dumps({'settlement_opened':False,'training_issues':['100101']}))",sep='\n'))
  db <- file.path(p,'db.sqlite');nowscore_query_fixture(db)
  x <- settle_n7_baseline_study(p,db,py,root,'src.fundamentals_n67_overlay','settle_n67_overlay')
  testthat::expect_equal(nrow(x$results),16L)
  zero <- dplyr::filter(x$results,issue=='100101');pending <- dplyr::filter(x$results,issue=='100102')
  testthat::expect_true(all(zero$status=='NO_BET' & zero$stake==0 & zero$gross==0))
  testthat::expect_true(all(pending$status=='PENDING_AUDIT_OR_WINNING_SP' & is.na(pending$gross) & is.na(pending$n6_hits)))
  x$overlay_r_implementation <- n67_overlay_r_receipt(root)
  x$contract_sha256 <- digest::digest(file=file.path(p,'contract.json'),algo='sha256')
  jsonlite::write_json(x,file.path(p,'settlement.json'),auto_unbox=TRUE,dataframe='rows',na='null')
  y <- n67_overlay_report(p,root)
  testthat::expect_equal(nrow(y$summary),16L)
  testthat::expect_true(all(y$summary$stake==0 & is.na(y$summary$roi)))
  testthat::expect_equal(sum(y$common_issues$ready),1L)
  writeLines('changed',file.path(p,'plans.json'))
  testthat::expect_error(n67_overlay_report(p,root))
})
