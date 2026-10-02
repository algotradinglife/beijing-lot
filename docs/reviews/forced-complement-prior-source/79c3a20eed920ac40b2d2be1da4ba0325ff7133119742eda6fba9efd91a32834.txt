# Block 8: budget-derived group count -- budget state, candidate generation,
# coverage frontier and constrained portfolio allocation.
#
# This module implements stages 1-4 of
# docs/strategy/block8-budget-allocation-contract.md. It performs no scraping,
# persistence or historical fitting. Every decision-facing entry point receives an
# explicit cutoff and reuses the authoritative contracts, chronology, identity,
# structure, ticket-enumeration and valuation helpers rather than cloning their
# temporal logic. All tables are validated tibbles; empty results keep their full
# column set and types.
#
# Vocabulary used throughout:
#   * physical ticket  -- one fixture/outcome combination; a ticket_id is shared by
#     every structure over the same fixture set, so it can only be bought once.
#   * group            -- a fixture set (group_id is its canonical identity).
#   * candidate        -- one structure applied over one group (candidate_id carries
#     both); several candidates may share a group and therefore share tickets.

#' Derive the affordable issue budget state for one decision
#'
#' Computes what this issue may still spend at the decision instant. The issue cap
#' comes from the explicit `settings$issue_budget_cny`; the prior ledger is the same
#' paired purchases/fixture_sets history every other decision-facing stage consumes,
#' so chronology and issue identity are validated once, by the authoritative helper,
#' instead of being re-derived here. Spending rounds DOWN to whole units: a balance
#' that cannot buy a ticket buys zero, never a partial one. The optional
#' `spend_limit_cny` is a per-decision ceiling that can only LOWER what is available;
#' it never raises the issue balance.
#'
#' @param settings Complete explicit settings snapshot from `parlay_settings()`; its
#'   `issue_budget_cny` is the issue cap and its `unit_cny` the per-ticket cost.
#' @param prior_purchases Prior history for the SAME issue: the `history` object
#'   returned by an earlier decision, or `list(purchases=, fixture_sets=)`. NULL
#'   means the issue has no prior purchases.
#' @param cutoff Explicit cutoff object with a single UTC `cutoff_utc` and one
#'   `issue_id`. Prior purchases must be strictly before it and belong to the same
#'   issue.
#' @param spend_limit_cny Optional single nonnegative CNY ceiling for this decision.
#'   NULL (default) means no additional cap. A value above the remaining issue
#'   balance is clamped down to it, never the other way round.
#' @return A one-row tibble(issue_id, issue_budget_cny, spent_before_cny,
#'   remaining_cny, available_cny, affordable_units, unit_cny). `remaining_cny` is
#'   the issue balance after prior spend; `available_cny` additionally honours
#'   `spend_limit_cny`; `affordable_units` is `floor(available_cny / unit_cny)`.
#' @details Prior overspending is an ERROR, not a reported negative: a ledger whose
#'   spend exceeds the issue cap is invalid historical state (it cannot have been
#'   produced by this contract), and admitting it would silently spend a budget the
#'   issue never had. The check is against the explicit `issue_budget_cny` cap, so a
#'   legitimately exhausted issue (spent == cap) still yields a valid zero-unit row
#'   with `remaining_cny = 0`. A prior purchase from another issue, or one made at or
#'   after the cutoff, is an error from the shared binding helper.
parlay_budget_state <- function(settings, prior_purchases, cutoff,
                                spend_limit_cny = NULL) {
  parlay_validate_settings(settings)
  match_require_cutoff(cutoff)
  prior <- parlay_validate_prior_state(prior_purchases)
  # Reuse the one authoritative pairing check: issue identity, strict chronology and
  # fixture-set leg width. Reproducing those comparisons here would let them drift
  # from the binding every other stage enforces.
  .ValidatePriorBinding(prior, cutoff, list(settings = settings))

  issue_budget_cny <- as.numeric(settings$issue_budget_cny)
  unit_cny <- as.numeric(settings$unit_cny)
  purchases <- prior$purchases
  spent_before_cny <- if (is.null(purchases)) 0 else sum(purchases$stake_cny)
  # Invalid historical overspending is rejected at the boundary. Reporting a negative
  # balance would let a caller floor it to zero and spend against a breached cap.
  if (spent_before_cny > issue_budget_cny) {
    stop("parlay_budget_state: prior purchases for issue '", cutoff$issue_id,
         "' already spent ", format(spent_before_cny), " CNY, which exceeds the ",
         "issue cap of ", format(issue_budget_cny),
         " CNY; refusing to derive a budget from invalid history")
  }
  remaining_cny <- issue_budget_cny - spent_before_cny

  if (is.null(spend_limit_cny)) {
    available_cny <- max(remaining_cny, 0)
  } else {
    checkmate::assert_numeric(spend_limit_cny, len = 1L, any.missing = FALSE,
                              finite = TRUE, lower = 0,
                              .var.name = "spend_limit_cny")
    # A per-decision cap is a ceiling, not an increase: min() is what stops a caller
    # from spending past the issue balance by naming a larger limit.
    available_cny <- max(min(remaining_cny, as.numeric(spend_limit_cny)), 0)
  }
  affordable_units <- as.integer(floor(available_cny / unit_cny))

  tibble::tibble(
    issue_id = as.character(cutoff$issue_id),
    issue_budget_cny = issue_budget_cny,
    spent_before_cny = as.numeric(spent_before_cny),
    remaining_cny = as.numeric(remaining_cny),
    available_cny = as.numeric(available_cny),
    affordable_units = affordable_units,
    unit_cny = unit_cny)
}

# --- stage 2: bounded candidate generation -----------------------------------

