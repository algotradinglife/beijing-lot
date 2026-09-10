# Build full-scope retrospective features from declared accepted evidence.
# Baseline probabilities/means are FUNDAMENTALS, not market prices. No fitting.
# Requires explicit original cutoffs; returns scope, complete features and hashes.
three_issue_expert_inputs <- function(review_path,acceptance_path,context_path,cutoffs,project_root,labels_path,labels_acceptance_path) {
  review <- jsonlite::read_json(review_path,simplifyVector=TRUE)
  accepted <- jsonlite::read_json(acceptance_path,simplifyVector=TRUE)
  context <- jsonlite::read_json(context_path,simplifyVector=TRUE)
  if(!identical(context$seal,digest::digest(context$canonical_json,algo='sha256',serialize=FALSE))) stop('Context seal mismatch')
  canonical <- jsonlite::parse_json(context$canonical_json,simplifyVector=TRUE)
  if(!identical(context$rows,canonical$rows) || !identical(context$cutoffs,canonical$cutoffs)) stop('Context rows changed')
  if(!identical(context$cutoffs,cutoffs) || !identical(context$historical_admission,FALSE)) stop('Context cutoffs required')
  label_acceptance <- jsonlite::read_json(labels_acceptance_path,simplifyVector=TRUE)
  bindings <- label_acceptance$artifact_sha256
  matches <- names(bindings)[basename(names(bindings))==basename(labels_path)]
  if(length(matches)!=1 || !identical(unname(bindings[[matches]]),digest::digest(file=labels_path,algo='sha256')))
    stop('Accepted settlement artifact changed')
  accepted_labels <- jsonlite::read_json(labels_path,simplifyVector=TRUE)$evaluation$fixtures |>
    dplyr::filter(scenario=='baseline')
  r <- tibble::as_tibble(review$fixtures); c <- tibble::as_tibble(context$rows)
  keys <- c('issue','slot','provider_id')
  if(anyDuplicated(r[keys]) || anyDuplicated(c[keys]) || nrow(r)!=nrow(c) || nrow(dplyr::anti_join(r,c,by=keys))) stop('Unique full-scope identities required')
  if(anyDuplicated(accepted_labels[keys]) || nrow(accepted_labels)!=nrow(r) ||
     nrow(dplyr::anti_join(r,accepted_labels,by=keys))) stop('Accepted label identity mismatch')
  accepted_labels <- dplyr::left_join(dplyr::select(r,dplyr::all_of(keys)),accepted_labels,by=keys,relationship='one-to-one')
  for(field in c('home','away','handicap','actual_home','actual_away'))
    if(anyNA(r[[field]]) || anyNA(accepted_labels[[field]]) || any(r[[field]]!=accepted_labels[[field]]))
      stop('Accepted settlement/orientation mismatch')
  for(field in c('W','D','L','lambda_home','lambda_away'))
    if(any(!is.finite(r[[field]])) || any(abs(r[[field]]-accepted_labels[[field]])>1e-8))
      stop('Accepted baseline model mismatch')
  c <- dplyr::left_join(dplyr::select(r,dplyr::all_of(keys)),c,by=keys,relationship='one-to-one')
  if(anyNA(r$handicap) || anyNA(c$handicap) || any(r$handicap!=c$handicap) ||
     any(!r$scorable) || any(!is.finite(c(r$actual_home,r$actual_away))) ||
     any(r$actual_home<0 | r$actual_away<0 | r$actual_home%%1!=0 | r$actual_away%%1!=0)) stop('Accepted label/handicap contract')
  x <- expert_feature_table(r,context,cutoffs)
  x$draw_target <- r$actual_home-r$actual_away+r$handicap==0
  x$cover_target <- ifelse(r$handicap<0,1,-1)*(r$actual_home-r$actual_away+r$handicap)>0
  scope <- dplyr::transmute(r,issue,slot,provider_id,home,away,handicap,status='READY')
  excluded <- tibble::as_tibble(accepted$skipped) |>
    dplyr::transmute(issue,slot=as.integer(slot),provider_id=NA_character_,home,away,
                    handicap=NA_real_,status=paste0(status,':',result_state))
  scope <- dplyr::bind_rows(scope,excluded) |> dplyr::arrange(issue,slot)
  if(anyDuplicated(scope[c('issue','slot')])) stop('Duplicate scope slots')
  for(issue in names(accepted$fixture_counts)) {
    slots <- scope$slot[scope$issue==issue]
    if(!setequal(slots,seq_len(accepted$fixture_counts[[issue]]))) stop('Incomplete full scope')
  }
  list(data=x,scope=scope,receipt=list(kind='FULL_SCOPE_FUNDAMENTALS_INPUT',cutoffs=cutoffs,
    historical_admission=FALSE,context_receipt_hash=context$seal,
    source_hashes=list(review=digest::digest(file=review_path,algo='sha256'),
      acceptance=digest::digest(file=acceptance_path,algo='sha256'),
      labels=digest::digest(file=labels_path,algo='sha256'),label_acceptance=digest::digest(file=labels_acceptance_path,algo='sha256'),context=digest::digest(file=context_path,algo='sha256')),
    implementation_hashes=stats::setNames(lapply(c('r/fundamentals_three_issue_experts.R','r/fundamentals_high_margin.R'),function(p)digest::digest(file=file.path(project_root,p),algo='sha256')),c('r/fundamentals_three_issue_experts.R','r/fundamentals_high_margin.R'))))
}

