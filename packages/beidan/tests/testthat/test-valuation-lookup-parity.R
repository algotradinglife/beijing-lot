test_that("indexed SP lookup preserves exact old valuation outputs and availability", {
  fixture <- readRDS(test_path("fixtures", "valuation-lookup-parity.rds"))
  for (i in seq_along(fixture$args)) {
    expect_identical(do.call(parlay_value_tickets, fixture$args[[i]]),
                     fixture$expected[[i]], info = names(fixture$args)[i])
  }
  bad <- fixture$args$normal
  quote <- bad$prematch_sp[bad$prematch_sp$fixture_id == bad$ticket_legs$fixture_id[1L] &
    bad$prematch_sp$outcome == bad$ticket_legs$outcome[1L], ][1L, ]
  # A contradiction at an older instant must still be refused.
  older <- dplyr::bind_rows(quote, quote)
  older$quote_at <- older$quote_at - 120
  older$sp_raw <- c(2, 3)
  bad$prematch_sp <- dplyr::bind_rows(bad$prematch_sp, older)
  expect_error(do.call(parlay_value_tickets, bad), "conflicting SP quotes")
  bad <- fixture$args$normal
  bad$tickets$ticket_id[1L] <- "wrong"
  expect_error(do.call(parlay_value_tickets, bad), "identifiers must match")
  empty <- fixture$args$normal
  empty$tickets <- empty$tickets[0, ]
  empty$ticket_legs <- empty$ticket_legs[0, ]
  expect_identical(do.call(parlay_value_tickets, empty), match_typed_empty("tickets"))
})
