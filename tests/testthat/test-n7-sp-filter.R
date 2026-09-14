source(file.path('..','..','r','n7_sp_filter.R'))
testthat::test_that('SP gate keeps exact threshold and removes complete groups without reindexing', {
 cuts<-list(a='epoch')
 f<-list(p_W=.5,p_D=.3,p_L=.2,q_W=.5,q_D=.3,q_L=.2)
 low<-f;low$q_W<-.8;low$q_D<-.1;low$q_L<-.1
 base<-list(cutoffs=cuts,fixtures=c(rep(list(f),7),list(low)),
   options=list(list(sleeve_id=0,fixtures=1:7),list(sleeve_id=1,fixtures=2:8)))
 part<-list(cutoffs=cuts,core_ids=0:1,opening_depths=c('0'=15,'1'=32),
   opportunity_ids=integer(),opportunity_depth=15L,opportunity_stake_cny=0)
 all<-n7_sp_filter(base,part,cuts,1)
 testthat::expect_identical(all$partition,part)
 z<-n7_sp_filter(base,part,cuts,2)
 testthat::expect_identical(z$partition$core_ids,0L)
 testthat::expect_equal(z$partition$opening_depths,c('0'=15))
 testthat::expect_equal(z$fixtures$fixture_index,1:8)
 testthat::expect_equal(z$groups$eligible,c(TRUE,FALSE))
 testthat::expect_equal(z$fixtures$estimated_sp,c(rep(2,7),1.25))
 none<-n7_sp_filter(base,part,cuts,2.01)
 testthat::expect_length(none$partition$core_ids,0)
 testthat::expect_length(none$partition$opening_depths,0)
 opp<-part;opp$core_ids<-0L;opp$opening_depths<-c('0'=15);opp$opportunity_ids<-1L;opp$opportunity_stake_cny<-30
 testthat::expect_equal(n7_sp_filter(base,opp,cuts,2)$partition$opportunity_stake_cny,0)
 bad<-base;bad$fixtures[[1]]$q_W<-NA_real_
 testthat::expect_error(n7_sp_filter(bad,part,cuts,1))
 bad<-base;bad$fixtures[[1]]$q_W<-0
 testthat::expect_error(n7_sp_filter(bad,part,cuts,1))
 testthat::expect_error(n7_sp_filter(base,part,list(a='later'),1))
 testthat::expect_error(n7_sp_filter(base,part,cuts,NA_real_))
 testthat::expect_error(n7_sp_filter(base,part,cuts,.9))
 bad<-base;bad$options[[1]]$fixtures<-rep(1,7)
 testthat::expect_error(n7_sp_filter(bad,part,cuts,1))
 # Gate uses probability Top1, not shortest q price; deterministic W,D,L tie.
 tie<-base;tie$fixtures[[1]]<-list(p_W=.4,p_D=.4,p_L=.2,q_W=.2,q_D=.6,q_L=.2)
 testthat::expect_equal(n7_sp_filter(tie,part,cuts,1)$fixtures$estimated_sp[1],5)
 # Settlement metadata must have no influence on gate decisions.
 mutated<-base;mutated$settlement<-list(actual_rank=1,spf_sp=999)
 testthat::expect_identical(n7_sp_filter(mutated,part,cuts,2),z)
})

testthat::test_that('equivalence classes preserve every policy and separate rules or admitted groups', {
 cuts<-list(a='epoch');f<-list(p_W=.5,p_D=.3,p_L=.2,q_W=.5,q_D=.3,q_L=.2)
 base<-list(cutoffs=cuts,fixtures=rep(list(f),7),options=list(list(sleeve_id=0,fixtures=1:7)))
 part<-list(cutoffs=cuts,core_ids=0L,opening_depths=c('0'=15),opportunity_ids=integer(),
   opportunity_depth=15L,opportunity_stake_cny=0)
 policies<-data.frame(id=letters[1:4],minimum_sp=c(1.1,1.2,2.1,1.1),mode='DEPTH',
   objective=c('any_hit','any_hit','any_hit','expected_net'),allocation_order='OPEN_FIRST')
 z<-n7_sp_policy_groups(base,part,cuts,policies)
 testthat::expect_identical(z$classes,list(1:2,3L,4L))
 testthat::expect_equal(vapply(z$gates,`[[`,numeric(1),'minimum_sp'),policies$minimum_sp)
 testthat::expect_identical(z$gates[[1]]$partition,z$gates[[2]]$partition)
 testthat::expect_length(z$gates[[3]]$partition$core_ids,0)
 testthat::expect_error(n7_sp_policy_groups(base,part,list(a='later'),policies))
 policies$id[2]<-policies$id[1]
 testthat::expect_error(n7_sp_policy_groups(base,part,cuts,policies))
})
