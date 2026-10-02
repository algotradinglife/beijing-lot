#' Capture European, total and Beijing pre-match SP markets together
#'
#' Captures full pregame quote histories, without averaging or cutoff selection.
#' The Nowscore native fixture ID must match Titan. Name/kickoff differences
#' are warnings in diagnostics and coverage$detail, not rejection conditions.
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
#'   Nonempty replay must also contain the issue's Nowscore SPF page URL.
#' @return List of tibbles euro, totals, companies, diagnostics, coverage, captures,
#'   receipt_path, prematch_sp, prematch_sp_identities and prematch_sp_receipt_path.
#'   prematch_sp_identities binds its fixture/native IDs and handicap to the schedule.
#'   The SP table is
#'   independently observed Beijing handicap SP, with diagnostics in its attributes.
#'   Public timestamps use Asia/Shanghai. Euro prices are decimal;
#'   total Hong Kong prices are converted to decimal by adding one. No SP is inferred.
#'   Empty schedule returns typed empty tables without requests. Missing data is
#'   never synthesized. Source quote time is distinct from actual observed_at.
#' @export
fetch_match_markets <- function(schedule, raw_dir, backend,
                                totals_company_ids = "8", timeout = 25,
                                retries = 2L, pages = NULL) {
  if (!tibble::is_tibble(schedule)) stop("schedule must be a tibble")
  required <- c("issue_id", "slot", "handicap", "fixture_key", "provider_id_nowscore", "home_nowscore", "away_nowscore", "kickoff_at")
  if (!all(required %in% names(schedule))) stop("schedule lacks required Nowscore identity fields")
  checkmate::assert_string(raw_dir, min.chars = 1, na.ok = FALSE)
  checkmate::assert_character(totals_company_ids, min.len = 1, any.missing = FALSE, unique = TRUE)
  checkmate::assert_number(timeout, lower = .001, finite = TRUE)
  checkmate::assert_integerish(retries, lower = 0, upper = 3, len = 1, any.missing = FALSE)
  if (!inherits(backend, "python_backend")) stop("backend must be a python_backend")
  if (!inherits(schedule$kickoff_at, "POSIXct") || anyNA(schedule$kickoff_at)) stop("schedule kickoff_at must be known timestamps")
  if (nrow(schedule) && (anyNA(schedule$issue_id) || dplyr::n_distinct(schedule$issue_id) != 1L)) {
    stop("schedule must contain exactly one issue")
  }
  sp_pages <- NULL
  if (nrow(schedule) && !is.null(pages)) {
    sp_url <- paste0("https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum=", unique(schedule$issue_id))
    sp_pages <- pages[[sp_url]]
    if (is.null(sp_pages)) stop("offline replay lacks Nowscore prematch SP page: ", sp_url)
  }
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
    diagnostics = tibble::tibble(fixture_id = character(), market = character(), company_id = character(), reason = character(), count = integer()),
    coverage = tibble::tibble(fixture_id = character(), status = character(), detail = character(), euro_rows = integer(), totals_rows = integer()),
    identities = tibble::tibble(fixture_id = character(), provider_id_nowscore = character(), home_nowscore = character(), away_nowscore = character(), kickoff_at = character()),
    captures = tibble::tibble(fixture_id = character(), market = character(), source_url = character(), observed_at = character(), raw_path = character(), sha256 = character())
  )
  for (table in names(templates)) {
    result[[table]] <- if (length(result[[table]])) dplyr::bind_rows(result[[table]]) else templates[[table]]
  }
  result$identities$kickoff_at <- issue_schedule_timestamp(result$identities$kickoff_at, "kickoff_at")
  result$captures$observed_at <- issue_schedule_timestamp(result$captures$observed_at, "observed_at")
  result$companies <- dplyr::distinct(result$companies)
  result$prematch_sp <- if (nrow(schedule)) {
    fetch_issue_prematch_sp(schedule, file.path(raw_dir, "prematch_sp"), backend,
      timeout = timeout, retries = retries, pages = sp_pages)
  } else {
    dplyr::mutate(match_typed_empty("prematch_sp"),
      quote_at = lubridate::with_tz(quote_at, "Asia/Shanghai"))
  }
  result["prematch_sp_receipt_path"] <- list(attr(result$prematch_sp, "receipt_path"))
  result$prematch_sp_identities <- schedule |>
    dplyr::filter(fixture_key %in% result$prematch_sp$fixture_id) |>
    dplyr::transmute(fixture_id = fixture_key, provider_id_nowscore, handicap)
  return(result)
}

