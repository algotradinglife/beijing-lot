# Inputs: sealed study directory and explicit repository root; outputs tidy
# per-issue and pooled diagnostic tables. No fitting or file writes.
n7_twocover_report <- function(study, project_root) {
  x <- jsonlite::read_json(file.path(study,'settlement.json'),simplifyVector=TRUE)
  for(f in names(x$report_implementation)) stopifnot(identical(x$report_implementation[[f]],digest::digest(file=file.path(project_root,f),algo='sha256')))
  stopifnot(identical(sort(names(x$report_implementation)),sort(c('r/fundamentals_n7_twocover.R','scripts/settle_fundamentals_n7_twocover.R'))))
  contract <- jsonlite::read_json(file.path(study,'contract.json'))
  stopifnot(identical(as.list(x$r_implementation),n7_baseline_r_receipt(project_root)))
  for(n in c('plans','inputs','contract')) stopifnot(identical(x[[paste0(n,'_sha256')]],digest::digest(file=file.path(study,paste0(n,'.json')),algo='sha256')))
  y <- n7_baseline_summary(tibble::as_tibble(x$results),unlist(contract$training_issues),project_root,
                           arm_columns=c('strategy','funding'),expected_arm_count=3L)
  z <- dplyr::filter(y$per_issue,issue %in% y$common_issues$issue[y$common_issues$ready])
  z <- dplyr::bind_rows(z,dplyr::mutate(z,partition='ALL'))
  extra <- z |> dplyr::group_by(partition,strategy,funding) |>
    dplyr::summarise(any_hit_issues=sum(hits>0),worst_issue_net=if(length(net)) min(net) else NA_real_,.groups='drop')
  y$summary <- dplyr::left_join(y$summary,extra,by=c('partition','strategy','funding'),relationship='one-to-one')
  y
}
