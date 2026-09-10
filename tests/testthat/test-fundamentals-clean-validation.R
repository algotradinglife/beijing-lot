for(m in c('probability_exploration','fundamentals_home_away','goal_distribution_experiment',
 'fundamentals_score_diagnostic','fundamentals_score_shape','fundamentals_high_margin','fundamentals_three_issue_experts',
 'fundamentals_market_comparison','fundamentals_total_market','fundamentals_retraining','eight_issue_holdout','fundamentals_clean_validation'))
 source(file.path('..','..','r',paste0(m,'.R')))
testthat::test_that('approved diagnostic inputs reuse baseline and market projections', {
 con <- gzfile(file.path('..','fixtures','clean_validation_input.json.gz'),'rt')
 input <- jsonlite::fromJSON(paste(readLines(con,warn=FALSE),collapse=''),simplifyVector=FALSE)$input;close(con)
 x <- project_clean_validation_input(input,1e-10)
 testthat::expect_equal(nrow(x$features),1)
 testthat::expect_equal(x$features$lambda_home,2)
 testthat::expect_equal(x$features$lambda_away,1)
 testthat::expect_equal(x$features$home_venue_goals_for_pg,2)
 testthat::expect_equal(sum(x$control$scores$probability),1)
 testthat::expect_equal(sum(x$market$grids[['100101/1']]$probability),1)
 testthat::expect_equal(x$features$predictor_clock_ts,'2010-01-01T11:00:00+00:00')
 testthat::expect_true(is.finite(x$features$market_total))
 bad <- input;bad$cutoffs[['1']] <- '2010-01-02T12:00:00Z'
 testthat::expect_error(project_clean_validation_input(bad,1e-10),'cutoff')
 bad <- input;bad$market$rows[[1]]$status <- 'QUARANTINED_IDENTITY';bad$clocks <- list()
 z <- project_clean_validation_input(bad,1e-10)
 testthat::expect_equal(nrow(z$features),0)
 testthat::expect_equal(nrow(z$control$fixtures),0)
 bad <- input;bad$forms$windows[[1]]$status <- 'INSUFFICIENT_HISTORY'
 testthat::expect_equal(project_clean_validation_input(bad,1e-10)$status,'NO_BASELINE')
 bad <- input;bad$clocks <- list()
 testthat::expect_error(project_clean_validation_input(bad,1e-10),'Missing prior')
})

source(file.path('..','..','r','fundamentals_clean_settlement.R'))

testthat::test_that('SPF-only settlement binds identity handicap and final score', {
 f <- tibble::tibble(issue='100402',slot=1L,provider_id='1',handicap=-1,home='H',away='A',actual_home=3,actual_away=1,result_state='完场')
 z <- tibble::tibble(issue='100402',slot=1L,play='spf',native_match_id='1',handicap_raw='-1',score='3:1',option=c('胜','平','负'),sp=c(2,3,4),source_sha256='abc')
 x <- clean_validation_spf_audit(z,f)
 testthat::expect_equal(x$status,'READY');testthat::expect_equal(x$spf_sp,2);testthat::expect_equal(x$actual_direction,'W')
 bad <- z;bad$handicap_raw <- '0'
 testthat::expect_match(clean_validation_spf_audit(bad,f)$status,'IDENTITY')
 bad <- z;bad$native_match_id <- '2'
 testthat::expect_match(clean_validation_spf_audit(bad,f)$status,'IDENTITY')
 bad <- z;bad$score <- '1:1'
 testthat::expect_match(clean_validation_spf_audit(bad,f)$status,'IDENTITY')
 bad <- z;bad$sp[1] <- NA_real_
 testthat::expect_match(clean_validation_spf_audit(bad,f)$status,'MISSING_WINNING_SP')
 testthat::expect_true(is.na(clean_validation_spf_audit(bad,f)$spf_sp))
 bad <- f;bad$result_state <- '推迟';bad$actual_home <- NA_real_
 testthat::expect_match(clean_validation_spf_audit(z,bad)$status,'IDENTITY')
 testthat::expect_error(clean_validation_spf_audit(dplyr::bind_rows(z,z),f),'Unique')
 testthat::expect_error(clean_validation_spf_audit(z,dplyr::bind_rows(f,f)),'Unique')
 blank <- z;blank$handicap_raw <- ''
 testthat::expect_match(clean_validation_spf_audit(blank,f)$status,'IDENTITY')
 zero <- f;zero$handicap <- 0
 accepted <- clean_validation_spf_audit(blank,zero)
 testthat::expect_equal(accepted$status,'READY')
 testthat::expect_equal(accepted$handicap_evidence,'EXPLICIT_ROSTER_ZERO_DB_FIELD_BLANK')
 blank$handicap_raw <- NA_character_
 testthat::expect_match(clean_validation_spf_audit(blank,zero)$status,'IDENTITY')
})
