source(file.path('..','..','r','joint_tail_risk.R'))
test_that('fixed overlays cut integer tickets with bound model and cutoff', {
 c<-list(cutoff_kind='DECISION_EPOCH',historical_admission=FALSE,target_issue='1',model_receipt_sha256='sha')
 t<-data.frame(issue='1',ticket_id=letters[1:8],cell=rep(c('a','b'),each=4),
  prob=c(.01,.005,.0015,.001,.009,.004,.0014,.001),base_copies=1L)
 s<-data.frame(issue='1',cell=c('a','b'),long_hit_signal='GOOD',supported=TRUE,
  hit_ratio=c(.5,1),long_return_ratio=c(.5,1))
 attr(s,'input_receipt')<-list(cutoff=c,hash=digest::digest(s,algo='sha256'))
 expect_equal(joint_tail_risk(t,s,c,'sha','KEEP',.25,.002,.25,.8,1,2,16)$copies,rep(1L,8))
 expect_equal(joint_tail_risk(t,s,c,'sha','CELL_CAP',.25,.002,.25,.8,1,2,16)$copies,c(1,1,0,0,1,1,0,0))
 expect_equal(joint_tail_risk(t,s,c,'sha','LOWP_CAP',.25,.002,.25,.8,1,2,16)$copies,c(1,1,1,0,1,1,1,0))
 expect_equal(joint_tail_risk(t,s,c,'sha','RECENT_LOW',.25,.002,.25,.8,1,2,16)$copies,c(1,1,1,0,1,1,1,1))
 expect_equal(joint_tail_risk(t,s,c,'sha','LONG_RETURN',.25,.002,.25,.8,1,2,16)$copies,c(1,1,0,0,1,1,1,1))
 other<-c;other$target_issue<-'2'
 expect_error(joint_tail_risk(t,s,other,'sha','KEEP',.25,.002,.25,.8,1,2,16))
 expect_error(joint_tail_risk(t,s,c,'different','KEEP',.25,.002,.25,.8,1,2,16))
 s$hit_ratio[1]<-.9
 expect_error(joint_tail_risk(t,s,c,'sha','KEEP',.25,.002,.25,.8,1,2,16))
})
test_that('window drawdown uses its own opening point and zero stake is undefined ROI', {
 x<-data.frame(policy='p',period=1:4,stake=c(2,2,2,0),gross=c(0,5,0,0),net=c(-2,3,-2,0),hits=c(0,1,0,0))
 w<-data.frame(window=c('all','tail','cash'),start=c(1,3,4),end=4)
 z<-joint_tail_windows(x,w)
 expect_equal(z$local_drawdown,c(2,2,0));expect_equal(z$net,c(-1,-2,0));expect_true(is.na(z$roi[3]))
 expect_error(joint_tail_windows(x[-2,],w))
})