#' Choose up to `max_candidates` fixture sets from a bounded fixture pool
#'
#' Builds candidate groups from the eligible fixture slate under a bounded search.
#' Eligible fixtures are those that survive the shared, cutoff-aware status selection;
#' group identity is the canonical sorted fixture set, so two different enumeration
#' paths cannot produce the same group twice. When the number of distinct
#' `n_legs`-fixture sets can be enumerated exhaustively (`choose(n, n_legs)` at most
#' `max_candidates`) every set is examined. Otherwise a bounded, deterministically
#' seeded sample of distinct sets is drawn with base-R combinatrics; the RNG state of
#' the caller is saved and restored, so the draw is reproducible and side-effect free.
#' There is no purchased group count: `max_candidates` bounds the SEARCH, and how many
#' groups are ultimately funded is an output of stage 4.
#'
#' @param projected Probability projection from `estimate_match_probabilities()`. Its
#'   cutoff, fixtures, probabilities and match_status are re-validated here; a
#'   hand-assembled projection whose cutoff names another issue is refused.
#' @param settings Complete explicit settings snapshot from `parlay_settings()`; its
#'   `n_legs` fixes the candidate width and `unit_cny`/`issue_budget_cny` are reported
#'   as context only.
#' @param construction_policy Explicit list with `max_candidates` (positive integer
#'   search bound) and `seed` (integer scalar). Extra fields are refused rather than
#'   ignored so a misspelled bound cannot silently fall back to a default.
#' @return A named list:
#'   * `group_legs` -- validated group_legs tibble of the constructed groups;
#'   * `diagnostics` -- one-row tibble(n_eligible, n_legs, theoretical_count,
#'     max_candidates, examined_count, exhaustive, incomplete_search) describing the
#'     search honestly. `incomplete_search` is TRUE exactly when the theoretical
#'     space exceeds the examined bound.
#' @details Theoretical count is `choose(n_eligible, n_legs)`, which counts distinct
#'   fixture sets: eligible sets may overlap (a fixture may appear in several groups),
#'   and canonical identity deduplicates them. Fewer than `n_legs` eligible fixtures
#'   yields a typed-empty `group_legs` and a zero-count diagnostic, not an error.
#'   This bounded baseline makes no global-optimality claim.
parlay_generate_candidates <- function(projected, settings, construction_policy) {
  context <- parlay_projection_context(projected)
  cutoff <- context$cutoff
  parlay_validate_settings(settings)
  checkmate::assert_list(construction_policy, names = "unique",
                         .var.name = "construction_policy")
  allowed <- c("max_candidates", "seed")
  unknown <- setdiff(names(construction_policy), allowed)
  if (length(unknown)) {
    stop("parlay_generate_candidates: unknown construction_policy field(s) ",
         paste(unknown, collapse = ", "), "; allowed fields are ",
         paste(allowed, collapse = ", "))
  }
  missing_fields <- setdiff(allowed, names(construction_policy))
  if (length(missing_fields)) {
    stop("parlay_generate_candidates: construction_policy is missing ",
         paste(missing_fields, collapse = ", "))
  }
  max_candidates <- construction_policy$max_candidates
  checkmate::assert_count(max_candidates, positive = TRUE,
                          .var.name = "construction_policy$max_candidates")
  seed <- construction_policy$seed
  checkmate::assert_int(seed, .var.name = "construction_policy$seed")
  n_legs <- as.integer(settings$n_legs)

  diagnostics_template <- function(n_eligible, theoretical, examined, exhaustive,
                                   incomplete) {
    tibble::tibble(
      n_eligible = as.integer(n_eligible),
      n_legs = as.integer(n_legs),
      theoretical_count = as.numeric(theoretical),
      max_candidates = as.integer(max_candidates),
      examined_count = as.integer(examined),
      exhaustive = exhaustive,
      incomplete_search = incomplete)
  }

  # Eligibility is decided by the one shared selector, under this exact cutoff. It
  # is the same admission fixtures enter group construction through, so a fixture
  # that is not visible as scheduled here can never be grouped.
  selection <- match_select_status(projected$fixtures, projected$match_status, cutoff)
  eligible_fixtures <- selection$fixtures
  # Selecting status is not enough: the same decision-window admission the old
  # parlay_construct_groups() applies must hold here too, or a fixture that has
  # already kicked off or lies outside [cutoff+4h, cutoff+28h) would be grouped and
  # bought. The window boundary arithmetic comes from the shared helper.
  .ValidateCandidateFixtures(eligible_fixtures, cutoff)
  wide <- parlay_probability_wide(projected$probabilities)
  eligible_ids <- intersect(eligible_fixtures$fixture_id, wide$fixture_id)
  n_eligible <- length(eligible_ids)

  if (n_eligible < n_legs) {
    return(list(
      group_legs = match_typed_empty("group_legs"),
      diagnostics = diagnostics_template(n_eligible, 0, 0L, TRUE, FALSE)))
  }

  theoretical <- choose(n_eligible, n_legs)
  # Exhaustive when the whole space fits the declared bound. choose() returns a
  # double, so the comparison is safe for large slates instead of overflowing an
  # integer product.
  exhaustive <- theoretical <= max_candidates
  if (exhaustive) {
    # Deterministic, complete: every distinct fixture set is examined in a stable
    # lexicographic order over the eligible fixture ids.
    sets <- utils::combn(sort(eligible_ids), n_legs, simplify = FALSE)
    examined <- length(sets)
  } else {
    # Bounded deterministic sample. The caller's RNG state is saved and restored so
    # this search cannot perturb any other stochastic step in the session.
    sets <- .SampleDistinctFixtureSets(eligible_ids, n_legs, max_candidates, seed)
    examined <- length(sets)
  }

  # Canonical group identity deduplicates sets that differ only by enumeration order.
  group_ids <- vapply(sets, parlay_group_identity, character(1))
  keep <- !duplicated(group_ids)
  sets <- sets[keep]
  examined <- length(sets)

  rows <- list()
  for (set_index in seq_along(sets)) {
    members <- as.character(sets[[set_index]])
    group_id <- group_ids[keep][set_index]
    for (order_index in seq_along(members)) {
      rows[[length(rows) + 1L]] <- tibble::tibble(
        group_id = group_id, fixture_id = members[order_index],
        leg_order = as.integer(order_index))
    }
  }
  group_legs <- if (length(rows)) {
    match_validate_table(dplyr::bind_rows(rows), "group_legs")
  } else {
    match_typed_empty("group_legs")
  }
  list(group_legs = group_legs,
       diagnostics = diagnostics_template(n_eligible, theoretical, examined,
                                          exhaustive, !exhaustive))
}

#' Validate candidate fixtures against issue identity and the decision window
#'
#' Internal admission check shared by [parlay_generate_candidates()] and
#' [parlay_coverage_frontier()]. It never re-derives chronology: the window
#' boundaries come from the shared [match_decision_window()] and the elapsed-hour
#' rule is the half-open interval `[cutoff + 4h, cutoff + 28h)`, exactly as the
#' authoritative `parlay_construct_groups()` admits fixtures. A fixture that has
#' already kicked off at the cutoff, belongs to another issue, or falls outside the
#' window is refused rather than silently grouped and bought.
#'
#' @param fixtures Validated fixtures tibble, already selected by
#'   [match_select_status()] under the same cutoff.
#' @param cutoff Explicit cutoff object validated by [match_require_cutoff()].
#' @return The input `fixtures` invisibly; any violation raises an error.
#' @noRd
.ValidateCandidateFixtures <- function(fixtures, cutoff) {
  if (!nrow(fixtures)) return(invisible(fixtures))
  if ("issue_id" %in% names(fixtures)) {
    stray <- setdiff(unique(as.character(fixtures$issue_id)),
                     as.character(cutoff$issue_id))
    if (length(stray)) {
      stop("parlay_generate_candidates: fixtures belong to issue(s) ",
           paste(stray, collapse = ", "), ", not ", cutoff$issue_id)
    }
  }
  if ("kickoff_at" %in% names(fixtures)) {
    cutoff_bound <- match_cutoff_utc(cutoff)
    if (any(fixtures$kickoff_at <= cutoff_bound)) {
      stop("parlay_generate_candidates: fixtures already kicked off at the cutoff ",
           "are not eligible")
    }
    # Subsecond boundaries stay identical to input preparation because the elapsed
    # hours are added by the shared window helper, not recomputed here.
    window <- match_decision_window(cutoff_bound)
    outside <- fixtures$kickoff_at < window$start_utc |
      fixtures$kickoff_at >= window$end_utc
    if (any(outside)) {
      stop("parlay_generate_candidates: fixture(s) outside the decision window ",
           window$start_utc, " to ", window$end_utc, " are not eligible")
    }
  }
  invisible(fixtures)
}

