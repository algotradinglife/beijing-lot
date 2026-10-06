testthat::test_that("basis-aware preparation removes the foreign euro admission gate", {
  fx <- epoch_fixture(2L)
  fx$inputs$euro <- fx$inputs$euro |> dplyr::filter(fixture_id!=fx$inputs$fixtures$fixture_id[1])
  policy <- list(euro=default_euro(),totals=default_totals())
  dc <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,policy,probability_base="dc")
  bd <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,probability_base="beidan")
  testthat::expect_equal(nrow(dc$fixtures),1L)
  testthat::expect_equal(nrow(bd$fixtures),2L)
  testthat::expect_true(.ValidatePreparedProbabilityInputs(dc))
  testthat::expect_true(.ValidatePreparedProbabilityInputs(bd))
  testthat::expect_equal(nrow(bd$totals_selected),0L)
  testthat::expect_equal(nrow(bd$euro_mean),0L)
  testthat::expect_identical(bd$market_policy,list())
  testthat::expect_true(all(dc$preparation_receipt$max_prior_eligible_euro_quote_at<dc$cutoff$cutoff_utc))
})
testthat::test_that("prepared source basis and chronology cannot be relabelled without rebuilding", {
  fx <- epoch_fixture(2L)
  e <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,probability_base="beidan")
  bad <- e;bad$probability_base <- "dc"
  testthat::expect_error(.ValidatePreparedProbabilityInputs(bad),"basis")
  bad <- e;bad$cutoff$cutoff_utc <- bad$cutoff$cutoff_utc+1;bad$decision_at <- bad$decision_at+1
  testthat::expect_error(.ValidatePreparedProbabilityInputs(bad),"cutoff")
  bad <- e;bad$preparation_receipt$input_snapshot$inputs$prematch_sp$sp_raw[1] <- 7
  testthat::expect_error(.ValidatePreparedProbabilityInputs(bad),"source")
  bad <- e;bad$preparation_receipt$implementation_hash <- "stale"
  testthat::expect_error(.ValidatePreparedProbabilityInputs(bad),"implementation")
  bad <- e;bad$preparation_receipt$parameters$probability_base <- "dc"
  testthat::expect_error(.ValidatePreparedProbabilityInputs(bad),"replay")
  bad <- e;bad$preparation_receipt <- NULL
  testthat::expect_error(.ValidatePreparedProbabilityInputs(bad),"required")
  bad <- e;bad$fixtures <- bad$fixtures[-1,]
  testthat::expect_error(.ValidatePreparedProbabilityInputs(bad),"output")
  bad <- fx$inputs;bad$prematch_sp$quote_at[1] <- NA
  testthat::expect_error(prepare_match_inputs(bad,fx$cutoff$cutoff_utc,probability_base="beidan"),"finite")
})
