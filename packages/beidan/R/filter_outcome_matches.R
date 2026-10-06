# Fixture admission filter for the outcome-role pipeline.
#
# This is the FIRST stage of the pipeline: it decides which fixtures may enter
# classification at all, using the model's own Top1 outcome matched against the
# latest pre-cutoff raw starting price for that same outcome. It never ranks,
# never builds groups and never buys. The classifier itself stays quote-free: it
# receives probabilities only, so this module is the single place where a quote
# or a cutoff is read.
#
# The receipt reuses the pool's authoritative helpers rather than restating
# them: `.rank_outcome_cutoff_hash()` for the cutoff identity/instant scheme and
# `.rank_outcome_code_hash(roots = ...)` for the transitive implementation hash.

#' Order a quote ledger into its canonical evidence order
#'
#' Internal. Puts the evidence rows in the deterministic order the receipt hash
#' is taken over, so an order-independent hash and an exactly hashable snapshot
#' are produced from one rule.
#'
#' @param prematch_sp Validated `prematch_sp` tibble.
#' @return The same tibble with rows in canonical evidence order.
#' @noRd
.filter_outcome_sp_order <- function(prematch_sp) {
  keys <- order(as.character(prematch_sp$fixture_id),
                as.character(prematch_sp$outcome),
                as.numeric(prematch_sp$quote_at),
                as.numeric(prematch_sp$sp_raw),
                as.character(prematch_sp$source_url),
                method = "radix")
  prematch_sp[keys, , drop = FALSE]
}

#' Hash a quote ledger by its complete raw evidence
#'
#' Internal. Binds every column of the authoritative `prematch_sp` schema,
#' including `source_url`: the raw starting price, its fixture, outcome, instant
#' and the source identity it came from. Row order is normalized first, so an
#' otherwise identical ledger hashes the same regardless of row order, while a
#' retimed, re-priced or re-sourced ledger changes the hash.
#' `rlang::hash()` of the returned `prematch_sp_snapshot` reproduces this value.
#'
#' @param prematch_sp Validated `prematch_sp` tibble.
#' @return A single `rlang` hash of the complete evidence rows.
#' @noRd
.filter_outcome_sp_hash <- function(prematch_sp) {
  rlang::hash(.filter_outcome_sp_order(prematch_sp))
}

#' Typed-empty shapes for the filter's two audit tables
#'
#' Internal. The empty result of [filter_outcome_matches()] keeps full column
#' sets and types so an empty audit can be bound with a non-empty one.
#'
#' @param table One of `"excluded"` (one row per removed fixture) or `"audit"`
#'   (one row per input fixture).
#' @return A zero-row tibble with the named columns and types.
#' @noRd
.filter_outcome_typed_empty <- function(table) {
  if (identical(table, "excluded")) {
    return(tibble::tibble(
      fixture_id = character(0),
      top1_outcome = character(0),
      top1_probability = double(0),
      top1_sp = double(0),
      quote_at = as.POSIXct(character(0), tz = "UTC"),
      retained = logical(0),
      reason = character(0)
    ))
  }
  if (identical(table, "audit")) {
    return(tibble::tibble(
      fixture_id = character(0),
      top1_outcome = character(0),
      top1_probability = double(0),
      top1_sp = double(0),
      quote_at = as.POSIXct(character(0), tz = "UTC"),
      retained = logical(0),
      reason = character(0),
      missing_sp = logical(0)
    ))
  }
  stop("filter_outcome_matches: unknown audit table ", table)
}

#' One fixture's latest usable pre-cutoff quote for one outcome
#'
#' Internal. Selects the STRICTLY latest quote observed before the cutoff. Rows
#' whose `sp_raw` is missing, non-finite or non-positive cause an error.
#' Invalid evidence must never be treated as an absent quote. Any
#' positive finite decimal is a real quote, including a fractional price such as
#' `1.99`, so an unusual price is never discarded as malformed. When several
#' rows share the latest instant their raw values must agree; a genuine conflict
#' is an error rather than a silent pick between competing quotes.
#'
#' @param rows A `prematch_sp`-schema tibble already filtered to one fixture and
#'   one outcome.
#' @return A list with `usable` (logical), `sp_raw` (double), `quote_at`
#'   (POSIXct) and `invalid` (integer count of dropped invalid quotes). A usable
#'   quote is finite and strictly positive.
#' @noRd
.filter_outcome_latest_quote <- function(rows) {
  if (!nrow(rows)) {
    return(list(usable = FALSE, sp_raw = NA_real_,
                quote_at = as.POSIXct(NA_real_, origin = "1970-01-01", tz = "UTC")))
  }
  quote_at <- rows$quote_at
  sp_raw <- as.double(rows$sp_raw)
  invalid <- is.na(sp_raw) | !is.finite(sp_raw) | sp_raw <= 0
  if (any(invalid)) {
    stop("filter_outcome_matches: invalid pre-cutoff Top1 sp_raw; expected finite positive prices",
         call. = FALSE)
  }
  keep <- seq_len(nrow(rows))
  latest <- max(as.numeric(quote_at[keep]))
  at_latest <- keep[as.numeric(quote_at[keep]) == latest]
  values <- unique(sp_raw[at_latest])
  if (length(values) > 1L) {
    stop("filter_outcome_matches: conflicting sp_raw values at the latest ",
         "pre-cutoff quote for fixture ", as.character(rows$fixture_id[1L]),
         " outcome ", as.character(rows$outcome[1L]), call. = FALSE)
  }
  list(usable = TRUE, sp_raw = values,
       quote_at = quote_at[at_latest[1L]])
}

