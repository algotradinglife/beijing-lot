source(file.path('..','..','r','joint_win_scale.R'))
source(file.path('..','..','r','joint_selective_add.R'))
test_that('cross-cell probability, price and exposure produce distinct selections', {
 cut<-list(cutoff_kind='DECISION_EPOCH',cutoff_identity='x',cutoff_ts='2020-01-01T00:00:00Z',historical_admission=FALSE,target_issue='01',model_receipt_sha256='m')
 t<-data.frame(issue='01',ticket_id=letters[1:4],sleeve_id=c(1,1,2,2),cell=c('a','a','b','b'),prob=c(.4,.3,.2,.1),payout_hat=c(10,10,40,60),base_copies=1L)
 m<-data.frame(sleeve_id=c(1,2),fixture=c('x','y'))
 f<-data.frame(issue='01',cell=c('a','b'),return_ratio=1.4,long_return_ratio=1.4,supported=TRUE,long_hit_signal='GOOD')
 attr(f,'input_receipt')<-list(cutoff=cut,hash=digest::digest(f,algo='sha256'))
 s<-list(alpha=.5,bad=.8,good=1.2,fraction=.5,unit=2,budget=12,n=1,fixture_cap_cny=6)
 expected<-list(ORIGINAL=c(2,1,2,1),PROB=c(2,2,1,1),EV=c(1,1,2,2),PROB_CAP=c(2,1,2,1),EV_CAP=c(2,1,2,1))
 for(p in names(expected)) {
  a<-joint_selective_add(t,m,f,cut,'m',p,s)
  expect_equal(a$copies,expected[[p]])
  expect_identical(a$copies,joint_selective_replay(t,m,f,cut,'m',p,s))
  q<-t[4:1,];q$actual_gross<-1e20
  b<-joint_selective_add(q,m,f,cut,'m',p,s)
  expect_identical(b[match(a$ticket_id,b$ticket_id),],a)
  expect_equal(joint_selective_add(t[FALSE,],m,f,cut,'m',p,s)$copies,integer())
 }
 s$fixture_cap_cny<-4
 expect_equal(joint_selective_add(t,m,f,cut,'m','PROB_CAP',s)$copies,rep(1L,4))
 s$budget<-8
 expect_equal(joint_selective_add(t,m,f,cut,'m','EV',s)$copies,rep(1L,4))
 bad<-cut;bad$target_issue<-'02'
 expect_error(joint_selective_add(t,m,f,bad,'m','EV',s))
 expect_error(joint_selective_replay(t,m,f,bad,'m','EV',s))
 expect_error(joint_selective_add(t,m[1,,drop=FALSE],f,cut,'m','EV',s))
 q<-t;q$payout_hat[1]<-NA_real_;expect_error(joint_selective_add(q,m,f,cut,'m','EV',s))
 q<-t;q$ticket_id[2]<-'a';expect_error(joint_selective_add(q,m,f,cut,'m','EV',s))
 f$return_ratio[1]<-0;expect_error(joint_selective_add(t,m,f,cut,'m','EV',s))
})
test_that('unsupported cells and unheld tickets never gain copies', {
 cut<-list(cutoff_kind='DECISION_EPOCH',cutoff_identity='x',cutoff_ts='2020-01-01T00:00:00Z',historical_admission=FALSE,target_issue='01',model_receipt_sha256='m')
 t<-data.frame(issue='01',ticket_id=letters[1:3],sleeve_id=1,cell='a',prob=c(.9,.1,.1),payout_hat=10,base_copies=c(0L,1L,1L))
 m<-data.frame(sleeve_id=1,fixture='x')
 f<-data.frame(issue='01',cell='a',return_ratio=2,long_return_ratio=1,supported=FALSE,long_hit_signal='UNKNOWN')
 attr(f,'input_receipt')<-list(cutoff=cut,hash=digest::digest(f,algo='sha256'))
 s<-list(alpha=.5,bad=.8,good=1.2,fraction=.5,unit=2,budget=12,n=1,fixture_cap_cny=12)
 for(p in c('ORIGINAL','PROB','EV','PROB_CAP','EV_CAP'))expect_equal(joint_selective_add(t,m,f,cut,'m',p,s)$copies,c(0,1,1))
 f$supported<-TRUE;f$long_hit_signal<-'GOOD';attr(f,'input_receipt')<-NULL
 attr(f,'input_receipt')<-list(cutoff=cut,hash=digest::digest(f,algo='sha256'))
 expect_equal(joint_selective_add(t,m,f,cut,'m','PROB',s)$copies,c(0,2,1))
})
