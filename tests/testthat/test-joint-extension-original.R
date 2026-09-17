for(f in c('n7_probability_replay','n7_sleeve_tables','n7_joint_sleeves','n7_capital_depth',
 'n7_capital_portfolio','n7_core_opportunity','n7_sweet_union','n7_sp_filter','joint_extension_original'))source(file.path('..','..','r',paste0(f,'.R')))
test_that('extension reuses JOINT canonical prefix, identities and empty cash outcome', {
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 b<-list(issue=e$issue,cutoffs=e$cutoffs,historical_admission=FALSE,seal='test',expanded_pool=list(fixtures=e$fixtures),sleeves=list(list(id=0L,fixture_indices=as.list(0:6),origin='QUALITY',enumeration=e,options=list())))
 f<-dplyr::bind_rows(e$fixtures);f$new_D<-.7;f$new_W<-.2;f$new_L<-.1
 b<-n7_probability_bundle(b,f,b$cutoffs,'test')
 s<-list(model_id='test',target_coverage=.25,group_cap_cny=256,minimum_sp=1.3,budget_cny=1024,unit_cny=2,payout_factor=.65,seed=42501,worlds=256,max_actions=1024)
 z<-joint_extension_original(b,b$cutoffs,s,Sys.getenv('RETICULATE_PYTHON'))
 expect_equal(z$metrics$bought_groups,1);expect_equal(z$metrics$original_stake,2*nrow(z$tickets))
 expect_gte(sum(z$tickets$prob),.25);expect_equal(nrow(z$members),7)
 expect_equal(z$tickets$prob_rank,seq_len(nrow(z$tickets)));expect_equal(z$tickets$prob,sort(z$tickets$prob,decreasing=TRUE))
 expect_error(joint_extension_original(b,list(),s,Sys.getenv('RETICULATE_PYTHON')))
 s$minimum_sp<-1e9;empty<-joint_extension_original(b,b$cutoffs,s,Sys.getenv('RETICULATE_PYTHON'))
 expect_equal(nrow(empty$tickets),0);expect_equal(empty$metrics$original_stake,0)
})
test_that('BASE relational replay preserves unknown cells and odd half cuts',{
 cut<-list(cutoff_kind='DECISION_EPOCH',historical_admission=FALSE)
 s<-tibble::tibble(cell=c('bad','good'),long_hit_signal=c('BAD','GOOD'))
 attr(s,'signal_receipt')<-list(cutoff=cut,signal_hash=digest::digest(s,algo='sha256'))
 t<-tibble::tibble(ticket_id=letters[1:5],cell=c('bad','bad','bad','good','unknown'),prob=c(.1,.3,.2,.4,.1))
 expect_equal(joint_extension_base_replay(t,s,cut),c(0L,1L,1L,1L,1L))
 expect_equal(joint_extension_base_replay(t[5:1,],s,cut),c(1L,1L,1L,1L,0L))
 s$long_hit_signal[1]<-'GOOD';expect_error(joint_extension_base_replay(t,s,cut))
})
