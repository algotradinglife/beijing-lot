#' Capture observed Beijing Single Match pre-match reference SP
#' @param schedule Nonempty tibble of one issue, with issue_id, slot, fixture_key,
#'   provider_id_nowscore, integer handicap and POSIXct kickoff_at. Unique slots.
#' @param raw_dir Explicit nonempty raw-response directory. Each call creates a
#'   separate receipt and preserves original bytes before parsing.
#' @param backend Explicit python_backend() handle using the project interpreter.
#' @param timeout Positive finite timeout in seconds, default25.
#' @param retries Nonnegative integer extra transient retries, default2.
#' @param pages NULL for live fetch; or list(body=raw, observed_at=timezone-aware
#'   ISO timestamp) for offline replay. Replay must retain actual observation time.
#' @return Validated prematch_sp tibble: fixture_id, outcome(W/D/L), quote_at
#'   (Beijing POSIXct observation time), sp_raw(double), source_url. Empty results
#'   retain types. Attributes diagnostics and receipt_path explain exclusions.
#' @details Uses only the labelled Beijing handicap W/D/L SP cells. No European
#'   odds, payout predictions or settlement SP are substituted. Incomplete vectors,
#'   closed/in-play/finished fixtures, mismatched identity/handicap and kickoff at
#'   or before observation are excluded with reasons. Parser failures error.
#'   These are floating reference SP, not locked payout odds. Values above10 remain
#'   unchanged here; apply the existing valuation transform downstream. Current
#'   captures cannot serve an earlier decision cutoff. No network on import.
#' @export
fetch_issue_prematch_sp <- function(schedule, raw_dir, backend, timeout = 25,
                                    retries = 2L, pages = NULL) {
  if (!tibble::is_tibble(schedule)) stop("schedule must be a tibble")
  required <- c("issue_id", "slot", "fixture_key", "provider_id_nowscore", "handicap", "kickoff_at")
  checkmate::assert_subset(required, names(schedule))
  if (!nrow(schedule)) stop("schedule must contain at least one fixture")
  for (column in c("issue_id", "fixture_key", "provider_id_nowscore")) {
    checkmate::assert_character(schedule[[column]], any.missing = FALSE, min.chars = 1)
  }
  checkmate::assert_integerish(schedule$slot, lower = 1, any.missing = FALSE)
  checkmate::assert_numeric(schedule$handicap, any.missing = FALSE, finite = TRUE)
  checkmate::assert_posixct(schedule$kickoff_at, any.missing=FALSE)
  checkmate::assert_string(raw_dir, min.chars = 1, na.ok = FALSE)
  checkmate::assert_number(timeout, lower = .Machine$double.eps, finite = TRUE)
  checkmate::assert_count(retries)
  if (!inherits(backend, "python_backend")) stop("backend must be a python_backend")
  if (!is.null(pages)) {
    checkmate::assert_names(names(pages), permutation.of = c("body", "observed_at"))
    if (!is.raw(pages$body)) stop("pages$body must be raw")
    checkmate::assert_string(pages$observed_at, min.chars = 1, na.ok = FALSE)
  }
  module <- reticulate::import_from_path("beidan_backend.prematch_sp", path = backend$root,
                                          convert = FALSE)
  actual <- reticulate::py_to_r(module$`__file__`)
  expected <- file.path(backend$root, "beidan_backend", "prematch_sp.py")
  if (!identical(normalizePath(actual), normalizePath(expected))) {
    stop("prematch SP backend loaded from another location")
  }
  rows <- lapply(seq_len(nrow(schedule)), function(i) {
    row <- as.list(schedule[i, required]); row$slot <- as.integer(row$slot)
    row$kickoff_at <- format(lubridate::with_tz(schedule$kickoff_at[i], "UTC"), "%Y-%m-%dT%H:%M:%SZ")
    row
  })
  result <- module$fetch_issue_prematch_sp(rows, raw_dir, timeout = timeout,
    retries = as.integer(retries), pages = if (is.null(pages)) NULL else issue_schedule_pages_dict(pages))
  payload <- reticulate::py_to_r(result)
  out <- match_typed_empty("prematch_sp")
  out$quote_at <- lubridate::with_tz(out$quote_at, "Asia/Shanghai")
  if (length(payload$prematch_sp)) {
    out <- dplyr::bind_rows(payload$prematch_sp)
    out$sp_raw <- as.double(out$sp_raw)
    out$quote_at <- lubridate::with_tz(
      lubridate::ymd_hms(out$quote_at, quiet = TRUE), "Asia/Shanghai")
    if (anyNA(out$quote_at)) stop("invalid observed timestamp")
  }
  attr(out, "diagnostics") <- if (length(payload$diagnostics)) dplyr::bind_rows(payload$diagnostics) else
    tibble::tibble(issue_id = character(), fixture_id = character(), reason = character())
  attr(out, "receipt_path") <- payload$receipt_path
  match_validate_table(out, "prematch_sp", keys=c("fixture_id","outcome","quote_at"))
  return(out)
}
