#' Compress purchased single tickets into disjoint Cartesian-product slips
#'
#' A deterministic lossless formatting operation, without learning or selection.
#' Only boxes with identical options at every other fixture and disjoint options
#' at the merged fixture can be combined. Forward/reverse coordinate rotations
#' are tried independently for each group and price, retaining the smallest
#' partition. This heuristic does not guarantee a globally minimum partition.
#'
#' @param tickets Tibble, one row per purchased single: unique nonempty character
#'   `ticket_id`, positive integer `order`, and finite positive numeric
#'   `cost_cny` in CNY per single. Additional columns are ignored.
#' @param legs Tibble, one row per ticket/fixture: character `ticket_id` and
#'   nonempty `fixture_id`, positive integer `slot`, character `outcome` W/D/L.
#'   Each order has one common nonempty fixture set and a bijective fixture/slot
#'   mapping. Additional columns are ignored. Identifiers retain leading zeros.
#' @return List of tibbles: `slips` (order integer, slip_id character,
#'   ticket_count integer, unit_cny double, cost_cny double); `legs` (order
#'   integer, slip_id/fixture_id character, slot integer, outcomes list of
#'   character vectors ordered W/D/L); `membership` (order integer,
#'   slip_id/ticket_id character). Membership partitions all original tickets;
#'   expanding each slip's options reproduces exactly those tickets.
#' @details Both empty inputs return typed empty outputs. Missing values, wrong
#'   types, duplicate IDs/combinations, missing/orphan/duplicate legs, inconsistent
#'   fixtures/slots, invalid outcomes and nonfinite aggregate amounts fail.
#'   Different orders and per-single prices never merge. No I/O or mutation.
#' @export
CompressParlayTickets <- function(tickets, legs) {
  if (!tibble::is_tibble(tickets) || !tibble::is_tibble(legs))
    stop("tickets and legs must be tibbles")
  checkmate::assert_names(names(tickets), must.include = c("ticket_id", "order", "cost_cny"))
  checkmate::assert_names(names(legs), must.include = c("ticket_id", "fixture_id", "slot", "outcome"))
  tickets <- dplyr::select(tickets, ticket_id, order, cost_cny)
  legs <- dplyr::select(legs, ticket_id, fixture_id, slot, outcome)
  for (x in list(tickets$ticket_id, legs$ticket_id, legs$fixture_id, legs$outcome)) {
    checkmate::assert_character(x, any.missing = FALSE, min.chars = 1L)
    if (!is.null(dim(x))) stop("Character columns must be vectors")
  }
  checkmate::assert_integer(tickets$order, lower = 1L, any.missing = FALSE)
  checkmate::assert_integer(legs$slot, lower = 1L, any.missing = FALSE)
  checkmate::assert_numeric(tickets$cost_cny, finite = TRUE, any.missing = FALSE)
  if (!is.null(dim(tickets$order)) || !is.null(dim(legs$slot)) ||
      !is.null(dim(tickets$cost_cny)) || is.object(tickets$cost_cny) ||
      any(tickets$cost_cny <= 0) || !is.finite(sum(tickets$cost_cny)))
    stop("Invalid scalar column types or positive finite CNY amounts")
  if (anyDuplicated(tickets$ticket_id)) stop("ticket_id must be unique")
  if (anyDuplicated(legs[c("ticket_id", "fixture_id")]))
    stop("Duplicate ticket_id/fixture_id legs")
  if (!setequal(tickets$ticket_id, legs$ticket_id)) stop("Missing or orphan ticket legs")
  if (any(!legs$outcome %in% c("W", "D", "L"))) stop("outcome must be W/D/L")
  empty <- list(
    slips = tibble::tibble(order = integer(), slip_id = character(),
      ticket_count = integer(), unit_cny = double(), cost_cny = double()),
    legs = tibble::tibble(order = integer(), slip_id = character(),
      fixture_id = character(), slot = integer(), outcomes = list()),
    membership = tibble::tibble(order = integer(), slip_id = character(), ticket_id = character()))
  if (!nrow(tickets)) return(empty)
  tickets <- dplyr::arrange(tickets, order, ticket_id)
  legs <- dplyr::left_join(legs, tickets, by = "ticket_id", relationship = "many-to-one")
  outputs <- list()
  for (group_order in sort(unique(tickets$order))) {
    group_legs <- dplyr::filter(legs, order == group_order)
    coordinates <- group_legs |> dplyr::distinct(fixture_id, slot) |> dplyr::arrange(slot)
    if (anyDuplicated(coordinates$fixture_id) || anyDuplicated(coordinates$slot))
      stop("Fixture and slot mapping must be one-to-one within order")
    counts <- dplyr::count(group_legs, ticket_id)
    if (any(counts$n != nrow(coordinates)))
      stop("Every ticket must have the same nonempty fixture set within order")
    column_names <- paste0("fixture_", seq_len(nrow(coordinates)))
    wide <- group_legs |>
      dplyr::mutate(coordinate = column_names[match(fixture_id, coordinates$fixture_id)]) |>
      dplyr::select(ticket_id, coordinate, outcome) |>
      tidyr::pivot_wider(names_from = coordinate, values_from = outcome) |>
      dplyr::arrange(ticket_id)
    outcomes <- dplyr::select(wide, dplyr::all_of(column_names))
    if (anyNA(outcomes) || anyDuplicated(outcomes))
      stop("Missing legs or duplicate purchased combination within order")
    prices <- tickets$cost_cny[match(wide$ticket_id, tickets$ticket_id)]
    group_boxes <- list()
    group_members <- list()
    group_prices <- double()
    for (price in sort(unique(prices))) {
      indices <- which(prices == price)
      initial <- matrix(c(1L, 2L, 4L)[match(as.matrix(outcomes[indices, ]),
        c("W", "D", "L"))], nrow = length(indices))
      dimensions <- ncol(initial)
      best_count <- nrow(initial) + 1L
      best_key <- NULL
      for (direction in c(1L, -1L)) {
        base_order <- if (direction == 1L) seq_len(dimensions) else rev(seq_len(dimensions))
        for (rotation in seq_len(dimensions) - 1L) {
          dimension_order <- base_order[((seq_len(dimensions) + rotation - 1L) %% dimensions) + 1L]
          boxes <- initial
          members <- as.list(wide$ticket_id[indices])
          repeat {
            previous_count <- nrow(boxes)
            for (dimension in dimension_order) {
              others <- setdiff(seq_len(dimensions), dimension)
              keys <- if (length(others)) apply(boxes[, others, drop = FALSE], 1,
                paste0, collapse = "") else rep("", nrow(boxes))
              blocks <- split(seq_len(nrow(boxes)), keys)
              merged <- matrix(0L, nrow = length(blocks), ncol = dimensions)
              merged_members <- vector("list", length(blocks))
              for (j in seq_along(blocks)) {
                rows <- blocks[[j]]
                masks <- boxes[rows, dimension]
                union_mask <- 0L
                for (mask in masks) {
                  if (bitwAnd(union_mask, mask) != 0L)
                    stop("Internal invariant: Cartesian boxes overlap")
                  union_mask <- bitwOr(union_mask, mask)
                }
                merged[j, ] <- boxes[rows[1L], ]
                merged[j, dimension] <- union_mask
                merged_members[[j]] <- sort(unlist(members[rows], use.names = FALSE), method = "radix")
              }
              boxes <- merged
              members <- merged_members
            }
            if (nrow(boxes) == previous_count) break
          }
          row_keys <- apply(boxes, 1, paste0, collapse = "")
          canonical <- order(row_keys, method = "radix")
          key <- paste(row_keys[canonical], collapse = ";")
          if (nrow(boxes) < best_count ||
              (nrow(boxes) == best_count && key < best_key)) {
            best_count <- nrow(boxes)
            best_key <- key
            best_boxes <- boxes[canonical, , drop = FALSE]
            best_members <- members[canonical]
          }
        }
      }
      group_boxes <- c(group_boxes, lapply(seq_len(nrow(best_boxes)),
        function(i) best_boxes[i, ]))
      group_members <- c(group_members, best_members)
      group_prices <- c(group_prices, rep(as.double(price), nrow(best_boxes)))
    }
    for (i in seq_along(group_boxes)) {
      slip_id <- sprintf("G%d-%03d", group_order, i)
      options <- lapply(group_boxes[[i]], function(mask)
        c("W", "D", "L")[bitwAnd(mask, c(1L, 2L, 4L)) != 0L])
      ticket_count <- prod(lengths(options))
      if (ticket_count != length(group_members[[i]]))
        stop("Internal invariant: expansion and membership differ")
      outputs[[length(outputs) + 1L]] <- list(
        slips = tibble::tibble(order = group_order, slip_id = slip_id,
          ticket_count = as.integer(ticket_count), unit_cny = group_prices[i],
          cost_cny = ticket_count * group_prices[i]),
        legs = tibble::tibble(order = group_order, slip_id = slip_id,
          fixture_id = coordinates$fixture_id, slot = coordinates$slot, outcomes = options),
        membership = tibble::tibble(order = group_order, slip_id = slip_id,
          ticket_id = group_members[[i]]))
    }
  }
  result <- lapply(names(empty), function(name)
    dplyr::bind_rows(lapply(outputs, `[[`, name)))
  names(result) <- names(empty)
  return(result)
}