#' Draw a bounded sample of distinct n_legs-fixture sets without perturbing caller RNG
#'
#' Internal helper for [parlay_generate_candidates()]. Uses base-R sampling only. The
#' session RNG state is captured before and restored after, so the draw is
#' reproducible for a fixed `seed` and does not mutate the caller's random stream.
#'
#' @param eligible_ids Character vector of eligible fixture identifiers.
#' @param n_legs Positive whole number of fixtures per set.
#' @param count Positive whole number of distinct sets to draw.
#' @param seed Integer scalar seed for the deterministic draw.
#' @return A list of character vectors, each of length `n_legs`, deduplicated by
#'   canonical set identity and sorted internally so identity is enumeration-order
#'   independent.
#' @noRd
.SampleDistinctFixtureSets <- function(eligible_ids, n_legs, count, seed) {
  pool <- sort(unique(as.character(eligible_ids)))
  # Preserve the caller's stream: set.seed() below must be undone. If the session
  # has no RNG state yet, .Random.seed does not exist and restoring must not create
  # one spuriously.
  had_seed <- exists(".Random.seed", envir = globalenv(), inherits = FALSE)
  old_seed <- if (had_seed) get(".Random.seed", envir = globalenv(), inherits = FALSE) else NULL
  on.exit({
    if (had_seed) {
      assign(".Random.seed", old_seed, envir = globalenv())
    } else if (exists(".Random.seed", envir = globalenv(), inherits = FALSE)) {
      rm(".Random.seed", envir = globalenv())
    }
  }, add = TRUE)

  set.seed(seed)
  collected <- list()
  seen <- new.env(parent = emptyenv())
  # Draw sets independently; the space exceeds the bound so collisions are possible,
  # and a bounded number of attempts keeps the search finite. Each accepted set is
  # canonicalised so two draws of the same fixtures are one set.
  attempts <- 0L
  max_attempts <- as.integer(count) * 20L + 100L
  while (length(collected) < count && attempts < max_attempts) {
    attempts <- attempts + 1L
    draw <- sort(sample(pool, n_legs, replace = FALSE))
    key <- paste(draw, collapse = "\r")
    if (exists(key, envir = seen, inherits = FALSE)) next
    assign(key, TRUE, envir = seen)
    collected[[length(collected) + 1L]] <- draw
  }
  collected
}

# --- stage 3: coverage frontier ----------------------------------------------

