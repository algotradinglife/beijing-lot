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
  sp_text <- paste(readLines(testthat::test_path("fixtures", "prematch_sp", "reference.html"), warn=FALSE), collapse="\n")
  for (pair in list(c("25053","26098"),c("123","2997421"),c("M[1]","M[39]"),
                   c("row_1","row_39"),c('matchid="1"','matchid="39"'),
                   c("<td>1</td>","<td>39</td>"),c("sp_1_","sp_39_"),c("26098_1_5","26098_39_5"))) {
    sp_text <- gsub(pair[1],pair[2],sp_text,fixed=TRUE)
  }
  sp_url <- "https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum=26098"
  pages[[sp_url]] <- list(body=charToRaw(sp_text),observed_at="2026-09-26T01:00:00+08:00")
  result <- fetch_match_markets(schedule, tempfile(), backend, pages = pages)
  testthat::expect_identical(result$coverage$status, "ok")
  testthat::expect_equal(nrow(result$euro), 1190)
  testthat::expect_equal(nrow(result$totals), 43)
  testthat::expect_identical(lubridate::tz(result$euro$quote_at), "Asia/Shanghai")
  testthat::expect_identical(lubridate::tz(result$captures$observed_at), "Asia/Shanghai")
  testthat::expect_true(all(result$totals$over_decimal > 1))
  input <- match_inputs_from_capture(schedule, result)
  testthat::expect_equal(nrow(input$prematch_sp), 3)
  testthat::expect_equal(input$prematch_sp$sp_raw[match(c("W","D","L"),input$prematch_sp$outcome)],c(2.5,3.4,12))
  testthat::expect_equal(as.numeric(input$prematch_sp$quote_at),rep(as.numeric(schedule$observed_at),3))
  testthat::expect_true(file.exists(result$prematch_sp_receipt_path))
  testthat::expect_equal(nrow(attr(result$prematch_sp,"diagnostics")),0)
  missing_sp <- result; missing_sp$prematch_sp <- NULL
  testthat::expect_error(match_inputs_from_capture(schedule,missing_sp),"lacks prematch_sp")
  missing_page <- pages; missing_page[[sp_url]] <- NULL
  testthat::expect_error(fetch_match_markets(schedule,tempfile(),backend,pages=missing_page),"lacks Nowscore")
  testthat::expect_identical(input$match_status$status, "unknown")
  testthat::expect_equal(as.numeric(input$match_status$available_at), as.numeric(schedule$observed_at))
  testthat::expect_equal(nrow(input$euro), 1190)
  # A failed Titan request must not discard independently valid Beijing SP.
  sp_only_pages <- pages[sp_url]
  sp_only <- fetch_match_markets(schedule,tempfile(),backend,pages=sp_only_pages)
  testthat::expect_equal(nrow(sp_only$euro),0)
  testthat::expect_equal(nrow(sp_only$identities),0)
  sp_only_inputs <- match_inputs_from_capture(schedule,sp_only)
  testthat::expect_equal(nrow(sp_only_inputs$prematch_sp),3)
  changed_handicap <- schedule;changed_handicap$handicap <- 1
  testthat::expect_error(match_inputs_from_capture(changed_handicap,sp_only),"handicap")
  missing_identity <- result;missing_identity$prematch_sp_identities <- NULL
  testthat::expect_error(match_inputs_from_capture(schedule,missing_identity),"lacks prematch SP identity")
  empty <- fetch_match_markets(schedule[FALSE, ], tempfile(), backend, pages = list())
  testthat::expect_s3_class(empty$euro, "tbl_df")
  testthat::expect_equal(nrow(empty$euro), 0)
  testthat::expect_equal(nrow(empty$prematch_sp),0)
  testthat::expect_true("prematch_sp_receipt_path" %in% names(empty))
  testthat::expect_null(empty$prematch_sp_receipt_path)
  testthat::expect_identical(names(empty$prematch_sp),names(result$prematch_sp))
  testthat::expect_identical(names(empty$euro), names(result$euro))
  testthat::expect_identical(lubridate::tz(empty$euro$quote_at), "Asia/Shanghai")
  testthat::expect_error(fetch_match_markets(schedule, tempfile(), backend, retries = 4), "<= 3")
  testthat::expect_error(fetch_match_markets(schedule, tempfile(), backend, totals_company_ids = c("8", "8")), "duplicat")
  changed <- schedule
  changed$provider_id_nowscore <- "9999999"
  testthat::expect_error(match_inputs_from_capture(changed, result), "identity|match")
  changed <- schedule
  changed$kickoff_at <- changed$kickoff_at + 86400
  testthat::expect_warning(updated <- match_inputs_from_capture(changed, result), "Captured names/kickoff differ")
  testthat::expect_equal(nrow(updated$euro), nrow(result$euro))
  testthat::expect_equal(as.numeric(updated$fixtures$kickoff_at), as.numeric(changed$kickoff_at))
  changed <- schedule
  changed$home_nowscore <- "另一译名"
  testthat::expect_warning(updated <- match_inputs_from_capture(changed, result), "Captured names/kickoff differ")
  testthat::expect_equal(nrow(updated$totals), nrow(result$totals))
  testthat::expect_true(all(result$diagnostics$fixture_id == "26098:39"))
  bad <- result
  bad$prematch_sp$fixture_id[1] <- "unmatched"
  testthat::expect_error(match_inputs_from_capture(schedule, bad), "do not match")
  bad <- result
  bad$euro$fixture_id[1] <- "unmatched"
  testthat::expect_error(match_inputs_from_capture(schedule, bad), "do not match")
})


testthat::test_that("earlier conflicting quotes do not affect selected current price", {
  instant <- lubridate::ymd_hms("2026-09-26 18:00:00", tz = "Asia/Shanghai")
  quotes <- tibble::tibble(fixture_id = "26098:57", company_id = "281",
    quote_at = instant - c(120, 120, 60, -60),
    odds_home = c(1.5, 1.53, 1.57, 9))
  selected <- match_latest_quote_before(quotes, instant, "odds_home")
  testthat::expect_equal(selected$odds_home, 1.57)
  testthat::expect_equal(selected$quote_at, instant - 60)
})
