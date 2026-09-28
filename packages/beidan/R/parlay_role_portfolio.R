# Role round-robin (#537), stage 3: package enumeration, depth, and budget-constrained
# portfolio selection with bounded local improvement.
#
# Issue #537 splits the decision into three separable steps:
#   1. candidate generation  -- parlay_construct_role_groups(), budget-independent;
#   2. single-group depth     -- buy top floor(group_budget_cny / unit_cny) legal
#      tickets of a candidate, capped by the structure's FULL support space;
#   3. portfolio selection    -- greedily include whole packages under the total
#      budget_cny, checking match reuse/overlap against the groups already selected.
#      No prior purchase history is consulted and no historical spend is deducted;
#      the caller manages cumulative budget outside this function.
#
# Three things this stage must never do:
#   * let a package be shrunk to fit the remaining budget. An unaffordable WHOLE
#     package is skipped; the balance is kept.
#   * silently switch or impute an objective. "probability" and "ev" are separate
#     paths; a missing SP is an error on the EV path.
#   * claim a historical availability receipt. Nothing is fitted here.

# --- result construction -----------------------------------------------------

#' Group legs of the selected candidate groups
#'
#' Internal. One row per (group, round) with `leg_order = round`, because a role
#' leg's round IS its position in the group.
#' @param portfolio Role candidate pool from [parlay_construct_role_groups()].
#' @param selected_groups The selected subset of `portfolio$groups`.
#' @return A validated `group_legs` tibble; the typed-empty table when nothing was
#'   selected.
#' @noRd
.parlay_role_group_legs <- function(portfolio, selected_groups) {
  empty <- match_typed_empty("group_legs")
  if (!nrow(selected_groups)) return(empty)
  ids <- as.character(selected_groups$group_id)
  legs <- portfolio$role_legs
  legs <- legs[as.character(legs$group_id) %in% ids, , drop = FALSE]
  if (!nrow(legs)) return(empty)
  out <- tibble::tibble(group_id = as.character(legs$group_id),
                        fixture_id = as.character(legs$fixture_id),
                        leg_order = as.integer(legs$round))
  out <- out[order(out$group_id, out$leg_order), , drop = FALSE]
  match_validate_table(out, "group_legs")
}

#' Build ticket supports from the frozen role legs
#'
#' Internal. The allowed set is the role's retained outcomes and `preference` is the
#' retained order inside that role (1 = most likely), which fixes the ticket mask. The
#' supports come from the FROZEN roles, never from a re-derived assignment.
#' @param portfolio Role candidate pool from [parlay_construct_role_groups()].
#' @param group_legs Validated legs of the selected groups.
#' @param label Candidate label suffix derived from the pattern.
#' @return A validated `supports` tibble (candidate_id, fixture_id, outcome, allowed,
#'   preference).
#' @noRd
.parlay_role_supports <- function(portfolio, group_legs, label) {
  legs <- portfolio$role_legs
  rows <- list()
  for (group_id in unique(as.character(group_legs$group_id))) {
    block <- legs[as.character(legs$group_id) == group_id, , drop = FALSE]
    block <- block[order(block$round), , drop = FALSE]
    for (i in seq_len(nrow(block))) {
      ordered <- match_outcomes() %in% as.character(block$allowed_outcomes[[i]])
      ordered <- match_outcomes()[ordered]
      for (j in seq_along(ordered)) {
        rows[[length(rows) + 1L]] <- tibble::tibble(
          candidate_id = paste0(group_id, "|", label),
          fixture_id = as.character(block$fixture_id[i]),
          outcome = ordered[j], allowed = TRUE, preference = as.integer(j))
      }
    }
  }
  match_validate_table(dplyr::bind_rows(rows), "supports")
}

#' Build an empty selection under the explicit budget contract
#' @param portfolio Candidate pool.
#' @param prematch_sp Validated reference SP table.
#' @param cutoff Explicit decision cutoff.
#' @param objective Probability or EV objective.
#' @param budget_cny Explicit total decision budget in CNY, or `NULL` for unlimited.
#' @param constraints Final reuse and overlap limits.
#' @return A normal result with no purchases.
#' @noRd
.parlay_role_empty_result <- function(portfolio, prematch_sp, cutoff, objective,
                                      budget_cny, constraints) {
  purchases <- tibble::tibble(ticket_id=character(), group_id=character(),
    candidate_id=character(), rank=integer(), probability=double(), cost_cny=double(),
    sp_product_est=double(), ev_net_est=double(), objective=character())
  .parlay_role_result(portfolio,purchases,prematch_sp,cutoff,objective,
    budget_cny,constraints)
}


#' Package table for the complete candidate groups
#'
#' Internal. One row per complete candidate with its physical ticket package at the
#' requested depth. `package_score` is the sum of the selected tickets' probability
#' (or EV under the EV objective) and the sort is deterministic: score descending,
#' then group_slot, then group_id.
#' @param portfolio Role candidate pool.
#' @param probabilities Authoritative probability tibble.
#' @param prematch_sp Pre-cutoff SP tibble.
#' @param cutoff Decision cutoff.
#' @param group_budget_cny Per-group budget in CNY, or `NULL` for the group's FULL
#'   legal support space.
#' @param objective One of `"probability"` or `"ev"`.
#' @return A list(packages, stack) where `packages` is a tibble(group_slot, group_id,
#'   rank, package_units, package_cost_cny, package_score, support_cap, tickets,
#'   ranked) and `stack` is the per-group list of selected ranked rows.
#' @noRd
.parlay_role_packages <- function(portfolio, probabilities, prematch_sp, cutoff,
                                  group_budget_cny, objective) {
  settings <- portfolio$settings
  n_legs <- as.integer(settings$n_legs)
  label <- paste0("p", paste(portfolio$pattern, collapse = ""))
  groups <- portfolio$groups[portfolio$groups$complete, , drop = FALSE]
  groups <- groups[order(groups$group_slot), , drop = FALSE]
  if (!nrow(groups)) {
    return(list(packages = .parlay_role_typed_empty("selection"), stack = list(),
                fixture_sets = list(), label = label,
                group_legs = match_typed_empty("group_legs")))
  }
  unit_cny <- as.numeric(settings$unit_cny)
  # `group_budget_cny = NULL` means the group buys its FULL legal support space; a
  # finite value is capped by that same space and floored to whole tickets. A
  # zero/sub-unit budget therefore yields zero tickets rather than an error.
  unlimited_group_budget <- is.null(group_budget_cny)
  units_wanted <- if (unlimited_group_budget) NA_integer_ else
    floor(as.numeric(group_budget_cny) / unit_cny)
  leg_rows <- list()
  stack <- list()
  fixture_sets <- list()
  rows <- list()
  for (i in seq_len(nrow(groups))) {
    group_id <- as.character(groups$group_id[i])
    block <- portfolio$role_legs[as.character(portfolio$role_legs$group_id) == group_id,
                                 , drop = FALSE]
    block <- block[order(block$round), , drop = FALSE]
    support_rows <- list()
    for (j in seq_len(nrow(block))) {
      ordered <- match_outcomes()[match_outcomes() %in%
                                    as.character(block$allowed_outcomes[[j]])]
      for (k in seq_along(ordered)) {
        support_rows[[length(support_rows) + 1L]] <- tibble::tibble(
          candidate_id = paste0(group_id, "|", label),
          fixture_id = as.character(block$fixture_id[j]),
          outcome = ordered[k], allowed = TRUE, preference = as.integer(k))
      }
    }
    candidate_id <- paste0(group_id, "|", label)
    group_legs <- tibble::tibble(
      group_id = rep(group_id, nrow(block)),
      fixture_id = as.character(block$fixture_id),
      leg_order = as.integer(block$round))
    group_legs <- match_validate_table(group_legs[order(group_legs$leg_order), ,
                                                 drop = FALSE], "group_legs")
    supports <- match_validate_table(dplyr::bind_rows(support_rows), "supports")
    tickets <- parlay_enumerate_tickets(group_legs, probabilities, cutoff, supports,
                                        n_legs = n_legs)
    valued <- parlay_value_tickets(tickets$tickets, tickets$ticket_legs, prematch_sp,
                                   cutoff, settings$sp_threshold,
                                   settings$sp_replacement, settings$unit_cny,
                                   settings$payout_factor)
    ranked <- parlay_rank_tickets(valued, tickets$candidate_tickets, cutoff,
                                  "probability_desc")
    # `parlay_rank_tickets` carries probability and EV but not the SP product; attach
    # it so the purchase ledger can report the estimated SP of each bought ticket.
    ranked$sp_product_est <- as.numeric(
      valued$sp_product_est[match(ranked$ticket_id, valued$ticket_id)])
    support_cap <- nrow(ranked)
    # WITHIN-PACKAGE DEPTH IS ALWAYS THE PROBABILITY TOP. The objective ranks WHOLE
    # packages by their aggregate score below; it must never reorder the tickets
    # inside a package, because the depth contract is "the top N most likely legal
    # tickets" regardless of whether EV ranks the packages.
    take <- as.integer(if (unlimited_group_budget) support_cap else min(units_wanted, support_cap))
    if (identical(objective, "ev") && any(!is.finite(ranked$ev_net_est))) {
      stop("objective ev requires complete valid pre-cutoff SP")
    }
    selected <- if (take > 0L) ranked[seq_len(take), , drop = FALSE] else
      ranked[0, , drop = FALSE]
    score <- if (!nrow(selected)) 0 else if (identical(objective, "ev")) {
      sum(as.numeric(selected$ev_net_est))
    } else {
      sum(as.numeric(selected$probability))
    }
    selected$objective <- rep(objective, nrow(selected))
    stack[[group_id]] <- selected
    fixture_sets[[group_id]] <- sort(unique(as.character(block$fixture_id)))
    rows[[length(rows) + 1L]] <- tibble::tibble(
      group_slot = as.integer(groups$group_slot[i]), group_id = group_id,
      rank = as.integer(i), package_units = as.integer(take),
      package_cost_cny = as.numeric(take * as.numeric(settings$unit_cny)),
      package_score = as.numeric(score), support_cap = as.integer(support_cap))
    leg_rows[[length(leg_rows) + 1L]] <- group_legs
  }
  packages <- dplyr::bind_rows(rows)
  # Deterministic package ordering: score descending, ties by group_slot then
  # group_id so the inclusion order never depends on row order.
  packages <- packages[order(-packages$package_score, packages$group_slot,
                             packages$group_id), , drop = FALSE]
  packages$rank <- seq_len(nrow(packages))
  list(packages = packages, stack = stack, fixture_sets = fixture_sets,
       label = label,
       group_legs = if (length(leg_rows)) dplyr::bind_rows(leg_rows) else
         match_typed_empty("group_legs"))
}