#' Build per-candidate coverage frontiers over the legal support space
#'
#' Applies each structure in `patterns` to `group_legs` (reusing the role-based
#' structure assignment), enumerates the resulting physical tickets, values them with the
#' existing pre-cutoff-SP transform and ranks them. The frontier is the DEPTH curve
#' of each candidate: buying the top-k ranked tickets of a candidate gives depth `k`,
#' with cumulative probability equal to the sum of those tickets' unconditional
#' masses and cumulative EV equal to the sum of their net EVs. Depth 0 is always
#' present (buy nothing: zero cost, zero cumulative probability, zero EV).
#'
#' @param projected Probability projection from `estimate_match_probabilities()`. Its
#'   cutoff, fixtures, probabilities, prematch_sp and match_status are re-validated
#'   here, so the frontier is bound to the same instant and slate as the projection.
#' @param group_legs Validated group_legs tibble of candidate fixture sets.
#' @param patterns Named list of `n_legs`-long integer vectors (each value 1, 2 or 3):
#'   the legal mask per structure. Legal masks are IMMUTABLE here; budget truncation
#'   happens in stage 4, never by shrinking a mask.
#' @param settings Complete explicit settings snapshot; `n_legs`, `unit_cny`,
#'   `payout_factor`, `sp_threshold` and `sp_replacement` drive structure, valuation
#'   and cost.
#' @param policy Explicit list with `min_support_mass` (default 0, uncalibrated),
#'   optional `ranking` ("probability_desc" or "ev_desc"), and optional
#'   `max_depth` (whole nonnegative number; 0 keeps only the depth-0 curve). `min_support_mass` is the minimum total
#'   support mass a candidate must carry to be admitted; candidates below it are
#'   reported in `rejected` rather than silently dropped. `max_depth` truncates the
#'   DEPTH CURVE only -- the legal supports, tickets and ranked space are reported in
#'   full, so budget truncation can never be mistaken for an absent legal mask.
#' @return Named list:
#'   * `candidates`/`supports` -- validated supports tibble (legal masks);
#'   * `tickets`, `ticket_legs`, `candidate_tickets` -- the enumeration tables;
#'   * `ranked` -- validated ranked tibble, one row per candidate/ticket;
#'   * `frontier` -- tibble(candidate_id, group_id, depth, cost_cny,
#'     cumulative_probability, marginal_probability, cumulative_ev_net), one curve
#'     per admitted candidate including depth 0, truncated at `max_depth`;
#'   * `rejected` -- tibble(candidate_id, group_id, support_mass, reason) for
#'     candidates removed by `min_support_mass`;
#'   * `bound` -- one-row tibble(issue_id, cutoff_utc, n_legs, unit_cny,
#'     ranking, max_depth) recording the exact cutoff/settings the frontier was
#'     built against, so a downstream allocator can prove it consumes this artifact
#'     and not one built for another instant, slate or budget.
#' @details Probabilities are UNCONDITIONAL original product masses: the frontier is
#'   never renormalised inside a mask, so a truncated purchase cannot inflate the
#'   reported coverage. EV stays NA when pre-cutoff SP is unavailable for any leg of a
#'   ticket; a candidate whose tickets all have NA EV keeps NA cumulative EV and is
#'   still admitted under a probability policy. No historical labels are read.
parlay_coverage_frontier <- function(projected, group_legs, patterns, settings, policy) {
  context <- parlay_projection_context(projected)
  cutoff <- context$cutoff
  parlay_validate_settings(settings)
  match_validate_table(group_legs, "group_legs")
  checkmate::assert_list(patterns, min.len = 1L, names = "unique",
                         .var.name = "patterns")
  checkmate::assert_list(policy, names = "unique", .var.name = "policy")
  allowed <- c("min_support_mass", "ranking", "max_depth")
  unknown <- setdiff(names(policy), allowed)
  if (length(unknown)) {
    stop("parlay_coverage_frontier: unknown policy field(s) ",
         paste(unknown, collapse = ", "), "; allowed fields are ",
         paste(allowed, collapse = ", "))
  }
  min_support_mass <- policy$min_support_mass %||% 0
  checkmate::assert_numeric(min_support_mass, len = 1L, any.missing = FALSE,
                            finite = TRUE, lower = 0, upper = 1,
                            .var.name = "policy$min_support_mass")
  ranking <- policy$ranking %||% "probability_desc"
  if (!ranking %in% c("probability_desc", "ev_desc")) {
    stop("parlay_coverage_frontier: policy$ranking must be 'probability_desc' or ",
         "'ev_desc', got ", ranking)
  }
  n_legs <- as.integer(settings$n_legs)
  wrong_width <- vapply(patterns, function(p) length(p) != n_legs, logical(1))
  if (any(wrong_width)) {
    stop("parlay_coverage_frontier: every pattern must have ", n_legs,
         " legs; pattern(s) ", paste(which(wrong_width), collapse = ", "),
         " disagree")
  }
  # A directly supplied group_legs must not bypass the same issue, status and
  # decision-window admission the generated path enforces. Status is re-selected by
  # the shared selector under this exact cutoff; the surviving slate is window-checked
  # by the shared helper; and every group leg must be IN that surviving slate. A leg
  # that is not scheduled-and-in-window at this cutoff is an explicit error, never a
  # silently omitted fixture.
  if (nrow(group_legs)) {
    selection <- match_select_status(projected$fixtures, projected$match_status, cutoff)
    .ValidateCandidateFixtures(selection$fixtures, cutoff)
    eligible_ids <- unique(as.character(selection$fixtures$fixture_id))
    absent <- setdiff(unique(as.character(group_legs$fixture_id)), eligible_ids)
    if (length(absent)) {
      stop("parlay_coverage_frontier: group_legs reference fixture(s) not eligible ",
           "at this cutoff: ", paste(absent, collapse = ", "))
    }
  }
  # The depth curve must not claim more tickets than the issue budget can buy. The
  # ceiling is derived from the explicit settings, never from a caller assertion, and
  # it is INDEPENDENT of the legal supports/tickets: masks are immutable.
  budget_units <- floor(as.numeric(settings$issue_budget_cny) /
                          as.numeric(settings$unit_cny))
  if (!is.finite(budget_units) || budget_units < 0) budget_units <- 0
  max_depth <- policy$max_depth %||% budget_units
  # Zero is a legal depth: an issue budget that affords no unit still has a well-formed
  # depth-0 curve (buy nothing), so the ceiling is a whole nonnegative count rather
  # than a positive one.
  checkmate::assert_count(max_depth, .var.name = "policy$max_depth")
  max_depth <- min(as.numeric(max_depth), budget_units)
  # Bound metadata: the frontier is only valid for this cutoff/settings pair, and a
  # consumer validates identity against it instead of trusting a look-alike artifact.
  bound <- tibble::tibble(
    issue_id = as.character(cutoff$issue_id),
    cutoff_utc = cutoff$cutoff_utc,
    n_legs = as.integer(n_legs),
    unit_cny = as.numeric(settings$unit_cny),
    ranking = ranking,
    max_depth = as.integer(max_depth))

  empty_frontier <- tibble::tibble(
    candidate_id = character(0), group_id = character(0), depth = integer(0),
    cost_cny = numeric(0), cumulative_probability = numeric(0),
    marginal_probability = numeric(0), cumulative_ev_net = numeric(0))
  empty_rejected <- tibble::tibble(
    candidate_id = character(0), group_id = character(0), support_mass = numeric(0),
    reason = character(0))

  if (!nrow(group_legs)) {
    return(list(
      candidates = match_typed_empty("supports"), supports = match_typed_empty("supports"),
      tickets = match_typed_empty("tickets"),
      ticket_legs = match_typed_empty("ticket_legs"),
      candidate_tickets = tibble::tibble(candidate_id = character(0),
                                         ticket_id = character(0)),
      ranked = match_typed_empty("ranked"), frontier = empty_frontier,
      rejected = empty_rejected, bound = bound, group_legs = group_legs))
  }

  # One shared structure pass per declared pattern, each with its own candidate label,
  # exactly as the projection path builds them. Legal masks are built once here and
  # never re-derived during truncation.
  structures <- lapply(seq_along(patterns), function(index) {
    label <- paste0("p", paste(patterns[[index]], collapse = ""))
    parlay_apply_structure(group_legs, projected$probabilities, cutoff,
                           patterns[[index]], candidate_label = label)
  })
  supports <- dplyr::bind_rows(lapply(structures, function(s) s$supports))
  support_summary <- dplyr::bind_rows(lapply(structures, function(s) s$support_summary))

  # min_support_mass is applied BEFORE enumeration so a candidate that cannot clear
  # the floor never enters the ranked space. Rejections are reported, never hidden.
  admitted_ids <- character(0)
  rejected_rows <- list()
  if (nrow(support_summary)) {
    for (i in seq_len(nrow(support_summary))) {
      candidate_id <- support_summary$candidate_id[i]
      mass <- support_summary$support_mass[i]
      if (is.finite(mass) && mass >= min_support_mass) {
        admitted_ids <- c(admitted_ids, candidate_id)
      } else {
        rejected_rows[[length(rejected_rows) + 1L]] <- tibble::tibble(
          candidate_id = candidate_id,
          group_id = sub("[|].*$", "", candidate_id),
          support_mass = as.numeric(mass),
          reason = paste0("support_mass ", format(mass), " below min_support_mass ",
                          format(min_support_mass)))
      }
    }
  }
  supports <- supports[supports$candidate_id %in% admitted_ids, , drop = FALSE]
  if (!nrow(supports)) {
    return(list(
      candidates = match_typed_empty("supports"), supports = match_typed_empty("supports"),
      tickets = match_typed_empty("tickets"),
      ticket_legs = match_typed_empty("ticket_legs"),
      candidate_tickets = tibble::tibble(candidate_id = character(0),
                                         ticket_id = character(0)),
      ranked = match_typed_empty("ranked"), frontier = empty_frontier,
      rejected = if (length(rejected_rows)) dplyr::bind_rows(rejected_rows) else empty_rejected,
      bound = bound, group_legs = group_legs))
  }

  tickets <- parlay_enumerate_tickets(group_legs, projected$probabilities, cutoff,
                                      supports, n_legs = n_legs)
  valued <- parlay_value_tickets(tickets$tickets, tickets$ticket_legs,
                                 projected$prematch_sp, cutoff,
                                 settings$sp_threshold, settings$sp_replacement,
                                 settings$unit_cny, settings$payout_factor)
  ranked <- parlay_rank_tickets(valued, tickets$candidate_tickets, cutoff, ranking)

  # Depth curves. ranked is already ordered by descending score with deterministic
  # ticket_id tie-breaks, so rank d is exactly the d-th ticket bought. cumulative_*
  # sums unconditional mass / net EV over bought tickets; cumulative EV stays NA if
  # any bought ticket has NA EV under a probability policy (partial pricing must not
  # masquerade as zero EV). The curve is truncated at max_depth -- the affordable
  # issue-budget ceiling -- while supports/tickets/ranked above stay complete.
  frontier_rows <- list()
  if (nrow(ranked)) {
    for (candidate_id in unique(ranked$candidate_id)) {
      block <- ranked[ranked$candidate_id == candidate_id, , drop = FALSE]
      block <- block[order(block$rank), , drop = FALSE]
      # Canonical identity is taken from the FULL ranked block BEFORE the depth curve
      # is truncated. Truncating to a budget of zero first would leave block with no
      # rows and group_id as NA, so depth 0 would lose the group it belongs to.
      group_id <- block$group_id[1]
      if (nrow(block) > max_depth) block <- block[seq_len(max_depth), , drop = FALSE]
      frontier_rows[[length(frontier_rows) + 1L]] <- tibble::tibble(
        candidate_id = candidate_id, group_id = group_id, depth = 0L,
        cost_cny = 0, cumulative_probability = 0, marginal_probability = 0,
        cumulative_ev_net = 0)
      cum_prob <- 0
      cum_ev <- 0
      ev_na <- FALSE
      for (depth in seq_len(nrow(block))) {
        marginal <- block$probability[depth]
        cum_prob <- cum_prob + marginal
        if (is.na(block$ev_net_est[depth])) ev_na <- TRUE else cum_ev <- cum_ev + block$ev_net_est[depth]
        frontier_rows[[length(frontier_rows) + 1L]] <- tibble::tibble(
          candidate_id = candidate_id, group_id = group_id, depth = as.integer(depth),
          cost_cny = as.numeric(depth) * as.numeric(settings$unit_cny),
          cumulative_probability = cum_prob, marginal_probability = marginal,
          cumulative_ev_net = if (ev_na) NA_real_ else cum_ev)
      }
    }
  }
  frontier <- if (length(frontier_rows)) dplyr::bind_rows(frontier_rows) else empty_frontier

  list(candidates = supports, supports = supports, tickets = valued,
       ticket_legs = tickets$ticket_legs, candidate_tickets = tickets$candidate_tickets,
       ranked = ranked, frontier = frontier,
       rejected = if (length(rejected_rows)) dplyr::bind_rows(rejected_rows) else empty_rejected,
       bound = bound, group_legs = group_legs)
}

