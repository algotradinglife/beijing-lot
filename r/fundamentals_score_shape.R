# Fixed finite-grid sensitivity analysis, not a fitted or prospective model.
# P(H,A) = P(D) P(K|D), D=H-A and K=min(H,A); total=abs(D)+2*K.
# Explicit scalar factors multiply |D|>=margin_threshold mass and conditional
# odds per extra paired goal K. Each margin's conditional mass reconciles on its
# own before margins normalize. Zero support remains zero; no new goal cells.
# Input/output: unique nonnegative integer goals, probability fractions summing
# to one. Invalid/empty/nonfinite inputs stop. Pure function, no I/O or learning.
score_shape_grid <- function(grid, margin_threshold, tail_factor, pair_factor) {
  columns <- c('home_goals','away_goals','probability')
  if (!is.data.frame(grid) || !all(columns %in% names(grid)) || !nrow(grid)) stop('Nonempty score grid required')
  x <- grid[columns]
  if (!all(vapply(x,is.numeric,logical(1))) || anyNA(x) || any(!is.finite(as.matrix(x))) ||
      any(as.matrix(x)<0) || any(x$home_goals%%1!=0 | x$away_goals%%1!=0) ||
      anyDuplicated(x[c('home_goals','away_goals')]) || abs(sum(x$probability)-1)>1e-10) stop('Invalid score grid')
  for (p in list(margin_threshold,tail_factor,pair_factor)) {
    if (!is.numeric(p) || length(p)!=1L || is.na(p) || !is.finite(p) || p<=0) stop('Positive finite scalar parameters required')
  }
  if (margin_threshold%%1!=0) stop('Integer margin threshold required')
  x$net <- x$home_goals-x$away_goals
  x$paired_goals <- pmin(x$home_goals,x$away_goals)
  x$probability <- 0
  margins <- unique(x$net)
  mass <- vapply(margins,function(d)sum(grid$probability[x$net==d]),numeric(1))
  log_mass <- log(mass)+ifelse(abs(margins)>=margin_threshold,log(tail_factor),0)
  mass <- exp(log_mass-max(log_mass));mass <- mass/sum(mass)
  for (i in seq_along(margins)) {
    selected <- which(x$net==margins[i] & grid$probability>0)
    if (!length(selected)) next
    logs <- log(grid$probability[selected])+x$paired_goals[selected]*log(pair_factor)
    conditional <- exp(logs-max(logs));conditional <- conditional/sum(conditional)
    x$probability[selected] <- mass[i]*conditional
  }
  if (anyNA(x$probability) || any(!is.finite(x$probability)) || abs(sum(x$probability)-1)>1e-10) stop('Scenario mass reconciliation failed')
  tibble::as_tibble(x)
}

