# Source the baseline module before use. Explicit code ledger, no side effects.
n7_selection_r_receipt <- function(project_root) {
  extra <- c('r/fundamentals_n7_selection.R','scripts/settle_fundamentals_n7_selection.R')
  c(n7_baseline_r_receipt(project_root),stats::setNames(lapply(file.path(project_root,extra),digest::digest,algo='sha256',file=TRUE),extra))
}

# Read bound settled inputs and summarize four fixed selector/grouping arms.
# No fitting, selection or DB writes. Returns per-issue and pooled risk tables.
n7_selection_report <- function(study, project_root) {
  x <- jsonlite::read_json(file.path(study,'settlement.json'),simplifyVector=TRUE)
  contract <- jsonlite::read_json(file.path(study,'contract.json'))
  stopifnot(identical(as.list(x$selection_r_implementation),n7_selection_r_receipt(project_root)),
            identical(x$plans_sha256,digest::digest(file=file.path(study,'plans.json'),algo='sha256')),
            identical(x$inputs_sha256,digest::digest(file=file.path(study,'inputs.json'),algo='sha256')),
            identical(x$contract_sha256,digest::digest(file=file.path(study,'contract.json'),algo='sha256')))
  n7_baseline_summary(tibble::as_tibble(x$results),unlist(contract$training_issues),project_root,
                      arm_columns=c('selector','grouping'),expected_arm_count=4L)
}
