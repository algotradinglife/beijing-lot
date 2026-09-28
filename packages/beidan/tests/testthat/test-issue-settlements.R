test_that("settlement capture crosses Python boundary as Beijing typed tibble", {
  python <- Sys.getenv("RETICULATE_PYTHON")
  skip_if(!nzchar(python), "explicit Python interpreter required")
  backend <- python_backend(python)
  schedule <- tibble::tibble(issue_id = "25053", slot = 1L, fixture_key = "25053:1",
    provider_id_nowscore = "123", handicap = 0)
  path <- test_path("fixtures", "settlement", "finished.html")
  pages <- list(body = readBin(path, "raw", n = file.info(path)$size),
    observed_at = "2026-09-26T10:00:00+08:00")
  x <- fetch_issue_settlements(schedule, tempfile(), backend, pages = pages)
  expect_s3_class(x, "tbl_df")
  expect_silent(match_validate_table(x, "settlements"))
  expect_identical(names(x), match_table_schemas()$settlements$columns)
  expect_identical(x$outcome, "W")
  expect_equal(x$settled_sp, 2.5)
  expect_equal(lubridate::tz(x$label_available_at), "Asia/Shanghai")
  expect_equal(format(x$label_available_at, "%H:%M:%S"), "10:00:00")
  expect_true(file.exists(attr(x,"receipt_path")))
  plan <- list(issue_id="25053", constants=list(unit_cny=2, payout_factor=0.65, n_legs=1L),
    funded=tibble::tibble(ticket_id="ticket1", group_id="group1"),
    ticket_legs=tibble::tibble(ticket_id="ticket1", fixture_id="25053:1", outcome="W"))
  settled <- parlay_settle_plan(plan, x, as.POSIXct("2026-09-26 03:00:00", tz="UTC"))
  expect_identical(settled$ticket_returns$status, "WON")
  expect_equal(settled$ticket_returns$payout_cny, 2 * 0.65 * 2.5)
  early <- parlay_settle_plan(plan, x, as.POSIXct("2026-09-26 01:00:00", tz="UTC"))
  expect_identical(early$ticket_returns$status, "PENDING")
  schedule$provider_id_nowscore <- "999"
  y <- fetch_issue_settlements(schedule, tempfile(), backend, pages = pages)
  expect_equal(nrow(y), 0)
  expect_silent(match_validate_table(y, "settlements"))
  expect_s3_class(y$label_available_at, "POSIXct")
  expect_identical(attr(y,"diagnostics")$reason, "identity_or_handicap_mismatch")
  expect_error(fetch_issue_settlements(as.data.frame(schedule), tempfile(), backend), "tibble")
  expect_error(fetch_issue_settlements(schedule[0, ], tempfile(), backend), "at least")
  expect_error(fetch_issue_settlements(schedule, "", backend))
  expect_error(fetch_issue_settlements(schedule, tempfile(), backend, timeout=0))
  expect_error(fetch_issue_settlements(schedule, tempfile(), backend, retries=-1))
  expect_error(fetch_issue_settlements(schedule, tempfile(), list()), "backend")
  expect_error(fetch_issue_settlements(schedule, tempfile(), backend, pages=list(body="html", observed_at="x")), "raw")
  expect_error(fetch_issue_settlements(schedule, tempfile(), backend, pages=list(body=pages$body)))
})

test_that("explicit all-one cancellation survives the R/Python boundary without a WDL label", {
  python <- Sys.getenv("RETICULATE_PYTHON")
  skip_if(!nzchar(python), "explicit Python interpreter required")
  path <- test_path("fixtures", "settlement", "cancelled-all-one.html")
  schedule <- tibble::tibble(issue_id="25053",slot=1L,fixture_key="25053:1",
    provider_id_nowscore="123",handicap=0)
  x <- fetch_issue_settlements(schedule,tempfile(),python_backend(python),
    pages=list(body=readBin(path,"raw",n=file.info(path)$size),
      observed_at="2026-09-27T21:02:44+08:00"))
  expect_silent(match_validate_table(x,"settlements"))
  expect_identical(x$status,"all_options_one")
  expect_identical(x$outcome,"ALL")
  expect_equal(x$settled_sp,1)
  expect_equal(lubridate::tz(x$label_available_at),"Asia/Shanghai")
  expect_equal(nrow(attr(x,"diagnostics")),0)
})
