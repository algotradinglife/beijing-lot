# Rank outcome-selection variants of an admitted fixture pool (#553).
#
# The third stage of the outcome-role pipeline. It consumes the authoritative
# `prepare_outcome_selections()` table and appends one integer `rank`. Ranking is
# per VARIANT, not per fixture: every row is a `(fixture, selection)` choice and
# each choice competes inside its own `base_role` board only. No labels, clock or
# IO are read and no model is fitted.

#' Identify fixed fixture-level classifier columns
#'
#' @return Character names of probabilities, fixture identity and base category.
#' @noRd
.rank_outcome_fixture_columns <- function() {
  c("fixture_id", "win", "draw", "lose", "base_role")
}

#' Read explicit filtering provenance from a selection table
#'
#' @param selections Selection tibble; no session state is read.
#' @return The carried filter_receipt attribute, or NULL when absent.
#' @noRd
.rank_outcome_filter_receipt <- function(selections) {
  attr(selections, "filter_receipt", exact = TRUE)
}

#' Hash the loaded implementation that produced a ranking receipt
#'
#' Internal. Conservative transitive binding of the loaded `beidan` namespace
#' code, not of a file path: the formals and body of [rank_outcome_selections()]
#' and of every namespace symbol its body reaches, including the
#' [prepare_outcome_selections()], [classify_outcomes()],
#' [match_require_cutoff()] and filter-verification implementations it depends on.
#'
#' @param roots Optional character vector of extra namespace symbols to bind
#'   transitively in addition to the ranking roots.
#' @return A single non-empty character hash. Missing implementation roots or
#'   an unavailable namespace or hash cause an error.
#' @noRd
.rank_outcome_code_hash <- function(roots = character(0)) {
  ns <- tryCatch(asNamespace("beidan"), error = function(e) NULL)
  if (is.null(ns)) stop("Implementation namespace is unavailable", call. = FALSE)
  roots <- unique(c(
    "rank_outcome_selections", "prepare_outcome_selections",
    "classify_outcomes", "match_require_cutoff",
    ".prepare_outcome_derived_columns",
    ".rank_outcome_fixture_columns", ".rank_outcome_filter_receipt",
    roots
  ))
  dependency_versions <- vapply(
    c("R", "Rcpp", "tibble", "dplyr", "tidyr", "rlang", "checkmate",
      "lubridate", "S7"),
    function(package) {
      version <- if (package == "R") as.character(getRversion()) else
        as.character(utils::packageVersion(package))
      paste0(package, "==", version)
    }, character(1))
  parts <- c("beidan-schema:rank_outcome_selections:1", dependency_versions)
  seen <- new.env(parent = emptyenv())
  visit <- function(name) {
    if (!nzchar(name) || exists(name, envir = seen, inherits = FALSE)) {
      return(invisible(NULL))
    }
    assign(name, TRUE, envir = seen)
    fn <- tryCatch(get(name, envir = ns, inherits = FALSE), error = function(e) NULL)
    if (!is.function(fn)) {
      parts <<- c(parts, paste0(
        name, "=",
        paste(paste(utils::capture.output(utils::str(fn)), collapse = " "),
              collapse = " ")
      ))
      return(invisible(NULL))
    }
    parts <<- c(
      parts,
      paste0(name, "::formals=",
             paste(utils::capture.output(base::args(fn)), collapse = " ")),
      paste0(name, "::body=", paste(deparse(body(fn)), collapse = " "))
    )
    symbols <- all.names(body(fn), functions = TRUE, unique = TRUE)
    for (symbol in symbols) {
      if (exists(symbol, envir = ns, inherits = FALSE)) visit(symbol)
    }
    invisible(NULL)
  }
  for (name in roots) {
    if (!exists(name, envir = ns, inherits = FALSE) ||
        !is.function(get(name, envir = ns, inherits = FALSE))) {
      stop("Missing implementation root: ", name, call. = FALSE)
    }
    visit(name)
  }
  hash <- rlang::hash(parts)
  if (is.null(hash) || !nzchar(hash)) {
    stop("Implementation hash is unavailable", call. = FALSE)
  }
  hash
}

