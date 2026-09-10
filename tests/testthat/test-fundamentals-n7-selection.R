source(file.path('..','..','r','fundamentals_n7_baseline.R'))
source(file.path('..','..','r','fundamentals_n7_selection.R'))
testthat::test_that('selection report binds code and four-arm cohort', {
  root <- normalizePath(file.path('..','..'));p <- tempfile();dir.create(p)
  x <- tidyr::expand_grid(issue=c('a','b'),selector=c('COVERAGE','VALUE'),grouping=c('CONCENTRATED','SNAKE')) |>
    dplyr::mutate(stake=256,gross=300,net=44,roi=44/256,hits=1,groups=1,ideal_gross=300,status='COMPLETE',issue_anchor_ts='2010-01-01')
  writeLines('{}',file.path(p,'inputs.json'));writeLines('[]',file.path(p,'plans.json'))
  jsonlite::write_json(list(training_issues='a'),file.path(p,'contract.json'),auto_unbox=TRUE)
  ledger <- n7_selection_r_receipt(root)
  testthat::expect_true(all(c('r/fundamentals_returns.R','r/fundamentals_n7_selection.R') %in% names(ledger)))
  artifact <- list(results=x,selection_r_implementation=ledger,
    plans_sha256=digest::digest(file=file.path(p,'plans.json'),algo='sha256'),
    inputs_sha256=digest::digest(file=file.path(p,'inputs.json'),algo='sha256'),
    contract_sha256=digest::digest(file=file.path(p,'contract.json'),algo='sha256'))
  jsonlite::write_json(artifact,file.path(p,'settlement.json'),auto_unbox=TRUE,dataframe='rows')
  y <- n7_selection_report(p,root)
  testthat::expect_equal(nrow(y$summary),12L)
  testthat::expect_true(all(y$summary$roi==44/256))
  artifact$results$status[] <- 'PENDING_WINNING_SP'
  jsonlite::write_json(artifact,file.path(p,'settlement.json'),auto_unbox=TRUE,dataframe='rows')
  testthat::expect_equal(nrow(n7_selection_report(p,root)$summary),0L)
  writeLines('changed',file.path(p,'inputs.json'))
  testthat::expect_error(n7_selection_report(p,root))
})

testthat::test_that('six-fixture NO_BET survives Python, SQLite audit and R conversion', {
  root <- normalizePath(file.path('..','..'));p <- tempfile();dir.create(p)
  source(file.path(root,'r/python_bridge.R'))
  source(file.path(root,'r/fundamentals_returns.R'))
  source(file.path(root,'r/nowscore_query.R'))
  source('helper-nowscore-query.R')
  python <- Sys.getenv('FUNDAMENTALS_PYTHON',unset=Sys.getenv('RETICULATE_PYTHON'))
  module <- project_python_module('src.fundamentals_n7_selection',root,python,FALSE)
  main <- reticulate::import_main(convert=FALSE)
  main$n7_fixture_dir <- p;main$n7_fixture_root <- root
  reticulate::py_run_string(paste(
    "import json, pandas as pd",
    "from pathlib import Path",
    "from src.temporal_learning import Cutoff",
    "from src.temporal_learning.provenance import implementation_closure",
    "from src.fundamentals_n7_selection import n7_selection_plan",
    "f=pd.DataFrame(dict(issue=['100101']*6,slot=range(1,7),provider_id=[str(i) for i in range(6)],handicap=0,p_W=.5,p_D=.3,p_L=.2,q_W=.4,q_D=.3,q_L=.3))",
    "epochs={str(i):Cutoff.decision_epoch('100101','2010-01-01T00:00:00Z') for i in f.slot}",
    "plans=[n7_selection_plan(f,cutoffs=epochs,selector=s,grouping=g,max_groups=6,unit_cny=2,group_budget_cny=432,payout_factor=.65,allocation_seed=417) for s in ['COVERAGE','VALUE'] for g in ['CONCENTRATED','SNAKE']]",
    "labels=f[['issue','slot','provider_id','handicap']].assign(home='H',away='A',actual_home=1,actual_away=0).to_dict('records')",
    "inputs=dict(historical_admission=False,source_hashes={},implementation=implementation_closure(Path(n7_fixture_root),['src.fundamentals_n7_selection'],distributions=['numpy','pandas']),labels=labels,cutoffs={'100101':{str(i):'2010-01-01T00:00:00Z' for i in f.slot}})",
    "Path(n7_fixture_dir,'plans.json').write_text(json.dumps(plans))",
    "Path(n7_fixture_dir,'inputs.json').write_text(json.dumps(inputs))",
    "Path(n7_fixture_dir,'contract.json').write_text(json.dumps({'settlement_opened':False}))",sep='\n'))
  db <- file.path(p,'test.sqlite');nowscore_query_fixture(db)
  x <- settle_n7_baseline_study(p,db,python,root,'src.fundamentals_n7_selection','settle_n7_selection')
  testthat::expect_equal(nrow(x$results),4L)
  testthat::expect_true(all(x$results$status=='NO_BET'))
  testthat::expect_true(all(x$results$stake==0 & x$results$gross==0 & x$results$expected_gross==0))
  testthat::expect_type(x$results$expected_roi,'double')
  testthat::expect_true(all(is.na(x$results$expected_roi) & is.na(x$results$roi)))
})
