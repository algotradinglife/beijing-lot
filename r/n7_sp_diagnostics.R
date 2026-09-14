# Descriptive SP-filter comparisons only; no fitting, selection or IO.
# rows: settled plans keyed issue/arm/seed, explicit SP and admission diagnostics.
# issue_order: complete chronological character IDs; initial_capital_cny: CNY.
# Returns summary, curves, blocks, per_issue, admission, admission_summary,
# paired differences and common-staked issue comparisons. ROI is a fraction;
# zero stake has NA ROI. Invalid identities/admission/controls fail closed.
n7_sp_diagnostics <- function(rows,issue_order,initial_capital_cny) {
  required<-c('issue','arm','seed','mode','objective','allocation_order','budget_cny','minimum_sp',
    'total_fixtures','eligible_fixtures','total_groups','eligible_groups','eligible_core_groups','removed_top1_mass')
  stopifnot(all(required %in% names(rows)),!anyNA(rows[required]),
    !anyDuplicated(rows[c('issue','arm','seed')]),all(rows$minimum_sp>=1),
    all(rows$eligible_fixtures>=0 & rows$eligible_fixtures<=rows$total_fixtures),
    all(rows$eligible_groups>=0 & rows$eligible_groups<=rows$total_groups),
    all(rows$eligible_core_groups>=0 & rows$eligible_core_groups<=rows$eligible_groups))
z<-n7_sweet_union_summary(rows,issue_order,initial_capital_cny)
stopifnot(!any(z$curves$stopped))
policy<-rows |> distinct(arm,mode,objective,allocation_order,budget_cny,minimum_sp) |>
 mutate(rule=paste(mode,allocation_order,objective,sep='/'),gate=factor(minimum_sp),budget=factor(budget_cny))
summary<-z$summary |> left_join(policy,by='arm',relationship='many-to-one')
curves<-z$curves |> select(-any_of(c('mode','objective','allocation_order','budget_cny','minimum_sp'))) |>
 left_join(policy,by='arm',relationship='many-to-one')
blocks<-n7_selection_blocks(rows,issue_order,50) |> left_join(policy,by='arm',relationship='many-to-one')
per_issue<-rows |> mutate(issue_roi=ifelse(stake>0,net/stake,NA_real_))
admission<-rows |> distinct(issue,minimum_sp,total_fixtures,eligible_fixtures,total_groups,eligible_groups,eligible_core_groups,removed_top1_mass)
stopifnot(nrow(admission)==length(issue_order)*length(unique(rows$minimum_sp)),
 !anyDuplicated(admission[c('issue','minimum_sp')]))
admission_summary<-admission |> group_by(minimum_sp) |> summarise(
 mean_retained_fixtures=mean(eligible_fixtures),mean_retained_groups=mean(eligible_groups),
 mean_retained_core=mean(eligible_core_groups),no_group_issues=sum(eligible_groups==0),
 no_core_issues=sum(eligible_core_groups==0),enough_fixtures_to_rebuild=sum(eligible_fixtures>=7),
 rebuild_possible_but_no_original_groups=sum(eligible_fixtures>=7 & eligible_groups==0),
 mean_removed_top1_mass=sum(removed_top1_mass)/n(),.groups='drop')
control<-summary |> filter(minimum_sp==1) |> select(rule,budget_cny,seed,
 control_net=net,control_stake=stake,control_roi=roi,control_dd=max_drawdown,control_hit=hit_issues)
stopifnot(!anyDuplicated(control[c('rule','budget_cny','seed')]))
paired<-summary |> left_join(control,by=c('rule','budget_cny','seed'),relationship='many-to-one') |>
 mutate(delta_net=net-control_net,delta_stake=stake-control_stake,delta_roi=roi-control_roi,
 delta_dd=max_drawdown-control_dd,delta_hit=hit_issues-control_hit)
stopifnot(!anyNA(paired[c('control_net','control_stake','control_dd','control_hit')]))
# Same issue set per gate, including all no-bet issues, for paired comparisons.
# Common-staked summary separates selected-issue composition from full exposure.
control_rows<-rows |> filter(minimum_sp==1) |>
 select(issue,seed,mode,objective,allocation_order,budget_cny,control_stake=stake,control_net=net,control_hits=hits)
common<-rows |> left_join(control_rows,
 by=c('issue','seed','mode','objective','allocation_order','budget_cny'),relationship='many-to-one') |>
 filter(stake>0,control_stake>0) |> group_by(arm,seed) |>
 summarise(common_issues=n(),filtered_stake=sum(stake),original_stake=sum(control_stake),
 filtered_net=sum(net),original_net=sum(control_net),filtered_hit=sum(hits>0),original_hit=sum(control_hits>0),
 filtered_roi=filtered_net/filtered_stake,original_roi=original_net/original_stake,.groups='drop')
list(summary=summary,curves=curves,blocks=blocks,per_issue=per_issue,
 admission=admission,admission_summary=admission_summary,paired=paired,common=common)
}