#' Hash the frozen cutoff identity and instant of a ranking receipt
#'
#' Internal. The receipt binds exactly the two fields that identify a decision:
#' the issue id (as character) and the UTC instant (as numeric), using the SAME
#' scheme as the candidate pool's authoritative `cutoff_hash`. It carries no
#' clock, no inferred instant and no hidden state; the caller's validated cutoff
#' is the only input.
#'
#' @param cutoff A cutoff already accepted by [match_require_cutoff()].
#' @return A single 32-hex-character `rlang` hash of the cutoff identity.
#' @noRd
.rank_outcome_cutoff_hash <- function(cutoff) {
  rlang::hash(list(as.character(cutoff$issue_id),
                   as.numeric(cutoff$cutoff_utc)))
}

#' Verify filtering provenance by independent replay
#'
#' @param selections Expanded selection tibble with consistent fixture source columns.
#' @param receipt Explicit filtering receipt binding cutoff, inputs, quotes and code.
#' @return The verified receipt. Invalid binding, policy or source mutation errors.
#' @noRd
.rank_outcome_verify_filter_receipt <- function(selections, receipt) {
  if (!is.list(receipt)) {
    stop("`selections` carries a malformed `filter_receipt` attribute.",
         call. = FALSE)
  }
  required <- c("cutoff", "cutoff_hash", "input_hash", "input_snapshot",
                "prematch_sp_hash", "prematch_sp_snapshot",
                "sp_threshold", "sp_strict_below", "missing_sp_reason", "policy_hash",
                "code_hash")
  missing_fields <- setdiff(required, names(receipt))
  if (length(missing_fields) > 0L) {
    stop(
      sprintf(
        "`selections` filter_receipt is missing field(s): %s.",
        paste(missing_fields, collapse = ", ")
      ),
      call. = FALSE
    )
  }
  # The carried cutoff is a decision epoch; it must be valid on its own.
  match_require_cutoff(receipt$cutoff)
  # The filter exposes no separate raw input table in its receipt; its raw
  # evidence IS `prematch_sp_snapshot` (every schema column, including
  # `source_url`, in canonical row and column order). That snapshot is what the
  # authoritative filter is replayed with, and step 3 below proves it still
  # hashes to the receipt's `prematch_sp_hash`.
  replay <- tryCatch(
    filter_outcome_matches(receipt$input_snapshot, receipt$prematch_sp_snapshot,
                           receipt$cutoff, sp_threshold = receipt$sp_threshold),
    error = function(e) {
      stop(
        paste0("`selections` filter_receipt failed independent filter replay: ",
               conditionMessage(e)),
        call. = FALSE
      )
    }
  )
  fresh <- replay$receipt
  # 1. Implementation identity: the loaded filter code that produced the receipt
  #    must still be the code that runs now.
  if (!identical(receipt$code_hash, fresh$code_hash)) {
    stop(
      paste0("`selections` filter_receipt code_hash does not match the loaded ",
             "filter implementation; the receipt is stale."),
      call. = FALSE
    )
  }
  # 2. Cutoff identity and instant.
  if (!identical(receipt$cutoff_hash, fresh$cutoff_hash)) {
    stop(
      paste0("`selections` filter_receipt cutoff_hash does not verify against ",
             "its carried cutoff."),
      call. = FALSE
    )
  }
  # 3. Filter input and raw SP evidence, including its source identity.
  if (!identical(receipt$input_hash, fresh$input_hash) ||
      !identical(rlang::hash(receipt$input_snapshot),
                 receipt$input_hash)) {
    stop(
      "`selections` filter_receipt input_hash does not verify against its ",
      "input_snapshot or the filter replay.",
      call. = FALSE
    )
  }
  if (!identical(receipt$prematch_sp_hash, fresh$prematch_sp_hash) ||
      !identical(rlang::hash(receipt$prematch_sp_snapshot),
                 receipt$prematch_sp_hash) ||
      !identical(receipt$prematch_sp_snapshot, fresh$prematch_sp_snapshot)) {
    stop(
      paste0("`selections` filter_receipt quote evidence does not match the ",
             "filter replay; the raw SP ledger or its source identity changed."),
      call. = FALSE
    )
  }
  # 4. The admitted output: the pool's source rows must be exactly the replay's
  #    admitted rows. The comparison is made on a bare named list of the source
  #    columns, with every attribute dropped from BOTH sides, so neither the
  #    carried `filter_receipt` nor any other attribute of either tibble can
  #    decide the verdict.
  policy_fields <- c("sp_threshold", "sp_strict_below", "missing_sp_reason")
  if (!identical(receipt$policy_hash, fresh$policy_hash) ||
      !identical(receipt[policy_fields], fresh[policy_fields])) {
    stop("`selections` filter_receipt policy does not match independent replay.",
         call. = FALSE)
  }
  admitted_columns <- setdiff(names(selections), .prepare_outcome_derived_columns())
  if (!identical(admitted_columns, names(replay$matches))) {
    stop("`selections` source schema does not match filter_receipt replay.",
         call. = FALSE)
  }
  bare_columns <- function(table) {
    rows <- table[!duplicated(table$fixture_id), admitted_columns, drop = FALSE]
    rows <- rows[order(rows$fixture_id, method = "radix"), , drop = FALSE]
    columns <- as.list(rows)
    attributes(columns) <- list(names = admitted_columns)
    columns
  }
  if (!identical(bare_columns(selections), bare_columns(replay$matches))) {
    stop(
      paste0("`selections` does not match the fixtures admitted by its ",
             "filter_receipt replay."),
      call. = FALSE
    )
  }
  receipt
}