# Seal all scenarios before results are supplied. Explicit cutoffs must be the
# exact issue/slot bindings already validated by shared temporal_learning. This
# function does not select history, infer availability, fit, rank variants or
# cache. Scenario rows have unique names plus positive tail_factor/pair_factor;
# baseline must be (1,1). Whole model seal binds transitive input/code receipts.
# Returned grids are finite distributions; point mass outside support is zero.
# generated_at is a caller-declared UTC receipt string, never a selection clock.
prepare_score_shape_scenarios <- function(models, cutoffs, scenarios, margin_threshold,
    project_root, generated_at) {
  fields <- c('experiments','scores','coverage_choices','provenance','implementation_hashes','parameters','gates','historical_admission')
  if (!identical(models$seal,digest::digest(models[fields],algo='sha256')) ||
      !identical(models$historical_admission,FALSE)) stop('Sealed diagnostic models required')
  expected <- lapply(models$experiments,`[[`,'cutoffs')
  if (!identical(cutoffs,expected)) stop('Scenario cutoff binding mismatch')
  if (!is.data.frame(scenarios) || !all(c('scenario','tail_factor','pair_factor') %in% names(scenarios)) ||
      !nrow(scenarios) || !is.character(scenarios$scenario) || anyNA(scenarios) ||
      any(!nzchar(scenarios$scenario)) || anyDuplicated(scenarios$scenario) ||
      sum(scenarios$scenario=='baseline')!=1L) stop('Unique scenarios including baseline required')
  baseline <- scenarios[scenarios$scenario=='baseline',]
  if (baseline$tail_factor!=1 || baseline$pair_factor!=1) stop('Baseline factors must be one')
  # Validate parameters even when every fixture is excluded.
  for (i in seq_len(nrow(scenarios))) score_shape_grid(tibble::tibble(home_goals=0,away_goals=0,probability=1),
    margin_threshold,scenarios$tail_factor[i],scenarios$pair_factor[i])
  if (!is.character(generated_at) || length(generated_at)!=1L || is.na(generated_at) ||
      !grepl('^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$',generated_at) ||
      is.na(as.POSIXct(generated_at,format='%Y-%m-%dT%H:%M:%SZ',tz='UTC'))) stop('UTC generation timestamp required')
  source_files <- names(models$implementation_hashes)
  for (file in source_files) if (!identical(unname(models$implementation_hashes[[file]]),
      digest::digest(file=file.path(project_root,file),algo='sha256'))) stop('Source implementation changed')
  grids <- list(); fixtures <- list(); choices <- list()
  for (issue in names(models$experiments)) {
    e <- models$experiments[[issue]]
    raw <- dplyr::filter(e$fixtures,variant=='raw',status=='OK_DIAGNOSTIC')
    for (j in seq_len(nrow(scenarios))) {
      s <- scenarios[j,]; f <- raw; scenario_grids <- list()
      for (column in c('boundary_mass','finite_mean_total','finite_mean_net','ordinary_W','ordinary_D','ordinary_L',
          'home_ge2','home_ge3','home_ge4','away_ge2','away_ge3','away_ge4','total_ge5','total_ge6')) f[[column]] <- numeric(nrow(f))
      for (i in seq_len(nrow(f))) {
        key <- paste(f$slot[i],'raw',sep='/')
        g <- score_shape_grid(e$grids[[key]],margin_threshold,s$tail_factor,s$pair_factor)
        net <- g$net;total <- g$home_goals+g$away_goals
        g$outcome <- ifelse(net+f$handicap[i]>0,'W',ifelse(net+f$handicap[i]==0,'D','L'))
        for (d in c('W','D','L')) f[[d]][i] <- sum(g$probability[g$outcome==d])
        for (k in 2:4) {
          f[[paste0('home_ge',k)]][i] <- sum(g$probability[net>=k])
          f[[paste0('away_ge',k)]][i] <- sum(g$probability[net<= -k])
        }
        for (k in 5:6) f[[paste0('total_ge',k)]][i] <- sum(g$probability[total>=k])
        f$ordinary_W[i] <- sum(g$probability[net>0]);f$ordinary_D[i] <- sum(g$probability[net==0]);f$ordinary_L[i] <- sum(g$probability[net<0])
        f$lambda_home[i] <- sum(g$home_goals*g$probability);f$lambda_away[i] <- sum(g$away_goals*g$probability)
        f$finite_mean_total[i] <- sum(total*g$probability);f$finite_mean_net[i] <- sum(net*g$probability)
        f$boundary_mass[i] <- sum(g$probability[g$home_goals==max(g$home_goals) | g$away_goals==max(g$away_goals)])
        grids[[paste(issue,f$slot[i],s$scenario,sep='/')]] <- g
        scenario_grids[[key]] <- g
      }
      # Reuse authoritative W/D/L and protection tie rules. All five rules are
      # generated upstream of outcomes; evaluation below reports double_protect1.
      choice_input <- stats::setNames(list(list(fixtures=f,grids=scenario_grids,
        cutoffs=e$cutoffs[as.character(f$slot)])),issue)
      c <- if (nrow(f)) score_coverage_choices(choice_input) else models$coverage_choices[FALSE,]
      choices[[length(choices)+1L]] <- dplyr::mutate(c,scenario=s$scenario)
      fixtures[[length(fixtures)+1L]] <- dplyr::mutate(f,issue=issue,scenario=s$scenario,.before=1)
    }
  }
  files <- c('r/fundamentals_score_shape.R',source_files)
  hashes <- stats::setNames(vapply(file.path(project_root,files),digest::digest,character(1),file=TRUE,algo='sha256'),files)
  artifact <- list(fixtures=dplyr::bind_rows(fixtures),grids=grids,choices=dplyr::bind_rows(choices),
    receipt=list(kind='IN_SAMPLE_FIXED_SCENARIOS_NOT_FITTED',historical_admission=FALSE,
      source_model_seal=models$seal,cutoffs=cutoffs,scenarios=scenarios,margin_threshold=margin_threshold,
      input_provenance=models$provenance,implementation_hashes=as.list(hashes),generated_at=generated_at,
      support='SOURCE_FINITE_GRID_RENORMALIZED; OUTSIDE_SUPPORT_ZERO',
      original_tail_tolerance=models$parameters$tail_tolerance))
  c(artifact,list(seal=digest::digest(artifact,algo='sha256')))
}

