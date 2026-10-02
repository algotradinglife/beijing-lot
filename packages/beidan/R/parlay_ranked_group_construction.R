# Ranked-selection role candidates (#537 successor): stage 2 construction.
#
# Replaces the obsolete all-fixtures/all-roles score scan with a construction driven
# by the ranked direction table produced by rank_outcome_selections(). The generator
# walks a FINITE, deterministic trajectory of fixed-width cohorts. A cohort is a
# batch of `cohort_width` candidate group slots built simultaneously: each global
# round gives every slot exactly one leg, and the turn order inside a round is the
# deterministic snake. The target pattern is the caller's pattern sorted descending
# (risky role 3 -> 2 -> 1). A target-role-3 leg that cannot find an unused triple
# falls back to an unused double; the leg's ACTUAL role stays 2 and the substitution
# is recorded.
#
# Contract decisions implemented here:
#   * `max_candidates` is the caller's ceiling on the number of UNIQUE COMPLETE
#     candidate groups EMITTED, never on attempted slots. `NULL` means the caller
#     sets no ceiling and the trajectory runs to its own termination. It is never
#     derived from the issue budget; the budget does not influence construction.
#   * Termination is generational, not a hidden constant: the canonical state at the
#     START of a cohort is the tuple of per-role queue cursors plus the snake phase.
#     When a cohort would start from a state already seen, construction stops with
#     `state_repeated` BEFORE re-running that state. The state never includes the
#     growing set of seen packages or any slot count.
#   * `cohort_width` is derived from the ranked table alone, independent of
#     `max_candidates`: the maximum, over the supplied role queues (roles 3, 2 and 1), of the number of DISTINCT fixtures in that queue. Consequently `max = 1`,
#     `max = 2` and `max = NULL` share the identical first-cohort layout and a
#     positive ceiling truncates the emitted groups only, never the layout.
#   * Every cohort is built COMPLETELY before any group from it is emitted, and
#     complete unique groups are emitted in stable candidate order (cohort order,
#     then slot order). A ceiling therefore produces a prefix of the `NULL` output:
#     identical group ids, fixture/role/mask legs and actual patterns.
#   * Physical groups are de-duplicated across cohorts on the canonical physical
#     signature (every fixture together with its realized outcome combination), so
#     the same physical package is never emitted twice while two candidates over the
#     same fixtures with different retained outcome sets stay distinct.
#   * Shortages are explicit, never fabricated: a round walks its fallback boards
#     (3 -> 2, 2, 1) and records every non-target board as a substitution. Fewer
#     distinct fixtures than legs stops with `insufficient_fixtures`, an empty ranked
#     table stops with `empty_inputs`, and a positive ceiling stops with
#     `max_candidates`.
#   * Final reuse/overlap/budget admission is EXTERNAL. This function enumerates one
#     deterministic generation trajectory; it does not claim constraint-aware
#     enumeration or exhaustion of every combination.

#' Derive a validated long probability tibble from ranked selections
#'
#' @param ranked_selections Receipt-validated selection tibble with fixture_id and win/draw/lose.
#' @return One row per fixture and W/D/L outcome, with numeric probability; typed empty for no fixtures.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_probabilities <- function(ranked_selections) {
  fixture_ids <- as.character(ranked_selections$fixture_id)
  first <- !duplicated(fixture_ids)
  wide <- tibble::tibble(
    fixture_id = fixture_ids[first],
    win = as.numeric(ranked_selections$win[first]),
    draw = as.numeric(ranked_selections$draw[first]),
    lose = as.numeric(ranked_selections$lose[first]))
  long <- tidyr::pivot_longer(
    wide, c("win", "draw", "lose"),
    names_to = "outcome", values_to = "probability")
  long$outcome <- unname(c(win = "W", draw = "D", lose = "L")[long$outcome])
  long <- long[, c("fixture_id", "outcome", "probability"), drop = FALSE]
  match_validate_table(long, "probabilities")
}

#' Translate a ranked row's outcome names (classify_outcomes uses lower case) to the
#' canonical W/D/L labels the pool contract uses. The set itself is preserved exactly:
#' no mask is upgraded or widened.
#'
#' @param outcomes Character vector of win/draw/lose names or canonical W/D/L codes.
#' @return Character outcome vector in the supplied order; unknown labels error.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_mask <- function(outcomes) {
  labels <- c(win = "W", draw = "D", lose = "L", W = "W", D = "D", L = "L")
  mapped <- unname(labels[as.character(outcomes)])
  if (anyNA(mapped)) {
    stop("parlay_construct_role_groups: ranked selection has an unknown outcome label")
  }
  mapped
}

#' Verify that a supplied ranked table is canonically identical to a fresh ranking of
#' the SAME original pre-rank selection snapshot, column for column. Sorted on the
#' canonical (role descending, rank ascending, selection_id ascending, fixture_id)
#' keys so a caller may reorder rows without breaking verification, while any real
#' change to a fixture, metric, mask, rank or receipt still fails closed.
#'
#' @param table Ranked tibble containing base_role, rank, selection_id and fixture_id.
#' @return The same columns ordered by descending category and ascending rank and keys.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_canonical_keys <- function(table) {
  table[order(-table[["base_role"]], table[["rank"]], table[["selection_id"]],
              table[["fixture_id"]], method = "radix"), , drop = FALSE]
}

#' Compare canonical ranked columns without numeric truncation
#'
#' @param observed Observed ranked tibble.
#' @param expected Independently rebuilt canonical ranked tibble.
#' @return Logical scalar; FALSE for schema or value differences.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_columns_equal <- function(observed, expected) {
  if (!identical(names(observed), names(expected))) return(FALSE)
  for (column in names(expected)) {
    if (identical(column, "rank")) {
      # Compare the ACTUAL rank numbers, not a truncated integer coercion, so a
      # fractional rank can never pass as an equal whole number.
      if (!identical(as.numeric(observed[[column]]),
                     as.numeric(expected[[column]]))) {
        return(FALSE)
      }
    } else if (identical(column, "outcomes")) {
      if (!identical(lapply(observed[[column]], as.character),
                     lapply(expected[[column]], as.character))) {
        return(FALSE)
      }
    } else if (!identical(observed[[column]], expected[[column]])) {
      return(FALSE)
    }
  }
  TRUE
}

