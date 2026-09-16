# Descriptive diagnosis of frozen portfolios. Explicit map: issue/period/stage;
# input row and group contracts are those of the verified joint report.
# Monetary amounts CNY; probabilities 0..1. No fitting, policy changes or I/O.
# Dependencies: existing accounting, fixture-price, return-attribution,
# recent-structure and probability diagnostic modules. Missing/mismatched data
# fails. Returns tidy phase/price/probability/supply/depth/exposure tables.
joint_phase_diagnostic <- function(rows, groups, fixtures, audit, ranks, map,
                                   policies, minimum_sp, cap_cny, unit_cny,
                                   payout_factor, n_legs) {
  stopifnot(!anyDuplicated(map$issue),!anyNA(map),all(c('issue','period','stage') %in% names(map)),
    !anyDuplicated(map$period),identical(sort(map$period),seq_len(nrow(map))),
    'JOINT' %in% policies,!anyDuplicated(policies))
  rows <- rows |> dplyr::filter(policy %in% policies) |> dplyr::select(-dplyr::any_of('stage')) |>
    dplyr::left_join(map,by='issue',relationship='many-to-one')
  stopifnot(!anyNA(rows$stage),setequal(rows$policy,policies),
    !anyDuplicated(rows[c('issue','policy')]),nrow(rows)==length(policies)*nrow(map),
    all(is.finite(as.matrix(rows[c('stake','gross','net','model_hit')]))),
    all(rows$stake>=0),all(rows$gross>=0),all(abs(rows$gross-rows$net-rows$stake)<1e-7))
  groups <- groups |> dplyr::filter(policy %in% policies)
  funded <- groups |> dplyr::transmute(issue,arm=policy,seed=0L,sleeve_id,depth,stake,expected_gross,coverage,copies=1L)
  f <- n7_fixture_price_diagnostic(fixtures,audit)
  structure <- n7_diagnostic_group_structure(f,funded,ranks,map,unit_cny,payout_factor,n_legs,minimum_sp,cap_cny)
  bridge <- structure$bridge$periods |> dplyr::rename(policy=arm)
  check <- rows |> dplyr::left_join(bridge |> dplyr::select(issue,policy,actual_net,actual_gross),
                                   by=c('issue','policy'),relationship='one-to-one')
  stopifnot(all(check$stake[is.na(check$actual_net)]==0),
    all(abs(check$net-tidyr::replace_na(check$actual_net,0))<1e-6),
    all(abs(check$gross-tidyr::replace_na(check$actual_gross,0))<1e-6))
  phases <- rows |> dplyr::group_by(stage,policy) |> dplyr::summarise(
    first=min(issue),last=max(issue),issues=dplyr::n(),avg_stake=mean(stake),profit_issues=sum(net>0),
    stake=sum(stake),gross=sum(gross),net=sum(net),
    roi=if(stake>0)net/stake else NA_real_,hit_issues=sum(hits>0),winning_groups=sum(hits),
    avg_model_hit=mean(model_hit),hit_rate=mean(hits>0),.groups='drop')
  selected <- structure$members |> dplyr::semi_join(funded |> dplyr::filter(arm=='JOINT'),by=c('issue','sleeve_id')) |>
    dplyr::distinct(issue,slot) |> dplyr::mutate(selected=TRUE)
  f <- structure$fixtures |> dplyr::left_join(map,by='issue',relationship='many-to-one') |>
    dplyr::left_join(selected,by=c('issue','slot'),relationship='one-to-one') |>
    dplyr::mutate(selected=tidyr::replace_na(selected,FALSE))
  long <- f |> dplyr::select(issue,slot,provider_id,stage,selected,handicap,actual_outcome=actual_direction,
                            p_W,p_D,p_L,q_W,q_D,q_L) |>
    tidyr::pivot_longer(c(p_W,p_D,p_L,q_W,q_D,q_L),names_to=c('model','outcome'),
                      names_pattern='([pq])_([WDL])',values_to='probability')
  prob <- strategy_probability_diagnostics(long,c('stage','selected','handicap'),c('W','D','L'),seq(0,1,.1))
  outcome_ranks <- long |> dplyr::filter(model=='p') |> dplyr::group_by(issue,slot) |>
    dplyr::arrange(dplyr::desc(probability),match(outcome,c('W','D','L')),.by_group=TRUE) |>
    dplyr::mutate(outcome_rank=dplyr::row_number(),top2_mass=1-min(probability)) |>
    dplyr::filter(outcome==actual_outcome) |> dplyr::ungroup() |>
    dplyr::select(issue,slot,outcome_rank,top2_mass)
  combinations <- structure$members |> dplyr::select(issue,sleeve_id,slot) |>
    dplyr::semi_join(funded |> dplyr::filter(arm=='JOINT'),by=c('issue','sleeve_id')) |>
    dplyr::left_join(outcome_ranks,by=c('issue','slot'),relationship='many-to-one') |>
    dplyr::group_by(issue,sleeve_id) |> dplyr::summarise(third_count=sum(outcome_rank==3),
      second_count=sum(outcome_rank==2),model_all_top2=prod(top2_mass),.groups='drop') |>
    dplyr::left_join(map,by='issue',relationship='many-to-one')
  rank_mix <- combinations |> dplyr::count(stage,third_count,second_count,name='groups')
  top2_groups <- combinations |> dplyr::group_by(stage) |> dplyr::summarise(groups=dplyr::n(),
    actual_all_top2=mean(third_count==0),model_all_top2=mean(model_all_top2),
    mean_third=mean(third_count),mean_second=mean(second_count),.groups='drop')
  scores <- dplyr::bind_rows(dplyr::mutate(prob$scores,pool='ALL'),
                            dplyr::mutate(dplyr::filter(prob$scores,selected),pool='JOINT_SELECTED')) |>
    dplyr::group_by(stage,model,pool) |> dplyr::summarise(fixtures=dplyr::n(),
      top1=mean(top1),top2=mean(top2),brier=mean(brier),log_loss=mean(log_loss),.groups='drop')
  events <- long |> dplyr::filter(selected) |> dplyr::group_by(stage,model,outcome) |>
    dplyr::summarise(fixtures=dplyr::n(),predicted=mean(probability),observed=mean(outcome==actual_outcome),.groups='drop')
  supply <- f |> dplyr::group_by(issue,stage) |> dplyr::summarise(available=dplyr::n(),
    qualified=sum(estimated_top1_sp>=minimum_sp),.groups='drop') |>
    dplyr::group_by(stage) |> dplyr::summarise(issues=dplyr::n(),mean_available=mean(available),
      mean_qualified=mean(qualified),median_qualified=median(qualified),.groups='drop')
  depth <- n7_diagnostic_depth_distribution(structure$ranks |> dplyr::select(-stage,-period),
    funded |> dplyr::filter(arm=='JOINT'),map,unit_cny,c(0,15,32,64,128,256,512,1024,2187),c(0,16,32,64))
  uses <- structure$members |> dplyr::select(issue,sleeve_id,slot) |>
    dplyr::inner_join(funded |> dplyr::select(issue,sleeve_id,arm),by=c('issue','sleeve_id'),relationship='many-to-many') |>
    dplyr::count(issue,arm,slot,name='uses') |> dplyr::left_join(map,by='issue',relationship='many-to-one')
  exposure <- uses |> dplyr::group_by(issue,stage,arm) |> dplyr::summarise(unique_fixtures=dplyr::n(),
    max_uses=max(uses),herfindahl=sum((uses/sum(uses))^2),.groups='drop') |>
    dplyr::group_by(stage,arm) |> dplyr::summarise(issues=dplyr::n(),unique_fixtures=mean(unique_fixtures),
      max_uses=mean(max_uses),herfindahl=mean(herfindahl),.groups='drop')
  list(phases=phases,groups=structure$group_summary,candidates=structure$candidate_summary,
    scores=scores,events=events,supply=supply,exposure=exposure,
    depths=depth$summary,depth_cdf=depth$issue_cdf,miss_gaps=depth$miss_gaps,
    calibration=prob$calibration,handicap_scores=prob$summary,period_bridge=bridge,
    rank_mix=rank_mix,top2_groups=top2_groups)
}
