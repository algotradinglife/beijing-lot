# Reuse sealed inventories and authoritative fundamentals projection. No labels
# are opened here. Returns models plus label-free expert predictors; paths and
# project interpreter are explicit. Context must bind the same raw files.
retraining_new_inputs <- function(inventory_path,context_path,python,project_root,cache_dir) {
  inv <- jsonlite::read_json(inventory_path)
  ctx <- jsonlite::read_json(context_path,simplifyVector=TRUE)
  cuts <- stats::setNames(lapply(inv,`[[`,'cutoffs'),vapply(inv,`[[`,character(1),'issue'))
  if(!identical(cuts,ctx$cutoffs)) stop('New issue context cutoffs differ')
  models <- prepare_issue_score_models(inv,python,project_root,cache_dir,10,10,5,c(.7,1.3),c(.5,.5),1e-10)
  retraining_context_inputs(models,context_path,cuts,project_root)
}

# Rebuild expert predictors from a declared sealed context and prepared score
# models, then bind both to the same provenance. Does not parse pages or labels.
retraining_context_inputs <- function(models,context_path,cuts,project_root) {
  retraining_verify_provenance(models,project_root)
  ctx <- jsonlite::read_json(context_path,simplifyVector=TRUE)
  if(!identical(cuts,ctx$cutoffs)) stop('New issue context cutoffs differ')
  baselines <- list()
  for(issue in names(models$experiments)) {
    base <- dplyr::filter(models$experiments[[issue]]$fixtures,variant=='raw',status=='OK_DIAGNOSTIC')
    base$issue <- issue
    meta <- dplyr::bind_rows(models$provenance[[issue]]$review_context)
    base <- dplyr::left_join(base,dplyr::select(meta,issue,slot,provider_id,history_mode),
                            by=c('issue','slot','provider_id'),relationship='one-to-one')
    hashes <- models$provenance[[issue]]$input_file_hashes
    if(!identical(hashes,ctx$input_file_hashes[names(hashes)])) stop('Context raw sources differ')
    baselines[[issue]] <- base
  }
  # Validate/parse the full context once for the complete identity-keyed scope.
  features <- expert_feature_table(dplyr::bind_rows(baselines),ctx,cuts)
  bindings <- ctx$input_file_hashes
  bindings[[normalizePath(context_path)]] <- digest::digest(file=context_path,algo='sha256')
  code <- ctx$implementation_hashes
  for(path in c('r/fundamentals_retraining.R','r/fundamentals_three_issue_experts.R','r/fundamentals_high_margin.R'))
    code[[path]] <- digest::digest(file=file.path(project_root,path),algo='sha256')
  models$provenance$expert_context <- list(input_file_hashes=bindings,implementation_hashes=code,
    expert_feature_sha256=digest::digest(features,algo='sha256'))
  keys <- c('experiments','scores','coverage_choices','provenance','implementation_hashes','parameters','gates','historical_admission')
  models$seal <- digest::digest(models[keys],algo='sha256')
  retraining_verify_provenance(models,project_root)
  list(models=models,features=features,cutoffs=cuts)
}

# Add actual Euro+OU inferred means and handicap masses, keeping unavailable
# markets explicit NA. No fitting or settlement fields enter the calculation.
# Returns one row per original identity with aligned numeric market predictors.
retraining_market_features <- function(features,market,cutoffs) {
  if(!identical(market$cutoffs,cutoffs)) stop('Market feature cutoff mismatch')
  keys <- c('issue','slot','provider_id')
  if(anyDuplicated(features[keys]) || anyDuplicated(market$status[keys])) stop('Duplicate market feature identities')
  fields <- c('market_home_goals','market_away_goals','market_total','market_draw',
              'market_cover','market_draw_gap','market_draw_delta','market_cover_delta')
  x <- features
  for(field in fields) x[[field]] <- NA_real_
  for(i in seq_len(nrow(x))) {
    f <- x[i,]; s <- dplyr::filter(market$status,issue==f$issue,slot==f$slot,provider_id==f$provider_id)
    if(nrow(s)!=1 || s$status!='READY') next
    g <- market$grids[[paste(f$issue,f$slot,sep='/')]]
    if(is.null(g) || abs(sum(g$probability)-1)>1e-8) stop('Missing normalized market score grid')
    x$market_home_goals[i] <- s$lambda_home;x$market_away_goals[i] <- s$lambda_away
    x$market_total[i] <- s$lambda_home+s$lambda_away
    x$market_draw[i] <- sum(g$probability[g$outcome=='D'])
    x$market_cover[i] <- sum(g$probability[g$outcome==if(f$handicap<0) 'W' else 'L'])
    x$market_draw_gap[i] <- abs(s$lambda_home-s$lambda_away+f$handicap)
    x$market_draw_delta[i] <- x$market_draw[i]-f$baseline_draw
    x$market_cover_delta[i] <- x$market_cover[i]-f$baseline_cover
  }
  x
}

