#' Synthetic source-selection fixture exercised by the tests below.
#' @return Explicit fixture, bases, review, cutoff and backend root.
FmSourceTestFixture <- function() {
  root <- Sys.getenv("FM_NATIVE_TEST_ROOT");stopifnot(nzchar(root))
  fixture <- tibble::tibble(fixture_id="00001:4",issue_id="00001",home="H",away="A")
  cutoff <- list(issue_id="00001",cutoff_utc=as.POSIXct("2026-10-03 16:30:00",tz="UTC"))
  grid <- tibble::tibble(home_goals=c(0L,1L,2L),away_goals=0L,probability=c(.5,.3,.2))
  native <- list(grid=grid,cutoff=cutoff,model_id="SYNTHETIC_NATIVE",source_hashes=list(raw="native"),max_source_available_utc=cutoff$cutoff_utc-60,intended_use="HISTORICAL_DIAGNOSTIC")
  market<-native;market$model_id<-"SYNTHETIC_JOINT_MARKET";market$grid$probability<-c(.2,.3,.5);market$source_hashes<-list(raw="market")
  review <- list(confidence="low",market_sufficient=TRUE,market_consistent=TRUE,reason="Evidence quality low",counterevidence="No observed availability",evidence_ids="e1",cutoff_utc="2026-10-03T16:30:00Z",native_hash=beidan:::.score_margin_hash(native),market_hash=beidan:::.score_margin_hash(market),author="ROOT_SYNTHETIC",review_version="FM-1.6.0_TEST")
  return(list(root=root,fixture=fixture,cutoff=cutoff,native=native,market=market,review=review))
}

#' Shared admitted evidence for a synthetic source decision.
#' @param z Explicit fixture returned by FmSourceTestFixture.
#' @param poison Whether to add post-cutoff and exact-target rows.
#' @return Opaque authoritative context; no custom chronology implementation.
FmSourceTestContext <- function(z, poison=FALSE) {
  reticulate::use_python(file.path(z$root,".venv/bin/python"),required=TRUE)
  reticulate::import("sys",convert=FALSE)$path$insert(0L,file.path(z$root,"packages/beidan/inst/python"))
  backend<-reticulate::import("beidan_backend.fundamental_probability",convert=FALSE);shared<-reticulate::import("beidan_backend.temporal_learning",convert=FALSE)
  rows<-list(list(evidence_id="e1",fixture_id=z$fixture$fixture_id,source_hash="saved-evidence",row_key="e1",issue_code="HISTORY",issue_year=2026L,label_available_ts="2026-10-03T16:29:00Z",data_available_ts="2026-10-03T16:29:00Z"))
  if(poison)rows<-c(rows,list(modifyList(rows[[1]],list(evidence_id="future",row_key="future",data_available_ts="2026-10-03T16:30:00Z"))),list(modifyList(rows[[1]],list(evidence_id="target",row_key="target",issue_code="00001"))))
  hashes<-list(fm_source_selection_inputs=beidan:::.score_margin_hash(list(native=z$native,market=z$market,review=z$review,fixture=z$fixture,cutoff=z$cutoff)),fm_source_selection_code=digest::digest(paste(deparse(SelectFmProbabilitySource),collapse="\n"),algo="sha256"),fm_source_selection_dependencies=beidan:::.score_margin_code(z$root))
  return(backend$build_adjustment_evidence_context(rows,as.list(z$fixture),shared$Cutoff$decision_epoch(z$cutoff$issue_id,z$review$cutoff_utc),hashes,shared$AvailabilityPolicy$historical_proxy("SYNTHETIC_FM16_TEST"),"HISTORICAL_DIAGNOSTIC",z$root))
}

