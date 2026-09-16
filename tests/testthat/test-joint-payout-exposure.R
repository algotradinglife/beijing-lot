source('../../r/n7_sleeve_tables.R');source('../../r/n7_joint_sleeves.R');source('../../r/joint_payout_exposure.R')
testthat::test_that('fixed group filtering, cutoff boundary and cash reconcile',{
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 b<-list(issue=e$issue,cutoffs=e$cutoffs,historical_admission=FALSE,seal='test',expanded_pool=list(fixtures=e$fixtures),sleeves=list(list(id=0L,fixture_indices=as.list(0:6),origin='TEST',enumeration=e,options=list())))
 v<-n7_sleeve_tables(b,b$cutoffs,'test');a<-tibble::tibble(sleeve_id=0L,depth=64L)
 args<-list(bundle=b,view=v,allocations=a,cutoffs=b$cutoffs,python=Sys.getenv('FUNDAMENTALS_PYTHON'),budget_cny=1024,unit_cny=2,minimum_payout_cny=0,fixture_cap_cny=1024,direction_cap_cny=1024)
 z<-do.call(joint_payout_exposure,args)
 testthat::expect_setequal(z$tickets$ticket_col_idx,v$rank_idx[1,1:64])
 testthat::expect_equal(z$stake,128);testthat::expect_equal(z$cash,896)
 z<-do.call(joint_payout_exposure,modifyList(args,list(fixture_cap_cny=20)))
 testthat::expect_equal(z$stake,20);testthat::expect_true(all(z$fixture_exposure<=20))
 z<-do.call(joint_payout_exposure,modifyList(args,list(direction_cap_cny=10)))
 testthat::expect_true(all(z$direction_exposure<=10))
 z<-do.call(joint_payout_exposure,modifyList(args,list(minimum_payout_cny=max(v$long$payout_hat)+1)))
 testthat::expect_equal(z$stake,0);testthat::expect_equal(z$cash,1024)
 threshold<-median(v$long$payout_hat)
 z<-do.call(joint_payout_exposure,modifyList(args,list(minimum_payout_cny=threshold)))
 expected<-v$long |> dplyr::filter(payout_hat>=threshold) |> dplyr::arrange(dplyr::desc(prob),dplyr::desc(expected_gross_contribution),ticket_col_idx) |> head(64)
 testthat::expect_identical(z$tickets$ticket_col_idx,expected$ticket_col_idx)
 testthat::expect_error(do.call(joint_payout_exposure,modifyList(args,list(allocations=dplyr::bind_rows(a,a)))))
 bad<-args;bad$cutoffs<-list();testthat::expect_error(do.call(joint_payout_exposure,bad))
})
source('../../r/joint_payout_study.R')
testthat::test_that('independent metric verification rejects fabricated diagnostics',{
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 b<-list(issue=e$issue,cutoffs=e$cutoffs,historical_admission=FALSE,seal='test',expanded_pool=list(fixtures=e$fixtures),sleeves=list(list(id=0L,fixture_indices=as.list(0:6),origin='TEST',enumeration=e,options=list())))
 v<-n7_sleeve_tables(b,b$cutoffs,'test');python<-Sys.getenv('FUNDAMENTALS_PYTHON')
 z<-joint_payout_exposure(b,v,tibble::tibble(sleeve_id=0L,depth=64L),b$cutoffs,python,1024,2,0,1024,1024)
 cfg<-list(coverage_seed=19L,coverage_worlds=256L,unit_cny=2)
 w<-n7_joint_worlds(list(cutoffs=b$cutoffs,fixtures=b$expanded_pool$fixtures),b$cutoffs,19L,256L)
 h<-(as.integer(w %*% (3^(6:0)))+1L) %in% z$tickets$ticket_col_idx
 z$union_coverage<-mean(h);z$union_mc_se<-sqrt(mean(h)*(1-mean(h))/length(h))
 z$expected_gross<-sum(z$tickets$expected_gross_contribution)
 z$max_fixture_exposure<-max(z$fixture_exposure);z$max_direction_exposure<-max(z$direction_exposure)
 plan<-list(issue=b$issue,cutoffs=b$cutoffs,plans=list(TEST=z))
 testthat::expect_true(joint_payout_verify_metrics(b,plan,cfg,python))
 for(field in c('union_coverage','union_mc_se','expected_gross','max_fixture_exposure','max_direction_exposure')) {
  bad<-plan;bad$plans$TEST[[field]]<-NULL
  testthat::expect_error(joint_payout_verify_metrics(b,bad,cfg,python))
  bad$plans$TEST[[field]]<-999
  testthat::expect_error(joint_payout_verify_metrics(b,bad,cfg,python))
 }
 for(field in c('prob','payout_hat','expected_gross_contribution')) {
  bad<-plan;bad$plans$TEST$tickets[[field]][1]<-NA_real_
  testthat::expect_error(joint_payout_verify_metrics(b,bad,cfg,python))
 }
 bad<-plan;bad$plans$TEST$groups$coverage[1]<-0
 testthat::expect_error(joint_payout_verify_metrics(b,bad,cfg,python))
})
