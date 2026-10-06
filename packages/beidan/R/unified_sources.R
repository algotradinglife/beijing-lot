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
      summary_sp = row$summary_sp, summary_sp_raw = row$summary_sp_raw,
      parse_errors_json = as.character(jsonlite::toJSON(row$parse_errors, auto_unbox = FALSE)))
  })
  options <- unlist(lapply(result$data, function(row) lapply(row$options, function(option) {
    list(issue_id = row$issue, slot = row$slot, play = row$play, option = option$option,
      sp = option$sp, raw_sp = option$raw_sp)
  })), recursive = FALSE)
  if (is.null(options)) options <- list()
  list(events = .SourceRows(events, c(issue_id = "character", slot = "integer", native_id = "character",
    play = "character", home = "character", away = "character", status = "character", score = "character",
    halftime_score = "character", handicap = "integer", summary_sp = "double",
    summary_sp_raw = "character", parse_errors_json = "character")),
    options = .SourceRows(options, c(issue_id = "character", slot = "integer", play = "character",
      option = "character", sp = "double", raw_sp = "character")), receipt = result$receipt)
}

#' Read dual-source Euro and Titan totals through one cache
#' @inheritParams SourceIssue
#' @param fixtures Tibble with fixture_id, provider_id_nowscore, home_nowscore,
#'   away_nowscore and explicit POSIXct kickoff_at.
#' @param totals_company_ids Explicit native Titan total-goal company ID strings.
#' @return Typed tibbles euro (effective), euro_observations, euro_ledger,
#'   euro_current (source-published current price snapshots), euro_latest_history,
#'   totals, companies,
#'   diagnostics, receipts and gaps. Conflicts retain original source prices in
#'   ledger; valid primary history does not absorb extra secondary observations.
#'   Titan unavailable Euro may use Nowscore with SUPPLEMENTED provenance.
#'   Source identity conflicts fail closed. Totals has Titan coverage only.
#' @export
SourceMarkets <- function(client, fixtures, totals_company_ids, max_age, cache_only = FALSE) {
  if (!inherits(client, "source_api_client")) stop("client must be a source_api_client")
  checkmate::assert_number(max_age, lower = 0, finite = TRUE)
  checkmate::assert_flag(cache_only)
  if (!tibble::is_tibble(fixtures)) stop("fixtures must be a tibble")
  required <- c("fixture_id", "provider_id_nowscore", "home_nowscore", "away_nowscore", "kickoff_at")
  if (!all(required %in% names(fixtures)) || !inherits(fixtures$kickoff_at, "POSIXct") || anyNA(fixtures$kickoff_at)) stop("Missing fixture identity or typed kickoff")
  checkmate::assert_character(totals_company_ids, any.missing = FALSE, unique = TRUE)
  rows <- lapply(seq_len(nrow(fixtures)), function(i) list(fixture_id = fixtures$fixture_id[[i]],
    provider_id_nowscore = fixtures$provider_id_nowscore[[i]], home_nowscore = fixtures$home_nowscore[[i]],
    away_nowscore = fixtures$away_nowscore[[i]], kickoff_at = format(fixtures$kickoff_at[[i]], "%Y-%m-%dT%H:%M:%OS6%z", tz = "UTC")))
  result <- reticulate::py_to_r(client$client$markets(rows, as.list(totals_company_ids), max_age = max_age, cache_only = cache_only))
  base <- c(fixture_id = "character", company_id = "character", quote_at = "timestamp", odds_home = "double",
    odds_draw = "double", odds_away = "double", source_url = "character", source = "character")
  result$euro <- .SourceRows(result$euro, c(base, crosscheck_state = "character", independence = "character"))
  result$euro_latest_history <- .SourceRows(result$euro_latest_history, c(base, crosscheck_state = "character", independence = "character"))
  result$euro_current_observations <- .SourceRows(result$euro_current_observations, c(base, record_id = "character", company_name = "character", quote_phase = "character"))
  result$euro_current <- .SourceRows(result$euro_current, c(base, record_id = "character", company_name = "character", quote_phase = "character", odds_home_source = "character", odds_draw_source = "character", odds_away_source = "character", crosscheck_state = "character", independence = "character"))
  result$euro_current_ledger <- .SourceRows(result$euro_current_ledger, c(fixture_id = "character", company_id = "character", record_id = "character", company_name = "character",
    quote_at = "timestamp", option = "character", state = "character", titan = "double", nowscore = "double", selected_source = "character", independence = "character"))
  result$euro_observations <- .SourceRows(result$euro_observations, base)
  ledger <- lapply(result$euro_ledger, function(row) c(row[c("fixture_id", "company_id", "record_id", "company_name", "quote_at", "state", "independence")],
    list(titan_odds_home = row$titan$odds_home, titan_odds_draw = row$titan$odds_draw, titan_odds_away = row$titan$odds_away,
      nowscore_odds_home = row$nowscore$odds_home, nowscore_odds_draw = row$nowscore$odds_draw, nowscore_odds_away = row$nowscore$odds_away)))
  result$euro_ledger <- .SourceRows(ledger, c(fixture_id = "character", company_id = "character", record_id = "character", company_name = "character",
    quote_at = "timestamp", state = "character", independence = "character", titan_odds_home = "double", titan_odds_draw = "double", titan_odds_away = "double",
    nowscore_odds_home = "double", nowscore_odds_draw = "double", nowscore_odds_away = "double"))
  result$totals <- .SourceRows(result$totals, c(fixture_id = "character", company_id = "character", quote_at = "timestamp",
    line = "double", over_decimal = "double", under_decimal = "double", source_url = "character"))
  result$companies <- .SourceRows(result$companies, c(source = "character", company_id = "character", record_id = "character", company_name = "character", fixture_id = "character", market = "character"))
  result$diagnostics <- .SourceRows(result$diagnostics, c(fixture_id = "character", market = "character", company_id = "character", reason = "character", count = "integer"))
  result$gaps <- .SourceRows(result$gaps, c(fixture_id = "character", source = "character", market = "character", company_id = "character", error_type = "character"))
  result$receipts <- .SourceRows(lapply(result$receipts, function(row) row[c("fixture_id", "source", "url", "observed_at", "sha256", "capture_id", "cache_hit", "network_attempts", "request_key", "content_type", "cache_path", "processed_at")]),
    c(fixture_id = "character", source = "character", url = "character", observed_at = "timestamp", sha256 = "character", capture_id = "integer", cache_hit = "logical",
      network_attempts = "integer", request_key = "character", content_type = "character", cache_path = "character", processed_at = "timestamp"))
  result
}
