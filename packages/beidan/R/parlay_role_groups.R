# Role round-robin (#537), stage 2: deterministic role candidate-pool generation.
#
# Issue #537 supersedes the earlier budget-derived group count. Construction now only
# GENERATES a bounded, deterministic pool of candidate groups; it never looks at the
# issue budget, and it never applies the final reuse/overlap constraints. Those are
# the job of stage 3 (parlay_evaluate_portfolio), where they are checked against the
# already-selected groups in the current decision at selection time.
#
# Contract decisions this file implements:
#   * n_candidates is a MAXIMUM pool size, chosen by the caller; it is not derived
#     from any budget. settings$issue_budget_cny must not influence the pool.
#   * Each group is filled through GLOBAL snake rounds whose role order is the sorted
#     (descending) pattern, i.e. risky 3 -> 2 -> 1, so role-1 legs are planned last.
#   * Groups are DIVERSIFIED by a bounded deterministic rank-start offset: group i
#     starts at a uniformly spaced ranking offset and wraps, so the full ranking
#     is represented. Identical role/mask/fixture-set packages
#     are de-duplicated.
#   * There is NO duplicate fixture inside one group. Between candidates, reuse and
#     overlap are ALLOWED: selection, not generation, is what enforces the caps.
#   * Shortages are explicit: a slot that cannot be filled is reported, never
#     fabricated.
#
# Vocabulary:
#   * group_slot -- the 1-based position of a generated candidate in the output.
#   * role       -- the number of retained outcomes for a leg (1, 2 or 3).
#   * round      -- GLOBAL round index; round r fills leg r of every group.
#   * turn       -- 1-based position of a group inside one round's turn order.

# --- feasibility -------------------------------------------------------------

#' Within-group feasibility of one fixture
#'
#' Internal. Generation only forbids a duplicate fixture INSIDE the group being
#' built. Cross-group reuse and overlap are explicitly allowed at this stage: they
#' are enforced by [parlay_evaluate_portfolio()] when packages are selected.
#' @param fixture_id Single fixture identifier under test.
#' @param set Fixtures already assigned to THIS group, partial or complete.
#' @return A list(feasible, reason). `reason` is `""` when feasible and otherwise
#'   `duplicate_fixture_in_group`.
#' @noRd
.parlay_role_feasible <- function(fixture_id, set) {
  if (fixture_id %in% set) {
    return(list(feasible = FALSE, reason = "duplicate_fixture_in_group"))
  }
  list(feasible = TRUE, reason = "")
}

# --- validation --------------------------------------------------------------

#' Validate a role planning settings snapshot
#'
#' Internal. Reuses the authoritative session-settings validator so a role plan is
#' driven by exactly the parameter block the rest of the pipeline consumes.
#' @param settings Complete settings snapshot, normally from [parlay_settings()].
#' @return `TRUE` invisibly; an invalid snapshot raises an error.
#' @noRd
.parlay_role_validate_settings <- function(settings) {
  parlay_validate_settings(settings)
  invisible(TRUE)
}

#' Validate the structural pattern
#'
#' Internal. The pattern is one integer 1..3 per leg in leg order; its length must
#' equal the plan width.
#' @param pattern Candidate integer vector.
#' @param n_legs Plan width the pattern must match.
#' @return The pattern as an integer vector; a wrong length, a non-whole value or a
#'   value outside 1..3 raises an error.
#' @noRd
.parlay_role_validate_pattern <- function(pattern, n_legs) {
  if (!is.numeric(pattern) || length(pattern) != n_legs || anyNA(pattern) ||
      any(!is.finite(pattern)) || any(pattern != trunc(pattern)) ||
      any(pattern < 1) || any(pattern > 3)) {
    stop("parlay_construct_role_groups: pattern must be ", n_legs,
         " whole numbers drawn from 1, 2, 3")
  }
  as.integer(pattern)
}

