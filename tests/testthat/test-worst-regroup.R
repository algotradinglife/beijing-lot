for(n in c('n7_sleeve_tables','n7_joint_sleeves','n7_capital_depth','n7_capital_portfolio','n7_core_opportunity','n7_sweet_union','n7_sp_filter','n7_probability_replay','top2_fresh_groups','joint_candidate_comparison','zero_handicap_purchase','line_gap_third','worst_regroup'))source(file.path('..','..','r',paste0(n,'.R')))
testthat::test_that('fixed regrouping preserves fixtures, prices and label isolation',{
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 b<-list(issue=e$issue,cutoffs=e$cutoffs,historical_admission=FALSE,seal='test',expanded_pool=list(fixtures=e$fixtures),sleeves=list(list(id=0L,fixture_indices=as.list(0:6),origin='QUALITY',enumeration=e,options=list())))
 f<-dplyr::bind_rows(e$fixtures);extra<-f[1:3,];extra$slot<-max(f$slot)+1:3;extra$provider_id<-paste0('extra',1:3)
 f<-rbind(f,extra);b$cutoffs<-c(e$cutoffs,setNames(rep(e$cutoffs[1],3),as.character(extra$slot)));b$expanded_pool$fixtures<-c(e$fixtures,lapply(1:3,function(i)as.list(extra[i,])))
 s<-list(model_id='test',target_coverage=.25,group_cap_cny=256,minimum_sp=1,budget_cny=1024,unit_cny=2,payout_factor=.65,seed=42501,worlds=64,max_actions=1024)
 py<-Sys.getenv('RETICULATE_PYTHON');z<-worst_regroup_compare(b,b$cutoffs,py,s,8,4)
 testthat::expect_setequal(names(z$plans),c('OLD_TOP2','EXP_TOP2','OLD_JOINT','OLD_DROP','EXP_JOINT','EXP_DROP','EXP_DROP_EV','TOP2_PROB','TOP2_DIVERSE'))
 testthat::expect_identical(z$expanded$expanded_pool,b$expanded_pool)
 testthat::expect_identical(z$expanded$sleeves[[1]],b$sleeves[[1]])
 testthat::expect_true(all(vapply(z$plans,function(p)nrow(p$tickets)*2<=1024,logical(1))))
 labels<-f[c('issue','slot','provider_id','handicap')];labels$actual_direction<-c('W','D','L')[apply(as.matrix(f[c('p_W','p_D','p_L')]),1,which.max)];labels$spf_sp<-2
 for(policy in c('TOP2_PROB','TOP2_DIVERSE')){
  native<-top2_fresh_settle(z$fresh,labels);native<-native[native$policy==policy,]
  common<-joint_candidate_settle(z$plans[[policy]],labels)$rows
  testthat::expect_equal(common$gross,sum(native$gross));testthat::expect_equal(common$stake,sum(native$stake))
 }
 d<-worst_regroup_diagnose(z$expanded,z$pools$EXP,z$plans$EXP_DROP,labels,b$cutoffs,2,s$minimum_sp)
 testthat::expect_true(all(d$top2_possible));testthat::expect_true(all(d$sp_eligible))
 gated<-z$pools$EXP;gated$options<-list();dg<-worst_regroup_diagnose(z$expanded,gated,z$plans$EXP_DROP,labels,b$cutoffs,2,s$minimum_sp)
 testthat::expect_true(all(dg$sp_eligible & !dg$eligible & dg$top2_possible));testthat::expect_true(all(d$option_hit[d$eligible]));testthat::expect_equal(sum(d$hit),joint_candidate_settle(z$plans$EXP_DROP,labels)$rows$hits)
 testthat::expect_error(worst_regroup_diagnose(z$expanded,z$pools$EXP,z$plans$EXP_DROP,labels[-1,],b$cutoffs,2,s$minimum_sp))
 testthat::expect_error(worst_regroup_compare(b,list(),py,s,8,4))
 bad<-b;bad$expanded_pool$fixtures[[1]]$actual_direction<-'W';testthat::expect_error(worst_regroup_compare(bad,b$cutoffs,py,s,8,4))
 reach<-worst_regroup_fresh_reach(z$fresh,labels,b$cutoffs);testthat::expect_true(all(reach$top2_possible));testthat::expect_equal(nrow(reach),length(z$fresh$groups))
 testthat::expect_error(worst_regroup_fresh_reach(z$fresh,labels[-1,],b$cutoffs))
 testthat::expect_error(worst_regroup_fresh_reach(z$fresh,labels,list()))
 empty<-z$fresh;empty$selected$TOP2_PROB<-integer();empty$seal<-digest::digest(empty[names(empty)!='seal'],algo='sha256')
 ep<-worst_regroup_top2_plan(empty,b$cutoffs,s,'TOP2_PROB');testthat::expect_equal(nrow(ep$tickets),0)
 testthat::expect_equal(joint_candidate_settle(ep,labels)$rows$stake,0)
 testthat::expect_error(worst_regroup_top2_plan(empty,list(),s,'TOP2_PROB'))
})
testthat::test_that('period summaries separate rejected support from admitted depth',{
 g<-tidyr::expand_grid(issue=as.character(1:6),kind=c('OLD','EXP')) |> dplyr::mutate(group_id=1L,eligible=FALSE,sp_eligible=TRUE,top2_possible=FALSE,option_hit=FALSE,hit=FALSE,prefix_cost_cny=4)
 g$top2_possible[g$kind=='OLD' & g$issue %in% as.character(1:4)]<-TRUE
 g$eligible[g$kind=='OLD' & g$issue %in% as.character(1:3)]<-TRUE
 g$option_hit[g$kind=='OLD' & g$issue %in% as.character(1:2)]<-TRUE
 g$hit[g$kind=='OLD' & g$issue=='1']<-TRUE
 # An admitted losing group makes eligible_count nonzero in the rejected-winner
 # issue. Reusing 'eligible' as a summary name used to misclassify this case.
 extra<-g[g$kind=='OLD' & g$issue=='4',];extra$group_id<-2L;extra$eligible<-TRUE;extra$top2_possible<-FALSE;g<-dplyr::bind_rows(g,extra)
 fresh<-tibble::tibble(issue=as.character(1:6),group_id=1L,top2_possible=c(TRUE,TRUE,TRUE,TRUE,TRUE,FALSE))
 z<-worst_regroup_stages(g,fresh)$rows
 testthat::expect_equal(z$stage,c('OLD_DROP_HIT','OLD_OPTION_NOT_FUNDED','OLD_GROUP_UNDERDEPTH','OLD_GROUP_ADMISSION_GATE','BOUNDED_NEW_POOL_REACHABLE','NO_TOP2_WINNER_IN_SEARCH'))
 testthat::expect_equal(z$eligible_count_OLD[4],1);testthat::expect_equal(z$top2_groups_OLD[4],1);testthat::expect_equal(z$legal_top2_groups_OLD[4],0)
 testthat::expect_equal(z$minimum_top2_cost_OLD[4],4);testthat::expect_true(is.na(z$minimum_legal_top2_cost_OLD[4]))
 testthat::expect_error(worst_regroup_stages(dplyr::bind_rows(g,g[1,]),fresh))
 testthat::expect_error(worst_regroup_stages(g,fresh[-1,]))
})
