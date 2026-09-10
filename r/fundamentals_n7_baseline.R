# Explicit R implementation ledger for settlement, summaries and their entry point.
# Returns named SHA256 hashes; missing files fail. No writes or hidden root.
n7_baseline_r_receipt <- function(project_root) {
  paths <- c('r/fundamentals_n7_baseline.R','r/fundamentals_returns.R',
             'r/nowscore_query.R','r/python_bridge.R','scripts/settle_fundamentals_n7_baseline.R')
  stats::setNames(lapply(file.path(project_root,paths),digest::digest,algo='sha256',file=TRUE),paths)
}

# Read immutable plans, query authoritative R/SQLite settlement, and settle SPF.
# output_dir holds inputs/plans/contract JSON; db_path is read-only. Returns
# result and audit tables plus file hashes, without writing or fitting anything.
settle_n7_baseline_study <- function(output_dir, db_path, python, project_root,
                                       settlement_module='src.fundamentals_n7_baseline',
                                       settlement_function='settle_n7_baseline') {
  r_implementation <- n7_baseline_r_receipt(project_root)
  inputs <- jsonlite::read_json(file.path(output_dir,'inputs.json'),simplifyVector=TRUE)
  contract <- jsonlite::read_json(file.path(output_dir,'contract.json'))
  stopifnot(identical(contract$settlement_opened,FALSE),identical(inputs$historical_admission,FALSE))
  for(p in names(inputs$source_hashes)) if(!identical(inputs$source_hashes[[p]],digest::digest(file=p,algo='sha256'))) stop('Archived input changed')
  for(p in names(inputs$implementation$files)) if(!identical(inputs$implementation$files[[p]],digest::digest(file=file.path(project_root,p),algo='sha256'))) stop('Implementation changed')
  module <- project_python_module(settlement_module,project_root,python,FALSE)
  settle <- reticulate::py_get_attr(module,settlement_function)
  py_json <- reticulate::import('json',convert=FALSE)
  text <- paste(readLines(file.path(output_dir,'plans.json'),warn=FALSE),collapse='\n')
  plans <- py_json$loads(text)
  audit <- fundamentals_settlement_audit(db_path,tibble::as_tibble(inputs$labels),python,project_root)
  accepted <- as.data.frame(audit$fixtures)
  rows <- list()
  for(i in seq_len(reticulate::py_len(plans))) {
    plan <- plans$`__getitem__`(as.integer(i-1L))
    row <- reticulate::py_to_r(settle(plan,accepted))
    for(k in intersect(c('gross','net','roi','hits','ideal_gross','expected_roi','n6_hits','n7_hits'),names(row))) if(is.null(row[[k]])) row[k] <- list(NA_real_)
    row$issue_anchor_ts <- min(unlist(inputs$cutoffs[[row$issue]]))
    rows[[i]] <- tibble::as_tibble(row)
  }
  stopifnot(identical(r_implementation,n7_baseline_r_receipt(project_root)))
  list(r_implementation=r_implementation,results=dplyr::bind_rows(rows),audit=audit$fixtures,query_receipt=audit$receipt,
    plans_sha256=digest::digest(file=file.path(output_dir,'plans.json'),algo='sha256'),
    inputs_sha256=digest::digest(file=file.path(output_dir,'inputs.json'),algo='sha256'))
}

# Descriptive same-issue ROI and risk from settled plans; no policy selection.
# A pending arm excludes that issue from COMMON summaries, never sets PnL zero.
# Returned per-issue table retains all stakes and missing payouts. Drawdown is
# CNY from cumulative PnL including time zero, not an assumed funded bankroll.
n7_baseline_summary <- function(results, training_issues, project_root,
                                arm_columns=c('selector','shape','funding'),expected_arm_count=12L) {
  r_implementation <- n7_baseline_r_receipt(project_root)
  keys <- c('issue',arm_columns)
  if(anyDuplicated(results[keys]) || !nrow(results) || anyNA(results$stake)) stop('Unique complete plan keys required')
  counts <- dplyr::count(results,issue)
  if(any(counts$n!=expected_arm_count)) stop(paste('All',expected_arm_count,'frozen arms required for every issue'))
  arms <- unique(results[arm_columns])
  if(nrow(arms)!=expected_arm_count) stop('Common arm identities required')
  results$partition <- ifelse(results$issue %in% training_issues,'EARLIER32','LATER16')
  common <- results |> dplyr::group_by(issue) |> dplyr::summarise(ready=all(status %in% c('COMPLETE','NO_BET')),.groups='drop')
  x <- results |> dplyr::filter(issue %in% common$issue[common$ready])
  x <- dplyr::bind_rows(x,dplyr::mutate(x,partition='ALL'))
  rows <- list()
  for(g in dplyr::group_split(dplyr::group_by(x,dplyr::across(dplyr::all_of(c('partition',arm_columns)))))) {
    g <- g[order(as.POSIXct(g$issue_anchor_ts,tz='UTC'),g$issue),]
    if(anyNA(g[c('gross','net','hits','ideal_gross')])) stop('Completed results require finite payouts')
    equity <- c(0,cumsum(g$net));loss <- rle(g$net<=0)
    row <- g[1,c('partition',arm_columns)]
    row$issues <- nrow(g);row$stake <- sum(g$stake);row$gross <- sum(g$gross);row$net <- sum(g$net)
    row$roi <- if(row$stake>0) row$net/row$stake else NA_real_
    row$group_hits <- sum(g$hits);row$groups <- sum(g$groups);row$profitable_issues <- sum(g$net>0)
    row$max_drawdown_cny <- max(cummax(equity)-equity)
    row$longest_nonprofitable_run <- max(c(0L,loss$lengths[loss$values]))
    best <- which.max(g$gross);row$ex_largest_payout_net <- sum(g$net[-best])
    row$ideal_equal_net <- sum(g$ideal_gross)-row$stake
    rows[[length(rows)+1L]] <- row
  }
  prototype <- results[0,c('partition',arm_columns)]
  for(k in c('issues','stake','gross','net','roi','group_hits','groups','profitable_issues',
             'max_drawdown_cny','longest_nonprofitable_run','ex_largest_payout_net','ideal_equal_net')) prototype[[k]] <- numeric()
  stopifnot(identical(r_implementation,n7_baseline_r_receipt(project_root)))
  list(per_issue=results,summary=dplyr::bind_rows(prototype,dplyr::bind_rows(rows)),
       common_issues=common,r_implementation=r_implementation)
}
