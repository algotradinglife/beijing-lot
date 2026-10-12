score_direction_fixture <- function() {
  root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
  fixture <- tibble::tibble(fixture_id='00001:4',issue_id='00001',home='H',away='A')
  cutoff <- list(issue_id='00001',cutoff_utc=as.POSIXct('2026-09-24 10:30:00',tz='UTC'))
  grid <- tidyr::expand_grid(home_goals=0:5,away_goals=0:3) |> dplyr::mutate(probability=1/24)
  base <- list(grid=grid,cutoff=cutoff,model_id='TEST_DC',source_hashes=list(raw='fixture-source'),max_source_available_utc=cutoff$cutoff_utc-60,intended_use='HISTORICAL_DIAGNOSTIC')
  bins <- tibble::tibble(bin_id=c('low','one','two','three','high'),min_margin=c(-Inf,1,2,3,4),max_margin=c(0,1,2,3,Inf),target_mass=c(.1,.1,.3,.3,.2),evidence_id='e1',reason='Explicit expert scenario')
  judgement <- list(model_id='TEST_DIRECTION',rationale='Margin-led protection',bins=bins)
  list(root=root,fixture=fixture,cutoff=cutoff,base=base,judgement=judgement)
}

score_direction_context <- function(z,future=FALSE,target=FALSE) {
  reticulate::use_python(file.path(z$root,'.venv/bin/python'),required=TRUE)
  sys <- reticulate::import('sys',convert=FALSE);sys$path$insert(0L,file.path(z$root,'packages/beidan/inst/python'))
  backend <- reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
  shared <- reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
  rows <- list(list(evidence_id='e1',fixture_id=z$fixture$fixture_id,source_hash='saved-evidence',row_key='e1',issue_code='HISTORY',issue_year=2026L,label_available_ts='2026-09-23T00:00:00Z',data_available_ts='2026-09-23T00:00:00Z'))
  if(future || target) rows <- c(rows,list(modifyList(rows[[1]],list(evidence_id='future',row_key='future',source_hash='mutated-target',issue_code=if(target) '00001' else 'HISTORY',data_available_ts=if(future) '2026-09-24T10:30:00Z' else '2026-09-23T00:00:00Z'))))
  hashes <- list(base_artifact=.score_margin_hash(z$base),margin_judgement=.score_margin_hash(z$judgement),direction_implementation=.score_margin_code(z$root),raw='saved-evidence')
  backend$build_adjustment_evidence_context(rows,as.list(z$fixture),shared$Cutoff$decision_epoch(z$cutoff$issue_id,'2026-09-24T10:30:00Z'),hashes,shared$AvailabilityPolicy$historical_proxy('TEST_EVIDENCE_PROXY'),'HISTORICAL_DIAGNOSTIC',z$root)
}

testthat::test_that('margin targets preserve score conditionals and deliver ranked protection', {
  z <- score_direction_fixture();context <- score_direction_context(z)
  x <- adjust_score_margin_distribution(z$base,z$judgement,context,z$fixture,z$cutoff,z$root)
  projected <- project_score_outcomes(x,-2L,z$root)
  testthat::expect_equal(projected$outcome,c('W','D','L'))
  testthat::expect_equal(projected$probability,c(.5,.3,.2))
  testthat::expect_equal(sum(x$grid$probability),1)
  testthat::expect_equal(x$margins$probability[x$margins$margin==2],.3)
  testthat::expect_equal(x$margins$probability[x$margins$margin==3],.3)
  testthat::expect_equal(x$grid$probability,x$grid$base_probability*x$grid$multiplier)
  testthat::expect_s3_class(x$ledger,'tbl_df');testthat::expect_s3_class(x$margins,'tbl_df')
  testthat::expect_equal(x$receipt$cache_reuse,'NONE')
  testthat::expect_equal(x$receipt$input_hashes$direction_implementation,.score_margin_code(z$root))
  testthat::expect_equal(.score_margin_hash(z$base),.score_margin_hash(z$base))
  testthat::expect_false(identical(.score_margin_hash(-Inf),.score_margin_hash(Inf)))
  testthat::expect_false(identical(.score_margin_hash(NA_real_),.score_margin_hash(NULL)))
  z2 <- z;z2$base$model_id <- 'changed';testthat::expect_false(identical(.score_margin_hash(z$base),.score_margin_hash(z2$base)))
  for(kind in c('future','target')) {
    extra <- if(kind=='future') score_direction_context(z,future=TRUE) else score_direction_context(z,target=TRUE)
    y <- adjust_score_margin_distribution(z$base,z$judgement,extra,z$fixture,z$cutoff,z$root)
    testthat::expect_identical(y$grid,x$grid);testthat::expect_identical(y$margins,x$margins)
  }
  bad <- z$judgement;bad$bins$target_mass <- c(.2,.2,.2,.2,.2)
  testthat::expect_error(adjust_score_margin_distribution(z$base,bad,context,z$fixture,z$cutoff,z$root),'binding')
  badbase <- z$base;badbase$grid$probability[1:2] <- rev(badbase$grid$probability[1:2])+c(.01,-.01)
  testthat::expect_error(adjust_score_margin_distribution(badbase,z$judgement,context,z$fixture,z$cutoff,z$root),'binding')
  testthat::expect_error(adjust_score_margin_distribution(z$base,z$judgement,list(),z$fixture,z$cutoff,z$root),'Opaque')
  testthat::expect_error(adjust_score_margin_distribution(z$base,z$judgement,context,z$fixture,modifyList(z$cutoff,list(cutoff_utc=z$cutoff$cutoff_utc+1)),z$root),'Base cutoff')
  prospective <- z;prospective$base$intended_use <- 'PROSPECTIVE_DECISION'
  testthat::expect_error(adjust_score_margin_distribution(prospective$base,z$judgement,context,z$fixture,z$cutoff,z$root),'availability')
})

