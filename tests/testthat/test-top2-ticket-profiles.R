for(n in c('n7_joint_sleeves','n7_sp_filter','top2_fresh_groups','eight_strategy_validation','top2_return_filter','top2_ticket_profiles'))source(file.path('..','..','r',paste0(n,'.R')))
testthat::test_that('ticket profiles are label-free, partitioned and independently interpretable',{
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 f<-dplyr::bind_rows(e$fixtures);f$p_W<-.5;f$p_D<-.3;f$p_L<-.2;f$q_W<-.5;f$q_D<-.3;f$q_L<-.2
 extra<-f[1:3,];extra$slot<-max(f$slot)+1:3;extra$provider_id<-paste0('extra',1:3)
 f<-rbind(f,extra);cuts<-c(e$cutoffs,setNames(rep(e$cutoffs[1],3),as.character(extra$slot)))
 py<-Sys.getenv('RETICULATE_PYTHON');s<-top2_fresh_groups(f,cuts,py,7,1024,2,.65,1.3)
 z<-top2_return_filter_plan(s,cuts,py,512,7,1024,2,.65)
 a<-top2_ticket_profiles(z,cuts,512,.5,.3,.2);x<-a$rows
 testthat::expect_equal(nrow(x),512+sum(!z$arms$REFILL_512$original))
 testthat::expect_equal(sum(x$role=='RETAINED'),nrow(z$arms$CASH_512))
 testthat::expect_equal(x$top1_count+x$top2_count,rep(7,nrow(x)))
 testthat::expect_equal(x$core_count,x$top1_count)
 testthat::expect_equal(x$weak_count,rep(0,nrow(x)))
 testthat::expect_equal(x$min_leg_p,ifelse(x$top2_count>0,.3,.5))
 testthat::expect_equal(x$estimated_ev_roi,rep(-.35,nrow(x)))
 testthat::expect_equal(a$groups$top2_mass,rep(.8^7,nrow(a$groups)))
 testthat::expect_true(all(a$groups$top64_share>.5 & a$groups$top64_share<1))
 testthat::expect_true(all(x$max_refill_direction_exposure>=0 & x$max_refill_direction_exposure<=1))
 # Pure independent hand-count of exposure for first ticket's seven selections.
 first<-x[1,];g<-z$groups[[first$group_id]];state<-((first$code-1)%/%3^(6:0))%%3+1
 manual<-numeric(7)
 for(k in 1:7)for(j in seq_len(nrow(z$arms$REFILL_512))) {
  row<-z$arms$REFILL_512[j,];ix<-z$groups[[row$group_id]];position<-match(g[k],ix)
  if(!is.na(position))manual[k]<-manual[k]+(((row$code-1)%/%3^(7-position))%%3+1==state[k])
 }
 testthat::expect_equal(first$max_refill_direction_exposure,max(manual)/nrow(z$arms$REFILL_512))
 lab<-transform(f[c('issue','slot','provider_id','handicap')],status='READY',actual_direction='W',spf_sp=2)
 y<-top2_ticket_profile_labels(a,z,lab)
 testthat::expect_equal(sum(y$gross),4*1.3*2^7)
 testthat::expect_equal(sum(y$gross[y$role=='REMOVED']),4*1.3*2^7)
 testthat::expect_false(anyNA(y$gross));testthat::expect_equal(sum(y$hit),4)
 lab$actual_direction<-'D';lab$spf_sp<-3
 testthat::expect_identical(a,top2_ticket_profiles(z,cuts,512,.5,.3,.2))
 testthat::expect_error(top2_ticket_profile_labels(a,z,lab[-1,]))
 bad<-a;bad$rows$role[1]<-'ADDED';testthat::expect_error(top2_ticket_profile_labels(bad,z,lab))
 testthat::expect_error(top2_ticket_profiles(z,list(),512,.5,.3,.2))
 testthat::expect_error(top2_ticket_profiles(z,cuts,256,.5,.3,.2))
 y$cohort<-'ONE';b<-list(min_leg_p=c(0,.25,.35,.45,1.01),max_log_sp_share=c(0,.2,.3,1.01))
 out<-top2_ticket_profile_summary(y,b,c(1,3,5),unique(y$issue))
 total<-dplyr::filter(out$summary,evaluation=='ALL',feature=='ALL')
 testthat::expect_equal(sum(total$tickets),nrow(y));testthat::expect_equal(sum(total$gross_cny),sum(y$gross))
 testthat::expect_equal(total$net_cny,total$model_net+total$outcome_residual+total$price_residual)
 removed<-dplyr::filter(out$trimmed,evaluation=='ALL',feature=='ALL',role=='REMOVED',k==1)
 testthat::expect_equal(removed$removed_issues,1);testthat::expect_equal(removed$stake_cny,0)
 testthat::expect_true(is.na(removed$roi_percent))
 testthat::expect_error(top2_ticket_profile_summary(rbind(y,y[1,]),b,1,unique(y$issue)))
 testthat::expect_error(top2_ticket_profile_summary(y,list(min_leg_p=c(.4,1)),1,unique(y$issue)))
})
testthat::test_that('cell-specific trims respect different winners, ties and all three cohorts',{
 y<-tibble::tibble(issue=rep(sprintf('%02d',1:6),each=2),group_id=rep(1:2,6),code=1L,role='ADDED',
  cohort=rep(rep(c('EARLY','OLD','NEW'),each=2),each=2),top2_count=rep(c(0,2),6),core_count=4L,weak_count=1L,
  max_log_sp_share=.25,probability=.01,estimated_gross=100,stake=2,
  gross=as.vector(rbind(c(20,20,0,0,12,0),c(0,0,30,10,0,24)))) |>
  dplyr::mutate(hit=gross>0,net=gross-stake)
 a<-top2_ticket_profile_summary(y,list(probability=c(0,.02,1.01)),c(1,3,5),unique(y$issue))
 s<-dplyr::filter(a$summary,evaluation=='ALL',feature=='second_count')
 testthat::expect_equal(s$gross_cny,c(52,64));testthat::expect_equal(s$stake_cny,c(12,12))
 t<-dplyr::filter(a$trimmed,evaluation=='ALL',feature=='second_count',k==1)
 testthat::expect_equal(t$gross_cny,c(32,34));testthat::expect_equal(t$stake_cny,c(10,10))
 testthat::expect_equal(t$roi_percent,c(220,240))
 for(k in c(3,5)) {
  z<-dplyr::filter(a$trimmed,evaluation=='ALL',feature=='second_count',.data$k==.env$k)
  testthat::expect_equal(z$removed_issues,c(3L,3L));testthat::expect_equal(z$stake_cny,c(6,6))
  testthat::expect_equal(z$gross_cny,c(0,0));testthat::expect_equal(z$roi_percent,c(-100,-100))
 }
 t<-dplyr::filter(a$trimmed,evaluation=='EARLY',feature=='second_count',bin=='0',k==3)
 testthat::expect_equal(t$removed_issues,2L);testthat::expect_true(is.na(t$roi_percent))
})
testthat::test_that('heterogeneous Top2 enumeration verifies mass, depth and entropy',{
 e<-jsonlite::fromJSON(gzfile('../fixtures/n7_sleeve_numerical.json.gz'),simplifyVector=FALSE)$enumeration
 f<-dplyr::bind_rows(e$fixtures);f$p_W<-seq(.45,.7,length.out=7);f$p_D<-(1-f$p_W)*.6;f$p_L<-(1-f$p_W)*.4
 f$q_W<-f$p_W;f$q_D<-f$p_D;f$q_L<-f$p_L;py<-Sys.getenv('RETICULATE_PYTHON')
 s<-top2_fresh_groups(f,e$cutoffs,py,7,1024,2,.65,1.3)
 z<-top2_return_filter_plan(s,e$cutoffs,py,512,7,1024,2,.65)
 a<-top2_ticket_profiles(z,e$cutoffs,512,.5,.3,.2)
 states<-as.matrix(expand.grid(rep(list(1:2),7)));p<-as.matrix(f[paste0('p_',c('W','D','L'))])
 probs<-apply(states,1,function(row)prod(p[cbind(1:7,row)]));cum<-cumsum(sort(probs,decreasing=TRUE))
 testthat::expect_equal(unname(a$groups$top64_mass),unname(cum[64]));testthat::expect_equal(unname(a$groups$top64_share),unname(cum[64]/sum(probs)))
 testthat::expect_equal(unname(a$groups$depth_target),unname(which(cum>=.2)[1]));testthat::expect_equal(a$groups$entropy,-sum(p*log(p)))
 unreachable<-top2_ticket_profiles(z,e$cutoffs,512,.5,.3,.99)
 testthat::expect_true(is.na(unreachable$groups$depth_target))
})
