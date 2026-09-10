source("../../r/probability_exploration.R")

testthat::test_that("score support and handicap mapping are explicit", {
  x <- illustrative_score_grid(1.55, .95, -1, 1e-10)
  testthat::expect_equal(sum(x$grid$probability), 1)
  testthat::expect_lte(x$omitted_mass, 1e-10)
  testthat::expect_equal(sum(x$probability), 1)
  testthat::expect_equal(x$grid$handicap_outcome[x$grid$home_goals == 1 & x$grid$away_goals == 0], "D")
  testthat::expect_equal(x$grid$handicap_outcome[x$grid$home_goals == 2 & x$grid$away_goals == 0], "W")
  testthat::expect_equal(illustrative_score_grid(0, 0, 0, 1e-10)$probability, c(W=0,D=1,L=0))
  testthat::expect_error(illustrative_score_grid(NA, 1, 0, 1e-10))
  testthat::expect_error(illustrative_score_grid(-1, 1, 0, 1e-10))
  testthat::expect_error(illustrative_score_grid(1, 1, .5, 1e-10))
  testthat::expect_error(illustrative_score_grid(1, 1, 0, 0))
  testthat::expect_error(illustrative_score_grid(1e6, 1e6, 0, 1e-10), "capacity")
})

testthat::test_that("inverse price shares preserve ordering and reject invalid prices", {
  testthat::expect_equal(market_probability_proxy(c(W=2,D=4,L=4)), c(W=.5,D=.25,L=.25))
  testthat::expect_error(market_probability_proxy(c(2,4,4)))
  testthat::expect_error(market_probability_proxy(c(W=0,D=4,L=4)))
  testthat::expect_error(market_probability_proxy(c(W=NA,D=4,L=4)))
  testthat::expect_error(market_probability_proxy(numeric()))
})

testthat::test_that("exact ticket distribution reconciles cost, probability and one payout factor", {
  p <- matrix(rep(c(.4,.2,.4), each=7), 7, dimnames=list(NULL,c("W","D","L")))
  args <- list(probabilities=p, sp=1/p, selections=rep(list(c("W","L")),7),
    hedge_leg=1L, hedge_outcome="D", hedge_probability=.1, hedge_sp=10,
    n=7L, budget_cny=1024, unit_cny=2, payout_factor=.65, core_multiple=4L)
  original <- args
  pure <- do.call(n7_double_hedge_demo,args)
  testthat::expect_identical(args,original)
  testthat::expect_equal(pure$receipt$n_combinations,128)
  testthat::expect_equal(sum(pure$distribution$probability),1)
  testthat::expect_equal(pure$metrics$core_hit_probability,.8^7)
  testthat::expect_equal(pure$metrics$expected_net_cny,-358.4)
  testthat::expect_equal(unname(pure$distribution$gross_cny[1]), 8*.65*2.5^7)
  testthat::expect_equal(pure$metrics$zero_return_probability,1-.8^7)
  args$core_multiple <- 3L
  matched <- do.call(n7_double_hedge_demo,args)
  testthat::expect_equal(matched$metrics$expected_net_cny,-358.4)
  testthat::expect_equal(matched$metrics$hedge_stake_cny,256)
  testthat::expect_equal(matched$metrics$zero_return_probability,1-.8^7-.1)
  testthat::expect_equal(matched$metrics$hedge_hit_given_core_miss,.1/(1-.8^7))
  args$hedge_sp <- 7
  testthat::expect_equal(do.call(n7_double_hedge_demo,args)$metrics$expected_net_cny,-408.32)
  args$hedge_sp <- 17
  testthat::expect_equal(do.call(n7_double_hedge_demo,args)$metrics$expected_net_cny,-241.92)
  args$hedge_outcome <- "W"
  testthat::expect_error(do.call(n7_double_hedge_demo,args),"excluded")
  args <- original; args$hedge_probability <- .3
  testthat::expect_error(do.call(n7_double_hedge_demo,args))
  args <- original; args$budget_cny <- 1023
  testthat::expect_error(do.call(n7_double_hedge_demo,args),"Budget")
  args <- original; args$n <- 6L
  testthat::expect_error(do.call(n7_double_hedge_demo,args))
  args <- original; args$selections <- list()
  testthat::expect_error(do.call(n7_double_hedge_demo,args))
  args <- original; args$sp[1,1] <- NA
  testthat::expect_error(do.call(n7_double_hedge_demo,args))
  args <- original; args$probabilities[,] <- rep(c(.5,0,.5),each=7); args$hedge_probability <- 0
  testthat::expect_true(is.na(do.call(n7_double_hedge_demo,args)$metrics$hedge_hit_given_core_miss))
})

