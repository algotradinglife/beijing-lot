source('../../r/fundamentals_equity_curves.R');source('../../r/n7_purchase_accounting.R');source('../../r/joint_payout_report.R')
testthat::test_that('payout report binds original and exact removed/added bridge',{
 rows<-tibble::tibble(issue=rep(c('01','02'),2),policy=rep(c('BASE','FILTER'),each=2),
  stake=c(4,4,2,2),gross=c(10,0,0,8),net=c(6,-4,-2,6),hits=c(1,0,0,1),
  cash_cny=c(6,6,8,8),budget_cny=10,status='COMPLETE',model='TEST',union_coverage=.2,expected_gross=1,
  max_fixture_exposure=2,max_direction_exposure=2)
 original<-rows[1:2,c('issue','stake','gross','net','hits')]
 map<-tibble::tibble(issue=c('01','02'),period=1:2,stage=c('BEFORE','AFTER'))
 c<-tidyr::crossing(issue=c('01','02'),policy=c('BASE','FILTER'),category=c('COMMON','REMOVED','ADDED')) |> dplyr::mutate(net=0,tickets=0,stake=0,gross=0,expected_gross=0)
 c$net[c$policy=='BASE' & c$category=='COMMON']<-c(6,-4)
 c$net[c$policy=='FILTER' & c$category=='REMOVED']<-c(6,-4)
 c$net[c$policy=='FILTER' & c$category=='ADDED']<-c(-2,6)
 c$stake[c$policy=='BASE' & c$category=='COMMON']<-4
 c$stake[c$policy=='FILTER' & c$category=='REMOVED']<-4
 c$stake[c$policy=='FILTER' & c$category=='ADDED']<-2
 c$gross<-c$stake+c$net;c$tickets<-c$stake/2
 z<-joint_payout_report(rows,c,original,map,100,'BASE',2)
 testthat::expect_equal(nrow(z$bridge),4)
 testthat::expect_equal(z$summary$net_cny[z$summary$evaluation=='ALL' & z$summary$accounting_basis=='FUNDED' & z$summary$policy=='BASE'],2)
 bad<-c;bad$gross[1]<-999
 testthat::expect_error(joint_payout_report(rows,bad,original,map,100,'BASE',2))
 bad<-original;bad$net[1]<-7
 testthat::expect_error(joint_payout_report(rows,c,bad,map,100,'BASE',2))
 bad<-c;bad$net[1]<-100
 testthat::expect_error(joint_payout_report(rows,bad,original,map,100,'BASE',2))
})
