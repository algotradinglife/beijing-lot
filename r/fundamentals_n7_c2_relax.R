# Summarize fixed-policy budget use and additions; no fitting or I/O.
# Input: one row per partition/issue/policy, nonmissing numeric CNY amounts,
# integer group/hit/fixture counts. Empty, duplicate or inconsistent rows fail.
# Output: one row per partition/policy with additive budget, cash, additions,
# counts of issues with cash/hits/full losses, and issue-local fixture totals.
n7_relaxation_totals <- function(results) {
  keys <- c('partition','issue','policy')
  amounts <- c('budget_cny','cash_cny','added_stake','added_net','stake')
  counts <- c('added_groups','added_hits','hits','unique_fixtures')
  required <- c(keys,amounts,counts)
  stopifnot(all(required %in% names(results)),nrow(results)>0,
    !anyDuplicated(results[keys]),!anyNA(results[required]),
    all(vapply(results[c(amounts,counts)],is.numeric,logical(1))),
    all(is.finite(as.matrix(results[c(amounts,counts)]))),
    all(results$budget_cny>=0),all(results$stake>=0),all(results$cash_cny>=0),
    all(results$added_stake>=0),all(results$added_stake<=results$stake),
    all(as.matrix(results[counts])>=0),
    all(as.matrix(results[counts])==floor(as.matrix(results[counts]))),
    all(abs(results$stake+results$cash_cny-results$budget_cny)<1e-7),
    all(results$added_stake==64*results$added_groups))
  results |> dplyr::group_by(partition,policy) |>
    dplyr::summarise(cash_issues=sum(cash_cny>0),any_hit_issues=sum(hits>0),
      full_loss_issues=sum(stake>0 & hits==0),
      budget_cny=sum(budget_cny),cash_cny=sum(cash_cny),added_stake=sum(added_stake),
      added_net=sum(added_net),added_groups=sum(added_groups),added_hits=sum(added_hits),
      unique_fixtures=sum(unique_fixtures),.groups='drop')
}
