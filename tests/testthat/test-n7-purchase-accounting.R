source('../../r/fundamentals_equity_curves.R')
source('../../r/n7_baseline_comparison.R')
source('../../r/n7_purchase_accounting.R')
testthat::test_that('funded and shadow accounting separate unaffordable plans without deposits', {
 x<-tidyr::expand_grid(issue=c('01','02','03'),policy=c('JOINT','CASH')) |>
  dplyr::mutate(model='M',stage=ifelse(issue=='03','LATE','EARLY'),
   stake=ifelse(policy=='JOINT',8,0),gross=ifelse(policy=='JOINT' & issue=='03',100,0),
   net=gross-stake,budget_cny=8,cash_cny=8-stake,
   status=ifelse(stake>0,'COMPLETE','NO_BET'),hits=as.integer(gross>0))
 z<-n7_purchase_accounting(x,c('01','02','03'),c('EARLY','LATE'),'JOINT',10)
 all<-z$summary |> dplyr::filter(evaluation=='ALL',policy=='JOINT')
 funded<-all[all$accounting_basis=='FUNDED',];shadow<-all[all$accounting_basis=='SHADOW',]
 testthat::expect_equal(funded$stake_cny,8);testthat::expect_equal(funded$net_cny,-8)
 testthat::expect_equal(funded$stopped_issues,2L);testthat::expect_equal(funded$funding_stop_issue,'02')
 testthat::expect_equal(funded$hit_issues,0L);testthat::expect_equal(funded$minimum_equity_cny,2)
 testthat::expect_equal(shadow$stake_cny,24);testthat::expect_equal(shadow$net_cny,76)
 testthat::expect_equal(shadow$minimum_equity_cny,-6);testthat::expect_equal(shadow$max_drawdown_percent,160)
 testthat::expect_equal(shadow$hit_issues,1L)
 early<-z$summary |> dplyr::filter(evaluation=='EARLY',policy=='JOINT',accounting_basis=='FUNDED')
 late<-z$summary |> dplyr::filter(evaluation=='LATE',policy=='JOINT',accounting_basis=='FUNDED')
 testthat::expect_equal(early$net_cny,-8);testthat::expect_equal(late$net_cny,92)
 testthat::expect_true(all(is.na(z$summary$roi_percent[z$summary$policy=='CASH'])))
 shuffled<-n7_purchase_accounting(x[nrow(x):1,],c('01','02','03'),c('EARLY','LATE'),'JOINT',10)
 testthat::expect_equal(shuffled$summary,z$summary)
 # On affordable scope every preexisting monetary and hit metric is unchanged.
 old<-n7_baseline_comparison(x,c('01','02','03'),c('EARLY','LATE'),'JOINT',100)
 new<-n7_purchase_accounting(x,c('01','02','03'),c('EARLY','LATE'),'JOINT',100)
 for(basis in c('FUNDED','SHADOW')) {
  s<-new$summary[new$summary$accounting_basis==basis,names(old$summary)]
  testthat::expect_equal(s,old$summary)
 }
 testthat::expect_error(n7_purchase_accounting(x[-1,],c('01','02','03'),c('EARLY','LATE'),'JOINT',10))
 testthat::expect_error(n7_purchase_accounting(x,c('01','02'),c('EARLY','LATE'),'JOINT',10))
 testthat::expect_error(n7_purchase_accounting(x,c('01','02','03'),c('EARLY','LATE'),'NO_SUCH',10))
})