#' Filter matches to fixtures whose Top1 has an admissible pre-cutoff SP
#'
#' The pipeline's admission gate. Each row of a validated matches tibble is
#' classified with the authoritative [classify_outcomes()] and the fixture is
#' removed only when the latest quote for its model Top1 outcome observed
#' strictly before the explicit cutoff has a raw starting price strictly below
#' `sp_threshold`. A fixture whose valid Top1 quote meets the threshold is KEPT; so is a
#' fixture with no valid Top1 quote at all, which is kept and flagged as
#' missing. Only the Top1 outcome's quote is consulted; other outcomes' prices
#' never admit or remove a fixture.
#'
#' @param matches A `tibble` with one row per fixture: a unique, non-missing,
#'   non-empty character `fixture_id` (leading zeros preserved) and numeric
#'   `win`, `draw` and `lose` columns. Every other source column is preserved
#'   unchanged in the returned tibble.
#' @param prematch_sp A tibble in the authoritative `prematch_sp` schema
#'   (`fixture_id`, `outcome` in `W`/`D`/`L`, `quote_at` POSIXct, `sp_raw`
#'   double, `source_url`), validated by [match_validate_table()]. It may carry
#'   quotes for fixtures absent from `matches` and for instants after the
#'   cutoff; both are ignored rather than silently used.
#' @param cutoff The explicit decision cutoff, validated by
#'   [match_require_cutoff()]: a `temporal_learning`-style list carrying one UTC
#'   `cutoff_utc` and exactly one `issue_id`. It is never inferred from the
#'   clock, a hidden global or the quotes themselves. Only quotes strictly
#'   before it compete; a later observation can never change the selection.
#'
#' @param sp_threshold Finite plain scalar minimum Top1 decimal SP, at least 1;
#'   default 2. Equality is retained. Bound into the replay receipt.
#' @return A list with:
#'   * `matches`: the admitted subset of the input tibble, original columns and
#'     types preserved, original row order preserved, never carrying any audit
#'     column.
#'   * `excluded`: an audit tibble with one row per removed fixture and the
#'     columns `fixture_id`, `top1_outcome`, `top1_probability`, `top1_sp`,
#'     `quote_at`, `retained`, `reason`. `retained` is always `FALSE`.
#'   * `audit`: an audit tibble with one row per INPUT fixture, the `excluded`
#'     columns plus a trailing `missing_sp` logical flag. `retained` is `TRUE`
#'     for every kept fixture; `missing_sp` is additionally `TRUE` for a kept
#'     fixture that had no usable pre-cutoff Top1 quote. A removed fixture has
#'     both flags `FALSE` and `reason` `"sp_below_threshold"`; a kept fixture has
#'     `reason` `"retained"` or `"missing_sp"`.
#'   * `cutoff`: the validated cutoff object, unchanged.
#'   * `receipt`: a list binding the frozen evidence: `cutoff`, `cutoff_hash`
#'     (the pool's authoritative identity/instant scheme), `input_hash` and
#'     `input_snapshot` (the exact supplied `matches`, in caller order),
#'     `prematch_sp_hash` and `prematch_sp_snapshot` (the quote evidence in the
#'     canonical schema column order, whose `rlang::hash()` equals
#'     `prematch_sp_hash`), and `sp_threshold` (the explicit minimum),
#'     `sp_strict_below` (`TRUE`), `missing_sp_reason` (`"missing_sp"`) and
#'     `policy_hash` (hash of minimum, comparison and missing-SP policy) and
#'     `code_hash` (transitive hash of the loaded implementation). The receipt
#'     records no wall-clock time and reads no global, so repeated calls over the
#'     same inputs are identical.
#'
#'   An empty `matches` returns an empty admitted tibble with the same columns
#'   and typed-empty `excluded` and `audit` tables.
#'
#' @section Errors:
#' `matches` is an error when it is not a tibble, when `fixture_id` is missing,
#' duplicated, empty or not character, when a `win`/`draw`/`lose` column is
#' missing, non-numeric, missing-valued or rejected by [classify_outcomes()]
#' (including a triple that does not sum to one within `1e-9`), or when it
#' already carries a reserved audit column (`top1_outcome`, `top1_probability`,
#' `top1_sp`, `quote_at`, `retained`, `reason`, `missing_sp`).
#' `prematch_sp` is an error when it is not a tibble or violates its named
#' schema, and additionally when two usable quotes of one fixture and outcome
#' share the latest pre-cutoff instant with conflicting `sp_raw` values.
#' `cutoff` is an error when it is missing or malformed. Invalid quotes, unknown
#' outcomes and post-cutoff quotes are never silently treated as missing quotes:
#' invalid pre-cutoff Top1 prices and conflicting latest values stop the call.
#' Valid post-cutoff quotes do not participate in admission.
#'
#' @section Provenance:
#' The cutoff and both input tables are explicit caller arguments and are bound
#' by hash into the receipt. Both inputs are treated as read-only and are never
#' mutated. No fitting, no scraping, no IO and no hidden mutable state is
#' involved, and no learning cache is created or consulted.
#'
#' @examples
#' cutoff <- list(issue_id = "26098",
#'                cutoff_utc = as.POSIXct("2026-09-26 11:52:04", tz = "UTC"))
#' matches <- tibble::tibble(
#'   fixture_id = c("001", "002"),
#'   win = c(0.60, 0.40),
#'   draw = c(0.25, 0.30),
#'   lose = c(0.15, 0.30)
#' )
#' prematch_sp <- tibble::tibble(
#'   fixture_id = c("001", "002"),
#'   outcome = c("W", "W"),
#'   quote_at = as.POSIXct(c("2026-09-26 10:00:00", "2026-09-26 10:05:00"),
#'                         tz = "Asia/Shanghai"),
#'   sp_raw = c(1.85, 2.40),
#'   source_url = c("u1", "u2")
#' )
#' filtered <- filter_outcome_matches(matches, prematch_sp, cutoff)
#' filtered$matches
#' filtered$excluded
#' @export
filter_outcome_matches <- function(matches, prematch_sp, cutoff, sp_threshold = 2) {
  checkmate::assert_number(sp_threshold, lower = 1, finite = TRUE)
  if (is.object(sp_threshold) || !is.null(dim(sp_threshold))) {
    stop("`sp_threshold` must be a plain numeric scalar.", call. = FALSE)
  }
  match_require_cutoff(cutoff)

  if (!tibble::is_tibble(matches)) {
    stop("`matches` must be a tibble.", call. = FALSE)
  }
  required <- c("fixture_id", "win", "draw", "lose")
  missing_columns <- setdiff(required, names(matches))
  if (length(missing_columns) > 0L) {
    stop(
      sprintf("`matches` is missing required column(s): %s.",
              paste(missing_columns, collapse = ", ")),
      call. = FALSE
    )
  }
  # The reserved names are exactly the audit columns this function appends to its
  # own tables, plus `quote_at`, which names the matched quote. A pre-existing
  # one is refused rather than overwritten, so a caller's own evidence column is
  # never silently replaced by the filter's.
  reserved <- c("top1_outcome", "top1_probability", "top1_sp", "quote_at",
                "retained", "reason", "missing_sp")
  collisions <- intersect(reserved, names(matches))
  if (length(collisions) > 0L) {
    stop(
      sprintf(
        "`matches` already contains reserved audit column(s): %s; refusing to overwrite.",
        paste(collisions, collapse = ", ")
      ),
      call. = FALSE
    )
  }

  fixture_id <- matches[["fixture_id"]]
  if (!is.character(fixture_id)) {
    stop("`matches$fixture_id` must be a character vector.", call. = FALSE)
  }
  match_check_character_id(fixture_id, "matches$fixture_id")
  if (anyDuplicated(fixture_id)) {
    stop("`matches$fixture_id` must be unique.", call. = FALSE)
  }
  n <- nrow(matches)
  for (column in c("win", "draw", "lose")) {
    values <- matches[[column]]
    if (!is.numeric(values) || !is.null(dim(values)) || length(values) != n) {
      stop(sprintf("`matches$%s` must be a numeric column.", column),
           call. = FALSE)
    }
  }

  # The authoritative schema fixes both names and order; a caller may hand the
  # same column set in another order, which is normalized here rather than
  # weakening the shared validator or restating the schema locally. A non-tibble
  # data frame and a genuinely different column set still fail closed through
  # the shared validator.
  sp_schema <- match_table_schemas()[["prematch_sp"]]
  if (!tibble::is_tibble(prematch_sp)) {
    match_validate_table(prematch_sp, "prematch_sp")
  }
  missing_sp_columns <- setdiff(sp_schema$columns, names(prematch_sp))
  if (length(missing_sp_columns) > 0L ||
      !setequal(names(prematch_sp), sp_schema$columns)) {
    match_validate_table(prematch_sp, "prematch_sp")
  }
  quote_ledger <- match_validate_table(prematch_sp[sp_schema$columns],
                                       "prematch_sp")

  # Top1 is defined by the SAME rule as the classifier's first direction: highest
  # probability, ties broken win > draw > lose. The classifier never returns a
  # ranking, so it is recomputed here from the same inputs instead of being read
  # from the classifier's output.
  canonical <- c("win", "draw", "lose")
  labels <- c(win = "W", draw = "D", lose = "L")
  cutoff_utc <- cutoff$cutoff_utc

  admitted_rows <- integer(0)
  audit_rows <- vector("list", n)
  excluded_rows <- list()
  for (i in seq_len(n)) {
    probabilities <- c(
      win = as.double(matches[["win"]][[i]]),
      draw = as.double(matches[["draw"]][[i]]),
      lose = as.double(matches[["lose"]][[i]])
    )
    # The authoritative classifier validates the triple (finite, in [0, 1],
    # summing to one within 1e-9). Its choice set describes the fixture's base
    # category; Top1 itself is the first direction of the same ordering.
    classify_outcomes(probabilities[["win"]], probabilities[["draw"]],
                      probabilities[["lose"]])
    top1 <- canonical[order(-probabilities, c(1L, 2L, 3L))][1L]
    top1_outcome <- unname(labels[[top1]])
    top1_probability <- unname(probabilities[[top1]])

    # Chronology is applied to the complete ledger BEFORE any identity join, so a
    # post-cutoff observation cannot influence the selection and is not confused
    # with an absent one.
    prior <- quote_ledger[
      quote_ledger$fixture_id == fixture_id[[i]] &
        quote_ledger$outcome == top1_outcome &
        quote_ledger$quote_at < cutoff_utc,
      ,
      drop = FALSE
    ]
    quote <- .filter_outcome_latest_quote(prior)

    if (quote$usable && quote$sp_raw < sp_threshold) {
      retained <- FALSE
      missing_sp <- FALSE
      reason <- "sp_below_threshold"
    } else if (quote$usable) {
      retained <- TRUE
      missing_sp <- FALSE
      reason <- "retained"
    } else {
      retained <- TRUE
      missing_sp <- TRUE
      reason <- "missing_sp"
    }

    audit_rows[[i]] <- tibble::tibble(
      fixture_id = fixture_id[[i]],
      top1_outcome = top1_outcome,
      top1_probability = as.double(top1_probability),
      top1_sp = as.double(quote$sp_raw),
      quote_at = quote$quote_at,
      retained = retained,
      reason = reason,
      missing_sp = missing_sp
    )
    if (retained) {
      admitted_rows <- c(admitted_rows, i)
    } else {
      excluded_rows[[length(excluded_rows) + 1L]] <- audit_rows[[i]]
    }
  }

  audit <- if (n) dplyr::bind_rows(audit_rows) else .filter_outcome_typed_empty("audit")
  excluded <- if (length(excluded_rows)) {
    dplyr::bind_rows(excluded_rows) |>
      dplyr::select(dplyr::all_of(c("fixture_id", "top1_outcome",
                                    "top1_probability", "top1_sp", "quote_at",
                                    "retained", "reason")))
  } else {
    .filter_outcome_typed_empty("excluded")
  }
  admitted <- matches[admitted_rows, , drop = FALSE]

  receipt <- list(
    cutoff = cutoff,
    # Reuses the pool's authoritative cutoff identity/instant scheme instead of
    # restating it locally.
    cutoff_hash = .rank_outcome_cutoff_hash(cutoff),
    input_hash = rlang::hash(matches),
    input_snapshot = matches,
    prematch_sp_hash = .filter_outcome_sp_hash(quote_ledger),
    # One snapshot, in canonical column and evidence row order, so
    # `rlang::hash(prematch_sp_snapshot)` reproduces `prematch_sp_hash` exactly.
    prematch_sp_snapshot = .filter_outcome_sp_order(quote_ledger),
    policy_hash = rlang::hash(list(sp_threshold, TRUE, "missing_sp")),
    sp_threshold = sp_threshold,
    sp_strict_below = TRUE,
    missing_sp_reason = "missing_sp",
    # Reuses the pool's existing transitive implementation-hash helper: the
    # filter's own roots are added to the authoritative root set rather than a
    # third namespace walk being copied here.
    code_hash = .rank_outcome_code_hash(roots = c(
      "filter_outcome_matches", "match_validate_table", "match_typed_empty",
      "match_check_character_id", ".filter_outcome_sp_order",
      ".filter_outcome_sp_hash"
    ))
  )

  list(matches = admitted, excluded = excluded, audit = audit,
       cutoff = cutoff, receipt = receipt)
}
