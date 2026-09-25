testthat::test_that('valuation refuses missing, extra and mixed-width ticket legs', {
  cutoff <- list(issue_id = '00123', cutoff_utc = as.POSIXct('2026-09-22', tz = 'UTC'))
  tickets <- tibble::tibble(ticket_id = 'F:1', group_id = 'G', probability = .6,
    sp_product_est = NA_real_, ev_net_est = NA_real_)
  legs <- tibble::tibble(ticket_id = 'F:1', fixture_id = 'F', outcome = 'W')
  value <- function(t, l) parlay_value_tickets(t, l, match_typed_empty('prematch_sp'),
                                             cutoff, 10, 4.5, 2, .65)
  testthat::expect_error(value(tickets, match_typed_empty('ticket_legs')), 'identifiers')
  orphan <- legs
  orphan$ticket_id <- 'OTHER'
  testthat::expect_error(value(tickets, orphan), 'identifiers')
  testthat::expect_error(value(tickets, dplyr::bind_rows(legs, legs)), 'duplicate key')
  testthat::expect_error(value(match_typed_empty('tickets'), legs), 'identifiers')
  testthat::expect_equal(nrow(value(match_typed_empty('tickets'),
    match_typed_empty('ticket_legs'))), 0L)
  testthat::expect_true(is.na(value(tickets, legs)$ev_net_est))
  incomplete <- tickets
  incomplete$ticket_id <- 'F:1|G:1'
  incomplete_legs <- legs
  incomplete_legs$ticket_id <- incomplete$ticket_id
  testthat::expect_error(value(incomplete, incomplete_legs), 'physical ticket identity')
  two <- dplyr::bind_rows(tickets, dplyr::mutate(tickets, ticket_id = 'F:1|G:2'))
  mixed <- dplyr::bind_rows(legs, tibble::tibble(ticket_id = 'F:1|G:2',
                            fixture_id = c('F', 'G'), outcome = c('W', 'D')))
  testthat::expect_error(value(two, mixed), 'same positive leg count')
})
