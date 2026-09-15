for(name in c('n7_sleeve_tables','n7_joint_sleeves','n7_capital_depth',
 'n7_capital_portfolio','n7_core_opportunity','n7_sweet_union','n7_sp_filter',
 'n7_probability_replay','n7_purchase_pool','n7_purchase_exposure',
 'n7_purchase_shape','n7_purchase_group_filter','n7_purchase_confidence'))
 source(file.path('..','..','r',paste0(name,'.R')))

testthat::test_that('target labels cannot alter fixed purchase support and allocation', {
 python<-Sys.getenv('RETICULATE_PYTHON')
 testthat::skip_if(!nzchar(python),'Explicit project Python required')
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 b<-list(issue=e$issue,cutoffs=e$cutoffs,historical_admission=FALSE,
  expanded_pool=list(fixtures=e$fixtures),sleeves=list(list(id=0L,
  fixture_indices=as.list(0:6),origin='QUALITY',enumeration=e,options=list())))
 changed<-b
 changed$settlement<-list(issue=e$issue,actual_direction='L',spf_sp=999,
  label_available_at='1900-01-01T00:00:00Z')
 changed$future_settlements<-list(list(issue='999999',actual_direction='W',spf_sp=.01))
 # No fitting occurs here. This tests the frozen-bundle-to-purchase boundary;
 # history admission and calibration have separate shared-learning tests.
 outputs<-list()
 for(i in 1:2) {
  bundle<-list(b,changed)[[i]]
  original<-n7_probability_allocate(bundle,b$cutoffs,'TEST',python,.05,1024,1,1024,2,.65,42501,32,1024)
  pool<-n7_purchase_pool(original$pool,b$cutoffs,'GAP',.05,.5,c(64L,128L))
  shape<-n7_purchase_shape(pool,b$cutoffs,c(16,64),c(.25),2,.55,.4,.05)
  pool<-n7_purchase_group_filter(pool,shape,b$cutoffs,0,0,7,Inf)
  limits<-n7_purchase_confidence_limits(pool,b$cutoffs,2,.05,2,6,128,384)
  worlds<-n7_joint_worlds(pool,b$cutoffs,42501,32)
  scenarios<-n7_joint_returns(pool,worlds,b$cutoffs)
  fit<-n7_core_allocate(pool,scenarios,b$cutoffs,1024,'any_hit',1024,'OPEN_FIRST',limits)
  outputs[[i]]<-list(pool=pool,shape=shape,limits=limits,fit=fit,
   tickets=pool$options[fit$selected],exposure=n7_purchase_exposure(pool,b$cutoffs,2))
 }
 testthat::expect_gt(length(outputs[[1]]$pool$options),0)
 testthat::expect_gt(length(outputs[[1]]$tickets),0)
 for(field in names(outputs[[1]]))testthat::expect_identical(outputs[[1]][[field]],outputs[[2]][[field]],info=field)
 poisoned<-e$fixtures;poisoned[[1]]$actual_direction<-'W'
 testthat::expect_error(n7_joint_validate(poisoned,b$cutoffs,python))
 testthat::expect_error(n7_joint_validate(e$fixtures,list(),python))
})
