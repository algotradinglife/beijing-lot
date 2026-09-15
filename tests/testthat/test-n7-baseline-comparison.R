source('../../r/fundamentals_equity_curves.R')
source('../../r/n7_baseline_comparison.R')

testthat::test_that('baseline comparison preserves chronology, cash and stage accounts', {
 x<-tidyr::expand_grid(issue=c('01','02','03'),policy=c('BASE','ALT')) |>
  dplyr::mutate(model='M',stage=ifelse(issue=='03','LATE','EARLY'),
   stake=10,gross=c(0,20,30,0,0,0),net=gross-stake,budget_cny=10,cash_cny=0,
   status='COMPLETE',hits=as.integer(gross>0))
 z<-n7_baseline_comparison(x,c('01','02','03'),c('EARLY','LATE'),'BASE',100)
 s<-z$summary |> dplyr::filter(evaluation=='ALL',policy=='BASE')
 testthat::expect_equal(s$net_cny,0)
 testthat::expect_equal(s$max_drawdown_cny,10)
 testthat::expect_equal(s$minimum_equity_cny,90)
 testthat::expect_equal(s$roi_percent,0)
 testthat::expect_equal(s$net_without_best_cny,-20)
 p<-z$paired |> dplyr::filter(stage=='EARLY',policy=='ALT')
 testthat::expect_equal(p$rescued_issues,1)
 testthat::expect_equal(p$lost_issues,1)
 testthat::expect_equal(p$net_change_cny,-10)
 testthat::expect_equal(z$curves$equity_cny[z$curves$evaluation=='LATE' & z$curves$period==0],c(100,100))
 shuffled<-n7_baseline_comparison(x[nrow(x):1,],c('01','02','03'),c('EARLY','LATE'),'BASE',100)
 testthat::expect_equal(shuffled$summary,z$summary)
 cash<-x;cash$stake<-cash$gross<-cash$net<-cash$hits<-0;cash$cash_cny<-10;cash$status<-'NO_BET'
 testthat::expect_true(all(is.na(n7_baseline_comparison(cash,c('01','02','03'),c('EARLY','LATE'),'BASE',100)$summary$roi_percent)))
 bad<-x;bad$stage[1]<-'LATE'
 testthat::expect_error(n7_baseline_comparison(bad,c('01','02','03'),c('EARLY','LATE'),'BASE',100))
 testthat::expect_error(n7_baseline_comparison(x,c('01','02','03'),c('EARLY','LATE'),'MISSING',100))
 testthat::expect_error(n7_baseline_comparison(x,c('01','02','03'),c('EARLY','LATE'),'BASE',1))
 testthat::expect_error(n7_baseline_comparison(x[-1,],c('01','02','03'),c('EARLY','LATE'),'BASE',100))
 testthat::expect_error(n7_baseline_comparison(x[0,],character(),character(),'BASE',100))
})
