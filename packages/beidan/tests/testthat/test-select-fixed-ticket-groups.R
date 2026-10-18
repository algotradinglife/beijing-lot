#' Construct a label-free three-fixture fixed-block decision for selector tests
#' @return Explicit cutoff-bound decision; exercised by the tests below.
#' @noRd
FixedBlockFixture <- function() {
  q <- tibble::tibble(fixture_id = rep(c("A", "B", "C"), each = 3L),
    outcome = rep(c("W", "D", "L"), 3L),
    probability = c(.6, .25, .15, .5, .3, .2, .4, .35, .25))
  t <- tibble::tibble(group_id = rep(c("g1", "g2", "g3"), each = 2L),
    ticket_id = c("A:1|B:1", "A:1|B:2", "B:1|C:1", "B:3|C:1", "A:1|B:1", "A:1|B:2"),
    probability = c(.3, .18, .2, .08, .3, .18))
  d <- list(cutoff = list(issue_id = "001", cutoff_utc = lubridate::ymd_hms("2026-01-01 00:00:00", tz = "UTC")),
    probabilities = q, candidates = t, source_bindings = list(snapshot = "synthetic-independent-oracle"))
  d$source_receipt <- list(cutoff=d$cutoff,probability_hash=rlang::hash(q),candidate_hash=rlang::hash(t),max_source_available_utc=d$cutoff$cutoff_utc-60,source_snapshots=list(snapshot=strrep("a",64)))
  d$input_hash <- rlang::hash(d)
  d
}

test_that("fixed blocks use exact shared-fixture incremental coverage and retain copies", {
  d <- FixedBlockFixture()
  x <- SelectFixedTicketGroups(d, 3L, 2)
  expect_equal(x$selection$group_id, c("g1", "g2", "g3"))
  expect_equal(x$selection$marginal_coverage, c(.48, .16, 0), tolerance = 1e-12)
  expect_equal(x$selection$cumulative_coverage, c(.48, .64, .64), tolerance = 1e-12)
  expect_equal(x$selection$cumulative_expected_wins, c(.48, .76, 1.24))
  expect_equal(x$selection$cumulative_cost_cny, c(4, 8, 12))
  expect_equal(nrow(x$purchases), 6L)
  expect_equal(sum(x$purchases$ticket_id == "A:1|B:1"), 2L)
  expect_identical(SelectFixedTicketGroups(d, 3L, 2), x)
  expect_identical(x$receipt$cutoff, d$cutoff)
  expect_equal(SelectFixedTicketGroups(d, 1L, 2)$selection$group_id, "g1")
})

test_that("lazy selector matches an independently enumerated greedy state oracle", {
  d <- FixedBlockFixture()
  states <- tidyr::expand_grid(A = 1:3, B = 1:3, C = 1:3)
  state_mass <- d$probabilities$probability[states$A] *
    d$probabilities$probability[3L + states$B] * d$probabilities$probability[6L + states$C]
  covered <- cbind(g1 = states$A == 1L & states$B %in% 1:2,
    g2 = states$B %in% c(1L, 3L) & states$C == 1L,
    g3 = states$A == 1L & states$B %in% 1:2)
  owned <- rep(FALSE, nrow(states)); remaining <- colnames(covered); order <- character()
  for (step in 1:3) {
    gains <- colSums(covered[, remaining, drop = FALSE] * (!owned * state_mass))
    best <- names(gains)[order(-gains, names(gains))][1L]
    order <- c(order, best); owned <- owned | covered[, best]
    remaining <- setdiff(remaining, best)
  }
  expect_identical(SelectFixedTicketGroups(d, 3L, 2)$selection$group_id, order)
  # Post-cutoff labels are not part of the selector's decision or inputs.
  labels <- c(A = "W", B = "L", C = "D")
  before <- SelectFixedTicketGroups(d, 3L, 2)
  labels[] <- "L"
  expect_identical(SelectFixedTicketGroups(d, 3L, 2), before)
})

test_that("empty blocks retain tibble schemas and malformed bindings fail closed", {
  d <- FixedBlockFixture(); d$candidates <- d$candidates[0, ]; d$source_receipt$candidate_hash <- rlang::hash(d$candidates); d$input_hash <- NULL; d$input_hash <- rlang::hash(d)
  x <- SelectFixedTicketGroups(d, 8L, 2)
  expect_s3_class(x$selection, "tbl_df"); expect_type(x$selection$group, "integer")
  expect_equal(nrow(x$purchases), 0L); expect_type(x$purchases$probability, "double")
  d <- FixedBlockFixture(); d$cutoff$cutoff_utc <- d$cutoff$cutoff_utc + 1
  expect_error(SelectFixedTicketGroups(d, 8L, 2), "binding")
  d <- FixedBlockFixture(); d$cutoff <- NULL
  expect_error(SelectFixedTicketGroups(d, 8L, 2), "cutoff")
  d <- FixedBlockFixture(); d$candidates$probability[1] <- .1; d$source_receipt$candidate_hash <- rlang::hash(d$candidates); d$input_hash <- NULL; d$input_hash <- rlang::hash(d)
  expect_error(SelectFixedTicketGroups(d, 8L, 2), "probability mismatch")
  d <- FixedBlockFixture(); d$candidates <- d$candidates[-1, ]; d$source_receipt$candidate_hash <- rlang::hash(d$candidates); d$input_hash <- NULL; d$input_hash <- rlang::hash(d)
  expect_error(SelectFixedTicketGroups(d, 8L, 2), "equal ticket counts")
  d <- FixedBlockFixture(); d$candidates$ticket_id[1] <- "A:1|A:1"; d$source_receipt$candidate_hash <- rlang::hash(d$candidates); d$input_hash <- NULL; d$input_hash <- rlang::hash(d)
  expect_error(SelectFixedTicketGroups(d, 8L, 2), "canonical ticket")
  expect_error(SelectFixedTicketGroups(FixedBlockFixture(), 0L, 2))
  expect_error(SelectFixedTicketGroups(FixedBlockFixture(), 2L, 0))
})


test_that("rehashing a relabelled epoch cannot reuse an upstream forecast", {
  d <- FixedBlockFixture(); d$cutoff$cutoff_utc <- d$cutoff$cutoff_utc - 86400
  d$input_hash <- NULL; d$input_hash <- rlang::hash(d)
  expect_error(SelectFixedTicketGroups(d, 3L, 2), "upstream cutoff")
  d <- FixedBlockFixture(); d$source_receipt$max_source_available_utc <- d$cutoff$cutoff_utc
  d$input_hash <- NULL; d$input_hash <- rlang::hash(d)
  expect_error(SelectFixedTicketGroups(d, 3L, 2), "availability")
  d <- FixedBlockFixture(); d$source_receipt$probability_hash <- "stale"
  d$input_hash <- NULL; d$input_hash <- rlang::hash(d)
  expect_error(SelectFixedTicketGroups(d, 3L, 2), "binding")
  d <- FixedBlockFixture(); d$source_receipt$source_snapshots <- list(snapshot="invalid")
  d$input_hash <- NULL; d$input_hash <- rlang::hash(d)
  expect_error(SelectFixedTicketGroups(d, 3L, 2), "snapshot")
})
