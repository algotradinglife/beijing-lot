#' Select the complete schedule window for market capture
#'
#' @param schedule Schedule tibble with unique character fixture_key, positive
#'   integer slot and POSIXct kickoff_at. Unknown kickoff times are reported as
#'   exclusions. All other schedule columns are preserved.
#' @param reference_at One finite POSIXct capture-planning instant. This is not
#'   a frozen decision cutoff: prepare_match_inputs() selects again after capture.
#' @param window_hours Optional length-2 numeric elapsed-hour bounds
#'   `c(start, end)`, defaulting to the contract's `c(4, 28)`. Forwarded to
#'   match_decision_window(), so `c(2, 26)` selects earlier half-open bounds
#'   without moving the reference instant. Invalid bounds raise an error.
#' @return List(schedule, excluded, window). schedule preserves the input schema,
#'   ordered by kickoff and slot. excluded is a tibble(fixture_id, slot, reason).
#'   window contains the resolved window_hours and the shared start_utc/end_utc
#'   bounds. Empty inputs retain types.
#' @details Uses the same half-open
#'   `[reference + window_hours[1], reference + window_hours[2])` window as
#'   decision preparation. No slot ceiling, network requests, status inference or
#'   hidden clock reads. Invalid identifiers/types raise an error.
#' @export
match_market_schedule <- function(schedule, reference_at,
                                  window_hours = c(MATCH_WINDOW_START_HOURS,
                                                   MATCH_WINDOW_END_HOURS)) {
  if (!tibble::is_tibble(schedule)) stop("schedule must be a tibble")
  required <- c("fixture_key", "slot", "kickoff_at")
  if (!all(required %in% names(schedule))) stop("schedule lacks fixture_key, slot or kickoff_at")
  checkmate::assert_character(schedule$fixture_key, any.missing = FALSE,
                             min.chars = 1L, unique = TRUE)
  checkmate::assert_integer(schedule$slot, any.missing = FALSE, lower = 1L)
  if (!inherits(schedule$kickoff_at, "POSIXct")) stop("kickoff_at must be POSIXct")
  if (any(!is.na(schedule$kickoff_at) & !is.finite(as.numeric(schedule$kickoff_at)))) {
    stop("kickoff_at must be finite or missing")
  }
  if (!inherits(reference_at, "POSIXct")) stop("reference_at must be POSIXct")
  window <- match_decision_window(reference_at, window_hours = window_hours)
  known <- !is.na(schedule$kickoff_at)
  inside <- known & schedule$kickoff_at >= window$start_utc &
    schedule$kickoff_at < window$end_utc
  selected <- schedule[inside, , drop = FALSE] |>
    dplyr::arrange(kickoff_at, slot, fixture_key)
  excluded <- tibble::tibble(fixture_id = schedule$fixture_key[!inside],
    slot = schedule$slot[!inside],
    reason = dplyr::if_else(known[!inside], "kickoff outside capture window", "unknown kickoff")) |>
    dplyr::arrange(slot, fixture_id)
  list(schedule = selected, excluded = excluded, window = window)
}