#' Rank outcome selections by coverage or balance
#'
#' Validate an authoritative [prepare_outcome_selections()] table, then append one
#' integer `rank`. Every row is one VARIANT: a `(fixture_id, selection_id)`
#' outcome choice. Each variant is ranked inside its own `base_role` board, so two
#' directions of the same fixture compete with each other instead of sharing one
#' fixture rank, and a base-role-`1` variant is never compared with a base-role-`2`
#' one.
#'
#' @param selections A `tibble` returned by [prepare_outcome_selections()]. It
#'   must contain the source columns `fixture_id` (character), `win`, `draw` and
#'   `lose` (numeric), the derived columns `selection_id` (integer), `outcomes`
#'   (list), `base_role` and `n_outcomes` (integer), `coverage_probability`,
#'   `entropy` and `p3` (double), plus any additional source columns. A
#'   pre-existing `rank` column is rejected. When the table carries a
#'   `filter_receipt` attribute, that receipt is verified by replaying
#'   [filter_outcome_matches()]. The function does not mutate `selections`.
#' @param cutoff Explicit decision cutoff validated by [match_require_cutoff()]:
#'   a `temporal_learning`-style list carrying a single UTC `cutoff_utc` and one
#'   `issue_id`. The cutoff is supplied by the caller and is never inferred from
#'   the clock or hidden state. When a `filter_receipt` is carried, this cutoff
#'   must be the same decision epoch as the receipt's.
#' @param priority One of `"coverage"` or `"balance"` (default `"coverage"`;
#'   the default `c("coverage", "balance")` resolves to `"coverage"`). Inside a
#'   board, coverage ranks by `coverage_probability` descending then normalized
#'   `entropy` descending, and balance ranks by `entropy` descending then
#'   `coverage_probability` descending. Base-role `3` variants all reach coverage
#'   `1`, so coverage ranks them by `p3` descending then `entropy` descending, and
#'   balance by `entropy` descending then `p3` descending. Remaining ties are
#'   broken by `fixture_id` ascending then `selection_id` ascending, which makes
#'   every board's rank integer, unique and consecutive.
#'
#' @return A `tibble` with the columns of `selections` plus an appended integer
#'   `rank`, ordered by `base_role` descending (`3`, `2`, `1`), `rank` ascending
#'   and `selection_id` ascending. A base-role-`1` variant is therefore not
#'   forced behind a base-role-`2` one by the overall order; the board is what
#'   carries the comparison. Source columns and the actual directional metrics
#'   are preserved unchanged. An empty `selections` returns a typed-empty tibble
#'   with the same columns and integer `rank`.
#'
#'   The returned tibble carries provenance attributes:
#'   * `cutoff`: the validated cutoff object, unchanged.
#'   * `cutoff_hash`: `rlang::hash(list(as.character(cutoff$issue_id),
#'     as.numeric(cutoff$cutoff_utc)))`, the frozen cutoff receipt. It uses the
#'     SAME scheme as the pool's authoritative `cutoff_hash`, so the exact cutoff
#'     identity and instant this ranking was built for can be verified before the
#'     ranking is trusted again. A ranking whose `cutoff` attribute is retimed
#'     without rebuilding no longer reproduces this hash.
#'   * `input_snapshot`: the EXACT original pre-rank `selections` table supplied by
#'     the caller, preserved as explicit table state (never a hidden global). It
#'     keeps the caller's original row order, its source attributes and therefore
#'     any carried filter receipt, so the pre-rank input can be re-ranked and
#'     verified downstream. It never contains a `rank` column.
#'   * `input_hash`: `rlang::hash(selections)`, binding the exact supplied table; it
#'     verifies against `input_snapshot` because
#'     `rlang::hash(input_snapshot) == input_hash` by construction.
#'   * `priority`: the resolved `"coverage"` or `"balance"` policy.
#'   * `filter_receipt`: the verified receipt carried by `selections`, or `NULL`
#'     when the pool carries none. Its presence records that the source rows were
#'     admitted by [filter_outcome_matches()] under a specific cutoff, quote
#'     ledger and implementation.
#'   * `code_hash`: a transitive hash of the loaded implementation
#'     ([rank_outcome_selections()], [prepare_outcome_selections()],
#'     [classify_outcomes()], [match_require_cutoff()] and, when a filter receipt
#'     is carried, the filter and its verification helpers).
#'
#'   The receipt binds the *supplied* table; it is not proof that the source rows
#'   were observed before the cutoff. No learning, availability or fitting claim
#'   is made and no clock value is recorded.
#'
#' @section Errors:
#' `selections` is an error when it is not a tibble, when a required column is
#' missing or has the wrong type, when a `rank` column already exists, when a
#' `(fixture_id, selection_id)` key is duplicated, when a fixture-level column
#' differs across the rows of one fixture, when `base_role` is not `1`, `2` or
#' `3`, when `n_outcomes` is not the length of `outcomes`, when the recomputed
#' [prepare_outcome_selections()] table disagrees on keys, `outcomes`, `base_role`
#' or any metric beyond `1e-12`, or when `win`, `draw` and `lose` no longer
#' satisfy [classify_outcomes()]. A carried `filter_receipt` is an error when it is
#' malformed, when its implementation binding is stale, when it does not verify
#' against its own carried cutoff, input snapshot or quote evidence, or when the
#' supplied pool is not the fixture set the filter admits under that receipt.
#' `cutoff` is an error when it is missing or malformed, and when a carried filter
#' receipt names a different cutoff identity or instant. `priority` is an error
#' when it is not exactly `"coverage"` or `"balance"`.
#'
#' @section Provenance:
#' The cutoff is explicit caller context; it is validated and carried through
#' untouched. The function reads no labels, no clock and no IO, performs no
#' fitting and adds no scraping. All chronology is replayed through the
#' authoritative filter and no cutoff, temporal or cache utility is reimplemented
#' here.
#'
#' @examples
#' cutoff <- list(
#'   issue_id = "26098",
#'   cutoff_utc = as.POSIXct("2026-09-26 11:52:04", tz = "UTC")
#' )
#' matches <- tibble::tibble(
#'   fixture_id = c("A", "D"),
#'   win = c(0.55, 0.85),
#'   draw = c(0.23, 0.10),
#'   lose = c(0.22, 0.05)
#' )
#' rank_outcome_selections(prepare_outcome_selections(matches), cutoff)
#' rank_outcome_selections(prepare_outcome_selections(matches), cutoff, "balance")
#' @export
rank_outcome_selections <- function(selections, cutoff,
                                    priority = c("coverage", "balance")) {
  if (identical(priority, c("coverage", "balance"))) {
    priority <- "coverage"
  }
  if (!is.character(priority) || length(priority) != 1L || is.na(priority) ||
      !priority %in% c("coverage", "balance")) {
    stop("`priority` must be exactly \"coverage\" or \"balance\".", call. = FALSE)
  }

  match_require_cutoff(cutoff)

  if (!tibble::is_tibble(selections)) {
    stop("`selections` must be a tibble.", call. = FALSE)
  }
  if ("rank" %in% names(selections)) {
    stop(
      "`selections` already contains a `rank` column; refusing to overwrite.",
      call. = FALSE
    )
  }

  required_source <- c("fixture_id", "win", "draw", "lose")
  derived <- .prepare_outcome_derived_columns()
  missing_columns <- setdiff(c(required_source, derived), names(selections))
  if (length(missing_columns) > 0L) {
    stop(
      sprintf(
        "`selections` is missing required column(s): %s.",
        paste(missing_columns, collapse = ", ")
      ),
      call. = FALSE
    )
  }

  require_type <- function(name, ok, expected) {
    if (!ok) {
      stop(
        sprintf("`selections$%s` must be %s.", name, expected),
        call. = FALSE
      )
    }
  }
  require_type("fixture_id", is.character(selections[["fixture_id"]]),
               "a character vector")
  require_type("selection_id", is.integer(selections[["selection_id"]]),
               "an integer vector")
  require_type("outcomes", is.list(selections[["outcomes"]]),
               "a list column")
  for (column in c("base_role", "n_outcomes")) {
    require_type(column, is.integer(selections[[column]]),
                 "an integer vector")
  }
  for (metric in c("coverage_probability", "entropy", "p3")) {
    require_type(metric, is.double(selections[[metric]]), "a double vector")
  }
  for (probability in c("win", "draw", "lose")) {
    require_type(probability, is.numeric(selections[[probability]]),
                 "a numeric vector")
  }

  if (anyNA(selections[["selection_id"]])) {
    stop("`selections$selection_id` must be non-missing.", call. = FALSE)
  }
  if (any(selections[["selection_id"]] < 1L)) {
    stop("`selections$selection_id` must be positive.", call. = FALSE)
  }
  if (anyNA(selections[["base_role"]]) ||
      any(!selections[["base_role"]] %in% c(1L, 2L, 3L))) {
    stop(
      "`selections$base_role` must contain only 1, 2 or 3.",
      call. = FALSE
    )
  }
  if (anyNA(selections[["n_outcomes"]]) ||
      any(selections[["n_outcomes"]] != lengths(selections[["outcomes"]]))) {
    stop(
      paste0("`selections$n_outcomes` must be the number of selected outcomes ",
             "in each row."),
      call. = FALSE
    )
  }

  keys <- paste(selections[["fixture_id"]], selections[["selection_id"]],
                sep = "\r")
  if (anyDuplicated(keys)) {
    stop(
      "`selections` contains duplicate (fixture_id, selection_id) keys.",
      call. = FALSE
    )
  }

  source_columns <- setdiff(names(selections), derived)
  fixture_columns <- intersect(.rank_outcome_fixture_columns(), names(selections))
  fixture_values <- selections[["fixture_id"]]
  unique_fixtures <- unique(fixture_values)
  group_index <- match(fixture_values, unique_fixtures)
  consistent_columns <- union(source_columns, fixture_columns)
  for (column in consistent_columns) {
    values <- selections[[column]]
    for (group in seq_along(unique_fixtures)) {
      members <- values[group_index == group]
      first <- members[[1L]]
      consistent <- all(vapply(
        members,
        function(value) identical(value, first),
        logical(1)
      ))
      if (!consistent) {
        stop(
          sprintf(
            "`selections$%s` is inconsistent across rows of one fixture.",
            column
          ),
          call. = FALSE
        )
      }
    }
  }

  # The carried filter receipt, when present, is verified BEFORE the ranking is
  # built: a stale or tampered provenance record never produces a fresh rank.
  filter_receipt <- .rank_outcome_filter_receipt(selections)
  if (!is.null(filter_receipt)) {
    .rank_outcome_verify_filter_receipt(selections, filter_receipt)
    filter_cutoff <- filter_receipt$cutoff
    if (!identical(as.character(filter_cutoff$issue_id),
                   as.character(cutoff$issue_id)) ||
        !identical(as.numeric(filter_cutoff$cutoff_utc),
                   as.numeric(cutoff$cutoff_utc))) {
      stop(
        paste0("`cutoff` is not the decision epoch of the carried ",
               "`filter_receipt`; the ranking cutoff was retimed without ",
               "rebuilding the filter artifact."),
        call. = FALSE
      )
    }
  }

  unique_rows <- selections[!duplicated(fixture_values), source_columns,
                            drop = FALSE]
  single_threshold <- attr(selections, "single_threshold", exact = TRUE)
  if (is.null(single_threshold)) stop("missing single_threshold classification context", call. = FALSE)
  dc_protection <- attr(selections, "dc_protection", exact = TRUE)
  role_allocation <- attr(selections, "role_allocation", exact = TRUE)
  if (!is.null(role_allocation)) {
    match_require_cutoff(role_allocation$cutoff)
    if (!identical(.rank_outcome_cutoff_hash(role_allocation$cutoff),
                   .rank_outcome_cutoff_hash(cutoff))) {
      stop("role_allocation cutoff does not match ranking cutoff", call. = FALSE)
    }
  }
  recomputed <- prepare_outcome_selections(unique_rows, single_threshold = single_threshold,
                                           dc_protection = dc_protection,
    role_allocation = role_allocation)

  sort_keys <- function(table) {
    table[order(table[["fixture_id"]], table[["selection_id"]],
                method = "radix"), , drop = FALSE]
  }
  actual <- sort_keys(selections)
  expected <- sort_keys(recomputed)
  if (nrow(actual) != nrow(expected) ||
      !identical(actual[["fixture_id"]], expected[["fixture_id"]]) ||
      !identical(actual[["selection_id"]], expected[["selection_id"]])) {
    stop(
      paste0(
        "`selections` choices do not match the recomputed ",
        "prepare_outcome_selections() keys; missing or extra selections."
      ),
      call. = FALSE
    )
  }
  if (!identical(actual[["outcomes"]], expected[["outcomes"]]) ||
      !identical(actual[["base_role"]], expected[["base_role"]]) ||
      !identical(actual[["n_outcomes"]], expected[["n_outcomes"]])) {
    stop(
      paste0("`selections` outcomes, base_role and n_outcomes do not match the ",
             "recomputed classifier."),
      call. = FALSE
    )
  }
  for (metric in c("coverage_probability", "entropy", "p3")) {
    observed <- actual[[metric]]
    reference <- expected[[metric]]
    matches <- (is.na(observed) & is.na(reference)) |
      (!is.na(observed) & !is.na(reference) &
         abs(observed - reference) <= 1e-12)
    if (!all(matches)) {
      stop(
        sprintf(
          "`selections$%s` does not match the recomputed metric.",
          metric
        ),
        call. = FALSE
      )
    }
  }
  for (column in source_columns) {
    if (!identical(actual[[column]], expected[[column]])) {
      stop(
        sprintf(
          "`selections$%s` source column does not match the recomputation.",
          column
        ),
        call. = FALSE
      )
    }
  }

  input_hash <- rlang::hash(selections)
  filter_roots <- if (is.null(filter_receipt)) {
    character(0)
  } else {
    c("filter_outcome_matches", ".rank_outcome_verify_filter_receipt")
  }
  metadata <- list(
    cutoff = cutoff,
    cutoff_hash = .rank_outcome_cutoff_hash(cutoff),
    input_hash = input_hash,
    input_snapshot = selections,
    priority = priority,
    single_threshold = single_threshold,
    dc_protection = dc_protection,
    role_allocation = role_allocation,
    filter_receipt = filter_receipt,
    code_hash = .rank_outcome_code_hash(filter_roots)
  )

  ranked <- actual
  ranked[["rank"]] <- NA_integer_
  if (nrow(ranked) > 0L) {
    for (role_value in sort(unique(ranked[["base_role"]]), decreasing = TRUE)) {
      board <- which(ranked[["base_role"]] == role_value)
      metrics <- ranked$coverage_probability[board]
      balance <- ranked$entropy[board]
      p3 <- ranked$p3[board]
      if (role_value == 3L) {
        # Base-role-3 variants always select all three outcomes, so coverage is
        # constant at 1; the least likely outcome is the discriminating metric.
        ord <- if (priority == "coverage") {
          order(-p3, -balance, ranked$fixture_id[board],
                ranked$selection_id[board], method = "radix")
        } else {
          order(-balance, -p3, ranked$fixture_id[board],
                ranked$selection_id[board], method = "radix")
        }
      } else {
        ord <- if (priority == "coverage") {
          order(-metrics, -balance, ranked$fixture_id[board],
                ranked$selection_id[board], method = "radix")
        } else {
          order(-balance, -metrics, ranked$fixture_id[board],
                ranked$selection_id[board], method = "radix")
        }
      }
      # Consecutive unique integers within the board: the order is total, so no
      # two variants share a rank.
      ranked[["rank"]][board[ord]] <- seq_along(board)
    }
    ranked <- ranked[order(-ranked[["base_role"]], ranked[["rank"]],
                           ranked[["selection_id"]], method = "radix"),
                     , drop = FALSE]
  }
  ranked[["rank"]] <- as.integer(ranked[["rank"]])

  do.call(structure, c(list(ranked), metadata))
}
