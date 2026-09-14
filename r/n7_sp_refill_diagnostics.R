# Post-settlement descriptive comparison; does not learn or choose policies.
# rows: one issue/arm/seed with variant, rule and CNY accounting columns.
# issue_order: complete chronological IDs; initial_capital_cny: positive CNY.
# Returns shared equity summaries/curves, 50-issue blocks and loss streaks.
# Zero-profit/cash periods break a consecutive losing-issue streak. No IO.
n7_sp_refill_diagnostics <- function(rows,issue_order,initial_capital_cny) {
  stopifnot(all(c('variant','mode','objective','allocation_order','budget_cny') %in% names(rows)),
    !anyNA(rows[c('variant','mode','objective','allocation_order','budget_cny')]))
  z<-n7_sweet_union_summary(rows,issue_order,initial_capital_cny)
  metadata<-dplyr::distinct(rows,arm,variant,mode,objective,allocation_order,budget_cny)
  stopifnot(!anyDuplicated(metadata$arm),!any(z$curves$stopped))
  ordered<-rows[order(match(rows$issue,issue_order)),]
  streaks<-ordered |> dplyr::group_by(arm,seed) |>
    dplyr::summarise(longest_loss_streak={
      runs<-rle(net<0);max(c(0L,runs$lengths[runs$values]))
    },.groups='drop')
  z$summary<-z$summary |> dplyr::left_join(streaks,by=c('arm','seed'),relationship='one-to-one') |>
    dplyr::left_join(metadata,by='arm',relationship='many-to-one')
  z$curves<-z$curves |> dplyr::select(-dplyr::any_of(setdiff(names(metadata),'arm'))) |>
    dplyr::left_join(metadata,by='arm',relationship='many-to-one')
  z$blocks<-n7_selection_blocks(rows,issue_order,50) |>
    dplyr::left_join(metadata,by='arm',relationship='many-to-one')
  keys<-c('seed','mode','objective','allocation_order','budget_cny')
  control<-z$summary |> dplyr::filter(variant=='FILTER_ONLY') |>
    dplyr::select(dplyr::all_of(keys),filter_net=net,filter_stake=stake,filter_roi=roi,
      filter_drawdown=max_drawdown,filter_hits=hit_issues)
  z$paired<-z$summary |> dplyr::left_join(control,by=keys,relationship='many-to-one') |>
    dplyr::mutate(delta_net=net-filter_net,delta_stake=stake-filter_stake,
      delta_roi=roi-filter_roi,delta_drawdown=max_drawdown-filter_drawdown,
      delta_hit_issues=hit_issues-filter_hits)
  control_rows<-rows |> dplyr::filter(variant=='FILTER_ONLY') |>
    dplyr::select(issue,dplyr::all_of(keys),filter_net=net,filter_stake=stake,filter_gross=gross,filter_hits=hits)
  z$per_issue<-rows |> dplyr::left_join(control_rows,by=c('issue',keys),relationship='many-to-one') |>
    dplyr::mutate(delta_net=net-filter_net,delta_stake=stake-filter_stake,
      delta_gross=gross-filter_gross,delta_hits=hits-filter_hits)
  stopifnot(!anyNA(z$paired$filter_net),!anyNA(z$per_issue$filter_net))
  z
}
