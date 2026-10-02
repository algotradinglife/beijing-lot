# Ranked role round-robin portfolio evaluation (#537 successor).
#
# This is the SUCCESSOR to the obsolete score-table evaluator. It consumes the
# ranked candidate pool produced by [parlay_construct_role_groups()] over the
# ranked direction table of [rank_outcome_selections()], and it never re-derives an
# "old top2" assignment, a pattern role, or an arbitrary caller-supplied leg.
#
# The decision is a bounded, deterministic, single-pass funding walk:
#   1. every COMPLETE group is enumerated inside its own authoritative support mask
#      through the mature [parlay_enumerate_tickets()], [parlay_value_tickets()] and
#      [parlay_rank_tickets()] APIs, ranked by probability descending with a
#      canonical ticket-id tie;
#   2. the group's NOMINAL priority is the probability mass of its legal top-N
#      tickets for its ACTUAL group cap, and the walk visits groups in that
#      descending order with a stable group-id tie;
#   3. at admission a group is checked against the ALREADY-SELECTED groups under the
#      explicit reuse/overlap policies; a refused group consumes no constraint and
#      no cash, and the walk continues. Reuse counts EVERY actual fixture with no
#      exemption; pairwise overlap exempts a fixture that is a role-3 leg in BOTH
#      groups and counts every other shared fixture;
#   4. an admitted group buys its legal tickets in rank order, SKIPPING physical
#      tickets already bought anywhere in this decision, and continues DOWN the rank
#      until the wanted units, the remaining total budget or the legal space is
#      exhausted;
#   5. actual coverage is the probability that the ACTUAL owned new physical tickets
#      cover the group, recomputed after de-duplication and partial funding.
#
# The group order is the initial nominal order and never re-sorted dynamically.
# Money is charged once per physical ticket. No EV parameter is selected or learned
# and the default metric is coverage.

# --- policy validation -------------------------------------------------------

#' Validate the reuse policy
#'
#' Internal. `reuse_policy` is a named list with exactly `max_reuse`: a single
#' positive whole number, or `NULL` for unlimited reuse. There is no role
#' exemption: the policy governs every actual fixture in every actual group.
#' @param reuse_policy Named list with `max_reuse`.
#' @return A list with `max_reuse` as an integer or `NULL`.
#' @noRd
.parlay_ranked_validate_reuse_policy <- function(reuse_policy) {
  .parlay_ranked_validate_limit_policy(
    reuse_policy, "reuse_policy", "max_reuse", positive = TRUE)
}

#' Validate the overlap policy
#'
#' Internal. `overlap_policy` is a named list with exactly `max_overlap`: a single
#' non-negative whole number, or `NULL` for unlimited pairwise overlap. A fixture
#' that is a role-3 leg in BOTH compared groups is exempt and does not count toward
#' the limit; every other shared fixture counts.
#' @param overlap_policy Named list with `max_overlap`.
#' @return A list with `max_overlap` as an integer or `NULL`.
#' @noRd
.parlay_ranked_validate_overlap_policy <- function(overlap_policy) {
  .parlay_ranked_validate_limit_policy(
    overlap_policy, "overlap_policy", "max_overlap", positive = FALSE)
}

#' Validate one limit policy
#'
#' Internal. The policy must be a NAMED list with the single allowed field, whose
#' value is `NULL` (unlimited) or a bounded whole number. Unknown, duplicate or
#' missing names are refused rather than silently ignored.
#' @param policy Candidate policy list.
#' @param name Parameter name used in error messages.
#' @param field The single allowed field name.
#' @param positive `TRUE` when the limit must be at least 1 (reuse); `FALSE` when
#'   zero is allowed (overlap).
#' @return A one-field named list with the value as an integer or `NULL`.
#' @noRd
.parlay_ranked_validate_limit_policy <- function(policy, name, field,
                                                 positive) {
  if (!is.list(policy) || is.null(names(policy)) || any(!nzchar(names(policy)))) {
    stop("parlay_evaluate_portfolio: ", name, " must be a named list with the ",
         "single field '", field, "'")
  }
  if (anyDuplicated(names(policy))) {
    stop("parlay_evaluate_portfolio: ", name, " has duplicate field names")
  }
  unknown <- setdiff(names(policy), field)
  if (length(unknown)) {
    stop("parlay_evaluate_portfolio: unknown ", name, " field(s) ",
         paste(unknown, collapse = ", "), "; allowed field is '", field, "'")
  }
  if (!field %in% names(policy)) {
    stop("parlay_evaluate_portfolio: ", name, " is missing '", field, "'")
  }
  value <- policy[[field]]
  if (is.null(value)) return(stats::setNames(list(NULL), field))
  lower <- if (positive) 1 else 0
  if (!is.numeric(value) || is.object(value) || !is.null(dim(value)) ||
      length(value) != 1L || is.na(value) ||
      !is.finite(value) || value != trunc(value) || value < lower ||
      value > .Machine$integer.max) {
    stop("parlay_evaluate_portfolio: ", name, "$", field, " must be NULL or a ",
         if (positive) "positive whole number" else "non-negative whole number")
  }
  stats::setNames(list(as.integer(value)), field)
}

# --- pool validation ---------------------------------------------------------

#' Validate the ranked candidate pool
#'
#' Internal. Re-verifies everything the successor evaluator trusts: the embedded
#' cutoff, the cutoff hash, the ranked-selection receipt (which re-ranks the
#' carried `input_snapshot` and proves the ranks, masks and probabilities were not
#' tampered), the probability and pre-match SP hashes, the pool's own recorded
#' hashes, and then the FROZEN legs, masks, group patterns and substitutions.
#'
#' The evaluator never re-derives an assignment from a "top2" rule and never trusts
#' an arbitrary caller-supplied leg: the actual roles, rounds, fixtures and allowed
#' masks must agree with the pool's own `pattern`, `group_patterns` and
#' `substitutions` records, and the masks must be exactly the retained directions
#' of the ranked selections they were built from.
#' @param portfolio Pool from [parlay_construct_role_groups()].
#' @return A named list with the validated `cutoff`, `cutoff_hash`,
#'   `ranked_selections`, `probabilities`, `prematch_sp`, `settings`, `pattern`,
#'   `n_legs` and the frozen `legs`.
#' @noRd
.parlay_ranked_validate_pool <- function(portfolio) {
  if (!is.list(portfolio) || is.null(portfolio$role_legs) ||
      is.null(portfolio$settings) || is.null(portfolio$group_patterns) ||
      is.null(portfolio$ranked_selections)) {
    stop("parlay_evaluate_portfolio: portfolio must be the result of ",
         "parlay_construct_role_groups() over a ranked selection table")
  }
  cutoff <- portfolio[["cutoff"]]
  match_require_cutoff(cutoff)
  cutoff_hash <- .rank_outcome_cutoff_hash(cutoff)
  if (is.null(portfolio[["cutoff_hash"]]) ||
      !identical(portfolio[["cutoff_hash"]], cutoff_hash)) {
    stop("parlay_evaluate_portfolio: the embedded cutoff does not match the ",
         "construction cutoff recorded in the portfolio")
  }

  if (!identical(portfolio[["construction_code_hash"]],
      .rank_outcome_code_hash(roots = "parlay_construct_role_groups"))) {
    stop("parlay_evaluate_portfolio: construction implementation binding is ",
         "missing or stale; rebuild the candidate pool")
  }

  # The ranked-selection receipt is re-derived in full. A swapped input_snapshot,
  # a tampered rank, or a metric/outcome change fails here.
  ranked <- portfolio[["ranked_selections"]]
  ranked_receipt <- tryCatch(
    .parlay_ranked_validate_receipt(ranked),
    error = function(e) {
      stop("parlay_evaluate_portfolio: the portfolio ranked_selections receipt ",
           "is invalid: ", conditionMessage(e), call. = FALSE)
    })
  if (!identical(ranked_receipt$cutoff, cutoff)) {
    stop("parlay_evaluate_portfolio: the ranked-selection cutoff differs from the ",
         "pool cutoff")
  }
  if (!identical(portfolio[["ranked_selections_hash"]], rlang::hash(ranked))) {
    stop("parlay_evaluate_portfolio: the portfolio ranked_selections do not match ",
         "the hash it recorded")
  }

  probabilities <- match_validate_table(portfolio[["probabilities"]],
                                        "probabilities")
  expected_probabilities <- .parlay_ranked_probabilities(ranked)
  probability_order <- function(table) {
    table[order(table$fixture_id, table$outcome, method = "radix"), ,
          drop = FALSE]
  }
  if (!identical(probability_order(probabilities),
                 probability_order(expected_probabilities))) {
    stop("parlay_evaluate_portfolio: the portfolio probabilities do not match ",
         "the ranked selections they were derived from")
  }
  if (!identical(portfolio[["probability_hash"]], rlang::hash(probabilities))) {
    stop("parlay_evaluate_portfolio: the portfolio probabilities do not match ",
         "the hash it recorded")
  }

  prematch_sp <- match_validate_table(portfolio[["prematch_sp"]], "prematch_sp")
  if (!identical(portfolio[["prematch_sp_hash"]], rlang::hash(prematch_sp))) {
    stop("parlay_evaluate_portfolio: the portfolio prematch_sp does not match ",
         "the hash it recorded")
  }
  if (nrow(prematch_sp) && any(prematch_sp$quote_at >= cutoff$cutoff_utc)) {
    stop("parlay_evaluate_portfolio: every prematch_sp quote must be strictly ",
         "before the embedded cutoff")
  }

  parlay_validate_settings(portfolio$settings)
  n_legs <- as.integer(portfolio$settings$n_legs)
  pattern <- .parlay_role_validate_pattern(portfolio$pattern, n_legs)
  if (!identical(as.integer(pattern), sort(as.integer(pattern), decreasing = TRUE))) {
    stop("parlay_evaluate_portfolio: the pool pattern must be stored descending")
  }

  legs <- portfolio$role_legs
  # Schema/type validation before any arithmetic. The frozen legs must be the
  # group_legs contract shape plus the pool's mask columns. `base_role` is the
  # fixture's CLASSIFIER board (which board selected the slot); `n_outcomes` is the
  # realized outcome count of the chosen direction. They are distinct semantics and
  # neither may stand in for the other.
  required <- c("group_slot", "group_id", "fixture_id", "selection_id", "round",
                "base_role", "n_outcomes", "allowed_outcomes",
                "retained_probability")
  if (!all(required %in% names(legs))) {
    stop("parlay_evaluate_portfolio: portfolio role_legs is missing required ",
         "column(s) ", paste(setdiff(required, names(legs)), collapse = ", "))
  }
  if (!is.list(legs$allowed_outcomes)) {
    stop("parlay_evaluate_portfolio: portfolio role_legs$allowed_outcomes must be ",
         "a list column")
  }
  .parlay_ranked_validate_legs(legs, portfolio, probabilities, pattern, n_legs)

  # The validated pool keeps the CONSTRUCTOR'S public field name, `ranked_selections`.
  # A second alias (`ranked`) is deliberately not carried: the previous version
  # returned `ranked` while two consumers read `pool$ranked_selections`, which
  # resolved to NULL and silently turned the improvement stage into a no-op.
  list(cutoff = cutoff, cutoff_hash = cutoff_hash,
       ranked_selections = ranked,
       probabilities = probabilities, prematch_sp = prematch_sp,
       settings = portfolio$settings, pattern = as.integer(pattern),
       n_legs = n_legs, legs = legs,
       group_patterns = portfolio$group_patterns,
       substitutions = portfolio$substitutions,
       groups = portfolio$groups)
}

