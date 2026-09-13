for(path in c('n7_sleeve_tables.R','n7_joint_sleeves.R','n7_capital_depth.R',
              'n7_capital_portfolio.R','n7_capital_issue.R'))source(file.path('..','..','r',path))

test_that('prediction-only runner covers preferences budgets and exact threshold controls',{
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 p<-unlist(e$probability);v<-unlist(e$expected_contribution)
 g<-list(id=0L,fixture_indices=as.list(0:6),origin='TEST',enumeration=e,
   options=list(PROB=list(status='COMPLETE',state_ids=as.list(order(-p,-v)[1:64]-1L))))
 b<-list(issue=e$issue,cutoffs=e$cutoffs,historical_admission=FALSE,seal='fixture',
   expanded_pool=list(fixtures=e$fixtures),sleeves=list(g))
 cfg<-list(unit_cny=2,payout_factor=.65,budgets=c(128,256),seeds=42501,
   training_worlds=16,evaluation_worlds=32,evaluation_seed_offset=10000,
   depths=c(8,64,128),equal_depths=64,coverage_targets=.1,coverage_tolerance=1e-12,
   model_id='test',nodes=10,gap=0,time_seconds=10L,
   preferences=list(list(name='ANY',objective='any_hit',minimum_roi=-1,minimum_hit=0,spend_all=TRUE),
     list(name='RANDOM',objective='random',minimum_roi=-1,minimum_hit=0,spend_all=TRUE)))
 py<-Sys.getenv('FUNDAMENTALS_PYTHON');expect_true(nzchar(py))
 ans<-n7_capital_issue(b,b$cutoffs,cfg,py)
 expect_length(ans$plans,8);expect_length(ans$frontier_status,8)
 expect_length(ans$worlds,1)
 expect_equal(dim(ans$worlds[[1]]$training),c(16,7))
 expect_equal(dim(ans$worlds[[1]]$evaluation),c(32,7))
 expect_equal(nrow(ans$curves),2188)
 expect_false(ans$historical_admission)
 for(plan in ans$plans) {
   expect_equal(plan$cash_cny+plan$stake,plan$budget_cny)
   expect_equal(plan$evaluation$simulation_worlds,32)
   expect_identical(plan$cutoffs,b$cutoffs)
   if(plan$support_space=='DEPTH_64' && plan$budget_cny==128)
     expect_equal(plan$stake,128)
   if(plan$support_space=='TAU_0.1' && plan$funded_sleeves>0) {
     key<-plan$sleeve_keys[[1]]
     expect_gte(key$coverage,.1)
     expect_lt(ans$curves$coverage[ans$curves$depth==key$depth-1],.1)
   }
 }
 expect_error(n7_capital_issue(b,list(),cfg,py))
 bad<-cfg;bad$depths<-c(4,8.5)
 expect_error(n7_capital_issue(b,b$cutoffs,bad,py))
 bad<-cfg;bad$seeds<-c(1,10001)
 expect_error(n7_capital_issue(b,b$cutoffs,bad,py))
})
