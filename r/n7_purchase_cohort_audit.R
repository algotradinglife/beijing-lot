# Independent post-settlement cohort audit; no production accounting helpers.
# periods: one row per issue/policy, with stake/gross/net/hits/cash_cny (CNY).
# observed: reported cohort summary with evaluation ALL/ORIGINAL/ADDITIONAL.
# issue_order/original_issues and expected_policies are independently frozen IDs.
# budget_cny and initial_capital_cny are positive scalar business constants.
# Returns independently calculated summary after exact scope/accounting checks.
# No learning, I/O or side effects. Missing/duplicate/nonfinite rows fail closed;
# zero spending requires NA ROI. Cohort accounts start independently, ALL once.
n7_purchase_cohort_audit <- function(periods,observed,issue_order,original_issues,
                                     expected_policies,budget_cny,initial_capital_cny) {
 required<-c('issue','policy','stake','gross','net','hits','cash_cny')
 stopifnot(all(required %in% names(periods)),!anyNA(periods[required]),
  is.character(issue_order),length(issue_order)>0,!anyNA(issue_order),
  !anyDuplicated(issue_order),all(nzchar(issue_order)),
  is.character(original_issues),!anyNA(original_issues),!anyDuplicated(original_issues),
  all(original_issues %in% issue_order),is.character(periods$issue),
  is.character(expected_policies),length(expected_policies)>0,!anyNA(expected_policies),
  !anyDuplicated(expected_policies),all(nzchar(expected_policies)),
  setequal(periods$policy,expected_policies),
  is.numeric(budget_cny),length(budget_cny)==1,is.finite(budget_cny),budget_cny>0,
  is.numeric(initial_capital_cny),length(initial_capital_cny)==1,
  is.finite(initial_capital_cny),initial_capital_cny>0,
  !anyDuplicated(periods[c('issue','policy')]),setequal(periods$issue,issue_order),
  is.character(periods$policy),all(nzchar(periods$policy)))
 for(name in setdiff(required,c('issue','policy')))
  stopifnot(is.numeric(periods[[name]]),all(is.finite(periods[[name]])))
 stopifnot(all(periods$stake>=0 & periods$stake<=budget_cny),all(periods$gross>=0),
  all(periods$hits>=0 & periods$hits==floor(periods$hits)),
  all((periods$gross>0)==(periods$hits>0)),
  all(abs(periods$net-(periods$gross-periods$stake))<1e-6),
  all(abs(periods$cash_cny-(budget_cny-periods$stake))<1e-6))
 scopes<-list(ALL=issue_order,ORIGINAL=issue_order[issue_order %in% original_issues],
              ADDITIONAL=issue_order[!issue_order %in% original_issues])
 scopes<-scopes[lengths(scopes)>0];out<-list()
 for(policy in expected_policies) {
  p<-periods[periods$policy==policy,]
  stopifnot(nrow(p)==length(issue_order),setequal(p$issue,issue_order))
  for(evaluation in names(scopes)) {
   x<-p[match(scopes[[evaluation]],p$issue),];net<-x$gross-x$stake
   equity<-initial_capital_cny+c(0,cumsum(net));peak<-cummax(equity);dd<-peak-equity
   # Independently ensure these are affordable funded accounts, not shadow debt.
   stopifnot(all(head(equity,-1)>=x$stake))
   stake<-sum(x$stake)
   out[[length(out)+1L]]<-data.frame(evaluation=evaluation,policy=policy,
    issues=nrow(x),stake_cny=stake,net_cny=sum(net),
    roi_percent=if(stake>0)100*sum(net)/stake else NA_real_,
    hit_issues=sum(x$gross>0),profit_issues=sum(net>0),winning_groups=sum(x$hits),
    cash_cny=sum(x$cash_cny),max_drawdown_cny=max(dd),minimum_equity_cny=min(equity),
    net_without_best_cny=sum(net)-max(net),max_drawdown_percent=100*max(dd/peak))
  }
 }
 expected<-do.call(rbind,out);keys<-c('evaluation','policy')
 stopifnot(all(names(expected) %in% names(observed)),!anyNA(observed[keys]),
  !anyDuplicated(observed[keys]),nrow(observed)==nrow(expected))
 for(i in seq_len(nrow(expected))) {
  e<-expected[i,];z<-observed[observed$evaluation==e$evaluation & observed$policy==e$policy,]
  stopifnot(nrow(z)==1)
  for(name in setdiff(names(expected),keys)) {
   stopifnot(is.numeric(z[[name]]))
   if(is.na(e[[name]]))stopifnot(is.na(z[[name]]))
   else stopifnot(is.finite(z[[name]]),abs(z[[name]]-e[[name]])<1e-6)
  }
 }
 tibble::as_tibble(expected)
}