testthat::test_that("report setup rejects incompatible business constants", {
  old <- setwd("../..")
  on.exit(setwd(old), add=TRUE)
  lines <- readLines("quarto/12_fundamentals_probability_exploration.qmd")
  start <- which(lines == "```{r}")[1]
  end <- which(seq_along(lines) > start & lines == "```")[1]
  code <- parse(text=lines[(start+1):(end-1)])
  params <- list(n=7, budget_cny=1024, unit_cny=2, payout_factor=.65,
    tail_tolerance=1e-10, lambda_home=c(1.55,1.2,1.8,.95,1.35,1.6,1.1),
    lambda_away=c(.95,1.1,.85,1.4,1.2,1.05,1.6), handicap=c(-1,0,-1,1,0,-1,1))
  for (key in c("n","budget_cny","unit_cny","payout_factor")) {
    changed <- params; changed[[key]] <- changed[[key]] * 2
    testthat::expect_error(eval(code, list2env(list(params=changed))), "requires")
  }
  env <- list2env(list(params=params))
  eval(code,env)
  testthat::expect_equal(env$comparison$expected_net_cny,c(-358.4,-408.32,-358.4,-241.92))
  testthat::expect_equal(env$comparison$worst_20pct_mean_net_cny,rep(-1024,4))
  # Equal selected probabilities imply a single positive core payout.
  p <- matrix(rep(c(.4,.2,.4),each=7),7,dimnames=list(NULL,c("W","D","L")))
  x <- n7_double_hedge_demo(p,1/p,rep(list(c("W","L")),7),1L,"D",.1,10,7L,1024,2,.65,3L)
  masses <- c(.8^7,.1,1-.8^7-.1)
  net <- c(6*.65*2.5^7,256*.65*10,0)-1024
  testthat::expect_equal(x$metrics$profit_probability,sum(masses[net>0]))
  testthat::expect_equal(x$metrics$net_sd_cny,sqrt(sum(masses*net^2)-sum(masses*net)^2))
})

testthat::test_that("same ordinary probabilities can hide opposing handicap differences", {
  market <- tibble::tibble(home_goals=c(1,2,0,0),away_goals=c(0,0,0,1),
    probability=c(.3,.3,.2,.2))
  model <- market; model$probability <- c(.4,.2,.2,.2)
  x <- illustrative_market_disagreement(model,market,-1,c(W=4,D=4,L=2))
  testthat::expect_equal(x$outcomes$model_ordinary,x$outcomes$market_ordinary)
  testthat::expect_equal(x$outcomes$model_handicap,c(.2,.4,.4))
  testthat::expect_equal(x$outcomes$market_internal_pp,c(5,5,-10))
  testthat::expect_equal(x$outcomes$model_vs_quote_pp,c(-5,15,-10))
  testthat::expect_equal(x$outcomes$model_vs_quote_pp,
    x$outcomes$market_internal_pp+x$outcomes$model_vs_market_scores_pp)
  testthat::expect_equal(sum(x$scores$contribution_pp),0)
  testthat::expect_equal(x$scores$contribution_pp,c(10,-10,0,0))
  # Different finite supports preserve all probability mass.
  alternate <- tibble::tibble(home_goals=3,away_goals=0,probability=1)
  y <- illustrative_market_disagreement(alternate,market,-1,c(W=4,D=4,L=2))
  testthat::expect_equal(y$outcomes$model_handicap,c(1,0,0))
  testthat::expect_equal(sum(y$scores$market_probability),1)
  testthat::expect_error(illustrative_market_disagreement(market[0,],market,-1,c(W=4,D=4,L=2)))
  bad <- market; bad$probability[1] <- NA
  testthat::expect_error(illustrative_market_disagreement(bad,market,-1,c(W=4,D=4,L=2)))
  bad <- market; bad$probability[1] <- .5
  testthat::expect_error(illustrative_market_disagreement(bad,market,-1,c(W=4,D=4,L=2)))
  bad <- market; bad$home_goals[1] <- .5
  testthat::expect_error(illustrative_market_disagreement(bad,market,-1,c(W=4,D=4,L=2)))
  testthat::expect_error(illustrative_market_disagreement(rbind(market,market),market,-1,c(W=4,D=4,L=2)))
  testthat::expect_error(illustrative_market_disagreement(model,market,-.5,c(W=4,D=4,L=2)))
  testthat::expect_error(illustrative_market_disagreement(model,market,-1,c(W=NA,D=4,L=2)))
})

testthat::test_that("explicit score examples survive zero goal rates", {
  x <- illustrative_score_examples(c("1:0","2:0","3:0","3:1"),0,0,-2,1e-10)
  testthat::expect_equal(x$probability,rep(0,4))
  testthat::expect_equal(x$handicap_outcome,c("L","D","W","D"))
  testthat::expect_equal(x$score,c("1:0","2:0","3:0","3:1"))
  testthat::expect_equal(illustrative_score_examples("0:0",0,0,0,1e-10)$probability,1)
  testthat::expect_equal(illustrative_score_examples("2:0",2.4,.7,-2,1e-10)$probability,exp(-3.1)*2.4^2/2)
  testthat::expect_error(illustrative_score_examples(character(),1,1,0,1e-10))
  testthat::expect_error(illustrative_score_examples("1.5:0",1,1,0,1e-10))
  testthat::expect_error(illustrative_score_examples(c("1:0","1:0"),1,1,0,1e-10))
  testthat::expect_error(illustrative_score_examples("1:0",-1,1,0,1e-10))
})
