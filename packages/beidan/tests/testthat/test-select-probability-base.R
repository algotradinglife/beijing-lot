testthat::test_that("Beidan uses complete raw SP alone and ignores DC configuration", {
  fx <- epoch_fixture(2L)
  fx$inputs$prematch_sp <- tibble::tibble(fixture_id=rep(fx$inputs$fixtures$fixture_id,each=3L),
    outcome=rep(c("W","D","L"),2L),quote_at=fx$cutoff$cutoff_utc-60,
    sp_raw=rep(c(2,4,8),2L),source_url="fixture://sp")
  fx$inputs$euro <- NULL; fx$inputs$totals <- NULL
  epoch <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,probability_base="beidan")
  x <- beidan::SelectProbabilityBase(epoch,model_config=list(nonsense=TRUE))
  testthat::expect_equal(x$probabilities$probability[x$probabilities$outcome=="W"],rep(4/7,2))
  testthat::expect_equal(x$probabilities$probability[x$probabilities$outcome=="D"],rep(2/7,2))
  testthat::expect_equal(x$probabilities$probability[x$probabilities$outcome=="L"],rep(1/7,2))
  testthat::expect_null(x$model_config)
  testthat::expect_equal(nrow(x$fit),0)
  testthat::expect_identical(x$probability_base,"beidan")
  testthat::expect_true(.ValidatePreparedProbabilityInputs(epoch))
  testthat::expect_error(estimate_match_probabilities(epoch),"DC estimator")
})
testthat::test_that("DC and mixed share their declared basis throughout preparation", {
  fx <- epoch_fixture(2L)
  policy <- list(euro=default_euro(),totals=default_totals())
  dc_epoch <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,policy,probability_base="dc")
  mix_epoch <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,policy,probability_base="mixed")
  bd_epoch <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,probability_base="beidan")
  dc <- SelectProbabilityBase(dc_epoch,"dc")
  bd <- SelectProbabilityBase(bd_epoch)
  mixed <- SelectProbabilityBase(mix_epoch,"mixed",.75)
  testthat::expect_identical(dc$probabilities,estimate_match_probabilities(dc_epoch)$probabilities)
  expected <- BlendMatchProbabilities(dc$probabilities,bd$probabilities,.75)
  testthat::expect_equal(mixed$probabilities,expected)
  testthat::expect_equal(SelectProbabilityBase(mix_epoch,"mixed",0)$probabilities,dc$probabilities)
  testthat::expect_equal(SelectProbabilityBase(mix_epoch,"mixed",1)$probabilities,bd$probabilities)
  testthat::expect_error(SelectProbabilityBase(dc_epoch,"beidan"),"differs")
  testthat::expect_error(SelectProbabilityBase(bd_epoch,"dc"),"differs")
  bad <- dc_epoch;bad$probability_base <- "beidan"
  testthat::expect_error(SelectProbabilityBase(bad),"receipt")
  bad <- dc_epoch;bad$preparation_receipt <- NULL
  testthat::expect_error(SelectProbabilityBase(bad,"dc"),"receipt")
})
testthat::test_that("basis and weights reject invalid dimensioned or missing input", {
  fx <- epoch_fixture(2L)
  policy <- list(euro=default_euro(),totals=default_totals())
  mix_epoch <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,policy,probability_base="mixed")
  bd_epoch <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,probability_base="beidan")
  for (w in list(NULL,-.1,1.1,NA_real_,Inf,c(.5,.75),matrix(.75),as.Date("1970-01-01"))) {
    testthat::expect_error(SelectProbabilityBase(mix_epoch,"mixed",w))
  }
  testthat::expect_error(SelectProbabilityBase(bd_epoch,"bad"))
  testthat::expect_error(SelectProbabilityBase(bd_epoch,bd_weight=.75))
  bad <- fx$inputs;bad$totals <- bad$totals[0,]
  e <- prepare_match_inputs(bad,fx$cutoff$cutoff_utc,policy,probability_base="mixed")
  testthat::expect_error(SelectProbabilityBase(e,"mixed",.75),"alignment")
})
testthat::test_that("SP completeness and cutoff are checked before source selection", {
  fx <- epoch_fixture(2L)
  bad <- fx$inputs;bad$prematch_sp <- bad$prematch_sp[-1,]
  e <- prepare_match_inputs(bad,fx$cutoff$cutoff_utc,probability_base="beidan")
  testthat::expect_error(SelectProbabilityBase(e))
  bad <- fx$inputs;bad$prematch_sp$quote_at <- fx$cutoff$cutoff_utc
  e <- prepare_match_inputs(bad,fx$cutoff$cutoff_utc,probability_base="beidan")
  testthat::expect_error(SelectProbabilityBase(e))
  for (v in c(0,-1,Inf,NA_real_)) {
    bad <- fx$inputs;bad$prematch_sp$sp_raw[1] <- v
    e <- prepare_match_inputs(bad,fx$cutoff$cutoff_utc,probability_base="beidan")
    testthat::expect_error(SelectProbabilityBase(e))
  }
  e <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,probability_base="beidan")
  bad <- e;bad$cutoff$cutoff_utc <- bad$cutoff$cutoff_utc+1
  testthat::expect_error(SelectProbabilityBase(bad),"receipt")
  bad <- e;bad$fixtures$issue_id[1] <- "wrong"
  testthat::expect_error(SelectProbabilityBase(bad),"output")
  bad <- e;bad$prematch_sp$sp_raw[1] <- 3
  testthat::expect_error(SelectProbabilityBase(bad),"output")
})
testthat::test_that("empty admitted pools retain schemas and deterministic receipts", {
  fx <- epoch_fixture(2L)
  fx$inputs$match_status <- match_typed_empty("match_status")
  e <- prepare_match_inputs(fx$inputs,fx$cutoff$cutoff_utc,probability_base="beidan")
  x <- SelectProbabilityBase(e)
  testthat::expect_identical(x$probabilities,match_typed_empty("probabilities"))
  testthat::expect_identical(x$fit,match_typed_empty("fit"))
  testthat::expect_identical(SelectProbabilityBase(e),x)
  testthat::expect_identical(x$probability_base_receipt$input_snapshot,e)
  testthat::expect_identical(x$probability_base_receipt$input_hash,rlang::hash(e))
  bare <- x;bare$probability_base_receipt <- NULL
  testthat::expect_identical(x$probability_base_receipt$output_hash,rlang::hash(bare))
})
