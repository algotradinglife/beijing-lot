# Settle a single sealed issue using the authoritative Python settlement API.
# ledger is typed sparse plan; b is verified membership projection; audit is
# issue-specific accepted labels. accounting explicitly sets budget/unit/factor.
# No selection, learning or writes; returns rows, coarse bridge and diagnostics.
# Every physical copy is settled in a unique-ticket layer. Independent R state
# and payout arithmetic must reconcile exactly. Empty issues stay NO_BET.
joint_rotation_settle_issue <- function(z,b,audit,accounting,python) {
 reticulate::use_python(python,required=TRUE)
 id<-b$issue
 stopifnot(all(z$issue==id),all(audit$issue==id),accounting$unit==2,accounting$payout_factor==.65,accounting$budget>=0)
 settler<-reticulate::import('src.n7_single_ticket_sampling',convert=TRUE)
 jsonmod<-reticulate::import('json',convert=FALSE)
 stable<-reticulate::import('src.temporal_learning.core',convert=TRUE)
 rows<-list()
 diagnostics<-joint_rotation_diagnostics(z,id,length(b$sleeves),2187,accounting$unit)
 ia<-audit
 groups<-list();sids<-vapply(b$sleeves,function(g)as.character(g$id),character(1))
 for(sid in unique(z$sleeve_id)) {
  g<-b$sleeves[[match(as.character(sid),sids)]];fx<-bind_rows(b$fixtures[as.integer(unlist(g$fixture_indices))+1L])
  labels<-fx |> select(slot,provider_id,handicap) |> left_join(ia,by=c('slot','provider_id','handicap'),relationship='one-to-one')
  stopifnot(nrow(labels)==7,!anyNA(labels$actual_direction),!anyNA(labels$spf_sp))
  actual<-sum((match(labels$actual_direction,c('W','D','L'))-1L)*3^(6:0))+1L
  groups[[as.character(sid)]]<-tibble(sleeve_id=sid,actual=actual,winning_gross=accounting$unit*accounting$payout_factor*prod(labels$spf_sp))
 }
 labels<-if(length(groups))bind_rows(groups) else tibble(sleeve_id=integer(),actual=integer(),winning_gross=double())
 z<-z |> left_join(labels,by='sleeve_id',relationship='many-to-one') |>
  mutate(hit=ticket_col_idx==actual,gross=if_else(hit,winning_gross,0),delta=copies-base_copies)
 for(policy in c('BASE','EXPAND','EXPAND_PROB','ROTATE','ROTATE_PROB')) {
  a<-z |> filter(.data$policy==.env$policy)
  settled<-list(stake=0,gross=0,net=0,hits=0,status='NO_BET')
  for(layer in 1:2) {
  bought<-a |> filter(copies>=layer)
  if(!nrow(bought))next
  legs<-lapply(bought$sleeve_id,function(sid)b$sleeves[[match(as.character(sid),sids)]]$fixture_indices)
  outcomes<-lapply(bought$ticket_col_idx,function(k)as.list(as.integer(((k-1)%/%3^(6:0))%%3)))
  packed<-list(issue=id,budget_cny=accounting$budget,unit_cny=accounting$unit,payout_factor=accounting$payout_factor,fixture_indices=legs,outcomes=outcomes,
   groups=nrow(bought),fixtures=b$fixtures,stake=accounting$unit*nrow(bought),cash_cny=accounting$budget-accounting$unit*nrow(bought))
  pp<-jsonmod$loads(jsonlite::toJSON(packed,auto_unbox=TRUE,digits=NA));pp$`__setitem__`('seal',stable$stable_json_hash(pp))
  part<-settler$settle_single_tickets(pp,reticulate::r_to_py(ia))
  stopifnot(part$status %in% c('COMPLETE','NO_BET'))
  for(k in c('stake','gross','net','hits'))settled[[k]]<-settled[[k]]+part[[k]]
  if(part$status=='COMPLETE')settled$status<-'COMPLETE'
  }
  stopifnot(settled$status %in% c('COMPLETE','NO_BET'),abs(settled$gross-sum(a$gross*a$copies))<1e-6)
  rows[[paste(id,policy)]]<-tibble(issue=id,policy,stake=settled$stake,gross=settled$gross,net=settled$net,hits=settled$hits)
 }
 bridge<-z |> filter(policy!='BASE',delta!=0) |>
  mutate(component=if_else(delta<0,'REMOVED',if_else(base_copies==0,'NEW','MULTIPLIED'))) |>
  group_by(issue,policy,component) |> summarise(stake_change=sum(accounting$unit*delta),gross_change=sum(gross*delta),net_change=gross_change-stake_change,.groups='drop')
 list(rows=bind_rows(rows),bridge=bridge,diagnostics=diagnostics)
}
