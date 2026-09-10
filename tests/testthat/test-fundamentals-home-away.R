source("../../r/probability_exploration.R")
source("../../r/fundamentals_home_away.R")

test_that("cross means, probabilities, choices and results are separate", {
  cutoff <- "2010-01-01T00:00:00+00:00"
  receipt <- list(cutoff_ts=cutoff,historical_admission=FALSE,intended_use="RETROSPECTIVE_DESCRIPTION_ONLY")
  home <- list(list(home_goals=2L,away_goals=1L),list(home_goals=2L,away_goals=0L))
  home[[1]]$observed_sources <- list("titan","nowscore"); home[[1]]$blocks <- list("home","away","h2h")
  away <- list(list(home_goals=2L,away_goals=1L),list(home_goals=2L,away_goals=1L))
  w <- list(slot=1L,provider_id="001",home="H",away="A",competition="cup",cutoff_utc=cutoff,
    status="OK_DIAGNOSTIC",home_window=home,away_window=away,home_receipt=receipt,away_receipt=receipt)
  h <- tibble::tibble(slot=1L,provider_id="001",home_handicap=-1L)
  cutoffs <- list(`1`=cutoff)
  model <- home_away_probabilities(list(w),h,cutoffs,5L,1e-10)
  expect_equal(model$fixtures$lambda_home,2)
  expect_equal(model$fixtures$lambda_away,.75)
  expect_equal(sum(unlist(model$fixtures[c("W","D","L")])),1)
  expect_equal(nrow(model$scores),5)
  expect_false(model$fixtures$protection %in% model$scores$score[model$scores$outcome %in% strsplit(model$fixtures$double,"+",fixed=TRUE)[[1]]])
  original <- model
  results <- tibble::tibble(slot=1L,provider_id="001",result_state="完场",actual_home=3L,actual_away=1L)
  evaluated <- home_away_hits(model,results)
  expect_equal(evaluated$fixtures$actual_outcome,"W")
  expect_identical(model,original)
  results$actual_home <- 0L
  changed <- home_away_hits(model,results)
  expect_equal(changed$fixtures$actual_outcome,"L")
  expect_equal(changed$fixtures$lambda_home,evaluated$fixtures$lambda_home)
  results$result_state <- "推迟"; results$actual_home <- NA_integer_; results$actual_away <- NA_integer_
  delayed <- home_away_hits(model,results)
  expect_true(all(is.na(delayed$summary$rate)))
  expect_true(all(delayed$summary$denominator==0))
  expect_true(is.na(delayed$fixtures$double_hit))
  results$provider_id <- "wrong"
  expect_error(home_away_hits(model,results),"identity")
  expect_error(home_away_probabilities(list(w,w),h,cutoffs,5L,1e-10),"cardinality")
  expect_error(home_away_probabilities(list(w),h,list(`1`="2010-01-02T00:00:00Z"),5L,1e-10),"Cutoff")
  w$home_window[[1]]$home_goals <- NA_integer_
  expect_error(home_away_probabilities(list(w),h,cutoffs,5L,1e-10),"goals")
})

test_that("neutral and sparse fixtures stay in denominator inventory with NA predictions", {
  cutoff <- "2010-01-01T00:00:00+00:00"
  receipt <- list(cutoff_ts=cutoff,historical_admission=FALSE,intended_use="RETROSPECTIVE_DESCRIPTION_ONLY")
  w <- list(slot=1L,provider_id="001",home="H",away="A",competition="cup",cutoff_utc=cutoff,
    status="NEUTRAL_TARGET",home_window=list(),away_window=list(),home_receipt=receipt,away_receipt=receipt)
  h <- tibble::tibble(slot=1L,provider_id="001",home_handicap=0L)
  for (status in c("NEUTRAL_TARGET","INSUFFICIENT_HISTORY","IDENTITY_UNAVAILABLE")) {
    w$status <- status
    m <- home_away_probabilities(list(w),h,list(`1`=cutoff),5L,1e-10)
    expect_equal(nrow(m$fixtures),1)
    expect_true(is.na(m$fixtures$W))
    expect_equal(nrow(m$scores),0)
  }
  w$status <- "OK_DIAGNOSTIC"; w$home_window <- w$away_window <- list(list(home_goals=0L,away_goals=0L))
  m <- home_away_probabilities(list(w),h,list(`1`=cutoff),5L,1e-10)
  expect_equal(m$fixtures$D,1)
  expect_equal(m$scores$score,"0:0")
  expect_equal(m$fixtures$protection_probability,0)
  expect_true(is.na(m$fixtures$protection))
})
