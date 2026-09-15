for(f in c('n7_probability_replay','n7_sleeve_tables','n7_joint_sleeves','n7_capital_depth',
           'n7_capital_portfolio','n7_core_opportunity','n7_sweet_union','n7_sp_filter'))
 source(file.path('..','..','r',paste0(f,'.R')))

testthat::test_that('reweighting preserves fixture/price identity and canonical ranking', {
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 b<-list(issue=e$issue,cutoffs=e$cutoffs,historical_admission=FALSE,seal='test',
  expanded_pool=list(fixtures=e$fixtures),sleeves=list(list(id=0L,fixture_indices=as.list(0:6),origin='QUALITY',enumeration=e,options=list())))
 f<-dplyr::bind_rows(e$fixtures)
 f$new_W<-f$p_W;f$new_D<-f$p_D;f$new_L<-f$p_L
 same<-n7_probability_bundle(b,f,b$cutoffs,'same')
 a<-n7_sleeve_tables(b,b$cutoffs,'old');z<-n7_sleeve_tables(same,b$cutoffs,'same')
 testthat::expect_equal(a$prob_mat,z$prob_mat,tolerance=1e-12)
 testthat::expect_equal(a$rank_idx,z$rank_idx)
 f$new_D<-.7;f$new_W<-.2;f$new_L<-.1
 new<-n7_probability_bundle(b,f,b$cutoffs,'new')
 y<-n7_sleeve_tables(new,b$cutoffs,'new')
 testthat::expect_equal(y$payout_hat_mat,a$payout_hat_mat)
 testthat::expect_equal(max(y$prob_mat),.7^7)
 testthat::expect_equal(sum(y$prob_mat),1)
 testthat::expect_false(identical(new$seal,b$seal))
 bad<-b;bad$sleeves[[1]]$enumeration$estimated_payout<-as.list(2*unlist(e$estimated_payout))
 testthat::expect_error(n7_probability_bundle(bad,f,b$cutoffs,'bad-price'))
 testthat::expect_error(n7_probability_bundle(b,transform(f,new_D=1),b$cutoffs,'bad'))
 testthat::expect_error(n7_probability_bundle(b,f[-1,],b$cutoffs,'bad'))
 testthat::expect_error(n7_probability_bundle(b,transform(f,actual='D'),b$cutoffs,'bad'))
 py<-Sys.getenv('RETICULATE_PYTHON')
 testthat::expect_true(file.exists(py))
 fit<-n7_probability_allocate(new,b$cutoffs,'new',py,.25,256,1.3,1024,2,.65,42501,256,256)
 testthat::expect_equal(length(fit$fit$selected),1)
 testthat::expect_lte(fit$pool$options[[fit$fit$selected]]$stake,256)
 testthat::expect_gte(fit$pool$options[[fit$fit$selected]]$coverage,.25)
 empty<-n7_probability_allocate(new,b$cutoffs,'new',py,.25,256,1e9,1024,2,.65,42501,256,256)
 testthat::expect_length(empty$fit$selected,0)
 testthat::expect_error(n7_probability_allocate(new,b$cutoffs,'new',py,.25,256,1.3,1024,2,.7,42501,256,256))
})
