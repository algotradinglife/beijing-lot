make_goal_context <- function(fixture, matches=12L, goals=10L, post_cutoff=FALSE) {
  root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
  reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
  sys <- reticulate::import('sys',convert=FALSE)
  sys$path$insert(0L,file.path(root,'packages/beidan/inst/python'))
  backend <- reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
  shared <- reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
  rows <- list(list(team=fixture$home,venue='home',matches=matches,goals_for=goals,goals_against=13L),
               list(team=fixture$away,venue='away',matches=13L,goals_for=20L,goals_against=21L))
  for(i in seq_along(rows)) rows[[i]] <- c(rows[[i]],list(row_key=paste0('r',i),issue_code='HISTORY',
    issue_year=2026L,label_available_ts='2026-10-08T00:00:00Z',data_available_ts='2026-10-08T00:00:00Z'))
  if(post_cutoff) {
    rows <- c(rows,list(modifyList(rows[[1]],list(row_key='target',issue_code='26103',goals_for=999L)),
      modifyList(rows[[1]],list(row_key='future',data_available_ts='2026-10-10T00:00:00Z',goals_for=888L))))
  }
  backend$build_goal_baseline_context(rows,as.list(fixture),
    shared$Cutoff$decision_epoch('26103','2026-10-09T14:42:26.035423Z'),list(raw=digest::digest(jsonlite::toJSON(rows,auto_unbox=TRUE),algo='sha256',serialize=FALSE)),
    shared$AvailabilityPolicy$historical_proxy('DATED_SUMMARY_DIAGNOSTIC'),
    'HISTORICAL_DIAGNOSTIC',root)
}

make_goal_evidence <- function(fixture, ids=c('e1','e2'), future=FALSE) {
  root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
  backend <- reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
  shared <- reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
  rows <- lapply(ids,function(id) list(evidence_id=id,fixture_id=fixture$fixture_id,
    source_hash=paste0('source-',id),row_key=id,issue_code='HISTORY',issue_year=2026L,
    label_available_ts='2026-10-08T00:00:00Z',data_available_ts='2026-10-08T00:00:00Z'))
  if(future) rows[[length(rows)]]$data_available_ts <- '2026-10-10T00:00:00Z'
  backend$build_adjustment_evidence_context(rows,as.list(fixture),
    shared$Cutoff$decision_epoch('26103','2026-10-09T14:42:26.035423Z'),list(raw='evidence-fixture'),
    shared$AvailabilityPolicy$historical_proxy('EVIDENCE_DIAGNOSTIC'),
    'HISTORICAL_DIAGNOSTIC',root)
}

testthat::test_that('shared-admitted venue baseline is sealed, typed and cutoff bound', {
  root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
  f <- tibble::tibble(fixture_id='26103:79',issue_id='26103',home='Paju',away='Busan',handicap=0L)
  policy <- list(rho=-.1,tail_tolerance=1e-10,minimum_matches=5L,lambda_digits=2L)
  c <- make_goal_context(f)
  x <- fundamental_goal_baseline(c,f,policy,root)
  testthat::expect_s3_class(x,'fundamental_scenario')
  testthat::expect_s3_class(x$ledger,'tbl_df')
  testthat::expect_equal(x$parameters$lambda_home,1.22)
  testthat::expect_equal(x$parameters$lambda_away,1.31)
  testthat::expect_equal(as.numeric(x$cutoff$cutoff_utc),1791556946.035423)
  testthat::expect_true(all(x$probabilities$probability>=0))
  changed <- fundamental_goal_baseline(make_goal_context(f,post_cutoff=TRUE),f,policy,root)
  testthat::expect_equal(changed$probabilities,x$probabilities)
  testthat::expect_equal(changed$summaries,x$summaries)
  testthat::expect_false(identical(changed$seal,x$seal))
  testthat::expect_equal(sum(x$probabilities$probability),1)
  testthat::expect_true(.fundamental_verify(x))
  testthat::expect_identical(.fundamental_code_hash(),x$receipt$implementation_hash)
  testthat::expect_equal(.fundamental_finish(x)$probabilities,x$probabilities)
  testthat::expect_error(fundamental_goal_baseline(list(),f,policy,root),'Opaque')
  testthat::expect_error(fundamental_goal_baseline(c,dplyr::mutate(f,home='Other'),policy,root),'binding')
  testthat::expect_error(fundamental_goal_baseline(make_goal_context(f,matches=0L),f,policy,root),'support')
  testthat::expect_error(fundamental_goal_baseline(c,f,modifyList(policy,list(minimum_matches=14L)),root),'support')
  testthat::expect_error(fundamental_goal_baseline(c,f,modifyList(policy,list(lambda_digits=NA)),root))
  bad <- x;bad$cutoff$cutoff_utc <- bad$cutoff$cutoff_utc+1
  testthat::expect_error(.fundamental_verify(bad),'integrity')
  testthat::expect_error(.fundamental_verify(list()),'scenario')
  bad <- x;bad$receipt$implementation_hash <- 'bad';bad$seal <- NULL;bad$seal <- rlang::hash(bad)
  testthat::expect_error(.fundamental_verify(bad),'implementation')
  bad <- x;bad$cutoff$issue_id <- 'other';bad$seal <- NULL;bad$seal <- rlang::hash(bad)
  testthat::expect_error(.fundamental_verify(bad),'binding')
  bad <- x;bad$cutoff$cutoff_utc <- bad$cutoff$cutoff_utc+1;bad$receipt$cutoff_hash <- rlang::hash(bad$cutoff);bad$seal <- NULL;bad$seal <- rlang::hash(bad)
  testthat::expect_error(.fundamental_verify(bad),'binding')
})

