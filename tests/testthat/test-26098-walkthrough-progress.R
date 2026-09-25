testthat::test_that("walkthrough does not count SPECIAL or empty objects as completed", {
  text <- readLines(testthat::test_path("..", "..", "quarto", "26098_walkthrough.qmd"))
  start <- which(text == "#| label: progress") + 1L
  end <- which(seq_along(text) > start & text == "```")[1L] - 1L
  env <- new.env(parent = globalenv())
  env$schedule <- tibble::tibble()
  env$markets <- list(coverage = tibble::tibble(status = "partial"))
  env$epoch <- list(fixtures = tibble::tibble())
  env$projected <- list(probabilities = tibble::tibble())
  env$result <- list(funded = list(purchases = tibble::tibble(ticket_id = "a")))
  env$settled <- list(ticket_returns = tibble::tibble(status = "SPECIAL"))
  env$diagnosis <- tibble::tibble(status = "PENDING")
  env$decision_at <- NULL
  printed <- capture.output(eval(parse(text = text[start:end]), envir = env))
  testthat::expect_equal(env$settled_count, 0L)
  testthat::expect_equal(env$special_count, 1L)
  testthat::expect_equal(env$market_count, 0L)
  testthat::expect_equal(env$admitted_count, 0L)
  testthat::expect_true(any(grepl("尚未完成", printed)))
})
