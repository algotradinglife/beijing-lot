# #437: frozen prediction curves and fixed-policy, retrospective budget probes.
# No fitting, historical threshold selection or result-bearing allocation input.

# Exact coverage prefixes, using the existing authoritative depth resolver.
# One row per sleeve/target; money CNY; targets fractions. Native cutoff validation
# is performed by n7_joint_validate at the runner boundary. No IO or labels.
n7_sweet_points <- function(curves, targets, cutoffs, expected_cutoffs, unit_cny) {
  stopifnot(identical(cutoffs,expected_cutoffs),length(cutoffs)>0,unit_cny==2,
    all(is.finite(targets)),length(targets)>0,all(targets>0 & targets<=1),
    !anyDuplicated(targets),!anyDuplicated(curves[c('sleeve_id','depth')]))
  curves$sleeve_id <- as.character(curves$sleeve_id)
  pieces <- split(curves,curves$sleeve_id)
  out <- list();k <- 0L
  for (id in names(pieces)) {
    z <- pieces[[id]]
    for (target in targets) {
      p <- n7_capital_resolve(z,'coverage',setNames(target,id),4374,1e-12,
        cutoffs,expected_cutoffs)$allocation
      hit <- z[z$depth==p$n_tickets,]
      stopifnot(nrow(hit)==1,hit$stake==unit_cny*hit$depth,
        is.finite(hit$expected_gross),hit$expected_gross>=0)
      k <- k+1L
      out[[k]] <- tibble::tibble(sleeve_id=id,target=target,depth=p$n_tickets,
        stake=p$stake,coverage=p$actual_coverage,expected_gross=hit$expected_gross)
    }
  }
  result <- dplyr::bind_rows(out);attr(result,'cutoffs') <- cutoffs;result
}

# Exact 0/1 knapsack with fixture reuse and pair overlap constraints via HiGHS.
# Maximize SUM of group coverage, not union probability. Candidate prefixes are
# purchased once; no copies/deepening, unspent cash retained. These fixed probes
# are not learned policies. points must contain only the six prediction columns.
# fixture_sets: named list of seven distinct slot IDs; U/P explicit integers.
# Returns funded IDs, stake/cash and solver status, or fails (no partial success).
n7_sweet_allocate <- function(points, fixture_sets, cutoffs, expected_cutoffs,
                              target, cap_cny, budget_cny, unit_cny, reuse, overlap) {
  stopifnot(identical(cutoffs,expected_cutoffs),length(cutoffs)>0,
    identical(attr(points,'cutoffs'),cutoffs),unit_cny==2,budget_cny==1024,
    identical(names(points),c('sleeve_id','target','depth','stake','coverage','expected_gross')),
    is.finite(cap_cny),cap_cny>0,is.finite(target),target>0,target<=1,
    reuse>=1,reuse==floor(reuse),overlap>=0,overlap<=7,overlap==floor(overlap),
    !anyNA(points),all(points$stake==2*points$depth),
    all(is.finite(points$coverage)),all(points$coverage>=0 & points$coverage<=1),
    !anyDuplicated(points[c('sleeve_id','target')]))
  z <- points[abs(points$target-target)<1e-12 & points$stake<=cap_cny,]
  if(!nrow(z))return(list(ids=character(),stake=0,cash=budget_cny,status='EMPTY',cutoffs=cutoffs))
  stopifnot(all(z$sleeve_id %in% names(fixture_sets)))
  sets <- fixture_sets[z$sleeve_id]
  stopifnot(all(lengths(sets)==7),all(vapply(sets,anyDuplicated,integer(1))==0),
    all(unlist(sets) %in% names(cutoffs)))
  slots <- unique(unlist(sets))
  incidence <- vapply(sets,function(s)as.numeric(slots %in% s),numeric(length(slots)))
  A <- rbind(z$stake,incidence);rhs <- c(budget_cny,rep(reuse,length(slots)))
  if(nrow(z)>1)for(i in seq_len(nrow(z)-1))for(j in (i+1):nrow(z)) {
    if(length(intersect(sets[[i]],sets[[j]]))>overlap) {
      row <- numeric(nrow(z));row[c(i,j)] <- 1
      A <- rbind(A,row);rhs <- c(rhs,1)
    }
  }
  fit <- highs::highs_solve(L=z$coverage,lower=rep(0,nrow(z)),upper=rep(1,nrow(z)),
    A=A,lhs=rep(-Inf,nrow(A)),rhs=rhs,types=rep('I',nrow(z)),maximum=TRUE,
    control=highs::highs_control(threads=1L,random_seed=0L,log_to_console=FALSE,
      mip_rel_gap=0,mip_max_nodes=100000L))
  stopifnot(identical(as.character(fit$status_message),'Optimal'))
  chosen <- as.numeric(fit$primal_solution>.5)
  stopifnot(all(as.numeric(A %*% chosen)<=rhs+1e-8))
  cost <- sum(z$stake[chosen==1])
  list(ids=z$sleeve_id[chosen==1],stake=cost,cash=budget_cny-cost,status='OPTIMAL',cutoffs=cutoffs)
}