#' Recompute the rank receipt in full. The supplied table must carry the ORIGINAL
#' pre-rank selection snapshot it was built from, and its `input_hash` must equal
#' `rlang::hash(input_snapshot)`. The snapshot is then re-ranked with the carried
#' cutoff and priority; the canonical columns, rank, probabilities and receipt hashes
#' must all match. A swapped hash, a swapped snapshot, a tampered rank and a tampered
#' probability therefore all fail closed instead of being frozen into the pool.
#'
#' The frozen `cutoff_hash` is checked EXACTLY, and BEFORE any recomputation: it is
#' the pool's authoritative cutoff scheme applied to the carried cutoff, so a ranking
#' whose `cutoff` attribute alone was retimed (another instant or another issue) can
#' never be accepted, even when `settings` carry no cutoff and the ranked table is
#' empty. Only a fresh rank_outcome_selections() call rebuilds the receipt.
#'
#' @param ranked_selections Ranked tibble with cutoff, original input snapshot and bound hashes.
#' @return Validated cutoff, hashes, priority, input snapshot and recomputed ranking; malformed or inconsistent receipts error.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_validate_receipt <- function(ranked_selections) {
  if (!tibble::is_tibble(ranked_selections)) {
    stop("parlay_construct_role_groups: ranked_selections must be a tibble")
  }
  if (!"rank" %in% names(ranked_selections)) {
    stop("parlay_construct_role_groups: ranked_selections is missing its `rank` ",
         "receipt column")
  }
  cutoff <- attr(ranked_selections, "cutoff", exact = TRUE)
  match_require_cutoff(cutoff)
  cutoff_hash <- attr(ranked_selections, "cutoff_hash", exact = TRUE)
  if (is.null(cutoff_hash) || !is.character(cutoff_hash) ||
      length(cutoff_hash) != 1L || is.na(cutoff_hash) ||
      !grepl("^[0-9a-f]{32}$", cutoff_hash)) {
    stop("parlay_construct_role_groups: ranked_selections is missing or has a ",
         "malformed `cutoff_hash` receipt")
  }
  if (!identical(cutoff_hash, .rank_outcome_cutoff_hash(cutoff))) {
    stop("parlay_construct_role_groups: ranked_selections `cutoff_hash` does not ",
         "verify against its carried `cutoff`; the cutoff was retimed without ",
         "rebuilding the ranking")
  }
  priority <- attr(ranked_selections, "priority", exact = TRUE)
  if (is.null(priority) || !is.character(priority) || length(priority) != 1L ||
      is.na(priority) || !priority %in% c("coverage", "balance")) {
    stop("parlay_construct_role_groups: ranked_selections is missing a valid ",
         "`priority` receipt")
  }
  input_hash <- attr(ranked_selections, "input_hash", exact = TRUE)
  code_hash <- attr(ranked_selections, "code_hash", exact = TRUE)
  if (is.null(input_hash) || !is.character(input_hash) || length(input_hash) != 1L ||
      is.na(input_hash) || !grepl("^[0-9a-f]{32}$", input_hash)) {
    stop("parlay_construct_role_groups: ranked_selections is missing or has a ",
         "malformed `input_hash` receipt")
  }
  if (is.null(code_hash) || !is.character(code_hash) || length(code_hash) != 1L ||
      is.na(code_hash) || !nzchar(code_hash)) {
    stop("parlay_construct_role_groups: ranked_selections is missing its ",
         "`code_hash` receipt")
  }
  # The original pre-rank selection snapshot is explicit table state, not a hidden
  # global: its hash must verify the carried `input_hash` exactly.
  snapshot <- attr(ranked_selections, "input_snapshot", exact = TRUE)
  if (is.null(snapshot) || !tibble::is_tibble(snapshot)) {
    stop("parlay_construct_role_groups: ranked_selections is missing its ",
         "`input_snapshot` receipt (the original pre-rank selection table)")
  }
  if (!identical(rlang::hash(snapshot), input_hash)) {
    stop("parlay_construct_role_groups: ranked_selections `input_hash` does not ",
         "verify against its `input_snapshot`; the source receipt was swapped or ",
         "tampered")
  }
  recomputed <- tryCatch(
    rank_outcome_selections(snapshot, cutoff, priority),
    error = function(e) {
      stop("parlay_construct_role_groups: ranked_selections rank receipt failed ",
           "recomputation via rank_outcome_selections/prepare_outcome_selections: ",
           conditionMessage(e), call. = FALSE)
    })
  observed_rank <- ranked_selections$rank
  if (!is.numeric(observed_rank) || length(observed_rank) != nrow(ranked_selections) ||
      anyNA(observed_rank) || any(!is.finite(observed_rank)) ||
      any(observed_rank != trunc(observed_rank))) {
    stop("parlay_construct_role_groups: ranked_selections$rank must be a vector of ",
         "finite, non-missing whole numbers; a fractional or non-finite rank is a ",
         "failed receipt")
  }
  observed_canonical <- .parlay_ranked_canonical_keys(ranked_selections)
  expected_canonical <- .parlay_ranked_canonical_keys(recomputed)
  if (nrow(observed_canonical) != nrow(expected_canonical) ||
      !.parlay_ranked_columns_equal(observed_canonical, expected_canonical)) {
    stop("parlay_construct_role_groups: ranked_selections receipt does not match ",
         "the canonical columns re-ranked from its `input_snapshot` (rank, ",
         "metrics, masks or source rows disagree)")
  }
  # The code hash and priority are re-derivable and must match exactly, so a swapped
  # or stale receipt is refused.
  if (!identical(priority, attr(recomputed, "priority", exact = TRUE)) ||
      !identical(code_hash, attr(recomputed, "code_hash", exact = TRUE))) {
    stop("parlay_construct_role_groups: ranked_selections rank receipt hashes do ",
         "not match the recomputation")
  }
  list(cutoff = cutoff, cutoff_hash = cutoff_hash, priority = priority,
       input_hash = input_hash, code_hash = code_hash,
       input_snapshot = snapshot, recomputed = recomputed)
}

