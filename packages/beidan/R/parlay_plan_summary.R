#' Summarise funded groups and physical tickets
#'
#' @param result Complete result of parlay_build_plan(), with funded purchases,
#'   frontier ranked/candidate_tickets/ticket_legs and group_legs tables.
#' @return List(groups, tickets) of tibbles. Coverage sums only this decision's
#'   actual purchased probability mass; funded_depth is the maximum support rank,
#'   distinct from funded_tickets. Missing SP leaves EV unavailable. Display labels
#'   G01, G02 follow canonical group order and are not persistent identities.
#' @details Per-group coverage is not a portfolio union probability. No persistence,
#'   fitting, ranking or purchases occur. Invalid purchase-to-ranked joins error.
#' @export
parlay_plan_summary <- function(result) {
  if (!is.list(result) || is.null(result$funded$purchases) ||
      is.null(result$frontier$ranked)) stop("parlay_plan_summary: complete build result required")
  purchases <- match_validate_table(result$funded$purchases, "purchases")
  frontier <- result$frontier
  ranked <- match_validate_table(frontier$ranked, "ranked",
                                 keys = c("candidate_id", "ticket_id"))
  groups_empty <- tibble::tibble(display_label = character(), group_id = character(),
    candidate_id = character(), fixtures = character(), structure = character(),
    objective = character(), funded_tickets = integer(), funded_depth = integer(),
    support_size = integer(), coverage_probability = double(), cost_cny = double(),
    ev_available = logical(), coverage_basis = character())
  tickets_empty <- tibble::tibble(display_label = character(), ticket_id = character(),
    candidate_id = character(), ticket_outcomes = character(), group_id = character(),
    structure = character(), probability_mass = double(), cost_cny = double(),
    objective_value = double(), ev_net = double(), ev_availability = character(),
    support_rank = integer())
  if (!nrow(purchases)) return(list(groups = groups_empty, tickets = tickets_empty))
  key <- c("candidate_id", "ticket_id")
  if (nrow(dplyr::anti_join(purchases, ranked, by = key))) {
    stop("parlay_plan_summary: purchased ticket missing from candidate ranking")
  }
  rows <- dplyr::left_join(purchases,
    dplyr::select(ranked, dplyr::all_of(c(key, "probability", "ev_net_est", "rank"))),
    by = key, relationship = "many-to-one")
  ids <- sort(unique(rows$group_id))
  labels <- stats::setNames(sprintf("G%02d", seq_along(ids)), ids)
  objective <- result$config$objective
  checkmate::assert_choice(objective, c("probability", "ev"))
  group_legs <- frontier$group_legs
  ticket_text <- parlay_ticket_strings(
    frontier$ticket_legs[frontier$ticket_legs$ticket_id %in% purchases$ticket_id, , drop = FALSE],
    group_legs[group_legs$group_id %in% ids, , drop = FALSE])
  # ticket strings helper returns one canonical readable outcome sequence per ticket.
  outcomes <- ticket_text
  supports <- frontier$supports
  structures <- vapply(rows$candidate_id, function(id) {
    x <- supports[supports$candidate_id == id, , drop = FALSE]
    depths <- table(x$fixture_id[x$allowed])
    paste(sort(as.integer(depths), decreasing = TRUE), collapse = "")
  }, character(1))
  tickets <- tibble::tibble(display_label = unname(labels[rows$group_id]),
    ticket_id = rows$ticket_id, candidate_id = rows$candidate_id,
    ticket_outcomes = unname(outcomes[rows$ticket_id]), group_id = rows$group_id,
    structure = structures, probability_mass = rows$probability,
    cost_cny = rows$stake_cny,
    objective_value = if (objective == "ev") rows$ev_net_est else rows$probability,
    ev_net = rows$ev_net_est,
    ev_availability = ifelse(is.na(rows$ev_net_est), "unavailable", "available"),
    support_rank = as.integer(rows$rank))
  group_rows <- lapply(ids, function(id) {
    x <- tickets[tickets$group_id == id, , drop = FALSE]
    candidate <- unique(x$candidate_id)
    if (length(candidate) != 1L) stop("parlay_plan_summary: multiple structures funded in one group")
    legs <- group_legs[group_legs$group_id == id, , drop = FALSE]
    legs <- legs[order(legs$leg_order), , drop = FALSE]
    tibble::tibble(display_label = unname(labels[id]), group_id = id,
      candidate_id = candidate, fixtures = paste(legs$fixture_id, collapse = ", "),
      structure = x$structure[1], objective = objective,
      funded_tickets = as.integer(nrow(x)), funded_depth = as.integer(max(x$support_rank)),
      support_size = as.integer(sum(frontier$candidate_tickets$candidate_id == candidate)),
      coverage_probability = sum(x$probability_mass), cost_cny = sum(x$cost_cny),
      ev_available = all(is.finite(x$ev_net)),
      coverage_basis = "group_coverage_not_portfolio_union")
  })
  list(groups = dplyr::bind_rows(group_rows), tickets = tickets)
}
