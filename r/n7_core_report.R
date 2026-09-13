# Pair every period/seed against explicit comparison arms. Descriptive only;
# unequal spending is reported, never rescaled to manufacture matched returns.
# Inputs are funded period rows from n7_capital_report; money CNY, ROI percent.
n7_core_pairs <- function(periods,comparisons,issue_order,seeds) {
  stopifnot(all(c('issue','arm','seed','stake','gross','net','hits') %in% names(periods)),
    all(c('treatment','control','comparison') %in% names(comparisons)),
    !anyDuplicated(periods[c('issue','arm','seed')]),
    !anyNA(periods[c('issue','arm','seed','stake','gross','net','hits')]),
    !anyDuplicated(issue_order),length(issue_order)>0,length(seeds)>0,!anyDuplicated(seeds))
  rows<-lapply(seq_len(nrow(comparisons)),function(j) {
    rule<-comparisons[j,]
    a<-periods |> dplyr::filter(arm==rule$treatment) |>
      dplyr::select(issue,seed,a_stake=stake,a_net=net,a_gross=gross,a_hits=hits)
    b<-periods |> dplyr::filter(arm==rule$control) |>
      dplyr::select(issue,seed,b_stake=stake,b_net=net,b_gross=gross,b_hits=hits)
    z<-dplyr::full_join(a,b,by=c('issue','seed'),relationship='one-to-one')
    stopifnot(nrow(z)==length(issue_order)*length(seeds),!anyNA(z),
      setequal(z$issue,issue_order),setequal(z$seed,seeds))
    z |> dplyr::group_by(seed) |> dplyr::summarise(
      treatment=rule$treatment,control=rule$control,comparison=rule$comparison,
      issues=dplyr::n(),rescued=sum(a_hits>0 & b_hits==0),lost=sum(a_hits==0 & b_hits>0),
      both_hit=sum(a_hits>0 & b_hits>0),both_missed=sum(a_hits==0 & b_hits==0),
      net_delta_cny=sum(a_net-b_net),stake_delta_cny=sum(a_stake-b_stake),
      equal_spend_issues=sum(a_stake==b_stake),
      treatment_roi_percent=if(sum(a_stake)>0)100*sum(a_net)/sum(a_stake) else NA_real_,
      control_roi_percent=if(sum(b_stake)>0)100*sum(b_net)/sum(b_stake) else NA_real_,
      .groups='drop')
  })
  dplyr::bind_rows(rows)
}

# Attribute realized CNY to core and opportunity sleeves, including cash-stop.
# Separate accounting does not imply independent risks or isolated opportunity EV.
n7_core_attribution <- function(periods) {
  x<-periods |> dplyr::filter(!reference)
  stopifnot(all(c('core_stake','core_gross','opportunity_stake','opportunity_gross','stopped') %in% names(x)),
    !anyNA(x[c('core_stake','core_gross','opportunity_stake','opportunity_gross','stopped')]))
  x<-x |> dplyr::mutate(dplyr::across(c(core_stake,core_gross,opportunity_stake,opportunity_gross),
    ~ifelse(stopped,0,.x)))
  stopifnot(all(abs(x$core_stake+x$opportunity_stake-x$stake)<1e-8),
    all(abs(x$core_gross+x$opportunity_gross-x$gross)<1e-6))
  x |> dplyr::group_by(arm,seed) |> dplyr::summarise(
    core_stake=sum(core_stake),core_gross=sum(core_gross),
    opportunity_stake=sum(opportunity_stake),opportunity_gross=sum(opportunity_gross),
    .groups='drop') |>
    dplyr::mutate(core_net=core_gross-core_stake,opportunity_net=opportunity_gross-opportunity_stake,
      core_roi_percent=ifelse(core_stake>0,100*core_net/core_stake,NA_real_),
      opportunity_roi_percent=ifelse(opportunity_stake>0,100*opportunity_net/opportunity_stake,NA_real_))
}

# Realized funded coverage versus paid copies. Sleeve rows represent one prefix
# in one copy layer; period rows are the cash-stop-adjusted report. CNY units.
# Returns per-arm/seed exposure totals; no learning, selection, or side effects.
n7_core_exposure <- function(sleeves,periods) {
  keys<-c('issue','arm','seed')
  stopifnot(all(c(keys,'sleeve_id','role','copy_index','depth','stake') %in% names(sleeves)),
    all(c(keys,'reference','stopped','stake') %in% names(periods)),
    !anyDuplicated(periods[keys]),
    !anyDuplicated(sleeves[c(keys,'sleeve_id','copy_index')]),
    !anyNA(sleeves[c(keys,'role','copy_index','depth','stake')]),
    all(sleeves$role %in% c('CORE','OPPORTUNITY')),
    all(sleeves$copy_index>=1 & sleeves$copy_index<=3 & sleeves$copy_index==floor(sleeves$copy_index)),
    all(sleeves$depth>0 & sleeves$depth==floor(sleeves$depth)),
    all(sleeves$stake==2*sleeves$depth))
  p<-periods |> dplyr::filter(!reference) |>
    dplyr::select(dplyr::all_of(keys),stopped,period_stake=stake)
  z<-dplyr::left_join(sleeves,p,by=keys,relationship='many-to-one')
  stopifnot(!anyNA(z$stopped))
  total<-z |> dplyr::group_by(issue,arm,seed) |>
    dplyr::summarise(paid=sum(ifelse(stopped,0,stake)),.groups='drop')
  check<-dplyr::left_join(p,total,by=keys,relationship='one-to-one')
  stopifnot(all(dplyr::coalesce(check$paid,0)==check$period_stake))
  by_issue<-z |> dplyr::filter(!stopped) |> dplyr::group_by(issue,arm,seed) |>
    dplyr::summarise(core_groups=sum(role=='CORE' & copy_index==1),
      opportunity_groups=sum(role=='OPPORTUNITY' & copy_index==1),
      unique_ticket_units=sum(depth[copy_index==1]),paid_ticket_units=sum(depth),
      repeated_stake_cny=sum(stake[copy_index>1]),.groups='drop')
  dplyr::left_join(p,by_issue,by=keys,relationship='one-to-one') |>
    dplyr::mutate(dplyr::across(c(core_groups,opportunity_groups,unique_ticket_units,
      paid_ticket_units,repeated_stake_cny),~dplyr::coalesce(.x,0))) |>
    dplyr::group_by(arm,seed) |> dplyr::summarise(issues=dplyr::n(),
      core_groups_mean=mean(core_groups),opportunity_groups_mean=mean(opportunity_groups),
      unique_ticket_units=sum(unique_ticket_units),paid_ticket_units=sum(paid_ticket_units),
      repeated_stake_cny=sum(repeated_stake_cny),
      repeated_stake_percent=if(sum(period_stake)>0)100*sum(repeated_stake_cny)/sum(period_stake) else NA_real_,
      .groups='drop')
}
