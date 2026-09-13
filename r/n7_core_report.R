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
