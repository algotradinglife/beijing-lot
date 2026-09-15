source(file.path('..','..','r','draw_refresh.R'))
source(file.path('..','..','r','draw_handicap_refresh.R'))
source(file.path('..','..','r','draw_correction_candidates.R'))
testthat::test_that('fixed correction candidates bind chronology and preserve probability contracts', {
 root<-normalizePath('../..');py<-Sys.getenv('RETICULATE_PYTHON')
 reticulate::use_python(py,required=TRUE)
 core<-reticulate::import('src.temporal_learning.core')
 blocks<-reticulate::import('src.temporal_learning.frozen_blocks')
 h<-expand.grid(i=1:8,slot=1:3)
 h$issue_code<-sprintf('%06d',h$i);h$provider_id<-paste(h$i,h$slot,sep='-')
 h$q_W<-.4;h$q_D<-.2;h$q_L<-.4;h$actual<-ifelse(h$slot==1,'D','W')
 h$handicap<-c(-1,0,1)[h$slot]
 h$fixture_decision_ts<-sprintf('2011-01-%02dT00:00:00Z',h$i)
 h$last_fixture_cutoff<-h$fixture_decision_ts;h$i<-NULL
 targets<-data.frame(issue_code=c('000006','000007','000008'),
  fixture_decision_ts=c('2011-01-06T00:00:00Z','2011-01-07T00:00:00Z','2011-01-08T00:00:00Z'))
 b<-blocks$frozen_block_schedule(reticulate::r_to_py(targets),cadence=2L)[[1]]
 cutoff<-core$Cutoff$decision_epoch(b$fit_issue,b$fit_cutoff_ts)
 a<-draw_handicap_fit(h,b,cutoff,root,list(input=paste(rep('a',64),collapse='')),
  c(0,.3,1),c(0,.5,1),2,2,2,2,24,3,2,py)
 f<-h[h$issue_code=='000007',c('slot','provider_id','handicap','q_W','q_D','q_L','fixture_decision_ts')]
 f$issue<-'000007';c7<-core$Cutoff$decision_epoch('000007','2011-01-07T00:00:00Z')

 z<-draw_correction_candidates(a,f,c7,.5,c(.25,.5),100,100,1.96,root,py)
 testthat::expect_equal(nrow(z$rows),18L)
 testthat::expect_equal(z$rows$W+z$rows$D+z$rows$L,rep(1,18))
 testthat::expect_equal(z$rows$W/z$rows$L,rep(1,18))
 raw<-subset(z$rows,model=='RAW'); dyn<-subset(z$rows,model=='DYNAMIC')
 testthat::expect_equal(raw$D,rep(.2,3))
 testthat::expect_equal(subset(z$rows,model=='WEAK_0.25')$D,.2+.25*(dyn$D-.2))
 testthat::expect_equal(subset(z$rows,model=='SPARSE')$correction_weight,rep(4/104,3))
 testthat::expect_equal(subset(z$rows,model=='LOCAL')$D,raw$D)
 active<-draw_correction_candidates(a,f,c7,.5,.25,100,1,.1,root,py)
 testthat::expect_true(all(subset(active$rows,model=='LOCAL')$correction_weight==1))
 testthat::expect_identical(z$receipt$target_issue,'000007')
 testthat::expect_error(draw_correction_candidates(a,transform(f,actual_outcome='W'),c7,.5,.25,100,100,1.96,root,py))
 testthat::expect_error(draw_correction_candidates(a,f,cutoff,.5,.25,100,100,1.96,root,py))
 testthat::expect_error(draw_correction_candidates(a,f,c7,.5,1,100,100,1.96,root,py))
 changed<-h;future<-changed$issue_code>='000006';changed$actual[future]<-'L'
 changed$fixture_decision_ts[future]<-'2010-01-01T00:00:00Z';changed$last_fixture_cutoff[future]<-'2010-01-01T00:00:00Z'
 aa<-draw_handicap_fit(changed,b,cutoff,root,list(input=paste(rep('a',64),collapse='')),
  c(0,.3,1),c(0,.5,1),2,2,2,2,24,3,2,py)
 zz<-draw_correction_candidates(aa,f,c7,.5,c(.25,.5),100,100,1.96,root,py)
 testthat::expect_identical(z$rows,zz$rows)
})

testthat::test_that('evaluation identity verification rejects missing and changed helpers', {
 source(file.path('..','..','r','strategy_diagnostic_probabilities.R'))
 root<-tempfile();dir.create(root)
 writeLines('scoring helper',file.path(root,'scoring.R'))
 hashes<-list(scoring.R=digest::digest(file=file.path(root,'scoring.R'),algo='sha256'))
 testthat::expect_invisible(strategy_verify_diagnostic_inputs(root,hashes,'scoring.R'))
 testthat::expect_error(strategy_verify_diagnostic_inputs(root,list(),'scoring.R'))
 writeLines('changed scoring',file.path(root,'scoring.R'))
 testthat::expect_error(strategy_verify_diagnostic_inputs(root,hashes,'scoring.R'))
})
