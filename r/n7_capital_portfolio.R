# #425 prefix options and finite-space allocation. Reuse #424 surfaces/worlds;
# no fitted history, source fetching or actual settlements enter these functions.

# Construct canonical prefix options at explicit candidate depths. Full curves
# remain separate and exact. Duplicate unordered seven-fixture sets are rejected.
# Each option carries exact CNY expectation, coverage and original state columns.
n7_capital_options <- function(bundle,cutoffs,python,model_id,depths,unit_cny,payout_factor) {
  n7_joint_validate(bundle$expanded_pool$fixtures,cutoffs,python)
  stopifnot(unit_cny==2,payout_factor==.65,length(depths)>0,all(is.finite(depths)),
    all(depths>=1 & depths<=2187),all(depths==floor(depths)),!anyDuplicated(depths))
  v <- n7_sleeve_tables(bundle,cutoffs,model_id)
  set_keys <- vapply(bundle$sleeves,function(g)paste(sort(unlist(g$fixture_indices)),collapse=','),character(1))
  stopifnot(!anyDuplicated(set_keys))
  options <- list()
  for(j in seq_along(bundle$sleeves))for(k in depths) {
    g <- bundle$sleeves[[j]];ids <- v$rank_idx[j,seq_len(k)]
    options[[length(options)+1L]] <- list(sleeve_id=g$id,rule='PROB_PREFIX',depth=k,
      fixtures=as.integer(unlist(g$fixture_indices))+1L,state_ids=ids,
      coverage=sum(v$prob_mat[j,ids]),expected_gross=sum(v$value_mat[j,ids]),
      stake=unit_cny*k,state_probability=v$prob_mat[j,],state_payout=v$payout_hat_mat[j,])
  }
  list(issue=bundle$issue,cutoffs=cutoffs,fixtures=bundle$expanded_pool$fixtures,
    options=options,surface=v,model_id=model_id,historical_admission=FALSE)
}

# Model accounting on shared scenarios. Distributional estimates use uniform
# scenario weights. Missing conditional event support gives NA, never infinity.
# Exact linear expectation is reported separately from finite-world averages.
n7_capital_evaluate <- function(pool,selected,scenarios,cutoffs,budget_cny) {
  stopifnot(identical(pool$cutoffs,cutoffs),identical(scenarios$cutoffs,cutoffs),
    all(selected %in% seq_along(pool$options)),!anyDuplicated(selected),
    all(is.finite(scenarios$gross)),all(scenarios$gross>=0),
    all(scenarios$hits %in% 0:1),nrow(scenarios$hits)>0,
    identical(dim(scenarios$hits),dim(scenarios$gross)),
    ncol(scenarios$hits)==length(pool$options),is.finite(budget_cny),budget_cny>=0)
  opts <- pool$options[selected]
  stopifnot(!anyDuplicated(vapply(opts,function(o)o$sleeve_id,numeric(1))))
  stake <- sum(vapply(opts,function(o)o$stake,numeric(1)))
  stopifnot(stake<=budget_cny+1e-8)
  gross <- rowSums(scenarios$gross[,selected,drop=FALSE]);hits <- rowSums(scenarios$hits[,selected,drop=FALSE])
  net <- gross-stake;win <- net>1e-8;lose <- net< -1e-8
  gain <- if(any(win))mean(net[win]) else NA_real_
  loss <- if(any(lose))mean(net[lose]) else NA_real_
  coverage <- vapply(opts,function(o)o$coverage,numeric(1))
  money <- vapply(opts,function(o)o$stake,numeric(1))
  expected <- sum(vapply(opts,function(o)o$expected_gross,numeric(1)))
  tibble::tibble(sleeves=length(opts),distinct_fixture_count=length(unique(unlist(lapply(opts,`[[`,'fixtures')))),
    stake=stake,cash=budget_cny-stake,expected_gross=expected,expected_net=expected-stake,
    expected_roi=if(stake>0)expected/stake-1 else NA_real_,
    any_hit=mean(hits>=1),at_least_two=mean(hits>=2),zero_hit=mean(hits==0),
    profit_probability=mean(win),loss_probability=mean(lose),zero_net_probability=mean(!win & !lose),
    conditional_gain=gain,conditional_loss=loss,payoff_ratio=if(any(win)&&any(lose))gain/abs(loss) else NA_real_,
    gain_support=sum(win),loss_support=sum(lose),simulation_worlds=length(net),
    payoff_support_status=if(any(win)&&any(lose))'BOTH_EVENTS_OBSERVED' else 'INSUFFICIENT_CONDITIONAL_SUPPORT',
    simulated_expected_net=mean(net),coverage_mean=if(length(opts))mean(coverage) else NA_real_,
    coverage_weighted_mean=if(stake>0)sum(coverage*money)/stake else NA_real_,
    coverage_median=if(length(opts))median(coverage) else NA_real_,
    coverage_min=if(length(opts))min(coverage) else NA_real_,coverage_max=if(length(opts))max(coverage) else NA_real_)
}

