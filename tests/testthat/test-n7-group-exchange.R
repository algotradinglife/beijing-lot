root<-normalizePath(file.path(testthat::test_path(),'../..'))
source(file.path(root,'r/n7_capital_portfolio.R'))
source(file.path(root,'r/n7_core_opportunity.R'))
source(file.path(root,'r/n7_group_exchange.R'))
testthat::test_that('one-to-two escapes a strict one-swap local optimum', {
 cuts<-list(a='epoch')
 opts<-lapply(0:2,function(j)list(sleeve_id=j,stake=if(j==0)6 else 4,depth=if(j==0)3 else 2,
   coverage=.5,expected_gross=if(j==0)10 else 8,unit_copies=1,fixtures=1:7))
 pool<-list(options=opts,cutoffs=cuts,mode='BREADTH',opening_options=1:3,opportunity_options=integer())
 hits<-cbind(c(1,1,1,1,1,0),c(1,1,0,1,0,0),c(0,0,1,0,1,1))
 sc<-list(hits=hits,gross=hits*10,cutoffs=cuts)
 testthat::expect_equal(n7_core_allocate(pool,sc,cuts,8,'any_hit',256,'OPEN_FIRST')$selected,1L)
 a<-n7_group_exchange(pool,sc,cuts,1L,8,1)
 b<-n7_group_exchange(pool,sc,cuts,1L,8,2)
 testthat::expect_identical(a$selected,1L)
 testthat::expect_equal(sort(b$selected),2:3)
 testthat::expect_equal(b$metrics$any_hit,1)
 testthat::expect_equal(b$metrics$stake,8)
 testthat::expect_equal(b$actions$gain_worlds,1)
 testthat::expect_equal(b$actions$removed_id,0)
 testthat::expect_equal(n7_group_exchange(pool,sc,cuts,b$selected,8,2)$actions,tibble::tibble())
 pool$opportunity_options<-1L
 testthat::expect_equal(n7_group_exchange(pool,sc,cuts,1L,8,2)$selected,1L)
 testthat::expect_error(n7_group_exchange(pool,sc,cuts,2L,8,2))
 testthat::expect_error(n7_group_exchange(pool,sc,list(a='later'),1L,8,2))
 testthat::expect_error(n7_group_exchange(pool,sc,cuts,1L,7,2))
 pool$opportunity_options<-integer();sc$future_label<-99
 testthat::expect_identical(n7_group_exchange(pool,sc,cuts,1L,8,2),b)
})
testthat::test_that('empty pools hold cash and equal coverage cannot churn', {
 cuts<-list(a='epoch');pool<-list(options=list(),mode='BREADTH',cutoffs=cuts,
  opening_options=integer(),opportunity_options=integer())
 sc<-list(hits=matrix(0,2,0),gross=matrix(0,2,0),cutoffs=cuts)
 x<-n7_group_exchange(pool,sc,cuts,integer(),8,2)
 testthat::expect_equal(x$metrics$cash,8)
 testthat::expect_length(x$selected,0)
})
testthat::test_that('single replacements and deterministic ties use the declared order', {
 cuts<-list(a='epoch')
 opts<-lapply(0:2,function(j)list(sleeve_id=j,stake=4,coverage=.5,
  expected_gross=if(j==2)12 else 10,unit_copies=1,fixtures=1:7))
 pool<-list(options=opts,cutoffs=cuts,mode='BREADTH',opening_options=1:3,opportunity_options=integer())
 hits<-cbind(c(1,0,0),c(1,1,0),c(1,1,0));sc<-list(hits=hits,gross=hits*10,cutoffs=cuts)
 testthat::expect_equal(n7_group_exchange(pool,sc,cuts,1L,4,1)$selected,3L)
 pool$options[[3]]$expected_gross<-10
 testthat::expect_equal(n7_group_exchange(pool,sc,cuts,1L,4,1)$selected,2L)
 testthat::expect_equal(n7_group_exchange(pool,sc,cuts,3L,4,1)$selected,3L)
})
