# #425 prefix-depth contracts. Pure R; no labels, fitting, network or writes.
# All input surfaces come from n7_sleeve_tables; explicit cutoff identities bind
# each decision. Probabilities are fractions, stakes/returns CNY, ranks1-based.

# Full0..2187 cumulative surfaces, retaining canonical ticket state identities.
# Returns one tibble row per sleeve/depth; ROI and terminal marginals use NA.
n7_capital_curves <- function(surface, cutoffs, expected_cutoffs, unit_cny) {
  stopifnot(identical(cutoffs, expected_cutoffs), length(cutoffs)>0, unit_cny==2,
    identical(dim(surface$prob_mat),dim(surface$value_mat)),
    identical(dim(surface$prob_mat),dim(surface$rank_idx)),ncol(surface$prob_mat)==2187)
  rows <- vector('list',nrow(surface$prob_mat))
  for(j in seq_len(nrow(surface$prob_mat))) {
    p <- surface$prob_mat[j,];v <- surface$value_mat[j,];rank <- surface$rank_idx[j,]
    stopifnot(all(is.finite(p)),all(p>=0),abs(sum(p)-1)<1e-8,
      all(is.finite(v)),all(v>=0),identical(sort(as.integer(rank)),seq_len(2187)),
      all(rank==floor(rank)),all(diff(p[rank])<=1e-14))
    k <- 0:2187;stake <- unit_cny*k;gross <- c(0,cumsum(v[rank]))
    rows[[j]] <- tibble::tibble(sleeve_id=rownames(surface$prob_mat)[j],depth=k,
      state_id=c(NA_integer_,as.integer(rank)-1L),stake=stake,
      coverage=c(0,cumsum(p[rank])),expected_gross=gross,expected_net=gross-stake,
      expected_roi=ifelse(stake>0,(gross-stake)/stake,NA_real_),
      marginal_coverage=c(p[rank],NA_real_),marginal_net=c(v[rank]-unit_cny,NA_real_))
  }
  dplyr::bind_rows(rows)
}

# Resolve exact prefix depth per sleeve. targets is a named numeric vector;
# mode is top_n or coverage. Overspending is reported, never silently truncated.
# tau1 permits declared rounding tolerance and omits zero-probability tail.
n7_capital_resolve <- function(curves, mode, targets, budget_cny, tolerance,
                               cutoffs, expected_cutoffs) {
  stopifnot(identical(cutoffs,expected_cutoffs),length(cutoffs)>0,
    mode %in% c('top_n','coverage'),is.numeric(targets),length(targets)>0,
    !is.null(names(targets)),!anyDuplicated(names(targets)),all(is.finite(targets)),
    all(names(targets) %in% unique(curves$sleeve_id)),
    length(budget_cny)==1,is.finite(budget_cny),budget_cny>=0,
    length(tolerance)==1,is.finite(tolerance),tolerance>=0,tolerance<=1e-8)
  if(mode=='coverage')stopifnot(all(targets>=0 & targets<=1))
  else stopifnot(all(targets>=0 & targets<=2187),all(targets==floor(targets)))
  output <- lapply(seq_along(targets),function(j) {
    z <- curves[curves$sleeve_id==names(targets)[j],];z <- z[order(z$depth),]
    stopifnot(identical(as.integer(z$depth),0:2187),all(is.finite(z$coverage)),
      all(diff(z$coverage)>=-1e-14),z$coverage[1]==0,abs(tail(z$coverage,1)-1)<=1e-8)
    target <- unname(targets[j])
    eligible <- if(mode=='top_n') which(z$depth==target) else
      which(z$coverage >= if(target==1)1-tolerance else target)
    if(!length(eligible))stop('Coverage target unreachable')
    chosen <- z[eligible[1],]
    tibble::tibble(sleeve_id=names(targets)[j],target_coverage=if(mode=='coverage')target else NA_real_,
      n_tickets=chosen$depth,actual_coverage=chosen$coverage,stake=chosen$stake,
      coverage_overshoot=if(mode=='coverage')chosen$coverage-target else NA_real_)
  })
  result <- dplyr::bind_rows(output);total <- sum(result$stake)
  list(allocation=result,total_stake=total,cash=if(total<=budget_cny)budget_cny-total else NA_real_,
    budget_excess=max(0,total-budget_cny),status=if(total<=budget_cny)'FEASIBLE' else 'OVER_BUDGET',
    configuration_key=paste(result$sleeve_id,result$n_tickets,sep=':',collapse='|'),cutoffs=cutoffs)
}
