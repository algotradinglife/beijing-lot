# Independent post-settlement cohort audit; no production accounting helpers.
# periods: one row per issue/policy, with stake/gross/net/hits/cash_cny (CNY).
# observed: reported ALL/ORIGINAL/ADDITIONAL summary for FUNDED and SHADOW.
# issue_order/original_issues and expected_policies are independently frozen IDs.
# budget_cny and initial_capital_cny are positive scalar business constants.
# Returns independently calculated summary after exact scope/accounting checks.
# No learning, I/O or side effects. Missing/duplicate/nonfinite rows fail closed;
# zero spending requires NA ROI. Cohort accounts start independently, ALL once.
# Independently reconstruct permanent funding stop; SHADOW may be negative.
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
   original<-p[match(scopes[[evaluation]],p$issue),]
   stopped<-logical(nrow(original));balance<-initial_capital_cny;hold<-FALSE
   for(j in seq_len(nrow(original))) {
    if(!hold && balance+1e-8<original$stake[j])hold<-TRUE
    stopped[j]<-hold
    if(!hold)balance<-balance+original$net[j]
   }
   stop_issue<-if(any(stopped))original$issue[which(stopped)[1]] else NA_character_
   for(basis in c('FUNDED','SHADOW')) {
    x<-original
    if(basis=='FUNDED') {
     x$stake[stopped]<-x$gross[stopped]<-x$net[stopped]<-x$hits[stopped]<-0
     x$cash_cny<-budget_cny-x$stake
    }
    net<-x$gross-x$stake;equity<-initial_capital_cny+c(0,cumsum(net))
    peak<-cummax(equity);dd<-peak-equity;stake<-sum(x$stake)
    out[[length(out)+1L]]<-data.frame(evaluation=evaluation,accounting_basis=basis,policy=policy,
    issues=nrow(x),stake_cny=stake,net_cny=sum(net),
    roi_percent=if(stake>0)100*sum(net)/stake else NA_real_,
    hit_issues=sum(x$gross>0),profit_issues=sum(net>0),winning_groups=sum(x$hits),
    cash_cny=sum(x$cash_cny),max_drawdown_cny=max(dd),minimum_equity_cny=min(equity),
    net_without_best_cny=sum(net)-max(net),max_drawdown_percent=100*max(dd/peak),
    bet_issues=sum(x$stake>0),stopped_issues=if(basis=='FUNDED')sum(stopped) else 0,
    funding_stop_issue=stop_issue)
   }
  }
 }
 expected<-do.call(rbind,out);keys<-c('evaluation','accounting_basis','policy')
 stopifnot(all(names(expected) %in% names(observed)),!anyNA(observed[keys]),
  !anyDuplicated(observed[keys]),nrow(observed)==nrow(expected))
 for(i in seq_len(nrow(expected))) {
  e<-expected[i,];z<-observed[observed$evaluation==e$evaluation & observed$policy==e$policy &
                            observed$accounting_basis==e$accounting_basis,]
  stopifnot(nrow(z)==1)
  if(is.na(e$funding_stop_issue))stopifnot(is.na(z$funding_stop_issue))
  else stopifnot(identical(z$funding_stop_issue,e$funding_stop_issue))
  for(name in setdiff(names(expected),c(keys,'funding_stop_issue'))) {
   stopifnot(is.numeric(z[[name]]))
   if(is.na(e[[name]]))stopifnot(is.na(z[[name]]))
   else stopifnot(is.finite(z[[name]]),abs(z[[name]]-e[[name]])<1e-6)
  }
 }
 tibble::as_tibble(expected)
}
