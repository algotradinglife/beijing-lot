source(file.path('..','..','r','n7_risk_monitor.R'))
test_that('persistent fresh evidence controls defensive and recovery transitions', {
 c<-list(status='READY',receipt=list(cutoff_identity='x'),history_identity='1',
 rows=data.frame(weight=1,hit_residual=-.1,depth_residual=-.1))
 a<-n7_risk_state(c,NULL,'x',-.05,0,2,3);expect_equal(a$state,'NORMAL')
 b<-n7_risk_state(c,a,'x',-.05,0,2,3);expect_equal(b$bad,1)
 c$history_identity<-'2';b<-n7_risk_state(c,b,'x',-.05,0,2,3);expect_equal(b$state,'DEFENSIVE')
 c$rows$hit_residual<-c$rows$depth_residual<-.1
 for(i in 3:5) {c$history_identity<-as.character(i);b<-n7_risk_state(c,b,'x',-.05,0,2,3)}
 expect_equal(b$state,'RECOVERING')
 for(i in 6:8) {c$history_identity<-as.character(i);b<-n7_risk_state(c,b,'x',-.05,0,2,3)}
 expect_equal(b$state,'NORMAL')
 c$status<-'WARMUP';expect_equal(n7_risk_state(c,b,'x',-.05,0,2,3)$state,'WARMUP')
 expect_error(n7_risk_state(c,b,'wrong',-.05,0,2,3))
})
test_that('whole prefix funding preserves integer cash and coverage priority', {
 cut<-list(cutoff_identity='x',cutoff_kind='DECISION_EPOCH',target_issue='1',
  cutoff_ts='2010-01-01T00:00:00Z',historical_admission=FALSE)
 g<-data.frame(sleeve_id=c('a','b','c'),depth=c(3,2,2),stake=c(6,4,4),coverage=c(.25,.27,.26))
 a<-n7_risk_fund(g,8,'ORIGINAL',2,cut,'x');expect_equal(a$groups$sleeve_id,'a');expect_equal(a$cash,2)
 b<-n7_risk_fund(g,8,'HIGH',2,cut,'x');expect_equal(b$groups$sleeve_id,c('b','c'));expect_equal(b$cash,0)
 expect_equal(n7_risk_fund(g,0,'HIGH',2,cut,'x')$stake,0)
 expect_equal(n7_risk_fund(g[FALSE,],8,'HIGH',2,cut,'x')$cash,8)
 expect_error(n7_risk_fund(g,7,'HIGH',2,cut,'x'))
 expect_error(n7_risk_fund(g,8,'HIGH',2,cut,'wrong'))
})