testthat::test_that('adjustment ledger replays qualitative then market stages without rho edits', {
  root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
  f <- tibble::tibble(fixture_id='26103:79',issue_id='26103',home='Paju',away='Busan',handicap=0L)
  x <- fundamental_goal_baseline(make_goal_context(f),f,
    list(rho=-.1,tail_tolerance=1e-10,minimum_matches=5L,lambda_digits=2L),root)
  a <- tibble::tibble(adjustment_id=c('a','b'),stage='qualitative',
    parameter=c('lambda_home','lambda_away'),delta_goals=c(.02,.04),evidence_id=c('e1','e2'),reason=c('exposure','attack'))
  p <- list(max_absolute_delta=.2,evidence_context=make_goal_evidence(f))
  q <- apply_goal_adjustments(x,a,p)
  testthat::expect_equal(q$parameters$lambda_home,1.24)
  testthat::expect_equal(q$parameters$lambda_away,1.35)
  testthat::expect_equal(q$policy$rho,-.1)
  testthat::expect_equal(q$receipt$parent_seal,x$seal)
  testthat::expect_identical(apply_goal_adjustments(x,x$ledger,p),x)
  m <- dplyr::mutate(a[1,],adjustment_id='c',stage='market_review',parameter='lambda_away',delta_goals=.1)
  final <- apply_goal_adjustments(q,m,p)
  testthat::expect_equal(final$parameters$lambda_away,1.45)
  testthat::expect_equal(final$probabilities$probability,c(.3108741,.2814872,.4076387),tolerance=1e-7)
  testthat::expect_equal(nrow(final$ledger),3L)
  testthat::expect_equal(final$parameter_history$revision,c(0L,2L,3L))
  testthat::expect_equal(nrow(final$probability_history),9L)
  testthat::expect_error(apply_goal_adjustments(q,a,p),'Duplicate')
  testthat::expect_error(apply_goal_adjustments(final,dplyr::mutate(a,adjustment_id=c('d','e')),p),'backward')
  testthat::expect_error(apply_goal_adjustments(x,dplyr::mutate(a,parameter='rho'),p),'parameter')
  testthat::expect_error(apply_goal_adjustments(x,dplyr::mutate(a,delta_goals=.3),p),'bound')
  testthat::expect_error(apply_goal_adjustments(x,dplyr::mutate(a,delta_goals=NA_real_),p))
  testthat::expect_error(apply_goal_adjustments(x,dplyr::mutate(a,reason=''),p))
  testthat::expect_error(apply_goal_adjustments(x,dplyr::mutate(a,evidence_id='missing'),p),'unavailable')
  testthat::expect_error(apply_goal_adjustments(x,dplyr::mutate(a,delta_goals=-2),modifyList(p,list(max_absolute_delta=3))),'nonpositive')
  testthat::expect_error(apply_goal_adjustments(x,dplyr::mutate(a,stage=c('qualitative','market_review')),p),'One stage')
  testthat::expect_error(apply_goal_adjustments(x,a,list(max_absolute_delta=.2,evidence_context=make_goal_evidence(f,future=TRUE))),'unavailable')
  only_home <- apply_goal_adjustments(x,a[1,],list(max_absolute_delta=.2,evidence_context=make_goal_evidence(f,ids='e1')))
  second <- apply_goal_adjustments(only_home,dplyr::mutate(a[2,],stage='market_review'),
    list(max_absolute_delta=.1,evidence_context=make_goal_evidence(f,ids='e2')))
  testthat::expect_equal(second$evidence$evidence_id,c('e1','e2'))
  testthat::expect_equal(length(second$receipt$adjustment_policies),2L)
  testthat::expect_equal(second$receipt$adjustment_policies[[1]]$max_absolute_delta,.2)
  testthat::expect_equal(second$receipt$adjustment_policies[[2]]$max_absolute_delta,.1)

})

