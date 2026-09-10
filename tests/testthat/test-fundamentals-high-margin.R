source('../../r/fundamentals_high_margin.R')
testthat::test_that('large historical wins use team orientation and strict margin', {
 x <- tibble::tibble(home_id=c('a','b','a'),away_id=c('b','a','c'),
                    home_goals=c(3,0,2),away_goals=c(0,4,0))
 testthat::expect_equal(historical_large_margin_rate(x,2,"a"),2/3)
 testthat::expect_equal(historical_large_margin_rate(x,3,"a"),1/3)
 testthat::expect_error(historical_large_margin_rate(x,2,'wrong'),'identity')
 bad <- x;bad$away_id[1] <- 'a'
 testthat::expect_error(historical_large_margin_rate(bad,2,'a'),'identity')
 testthat::expect_error(historical_large_margin_rate(x[0,],2,"a"),'window')
 x$home_goals[1] <- NA_real_
 testthat::expect_error(historical_large_margin_rate(x,2,"a"),'scores')
})
testthat::test_that('giving side depends on handicap, not league superiority', {
 x <- tibble::tibble(issue='001',slot=1:4,provider_id=as.character(1:4),
  home_tier=c(2,1,1,1),away_tier=c(1,2,1,1),handicap=c(-2,2,-2,-1),
  W=.4,D=.3,L=.3,market_total=2.5,overall_expected_net=c(2,-2,2,1),
  venue_expected_net=c(3,-3,3,1),ppg_overall_difference=c(.5,-.5,.5,0),
  ppg_venue_difference=c(.8,-.8,.8,0))
 z <- high_margin_features(x)
 testthat::expect_equal(z$giving_home,c(TRUE,FALSE,TRUE,NA))
 testthat::expect_equal(z$giving_handicap[1:3],rep(-2,3))
 testthat::expect_equal(z$giving_market_cover[1:3],c(.4,.3,.4))
 testthat::expect_equal(z$giving_overall_margin[1:3],rep(0,3))
 testthat::expect_equal(z$status,c(rep('LARGE_HANDICAP',3),'OUTSIDE_SCOPE'))
 testthat::expect_error(high_margin_features(dplyr::bind_rows(x,x)),'identities')
 x$D[1] <- .8
 testthat::expect_error(high_margin_features(x),'distribution')
})
testthat::test_that('large handicap expert limits scope and retains abstention semantics', {
 root <- normalizePath('../..')
 paths <- stats::setNames(c(tempfile(fileext='.json'),tempfile(fileext='.json')),c('draw-threshold-v1','draw-binary-v1'))
 for(tag in names(paths)) {
   con <- gzfile(file.path(root,'tests/fixtures/high_margin_legacy',paste0(tag,'.json.gz')),'rt')
   writeLines(readLines(con,warn=FALSE),paths[[tag]]);close(con)
 }
 a <- paths[['draw-threshold-v1']];b <- paths[['draw-binary-v1']]
 cuts <- jsonlite::read_json(a,simplifyVector=TRUE)$comparison$receipt$cutoffs
 z <- explore_high_margin_expert(b,a,cuts,'SAMPLE_IN_EXPLORATION_ONLY',root)
 testthat::expect_equal(nrow(z$scope),23L)
 testthat::expect_equal(sum(z$scope$eligible),8L)
 testthat::expect_equal(nrow(z$predictions),8L)
 testthat::expect_equal(sum(z$predictions$covered),4L)
 testthat::expect_true(all(z$leaves$n>=3))
 testthat::expect_lte(nrow(z$leaves),2L)
 testthat::expect_equal(z$leaves$probability,(z$leaves$covers+1)/(z$leaves$n+2))
 testthat::expect_equal(z$predictions$covered,z$predictions$actual==z$predictions$cover_direction)
 testthat::expect_false(z$receipt$deployable)
 testthat::expect_error(explore_high_margin_expert(b,a,cuts,'',root),'exception')
 testthat::expect_error(explore_high_margin_expert(b,a,list(),'SAMPLE_IN_EXPLORATION_ONLY',root),'Cutoff')
 testthat::expect_error(explore_high_margin_expert(b,a,cuts,'SAMPLE_IN_EXPLORATION_ONLY',root,c(.8,.2)),'bounds')
 saved <- jsonlite::read_json(a,simplifyVector=TRUE)
 saved$binary$fixtures <- saved$binary$fixtures[nrow(saved$binary$fixtures):1,]
 tmp <- tempfile(fileext='.json');on.exit(unlink(tmp))
 jsonlite::write_json(saved,tmp,auto_unbox=TRUE,dataframe='rows',digits=15)
 other <- explore_high_margin_expert(b,tmp,cuts,'SAMPLE_IN_EXPLORATION_ONLY',root)
 testthat::expect_equal(z$predictions,other$predictions)
 bad <- saved;bad$comparison$fixtures$handicap[1] <- -3
 jsonlite::write_json(bad,tmp,auto_unbox=TRUE,dataframe='rows',digits=15)
 testthat::expect_error(explore_high_margin_expert(b,tmp,cuts,'SAMPLE_IN_EXPLORATION_ONLY',root),'orientation/handicap')
 bad <- saved;bad$comparison$receipt$source_ou_receipt$source_market_receipt$selected_windows[['100101/3']]$home_team_id <- 'wrong'
 jsonlite::write_json(bad,tmp,auto_unbox=TRUE,dataframe='rows',digits=15)
 testthat::expect_error(explore_high_margin_expert(b,tmp,cuts,'SAMPLE_IN_EXPLORATION_ONLY',root),'orientation')
})
testthat::test_that('goal structure separates allocation from total and orients away giving team', {
 x <- tibble::tibble(giving_home=c(TRUE,FALSE),giving_handicap=c(-2,-2),
   lambda_home=c(3,1.5),lambda_away=c(0,1.5),finite_mean_total=c(3,3))
 for(side in c('home','away')) for(view in c('overall','venue')) {
   x[[paste(side,view,'goals_for_pg',sep='_')]] <- if(side=='home') c(2,1) else c(1,2)
   x[[paste(side,view,'goals_against_pg',sep='_')]] <- if(side=='home') c(.5,1.5) else c(1.5,.5)
 }
 z <- high_margin_goal_structure(x)
 testthat::expect_equal(z$giving_expected_goals,c(3,1.5))
 testthat::expect_equal(z$receiving_expected_goals,c(0,1.5))
 testthat::expect_equal(z$giving_goal_share,c(1,.5))
 testthat::expect_equal(z$market_net_to_line,c(1,-2))
 testthat::expect_equal(z$giving_venue_goals_for_pg,c(2,2))
 testthat::expect_equal(z$receiving_overall_goals_against_pg,c(1.5,1.5))
 bad <- x;bad$lambda_home[1] <- -1
 testthat::expect_error(high_margin_goal_structure(bad),'Invalid')
 bad <- x;bad$finite_mean_total[1] <- 4
 testthat::expect_error(high_margin_goal_structure(bad),'Invalid')
 bad <- x;bad$away_overall_goals_for_pg[1] <- NA_real_
 testthat::expect_error(high_margin_goal_structure(bad),'Invalid')
})
testthat::test_that('feature ablations use explicit fixed sets on the same sample', {
 root <- normalizePath('../..')
 paths <- stats::setNames(c(tempfile(fileext='.json'),tempfile(fileext='.json')),c('draw-threshold-v1','draw-binary-v1'))
 for(tag in names(paths)) {
   con <- gzfile(file.path(root,'tests/fixtures/high_margin_legacy',paste0(tag,'.json.gz')),'rt')
   writeLines(readLines(con,warn=FALSE),paths[[tag]]);close(con)
 }
 a <- paths[['draw-threshold-v1']];b <- paths[['draw-binary-v1']]
 cuts <- jsonlite::read_json(a,simplifyVector=TRUE)$comparison$receipt$cutoffs
 total <- explore_high_margin_expert(b,a,cuts,'SAMPLE_IN_EXPLORATION_ONLY',root,feature_set='total_only')
 goals <- explore_high_margin_expert(b,a,cuts,'SAMPLE_IN_EXPLORATION_ONLY',root,feature_set='goal_structure')
 testthat::expect_identical(total$receipt$features,'market_total')
 testthat::expect_false('market_total' %in% goals$receipt$features)
 testthat::expect_true(all(c('giving_expected_goals','receiving_expected_goals') %in% goals$receipt$features))
 testthat::expect_equal(total$predictions[c('issue','slot','provider_id','covered')],goals$predictions[c('issue','slot','provider_id','covered')])
 testthat::expect_error(explore_high_margin_expert(b,a,cuts,'SAMPLE_IN_EXPLORATION_ONLY',root,feature_set='bad'),'feature set')
})
