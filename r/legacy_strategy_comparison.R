# Descriptive comparison of already frozen, settled strategies. One row per
# issue/policy; explicit common issue chronology and stage order. Amounts CNY.
# Requires strategy_equity_curves and n7_purchase_accounting to be sourced.
# No fitting, policy selection, implicit missing-period imputation or I/O.
# Returns funding-aware accounting, paired correlations/unique hits and
# policy-specific removal of the largest 1/3/5 profits (descriptive only).
legacy_strategy_comparison <- function(periods, issue_order, stage_order,
                                      baseline_policy, initial_capital_cny) {
  accounting <- n7_purchase_accounting(periods, issue_order, stage_order,
                                       baseline_policy, initial_capital_cny)
  z <- accounting$curves |> dplyr::filter(period > 0)
  b <- z |> dplyr::filter(policy == baseline_policy) |>
    dplyr::select(evaluation, accounting_basis, issue, base_net = net, base_gross = gross)
  pairs <- z |> dplyr::left_join(b, by = c('evaluation', 'accounting_basis', 'issue'),
                                relationship = 'many-to-one') |>
    dplyr::group_by(evaluation, accounting_basis, policy) |>
    dplyr::summarise(issues = dplyr::n(),
      correlation = if(dplyr::n() > 1 && sd(net) > 0 && sd(base_net) > 0)
        cor(net, base_net) else NA_real_,
      both_hit = sum(gross > 0 & base_gross > 0),
      unique_hit = sum(gross > 0 & base_gross == 0),
      baseline_only_hit = sum(gross == 0 & base_gross > 0),
      neither_hit = sum(gross == 0 & base_gross == 0),
      unique_profit = sum(net > 0 & base_net <= 0), .groups = 'drop')
  trimmed <- list()
  for(k in c(1L, 3L, 5L)) {
    # Remove each policy's own largest net results, including their stake.
    trimmed[[as.character(k)]] <- z |>
      dplyr::group_by(evaluation, accounting_basis, policy) |>
      dplyr::arrange(dplyr::desc(net), period, .by_group = TRUE) |>
      dplyr::filter(dplyr::row_number() > k) |>
      dplyr::summarise(remaining_issues = dplyr::n(), stake_cny = sum(stake),
        net_cny = sum(net), roi_percent = if(stake_cny > 0)100 * net_cny / stake_cny else NA_real_,
        .groups = 'drop') |> dplyr::mutate(removed = k)
  }
  c(accounting, list(complementarity = pairs, trimmed = dplyr::bind_rows(trimmed)))
}
