source(file.path('..','..','r','n7_purchase_pool.R'))

testthat::test_that('purchase ordering preserves probability and explicit costs', {
  c<-list(a='2020-01-01T00:00:00Z');q<-c(.6,.3,.1)
  states<-as.matrix(expand.grid(rep(list(0:2),7)))[,7:1]
  p<-apply(states,1,function(s)prod(q[s+1]))
  o<-list(sleeve_id=1,fixtures=1:7,depth=32,stake=64,state_ids=order(-p,1:2187)[1:32],
    state_probability=p,state_payout=rep(10,2187),coverage=0,expected_gross=0)
  b<-list(cutoffs=c,mode='BREADTH',opportunity_options=integer(),opening_options=1,
    fixtures=rep(list(list(p_W=.6,p_D=.3,p_L=.1)),7),options=list(o))
  z<-n7_purchase_pool(b,c,'PROB',.05,.5,c(64L,128L))
  testthat::expect_identical(z$options[[1]]$state_ids,o$state_ids)
  testthat::expect_equal(vapply(z$options,`[[`,numeric(1),'stake'),c(64,128,256))
  testthat::expect_identical(z$options[[3]]$state_probability,p)
  h<-n7_purchase_pool(b,c,'HARD',.05,.5,c(128L,256L))
  testthat::expect_length(h$options,2)
  testthat::expect_equal(h$options[[2]]$third_tickets,0)
  testthat::expect_equal(h$options[[2]]$coverage,.9^7)
  g<-n7_purchase_pool(b,c,'GAP',.3,.5,integer())
  testthat::expect_identical(g$options[[1]]$state_ids,o$state_ids)
  # At depth 128 the unpenalized support includes third outcomes. An active
  # penalty must change membership without changing the probability measure.
  b$options[[1]]$depth<-128L;b$options[[1]]$stake<-256
  b$options[[1]]$state_payout<-1+seq_len(2187)/2187
  plain<-n7_purchase_pool(b,c,'PROB',.05,.5,integer())$options[[1]]
  active<-n7_purchase_pool(b,c,'GAP',.05,.5,integer())$options[[1]]
  testthat::expect_false(setequal(active$state_ids,plain$state_ids))
  testthat::expect_lt(active$third_tickets,plain$third_tickets)
  testthat::expect_identical(active$state_probability,p)
  testthat::expect_equal(active$coverage,sum(p[active$state_ids]))
  testthat::expect_equal(active$expected_gross,
    sum((p*b$options[[1]]$state_payout)[active$state_ids]))
  # Equal probability and score ties prefer payout value, then canonical ID.
  tie<-b;tie$fixtures<-rep(list(list(p_W=1/3,p_D=1/3,p_L=1/3)),7)
  tie$options[[1]]$state_probability<-rep(1/2187,2187)
  tied<-n7_purchase_pool(tie,c,'GAP',.05,.5,integer())$options[[1]]
  testthat::expect_identical(tied$state_ids,2187:2060)
  tie$options[[1]]$state_payout<-rep(10,2187)
  tied<-n7_purchase_pool(tie,c,'GAP',.05,.5,integer())$options[[1]]
  testthat::expect_identical(tied$state_ids,1:128)
  testthat::expect_error(n7_purchase_pool(b,c,'GAP',-.1,.5,integer()))
  testthat::expect_error(n7_purchase_pool(b,list(a='other'),'PROB',.05,.5,integer()))
})
