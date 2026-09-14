# Descriptive analysis of frozen, settled #453 plans; no tuning or selection.
# rows: issue/arm/seed plus variant, budget, stake/gross/net/hits/groups;
# funded and membership follow n7_selection_overlap's contracts. Explicit
# chronological issue_order and initial capital CNY. Returns summary, equity,
# paired contrasts to JOINT, chronological blocks and overlap diagnostics.
# Missing series/keys or invalid accounting fail through shared contracts.
n7_quality_diagnostics <- function(rows,funded,membership,issue_order,initial_capital_cny) {
  meta<-rows |> dplyr::distinct(arm,variant,budget_cny)
  stopifnot(!anyDuplicated(meta$arm),'JOINT' %in% meta$variant,
    !anyDuplicated(rows[c('issue','variant','budget_cny','seed')]))
  z<-n7_sweet_union_summary(rows,issue_order,initial_capital_cny)
  # All risk and paired diagnostics follow the actual funded ledger, including
  # permanent cash-holding after an unaffordable whole plan.
  active<-z$curves |> dplyr::filter(period>0) |>
    dplyr::select(issue,arm,seed,stopped,funded_stake_cny,funded_net_cny)
  rows<-rows |> dplyr::left_join(active,by=c('issue','arm','seed'),relationship='one-to-one') |>
    dplyr::mutate(stake=funded_stake_cny,net=funded_net_cny,gross=stake+net,cash=budget_cny-stake,
      hits=ifelse(stopped,0,hits),groups=ifelse(stopped,0,groups),eval_union=ifelse(stopped,0,eval_union))
  funded<-funded |> dplyr::semi_join(rows |> dplyr::filter(!stopped),by=c('issue','arm','seed'))
  overlap<-n7_selection_overlap(rows,funded,membership)
  exposure<-funded |> dplyr::left_join(membership,by=c('issue','sleeve_id'),relationship='many-to-many') |>
    dplyr::group_by(issue,arm,seed,fixture_id) |> dplyr::summarise(exposure_cny=sum(stake)/7,.groups='drop') |>
    dplyr::group_by(issue,arm,seed) |> dplyr::summarise(
      max_fixture_capital_share=max(exposure_cny)/sum(exposure_cny),
      fixture_capital_hhi=sum((exposure_cny/sum(exposure_cny))^2),.groups='drop')
  overlap<-overlap |> dplyr::left_join(exposure,by=c('issue','arm','seed'),relationship='one-to-one') |>
    dplyr::mutate(dplyr::across(c(max_fixture_capital_share,fixture_capital_hhi),~tidyr::replace_na(.x,0)))
  risk<-rows |> dplyr::left_join(overlap |> dplyr::select(-eval_union),by=c('issue','arm','seed'),relationship='one-to-one') |>
    dplyr::arrange(match(issue,issue_order)) |>
    dplyr::group_by(arm,seed) |> dplyr::summarise(
      funded_issues=sum(stake>0),zero_hit_issues=sum(stake>0 & hits==0),
      mean_pair_overlap=mean(mean_pair_overlap[stake>0]),
      mean_max_reuse=mean(max_fixture_reuse[stake>0]),
      mean_model_union=mean(eval_union[stake>0]),
      observed_union=mean(hits[stake>0]>0),
      mean_fixture_capital_hhi=mean(fixture_capital_hhi[stake>0]),
      mean_max_fixture_capital_share=mean(max_fixture_capital_share[stake>0]),
      longest_loss_streak={runs<-rle(net<0);max(c(0,runs$lengths[runs$values]))},
      mean_redundant_mass=mean(coverage_minus_union[stake>0]),.groups='drop')
  summary<-z$summary |> dplyr::left_join(meta,by='arm',relationship='many-to-one') |>
    dplyr::left_join(risk,by=c('arm','seed'),relationship='one-to-one')
  base<-summary |> dplyr::filter(variant=='JOINT') |> dplyr::select(seed,budget_cny,
    base_net=net,base_roi=roi,base_drawdown=max_drawdown,base_hits=hit_issues,
    base_stake=stake,base_best1=net_without_best,base_best3=net_without_best3,base_best5=net_without_best5)
  paired<-summary |> dplyr::left_join(base,by=c('seed','budget_cny'),relationship='many-to-one') |>
    dplyr::mutate(delta_net=net-base_net,delta_roi=roi-base_roi,
      delta_drawdown=max_drawdown-base_drawdown,delta_hits=hit_issues-base_hits,
      delta_stake=stake-base_stake,delta_best1=net_without_best-base_best1,
      delta_best3=net_without_best3-base_best3,delta_best5=net_without_best5-base_best5)
  baseline<-rows |> dplyr::filter(variant=='JOINT') |> dplyr::select(issue,seed,budget_cny,
    base_net=net,base_gross=gross,base_stake=stake,base_hits=hits)
  per_issue<-rows |> dplyr::left_join(baseline,by=c('issue','seed','budget_cny'),relationship='many-to-one') |>
    dplyr::mutate(delta_net=net-base_net,delta_gross=gross-base_gross,delta_stake=stake-base_stake,
      rescued=hits>0 & base_hits==0,lost=hits==0 & base_hits>0,both_miss=hits==0 & base_hits==0)
  stopifnot(!anyNA(paired$base_net),!anyNA(per_issue$base_net))
  curves<-z$curves |> dplyr::select(-variant,-budget_cny) |>
    dplyr::left_join(meta,by='arm',relationship='many-to-one')
  blocks<-n7_selection_blocks(rows,issue_order,50L) |>
    dplyr::left_join(meta,by='arm',relationship='many-to-one')
  list(summary=summary,curves=curves,paired=paired,per_issue=per_issue,blocks=blocks,overlap=overlap)
}
