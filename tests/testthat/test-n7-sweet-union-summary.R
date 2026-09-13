source(file.path('..','..','r','fundamentals_equity_curves.R'))
source(file.path('..','..','r','n7_sweet_union_summary.R'))
testthat::test_that('union summaries use exact issue order, funded money and cash',{
  x <- tibble::tibble(issue=c('02','01','03'),arm='a',seed=1,
    stake=c(2,2,0),gross=c(0,6,0),net=c(-2,4,0),cash=c(2,2,4),
    budget_cny=4,hits=c(0,1,0))
  z <- n7_sweet_union_summary(x,c('01','02','03'),100)
  testthat::expect_equal(z$summary$net,2)
  testthat::expect_equal(z$summary$roi,.5)
  testthat::expect_equal(z$summary$max_drawdown,2)
  testthat::expect_equal(z$summary$hit_issues,1)
  testthat::expect_equal(z$summary$profit_issues,1)
  testthat::expect_equal(z$summary$cash,8)
  testthat::expect_equal(z$summary$net_without_best,-2)
  testthat::expect_equal(z$summary$net_without_best3,0)
  testthat::expect_equal(z$summary$net_without_best5,0)
  testthat::expect_equal(z$curves$equity_cny,c(100,104,102,102))
  testthat::expect_error(n7_sweet_union_summary(x,c('01','02'),100))
  x$gross[1] <- 1
  testthat::expect_error(n7_sweet_union_summary(x,c('01','02','03'),100))
})
