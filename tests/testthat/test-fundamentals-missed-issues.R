source(file.path('..','..','r','fundamentals_missed_issues.R'))
testthat::test_that('frozen holdings distinguish single/double misses and reuse',{
 l <- tibble::tibble(issue='001',group=rep(1:2,each=7),slot=rep(1:7,2),
   provider_id=rep(sprintf('%03d',1:7),2),handicap=0,support=rep(c('3','3',rep('31',5)),2))
 a <- dplyr::distinct(l,issue,slot,provider_id,handicap) |>
   dplyr::mutate(status='READY',actual_direction=c('L',rep('W',6)))
 x <- missed_issue_diagnostics(l,a)
 testthat::expect_equal(x$groups$single_misses,c(1L,1L))
 testthat::expect_equal(x$issues$winning_groups,0L)
 testthat::expect_equal(x$issues$nearest_misses,1L)
 testthat::expect_equal(x$fixtures$groups_missed,c(2L,rep(0L,6)))
 testthat::expect_identical(x$issues$issue,'001')
 a$actual_direction[1] <- 'W';a$actual_direction[3] <- 'L'
 testthat::expect_equal(missed_issue_diagnostics(l,a)$groups$double_misses,c(1L,1L))
 a$actual_direction[3] <- 'W'
 testthat::expect_equal(missed_issue_diagnostics(l,a)$issues$winning_groups,2L)
 testthat::expect_error(missed_issue_diagnostics(l,a[-1,]))
 testthat::expect_error(missed_issue_diagnostics(l,dplyr::bind_rows(a,a[1,])))
 bad <- l;bad$support[1] <- '33'
 testthat::expect_error(missed_issue_diagnostics(bad,a))
 bad <- a;bad$handicap[1] <- 1
 testthat::expect_error(missed_issue_diagnostics(l,bad))
 testthat::expect_error(missed_issue_diagnostics(l[-1,],a))
 testthat::expect_error(missed_issue_diagnostics(l[0,],a))
})