# --- selection ---------------------------------------------------------------

#' Greedy budget- and constraint-constrained package selection
#'
#' Internal. Walks the deterministically ordered packages and includes a WHOLE
#' package only when
#'   * at least one physical ticket is new; duplicate-only packages are skipped, AND
#'   * its NEWLY purchased units still fit the remaining total `budget_cny` (balance
#'     kept, no tail shrink; `NULL` means no cap), AND
#'   * adding it keeps match reuse and pairwise overlap within `constraints` against
#'     the groups already selected.
#' Only the newly purchased physical units are charged, once each: a package that
#' overlaps an already-selected group through some tickets contributes exactly its
#' new tickets and their actual cost, never its full package cost followed by a later
#' de-duplication. An unaffordable package is SKIPPED whole and the walk continues.
#' @param packages Deterministically ordered package tibble.
#' @param stack Per-group selected ranked rows.
#' @param unit_cny Positive CNY cost of one ticket.
#' @param budget_cny Total decision budget in CNY, or `NULL` for unlimited.
#' @param constraints List with `max_reuse` and `max_overlap`.
#' @param fixture_sets Named list mapping group_id to its sorted fixture set.
#' @return A list(selection, selected_ids, consumed, remaining, purchases) where
#'   `purchases` maps each selected group to the physical tickets it NEWLY bought.
#' @noRd
.parlay_role_select <- function(packages, stack, unit_cny, budget_cny, constraints,
                                fixture_sets) {
  n <- nrow(packages)
  selection <- tibble::tibble(
    group_slot = as.integer(packages$group_slot),
    group_id = as.character(packages$group_id),
    rank = as.integer(packages$rank),
    package_units = as.integer(packages$package_units),
    package_cost_cny = as.numeric(packages$package_cost_cny),
    package_score = as.numeric(packages$package_score),
    selected = rep(FALSE, n), reason = rep(NA_character_, n))
  # No prior purchase history is consulted: only the current groups may reuse or
  # overlap, and physical tickets are de-duplicated across the groups selected HERE.
  budget_is_null <- is.null(budget_cny)
  purchased <- character(0)
  selected_sets <- list()
  new_purchases <- list()
  consumed <- 0
  max_reuse <- as.numeric(constraints$max_reuse)
  max_overlap <- as.numeric(constraints$max_overlap)
  for (i in seq_len(n)) {
    group_id <- as.character(packages$group_id[i])
    if (nrow(stack[[group_id]]) == 0L) {
      selection$reason[i] <- "empty_package"
      next
    }
    # Duplicate rejection comes FIRST: a package that would re-buy physical tickets
    # already held by an earlier selected group is skipped as duplicate-only without
    # charging its full package cost.
    tickets <- as.character(stack[[group_id]]$ticket_id)
    new_index <- which(!tickets %in% purchased)
    selection$package_units[i] <- as.integer(length(new_index))
    selection$package_cost_cny[i] <- length(new_index) * unit_cny
    selection$package_score[i] <- sum(if (identical(stack[[group_id]]$objective[1], "ev"))
      stack[[group_id]]$ev_net_est[new_index] else stack[[group_id]]$probability[new_index])
    if (!length(new_index)) {
      selection$reason[i] <- "duplicate_physical_tickets_only"
      next
    }
    # Charge only the NEWLY purchased units at their actual unit cost.
    new_cost <- as.numeric(length(new_index) * as.numeric(unit_cny))
    if (!budget_is_null && consumed + new_cost > as.numeric(budget_cny) + 1e-9) {
      selection$reason[i] <- "insufficient_remaining_budget"
      next
    }
    set <- as.character(fixture_sets[[group_id]])
    # Constraint check against the FINAL selected state: only the groups selected so
    # far, never the whole overlapping candidate pool.
    groups <- selected_sets
    reuse_ok <- all(vapply(set, function(fixture_id) {
      sum(vapply(groups, function(g) fixture_id %in% g, logical(1L))) + 1 <= max_reuse
    }, logical(1)))
    if (!reuse_ok) {
      selection$reason[i] <- "max_reuse_exceeded"
      next
    }
    overlap_ok <- all(vapply(groups, function(g) {
      length(intersect(g, set)) <= max_overlap
    }, logical(1)))
    if (!overlap_ok) {
      selection$reason[i] <- "max_overlap_exceeded"
      next
    }
    selection$selected[i] <- TRUE
    selection$reason[i] <- "selected"
    # The selection ledger reports what was ACTUALLY bought: only the newly purchased
    # units and their actual cost, not the full package price.
    selection$package_units[i] <- as.integer(length(new_index))
    selection$package_cost_cny[i] <- as.numeric(new_cost)
    selected_row <- stack[[group_id]][new_index, , drop = FALSE]
    purchased <- c(purchased, tickets[new_index])
    new_purchases[[length(new_purchases) + 1L]] <- tibble::tibble(
      ticket_id = as.character(selected_row$ticket_id),
      group_id = as.character(group_id),
      candidate_id = as.character(selected_row$candidate_id),
      rank = as.integer(selected_row$rank),
      probability = as.numeric(selected_row$probability),
      cost_cny = as.numeric(unit_cny),
      sp_product_est = as.numeric(selected_row$sp_product_est),
      ev_net_est = as.numeric(selected_row$ev_net_est),
      objective = as.character(selected_row$objective))
    selected_sets[[length(selected_sets) + 1L]] <- set
    consumed <- consumed + new_cost
  }
  purchases <- if (length(new_purchases)) {
    dplyr::bind_rows(new_purchases)
  } else {
    tibble::tibble(
      ticket_id = character(0), group_id = character(0), candidate_id = character(0),
      rank = integer(0), probability = numeric(0), cost_cny = numeric(0),
      sp_product_est = numeric(0), ev_net_est = numeric(0), objective = character(0))
  }
  list(selection = selection,
       selected_ids = as.character(packages$group_id[selection$selected]),
       consumed = as.numeric(consumed),
       remaining = if (budget_is_null) NA_real_ else
         as.numeric(as.numeric(budget_cny) - consumed),
       purchased = purchased, new_purchases = purchases)
}