#' Validate the candidate-pool bound
#'
#' Internal. `n_candidates` is a positive whole number: how many candidate groups the
#' caller wants at most. It is a search bound, never a budget-derived count.
#' @param n_candidates Candidate pool bound.
#' @return `n_candidates` as an integer; a non-positive or non-whole value errors.
#' @noRd
.parlay_role_validate_n_candidates <- function(n_candidates) {
  checkmate::assert_count(n_candidates, positive = TRUE,
                          .var.name = "n_candidates")
  as.integer(n_candidates)
}

#' Validate the frozen pre-match SP carried by a candidate pool
#'
#' Internal. The SP table is schema-validated and every quote must be STRICTLY
#' before the decision cutoff: a quote at or after the cutoff was not visible to the
#' decision and must not enter the frozen pool. An empty table is the explicit
#' historical "SP missing" state and is allowed here; whether EV is available is
#' decided downstream by [parlay_value_tickets()].
#' @param prematch_sp Candidate SP tibble.
#' @param cutoff Explicit decision cutoff with `cutoff_utc`.
#' @return The validated SP tibble.
#' @noRd
.parlay_role_validate_prematch_sp <- function(prematch_sp, cutoff) {
  prematch_sp <- match_validate_table(prematch_sp, "prematch_sp")
  if (nrow(prematch_sp)) {
    if (anyNA(prematch_sp$quote_at)) {
      stop("parlay_construct_role_groups: prematch_sp$quote_at must not be missing")
    }
    if (any(prematch_sp$quote_at >= cutoff$cutoff_utc)) {
      stop("parlay_construct_role_groups: prematch_sp quotes must be strictly ",
           "before the cutoff; a quote at or after the decision instant would leak ",
           "future information into the frozen pool")
    }
  }
  prematch_sp
}

#' Validate a role score table against the authoritative probabilities
#'
#' Internal. The table may come from [parlay_role_scores()] or from a caller, but its
#' columns and its score/rank/retained values are re-derived from `probabilities`, so
#' a tampered score or rank cannot steer the plan and attributes are never trusted
#' alone.
#' @param role_scores Candidate tibble with `fixture_id`, `role`, `score`, `rank`,
#'   `retained_probability` and `allowed_outcomes`.
#' @param probabilities Authoritative probability tibble the scores must agree with.
#' @return `TRUE` invisibly; a missing column, an unpriced fixture/role, or a score,
#'   retained mass or rank that disagrees with the probabilities raises an error.
#' @noRd
.parlay_role_validate_scores <- function(role_scores, probabilities) {
  if (is.null(role_scores) || !is.data.frame(role_scores)) {
    stop("parlay_construct_role_groups: role_scores must be a role score tibble")
  }
  required <- c("fixture_id", "role", "score", "rank", "retained_probability",
                "allowed_outcomes")
  checkmate::assert_names(names(role_scores), must.include = required,
                          .var.name = "names(role_scores)")
  checkmate::assert_character(role_scores$fixture_id, any.missing = FALSE,
                              min.chars = 1, .var.name = "role_scores$fixture_id")
  checkmate::assert_integerish(role_scores$role, any.missing = FALSE,
                               .var.name = "role_scores$role")
  if (any(!role_scores$role %in% 1:3)) {
    stop("parlay_construct_role_groups: role_scores$role must be 1, 2 or 3")
  }
  checkmate::assert_numeric(role_scores$score, any.missing = FALSE, finite = TRUE,
                            .var.name = "role_scores$score")
  checkmate::assert_integerish(role_scores$rank, any.missing = FALSE,
                               .var.name = "role_scores$rank")
  expected <- parlay_role_scores(probabilities,
                                 list(issue_id = "validation",
                                      cutoff_utc = as.POSIXct(0, origin = "1970-01-01",
                                                              tz = "UTC")))
  # Require exactly the authoritative fixture/role grid, including masks and ranks.
  key <- function(x) paste(x$fixture_id, x$role)
  expected_key <- key(expected)
  if (anyDuplicated(key(role_scores)) || !setequal(key(role_scores), expected_key)) {
    stop("role_scores must contain each fixture/role exactly once")
  }
  checkmate::assert_numeric(role_scores$retained_probability, any.missing=FALSE, finite=TRUE)
  position <- match(key(role_scores), expected_key)
  if (anyNA(position)) {
    stop("parlay_construct_role_groups: role_scores names a fixture/role that the ",
         "supplied probabilities do not price")
  }
  if (!identical(unname(role_scores$allowed_outcomes), unname(expected$allowed_outcomes[position]))) {
    stop("role_scores allowed_outcomes disagree with authoritative role masks")
  }
  if (any(abs(role_scores$score - expected$score[position]) > 1e-12) ||
      any(abs(role_scores$retained_probability -
              expected$retained_probability[position]) > 1e-12) ||
      any(role_scores$rank != expected$rank[position])) {
    stop("parlay_construct_role_groups: role_scores disagree with the authoritative ",
         "probabilities; re-derive them with parlay_role_scores() instead of ",
         "trusting mutable attributes")
  }
  invisible(TRUE)
}

