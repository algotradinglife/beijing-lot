# results: decoded study JSON with rows (issue-policy CNY settlement) and legs
# (fixture-policy decisions, including skipped fixtures). No I/O or tuning.
# Returns partition-policy totals, per-issue ROI/equity/drawdown and conflict
# diagnostics. Unspent cash earns zero; no score protection or reinvestment.
# Sources r/fundamentals_integration_weight.R must be loaded by the caller.
decision_chain_tables <- function(results) {
  x <- tibble::as_tibble(results$rows)
  legs <- tibble::as_tibble(results$legs)
  stopifnot(all(c('selected_matches','conflict_candidates','skipped_candidates',
    'removed_current_matches','added_matches','unspent_vs_current_cny') %in% names(x)),
    all(c('partition','policy','issue','slot','provider_id','conflict','selected',
      'current_hit','routed_hit','selected_hit') %in% names(legs)),
    !anyDuplicated(legs[c('policy','issue','slot')]),
    all(x$selected_matches==7*x$groups),all(x$unspent_vs_current_cny>=0))
  totals <- integration_weight_summary(x)
  diagnostics <- x |> dplyr::group_by(partition,policy) |>
    dplyr::summarise(candidates=sum(candidates),conflict_candidates=sum(conflict_candidates),
      skipped_candidates=sum(skipped_candidates),selected_matches=sum(selected_matches),
      removed_current_matches=sum(removed_current_matches),added_matches=sum(added_matches),
      unspent_vs_current_cny=sum(unspent_vs_current_cny),.groups='drop')
  totals <- dplyr::left_join(totals,diagnostics,by=c('partition','policy'),relationship='one-to-one')
  current <- totals |> dplyr::filter(policy=='CURRENT') |>
    dplyr::select(partition,current_net_cny=net_cny,current_stake_cny=stake_cny)
  totals <- dplyr::left_join(totals,current,by='partition',relationship='many-to-one') |>
    dplyr::mutate(net_lift_cny=net_cny-current_net_cny,
      return_on_current_budget=net_cny/current_stake_cny)
  periods <- x |> dplyr::arrange(partition,policy,issue) |>
    dplyr::group_by(partition,policy) |>
    dplyr::mutate(ROI_percent=dplyr::if_else(stake>0,100*net/stake,NA_real_),
      cumulative_net_cny=cumsum(net),drawdown_cny=cummax(pmax(0,cumulative_net_cny))-cumulative_net_cny) |>
    dplyr::ungroup()
  accuracy <- legs |> dplyr::group_by(partition,policy,conflict) |>
    dplyr::summarise(fixtures=dplyr::n(),current_hits=sum(current_hit),
      routed_fixtures=sum(!is.na(routed_hit)),routed_hits=sum(routed_hit,na.rm=TRUE),
      selected_fixtures=sum(selected),selected_hits=sum(selected_hit,na.rm=TRUE),.groups='drop') |>
    dplyr::mutate(current_hit_rate=current_hits/fixtures,
      routed_hit_rate=dplyr::if_else(routed_fixtures>0,routed_hits/routed_fixtures,NA_real_),
      selected_hit_rate=dplyr::if_else(selected_fixtures>0,selected_hits/selected_fixtures,NA_real_))
  list(summary=totals,periods=periods,accuracy=accuracy)
}
