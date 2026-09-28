# Project one approved, cutoff-bound issue into the existing score/feature
# interfaces. Input is the unsimplified JSON from prepare_clean_validation.py.
# Fixed raw cross-mean Poisson baseline, Euro+OU market, no fitting or labels.
# Returns baseline control, predictors, market grids/status and exact cutoffs.
project_clean_validation_input <- function(input, tail_tolerance) {
  issue <- input$issue
  cuts <- stats::setNames(list(input$cutoffs),issue)
  if (!identical(input$forms$context$cutoffs,cuts) || !identical(input$market$cutoffs,input$cutoffs))
    stop('Prepared issue cutoff mismatch')
  model <- home_away_probabilities(input$forms$windows,dplyr::bind_rows(input$handicaps),input$cutoffs,5L,tail_tolerance)
  experiment <- goal_distribution_experiment(model,input$cutoffs,c(.7,1.3),c(.5,.5),tail_tolerance)
  if (!any(experiment$fixtures$variant=='raw' & experiment$fixtures$status=='OK_DIAGNOSTIC')) {
    return(list(status='NO_BASELINE',control=list(fixtures=tibble::tibble(),scores=tibble::tibble(),cutoffs=cuts),
                features=tibble::tibble(),market=list(status=dplyr::bind_rows(input$market$rows),grids=list(),cutoffs=cuts),cutoffs=cuts))
  }
  control <- holdout_baseline_control(list(experiments=stats::setNames(list(experiment),issue)),cuts)
  base <- dplyr::filter(experiment$fixtures,variant=='raw',status=='OK_DIAGNOSTIC')
  base$issue <- issue
  modes <- dplyr::bind_rows(lapply(input$forms$windows,function(w) tibble::tibble(slot=w$slot,history_mode=w$history_mode)))
  base <- dplyr::left_join(base,modes,by='slot',relationship='one-to-one')
  ctx <- jsonlite::parse_json(input$forms$context$canonical_json,simplifyVector=TRUE)
  ctx$canonical_json <- input$forms$context$canonical_json;ctx$seal <- input$forms$context$seal
  features <- expert_feature_table(base,ctx,cuts)
  quote_status <- dplyr::bind_rows(input$market$rows)
  quotes <- dplyr::bind_rows(input$market$selected)
  statuses <- grids <- list()
  for (i in seq_len(nrow(control$fixtures))) {
    f <- control$fixtures[i,]
    q <- dplyr::filter(quote_status,slot==f$slot,provider_id==f$provider_id)
    if (nrow(q)!=1) stop('Unique market fixture required')
    row <- dplyr::mutate(f,status=q$status,market_residual=NA_real_,lambda_home=NA_real_,lambda_away=NA_real_)
    if (q$status=='READY') {
      selected <- dplyr::filter(quotes,slot==f$slot,provider_id==f$provider_id)
      constraint <- total_market_constraint(selected,c(.1,16))
      odds <- unlist(q[c('odds_W','odds_D','odds_L')]);target <- (1/odds)/sum(1/odds)
      projection <- total_constrained_projection(constraint$lambda_total,target,f$handicap,tail_tolerance,rho)
      row$lambda_home <- projection$fields$lambda_home;row$lambda_away <- projection$fields$lambda_away
      row$market_residual <- projection$fields$market_residual
      grids[[paste(issue,f$slot,sep='/')]] <- projection$grid
    }
    statuses[[i]] <- row
  }
  market <- list(status=dplyr::bind_rows(statuses),grids=grids,cutoffs=cuts)
  features <- retraining_market_features(features,market,cuts)
  clocks <- dplyr::bind_rows(tibble::tibble(issue=character(),slot=integer(),provider_id=character(),predictor_clock_ts=character()),lapply(input$clocks,function(r) tibble::tibble(issue=r$issue,slot=r$slot,provider_id=r$provider_id,predictor_clock_ts=r$predictor_clock_ts)))
  features <- dplyr::left_join(features,clocks,by=c('issue','slot','provider_id'),relationship='one-to-one')
  ready <- dplyr::filter(market$status,status=='READY')
  keys <- c('issue','slot','provider_id')
  control$fixtures <- dplyr::semi_join(control$fixtures,ready,by=keys)
  control$scores <- dplyr::semi_join(control$scores,ready,by=keys)
  features <- dplyr::semi_join(features,ready,by=keys)
  if (anyNA(features$predictor_clock_ts)) stop('Missing prior predictor clock')
  list(control=control,features=features,market=market,cutoffs=cuts)
}
