# Freeze precisely the two already nominated trees. Training is limited to the
# inventoried old issues; cutoff is a target-issue map, not availability evidence.
# Authorized exception is diagnostic only. No target outcomes, writes or tuning.
freeze_diagnostic_experts <- function(evidence_path,target_issue,cutoffs,owner_exception) {
  if(!identical(owner_exception,'FROZEN_NEW_ISSUE_DIAGNOSTIC') ||
     !is.character(target_issue) || length(target_issue)!=1 || !length(cutoffs)) stop('Explicit diagnostic exception/target cutoff required')
  e <- jsonlite::read_json(evidence_path,simplifyVector=TRUE)
  x <- tibble::as_tibble(e$inputs$data)
  if(target_issue %in% x$issue || !setequal(unique(x$issue),c('100101','100102','100103'))) stop('Training/target issue separation')
  models <- list()
  for(name in c('draw','high')) {
    old <- e$results[[name]]; receipt <- old$receipt
    model <- if(name=='draw') 'd1_b5' else 'd2_b5'
    data <- if(name=='draw') x else dplyr::filter(x,handicap_depth>=2)
    cfg <- dplyr::filter(receipt$configs, .data$model==.env$model)
    rebuilt <- compare_abstaining_experts(data,receipt$expert,unlist(receipt$features),receipt$target,
      receipt$baseline,receipt$cutoff,'SAMPLE_IN_EXPLORATION_ONLY',cfg,unlist(receipt$bounds),retain_fits=TRUE)
    expected <- dplyr::filter(old$predictions,.data$model==.env$model)
    keys <- c('issue','slot','provider_id')
    check <- dplyr::left_join(rebuilt$predictions,expected,by=keys,suffix=c('','.old'),relationship='one-to-one')
    if(nrow(check)!=nrow(expected) || anyNA(check$probability.old) ||
       any(abs(check$probability-check$probability.old)>1e-12) || any(check$node!=check$node.old)) stop('Frozen tree replay mismatch')
    fit <- rebuilt$fits[[model]]
    attr(fit$terms,".Environment") <- baseenv()
    models[[name]] <- list(fit=fit,features=unlist(receipt$features),model=model,leaves=rebuilt$leaves)
  }
  artifact <- list(models=models,receipt=list(target_issue=target_issue,cutoffs=cutoffs,
    owner_exception=owner_exception,historical_admission=FALSE,deployable=FALSE,
    evidence_class='HISTORICAL_PROXY',training_issues=sort(unique(x$issue)),
    target_labels_used=FALSE,implementation_hashes=list(
      fit=digest::digest(body(compare_abstaining_experts),algo='sha256'),
      features=digest::digest(body(expert_feature_table),algo='sha256'),
      freeze=digest::digest(body(freeze_diagnostic_experts),algo='sha256')),source_sha256=digest::digest(file=evidence_path,algo='sha256'),
    bounds=c(.2,.6),weight=.5,rpart_version=as.character(utils::packageVersion('rpart'))))
  c(artifact,list(seal=digest::digest(artifact,algo='sha256')))
}

# Predict only from the frozen rpart trees. Documented matrix prediction supplies
# class counts: class, FALSE count, TRUE count, probabilities, node probability.
# Unit weights and binary classes were fixed during training. No label argument.
# Nonfinite model features abstain explicitly; they do not remove baseline rows.
predict_diagnostic_experts <- function(frozen,features,cutoffs,owner_exception) {
  if(!identical(frozen$seal,digest::digest(frozen[c('models','receipt')],algo='sha256')) ||
     !identical(owner_exception,'FROZEN_NEW_ISSUE_DIAGNOSTIC') ||
     !identical(frozen$receipt$cutoffs,cutoffs)) stop('Frozen model/cutoff mismatch')
  keys <- c('issue','slot','provider_id')
  if(anyDuplicated(features[keys]) || any(features$issue!=frozen$receipt$target_issue) ||
     any(!as.character(features$slot) %in% names(cutoffs))) stop('Target identity mismatch')
  out <- features[keys]
  for(name in c('draw','high')) {
    m <- frozen$models[[name]]
    if(!all(m$features %in% names(features))) stop('Missing expert features')
    eligible <- if(name=='draw') rep(TRUE,nrow(features)) else abs(features$handicap)>=2
    complete <- apply(as.matrix(features[m$features]),1,function(row)all(is.finite(row)))
    ready <- eligible & complete
    p <- rep(NA_real_,nrow(features))
    if(any(ready)) {
      matrix <- stats::predict(m$fit,newdata=as.data.frame(features[ready,m$features]),type='matrix')
      if(ncol(matrix)!=6 || any(matrix[,2:3]<0)) stop('rpart binary prediction contract')
      p[ready] <- (matrix[,3]+1)/(rowSums(matrix[,2:3,drop=FALSE])+2)
    }
    out[[paste0(name,'_probability')]] <- p
    out[[paste0(name,'_signal')]] <- ifelse(!eligible,'NOT_APPLICABLE',ifelse(!complete,'INSUFFICIENT_FEATURES',
      ifelse(p<=.2,'NEGATIVE',ifelse(p>=.6,'POSITIVE','ABSTAIN'))))
  }
  out
}

