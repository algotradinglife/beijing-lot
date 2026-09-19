# Independent descriptive replay of published curves and diagnostic tables.
# periods is the verified settled ledger; scopes is a named issue-order list.
# observed contains curves/trimmed/streaks/complementarity/paired data frames.
# Explicit CNY capital and baseline policy; no purchase/accounting imports,
# fitting, I/O or state. Reject missing/extra keys and numerical discrepancies.
eight_strategy_detail_audit <- function(periods,scopes,observed,capital,baseline) {
 stopifnot(capital>0,length(capital)==1,!anyDuplicated(periods[c('issue','policy')]),
  baseline %in% periods$policy,length(scopes)>0)
 expected<-list();trims<-runs<-pairs<-paired<-list()
 for(scope in names(scopes))for(basis in c('FUNDED','SHADOW')) {
  ledgers<-list()
  for(policy in unique(periods$policy)) {
   x<-periods[periods$policy==policy,];x<-x[match(scopes[[scope]],x$issue),]
   stopifnot(!anyNA(x[c('issue','stake','gross','net','hits')]))
   balance<-capital;hold<-FALSE;stopped<-logical(nrow(x))
   for(i in seq_len(nrow(x))) {
    if(balance+1e-8<x$stake[i])hold<-TRUE
    stopped[i]<-hold
    if(!hold)balance<-balance+x$net[i]
   }
   stop_issue<-if(any(stopped))x$issue[which(stopped)[1]] else NA_character_
   starts<-stopped & !c(FALSE,head(stopped,-1))
   if(basis=='FUNDED')for(n in c('stake','gross','net','hits'))x[[n]][stopped]<-0
   equity<-capital+c(0,cumsum(x$net))
   key<-data.frame(evaluation=scope,accounting_basis=basis,policy=policy)
   curve<-cbind(key,data.frame(period=0:nrow(x),issue=c(NA_character_,x$issue),
    stopped=c(FALSE,if(basis=='FUNDED')stopped else rep(FALSE,nrow(x))),
    stop_started=c(FALSE,if(basis=='FUNDED')starts else rep(FALSE,nrow(x))),
    funding_stop_issue=stop_issue,stake=c(0,x$stake),gross=c(0,x$gross),
    net=c(0,x$net),hits=c(0,x$hits),equity_cny=equity,
    opening_cny=c(capital,head(equity,-1)),drawdown_cny=cummax(equity)-equity,
    cumulative_net_cny=equity-capital,capital_return_percent=100*(equity-capital)/capital))
   expected[[length(expected)+1L]]<-curve;ledgers[[policy]]<-x
   streak<-0L;best<-0L
   for(i in which(x$stake>0)) {
    streak<-if(x$gross[i]>0)0L else streak+1L;best<-max(best,streak)
   }
   runs[[length(runs)+1L]]<-cbind(key,bet_issues=sum(x$stake>0),longest_no_hit_bet_run=best)
   positives<-which(x$net>0);ordered<-positives[order(-x$net[positives],positives)]
   for(k in c(1L,3L,5L)) {
    drop<-head(ordered,k);keep<-setdiff(seq_len(nrow(x)),drop)
    stake<-sum(x$stake[keep]);net<-sum(x$net[keep])
    trims[[length(trims)+1L]]<-cbind(key,requested_remove=k,actual_removed=length(drop),
     remaining_issues=length(keep),stake_cny=stake,net_cny=net,
     roi_percent=if(stake>0)100*net/stake else NA_real_)
   }
  }
  b<-ledgers[[baseline]]
  for(policy in names(ledgers)) {
   x<-ledgers[[policy]];key<-data.frame(evaluation=scope,accounting_basis=basis,policy=policy)
   both<-sum(x$gross>0 & b$gross>0);unique_hit<-sum(x$gross>0 & b$gross==0)
   lost<-sum(x$gross==0 & b$gross>0)
   pairs[[length(pairs)+1L]]<-cbind(key,issues=nrow(x),
    correlation=if(nrow(x)>1 && sd(x$net)>0 && sd(b$net)>0)cor(x$net,b$net) else NA_real_,
    both_hit=both,unique_hit=unique_hit,baseline_only_hit=lost,
    neither_hit=sum(x$gross==0 & b$gross==0),unique_profit=sum(x$net>0 & b$net<=0))
   paired[[length(paired)+1L]]<-cbind(key,rescued_issues=unique_hit,lost_issues=lost,
    net_change_cny=sum(x$net-b$net))
  }
 }
 tables<-list(curves=dplyr::bind_rows(expected),trimmed=dplyr::bind_rows(trims),
  streaks=dplyr::bind_rows(runs),complementarity=dplyr::bind_rows(pairs),paired=dplyr::bind_rows(paired))
 for(name in names(tables)) {
  e<-tables[[name]];z<-observed[[name]]
  keys<-c('evaluation','accounting_basis','policy',if(name=='curves')'period' else if(name=='trimmed')'requested_remove')
  stopifnot(!is.null(z),all(names(e) %in% names(z)),nrow(z)==nrow(e),!anyDuplicated(z[keys]))
  e<-e[do.call(order,e[keys]),];z<-z[do.call(order,z[keys]),]
  for(n in names(e)) {
   stopifnot(identical(is.na(e[[n]]),is.na(z[[n]])))
   if(is.numeric(e[[n]]))stopifnot(all(abs(e[[n]]-z[[n]])<1e-6,na.rm=TRUE))
   else stopifnot(identical(e[[n]],z[[n]]))
  }
 }
 invisible(TRUE)
}
