root <- normalizePath(file.path(testthat::test_path(), '../..'))
source(file.path(root, 'r/n7_capital_depth.R'))
test_that('full curves retain rank identity and reconcile money and missing endpoints', {
  p <- c(.6,.3,.1,rep(0,2184));s <- list(prob_mat=matrix(p,1,dimnames=list('7',NULL)),
    value_mat=matrix(p*10,1),rank_idx=matrix(1:2187,1));c <- list(a='epoch')
  x <- n7_capital_curves(s,c,c,2)
  expect_equal(nrow(x),2188);expect_equal(x$coverage[1:4],c(0,.6,.9,1))
  expect_equal(x$expected_net[4],4);expect_true(is.na(x$expected_roi[1]))
  expect_true(is.na(tail(x$marginal_net,1)));expect_equal(x$state_id[2:4],0:2)
  expect_error(n7_capital_curves(s,list(a='wrong'),c,2))
  s$rank_idx[1,1] <- 2;expect_error(n7_capital_curves(s,c,c,2))
})
test_that('thresholds resolve minimal exact prefixes and budget is not truncated', {
  p <- c(.6,.3,.1,rep(0,2184));s <- list(prob_mat=matrix(p,1,dimnames=list('7',NULL)),
    value_mat=matrix(p*10,1),rank_idx=matrix(1:2187,1));c <- list(a='epoch')
  x <- n7_capital_curves(s,c,c,2)
  for(tau in c(0,.6,.60001,1)) {
    r <- n7_capital_resolve(x,'coverage',setNames(tau,'7'),100,1e-10,c,c)
    k <- r$allocation$n_tickets
    expect_gte(r$allocation$actual_coverage+1e-10,tau)
    if(k>0)expect_lt(x$coverage[k],tau)
  }
  r <- n7_capital_resolve(x,'coverage',c('7'=1),4,1e-10,c,c)
  expect_equal(r$allocation$n_tickets,3);expect_equal(r$status,'OVER_BUDGET')
  expect_equal(r$budget_excess,2);expect_true(is.na(r$cash))
  a <- n7_capital_resolve(x,'coverage',c('7'=.7),20,1e-10,c,c)
  b <- n7_capital_resolve(x,'coverage',c('7'=.8),20,1e-10,c,c)
  expect_equal(a$configuration_key,b$configuration_key)
  expect_error(n7_capital_resolve(x,'coverage',c('7'=NA_real_),20,1e-10,c,c))
  expect_error(n7_capital_resolve(x,'coverage',c('7'=1.1),20,1e-10,c,c))
  expect_error(n7_capital_resolve(x,'top_n',c('7'=1.5),20,1e-10,c,c))
  expect_equal(n7_capital_resolve(x,'top_n',c('7'=3),20,1e-10,c,c)$allocation$n_tickets,3)
})
