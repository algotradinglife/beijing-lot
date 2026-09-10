# Explicit implementation ledger for the shared R audit and overlay report.
n67_overlay_r_receipt <- function(project_root) {
  extra <- c('r/fundamentals_n67_overlay.R','scripts/settle_fundamentals_n67_overlay.R')
  c(n7_baseline_r_receipt(project_root),stats::setNames(lapply(file.path(project_root,extra),digest::digest,algo='sha256',file=TRUE),extra))
}

# Read immutable-bound settlement; compare8 arms on common settled issues.
# NO_BET keeps cash, pending keeps unknown payoff. No fitting or side effects.
n67_overlay_report <- function(study,project_root) {
  x <- jsonlite::read_json(file.path(study,'settlement.json'),simplifyVector=TRUE)
  contract <- jsonlite::read_json(file.path(study,'contract.json'))
  stopifnot(identical(as.list(x$overlay_r_implementation),n67_overlay_r_receipt(project_root)),
    identical(x$plans_sha256,digest::digest(file=file.path(study,'plans.json'),algo='sha256')),
    identical(x$inputs_sha256,digest::digest(file=file.path(study,'inputs.json'),algo='sha256')),
    identical(x$contract_sha256,digest::digest(file=file.path(study,'contract.json'),algo='sha256')))
  y <- n7_baseline_summary(tibble::as_tibble(x$results),unlist(contract$training_issues),project_root,
                           arm_columns=c('strategy','funding'),expected_arm_count=8L)
  z <- dplyr::filter(y$per_issue,issue %in% y$common_issues$issue[y$common_issues$ready])
  z <- dplyr::bind_rows(z,dplyr::mutate(z,partition='ALL'))
  extra <- z |> dplyr::group_by(partition,strategy,funding) |>
    dplyr::summarise(any_hit_issues=sum(hits>0),n6_hits=sum(n6_hits),n7_hits=sum(n7_hits),
                     mean_model_any_hit=mean(model_any_hit),.groups='drop')
  y$summary <- dplyr::left_join(y$summary,extra,by=c('partition','strategy','funding'),relationship='one-to-one')
  y
}
