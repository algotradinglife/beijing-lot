#' Capture real Titan European and total markets for a schedule subset
#'
#' Captures full pregame quote histories, without averaging or cutoff selection.
#' Nowscore fixture ID, both names and kickoff must match Titan's native metadata.
#' Network requests are spaced at least one second apart. Raw responses and an
#' observation receipt are saved before parsing. Failed fixtures remain in coverage.
#' @param schedule Schedule tibble from [fetch_issue_schedule()], optionally filtered.
#' @param raw_dir Explicit writable directory for immutable capture snapshots.
#' @param backend Explicit [python_backend()] handle.
#' @param totals_company_ids Character vector of Titan totals company IDs; default
#'   "8" is Bet365. This is a different namespace from European company IDs.
#' @param timeout Positive request timeout, seconds.
#' @param retries Integer transient retries, zero through three.
#' @param pages NULL for live capture, or URL-named list of lists with raw body and
#'   original ISO observed_at for deterministic offline replay.
#' @return List of tibbles euro, totals, companies, diagnostics, coverage, captures,
#'   and receipt_path. Public timestamps use Asia/Shanghai. Euro prices are decimal;
#'   total Hong Kong prices are converted to decimal by adding one. No SP is inferred.
#'   Empty schedule returns typed empty tables without requests. Missing data is
#'   never synthesized. Source quote time is distinct from actual observed_at.
#' @export
fetch_match_markets <- function(schedule, raw_dir, backend,
                                totals_company_ids = "8", timeout = 25,
                                retries = 2L, pages = NULL) {
  if (!tibble::is_tibble(schedule)) stop("schedule must be a tibble")
  required <- c("fixture_key", "provider_id_nowscore", "home_nowscore", "away_nowscore", "kickoff_at")
  if (!all(required %in% names(schedule))) stop("schedule lacks required Nowscore identity fields")
  checkmate::assert_string(raw_dir, min.chars = 1, na.ok = FALSE)
  checkmate::assert_character(totals_company_ids, min.len = 1, any.missing = FALSE, unique = TRUE)
  checkmate::assert_number(timeout, lower = .001, finite = TRUE)
  checkmate::assert_integerish(retries, lower = 0, upper = 3, len = 1, any.missing = FALSE)
  if (!inherits(backend, "python_backend")) stop("backend must be a python_backend")
  if (!inherits(schedule$kickoff_at, "POSIXct") || anyNA(schedule$kickoff_at)) stop("schedule kickoff_at must be known timestamps")
  module <- reticulate::import("beidan_backend.market_capture.service", convert = FALSE)
  expected <- file.path(backend$root, "beidan_backend", "market_capture", "service.py")
  if (!identical(normalizePath(reticulate::py_to_r(module$`__file__`)), normalizePath(expected))) {
    stop("Market backend loaded from another package location")
  }
  fixtures <- lapply(seq_len(nrow(schedule)), function(i) {
    list(fixture_id = schedule$fixture_key[[i]],
         provider_id_nowscore = schedule$provider_id_nowscore[[i]],
         home_nowscore = schedule$home_nowscore[[i]], away_nowscore = schedule$away_nowscore[[i]],
         kickoff_at = format(schedule$kickoff_at[[i]], "%Y-%m-%dT%H:%M:%OS6%z", tz = "Asia/Shanghai"))
  })
  result <- reticulate::py_to_r(module$fetch_markets(
    fixtures, raw_dir, as.list(totals_company_ids), timeout, as.integer(retries),
    if (is.null(pages)) NULL else issue_schedule_pages_dict(pages)))
  for (table in c("euro", "totals")) {
    data <- if (length(result[[table]])) {
      match_coerce_source_table(issue_schedule_rows_to_tibble(result[[table]]), table)
    } else match_typed_empty(table)
    result[[table]] <- dplyr::mutate(data, quote_at = lubridate::with_tz(quote_at, "Asia/Shanghai"))
  }
  templates <- list(
    companies = tibble::tibble(market = character(), company_id = character(), company_name = character()),
    diagnostics = tibble::tibble(market = character(), company_id = character(), reason = character(), count = integer()),
    coverage = tibble::tibble(fixture_id = character(), status = character(), detail = character(), euro_rows = integer(), totals_rows = integer()),
    captures = tibble::tibble(fixture_id = character(), market = character(), source_url = character(), observed_at = character(), raw_path = character(), sha256 = character())
  )
  for (table in names(templates)) {
    result[[table]] <- if (length(result[[table]])) dplyr::bind_rows(result[[table]]) else templates[[table]]
  }
  result$captures$observed_at <- issue_schedule_timestamp(result$captures$observed_at, "observed_at")
  result$companies <- dplyr::distinct(result$companies)
  return(result)
}

#' Connect captured markets and observed schedule to existing match inputs
#'
#' Does not infer historical scheduled status from a later finished/unknown row.
#' Actual observed_at is used for status availability. Historical market quotes
#' may be inspected independently when the old status ledger is unavailable.
#' @param schedule Schedule tibble used for capture; must contain known kickoff.
#' @param markets List returned by [fetch_match_markets()].
#' @return Validated match input list for [prepare_match_inputs()]. Its existing
#'   internal contract uses UTC instants; display with lubridate::with_tz when needed.
#'   prematch_sp is typed empty because European prices are not beidan SP.
#' @export
match_inputs_from_capture <- function(schedule, markets) {
  if (!tibble::is_tibble(schedule)) stop("schedule must be a tibble")
  checkmate::assert_list(markets)
  fixtures <- dplyr::transmute(schedule, issue_id, fixture_id = fixture_key, slot,
    provider_id = provider_id_nowscore, kickoff_at, handicap, sale_state,
    source_url = source_url_nowscore)
  status <- dplyr::transmute(schedule, issue_id, fixture_id = fixture_key,
    status = match_status, status_at = observed_at, available_at = observed_at,
    source_url = source_url_nowscore)
  tables <- list(fixtures = fixtures, euro = markets$euro, totals = markets$totals,
                 prematch_sp = match_typed_empty("prematch_sp"), match_status = status)
  if (!all(markets$euro$fixture_id %in% fixtures$fixture_id) ||
      !all(markets$totals$fixture_id %in% fixtures$fixture_id)) stop("Market fixture IDs do not match schedule")
  return(read_match_inputs(list(kind = "frames", tables = tables), unique(schedule$issue_id)))
}
