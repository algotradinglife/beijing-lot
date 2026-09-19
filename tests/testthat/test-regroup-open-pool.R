for(n in c('n7_sleeve_tables','n7_joint_sleeves','n7_capital_depth','n7_capital_portfolio','n7_core_opportunity','n7_sweet_union','n7_sp_filter','n7_probability_replay','joint_candidate_comparison','zero_handicap_purchase','line_gap_third','regroup_open_pool'))source(file.path('..','..','r',paste0(n,'.R')))
testthat::test_that('coverage target no longer excludes SP-qualified diffuse groups',{
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 b<-list(issue=e$issue,cutoffs=e$cutoffs,historical_admission=FALSE,seal='test',expanded_pool=list(fixtures=e$fixtures),sleeves=list(list(id=0L,fixture_indices=as.list(0:6),origin='QUALITY',enumeration=e,options=list())))
 f<-dplyr::bind_rows(e$fixtures);f$p_W<-.36;f$p_D<-.34;f$p_L<-.30
 b<-zero_purchase_bundle(b,f,b$cutoffs,'diffuse',2,.65)
 s<-list(model_id='test',target_coverage=.25,group_cap_cny=256,minimum_sp=1,budget_cny=1024,unit_cny=2,payout_factor=.65,seed=42501,worlds=64,max_actions=1024)
 py<-Sys.getenv('RETICULATE_PYTHON');z<-regroup_open_pool(b,b$cutoffs,py,s,'OPEN')
 testthat::expect_gt(z$depths$target_cost,256);testthat::expect_equal(z$depths$depth,128)
 testthat::expect_length(z$pool$options,1);testthat::expect_equal(nrow(z$plan$tickets),128)
 testthat::expect_identical(z$plan$fixtures,f);testthat::expect_lt(z$pool$options[[1]]$coverage,.25)
 testthat::expect_equal(z$metrics$stake,256)
 old<-n7_probability_allocate(b,b$cutoffs,'test',py,.25,256,1,1024,2,.65,42501,64,1024)
 testthat::expect_length(old$pool$options,0)
 s$minimum_sp<-1e6;empty<-regroup_open_pool(b,b$cutoffs,py,s,'OPEN');testthat::expect_equal(nrow(empty$plan$tickets),0)
 testthat::expect_error(regroup_open_pool(b,list(),py,s,'OPEN'))
 s$group_cap_cny<-258;testthat::expect_error(regroup_open_pool(b,b$cutoffs,py,s,'OPEN'))
})