# --- local improvement -------------------------------------------------------

#' Whole-portfolio objective value
#'
#' Internal. The probability objective is the sum of the purchased tickets'
#' UNCONDITIONAL masses -- the expected number of winning tickets. It is explicitly
#' NOT a union / at-least-one probability.
#' @param purchases Selected purchase rows.
#' @param objective One of `"probability"` or `"ev"`.
#' @return A single numeric objective value; 0 when nothing was purchased.
#' @noRd
.parlay_role_objective <- function(purchases, objective) {
  if (!nrow(purchases)) return(0)
  if (identical(objective, "ev")) {
    if (anyNA(purchases$ev_net_est)) {
      stop("parlay_evaluate_portfolio: objective 'ev' requires a complete valid ",
           "pre-cutoff SP valuation; purchased tickets have no EV")
    }
    return(sum(as.numeric(purchases$ev_net_est)))
  }
  sum(as.numeric(purchases$probability))
}

#' Validate a full-portfolio leg assignment
#'
#' Internal. Applies the SAME arithmetic construction uses: per-fixture reuse over
#' every in-plan group, and pairwise overlap between every pair of groups,
#' plus a duplicate check inside each group and the plan width.
#' @param legs Candidate role legs tibble.
#' @param constraints List with `max_reuse` and `max_overlap`.
#' @param n_legs Plan width.
#' @return A list(valid, reason). `reason` is `""` when valid and otherwise one of
#'   `duplicate_fixture_in_group`, `fixture_reuse_cap_exceeded`,
#'   `group_overlap_cap_exceeded` or `group_width_exceeded`.
#' @noRd
.parlay_role_validate_assignment <- function(legs, constraints,
                                             n_legs) {
  max_reuse <- as.numeric(constraints$max_reuse)
  max_overlap <- as.numeric(constraints$max_overlap)
  sets <- split(as.character(legs$fixture_id), as.character(legs$group_slot))
  # A group that repeats a fixture is invalid regardless of the caps.
  for (set in sets) {
    if (anyDuplicated(set)) {
      return(list(valid = FALSE, reason = "duplicate_fixture_in_group"))
    }
  }
  groups <- unname(sets)
  # Reuse: a fixture may appear in at most max_reuse distinct groups.
  for (fixture_id in unique(unlist(sets))) {
    uses <- sum(vapply(groups, function(g) fixture_id %in% g, logical(1L)))
    if (uses > max_reuse) {
      return(list(valid = FALSE, reason = "fixture_reuse_cap_exceeded"))
    }
  }
  # Overlap: every PAIR of selected groups shares at most
  # max_overlap fixtures.
  for (i in seq_along(groups)) {
    for (j in seq_along(groups)) {
      if (i >= j) next
      if (length(intersect(groups[[i]], groups[[j]])) > max_overlap) {
        return(list(valid = FALSE, reason = "group_overlap_cap_exceeded"))
      }
    }
  }
  # A group must not exceed the plan width.
  if (any(lengths(sets) > n_legs)) {
    return(list(valid = FALSE, reason = "group_width_exceeded"))
  }
  list(valid = TRUE, reason = "")
}

#' Validate the bounded improvement policy
#'
#' Internal. Accepts exactly `max_passes`, `rank_window` and `max_evaluations`;
#' unknown fields or non-whole values are refused rather than silently defaulted.
#' @param policy Named list of the three whole positive counts.
#' @return The policy as a list of three integers.
#' @noRd
.parlay_role_validate_policy <- function(policy) {
  checkmate::assert_list(policy, names = "unique",
                         .var.name = "improvement_policy")
  allowed <- c("max_passes", "rank_window", "max_evaluations")
  unknown <- setdiff(names(policy), allowed)
  if (length(unknown)) {
    stop("parlay_evaluate_portfolio: unknown improvement_policy field(s) ",
         paste(unknown, collapse = ", "), "; allowed fields are ",
         paste(allowed, collapse = ", "))
  }
  missing <- setdiff(allowed, names(policy))
  if (length(missing)) {
    stop("parlay_evaluate_portfolio: improvement_policy is missing ",
         paste(missing, collapse = ", "))
  }
  checkmate::assert_count(policy$max_passes, positive = TRUE,
                          .var.name = "improvement_policy$max_passes")
  checkmate::assert_count(policy$max_evaluations, positive = TRUE,
                          .var.name = "improvement_policy$max_evaluations")
  checkmate::assert_count(policy$rank_window, positive = TRUE,
                          .var.name = "improvement_policy$rank_window")
  list(max_passes = as.integer(policy$max_passes),
       rank_window = as.integer(policy$rank_window),
       max_evaluations = as.integer(policy$max_evaluations))
}

#' Validate an optional CNY budget
#'
#' Internal. `NULL` means "unspecified" and is preserved: an unlimited decision is
#' represented by `NULL`, never by an infinite number. A supplied value must be a
#' single non-negative finite number; negative, `NA` and infinite values are refused.
#' @param value Candidate budget.
#' @param name Parameter name used in the error message.
#' @return The numeric scalar, or `NULL`.
#' @noRd
.parlay_role_validate_budget <- function(value, name) {
  if (is.null(value)) return(NULL)
  checkmate::assert_number(value, lower = 0, finite = TRUE, .var.name = name)
  checkmate::assert_true(!is.object(value) && is.null(dim(value)),
    .var.name = paste(name, "must be an unclassed numeric scalar"))
  as.numeric(value)
}

#' Validate the explicit selection constraints
#'
#' Internal. Accepts exactly `max_reuse` and `max_overlap`; unknown fields are refused.
#' @param constraints Named list with `max_reuse` and `max_overlap`.
#' @param n_legs Plan width the overlap cap may not exceed.
#' @return `TRUE` invisibly.
#' @noRd
.parlay_role_validate_constraints <- function(constraints, n_legs) {
  checkmate::assert_list(constraints, names = "unique", .var.name = "constraints")
  allowed <- c("max_reuse", "max_overlap")
  unknown <- setdiff(names(constraints), allowed)
  if (length(unknown)) {
    stop("parlay_evaluate_portfolio: unknown constraints field(s) ",
         paste(unknown, collapse = ", "), "; allowed fields are ",
         paste(allowed, collapse = ", "))
  }
  missing <- setdiff(allowed, names(constraints))
  if (length(missing)) {
    stop("parlay_evaluate_portfolio: constraints is missing ",
         paste(missing, collapse = ", "))
  }
  checkmate::assert_count(constraints$max_reuse, positive = TRUE,
                          .var.name = "constraints$max_reuse")
  checkmate::assert_count(constraints$max_overlap,
                          .var.name = "constraints$max_overlap")
  if (constraints$max_overlap > n_legs) {
    stop("parlay_evaluate_portfolio: constraints$max_overlap must not exceed ",
         "n_legs ", n_legs)
  }
  invisible(TRUE)
}

# --- metrics -----------------------------------------------------------------

