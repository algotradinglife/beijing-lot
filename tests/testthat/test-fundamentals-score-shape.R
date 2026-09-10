source('../../r/probability_exploration.R')
source('../../r/fundamentals_score_diagnostic.R')
source('../../r/fundamentals_score_shape.R')

test_that('factorization preserves margin or conditional probabilities independently', {
  g <- illustrative_score_grid(1.8,1.2,-1,1e-10)$grid
  g <- dplyr::transmute(g,home_goals,away_goals,probability=probability_raw/sum(probability_raw))
  original <- g
  baseline <- score_shape_grid(g,3L,1,1)
  expect_equal(baseline$probability,g$probability,tolerance=1e-14)
  low <- score_shape_grid(g,3L,1,1/1.5);high <- score_shape_grid(g,3L,1,1.5)
  tail <- score_shape_grid(g,3L,1.5,1);combined <- score_shape_grid(g,3L,1.5,1.5)
  for (d in unique(baseline$net)) {
    idx <- baseline$net==d;p <- sum(baseline$probability[idx])
    expect_equal(sum(low$probability[idx]),p,tolerance=1e-13)
    expect_equal(sum(high$probability[idx]),p,tolerance=1e-13)
    expect_equal(tail$probability[idx]/sum(tail$probability[idx]),baseline$probability[idx]/p,tolerance=1e-12)
    expect_equal(combined$probability[idx]/sum(combined$probability[idx]),high$probability[idx]/p,tolerance=1e-12)
  }
  base_mass <- sum(baseline$probability[abs(baseline$net)>=3])
  tail_mass <- sum(tail$probability[abs(tail$net)>=3])
  expect_equal(tail_mass/(1-tail_mass),1.5*base_mass/(1-base_mass))
  expect_gt(sum(high$probability*high$paired_goals),sum(baseline$probability*baseline$paired_goals))
  expect_lt(sum(low$probability*low$paired_goals),sum(baseline$probability*baseline$paired_goals))
  expect_equal(sum(combined$probability),1)
  expect_identical(g,original)
  zero <- tibble::tibble(home_goals=c(0,1,2),away_goals=c(0,0,0),probability=c(1,0,0))
  expect_equal(score_shape_grid(zero,3L,2,2)$probability,c(1,0,0))
  expect_error(score_shape_grid(g[FALSE,],3,1,1),'Nonempty')
  expect_error(score_shape_grid(dplyr::bind_rows(g,g[1,]),3,1,1),'Invalid')
  bad <- g;bad$probability[1] <- NA_real_
  expect_error(score_shape_grid(bad,3,1,1),'Invalid')
  expect_error(score_shape_grid(g,3,0,1),'Positive')
  expect_error(score_shape_grid(g,3,1,Inf),'Positive')
  expect_error(score_shape_grid(g,2.5,1,1),'Integer')
})