testthat::test_that('market comparison preserves ordinary scope, time exclusions and stale evidence', {
  root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
  f <- tibble::tibble(fixture_id='26103:79',issue_id='26103',home='Paju',away='Busan',handicap=-1L)
  x <- fundamental_goal_baseline(make_goal_context(f),f,
    list(rho=-.1,tail_tolerance=1e-10,minimum_matches=5L,lambda_digits=2L),root)
  d <- c(x$cutoff,list(max_quote_age_hours=24,total_bounds=c(.1,10)))
  m <- tibble::tibble(company_id=c('a','a','b'),fixture_id=f$fixture_id,
    quote_at=x$cutoff$cutoff_utc+c(-3600,1,-2*86400),odds_home=c(3.3,99,3.5),odds_draw=c(3.3,99,3.5),odds_away=c(2,1.01,2))
  t <- tibble::tibble(company_id='t',fixture_id=f$fixture_id,quote_at=x$cutoff$cutoff_utc-3600,
    line=2.5,over_decimal=1.9,under_decimal=1.9)
  z <- compare_fundamental_market(x,m,t,d)
  testthat::expect_equal(nrow(z$market),2L)
  changed <- m;changed$odds_home[2] <- 0
  testthat::expect_equal(compare_fundamental_market(x,changed,t,d)$comparison,z$comparison)
  testthat::expect_equal(z$receipt$exclusions$market$future_or_cutoff,1L)
  testthat::expect_equal(sum(z$market$stale),1L)
  testthat::expect_equal(sum(z$comparison$market),1)
  testthat::expect_equal(z$comparison$fundamental,x$ordinary$probability)
  testthat::expect_equal(z$total$lambda_total,2.6740603,tolerance=1e-7)
  testthat::expect_true(is.finite(z$projection$fields$market_residual))
  empty <- compare_fundamental_market(x,m[0,],t[0,],d)
  testthat::expect_s3_class(empty$comparison,'tbl_df')
  testthat::expect_equal(nrow(empty$comparison),0L)
  testthat::expect_null(empty$total)
  testthat::expect_null(compare_fundamental_market(x,m[0,],t,d)$projection)
  testthat::expect_error(compare_fundamental_market(x,m,t,modifyList(d,list(cutoff_utc=d$cutoff_utc+1))),'cutoff')
  testthat::expect_error(compare_fundamental_market(x,dplyr::mutate(m,fixture_id='bad'),t,d),'fixture')
  testthat::expect_error(compare_fundamental_market(x,dplyr::bind_rows(m,m[1,]),t,d),'company/time')
  testthat::expect_error(compare_fundamental_market(x,dplyr::mutate(m,odds_home=1),t,d),'exceed')
  testthat::expect_error(compare_fundamental_market(x,m,dplyr::mutate(t,line=2.25),d),'half-goal')
  testthat::expect_error(compare_fundamental_market(x,dplyr::mutate(m,quote_at=as.numeric(quote_at)),t,d),'times')
})
