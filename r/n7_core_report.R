# Descriptive fixed-core coverage and cash-aware accounting summaries.
n7_core_coverage_summary <- function(coverage,periods) {
  # coverage: one frozen issue/arm/seed/scenario-kind; probabilities fractions.
  # Return means over all account periods, zeroing stopped/nonfunded periods;
  # increments are percentage points with the treatment's core tickets fixed.
  # Counts reconcile event unions; this diagnostic never ranks or reallocates.
  keys<-c('issue','arm','seed')
  required<-c('worlds','core_hits','opportunity_hits','shared_hits','union_hits','incremental_hits')
  stopifnot(all(c(keys,'kind',required) %in% names(coverage)),
    !anyDuplicated(coverage[c(keys,'kind')]),!anyNA(coverage[c(keys,'kind',required)]),
    all(coverage$kind %in% c('training','evaluation')),
    all(as.matrix(coverage[required])>=0),all(as.matrix(coverage[required])==floor(as.matrix(coverage[required]))),
    all(coverage$worlds>0),all(coverage$union_hits<=coverage$worlds),
    all(coverage$shared_hits<=pmin(coverage$core_hits,coverage$opportunity_hits)),
    all(coverage$union_hits==coverage$core_hits+coverage$opportunity_hits-coverage$shared_hits),
    all(coverage$incremental_hits==coverage$union_hits-coverage$core_hits),
    !anyDuplicated(periods[keys]))
  p<-periods |> dplyr::filter(!reference) |>
    dplyr::select(dplyr::all_of(keys),stopped,stake)
  expected<-tidyr::crossing(p,kind=c('training','evaluation'))
  z<-dplyr::full_join(expected,coverage,by=c(keys,'kind'),relationship='one-to-one')
  stopifnot(nrow(z)==2*nrow(p),!anyNA(z[c('stopped','stake',required)]))
  z |> dplyr::mutate(funded=!stopped & stake>0) |>
    dplyr::group_by(arm,seed,kind) |> dplyr::summarise(issues=dplyr::n(),funded_issues=sum(funded),
      core_probability_percent=100*mean(ifelse(funded,core_hits/worlds,0)),
      opportunity_probability_percent=100*mean(ifelse(funded,opportunity_hits/worlds,0)),
      union_probability_percent=100*mean(ifelse(funded,union_hits/worlds,0)),
      incremental_percentage_points=100*mean(ifelse(funded,incremental_hits/worlds,0)),
      .groups='drop')
}

