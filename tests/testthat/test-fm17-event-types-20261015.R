testthat::test_that("sealed event diagnostic reconciles cohorts and stage projections", {
  root <- rprojroot::find_root(rprojroot::has_file("AGENTS.md"))
  output <- tempfile("fm17-types-")
  log <- tempfile("fm17-types-log-")
  status <- system2("/opt/R/4.6.1/bin/Rscript", shQuote(c(
    file.path(root, "r/fm17_event_type_diagnosis.R"), root, output,
    file.path(root, "config/fm17_event_types_20261015.csv"))),
    env = paste0("R_LIBS=", shQuote(paste(.libPaths(), collapse = ":"))), stdout = log, stderr = log)
  testthat::expect_equal(status, 0L, info = paste(readLines(log), collapse = "\n"))
  m <- readr::read_csv(file.path(output, "metrics.csv"), show_col_types = FALSE)
  coverage <- readr::read_csv(file.path(output, "coverage_summary.csv"), show_col_types = FALSE)
  all_coverage <- dplyr::filter(coverage, issue_id == "ALL")
  testthat::expect_equal(sum(all_coverage$roster_n), 347)
  testthat::expect_equal(sum(all_coverage$scored_n), 345)
  testthat::expect_equal(sum(all_coverage$estimated_n), 94)
  cup <- dplyr::filter(all_coverage, event_type == "cup")
  testthat::expect_equal(cup$estimated_n, 0)
  testthat::expect_equal(cup$native_n, 9)
  testthat::expect_equal(cup$market_n, 16)
  cm <- dplyr::filter(m, issue_id == "ALL", event_type == "cup", comparison == "near_sale", model == "FM-1.7.0")
  testthat::expect_equal(cm$n, 25)
  testthat::expect_equal(cm$hits1, 6)
  testthat::expect_equal(cm$hits2, 21)
  sums <- m |>
    dplyr::filter(issue_id == "ALL", comparison == "near_sale") |>
    dplyr::group_by(model) |>
    dplyr::summarise(n = sum(n), hits1 = sum(hits1), hits2 = sum(hits2), .groups = "drop")
  testthat::expect_true(all(sums$n == 345))
  testthat::expect_equal(sums$hits1[match("FM17_OVERLAY_OPPONENT_NATIVE", sums$model)], 135)
  testthat::expect_equal(sums$hits1[match("FM17_OVERLAY_SAME_SUPPORT_RAW", sums$model)], 140)
  testthat::expect_true(all(sums$hits2[sums$model != "BEIDAN_LATER"] == 250))
  effects <- readr::read_csv(file.path(output, "effects.csv"), show_col_types = FALSE)
  issue_effects <- dplyr::filter(effects, issue_id == "26102")
  testthat::expect_equal(sum(issue_effects$changed_n), 22)
  testthat::expect_equal(sum(issue_effects$opponent_lost_top1), 2)
  testthat::expect_equal(sum(issue_effects$opponent_saved_top1), 2)
  stages <- readr::read_csv(file.path(output, "stage_probabilities.csv"), show_col_types = FALSE)
  mass <- stages |> dplyr::group_by(fixture_id, stage, model) |>
    dplyr::summarise(mass = sum(probability), .groups = "drop")
  testthat::expect_true(all(abs(mass$mass - 1) < 1e-8))
  cases <- readr::read_csv(file.path(output, "cases.csv"), show_col_types = FALSE)
  testthat::expect_equal(sum(cases$event_type == "cup"), 25)
  testthat::expect_equal(sum(cases$issue_id == "26102" & cases$candidate_estimated), 22)
  testthat::expect_true(all(is.finite(cases$original_lambda_home[cases$selected_source == "native"])))
  market <- readr::read_csv(file.path(output, "market_evidence.csv"), show_col_types = FALSE)
  testthat::expect_equal(sum(market$available_joint_market[cases$selected_source[match(market$fixture_id, cases$fixture_id)] == "market"]), 16)
  testthat::expect_true(market$euro_rows[match("26102:20", market$fixture_id)] > 0)
  receipt <- jsonlite::fromJSON(file.path(output, "receipt.json"))
  testthat::expect_equal(receipt$mode, "POSTHOC_DESCRIPTIVE_NO_MODEL_UPDATE")
  testthat::expect_equal(receipt$dataset_version, "20261013-v2")
  testthat::expect_equal(length(names(receipt$output_hashes)), 12L)
  testthat::expect_setequal(names(receipt$input_hashes), c("scores", "labels", "roster", "stage", "parent", "candidate", "classification"))
  for (name in names(receipt$output_hashes)) {
    testthat::expect_equal(digest::digest(file = file.path(output, paste0(name, ".csv")), algo = "sha256"), receipt$output_hashes[[name]])
  }
  cat("tampered", file = file.path(output, "metrics.csv"), append = TRUE)
  testthat::expect_error(stopifnot(digest::digest(file = file.path(output, "metrics.csv"), algo = "sha256") == receipt$output_hashes$metrics))
  baseline <- readr::read_csv(file.path(root, "results/fm17-opponent-lambda-20261013/metrics.csv"), show_col_types = FALSE) |>
    dplyr::filter(cohort == "FULL_FROZEN_ROUTING_OVERLAY", issue_id == "ALL", comparison == "near_sale", model == "FM-1.7.0")
  type_baseline <- dplyr::filter(m, issue_id == "ALL", comparison == "near_sale", model == "FM-1.7.0")
  testthat::expect_equal(sum(type_baseline$brier * type_baseline$n) / sum(type_baseline$n), baseline$brier, tolerance = 1e-12)
  testthat::expect_equal(sum(type_baseline$logloss * type_baseline$n) / sum(type_baseline$n), baseline$logloss, tolerance = 1e-12)
})

testthat::test_that("unknown or duplicate event mappings fail before output writes", {
  root <- rprojroot::find_root(rprojroot::has_file("AGENTS.md"))
  mapping <- readr::read_csv(file.path(root, "config/fm17_event_types_20261015.csv"), show_col_types = FALSE)
  for (variant in c("unknown", "duplicate")) {
    bad <- if (variant == "unknown") dplyr::filter(mapping, league != "西乙") else dplyr::bind_rows(mapping, mapping[1, ])
    path <- tempfile(fileext = ".csv")
    readr::write_csv(bad, path)
    out <- tempfile("fm17-failed-")
    log <- tempfile()
    status <- system2("/opt/R/4.6.1/bin/Rscript", shQuote(c(file.path(root, "r/fm17_event_type_diagnosis.R"), root, out, path)),
      env = paste0("R_LIBS=", shQuote(paste(.libPaths(), collapse = ":"))), stdout = log, stderr = log)
    testthat::expect_true(status != 0L)
    testthat::expect_false(dir.exists(out))
  }
})