# Label-free projection and selection for exactly one target issue. Missing
# expert features keep baseline. Returns both distributions and fixed choices.
next_issue_selections <- function(models,signals,cutoffs,owner_exception) {
  if(!identical(owner_exception,'FROZEN_NEW_ISSUE_DIAGNOSTIC') || length(models$experiments)!=1) stop('Single diagnostic target required')
  issue <- names(models$experiments)[1]; e <- models$experiments[[1]]
  if(!identical(e$cutoffs,cutoffs)) stop('Selection cutoff mismatch')
  f <- dplyr::filter(e$fixtures,variant=='raw',status=='OK_DIAGNOSTIC')
  keys <- c('issue','slot','provider_id');f$issue <- issue
  if(anyDuplicated(signals[keys]) || nrow(signals)!=nrow(f) || nrow(dplyr::anti_join(f,signals,by=keys))) stop('Signal identity mismatch')
  signals <- dplyr::left_join(f[keys],signals,by=keys,relationship='one-to-one')
  adjusted <- e; notes <- list()
  for(i in seq_len(nrow(f))) {
    row <- f[i,]; s <- signals[i,]; key <- paste(row$slot,'raw',sep='/')
    dp <- if(s$draw_signal %in% c('POSITIVE','NEGATIVE')) s$draw_probability else NA_real_
    hp <- if(s$high_signal %in% c('POSITIVE','NEGATIVE')) s$high_probability else NA_real_
    projected <- fuse_expert_score_grid(e$grids[[key]],row$handicap,dp,hp,.5,cutoffs[[as.character(row$slot)]],owner_exception)
    at <- which(adjusted$fixtures$slot==row$slot & adjusted$fixtures$variant=='raw')
    for(k in c('W','D','L')) adjusted$fixtures[[k]][at] <- unname(projected$probabilities[k])
    adjusted$grids[[key]] <- projected$grid
    notes[[i]] <- dplyr::mutate(s,fusion=projected$status)
  }
  choices <- dplyr::bind_rows(
    dplyr::mutate(dplyr::filter(score_coverage_choices(models$experiments),rule=='double_protect1'),scenario='baseline'),
    dplyr::mutate(dplyr::filter(score_coverage_choices(stats::setNames(list(adjusted),issue)),rule=='double_protect1'),scenario='both_half'))
  list(choices=choices,signals=dplyr::bind_rows(notes),baseline=e,adjusted=adjusted,
    cutoffs=cutoffs,owner_exception=owner_exception,historical_admission=FALSE)
}