#' Validate the frozen role legs, masks, patterns and substitutions
#'
#' Internal. Enforces: one row per (group, round-role), rounds exactly `1..n_legs`
#' in the target pattern order, a unique fixture inside a group, actual roles that
#' match the group's recorded `actual_pattern`, retained masks that are exactly the
#' ranked directions of that fixture and role with the correct preference order,
#' and substitution rows whose recorded fallback is a real target-3 -> actual-2
#' replacement with the group's own ranked doubles.
#' @param legs Frozen role legs tibble.
#' @param portfolio The candidate pool.
#' @param probabilities Derived probability table.
#' @param pattern Descending target pattern.
#' @param n_legs Plan width.
#' @return `TRUE` invisibly.
#' @noRd
.parlay_ranked_validate_legs <- function(legs, portfolio, probabilities, pattern,
                                         n_legs) {
  if (!nrow(legs)) return(invisible(TRUE))
  if (anyNA(legs$group_slot) || anyNA(legs$group_id) || anyNA(legs$fixture_id) ||
      anyNA(legs$base_role) || anyNA(legs$n_outcomes) || anyNA(legs$round)) {
    stop("parlay_evaluate_portfolio: portfolio role_legs contains missing keys")
  }
  if (anyDuplicated(paste(legs$group_id, legs$round))) {
    stop("parlay_evaluate_portfolio: portfolio role_legs has a duplicated ",
         "(group_id, round) leg")
  }
  if (any(legs$round < 1L) || any(legs$round > n_legs)) {
    stop("parlay_evaluate_portfolio: portfolio role_legs$round must lie in 1..",
         n_legs)
  }
  # `base_role` is the CLASSIFIER board that selected the leg: 1, 2 or 3. A base-1
  # protected double is a real, allowed leg even though it carries two outcomes.
  if (any(!legs$base_role %in% c(1L, 2L, 3L))) {
    stop("parlay_evaluate_portfolio: portfolio role_legs$base_role must be 1, 2 or 3")
  }
  # `n_outcomes` is the realized outcome count of the chosen direction and must
  # equal the frozen mask length exactly: a protected double is never reported as a
  # single and a true triple is never reported as a double.
  if (anyNA(legs$n_outcomes) ||
      any(as.integer(legs$n_outcomes) != lengths(legs$allowed_outcomes))) {
    stop("parlay_evaluate_portfolio: portfolio role_legs$n_outcomes must equal ",
         "the number of retained outcomes in each leg's mask")
  }
  if (any(!is.finite(legs$retained_probability)) ||
      any(legs$retained_probability < 0) ||
      any(legs$retained_probability > 1 + 1e-9)) {
    stop("parlay_evaluate_portfolio: portfolio role_legs$retained_probability ",
         "must lie in [0, 1] within the accepted 1e-9 probability-sum tolerance")
  }

  # Targets: group_patterns carries the target and actual pattern of every emitted
  # group. A leg's round must be the round whose TARGET role it fills.
  patterns <- portfolio$group_patterns
  if (!all(c("group_slot", "group_id", "target_pattern", "actual_pattern") %in%
           names(patterns))) {
    stop("parlay_evaluate_portfolio: portfolio group_patterns is missing required ",
         "columns")
  }
  target_of <- function(group_id) {
    row <- patterns[as.character(patterns$group_id) == as.character(group_id), ,
                    drop = FALSE]
    if (nrow(row) != 1L) {
      stop("parlay_evaluate_portfolio: portfolio group_patterns must have exactly ",
           "one row per emitted group; group_id ", group_id, " has ", nrow(row))
    }
    values <- row$target_pattern[[1L]]
    actual <- row$actual_pattern[[1L]]
    if (length(values) != n_legs || length(actual) != n_legs ||
        anyNA(values) || anyNA(actual)) {
      stop("parlay_evaluate_portfolio: portfolio group_patterns must carry an ",
           n_legs, "-round target and actual pattern")
    }
    list(target = as.integer(values), actual = as.integer(actual))
  }
  for (group_id in unique(as.character(legs$group_id))) {
    block <- legs[as.character(legs$group_id) == group_id, , drop = FALSE]
    spec <- target_of(group_id)
    if (nrow(block) != n_legs) {
      stop("parlay_evaluate_portfolio: complete group ", group_id, " has ",
           nrow(block), " legs, expected ", n_legs)
    }
    block <- block[order(block$round), , drop = FALSE]
    if (!identical(as.integer(block$round), seq_len(n_legs))) {
      stop("parlay_evaluate_portfolio: complete group ", group_id,
           " must fill every round 1..", n_legs)
    }
    if (!identical(as.integer(block$n_outcomes), spec$actual)) {
      stop("parlay_evaluate_portfolio: group ", group_id, " selected outcome counts disagree ",
           "with its recorded actual_pattern")
    }
    # The target board and the realized board: a leg fills its target board exactly,
    # or falls back through the approved ordered boards (3 -> 2). Nothing is
    # upgraded, so a target-1 protected double stays a base-1 double.
    fallbacks <- lapply(spec$target, .parlay_ranked_fallback_boards)
    legal_actual <- vapply(seq_len(n_legs), function(i) {
      block$base_role[i] %in% fallbacks[[i]]
    }, logical(1))
    if (!identical(spec$target, as.integer(pattern)) || !all(legal_actual)) {
      stop("parlay_evaluate_portfolio: target pattern or fallback boards disagree")
    }
    replaced <- which(spec$target != block$base_role)
    records <- portfolio$substitutions[
      as.character(portfolio$substitutions$group_id) == group_id, , drop = FALSE]
    if (nrow(records) != length(replaced) ||
        !identical(sort(as.integer(records$round)), as.integer(replaced))) {
      stop("parlay_evaluate_portfolio: substitution records must exactly match fallback legs")
    }
    if (anyDuplicated(as.character(block$fixture_id))) {
      stop("parlay_evaluate_portfolio: group ", group_id,
           " repeats a fixture inside one group")
    }
    .parlay_ranked_validate_masks(block, portfolio$ranked_selections,
                                  probabilities, group_id)
    expected_suffix <- substr(
      rlang::hash(.parlay_ranked_candidate_signature(block)), 1L, 12L)
    expected_prefix <- paste0(.parlay_role_group_id(as.character(block$fixture_id)),
                              "@", as.numeric(portfolio$cutoff$cutoff_utc), ":P")
    if (!startsWith(group_id, expected_prefix) ||
        !endsWith(group_id, paste0(":", expected_suffix))) {
      stop("parlay_evaluate_portfolio: constructor group identity does not match incoming legs")
    }
  }

  # Substitutions: a leg whose TARGET board had no unused choice and was filled from
  # a lower approved board (3 -> 2). Every substitution must name a real leg
  # and that leg's own selected direction.
  subs <- portfolio$substitutions
  if (nrow(subs)) {
    required_subs <- c("group_slot", "group_id", "round", "fixture_id",
                       "selection_id", "target_role", "base_role", "n_outcomes",
                       "reason")
    if (!all(required_subs %in% names(subs))) {
      stop("parlay_evaluate_portfolio: portfolio substitutions is missing ",
           "required columns")
    }
    if (any(!subs$reason %in% "target_role_shortage_board_fallback")) {
      stop("parlay_evaluate_portfolio: unknown substitution reason")
    }
    for (i in seq_len(nrow(subs))) {
      group_id <- as.character(subs$group_id[i])
      round <- as.integer(subs$round[i])
      target <- as.integer(subs$target_role[i])
      actual <- as.integer(subs$base_role[i])
      if (!actual %in% .parlay_ranked_fallback_boards(target) || actual == target) {
        stop("parlay_evaluate_portfolio: substitution for group ", group_id,
             " round ", round, " names an illegal board fallback")
      }
      leg <- legs[as.character(legs$group_id) == group_id & legs$round == round, ,
                  drop = FALSE]
      if (nrow(leg) != 1L || as.integer(leg$base_role) != actual ||
          as.integer(leg$n_outcomes) != as.integer(subs$n_outcomes[i]) ||
          !identical(as.character(leg$fixture_id), as.character(subs$fixture_id[i]))) {
        stop("parlay_evaluate_portfolio: substitution for group ", group_id,
             " round ", round, " does not match its fallback leg")
      }
      directions <- portfolio$ranked_selections
      direction <- directions[
        directions$fixture_id == subs$fixture_id[i] &
        directions$selection_id == subs$selection_id[i], , drop = FALSE]
      codes <- c(win = "W", draw = "D", lose = "L")
      if (nrow(direction) != 1L ||
          !setequal(unname(codes[direction$outcomes[[1L]]]),
                    leg$allowed_outcomes[[1L]])) {
        stop("parlay_evaluate_portfolio: substitution direction disagrees with fallback mask")
      }
      ranked_board <- portfolio$ranked_selections$base_role[
        as.character(portfolio$ranked_selections$fixture_id) ==
          as.character(subs$fixture_id[i]) &
          as.integer(portfolio$ranked_selections$selection_id) ==
            as.integer(subs$selection_id[i])]
      if (length(ranked_board) != 1L || as.integer(ranked_board) != actual) {
        stop("parlay_evaluate_portfolio: substitution fixture ",
             subs$fixture_id[i], " is not a ranked base-role-", actual,
             " direction")
      }
    }
  }
  invisible(TRUE)
}