# Finite-prefix MILP: one funded option per sleeve, exact/full or capped spending.
# objective = any_hit / at_least_two / expected_net / row_coverage. Bounds and
# preferences explicit; minimal ROI is a fraction, minimum_hit in[0,1]. Incumbents
# may be returned as FEASIBLE_NOT_PROVEN only after all actual constraints pass.
n7_capital_solve <- function(pool,scenarios,cutoffs,budget_cny,objective,minimum_roi,
                              minimum_hit,spend_all,nodes,gap,seed,time_seconds) {
  stopifnot(identical(pool$cutoffs,cutoffs),identical(scenarios$cutoffs,cutoffs),
    objective %in% c('any_hit','at_least_two','expected_net','row_coverage','random'),
    is.finite(budget_cny),budget_cny>=0,budget_cny%%2==0,
    is.finite(minimum_roi),minimum_roi>=-1,minimum_hit>=0,minimum_hit<=1,
    length(spend_all)==1,is.logical(spend_all),!is.na(spend_all),nodes>=1,nodes==floor(nodes),
    gap>=0,gap<1,seed>=0,seed==floor(seed),is.finite(time_seconds),time_seconds>0)
  k <- length(pool$options);w <- nrow(scenarios$hits)
  stopifnot(k>0,w>0,ncol(scenarios$hits)==k,all(scenarios$hits %in% 0:1))
  stake <- vapply(pool$options,function(o)o$stake,numeric(1))
  gross <- vapply(pool$options,function(o)o$expected_gross,numeric(1))
  groups <- vapply(pool$options,function(o)o$sleeve_id,numeric(1))
  prefix <- outer(unique(groups),groups,`==`)*1
  # Binary indicators are necessary for >=2: continuous values would reward a
  # single hit by0.5. Separate any-hit indicators enforce minimum_hit for all objectives.
  use_two <- objective=='at_least_two';nvars <- k+w+if(use_two)w else 0
  fixed <- rbind(prefix,stake,gross-(1+minimum_roi)*stake)
  A <- cbind(Matrix::Matrix(fixed,sparse=TRUE),Matrix::Matrix(0,nrow(fixed),nvars-k))
  lo <- c(rep(-Inf,nrow(prefix)),if(spend_all)budget_cny else 0,0)
  hi <- c(rep(1,nrow(prefix)),budget_cny,Inf)
  hit <- Matrix::Matrix(scenarios$hits,sparse=TRUE)
  a <- cbind(hit,-Matrix::Diagonal(w));if(use_two)a<-cbind(a,Matrix::Matrix(0,w,w))
  A<-rbind(A,a);lo<-c(lo,rep(0,w));hi<-c(hi,rep(Inf,w))
  A<-rbind(A,Matrix::sparseMatrix(i=rep(1L,w),j=k+seq_len(w),x=1/w,dims=c(1,nvars)))
  lo<-c(lo,minimum_hit);hi<-c(hi,Inf)
  if(use_two) {
    A<-rbind(A,cbind(hit,Matrix::Matrix(0,w,w),-2*Matrix::Diagonal(w)))
    lo<-c(lo,rep(0,w));hi<-c(hi,rep(Inf,w))
  }
  L<-rep(0,nvars)
  if(objective=='any_hit')L[k+seq_len(w)]<-1/w
  if(use_two)L[k+w+seq_len(w)]<-1/w
  if(objective=='expected_net')L[seq_len(k)]<-gross-stake
  if(objective=='row_coverage')L[seq_len(k)]<-vapply(pool$options,function(o)o$coverage,numeric(1))
  if(objective=='random')L[seq_len(k)]<-withr::with_seed(seed,stats::runif(k))
  fit<-highs::highs_solve(L=L,lower=rep(0,nvars),upper=rep(1,nvars),A=A,lhs=lo,rhs=hi,
    types=rep('I',nvars),maximum=TRUE,control=highs::highs_control(mip_max_nodes=as.integer(nodes),
      mip_rel_gap=gap,mip_feasibility_tolerance=1e-9,primal_feasibility_tolerance=1e-9,
      threads=1L,time_limit=as.double(time_seconds),random_seed=as.integer(seed),log_to_console=FALSE))
  selected<-integer();status<-as.character(fit$status_message)
  primal<-fit$primal_solution
  if(identical(as.character(fit$info$primal_solution_status),'Feasible') &&
      length(primal)==nvars && all(is.finite(primal)) && all(abs(primal-round(primal))<1e-6)) {
    chosen<-which(primal[seq_len(k)]>.5)
    amount<-sum(stake[chosen]);nh<-rowSums(scenarios$hits[,chosen,drop=FALSE])
    valid<-!anyDuplicated(groups[chosen]) && amount<=budget_cny+1e-7 &&
      (!spend_all || abs(amount-budget_cny)<1e-7) &&
      sum(gross[chosen])>=amount*(1+minimum_roi)-1e-7 && mean(nh>=1)>=minimum_hit-1e-9
    if(valid){selected<-chosen;status<-if(status=='Optimal')'OPTIMAL_WITHIN_TOLERANCE' else 'FEASIBLE_NOT_PROVEN'}
    else status<-'NUMERICAL_REJECTION'
  }
  list(selected=selected,status=status,solver=fit$info,cutoffs=cutoffs,historical_admission=FALSE)
}

