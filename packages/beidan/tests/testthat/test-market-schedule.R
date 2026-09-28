testthat::test_that("capture covers all slots in the shared half-open window", {
  at <- lubridate::ymd_hms("2026-09-26 20:00:00", tz = "Asia/Shanghai")
  s <- tibble::tibble(fixture_key = paste0("26098:", c(78,79,120,121,122)),
    slot = c(78L,79L,120L,121L,122L),
    kickoff_at = at + lubridate::dhours(c(3.99,4,27.99,28,29)),
    team = letters[1:5])
  result <- match_market_schedule(s, at)
  testthat::expect_identical(result$schedule$slot, c(79L,120L))
  testthat::expect_identical(result$schedule, s[2:3, ])
  testthat::expect_identical(result$excluded$slot, c(78L,121L,122L))
  testthat::expect_identical(result$window, match_decision_window(at))
  testthat::expect_identical(match_market_schedule(s[5:1, ], at), result)
  # Display timezone does not change which instants are selected.
  utc <- s; utc$kickoff_at <- lubridate::with_tz(utc$kickoff_at, "UTC")
  testthat::expect_identical(match_market_schedule(utc, at)$schedule$slot, c(79L,120L))
})

testthat::test_that("capture reports missing times and preserves empty schemas", {
  at <- lubridate::ymd_hms("2026-09-26 20:00:00", tz = "Asia/Shanghai")
  s <- tibble::tibble(fixture_key="26098:79",slot=79L,kickoff_at=at + lubridate::dhours(5))
  empty <- match_market_schedule(s[0, ], at)
  testthat::expect_identical(empty$schedule, s[0, ])
  testthat::expect_s3_class(empty$excluded, "tbl_df")
  s$kickoff_at[1] <- NA
  result <- match_market_schedule(s, at)
  testthat::expect_equal(nrow(result$schedule), 0L)
  testthat::expect_identical(result$excluded$reason, "unknown kickoff")
  testthat::expect_error(match_market_schedule(s, NA_real_), "POSIXct")
  testthat::expect_error(match_market_schedule(s, at[c(1,1)]), "one finite instant")
  testthat::expect_error(match_market_schedule(s, as.POSIXct(NA)), "one finite instant")
  testthat::expect_error(match_market_schedule(dplyr::bind_rows(s,s), at), "duplicat")
  bad <- s; bad$kickoff_at <- "tomorrow"
  testthat::expect_error(match_market_schedule(bad, at), "POSIXct")
  bad <- s; bad$kickoff_at <- as.POSIXct(Inf, origin="1970-01-01",tz="UTC")
  testthat::expect_error(match_market_schedule(bad, at), "finite")
  testthat::expect_error(match_market_schedule(as.data.frame(s), at), "tibble")
  testthat::expect_error(match_market_schedule(s[,1:2], at), "lacks")
})