# --- the generator -----------------------------------------------------------

#' Choose the next feasible fixture for one turn under a rank-start offset
#'
#' Internal. Scans one role's ranking starting at `offset` (1-based) and wrapping, so
#' each group begins at a different rank and the pool is diverse rather than every
#' group taking the top-ranked fixture. The first fixture not already in this group
#' wins.
#'
#' The caller computes `offset` so the rank starts distribute UNIFORMLY across the
#' whole role ranking: `floor((slot - 1) * n_fixtures / n_candidates) + 1`. With 8
#' candidates and 49 ranked fixtures the starts are 1, 7, 13, ... 43 -- the entire
#' ranking is explored, not just its first `n_candidates` positions.
#' @param candidates Score rows for one role, ordered by rank.
#' @param set Fixtures already assigned to this group.
#' @param offset 1-based rank position to start scanning at.
#' @return A list(fixture_id, allowed, retained, skips). `fixture_id` is
#'   `NA_character_` when nothing is feasible.
#' @noRd
.parlay_role_choose_fixture <- function(candidates, set, offset) {
  ordered <- candidates[order(candidates$rank), , drop = FALSE]
  n <- nrow(ordered)
  if (!n) {
    return(list(fixture_id = NA_character_, allowed = NULL, retained = NA_real_,
                skips = list()))
  }
  start <- ((as.integer(offset) - 1L) %% n) + 1L
  skips <- list()
  for (step in seq_len(n)) {
    i <- ((start - 1L + step - 1L) %% n) + 1L
    fixture_id <- ordered$fixture_id[i]
    verdict <- .parlay_role_feasible(fixture_id, set)
    if (isTRUE(verdict$feasible)) {
      return(list(fixture_id = fixture_id, allowed = ordered$allowed_outcomes[[i]],
                  retained = ordered$retained_probability[i], skips = skips))
    }
    skips[[length(skips) + 1L]] <- list(fixture_id = fixture_id,
                                        reason = verdict$reason)
  }
  list(fixture_id = NA_character_, allowed = NULL, retained = NA_real_, skips = skips)
}

#' Canonical de-duplication key of a candidate package
#'
#' Internal. The key is the SORTED set of `(fixture_id, role, mask)` tuples and it
#' deliberately contains NO group slot, rank offset or round order: two candidates
#' that buy the same physical package under the same roles and masks from the same
#' admitted fixtures are the same package and only one may enter the pool. The mask
#' participates because the same fixture under a different role is a different leg.
#' @param block Leg rows of one candidate (group_slot, fixture_id, role,
#'   allowed_outcomes).
#' @return A single character key.
#' @noRd
.parlay_role_package_key <- function(block) {
  if (!nrow(block)) return(NA_character_)
  tuples <- vapply(seq_len(nrow(block)), function(i) {
    mask <- paste(sort(as.character(block$allowed_outcomes[[i]])), collapse = "+")
    paste(as.character(block$fixture_id[i]), as.integer(block$role[i]), mask,
          sep = ":")
  }, character(1))
  paste(sort(tuples), collapse = "|")
}