# Pack a variable-depth allocation into the authoritative settlement schema.
# groups counts physical CNY2 tickets; funded_sleeves counts seven-fixture sets.
# Sorting physical fixture indices also permutes outcome columns. State IDs in
# sleeve_keys retain the ORIGINAL ordered sleeve identity (zero-based on disk).
# Exposure is stake at risk, not a count of reused sleeves. No I/O or settlement.
n7_capital_plan <- function(pool,selected,cutoffs,arm,seed,training,evaluation,
                            status,solver,budget_cny,unit_cny,payout_factor) {
  stopifnot(unit_cny==2,payout_factor==.65,budget_cny%%2==0,
    length(arm)==1L,nzchar(arm),length(seed)==1L,is.finite(seed),seed==floor(seed))
  train<-n7_capital_evaluate(pool,selected,training,cutoffs,budget_cny)
  eval<-n7_capital_evaluate(pool,selected,evaluation,cutoffs,budget_cny)
  canonical<-as.matrix(expand.grid(rep(list(0:2),7)))[,7:1,drop=FALSE]
  indices<-outcomes<-matrix(integer(),0,7)
  keys<-list(); sets<-character()
  exposure<-matrix(0,length(pool$fixtures),3)
  incidence<-matrix(0,length(pool$fixtures),length(selected))
  for(i in seq_along(selected)) {
    o<-pool$options[[selected[i]]];f<-o$fixtures;ids<-o$state_ids;k<-length(ids)
    stopifnot(length(f)==7,!anyDuplicated(f),all(f==floor(f)),
      all(f>=1 & f<=length(pool$fixtures)),k>0,k==o$depth,
      all(ids==floor(ids)),all(ids>=1 & ids<=2187),!anyDuplicated(ids),
      o$stake==unit_cny*k)
    sets<-c(sets,paste(sort(f),collapse=','))
    sort_columns<-order(f)
    indices<-rbind(indices,matrix(rep(f[sort_columns]-1L,each=k),ncol=7))
    outcomes<-rbind(outcomes,canonical[ids,sort_columns,drop=FALSE])
    incidence[f,i]<-1
    for(j in seq_along(f))exposure[f[j],]<-exposure[f[j],]+
      unit_cny*tabulate(canonical[ids,j]+1L,nbins=3)
    keys[[i]]<-list(sleeve_id=o$sleeve_id,rule=o$rule,depth=k,
      fixture_indices=as.list(f-1L),state_ids=as.list(ids-1L),
      coverage=o$coverage,stake=o$stake,expected_gross=o$expected_gross)
  }
  stopifnot(!anyDuplicated(sets),nrow(indices)*unit_cny==train$stake,
    !anyDuplicated(apply(3*indices+outcomes,1,paste,collapse=',')),
    abs(sum(exposure)-7*train$stake)<1e-8)
  overlap<-crossprod(incidence);diag(overlap)<-0
  list(issue=pool$issue,arm=arm,seed=seed,model_id=pool$model_id,
    fixtures=pool$fixtures,cutoffs=cutoffs,fixture_indices=indices,outcomes=outcomes,
    groups=nrow(indices),funded_sleeves=length(selected),sleeve_keys=keys,
    stake=train$stake,cash_cny=budget_cny-train$stake,budget_cny=budget_cny,
    unit_cny=unit_cny,payout_factor=payout_factor,solver_status=status,solver=solver,
    training=as.list(train),evaluation=as.list(eval),
    fixture_outcome_exposure_cny=exposure,fixture_exposure_cny=as.list(rowSums(exposure)),
    max_fixture_exposure_cny=max(c(0,rowSums(exposure))),
    max_outcome_exposure_cny=max(c(0,exposure)),
    max_reuse=max(c(0,rowSums(incidence))),max_overlap=max(c(0,overlap)),
    historical_admission=FALSE)
}
