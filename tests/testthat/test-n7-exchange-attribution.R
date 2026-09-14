source(testthat::test_path('..','..','r','n7_exchange_attribution.R'))
source(testthat::test_path('..','..','r','n7_quality_settlement.R'))

testthat::test_that('group-level replay rejects balanced payout misallocation', {
  rows<-tibble::tibble(issue='001',arm='x',seed=1,stake=4,budget_cny=4,cash=0,groups=2)
  funded<-tibble::tibble(issue='001',arm='x',seed=1,sleeve_id=c('1','2'),depth=1,
    copies=1,stake=2,coverage=.25,expected_gross=3)
  ranks<-tibble::tibble(issue='001',sleeve_id=c('1','2'),actual_rank=1,actual_gross_cny=c(10,20))
  groups<-n7_quality_settlement(rows,funded,ranks)$groups
  testthat::expect_true(n7_verify_attribution_groups(groups,rows,funded,ranks))
  bad<-groups;bad$gross<-rev(bad$gross);bad$net<-bad$gross-bad$stake
  testthat::expect_equal(sum(bad$gross),sum(groups$gross))
  testthat::expect_error(n7_verify_attribution_groups(bad,rows,funded,ranks))
  testthat::expect_error(n7_verify_attribution_groups(groups[-1,],rows,funded,ranks))
  testthat::expect_error(n7_verify_attribution_groups(groups,rows,funded,ranks[-1,]))
  bad<-groups;bad$actual_rank[1]<-2
  testthat::expect_error(n7_verify_attribution_groups(bad,rows,funded,ranks))
  testthat::expect_true(n7_verify_attribution_groups(groups[0,],rows[0,],funded[0,],ranks[0,]))
})

testthat::test_that('attribution reconciles additions, removals, retained and empty plans', {
  g<-tibble::tibble(issue='001',arm=c('b','b','x','x'),seed=1,sleeve_id=c('1','2','2','3'),
    stake=2,gross=c(10,0,0,20),net=c(8,-2,-2,18),coverage=.25,expected_gross=3,
    depth=1,copies=1,hit=c(TRUE,FALSE,FALSE,TRUE))
  p<-tibble::tibble(issue=rep(c('001','002'),each=2),arm=rep(c('b','x'),2),seed=1,
    variant=rep(c('JOINT','EXCHANGE12'),2),budget_cny=4,stake=c(4,4,0,0),
    gross=c(10,20,0,0),net=c(6,16,0,0),hits=c(1,1,0,0))
  z<-n7_exchange_attribution(g,p,c('001','002'),c(1L,3L))
  testthat::expect_equal(sort(z$ledger$role),c('added','removed','retained'))
  testthat::expect_equal(z$paired$delta_net,c(10,0))
  testthat::expect_equal(z$paired$added_gross,c(20,0))
  testthat::expect_equal(z$paired$removed_gross,c(10,0))
  testthat::expect_equal(z$trims$delta_trimmed_net,rep(0,4))
  testthat::expect_equal(z$adverse$stressed_delta_net,c(-10,-10))
  testthat::expect_equal(z$ledger$delta_net[z$ledger$role=='retained'],0)
  # All empty groups still preserve all plans and typed accounting outputs.
  empty<-n7_exchange_attribution(g[0,],transform(p,stake=0,gross=0,net=0,hits=0),c('001','002'),1L)
  testthat::expect_equal(empty$paired$ledger_net,c(0,0))
  testthat::expect_equal(empty$trims$trimmed_net,c(0,0))
  testthat::expect_error(n7_exchange_attribution(rbind(g,g[1,]),p,c('001','002'),1L))
  bad<-g;bad$coverage[3]<-.3
  testthat::expect_error(n7_exchange_attribution(bad,p,c('001','002'),1L))
  bad<-g;bad$net[1]<-NA_real_
  testthat::expect_error(n7_exchange_attribution(bad,p,c('001','002'),1L))
  testthat::expect_error(n7_exchange_attribution(g,p[-2,],c('001','002'),1L))
  testthat::expect_error(n7_exchange_attribution(g,p,c('001','002'),0L))
  testthat::expect_error(n7_exchange_attribution(g,p,c('001'),1L))
  testthat::expect_error(n7_exchange_attribution(g,transform(p,net=net+1),c('001','002'),1L))
})