# NOTE: the obsolete "one evaluation funds one actual structure" guard has been
# deleted. Under the outcome-role contract a target pattern may legitimately be
# realized by DIFFERENT actual structures across groups (a target-3 round that met a
# shortage falls back to a base-2 double while its sibling group keeps its triple),
# so the pool is evaluated as a whole and each group's own realized space is priced
# from its own frozen masks. Refusing the mixed pool would contradict the approved
# rule that the same target pattern admits heterogeneous actual structures.

#'
#' Validate one group's retained masks against the ranked selections
#'
#' Internal. The allowed set of a leg must be exactly the outcomes of the ranked
#' selection named by the leg's own `(fixture_id, selection_id)` key, and the
#' retained probability must be their probability sum. The evaluator therefore
#' cannot consume a mask that the ranking stage never produced.
#' @param block Legs of one group, ordered by round.
#' @param ranked Ranked selections tibble.
#' @param probabilities Derived probability table.
#' @param group_id Group identity used in error messages.
#' @return `TRUE` invisibly.
#' @noRd
.parlay_ranked_validate_masks <- function(block, ranked, probabilities,
                                          group_id) {
  wide <- parlay_probability_wide(probabilities)
  for (i in seq_len(nrow(block))) {
    fixture_id <- as.character(block$fixture_id[i])
    selection_id <- as.integer(block$selection_id[i])
    board <- as.integer(block$base_role[i])
    rows <- ranked[as.character(ranked$fixture_id) == fixture_id &
                     as.integer(ranked$selection_id) == selection_id, ,
                   drop = FALSE]
    if (nrow(rows) != 1L) {
      stop("parlay_evaluate_portfolio: group ", group_id, " leg ", fixture_id,
           " selection ", selection_id, " has no unique ranked selection")
    }
    # The leg's named direction must belong to the board the leg records, so a
    # base-1 protected double can never masquerade as a base-2 or base-3 choice.
    if (as.integer(rows$base_role[[1L]]) != board ||
        as.integer(rows$n_outcomes[[1L]]) != as.integer(block$n_outcomes[i])) {
      stop("parlay_evaluate_portfolio: group ", group_id, " leg ", fixture_id,
           " selection ", selection_id, " base_role/n_outcomes disagree with ",
           "the ranked selection")
    }
    # The rank table names outcomes as "win"/"draw"/"lose"; the frozen leg masks
    # carry the canonical W/D/L codes. The leg mask must be EXACTLY the named
    # ranked direction's set -- never an arbitrary mask, never a union across
    # complementary directions and never a widened or upgraded set.
    names_out <- c(win = "W", draw = "D", lose = "L")
    ranked_mask <- sort(unname(names_out[as.character(rows$outcomes[[1L]])]))
    observed <- sort(as.character(block$allowed_outcomes[[i]]))
    if (!identical(ranked_mask, observed)) {
      stop("parlay_evaluate_portfolio: group ", group_id, " leg ", fixture_id,
           " allowed mask is not the ranked direction set for selection ",
           selection_id)
    }
    expected <- observed
    row <- wide[wide$fixture_id == fixture_id, , drop = FALSE]
    expected_probability <- sum(as.numeric(row[1, expected]))
    if (!isTRUE(all.equal(as.numeric(block$retained_probability[i]),
                          expected_probability, tolerance = 1e-12))) {
      stop("parlay_evaluate_portfolio: group ", group_id, " leg ", fixture_id,
           " retained_probability disagrees with the ranked directions")
    }
  }
  invisible(TRUE)
}

# --- per-group enumeration ---------------------------------------------------

#' Enumerate, value and rank one complete group inside its support mask
#'
#' Internal. Uses the group's FROZEN legs and masks: the allowed set is the leg's
#' retained directions in canonical outcome order and the preference is 1-based
#' inside that set. Enumeration, valuation and ranking all go through the mature
#' package APIs so the physical-ticket identity, the once-applied payout factor and
#' the probability-descending/ticket-id tie are exactly the shared ones.
#'
#' Raw pre-match SP is used as-is: the no-replacement threshold is
#' `.Machine$double.xmax`, so a quote above any practical value is preserved. A
#' missing SP leaves `ev_net_est` as `NA_real_` -- EV is unavailable while the
#' coverage mass stays usable.
#' @param group_id Group identity.
#' @param block Legs of the group, ordered by round.
#' @param probabilities Derived probability table.
#' @param prematch_sp Frozen pre-cutoff SP tibble.
#' @param cutoff Validated cutoff.
#' @param settings Validated parlay settings.
#' @param n_legs Plan width.
#' @return A list(group_legs, supports, tickets, ticket_legs, candidate_tickets,
#'   ranked, fixture_set, triple_fixtures, legal_space).
#' @noRd
.parlay_ranked_group_space <- function(group_id, block, probabilities, prematch_sp,
                                       cutoff, settings, n_legs) {
  group_legs <- match_validate_table(
    tibble::tibble(
      group_id = rep(as.character(group_id), nrow(block)),
      fixture_id = as.character(block$fixture_id),
      leg_order = as.integer(block$round)),
    "group_legs")
  group_legs <- group_legs[order(group_legs$leg_order), , drop = FALSE]
  candidate_id <- paste0(group_id, "|", n_legs)
  support_rows <- list()
  for (i in seq_len(nrow(block))) {
    ordered <- match_outcomes()[match_outcomes() %in%
                                  as.character(block$allowed_outcomes[[i]])]
    for (j in seq_along(ordered)) {
      support_rows[[length(support_rows) + 1L]] <- tibble::tibble(
        candidate_id = candidate_id,
        fixture_id = as.character(block$fixture_id[i]),
        outcome = ordered[j], allowed = TRUE, preference = as.integer(j))
    }
  }
  supports <- match_validate_table(dplyr::bind_rows(support_rows), "supports")
  tickets <- parlay_enumerate_tickets(group_legs, probabilities, cutoff, supports,
                                      n_legs = n_legs)
  # `.Machine$double.xmax` is the explicit "never replace" threshold, so raw
  # pre-match SP is preserved exactly and a missing SP yields NA EV.
  valued <- parlay_value_tickets(
    tickets$tickets, tickets$ticket_legs, prematch_sp, cutoff,
    .Machine$double.xmax, 1, as.numeric(settings$unit_cny),
    as.numeric(settings$payout_factor))
  ranked <- parlay_rank_tickets(valued, tickets$candidate_tickets, cutoff,
                                "probability_desc")
  ranked$sp_product_est <- as.numeric(
    valued$sp_product_est[match(ranked$ticket_id, valued$ticket_id)])
  list(group_legs = group_legs, supports = supports, tickets = tickets,
       ranked = ranked, fixture_set = sort(unique(as.character(block$fixture_id))),
       # The ACTUAL full-triple fixtures of this group: a fixture exempted from the
       # pairwise overlap must ACTUALLY select all three outcomes in this group
       # (`n_outcomes == 3`), not merely sit on the base-role-3 board. A base-1
       # protected double and a base-2 pair therefore never qualify, and a target-3
       # round that fell back to a double never grants the exemption.
       triple_fixtures = sort(unique(as.character(
         block$fixture_id[as.integer(block$n_outcomes) == 3L]))),
       legal_space = nrow(ranked), candidate_id = candidate_id)
}

#' The wanted units of a group for an actual group cap
#'
#' Internal. `group_budget_cny = NULL` means the group buys its FULL legal space.
#' Otherwise the cap is `min(cap, full support cost)` floored to whole units, so a
#' zero or sub-unit budget wants zero tickets without erroring.
#' @param group_budget_cny Validated per-group budget, or `NULL`.
#' @param legal_space Number of legal tickets in the group's support.
#' @param unit_cny Positive ticket unit cost.
#' @return Non-negative whole number of units wanted.
#' @noRd
.parlay_ranked_wanted_units <- function(group_budget_cny, legal_space, unit_cny) {
  if (is.null(group_budget_cny)) return(as.integer(legal_space))
  cap <- min(as.numeric(group_budget_cny),
             as.numeric(legal_space) * as.numeric(unit_cny))
  as.integer(floor(cap / as.numeric(unit_cny)))
}

# --- exact coverage ----------------------------------------------------------

#' Canonicalize one purchased ticket into a fixture -> outcome-code event
#'
#' Internal. A physical ticket is a PARTIAL ASSIGNMENT: it constrains one outcome
#' code per fixture it touches and says nothing about the rest. Canonicalizing to a
#' sorted, named integer vector makes tickets comparable and de-duplicable without
#' reference to the order their legs happen to be stored in.
#' @param ticket_id Physical ticket id.
#' @param ticket_legs Validated ticket_legs table.
#' @param outcomes Canonical outcome codes, `match_outcomes()`.
#' @return Named integer vector, `fixture_id -> code`, sorted by fixture id.
#' @noRd
.parlay_ranked_ticket_event <- function(ticket_id, ticket_legs, outcomes) {
  legs <- ticket_legs[as.character(ticket_legs$ticket_id) == ticket_id, ,
                      drop = FALSE]
  if (!nrow(legs)) {
    stop("parlay_evaluate_portfolio: ticket ", ticket_id,
         " has no legs in the purchased ledger")
  }
  codes <- match(as.character(legs$outcome), outcomes)
  if (anyNA(codes)) {
    stop("parlay_evaluate_portfolio: ticket ", ticket_id,
         " carries an unknown outcome code")
  }
  event <- stats::setNames(as.integer(codes), as.character(legs$fixture_id))
  event[order(names(event))]
}

#' Partition the touched fixtures into independent connected components
#'
#' Internal. Two fixtures belong to the same component when some owned ticket
#' constrains BOTH of them. Different components share no ticket, so -- because
#' fixtures are independent -- the union probability factorizes as
#' `1 - prod(1 - coverage_of_component)`. This is what keeps the work proportional
#' to the ACTUAL ticket support instead of the global `3^F` product.
#' @param events List of canonical ticket events (named integer vectors).
#' @param fixtures Every touched fixture.
#' @return List of character vectors, one per connected component.
#' @noRd
.parlay_ranked_components <- function(events, fixtures) {
  parent <- stats::setNames(fixtures, fixtures)
  find <- function(x) {
    while (parent[[x]] != x) {
      parent[[x]] <<- parent[[parent[[x]]]]
      x <- parent[[x]]
    }
    x
  }
  union <- function(a, b) {
    ra <- find(a)
    rb <- find(b)
    if (ra != rb) parent[[rb]] <<- ra
  }
  for (event in events) {
    members <- names(event)
    if (length(members) > 1L) {
      anchor <- members[1L]
      for (member in members[-1L]) union(anchor, member)
    }
  }
  roots <- vapply(fixtures, find, character(1), USE.NAMES = FALSE)
  split(fixtures, roots)
}

