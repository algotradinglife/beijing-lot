for(n in c('n7_joint_sleeves','n7_sp_filter','top2_fresh_groups','eight_strategy_validation','top2_return_filter'))source(file.path('..','..','r',paste0(n,'.R')))
testthat::test_that('fixed return gates preserve original tickets and recycle only removed funds',{
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 f<-dplyr::bind_rows(e$fixtures);f$p_W<-.5;f$p_D<-.3;f$p_L<-.2;f$q_W<-.5;f$q_D<-.3;f$q_L<-.2
 py<-Sys.getenv('RETICULATE_PYTHON');f<-f[c('issue','slot','provider_id','handicap',paste0('p_',c('W','D','L')),paste0('q_',c('W','D','L')))]
 extra<-f[1:3,];extra$slot<-max(f$slot)+1:3;extra$provider_id<-paste0('extra',1:3)
 f<-rbind(f,extra);cuts<-c(e$cutoffs,setNames(rep(e$cutoffs[1],3),as.character(extra$slot)))
 s<-top2_fresh_groups(f,cuts,py,7,1024,2,.65,1.3)
 z<-top2_return_filter_plan(s,cuts,py,c(128,256,512,1024),7,1024,2,.65)
 testthat::expect_equal(nrow(z$arms$BASE),512L)
 boundary<-min(z$arms$BASE$estimated_gross)
 equal<-top2_return_filter_plan(s,cuts,py,boundary,7,1024,2,.65)
 testthat::expect_equal(nrow(equal$arms[[2]]),512L)
 none<-top2_return_filter_plan(s,cuts,py,1e12,7,1024,2,.65)
 testthat::expect_equal(nrow(none$arms[[2]]),0L)
 testthat::expect_equal(nrow(none$arms[[3]]),0L)
 testthat::expect_equal(z$arms$CASH_128,z$arms$BASE)
 testthat::expect_equal(nrow(z$arms$CASH_256),508L) # only W7 falls below 256; W6D returns 277.33
 testthat::expect_equal(nrow(z$arms$REFILL_256),512L)
 testthat::expect_true(all(z$arms$REFILL_256$estimated_gross>=256))
 testthat::expect_equal(sum(!z$arms$REFILL_256$original),4L)
 testthat::expect_false(anyDuplicated(z$arms$REFILL_256[c('group_id','code')])>0)
 testthat::expect_equal(z$arms$BASE$probability*z$arms$BASE$estimated_gross,rep(1.3,512))
 for(t in c(256,512,1024))testthat::expect_true(all(z$arms[[paste0('CASH_',t)]]$original))
 lab<-transform(f[c('issue','slot','provider_id','handicap')],status='READY',actual_direction='W',spf_sp=2)
 out<-top2_return_filter_settle(z,lab)$rows
 testthat::expect_false(anyNA(out))
 testthat::expect_equal(out$gross,out$retained_gross+out$added_gross)
 testthat::expect_equal(out$retained_gross[out$policy=='BASE'],4*1.3*2^7)
 testthat::expect_equal(out$gross[out$policy=='BASE'],4*1.3*2^7)
 testthat::expect_equal(out$gross[out$policy=='CASH_256'],0)
 testthat::expect_equal(out$stake[out$policy=='CASH_256'],1016)
 # Labels/official prices cannot change frozen allocation, even after inspection.
 lab$actual_direction<-'D';lab$spf_sp<-8;top2_return_filter_settle(z,lab)
 testthat::expect_identical(z,top2_return_filter_plan(s,cuts,py,c(128,256,512,1024),7,1024,2,.65))
 testthat::expect_error(top2_return_filter_plan(s,list(),py,256,7,1024,2,.65))
 testthat::expect_error(top2_return_filter_plan(s,cuts,py,NA_real_,7,1024,2,.65))
 testthat::expect_error(top2_return_filter_plan(s,cuts,py,c(256,256),7,1024,2,.65))
 bad<-z;bad$arms$BASE$code[1]<-99L;testthat::expect_error(top2_return_filter_settle(bad,lab))
 testthat::expect_error(top2_return_filter_settle(z,lab[-1,]))
 lab$status[1]<-'PENDING';testthat::expect_error(top2_return_filter_settle(z,lab));lab$status[1]<-'READY'
 one<-top2_fresh_groups(f[1:7,],e$cutoffs,py,7,1024,2,.65,1.3)
 a<-top2_return_filter_plan(one,e$cutoffs,py,256,7,1024,2,.65)
 testthat::expect_equal(a$arms$CASH_256,a$arms$REFILL_256) # no unused candidate
 empty<-top2_fresh_groups(f[1:7,],e$cutoffs,py,7,1024,2,.65,3)
 a<-top2_return_filter_plan(empty,e$cutoffs,py,256,7,1024,2,.65)
 testthat::expect_equal(nrow(a$arms$BASE),0L)
 testthat::expect_true(all(top2_return_filter_settle(a,lab[1:7,])$rows$stake==0))
})
