source(file.path('..','..','r','fundamentals_equity_curves.R'))
source(file.path('..','..','r','n7_sweet_union_summary.R'))
source(file.path('..','..','r','n7_expanded_diagnostics.R'))
testthat::test_that('expanded summaries separate cohorts and maintain complete accounting',{
  x<-tidyr::expand_grid(issue=c('01','02','03'),variant=c('JOINT','EXCHANGE12')) |>
    dplyr::mutate(arm=variant,seed=1,budget_cny=4,stake=2,cash=2,
      gross=c(0,4,0,0,4,4),net=gross-stake,hits=as.integer(gross>0),
      cohort=ifelse(issue=='01','OLD','NEW'),eval_union=.4)
  z<-n7_expanded_diagnostics(x,c('01','02','03'),100,2,seq(0,1,.1))
  testthat::expect_equal(nrow(z$summary),6)
  s<-dplyr::filter(z$summary,scope=='ALL',variant=='EXCHANGE12')
  testthat::expect_equal(s$net,2);testthat::expect_equal(s$roi,1/3)
  testthat::expect_equal(s$max_drawdown,2);testthat::expect_equal(s$hit_issues,2)
  testthat::expect_equal(sum(z$paired$rescued),1)
  testthat::expect_equal(sum(z$paired$delta_net),4)
  testthat::expect_error(n7_expanded_diagnostics(x[-1,],c('01','02','03'),100,2,seq(0,1,.1)))
  testthat::expect_error(n7_expanded_diagnostics(x,c('01','02','03'),100,0,seq(0,1,.1)))
  x$eval_union[1]<-NA_real_
  testthat::expect_error(n7_expanded_diagnostics(x,c('01','02','03'),100,2,seq(0,1,.1)))
})
testthat::test_that('group trimming removes positive profit, preserves cash and losses',{
  p<-tibble::tibble(issue=c('01','02'),arm='a',seed=1,variant='JOINT',budget_cny=4,
    cohort=c('OLD','NEW'),net=c(3,-2),stake=2)
  g<-tibble::tibble(issue=c('01','02'),arm='a',seed=1,sleeve_id='0',net=c(3,-2),stake=2)
  z<-n7_expanded_group_trims(g,p,c(0,1,3))
  testthat::expect_equal(dplyr::filter(z,scope=='ALL')$trimmed_net,c(1,-2,-2))
  testthat::expect_equal(dplyr::filter(z,scope=='NEW')$trimmed_net,c(-2,-2,-2))
  testthat::expect_error(n7_expanded_group_trims(dplyr::bind_rows(g,g[1,]),p,1))
})
