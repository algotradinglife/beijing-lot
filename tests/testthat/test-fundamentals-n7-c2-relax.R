source(file.path('..','..','r','fundamentals_n7_c2_relax.R'))
testthat::test_that('cash issue count uses rows before summing cash', {
 x <- tibble::tibble(partition='TEST',policy='A',issue=c('001','002','003'),
   budget_cny=c(128,128,128),cash_cny=c(0,64,64),stake=c(128,64,64),
   added_stake=c(64,0,0),added_net=c(10,0,0),added_groups=c(1L,0L,0L),
   added_hits=c(1L,0L,0L),hits=c(1L,0L,0L),unique_fixtures=c(14L,7L,7L))
 y <- n7_relaxation_totals(x)
 testthat::expect_equal(y$cash_issues,2L)
 testthat::expect_equal(y$cash_cny,128)
 testthat::expect_equal(y$budget_cny,384)
 testthat::expect_equal(y$any_hit_issues,1L)
 testthat::expect_equal(y$full_loss_issues,2L)
 testthat::expect_equal(y$added_stake,64)
 testthat::expect_equal(y$added_net,10)
 testthat::expect_equal(y$unique_fixtures,28L)
 z <- dplyr::bind_rows(x,dplyr::mutate(x,policy='B',cash_cny=0,stake=128))
 testthat::expect_equal(n7_relaxation_totals(z)$cash_issues,c(2L,0L))
 testthat::expect_error(n7_relaxation_totals(dplyr::bind_rows(x,x[1,])))
 testthat::expect_error(n7_relaxation_totals(x[0,]))
 bad <- x;bad$cash_cny[1] <- NA_real_
 testthat::expect_error(n7_relaxation_totals(bad))
 bad <- x;bad$cash_cny[1] <- -1
 testthat::expect_error(n7_relaxation_totals(bad))
 bad <- x;bad$added_groups[1] <- 2
 testthat::expect_error(n7_relaxation_totals(bad))
})
