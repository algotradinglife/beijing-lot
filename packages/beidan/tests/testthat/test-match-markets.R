testthat::test_that("real Titan capture converts through the R boundary and existing inputs", {
  python <- Sys.getenv("RETICULATE_PYTHON", unset = "")
  testthat::skip_if(!nzchar(python), "explicit RETICULATE_PYTHON required")
  backend <- python_backend(python)
  schedule <- tibble::tibble(issue_id = "26098", slot = 39L, fixture_key = "26098:39",
    provider_id_nowscore = "2997421", home_nowscore = "蒂华纳", away_nowscore = "阿特拉斯",
    kickoff_at = lubridate::ymd_hms("2026-09-26 11:00:00", tz = "Asia/Shanghai"),
    handicap = 0, sale_state = "open", match_status = "unknown",
    observed_at = lubridate::ymd_hms("2026-09-26 01:00:00", tz = "Asia/Shanghai"),
    source_url_nowscore = "https://cp.nowscore.com/buy/DanChang.aspx?issueNum=26098")
  pages <- list()
  for (name in c("euro", "total_history")) {
    meta <- jsonlite::read_json(testthat::test_path("fixtures", "market_capture", paste0(name, ".json")))
    pages[[meta$url]] <- list(body = readBin(testthat::test_path("fixtures", "market_capture", paste0(name, ".raw")), "raw", n = 1e7), observed_at = meta$observed_at)
  }
  result <- fetch_match_markets(schedule, tempfile(), backend, pages = pages)
  testthat::expect_identical(result$coverage$status, "ok")
  testthat::expect_equal(nrow(result$euro), 1208)
  testthat::expect_equal(nrow(result$totals), 43)
  testthat::expect_identical(lubridate::tz(result$euro$quote_at), "Asia/Shanghai")
  testthat::expect_identical(lubridate::tz(result$captures$observed_at), "Asia/Shanghai")
  testthat::expect_true(all(result$totals$over_decimal > 1))
  input <- match_inputs_from_capture(schedule, result)
  testthat::expect_equal(nrow(input$prematch_sp), 0)
  testthat::expect_identical(input$match_status$status, "unknown")
  testthat::expect_equal(as.numeric(input$match_status$available_at), as.numeric(schedule$observed_at))
  testthat::expect_equal(nrow(input$euro), 1208)
  empty <- fetch_match_markets(schedule[FALSE, ], tempfile(), backend, pages = list())
  testthat::expect_s3_class(empty$euro, "tbl_df")
  testthat::expect_equal(nrow(empty$euro), 0)
  testthat::expect_identical(names(empty$euro), names(result$euro))
  testthat::expect_identical(lubridate::tz(empty$euro$quote_at), "Asia/Shanghai")
  testthat::expect_error(fetch_match_markets(schedule, tempfile(), backend, retries = 4), "<= 3")
  testthat::expect_error(fetch_match_markets(schedule, tempfile(), backend, totals_company_ids = c("8", "8")), "duplicat")
  changed <- schedule
  changed$provider_id_nowscore <- "9999999"
  testthat::expect_error(match_inputs_from_capture(changed, result), "Captured identity differs")
  changed <- schedule
  changed$kickoff_at <- changed$kickoff_at + 86400
  testthat::expect_error(match_inputs_from_capture(changed, result), "Captured identity differs")
  testthat::expect_true(all(result$diagnostics$fixture_id == "26098:39"))
  bad <- result
  bad$euro$fixture_id[1] <- "unmatched"
  testthat::expect_error(match_inputs_from_capture(schedule, bad), "do not match")
})
