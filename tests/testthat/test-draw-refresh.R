source(file.path('..','..','r','draw_refresh.R'))

testthat::test_that('block cell calibration separates components and freezes target predictions', {
 root<-normalizePath('../..');py<-Sys.getenv('RETICULATE_PYTHON')
 testthat::expect_true(file.exists(py))
 reticulate::use_python(py,required=TRUE)
 core<-reticulate::import('src.temporal_learning.core')
 blocks<-reticulate::import('src.temporal_learning.frozen_blocks')
 h<-expand.grid(i=1:8,slot=1:3)
 h$issue_code<-sprintf('%06d',h$i);h$provider_id<-paste(h$i,h$slot,sep='-')
 h$q_W<-.4;h$q_D<-.2;h$q_L<-.4;h$actual<-ifelse(h$slot==1,'D','W')
 h$fixture_decision_ts<-sprintf('2011-01-%02dT00:00:00Z',h$i)
 h$last_fixture_cutoff<-h$fixture_decision_ts;h$i<-NULL
 targets<-data.frame(issue_code=c('000006','000007'),fixture_decision_ts=c('2011-01-06T00:00:00Z','2011-01-07T00:00:00Z'))
 b<-blocks$frozen_block_schedule(reticulate::r_to_py(targets),cadence=2L)[[1]]
 cutoff<-core$Cutoff$decision_epoch(b$fit_issue,b$fit_cutoff_ts)
 a<-draw_refresh_fit(h,b,cutoff,root,list(input=paste(rep('a',64),collapse='')),
   c(0,.3,1),c(0,.5,1),2,2,24,3,2,py,gap_mode='absolute')
 f<-h[h$issue_code=='000007',c('slot','provider_id','q_W','q_D','q_L','fixture_decision_ts')]
 f$issue<-'000007';c7<-core$Cutoff$decision_epoch('000007','2011-01-07T00:00:00Z')
 z<-draw_refresh_predict(a,f,c7,.5,root,py)
 testthat::expect_equal(z$n_long,rep(12L,3))
 testthat::expect_equal(z$recent_ess,rep(9,3))
 long<-(4+2*.2)/(12+2);recent<-(9/3+2*long)/(9+2)
 testthat::expect_equal(z$new_D,rep((long+recent)/2,3))
 testthat::expect_equal(z$new_W+z$new_D+z$new_L,rep(1,3))
 testthat::expect_equal(z$new_W/z$new_L,f$q_W/f$q_L)
 testthat::expect_equal(draw_refresh_predict(a,f,c7,0,root,py)$new_D,rep(long,3))
 unseen<-f;unseen$q_W<-.1;unseen$q_D<-.8;unseen$q_L<-.1
 testthat::expect_equal(draw_refresh_predict(a,unseen,c7,.5,root,py)$new_D,rep(.8,3))
 h$actual[h$issue_code %in% c('000006','000007','000008')]<-'L'
 mutated<-draw_refresh_fit(h,b,cutoff,root,list(input=paste(rep('a',64),collapse='')),
   c(0,.3,1),c(0,.5,1),2,2,24,3,2,py,gap_mode='absolute')
 testthat::expect_identical(a,mutated)
 testthat::expect_identical(z,draw_refresh_predict(mutated,f,c7,.5,root,py))
 testthat::expect_error(draw_refresh_predict(a,transform(f,actual='D'),c7,.5,root,py))
 testthat::expect_error(draw_refresh_predict(a,f,c7,1,root,py))
 testthat::expect_error(draw_refresh_predict(a,f,core$Cutoff$decision_epoch('000007','2011-01-07T01:00:00Z'),.5,root,py))
 bad<-a;bad$cells$long_rate<-1
 testthat::expect_error(draw_refresh_predict(bad,f,c7,.5,root,py))
 testthat::expect_error(draw_refresh_fit(h,b,c7,root,list(input='a'),c(0,1),c(0,1),2,2,24,3,2,py,gap_mode='absolute'))
})