test_that('sealed scenarios reuse choices and evaluate mass decomposition without target fitting', {
  project <- normalizePath('../..')
  g <- illustrative_score_grid(1.8,1.2,-1,1e-10)$grid
  g <- dplyr::transmute(g,home_goals,away_goals,probability=probability_raw/sum(probability_raw),outcome=handicap_outcome)
  f <- tibble::tibble(slot=1L,provider_id='001',home='Home',away='Away',variant='raw',status='OK_DIAGNOSTIC',
    handicap=-1,lambda_home=1.8,lambda_away=1.2,W=sum(g$probability[g$outcome=='W']),
    D=sum(g$probability[g$outcome=='D']),L=sum(g$probability[g$outcome=='L']))
  # Input toy fixture contains no results; cutoff is an opaque, already bound
  # fixture epoch here. Real shared-window replay is tested in score-review.R.
  cuts <- list('001'=list('1'='2010-01-01T00:00:00Z'))
  experiment <- list(fixtures=f,grids=list('1/raw'=g),cutoffs=cuts[['001']])
  model <- list(experiments=list('001'=experiment),scores=tibble::tibble(),
    coverage_choices=score_coverage_choices(list('001'=experiment)),provenance=list(),
    implementation_hashes=stats::setNames(digest::digest(file='../../r/fundamentals_score_diagnostic.R',algo='sha256'),'r/fundamentals_score_diagnostic.R'),
    parameters=list(tail_tolerance=1e-10),gates=tibble::tibble(),historical_admission=FALSE)
  model$seal <- digest::digest(model,algo='sha256')
  policy <- tibble::tibble(scenario=c('baseline','tail','low','high'),tail_factor=c(1,1.5,1,1),pair_factor=c(1,1,1/1.5,1.5))
  artifact <- prepare_score_shape_scenarios(model,cuts,policy,3L,project,'2026-09-08T00:00:00Z')
  evaluation <- list(fixtures=dplyr::mutate(f,issue='001',scorable=TRUE,actual_home=3L,actual_away=1L),seal=model$seal)
  result <- evaluate_score_shape_scenarios(artifact,evaluation)
  expect_equal(nrow(result$summary),4L)
  expect_equal(result$fixtures$score_nll,result$fixtures$margin_nll+result$fixtures$conditional_nll)
  expect_equal(nrow(result$tails),16L)
  expect_true(all(result$summary$covered_count==result$summary$main_hits+result$summary$protection_adds))
  expect_true(all(result$summary$covered_count==result$summary$covered_count[1]+result$summary$gains-result$summary$losses))
  expect_false(artifact$receipt$historical_admission)
  expect_identical(artifact$receipt$cutoffs,cuts)
  expect_true('r/fundamentals_score_shape.R' %in% names(artifact$receipt$implementation_hashes))
  roundtrip <- jsonlite::fromJSON(jsonlite::toJSON(artifact$receipt,auto_unbox=TRUE),simplifyVector=FALSE)
  expect_identical(roundtrip$implementation_hashes,artifact$receipt$implementation_hashes)
  expect_identical(roundtrip$cutoffs,cuts)
  previous <- artifact
  evaluation$fixtures$actual_home <- 0L;evaluation$fixtures$actual_away <- 0L
  other <- evaluate_score_shape_scenarios(artifact,evaluation)
  expect_identical(artifact,previous)
  expect_false(identical(result$receipt$evaluated_labels_sha256,other$receipt$evaluated_labels_sha256))
  repeated <- prepare_score_shape_scenarios(model,cuts,policy,3L,project,'2026-09-08T00:00:00Z')
  expect_identical(repeated$seal,artifact$seal)
  expect_error(prepare_score_shape_scenarios(model,list(),policy,3L,project,'2026-09-08T00:00:00Z'),'cutoff')
  bad <- policy;bad$tail_factor[1] <- 2
  expect_error(prepare_score_shape_scenarios(model,cuts,bad,3L,project,'2026-09-08T00:00:00Z'),'Baseline')
  expect_error(prepare_score_shape_scenarios(model,cuts,policy,3L,project,'bad'),'UTC')
  changed <- artifact;changed$choices$selected[1] <- 'W,D,L'
  expect_error(evaluate_score_shape_scenarios(changed,evaluation),'sealed')
  empty_model <- model;empty_model$experiments[['001']]$fixtures <- f[FALSE,]
  empty_model$coverage_choices <- model$coverage_choices[FALSE,]
  empty_model$seal <- digest::digest(empty_model[setdiff(names(empty_model),'seal')],algo='sha256')
  empty <- prepare_score_shape_scenarios(empty_model,cuts,policy,3L,project,'2026-09-08T00:00:00Z')
  empty_evaluation <- list(fixtures=evaluation$fixtures[FALSE,],seal=empty_model$seal)
  empty_result <- evaluate_score_shape_scenarios(empty,empty_evaluation)
  expect_equal(nrow(empty_result$fixtures),0L)
  expect_equal(nrow(empty_result$summary),0L)
  expect_equal(nrow(empty_result$tails),0L)
  evaluation$fixtures$actual_home <- 1000
  expect_error(evaluate_score_shape_scenarios(artifact,evaluation),'outside')
  evaluation$fixtures$provider_id <- 'wrong'
  expect_error(evaluate_score_shape_scenarios(artifact,evaluation),'identity')
})
