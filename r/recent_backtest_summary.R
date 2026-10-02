#' Attribute eliminated stake from independently validated ranked purchases
#' @param prepared Canonical result of beidan's authoritative risk preparation.
#' @return Tibble of fixture/outcome knockout and surviving actual stake, CNY.
#' Empty purchases return a typed empty table. No labels or IO are used.
RecentSummaryExposure <- function(prepared) {
  if (!nrow(prepared$purchases)) return(beidan:::.ParlayLossExposureEmpty())
  total <- sum(prepared$purchases$stake_cny)
  grid <- prepared$probabilities |> dplyr::select(fixture_id, outcome)
  purchased_legs <- prepared$legs |>
    dplyr::inner_join(prepared$purchases |> dplyr::select(ticket_id, stake_cny),
      by = "ticket_id", relationship = "many-to-one") |>
    dplyr::rename(selected_outcome = outcome)
  eliminated <- grid |>
    dplyr::left_join(purchased_legs, by = "fixture_id", relationship = "many-to-many") |>
    dplyr::group_by(fixture_id, outcome) |>
    dplyr::summarise(knockout_cny = sum(stake_cny[!is.na(selected_outcome) &
      selected_outcome != outcome], na.rm = TRUE), .groups = "drop")
  eliminated |> dplyr::mutate(plan_stake_cny = total,
    knockout_fraction = knockout_cny / total, surviving_cny = total - knockout_cny) |>
    dplyr::select(fixture_id, outcome, plan_stake_cny, knockout_cny,
      knockout_fraction, surviving_cny)
}

#' Summarise frozen research alternatives without feeding labels into selection
#' @param experiment Named results, metadata tibble with scenario_id, bound cutoff.
#' @param settlements Valid settlement tibble; labels are used for evaluation only.
#' @param as_of Explicit settlement visibility POSIXct timestamp after decision.
#' @return Scenario and group tibbles, ticket returns, exposures and source receipt.
#' Monetary values are CNY. Pending/special tickets force final_net_cny to NA.
#' Group q sums unique physical ticket probabilities (not multiplied by stake).
#' Conditional gross = expected gross/q, and required break-even gross = cost/q.
#' These model quantities assume normal W/D/L; actual ALL settlement can pay
#' several tickets and is evaluated separately by the authoritative settlement API.
RecentBacktestSummary <- function(experiment, settlements, as_of) {
  checkmate::assert_list(experiment$results, names = "unique", min.len = 1L)
  checkmate::assert_tibble(experiment$metadata)
  checkmate::assert_character(experiment$metadata$scenario_id, any.missing = FALSE, unique = TRUE)
  if (!setequal(names(experiment$results), experiment$metadata$scenario_id)) stop("scenario metadata mismatch")
  beidan:::match_require_cutoff(experiment$cutoff)
  checkmate::assert_posixct(as_of, len = 1L, any.missing = FALSE)
  if (as_of <= experiment$cutoff$cutoff_utc) stop("as_of must follow decision cutoff")
  groups <- list(); summaries <- list(); ticket_returns <- list(); exposures <- list()
  for (id in experiment$metadata$scenario_id) {
    evaluation <- experiment$results[[id]]
    prepared <- beidan:::.ParlayRiskPrepare(evaluation, experiment$cutoff)
    actual <- beidan::parlay_settle_plan(evaluation$plan, settlements, as_of)
    exposure <- RecentSummaryExposure(prepared)
    values <- prepared$tickets |>
      dplyr::select(ticket_id, probability, payout_cny) |>
      dplyr::left_join(prepared$purchases |> dplyr::select(ticket_id, group_id, stake_cny),
        by = "ticket_id", relationship = "one-to-one")
    model <- values |> dplyr::group_by(group_id) |>
      dplyr::summarise(cost_cny = sum(stake_cny), q = sum(probability),
        expected_gross_cny = sum(probability * payout_cny), .groups = "drop") |>
      dplyr::mutate(expected_net_cny = expected_gross_cny - cost_cny,
        conditional_gross_cny = dplyr::if_else(q > 0, expected_gross_cny / q, NA_real_),
        required_break_even_gross_cny = dplyr::if_else(q > 0, cost_cny / q, NA_real_))
    groups[[id]] <- model |> dplyr::left_join(actual$group_returns, by = "group_id", relationship = "one-to-one") |>
      dplyr::mutate(final_net_cny = dplyr::if_else(n_pending + n_special == 0L, net_cny, NA_real_), scenario_id = id, .before = 1)
    tickets <- actual$ticket_returns
    cost <- sum(prepared$purchases$stake_cny)
    pending <- sum(tickets$stake_cny[tickets$status == "PENDING"])
    unresolved <- any(!tickets$status %in% c("WON", "LOST"))
    gross <- sum(tickets$payout_cny, na.rm = TRUE)
    summaries[[id]] <- tibble::tibble(scenario_id = id, actual_cost_cny = cost,
      known_payout_cny = gross, pending_stake_cny = pending,
      final_net_cny = if (unresolved) NA_real_ else gross - cost,
      n_winning_tickets = sum(tickets$status == "WON"),
      expected_gross_cny = sum(model$expected_gross_cny), expected_net_cny = sum(model$expected_net_cny),
      max_knockout_fraction = if (nrow(exposure)) max(exposure$knockout_fraction) else 0)
    ticket_returns[[id]] <- dplyr::mutate(tickets, scenario_id = id, .before = 1)
    exposures[[id]] <- dplyr::mutate(exposure, scenario_id = id, .before = 1)
  }
  list(summary = dplyr::left_join(experiment$metadata, dplyr::bind_rows(summaries), by = "scenario_id", relationship = "one-to-one"),
    groups = dplyr::bind_rows(groups), ticket_returns = dplyr::bind_rows(ticket_returns),
    exposures = dplyr::bind_rows(exposures), receipt = list(cutoff = experiment$cutoff, as_of = as_of,
      experiment_hash = rlang::hash(experiment), settlement_hash = rlang::hash(settlements),
      implementation_hash = rlang::hash(list(body(RecentBacktestSummary), body(RecentSummaryExposure))), settlement_used_for_selection = FALSE))
}