test_that("FM16 uses exact market grid only when confidence and both market gates permit", {
  for(conf in c("low","uncertain","adequate")) for(sufficient in c(FALSE,TRUE)) for(consistent in c(FALSE,TRUE)) {
    z<-FmSourceTestFixture();z$review$confidence<-conf;z$review$market_sufficient<-sufficient;z$review$market_consistent<-consistent
    ctx<-FmSourceTestContext(z);x<-SelectFmProbabilitySource(z$native,z$market,z$review,ctx,z$fixture,z$cutoff,z$root)
    expected<-if(conf %in% c("low","uncertain")&&sufficient&&consistent)"market"else"native"
    expect_identical(x,SelectFmProbabilitySource(z$native,z$market,z$review,ctx,z$fixture,repository_root=z$root))
    expect_identical(x$selected_source,expected);expect_identical(x$base$grid,z[[expected]]$grid)
    expect_identical(x,SelectFmProbabilitySource(z$native,z$market,z$review,ctx,z$fixture,z$cutoff,z$root))
    canonical<-x$base;canonical$source_hashes$selection_receipt<-NULL
    expect_identical(x$receipt$output_hash,beidan:::.score_margin_hash(canonical))
    expect_identical(x$base$source_hashes$selection_receipt,beidan:::.score_margin_hash(x$receipt))
    expect_identical(x$receipt$output_hash_scope,"BASE_EXCLUDING_SOURCE_HASHES_SELECTION_RECEIPT")
    expect_equal(x$receipt$selected_grid_hash,beidan:::.score_margin_hash(z[[expected]]$grid))
  }
  z<-FmSourceTestFixture();ctx<-FmSourceTestContext(z);a<-SelectFmProbabilitySource(z$native,z$market,z$review,ctx,z$fixture,z$cutoff,z$root)
  b<-SelectFmProbabilitySource(z$native,z$market,z$review,FmSourceTestContext(z,TRUE),z$fixture,z$cutoff,z$root)
  expect_identical(a$base$grid,b$base$grid);expect_identical(a$selected_source,b$selected_source)
  expect_identical(a$receipt$input_hashes,b$receipt$input_hashes)
})

test_that("FM16 absent market preserves native only when market gate is false", {
  z<-FmSourceTestFixture();z$market<-NULL;z$review$market_hash<-"ABSENT";z$review$market_sufficient<-FALSE
  x<-SelectFmProbabilitySource(z$native,z$market,z$review,FmSourceTestContext(z),z$fixture,z$cutoff,z$root)
  expect_identical(x$selected_source,"native");expect_identical(x$base$grid,z$native$grid)
  z$review$market_sufficient<-TRUE
  expect_error(SelectFmProbabilitySource(z$native,z$market,z$review,FmSourceTestContext(z),z$fixture,z$cutoff,z$root),"requires joint")
})

test_that("FM16 rejects stale, changed or unbound source decisions", {
  z<-FmSourceTestFixture();ctx<-FmSourceTestContext(z)
  zz<-z;zz$review$confidence<-"adequate";expect_error(SelectFmProbabilitySource(zz$native,zz$market,zz$review,ctx,zz$fixture,zz$cutoff,zz$root),"binding")
  zz<-z;zz$market$grid$probability<-c(.1,.3,.6);expect_error(SelectFmProbabilitySource(zz$native,zz$market,zz$review,ctx,zz$fixture,zz$cutoff,zz$root),"binding")
  zz<-z;zz$cutoff$cutoff_utc<-zz$cutoff$cutoff_utc+1;expect_error(SelectFmProbabilitySource(zz$native,zz$market,zz$review,ctx,zz$fixture,zz$cutoff,zz$root),"cutoff")
  zz<-z;zz$review$evidence_ids<-"missing";expect_error(SelectFmProbabilitySource(zz$native,zz$market,zz$review,FmSourceTestContext(zz),zz$fixture,zz$cutoff,zz$root),"unavailable")
  for(kind in c("empty","na","duplicate","future","handicap","fractional","use")) {
    zz<-z
    if(kind=="empty")zz$native$grid<-zz$native$grid[0,]
    if(kind=="na")zz$native$grid$probability[1]<-NA_real_
    if(kind=="duplicate")zz$native$grid<-dplyr::bind_rows(zz$native$grid,zz$native$grid[1,])
    if(kind=="future")zz$native$max_source_available_utc<-zz$cutoff$cutoff_utc
    if(kind=="handicap")zz$native$handicap<- -1
    if(kind=="fractional")zz$native$grid$home_goals[1]<-.5
    if(kind=="use")zz$market$intended_use<-"PROSPECTIVE_DECISION"
    expect_error(SelectFmProbabilitySource(zz$native,zz$market,zz$review,ctx,zz$fixture,zz$cutoff,zz$root))
  }
  expect_error(SelectFmProbabilitySource(z$native,z$market,z$review,list(),z$fixture,z$cutoff,z$root),"Opaque")
  expect_error(SelectFmProbabilitySource(z$native,z$market,z$review,ctx,z$fixture,NULL,z$root))
  zz<-z;zz$review$market_consistent<-NA;expect_error(SelectFmProbabilitySource(zz$native,zz$market,zz$review,ctx,zz$fixture,zz$cutoff,zz$root))
  zz<-z;zz$fixture$handicap<-1;expect_error(SelectFmProbabilitySource(zz$native,zz$market,zz$review,ctx,zz$fixture,zz$cutoff,zz$root))
})
