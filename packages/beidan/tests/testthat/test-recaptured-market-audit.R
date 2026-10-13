root <- normalizePath(Sys.getenv('FM17_MARKET_ROOT',getwd()))
ns <- new.env(parent=asNamespace('beidan'))
sys.source(file.path(root,'packages/beidan/R/recaptured_market_audit.R'),envir=ns)
inspect <- ns$.InspectRecapturedMarkets

market_inputs <- function() {
 scope<-tibble::tibble(home_id='146',away_id='138',fixture_id='26102:6',issue_id='26102',provider_id_nowscore='3014103',home_nowscore='Home',away_nowscore='Away',kickoff_at='2026-10-05T18:30:00+00:00',cutoff_utc=as.POSIXct('2026-10-04 18:30:00',tz='UTC'))
 fixture<-as.list(scope[1,c('fixture_id','provider_id_nowscore','home_nowscore','away_nowscore','kickoff_at')])
 euro<-list(fixture_id='26102:6',company_id='281',quote_at='2026-10-04T16:00:00+00:00',odds_home=1.9,odds_draw=3.4,odds_away=4,source_url='https://1x2d.titan007.com/3014103.js')
 other<-euro;other$company_id<-'999';other$quote_at<-'2026-10-04T17:00:00+00:00'
 old<-euro;old$company_id<-'115';old$quote_at<-'2026-10-01T16:00:00+00:00'
 asian<-list(fixture_id='26102:6',company_id='8',quote_at='2026-10-04T16:00:00+00:00',handicap=-.5,home_decimal=1.9,away_decimal=1.95,source_url='https://m.titan007.com/HandicapDataInterface.ashx')
 total<-list(fixture_id='26102:6',company_id='8',quote_at='2026-10-04T16:00:00+00:00',line=2.5,over_decimal=1.9,under_decimal=1.95,source_url='https://m.titan007.com/HandicapDataInterface.ashx')
 p<-list(fixture=fixture,expected_team_ids=list(home_id='146',away_id='138'),identity_status='EXACT',euro=list(euro,other,old),asian=list(asian),totals=list(total))
 list(scope=scope,packets=list('26102:6'=p),policy=list(max_quote_age_hours=48,euro_companies=c('281','115','82','432')))
}

test_that('market audit separates age, basket and identity without losing channels',{
 x<-market_inputs();a<-inspect(x$scope,x$packets,x$policy,root)
 expect_s3_class(a$history,'tbl_df');expect_s3_class(a$latest,'tbl_df');expect_s3_class(a$coverage,'tbl_df')
 expect_equal(nrow(a$history),5L);expect_equal(nrow(a$coverage),3L)
 e<-a$coverage[a$coverage$market=='euro',]
 expect_equal(e$fresh_companies,2L);expect_equal(e$supported_fresh_companies,1L);expect_equal(e$qualified_companies,1L)
 expect_equal(a$latest$age_hours[a$latest$company_id=='281'],2.5)
 expect_true(all(a$coverage$status=='QUALIFIED_PROXY'))
 expect_identical(inspect(x$scope,x$packets,x$policy,root),a)
 x$packets[[1]]$identity_status<-'NAME_OR_CLOCK_CONFLICT'
 z<-inspect(x$scope,x$packets,x$policy,root)
 expect_true(all(z$coverage$qualified_companies==0L));expect_true(all(z$coverage$status=='IDENTITY_REVIEW_REQUIRED'))
 expect_equal(nrow(z$latest),5L)
})

test_that('a missing market preserves typed independently valid channels',{
 x<-market_inputs();x$packets[[1]]$euro<-list()
 a<-inspect(x$scope,x$packets,x$policy,root)
 expect_equal(a$coverage$status[a$coverage$market=='euro'],'NO_PARSED_QUOTES')
 expect_equal(a$coverage$qualified_companies[a$coverage$market!='euro'],c(1L,1L))
 expect_type(a$history$odds_home,'double');expect_s3_class(a$history$quote_at,'POSIXct')
 x$packets[[1]]$asian<-list();x$packets[[1]]$totals<-list()
 z<-inspect(x$scope,x$packets,x$policy,root)
 expect_equal(nrow(z$history),0L);expect_type(z$history$sequence,'integer')
 expect_true(all(z$coverage$status=='NO_PARSED_QUOTES'))
})

test_that('cutoff and future quote mutations cannot replace prior selection',{
 x<-market_inputs();a<-inspect(x$scope,x$packets,x$policy,root)
 future<-x$packets[[1]]$euro[[1]];future$quote_at<-'2026-10-04T18:30:00+00:00';future$odds_home<-9
 x$packets[[1]]$euro[[4]]<-future
 future$quote_at<-'2026-10-06T18:30:00+00:00';x$packets[[1]]$euro[[5]]<-future
 z<-inspect(x$scope,x$packets,x$policy,root)
 expect_equal(nrow(z$history),7L);expect_equal(sum(z$history$prior),5L)
 expect_equal(z$latest,a$latest)
 expect_false(identical(z$receipts[[1]]$shared$cache_key,a$receipts[[1]]$shared$cache_key))
 x$scope$cutoff_utc<-as.POSIXct('2026-09-30 18:30:00',tz='UTC')
 n<-inspect(x$scope,x$packets,x$policy,root)
 expect_equal(nrow(n$latest),0L);expect_true(all(n$coverage$status=='NO_PRIOR_QUOTES'))
})

test_that('data contracts reject malformed scope, prices and clocks',{
 x<-market_inputs();z<-x;z$scope$cutoff_utc<-NULL
 expect_error(inspect(z$scope,z$packets,z$policy,root),'cutoff scope')
 z<-x;z$scope$cutoff_utc[1]<-NA
 expect_error(inspect(z$scope,z$packets,z$policy,root),'typed cutoff')
 z<-x;z$packets[[1]]$fixture$home_nowscore<-'Other'
 expect_error(inspect(z$scope,z$packets,z$policy,root),'binding differs')
 z<-x;z$packets[[1]]$euro[[1]]$quote_at<-'2026-10-04 16:00:00'
 expect_error(inspect(z$scope,z$packets,z$policy,root),'timezone')
 z<-x;z$packets[[1]]$euro[[1]]$odds_home<-1
 expect_error(inspect(z$scope,z$packets,z$policy,root),'exceed one')
 z<-x;z$packets[[1]]$asian[[1]]$handicap<-.2
 expect_error(inspect(z$scope,z$packets,z$policy,root),'Quarter-goal')
 z<-x;z$packets[[1]]$euro[[1]]$fixture_id<-'26102:7'
 expect_error(inspect(z$scope,z$packets,z$policy,root),'Quote fixture')
 expect_error(inspect(x$scope,x$packets[FALSE],x$policy,root),'Exact packet scope')
})
