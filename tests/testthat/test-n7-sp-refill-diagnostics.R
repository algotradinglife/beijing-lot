source('../../r/fundamentals_equity_curves.R')
source('../../r/n7_sweet_union_summary.R')
source('../../r/n7_selection_diagnostics.R')
source('../../r/n7_sp_refill_diagnostics.R')
testthat::test_that('refill summaries preserve cash, loss streaks and metadata',{
  x<-tibble::tibble(issue=sprintf('%03d',1:5),arm='A',seed=1,stake=c(2,2,0,2,2),
    gross=c(0,0,0,6,0),net=c(-2,-2,0,4,-2),cash=c(0,0,2,0,0),
    budget_cny=2,hits=c(0,0,0,1,0),variant='FILTER_ONLY',mode='DEPTH',
    objective='any_hit',allocation_order='OPEN_FIRST')
  z<-n7_sp_refill_diagnostics(x,x$issue,100)
  testthat::expect_equal(z$summary$longest_loss_streak,2)
  testthat::expect_equal(z$summary$net,-2)
  testthat::expect_equal(z$summary$roi,-.25)
  testthat::expect_equal(z$summary$max_drawdown,4)
  testthat::expect_equal(z$summary$hit_issues,1)
  testthat::expect_equal(z$summary$variant,'FILTER_ONLY')
  y<-x;y$variant<-'REFILL';y$arm<-'B';y$gross[4]<-0;y$net[4]<- -2;y$hits[4]<-0
  paired<-n7_sp_refill_diagnostics(dplyr::bind_rows(x,y),x$issue,100)
  testthat::expect_equal(paired$paired$delta_net[paired$paired$arm=='B'],-6)
  testthat::expect_equal(paired$per_issue$delta_gross[paired$per_issue$arm=='B'],c(0,0,0,-6,0))
  testthat::expect_error(n7_sp_refill_diagnostics(dplyr::bind_rows(x,x[1,]),x$issue,100))
  x$variant[1]<-NA_character_
  testthat::expect_error(n7_sp_refill_diagnostics(x,x$issue,100))
})