# Reproject a frozen baseline and supplied expert signals, using the existing
# score fusion and double/protection selector. Explicit historical cutoffs;
# no labels, fitting, or writes. Every fixture remains in the denominator.
retraining_score_choices <- function(control,signals,cutoffs,weight) {
  if(!identical(control$cutoffs,cutoffs) || length(weight)!=1 || !is.finite(weight) || weight<0 || weight>1) stop('Explicit score policy/cutoffs required')
  keys <- c('issue','slot','provider_id')
  base <- dplyr::filter(control$fixtures,scenario=='baseline')
  if(anyDuplicated(signals[keys]) || nrow(dplyr::anti_join(base,signals,by=keys))) stop('Missing unique fixture signals')
  choices <- grids <- notes <- list()
  for(i in seq_len(nrow(base))) {
    f <- base[i,]; s <- dplyr::filter(signals,issue==f$issue,slot==f$slot,provider_id==f$provider_id)
    g <- dplyr::filter(control$scores,issue==f$issue,slot==f$slot,provider_id==f$provider_id,scenario=='baseline') |>
      dplyr::select(home_goals,away_goals,probability,outcome)
    dp <- if(s$draw_signal %in% c('POSITIVE','NEGATIVE')) s$draw_probability else NA_real_
    hp <- if(s$high_signal %in% c('POSITIVE','NEGATIVE')) s$high_probability else NA_real_
    z <- fuse_expert_score_grid(g,f$handicap,dp,hp,weight,cutoffs[[f$issue]][[as.character(f$slot)]],'FROZEN_NEW_ISSUE_DIAGNOSTIC')
    # Existing selector owns tie-breaking and the uncovered-direction score.
    fixture <- tibble::tibble(slot=f$slot,provider_id=f$provider_id,handicap=f$handicap,
      variant='raw',status='OK_DIAGNOSTIC',W=unname(z$probabilities['W']),D=unname(z$probabilities['D']),L=unname(z$probabilities['L']))
    experiment <- list(cutoffs=cutoffs[[f$issue]][as.character(f$slot)],fixtures=fixture,grids=stats::setNames(list(z$grid),paste(f$slot,'raw',sep='/')))
    choice <- dplyr::filter(score_coverage_choices(stats::setNames(list(experiment),f$issue)),rule=='double_protect1')
    choice$home <- f$home;choice$away <- f$away;choice$handicap <- f$handicap;choice$scenario <- 'retrained'
    choices[[i]] <- choice
    grids[[i]] <- dplyr::mutate(z$grid,issue=f$issue,slot=f$slot,provider_id=f$provider_id,scenario='retrained')
    notes[[i]] <- dplyr::mutate(s,fusion=z$status)
  }
  list(fixtures=dplyr::bind_rows(choices),scores=dplyr::bind_rows(grids),signals=dplyr::bind_rows(notes),cutoffs=cutoffs)
}

