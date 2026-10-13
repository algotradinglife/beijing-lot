# Helpers are exercised by normal, mirrored and failure-path integration cases.
half_market_fixture <- function(root) {
 cutoff<-list(issue_id='00001',cutoff_utc=as.POSIXct('2026-09-24 10:30:00',tz='UTC'))
 fixture<-tibble::tibble(fixture_id='00001:4',issue_id='00001',home='H',away='A')
 qtime<-cutoff$cutoff_utc-3600
 po<-stats::ppois(2,2.6,lower.tail=FALSE)
 list(root=root,cutoff=cutoff,fixture=fixture,asian=tibble::tibble(company_id='8',fixture_id=fixture$fixture_id,quote_at=qtime,handicap=-.5,home_decimal=2,away_decimal=2),totals=tibble::tibble(fixture_id=fixture$fixture_id,company_id='8',quote_at=qtime,line=2.5,over_decimal=1/po,under_decimal=1/(1-po)),policy=list(rho=-.1,total_bounds=c(.1,16),lambda_floor=.05,tail_tolerance=1e-10,max_quote_age_hours=24))
}
half_market_context <- function(z) {
 reticulate::use_python(file.path(z$root,'.venv/bin/python'),required=TRUE)
 reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(z$root,'packages/beidan/inst/python'))
 backend<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
 shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
 hashes<-list(partial_input=.score_margin_hash(list(asian=z$asian,totals=z$totals,policy=z$policy,fixture=z$fixture,cutoff=z$cutoff)),partial_code=digest::digest(paste(deparse(.ProjectHalfAsianTotalDc),collapse='\n'),algo='sha256'),direction_implementation=.score_margin_code(z$root),partial_total_code=.score_margin_hash(lapply(list(total_market_constraint,asian_total_probability),function(f)paste(deparse(f),collapse='\n'))))
 rows<-list()
 for(kind in c('asian','totals')) {
  q<-z[[kind]];ts<-format(q$quote_at,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')
  rows[[kind]]<-list(evidence_id=paste0(kind,'-8'),fixture_id=z$fixture$fixture_id,source_hash=.score_margin_hash(q),row_key=paste0(kind,'-8'),issue_code='QUOTE_PROXY',issue_year=2026L,label_available_ts=ts,data_available_ts=ts)
 }
 backend$build_adjustment_evidence_context(unname(rows),as.list(z$fixture),shared$Cutoff$decision_epoch(z$fixture$issue_id,format(z$cutoff$cutoff_utc,'%Y-%m-%dT%H:%M:%SZ',tz='UTC')),hashes,shared$AvailabilityPolicy$historical_proxy('TEST_PARTIAL_MARKET'),'HISTORICAL_DIAGNOSTIC',z$root)
}

test_that('half Asian plus total identifies a fresh DC mean without Euro data', {
 root<-Sys.getenv('FM17_DIAG_BACKEND');stopifnot(nzchar(root))
 z<-half_market_fixture(root);ctx<-half_market_context(z)
 p<-.ProjectHalfAsianTotalDc(z$asian,z$totals,z$policy,ctx,z$fixture,z$cutoff,z$root)
 expect_s3_class(p$grid,'tbl_df');expect_s3_class(p$parameters,'tbl_df')
 expect_equal(p$parameters$total_mean,2.6,tolerance=1e-8)
 expect_equal(sum(p$grid$probability),1,tolerance=1e-12)
 expect_equal(p$asian_target,.5);expect_equal(p$asian_model,.5,tolerance=1e-8)
 expect_equal(sum(p$grid$probability[p$grid$home_goals>p$grid$away_goals]),.5,tolerance=1e-8)
 expect_gt(p$parameters$lambda_home,p$parameters$lambda_away)
 expect_identical(p$receipt$cutoff,z$cutoff);expect_identical(p$receipt$cache_reuse,'NONE')
 expect_identical(p,.ProjectHalfAsianTotalDc(z$asian,z$totals,z$policy,ctx,z$fixture,z$cutoff,z$root))
 z$asian$handicap<-.5;mirrored<-.ProjectHalfAsianTotalDc(z$asian,z$totals,z$policy,half_market_context(z),z$fixture,z$cutoff,z$root)
 expect_equal(mirrored$parameters$lambda_home,p$parameters$lambda_away,tolerance=1e-7)
 expect_equal(mirrored$parameters$lambda_away,p$parameters$lambda_home,tolerance=1e-7)
})

test_that('partial market refuses unsupported, stale and detached quote inputs', {
 root<-Sys.getenv('FM17_DIAG_BACKEND');stopifnot(nzchar(root))
 z<-half_market_fixture(root);ctx<-half_market_context(z)
 for(h in c(0,-.25,-.75)) {
  q<-z$asian;q$handicap<-h
  expect_error(.ProjectHalfAsianTotalDc(q,z$totals,z$policy,ctx,z$fixture,z$cutoff,z$root),'Half-goal')
 }
 q<-z$asian;q$quote_at<-z$cutoff$cutoff_utc
 expect_error(.ProjectHalfAsianTotalDc(q,z$totals,z$policy,ctx,z$fixture,z$cutoff,z$root),'fresh quote')
 q$quote_at<-z$cutoff$cutoff_utc-25*3600
 expect_error(.ProjectHalfAsianTotalDc(q,z$totals,z$policy,ctx,z$fixture,z$cutoff,z$root),'fresh quote')
 q<-z$totals;q$line<-2.25
 expect_error(.ProjectHalfAsianTotalDc(z$asian,q,z$policy,ctx,z$fixture,z$cutoff,z$root),'Supported total')
 q<-z$asian;q$home_decimal<-NA_real_
 expect_error(.ProjectHalfAsianTotalDc(q,z$totals,z$policy,ctx,z$fixture,z$cutoff,z$root))
 expect_error(.ProjectHalfAsianTotalDc(z$asian[0,],z$totals,z$policy,ctx,z$fixture,z$cutoff,z$root))
 q<-z$asian;q$home_decimal<-1
 expect_error(.ProjectHalfAsianTotalDc(q,z$totals,z$policy,ctx,z$fixture,z$cutoff,z$root),'Decimal')
 q<-z$asian;q$home_decimal<-2.1
 expect_error(.ProjectHalfAsianTotalDc(q,z$totals,z$policy,ctx,z$fixture,z$cutoff,z$root),'binding')
 p<-z$policy;p$lambda_floor<-1.5
 expect_error(.ProjectHalfAsianTotalDc(z$asian,z$totals,p,ctx,z$fixture,z$cutoff,z$root),'binding')
 zz<-z;zz$policy$lambda_floor<-1.5
 expect_error(.ProjectHalfAsianTotalDc(zz$asian,zz$totals,zz$policy,half_market_context(zz),zz$fixture,zz$cutoff,zz$root),'Feasible')
 zz<-z;zz$asian$home_decimal<-10000
 expect_error(.ProjectHalfAsianTotalDc(zz$asian,zz$totals,zz$policy,half_market_context(zz),zz$fixture,zz$cutoff,zz$root),'Interior')
 f<-z$fixture;f$handicap<-0L
 expect_error(.ProjectHalfAsianTotalDc(z$asian,z$totals,z$policy,ctx,f,z$cutoff,z$root))
})
