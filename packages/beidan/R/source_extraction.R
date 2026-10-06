#' Import an extraction module from the explicitly selected package backend
#' @param backend Initialized python_backend handle.
#' @param name Bundled module basename.
#' @return Python module; errors on a different package location. No network I/O.
.ExtractionModule <- function(backend, name) {
  if (!inherits(backend, "python_backend")) stop("backend must be a python_backend")
  module <- reticulate::import(paste0("beidan_backend.", name), convert = FALSE)
  actual <- normalizePath(reticulate::py_to_r(module$`__file__`), mustWork = TRUE)
  expected <- normalizePath(file.path(backend$root, "beidan_backend", paste0(name, ".py")), mustWork = TRUE)
  if (!identical(actual, expected)) stop("Extraction backend loaded from another package location")
  return(module)
}

#' Convert contracted source records to a typed tibble
#' @param rows List of named records; Python None becomes NULL.
#' @param schema Named character vector: character, double, integer, logical,
#'   timestamp (POSIXct UTC), or date (Date).
#' @return Tibble preserving row order, IDs, zero, empty strings and nullable
#'   cells. Empty input has the same schema. Invalid scalar types fail closed.
.SourceRows <- function(rows, schema) {
  if (!is.list(rows) || is.null(names(schema)) || anyDuplicated(names(schema))) stop("Invalid records/schema")
  columns <- lapply(names(schema), function(column) {
    kind <- schema[[column]]
    missing <- switch(kind, character = NA_character_, double = NA_real_,
      integer = NA_integer_, logical = NA, timestamp = NA_character_, date = NA_character_,
      stop("Unknown source schema type"))
    values <- lapply(rows, function(row) {
      if (!is.list(row) || !setequal(names(row), names(schema))) stop("Source record shape mismatch")
      value <- row[[column]]
      if (is.null(value)) return(missing)
      if (length(value) != 1L || !is.null(dim(value)) || is.object(value) || anyNA(value)) stop("Invalid scalar source value: ", column)
      if (kind %in% c("character", "timestamp", "date") && !is.character(value)) stop("Source string type mismatch: ", column)
      if (kind == "logical" && !is.logical(value)) stop("Source logical type mismatch: ", column)
      if (kind %in% c("integer", "double") && (!is.numeric(value) || !is.finite(value))) stop("Source numeric type mismatch: ", column)
      if (kind == "integer" && (value != trunc(value) || abs(value) > .Machine$integer.max)) stop("Source integer range mismatch: ", column)
      return(switch(kind, integer = as.integer(value), double = as.double(value), value))
    })
    prototype <- switch(kind, double = double(), integer = integer(), logical = logical(), character())
    vector <- if (length(values)) unlist(values, use.names = FALSE) else prototype
    if (kind == "timestamp") {
      if (any(!is.na(vector) & !grepl("(Z|[+-][0-9]{2}:?[0-9]{2})$", vector))) stop("Source timestamp lacks timezone: ", column)
      parsed <- lubridate::ymd_hms(vector, tz = "UTC", quiet = TRUE)
      if (any(is.na(parsed) & !is.na(vector))) stop("Invalid source timestamp: ", column)
      return(parsed)
    }
    if (kind == "date") {
      if (any(!is.na(vector) & !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", vector))) stop("Invalid source date: ", column)
      parsed <- lubridate::ymd(vector, quiet = TRUE)
      if (any(is.na(parsed) & !is.na(vector))) stop("Invalid source date: ", column)
      return(parsed)
    }
    return(vector)
  })
  names(columns) <- names(schema)
  return(tibble::as_tibble(columns))
}

#' Open a reusable NovaAPI client
#' @param cache_path Explicit SQLite file in an existing data directory.
#' @param account Non-secret subscription namespace; use one per subscription.
#' @param backend Explicit python_backend handle selecting the project Python.
#' @param min_interval Request spacing seconds, at least 2.1 (30/minute limit).
#' @return nova_api_client handle. Creates cache schema but does not fetch.
#'   Live attempts require NOVA_API_KEY and NOVA_PRIVATE_KEY environment values;
#'   offline reads need neither. Credentials are not passed in function arguments.
#' @export
OpenNovaAPI <- function(cache_path, account, backend, min_interval = 2.1) {
  checkmate::assert_string(cache_path, min.chars = 1, na.ok = FALSE)
  checkmate::assert_string(account, min.chars = 1, na.ok = FALSE)
  module <- .ExtractionModule(backend, "nova_api")
  client <- module$NovaClient(cache_path, account, min_interval = min_interval)
  return(structure(list(client = client, backend = backend), class = "nova_api_client"))
}

#' Read a documented NovaAPI endpoint with explicit freshness
#' @param client Handle from OpenNovaAPI.
#' @param endpoint Documented endpoint name from Python ENDPOINTS; usage is
#'   excluded because its response echoes credentials.
#' @param params Named list of nonempty strings, never authentication values.
#' @param max_age Maximum live-cache age in seconds; zero refreshes explicitly.
#' @param cache_only TRUE never accesses the network and allows older observations.
#' @param capture_id Optional positive integer selecting immutable offline replay.
#' @return List data (original JSON structure) and receipt. Not a flattened table;
#'   use ExtractNovaOdds or ExtractNovaBeidan for contracted tibbles. Failures and
#'   null data raise errors; valid empty arrays remain empty. Raw bytes are saved.
#' @export
NovaRequest <- function(client, endpoint, params = list(), max_age,
                        cache_only = FALSE, capture_id = NULL) {
  if (!inherits(client, "nova_api_client")) stop("client must be a nova_api_client")
  if (!is.list(params) || (length(params) && (is.null(names(params)) || anyDuplicated(names(params))))) stop("params must be a named list")
  if (!all(vapply(params, function(x) is.character(x) && length(x) == 1L && !is.na(x) && nzchar(x), logical(1)))) stop("params must contain strings")
  if (!is.null(capture_id)) checkmate::assert_integerish(capture_id, lower = 1, upper = .Machine$integer.max, len = 1, any.missing = FALSE)
  dictionary <- reticulate::dict()
  for (name in names(params)) dictionary[[name]] <- params[[name]]
  return(reticulate::py_to_r(client$client$request(endpoint, dictionary,
    max_age = max_age, cache_only = cache_only,
    capture_id = if (is.null(capture_id)) NULL else as.integer(capture_id))))
}

#' Extract tidy NovaAPI institutional odds using one response
#' @param client Handle from OpenNovaAPI.
#' @param params Named string list with exactly one idEvent, matchId or bdMatchId,
#'   optionally providerId/marketId. IDs are in NovaAPI's namespace.
#' @param source_timezone Explicit interpretation of timezone-naive source times.
#' @param max_age Cache freshness seconds, zero explicitly refreshes.
#' @param history TRUE extracts every history point; FALSE latest quotes.
#' @param cache_only TRUE never fetches; old observations are permitted.
#' @param capture_id Optional positive integer raw capture ID for pinned replay.
#' @return List odds tibble and receipt. Key is event/provider/market/option/line/time;
#'   IDs are character, odds observed decimal double >=1, quote_at POSIXct UTC.
#'   quote_status flags unit_price (exactly 1) separately from quoted (>1),
#'   preserving extreme source values without treating them as usable bets. Empty
#'   providers gives typed zero rows; malformed/null values fail. Source is
#'   novaapi with unverified upstream, never relabelled Titan/Nowscore.
#' @export
ExtractNovaOdds <- function(client, params, source_timezone, max_age,
                            history = FALSE, cache_only = FALSE, capture_id = NULL) {
  if (!inherits(client, "nova_api_client")) stop("client must be a nova_api_client")
  if (!is.list(params) || is.null(names(params)) || anyDuplicated(names(params))) stop("params must be a named list")
  if (!is.null(capture_id)) checkmate::assert_integerish(capture_id, lower = 1, upper = .Machine$integer.max, len = 1, any.missing = FALSE)
  dictionary <- reticulate::dict()
  for (name in names(params)) dictionary[[name]] <- params[[name]]
  result <- reticulate::py_to_r(client$client$odds(params = dictionary,
    source_timezone = source_timezone, max_age = max_age, history = history, cache_only = cache_only,
    capture_id = if (is.null(capture_id)) NULL else as.integer(capture_id)))
  result$odds <- .SourceRows(result$data, c(event_id = "character", provider_id = "character",
    market_id = "character", option = "character", line = "character", odds = "double", quote_at = "timestamp", quote_status = "character"))
  result$data <- NULL
  return(result)
}

#' Extract every North Single Match play from one NovaAPI issue response
#' @param client Handle from OpenNovaAPI.
#' @param draw_no Explicit five-character issue ID; no implicit latest issue.
#' @param source_timezone Explicit timezone for source sale cutoff timestamps.
#' @param max_age Cache freshness seconds; zero explicitly refreshes.
#' @param cache_only TRUE permits offline reads only.
#' @param capture_id Optional positive integer raw capture ID for pinned replay.
#' @return List matches and sp tibbles plus receipt. matches has one row per
#'   play/match, sp one row per play/match/sp1..sp25. Nullable handicap/SP remain
#'   NA_real_; SP zero remains zero. settled distinguishes awarded values.
#'   sale_end_at is POSIXct UTC and is never interpreted as kickoff. Raw bytes
#'   retain unknown fields. No probability learning or selection occurs.
#' @export
ExtractNovaBeidan <- function(client, draw_no, source_timezone, max_age, cache_only = FALSE, capture_id = NULL) {
  if (!inherits(client, "nova_api_client")) stop("client must be a nova_api_client")
  if (!is.null(capture_id)) checkmate::assert_integerish(capture_id, lower = 1, upper = .Machine$integer.max, len = 1, any.missing = FALSE)
  result <- reticulate::py_to_r(client$client$beidan(draw_no,
    source_timezone = source_timezone, max_age = max_age, cache_only = cache_only,
    capture_id = if (is.null(capture_id)) NULL else as.integer(capture_id)))
  result$matches <- .SourceRows(result$data$matches, c(issue_id = "character", play_id = "character",
    match_id = "character", home = "character", away = "character", league = "character",
    sale_end_at = "timestamp", settled = "logical", handicap = "double", full_score = "character", half_score = "character"))
  result$sp <- .SourceRows(result$data$sp, c(issue_id = "character", play_id = "character",
    match_id = "character", item = "character", sp = "double", settled = "logical"))
  result$data <- NULL
  return(result)
}

#' Extract an entire Nowscore issue with persistent raw-response reuse
#' @param issue_id Explicit issue identifier with leading zeros preserved.
#' @param cache_path Explicit SQLite path in existing data directory.
#' @param backend Explicit python_backend handle.
#' @param max_age Maximum raw-response age seconds; zero explicitly refreshes.
#' @param cache_only TRUE permits older offline observations, never fetches.
#' @param capture_id Optional positive integer raw capture ID for pinned replay.
#' @param min_interval Network spacing seconds; default 120 follows existing
#'   Nowscore refresh cadence. Shared store retains the largest requested interval.
#' @return List matches tibble and receipt. Native IDs character, slot integer,
#'   nullable handicap double, dates Date, sale_end_at/observed_at POSIXct UTC.
#'   kickoff clock and explicit kickoff script date are separate; no inferred
#'   kickoff instant. Source is nowscore. Parser failures raise, not empty data.
#' @export
ExtractNowscoreIssue <- function(issue_id, cache_path, backend, max_age,
                                cache_only = FALSE, min_interval = 120, capture_id = NULL) {
  if (!is.null(capture_id)) checkmate::assert_integerish(capture_id, lower = 1, upper = .Machine$integer.max, len = 1, any.missing = FALSE)
  module <- .ExtractionModule(backend, "source_extraction")
  result <- reticulate::py_to_r(module$extract_nowscore_issue(issue_id, cache_path,
    max_age = max_age, cache_only = cache_only, min_interval = min_interval,
    capture_id = if (is.null(capture_id)) NULL else as.integer(capture_id)))
  result$matches <- .SourceRows(result$data, c(issue_id = "character", native_id = "character",
    slot = "integer", home = "character", away = "character", league = "character",
    handicap = "double", kickoff_hhmm = "character", kickoff_date = "date", group_date = "date",
    sale_end_at = "timestamp", score = "character", status = "character", can_sale = "logical",
    observed_at = "timestamp", source_url = "character"))
  result$data <- NULL
  return(result)
}

#' Extract Titan Euro and total histories using the existing parser
#' @param fixtures Tibble with fixture_id, provider_id_nowscore, home_nowscore,
#'   away_nowscore and timezone-aware POSIXct kickoff_at.
#' @param cache_path Explicit SQLite path in existing data directory.
#' @param backend Explicit python_backend handle.
#' @param totals_company_ids Character vector of Titan totals company IDs;
#'   empty vector requests Euro only. Titan's company namespace differs from Nova.
#' @param max_age Raw-response freshness seconds; zero refreshes explicitly.
#' @param cache_only TRUE permits older offline captures, never fetches.
#' @param min_interval Network spacing seconds; default 60 follows existing cadence.
#' @return List euro, totals, companies and diagnostics tibbles, and receipts list.
#'   Euro odds are decimal; total Hong Kong prices become decimal (+1). Quote
#'   time and observed receipt time remain separate. Empty fixtures returns typed
#'   empty tables without network. Native identity mismatches fail closed.
#' @export
ExtractTitanMarkets <- function(fixtures, cache_path, backend, totals_company_ids,
                                max_age, cache_only = FALSE, min_interval = 60) {
  if (!tibble::is_tibble(fixtures)) stop("fixtures must be a tibble")
  required <- c("fixture_id", "provider_id_nowscore", "home_nowscore", "away_nowscore", "kickoff_at")
  if (!all(required %in% names(fixtures)) || !inherits(fixtures$kickoff_at, "POSIXct") || anyNA(fixtures$kickoff_at)) stop("Missing fixture identity or typed kickoff")
  checkmate::assert_character(totals_company_ids, any.missing = FALSE, unique = TRUE)
  module <- .ExtractionModule(backend, "source_extraction")
  rows <- lapply(seq_len(nrow(fixtures)), function(i) list(
    fixture_id = fixtures$fixture_id[[i]], provider_id_nowscore = fixtures$provider_id_nowscore[[i]],
    home_nowscore = fixtures$home_nowscore[[i]], away_nowscore = fixtures$away_nowscore[[i]],
    kickoff_at = format(fixtures$kickoff_at[[i]], "%Y-%m-%dT%H:%M:%OS6%z", tz = "UTC")))
  result <- reticulate::py_to_r(module$extract_titan_markets(rows, cache_path,
    as.list(totals_company_ids), max_age = max_age, cache_only = cache_only, min_interval = min_interval))
  result$euro <- .SourceRows(result$euro, c(fixture_id = "character", company_id = "character",
    quote_at = "timestamp", odds_home = "double", odds_draw = "double", odds_away = "double", source_url = "character"))
  result$totals <- .SourceRows(result$totals, c(fixture_id = "character", company_id = "character",
    quote_at = "timestamp", line = "double", over_decimal = "double", under_decimal = "double", source_url = "character"))
  result$companies <- .SourceRows(result$companies, c(market = "character", company_id = "character", company_name = "character"))
  result$diagnostics <- .SourceRows(result$diagnostics, c(fixture_id = "character", market = "character",
    company_id = "character", reason = "character", count = "integer"))
  return(result)
}