#' Exact union probability inside ONE connected component by Shannon decomposition
#'
#' Internal. Weighted recursive decomposition over the component's canonical event
#' set. The recursion keys on the FIRST still-unassigned fixture of the component
#' that any surviving event constrains, and splits its outcome space into the three
#' mutually exclusive, exhaustive cases W/D/L:
#'
#'   * an event that ASSIGNS that fixture a different code is incompatible with the
#'     case and is discarded;
#'   * an event that assigns the matching code is SATISFIED and covers the whole
#'     case, so the case contributes `P(fixture = code)` immediately;
#'   * an event that does not mention the fixture survives whole, with its
#'     residual mass at least as large as the case, so the case contributes
#'     `P(fixture = code) * union(residual)`.
#'
#' Consequences that matter here:
#'   * no surviving events has union `0`; a satisfied empty assignment covers
#'     its conditional branch with probability `1`;
#'   * mutually exclusive events over ONE identical fixture set (same fixtures,
#'     complementary assignments) sum their probabilities exactly, because the
#'     matching case of each assignment is disjoint;
#'   * nested/subset events stay exact: a covering event is satisfied before a
#'     narrower event is ever decomposed.
#'
#' The residual state is canonicalized (events sorted and de-duplicated) and
#' memoized, so a state reached by different branches is computed once. The
#' component has at most `3^|component|` states in principle, but only the states
#' the actual event support reaches are ever built -- the global `3^F` grid is
#' never materialized.
#' @param events List of canonical ticket events over `fixtures`.
#' @param fixtures Fixtures of this component.
#' @param probability_of Function `(fixture_id, code) -> probability`.
#' @param memo Environment used as the state cache.
#' @return A single probability in `[0, 1]`.
#' @noRd
.parlay_ranked_component_union <- function(events, fixtures, probability_of,
                                           memo) {
  canonical <- function(state) {
    if (!length(state)) return(list())
    keys <- vapply(state, function(event) {
      paste(names(event), event, sep = "=", collapse = "|")
    }, character(1))
    state[order(keys)][!duplicated(sort(keys))]
  }
  state_key <- function(state) {
    rlang::hash(state)
  }
  decompose <- function(state) {
    # The base case is "no surviving event can cover the remaining fixtures", so the
    # probability of coverage is ZERO. Satisfaction is handled explicitly below and
    # never reaches this branch, so pruning the last incompatible event must not be
    # confused with being covered.
    if (!length(state)) return(0)
    key <- state_key(state)
    if (!is.null(memo[[key]])) return(memo[[key]])
    # The pivot is the FIRST fixture in canonical (sorted) fixture order that any
    # surviving event still constrains. Satisfied events never reach a residual
    # state, so an unconstrained fixture is never chosen and every branch makes
    # real progress.
    constrained <- unique(unlist(lapply(state, names), use.names = FALSE))
    pivot <- constrained[order(match(constrained, fixtures))][1L]
    if (is.null(pivot) || is.na(pivot)) {
      stop("parlay_evaluate_portfolio: internal union state has no pivot fixture")
    }
    total <- 0
    for (code in seq_along(match_outcomes())) {
      residual <- list()
      satisfied <- FALSE
      for (event in state) {
        position <- match(pivot, names(event))
        if (!is.na(position)) {
          if (event[[position]] == code) {
            # This event AGREEES with the case on the pivot. It is satisfied only
            # when the pivot was its LAST unassigned fixture; otherwise the pivot is
            # discharged and the event continues as a smaller event over the
            # remaining fixtures, so the case is not yet covered.
            reduced <- event[-position]
            if (!length(reduced)) {
              satisfied <- TRUE
              break
            }
            residual[[length(residual) + 1L]] <- reduced
          }
          # INCOMPATIBLE with the case: discarded, but the case is NOT covered.
          next
        }
        # Does not mention the pivot: survives whole into the residual state.
        residual[[length(residual) + 1L]] <- event
      }
      value <- if (satisfied) 1 else decompose(canonical(residual))
      total <- total + probability_of(pivot, code) * value
    }
    memo[[key]] <- total
    total
  }
  events <- canonical(events)
  if (length(events) && all(vapply(events, function(event) {
    identical(names(event), names(events[[1L]]))
  }, logical(1)))) {
    # Distinct full assignments on the same fixture set are mutually exclusive.
    return(sum(vapply(events, function(event) {
      prod(vapply(seq_along(event), function(i) {
        probability_of(names(event)[i], event[[i]])
      }, numeric(1)))
    }, numeric(1))))
  }
  return(decompose(events))
}

#' Exact coverage of the whole owned portfolio across every selected group
#'
#' Internal. The union probability over ALL owned physical tickets is the
#' probability that AT LEAST ONE owned ticket wins. Tickets are partial fixture
#' assignments, so the quantity is computed as an exact event union:
#'
#'   * physically identical tickets are harmless duplicates and are collapsed;
#'   * tickets spanning DISJOINT fixture sets are independent and combine as
#'     `1 - prod(1 - p)`;
#'   * tickets OVERLAPPING on a fixture are resolved by the weighted recursive
#'     Shannon decomposition in [.parlay_ranked_component_union()].
#'
#' Used by both the per-group coverage and the improvement stage's strict
#' whole-portfolio union gain. It never materializes the global `3^F` outcome grid,
#' so disjoint components with 20+ fixtures remain practical. Highly overlapping
#' portfolios may still require many recursive states.
#' @param tickets Character vector of owned physical ticket ids.
#' @param ticket_legs Validated ticket_legs table.
#' @param probabilities Derived probability table.
#' @return A single probability in `[0, 1]`; `0` when nothing is owned.
#' @noRd
.parlay_ranked_union_coverage <- function(tickets, ticket_legs, probabilities) {
  if (!length(tickets)) return(0)
  outcomes <- match_outcomes()
  wide <- parlay_probability_wide(probabilities)
  owned <- lapply(unique(as.character(tickets)), .parlay_ranked_ticket_event,
                  ticket_legs, outcomes)
  fixtures <- sort(unique(unlist(lapply(owned, names), use.names = FALSE)))
  probability_cache <- new.env(parent = emptyenv())
  probability_of <- function(fixture_id, code) {
    key <- paste0(fixture_id, "\r", code)
    if (!is.null(probability_cache[[key]])) return(probability_cache[[key]])
    row <- wide[wide$fixture_id == fixture_id, , drop = FALSE]
    if (nrow(row) != 1L) {
      stop("parlay_evaluate_portfolio: fixture ", fixture_id,
           " has no unique probability row")
    }
    value <- as.numeric(row[1, outcomes[code]])
    probability_cache[[key]] <- value
    value
  }
  components <- .parlay_ranked_components(owned, fixtures)
  # Independent components: the union is one minus the probability that no
  # component is covered. Within a component, tickets may overlap and are resolved
  # exactly by the recursive decomposition.
  miss <- 1
  for (component in components) {
    local <- Filter(function(event) all(names(event) %in% component), owned)
    coverage <- .parlay_ranked_component_union(local, component, probability_of,
                                               new.env(parent = emptyenv()))
    miss <- miss * (1 - coverage)
  }
  as.numeric(1 - miss)
}

# --- admission ---------------------------------------------------------------

#' Pairwise fixture overlap that ignores a shared ACTUAL triple fixture
#'
#' Internal. A fixture that ACTUALLY selects all three outcomes in BOTH groups never
#' counts toward the pairwise overlap: admitting one group does not spend the
#' triple-guarantee of a fixture the other group also funds as a real triple. Any
#' other shared fixture (an ordinary double, a base-1 protected double, or a
#' target-3 fallback double) still counts. The exemption is keyed on the realized
#' outcome combination (`n_outcomes == 3`), never on `base_role`, so a base-1
#' protected double is never granted a triple's exemption. Fixture sets must be
#' explicit character vectors; character(0) means no actual triples.
#' @param candidate_fixtures Candidate group's actual fixtures.
#' @param candidate_triples Character vector of candidate actual-triple fixture IDs.
#' @param record_fixtures Admitted group's actual fixtures.
#' @param record_triples Character vector of admitted actual-triple fixture IDs.
#' @return Non-negative whole number of counted shared fixtures.
#' @noRd
.parlay_ranked_counted_overlap <- function(candidate_fixtures, candidate_triples,
                                           record_fixtures, record_triples) {
  checkmate::assert_character(candidate_triples, any.missing = FALSE, min.chars = 1)
  checkmate::assert_character(record_triples, any.missing = FALSE, min.chars = 1)
  shared <- intersect(candidate_fixtures, record_fixtures)
  shared_triples <- intersect(candidate_triples, record_triples)
  return(length(setdiff(shared, shared_triples)))
}

#' Check one candidate group against the already-admitted groups
#'
#' Internal. Applies the SAME arithmetic the funding walk uses -- per-fixture reuse
#' across every admitted group and pairwise overlap between the candidate and each
#' admitted group -- but with the explicit policies.
#'
#' Reuse has NO exemption: `max_reuse` counts EVERY actual fixture of every actual
#' group, including a fixture that is an actual triple. Overlap has exactly ONE
#' exemption: a fixture that ACTUALLY selects all three outcomes in BOTH groups is
#' exempt and does not count toward `max_overlap`. Any other shared fixture counts.
#' The exemption is derived from the realized outcome combination, so a base-1
#' protected double and a target-3 fallback double never qualify.
#'
#' A group whose fixtures all already appear, but which would still buy a new
#' physical ticket, is NOT refused here; the caller refuses an all-already-bought
#' group as `no_new_tickets` without consuming a constraint.
#' @param fixture_set Sorted fixtures of the candidate.
#' @param admitted List of already-admitted group records, each with `fixture_set`
#'   and an explicit character vector `triple_fixtures` (possibly empty).
#' @param reuse_policy Validated reuse policy.
#' @param overlap_policy Validated overlap policy.
#' @param triple_fixtures Explicit character vector of candidate actual triples.
#' @return A list(allowed, reason). `reason` is `""` when allowed.
#' @noRd
.parlay_ranked_admit <- function(fixture_set, admitted, reuse_policy,
                                 overlap_policy, triple_fixtures) {
  max_reuse <- reuse_policy$max_reuse
  max_overlap <- overlap_policy$max_overlap
  if (!is.null(max_reuse)) {
    counts <- table(c(fixture_set,
                      unlist(lapply(admitted, function(a) a$fixture_set))))
    if (length(counts) && max(counts) > max_reuse) {
      return(list(allowed = FALSE, reason = "reuse_cap_exceeded"))
    }
  }
  if (!is.null(max_overlap)) {
    for (record in admitted) {
      counted <- .parlay_ranked_counted_overlap(
        fixture_set, triple_fixtures, record$fixture_set, record$triple_fixtures)
      if (counted > max_overlap) {
        return(list(allowed = FALSE, reason = "overlap_cap_exceeded"))
      }
    }
  }
  list(allowed = TRUE, reason = "")
}