#' The ordered ranked-choice queue for one TARGET role. Selection is by the
#' classifier's `base_role`, never by the realized `n_outcomes`: a protected double
#' is a base-1 variant that actually carries two outcomes and MUST stay in the
#' role-1 board, while a base-3 fixture always carries three. There are THREE boards
#' (3, 2 and 1), each with its own continuous cursor. rank_outcome_selections()
#' already orders rows by base_role descending, with a distinct continuous rank
#' for every selection variant. The queue is re-sorted on (rank, selection_id,
#' fixture_id) so the
#' board order is stable regardless of how the caller reordered the ranked rows.
#'
#' @param ranked_selections Receipt-validated selection tibble.
#' @param base_role Integer category 1, 2 or 3, independent of actual mask size.
#' @return A selection tibble ordered by rank and stable keys; typed empty when this board is absent.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_queue <- function(ranked_selections, base_role) {
  queue <- ranked_selections[ranked_selections$base_role == base_role, ,
                             drop = FALSE]
  queue[order(queue$rank, queue$selection_id, queue$fixture_id, method = "radix"),
        , drop = FALSE]
}

#' Cohort width: the maximum, over the supplied target-role queues (role 3, role 2,
#' role 1), of the number of DISTINCT fixtures in that queue. It is a property of the
#' ranked table alone and never of `max_candidates`, so every ceiling shares the
#' identical first-cohort layout. A cohort never needs to be wider than the largest
#' distinct fixture pool: beyond that a slot could not avoid repeating a fixture
#' inside its own group. The value is at least 1L whenever the queues are non-empty.
#'
#' @param queues Named list of the three ranked classifier-board tibbles.
#' @return Positive integer maximum distinct-fixture count across boards, floored at one.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_cohort_width <- function(queues) {
  widths <- vapply(queues, function(queue) {
    length(unique(as.character(queue$fixture_id)))
  }, integer(1))
  as.integer(max(1L, widths))
}

#' Bounded forward scan of a queue starting at `cursor`, wrapping at most once. The
#' first row is taken; a row whose fixture is already in `used` is skipped and the
#' scan continues to the next ranked choice. The returned cursor points just past the
#' chosen row, so the NEXT group continues from there (wrapping to the head at the
#' tail) instead of restarting. When nothing is feasible the scan is exhausted after
#' `nrow(queue)` steps, so it can never loop forever.
#'
#' @param queue Ranked selection tibble for one board.
#' @param cursor One-based next queue position.
#' @param used Character fixture identifiers already in this group.
#' @return List(index, cursor); index is NA_integer_ when no unused fixture is available after one full scan.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_scan <- function(queue, cursor, used) {
  n <- nrow(queue)
  if (n < 1L) {
    return(list(index = NA_integer_, cursor = as.integer(cursor)))
  }
  start <- ((as.integer(cursor) - 1L) %% n) + 1L
  for (step in seq_len(n)) {
    i <- ((start - 1L + step - 1L) %% n) + 1L
    if (!queue$fixture_id[[i]] %in% used) {
      return(list(index = i, cursor = (i %% n) + 1L))
    }
  }
  list(index = NA_integer_, cursor = as.integer(cursor))
}

#' Canonical cohort-start state: the per-role queue cursors, the snake phase AND the
#' three immutable ranked-board lengths. The cursors alone are not sufficient because
#' two different boards can map a cursor onto the same integer; binding the board
#' sizes makes a repeat a genuine generational cycle. It deliberately excludes the
#' growing set of seen packages and every slot count, so termination never depends on
#' how much has already been emitted.
#'
#' @param cursors Named list of one-based board cursor integers.
#' @param phase Snake traversal phase, 0 or 1.
#' @param queues The three immutable ranked-board tibbles.
#' @return Character key binding cursors, phase and board lengths, independent of prior emissions.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_state_key <- function(cursors, phase, queues) {
  paste(c(as.integer(cursors[["3"]]), as.integer(cursors[["2"]]),
          as.integer(cursors[["1"]]), as.integer(phase),
          nrow(queues[["3"]]), nrow(queues[["2"]]), nrow(queues[["1"]])),
        collapse = ":")
}

#' The ordered target roles a round falls back through when its primary board has no
#' unused choice: a target 3 round tries the triples, then the doubles; a target 2
#' round tries only the doubles; a target 1 round tries only base-role-1
#' entries, which include single and protected-double variants. The chosen direction's own mask is kept
#' EXACTLY (never widened or upgraded), `base_role` records the board it came from and
#' `n_outcomes` its real size, so a base-1 protected double is never mistaken for a
#' single nor for a true triple.
#'
#' @param target Integer target category 1, 2 or 3.
#' @return Integer vector: 3 may use 3 then 2; 1 and 2 use only their own category. Other targets error.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_fallback_boards <- function(target) {
  switch(as.character(target),
         "3" = c(3L, 2L),
         "2" = 2L,
         "1" = 1L,
         stop("parlay_construct_role_groups: unsupported target role ", target))
}

#' Create a typed empty actual-pattern table
#'
#' @return Zero-row tibble with integer group_slot, character group_id and list target_pattern/actual_pattern columns.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_typed_empty_patterns <- function() {
  tibble::tibble(
    group_slot = integer(0), group_id = character(0),
    target_pattern = list(), actual_pattern = list())
}

#' Create a typed empty shortage-substitution table
#'
#' @return Zero-row tibble with the explicit substitution identifier, category, actual mask size and reason columns.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_typed_empty_substitutions <- function() {
  tibble::tibble(
    group_slot = integer(0), group_id = character(0), round = integer(0),
    fixture_id = character(0), selection_id = integer(0),
    target_role = integer(0), base_role = integer(0), n_outcomes = integer(0),
    reason = character(0))
}

