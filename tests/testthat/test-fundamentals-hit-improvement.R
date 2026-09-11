source(file.path('..','..','r','fundamentals_equity_curves.R'))
source(file.path('..','..','r','fundamentals_missed_summary.R'))
source(file.path('..','..','r','fundamentals_hit_improvement.R'))
testthat::test_that('matched rescues distinguish lost original hit and tail lift',{
 x<-tibble::tibble(policy=rep(c('MAIN','ALT'),each=3),issue=rep(c('001','002','003'),2),status='COMPLETE',
 weight=rep(c(0,.5),each=3),protect=FALSE,cap=NA_integer_,stake=64,budget=1024,cash=960,groups=1,
 hits=c(0,1,1,1,0,1),gross=c(0,200,200,200,0,250)) |> dplyr::mutate(net=gross-stake)
 z<-hit_improvement_summary(x,'MAIN',c('001','002','003'),100000)$summary |> dplyr::filter(policy=='ALT')
 testthat::expect_equal(z$rescued_issues,1L);testthat::expect_equal(z$lost_issues,1L)
 testthat::expect_equal(z$preserved_issues,1L);testthat::expect_equal(z$net_lift,50)
 testthat::expect_equal(z$ex_best_lift,-150);testthat::expect_equal(z$best_lift_issue,'001')
 testthat::expect_equal(z$stake_change_cny,0);testthat::expect_error(hit_improvement_summary(x,'MISSING',c('001','002','003'),100000))
})