# --- the funding walk --------------------------------------------------------

#' Stage one group's funding without mutating the committed ledger
#' @param state Explicit temporary ledger: bought, spent, admitted, purchases,
#'   ticket_legs and selection lists. Failed staging returns the original ledger.
#' @param space Enumerated group space from .parlay_ranked_group_space().
#' @param nominal One-row group quota/priority tibble.
#' @param pool Explicit normalized decision pool with cutoff and probabilities.
#' @param budget_cny Explicit total CNY cap or NULL.
#' @param reuse_policy Explicit reuse cap; all actual roles count.
#' @param overlap_policy Explicit overlap cap; shared actual triples are exempt.
#' @return List(state,reason). Pure tentative transaction, no IO/labels/fitting.
#'   Tickets follow descending probability; physical duplicates never repurchased.
#' @noRd
.parlay_ranked_stage_group <- function(state,space,nominal,pool,budget_cny,
                                       reuse_policy,overlap_policy) {
  group_id <- as.character(nominal$group_id[1])
  wanted <- as.integer(nominal$group_units[1])
  fresh <- space$ranked[!space$ranked$ticket_id %in% state$bought,,drop=FALSE]
  if(!nrow(fresh) || wanted==0L) return(list(state=state,reason="no_new_tickets"))
  verdict <- .parlay_ranked_admit(space$fixture_set,state$admitted,reuse_policy,
    overlap_policy,space$triple_fixtures)
  if(!verdict$allowed) return(list(state=state,reason=verdict$reason))
  units <- if(is.null(budget_cny)) wanted else min(wanted,
    max(0,floor((budget_cny-state$spent+1e-9)/pool$settings$unit_cny)))
  units <- min(units,nrow(fresh))
  if(units==0) return(list(state=state,reason="no_new_tickets"))
  owned <- fresh[seq_len(units),,drop=FALSE] |>
    dplyr::transmute(group_slot=as.integer(nominal$group_slot[1]),
      group_id=group_id,ticket_id=as.character(ticket_id),rank=as.integer(rank),
      probability=as.numeric(probability),cost_cny=as.numeric(pool$settings$unit_cny),
      sp_product_est=as.numeric(sp_product_est),ev_net_est=as.numeric(ev_net_est))
  legs <- dplyr::semi_join(space$tickets$ticket_legs,owned,by="ticket_id")
  state$bought <- c(state$bought,owned$ticket_id)
  state$spent <- state$spent+sum(owned$cost_cny)
  state$admitted[[length(state$admitted)+1L]] <- list(group_id=group_id,
    fixture_set=space$fixture_set,triple_fixtures=space$triple_fixtures)
  state$purchases[[length(state$purchases)+1L]] <- owned
  state$ticket_legs[[length(state$ticket_legs)+1L]] <- legs
  # All tickets in this group use the same fixtures, hence distinct tickets are mutually exclusive.
  state$selection[[length(state$selection)+1L]] <- dplyr::mutate(nominal,
    admitted=TRUE,tickets=as.integer(nrow(owned)),spent_cny=sum(owned$cost_cny),
    actual_coverage=sum(owned$probability),reason="admitted")
  list(state=state,reason="admitted")
}

#' Fund the ranked candidate pool under the explicit budget and policies
#'
#' Internal. The bounded successor funding walk:
#'   1. every complete group is enumerated once and its NOMINAL priority computed
#'      as the probability mass of its legal top-N tickets for its actual group cap;
#'   2. groups are visited in the initial nominal order (mass descending, stable
#'      group id tie) and never re-sorted dynamically;
#'   3. triggering actual double fixtures require both purchased directions in
#'      different groups. Seeds and partners are staged in stable nominal order;
#'      partner obligations expand the finite bundle. No combinatorial search or
#'      backtracking is claimed. Missing partners roll back every tentative purchase.
#'   4. a group with no new physical ticket is rejected `no_new_tickets` without
#'      consuming a constraint or cash; an admitted group is checked for reuse and
#'      overlap and a refusal consumes nothing;
#'   4. an admitted group buys its rank-ordered tickets, SKIPPING physical tickets
#'      already bought anywhere in this decision, continuing DOWN the rank until the
#'      wanted units, the remaining total budget or the legal space is exhausted;
#'   5. spent cash, new tickets and the group's ACTUAL coverage are recorded from
#'      the owned new tickets only.
#' @param pool Validated pool list from [.parlay_ranked_validate_pool()].
#' @param group_budget_cny Validated per-group budget, or `NULL`.
#' @param budget_cny Validated total budget, or `NULL`.
#' @param reuse_policy Validated reuse policy.
#' @param overlap_policy Validated overlap policy.
#' @return A list with the per-group spaces, the nominal ordering, the purchases
#'   ledger, the selection audit and the rejections.
#' @noRd
.parlay_ranked_fund <- function(pool, group_budget_cny, budget_cny, reuse_policy,
                                overlap_policy) {
  settings <- pool$settings
  unit_cny <- as.numeric(settings$unit_cny)
  groups <- pool$legs
  group_ids <- unique(as.character(groups$group_id[order(groups$group_slot)]))
  spaces <- list()
  nominal <- list()
  for (group_id in group_ids) {
    block <- groups[as.character(groups$group_id) == group_id, , drop = FALSE]
    block <- block[order(block$round), , drop = FALSE]
    space <- .parlay_ranked_group_space(
      group_id, block, pool$probabilities, pool$prematch_sp, pool$cutoff,
      settings, pool$n_legs)
    wanted <- .parlay_ranked_wanted_units(group_budget_cny, space$legal_space,
                                          unit_cny)
    head <- space$ranked[seq_len(min(wanted, space$legal_space)), , drop = FALSE]
    nominal_mass <- if (nrow(head)) sum(as.numeric(head$probability)) else 0
    slot <- pool$legs$group_slot[as.character(pool$legs$group_id) == group_id][1]
    spaces[[group_id]] <- space
    nominal[[length(nominal) + 1L]] <- tibble::tibble(
      group_slot = as.integer(slot), group_id = group_id,
      legal_space = as.integer(space$legal_space),
      group_units = as.integer(wanted),
      nominal_coverage = as.numeric(nominal_mass))
  }
  # A pool with no emitted group still has to produce the same shape: `bind_rows` of
  # an empty list yields a 0x0 tibble, so the typed-empty nominal table is used
  # explicitly and the ordering below stays a no-op on zero rows.
  nominal <- if (length(nominal)) dplyr::bind_rows(nominal) else
    .parlay_ranked_empty_nominal()
  # Initial nominal priority: mass descending, stable group id tie. This order is
  # followed for the whole walk.
  nominal <- nominal[order(-nominal$nominal_coverage, nominal$group_id), ,
                     drop = FALSE]

  state <- list(bought=character(),spent=0,admitted=list(),purchases=list(),
                ticket_legs=list(),selection=list())
  rejections <- list()
  for (i in seq_len(nrow(nominal))) {
    seed <- as.character(nominal$group_id[i])
    if (seed %in% vapply(state$admitted,function(x)x$group_id,character(1))) next
    attempt <- .parlay_ranked_stage_group(state,spaces[[seed]],nominal[i,],
      pool,budget_cny,reuse_policy,overlap_policy)
    reason <- attempt$reason
    if(identical(reason,"admitted")) state <- attempt$state
    else rejections[[length(rejections)+1L]] <- tibble::tibble(
      group_slot=as.integer(nominal$group_slot[i]),group_id=seed,reason=reason,
      detail="candidate refused; no cost or admission was consumed")
  }
  selected <- if(length(state$selection)) dplyr::bind_rows(state$selection) else
    .parlay_ranked_empty_selection()
  rejected <- if(length(rejections)) dplyr::bind_rows(rejections) else
    .parlay_ranked_empty_rejections()
  skipped <- dplyr::anti_join(nominal,dplyr::select(selected,group_id),by="group_id") |>
    dplyr::left_join(dplyr::select(rejected,group_id,reason),by="group_id",relationship="one-to-one") |>
    dplyr::mutate(admitted=FALSE,tickets=0L,spent_cny=0,actual_coverage=0)
  selected <- dplyr::bind_rows(selected,skipped) |>
    dplyr::slice(match(nominal$group_id,group_id))
  purchases <- if(length(state$purchases)) dplyr::bind_rows(state$purchases) else
    .parlay_ranked_empty_purchases()
  ticket_legs <- if(length(state$ticket_legs)) dplyr::bind_rows(state$ticket_legs) else
    match_typed_empty("ticket_legs")
  list(spaces=spaces,nominal=nominal,purchases=purchases,ticket_legs=ticket_legs,
       selection=selected,rejections=rejected,bought=state$bought,spent=state$spent,
       selected_groups=vapply(state$admitted,function(x)x$group_id,character(1)))
}

#' Typed-empty nominal priority table
#'
#' Internal. `bind_rows()` of an empty list yields a 0x0 tibble, so a pool with no
#' emitted group needs this explicit shape for the funding walk to stay total.
#' @return A typed-empty nominal tibble.
#' @noRd
.parlay_ranked_empty_nominal <- function() {
  tibble::tibble(group_slot = integer(0), group_id = character(0),
                 legal_space = integer(0), group_units = integer(0),
                 nominal_coverage = numeric(0))
}

#' Typed-empty purchase ledger
#' @return A typed-empty purchases tibble.
#' @noRd
.parlay_ranked_empty_purchases <- function() {
  tibble::tibble(group_slot = integer(0), group_id = character(0),
                 ticket_id = character(0), rank = integer(0),
                 probability = numeric(0), cost_cny = numeric(0),
                 sp_product_est = numeric(0), ev_net_est = numeric(0))
}

