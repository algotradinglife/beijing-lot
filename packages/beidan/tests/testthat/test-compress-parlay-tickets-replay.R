testthat::test_that("independent complete, missing-corner and diagonal examples", {
  tickets <- tibble::tibble(ticket_id = c("001", "002", "003", "004"),
    order = rep(1L, 4), cost_cny = rep(2, 4))
  legs <- tibble::tibble(ticket_id = rep(tickets$ticket_id, each = 2),
    fixture_id = rep(c("01", "02"), 4), slot = rep(c(1L, 2L), 4),
    outcome = c("W", "W", "W", "L", "D", "W", "D", "L"))
  full <- CompressParlayTickets(tickets, legs)
  testthat::expect_equal(nrow(full$slips), 1L)
  testthat::expect_equal(full$slips$ticket_count, 4L)
  testthat::expect_equal(full$slips$cost_cny, 8)
  testthat::expect_identical(full$legs$fixture_id, c("01", "02"))
  testthat::expect_identical(full$legs$outcomes, list(c("W", "D"), c("W", "L")))
  corner <- CompressParlayTickets(tickets[1:3, ], legs[1:6, ])
  testthat::expect_equal(nrow(corner$slips), 2L)
  testthat::expect_equal(sum(corner$slips$ticket_count), 3L)
  diagonal <- CompressParlayTickets(tickets[c(1, 4), ], legs[c(1, 2, 7, 8), ])
  testthat::expect_equal(nrow(diagonal$slips), 2L)
})

testthat::test_that("deterministic sparse synthetic products expand without filling holes", {
  grid <- tidyr::expand_grid(A = c("W", "D", "L"), B = c("W", "D", "L"))
  set.seed(2718)
  for (iteration in seq_len(32L)) {
    chosen <- sort(sample(seq_len(nrow(grid)), sample(seq_len(nrow(grid)), 1)))
    tickets <- tibble::tibble(ticket_id = sprintf("%03d", chosen),
      order = rep(1L, length(chosen)), cost_cny = rep(2, length(chosen)))
    legs <- dplyr::bind_cols(tickets["ticket_id"], grid[chosen, ]) |>
      tidyr::pivot_longer(c("A", "B"), names_to = "fixture_id", values_to = "outcome") |>
      dplyr::mutate(slot = match(fixture_id, c("A", "B")))
    compressed <- CompressParlayTickets(tickets, legs)
    expanded <- list()
    for (i in seq_len(nrow(compressed$slips))) {
      block <- dplyr::filter(compressed$legs, slip_id == compressed$slips$slip_id[i]) |>
        dplyr::arrange(slot)
      expanded[[i]] <- tidyr::expand_grid(!!!stats::setNames(block$outcomes, block$fixture_id))
    }
    all_bets <- dplyr::bind_rows(expanded)
    testthat::expect_equal(dplyr::arrange(all_bets, A, B), dplyr::arrange(grid[chosen, ], A, B))
    testthat::expect_false(anyDuplicated(all_bets) > 0L)
    testthat::expect_equal(sum(compressed$slips$cost_cny), 2 * length(chosen))
  }
})

testthat::test_that("compression replays every frozen bet without extra bets", {
  root <- rprojroot::find_root(rprojroot::has_file("packages/beidan/DESCRIPTION"))
  paths <- c("docs/reviews/upcoming-20261004-evidence/plans/frozen-research-plans.rds",
    "docs/reviews/upcoming-20261004-3322221-evidence/plans/frozen-research-plans.rds")
  for (path in paths) {
    frozen <- readRDS(file.path(root, path))
    for (pattern in names(frozen$tickets)) {
      tickets <- frozen$tickets[[pattern]]
      legs <- frozen$ticket_legs[[pattern]]
      compressed <- CompressParlayTickets(tickets, legs)
      testthat::expect_lte(nrow(compressed$slips), nrow(tickets))
      testthat::expect_equal(sum(compressed$slips$cost_cny), sum(tickets$cost_cny))
      testthat::expect_equal(sum(compressed$slips$ticket_count), nrow(tickets))
      testthat::expect_setequal(compressed$membership$ticket_id, tickets$ticket_id)
      testthat::expect_false(anyDuplicated(compressed$membership$ticket_id) > 0L)
      for (i in seq_len(nrow(compressed$slips))) {
        slip <- compressed$slips[i, ]
        block <- dplyr::filter(compressed$legs, slip_id == slip$slip_id)
        block <- dplyr::arrange(block, slot)
        grids <- tidyr::expand_grid(!!!stats::setNames(block$outcomes, block$fixture_id))
        expected_ids <- dplyr::filter(compressed$membership,
          slip_id == slip$slip_id)$ticket_id
        original <- dplyr::filter(legs, ticket_id %in% expected_ids) |>
          dplyr::select(ticket_id, fixture_id, outcome) |>
          tidyr::pivot_wider(names_from = fixture_id, values_from = outcome)
        original <- dplyr::select(original, dplyr::all_of(block$fixture_id))
        testthat::expect_equal(nrow(grids), slip$ticket_count)
        # Compare actual Cartesian expansions, independently of membership counts.
        testthat::expect_equal(dplyr::arrange(grids, dplyr::across(dplyr::everything())),
          dplyr::arrange(original, dplyr::across(dplyr::everything())))
        testthat::expect_equal(slip$cost_cny, sum(tickets$cost_cny[
          match(expected_ids, tickets$ticket_id)]))
      }
      set.seed(2718)
      shuffled <- CompressParlayTickets(tickets[sample(nrow(tickets)), ],
        legs[sample(nrow(legs)), ])
      testthat::expect_identical(shuffled, compressed)
    }
  }
})
