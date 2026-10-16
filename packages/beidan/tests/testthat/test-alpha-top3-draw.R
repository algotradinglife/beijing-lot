testthat::test_that("alpha preserves full sides, score ratios, ties and chronology", {
  root <- rprojroot::find_root(rprojroot::has_file("AGENTS.md"))
  env <- new.env(parent = asNamespace("beidan")); sys.source(file.path(root, "packages/beidan/R/alpha_top3_draw.R"), env)
  reticulate::use_python(file.path(root, ".venv/bin/python"), required = TRUE)
  reticulate::import("sys", convert = FALSE)$path$insert(0L, file.path(root, "packages/beidan/inst/python"))
  shared <- reticulate::import("beidan_backend.temporal_learning", convert = FALSE)
  backend <- reticulate::import("beidan_backend.fundamental_probability", convert = FALSE)
  parent <- readRDS(file.path(root, "results/fm17-three-issues-20261013/forecasts.rds"))
  e <- parent$entries[["26098:104"]]
  example <- tibble::tibble(home_goals = c(0L, 1L, 0L, 2L, 3L, 0L),
    away_goals = c(0L, 0L, 1L, 0L, 0L, 2L), probability = c(.25, .22, .20, .12, .08, .13))
  for (scenario in c("normal", "nonzero", "tie", "nontrigger", "single", "two", "missing_atom")) {
    base <- e$results[["FM-1.7.0"]]$base; base$grid <- example; h <- 0
    if (scenario == "nonzero") h <- -1
    if (scenario == "missing_atom") h <- 10
    if (scenario == "tie") base$grid$probability <- c(.3, .25, .2, .2, .03, .02)
    if (scenario == "nontrigger") base$grid$probability <- c(.12, .4, .3, .1, .04, .04)
    if (scenario == "single") base$grid <- example[1, ] |> dplyr::mutate(probability = 1)
    if (scenario == "two") base$grid <- example[1:2, ] |> dplyr::mutate(probability = c(.6, .4))
    hashes <- list(alpha_input = beidan:::.score_margin_hash(list(base = base, handicap = h,
      fixture = e$fixture, cutoff = e$cutoff)), alpha_code = digest::digest(list(body(env$AlphaTop3Draw),
        body(beidan:::.score_margin_hash), body(beidan:::match_require_cutoff),
        body(beidan:::match_check_character_id)), algo = "sha256"))
    context <- backend$build_adjustment_evidence_context(e$evidence_rows, as.list(e$fixture),
      shared$Cutoff$decision_epoch(e$fixture$issue_id, format(e$cutoff$cutoff_utc, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")),
      hashes, shared$AvailabilityPolicy$historical_proxy("SYNTHETIC_ALPHA_ALGEBRA_TEST"), "HISTORICAL_DIAGNOSTIC", root)
    x <- env$AlphaTop3Draw(base, h, e$fixture, e$cutoff, context, root)
    testthat::expect_equal(sum(x$grid$probability), 1, tolerance = 1e-12)
    testthat::expect_equal(sum(x$probabilities$probability), 1, tolerance = 1e-12)
    if (scenario == "normal") {
      testthat::expect_equal(x$probabilities$probability, c((1-.25/.67)*.42/.75, .25/.67, (1-.25/.67)*.33/.75))
      testthat::expect_equal(x$grid$probability[2]/x$grid$probability[4], .22/.12)
      testthat::expect_equal(x$projection_handicap, 0L)
      testthat::expect_false(x$receipt$tail_compression)
      testthat::expect_error(env$AlphaTop3Draw(base, h + 1e-8, e$fixture, e$cutoff, context, root), "Exact integer")
      fractional <- base; fractional$grid$home_goals[1] <- 1e-8
      testthat::expect_error(env$AlphaTop3Draw(fractional, h, e$fixture, e$cutoff, context, root), "Exact integer")
      env$match_require_cutoff <- beidan:::match_require_cutoff
      environment(env$match_require_cutoff) <- env
      env$match_check_character_id <- beidan:::match_check_character_id
      body(env$match_check_character_id) <- substitute({ ORIGINAL; invisible(value) },
        list(ORIGINAL = body(env$match_check_character_id)))
      testthat::expect_error(env$AlphaTop3Draw(base, h, e$fixture, e$cutoff, context, root), "binding differs")
      rm(list = c("match_require_cutoff", "match_check_character_id"), envir = env)
    }
    if (scenario == "tie") testthat::expect_equal(x$receipt$core_mass, .95)
    if (scenario %in% c("nontrigger", "missing_atom")) {
      testthat::expect_false(x$receipt$triggered); testthat::expect_identical(x$grid, base$grid)
    }
    bad <- base; bad$grid$probability[1] <- bad$grid$probability[1] + .01
    testthat::expect_error(env$AlphaTop3Draw(bad, h, e$fixture, e$cutoff, context, root))
    bad <- base; bad$source_hashes$mutation <- "changed"
    testthat::expect_error(env$AlphaTop3Draw(bad, h, e$fixture, e$cutoff, context, root), "binding differs")
    bad <- base; bad$receipt <- list(tail = TRUE)
    testthat::expect_error(env$AlphaTop3Draw(bad, h, e$fixture, e$cutoff, context, root), "BEFORE-tail")
    bad <- e$cutoff; bad$cutoff_utc <- bad$cutoff_utc + 1
    testthat::expect_error(env$AlphaTop3Draw(base, h, e$fixture, bad, context, root), "Cutoff differs")
  }
})
