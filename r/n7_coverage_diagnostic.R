# Retrospective fixed-grid description only, not a learned allocation policy.
# ranks: hash-verified n7_rank_diagnostic table with cohort and exact target costs.
# targets: integer percentage points naming coverage_<target>_cost_cny columns.
# caps_cny: finite positive CNY limits, applied to modeled target cost, not labels.
# Returns eligible candidate rows for each grid cell. Gross already includes .65.
# Missing values/keys, invalid costs or missing targets fail. No IO or learning.
n7_coverage_grid <- function(ranks, targets, caps_cny) {
  stopifnot(nrow(ranks)>0,!anyDuplicated(ranks[c('issue','sleeve_id')]),
    length(targets)>0,all(is.finite(targets)),all(targets==floor(targets)),
    all(targets>0 & targets<=100),!anyDuplicated(targets),
    length(caps_cny)>0,all(is.finite(caps_cny)),all(caps_cny>0),!anyDuplicated(caps_cny))
  cols <- paste0('coverage_',targets,'_cost_cny')
  stopifnot(all(cols %in% names(ranks)),
    !anyNA(ranks[c('issue','sleeve_id','cohort','actual_hit_cost_cny','actual_gross_cny',cols)]),
    all(is.finite(ranks$actual_gross_cny)),all(ranks$actual_gross_cny>=0),
    all(ranks$actual_hit_cost_cny %in% (2*(1:2187))))
  out <- list(); k <- 0L
  for (target in targets) {
    costs <- ranks[[paste0('coverage_',target,'_cost_cny')]]
    stopifnot(all(costs %in% (2*(1:2187))))
    for (cap in caps_cny) {
      k <- k+1L
      out[[k]] <- ranks |> dplyr::mutate(target_pct=target,cap_cny=cap,
        stake=costs,hit=actual_hit_cost_cny<=stake,
        gross=ifelse(hit,actual_gross_cny,0),net=gross-stake) |>
        dplyr::filter(stake<=cap)
    }
  }
  dplyr::bind_rows(out)
}

# Summarize candidate ROI and removal of the largest-net issue (all its groups).
# Empty grid cells have no row. Candidate groups can overlap: no independence
# claims or binomial intervals. Returns summary and per-issue amounts, in CNY.
n7_coverage_summary <- function(rows) {
  keys <- c('cohort','target_pct','cap_cny')
  stopifnot(nrow(rows)>0,!anyNA(rows[c(keys,'issue','sleeve_id','stake','gross','net','hit')]),
    !anyDuplicated(rows[c(keys,'issue','sleeve_id')]),all(rows$stake>0),
    all(is.finite(rows$stake)),all(is.finite(rows$gross)),
    all(abs(rows$net-(rows$gross-rows$stake))<1e-8))
  issues <- rows |> dplyr::group_by(dplyr::across(dplyr::all_of(c(keys,'issue')))) |>
    dplyr::summarise(groups=dplyr::n(),stake=sum(stake),gross=sum(gross),net=sum(net),.groups='drop')
  best <- issues |> dplyr::arrange(dplyr::desc(net),issue) |>
    dplyr::group_by(dplyr::across(dplyr::all_of(keys))) |> dplyr::slice_head(n=1) |>
    dplyr::ungroup() |> dplyr::select(dplyr::all_of(keys),best_issue=issue,
      best_net=net,best_stake=stake)
  summary <- rows |> dplyr::group_by(dplyr::across(dplyr::all_of(keys))) |>
    dplyr::summarise(groups=dplyr::n(),issues=dplyr::n_distinct(issue),
      cost_median=median(stake),cost_q25=quantile(stake,.25),cost_q75=quantile(stake,.75),
      hit_rate=mean(hit),stake=sum(stake),gross=sum(gross),net=sum(net),.groups='drop') |>
    dplyr::left_join(best,by=keys,relationship='one-to-one') |>
    dplyr::mutate(roi=net/stake,roi_without_best=ifelse(stake>best_stake,
      (net-best_net)/(stake-best_stake),NA_real_))
  list(summary=summary,issues=issues)
}