#' Connect captured markets and observed schedule to existing match inputs
#'
#' Native IDs bind the capture. Name/kickoff changes warn rather than reject;
#' current schedule values are retained. Titan source differences are recorded
#' in markets$diagnostics and coverage$detail.
#' Does not infer historical scheduled status from a later finished/unknown row.
#' Actual observed_at is used for status availability. Historical market quotes
#' may be inspected independently when the old status ledger is unavailable.
#' @param schedule Schedule tibble used for capture; must contain known kickoff.
#' @param markets List returned by [fetch_match_markets()].
#' @return Validated match input list for [prepare_match_inputs()]. Its existing
#'   internal contract uses UTC instants; display with lubridate::with_tz when needed.
#'   prematch_sp comes from the same capture's independently fetched Beijing SP.
#' @export
match_inputs_from_capture <- function(schedule, markets) {
  if (!tibble::is_tibble(schedule)) stop("schedule must be a tibble")
  checkmate::assert_list(markets)
  if (is.null(markets[["prematch_sp"]])) stop("markets lacks prematch_sp; declare missing historical SP explicitly or refresh capture")
  match_validate_table(markets[["prematch_sp"]], "prematch_sp")
  if (nrow(markets[["prematch_sp"]])) {
    sp_identity <- markets[["prematch_sp_identities"]]
    if (is.null(sp_identity)) stop("markets lacks prematch SP identity")
    checkmate::assert_names(names(sp_identity), must.include =
      c("fixture_id", "provider_id_nowscore", "handicap"))
    sp_index <- match(sp_identity$fixture_id, schedule$fixture_key)
    if (anyNA(sp_index) || anyDuplicated(sp_identity$fixture_id) ||
        anyNA(sp_identity) ||
        !all(sp_identity$provider_id_nowscore == schedule$provider_id_nowscore[sp_index]) ||
        !all(sp_identity$handicap == schedule$handicap[sp_index]) ||
        !all(markets[["prematch_sp"]]$fixture_id %in% sp_identity$fixture_id)) {
      stop("Prematch SP fixture IDs/native identity/handicap do not match schedule")
    }
  }
  if (is.null(markets$identities)) stop("markets lacks captured identity; replay raw capture")
  identity <- markets$identities
  idx <- match(identity$fixture_id, schedule$fixture_key)
  if (anyNA(idx) || anyDuplicated(identity$fixture_id) ||
      !all(identity$provider_id_nowscore == schedule$provider_id_nowscore[idx])) {
    stop("Captured identity differs from current schedule: fixture/native ID mismatch")
  }
  changed <- identity$home_nowscore != schedule$home_nowscore[idx] |
    identity$away_nowscore != schedule$away_nowscore[idx] |
    as.numeric(identity$kickoff_at) != as.numeric(schedule$kickoff_at[idx])
  if (any(changed, na.rm = TRUE)) {
    warning("Captured names/kickoff differ from current schedule for ",
      paste(identity$fixture_id[which(changed)], collapse = ", "),
      "; native IDs match; current schedule values retained", call. = FALSE)
  }
  if (!all(c(markets$euro$fixture_id, markets$totals$fixture_id) %in% identity$fixture_id)) {
    stop("Market fixture IDs do not match captured identity")
  }
  fixtures <- dplyr::transmute(schedule, issue_id, fixture_id = fixture_key, slot,
    provider_id = provider_id_nowscore, kickoff_at, handicap, sale_state,
    source_url = source_url_nowscore)
  status <- dplyr::transmute(schedule, issue_id, fixture_id = fixture_key,
    status = match_status, status_at = observed_at, available_at = observed_at,
    source_url = source_url_nowscore)
  tables <- list(fixtures = fixtures, euro = markets$euro, totals = markets$totals,
                 prematch_sp = markets[["prematch_sp"]], match_status = status)
  if (!all(markets$euro$fixture_id %in% fixtures$fixture_id) ||
      !all(markets$totals$fixture_id %in% fixtures$fixture_id)) stop("Market fixture IDs do not match schedule")
  return(read_match_inputs(list(kind = "frames", tables = tables), unique(schedule$issue_id)))
}