#' The market-schedule-free identity of one PHYSICAL candidate: every leg's concrete
#' fixture together with the exact outcome set it retains. Two candidates that share
#' a fixture set but differ in one leg's realized outcome combination are DIFFERENT
#' packages, so de-duplication on the fixture set alone would wrongly collapse them.
#'
#' @param block Leg tibble with unique fixture_id and allowed_outcomes list columns.
#' @return Character key ordered by fixture identifier and each canonical outcome mask; no round, slot or category alias participates.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_candidate_signature <- function(block) {
  legs <- block[order(block$fixture_id, method = "radix"), , drop = FALSE]
  paste0(
    vapply(seq_len(nrow(legs)), function(i) {
      paste0(as.character(legs$fixture_id[[i]]), ":",
             paste(sort(as.character(legs$allowed_outcomes[[i]])), collapse = "+"))
    }, character(1)),
    collapse = "|")
}

#' Build ONE complete cohort of `width` group slots. Each global round fills one leg
#' per slot; the turn order is the snake flipped by `phase` (even phase runs the even
#' rounds forwards). Per-role queue cursors are threaded through the cohort and
#' returned, so the next cohort continues where this one stopped. The cohort is always
#' built in full; the caller decides how much of it to emit.
#'
#' Each round has a TARGET role from the descending pattern. For target role 3 the
#' round walks the base_role-3 board, then falls back to the base_role-2 board when no
#' unused triple remains; for target role 2 it walks only the base_role-2 board. A
#' fallback keeps the chosen direction's own mask EXACTLY (never widened) and records
#' target 3 -> base 2. `n_outcomes` is always the realized size of the chosen
#' direction, so a base-1 protected double (n_outcomes 2) or a base-2 pair are never
#' confused with a true triple.
#'
#' @param queues Three receipt-validated ranked boards.
#' @param cursors Explicit next position for each board.
#' @param phase Snake traversal phase, 0 or 1.
#' @param pattern Descending integer target categories.
#' @param width Positive number of group slots built together.
#' @param n_legs Positive plan width, equal to length(pattern).
#' @return List of role_legs, trace, substitutions, actual_pattern and advanced cursors; unavailable positions remain audited, never invented.
#' @details Internal deterministic helper with no IO or mutable session state.
#' @noRd
.parlay_ranked_cohort <- function(queues, cursors, phase, pattern, width, n_legs) {
  sets <- stats::setNames(vector("list", width), as.character(seq_len(width)))
  for (slot in seq_len(width)) sets[[slot]] <- character(0)
  leg_rows <- list()
  trace_rows <- list()
  substitution_rows <- list()

  add_trace <- function(round, turn, slot, role, fixture_id, action, reason) {
    trace_rows[[length(trace_rows) + 1L]] <<- tibble::tibble(
      round = as.integer(round), turn = as.integer(turn),
      group_slot = as.integer(slot), role = as.integer(role),
      fixture_id = fixture_id, action = action, reason = reason)
  }
  add_leg <- function(slot, round, chosen, base_role) {
    leg_rows[[length(leg_rows) + 1L]] <<- tibble::tibble(
      group_slot = as.integer(slot), group_id = NA_character_,
      fixture_id = as.character(chosen$fixture_id[[1]]),
      selection_id = as.integer(chosen$selection_id[[1]]),
      round = as.integer(round), base_role = as.integer(base_role),
      n_outcomes = as.integer(chosen$n_outcomes[[1]]),
      allowed_outcomes = list(.parlay_ranked_mask(chosen$outcomes[[1]])),
      retained_probability = as.numeric(chosen$coverage_probability[[1]]))
  }

  for (round in seq_len(n_legs)) {
    target <- as.integer(pattern[[round]])
    reverse <- ((round + phase) %% 2L) == 0L
    turn_order <- if (reverse) rev(seq_len(width)) else seq_len(width)
    for (turn in seq_along(turn_order)) {
      slot <- turn_order[[turn]]
      used <- sets[[slot]]
      chosen <- NULL
      base_role <- NA_integer_
      substitution <- FALSE
      reason <- ""
      # Walk the round's fallback boards in order. The FIRST board with an unused
      # choice wins; when its board is not the target's own board the leg is a
      # recorded substitution. The chosen direction's mask is kept exactly.
      for (board in .parlay_ranked_fallback_boards(target)) {
        scan <- .parlay_ranked_scan(queues[[as.character(board)]],
                                    cursors[[as.character(board)]], used)
        if (!is.na(scan$index)) {
          chosen <- queues[[as.character(board)]][scan$index, , drop = FALSE]
          cursors[[as.character(board)]] <- scan$cursor
          base_role <- board
          substitution <- board != target
          break
        }
      }
      if (is.null(chosen)) {
        reason <- switch(as.character(target),
                         "3" = "no_available_triple_or_double",
                         "2" = "no_available_double",
                         "1" = "no_available_base_role_1")
        add_trace(round, turn, slot, target, NA_character_, "unfilled", reason)
        next
      }
      sets[[slot]] <- sort(c(sets[[slot]], as.character(chosen$fixture_id[[1]])))
      add_leg(slot, round, chosen, base_role)
      if (substitution) {
        substitution_rows[[length(substitution_rows) + 1L]] <- tibble::tibble(
          group_slot = as.integer(slot), group_id = NA_character_,
          round = as.integer(round),
          fixture_id = as.character(chosen$fixture_id[[1]]),
          selection_id = as.integer(chosen$selection_id[[1]]),
          target_role = as.integer(target), base_role = as.integer(base_role),
          n_outcomes = as.integer(chosen$n_outcomes[[1]]),
          reason = "target_role_shortage_board_fallback")
        add_trace(round, turn, slot, target, as.character(chosen$fixture_id[[1]]),
                  "selected", "target_role_shortage_board_fallback")
      } else {
        add_trace(round, turn, slot, target, as.character(chosen$fixture_id[[1]]),
                  "selected", "")
      }
    }
  }

  legs <- if (length(leg_rows)) dplyr::bind_rows(leg_rows) else
    .parlay_role_typed_empty("legs")
  if (nrow(legs)) {
    legs <- legs[order(legs$group_slot, legs$round, method = "radix"), , drop = FALSE]
  }
  trace <- if (length(trace_rows)) dplyr::bind_rows(trace_rows) else
    .parlay_role_typed_empty("trace")
  substitutions <- if (length(substitution_rows)) {
    dplyr::bind_rows(substitution_rows)
  } else {
    .parlay_ranked_typed_empty_substitutions()
  }
  actual_pattern <- lapply(seq_len(width), function(slot) {
    block <- legs[legs$group_slot == slot, , drop = FALSE]
    pattern_vector <- rep(NA_integer_, n_legs)
    if (nrow(block)) pattern_vector[block$round] <- block$n_outcomes
    pattern_vector
  })
  list(role_legs = legs, trace = trace, substitutions = substitutions,
       actual_pattern = actual_pattern,
       cursors = cursors)
}

