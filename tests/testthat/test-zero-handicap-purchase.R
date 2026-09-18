for(n in c('n7_joint_sleeves','n7_sleeve_tables','n7_probability_replay','n7_sp_filter','top2_fresh_groups','joint_candidate_comparison','zero_handicap_purchase'))source(file.path('..','..','r',paste0(n,'.R')))
testthat::test_that('zero intervention preserves controls and fails on missing odds or labels', {
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 f<-dplyr::bind_rows(e$fixtures);f$handicap[1:2]<-c(0,1);py<-Sys.getenv('RETICULATE_PYTHON')
 euro<-f[f$handicap==0,c('issue','slot','provider_id','handicap')];euro$odds_W<-2;euro$odds_D<-4;euro$odds_L<-4
 z<-zero_purchase_fixtures(f,euro,e$cutoffs,py,'EURO_P');zz<-zero_purchase_fixtures(f,euro,e$cutoffs,py,'EURO_PQ')
 testthat::expect_identical(zero_purchase_fixtures(f,euro,e$cutoffs,py,'BASE'),f)
 testthat::expect_identical(z[f$handicap!=0,],f[f$handicap!=0,])
 testthat::expect_identical(z[paste0('q_',c('W','D','L'))],f[paste0('q_',c('W','D','L'))])
 testthat::expect_equal(z$p_W[f$handicap==0],rep(.5,nrow(euro)))
 testthat::expect_equal(zz$q_D[f$handicap==0],rep(.25,nrow(euro)))
 testthat::expect_error(zero_purchase_fixtures(f,euro[-1,],e$cutoffs,py,'EURO_P'))
 testthat::expect_error(zero_purchase_fixtures(f,transform(euro,odds_W=NA),e$cutoffs,py,'EURO_P'))
 testthat::expect_error(zero_purchase_fixtures(f,transform(euro,actual='W'),e$cutoffs,py,'EURO_P'))
 testthat::expect_error(zero_purchase_fixtures(transform(f,actual_direction='W'),euro,e$cutoffs,py,'EURO_P'))
 testthat::expect_error(zero_purchase_fixtures(f,euro,list(),py,'EURO_P'))
})
testthat::test_that('bundle price and mass revaluation is independent of settlement', {
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 b<-list(issue=e$issue,cutoffs=e$cutoffs,historical_admission=FALSE,seal='test',expanded_pool=list(fixtures=e$fixtures),sleeves=list(list(id=0L,fixture_indices=as.list(0:6),origin='QUALITY',enumeration=e,options=list())))
 f<-dplyr::bind_rows(e$fixtures);f$p_W<-.5;f$p_D<-.3;f$p_L<-.2;f$q_W<-.4;f$q_D<-.35;f$q_L<-.25
 z<-zero_purchase_bundle(b,f,b$cutoffs,'test',2,.65);v<-n7_sleeve_tables(z,b$cutoffs,'test')
 testthat::expect_equal(v$prob_mat[1,1],.5^7);testthat::expect_equal(v$payout_hat_mat[1,1],1.3/.4^7)
 testthat::expect_equal(sum(v$prob_mat),1);testthat::expect_identical(z$sleeves[[1]]$fixture_indices,b$sleeves[[1]]$fixture_indices)
 testthat::expect_error(zero_purchase_bundle(b,f[-1,],b$cutoffs,'test',2,.65))
 testthat::expect_error(zero_purchase_bundle(b,f,list(),'test',2,.65))
})
testthat::test_that('fixed Top2 reproduces native baseline and respects emptied gate', {
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 f<-dplyr::bind_rows(e$fixtures);f$p_W<-.5;f$p_D<-.3;f$p_L<-.2;f$q_W<-.5;f$q_D<-.3;f$q_L<-.2;py<-Sys.getenv('RETICULATE_PYTHON')
 fresh<-top2_fresh_groups(f,e$cutoffs,py,7,1024,2,.65,1.3);z<-zero_purchase_top2(fresh,f,e$cutoffs,py)
 testthat::expect_identical(z$groups,fresh$groups);testthat::expect_identical(z$options,fresh$options);testthat::expect_identical(z$selected$TOP2_DIVERSE,fresh$selected$TOP2_DIVERSE)
 ff<-f;ff$p_D<-.15;ff$p_L<-.35;zz<-zero_purchase_top2(fresh,ff,e$cutoffs,py)
 testthat::expect_equal(unname(zz$options[1,]),c(1,3));testthat::expect_identical(zz$groups,fresh$groups)
 ff$q_W<-.9;ff$q_D<-.05;ff$q_L<-.05;testthat::expect_length(zero_purchase_top2(fresh,ff,e$cutoffs,py)$selected$TOP2_DIVERSE,0)
 testthat::expect_error(zero_purchase_top2(fresh,f,list(),py))
})
testthat::test_that('canonical ticket adapter uses exact existing settlement contract', {
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration;f<-dplyr::bind_rows(e$fixtures)
 g<-tibble::tibble(group_id=1L,fixture_index=1:7);o<-list(sleeve_id=1,state_ids=c(1L,2L),state_probability=rep(1/2187,2187),state_payout=rep(100,2187));s<-list(unit_cny=2,payout_factor=.65,budget_cny=1024)
 p<-zero_purchase_tickets(f,g,list(o),e$cutoffs,s,'TEST');lab<-f[c('issue','slot','provider_id','handicap')];lab$actual_direction<-'W';lab$spf_sp<-2
 z<-joint_candidate_settle(p,lab);testthat::expect_equal(z$rows$gross,1.3*2^7);testthat::expect_equal(z$rows$stake,4);testthat::expect_equal(z$rows$hits,1)
 lab$actual_direction<-'L';testthat::expect_equal(joint_candidate_settle(p,lab)$rows$gross,0)
 empty<-zero_purchase_tickets(f,g,list(),e$cutoffs,s,'TEST');testthat::expect_equal(joint_candidate_settle(empty,lab)$rows$stake,0)
 testthat::expect_error(zero_purchase_tickets(f,g,list(o,o),e$cutoffs,s,'TEST'))
 testthat::expect_error(zero_purchase_tickets(f,g,list(o),list(),s,'TEST'))
})
testthat::test_that('parallel merge rejects differing parent identities and parameters', {
 cfg<-list(scope_sha256='s',euro_manifest_sha256='e',top2=list(path='t',sha256='t1'),joint=list(path='j',sha256='j1'),reference=list(path='r',sha256='r1'),settings=list(budget_cny=1024L))
 part<-list(status='FROZEN_NOT_SETTLED',config=cfg,code=list(x='hash'),closure=list(closure_sha256='c'))
 testthat::expect_true(zero_purchase_chunk(part,cfg,part$code,'c'))
 for(k in c('top2','joint','reference'))for(field in c('path','sha256')){
  bad<-part;bad$config[[k]][[field]]<-'other';testthat::expect_error(zero_purchase_chunk(bad,cfg,part$code,'c'))
 }
 bad<-part;bad$config$settings$budget_cny<-2048L;testthat::expect_error(zero_purchase_chunk(bad,cfg,part$code,'c'))
 testthat::expect_error(zero_purchase_chunk(part,cfg,list(x='different'),'c'))
 testthat::expect_error(zero_purchase_chunk(part,cfg,part$code,'different'))
})
