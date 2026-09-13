# Post-settlement diagnosis only: no fitting, selection or policy changes.
# x: validated frozen issue JSON; unit/payout explicit CNY constants; targets
# are cumulative probabilities. Returns one row per candidate, with CNY costs,
# 1-based actual rank and probabilities as fractions. Missing labels/SP fail.
n7_rank_diagnostic <- function(x, unit_cny, payout_factor, targets) {
  stopifnot(unit_cny == 2, payout_factor == .65,
    identical(x$evidence_class, 'POST_SETTLEMENT_DIAGNOSTIC'),
    length(x$cutoffs)>0, length(targets)>0, all(is.finite(targets)),
    all(targets>0 & targets<=1), !anyDuplicated(targets))
  curves <- tibble::as_tibble(x$curves)
  audit <- tibble::as_tibble(x$audit)
  fixtures <- tibble::as_tibble(x$fixtures)
  keys <- c('issue','slot','provider_id')
  stopifnot(!anyDuplicated(audit[keys]),!anyDuplicated(fixtures[keys]),
    all(as.character(audit$issue)==x$issue),all(as.character(fixtures$issue)==x$issue))
  fixtures <- dplyr::left_join(fixtures, audit, by=keys, suffix=c('', '_audit'),
    relationship='one-to-one')
  stopifnot(all(!is.na(fixtures$actual_direction)),
    all(fixtures$actual_direction %in% c('W','D','L')),
    all(fixtures$handicap == fixtures$handicap_audit),
    all(is.finite(fixtures$spf_sp)), all(fixtures$spf_sp>0),
    all(!is.na(fixtures$status)), !any(grepl('spf:IDENTITY',fixtures$status)))
  stopifnot(!anyDuplicated(x$sleeves$id),
    setequal(as.character(curves$sleeve_id),as.character(x$sleeves$id)))
  rows <- vector('list',nrow(x$sleeves));sets <- character(length(rows))
  for (j in seq_along(rows)) {
    s <- x$sleeves[j,]; ix <- as.integer(s$fixture_indices[[1]])+1L
    stopifnot(length(ix)==7,!anyDuplicated(ix),all(ix>=1 & ix<=nrow(fixtures)))
    sets[j] <- paste(sort(ix),collapse=',')
    f <- fixtures[ix,]; code <- match(f$actual_direction,c('W','D','L'))-1L
    state <- sum(code*3^(6:0))
    z <- curves[as.character(curves$sleeve_id)==as.character(s$id),]
    z <- z[order(z$depth),]
    stopifnot(identical(as.integer(z$depth),0:2187),
      is.na(z$state_id[1]),identical(sort(as.integer(z$state_id[-1])),0:2186),
      all(is.finite(z$coverage)),abs(z$coverage[1])<1e-12,
      abs(tail(z$coverage,1)-1)<1e-8,all(diff(z$coverage)>=-1e-12),
      all(z$stake==unit_cny*z$depth))
    p <- diff(z$coverage);stopifnot(all(diff(p)<=1e-12))
    hit <- z[z$state_id==state & !is.na(z$state_id),]
    stopifnot(nrow(hit)==1)
    gross <- unit_cny*payout_factor*prod(f$spf_sp)
    row <- tibble::tibble(issue=x$issue,sleeve_id=as.character(s$id),origin=s$origin,
      fixture_slots=paste(f$slot,collapse=','),actual_state_id=state,
      actual_rank=hit$depth,actual_hit_cost_cny=hit$stake,
      actual_probability=p[hit$depth],actual_cumulative=hit$coverage,
      model_expected_hit_cost_cny=sum(p*unit_cny*(1:2187)),
      actual_gross_cny=gross,actual_prefix_net_cny=gross-hit$stake,
      actual_prefix_roi=gross/hit$stake-1,
      break_even_depth=min(2187,floor(gross/unit_cny)),
      model_prefix_gross_cny=hit$expected_gross,
      top64_coverage=z$coverage[z$depth==64],
      top128_coverage=z$coverage[z$depth==128])
    for (t in targets) row[[paste0('coverage_',round(100*t),'_cost_cny')]] <-
      z$stake[which(z$coverage>=t-1e-12)[1]]
    rows[[j]] <- row
  }
  stopifnot(!anyDuplicated(sets))
  dplyr::bind_rows(rows)
}

# One row per issue and budget. Oracle counts know results; they are not bets.
# Candidate sets share fixtures, so group rates do not imply independent trials.
n7_rank_summary <- function(rows, budgets_cny) {
  stopifnot(nrow(rows)>0,!anyDuplicated(rows[c('issue','sleeve_id')]),
    all(is.finite(budgets_cny)),all(budgets_cny>0),!anyDuplicated(budgets_cny))
  dplyr::bind_rows(lapply(budgets_cny,function(b) {
    rows |> dplyr::group_by(issue) |> dplyr::summarise(budget_cny=b,
      candidates=dplyr::n(),min_cost_cny=min(actual_hit_cost_cny),
      q25_cost_cny=as.numeric(quantile(actual_hit_cost_cny,.25)),
      median_cost_cny=median(actual_hit_cost_cny),
      q75_cost_cny=as.numeric(quantile(actual_hit_cost_cny,.75)),
      max_cost_cny=max(actual_hit_cost_cny),
      median_model_cost_cny=median(model_expected_hit_cost_cny),
      affordable_candidates=sum(actual_hit_cost_cny<=b),
      profitable_affordable_candidates=sum(actual_hit_cost_cny<=b & actual_prefix_net_cny>0),
      oracle_any_hit=any(actual_hit_cost_cny<=b),
      oracle_profitable_prefix=any(actual_hit_cost_cny<=b & actual_prefix_net_cny>0),
      .groups='drop')
  }))
}

# Reconcile diagnostic ranks/returns against every original frozen allocation.
# allocations: one funded sleeve per issue/seed/arm; results: one plan per key.
# Zero-funded plans produce zero hits/gross. Returns counts or errors, no writes.
n7_rank_allocation_check <- function(rows, allocations, results) {
  # Frozen portable allocations encode internal sleeve IDs as JSON integers.
  # Normalize explicitly to the diagnostic table's character key before joining.
  allocations$sleeve_id <- as.character(allocations$sleeve_id)
  key <- c('issue','seed','arm')
  stopifnot(!anyDuplicated(rows[c('issue','sleeve_id')]),
    !anyDuplicated(allocations[c(key,'sleeve_id')]),!anyDuplicated(results[key]),
    all(allocations$depth>=1 & allocations$depth<=2187),
    all(allocations$depth==floor(allocations$depth)))
  joined <- dplyr::left_join(allocations,rows,by=c('issue','sleeve_id'),
    relationship='many-to-one')
  stopifnot(!anyNA(joined$actual_rank),
    nrow(dplyr::anti_join(allocations,results,by=key))==0)
  totals <- joined |> dplyr::group_by(dplyr::across(dplyr::all_of(key))) |>
    dplyr::summarise(replay_hits=sum(depth>=actual_rank),
      replay_gross=sum(actual_gross_cny[depth>=actual_rank]),.groups='drop')
  check <- dplyr::left_join(results,totals,by=key,relationship='one-to-one')
  check$replay_hits[is.na(check$replay_hits)] <- 0
  check$replay_gross[is.na(check$replay_gross)] <- 0
  stopifnot(all(check$hits==check$replay_hits),
    all(abs(check$gross-check$replay_gross)<=1e-6+abs(check$gross)*1e-10))
  list(status='PASS',plans=nrow(check),allocations=nrow(allocations))
}