#' Construct deterministic role candidate groups from ranked selections
#'
#' Stage-2 candidate generation, superseding the obsolete all-fixtures/all-roles
#' score scan. It consumes the ranked direction table produced by
#' [rank_outcome_selections()] and never looks at the issue budget or applies the
#' final reuse/overlap caps.
#'
#' The bound cutoff, ranking priority and receipt hashes are read from the
#' attributes of `ranked_selections`. The carried `input_hash` must verify against
#' the EXPLICIT `input_snapshot` attribute (`rlang::hash(input_snapshot)`), and the
#' original pre-rank snapshot is then re-ranked with the carried cutoff and priority
#' through [rank_outcome_selections()] and [prepare_outcome_selections()]. The
#' canonical columns, rank, probability table and receipt hashes of the supplied
#' table must all match that recomputation. The derived probability table is rebuilt
#' from the ranked table's own `win`, `draw` and `lose` columns in canonical
#' `W`/`D`/`L` order. No clock value and no hidden state are read.
#'
#' Generation walks a finite, deterministic trajectory of fixed-width cohorts. The
#' cohort width is derived from the ranked table alone as the maximum, over the
#' supplied role queues (role 3 and role 2), of the number of DISTINCT fixtures in
#' that queue, and is at least `1`. It never depends on `max_candidates`, so the
#' first cohort has the identical layout under `max_candidates = 1`, `2` or `NULL`.
#' A cohort is a batch of `cohort_width` candidate slots; each global round fills
#' one leg per slot over the pattern sorted descending, and the turn order is the
#' deterministic snake (`1..W` on odd rounds, `W..1` on even rounds) flipped by a
#' per-cohort phase. The per-role queue cursors are carried across cohorts.
#'
#' Every cohort is built COMPLETELY before anything is emitted. Complete groups are
#' then emitted in stable candidate order (cohort order, slot order), skipping
#' physical packages already emitted. `max_candidates` therefore truncates only the
#' emitted groups: for a positive `N` the emitted groups are a prefix of the `NULL`
#' output with identical group ids, fixture/role/mask legs and actual patterns (the
#' audit stopping metadata may differ). Two candidates that buy the same physical
#' package under the same roles and masks are one package; different complementary
#' directions of one fixture are different packages and both survive.
#'
#' Termination is generational and needs no hidden constant. The canonical state at
#' the START of a cohort is the tuple of per-role queue cursors plus the snake
#' phase; when a cohort would start from an already-seen state, construction stops
#' with `state_repeated` before re-running it. The state never includes the growing
#' set of emitted packages or any slot count.
#'
#' Each round takes the next unused choice from the named TARGET board: a
#' target-role-3 round walks the base-role-3 board, a target-role-2 round the
#' base-role-2 board and a target-role-1 round the base-role-1 board. When that
#' board has no unused choice the round falls back through the ordered boards of
#' [.parlay_ranked_fallback_boards()] (3 -> 2 only), the leg's `base_role`
#' records the board actually used, `n_outcomes` its real outcome count and the
#' fallback is recorded in `substitutions`. The chosen direction's mask is kept
#' exactly as ranked and is never upgraded, so a base-1 protected double is neither
#' mistaken for a single nor granted a triple's overlap exemption. Every board has
#' its own continuous cursor that wraps at the tail and is carried to the next group
#' rather than reset. Fewer distinct fixtures than legs stops with
#' `insufficient_fixtures`; an empty ranked table stops with `empty_inputs`. An incomplete slot is recorded in `shortages` and `trace`,
#' and never emitted in `groups`.
#'
#' @param ranked_selections A tibble returned by [rank_outcome_selections()]. Its
#'   `win`, `draw` and `lose` columns supply the derived probabilities; its `rank`,
#'   `selection_id`, `outcomes`, `base_role`, `n_outcomes`,
#'   `coverage_probability`, `entropy` and `p3`
#'   columns supply the ranked choices; and its `cutoff`, `cutoff_hash`, `priority`,
#'   `input_hash`, `input_snapshot` and `code_hash` attributes are validated against
#'   a full re-ranking of the snapshot. The `cutoff_hash` is the frozen cutoff
#'   receipt and must equal `rlang::hash(list(as.character(cutoff$issue_id),
#'   as.numeric(cutoff$cutoff_utc)))` for the carried `cutoff`; it is checked
#'   exactly and before any recomputation, so a `cutoff` attribute retimed alone
#'   (another instant or another issue) fails even when `settings` carry no cutoff.
#'   Only a fresh [rank_outcome_selections()] call rebuilds the receipt. The
#'   snapshot must be the original pre-rank selection table, so a swapped
#'   `input_hash`, a swapped snapshot and any tampered rank, metric, mask or
#'   probability all fail closed.
#' @param settings Explicit parlay settings snapshot from [parlay_settings()]. Only
#'   its `n_legs` drives construction. Its `issue_budget_cny` is carried through
#'   untouched and never influences the pool. When it carries its own `cutoff`, the
#'   identity must match the ranked table's cutoff.
#' @param pattern Integer vector of length `settings$n_legs`, each value 1, 2 or 3:
#'   the target role of each GLOBAL round. It is sorted descending internally.
#' @param max_candidates `NULL` (the default) to set no caller ceiling, or a single
#'   positive whole number: the maximum number of UNIQUE COMPLETE candidate groups
#'   to EMIT. It bounds emitted groups, not attempted slots, and is never derived
#'   from a budget. `NULL` runs the deterministic trajectory to its own
#'   `state_repeated`/shortage termination. A non-positive, non-whole, infinite,
#'   vector or non-numeric value is an error, as is a whole number above
#'   `.Machine$integer.max`.
#' @param prematch_sp Pre-cutoff SP tibble (`fixture_id`, `outcome`, `quote_at`,
#'   `sp_raw`, `source_url`) frozen into the pool. Every `quote_at` must be STRICTLY
#'   before the bound cutoff. The default typed-empty table is the explicit
#'   historical "SP missing" state.
#'
#' @return A named list:
#'   * `role_legs` -- tibble(group_slot, group_id, fixture_id, selection_id,
#'     round, base_role, n_outcomes, allowed_outcomes, retained_probability),
#'     one row per leg of an emitted complete group. `base_role` is its classifier
#'     board; `n_outcomes` is the actual retained mask size (1, 2 or 3);
#'   * `groups` -- tibble(group_slot, group_id, complete), one row per emitted
#'     unique complete candidate, with `complete = TRUE`;
#'   * `trace` -- tibble(round, turn, group_slot, role, fixture_id, action, reason),
#'     one row per turn of every built cohort with `group_slot` remapped to the
#'     stable emitted slot (NA for turns of slots that were not emitted);
#'   * `shortages` -- tibble(group_slot, group_id, round, turn, role, reason);
#'   * `group_patterns` -- tibble(group_slot, group_id, target_pattern,
#'     actual_pattern), the target audit pattern and the selected outcome counts in round order,
#'     remapped to the emitted stable slots;
#'   * `substitutions` -- tibble(group_slot, group_id, round, fixture_id,
#'     selection_id, target_role, base_role, n_outcomes, reason) for every
#'     `target_role_shortage_board_fallback`, remapped to the emitted stable slots;
#'   * `generation_status` -- list(generated_count integer, stop_reason character,
#'     max_candidates NULL or integer, cohort_width integer, attempted_count
#'     integer). `stop_reason` is one of `max_candidates`, `state_repeated`,
#'     `insufficient_fixtures`, `empty_inputs`;
#'   * `cutoff`, `cutoff_hash`, `construction_code_hash`, `settings`,
#'     `probability_hash`, `probabilities`,
#'     `prematch_sp`, `prematch_sp_hash`, `ranked_selections`,
#'     `ranked_selections_hash` and the target `pattern` -- the frozen context.
#'
#' @section Errors:
#' `ranked_selections` is an error when it is not a tibble, when its `rank` or
#' receipt attributes (`cutoff`, `cutoff_hash`, `priority`, `input_hash`,
#' `input_snapshot`, `code_hash`) are missing or malformed, when `cutoff_hash`
#' does not equal the frozen hash of the carried `cutoff`, when `input_hash` does
#' not verify against `input_snapshot`, when the bound cutoff is missing or
#' invalid, or when the canonical columns, rank, probability table or receipt
#' hashes disagree with a re-ranking of `input_snapshot` through
#' [rank_outcome_selections()] and [prepare_outcome_selections()]. `settings`,
#' `pattern` and `max_candidates` are errors when they fail their authoritative
#' validators (`max_candidates` also when it exceeds `.Machine$integer.max`), and
#' `prematch_sp` when a quote is at or after the cutoff.
#'
#' @details Pure deterministic construction over the supplied admitted pool. It
#'   performs no scraping, fitting, IO or betting and keeps no mutable state. Final
#'   reuse/overlap/budget admission remains external: this enumerates one
#'   deterministic generation trajectory, not every combination.
#' @examples
#' cutoff <- list(issue_id = "26098",
#'                cutoff_utc = as.POSIXct("2026-09-26 11:52:04", tz = "UTC"))
#' matches <- tibble::tibble(
#'   fixture_id = c("A", "B"),
#'   win = c(0.45, 0.40),
#'   draw = c(0.27, 0.30),
#'   lose = c(0.28, 0.30))
#' ranked <- rank_outcome_selections(prepare_outcome_selections(matches), cutoff)
#' settings <- parlay_settings()
#' settings$n_legs <- 2L
#' parlay_construct_role_groups(ranked, settings, pattern = c(2L, 2L),
#'                              max_candidates = 2L)
#' @export
parlay_construct_role_groups <- function(ranked_selections, settings, pattern,
                                         max_candidates = NULL,
                                         prematch_sp = match_typed_empty("prematch_sp")) {
  .parlay_role_validate_settings(settings)
  n_legs <- as.integer(settings$n_legs)
  role_pattern <- sort(.parlay_role_validate_pattern(pattern, n_legs),
                       decreasing = TRUE)
  ceiling <- .parlay_role_validate_max_candidates(max_candidates)

  receipt <- .parlay_ranked_validate_receipt(ranked_selections)
  cutoff <- receipt$cutoff
  # The cutoff identity is frozen into the pool so the evaluator can prove it was
  # never retimed, malformed or hash-swapped after construction.
  cutoff_hash <- .rank_outcome_cutoff_hash(cutoff)
  construction_code_hash <- .rank_outcome_code_hash(
    roots = "parlay_construct_role_groups")
  if (!is.null(settings$cutoff) &&
      (!identical(as.character(settings$cutoff$issue_id),
                  as.character(cutoff$issue_id)) ||
       !identical(as.numeric(settings$cutoff$cutoff_utc),
                  as.numeric(cutoff$cutoff_utc)))) {
    stop("parlay_construct_role_groups: settings cutoff does not match the ",
         "ranked-selection cutoff")
  }
  prematch_sp <- .parlay_role_validate_prematch_sp(prematch_sp, cutoff)
  prematch_sp_hash <- rlang::hash(prematch_sp)

  probabilities <- .parlay_ranked_probabilities(ranked_selections)
  # The probability table derived from the supplied ranked rows must equal the one
  # derived from the re-ranked snapshot; a tampered win/draw/lose column therefore
  # cannot survive the receipt check even when it leaves the rank order unchanged.
  # The comparison is canonical on (fixture_id, outcome) so a caller may still
  # reorder the ranked rows without breaking the receipt.
  probability_order <- function(table) {
    table[order(table$fixture_id, table$outcome, method = "radix"), ,
          drop = FALSE]
  }
  if (!identical(probability_order(probabilities),
                 probability_order(.parlay_ranked_probabilities(
                   receipt$recomputed)))) {
    stop("parlay_construct_role_groups: ranked_selections probabilities do not ",
         "match the re-ranked input_snapshot")
  }
  probability_hash <- rlang::hash(probabilities)
  ranked_hash <- rlang::hash(ranked_selections)

  empty_pool <- function(stop_reason, cohort_width) {
    list(
      role_legs = .parlay_role_typed_empty("legs"),
      groups = .parlay_role_typed_empty("groups"),
      trace = .parlay_role_typed_empty("trace"),
      shortages = .parlay_role_typed_empty("shortages"),
      group_patterns = .parlay_ranked_typed_empty_patterns(),
      substitutions = .parlay_ranked_typed_empty_substitutions(),
      generation_status = list(
        generated_count = 0L, stop_reason = stop_reason,
        max_candidates = ceiling, cohort_width = as.integer(cohort_width),
        attempted_count = 0L),
      cutoff = cutoff, settings = settings, probability_hash = probability_hash,
      probabilities = probabilities, pattern = role_pattern,
      ranked_selections = ranked_selections, ranked_selections_hash = ranked_hash,
      prematch_sp = prematch_sp, prematch_sp_hash = prematch_sp_hash,
      cutoff_hash = cutoff_hash, construction_code_hash = construction_code_hash)
  }

  queues <- list("3" = .parlay_ranked_queue(ranked_selections, 3L),
                 "2" = .parlay_ranked_queue(ranked_selections, 2L),
                 "1" = .parlay_ranked_queue(ranked_selections, 1L))
  # --- fail-closed pre-conditions -------------------------------------------
  if (!nrow(ranked_selections) ||
      (!nrow(queues[["3"]]) && !nrow(queues[["2"]]) && !nrow(queues[["1"]]))) {
    return(empty_pool("empty_inputs", 0L))
  }
  cohort_width <- .parlay_ranked_cohort_width(queues)
  distinct_fixtures <- length(unique(as.character(ranked_selections$fixture_id)))
  if (distinct_fixtures < n_legs) {
    return(empty_pool("insufficient_fixtures", cohort_width))
  }

  # --- deterministic trajectory ---------------------------------------------
  # `emitted` accumulates one record per emitted group with its stable emitted
  # slot, the cohort-local source slot, the cohort phase it came from, and its
  # actual pattern. Audit rows are remapped onto these stable slots at the end.
  cursors <- list("3" = 1L, "2" = 1L, "1" = 1L)
  phase <- 0L
  seen_states <- character(0)
  emitted_keys <- character(0)
  emitted <- list()
  emitted_patterns <- list()
  all_substitutions <- list()
  trace_rows <- list()
  shortage_rows <- list()
  generated_count <- 0L
  attempted_count <- 0L
  stop_reason <- "state_repeated"

  repeat {
    state_key <- .parlay_ranked_state_key(cursors, phase, queues)
    if (state_key %in% seen_states) {
      stop_reason <- "state_repeated"
      break
    }
    seen_states <- c(seen_states, state_key)
    room <- if (is.null(ceiling)) Inf else ceiling - generated_count
    if (room <= 0) {
      stop_reason <- "max_candidates"
      break
    }
    built <- .parlay_ranked_cohort(queues, cursors, phase, role_pattern,
                                   cohort_width, n_legs)
    source_phase <- phase
    cursors <- built$cursors
    phase <- 1L - phase
    attempted_count <- attempted_count + cohort_width

    accepted <- integer(0)
    cohort_shortages <- list()
    for (slot in seq_len(cohort_width)) {
      block <- built$role_legs[built$role_legs$group_slot == slot, , drop = FALSE]
      if (!nrow(block)) next
      if (nrow(block) != n_legs) {
        # An incomplete slot is reported but never emitted as a candidate.
        cohort_shortages[[length(cohort_shortages) + 1L]] <- tibble::tibble(
          group_slot = as.integer(slot), group_id = NA_character_,
          round = NA_integer_, turn = NA_integer_, role = NA_integer_,
          reason = "incomplete_candidate_group")
        next
      }
      key <- .parlay_ranked_candidate_signature(block)
      if (key %in% emitted_keys) {
        cohort_shortages[[length(cohort_shortages) + 1L]] <- tibble::tibble(
          group_slot = as.integer(slot), group_id = NA_character_,
          round = as.integer(block$round), turn = NA_integer_,
          role = as.integer(block$base_role),
          reason = "duplicate_candidate_package")
        next
      }
      if (length(accepted) >= room) next
      accepted <- c(accepted, slot)
      emitted_keys <- c(emitted_keys, key)
    }
    base_slot <- length(emitted)

    for (slot in accepted) {
      block <- built$role_legs[built$role_legs$group_slot == slot, , drop = FALSE]
      stable_slot <- as.integer(length(emitted) + 1L)
      block$group_slot <- stable_slot
      signature <- .parlay_ranked_candidate_signature(block)
      emitted[[stable_slot]] <- list(
        legs = block, actual_pattern = built$actual_pattern[[slot]],
        signature = signature, source_slot = as.integer(slot),
        source_phase = as.integer(source_phase))
      emitted_patterns[[stable_slot]] <- built$actual_pattern[[slot]]
    }
    # The trace audits every turn of the built cohort, including slots that were not
    # emitted. Its `group_slot` is remapped onto the stable emitted slot for accepted
    # groups and left NA for the rest, so it never exposes a cohort-local index.
    if (nrow(built$trace)) {
      remapped <- built$trace
      remapped$group_slot <- as.integer(
        base_slot + match(remapped$group_slot, accepted))
      trace_rows[[length(trace_rows) + 1L]] <- remapped
    }
    if (length(cohort_shortages)) {
      remapped_shortages <- dplyr::bind_rows(cohort_shortages)
      remapped_shortages$group_slot <- as.integer(
        base_slot + match(remapped_shortages$group_slot, accepted))
      shortage_rows[[length(shortage_rows) + 1L]] <- remapped_shortages
    }
    # Substitutions are remapped to the stable emitted slots WITHIN their own cohort
    # before accumulation: a substitution may only be attributed to a group that this
    # same cohort emitted. Substitutions of unemitted slots (incomplete or duplicate
    # packages) and of later duplicate cohorts are discarded here, so a global
    # first-source-slot match can no longer attach another cohort's fallback to an
    # unrelated group.
    if (nrow(built$substitutions)) {
      cohort_map <- match(built$substitutions$group_slot, accepted)
      kept <- !is.na(cohort_map)
      if (any(kept)) {
        cohort_subs <- built$substitutions[kept, , drop = FALSE]
        cohort_subs$group_slot <- as.integer(base_slot + cohort_map[kept])
        all_substitutions[[length(all_substitutions) + 1L]] <- cohort_subs
      }
    }
    generated_count <- generated_count + length(accepted)
    if (!is.null(ceiling) && generated_count >= ceiling) {
      stop_reason <- "max_candidates"
      break
    }
    # Termination is generational: the loop stops when a cohort would START from an
    # already-seen cursor-plus-phase-plus-board state. A cohort that emitted nothing
    # is NOT by itself evidence of exhaustion, because the cursors may still have
    # advanced to a fresh start state; the next iteration's state check decides. With
    # `max_candidates = NULL` this walks the finite state space exactly (each start
    # state is visited once), so no duplicate group is ever generated forever.
  }

  # --- stable identities and audit remap ------------------------------------
  # A group id binds the cutoff instant, the source slot and the canonical PHYSICAL
  # signature (every fixture together with its realized outcome combination), so two
  # candidates over the same fixtures but with a different retained outcome set get
  # distinct ids and the same physical package gets the same id in any run of the
  # same trajectory. This is the unique purchase key: it prevents the same physical
  # ticket from being bought or charged twice.
  n_emitted <- length(emitted)
  if (n_emitted) {
    source_slots <- vapply(emitted, function(record) record$source_slot, integer(1))
    source_phases <- vapply(emitted, function(record) record$source_phase, integer(1))
    signatures <- vapply(emitted, function(record) record$signature, character(1))
    ids <- paste0(
      vapply(emitted, function(record) {
        .parlay_role_group_id(as.character(record$legs$fixture_id))
      }, character(1)),
      "@", as.numeric(cutoff$cutoff_utc), ":P", as.integer(source_slots),
      ":", substr(vapply(signatures, rlang::hash, character(1)), 1L, 12L))
    mapped <- dplyr::bind_rows(lapply(seq_len(n_emitted), function(i) {
      block <- emitted[[i]]$legs
      block$group_id <- ids[[i]]
      block$source_slot <- source_slots[[i]]
      block$source_phase <- source_phases[[i]]
      block
    }))
    mapped <- mapped[, c("group_slot", "group_id", "fixture_id", "selection_id",
                         "round", "base_role", "n_outcomes", "allowed_outcomes",
                         "retained_probability"),
                     drop = FALSE]
    mapped <- mapped[order(mapped$group_slot, mapped$round, method = "radix"),
                     , drop = FALSE]
    groups <- tibble::tibble(
      group_slot = as.integer(seq_len(n_emitted)),
      group_id = ids,
      complete = rep(TRUE, n_emitted))
    group_patterns <- tibble::tibble(
      group_slot = as.integer(seq_len(n_emitted)),
      group_id = ids,
      target_pattern = rep(list(as.integer(role_pattern)), n_emitted),
      actual_pattern = emitted_patterns)
    # Substitutions were already remapped to their stable emitted slots cohort by
    # cohort, so only the binding to the emitted group ids remains here.
    substitutions <- if (length(all_substitutions)) {
      all_sub <- dplyr::bind_rows(all_substitutions)
      all_sub$group_id <- ids[all_sub$group_slot]
      all_sub[, c("group_slot", "group_id", "round", "fixture_id", "selection_id",
                  "target_role", "base_role", "n_outcomes", "reason"),
              drop = FALSE]
    } else {
      .parlay_ranked_typed_empty_substitutions()
    }
  } else {
    mapped <- .parlay_role_typed_empty("legs")
    groups <- .parlay_role_typed_empty("groups")
    group_patterns <- .parlay_ranked_typed_empty_patterns()
    substitutions <- .parlay_ranked_typed_empty_substitutions()
  }

  trace <- if (length(trace_rows)) dplyr::bind_rows(trace_rows) else
    .parlay_role_typed_empty("trace")
  shortages <- if (length(shortage_rows)) dplyr::bind_rows(shortage_rows) else
    .parlay_role_typed_empty("shortages")

  list(role_legs = mapped, groups = groups, trace = trace,
       shortages = shortages, group_patterns = group_patterns,
       substitutions = substitutions,
       generation_status = list(
         generated_count = as.integer(generated_count),
         stop_reason = stop_reason, max_candidates = ceiling,
         cohort_width = as.integer(cohort_width),
         attempted_count = as.integer(attempted_count)),
       cutoff = cutoff, settings = settings, probability_hash = probability_hash,
       probabilities = probabilities, pattern = role_pattern,
       ranked_selections = ranked_selections, ranked_selections_hash = ranked_hash,
       prematch_sp = prematch_sp, prematch_sp_hash = prematch_sp_hash,
       cutoff_hash = cutoff_hash, construction_code_hash = construction_code_hash)
}
