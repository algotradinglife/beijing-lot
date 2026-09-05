# Diagnostic historical snapshots. Python owns slicing and source-binding receipts.
# Callers source r/python_bridge.R and provide the interpreter and project root.
snapshot_long <- function(data_root, project_root, python, fixture_ids = NULL, limit = NULL) {
  module <- project_python_module("src.titan_clean.snapshots", project_root, python)
  sets <- module$derive_batch_snapshots(data_root,
    fixture_ids = if (is.null(fixture_ids)) NULL else as.list(fixture_ids),
    limit = if (is.null(limit)) NULL else as.integer(limit))
  prototype <- tibble::tibble(fixture_id = character(), kind = character(), quote_key = character(),
    home_odds = double(), draw_odds = double(), away_odds = double(),
    market_time = as.POSIXct(character(), tz = "UTC"), market_time_source_raw = character())
  rows <- lapply(sets, function(s) {
    dplyr::bind_rows(lapply(s$rows, function(row) {
      tibble::tibble(fixture_id = s$fixture_id, kind = row$kind, quote_key = row$quote_key,
        home_odds = if (is.null(row$home_odds)) NA_real_ else row$home_odds,
        draw_odds = if (is.null(row$draw_odds)) NA_real_ else row$draw_odds,
        away_odds = if (is.null(row$away_odds)) NA_real_ else row$away_odds,
        market_time = if (is.null(row$market_time)) as.POSIXct(NA_real_, origin = "1970-01-01", tz = "UTC")
                      else lubridate::with_tz(lubridate::force_tz(row$market_time, "Asia/Shanghai"), "UTC"),
        market_time_source_raw = if (is.null(row$market_time_source_raw)) NA_character_ else row$market_time_source_raw)
    }))
  })
  table <- dplyr::bind_rows(c(list(prototype), rows))
  if (anyDuplicated(table[c("fixture_id", "kind", "quote_key")])) stop("duplicate snapshot key")
  attr(table, "receipts") <- lapply(sets, function(s) s$receipt())
  table
}

snapshot_wide <- function(data_root, project_root, python, fixture_ids = NULL, limit = NULL) {
  table <- snapshot_long(data_root, project_root, python, fixture_ids, limit)
  result <- tidyr::pivot_wider(table, id_cols = c(fixture_id, quote_key), names_from = kind,
    values_from = c(home_odds, draw_odds, away_odds, market_time))
  attr(result, "receipts") <- attr(table, "receipts")
  result
}