#' Generate deterministic role candidate groups
#'
#' Separates candidate GENERATION from single-group depth and portfolio selection
#' (issue #537). It produces up to `n_candidates` candidate groups from the role
#' rankings produced by [parlay_role_scores()], using GLOBAL snake rounds whose role
#' order is the sorted (descending) pattern, i.e. risky role 3 first and safest role 1
#' last. Turn order oscillates: odd rounds run groups 1..n, even rounds n..1.
#'
#' Groups are diversified by a bounded deterministic rank-start offset: group `i`
#' begins scanning each role's ranking at position
#' `floor((i - 1) * n_fixtures / n_candidates) + 1` and wraps. The offsets therefore
#' spread UNIFORMLY over the ENTIRE role ranking instead of only its first
#' `n_candidates` positions. That guarantees the pool is not the same top-fixture
#' group repeated, while remaining fully reproducible. Identical role/mask/fixture-set
#' packages are de-duplicated on a canonical key that is the SORTED
#' fixture/role/mask tuple set with NO group slot in it, so two slots that fill the
#' same packages with the same masks collapse to one candidate even when they were
#' reached through different offsets and rounds.
#'
#' The ISSUE BUDGET DOES NOT AFFECT THE POOL. `settings$issue_budget_cny` is carried
#' for downstream selection but is never read here, and there is no group budget and
#' no reuse/overlap constraint argument: between-candidate reuse and overlap are
#' allowed at generation and are enforced only when packages are selected by
#' [parlay_evaluate_portfolio()].
#'
#' @param role_scores Score tibble from [parlay_role_scores()], or an equivalent
#'   explicit table. It is re-validated against `probabilities`; a tampered score or
#'   rank is refused rather than obeyed.
#' @param cutoff Explicit cutoff object with a single UTC `cutoff_utc` and one
#'   `issue_id`. It must match the cutoff bound in `settings` when one is present.
#' @param settings Explicit parlay settings snapshot from [parlay_settings()]. Only
#'   its `n_legs` drives construction; the same `n_legs` applies to every group. Its
#'   `issue_budget_cny` is carried through untouched and must not change the pool.
#' @param pattern Integer vector of length `settings$n_legs`, each value 1, 2 or 3:
#'   the role used in each GLOBAL round. It is sorted descending internally so the
#'   risky roles are planned first.
#' @param n_candidates Positive whole number, the MAXIMUM number of candidate groups
#'   to generate. It is an explicit search bound, never derived from a budget.
#' @param probabilities Authoritative probability tibble the scores were derived from
#'   (columns `fixture_id`, `outcome`, `probability`). It is required: the rankings
#'   are re-validated against it rather than trusted from attributes.
#' @param prematch_sp Pre-cutoff SP tibble (`fixture_id`, `outcome`, `quote_at`,
#'   `sp_raw`, `source_url`) frozen into the pool. Every `quote_at` must be STRICTLY
#'   before `cutoff$cutoff_utc`; a quote at or after the cutoff leaks future
#'   information and is refused. The default typed-empty table is the explicit
#'   historical "SP missing" state and is allowed; it simply leaves EV unavailable.
#' @return A named list:
#'   * `role_legs` -- tibble(group_slot, group_id, fixture_id, role, round,
#'     allowed_outcomes, retained_probability), one row per actually filled leg;
#'   * `groups` -- tibble(group_slot, group_id, complete), one row per generated
#'     candidate, complete only when every round filled a leg;
#'   * `trace` -- tibble(round, turn, group_slot, role, fixture_id, action, reason),
#'     one row per turn with `action` "selected", "skipped" or "unfilled";
#'   * `shortages` -- tibble(group_slot, group_id, round, turn, role, reason) for every
#'     turn that could not be filled;
#'   * `cutoff`, `cutoff_hash`, `settings`, `probability_hash`, `prematch_sp`,
#'     `prematch_sp_hash`, `scores` -- the frozen context;
#'   * `pattern` -- the sorted role pattern the pool was drawn with.
#'   Incomplete candidates keep their `group_id` (`NA` until at least one leg is
#'   filled) and are reported, not fabricated.
#' @details The caller supplies an already-admitted pool: this stage performs no
#'   scraping and makes no eligibility claim about a fixture it was not given. It has
#'   no disk, network, fitting or betting side effects.
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
#' pool <- parlay_construct_role_groups(
#'   parlay_role_scores(probabilities, cutoff), cutoff, settings,
#'   pattern = c(2L, 1L), n_candidates = 4L, probabilities = probabilities)
#' pool$role_legs
#' @export
parlay_construct_role_groups <- function(role_scores, cutoff, settings, pattern,
                                         n_candidates, probabilities,
                                         prematch_sp = match_typed_empty("prematch_sp")) {
  match_require_cutoff(cutoff)
  # The cutoff identity is frozen into the pool so the evaluator can prove it was
  # never retimed, malformed or hash-swapped after construction.
  cutoff_hash <- rlang::hash(list(as.character(cutoff$issue_id), as.numeric(cutoff$cutoff_utc)))
  parlay_validate_settings(settings)
  # `settings` is a plain snapshot; when it carries its own bound cutoff it must be
  # the same decision. A projection-derived settings block that names another instant
  # would plan one issue's legs at another issue's epoch.
  if (!is.null(settings$cutoff)) {
    checkmate::assert_list(settings$cutoff, .var.name = "settings$cutoff")
    if (!identical(as.character(settings$cutoff$issue_id),
                   as.character(cutoff$issue_id)) ||
        !identical(as.numeric(settings$cutoff$cutoff_utc),
                   as.numeric(cutoff$cutoff_utc))) {
      stop("parlay_construct_role_groups: settings cutoff does not match the ",
           "decision cutoff")
    }
  }
  if (is.null(probabilities)) {
    stop("parlay_construct_role_groups: probabilities are required; the role ",
         "rankings must be re-derivable from the authoritative probability table ",
         "rather than trusted from attributes")
  }
  probabilities <- match_validate_table(probabilities, "probabilities")
  prematch_sp <- .parlay_role_validate_prematch_sp(prematch_sp, cutoff)
  prematch_sp_hash <- rlang::hash(prematch_sp)
  n_legs <- as.integer(settings$n_legs)
  role_pattern <- sort(.parlay_role_validate_pattern(pattern, n_legs),
                       decreasing = TRUE)
  n_pool <- .parlay_role_validate_n_candidates(n_candidates)
  .parlay_role_validate_scores(role_scores, probabilities)
  fixture_ids <- sort(unique(as.character(probabilities$fixture_id)))
  probability_hash <- rlang::hash(probabilities)

  # An empty admitted pool supports no candidate at all: return the typed-empty pool
  # rather than n_candidates groups of recorded shortages.
  if (!length(fixture_ids)) {
    return(list(role_legs = .parlay_role_typed_empty("legs"),
                groups = .parlay_role_typed_empty("groups"),
                trace = .parlay_role_typed_empty("trace"),
                shortages = .parlay_role_typed_empty("shortages"),
                cutoff = cutoff, settings = settings,
                probability_hash = probability_hash, pattern = role_pattern,
                probabilities = probabilities, scores = role_scores,
                prematch_sp = prematch_sp, prematch_sp_hash = prematch_sp_hash,
                cutoff_hash = cutoff_hash))
  }

  plan <- .parlay_role_plan_groups(role_scores, role_pattern, n_pool, n_legs)
  legs <- plan$role_legs
  groups <- plan$groups
  # Attach the canonical group ids now that the sets are known. Whole packages were
  # de-duplicated on the slot-free fixture/role/mask key during construction, so the
  # pool never repeats a package; a dropped slot keeps its provisional id and
  # `complete = FALSE` as audit evidence. The id is bound to the cutoff instant so a
  # pool can never be replayed against another decision epoch. Slots that ended up
  # with no legs at all are reported as unavailable in the id column.
  if (nrow(legs)) {
    slot_fixtures <- split(as.character(legs$fixture_id),
                           as.character(legs$group_slot))
    ids <- stats::setNames(
      paste0(vapply(slot_fixtures, .parlay_role_group_id, character(1)), "@",
             as.numeric(cutoff$cutoff_utc), ":", names(slot_fixtures)),
      names(slot_fixtures))
    legs$group_id <- unname(ids[as.character(legs$group_slot)])
    filled <- as.character(groups$group_slot) %in% names(ids)
    groups$group_id <- unname(ifelse(filled,
                                     ids[as.character(groups$group_slot)],
                                     groups$group_id))
    legs <- legs[, c("group_slot", "group_id", "fixture_id", "role", "round",
                     "allowed_outcomes", "retained_probability")]
  }
  plan$shortages$group_id <- groups$group_id[
    match(plan$shortages$group_slot, groups$group_slot)]
  list(role_legs = legs, groups = groups, trace = plan$trace,
       shortages = plan$shortages, cutoff = cutoff, settings = settings,
       probability_hash = probability_hash, pattern = role_pattern,
       probabilities = probabilities, scores = role_scores,
       prematch_sp = prematch_sp, prematch_sp_hash = prematch_sp_hash,
       cutoff_hash = cutoff_hash)
}