# --- stage 4: constrained greedy portfolio allocation ------------------------

#' Allocate the affordable budget across candidate groups
#'
#' Greedy portfolio construction over the frontier produced by
#' [parlay_coverage_frontier()]. Starting from the prior ledger, the loop repeatedly
#' compares the NEXT unique unpurchased ticket of every admissible candidate and buys
#' the one with the highest marginal objective per CNY. A group that is not yet
#' admitted competes with deepening an already-admitted group in the SAME loop, so
#' opening a new fixture set and adding tickets to an existing one are ranked against
#' each other rather than processed in separate passes. The loop stops when the
#' affordable units are exhausted or no admissible candidate has an unpurchased
#' ticket left.
#'
#' @param frontier_result Result of [parlay_coverage_frontier()]; its `ranked`,
#'   `group_legs` and `tickets` tables drive selection and the returned summary.
#' @param group_legs Validated group_legs tibble for the same candidate universe.
#' @param budget_state One-row tibble from [parlay_budget_state()]; its
#'   `affordable_units` is the outer spending ceiling for this decision.
#' @param prior_purchases Prior history for the SAME issue (`list(purchases=,
#'   fixture_sets=)` or NULL). Reuse and overlap constraints INCLUDE these groups, and
#'   their physical tickets can never be bought again.
#' @param cutoff Explicit cutoff object; prior history is re-bound to it.
#' @param constraints Explicit list with `max_reuse` (positive integer) and
#'   `max_overlap` (integer in 0..n_legs). Both are counts over DISTINCT funded
#'   groups, never over tickets.
#' @param objective Either "probability" (expected NUMBER of winning tickets, i.e. the
#'   sum of marginal masses) or "ev" (marginal net EV per ticket, requiring a complete
#'   valid pre-cutoff SP valuation). Any other value errors rather than defaulting.
#' @param frontier_result Result of [parlay_coverage_frontier()]. Its `bound` metadata
#'   is REQUIRED unconditionally: the frontier must declare the exact issue, cutoff
#'   instant, leg width and unit cost it was built against, and every one of those is
#'   compared against this decision and `budget_state`. A missing or disagreeing
#'   binding is refused. There is no bypass flag or optional-settings path: a
#'   hand-built frontier declares the same `bound` contract it would be consumed
#'   under.
#' @return Named list:
#'   * `purchases` -- validated purchases tibble (issue_id, ticket_id, epoch_at,
#'     group_id, candidate_id, stake_cny), typed-empty when nothing is bought;
#'   * `selected` -- one row per funded candidate with group, structure, units, cost,
#'     objective value and selection reason;
#'   * `trace` -- one row per ACTUAL purchase, in selection order, with
#'     (step, candidate_id, group_id, ticket_id, marginal, score_per_cny, action)
#'     where action is "OPEN" for the group's first ticket and "DEEPEN" afterwards;
#'     typed-empty when nothing is bought;
#'   * `history` -- list(purchases=, fixture_sets=) to hand to the next decision;
#'   * `diagnostics` -- list(n_groups, n_candidates, units_bought, cost_cny,
#'     unspent_cny, available_units, objective, objective_basis, rejected).
#'     `objective_basis` states explicitly that a "probability" objective is the
#'     expected COUNT of winning tickets (sum of marginals), NOT a union or a
#'     probability-of-at-least-one figure.
#' @details This is a greedy approximation, NOT a global optimum. The probability
#'   objective is expected ticket COUNT: overlapping group events must not be summed
#'   as a union, so no union-probability or profit claim is made. In EV mode a
#'   nonpositive next marginal is left unspent, which is only sound when the candidate
#'   is ordered by EV; the entries of each candidate are therefore sorted by EV
#'   (descending, ticket_id tie-break) under objective "ev", and a non-EV-ranked
#'   frontier is refused. A probability-ordered frontier re-sorted here would silently
#'   change the greedy order, so the allocator refuses a ranking it did not ask for
#'   rather than picking tickets out of order. Reuse and overlap are counted over
#'   DISTINCT funded groups, never over tickets; additional tickets in an existing
#'   group do not consume another reuse slot, but ONE structure per selected group is
#'   enforced -- a group may only be deepened by the candidate that opened it, and a
#'   different structure over the same fixture set is refused. A physical ticket can
#'   never be purchased twice across candidates or prior history. Ties are broken
#'   deterministically by candidate_id then rank. Zero affordable units, or no
#'   feasible ticket, produces typed-empty outputs rather than an error.
parlay_allocate_portfolio <- function(frontier_result, group_legs, budget_state,
                                      prior_purchases, cutoff, constraints, objective) {
  match_require_cutoff(cutoff)
  if (!is.list(frontier_result) || is.null(frontier_result$ranked)) {
    stop("parlay_allocate_portfolio: frontier_result must be the result of ",
         "parlay_coverage_frontier()")
  }
  match_validate_table(group_legs, "group_legs")
  match_validate_table(frontier_result$ranked, "ranked",
                       keys = c("candidate_id", "ticket_id"))
  # budget_state is a one-row tibble produced by parlay_budget_state(); accept exactly
  # that shape so a hand-made frame cannot smuggle in a different ceiling.
  checkmate::assert_data_frame(budget_state, min.rows = 1L, max.rows = 1L,
                               .var.name = "budget_state")
  required_state <- c("issue_id", "available_cny", "affordable_units", "unit_cny",
                      "spent_before_cny", "issue_budget_cny")
  missing_state <- setdiff(required_state, names(budget_state))
  if (length(missing_state)) {
    stop("parlay_allocate_portfolio: budget_state is missing ",
         paste(missing_state, collapse = ", "))
  }
  if (!identical(as.character(budget_state$issue_id), as.character(cutoff$issue_id))) {
    stop("parlay_allocate_portfolio: budget_state is bound to issue '",
         budget_state$issue_id, "' but the cutoff names '", cutoff$issue_id, "'")
  }
  unit_cny <- as.numeric(budget_state$unit_cny)
  checkmate::assert_numeric(unit_cny, len = 1L, any.missing = FALSE, finite = TRUE,
                            .var.name = "budget_state$unit_cny")
  if (unit_cny <= 0) {
    stop("parlay_allocate_portfolio: budget_state$unit_cny must be positive")
  }
  available_cny <- as.numeric(budget_state$available_cny)
  checkmate::assert_numeric(available_cny, len = 1L, any.missing = FALSE,
                            finite = TRUE, lower = 0,
                            .var.name = "budget_state$available_cny")
  # affordable_units must be a genuine whole nonnegative count, checked instead of
  # coerced: as.integer() would turn 2.7 into 2 or a malformed value into a silent 1.
  affordable_units <- budget_state$affordable_units
  checkmate::assert_numeric(affordable_units, len = 1L, any.missing = FALSE,
                            finite = TRUE, lower = 0,
                            .var.name = "budget_state$affordable_units")
  if (affordable_units != trunc(affordable_units)) {
    stop("parlay_allocate_portfolio: budget_state$affordable_units must be a whole ",
         "number, got ", format(affordable_units))
  }
  affordable_units <- as.integer(affordable_units)
  # Consistency with the stated budget: the affordable count is what remains of
  # available_cny at this unit cost, so it can never exceed floor(available/unit).
  if (affordable_units != floor(available_cny / unit_cny)) {
    stop("parlay_allocate_portfolio: budget_state$affordable_units (",
         affordable_units, ") is inconsistent with available_cny (",
         format(available_cny), ") at unit_cny ", format(unit_cny),
         "; expected ", floor(available_cny / unit_cny))
  }

  # Bind the frontier artifact to THIS cutoff/settings. The `bound` metadata is
  # REQUIRED: without it a frontier built for another instant, width or unit cost
  # would be consumed silently, so a missing binding is an unconditional error.
  .ValidateFrontierBinding(frontier_result, group_legs, cutoff, unit_cny)

  prior <- parlay_validate_prior_state(prior_purchases)
  n_legs <- parlay_structure_legs(group_legs)
  # The prior ledger is bound by the ONE authoritative helper, uniformly. When the
  # candidate universe is empty the leg width is not invented as 1: it comes from the
  # REQUIRED frontier bound, which is the artifact's own declaration of the width it
  # was built for, so a valid 2- or 7-leg prior is not falsely width-rejected.
  if (!nrow(group_legs)) n_legs <- as.integer(frontier_result$bound$n_legs)
  .ValidatePriorBinding(prior, cutoff, list(settings = list(n_legs = n_legs)))

  actual_spent <- if (is.null(prior$purchases)) 0 else sum(prior$purchases$stake_cny)
  checkmate::assert_number(budget_state$issue_budget_cny, lower = 0, finite = TRUE)
  checkmate::assert_number(budget_state$spent_before_cny, lower = 0, finite = TRUE)
  if (budget_state$spent_before_cny != actual_spent) {
    stop("parlay_allocate_portfolio: budget_state spent_before_cny disagrees with prior purchases")
  }
  actual_remaining <- budget_state$issue_budget_cny - actual_spent
  if (actual_remaining < 0 || available_cny > actual_remaining) {
    stop("parlay_allocate_portfolio: available_cny exceeds remaining issue budget")
  }
  if (!"remaining_cny" %in% names(budget_state) ||
      !isTRUE(budget_state$remaining_cny == actual_remaining)) {
    stop("parlay_allocate_portfolio: remaining_cny disagrees with prior purchases")
  }

  checkmate::assert_list(constraints, names = "unique", .var.name = "constraints")
  allowed <- c("max_reuse", "max_overlap")
  unknown <- setdiff(names(constraints), allowed)
  if (length(unknown)) {
    stop("parlay_allocate_portfolio: unknown constraints field(s) ",
         paste(unknown, collapse = ", "), "; allowed fields are ",
         paste(allowed, collapse = ", "))
  }
  missing_fields <- setdiff(allowed, names(constraints))
  if (length(missing_fields)) {
    stop("parlay_allocate_portfolio: constraints is missing ",
         paste(missing_fields, collapse = ", "))
  }
  max_reuse <- constraints$max_reuse
  max_overlap <- constraints$max_overlap
  checkmate::assert_count(max_reuse, positive = TRUE, .var.name = "constraints$max_reuse")
  checkmate::assert_count(max_overlap, .var.name = "constraints$max_overlap")
  if (n_legs > 0L && max_overlap > n_legs) {
    stop("parlay_allocate_portfolio: constraints$max_overlap must not exceed n_legs ",
         n_legs)
  }

  checkmate::assert_string(objective, min.chars = 1L, .var.name = "objective")
  if (!objective %in% c("probability", "ev")) {
    stop("parlay_allocate_portfolio: objective must be 'probability' or 'ev', got ",
         objective)
  }
  ranked <- frontier_result$ranked
  # EV mode needs a COMPLETE valid valuation. Falling back to probability would
  # silently change the stated objective, so a missing EV is a hard error.
  if (identical(objective, "ev") && nrow(ranked) && anyNA(ranked$ev_net_est)) {
    stop("parlay_allocate_portfolio: objective 'ev' requires a complete valid ",
         "pre-cutoff SP valuation; ", sum(is.na(ranked$ev_net_est)), " of ",
         nrow(ranked), " candidate tickets have no EV")
  }
  # EV mode must buy each candidate's tickets in EV order; skipping a nonpositive
  # marginal is only sound when the next unpurchased ticket really is the best
  # remaining one. A probability-ranked frontier re-sorted silently could hide a
  # higher-EV ticket behind a negative one, so the frontier's declared ranking is
  # checked against what the observable rows already satisfy: each candidate's
  # ev_net_est must be non-increasing in `rank`. A ranking mismatch is refused.
  if (identical(objective, "ev") && nrow(ranked)) {
    for (candidate_id in unique(ranked$candidate_id)) {
      block <- ranked[ranked$candidate_id == candidate_id, , drop = FALSE]
      block <- block[order(block$rank), , drop = FALSE]
      if (any(diff(block$ev_net_est) > 0)) {
        stop("parlay_allocate_portfolio: objective 'ev' requires a frontier ranked ",
             "by EV; candidate '", candidate_id, "' has a higher-EV ticket after a ",
             "lower-EV one. Build the frontier with ranking = 'ev_desc'")
      }
    }
  }

  if (identical(objective, "probability") && nrow(ranked)) {
    for (candidate_id in unique(ranked$candidate_id)) {
      block <- ranked[ranked$candidate_id == candidate_id, , drop = FALSE]
      block <- block[order(block$rank), , drop = FALSE]
      if (any(diff(block$probability) > 0)) {
        stop("parlay_allocate_portfolio: probability objective requires probability-ranked tickets")
      }
    }
  }

  empty_purchases <- match_typed_empty("purchases")
  empty_selected <- tibble::tibble(
    candidate_id = character(0), group_id = character(0), structure = character(0),
    units = integer(0), cost_cny = numeric(0), objective_value = numeric(0),
    objective = character(0), reason = character(0))
  # One row per ACTUAL purchase, in the exact order the greedy loop bought them, so
  # the selection path is auditable instead of only its aggregate.
  empty_trace <- tibble::tibble(
    step = integer(0), candidate_id = character(0), group_id = character(0),
    ticket_id = character(0), marginal = numeric(0), score_per_cny = numeric(0),
    action = character(0))

  # Seed admission from prior history: purchases and fixture sets travel together, so
  # prior groups participate in reuse/overlap and their tickets are already committed.
  admitted <- list()
  fixture_sets <- prior$fixture_sets %||% list()
  if (length(fixture_sets)) {
    for (k in seq_along(fixture_sets)) {
      admitted[[length(admitted) + 1L]] <- list(group_id = names(fixture_sets)[k],
                                                fixtures = sort(unique(as.character(fixture_sets[[k]]))))
    }
  }
  prior_purchases_table <- prior$purchases %||% match_typed_empty("purchases")
  selected_ticket_ids <- as.character(prior_purchases_table$ticket_id)

  purchases_rows <- list()
  selected_state <- list()   # keyed by candidate_id: units, cost, objective sum
  trace_rows <- list()
  reason_by_candidate <- character(0)
  units_left <- affordable_units

  if (units_left > 0L && nrow(ranked)) {
    # Each candidate's tickets in rank order. The next unique ticket is the first not
    # yet committed on this issue; a ticket shared by two structures can only be
    # bought once, by whichever candidate reaches it first.
    ticket_index <- list()
    for (candidate_id in unique(ranked$candidate_id)) {
      block <- ranked[ranked$candidate_id == candidate_id, , drop = FALSE]
      ticket_index[[candidate_id]] <- block[order(block$rank), , drop = FALSE]
    }
    cursor <- stats::setNames(rep(0L, length(ticket_index)), names(ticket_index))
    # Which candidate opened each funded group. One structure per selected group: a
    # group may only be deepened by the candidate that opened it, never by a different
    # structure over the same fixture set. Prior groups count as already opened, by
    # their prior candidate where the ledger records one.
    group_opener <- list()
    if (nrow(prior_purchases_table)) {
      for (i in seq_len(nrow(prior_purchases_table))) {
        group_id_i <- prior_purchases_table$group_id[i]
        candidate_i <- as.character(prior_purchases_table$candidate_id[i])
        # A prior group carrying two candidate IDs is ambiguous evidence: the ledger
        # cannot say which structure opened it, so a later deepening cannot be
        # attributed. Choosing the last silently would invent history.
        existing_opener <- group_opener[[group_id_i]]
        if (!is.null(existing_opener) && !identical(existing_opener, candidate_i)) {
          stop("parlay_allocate_portfolio: prior group '", group_id_i,
               "' carries more than one candidate_id ('", existing_opener, "' and '",
               candidate_i, "'); a group must have exactly one opening structure")
        }
        group_opener[[group_id_i]] <- candidate_i
      }
    }

    repeat {
      if (units_left <= 0L) break
      best <- NULL
      for (candidate_id in names(ticket_index)) {
        block <- ticket_index[[candidate_id]]
        position <- cursor[[candidate_id]] + 1L
        # Skip tickets already committed anywhere on this issue (prior history or an
        # earlier purchase in this same loop).
        while (position <= nrow(block) && block$ticket_id[position] %in% selected_ticket_ids) {
          position <- position + 1L
        }
        if (position > nrow(block)) next
        group_id <- block$group_id[position]
        legs <- group_legs[group_legs$group_id == group_id, , drop = FALSE]
        if (!nrow(legs)) next
        fixtures_of_group <- sort(unique(as.character(legs$fixture_id)))
        # ONE structure per selected group. A group already opened by a DIFFERENT
        # candidate may not be deepened by this one: two structures over the same
        # fixture set are two different bets on that set, and the portfolio funds a
        # single structure per group. Only the opener may add tickets to it.
        opener <- group_opener[[group_id]]
        if (!is.null(opener) && !identical(opener, candidate_id)) {
          reason_by_candidate[candidate_id] <- "STRUCTURE_ALREADY_SELECTED"
          next
        }
        # Reuse/overlap admission is the authoritative shared helper, seeded with the
        # prior groups AND every group admitted so far in this loop. A deepening of an
        # already-admitted group is admitted without consuming another reuse slot.
        verdict <- parlay_group_admission(
          prior_groups = lapply(admitted, function(x) x$fixtures),
          candidate = fixtures_of_group,
          max_reuse = max_reuse, max_overlap = max_overlap)
        if (!isTRUE(verdict$admitted)) {
          reason_by_candidate[candidate_id] <- verdict$reason
          next
        }
        marginal <- if (identical(objective, "ev")) {
          block$ev_net_est[position]
        } else {
          block$probability[position]
        }
        # Neither objective spends money on a ticket with nonpositive marginal value.
        if (!is.na(marginal) && marginal <= 0) next
        score <- marginal / unit_cny
        candidate_key <- candidate_id
        is_better <- is.null(best) ||
          score > best$score ||
          (score == best$score && candidate_key < best$candidate_id)
        if (is_better) {
          best <- list(candidate_id = candidate_id, group_id = group_id,
                       position = position, ticket_id = block$ticket_id[position],
                       marginal = marginal, score = score,
                       fixtures = fixtures_of_group)
        }
      }
      if (is.null(best)) break

      # Commit the winning ticket and register its group as admitted. Registration
      # happens only after an actual purchase, so a group that buys nothing never
      # consumes a reuse/overlap slot.
      existing <- which(vapply(admitted, function(x) identical(x$group_id, best$group_id),
                               logical(1)))
      if (!length(existing)) {
        admitted[[length(admitted) + 1L]] <- list(group_id = best$group_id,
                                                  fixtures = best$fixtures)
      }
      # Record the opening structure so a later different structure over the same set
      # is refused as STRUCTURE_ALREADY_SELECTED rather than funded as a deepening.
      group_opener[[best$group_id]] <- best$candidate_id
      cursor[[best$candidate_id]] <- best$position
      selected_ticket_ids <- c(selected_ticket_ids, best$ticket_id)
      units_left <- units_left - 1L
      purchases_rows[[length(purchases_rows) + 1L]] <- tibble::tibble(
        issue_id = as.character(cutoff$issue_id), ticket_id = best$ticket_id,
        epoch_at = cutoff$cutoff_utc, group_id = best$group_id,
        candidate_id = best$candidate_id, stake_cny = unit_cny)
      # Trace the actual purchase. OPEN when this ticket is the group's first on this
      # issue (no prior ticket for the group), DEEPEN otherwise.
      prior_group_tickets <- sum(prior_purchases_table$group_id == best$group_id)
      action <- if (prior_group_tickets == 0L && is.null(selected_state[[best$candidate_id]])) {
        "OPEN"
      } else {
        "DEEPEN"
      }
      trace_rows[[length(trace_rows) + 1L]] <- tibble::tibble(
        step = as.integer(length(purchases_rows)), candidate_id = best$candidate_id,
        group_id = best$group_id, ticket_id = best$ticket_id,
        marginal = as.numeric(best$marginal), score_per_cny = as.numeric(best$score),
        action = action)
      state <- selected_state[[best$candidate_id]]
      if (is.null(state)) {
        state <- list(candidate_id = best$candidate_id, group_id = best$group_id,
                      structure = sub("^.*[|]", "", best$candidate_id),
                      units = 0L, cost_cny = 0, objective_value = 0,
                      first_reason = action)
      }
      state$units <- state$units + 1L
      state$cost_cny <- state$cost_cny + unit_cny
      state$objective_value <- state$objective_value + best$marginal
      selected_state[[best$candidate_id]] <- state
    }
  }

  trace <- if (length(trace_rows)) dplyr::bind_rows(trace_rows) else empty_trace

  purchases <- if (length(purchases_rows)) {
    match_validate_table(dplyr::bind_rows(purchases_rows), "purchases")
  } else {
    empty_purchases
  }
  # Selected groups derive from the purchases that actually happened: one row per
  # funded candidate, so a candidate that bought nothing never appears.
  selected <- if (length(selected_state)) {
    rows <- lapply(selected_state, function(s) tibble::tibble(
      candidate_id = s$candidate_id, group_id = s$group_id, structure = s$structure,
      units = as.integer(s$units), cost_cny = as.numeric(s$cost_cny),
      objective_value = as.numeric(s$objective_value), objective = objective,
      reason = s$first_reason))
    dplyr::bind_rows(rows)
  } else {
    empty_selected
  }
  # The next decision receives every funded group with its fixture set, so it cannot
  # re-open a group or forget a physical ticket.
  updated_sets <- fixture_sets
  if (nrow(selected)) {
    for (i in seq_len(nrow(selected))) {
      group_id <- selected$group_id[i]
      if (is.null(updated_sets[[group_id]])) {
        legs <- group_legs[group_legs$group_id == group_id, , drop = FALSE]
        updated_sets[[group_id]] <- sort(unique(as.character(legs$fixture_id)))
      }
    }
  }
  n_groups_derived <- length(unique(selected$group_id))
  # Actual cost of what was bought, not a units-left remainder: the two differ exactly
  # when the affordable unit count is fractional (e.g. an 11 CNY cap buys 5 units at
  # unit 2 and leaves 1 CNY genuinely unspent, not 0).
  cost_cny <- nrow(purchases) * unit_cny
  diagnostics <- list(
    n_groups = as.integer(n_groups_derived),
    n_candidates = as.integer(length(unique(selected$candidate_id))),
    units_bought = as.integer(nrow(purchases)),
    cost_cny = as.numeric(cost_cny),
    unspent_cny = as.numeric(available_cny - cost_cny),
    available_units = as.integer(affordable_units),
    objective = objective,
    # Says out loud what the probability objective IS, so no caller reads the summed
    # marginals as a union / at-least-one probability.
    objective_basis = if (identical(objective, "ev")) {
      "marginal net EV per ticket"
    } else {
      "expected count of winning tickets (sum of marginal masses), not a union probability"
    },
    constrained_reuse = max_reuse, constrained_overlap = max_overlap,
    rejected = stats::setNames(as.character(reason_by_candidate), names(reason_by_candidate)))

  list(purchases = purchases, selected = selected, trace = trace,
       history = list(purchases = dplyr::bind_rows(prior_purchases_table, purchases),
                      fixture_sets = updated_sets),
       diagnostics = diagnostics)
}

