root<-normalizePath(file.path(testthat::test_path(),'../..'))
source(file.path(root,'r/n7_core_report.R'))
test_that('paired rescue and loss counts retain unequal spending and complete scope',{
 x<-tibble::tibble(issue=rep(c('001','002'),2),seed=1,arm=rep(c('A','B'),each=2),
  stake=c(10,20,20,20),gross=c(30,0,0,50),net=c(20,-20,-20,30),hits=c(1,0,0,1),stopped=FALSE)
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
test_that('exposure separates paid copies from unique coverage and cash stops',{
 s<-tibble::tibble(issue=c('001','001','002'),arm='A',seed=1,sleeve_id=1,
  role='CORE',copy_index=c(1,2,1),depth=15,stake=30)
 p<-tibble::tibble(issue=c('001','002','003'),arm='A',seed=1,
  reference=FALSE,stopped=c(FALSE,TRUE,FALSE),stake=c(60,0,0))
 z<-n7_core_exposure(s,p)
 expect_equal(z$unique_ticket_units,15);expect_equal(z$paid_ticket_units,30)
 expect_equal(z$repeated_stake_cny,30);expect_equal(z$repeated_stake_percent,50)
 expect_equal(z$core_groups_mean,1/3)
 expect_error(n7_core_exposure(dplyr::bind_rows(s,s[1,]),p))
 expect_error(n7_core_exposure(s,dplyr::mutate(p,stake=100)))
 expect_error(n7_core_exposure(dplyr::mutate(s,issue='unknown'),p))
 empty<-n7_core_exposure(s[FALSE,],dplyr::mutate(p,stake=0))
 expect_equal(empty$paid_ticket_units,0);expect_true(is.na(empty$repeated_stake_percent))
})
test_that('rank-based attribution reconciles copies before fixed cost-band summaries',{
 ranks<-tibble::tibble(issue=c('001','001'),sleeve_id=c(1,2),actual_rank=c(10,20),
  actual_gross_cny=c(100,200),coverage_20_cost_cny=c(64,128))
 sleeves<-tibble::tibble(issue='001',arm='A',seed=1,sleeve_id=c(1,1,2),
  copy_index=c(1,2,1),role=c('CORE','CORE','OPPORTUNITY'),depth=15,stake=30,expected_gross=24)
 p<-tibble::tibble(issue='001',arm='A',seed=1,reference=FALSE,stopped=FALSE,gross=200,hits=1,stake=90)
 z<-n7_core_rank_attribution(ranks,sleeves,p)
 core<-z[z$role=='CORE',]
 expect_equal(core$unique_hits,1);expect_equal(core$paid_hits,2)
 expect_equal(core$gross,200);expect_equal(core$stake,60)
 expect_equal(core$model_roi_percent,-20);expect_equal(as.character(core$cost_band),'<=32')
 expect_error(n7_core_rank_attribution(ranks,sleeves,dplyr::mutate(p,gross=201)))
 expect_error(n7_core_rank_attribution(ranks[1,],sleeves,p))
 stop<-n7_core_rank_attribution(ranks,sleeves,dplyr::mutate(p,stopped=TRUE,gross=0,hits=0,stake=0))
 expect_equal(nrow(stop),0)
})
test_that('paired account results distinguish funded misses from cash stops and no bets',{
 x<-tibble::tibble(issue=rep(c('001','002','003','004'),2),arm=rep(c('A','B'),each=4),seed=1,
  stake=c(2,2,0,0,0,2,0,0),hits=c(1,1,0,0,0,0,0,0),
  gross=c(4,4,0,0,0,0,0,0),stopped=c(FALSE,FALSE,FALSE,TRUE,TRUE,FALSE,FALSE,TRUE)) |>
  dplyr::mutate(net=gross-stake)
 z<-n7_core_pairs(x,tibble::tibble(treatment='A',control='B',comparison='test'),
  c('001','002','003','004'),1)
 expect_equal(z$rescued,2);expect_equal(z$funded_rescued,1)
 expect_equal(z$both_funded,1);expect_equal(z$one_side_funded,1);expect_equal(z$neither_funded,2)
 expect_equal(z$one_side_stopped,1);expect_equal(z$both_stopped,1)
 expect_equal(z$treatment_no_bet,1);expect_equal(z$control_no_bet,1)
 expect_equal(z$equal_spend_issues,1)
 expect_equal(z$both_funded+z$one_side_funded+z$neither_funded,z$issues)
})