#' Typed-empty selection audit
#' @return A typed-empty selection tibble.
#' @noRd
.parlay_ranked_empty_selection <- function() {
  tibble::tibble(group_slot = integer(0), group_id = character(0),
                 legal_space = integer(0), group_units = integer(0),
                 nominal_coverage = numeric(0), admitted = logical(0),
                 tickets = integer(0), spent_cny = numeric(0),
                 actual_coverage = numeric(0), reason = character(0))
}

#' Typed-empty rejection audit
#' @return A typed-empty rejections tibble.
#' @noRd
.parlay_ranked_empty_rejections <- function() {
  tibble::tibble(group_slot = integer(0), group_id = character(0),
                 reason = character(0), detail = character(0))
}

# --- receipt and result assembly ---------------------------------------------

#' Actual-summary of the ranked funding walk
#'
#' Internal. Reports the ACTUAL selected groups, new ticket count, spent cash and
#' the per-group target/actual pattern, nominal coverage and the ACTUAL owned
#' coverage. With an unlimited total budget `unspent_cny` is `NA_real_`, never a
#' fake zero. EV is reported as a nullable availability flag plus a net figure that
#' is `NA_real_` when any owned ticket lacks a usable pre-match SP.
#' @param fund Result of [.parlay_ranked_fund()].
#' @param pool Validated pool list.
#' @param budget_cny Validated total budget or `NULL`.
#' @param group_budget_cny Validated per-group budget or `NULL`.
#' @return A named list of summary tables.
#' @noRd
.parlay_ranked_summary <- function(fund, pool, budget_cny, group_budget_cny) {
  purchases <- fund$purchases
  patterns <- pool$group_patterns
  group_rows <- lapply(seq_len(nrow(fund$nominal)), function(i) {
    group_id <- as.character(fund$nominal$group_id[i])
    pat <- patterns[as.character(patterns$group_id) == group_id, , drop = FALSE]
    owned <- purchases[as.character(purchases$group_id) == group_id, , drop = FALSE]
    target <- if (nrow(pat)) pat$target_pattern[[1L]] else integer(0)
    actual <- if (nrow(pat)) pat$actual_pattern[[1L]] else integer(0)
    tibble::tibble(
      group_slot = as.integer(fund$nominal$group_slot[i]), group_id = group_id,
      target_pattern = paste(as.integer(target), collapse = ""),
      actual_pattern = paste(as.integer(actual), collapse = ""),
      legal_space = as.integer(fund$nominal$legal_space[i]),
      group_units = as.integer(fund$nominal$group_units[i]),
      nominal_coverage = as.numeric(fund$nominal$nominal_coverage[i]),
      admitted = group_id %in% fund$selected_groups,
      tickets = as.integer(nrow(owned)), spent_cny = as.numeric(sum(owned$cost_cny)),
      actual_coverage = as.numeric(sum(fund$selection$actual_coverage[
        as.character(fund$selection$group_id) == group_id])),
      ev_available = nrow(owned) > 0L && all(is.finite(owned$ev_net_est)),
      ev_net_cny = if (nrow(owned) && all(is.finite(owned$ev_net_est))) {
        as.numeric(sum(owned$ev_net_est))
      } else {
        NA_real_
      })
  })
  group_selection <- if (length(group_rows)) dplyr::bind_rows(group_rows) else
    tibble::tibble(group_slot = integer(0), group_id = character(0),
                   target_pattern = character(0), actual_pattern = character(0),
                   legal_space = integer(0), group_units = integer(0),
                   nominal_coverage = numeric(0), admitted = logical(0),
                   tickets = integer(0), spent_cny = numeric(0),
                   actual_coverage = numeric(0), ev_available = logical(0),
                   ev_net_cny = numeric(0))
  total_coverage <- .parlay_ranked_union_coverage(
    as.character(purchases$ticket_id), fund$ticket_legs, pool$probabilities)
  summary <- list(
    selected_groups = as.integer(length(fund$selected_groups)),
    new_ticket_count = as.integer(nrow(purchases)),
    spent_cny = as.numeric(sum(purchases$cost_cny)),
    unspent_cny = if (is.null(budget_cny)) NA_real_ else
      as.numeric(as.numeric(budget_cny) - sum(purchases$cost_cny)),
    group_budget_cny = group_budget_cny,
    nominal_coverage = as.numeric(sum(fund$nominal$nominal_coverage[
      fund$nominal$group_id %in% fund$selected_groups])),
    actual_coverage = as.numeric(total_coverage),
    tickets = as.integer(nrow(purchases)),
    ev_available = nrow(purchases) > 0L && all(is.finite(purchases$ev_net_est)),
    ev_net_cny = if (nrow(purchases) && all(is.finite(purchases$ev_net_est))) {
      as.numeric(sum(purchases$ev_net_est))
    } else {
      NA_real_
    },
    objective_basis = "probability that at least one owned physical ticket wins",
    unspent_basis = if (is.null(budget_cny)) "unlimited budget; NA not 0"
                    else "budget minus actually spent cash")
  list(group_selection = group_selection, summary = summary)
}

#' Frozen delivery plan for downstream settlement
#'
#' Internal. Builds the frozen plan through the mature [.FreezeParlayPlan()] so
#' [parlay_settle_plan()] can consume it. The `funded` table is the purchase ledger
#' projected onto the frozen ticket identity.
#' @param pool Validated pool list.
#' @param fund Result of [.parlay_ranked_fund()].
#' @param purchases The purchase ledger.
#' @param budget_cny Validated total budget or `NULL`.
#' @param reuse_policy Resolved reuse policy actually applied by the funding walk.
#' @param overlap_policy Resolved overlap policy actually applied by the funding
#'   walk. Both are recorded UNCHANGED, so a finite limit is never rewritten to
#'   `NULL` (unlimited) and the frozen plan describes the decision that was made.
#' @return A frozen plan list.
#' @noRd
.parlay_ranked_freeze <- function(pool, fund, purchases, budget_cny, reuse_policy,
                                  overlap_policy) {
  settings <- pool$settings
  if (!nrow(purchases)) {
    group_legs <- match_typed_empty("group_legs")
    purchased_rows <- tibble::tibble(
      issue_id = character(0), ticket_id = character(0),
      epoch_at = as.POSIXct(character(0), tz = "UTC"),
      group_id = character(0), candidate_id = character(0), stake_cny = numeric(0))
  } else {
    group_legs <- dplyr::bind_rows(lapply(fund$selected_groups, function(group_id) {
      block <- pool$legs[as.character(pool$legs$group_id) == group_id, , drop = FALSE]
      tibble::tibble(group_id = as.character(group_id),
                     fixture_id = as.character(block$fixture_id),
                     leg_order = as.integer(block$round))
    }))
    group_legs <- match_validate_table(
      group_legs[order(group_legs$group_id, group_legs$leg_order), , drop = FALSE],
      "group_legs")
    purchased_rows <- tibble::tibble(
      issue_id = rep(as.character(pool$cutoff$issue_id), nrow(purchases)),
      ticket_id = as.character(purchases$ticket_id),
      epoch_at = rep(pool$cutoff$cutoff_utc, nrow(purchases)),
      group_id = as.character(purchases$group_id),
      candidate_id = rep(NA_character_, nrow(purchases)),
      stake_cny = as.numeric(purchases$cost_cny))
  }
  funded_rows <- tibble::tibble(
    ticket_id = as.character(purchases$ticket_id),
    group_id = as.character(purchases$group_id),
    stake_cny = as.numeric(purchases$cost_cny))
  .FreezeParlayPlan(
    issue_id = as.character(pool$cutoff$issue_id),
    epoch_utc = pool$cutoff$cutoff_utc, group_legs = group_legs,
    structure = list(supports = match_typed_empty("supports")),
    tickets = list(tickets = match_typed_empty("tickets"),
                   ticket_legs = if (nrow(fund$ticket_legs)) fund$ticket_legs else
                     match_typed_empty("ticket_legs")),
    valued = match_typed_empty("tickets"),
    funded = funded_rows, purchases = purchased_rows, constants = settings,
    policies = list(objective = "coverage",
                    max_reuse = reuse_policy$max_reuse,
                    max_overlap = overlap_policy$max_overlap,
                    # The ONE overlap exemption: a fixture that ACTUALLY selects all
                    # three outcomes in BOTH groups. Keyed on the realized outcome
                    # combination, never on base_role, so a base-1 protected double
                    # is never exempted.
                    overlap_actual_triple_exemption = TRUE,
                    budget_cny = budget_cny))
}

# --- improvement stage -------------------------------------------------------

#' Re-evaluate the exact owned purchase ledger
#'
#' Internal. Given a set of owned physical ticket ids (the exact funded ledger),
#' recomputes the actual whole-portfolio union coverage and returns the ledger
#' joined back to its group and candidate attribution. The join is on the
#' composite (candidate_id, ticket_id) key where group ranking is needed, so a
#' shared physical ticket is attributed to the group that actually bought it.
#' @param tickets Character vector of owned physical ticket ids.
#' @param pool Validated pool list.
#' @param fund Baseline fund result providing per-ticket attribution.
#' @return A list(purchases, unique_tickets, coverage, spent).
#' @noRd
.parlay_ranked_evaluate_ledger <- function(tickets, pool, fund) {
  ledger <- fund$purchases[as.character(fund$purchases$ticket_id) %in% tickets, ,
                           drop = FALSE]
  unique_tickets <- unique(as.character(ledger$ticket_id))
  list(purchases = ledger, unique_tickets = unique_tickets,
       coverage = .parlay_ranked_union_coverage(unique_tickets, fund$ticket_legs,
                                                pool$probabilities),
       spent = as.numeric(sum(ledger$cost_cny)))
}