# Pair every period/seed against explicit comparison arms. Descriptive only;
# unequal spending is reported, never rescaled to manufacture matched returns.
# Inputs are funded period rows from n7_capital_report; money CNY, ROI percent.
n7_core_pairs <- function(periods,comparisons,issue_order,seeds) {
  stopifnot(all(c('issue','arm','seed','stake','gross','net','hits','stopped') %in% names(periods)),
    all(c('treatment','control','comparison') %in% names(comparisons)),
    !anyDuplicated(periods[c('issue','arm','seed')]),
    !anyNA(periods[c('issue','arm','seed','stake','gross','net','hits','stopped')]),
    !anyDuplicated(issue_order),length(issue_order)>0,length(seeds)>0,!anyDuplicated(seeds))
  rows<-lapply(seq_len(nrow(comparisons)),function(j) {
    rule<-comparisons[j,]
    a<-periods |> dplyr::filter(arm==rule$treatment) |>
      dplyr::select(issue,seed,a_stake=stake,a_net=net,a_gross=gross,a_hits=hits,a_stopped=stopped)
    b<-periods |> dplyr::filter(arm==rule$control) |>
      dplyr::select(issue,seed,b_stake=stake,b_net=net,b_gross=gross,b_hits=hits,b_stopped=stopped)
    z<-dplyr::full_join(a,b,by=c('issue','seed'),relationship='one-to-one')
    stopifnot(nrow(z)==length(issue_order)*length(seeds),!anyNA(z),
      setequal(z$issue,issue_order),setequal(z$seed,seeds))
    z |> dplyr::group_by(seed) |> dplyr::summarise(
      treatment=rule$treatment,control=rule$control,comparison=rule$comparison,
      issues=dplyr::n(),rescued=sum(a_hits>0 & b_hits==0),lost=sum(a_hits==0 & b_hits>0),
      both_hit=sum(a_hits>0 & b_hits>0),both_missed=sum(a_hits==0 & b_hits==0),
      both_funded=sum(a_stake>0 & b_stake>0),
      one_side_funded=sum(xor(a_stake>0,b_stake>0)),neither_funded=sum(a_stake==0 & b_stake==0),
      treatment_stopped=sum(a_stopped),control_stopped=sum(b_stopped),
      one_side_stopped=sum(xor(a_stopped,b_stopped)),both_stopped=sum(a_stopped & b_stopped),
      treatment_no_bet=sum(a_stake==0 & !a_stopped),control_no_bet=sum(b_stake==0 & !b_stopped),
      funded_rescued=sum(a_stake>0 & b_stake>0 & a_hits>0 & b_hits==0),
      funded_lost=sum(a_stake>0 & b_stake>0 & a_hits==0 & b_hits>0),
      net_delta_cny=sum(a_net-b_net),stake_delta_cny=sum(a_stake-b_stake),
      equal_spend_issues=sum(a_stake==b_stake & a_stake>0),
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

# Post-settlement diagnostic only. ranks: one issue/sleeve with accepted actual
# winning rank/return and theoretical 20% coverage cost. Each sleeve row is one
# paid copy; periods are cash-stop-adjusted. Reconciles every issue/arm/seed first,
# then groups by fixed theoretical ticket-cost bands, never selects investments.
n7_core_rank_attribution <- function(ranks,sleeves,periods) {
  key<-c('issue','arm','seed')
  stopifnot(!anyDuplicated(ranks[c('issue','sleeve_id')]),
    !anyDuplicated(sleeves[c(key,'sleeve_id','copy_index')]),!anyDuplicated(periods[key]),
    all(c('actual_rank','actual_gross_cny','coverage_20_cost_cny') %in% names(ranks)),
    all(ranks$actual_rank>=1 & ranks$actual_rank<=2187),
    all(ranks$coverage_20_cost_cny>0 & ranks$coverage_20_cost_cny%%2==0))
  ranks$sleeve_id<-as.character(ranks$sleeve_id)
  sleeves$sleeve_id<-as.character(sleeves$sleeve_id)
  p<-periods |> dplyr::filter(!reference) |>
    dplyr::select(dplyr::all_of(key),stopped,period_gross=gross,period_hits=hits,period_stake=stake)
  z<-dplyr::left_join(sleeves,ranks,by=c('issue','sleeve_id'),relationship='many-to-one') |>
    dplyr::left_join(p,by=key,relationship='many-to-one')
  stopifnot(!anyNA(z[c('actual_rank','actual_gross_cny','coverage_20_cost_cny','stopped')]))
  z<-z |> dplyr::mutate(won=depth>=actual_rank & !stopped,
    actual_gross=ifelse(won,actual_gross_cny,0),funded_stake=ifelse(stopped,0,stake),
    forecast_gross=ifelse(stopped,0,expected_gross),
    theory_tickets=coverage_20_cost_cny/2,
    cost_band=cut(theory_tickets,c(0,32,64,128,256,Inf),
      labels=c('<=32','33–64','65–128','129–256','>256'),right=TRUE))
  totals<-z |> dplyr::group_by(dplyr::across(dplyr::all_of(key))) |>
    dplyr::summarise(replay_gross=sum(actual_gross),replay_hits=sum(won & copy_index==1),
      replay_stake=sum(funded_stake),.groups='drop')
  check<-dplyr::left_join(p,totals,by=key,relationship='one-to-one') |>
    dplyr::mutate(dplyr::across(c(replay_gross,replay_hits,replay_stake),~dplyr::coalesce(.x,0)))
  stopifnot(all(check$replay_hits==check$period_hits),all(check$replay_stake==check$period_stake),
    all(abs(check$replay_gross-check$period_gross)<=1e-6+abs(check$period_gross)*1e-10))
  z |> dplyr::filter(!stopped) |> dplyr::group_by(arm,seed,role,cost_band) |>
    dplyr::summarise(issues=dplyr::n_distinct(issue),paid_prefixes=dplyr::n(),
      unique_prefixes=sum(copy_index==1),unique_hits=sum(won & copy_index==1),paid_hits=sum(won),
      stake=sum(funded_stake),gross=sum(actual_gross),model_gross=sum(forecast_gross),
      .groups='drop') |> dplyr::mutate(net=gross-stake,roi_percent=100*net/stake,
        model_roi_percent=100*(model_gross-stake)/stake)
}
