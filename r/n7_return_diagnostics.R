# Descriptive diagnostics of frozen plans; all monetary columns CNY. Explicit
# chronological issue_order and fixed bin/block sizes; no tuning or fitting.
# rows: complete issue/arm/seed ledger; groups: funded bridges from attribution.
# Reuses authoritative equity accounting; returns summary, curves, fixed blocks,
# coverage calibration (dependent group observations), and signed price tails.
# Requires capital sufficient to fund every plan; stops rather than mixing shadow
# and funded attribution. No IO. Missing chronology, incomplete arms, invalid bins/blocks fail.
n7_return_diagnostics <- function(rows,groups,issue_order,initial_capital_cny,block_size,coverage_breaks) {
  stopifnot(length(block_size)==1,is.finite(block_size),block_size>=1,block_size==floor(block_size),
    length(coverage_breaks)>=2,all(is.finite(coverage_breaks)),all(diff(coverage_breaks)>0),
    coverage_breaks[1]==0,tail(coverage_breaks,1)==1,
    all(c('model_net','outcome_residual','price_residual') %in% names(rows)),
    !anyNA(rows[c('model_net','outcome_residual','price_residual')]),
    all(abs(rows$net-rows$model_net-rows$outcome_residual-rows$price_residual)<1e-7))
  equity<-n7_sweet_union_summary(rows,issue_order,initial_capital_cny)
  stopifnot(!any(equity$curves$stopped))
  blocks<-rows |> dplyr::mutate(period=match(issue,issue_order),block=ceiling(period/block_size)) |>
    dplyr::group_by(arm,seed,block) |> dplyr::summarise(issues=dplyr::n(),stake=sum(stake),
      net=sum(net),roi=ifelse(stake>0,net/stake,NA_real_),model_net=sum(model_net),
      outcome_residual=sum(outcome_residual),price_residual=sum(price_residual),
      hit_issues=sum(hits>0),profit_issues=sum(net>0),.groups='drop')
  stopifnot(all(c('issue','arm','seed','coverage','hit','price_residual','actual_gross') %in% names(groups)),
    all(groups$issue %in% issue_order),!anyNA(groups[c('coverage','hit','price_residual','actual_gross')]),
    all(groups$coverage>=0 & groups$coverage<=1))
  calibration<-groups |> dplyr::mutate(bin=cut(coverage,coverage_breaks,include.lowest=TRUE)) |>
    dplyr::group_by(arm,seed,bin) |> dplyr::summarise(group_observations=dplyr::n(),
      issues=dplyr::n_distinct(issue),model_hit=mean(coverage),actual_hit=mean(hit),.groups='drop')
  tails<-rows |> dplyr::group_by(arm,seed) |>
    dplyr::arrange(dplyr::desc(price_residual),.by_group=TRUE) |>
    dplyr::mutate(price_rank=dplyr::row_number(),cumulative_price_residual=cumsum(price_residual),
      total_price_residual=sum(price_residual)) |> dplyr::ungroup()
  bridge<-rows |> dplyr::group_by(arm,seed) |> dplyr::summarise(stake=sum(stake),
    model_net=sum(model_net),outcome_residual=sum(outcome_residual),
    price_residual=sum(price_residual),net=sum(net),
    estimated_hit_net=model_net+outcome_residual,.groups='drop')
  list(summary=equity$summary,curves=equity$curves,blocks=blocks,
    calibration=calibration,price_tails=tails,bridge=bridge)
}
