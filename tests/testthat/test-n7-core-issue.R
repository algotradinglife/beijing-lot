root<-normalizePath(file.path(testthat::test_path(),'../..'))
for(f in c('n7_sleeve_tables','n7_joint_sleeves','n7_capital_depth',
 'n7_capital_portfolio','n7_core_opportunity','n7_core_plan','n7_core_issue'))source(file.path(root,'r',paste0(f,'.R')))
test_that('issue runner freezes deterministic full policies and rejects actual input columns',{
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 p<-unlist(e$probability);v<-unlist(e$expected_contribution)
 g<-list(id=0L,fixture_indices=as.list(0:6),origin='TEST',enumeration=e,
  options=list(PROB=list(status='COMPLETE',state_ids=as.list(order(-p,-v)[1:64]-1L))))
 b<-list(issue=e$issue,cutoffs=e$cutoffs,historical_admission=FALSE,
  expanded_pool=list(fixtures=e$fixtures),sleeves=list(g))
 cfg<-jsonlite::fromJSON(file.path(root,'config/n7_core_opportunity_433.json'),simplifyVector=FALSE)
 cfg$seeds<-list(42501);cfg$training_worlds<-16;cfg$evaluation_worlds<-32;cfg$depths<-list(15,32,64)
 cfg$policies<-lapply(c('BREADTH','DEPTH','MULTIPLY'),function(mode)list(name=mode,
  mode=mode,core_count=1,opportunity_cap_cny=0,opportunity_rule='PROB',
  max_copies=3,objective='any_hit'))
 cfg$arms<-lapply(cfg$policies,`[[`,'name')
 python<-Sys.getenv('FUNDAMENTALS_PYTHON');expect_true(nzchar(python))
 x<-n7_core_issue(b,b$cutoffs,cfg,python)
 expect_length(x$plans,3)
 expect_true(all(vapply(x$plans,function(z)z$stake<=1024,logical(1))))
 expect_equal(x,n7_core_issue(b,b$cutoffs,cfg,python))
 bad<-b;bad$expanded_pool$fixtures[[1]]$actual_direction<-'W'
 expect_error(n7_core_issue(bad,bad$cutoffs,cfg,python),'Prediction-only')
 expect_error(n7_core_issue(b,list(),cfg,python))
})
