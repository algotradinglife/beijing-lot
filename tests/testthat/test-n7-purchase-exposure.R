source(file.path('..','..','r','n7_purchase_exposure.R'))
source(file.path('..','..','r','n7_capital_portfolio.R'))
source(file.path('..','..','r','n7_core_opportunity.R'))

testthat::test_that('depth upgrade replaces rather than accumulates prior exposure', {
  cut<-list(a='2020-01-01T00:00:00Z')
  opts<-lapply(1:2,function(d)list(sleeve_id=1,fixtures=1:7,state_ids=seq_len(d),
    stake=2*d,expected_gross=3*d,coverage=.2*d,unit_copies=1,depth=d,role='CORE'))
  pool<-list(cutoffs=cut,fixtures=rep(list(list()),7),options=opts,mode='DEPTH',
    opening_options=1L,opportunity_options=integer())
  worlds<-list(cutoffs=cut,hits=cbind(c(1,0),c(1,1)),gross=cbind(c(3,0),c(3,3)))
  limit<-n7_purchase_limits(pool,cut,2,1,4)
  fit<-n7_core_allocate(pool,worlds,cut,4,'any_hit',10,'OPEN_FIRST',limit)
  testthat::expect_identical(fit$selected,2L)
  testthat::expect_equal(fit$metrics$stake,4)
  testthat::expect_equal(fit$actions$added_stake,c(2,2))
  limit<-n7_purchase_limits(pool,cut,2,1,2)
  fit<-n7_core_allocate(pool,worlds,cut,4,'any_hit',10,'OPEN_FIRST',limit)
  testthat::expect_identical(fit$selected,1L)
  testthat::expect_equal(fit$metrics$cash,2)
})

testthat::test_that('canonical states expose compatible and incompatible stake exactly', {
  c<-list(a='2020-01-01T00:00:00Z')
  p<-list(cutoffs=c,fixtures=rep(list(list()),7),options=list(
    list(sleeve_id=1,fixtures=1:7,state_ids=c(1L,2L),stake=4)))
  x<-n7_purchase_exposure(p,c,2)
  testthat::expect_equal(nrow(x),21L)
  testthat::expect_equal(x$required_stake[x$fixture==1],c(4,0,0))
  testthat::expect_equal(x$required_stake[x$fixture==7],c(2,2,0))
  testthat::expect_equal(x$incompatible_stake[x$fixture==7],c(2,2,4))
  testthat::expect_equal(x$required_stake+x$incompatible_stake,x$fixture_stake)
  p$options[[1]]$stake<-12
  y<-n7_purchase_exposure(p,c,2)
  testthat::expect_equal(y$required_stake,3*x$required_stake)
  testthat::expect_error(n7_purchase_exposure(p,list(a='other'),2))
  p$options[[1]]$state_ids<-c(1,1)
  testthat::expect_error(n7_purchase_exposure(p,c,2))
  p$options<-list()
  testthat::expect_equal(nrow(n7_purchase_exposure(p,c,2)),0L)
})

testthat::test_that('limits constrain shared direction money and fixture reuse', {
  c<-list(a='2020-01-01T00:00:00Z')
  opts<-lapply(1:2,function(i)list(sleeve_id=i,fixtures=1:7,state_ids=1L,stake=2,
    expected_gross=3,coverage=.2,unit_copies=1,depth=1,role='CORE'))
  p<-list(cutoffs=c,fixtures=rep(list(list()),7),options=opts,mode='BREADTH',
    opening_options=1:2,opportunity_options=integer())
  s<-list(cutoffs=c,hits=diag(2),gross=3*diag(2))
  free<-n7_core_allocate(p,s,c,4,'any_hit',10,'OPEN_FIRST')
  testthat::expect_length(free$selected,2)
  for(bounds in list(c(1,Inf),c(Inf,2))) {
    lim<-n7_purchase_limits(p,c,2,bounds[1],bounds[2])
    z<-n7_core_allocate(p,s,c,4,'any_hit',10,'OPEN_FIRST',lim)
    testthat::expect_length(z$selected,1)
    testthat::expect_equal(z$metrics$cash,2)
  }
  lim<-n7_purchase_limits(p,c,2,Inf,Inf)
  bounded<-n7_purchase_limits(p,c,2,1,2)
  for(value in list(numeric(),1,NA_real_,-1)) {
    bad<-bounded;bad$upper<-value
    testthat::expect_error(n7_core_allocate(p,s,c,4,'any_hit',10,'OPEN_FIRST',bad))
  }
  for(value in c(-1,NA_real_,Inf)) {
    bad<-bounded;bad$matrix[1,1]<-value
    testthat::expect_error(n7_core_allocate(p,s,c,4,'any_hit',10,'OPEN_FIRST',bad))
  }
  testthat::expect_identical(n7_core_allocate(p,s,c,4,'any_hit',10,'OPEN_FIRST',lim)$selected,free$selected)
  testthat::expect_error(n7_purchase_limits(p,c,2,0,2))
  changed<-p;changed$options[[1]]$coverage<-.3
  testthat::expect_error(n7_core_allocate(changed,s,c,4,'any_hit',10,'OPEN_FIRST',lim))
})
