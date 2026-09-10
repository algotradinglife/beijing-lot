# Convert sealed baseline experiments to a label-free score/fixture interface.
# Each row is issue/slot/provider; explicit fixture cutoffs must match exactly.
# No learning, labels or I/O. Invalid grids/identities stop; empty scopes persist.
holdout_baseline_control <- function(models,cutoffs) {
  if(!identical(names(models$experiments),names(cutoffs))) stop('Holdout issue/cutoff mismatch')
  rows <- grids <- list()
  for(issue in names(cutoffs)) {
    e <- models$experiments[[issue]]
    if(!identical(e$cutoffs,cutoffs[[issue]])) stop('Holdout fixture cutoffs differ')
    f <- dplyr::filter(e$fixtures,variant=='raw',status=='OK_DIAGNOSTIC')
    if(anyDuplicated(f$slot) || anyDuplicated(f$provider_id)) stop('Duplicate baseline identities')
    if(!nrow(f)) next
    f$issue <- issue;f$scenario <- 'baseline'
    rows[[issue]] <- dplyr::select(f,issue,slot,provider_id,home,away,handicap,scenario)
    for(i in seq_len(nrow(f))) {
      g <- e$grids[[paste(f$slot[i],'raw',sep='/')]]
      if(is.null(g) || !nrow(g) || anyNA(g) || any(!is.finite(g$probability)) || any(g$probability<0) || abs(sum(g$probability)-1)>1e-8) stop('Invalid baseline grid')
      grids[[paste(issue,f$slot[i])]] <- dplyr::mutate(g,issue=issue,slot=f$slot[i],provider_id=f$provider_id[i],scenario='baseline')
    }
  }
  if(!length(rows)) stop('No model-ready holdout fixtures')
  list(fixtures=dplyr::bind_rows(rows),scores=dplyr::bind_rows(grids),cutoffs=cutoffs)
}

