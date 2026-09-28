testthat::test_that("fixed-group alternative selects the true top128 of648 without refitting", {
  at <- lubridate::ymd_hms("2026-09-26 20:00:00", tz = "Asia/Shanghai")
  cutoff <- list(issue_id = "26098", cutoff_utc = lubridate::with_tz(at, "UTC"))
  fixtures <- tibble::tibble(issue_id = "26098", fixture_id = paste0("26098:", 1:7),
    slot = 1:7, provider_id = as.character(1:7), kickoff_at = at + lubridate::dhours(8),
    handicap = 0L, sale_state = "open", source_url = "fixture://test")
  # Entropy strictly declines: first four legs receive 3 outcomes, last three 2.
  triples <- rbind(c(.36,.34,.30), c(.40,.33,.27), c(.45,.32,.23),
    c(.50,.30,.20), c(.60,.25,.15), c(.70,.20,.10), c(.80,.15,.05))
  projected <- list(cutoff = cutoff, fixtures = fixtures,
    probabilities = tibble::tibble(fixture_id = rep(fixtures$fixture_id, each = 3),
      outcome = rep(c("W","D","L"), 7), probability = as.vector(t(triples))),
    prematch_sp = match_typed_empty("prematch_sp"),
    match_status = tibble::tibble(issue_id = "26098", fixture_id = fixtures$fixture_id,
      status = "scheduled", status_at = cutoff$cutoff_utc - 60,
      available_at = cutoff$cutoff_utc - 60, source_url = "fixture://status"))
  source <- parlay_build_plan(projected, parlay_strategy_config(parlay_settings(reset=TRUE),
    patterns = list(p3222221 = c(3L,2L,2L,2L,2L,2L,1L))))
  before <- rlang::hash(source)
  result <- parlay_restructure_plan(source, cutoff, c(3L,3L,3L,3L,2L,2L,2L), 256)
  # Expand.grid needs individual columns; explicit do.call is independent of production enumeration.
  grid <- do.call(expand.grid, c(rep(list(1:3),4), rep(list(1:2),3)))
  masses <- apply(grid, 1, function(x) prod(triples[cbind(1:7, as.integer(x))]))
  expected <- sort(masses, decreasing = TRUE)[1:128]
  testthat::expect_equal(result$summary$groups$support_size, 648L)
  testthat::expect_equal(result$summary$groups$funded_tickets, 128L)
  testthat::expect_equal(result$summary$groups$cost_cny, 256)
  testthat::expect_equal(result$summary$groups$coverage_probability, sum(expected))
  testthat::expect_equal(sort(result$summary$tickets$probability_mass, decreasing=TRUE), expected)
  testthat::expect_setequal(result$summary$tickets$support_rank, 1:128)
  testthat::expect_equal(unname(result$summary$groups$structure), "3333222")
  testthat::expect_true(all(is.na(result$summary$tickets$ev_net)))
  testthat::expect_identical(result$probabilities, source$probabilities)
  testthat::expect_identical(result$cutoff, source$cutoff)
  testthat::expect_identical(result$plan$group_legs, source$plan$group_legs)
  testthat::expect_identical(rlang::hash(source), before)
  testthat::expect_identical(result$provenance$source_hash, before)
  testthat::expect_equal(nrow(result$history$purchases),128L)
  schedule <- dplyr::transmute(fixtures, fixture_key=fixture_id, slot,
    home_name="甲", away_name="乙", handicap, kickoff_at)
  testthat::expect_equal(nrow(parlay_betting_sheet(result,schedule)$ticket_legs),896L)
  small <- parlay_restructure_plan(source, cutoff, rep(1L,7), 256)
  testthat::expect_equal(small$summary$groups$funded_tickets,1L)
  testthat::expect_equal(small$funded$diagnostics$unspent_cny,254)
  testthat::expect_error(parlay_restructure_plan(source, cutoff, rep(3L,7), 1026),"exceed")
  testthat::expect_error(parlay_restructure_plan(source, cutoff, rep(3L,7), 255),"divisible")
  testthat::expect_error(parlay_restructure_plan(source, cutoff, rep(3L,7), NA_real_))
  testthat::expect_error(parlay_restructure_plan(source, cutoff, rep(3L,7), Inf))
  testthat::expect_error(parlay_restructure_plan(source, cutoff, rep(3L,6), 256))
  testthat::expect_error(parlay_restructure_plan(source, cutoff, c(rep(3L,6),NA), 256))
  wrong <- cutoff; wrong$cutoff_utc <- wrong$cutoff_utc + 1
  testthat::expect_error(parlay_restructure_plan(source, wrong, rep(3L,7), 256),"cutoff")
  empty <- parlay_build_plan(projected, parlay_strategy_config(parlay_settings(),spend_limit_cny=0))
  testthat::expect_error(parlay_restructure_plan(empty,cutoff,rep(3L,7),256),"funded")
})