# Evaluate every supplied fixed scenario, never select a winning scenario.
# Actual D is used only for conditional diagnostic evaluation, never prediction.
# NLL decomposes exactly into margin NLL + score-given-margin NLL on finite
# support. All observed scores must be inside positive baseline support; fail
# closed otherwise instead of hiding out-of-grid losses. Returns tidy fixture,
# per-issue, tail, conditional, gains/losses and changed-case tables. No I/O.
evaluate_score_shape_scenarios <- function(scenarios, evaluation) {
  if (!identical(scenarios$seal,digest::digest(scenarios[c('fixtures','grids','choices','receipt')],algo='sha256')) ||
      !identical(scenarios$receipt$source_model_seal,evaluation$seal)) stop('Matching sealed scenarios/evaluation required')
  labels <- dplyr::filter(evaluation$fixtures,variant=='raw',scorable)
  keys <- c('issue','slot','provider_id')
  if (anyDuplicated(labels[keys])) stop('Duplicate result identity')
  expected <- dplyr::distinct(scenarios$fixtures,issue,slot,provider_id)
  if (!setequal(paste(labels$issue,labels$slot,labels$provider_id),paste(expected$issue,expected$slot,expected$provider_id))) stop('Result identity/cardinality mismatch')
  goals <- c(labels$actual_home,labels$actual_away)
  if (anyNA(goals) || any(!is.finite(goals)) || any(goals<0 | goals%%1!=0)) stop('Valid paired observed goals required')
  rows <- dplyr::left_join(scenarios$fixtures,dplyr::select(labels,issue,slot,provider_id,actual_home,actual_away),
    by=keys,relationship='many-to-one')
  rows$actual_net <- rows$actual_home-rows$actual_away;rows$actual_total <- rows$actual_home+rows$actual_away
  rows$score_probability <- rows$margin_probability <- rows$conditional_probability <- rows$conditional_mean_total <- double(nrow(rows))
  rows$top5_hit <- logical(nrow(rows))
  for (i in seq_len(nrow(rows))) {
    r <- rows[i,];g <- scenarios$grids[[paste(r$issue,r$slot,r$scenario,sep='/')]]
    p <- g$probability[g$home_goals==r$actual_home & g$away_goals==r$actual_away]
    if (length(p)!=1L || p<=0) stop('Observed score outside positive scenario support')
    same <- g$net==r$actual_net;mass <- sum(g$probability[same])
    rows$score_probability[i] <- p;rows$margin_probability[i] <- mass
    rows$conditional_probability[i] <- p/mass
    rows$conditional_mean_total[i] <- sum((g$home_goals[same]+g$away_goals[same])*g$probability[same])/mass
    top <- utils::head(dplyr::arrange(g,dplyr::desc(probability),home_goals+away_goals,home_goals),5)
    rows$top5_hit[i] <- any(top$home_goals==r$actual_home & top$away_goals==r$actual_away)
  }
  rows$score_nll <- -log(rows$score_probability);rows$margin_nll <- -log(rows$margin_probability)
  rows$conditional_nll <- -log(rows$conditional_probability)
  rows$draw_brier <- (rows$D-(rows$actual_net+rows$handicap==0))^2
  rows$bigwin_brier <- ((rows$home_ge3-(rows$actual_net>=3))^2+(rows$away_ge3-(rows$actual_net<= -3))^2)/2
  if (any(abs(rows$score_nll-rows$margin_nll-rows$conditional_nll)>1e-10)) stop('Likelihood decomposition failed')
  coverage <- list()
  for (name in scenarios$receipt$scenarios$scenario) {
    cov <- score_coverage_summary(dplyr::filter(scenarios$choices,scenario==name),evaluation)
    coverage[[name]] <- dplyr::select(dplyr::filter(cov$fixtures,rule=='double_protect1'),
      issue,slot,provider_id,scenario,selected,protect_home,protect_away,main_hit,protect_hit,covered,model_coverage)
  }
  rows <- dplyr::left_join(rows,dplyr::bind_rows(coverage),by=c(keys,'scenario'),relationship='one-to-one')
  if (anyNA(rows$covered)) stop('Missing scenario choices')
  base <- dplyr::transmute(dplyr::filter(rows,scenario=='baseline'),issue,slot,provider_id,
    baseline_covered=covered,baseline_selected=selected,baseline_protect_home=protect_home,
    baseline_protect_away=protect_away,baseline_score_nll=score_nll)
  rows <- dplyr::left_join(rows,base,by=keys,relationship='many-to-one')
  rows$gained <- !rows$baseline_covered & rows$covered;rows$lost <- rows$baseline_covered & !rows$covered
  rows$score_nll_change <- rows$score_nll-rows$baseline_score_nll
  summary <- dplyr::summarise(dplyr::group_by(rows,issue,scenario),n=dplyr::n(),
    mean_score_nll=mean(score_nll),mean_margin_nll=mean(margin_nll),mean_conditional_nll=mean(conditional_nll),
    draw_brier=mean(draw_brier),bigwin_brier=mean(bigwin_brier),top5_hits=sum(top5_hit),
    main_hits=sum(main_hit),protection_adds=sum(protect_hit),covered_count=sum(covered),coverage=mean(covered),
    gains=sum(gained),losses=sum(lost),mean_total=mean(finite_mean_total),actual_total=mean(actual_total),
    maximum_boundary_mass=if(dplyr::n()) max(boundary_mass) else NA_real_,.groups='drop')
  tails <- list()
  for (threshold in c(3L,4L)) for (side in c('home','away')) {
    t <- rows
    t$predicted <- t[[paste0(side,'_ge',threshold)]]
    t$observed <- if(side=='home') t$actual_net>=threshold else t$actual_net<= -threshold
    tails[[length(tails)+1L]] <- dplyr::mutate(dplyr::summarise(dplyr::group_by(t,issue,scenario),
      n=dplyr::n(),predicted_count=sum(predicted),observed_count=sum(observed),
      brier=mean((predicted-observed)^2),.groups='drop'),side=side,threshold=threshold)
  }
  conditional <- dplyr::summarise(dplyr::group_by(rows,issue,scenario,actual_net),n=dplyr::n(),
    observed_mean_total=mean(actual_total),predicted_conditional_total=mean(conditional_mean_total),
    mean_conditional_nll=mean(conditional_nll),.groups='drop')
  list(fixtures=rows,summary=summary,tails=dplyr::bind_rows(tails),conditional=conditional,
    changes=dplyr::filter(rows,gained | lost),baseline_misses=dplyr::filter(rows,!baseline_covered),
    receipt=list(scenario_seal=scenarios$seal,source_model_seal=evaluation$seal,
      evaluated_labels_sha256=digest::digest(dplyr::select(labels,dplyr::all_of(keys),actual_home,actual_away),algo='sha256'),
      historical_admission=FALSE,kind='IN_SAMPLE_DIAGNOSTIC_NO_WINNER_SELECTED'))
}