#' Build the candidate pool turn by turn
#'
#' Internal. Runs the `n_pool` candidates through role-driven global rounds in the
#' oscillating turn order, resolving ONE TURN AT A TIME and diversifying each group by
#' its own rank-start offset. Identical role/mask/fixture-set packages are
#' de-duplicated: a later group that reproduces an earlier package is dropped and its
#' slots recorded as shortages rather than emitted twice.
#' @param role_scores Validated role score table.
#' @param pattern Integer role per global round, sorted descending.
#' @param n_pool Maximum number of candidate groups to generate.
#' @param n_legs Plan width.
#' @return A list(role_legs, groups, trace, shortages) before canonical group ids are
#'   attached; each element is the typed-empty shape when nothing was generated.
#' @noRd
.parlay_role_plan_groups <- function(role_scores, pattern, n_pool, n_legs) {
  empty <- list(
    role_legs = .parlay_role_typed_empty("legs"),
    groups = .parlay_role_typed_empty("groups"),
    trace = .parlay_role_typed_empty("trace"),
    shortages = .parlay_role_typed_empty("shortages"))
  if (n_pool < 1L) return(empty)

  candidates_by_role <- lapply(1:3, function(role) {
    role_scores[role_scores$role == role, , drop = FALSE]
  })
  # `sets` is the LIVE assignment state for this group; each group is filled from its
  # own offset. Cross-group state is deliberately NOT consulted: overlap is allowed.
  sets <- stats::setNames(vector("list", n_pool), as.character(seq_len(n_pool)))
  for (slot in seq_len(n_pool)) sets[[slot]] <- character(0)
  group_ids <- stats::setNames(rep(NA_character_, n_pool), as.character(seq_len(n_pool)))
  leg_rows <- list()
  trace_rows <- list()
  shortage_rows <- list()
  seen_packages <- character(0)
  dropped <- rep(FALSE, n_pool)

  # Uniform deterministic rank-start offsets over the ENTIRE role ranking. Group
  # `slot` starts at floor((slot - 1) * n_fixtures / n_candidates) + 1, so `n_pool`
  # candidates sample the whole ranking rather than only its first `n_pool` positions.
  n_fixtures <- vapply(candidates_by_role, nrow, integer(1))
  offsets <- vapply(seq_len(n_pool), function(slot) {
    if (n_fixtures[1] < 1L) return(1L)
    as.integer(floor((slot - 1) * max(n_fixtures) / n_pool) + 1L)
  }, integer(1))

  for (round in seq_len(n_legs)) {
    role <- pattern[round]
    turn_order <- if (round %% 2L == 1L) seq_len(n_pool) else rev(seq_len(n_pool))
    for (turn in seq_along(turn_order)) {
      slot <- turn_order[turn]
      if (dropped[slot]) next
      set <- sets[[slot]]
      chose <- .parlay_role_choose_fixture(candidates_by_role[[role]], set,
                                           offsets[slot])
      for (skip in chose$skips) {
        trace_rows[[length(trace_rows) + 1L]] <- tibble::tibble(
          round = as.integer(round), turn = as.integer(turn),
          group_slot = as.integer(slot), role = as.integer(role),
          fixture_id = skip$fixture_id, action = "skipped", reason = skip$reason)
      }
      if (is.na(chose$fixture_id)) {
        trace_rows[[length(trace_rows) + 1L]] <- tibble::tibble(
          round = as.integer(round), turn = as.integer(turn),
          group_slot = as.integer(slot), role = as.integer(role),
          fixture_id = NA_character_, action = "unfilled",
          reason = "no_feasible_fixture_in_role_ranking")
        shortage_rows[[length(shortage_rows) + 1L]] <- tibble::tibble(
          group_slot = as.integer(slot), group_id = group_ids[[as.character(slot)]],
          round = as.integer(round), turn = as.integer(turn),
          role = as.integer(role), reason = "no_feasible_fixture_in_role_ranking")
        next
      }
      sets[[slot]] <- sort(c(sets[[slot]], chose$fixture_id))
      if (is.na(group_ids[[as.character(slot)]])) {
        group_ids[[as.character(slot)]] <- .parlay_role_group_id(sets[[slot]])
      }
      leg_rows[[length(leg_rows) + 1L]] <- tibble::tibble(
        group_slot = as.integer(slot), group_id = NA_character_,
        fixture_id = chose$fixture_id, role = as.integer(role),
        round = as.integer(round), allowed_outcomes = list(chose$allowed),
        retained_probability = as.numeric(chose$retained))
      trace_rows[[length(trace_rows) + 1L]] <- tibble::tibble(
        round = as.integer(round), turn = as.integer(turn),
        group_slot = as.integer(slot), role = as.integer(role),
        fixture_id = chose$fixture_id, action = "selected", reason = "")
      # A package is complete as soon as its last round fills a leg, so the canonical
      # key can be taken NOW: identical packages collapse at the first opportunity
      # instead of surviving the remaining rounds and being dropped afterwards.
      if (length(sets[[slot]]) == n_legs) {
        block <- dplyr::bind_rows(leg_rows[
          vapply(leg_rows, function(row) row$group_slot[[1]] == slot, logical(1))])
        key <- .parlay_role_package_key(block)
        if (key %in% seen_packages) {
          dropped[slot] <- TRUE
          for (i in seq_len(nrow(block))) {
            shortage_rows[[length(shortage_rows) + 1L]] <- tibble::tibble(
              group_slot = as.integer(slot),
              group_id = group_ids[[as.character(slot)]],
              round = as.integer(block$round[i]), turn = NA_integer_,
              role = as.integer(block$role[i]),
              reason = "duplicate_candidate_package")
          }
          trace_rows[[length(trace_rows) + 1L]] <- tibble::tibble(
            round = as.integer(round), turn = as.integer(turn),
            group_slot = as.integer(slot), role = as.integer(role),
            fixture_id = NA_character_, action = "skipped",
            reason = "duplicate_candidate_package")
          leg_rows <- leg_rows[
            !vapply(leg_rows, function(row) row$group_slot[[1]] == slot, logical(1))]
          sets[[slot]] <- character(0)
        } else {
          seen_packages <- c(seen_packages, key)
        }
      }
    }
  }
  legs <- if (length(leg_rows)) dplyr::bind_rows(leg_rows) else empty$role_legs
  if (nrow(legs)) legs <- legs[order(legs$group_slot, legs$round), , drop = FALSE]
  complete <- stats::setNames(vapply(seq_len(n_pool), function(slot) {
    length(sets[[slot]]) == n_legs && !dropped[slot]
  }, logical(1)), as.character(seq_len(n_pool)))
  groups <- tibble::tibble(
    group_slot = as.integer(seq_len(n_pool)),
    group_id = unname(group_ids),
    complete = unname(complete))
  list(role_legs = legs, groups = groups,
       trace = if (length(trace_rows)) dplyr::bind_rows(trace_rows) else empty$trace,
       shortages = if (length(shortage_rows)) {
         dplyr::bind_rows(shortage_rows)
       } else {
         empty$shortages
       })
}