#' One metric row for a stage
#'
#' Internal. Derived from the ACTUAL funded purchases of a result, never from the
#' intended plan.
#' @param purchases Purchased ticket rows (actual unique purchases).
#' @param stage Stage label.
#' @param objective One of `"probability"` or `"ev"`.
#' @param selected_groups Number of groups actually selected.
#' @param pool_groups Number of candidate groups in the pool.
#' @param budget_cny Total decision budget in CNY, or `NULL` for unlimited, in which
#'   case `unspent_cny` is `NA_real_` rather than an infinite balance.
#' @return A one-row tibble.
#' @noRd
.parlay_role_metric_row <- function(purchases, stage, objective, selected_groups,
                                    pool_groups, budget_cny) {
  tibble::tibble(
    stage = as.character(stage), objective = as.character(objective),
    purchased_tickets = as.integer(nrow(purchases)),
    cost_cny = as.numeric(sum(purchases$cost_cny)),
    expected_winning_tickets = as.numeric(sum(purchases$probability)),
    ev_net_cny = if (nrow(purchases) && all(is.finite(purchases$ev_net_est))) {
      as.numeric(sum(purchases$ev_net_est))
    } else {
      NA_real_
    },
    ev_available = nrow(purchases) > 0L && all(is.finite(purchases$ev_net_est)),
    unspent_cny = if (is.null(budget_cny)) NA_real_ else
      as.numeric(as.numeric(budget_cny) - sum(purchases$cost_cny)),
    complete_groups = as.integer(selected_groups),
    planned_groups = as.integer(pool_groups))
}

#' Per-group summary of the actual purchases
#'
#' Internal. Reports each selected group's actual tickets and cost, with its role
#' fixtures beside them.
#' @param purchases Purchased ticket rows.
#' @param portfolio Role candidate pool.
#' @param selected_ids Selected group ids.
#' @param group_budget_cny Per-group budget in CNY, or `NULL` for full support. With
#'   `NULL`, `unspent_cny` is `NA_real_`.
#' @return A tibble(group_slot, group_id, complete, tickets, cost_cny,
#'   expected_winning_tickets, ev_net_cny, ev_available, unspent_cny, role1_fixture,
#'   role2_fixture, role3_fixture); typed-empty when nothing was selected.
#' @noRd
.parlay_role_group_summary <- function(purchases, portfolio, selected_ids,
                                       group_budget_cny) {
  empty <- .parlay_role_eval_empty("group_summary")
  if (!length(selected_ids)) return(empty)
  legs <- portfolio$role_legs
  rows <- lapply(selected_ids, function(group_id) {
    x <- purchases[as.character(purchases$group_id) == group_id, , drop = FALSE]
    block <- legs[as.character(legs$group_id) == group_id, , drop = FALSE]
    slot <- portfolio$groups$group_slot[
      as.character(portfolio$groups$group_id) == group_id]
    role_fixture <- function(role) {
      value <- as.character(block$fixture_id[block$role == role])
      if (length(value)) paste(value, collapse = ", ") else NA_character_
    }
    tibble::tibble(
      group_slot = as.integer(slot[1]), group_id = group_id, complete = TRUE,
      tickets = as.integer(nrow(x)), cost_cny = as.numeric(sum(x$cost_cny)),
      expected_winning_tickets = as.numeric(sum(x$probability)),
      ev_net_cny = if (nrow(x) && all(is.finite(x$ev_net_est))) {
        as.numeric(sum(x$ev_net_est))
      } else {
        NA_real_
      },
      ev_available = nrow(x) > 0L && all(is.finite(x$ev_net_est)),
      unspent_cny = as.numeric(
        min(group_budget_cny %||% Inf, prod(lengths(block$allowed_outcomes)) *
          portfolio$settings$unit_cny) - sum(x$cost_cny)),
      role1_fixture = role_fixture(1L), role2_fixture = role_fixture(2L),
      role3_fixture = role_fixture(3L))
  })
  dplyr::bind_rows(rows)
}

#' Per-ticket table of the actual purchases
#'
#' Internal. One row per ACTUAL legal purchase with its rank in the group's support.
#' @param purchases Purchased ticket rows.
#' @param portfolio Role candidate pool.
#' @return A tibble(group_slot, group_id, ticket_id, rank, probability, cost_cny,
#'   sp_product_est, ev_net_est, ev_available, legal, objective_value); typed-empty
#'   when nothing was bought.
#' @noRd
.parlay_role_ticket_table <- function(purchases, portfolio) {
  empty <- .parlay_role_eval_empty("tickets")
  if (!nrow(purchases)) return(empty)
  rows <- lapply(seq_len(nrow(purchases)), function(i) {
    slot <- portfolio$groups$group_slot[
      as.character(portfolio$groups$group_id) == as.character(purchases$group_id[i])]
    tibble::tibble(
      group_slot = as.integer(slot[1]),
      group_id = as.character(purchases$group_id[i]),
      ticket_id = as.character(purchases$ticket_id[i]),
      rank = as.integer(purchases$rank[i]),
      probability = as.numeric(purchases$probability[i]),
      cost_cny = as.numeric(purchases$cost_cny[i]),
      sp_product_est = as.numeric(purchases$sp_product_est[i]),
      ev_net_est = as.numeric(purchases$ev_net_est[i]),
      ev_available = is.finite(purchases$ev_net_est[i]),
      legal = TRUE,
      objective_value = if (identical(purchases$objective[i], "ev")) {
        as.numeric(purchases$ev_net_est[i])
      } else {
        as.numeric(purchases$probability[i])
      })
  })
  dplyr::bind_rows(rows)
}

# --- improvement driver ------------------------------------------------------

