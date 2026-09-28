#' Replay fixed-group structural alternatives from an explicit frozen snapshot
#' @param source_path Original saved result RDS; probabilities/fixtures stay fixed.
#' @param alternative_path Published alternative RDS, bound to source SHA-256.
#' @param settlement_path Saved settlements and explicit as_of timestamp RDS.
#' @param cutoff Explicit cutoff exactly identical to the original decision.
#' @param patterns Named character structure labels; digits 1..3, seven roles.
#' @param group_budget_cny Whole-unit per-group cap, checked by package API.
#' @return Plans, settled summaries, winning legs, and source hash receipt.
#' No fetching/fitting/writes. Missing prematch SP remains unavailable; no EV gate.
recent_frozen_backtest <- function(source_path, alternative_path, settlement_path,
                                  cutoff, patterns = c("3333222", "3332222", "3322221", "3222221"),
                                  group_budget_cny = 256) {
  paths <- c(source = source_path, alternative = alternative_path, settlement = settlement_path)
  purrr::walk(paths, ~checkmate::assert_file_exists(.x))
  checkmate::assert_character(patterns, min.len = 1L, any.missing = FALSE, unique = TRUE,
                              pattern = "^[123]{7}$")
  source <- readRDS(source_path)
  alternative <- readRDS(alternative_path)
  settlement <- readRDS(settlement_path)
  beidan:::match_require_cutoff(cutoff)
  if (!identical(source$result$cutoff, cutoff) || !identical(alternative$result$cutoff, cutoff)) {
    stop("cutoff must equal both frozen decisions")
  }
  hashes <- purrr::map_chr(paths, ~digest::digest(file = .x, algo = "sha256"))
  if (!identical(alternative$source_sha256, unname(hashes[["source"]]))) stop("alternative source hash mismatch")
  checkmate::assert_posixct(source$market_captures$observed_at, min.len = 1L, any.missing = FALSE)
  if (any(source$market_captures$observed_at >= cutoff$cutoff_utc)) stop("post-cutoff market capture")
  if (!inherits(settlement$as_of, "POSIXct") || settlement$as_of <= cutoff$cutoff_utc) stop("invalid settlement as_of")
  plans <- list(published_3222221 = source$result, published_3333222 = alternative$result)
  for (pattern in patterns) {
    plans[[paste0("fixed_", pattern)]] <- beidan::parlay_restructure_plan(source$result, cutoff,
      as.integer(strsplit(pattern, "", fixed = TRUE)[[1]]), group_budget_cny)
  }
  settled <- purrr::map(plans, ~beidan::parlay_settle_plan(.x$plan, settlement$settlements, settlement$as_of))
  summary <- purrr::imap_dfr(settled, ~dplyr::mutate(.x$issue_returns, scenario = .y, .before = 1))
  groups <- purrr::imap_dfr(settled, ~dplyr::mutate(.x$group_returns, scenario = .y, .before = 1))
  winning <- purrr::imap_dfr(settled, ~dplyr::mutate(dplyr::filter(.x$ticket_returns, status == "WON"), scenario = .y, .before = 1))
  winning_legs <- purrr::imap_dfr(plans, function(plan, scenario) {
    ids <- dplyr::filter(winning, .data$scenario == .env$scenario)$ticket_id
    dplyr::filter(plan$plan$ticket_legs, ticket_id %in% ids) |>
      dplyr::left_join(dplyr::select(settlement$settlements, fixture_id, actual_outcome = outcome, settled_sp),
                       by = "fixture_id", relationship = "many-to-one") |>
      dplyr::mutate(scenario = scenario, .before = 1)
  })
  eligibility <- tibble::tibble(signal = c("frozen_probabilities", "prematch_sp", "settlements"),
    decision_eligible = c(TRUE, FALSE, FALSE), reason = c("original frozen model probabilities; no refit",
      "original frozen source has no prematch SP; later captures cannot price this decision",
      "outcome-only evaluation after cutoff; never used for construction"))
  list(plans = plans, settled = settled, summary = summary, group_returns = groups,
       winning_tickets = winning, winning_legs = winning_legs, source_eligibility = eligibility,
       receipt = list(cutoff = cutoff, as_of = settlement$as_of, source_hashes = hashes,
                      patterns = patterns, group_budget_cny = group_budget_cny,
                      maximum_source_observed_at = max(source$market_captures$observed_at),
                      market_capture_hash = rlang::hash(source$market_captures),
                      probability_hash = rlang::hash(source$result$probabilities),
                      implementation_hash = rlang::hash(body(recent_frozen_backtest))))
}