# Reproducible QMD entry point: prepare from declared raw receipts, predict,
# seal the label-free JSON snapshot on disk, THEN read settlement for evaluation.
# Existing snapshots are immutable; inputs/features/distributions/choices must replay exactly.
# Code-only validation fixes record separate replay hashes. Output dir is
# explicit; models/context files are read only, parse cache is optional.
run_next_issue_comparison <- function(inventory_path,context_path,frozen_path,python,
                                      project_root,cache_dir,output_dir,owner_exception) {
  if(!identical(owner_exception,'FROZEN_NEW_ISSUE_DIAGNOSTIC')) stop('Diagnostic exception required')
  inv <- jsonlite::read_json(inventory_path)
  if(length(inv)!=1) stop('One target inventory required')
  frozen <- readRDS(frozen_path)
  ctx <- jsonlite::read_json(context_path,simplifyVector=TRUE)
  expected_cuts <- inv[[1]]$cutoffs[names(ctx$cutoffs[[inv[[1]]$issue]])]
  if(!identical(ctx$cutoffs[[inv[[1]]$issue]],expected_cuts)) stop('Target context cutoff mismatch')
  models <- prepare_issue_score_models(inv,python,project_root,cache_dir,10,10,5,c(.7,1.3),c(.5,.5),1e-10)
  bindings <- models$provenance[[1]]$input_file_hashes
  if(!setequal(names(bindings),names(ctx$input_file_hashes)) ||
     !identical(ctx$input_file_hashes,bindings[names(ctx$input_file_hashes)])) stop('Context/raw source binding mismatch')
  base <- dplyr::filter(models$experiments[[1]]$fixtures,variant=='raw',status=='OK_DIAGNOSTIC')
  base$issue <- inv[[1]]$issue
  metadata <- dplyr::bind_rows(models$provenance[[1]]$review_context)
  base <- dplyr::left_join(base,dplyr::select(metadata,issue,slot,provider_id,history_mode),
                         by=c('issue','slot','provider_id'),relationship='one-to-one')
  features <- expert_feature_table(base,ctx,ctx$cutoffs)
  signals <- predict_diagnostic_experts(frozen,features,inv[[1]]$cutoffs,owner_exception)
  selected <- next_issue_selections(models,signals,inv[[1]]$cutoffs,owner_exception)
  implementations <- c('r/fundamentals_next_issue.R','r/fundamentals_three_issue_experts.R',
    'r/fundamentals_high_margin.R','r/fundamentals_expert_coverage.R','r/fundamentals_score_shape.R')
  snapshot <- list(selected=selected,features=features,
    receipt=list(frozen_seal=frozen$seal,owner_exception=owner_exception,historical_admission=FALSE,
      evidence_class='HISTORICAL_PROXY',target_labels_used=FALSE,
      input_hashes=stats::setNames(lapply(c(inventory_path,context_path,frozen_path),function(p)digest::digest(file=p,algo='sha256')),c('inventory','context','frozen')),
      implementation_hashes=stats::setNames(lapply(file.path(project_root,implementations),function(p)digest::digest(file=p,algo='sha256')),implementations),
      baseline_implementation_hashes=as.list(models$implementation_hashes),
      source_provenance=models$provenance,context_seal=ctx$seal))
  encoded <- as.character(jsonlite::toJSON(snapshot,auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null'))
  dir.create(output_dir,recursive=TRUE,showWarnings=FALSE)
  path <- file.path(output_dir,'predictions.json')
  if(file.exists(path)) {
    previous <- jsonlite::parse_json(readChar(path,file.info(path)$size,useBytes=TRUE))
    current <- jsonlite::parse_json(encoded)
    if(!identical(previous$selected,current$selected) || !identical(previous$features,current$features) ||
       !identical(previous$receipt$input_hashes,current$receipt$input_hashes)) stop('Frozen predictions changed; do not overwrite')
  } else {
    writeChar(encoded,path,eos=NULL,useBytes=TRUE)
  }
  prediction_sha256 <- digest::digest(file=path,algo='sha256')
  # The first access to target settlement occurs only below this disk seal.
  evaluation <- evaluate_issue_score_models(models,inv,python,project_root)
  evaluated <- list()
  for(scenario in c('baseline','both_half')) {
    choice <- dplyr::filter(selected$choices,.data$scenario==.env$scenario)
    evaluated[[scenario]] <- score_coverage_summary(choice,evaluation)
  }
  rows <- dplyr::bind_rows(lapply(names(evaluated),function(s)dplyr::mutate(evaluated[[s]]$fixtures,scenario=s)))
  summary <- dplyr::bind_rows(lapply(names(evaluated),function(s)dplyr::mutate(evaluated[[s]]$summary,scenario=s)))
  keys <- c('issue','slot','provider_id')
  actual <- dplyr::filter(evaluation$fixtures,variant=='raw')
  rows <- dplyr::left_join(rows,dplyr::select(actual,dplyr::all_of(keys),home,away),by=keys,relationship='many-to-one')
  base_hits <- dplyr::select(dplyr::filter(rows,scenario=='baseline'),dplyr::all_of(keys),baseline_covered=covered)
  rows <- dplyr::left_join(rows,base_hits,by=keys,relationship='many-to-one')
  rows$gained <- rows$covered & !rows$baseline_covered;rows$lost <- !rows$covered & rows$baseline_covered
  expert_eval <- dplyr::inner_join(signals,dplyr::select(dplyr::filter(actual,scorable),dplyr::all_of(keys),handicap,actual_home,actual_away),by=keys,relationship='one-to-one')
  expert_summary <- list()
  for(name in c('draw','high')) {
    direction <- expert_eval$actual_home-expert_eval$actual_away+expert_eval$handicap
    positive <- if(name=='draw') direction==0 else ifelse(expert_eval$handicap<0,1,-1)*direction>0
    signal <- expert_eval[[paste0(name,'_signal')]]
    for(kind in c('POSITIVE','NEGATIVE')) {
      at <- signal==kind
      expert_summary[[length(expert_summary)+1]] <- tibble::tibble(expert=name,signal=kind,n=sum(at),hits=sum(if(kind=='POSITIVE') positive[at] else !positive[at]))
    }
  }
  if(!identical(prediction_sha256,digest::digest(file=path,algo='sha256'))) stop('Prediction snapshot mutated after settlement')
  list(summary=summary,fixtures=rows,signals=signals,expert_summary=dplyr::bind_rows(expert_summary),
    scope=dplyr::select(actual,issue,slot,provider_id,home,away,status,result_state,scorable),
    predictions=selected,features=features,
    receipt=list(prediction_sha256=prediction_sha256,frozen_seal=frozen$seal,
      owner_exception=owner_exception,historical_admission=FALSE,deployable=FALSE,
      replay_implementation_hashes=snapshot$receipt$implementation_hashes,
      replay_baseline_implementation_hashes=snapshot$receipt$baseline_implementation_hashes))
}