#' Bounded improvement over legal same-role fixture replacements
#'
#' Internal. A meaningfully bounded first-improvement stage whose move space is
#' REACHABLE on a real pool. The ranking stage emits exactly ONE authoritative
#' direction or two complementary directions per `(fixture, role)`. Legal moves
#' include switching complementary directions or a single-fixture
#' REPLACEMENT / reallocation inside an admitted group:
#'
#'   * a leg's fixture is replaced by a DIFFERENT fixture whose authoritative
#'     ranked selection carries the SAME ACTUAL role (2 stays 2, 3 stays 3);
#'   * the replacement fixture's mask is that fixture's own authoritative ranked
#'     mask for that role -- never a mask this function invents, and never a
#'     target-role UPGRADE (a role-2 fallback leg is never promoted to role 3);
#'   * within-group uniqueness holds: the replacement fixture must not already be
#'     a leg of the same group;
#'   * each group's own actual pattern is preserved; different groups may retain
#'     different actual patterns under the same target pattern;
#'   * all final reuse/overlap, cost and physical-ticket de-duplication, frozen
#'     probabilities, SP and cutoff are re-applied by the full funding walk.
#'
#' A move is accepted only when its ACTUAL whole-portfolio union coverage is
#' strictly greater than the incumbent's. The union is exact (see
#' [.parlay_ranked_union_coverage()]); summing per-ticket masses across different
#' fixtures is deliberately NOT used, because that is a different quantity. Every
#' candidate is re-funded from the exact purchase ledger under the SAME group cap,
#' total budget and reuse/overlap policies. The pass structure is the existing
#' bounded one: `improve=TRUE` is a single deterministic pass in the pool's
#' initial nominal group order with a stable fixture-id tie, so the stage is
#' bounded by the emitted move space and selects no optimizer or budget.
#' @param pool Validated pool list.
#' @param fund Baseline fund result.
#' @param group_budget_cny Validated per-group budget or `NULL`.
#' @param budget_cny Validated total budget or `NULL`.
#' @param reuse_policy Validated reuse policy.
#' @param overlap_policy Validated overlap policy.
#' @param improve Logical scalar; `FALSE` returns the baseline untouched.
#' @return A list(fund, changes, evaluations, accepted).
#' @noRd
.parlay_ranked_improve <- function(pool, fund, group_budget_cny, budget_cny,
                                   reuse_policy, overlap_policy, improve) {
  changes <- .parlay_ranked_empty_changes()
  if (!improve || !length(fund$selected_groups) || !nrow(fund$purchases)) {
    return(list(pool = pool, fund = fund, changes = changes, evaluations = 0L, accepted = 0L))
  }
  baseline <- .parlay_ranked_evaluate_ledger(
    unique(as.character(fund$purchases$ticket_id)), pool, fund)
  best_coverage <- baseline$coverage
  best_fund <- fund
  # The incumbent POOL as well as the incumbent fund: an accepted move must compose
  # with the moves before it, so the next candidate replaces a leg of the incumbent
  # structure rather than restarting from the untouched baseline.
  best_pool <- pool
  evaluations <- 0L
  accepted <- 0L
  ranked <- pool$ranked_selections
  # The pool's complete legal fixture pool per role, in stable fixture-id order, so
  # the move order is deterministic and independent of discovery order.
  # A fixed, bounded traversal: the pool's initial nominal group order, then the
  # group's round order. It is never re-sorted after a move is accepted.
  for (group_id in fund$selected_groups) {
    for (round_index in seq_len(nrow(pool$legs[as.character(pool$legs$group_id) ==
                                               group_id, , drop = FALSE]))) {
      # The round layout of a group is fixed by its contract, so the round position
      # is stable across the whole walk; only the fixture behind it may change.
      layout <- best_pool$legs[as.character(best_pool$legs$group_id) == group_id, ,
                               drop = FALSE]
      layout <- layout[order(layout$round), , drop = FALSE]
      if (round_index > nrow(layout)) next
      # The leg's realized structure is the pair (board, outcome count): an
      # alternative must carry the SAME base_role AND the same n_outcomes, so a
      # replacement never silently changes the group's realized structure and a
      # base-1 protected double can never be swapped for a base-3 triple.
      board <- as.integer(layout$base_role[round_index])
      n_outcomes <- as.integer(layout$n_outcomes[round_index])
      current_fixture <- as.character(layout$fixture_id[round_index])
      current_mask <- sort(as.character(layout$allowed_outcomes[[round_index]]))
      alternatives <- ranked[as.integer(ranked$base_role) == board &
                               as.integer(ranked$n_outcomes) == n_outcomes, ,
                             drop = FALSE]
      alternatives <- alternatives[order(alternatives$fixture_id, alternatives$selection_id), , drop=FALSE]
      for (k in seq_len(nrow(alternatives))) {
        layout <- best_pool$legs[as.character(best_pool$legs$group_id) == group_id, , drop=FALSE]
        layout <- layout[order(layout$round), , drop=FALSE]
        current_fixture <- as.character(layout$fixture_id[round_index])
        current_mask <- sort(as.character(layout$allowed_outcomes[[round_index]]))
        candidate_fixture <- as.character(alternatives$fixture_id[k])
        proposed <- sort(.parlay_ranked_mask(alternatives$outcomes[[k]]))
        if (candidate_fixture == current_fixture && identical(proposed, current_mask)) next
        if (candidate_fixture %in% as.character(layout$fixture_id[-round_index])) next
        evaluations <- evaluations + 1L
        moved <- .parlay_ranked_replace_leg(
          best_pool, group_id, layout, round_index, candidate_fixture, board,
          n_outcomes, group_budget_cny, budget_cny, reuse_policy, overlap_policy,
          selection_id=alternatives$selection_id[k])
        candidate_ledger <- .parlay_ranked_evaluate_ledger(
          unique(as.character(moved$fund$purchases$ticket_id)), moved$pool, moved$fund)
        if (candidate_ledger$coverage > best_coverage + 1e-12) {
          changes <- dplyr::bind_rows(changes, tibble::tibble(
            group_id=group_id, round=as.integer(layout$round[round_index]),
            fixture_id=current_fixture, base_role=board, n_outcomes=n_outcomes,
            old_fixture_id=current_fixture, new_fixture_id=candidate_fixture,
            old_mask=paste(current_mask,collapse=","),
            new_mask=paste(proposed,collapse=","),
            coverage_before=as.numeric(best_coverage),
            coverage_after=as.numeric(candidate_ledger$coverage),
            delta=as.numeric(candidate_ledger$coverage-best_coverage)))
          best_coverage <- candidate_ledger$coverage
          best_fund <- moved$fund
          best_pool <- moved$pool
          accepted <- accepted + 1L
        }
      }
    }
  }
  list(pool = best_pool, fund = best_fund, changes = changes, evaluations = as.integer(evaluations),
       accepted = as.integer(accepted))
}

#' Re-fund the pool with one group leg replaced by a same-role fixture
#'
#' Internal. Rebuilds the pool legs so one (group, round) leg points at a different
#' fixture with the SAME actual role and carries that fixture's own authoritative
#' ranked mask. The target role, round position and the group's actual pattern are
#' preserved; nothing is upgraded and no mask is invented. The rebuilt pool is
#' re-validated against the ranked directions and then re-funded by the full walk,
#' so reuse/overlap, cost, de-duplication and cutoffs are re-applied.
#' @param pool Validated pool list.
#' @param group_id Group to move.
#' @param block The group's legs, ordered by round.
#' @param round_index 1-based position of the leg inside the group.
#' @param fixture_id Replacement fixture.
#' @param base_role The leg's base_role board, which the replacement must match.
#' @param n_outcomes The leg's realized outcome count, which the replacement must
#'   match so the group's actual structure is preserved exactly.
#' @param selection_id Authoritative direction id for the replacement fixture.
#' @param group_budget_cny Validated per-group budget or `NULL`.
#' @param budget_cny Validated total budget or `NULL`.
#' @param reuse_policy Validated reuse policy.
#' @param overlap_policy Validated overlap policy.
#' @return A list(pool = the moved pool, fund = its funding walk result).
#' @noRd
.parlay_ranked_replace_leg <- function(pool, group_id, block, round_index,
                                       fixture_id, base_role, n_outcomes,
                                       group_budget_cny, budget_cny,
                                       reuse_policy, overlap_policy,
                                       selection_id = 1L) {
  ranked <- pool$ranked_selections
  mask_row <- ranked[as.character(ranked$fixture_id) == fixture_id &
                       as.integer(ranked$selection_id) == selection_id, ,
                     drop = FALSE]
  if (nrow(mask_row) != 1L ||
      as.integer(mask_row$base_role[[1L]]) != base_role ||
      as.integer(mask_row$n_outcomes[[1L]]) != n_outcomes) {
    stop("parlay_evaluate_portfolio: replacement fixture ", fixture_id,
         " has no unique ranked base-role-", base_role, ", n_outcomes-",
         n_outcomes, " selection")
  }
  codes <- sort(.parlay_ranked_mask(mask_row$outcomes[[1L]]))
  moved <- pool
  rows <- which(as.character(moved$legs$group_id) == group_id)
  rows <- rows[order(moved$legs$round[rows])]
  target <- rows[round_index]
  moved$legs$fixture_id[target] <- fixture_id
  moved$legs$selection_id[target] <- as.integer(selection_id)
  moved$legs$allowed_outcomes[[target]] <- codes
  wide <- parlay_probability_wide(moved$probabilities)
  row <- wide[wide$fixture_id == fixture_id, , drop = FALSE]
  if (nrow(row) != 1L) {
    stop("parlay_evaluate_portfolio: replacement fixture ", fixture_id,
         " has no unique probability row")
  }
  moved$legs$retained_probability[target] <- sum(as.numeric(row[1, codes]))
  # The moved group's legs must still be exactly n_legs rows over the SAME realized
  # board pattern and outcome counts, with unique fixtures and masks the ranking
  # produced.
  moved_block <- moved$legs[rows, , drop = FALSE]
  moved_block <- moved_block[order(moved_block$round), , drop = FALSE]
  if (anyDuplicated(as.character(moved_block$fixture_id))) {
    stop("parlay_evaluate_portfolio: replacement repeats a fixture inside group ",
         group_id)
  }
  if (!identical(as.integer(moved_block$base_role), as.integer(block$base_role)) ||
      !identical(as.integer(moved_block$n_outcomes),
                 as.integer(block$n_outcomes))) {
    stop("parlay_evaluate_portfolio: replacement must preserve the actual pattern")
  }
  .parlay_ranked_validate_masks(moved_block, moved$ranked_selections,
                                moved$probabilities, group_id)
  list(pool = moved,
       fund = .parlay_ranked_fund(moved, group_budget_cny, budget_cny,
                                  reuse_policy, overlap_policy))
}

