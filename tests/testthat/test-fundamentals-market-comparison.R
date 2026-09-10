source('../../r/probability_exploration.R')
source('../../r/strength_market_scenario.R')
source('../../r/fundamentals_score_diagnostic.R')
source('../../r/fundamentals_score_shape.R')
source('../../r/fundamentals_market_comparison.R')

test_that('bounded correction limits each team and projection reconciles', {
  expect_equal(bounded_market_lambdas(c(2,1),c(20,.01),.2,.1),c(2.2,.9))
  expect_equal(bounded_market_lambdas(c(2,1),c(3,2),0,.1),c(2,1))
  expect_error(bounded_market_lambdas(c(0,1),c(1,1),.2,.1),'Positive')
  expect_error(bounded_market_lambdas(c(1,1),c(1,1),2,.1),'Invalid')
  expect_error(bounded_market_lambdas(c(1,1),c(1,1),.2,NA_real_),'Invalid')
  p <- market_score_projection(c(2,1),-1,1e-10)
  expect_equal(sum(unlist(p$fields[c('W','D','L')])),1)
  expect_equal(p$fields$D,sum(p$grid$probability[p$grid$net==1]))
  expect_equal(p$fields$home_ge3,sum(p$grid$probability[p$grid$net>=3]))
  expect_error(market_score_projection(c(-1,1),0,1e-10))
})

test_that('market comparison seals label-free choices and rejects mismatched inputs', {
  project <- normalizePath('../..')
  p <- market_score_projection(c(1.8,1.2),-1,1e-10)
  f <- dplyr::bind_cols(tibble::tibble(slot=1L,provider_id='001',home='Home',away='Away',
    variant='raw',status='OK_DIAGNOSTIC',handicap=-1),tibble::as_tibble(p$fields))
  cuts <- list('001'=list('1'='2010-01-01T00:00:00Z'))
  e <- list(fixtures=f,grids=list('1/raw'=p$grid),cutoffs=cuts[['001']],
    source_windows=list(list(slot=1L,home_window=list(list(competition_name='A',observed_sources=c('titan','nowscore'),blocks=c('a','b','c'))),
      away_window=list(list(competition_name='B')))))
  model <- list(experiments=list('001'=e),scores=tibble::tibble(),
    coverage_choices=score_coverage_choices(list('001'=e)),
    provenance=list('001'=list(review_context=list(list(slot=1L,home_league_evidence='A',away_league_evidence='B')))),
    implementation_hashes=stats::setNames(digest::digest(file='../../r/probability_exploration.R',algo='sha256'),'r/probability_exploration.R'),
    parameters=list(tail_tolerance=1e-10),gates=tibble::tibble(),historical_admission=FALSE)
  model$seal <- digest::digest(model,algo='sha256')
  odds <- 1/unlist(p$fields[c('ordinary_W','ordinary_D','ordinary_L')])
  capture_path <- tempfile();writeLines('synthetic quote envelope',capture_path)
  on.exit(unlink(capture_path))
  capture_sha <- digest::digest(file=capture_path,algo='sha256')
  quotes <- list(rows=list(list(issue='001',slot=1L,provider_id='001',cutoff_utc=cuts[['001']][['1']],
    status='OK_DIAGNOSTIC',companies=1L,capture_path=capture_path,capture_sha256=capture_sha,odds_W=odds[1],odds_D=odds[2],odds_L=odds[3])),
    receipts=list(list(issue='001',slot=1L,receipt=list(historical_admission=FALSE,
      target_issue='001',cutoff_ts=cuts[['001']][['1']],source_hashes=stats::setNames(list(capture_sha),capture_path),
      implementation_hashes=as.list(model$implementation_hashes),selected_ids=list('company')))),
    companies=list(list(issue='001',slot=1L,quote_id='company',odds_W=unname(odds[1]),odds_D=unname(odds[2]),odds_L=unname(odds[3]))),
    implementation_hashes=as.list(model$implementation_hashes),historical_admission=FALSE)
  quotes$receipts[[1]]$receipt_json <- as.character(jsonlite::toJSON(quotes$receipts[[1]]$receipt,auto_unbox=TRUE,digits=17,null='null'))
  quotes$receipts[[1]]$receipt$identity <- digest::digest(quotes$receipts[[1]]$receipt_json,algo='sha256',serialize=FALSE)
  quotes$canonical_json <- as.character(jsonlite::toJSON(quotes,auto_unbox=TRUE,digits=17,null='null'))
  quotes$seal <- digest::digest(quotes$canonical_json,algo='sha256',serialize=FALSE)
  catalog <- tibble::tibble(league=c('A','B'),country=c('X','X'),tier=c(1,2))
  args <- list(models=model,quotes=quotes,cutoffs=cuts,league_catalog=catalog,
    corrections=c(corrected10=.1,corrected20=.2),cap=.1,residual_limit=.05,project_root=project,generated_at='2026-09-08T00:00:00Z')
  x <- do.call(prepare_market_comparison,args)
  expect_equal(nrow(x$fixtures),4)
  expect_true(all(x$fixtures$market_residual<1e-6))
  expect_true(all(x$choices$main_choices[x$choices$rule=='double_protect1']==2))
  ev <- list(fixtures=dplyr::mutate(f,issue='001',scorable=TRUE,actual_home=3L,actual_away=1L),seal=model$seal)
  result <- evaluate_score_shape_scenarios(x,ev)
  expect_equal(nrow(result$summary),4)
  expect_equal(result$fixtures$score_nll,result$fixtures$margin_nll+result$fixtures$conditional_nll)
  ev$fixtures$actual_home <- 0L
  invisible(evaluate_score_shape_scenarios(x,ev))
  expect_identical(x,do.call(prepare_market_comparison,args))
  vector_args <- args;vector_args$quotes$receipts[[1]]$receipt$selected_ids <- 'company'
  expect_identical(x$fixtures,do.call(prepare_market_comparison,vector_args)$fixtures)
  bad <- args;bad$cutoffs <- list()
  expect_error(do.call(prepare_market_comparison,bad),'cutoffs')
  bad <- args;bad$quotes$rows[[1]]$provider_id <- 'wrong'
  expect_error(do.call(prepare_market_comparison,bad),'mutated')
  bad <- args;bad$quotes$rows[[1]]$status <- 'NO_PRIOR_LAST_QUOTES'
  expect_error(do.call(prepare_market_comparison,bad),'mutated')
  bad <- args;bad$quotes$rows[[1]]$odds_W <- 99
  expect_error(do.call(prepare_market_comparison,bad),'mutated')
  bad <- args;bad$quotes$receipts[[1]]$receipt$cutoff_ts <- '2099-01-01'
  expect_error(do.call(prepare_market_comparison,bad),'mutated')
  bad <- args;bad$quotes$implementation_hashes <- list()
  expect_error(do.call(prepare_market_comparison,bad),'seal')
  bad <- args;bad$league_catalog$tier <- c(1,1)
  expect_error(do.call(prepare_market_comparison,bad),'No common')
  writeLines('changed collection metadata',capture_path)
  expect_error(do.call(prepare_market_comparison,args),'envelope changed')
})