# Reuse prepared Titan-primary inputs and cutoff-specific frozen experts.
# Reads declared files, verifies transitive provenance, freezes prediction JSON
# before any target label access. RDS is an internal prepared input, not output
# for users. Fixed fusion weight; no tuning. Existing output must replay exactly.
eight_holdout_predictions <- function(study,python,project_root,cutoffs,weight) {
  new <- readRDS(file.path(study,'new-inputs-internal.rds'))
  retraining_verify_provenance(new$models,project_root)
  if(!identical(new$cutoffs,cutoffs) || !identical(new$models$provenance$expert_context$expert_feature_sha256,digest::digest(new$features,algo='sha256'))) stop('Holdout prepared inputs changed')
  control <- holdout_baseline_control(new$models,cutoffs)
  market <- ev_market_probabilities(file.path(study,'market/euro.json'),file.path(study,'market/total.json'),control$fixtures,cutoffs,project_root,1e-10)
  features <- retraining_market_features(new$features,market,cutoffs)
  module <- project_python_module('src.fundamentals_retrained_experts',project_root,python,FALSE)
  temporal <- project_python_module('src.temporal_learning',project_root,python,FALSE)
  signals <- list();model_paths <- character()
  for(issue in names(cutoffs)) {
    path <- file.path(study,'models',issue,'frozen-experts.pkl');model_paths <- c(model_paths,path,sub('pkl$','json',path))
    definition <- jsonlite::read_json(sub('pkl$','json',path))
    columns <- unique(c('issue','slot','provider_id','handicap',unlist(lapply(definition$receipt,`[[`,'features'))))
    f <- dplyr::filter(features,.data$issue==.env$issue) |> dplyr::select(dplyr::all_of(columns))
    if(!nrow(f)) next
    f$issue_code <- f$issue
    epoch <- temporal$Cutoff$decision_epoch(issue,min(unlist(cutoffs[[issue]])))
    if(!identical(definition$test_issue,issue)) stop('Model target cutoff mismatch')
    for(r in definition$receipt) {
      if(!identical(r$target_issue,issue) || !identical(r$cutoff_identity,reticulate::py_to_r(epoch$identity)) || !identical(r$cutoff_ts,reticulate::py_to_r(epoch$cutoff_ts$isoformat()))) stop('Model target cutoff mismatch')
    }
    s <- module$predict_frozen_file(path,as.data.frame(f),epoch,repository_root=project_root,in_sample=FALSE)
    z <- dplyr::bind_rows(reticulate::py_to_r(s$to_dict(orient='records')));z$issue <- z$issue_code;z$issue_code <- NULL
    signals[[issue]] <- z
  }
  signals <- dplyr::bind_rows(signals)
  adjusted <- retraining_score_choices(control,signals,cutoffs,weight)
  baseline <- retraining_score_choices(control,signals,cutoffs,0)
  baseline$fixtures$scenario <- 'baseline';baseline$scores$scenario <- 'baseline'
  selected <- list(fixtures=dplyr::bind_rows(baseline$fixtures,adjusted$fixtures),scores=dplyr::bind_rows(baseline$scores,adjusted$scores),signals=signals,cutoffs=cutoffs)
  paths <- c(file.path(study,c('new-inputs-internal.rds','new-inventories.json','market/euro.json','market/total.json')),model_paths)
  rfiles <- paste0('r/',c('python_bridge','probability_exploration','fundamentals_home_away','goal_distribution_experiment','fundamentals_score_diagnostic','fundamentals_score_shape','fundamentals_high_margin','fundamentals_three_issue_experts','fundamentals_expert_coverage','fundamentals_next_issue','fundamentals_ev_returns','fundamentals_market_comparison','fundamentals_total_market','fundamentals_retraining','eight_issue_holdout'),'.R')
  snapshot <- list(selected=selected,features=features,market=market,weight=weight,
    r_hashes=as.list(stats::setNames(vapply(file.path(project_root,rfiles),digest::digest,character(1),file=TRUE,algo='sha256'),rfiles)),
    input_hashes=stats::setNames(lapply(paths,digest::digest,file=TRUE,algo='sha256'),paths),
    implementation_sha256=digest::digest(file=file.path(project_root,'r/eight_issue_holdout.R'),algo='sha256'),
    historical_admission=FALSE,target_labels_opened=FALSE)
  encoded <- as.character(jsonlite::toJSON(snapshot,auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null'))
  path <- file.path(study,'predictions.json')
  if(file.exists(path)) {
    if(!identical(readChar(path,file.info(path)$size,useBytes=TRUE),encoded)) stop('Immutable holdout predictions changed')
  } else writeChar(encoded,path,eos=NULL,useBytes=TRUE)
  list(snapshot=snapshot,snapshot_seal=digest::digest(snapshot,algo='sha256'),models=new$models,prediction_path=path,prediction_sha256=digest::digest(file=path,algo='sha256'))
}

# Only now open target roster labels and evaluate frozen selections/signals.
# Returns complete scope plus scorable summaries. No fitting or price selection.
eight_holdout_evaluation <- function(frozen,inventories,python,project_root) {
  if(!identical(frozen$prediction_sha256,digest::digest(file=frozen$prediction_path,algo='sha256'))) stop('Frozen holdout changed')
  if(!identical(frozen$snapshot_seal,digest::digest(frozen$snapshot,algo='sha256'))) stop('In-memory holdout changed')
  evaluation <- evaluate_issue_score_models(frozen$models,inventories,python,project_root)
  selected <- frozen$snapshot$selected;rows <- summaries <- list()
  for(scenario in c('baseline','retrained')) {
    choices <- dplyr::filter(selected$fixtures,.data$scenario==.env$scenario) |> dplyr::select(-handicap)
    value <- score_coverage_summary(choices,evaluation)
    rows[[scenario]] <- value$fixtures
    summaries[[scenario]] <- dplyr::mutate(value$summary,scenario=scenario,double_hit_rate=main_hits/n)
  }
  labels <- dplyr::filter(evaluation$fixtures,variant=='raw')
  z <- dplyr::inner_join(selected$signals,dplyr::select(dplyr::filter(labels,scorable),issue,slot,provider_id,handicap,actual_home,actual_away),by=c('issue','slot','provider_id'),relationship='one-to-one')
  experts <- list()
  for(expert in c('draw','high')) {
    r <- z;r$expert <- expert;net <- r$actual_home-r$actual_away+r$handicap
    r$target <- if(expert=='draw') net==0 else ifelse(r$handicap<0,1,-1)*net>0
    r$probability <- r[[paste0(expert,'_probability')]];r$signal <- r[[paste0(expert,'_signal')]]
    r$correct <- ifelse(r$signal=='POSITIVE',r$target,ifelse(r$signal=='NEGATIVE',!r$target,NA))
    experts[[expert]] <- r
  }
  expert_rows <- dplyr::bind_rows(experts)
  expert_summary <- expert_rows |> dplyr::group_by(issue,expert,signal) |> dplyr::summarise(n=dplyr::n(),hits=sum(correct,na.rm=TRUE),accuracy=if(all(is.na(correct))) NA_real_ else mean(correct,na.rm=TRUE),.groups='drop')
  list(summary=dplyr::bind_rows(summaries),fixtures=dplyr::bind_rows(rows),expert_summary=expert_summary,expert_rows=expert_rows,scope=labels,market_status=frozen$snapshot$market$status,prediction_sha256=frozen$prediction_sha256)
}
