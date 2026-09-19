source(file.path('..','..','r','draw_refresh.R'))
source(file.path('..','..','r','draw_handicap_refresh.R'))
testthat::test_that('total refinement separates equal-handicap cells', {
 root<-normalizePath('../..');py<-Sys.getenv('RETICULATE_PYTHON')
 core<-reticulate::import('src.temporal_learning.core');api<-reticulate::import('src.temporal_learning.frozen_blocks')
 h<-expand.grid(day=1:6,slot=1:2);h$issue_code<-sprintf('%06d',h$day);h$provider_id<-paste(h$day,h$slot,sep='-')
 h$q_W<-.4;h$q_D<-.2;h$q_L<-.4;h$handicap<-0
 h$total_band<-ifelse(h$slot==1,'LOW','HIGH');h$actual<-ifelse(h$slot==1,'D','W')
 h$fixture_decision_ts<-sprintf('2011-01-%02dT00:00:00Z',h$day);h$last_fixture_cutoff<-h$fixture_decision_ts;h$day<-NULL
 b<-api$frozen_block_schedule(reticulate::r_to_py(subset(h,issue_code>='000005')),cadence=2L)[[1]]
 c<-core$Cutoff$decision_epoch(b$fit_issue,b$fit_cutoff_ts)
 m<-draw_handicap_fit(h,b,c,root,list(input=paste(rep('a',64),collapse='')),c(0,1),c(0,1),2,2,2,2,12,3,2,py,'absolute',c('handicap','total_band'))
 f<-subset(h,issue_code=='000005');f$issue<-f$issue_code;f$actual<-NULL
 z<-draw_handicap_predict(m,f,c,.5,root,py)
 testthat::expect_gt(z$new_D[1],z$new_D[2])
 testthat::expect_equal(z$h_n,c(4L,4L))
 f$total_band<-NULL;testthat::expect_error(draw_handicap_predict(m,f,c,.5,root,py))
})