#' Prove a frontier artifact belongs to this decision
#'
#' Internal binding check used by [parlay_allocate_portfolio()]. The frontier's
#' `bound` metadata is REQUIRED unconditionally and must declare the same issue,
#' cutoff instant, leg width and unit cost this decision consumes. A missing or
#' disagreeing binding is refused; there is no settings argument or bypass flag.
#'
#' @param frontier_result Result of [parlay_coverage_frontier()] carrying `bound`
#'   and the original `group_legs` membership snapshot.
#' @param group_legs Validated group_legs tibble whose width must match the bound.
#' @param cutoff Explicit cutoff object for this decision.
#' @param unit_cny Positive CNY unit cost from the budget state.
#' @return `TRUE` invisibly; any missing or disagreeing field raises an error.
#' @noRd
.ValidateFrontierBinding <- function(frontier_result, group_legs, cutoff, unit_cny) {
  bound <- frontier_result$bound
  if (is.null(bound)) {
    stop("parlay_allocate_portfolio: frontier_result has no `bound` metadata; a ",
         "frontier must be produced by parlay_coverage_frontier() or declare its ",
         "cutoff/settings binding explicitly")
  }
  checkmate::assert_data_frame(bound, min.rows = 1L, max.rows = 1L,
                               .var.name = "frontier_result$bound")
    needed <- c("issue_id", "cutoff_utc", "n_legs", "unit_cny")
  missing <- setdiff(needed, names(bound))
  if (length(missing)) {
    stop("parlay_allocate_portfolio: frontier_result$bound is missing ",
         paste(missing, collapse = ", "))
  }
  if (!identical(as.character(bound$issue_id), as.character(cutoff$issue_id))) {
    stop("parlay_allocate_portfolio: frontier bound to issue '", bound$issue_id,
         "' but the cutoff names '", cutoff$issue_id, "'")
  }
  if (!identical(as.numeric(bound$cutoff_utc), as.numeric(cutoff$cutoff_utc))) {
    stop("parlay_allocate_portfolio: frontier cutoff_utc (",
         format(bound$cutoff_utc, tz = "UTC"), ") differs from the decision cutoff (",
         format(cutoff$cutoff_utc, tz = "UTC"), ")")
  }
  if (!identical(as.numeric(bound$unit_cny), as.numeric(unit_cny))) {
    stop("parlay_allocate_portfolio: frontier unit_cny (", bound$unit_cny,
         ") differs from the budget state unit_cny (", unit_cny, ")")
  }
  if (is.null(frontier_result$group_legs)) {
    stop("parlay_allocate_portfolio: frontier group membership is missing")
  }
  match_validate_table(frontier_result$group_legs, "group_legs")
  supplied <- dplyr::arrange(group_legs, group_id, leg_order, fixture_id)
  bound_legs <- dplyr::arrange(frontier_result$group_legs, group_id, leg_order, fixture_id)
  if (!identical(supplied, bound_legs)) {
    stop("parlay_allocate_portfolio: group membership differs from the frontier")
  }
  n_legs <- parlay_structure_legs(group_legs)
  if (nrow(group_legs) && !identical(as.integer(bound$n_legs), as.integer(n_legs))) {
    stop("parlay_allocate_portfolio: frontier n_legs (", bound$n_legs,
         ") differs from group_legs width (", n_legs, ")")
  }
  invisible(TRUE)
}

