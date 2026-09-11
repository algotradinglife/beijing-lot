# Read immutable #422 JSON/CSV output as tibbles; no fitting, scraping or writes.
# run_dir: existing explicit directory. Errors on changed bytes/missing tables.
read_conditional_score_report <- function(run_dir) {
  stopifnot(is.character(run_dir), length(run_dir) == 1L, dir.exists(run_dir))
  receipt <- jsonlite::read_json(file.path(run_dir, "receipt.json"), simplifyVector = FALSE)
  if (!identical(receipt$historical_admission, FALSE)) stop("Retrospective receipt required")
  for (name in names(receipt$files)) {
    if (basename(name) != name || name %in% c(".", "..")) stop("Unsafe artifact path")
    path <- file.path(run_dir, name)
    if (!file.exists(path) ||
        !identical(digest::digest(file = path, algo = "sha256"), receipt$files[[name]])) {
      stop("Changed report artifact: ", name)
    }
  }
  tables <- c("observations", "returns", "training", "exclusions", "summary")
  if (!all(paste0(tables, ".csv") %in% names(receipt$files))) stop("Missing bound tables")
  result <- lapply(tables, function(name) {
    spec <- readr::cols()
    if (name != "summary") spec$cols$issue <- readr::col_character()
    if (name == "observations") spec$cols$provider_id <- readr::col_character()
    readr::read_csv(file.path(run_dir, paste0(name, ".csv")), show_col_types = FALSE,
                   col_types = spec)
  })
  names(result) <- tables
  result$receipt <- receipt
  result
}

# Aggregate probability and cash results, never learn thresholds or select bets.
# Input observations: one row per fixture/method; returns: issue/method/selection.
# ROI is sum(net)/sum(stake), not an average of issue percentages. No side effects.
summarise_conditional_score <- function(observations, returns) {
  if (anyDuplicated(observations[c("issue", "slot", "method")]) ||
      anyDuplicated(returns[c("issue", "method", "selection")])) stop("Duplicate report units")
  probability <- observations |>
    dplyr::group_by(method, conflict) |>
    dplyr::summarise(fixtures = dplyr::n(), issues = dplyr::n_distinct(issue),
      score_logloss = mean(score_logloss), wdl_logloss = mean(wdl_logloss),
      score_brier = mean(score_brier), wdl_brier = mean(wdl_brier),
      top1_percent = 100 * mean(top1), top2_percent = 100 * mean(top2),
      draw_bias_pp = 100 * mean(p_D - draw_actual),
      large_bias_pp = 100 * mean(large_probability - large_actual),
      btts_bias_pp = 100 * mean(btts_probability - btts_actual),
      conditional_total_error = mean(conditional_total_error, na.rm = TRUE),
      conditional_total_logloss = mean(conditional_total_logloss),
      conditional_total_brier = mean(conditional_total_brier, na.rm = TRUE),
      large_brier = mean((large_probability - large_actual)^2),
      btts_brier = mean((btts_probability - btts_actual)^2),
      .groups = "drop")
  money <- returns |>
    dplyr::group_by(method, selection) |>
    dplyr::summarise(issues = dplyr::n(), stake_cny = sum(stake),
      gross_cny = sum(gross), net_cny = sum(net),
      roi_percent = ifelse(stake_cny > 0, 100 * net_cny / stake_cny, NA_real_),
      maximum_drawdown_cny = max(drawdown_cny), .groups = "drop")
  margins <- observations |>
    dplyr::group_by(method, actual_margin) |>
    dplyr::summarise(fixtures = dplyr::n(),
      total_bias_goals = mean(conditional_total_error, na.rm = TRUE),
      conditional_logloss = mean(conditional_total_logloss),
      conditional_brier = mean(conditional_total_brier, na.rm = TRUE), .groups = "drop")
  list(probability = probability, money = money, margins = margins)
}
