#' Open the subscription-free Titan/Nowscore resource interface
#' @param cache_path Explicit SQLite file; its data directory must exist.
#' @param backend python_backend handle selecting the project interpreter.
#' @return source_api_client. Creates cache schema but does not fetch.
#' @export
OpenSourceAPI <- function(cache_path, backend) {
  checkmate::assert_string(cache_path, min.chars = 1, na.ok = FALSE)
  module <- .ExtractionModule(backend, "unified_sources")
  structure(list(client = module$SourceClient(cache_path), backend = backend), class = "source_api_client")
}

#' Fetch, supplement and cross-check two-source factual fundamentals
#' @param client Handle from OpenSourceAPI.
#' @param identity Named list of string provider_id, home, away, home_id, away_id,
#'   kickoff_utc (explicit timezone). Names and IDs must match exactly; no aliases.
#' @param fixture_id Explicit issue/slot or other immutable fixture key.
#' @param max_age Maximum live-cache age in seconds; zero explicitly refreshes.
#' @param cache_only TRUE never fetches, allowing old saved captures.
#' @param capture_ids Optional named URL-to-integer list for pinned cache-only replay.
#' @return List of typed tibbles fields, ledger, source_states, gaps and receipts,
#'   plus implementation hashes. Original bytes remain in the cache. JSON values retain
#'   null versus empty arrays. Conflicts have missing effective value; missing
#'   primary fields can use verified Nowscore. No historical-learning admission.
#' @export
SourceFundamentals <- function(client, identity, fixture_id, max_age, cache_only = FALSE, capture_ids = NULL) {
  if (!inherits(client, "source_api_client")) stop("client must be a source_api_client")
  checkmate::assert_string(fixture_id, min.chars = 1, na.ok = FALSE)
  if (!is.null(capture_ids)) {
    if (!is.list(capture_ids) || is.null(names(capture_ids)) || anyDuplicated(names(capture_ids))) stop("capture_ids must be a named list")
    for (id in capture_ids) checkmate::assert_integerish(id, lower = 1, upper = .Machine$integer.max, len = 1, any.missing = FALSE)
  }
  result <- reticulate::py_to_r(client$client$fundamentals(identity, fixture_id,
    max_age = max_age, cache_only = cache_only, capture_ids = if (is.null(capture_ids)) NULL else
      lapply(capture_ids, as.integer)))
  result$records <- NULL
  result$fields <- .SourceRows(result$fields, c(fixture_id = "character", field = "character",
    state = "character", value_json = "character", selected_source = "character"))
  result$ledger <- .SourceRows(result$ledger, c(fixture_id = "character", field = "character",
    state = "character", titan_json = "character", nowscore_json = "character"))
  result$source_states <- .SourceRows(result$source_states,
    c(fixture_id = "character", source = "character", state = "character"))
  result$gaps <- .SourceRows(result$gaps, c(fixture_id = "character", source = "character",
    url = "character", error_type = "character"))
  result$receipts <- .SourceRows(lapply(result$receipts, function(row) {
    row[c("fixture_id", "source", "url", "observed_at", "sha256", "capture_id", "cache_hit", "network_attempts", "request_key", "content_type", "cache_path", "processed_at")]
  }), c(fixture_id = "character", source = "character", url = "character", observed_at = "timestamp",
    sha256 = "character", capture_id = "integer", cache_hit = "logical", network_attempts = "integer",
    request_key = "character", content_type = "character", cache_path = "character", processed_at = "timestamp"))
  result
}

#' Read a whole Nowscore issue from the shared cache
#' @inheritParams SourceFundamentals
#' @param issue_id Native issue ID string, preserving leading zeros.
#' @return List matches (provider fixture tibble) and receipt; no fabricated kickoff instant.
#' @export
SourceIssue <- function(client, issue_id, max_age, cache_only = FALSE) {
  if (!inherits(client, "source_api_client")) stop("client must be a source_api_client")
  checkmate::assert_number(max_age, lower = 0, finite = TRUE)
  checkmate::assert_flag(cache_only)
  ExtractNowscoreIssue(issue_id, client$client$cache_path |> reticulate::py_to_r(),
    client$backend, max_age = max_age, cache_only = cache_only)
}

#' Read observed Northsingle SP and result options
#' @inheritParams SourceIssue
#' @param typeid Native play ID integer: 5 SPF, 6 goals, 7 odd/even, 8 score,
#'   9 half/full time. Empty and partial option coverage remain explicit.
#' @return Typed event and option tibbles, receipt. Options are observations,
#'   never inferred complete vectors or substituted prematch probabilities.
#' @export
SourceBeidan <- function(client, issue_id, typeid, max_age, cache_only = FALSE) {
  if (!inherits(client, "source_api_client")) stop("client must be a source_api_client")
  checkmate::assert_int(typeid, lower = 5, upper = 9, na.ok = FALSE)
  result <- reticulate::py_to_r(client$client$beidan(issue_id, as.integer(typeid),
    max_age = max_age, cache_only = cache_only))
  events <- lapply(result$data, function(row) {
    list(issue_id = row$issue, slot = row$slot, native_id = row$native_match_id,
      play = row$play, home = row$home, away = row$away, status = row$status,
      score = row$score, halftime_score = row$halftime_score, handicap = row$handicap,
      parse_errors_json = as.character(jsonlite::toJSON(row$parse_errors, auto_unbox = FALSE)))
  })
  options <- unlist(lapply(result$data, function(row) lapply(row$options, function(option) {
    list(issue_id = row$issue, slot = row$slot, play = row$play, option = option$option,
      sp = option$sp, raw_sp = option$raw_sp)
  })), recursive = FALSE)
  if (is.null(options)) options <- list()
  list(events = .SourceRows(events, c(issue_id = "character", slot = "integer", native_id = "character",
    play = "character", home = "character", away = "character", status = "character", score = "character",
    halftime_score = "character", handicap = "integer", parse_errors_json = "character")),
    options = .SourceRows(options, c(issue_id = "character", slot = "integer", play = "character",
      option = "character", sp = "double", raw_sp = "character")), receipt = result$receipt)
}

#' Read Titan Euro and total-goal history using the shared resource cache
#' @inheritParams SourceIssue
#' @param fixtures Contracted fixture tibble for ExtractTitanMarkets.
#' @param totals_company_ids Explicit native company ID strings; no implicit mapping.
#' @return Euro/totals/company/diagnostic tibbles and raw receipts. These markets
#'   have Titan coverage only; fundamentals agreement does not verify odds.
#' @export
SourceMarkets <- function(client, fixtures, totals_company_ids, max_age, cache_only = FALSE) {
  if (!inherits(client, "source_api_client")) stop("client must be a source_api_client")
  checkmate::assert_number(max_age, lower = 0, finite = TRUE)
  checkmate::assert_flag(cache_only)
  ExtractTitanMarkets(fixtures, client$client$cache_path |> reticulate::py_to_r(),
    client$backend, totals_company_ids, max_age = max_age, cache_only = cache_only)
}