# End-to-end QMD analysis entry. Declared prepared artifacts and frozen sklearn
# model; regenerates immutable choices before opening new roster labels.
# Training replay is explicitly in-sample. New issues use the same frozen fit.
# Returns match-level and issue-level coverage and expert signal diagnostics.
retraining_comparison <- function(output_dir,previous_path,next_path,python,project_root,cutoffs,weight) {
  old_path <- previous_path
  training <- jsonlite::read_json(file.path(output_dir,'training.json'),simplifyVector=TRUE)
  new <- readRDS(file.path(output_dir,'new-inputs-internal.rds'))
  retraining_verify_provenance(new$models,project_root)
  if(!identical(new$models$provenance$expert_context$expert_feature_sha256,digest::digest(new$features,algo='sha256'))) stop('Prepared expert features changed')
  inv <- jsonlite::read_json(file.path(output_dir,'new-inventories.json'))
  if(!identical(new$cutoffs,cutoffs[names(new$cutoffs)])) stop('New input cutoffs differ')
  control <- ev_control_inputs(old_path,next_path,cutoffs)
  control$fixtures <- dplyr::filter(control$fixtures,scenario=='baseline')
  control$scores <- dplyr::filter(control$scores,scenario=='baseline')
  additions <- grids <- list()
  for(issue in names(new$models$experiments)) {
    e <- new$models$experiments[[issue]]
    f <- dplyr::filter(e$fixtures,variant=='raw',status=='OK_DIAGNOSTIC')
    f$issue <- issue;f$scenario <- 'baseline'
    additions[[issue]] <- dplyr::select(f,issue,slot,provider_id,home,away,handicap,scenario)
    for(i in seq_len(nrow(f))) grids[[paste(issue,f$slot[i])]] <- dplyr::mutate(e$grids[[paste(f$slot[i],'raw',sep='/')]],
      issue=issue,slot=f$slot[i],provider_id=f$provider_id[i],scenario='baseline')
  }
  control$fixtures <- dplyr::bind_rows(control$fixtures,dplyr::bind_rows(additions))
  control$scores <- dplyr::bind_rows(control$scores,dplyr::bind_rows(grids))
  market <- ev_market_probabilities(file.path(output_dir,'market/euro.json'),file.path(output_dir,'market/total.json'),control$fixtures,cutoffs,project_root,1e-10)
  new_features <- retraining_market_features(new$features,market,cutoffs)
  old_features <- training$data;old_features$issue <- old_features$issue_code
  features <- dplyr::bind_rows(old_features,new_features)
  # Only nominated predictors plus identities are passed across the model boundary.
  columns <- unique(c('issue','slot','provider_id','handicap',unlist(training$features)))
  features <- dplyr::select(features,dplyr::all_of(columns));features$issue_code <- features$issue
  module <- project_python_module('src.fundamentals_retrained_experts',project_root,python,convert=FALSE)
  temporal <- project_python_module('src.temporal_learning',project_root,python,convert=FALSE)
  signals <- list()
  for(issue in names(cutoffs)) {
    f <- dplyr::filter(features,.data$issue==.env$issue)
    epoch <- temporal$Cutoff$decision_epoch(issue,min(unlist(cutoffs[[issue]])))
    prediction <- module$predict_frozen_file(file.path(output_dir,'frozen-experts.pkl'),as.data.frame(f),epoch,
      repository_root=project_root,in_sample=issue %in% c('100101','100102','100103','100104'))
    # Explicit records avoid exposing pandas ArrowStringArray through reticulate.
    s <- dplyr::bind_rows(reticulate::py_to_r(prediction$to_dict(orient='records')))
    s$issue <- s$issue_code;s$issue_code <- NULL;signals[[issue]] <- s
  }
  signals <- dplyr::bind_rows(signals)
  adjusted <- retraining_score_choices(control,signals,cutoffs,weight)
  baseline <- retraining_score_choices(control,signals,cutoffs,0)
  baseline$fixtures$scenario <- 'baseline';baseline$scores$scenario <- 'baseline'
  selected <- list(fixtures=dplyr::bind_rows(baseline$fixtures,adjusted$fixtures),
    scores=dplyr::bind_rows(baseline$scores,adjusted$scores),signals=adjusted$signals,cutoffs=cutoffs)
  paths <- c(old_path,next_path,file.path(output_dir,c('training.json','new-inputs-internal.rds','new-inventories.json',
               'frozen-experts.pkl','frozen-experts.json','market/euro.json','market/total.json')))
  rfiles <- c('r/fundamentals_retraining.R','r/fundamentals_score_diagnostic.R','r/fundamentals_expert_coverage.R',
              'r/fundamentals_score_shape.R','r/fundamentals_ev_returns.R','r/fundamentals_total_market.R',
              'r/python_bridge.R','r/probability_exploration.R','r/fundamentals_home_away.R',
              'r/goal_distribution_experiment.R','r/fundamentals_high_margin.R',
              'r/fundamentals_three_issue_experts.R','r/fundamentals_next_issue.R',
              'r/fundamentals_market_comparison.R','scripts/prepare_retraining_inputs.R')
  snapshot <- list(selected=selected,features=features,market=market,weight=weight,
    input_hashes=stats::setNames(lapply(paths,function(p)digest::digest(file=p,algo='sha256')),paths),
    r_hashes=stats::setNames(lapply(file.path(project_root,rfiles),function(p)digest::digest(file=p,algo='sha256')),rfiles),
    evidence_class='HISTORICAL_PROXY',training_replay='IN_SAMPLE',new_labels_used=FALSE)
  encoded <- as.character(jsonlite::toJSON(snapshot,auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null'))
  path <- file.path(output_dir,'predictions.json')
  if(file.exists(path)) {
    if(!identical(readChar(path,file.info(path)$size,useBytes=TRUE),encoded)) stop('Frozen predictions changed')
  } else writeChar(encoded,path,eos=NULL,useBytes=TRUE)
  seal <- digest::digest(file=path,algo='sha256')
  # First new-target settlement access, after disk freeze above.
  evaluation <- evaluate_issue_score_models(new$models,inv,python,project_root)
  a <- jsonlite::read_json(old_path,simplifyVector=TRUE)$fixtures
  b <- jsonlite::read_json(next_path,simplifyVector=TRUE)$fixtures
  old <- dplyr::bind_rows(dplyr::filter(a,scenario=='baseline'),dplyr::filter(b,scenario=='baseline')) |>
    dplyr::select(issue,slot,provider_id,home,away,handicap,actual_home,actual_away) |>
    dplyr::mutate(variant='raw',scorable=TRUE)
  labels <- dplyr::bind_rows(old,dplyr::filter(evaluation$fixtures,variant=='raw'))
  rows <- summaries <- list()
  for(scenario in c('baseline','retrained')) {
    choices <- dplyr::filter(selected$fixtures,.data$scenario==.env$scenario) |>
      dplyr::select(-handicap)
    value <- score_coverage_summary(choices,list(fixtures=labels))
    rows[[scenario]] <- value$fixtures
    summaries[[scenario]] <- dplyr::mutate(value$summary,scenario=scenario,double_hit_rate=main_hits/n)
  }
  se <- dplyr::inner_join(signals,dplyr::select(dplyr::filter(labels,scorable),issue,slot,provider_id,handicap,actual_home,actual_away),
    by=c('issue','slot','provider_id'),relationship='one-to-one')
  expert_rows <- list()
  for(name in c('draw','high')) {
    z <- se
    direction <- z$actual_home-z$actual_away+z$handicap
    z$target <- if(name=='draw') direction==0 else ifelse(z$handicap<0,1,-1)*direction>0
    z$probability <- z[[paste0(name,'_probability')]];z$signal <- z[[paste0(name,'_signal')]]
    z$expert <- name;z$emitted <- z$signal %in% c('POSITIVE','NEGATIVE')
    z$correct <- ifelse(z$emitted,ifelse(z$signal=='POSITIVE',z$target,!z$target),NA)
    expert_rows[[name]] <- z
  }
  expert_rows <- dplyr::bind_rows(expert_rows)
  expert_summary <- expert_rows |> dplyr::group_by(issue,expert,signal) |>
    dplyr::summarise(n=dplyr::n(),hits=sum(correct,na.rm=TRUE),accuracy=if(any(emitted)) mean(correct,na.rm=TRUE) else NA_real_,.groups='drop')
  if(!identical(seal,digest::digest(file=path,algo='sha256'))) stop('Frozen choices changed after labels')
  list(summary=dplyr::bind_rows(summaries),fixtures=dplyr::bind_rows(rows),expert_summary=expert_summary,
       expert_rows=expert_rows,scope=labels,market_status=market$status,selected=selected,market=market,
       receipt=list(prediction_sha256=seal,weight=weight,historical_admission=FALSE))
}

# Verify serialized baseline plus every declared raw/preprocessing binding.
# Legacy baseline receipts name five Python modules by basename; those keys
# explicitly mean src/<basename>, matching the authoritative receipt producer.
# Reads only; returns TRUE or stops on missing/changed files or model seal.
retraining_verify_provenance <- function(models,project_root) {
  keys <- c('experiments','scores','coverage_choices','provenance','implementation_hashes','parameters','gates','historical_admission')
  if(!identical(models$seal,digest::digest(models[keys],algo='sha256'))) stop('Prepared baseline seal changed')
  groups <- list(as.list(models$implementation_hashes))
  for(p in models$provenance) {
    groups[[length(groups)+1L]] <- p$input_file_hashes
    implementations <- p$implementation_hashes
    names(implementations) <- ifelse(grepl('/',names(implementations),fixed=TRUE),names(implementations),paste0('src/',names(implementations)))
    groups[[length(groups)+1L]] <- implementations
  }
  for(group in groups) for(path in names(group)) {
    file <- if(grepl('^/',path)) path else file.path(project_root,path)
    if(!file.exists(file) || !identical(group[[path]],digest::digest(file=file,algo='sha256'))) stop(paste('Prepared source/implementation changed:',path))
  }
  TRUE
}
