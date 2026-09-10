source(file.path('..','..','r','fundamentals_n7_baseline.R'))
testthat::test_that('N7 summaries preserve common denominators and downside', {
  x <- tidyr::expand_grid(issue=c('a','b'),selector=c('COVERAGE','VALUE'),shape=c('C0E0','C1E2','C1E3'),funding=c('UNIT','MATCHED'))
  x <- dplyr::mutate(x,stake=100,gross=ifelse(issue=='a',150,0),net=gross-stake,roi=net/stake,hits=as.integer(gross>0),groups=1L,ideal_gross=gross,status='COMPLETE',issue_anchor_ts=ifelse(issue=='a','2010-01-01','2010-01-02'))
  y <- n7_baseline_summary(x,'a',file.path('..','..'))
  z <- dplyr::filter(y$summary,partition=='ALL')
  testthat::expect_equal(nrow(z),12L)
  testthat::expect_true(all(z$roi == -.25 & z$max_drawdown_cny==100 & z$ex_largest_payout_net == -100))
  x$status[1] <- 'PENDING_WINNING_SP'
  y <- n7_baseline_summary(x,'a',file.path('..','..'))
  testthat::expect_equal(nrow(y$per_issue),24L)
  testthat::expect_true(all(y$summary$issues==1L))
  x$status[] <- 'PENDING_WINNING_SP'
  empty <- n7_baseline_summary(x,'a',file.path('..','..'))
  testthat::expect_equal(nrow(dplyr::filter(empty$summary,partition=='ALL')),0L)
  testthat::expect_setequal(names(empty$summary),names(z))
  testthat::expect_equal(nrow(empty$per_issue),24L)
  testthat::expect_error(n7_baseline_summary(x[-1,],'a',file.path('..','..')),'12')
  testthat::expect_error(n7_baseline_summary(dplyr::bind_rows(x,x[1,]),'a',file.path('..','..')),'Unique')
})
testthat::test_that('N7 settlement rejects a modified archive before database access', {
  p <- tempfile();dir.create(p)
  jsonlite::write_json(list(settlement_opened=FALSE),file.path(p,'contract.json'),auto_unbox=TRUE)
  jsonlite::write_json(list(historical_admission=FALSE,source_hashes=setNames(list('wrong'),file.path(p,'contract.json'))),file.path(p,'inputs.json'),auto_unbox=TRUE)
  testthat::expect_error(settle_n7_baseline_study(p,'missing','missing',file.path('..','..')),'Archived input changed')
})

testthat::test_that('R provenance binds audit and summary implementations', {
  root <- file.path('..','..');a <- n7_baseline_r_receipt(root)
  tmp <- tempfile();dir.create(tmp)
  for(p in names(a)) {dir.create(dirname(file.path(tmp,p)),recursive=TRUE,showWarnings=FALSE);file.copy(file.path(root,p),file.path(tmp,p))}
  testthat::expect_identical(n7_baseline_r_receipt(tmp),a)
  cat('\n# changed audit',file=file.path(tmp,'r/fundamentals_returns.R'),append=TRUE)
  testthat::expect_false(identical(n7_baseline_r_receipt(tmp),a))
  testthat::expect_error(n7_baseline_r_receipt(file.path(tmp,'missing')))
})