testthat::test_that('ticket handicap changes projection only, not calibration or frozen receipt', {
  z <- score_direction_fixture()
  x <- adjust_score_margin_distribution(z$base,z$judgement,score_direction_context(z),z$fixture,z$cutoff,z$root)
  before <- .score_margin_hash(x)
  for(h in c(-3L,-2L,-1L,0L,1L,2L)) {
    p <- project_score_outcomes(x,h,z$root)
    testthat::expect_equal(sum(p$probability),1)
    testthat::expect_equal(.score_margin_hash(x),before)
    testthat::expect_equal(p$probability[p$outcome=='W'],sum(x$grid$probability[x$grid$margin+h>0]))
  }
  testthat::expect_equal(project_score_outcomes(x,-3L,z$root)$outcome,c('L','D','W'))
  for(masses in list(c(.65,.25,.1),c(.25,.1,.65),c(.4,.2,.4))) {
    special <- z
    special$base$grid <- tibble::tibble(home_goals=c(1L,0L,0L),away_goals=c(0L,0L,1L),probability=c(.3,.3,.4))
    special$judgement$bins <- tibble::tibble(bin_id=c('away','draw','home'),min_margin=c(-Inf,0,1),max_margin=c(-1,0,Inf),target_mass=masses,evidence_id='e1',reason='Independent margin scenario')
    y <- adjust_score_margin_distribution(special$base,special$judgement,score_direction_context(special),special$fixture,special$cutoff,special$root)
    p <- project_score_outcomes(y,0L,z$root)
    if(identical(masses,c(.65,.25,.1))) testthat::expect_equal(p$outcome,c('L','D','W'))
    if(identical(masses,c(.25,.1,.65))) testthat::expect_equal(p$outcome,c('W','L','D'))
    if(identical(masses,c(.4,.2,.4))) {testthat::expect_equal(p$rank,c(1L,1L,3L));testthat::expect_equal(p$tied_rank,c(TRUE,TRUE,FALSE))}
  }
  testthat::expect_error(project_score_outcomes(x,.5,z$root))
  testthat::expect_error(project_score_outcomes(x$grid,0L,z$root),'cutoff-bound')
  bad <- x;bad$grid$probability[1] <- NA_real_
  testthat::expect_error(project_score_outcomes(bad,0L,z$root),'integrity')
  bad <- x;bad$cutoff$cutoff_utc <- bad$cutoff$cutoff_utc+1
  testthat::expect_error(project_score_outcomes(bad,0L,z$root),'integrity')
  bad <- z$judgement;bad$roles <- tibble::tibble(rank=1:3,outcome=c('W','D','L'))
  testthat::expect_error(adjust_score_margin_distribution(z$base,bad,score_direction_context(z),z$fixture,z$cutoff,z$root),'roles cannot')
  badbase <- z$base;badbase$beidan_handicap <- -2L
  testthat::expect_error(adjust_score_margin_distribution(badbase,z$judgement,score_direction_context(z),z$fixture,z$cutoff,z$root),'Ticket line')
  badfixture <- dplyr::mutate(z$fixture,handicap=-2L)
  testthat::expect_error(adjust_score_margin_distribution(z$base,z$judgement,score_direction_context(z),badfixture,z$cutoff,z$root))
  testthat::expect_false(identical(.score_margin_hash(z$cutoff),.score_margin_hash(modifyList(z$cutoff,list(cutoff_utc=z$cutoff$cutoff_utc+.000001)))))
})

testthat::test_that('invalid support, chronology, partitions and conflicting roles fail closed', {
  z <- score_direction_fixture();context <- score_direction_context(z)
  bad <- z$base;bad$grid <- bad$grid[0,]
  testthat::expect_error(adjust_score_margin_distribution(bad,z$judgement,context,z$fixture,z$cutoff,z$root))
  bad <- z$base;bad$max_source_available_utc <- z$cutoff$cutoff_utc
  testthat::expect_error(adjust_score_margin_distribution(bad,z$judgement,context,z$fixture,z$cutoff,z$root),'chronology')
  bad <- z$base;bad$grid$probability[1] <- NA_real_
  testthat::expect_error(adjust_score_margin_distribution(bad,z$judgement,context,z$fixture,z$cutoff,z$root))
  bad <- z$base;bad$grid <- dplyr::bind_rows(bad$grid,bad$grid[1,])
  testthat::expect_error(adjust_score_margin_distribution(bad,z$judgement,context,z$fixture,z$cutoff,z$root),'normalized')
  for(kind in c('gap','overlap','fractional','mass','missing')) {
    bad <- z$judgement
    if(kind=='gap') bad$bins$min_margin[2] <- 2
    if(kind=='overlap') bad$bins$min_margin[2] <- 0
    if(kind=='fractional') bad$bins$min_margin[2] <- 1.5
    if(kind=='mass') bad$bins$target_mass[1] <- .11
    if(kind=='missing') bad$bins$target_mass[1] <- NA_real_
    testthat::expect_error(adjust_score_margin_distribution(z$base,bad,context,z$fixture,z$cutoff,z$root))
  }
  for(kind in c('unsupported','evidence')) {
    bad <- z
    if(kind=='unsupported') {bad$judgement$bins$min_margin[5] <- 100;bad$judgement$bins$max_margin[4] <- 99}
    if(kind=='evidence') bad$judgement$bins$evidence_id <- 'unknown'
    ctx <- score_direction_context(bad)
    testthat::expect_error(adjust_score_margin_distribution(bad$base,bad$judgement,ctx,bad$fixture,bad$cutoff,bad$root),switch(kind,unsupported='support',evidence='unavailable'))
  }
})
