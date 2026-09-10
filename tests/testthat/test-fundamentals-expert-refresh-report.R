source('../../r/fundamentals_expert_refresh_report.R')
testthat::test_that('refresh comparison pairs eligible predictions and measures abstention', {
  d <- tempfile();dir.create(d);dir.create(file.path(d,'evaluation'))
  write <- function(x,p) jsonlite::write_json(x,file.path(d,p),auto_unbox=TRUE,na='null',dataframe='rows')
  f <- tibble::tibble(issue_code='002',slot=1:3,provider_id=c('a','b','c'),handicap=-2,baseline_draw=.2,baseline_cover=.4)
  write(list(test_issues=list('002')),'contract.json');write(f,'test-features.json')
  write(tibble::tibble(provider_id='c'),'training-data.json')
  write(list(labels=dplyr::mutate(f,actual_home=c(2,3,2),actual_away=0,label_status='COMPLETED') |> dplyr::select(issue_code,slot,provider_id,actual_home,actual_away,label_status)),'test-labels.json')
  for(v in c('old','new')) {
    write(list(rows=dplyr::mutate(f,draw_target_probability=c(.3,.4,.5),draw_signal=c('POSITIVE','NEGATIVE','ABSTAIN')) |> dplyr::select(issue_code,slot,provider_id,draw_target_probability,draw_signal)),paste0('evaluation/',v,'_draw.json'))
    write(list(rows=dplyr::mutate(f,high_probability=c(.2,NA,.5),high_signal='ABSTAIN') |> dplyr::select(issue_code,slot,provider_id,high_probability,high_signal)),paste0('evaluation/',v,'_high.json'))
  }
  x <- summarize_expert_refresh(d,verify_fn=function(...) TRUE)
  testthat::expect_equal(x$summary$n,c(2L,2L,1L,1L))
  testthat::expect_equal(x$summary$brier,c(.325,.325,.04,.04))
  testthat::expect_equal(x$signals$precision[x$signals$expert=='draw'],rep(1,4))
  testthat::expect_equal(x$exclusions$n[x$exclusions$reason=='TRAIN_TEST_GAME_OVERLAP'],1L)
  write(dplyr::bind_rows(f,f[1,]),'test-features.json')
  testthat::expect_error(summarize_expert_refresh(d,verify_fn=function(...) TRUE),'Duplicate')
})

testthat::test_that('report requires an explicit verifier runtime', {
  testthat::expect_error(verify_expert_refresh_report('x',''),'Explicit project Python')
  testthat::expect_error(summarize_expert_refresh('x',verify_fn=function(...) FALSE),'verification')
})
