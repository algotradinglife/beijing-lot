root<-normalizePath(file.path(testthat::test_path(),'../..'))
source(file.path(root,'r/n7_capital_portfolio.R'))
source(file.path(root,'r/n7_core_opportunity.R'))
source(file.path(root,'r/n7_quality_allocate.R'))
test_that('quality floor and joint/structural preferences preserve fixed prefixes',{
  cuts<-list(a='epoch')
  opts<-lapply(0:2,function(id)list(sleeve_id=id,depth=2,stake=4,
    expected_gross=if(id==0)30 else 20,state_payout=rep(100,2187),
    coverage=c(.5,.49,.46)[id+1],fixtures=if(id==2)8:14 else 1:7))
  base<-list(cutoffs=cuts,options=opts)
  part<-list(core_ids=0:2,opportunity_ids=integer(),opportunity_depth=15,
    opening_depths=c('0'=2,'1'=2,'2'=2),cutoffs=cuts)
  pool<-n7_core_option_pool(base,part,cuts,'BREADTH',1)
  hit<-cbind(c(1,0,0,0),c(1,0,0,0),c(0,1,0,0))
  sc<-list(cutoffs=cuts,hits=hit,gross=hit*100)
  a<-n7_quality_allocate(pool,sc,cuts,8,.95,'UNION')
  b<-n7_quality_allocate(pool,sc,cuts,8,.90,'UNION')
  expect_equal(a$selected,c(1,2));expect_equal(b$selected,c(1,3))
  expect_equal(b$metrics$stake,8);expect_equal(b$metrics$any_hit,.5)
  expect_true(any(!a$candidates$eligible))
  expect_equal(a,n7_quality_allocate(pool,sc,cuts,8,.95,'UNION'))
  expect_equal(n7_quality_allocate(pool,sc,cuts,2,.95,'UNION')$metrics$cash,2)
  pool$options[[3]]$coverage<-.48
  sc$hits[,2]<-c(0,1,1,0);sc$gross<-sc$hits*100
  # With group0 preselected, UNION prefers group1 while OVERLAP prefers group2.
  pool$opportunity_options<-1L;pool$opening_options<-2:3
  expect_equal(n7_quality_allocate(pool,sc,cuts,8,.95,'UNION')$selected,c(1,2))
  expect_equal(n7_quality_allocate(pool,sc,cuts,8,.95,'OVERLAP')$selected,c(1,3))
  expect_error(n7_quality_allocate(pool,sc,list(a='later'),8,.95,'UNION'))
  expect_error(n7_quality_allocate(pool,sc,cuts,8,1.1,'UNION'))
  expect_error(n7_quality_allocate(pool,sc,cuts,7,.95,'UNION'))
  expect_identical(n7_quality_allocate(pool,sc,cuts,8,.95,'UNION'),
    n7_quality_allocate(pool,c(sc,list(future_label='changed')),cuts,8,.95,'UNION'))
  empty<-pool;empty$options<-list();empty$opening_options<-empty$opportunity_options<-integer()
  empty_sc<-list(cutoffs=cuts,hits=matrix(numeric(),4,0),gross=matrix(numeric(),4,0))
  expect_equal(n7_quality_allocate(empty,empty_sc,cuts,8,.95,'UNION')$metrics$cash,8)
})
