# Read frozen holdout predictions and canonical labels, then calculate diagnostic
# metrics. No learning, selection or writes. Returns row-level audit, exclusions,
# pooled Brier, per-issue Brier and three-state signal precision/coverage tibbles.
# Probabilities use units [0,1]; NA predictions are counted, never imputed.
verify_expert_refresh_report <- function(study,python) {
  if(length(python)!=1L || is.na(python) || !nzchar(python) || !file.exists(python)) stop('Explicit project Python required')
  log <- system2(python,c('scripts/verify_expert_refresh.py','--study',shQuote(study)),stdout=TRUE,stderr=TRUE)
  if(!is.null(attr(log,'status')) && attr(log,'status')!=0L) stop(paste(c('Prediction verification failed',log),collapse='\n'))
  invisible(TRUE)
}

summarize_expert_refresh <- function(study,python=Sys.getenv('FUNDAMENTALS_PYTHON'),verify_fn=verify_expert_refresh_report) {
  if(!isTRUE(verify_fn(study,python))) stop('Prediction verification failed')
  read <- function(file) jsonlite::read_json(file.path(study,file),simplifyVector=TRUE)
  contract <- read('contract.json')
  features <- tibble::as_tibble(read('test-features.json'))
  labels <- tibble::as_tibble(read('test-labels.json')$labels)
  training <- tibble::as_tibble(read('training-data.json'))
  keys <- c('issue_code','slot','provider_id')
  if(anyDuplicated(features[keys]) || anyDuplicated(labels[c('issue_code','slot')])) stop('Duplicate identities')
  if(!setequal(unique(features$issue_code),contract$test_issues)) stop('Test issue mismatch')
  rows <- features |> dplyr::left_join(labels,by=keys,relationship='one-to-one') |>
    dplyr::mutate(reason=dplyr::case_when(is.na(label_status) ~ 'MISSING_IDENTITY_LABEL',
      label_status!='COMPLETED' ~ label_status,
      provider_id %in% training$provider_id ~ 'TRAIN_TEST_GAME_OVERLAP',TRUE ~ 'ACCEPTED'),
      draw_target=as.numeric(actual_home-actual_away+handicap==0),
      high_target=as.numeric((actual_home-actual_away+handicap)*ifelse(handicap<0,1,-1)>0))
  all <- list()
  for(expert in c('draw','high')) for(version in c('old','new')) {
    p <- tibble::as_tibble(read(paste0('evaluation/',version,'_',expert,'.json'))$rows)
    if(anyDuplicated(p[keys]) || nrow(dplyr::anti_join(features,p,by=keys)) || nrow(dplyr::anti_join(p,features,by=keys))) stop('Prediction identity mismatch')
    probability <- if(expert=='draw') 'draw_target_probability' else 'high_probability'
    signal <- paste0(expert,'_signal')
    z <- rows |> dplyr::left_join(p |> dplyr::select(dplyr::all_of(c(keys,probability,signal))),by=keys,relationship='one-to-one') |>
      dplyr::transmute(issue_code,slot,provider_id,reason,expert,version,
        probability=.data[[probability]],signal=.data[[signal]],
        target=if(.env$expert=='draw') draw_target else high_target,
        baseline=if(.env$expert=='draw') baseline_draw else baseline_cover)
    if(any(!is.na(z$probability) & (!is.finite(z$probability) | z$probability<0 | z$probability>1))) stop('Invalid probability')
    all[[paste(expert,version)]] <- z
  }
  audit <- dplyr::bind_rows(all)
  paired <- audit |> dplyr::group_by(expert,issue_code,slot,provider_id) |>
    dplyr::mutate(comparable=all(reason=='ACCEPTED' & is.finite(probability) & is.finite(baseline) & is.finite(target))) |> dplyr::ungroup()
  eligible <- paired |> dplyr::filter(comparable)
  summary <- eligible |> dplyr::group_by(expert,version) |> dplyr::summarise(n=dplyr::n(),
    observed=mean(target),predicted=mean(probability),brier=mean((probability-target)^2),
    baseline_brier=mean((baseline-target)^2),.groups='drop')
  per_issue <- eligible |> dplyr::group_by(issue_code,expert,version) |> dplyr::summarise(n=dplyr::n(),
    observed=mean(target),predicted=mean(probability),brier=mean((probability-target)^2),.groups='drop')
  signals <- eligible |> dplyr::group_by(expert,version,signal) |> dplyr::summarise(n=dplyr::n(),
    event_rate=mean(target),.groups='drop') |> dplyr::group_by(expert,version) |>
    dplyr::mutate(coverage=n/sum(n),precision=dplyr::case_when(signal=='POSITIVE' ~ event_rate,
      signal=='NEGATIVE' ~ 1-event_rate,TRUE ~ NA_real_)) |> dplyr::ungroup()
  list(summary=summary,signals=signals,per_issue=per_issue,audit=paired,
    exclusions=rows |> dplyr::count(reason),availability=paired |> dplyr::count(expert,version,comparable))
}