#' Bounded deterministic whole-portfolio improvement
#'
#' Internal. The complete first-improvement local search used by
#' [parlay_evaluate_portfolio()]. Starting from the greedy selection, each pass
#' builds the deterministic candidate moves for the CURRENT best assignment and
#' accepts the FIRST move whose whole-portfolio objective beats the incumbent by
#' more than `1e-12`; the remaining moves of that pass are not examined. Every
#' candidate move is re-selected under exactly the same per-group depth, total
#' budget and reuse/overlap constraints as the greedy selection, so an accepted
#' move can never relax them. A pass with no accepted move stops the search, as
#' does exhausting `policy$max_evaluations`. With `improve = FALSE` the initial
#' state is returned untouched, with zero counters and a typed-empty `changes`
#' table.
#' @param portfolio Candidate pool from [parlay_construct_role_groups()]. Its
#'   `role_legs` are the starting assignment and are never mutated.
#' @param initial_purchases Actual unique purchases of the greedy selection.
#' @param initial_value Whole-portfolio objective value of `initial_purchases`.
#' @param initial_selected_ids Group ids selected by the greedy selection.
#' @param initial_selection Selection audit tibble of the greedy selection.
#' @param probabilities Authoritative probability tibble carried by `portfolio`.
#' @param prematch_sp Pre-cutoff SP tibble carried by `portfolio`.
#' @param cutoff Validated decision cutoff embedded in `portfolio`.
#' @param objective One of `"probability"` or `"ev"`.
#' @param group_budget_cny Per-group depth budget in CNY, or `NULL` for full
#'   legal support.
#' @param budget_cny Total decision budget in CNY, or `NULL` for unlimited.
#' @param constraints Validated list with `max_reuse` and `max_overlap`.
#' @param policy Validated improvement policy with `max_passes`, `rank_window`
#'   and `max_evaluations`.
#' @param improve Logical scalar; `FALSE` disables the search.
#' @return A named list:
#'   * `purchases` -- purchases of the best assignment found (the initial ones
#'     when nothing improved);
#'   * `value` -- the matching whole-portfolio objective value;
#'   * `selected_ids`, `selection` -- the best assignment's selection evidence;
#'   * `portfolio` -- the best role-legs portfolio;
#'   * `changes` -- one row per accepted move; typed-empty when none;
#'   * `evaluations` -- candidate moves attempted, including duplicate-fixture rejections;
#'   * `passes_run` -- passes started, `0L` when `improve = FALSE`.
#' @noRd
.parlay_role_improve_portfolio <- function(portfolio, initial_purchases,
                                           initial_value, initial_selected_ids,
                                           initial_selection, probabilities,
                                           prematch_sp, cutoff, objective,
                                           group_budget_cny, budget_cny, constraints,
                                           policy, improve) {
  best_purchases <- initial_purchases
  best_value <- initial_value
  best_selected_ids <- initial_selected_ids
  best_selection <- initial_selection
  best_portfolio <- portfolio
  changes <- .parlay_role_eval_empty("changes")
  evaluations <- 0L
  passes_run <- 0L

  if (isTRUE(improve)) {
    for (pass in seq_len(policy$max_passes)) {
      passes_run <- pass
      accepted_this_pass <- FALSE
      moves <- .parlay_role_candidate_moves(best_portfolio, best_portfolio$scores,
                                            policy$rank_window, best_selected_ids)
      for (candidate_move in moves) {
        if (evaluations >= policy$max_evaluations) break
        candidate_legs <- .parlay_role_apply_move(best_portfolio$role_legs, candidate_move)
        evaluations <- evaluations + 1L
        if (any(vapply(split(candidate_legs$fixture_id,candidate_legs$group_slot),
                       anyDuplicated, integer(1)) > 0L)) next
        candidate_legs <- .parlay_role_refresh_masks(candidate_legs, probabilities)
        candidate_portfolio <- .parlay_role_with_legs(best_portfolio, candidate_legs)
        cand_packages <- .parlay_role_packages(candidate_portfolio, probabilities,
                                               prematch_sp, cutoff, group_budget_cny,
                                               objective)
        # The FINAL selected state is what the constraints bind: `.parlay_role_select`
        # checks only the groups it accepts, never the overlapping candidate pool.
        cand_selected <- .parlay_role_select(cand_packages$packages,
                                             cand_packages$stack,
                                             portfolio$settings$unit_cny,
                                             budget_cny, constraints,
                                             cand_packages$fixture_sets)
        cand_purchases <- cand_selected$new_purchases
        cand_value <- .parlay_role_objective(cand_purchases, objective)
        if (!is.finite(cand_value)) next
        if (cand_value > best_value + 1e-12) {
          changes <- dplyr::bind_rows(changes, tibble::tibble(
            pass = as.integer(pass), move = candidate_move$move,
            group_slot_a = as.integer(candidate_move$group_slot_a),
            group_slot_b = as.integer(candidate_move$group_slot_b),
            fixture_a = as.character(candidate_move$fixture_a),
            fixture_b = as.character(candidate_move$fixture_b),
            round_a = as.integer(best_portfolio$role_legs$round[candidate_move$index_a]),
            round_b = as.integer(best_portfolio$role_legs$round[candidate_move$index_b]),
            old_fixture = as.character(best_portfolio$role_legs$fixture_id[candidate_move$index_a]),
            new_fixture = as.character(candidate_legs$fixture_id[candidate_move$index_a]),
            role = as.integer(candidate_move$role),
            objective_before = as.numeric(best_value),
            objective_after = as.numeric(cand_value),
            delta = as.numeric(cand_value - best_value), accepted = TRUE))
          best_purchases <- cand_purchases
          best_value <- cand_value
          best_selected_ids <- cand_selected$selected_ids
          best_selection <- cand_selected$selection
          best_portfolio <- candidate_portfolio
          accepted_this_pass <- TRUE
          break
        }
      }
      if (evaluations >= policy$max_evaluations || !accepted_this_pass) break
    }
  }
  return(list(purchases = best_purchases, value = as.numeric(best_value),
       selected_ids = best_selected_ids, selection = best_selection,
       portfolio = best_portfolio, changes = changes,
       evaluations = as.integer(evaluations), passes_run = as.integer(passes_run)))
}

# --- public entry point ------------------------------------------------------

