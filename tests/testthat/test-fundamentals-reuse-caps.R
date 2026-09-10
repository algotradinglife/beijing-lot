source('../../r/fundamentals_equity_curves.R')
source('../../r/fundamentals_reuse_caps.R')
testthat::test_that('fixed-cap summaries reconcile cash and same-stake controls', {
 x <- tidyr::expand_grid(issue=c('001','002','003'),max_uses=c(2L,4L),kind=c('CAPPED','MATCHED_STAKE')) |>
  dplyr::mutate(max_pair_overlap=2L,policy=paste(max_uses,kind),status='COMPLETE',stake=64,
   budget_cny=128,cash_cny=64,groups=1,hits=0,net=dplyr::case_when(kind=='MATCHED_STAKE'~ -20,
    max_uses==2L~c(20,-10,30)[match(issue,c('001','002','003'))],TRUE~ -10),gross=net+stake)
 z <- reuse_cap_summary(x,100000);s <- z$summary
 a <- s[s$max_uses==2 & s$kind=='CAPPED',]
 testthat::expect_equal(a$net_cny,40)
 testthat::expect_equal(a$max_drawdown_cny,10)
 testthat::expect_equal(a$net_vs_same_stake,100)
 testthat::expect_equal(a$without_best_net,10)
 testthat::expect_equal(a$cash_cny,192)
 testthat::expect_equal(a$profitable_issues,2)
 testthat::expect_true(a$non_dominated)
 testthat::expect_false(s$non_dominated[s$max_uses==4 & s$kind=='CAPPED'])
 testthat::expect_equal(nrow(z$curves),16)
 bad<-x;bad$stake[1]<-63
 testthat::expect_error(reuse_cap_summary(bad,100000))
 testthat::expect_error(reuse_cap_summary(x[-1,],100000))
 testthat::expect_error(reuse_cap_summary(dplyr::bind_rows(x,x[1,]),100000))
 testthat::expect_error(reuse_cap_summary(x[0,],100000))
})