# Fixed candidate shallow trees; all are descriptive same-sample comparisons.
# No deployable best model is selected. Leaves use Laplace1, signals <=low/>=high.
# Inputs must be finite numeric predictors with explicit keys, labels and cutoffs.
compare_abstaining_experts <- function(data,expert,features,target,baseline,cutoffs,owner_exception,
                                       configs,bounds=c(.2,.6),retain_fits=FALSE) {
  if(!identical(owner_exception,'SAMPLE_IN_EXPLORATION_ONLY') || is.null(cutoffs)) stop('Retrospective exception/cutoffs required')
  if(!all(c('issue','slot','provider_id',features,target,baseline) %in% names(data)) ||
     anyDuplicated(data[c('issue','slot','provider_id')])) stop('Expert data contract')
  if(any(!vapply(seq_len(nrow(data)),function(i)!is.null(cutoffs[[data$issue[i]]][[as.character(data$slot[i])]]),logical(1)))) stop('Missing fixture cutoff')
  if(!is.logical(data[[target]]) || anyNA(data[[target]]) || length(unique(data[[target]]))!=2 ||
     !all(vapply(data[features],is.numeric,logical(1))) || any(!is.finite(as.matrix(data[features]))) ||
     any(!is.finite(data[[baseline]])) || any(data[[baseline]]<0 | data[[baseline]]>1)) stop('Invalid predictor/target/probability')
  if(length(bounds)!=2 || any(!is.finite(bounds)) || bounds[1]<=0 || bounds[2]>=1 || bounds[1]>=bounds[2] ||
     !all(c('model','depth','bucket') %in% names(configs)) || anyDuplicated(configs$model) ||
     anyNA(configs) || any(configs$depth<1 | configs$depth>3 | configs$depth%%1!=0) ||
     any(configs$bucket<3 | configs$bucket%%1!=0)) stop('Invalid fixed tree policies')
  predictions <- leaves <- fits <- list()
  y <- data[[target]]
  for(i in seq_len(nrow(configs))) {
    cfg <- configs[i,]
    fit <- rpart::rpart(target~.,data=data.frame(data[features],target=factor(y,levels=c(FALSE,TRUE))),method='class',
      control=rpart::rpart.control(maxdepth=cfg$depth,minbucket=cfg$bucket,minsplit=2*cfg$bucket,cp=0,xval=0,maxsurrogate=0,usesurrogate=0))
    if(retain_fits) fits[[cfg$model]] <- fit
    nodes <- as.integer(rownames(fit$frame)[fit$where])
    l <- tibble::tibble(node=nodes,y=y) |> dplyr::group_by(node) |>
      dplyr::summarise(n=dplyr::n(),positive=sum(y),probability=(positive+1)/(n+2),.groups='drop')
    l$rule <- vapply(rpart::path.rpart(fit,nodes=l$node,print.it=FALSE),paste,collapse=' & ',FUN.VALUE=character(1))
    l$expert <- expert;l$model <- cfg$model;leaves[[i]] <- l
    p <- l$probability[match(nodes,l$node)]
    z <- dplyr::select(data,issue,slot,provider_id,home,away)
    z$expert <- expert;z$model <- cfg$model;z$node <- nodes;z$actual <- y
    z$probability <- p;z$baseline_probability <- data[[baseline]]
    z$signal <- ifelse(p<=bounds[1],'NEGATIVE',ifelse(p>=bounds[2],'POSITIVE','ABSTAIN'))
    z$correct <- ifelse(z$signal=='ABSTAIN',NA,ifelse(z$signal=='POSITIVE',y,!y))
    z$brier <- (p-y)^2;z$baseline_brier <- (data[[baseline]]-y)^2
    predictions[[i]] <- z
  }
  p <- dplyr::bind_rows(predictions)
  scopes <- dplyr::bind_rows(dplyr::mutate(p,period=issue),dplyr::mutate(p,period='ALL'))
  summary <- scopes |> dplyr::group_by(expert,model,period) |> dplyr::summarise(n=dplyr::n(),
    positives=sum(actual),emitted=sum(signal!='ABSTAIN'),hits=sum(correct,na.rm=TRUE),
    coverage=emitted/n,accuracy=if(emitted) hits/emitted else NA_real_,
    positive_signals=sum(signal=='POSITIVE'),positive_hits=sum(signal=='POSITIVE' & actual),
    negative_signals=sum(signal=='NEGATIVE'),negative_hits=sum(signal=='NEGATIVE' & !actual),
    brier=mean(brier),baseline_brier=mean(baseline_brier),.groups='drop')
  list(fits=if(retain_fits) fits else NULL,predictions=p,leaves=dplyr::bind_rows(leaves),summary=summary,
    receipt=list(expert=expert,features=features,target=target,baseline=baseline,configs=configs,bounds=bounds,
      cutoff=cutoffs,owner_exception=owner_exception,historical_admission=FALSE,deployable=FALSE,
      target_labels_used=TRUE,selected_model=NULL,rpart_version=as.character(utils::packageVersion('rpart')),
      fit_function_hash=digest::digest(body(compare_abstaining_experts),algo='sha256'),input_hash=digest::digest(data,algo='sha256')))
}

