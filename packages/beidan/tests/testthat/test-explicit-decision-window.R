testthat::test_that("explicit hours preserve half-open elapsed bounds and defaults", {
  at <- as.POSIXct("2026-09-28 00:00:00", tz = "UTC") + 0.25
  default <- match_decision_window(at)
  testthat::expect_identical(default, match_decision_window(at, window_hours = c(4,28)))
  testthat::expect_equal(as.numeric(default$start_utc) - as.numeric(at), 4*3600)
  testthat::expect_equal(as.numeric(default$end_utc) - as.numeric(at), 28*3600)
  w <- match_decision_window(at, window_hours = c(2L,26L))
  testthat::expect_identical(w$window_hours, c(2,26))
  testthat::expect_equal(as.numeric(w$start_utc) - as.numeric(at), 7200)
  testthat::expect_equal(as.numeric(w$end_utc) - as.numeric(at), 93600)
  s <- tibble::tibble(fixture_key = letters[1:4], slot = 1:4,
    kickoff_at = at + c(7199.75,7200,93599.75,93600))
  result <- match_market_schedule(s, at, window_hours = c(2,26))
  testthat::expect_identical(result$schedule$slot, 2:3)
  testthat::expect_identical(result$window, w)
  testthat::expect_equal(nrow(match_market_schedule(s[0,], at, window_hours=c(2,26))$schedule),0L)
  testthat::expect_equal(as.numeric(match_decision_window(at,window_hours=c(0,1))$start_utc),as.numeric(at))
})

testthat::test_that("invalid elapsed-hour policies fail closed", {
  at <- as.POSIXct("2026-09-28 00:00:00", tz = "UTC")
  invalid <- list(NULL, numeric(), 2, c(2,26,28), c(-1,26), c(2,2), c(26,2),
    c(NA_real_,26), c(NaN,26), c(2,Inf), c("2","26"), c(TRUE,FALSE),
    as.Date(c("2026-01-01","2026-01-02")), as.difftime(c(2,26),units="hours"),
    matrix(c(2,26),1), structure(c(2,26),class="custom"))
  for (value in invalid) {
    testthat::expect_error(match_decision_window(at,window_hours=value),"window_hours")
  }
})

testthat::test_that("public preparation forwards window without retiming visibility", {
  fx <- epoch_fixture(4L)
  at <- fx$cutoff$cutoff_utc + 0.25
  fx$inputs$fixtures$kickoff_at <- at + c(7199.75,7200,93599.75,93600)
  policy <- list(euro=default_euro(), totals=default_totals())
  epoch <- prepare_match_inputs(fx$inputs,at,policy,window_hours=c(2,26))
  testthat::expect_identical(epoch$fixtures$fixture_id,fx$inputs$fixtures$fixture_id[2:3])
  testthat::expect_identical(epoch$cutoff$cutoff_utc,at)
  testthat::expect_identical(epoch$decision_at,at)
  testthat::expect_identical(epoch$window,match_decision_window(at,window_hours=c(2,26)))
  testthat::expect_identical(
    prepare_match_inputs(fx$inputs,at,policy),
    prepare_match_inputs(fx$inputs,at,policy,window_hours=c(4,28)))
  testthat::expect_error(prepare_match_inputs(fx$inputs,at,policy,window_hours=c(26,2)),"window_hours")
  late <- fx$inputs
  late$euro$quote_at <- at
  testthat::expect_equal(nrow(prepare_match_inputs(late,at,policy,window_hours=c(2,26))$fixtures),0L)
  cutoff <- list(cutoff_utc=at,issue_id=fx$cutoff$issue_id)
  engine <- .PrepareMatchInputs(fx$inputs,cutoff,policy$euro,policy$totals,window_hours=c(2,26))
  testthat::expect_identical(engine$fixtures,epoch$fixtures)
  testthat::expect_identical(engine$window,epoch$window)
})