#' Evaluate a role candidate pool under depth and budget, with bounded improvement
#'
#' Enumerates each complete candidate's physical ticket package at its single-group
#' depth, then greedily selects WHOLE packages under the total budget and the
#' reuse/overlap constraints -- checking them against the already-selected groups
#' only. The decision cutoff travels WITH the pool in `portfolio$cutoff`; there is
#' no external cutoff argument. The carried cutoff is re-validated and its hash must
#' equal the `cutoff_hash` recorded at construction, and the immutable probability
#' and pre-cutoff SP tables must match the hashes the pool recorded. The probability
#' objective is the sum of the purchased tickets' unconditional masses (the expected
#' number of winning tickets, NOT a union probability). A bounded deterministic local
#' search of fixture reassignments may improve the WHOLE-portfolio objective.
#'
#' @param portfolio Candidate pool from [parlay_construct_role_groups()]. It carries
#'   the explicitly constructed cutoff, the frozen probabilities and the pre-cutoff
#'   SP the evaluation consumes; no external cutoff or price table is accepted.
#' @param group_budget_cny CNY depth budget for ONE group, or `NULL` for the group's
#'   full legal support space. Each candidate buys top
#'   `floor(min(group_budget_cny, full_support_cost) / unit_cny)` legal tickets. A
#'   zero or sub-unit budget buys zero tickets rather than raising an error.
#' @param budget_cny CNY ceiling for the WHOLE decision, or `NULL` for unlimited. A
#'   package is skipped whole when it no longer fits; the balance is kept. With
#'   `NULL`, greedy selection runs without a cap and `unspent_cny` is `NA_real_`
#'   rather than an infinite balance. `0` yields an empty selection.
#' @param constraints Explicit list with `max_reuse` and `max_overlap`, checked only
#'   against the groups already selected.
#' @param improve Logical scalar. `TRUE` runs the bounded local search; `FALSE`
#'   returns the unimproved evaluation with a typed-empty `changes` table.
#' @param objective One of `"probability"` or `"ev"`.
#' @param improvement_policy Explicit list with `max_passes`, `rank_window` and
#'   `max_evaluations`.
#' @return A named list with the same fields for both `improve` settings:
#'   * `initial`, `final` -- normal result objects of the shape
#'     [parlay_build_plan()] produces, consumable by [parlay_betting_sheet()];
#'   * `metrics` -- tibble(stage, objective, purchased_tickets, cost_cny,
#'     expected_winning_tickets, ev_net_cny, ev_available, unspent_cny,
#'     complete_groups, planned_groups);
#'   * `group_summary` -- the selected groups and their actual purchases;
#'   * `tickets` -- the actual legal purchases;
#'   * `selection` -- tibble(group_slot, group_id, rank, package_units,
#'     package_cost_cny, package_score, selected, reason) for EVERY candidate in the
#'     deterministic inclusion order, so a rejection is auditable;
#'   * `changes` -- accepted improvement moves; TYPED-EMPTY when `improve = FALSE`;
#'   * `diagnostics`, `receipt`, `cutoff`.
#' @details No disk, network, fitting or betting side effects occur and the
#'   `portfolio` input is never mutated.
#' @examples
#' cutoff <- list(issue_id = "26098",
#'                cutoff_utc = as.POSIXct("2026-09-26 11:52:04", tz = "UTC"))
#' probabilities <- tibble::tibble(
#'   fixture_id = rep(c("A", "B", "C", "D"), each = 3),
#'   outcome = rep(c("W", "D", "L"), 4),
#'   probability = c(0.5, 0.49, 0.01, 0.7, 0.28, 0.02,
#'                   0.85, 0.1, 0.05, 0.8, 0.15, 0.05))
#' settings <- parlay_settings()
#' settings$n_legs <- 2L
#' settings$unit_cny <- 2
#' pool <- parlay_construct_role_groups(
#'   parlay_role_scores(probabilities, cutoff), cutoff, settings,
#'   pattern = c(2L, 1L), n_candidates = 2L, probabilities = probabilities)
#' evaluation <- parlay_evaluate_portfolio(
#'   pool,
#'   group_budget_cny = 4, budget_cny = 8,
#'   constraints = list(max_reuse = 1L, max_overlap = 0L), improve = FALSE)
#' evaluation$selection
#' @export
parlay_evaluate_portfolio <- function(portfolio, group_budget_cny = NULL,
                                      budget_cny = NULL, constraints, improve = TRUE,
                                      objective = "probability",
                                      improvement_policy = list(max_passes = 2L,
                                                                rank_window = 3L,
                                                                max_evaluations = 60L)) {
  if (!is.list(portfolio) || is.null(portfolio$role_legs) ||
      is.null(portfolio$settings)) {
    stop("parlay_evaluate_portfolio: portfolio must be the result of ",
         "parlay_construct_role_groups()")
  }
  # The decision cutoff travels WITH the pool and is validated before any other
  # carried state -- and before the unfundable early return below -- so a missing,
  # malformed, hash-less or retimed pool can never be evaluated, not even as an
  # empty result. `portfolio[["cutoff"]]` reads the exact bound field.
  cutoff <- portfolio[["cutoff"]]
  match_require_cutoff(cutoff)
  if (is.null(portfolio[["cutoff_hash"]])) {
    stop("parlay_evaluate_portfolio: the portfolio has no recorded cutoff_hash; ",
         "it was not built by parlay_construct_role_groups()")
  }
  if (!identical(portfolio[["cutoff_hash"]], rlang::hash(list(as.character(cutoff$issue_id), as.numeric(cutoff$cutoff_utc))))) {
    stop("parlay_evaluate_portfolio: the embedded cutoff does not match the ",
         "construction cutoff recorded in the portfolio")
  }
  # The immutable inputs travel WITH the pool: there is no external price table and
  # no compatibility wrapper. Both hashes are re-checked against the carried tables.
  probabilities <- match_validate_table(portfolio[["probabilities"]], "probabilities")
  prematch_sp <- match_validate_table(portfolio[["prematch_sp"]], "prematch_sp")
  if (!identical(portfolio$probability_hash, rlang::hash(probabilities))) {
    stop("parlay_evaluate_portfolio: the portfolio probabilities do not match ",
         "the hash it recorded")
  }
  if (!identical(portfolio[["prematch_sp_hash"]], rlang::hash(prematch_sp))) {
    stop("parlay_evaluate_portfolio: the portfolio prematch_sp does not match ",
         "the hash it recorded")
  }
  checkmate::assert_flag(improve, .var.name = "improve")
  checkmate::assert_choice(objective, c("probability", "ev"),
                           .var.name = "objective")
  parlay_validate_settings(portfolio$settings)
  n_legs <- as.integer(portfolio$settings$n_legs)
  .parlay_role_validate_constraints(constraints, n_legs)
  .parlay_role_validate_scores(portfolio$scores, probabilities)
  group_budget_cny <- .parlay_role_validate_budget(group_budget_cny,
                                                   "group_budget_cny")
  budget_cny <- .parlay_role_validate_budget(budget_cny, "budget_cny")
  policy <- .parlay_role_validate_policy(improvement_policy)
  demand <- .parlay_role_validate_pattern(portfolio$pattern, n_legs)
  legs <- portfolio$role_legs
  checkmate::assert_integerish(legs$round, lower = 1, upper = length(demand),
                               any.missing = FALSE)
  if (anyDuplicated(paste(legs$group_slot, legs$round)) ||
      anyNA(legs$role) || any(legs$role != demand[legs$round])) {
    stop("portfolio leg roles and rounds must match frozen pattern")
  }
  expected_legs <- .parlay_role_refresh_masks(portfolio$role_legs, probabilities)
  if (!identical(portfolio$role_legs$allowed_outcomes, expected_legs$allowed_outcomes) ||
      !identical(portfolio$role_legs$retained_probability,
                 expected_legs$retained_probability)) {
    stop("portfolio role masks disagree with probabilities")
  }

  packages <- .parlay_role_packages(portfolio, probabilities, prematch_sp, cutoff,
                                    group_budget_cny, objective)
  selected <- .parlay_role_select(packages$packages, packages$stack,
                                  portfolio$settings$unit_cny, budget_cny,
                                  constraints, packages$fixture_sets)
  receipt <- list(
    cutoff = cutoff, issue_id = as.character(cutoff$issue_id),
    probability_hash = rlang::hash(probabilities),
    portfolio_hash = rlang::hash(portfolio), code_hash = .parlay_role_code_hash(),
    cutoff_hash = rlang::hash(list(as.character(cutoff$issue_id), as.numeric(cutoff$cutoff_utc))),
    settings_hash = rlang::hash(portfolio$settings),
    prematch_sp_hash = rlang::hash(prematch_sp),
    group_budget_cny = group_budget_cny,
    budget_cny = budget_cny,
    constraints = constraints,
    improve = improve, improvement_policy = policy,
    objectives = as.character(objective))
  selected_groups <- portfolio$groups[
    as.character(portfolio$groups$group_id) %in% selected$selected_ids, ,
    drop = FALSE]

  if (!nrow(selected_groups) || nrow(packages$packages) == 0L) {
    return(.parlay_role_evaluation(
      portfolio, probabilities, packages, selected, selected_groups, prematch_sp,
      cutoff, objective, receipt, policy, improve))
  }

  # Actual purchases are the physical tickets each selected package NEWLY buys,
  # already de-duplicated across the groups selected here and charged once by
  # `.parlay_role_select`.
  purchases <- selected$new_purchases
  initial_purchases <- purchases
  initial_value <- .parlay_role_objective(initial_purchases, objective)
  # The ENTIRE first-improvement loop lives in the internal driver so the search and
  # its counters can be tested directly without rebuilding the evaluation wrapper.
  improvement <- .parlay_role_improve_portfolio(
    portfolio, initial_purchases, initial_value, selected$selected_ids,
    selected$selection, probabilities, prematch_sp, cutoff, objective,
    group_budget_cny, budget_cny, constraints, policy, improve)
  best_purchases <- improvement$purchases
  best_value <- improvement$value
  best_selected_ids <- improvement$selected_ids
  best_selection <- improvement$selection
  best_portfolio <- improvement$portfolio
  changes <- improvement$changes
  evaluations <- improvement$evaluations
  passes_run <- improvement$passes_run
  final_value <- best_value
  metrics <- dplyr::bind_rows(
    .parlay_role_metric_row(initial_purchases, "initial", objective,
                            length(selected$selected_ids), nrow(packages$packages),
                            budget_cny),
    .parlay_role_metric_row(best_purchases, "final", objective,
                            length(best_selected_ids), nrow(packages$packages),
                            budget_cny))
  diagnostics <- list(
    objective = as.character(objective),
    objective_basis = if (identical(objective, "ev")) {
      "sum of expected ticket payout minus actual cost"
    } else {
      "purchased unconditional masses (expected winning tickets), not a union probability"
    },
    unspent_cny = if (is.null(budget_cny)) NA_real_ else
      as.numeric(as.numeric(budget_cny) - sum(best_purchases$cost_cny)),
    complete_groups = as.integer(length(best_selected_ids)),
    planned_groups = as.integer(nrow(packages$packages)),
    budget_cny = budget_cny,
    group_budget_cny = group_budget_cny,
    max_passes = as.integer(policy$max_passes),
    rank_window = as.integer(policy$rank_window),
    max_evaluations = as.integer(policy$max_evaluations),
    evaluations = as.integer(evaluations), passes_run = as.integer(passes_run),
    accepted_moves = as.integer(nrow(changes)),
    improvement_enabled = isTRUE(improve),
    objective_initial = as.numeric(initial_value),
    objective_final = as.numeric(final_value))
  list(initial = .parlay_role_result(portfolio, initial_purchases, prematch_sp,
                                     cutoff, objective, budget_cny, constraints),
       final = .parlay_role_result(best_portfolio, best_purchases, prematch_sp, cutoff,
                                   objective, budget_cny, constraints),
       metrics = metrics,
       group_summary = .parlay_role_group_summary(best_purchases, best_portfolio,
                                                  best_selected_ids, group_budget_cny),
       tickets = .parlay_role_ticket_table(best_purchases, best_portfolio),
       selection = best_selection, changes = changes,
       diagnostics = diagnostics, receipt = receipt, cutoff = cutoff)
}

