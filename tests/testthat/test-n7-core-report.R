root<-normalizePath(file.path(testthat::test_path(),'../..'))
source(file.path(root,'r/n7_core_report.R'))
test_that('paired rescue and loss counts retain unequal spending and complete scope',{
 x<-tibble::tibble(issue=rep(c('001','002'),2),seed=1,arm=rep(c('A','B'),each=2),
  stake=c(10,20,20,20),gross=c(30,0,0,50),net=c(20,-20,-20,30),hits=c(1,0,0,1))
 map<-tibble::tibble(treatment='A',control='B',comparison='baseline')
 z<-n7_core_pairs(x,map,c('001','002'),1)
 expect_equal(z$rescued,1);expect_equal(z$lost,1);expect_equal(z$net_delta_cny,-10)
 expect_equal(z$equal_spend_issues,1);expect_equal(z$stake_delta_cny,-10)
 expect_error(n7_core_pairs(x[-1,],map,c('001','002'),1))
 expect_error(n7_core_pairs(x,map,c('001','002','003'),1))
})
test_that('attribution respects actual funding stops and does not invent opportunity ROI',{
 x<-tibble::tibble(arm='A',seed=1,reference=FALSE,stopped=c(FALSE,TRUE),stake=c(40,0),gross=c(80,0),
  core_stake=30,opportunity_stake=10,core_gross=60,opportunity_gross=20)
 z<-n7_core_attribution(x)
 expect_equal(z$core_stake,30);expect_equal(z$opportunity_stake,10)
 expect_equal(z$core_net,30);expect_equal(z$opportunity_roi_percent,100)
 x$core_gross[1]<-0;expect_error(n7_core_attribution(x))
})
