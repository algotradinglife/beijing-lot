root<-normalizePath(Sys.getenv('FM17_MARKET_ROOT',getwd()))
ns<-new.env(parent=asNamespace('beidan'));sys.source(file.path(root,'packages/beidan/R/recaptured_market_audit.R'),envir=ns)
compare<-ns$.CompareRecapturedMarkets
comparison_snapshot<-function(values=c(1.9,2),times=c('2026-10-04 12:00:00','2026-10-04 16:00:00'),prior=c(TRUE,TRUE),companies=1L) {
 n<-length(values);h<-tibble::tibble(fixture_id=rep('26102:6',n),market=rep('euro',n),company_id=rep('281',n),quote_at=as.POSIXct(times,tz='UTC'),prior=prior,odds_home=values,odds_draw=rep(3.4,n),odds_away=rep(4,n),handicap=rep(NA_real_,n),home_decimal=rep(NA_real_,n),away_decimal=rep(NA_real_,n),line=rep(NA_real_,n),over_decimal=rep(NA_real_,n),under_decimal=rep(NA_real_,n))
 a<-list(history=h,coverage=tibble::tibble(fixture_id=rep('26102:6',3),market=c('euro','asian','totals'),qualified_companies=c(companies,0L,0L)),policy=list(max_quote_age_hours=48L),receipts=list('26102:6'=list(cutoff=list(issue_id='26102',cutoff_utc=as.POSIXct('2026-10-04 18:30:00',tz='UTC')),input_hashes=list(audit_code=paste(rep('1',64),collapse='')))))
 list(audit=a,object_sha256=digest::digest(a,algo='sha256'))
}

test_that('older overlapping prices quarantine a better-covered new capture',{
 a<-comparison_snapshot();b<-comparison_snapshot(c(1.8,2.1,2.2),c('2026-10-04 12:00:00','2026-10-04 16:00:00','2026-10-04 17:00:00'),rep(TRUE,3),companies=2L)
 x<-compare(a,b)
 expect_true(x$ledger$conflict);expect_equal(x$ledger$selected,'offline')
 expect_equal(nrow(x$conflicts),2L)
 expect_true('2026-10-04 12:00:00' %in% as.character(x$conflicts$quote_at))
 expect_equal(x$ledger$reason,'PRICE_CONFLICT_NEW_QUARANTINED')
})

test_that('duplicate occurrences are reconciled as sets and future prices excluded',{
 a<-comparison_snapshot();b<-comparison_snapshot(c(1.9,1.9,2),c('2026-10-04 12:00:00','2026-10-04 12:00:00','2026-10-04 16:00:00'),rep(TRUE,3),companies=2L)
 x<-compare(a,b);expect_equal(nrow(x$conflicts),0L);expect_equal(x$ledger$selected,'recaptured')
 f<-comparison_snapshot(c(1.9,2,9),c('2026-10-04 12:00:00','2026-10-04 16:00:00','2026-10-04 18:30:00'),c(TRUE,TRUE,FALSE),companies=2L)
 z<-compare(a,f);expect_equal(z$ledger,x$ledger);expect_equal(nrow(z$conflicts),0L)
 conflict<-comparison_snapshot(c(1.8,1.9,2),c('2026-10-04 12:00:00','2026-10-04 12:00:00','2026-10-04 16:00:00'),rep(TRUE,3),companies=2L)
 q<-compare(a,conflict);expect_true(q$ledger$conflict);expect_equal(q$conflicts$new_occurrences,2L)
 tie<-compare(a,a);expect_equal(tie$ledger$selected,'offline')
})

test_that('comparison rejects detached objects and incompatible cutoff bindings',{
 a<-comparison_snapshot();b<-a;b$audit$history$odds_home[1]<-9
 expect_error(compare(a,b),'object binding')
 b<-a;b$audit$receipts[[1]]$cutoff<-NULL;b$object_sha256<-digest::digest(b$audit,algo='sha256')
 expect_error(compare(a,b),'explicit cutoff')
 b<-a;b$audit$receipts[[1]]$cutoff$cutoff_utc<-b$audit$receipts[[1]]$cutoff$cutoff_utc+60;b$object_sha256<-digest::digest(b$audit,algo='sha256')
 expect_error(compare(a,b),'cutoff or code')
 b<-comparison_snapshot(prior=c(TRUE,TRUE),times=c('2026-10-04 12:00:00','2026-10-05 16:00:00'))
 expect_error(compare(a,b),'violate cutoff')
 b<-a;b$audit$receipts[[1]]$shared<-list(cutoff_ts='2026-10-04T19:30:00+00:00');b$object_sha256<-digest::digest(b$audit,algo='sha256')
 expect_error(compare(a,b),'Shared cutoff')
})