#' Typed-empty evaluation for an unfundable pool
#'
#' Internal. Same field names as a populated evaluation.
#' @param portfolio Role candidate pool.
#' @param probabilities Authoritative probability tibble.
#' @param packages Package evidence from [.parlay_role_packages()].
#' @param selected Selection evidence from [.parlay_role_select()].
#' @param selected_groups Selected group rows (possibly none).
#' @param prematch_sp Pre-cutoff SP tibble used for valuation.
#' @param cutoff Decision cutoff.
#' @param objective One of `"probability"` or `"ev"`.
#' @param receipt Provenance receipt.
#' @param policy Validated improvement policy.
#' @param improve The improvement switch requested.
#' @return A named list with initial, final, metrics, group_summary, tickets,
#'   selection, changes, diagnostics, receipt and cutoff.
#' @noRd
.parlay_role_evaluation <- function(portfolio, probabilities, packages, selected,
                                    selected_groups, prematch_sp, cutoff, objective,
                                    receipt, policy, improve) {
  budget_cny <- receipt$budget_cny
  empty_purchases <- tibble::tibble(
    ticket_id = character(0), group_id = character(0), candidate_id = character(0),
    rank = integer(0), probability = numeric(0), cost_cny = numeric(0),
    sp_product_est = numeric(0), ev_net_est = numeric(0), objective = character(0))
  metrics <- dplyr::bind_rows(
    .parlay_role_metric_row(empty_purchases, "initial", objective, 0L,
                            nrow(packages$packages), budget_cny),
    .parlay_role_metric_row(empty_purchases, "final", objective, 0L,
                            nrow(packages$packages), budget_cny))
  selection <- if (nrow(packages$packages)) selected$selection else
    .parlay_role_typed_empty("selection")
  list(initial = .parlay_role_empty_result(portfolio, prematch_sp,cutoff,objective,
                                           budget_cny,receipt$constraints),
       final = .parlay_role_empty_result(portfolio, prematch_sp,cutoff,objective,
                                         budget_cny,receipt$constraints),
       metrics = metrics,
       group_summary = .parlay_role_eval_empty("group_summary"),
       tickets = .parlay_role_eval_empty("tickets"),
       selection = selection, changes = .parlay_role_eval_empty("changes"),
       diagnostics = list(
         objective = as.character(objective),
         objective_basis = if (identical(objective, "ev")) {
           "sum of expected ticket payout minus actual cost"
         } else {
           "purchased unconditional masses (expected winning tickets), not a union probability"
         },
         unspent_cny = if (is.null(budget_cny)) NA_real_ else as.numeric(budget_cny),
         complete_groups = 0L,
         planned_groups = as.integer(nrow(packages$packages)),
         budget_cny = budget_cny,
         group_budget_cny = receipt$group_budget_cny,
         max_passes = as.integer(policy$max_passes),
         rank_window = as.integer(policy$rank_window),
         max_evaluations = as.integer(policy$max_evaluations),
         evaluations = 0L, passes_run = 0L, accepted_moves = 0L,
         improvement_enabled = isTRUE(improve),
         objective_initial = 0, objective_final = 0,
         reason = "no candidate group could be selected within the budget"),
       receipt = receipt, cutoff = cutoff)
}

# --- internal helpers used by the entry point --------------------------------


#' Build a normal result object from selected purchases
#'
#' Internal. Reuses the shared freezing helper so the result is consumable by
#' [parlay_betting_sheet()].
#' @param portfolio Role candidate pool.
#' @param purchases Actual unique purchases.
#' @param prematch_sp Pre-cutoff SP tibble used for valuation.
#' @param cutoff Decision cutoff.
#' @param objective One of `"probability"` or `"ev"`.
#' @param budget_cny Total explicit decision budget in CNY, or `NULL` for unlimited.
#' @param constraints Final reuse and overlap limits.
#' @return A normal result list.
#' @noRd
.parlay_role_result <- function(portfolio, purchases, prematch_sp, cutoff, objective,
                                budget_cny, constraints) {
  settings <- portfolio$settings
  # A NULL budget leaves the frozen settings cap untouched; the unlimited decision
  # is expressed only through the NULL spend limit, never an infinite constant.
  if (!is.null(budget_cny)) settings$issue_budget_cny <- budget_cny
  label <- paste0("p", paste(portfolio$pattern, collapse = ""))
  selected_ids <- unique(as.character(purchases$group_id))
  selected_groups <- portfolio$groups[
    as.character(portfolio$groups$group_id) %in% selected_ids, , drop = FALSE]
  selected_legs <- portfolio$role_legs[portfolio$role_legs$group_id %in% selected_ids, , drop=FALSE]
  verdict <- .parlay_role_validate_assignment(selected_legs, constraints,
                                              settings$n_legs)
  if (!verdict$valid) stop("selected portfolio violates ",verdict$reason)
  group_legs <- .parlay_role_group_legs(portfolio, selected_groups)
  supports <- if (nrow(group_legs)) .parlay_role_supports(portfolio, group_legs, label)
    else match_typed_empty("supports")
  tickets <- parlay_enumerate_tickets(group_legs, portfolio$probabilities, cutoff,
                                      supports,
                                      n_legs = as.integer(settings$n_legs))
  valued <- parlay_value_tickets(tickets$tickets, tickets$ticket_legs, prematch_sp,
                                 cutoff, settings$sp_threshold, settings$sp_replacement,
                                 settings$unit_cny, settings$payout_factor)
  ranked <- parlay_rank_tickets(valued, tickets$candidate_tickets, cutoff,
                                "probability_desc")
  # Physical identity may occur in several candidates; attach the actual owning
  # candidate before matching purchases so shared tickets have one funded row.
  candidate_groups <- tibble::tibble(candidate_id=paste0(selected_groups$group_id,"|",label),
                                     group_id=selected_groups$group_id)
  ranked$group_id <- candidate_groups$group_id[match(ranked$candidate_id,candidate_groups$candidate_id)]
  index <- match(paste(purchases$candidate_id,purchases$ticket_id),
                 paste(ranked$candidate_id,ranked$ticket_id))
  if (anyNA(index)) stop("selected purchases are absent from the final candidate support")
  funded <- ranked[index, , drop=FALSE]
  purchase_rows <- if (nrow(purchases)) {
    tibble::tibble(issue_id = as.character(cutoff$issue_id),
                   ticket_id = as.character(purchases$ticket_id),
                   epoch_at = cutoff$cutoff_utc,
                   group_id = as.character(purchases$group_id),
                   candidate_id = as.character(purchases$candidate_id),
                   stake_cny = as.numeric(purchases$cost_cny))
  } else {
    match_typed_empty("purchases")
  }
  new_sets <- stats::setNames(lapply(selected_ids, function(group_id) {
    .parlay_role_fixture_set(portfolio$role_legs, group_id)
  }), selected_ids)
  # History is THIS decision's ledger only: no prior purchases are consulted or
  # accumulated, and no historical spending reduces the explicit budget.
  history <- list(purchases = purchase_rows, fixture_sets = new_sets)
  config <- parlay_strategy_config(
    settings, name = "role-round-robin",
    patterns = stats::setNames(list(as.integer(portfolio$pattern)), label),
    objective = objective, spend_limit_cny = budget_cny,
    max_reuse = constraints$max_reuse, max_overlap = constraints$max_overlap)
  plan <- .FreezeParlayPlan(cutoff$issue_id, cutoff$cutoff_utc, group_legs,
                            list(supports = supports), tickets, valued, funded,
                            purchase_rows, settings,
                            list(allocation = "role-round-robin-top-probability",
                                 objective = objective, budget_cny = budget_cny,
                                 budget_unlimited = is.null(budget_cny)))
  result <- list(config = config, cutoff = cutoff, constants = settings,
                 built = list(groups = list(group_legs = group_legs),
                              structure = list(supports = supports),
                              tickets = tickets, valued = valued),
                 probabilities = portfolio$probabilities, prematch_sp = prematch_sp,
                 ranked = ranked,
                 funded = list(purchases = purchase_rows, funded = funded,
                               fixture_sets = new_sets,
                               diagnostics = list(
                                 units_bought = as.integer(nrow(purchase_rows)),
                                 cost_cny = as.numeric(sum(purchase_rows$stake_cny))),
                               history = history),
                 plan = plan,
                 history = history,
                 budget_state = NULL,
                 frontier = list(group_legs = group_legs, supports = supports,
                                 ranked = ranked,
                                 candidate_tickets = tickets$candidate_tickets,
                                 ticket_legs = tickets$ticket_legs,
                                 tickets = tickets$tickets),
                 provenance = list(mode = "role_round_robin_proposal_not_actual_bet",
                                   cutoff_hash = rlang::hash(list(as.character(cutoff$issue_id), as.numeric(cutoff$cutoff_utc))),
                                   objective = objective,
                                   probability_hash = portfolio$probability_hash,
                                   prematch_sp_hash = portfolio[["prematch_sp_hash"]],
                                   budget_cny = budget_cny,
                                   budget_unlimited = is.null(budget_cny)))
  result$summary <- parlay_plan_summary(result)
  result
}

