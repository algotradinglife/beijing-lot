root <- normalizePath('../..')
source(file.path(root,'r/fundamentals_n7_baseline.R'))
source(file.path(root,'r/fundamentals_n7_twocover.R'))
testthat::test_that('two-cover summary preserves common cohort and detects tampering', {
  d <- tempfile();dir.create(d)
  for(n in c('inputs','plans')) writeLines('{}',file.path(d,paste0(n,'.json')))
  jsonlite::write_json(list(training_issues='100101'),file.path(d,'contract.json'),auto_unbox=TRUE)
  rows <- data.frame(issue='100101',strategy=c('BASE','DOUBLE_STAKE','TWO_COVER'),funding='UNIT',
    status='COMPLETE',stake=c(256,512,512),gross=c(400,800,600),net=c(144,288,88),roi=c(144/256,288/512,88/512),
    ideal_gross=c(400,800,600),hits=c(1,1,2),groups=c(1,1,2),issue_anchor_ts='2010-01-01T00:00:00Z')
  x <- list(results=rows,r_implementation=n7_baseline_r_receipt(root))
  paths <- c('r/fundamentals_n7_twocover.R','scripts/settle_fundamentals_n7_twocover.R')
  x$report_implementation <- stats::setNames(lapply(file.path(root,paths),digest::digest,file=TRUE,algo='sha256'),paths)
  for(n in c('inputs','plans','contract')) x[[paste0(n,'_sha256')]] <- digest::digest(file=file.path(d,paste0(n,'.json')),algo='sha256')
  jsonlite::write_json(x,file.path(d,'settlement.json'),dataframe='rows',auto_unbox=TRUE)
  y <- n7_twocover_report(d,root)
  testthat::expect_equal(nrow(y$summary),6L)
  testthat::expect_true(all(y$summary$any_hit_issues==1))
  x$results$status <- 'PENDING_AUDIT_OR_WINNING_SP'
  jsonlite::write_json(x,file.path(d,'settlement.json'),dataframe='rows',auto_unbox=TRUE)
  testthat::expect_equal(nrow(n7_twocover_report(d,root)$summary),0L)
  writeLines('changed',file.path(d,'plans.json'))
  testthat::expect_error(n7_twocover_report(d,root))
})
