source(file.path('..','..','r','eight_strategy_validation.R'))
testthat::test_that('unresolved audit labels cannot become settlement',{
 f<-data.frame(issue='100101',slot=1,provider_id='001',handicap=0)
 l<-cbind(f,status='READY',actual_direction='W',spf_sp=2)
 testthat::expect_equal(eight_strategy_ready_labels(f,l)$spf_sp,2)
 l$status<-'PENDING';testthat::expect_error(eight_strategy_ready_labels(f,l))
 l$status<-'READY';l$provider_id<-'002';testthat::expect_error(eight_strategy_ready_labels(f,l))
 testthat::expect_error(eight_strategy_ready_labels(f,l[FALSE,]))
})
testthat::test_that('version identity cannot be set by an arbitrary model label',{
 f<-data.frame(p_W=.5,p_D=.3,p_L=.2,q_W=.5,q_D=.3,q_L=.2)
 testthat::expect_equal(eight_strategy_probability_version(f,'ARCHIVED_RAW_MARKET','ARCHIVED_RAW_MARKET'),'ARCHIVED_RAW_MARKET')
 testthat::expect_equal(eight_strategy_probability_version(f,NULL,'frozen-market'),'ARCHIVED_P_COLUMN')
 testthat::expect_error(eight_strategy_probability_version(f,NULL,'ARCHIVED_RAW_MARKET'))
 testthat::expect_error(eight_strategy_probability_version(f,'ARCHIVED_RAW_MARKET','wrong'))
 f$p_D<-.4;testthat::expect_error(eight_strategy_probability_version(f,'ARCHIVED_RAW_MARKET','ARCHIVED_RAW_MARKET'))
})
testthat::test_that('paired freeze rejects changed inputs and missing arms',{
 f<-data.frame(issue='100101',slot=1L,provider_id='001',handicap=0,p_W=.4,p_D=.3,p_L=.3,q_W=.5,q_D=.2,q_L=.3)
 c<-list('1'='2010-01-01T00:00:00Z');h<-paste(rep('a',64),collapse='')
 j<-list(issue='100101',source_sha256=h,cutoffs=c,fixtures=list(as.list(f)),
  arms=setNames(rep(list(list(options=list())),4),c('JOINT','DEPTH_OPEN','U4','CONFIDENCE')))
 t<-list(issue='100101',source_sha256=h,
  fresh=list(cutoffs=c,fixtures=f,selected=list(TOP2_DIVERSE=integer())),
  expanded=list(cutoffs=c,fixtures=f,policies=c('HARD1','HARD2','WITHIN0'),tickets=data.frame(policy=character())))
 testthat::expect_true(eight_strategy_validate_pair(j,t))
 bad<-t;bad$source_sha256<-paste(rep('b',64),collapse='');testthat::expect_error(eight_strategy_validate_pair(j,bad))
 bad<-t;bad$expanded$fixtures$p_D<-.31;testthat::expect_error(eight_strategy_validate_pair(j,bad))
 bad<-t;bad$fresh$cutoffs[[1]]<-'2011-01-01';testthat::expect_error(eight_strategy_validate_pair(j,bad))
 bad<-j;bad$arms$U4<-NULL;testthat::expect_error(eight_strategy_validate_pair(bad,t))
 bad<-t;bad$expanded$policies<-'HARD1';testthat::expect_error(eight_strategy_validate_pair(j,bad))
 bad<-t;bad$fresh$selected<-list();testthat::expect_error(eight_strategy_validate_pair(j,bad))
})
testthat::test_that('trimming never removes losses and streaks count placed bets',{
 x<-data.frame(evaluation='ALL',accounting_basis='FUNDED',policy='A',period=0:5,
  stake=c(0,2,0,2,2,2),gross=c(0,0,0,0,8,0));x$net<-x$gross-x$stake
 z<-eight_strategy_tail_diagnostics(x,c(1,3))
 testthat::expect_equal(z$trimmed$actual_removed,c(1L,1L))
 testthat::expect_equal(z$trimmed$net_cny,c(-6,-6))
 testthat::expect_equal(z$streaks$longest_no_hit_bet_run,2L)
 testthat::expect_equal(z$streaks$bet_issues,4L)
 cash<-x;cash$stake<-cash$gross<-cash$net<-0
 z<-eight_strategy_tail_diagnostics(cash,3)
 testthat::expect_equal(z$trimmed$actual_removed,0L)
 testthat::expect_equal(z$streaks$longest_no_hit_bet_run,0L)
 testthat::expect_true(is.na(z$trimmed$roi_percent))
 testthat::expect_error(eight_strategy_tail_diagnostics(x,0))
 testthat::expect_error(eight_strategy_tail_diagnostics(rbind(x,x[1,]),1))
})

testthat::test_that('only explicit absent winning SP can exclude a common issue',{
 f<-data.frame(issue='100107',slot=81,provider_id='356437',handicap=1)
 l<-transform(f,status='READY',actual_direction='L',spf_sp=2)
 testthat::expect_equal(nrow(eight_strategy_unavailable_labels(f,l)),0)
 l$status<-'spf:MISSING_WINNING_SP';l$spf_sp<-NA_real_
 testthat::expect_equal(eight_strategy_unavailable_labels(f,l),l)
 bad<-l;bad$spf_sp<-2;testthat::expect_error(eight_strategy_unavailable_labels(f,bad))
 bad<-l;bad$status<-'READY';testthat::expect_error(eight_strategy_unavailable_labels(f,bad))
 bad<-l;bad$status<-'UNKNOWN';testthat::expect_error(eight_strategy_unavailable_labels(f,bad))
 bad<-l;bad$provider_id<-'other';testthat::expect_error(eight_strategy_unavailable_labels(f,bad))
 bad<-l;bad$actual_direction<-NA_character_;testthat::expect_error(eight_strategy_unavailable_labels(f,bad))
 testthat::expect_error(eight_strategy_unavailable_labels(f,rbind(l,l)))
 testthat::expect_error(eight_strategy_unavailable_labels(f,l[FALSE,]))
})