# Label-free feature projection shared by training and authorized diagnostic replay.
# Explicit cutoff-bound context; no fitting, outcomes, I/O or imputation.
expert_feature_table <- function(baseline,context,cutoffs) {
  if(!identical(context$cutoffs,cutoffs) ||
     !identical(context$seal,digest::digest(context$canonical_json,algo='sha256',serialize=FALSE))) stop('Context cutoff/seal mismatch')
  canonical <- jsonlite::parse_json(context$canonical_json,simplifyVector=TRUE)
  if(!identical(context[setdiff(names(context),c("canonical_json","seal"))],canonical)) stop('Context rows/cutoffs/source metadata changed')
  r <- tibble::as_tibble(baseline); c <- tibble::as_tibble(context$rows)
  keys <- c('issue','slot','provider_id')
  if(anyDuplicated(r[keys]) || anyDuplicated(c[keys]) || nrow(dplyr::anti_join(r,c,by=keys))) stop('Feature identity mismatch')
  c <- dplyr::left_join(dplyr::select(r,dplyr::all_of(keys)),c,by=keys,relationship='one-to-one')
  if(anyNA(c$handicap) || any(r$handicap!=c$handicap)) stop('Feature handicap mismatch')
  x <- r
  form_fields <- grep('^(home|away)_(overall|venue)_',names(c),value=TRUE)
  for(field in form_fields) x[[field]] <- c[[field]]
  x$home_team_id <- c$home_team_id;x$away_team_id <- c$away_team_id
  x$neutral <- as.numeric(r$history_mode=='ALL_VENUES')
  x$cup <- as.numeric(c$competition_category=='CUP')
  x$baseline_draw <- r$D
  x$expected_total <- r$lambda_home+r$lambda_away
  x$expected_net <- r$lambda_home-r$lambda_away
  x$draw_gap <- abs(x$expected_net+r$handicap)
  x$overall_ppg_gap <- c$home_overall_points_pg-c$away_overall_points_pg
  x$venue_ppg_gap <- c$home_venue_points_pg-c$away_venue_points_pg
  x$target_margin_frequency <- rowMeans(c[c('home_overall_exact_margin_rate','away_overall_exact_margin_rate','home_venue_exact_margin_rate','away_venue_exact_margin_rate')])
  giving_sign <- ifelse(r$handicap<0,1,-1)
  x$giving_home <- r$handicap<0
  x$giving_handicap <- -abs(r$handicap)
  x$finite_mean_total <- x$expected_total
  # Goal allocation helper is reused; h=0 orientation is unused outside high-margin scope.
  x <- high_margin_goal_structure(x)
  x$baseline_cover <- ifelse(x$giving_home,r$W,r$L)
  x$handicap_depth <- abs(r$handicap)
  x$giving_overall_ppg <- giving_sign*x$overall_ppg_gap
  x$giving_venue_ppg <- giving_sign*x$venue_ppg_gap
  ledger <- jsonlite::parse_json(context$canonical_json)$receipts
  x$giving_big_win_rate <- NA_real_
  for(i in which(x$handicap_depth>=2)) {
    entries <- Filter(function(z)z$issue==x$issue[i] && z$slot==x$slot[i] && z$provider_id==x$provider_id[i],ledger)
    if(length(entries)!=1) stop('Historical window identity mismatch')
    side <- if(x$giving_home[i]) 'home' else 'away'
    rows <- entries[[1]]$views[[paste0(side,'_venue')]]$rows
    minimal <- dplyr::bind_rows(lapply(rows,function(z)z[c('home_id','away_id','home_goals','away_goals')]))
    x$giving_big_win_rate[i] <- historical_large_margin_rate(minimal,x$handicap_depth[i],x[[paste0(side,'_team_id')]][i])
  }
  x
}
