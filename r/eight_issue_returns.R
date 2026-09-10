# Historical settlement of frozen test choices. Completed-sample eligibility is
# explicit retrospective filtering; labels/SP never train the experts. Inputs:
# immutable predictions/evaluation, cutoff map, read-only settlement DB, output
# directory and fixed business constants. Outputs include source receipts,
# immutable plans, audit, original main cash and three fixed-budget score arms.
eight_holdout_returns <- function(prediction_path,comparison_path,db_path,output_dir,cutoffs,python,project_root,n,group_cap,unit_cny,score_budget,payout_factor) {
  if(n!=7 || group_cap!=6 || unit_cny!=2 || score_budget!=256 || payout_factor!=.65) stop('Explicit fixed portfolio constants required')
  frozen <- jsonlite::read_json(prediction_path,simplifyVector=TRUE)
  observed <- jsonlite::read_json(comparison_path,simplifyVector=TRUE)
  if(!identical(frozen$selected$cutoffs,cutoffs) || !identical(observed$prediction_sha256,digest::digest(file=prediction_path,algo='sha256'))) stop('Holdout settlement prediction/cutoff mismatch')
  accepted <- dplyr::filter(observed$fixtures,scenario=='baseline') |> dplyr::select(issue,slot,provider_id,home,away,handicap,actual_home,actual_away)
  control <- frozen$selected
  control$fixtures <- dplyr::semi_join(control$fixtures,accepted,by=c('issue','slot','provider_id'))
  factors <- ev_candidate_factors(control,frozen$market,python,project_root)
  scopes <- dplyr::distinct(control$fixtures,issue,scenario)
  if(!nrow(factors)) {
    result <- list(pending_settlement=tibble::tibble(issue=character(),slot=integer(),provider_id=character(),status=character()),comparison=dplyr::transmute(scopes,issue,model=scenario,selection='coverage',status='NO_MARKET_CANDIDATES',actual_groups=0L,stake=0,main_gross=0,net=0),score_scenarios=tibble::tibble(),score_ledger=tibble::tibble(),groups=tibble::tibble(),legs=tibble::tibble(),historical_admission=FALSE,prediction_sha256=observed$prediction_sha256,cutoffs=cutoffs,input_hashes=list(predictions=digest::digest(file=prediction_path,algo='sha256'),comparison=digest::digest(file=comparison_path,algo='sha256')),implementation_sha256=digest::digest(file=file.path(project_root,'r/eight_issue_returns.R'),algo='sha256'))
    dir.create(output_dir,recursive=TRUE,showWarnings=FALSE)
    jsonlite::write_json(result,file.path(output_dir,'comparison.json'),auto_unbox=TRUE,dataframe='rows',digits=15)
    return(result)
  }
  provenance <- project_python_module('src.temporal_learning.provenance',project_root,python,FALSE)
  closure <- reticulate::py_to_r(provenance$implementation_closure(reticulate::import('pathlib',convert=FALSE)$Path(project_root),c('src.fundamentals_disjoint_portfolios','src.nowscore_settlement')))
  rfiles <- c('r/python_bridge.R','r/nowscore_query.R','r/fundamentals_returns.R','r/fundamentals_ev_returns.R','r/fundamentals_selection_comparison.R','r/fundamentals_direct_score_returns.R','r/eight_issue_returns.R')
  rhashes <- as.list(stats::setNames(vapply(file.path(project_root,rfiles),digest::digest,character(1),file=TRUE,algo='sha256'),rfiles))
  source <- list(factors=factors,summary=scopes,cutoffs=cutoffs,implementation=list(python=closure,r=rhashes),input_hashes=list(predictions=digest::digest(file=prediction_path,algo='sha256'),completed_sample=digest::digest(file=comparison_path,algo='sha256')),owner_exception='OWNER_AUTHORIZED_HISTORICAL_RETURNS',historical_admission=FALSE)
  dir.create(output_dir,recursive=TRUE,showWarnings=FALSE)
  path <- file.path(output_dir,'candidates.json');encoded <- as.character(jsonlite::toJSON(source,auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null'))
  if(file.exists(path)) {
    if(!identical(readChar(path,file.info(path)$size,useBytes=TRUE),encoded)) stop('Immutable holdout candidate changed')
  } else writeChar(encoded,path,eos=NULL,useBytes=TRUE)
  plans <- selection_comparison_plans(path,cutoffs,python,project_root,file.path(output_dir,'plans.json'),n,group_cap,unit_cny,2^n*unit_cny*group_cap+score_budget,payout_factor,'OWNER_AUTHORIZED_HISTORICAL_RETURNS',methods='coverage',group_policy='cap')
  # Score singles too are fixed before reading final payout prices.
  legs <- dplyr::bind_rows(lapply(plans$plans[grepl('/retrained/coverage$',names(plans$plans))],`[[`,'legs'))
  direct <- if(nrow(legs)) direct_score_plan(legs,dplyr::filter(control$scores,scenario=='retrained'),cutoffs,unit_cny,score_budget) else NULL
  if(!is.null(direct)) jsonlite::write_json(direct,file.path(output_dir,'score-plan.json'),auto_unbox=TRUE,dataframe='rows',digits=15)
  audit <- fundamentals_settlement_audit(db_path,accepted,python,project_root)
  jsonlite::write_json(audit,file.path(output_dir,'audit.json'),auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null')
  # Keep original plans immutable. An incomplete issue retains its planned stake
  # and unknown cash; it is never replaced or counted as a zero-return issue.
  pending <- audit$fixtures |> dplyr::filter(is.na(status) | status!='READY') |>
    dplyr::select(issue,slot,provider_id,status)
  complete <- plans
  complete$plans <- complete$plans[!vapply(complete$plans,function(p) any(p$legs$issue %in% pending$issue),logical(1))]
  complete$summary <- dplyr::filter(complete$summary,!issue %in% pending$issue)
  settled <- settle_selection_comparison(complete,audit$fixtures,python,project_root)
  comparison <- dplyr::left_join(plans$summary,settled$summary,by=c('issue','model','selection'),relationship='one-to-one')
  comparison$settlement_status <- ifelse(comparison$issue %in% pending$issue,'PENDING_AUDIT','COMPLETE')
  if('planned_stake' %in% names(comparison)) comparison$stake[comparison$settlement_status=='PENDING_AUDIT'] <- comparison$planned_stake[comparison$settlement_status=='PENDING_AUDIT']
  if(!is.null(direct)) {
    direct$ledger <- dplyr::filter(direct$ledger,!issue %in% pending$issue)
    direct$parent_plan_seal <- direct$seal
    direct$seal <- digest::digest(direct[setdiff(names(direct),'seal')],algo='sha256')
  }
  singles <- if(!is.null(direct) && nrow(direct$ledger)) settle_direct_scores(direct,audit$fixtures,dplyr::filter(comparison,model=='retrained',selection=='coverage',status=='PLANNED',settlement_status=='COMPLETE'),payout_factor,python,project_root) else list(rows=tibble::tibble(),ledger=tibble::tibble())
  result <- list(pending_settlement=pending,comparison=comparison,score_scenarios=singles$rows,score_ledger=singles$ledger,groups=settled$groups,legs=settled$legs,prediction_sha256=plans$prediction_sha256,audit_sha256=digest::digest(file=file.path(output_dir,'audit.json'),algo='sha256'),historical_admission=FALSE)
  jsonlite::write_json(result,file.path(output_dir,'comparison.json'),auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null')
  result
}
