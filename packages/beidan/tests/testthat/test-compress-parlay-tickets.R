testthat::test_that("PA scenarios preserve group and price boundaries", {
  tickets <- tibble::tibble(ticket_id = c("001", "002", "003", "004"),
    order = c(1L, 1L, 2L, 2L), cost_cny = c(2, 4, 2, 2))
  legs <- tibble::tibble(ticket_id = tickets$ticket_id, fixture_id = "01",
    slot = 1L, outcome = c("W", "D", "W", "D"))
  result <- CompressParlayTickets(tickets, legs)
  testthat::expect_equal(nrow(result$slips), 3L)
  testthat::expect_equal(result$slips$order, c(1L, 1L, 2L))
  testthat::expect_equal(result$slips$unit_cny, c(2, 4, 2))
  testthat::expect_equal(result$slips$ticket_count, c(1L, 1L, 2L))
  testthat::expect_equal(sum(result$slips$cost_cny), 10)
  testthat::expect_setequal(result$membership$ticket_id, tickets$ticket_id)
  # Names that match input column names remain legal character fixture IDs.
  legs$fixture_id <- "ticket_id"
  testthat::expect_identical(CompressParlayTickets(tickets, legs)$legs$fixture_id,
    rep("ticket_id", 3))
})

testthat::test_that("complete cube and singleton preserve exact amounts", {
  grid <- tidyr::expand_grid(A = c("W", "D"), B = c("W", "L"), C = c("D", "L"))
  tickets <- tibble::tibble(ticket_id = sprintf("%03d", seq_len(nrow(grid))),
    order = 1L, cost_cny = 2)
  legs <- dplyr::bind_cols(tickets["ticket_id"], grid) |>
    tidyr::pivot_longer(c("A", "B", "C"), names_to = "fixture_id", values_to = "outcome") |>
    dplyr::mutate(slot = match(fixture_id, c("A", "B", "C")))
  result <- CompressParlayTickets(tickets, legs)
  testthat::expect_equal(nrow(result$slips), 1L)
  testthat::expect_equal(result$slips$ticket_count, 8L)
  testthat::expect_equal(result$slips$cost_cny, 16)
  single <- CompressParlayTickets(tickets[1, ], legs[1:3, ])
  testthat::expect_equal(single$slips$ticket_count, 1L)
  testthat::expect_identical(single$membership$ticket_id, "001")
})

testthat::test_that("typed empty outputs and invalid boundary inputs", {
  tickets <- tibble::tibble(ticket_id = character(), order = integer(), cost_cny = double())
  legs <- tibble::tibble(ticket_id = character(), fixture_id = character(),
    slot = integer(), outcome = character())
  empty <- CompressParlayTickets(tickets, legs)
  testthat::expect_named(empty, c("slips", "legs", "membership"))
  testthat::expect_identical(vapply(empty, nrow, integer(1)), c(slips = 0L, legs = 0L, membership = 0L))
  testthat::expect_type(empty$slips$order, "integer")
  testthat::expect_type(empty$slips$ticket_count, "integer")
  testthat::expect_type(empty$slips$unit_cny, "double")
  testthat::expect_type(empty$slips$cost_cny, "double")
  testthat::expect_type(empty$legs$outcomes, "list")
  testthat::expect_type(empty$membership$ticket_id, "character")
  testthat::expect_error(CompressParlayTickets(tickets[, -1], legs))
  testthat::expect_error(CompressParlayTickets(tickets, legs[, -4]))
  testthat::expect_error(CompressParlayTickets(as.data.frame(tickets), legs))
  tickets <- tibble::tibble(ticket_id = c("001", "002"), order = 1L, cost_cny = 2)
  legs <- tibble::tibble(ticket_id = tickets$ticket_id, fixture_id = "A", slot = 1L, outcome = c("W", "D"))
  original <- tickets
  original_legs <- legs
  for (value in c(0, -1, Inf, NA_real_, NaN)) {
    bad <- tickets; bad$cost_cny[1] <- value
    testthat::expect_error(CompressParlayTickets(bad, legs))
  }
  bad <- tickets; bad$cost_cny <- c(.Machine$double.xmax, .Machine$double.xmax)
  testthat::expect_error(CompressParlayTickets(bad, legs))
  bad <- tickets; bad$cost_cny <- matrix(c(2, 2), ncol = 1)
  testthat::expect_error(CompressParlayTickets(bad, legs))
  bad <- tickets; bad$cost_cny <- as.Date(c("2026-10-01", "2026-10-02"))
  testthat::expect_error(CompressParlayTickets(bad, legs))
  for (value in c("", NA_character_, "001")) {
    bad <- tickets; bad$ticket_id[2] <- value
    testthat::expect_error(CompressParlayTickets(bad, legs))
  }
  bad <- tickets; bad$order <- c(1, 1)
  testthat::expect_error(CompressParlayTickets(bad, legs))
  bad <- tickets; bad$order[1] <- 0L
  testthat::expect_error(CompressParlayTickets(bad, legs))
  testthat::expect_error(CompressParlayTickets(tickets, legs[1, ]))
  bad <- legs; bad$ticket_id[1] <- "orphan"
  testthat::expect_error(CompressParlayTickets(tickets, bad))
  testthat::expect_error(CompressParlayTickets(tickets, dplyr::bind_rows(legs, legs[1, ])))
  for (value in c("X", "", NA_character_)) {
    bad <- legs; bad$outcome[1] <- value
    testthat::expect_error(CompressParlayTickets(tickets, bad))
  }
  bad <- legs; bad$outcome[2] <- "W"
  testthat::expect_error(CompressParlayTickets(tickets, bad))
  bad <- legs; bad$fixture_id[2] <- "B"
  testthat::expect_error(CompressParlayTickets(tickets, bad))
  bad <- legs; bad$slot[2] <- 2L
  testthat::expect_error(CompressParlayTickets(tickets, bad))
  bad <- legs; bad$fixture_id[1] <- NA_character_
  testthat::expect_error(CompressParlayTickets(tickets, bad))
  bad <- legs; bad$slot[1] <- NA_integer_
  testthat::expect_error(CompressParlayTickets(tickets, bad))
  testthat::expect_identical(tickets, original)
  testthat::expect_identical(legs, original_legs)
})