testthat::test_that('post-cutoff mutation cannot change support, tickets or allocation', {
 root<-normalizePath('../..');py<-Sys.getenv('RETICULATE_PYTHON')
 reticulate::use_python(py,required=TRUE)
 for(n in c('n7_probability_replay','n7_sleeve_tables','n7_joint_sleeves','n7_capital_depth',
            'n7_capital_portfolio','n7_core_opportunity','n7_sweet_union','n7_sp_filter'))source(file.path(root,'r',paste0(n,'.R')))
 core<-reticulate::import('src.temporal_learning.core');api<-reticulate::import('src.temporal_learning.frozen_blocks')
 h<-expand.grid(i=1:8,slot=1:3);h$issue_code<-sprintf('%06d',h$i);h$provider_id<-paste(h$i,h$slot,sep='-')
 h$q_W<-.4;h$q_D<-.2;h$q_L<-.4;h$actual<-ifelse(h$slot==1,'D','W')
 h$fixture_decision_ts<-sprintf('2011-01-%02dT00:00:00Z',h$i);h$last_fixture_cutoff<-h$fixture_decision_ts;h$i<-NULL
 targets<-data.frame(issue_code=c('000006','000007','000008'),fixture_decision_ts=c('2011-01-06T00:00:00Z','2011-01-07T00:00:00Z','2011-01-08T00:00:00Z'))
 block<-api$frozen_block_schedule(reticulate::r_to_py(targets),cadence=2L)[[1]]
 fit_cut<-core$Cutoff$decision_epoch(block$fit_issue,block$fit_cutoff_ts)
 mutated<-h;future<-mutated$issue_code>='000006';mutated$actual[future]<-'L'
 mutated$fixture_decision_ts[future]<-'2010-01-01T00:00:00Z';mutated$last_fixture_cutoff[future]<-'2010-01-01T00:00:00Z'
 a<-draw_refresh_fit(h,block,fit_cut,root,list(source=paste(rep('a',64),collapse='')),c(0,.3,1),c(0,.5,1),2,2,24,3,2,py,gap_mode='absolute')
 b<-draw_refresh_fit(mutated,block,fit_cut,root,list(source=paste(rep('a',64),collapse='')),c(0,.3,1),c(0,.5,1),2,2,24,3,2,py,gap_mode='absolute')
 testthat::expect_identical(a$cells,b$cells)
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 e$issue<-'000007';e$cutoffs<-lapply(e$cutoffs,function(x)'2011-01-07T00:00:00+00:00')
 for(i in seq_along(e$fixtures))e$fixtures[[i]]$issue<-'000007'
 bundle<-list(issue=e$issue,cutoffs=e$cutoffs,historical_admission=FALSE,seal='test-bundle',
  expanded_pool=list(fixtures=e$fixtures),sleeves=list(list(id=0L,fixture_indices=as.list(0:6),origin='QUALITY',enumeration=e,options=list())))
 frame<-dplyr::bind_rows(e$fixtures);frame$fixture_decision_ts<-'2011-01-07T00:00:00+00:00'
 cutoff<-core$Cutoff$decision_epoch('000007','2011-01-07T00:00:00+00:00')
 za<-draw_refresh_predict(a,frame,cutoff,.5,root,py);zb<-draw_refresh_predict(b,frame,cutoff,.5,root,py)
 ba<-n7_probability_bundle(bundle,za,bundle$cutoffs,a$seal);bb<-n7_probability_bundle(bundle,zb,bundle$cutoffs,b$seal)
 xa<-n7_probability_allocate(ba,bundle$cutoffs,a$seal,py,.25,256,1.3,1024,2,.65,42501,256,256)
 xb<-n7_probability_allocate(bb,bundle$cutoffs,b$seal,py,.25,256,1.3,1024,2,.65,42501,256,256)
 testthat::expect_identical(xa$surface$rank_idx,xb$surface$rank_idx)
 testthat::expect_identical(xa$gate,xb$gate)
 testthat::expect_identical(xa$pool$options,xb$pool$options)
 testthat::expect_identical(xa$fit,xb$fit)
})

testthat::test_that('signed bins retain mirrored direction and absolute bins agree with legacy', {
 c<-reticulate::import('src.temporal_learning.core')$Cutoff$decision_epoch('000001','2011-01-01T00:00:00Z')
 f<-data.frame(q_W=c(.5,.25,.375),q_D=c(.25,.25,.25),q_L=c(.25,.5,.375))
 a<-draw_refresh_bins(f,c,c(0,.2,.3,1),c(0,.1,.2,.3,1),'absolute')
 b<-draw_refresh_bins(f,c,c(0,.2,.3,1),c(-1,-.3,-.2,-.1,0,.1,.2,.3,1),'signed')
 testthat::expect_equal(a$secondary_bin,c(2L,2L,0L))
 testthat::expect_equal(b$secondary_bin,c(6L,1L,4L))
 testthat::expect_equal(a$market_bin,b$market_bin)
 testthat::expect_error(draw_refresh_bins(f,c,c(0,1),c(0,1),'signed'))
 testthat::expect_error(draw_refresh_bins(transform(f,q_D=NA),c,c(0,1),c(0,1),'absolute'))
})