#' Typed-empty accepted-change table
#' @return A typed-empty changes tibble.
#' @noRd
.parlay_ranked_empty_changes <- function() {
  tibble::tibble(group_id = character(0), round = integer(0),
                 fixture_id = character(0), base_role = integer(0),
                 n_outcomes = integer(0),
                 old_fixture_id = character(0), new_fixture_id = character(0),
                 old_mask = character(0), new_mask = character(0),
                 coverage_before = numeric(0), coverage_after = numeric(0),
                 delta = numeric(0))
}

# --- exported entry point ----------------------------------------------------

#' Evaluate a ranked role candidate pool into a funded delivery plan
#'
#' Successor to the obsolete score-table evaluator (#537). It consumes the ranked
#' candidate pool from [parlay_construct_role_groups()] and performs the bounded,
#' deterministic funding walk described in the file header: per-group enumeration
#' inside the authoritative mask, nominal priority by legal top-N mass, admission
#' under explicit reuse/overlap policies, physical-ticket de-duplication with
#' down-rank continuation, and ACTUAL coverage recomputed from the owned tickets.
#'
#' @param portfolio Ranked candidate pool from [parlay_construct_role_groups()]. Its
#'   embedded cutoff, hashes, ranked-selection receipt, masks, group patterns and
#'   substitutions are all re-validated; a tampered leg, mask, rank, hash or cutoff
#'   fails closed.
#' @param budget_cny Total decision budget in CNY, or `NULL` (default) for
#'   unlimited. A finite value is used in whole ticket units; a zero or sub-unit
#'   budget buys nothing and consumes no constraint. With `NULL`, `unspent_cny` is
#'   `NA_real_`, never a fake zero.
#' @param group_budget_cny Per-group budget in CNY, default `256`. `NULL` means the
#'   group buys its FULL legal support space; otherwise the cap is the smaller of
#'   the given amount and the group's full-support cost, floored to whole units.
#' @param reuse_policy Named list with exactly `max_reuse`: a single positive whole
#'   number, or `NULL` for unlimited. It governs every actual fixture in every
#'   actual group; there is no role exemption.
#' @param overlap_policy Named list with exactly `max_overlap`: a single
#'   non-negative whole number, or `NULL` for unlimited pairwise overlap. A fixture
#'   that is a role-3 leg in BOTH compared groups is exempt from the count; every
#'   other shared fixture counts.
#' @param improve Logical scalar (default `TRUE`). `TRUE` runs the bounded
#'   improvement stage over legal single-fixture replacements inside the admitted
#'   groups: a leg may take a different fixture whose authoritative ranked
#'   selection carries the SAME `base_role` board and the SAME `n_outcomes`
#'   realized count, keeping that fixture's own ranked mask and the group's actual
#'   pattern, respecting within-group fixture uniqueness and re-applying every
#'   reuse/overlap, cost and de-duplication rule. A move is accepted only for a
#'   strict whole-portfolio union-coverage gain. `FALSE` returns the unimproved walk
#'   with a typed-empty `changes` table.
#'
#' @return A named list:
#'   * `summary` -- actual selected group count, new ticket count, spent cash,
#'     `unspent_cny` (`NA_real_` under an unlimited total budget), nominal and
#'     ACTUAL union coverage, and a nullable EV availability flag;
#'   * `group_selection` -- one row per candidate group in the initial nominal
#'     order with its target/actual pattern, nominal and actual coverage, tickets
#'     and spend;
#'   * `purchases` -- the actual purchase ledger (one row per owned physical
#'     ticket, charged exactly once);
#'   * `funded_ledger` -- the ledger joined to its group attribution;
#'   * `rejections` -- every refused candidate with its exact reason
#'     (`no_new_tickets`, `reuse_cap_exceeded`, `overlap_cap_exceeded`);
#'   * `selection` -- the full per-candidate audit including `nominal_coverage`,
#'     `actual_coverage` and `reason`;
#'   * `changes` -- accepted improvement moves, one row per accepted single-fixture
#'     replacement (`old_fixture_id`/`new_fixture_id`, the leg's authoritative
#'     masks, and the exact union coverage before/after); typed-empty when
#'     `improve = FALSE`;
#'   * `plan` -- the frozen plan consumable by [parlay_settle_plan()];
#'   * `tickets` -- the per-ticket table of the actual purchases;
#'   * `diagnostics`, `receipt`, `cutoff`, `initial`, `final` -- provenance and the
#'     source-pool vs improved views, preserved separately without hidden mutation.
#'
#' @section Protective variants are selectable, never mandatory:
#' A protected double (a base-1 variant that retains two outcomes) is an ordinary
#' selectable candidate. It is never forced into a pair and no group owes a
#' complement: the walk simply buys the rank-ordered tickets of each admitted group
#' under the explicit budget, reuse and overlap policies. All protective variants
#' whose third outcome probability is strictly above `0.20` are eligible,
#' regardless of which outcome is third (the obsolete draw-only rule is deleted).
#' A group's own purchases are what realize its coverage; nothing is back-filled
#' from another group or from a label.
#'
#' @section Provenance:
#' The receipt binds the exact input hashes (portfolio, ranked selections,
#' probabilities, pre-match SP, settings), the resolved policies and budgets, the
#' embedded cutoff and a transitive code hash. Nothing is fitted, no EV parameter
#' is learned and the `portfolio` argument is never mutated.
#' @examples
#' cutoff <- list(issue_id = "26098",
#'                cutoff_utc = as.POSIXct("2026-09-26 12:00:00", tz = "UTC"))
#' matches <- tibble::tibble(
#'   fixture_id = c("A", "B", "C", "D"),
#'   win = c(0.45, 0.40, 0.50, 0.30),
#'   draw = c(0.27, 0.30, 0.30, 0.30),
#'   lose = c(0.28, 0.30, 0.20, 0.40))
#' ranked <- rank_outcome_selections(prepare_outcome_selections(matches), cutoff)
#' settings <- parlay_settings()
#' settings$n_legs <- 2L
#' pool <- parlay_construct_role_groups(ranked, settings, pattern = c(3L, 2L),
#'                                      max_candidates = 2L)
#' evaluation <- parlay_evaluate_portfolio(
#'   pool, group_budget_cny = 4, budget_cny = 8,
#'   reuse_policy = list(max_reuse = 1L),
#'   overlap_policy = list(max_overlap = 0L), improve = FALSE)
#' evaluation$summary
#' @export
parlay_evaluate_portfolio <- function(portfolio, budget_cny = NULL,
                                      group_budget_cny = 256, reuse_policy,
                                      overlap_policy, improve = TRUE) {
  pool <- .parlay_ranked_validate_pool(portfolio)
  checkmate::assert_flag(improve, .var.name = "improve")
  budget_cny <- .parlay_role_validate_budget(budget_cny, "budget_cny")
  group_budget_cny <- .parlay_role_validate_budget(group_budget_cny,
                                                   "group_budget_cny")
  reuse <- .parlay_ranked_validate_reuse_policy(reuse_policy)
  overlap <- .parlay_ranked_validate_overlap_policy(overlap_policy)

  fund <- .parlay_ranked_fund(pool, group_budget_cny, budget_cny, reuse, overlap)
  initial_summary <- .parlay_ranked_summary(fund, pool, budget_cny,
                                            group_budget_cny)
  improvement <- .parlay_ranked_improve(pool, fund, group_budget_cny, budget_cny,
                                        reuse, overlap, improve)
  best <- improvement$fund
  final_pool <- improvement$pool
  final_summary <- .parlay_ranked_summary(best, final_pool, budget_cny,
                                          group_budget_cny)
  frozen_plan <- .parlay_ranked_freeze(final_pool, best, best$purchases, budget_cny,
                                      reuse, overlap)
  receipt <- list(
    plan_hash = rlang::hash(frozen_plan),
    cutoff = pool$cutoff, issue_id = as.character(pool$cutoff$issue_id),
    cutoff_hash = pool$cutoff_hash, portfolio_hash = rlang::hash(portfolio),
    final_role_legs_hash = rlang::hash(final_pool$legs),
    final_purchase_hash = rlang::hash(best$purchases),
    construction_code_hash = portfolio$construction_code_hash,
    ranked_selections_hash = rlang::hash(pool$ranked_selections),
    probability_hash = rlang::hash(pool$probabilities),
    prematch_sp_hash = rlang::hash(pool$prematch_sp),
    settings_hash = rlang::hash(pool$settings),
    code_hash = .rank_outcome_code_hash(roots = c(
      "parlay_construct_role_groups", "parlay_evaluate_portfolio")),
    budget_cny = budget_cny, group_budget_cny = group_budget_cny,
    reuse_policy = reuse, overlap_policy = overlap, improve = improve,
    objective = "coverage",
    # The only overlap concession is an ACTUAL shared triple (all three outcomes
    # selected in BOTH groups); it is keyed on the realized outcome combination, not
    # on base_role. Protective variants are selectable and never mandatory, so no
    # complement obligation is recorded.
    overlap_exemption = "shared_actual_triple_only",
    sp_policy = "raw pre-match SP; no >10 replacement; missing SP leaves EV NA")
  diagnostics <- list(
    objective = "coverage",
    objective_basis = "exact probability that at least one owned physical ticket wins",
    group_order = "initial nominal legal-topN mass, descending; stable group_id tie",
    dynamic_resort = FALSE,
    dedup_identity = "physical ticket (fixture, outcome) pairs",
    ev_available = final_summary$summary$ev_available,
    unspent_cny = final_summary$summary$unspent_cny,
    planned_groups = as.integer(nrow(fund$nominal)),
    evaluations = improvement$evaluations,
    accepted_moves = improvement$accepted,
    improvement_enabled = isTRUE(improve))
  list(portfolio = portfolio,
       summary = final_summary$summary,
       group_selection = final_summary$group_selection,
       purchases = best$purchases,
       funded_ledger = best$purchases,
       rejections = best$rejections,
       selection = best$selection,
       changes = improvement$changes,
       plan = frozen_plan,
       tickets = best$purchases,
       diagnostics = diagnostics, receipt = receipt, cutoff = pool$cutoff,
       initial = list(summary = initial_summary$summary,
                      group_selection = initial_summary$group_selection,
                      purchases = fund$purchases, selection = fund$selection,
                      rejections = fund$rejections),
       final = list(role_legs = final_pool$legs,
                    summary = final_summary$summary,
                    group_selection = final_summary$group_selection,
                    purchases = best$purchases, selection = best$selection,
                    rejections = best$rejections))
}