#' Fixture set of a candidate group id
#'
#' Internal. Reads the authoritative legs table rather than parsing the group id.
#' @param legs Role legs tibble.
#' @param group_id Candidate group id.
#' @return Sorted character vector of the group's fixtures.
#' @noRd
.parlay_role_fixture_set <- function(legs, group_id) {
  sort(unique(as.character(legs$fixture_id[as.character(legs$group_id) == group_id])))
}

#' Deterministic candidate moves for the local search
#'
#' Internal. Both families draw from the ORIGINAL full role pool, so a fixture that
#' construction never selected can still enter the plan.
#'   * `role_neighbor`: within one group slot and role, replace the fixture by a ranked
#'     neighbour of the CURRENT fixture at that role, within `rank_window`;
#'   * `group_exchange`: swap fixtures between two different groups; each position retains its role.
#' @param portfolio Role portfolio from [parlay_construct_role_groups()].
#' @param role_scores Validated score table the rankings are read from.
#' @param rank_window Whole number of ranked neighbours to consider on each side.
#' @param selected_ids Optional selected group ids; NULL considers all complete groups.
#' @return A list of move descriptors, each with move, index_a, index_b, fixture_a,
#'   fixture_b, role, group_slot_a and group_slot_b.
#' @noRd
.parlay_role_candidate_moves <- function(portfolio, role_scores, rank_window, selected_ids = NULL) {
  legs <- portfolio$role_legs
  complete_groups <- portfolio$groups[portfolio$groups$complete, , drop = FALSE]
  if (!is.null(selected_ids)) complete_groups <- complete_groups[
    complete_groups$group_id %in% selected_ids, , drop = FALSE]
  moves <- list()
  if (!nrow(legs) || !nrow(complete_groups)) return(moves)
  slots <- as.integer(complete_groups$group_slot)
  # Ranked neighbours are looked up in the ORIGINAL score table, per role.
  by_role <- lapply(1:3, function(role) {
    block <- role_scores[role_scores$role == role, , drop = FALSE]
    block[order(block$rank), , drop = FALSE]
  })
  for (i in which(legs$group_slot %in% slots)) {
    slot <- as.integer(legs$group_slot[i])
    role <- as.integer(legs$role[i])
    current <- as.character(legs$fixture_id[i])
    pool <- by_role[[role]]
    position <- match(current, as.character(pool$fixture_id))
    if (is.na(position)) next
    lo <- max(1L, position - rank_window)
    hi <- min(nrow(pool), position + rank_window)
    for (k in seq(lo, hi)) {
      alternative <- as.character(pool$fixture_id[k])
      if (identical(alternative, current)) next
      moves[[length(moves) + 1L]] <- list(
        move = "role_neighbor", index_a = i, index_b = NA_integer_,
        fixture_a = alternative, fixture_b = NA_character_, role = role,
        group_slot_a = slot, group_slot_b = slot)
    }
  }
  # All cross-group leg pairs, including different roles. Destination roles stay fixed.
  indices <- which(legs$group_slot %in% slots)
  if (length(indices) >= 2L) for (a in seq_len(length(indices)-1L)) {
    for (b in (a+1L):length(indices)) {
      i <- indices[a]; j <- indices[b]
      if (legs$group_slot[i] == legs$group_slot[j] || legs$fixture_id[i] == legs$fixture_id[j]) next
      moves[[length(moves)+1L]] <- list(move="group_exchange",index_a=i,index_b=j,
        fixture_a=legs$fixture_id[i],fixture_b=legs$fixture_id[j],role=legs$role[i],
        group_slot_a=legs$group_slot[i],group_slot_b=legs$group_slot[j])
    }
  }
  moves
}
#' Apply one move to a copy of the role legs
#'
#' Internal. The ROLE stays in its group slot; only the fixture under it changes.
#' @param legs Current role legs tibble.
#' @param move Move descriptor from [.parlay_role_candidate_moves()].
#' @return A new role legs tibble with the move applied.
#' @noRd
.parlay_role_apply_move <- function(legs, move) {
  out <- legs
  if (identical(move$move, "role_neighbor")) {
    out$fixture_id[move$index_a] <- move$fixture_a
  } else {
    out$fixture_id[move$index_a] <- move$fixture_b
    out$fixture_id[move$index_b] <- move$fixture_a
  }
  out
}
#' Materialize a candidate move as a portfolio
#'
#' Internal. Replaces the role legs and re-derives the canonical group ids and
#' completeness. The roles, rounds, group slots and budgets never change; only the
#' fixture under a role does.
#' @param portfolio Role portfolio from [parlay_construct_role_groups()].
#' @param legs Replacement role legs tibble.
#' @return A portfolio list with updated `role_legs`, `groups$group_id` and
#'   `groups$complete`.
#' @noRd
.parlay_role_with_legs <- function(portfolio, legs) {
  out <- portfolio
  out$role_legs <- legs
  # Re-derive the canonical group ids, because changing a fixture changes the set and
  # therefore the identity of the group.
  ids <- stats::setNames(vapply(split(as.character(legs$fixture_id),
                                      as.character(legs$group_slot)),
                                .parlay_role_group_id, character(1)),
                         names(split(as.character(legs$fixture_id),
                                     as.character(legs$group_slot))))
  ids <- stats::setNames(paste0(ids, "@", as.numeric(portfolio$cutoff$cutoff_utc), ":", names(ids)), names(ids))
  out$role_legs$group_id <- unname(ids[as.character(out$role_legs$group_slot)])
  out$groups$group_id <- unname(ids[as.character(out$groups$group_slot)])
  # Completeness is a property of the legs: a group is complete when it holds one leg
  # per round of the plan, i.e. n_legs legs, all with distinct rounds.
  target <- as.integer(portfolio$settings$n_legs)
  out$groups$complete <- vapply(seq_len(nrow(out$groups)), function(i) {
    block <- out$role_legs[as.character(out$role_legs$group_slot) ==
                             as.character(out$groups$group_slot[i]), , drop = FALSE]
    nrow(block) == target && !anyDuplicated(block$round)
  }, logical(1))
  # Sort legs back into canonical (group_slot, round) order so downstream hashing is
  # order-stable.
  out$role_legs <- out$role_legs[order(out$role_legs$group_slot,
                                       out$role_legs$round), , drop = FALSE]
  out
}
#' Recompute each leg's mask under its frozen role
#'
#' Internal. The role is never re-derived: it comes from the leg's own `role` column.
#' @param legs Role legs tibble.
#' @param probabilities Authoritative probability tibble.
#' @return A copy of `legs` whose masks match the frozen role.
#' @noRd
.parlay_role_refresh_masks <- function(legs, probabilities) {
  wide <- parlay_probability_wide(probabilities)
  out <- legs
  for (i in seq_len(nrow(out))) {
    role <- as.integer(out$role[i])
    fixture_id <- as.character(out$fixture_id[i])
    triple <- as.numeric(wide[wide$fixture_id == fixture_id, match_outcomes()])
    definition <- .parlay_role_definition(triple, role)
    out$allowed_outcomes[[i]] <- definition$allowed
    out$retained_probability[i] <- as.numeric(definition$retained)
  }
  out
}
