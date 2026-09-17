# Build and independently replay an issue's full-universe fixed policies.
# bundle is verified externally by source SHA; base and signals are same-cutoff
# frozen inputs; settings explicitly supplies grid, money and exposure constants.
# Pure except explicit reticulate initialization; no file writes or labels.
# Returns sparse ledgers (bought or original tickets) and allocation diagnostics.
# Empty pools are retained as NO_BET; invalid source/clock/replay stops.
joint_grid_rotate_issue <- function(b,base,signals,cutoff,model_receipt_sha256,settings,python) {
 reticulate::use_python(python,required=TRUE)
 id<-b$issue;cut<-cutoff;diagnostics<-list()
 stopifnot(settings$n==7,all(base$issue==id),!anyDuplicated(base$ticket_id))
 stopifnot(identical(b$historical_admission,FALSE),id==cut$target_issue,min(unlist(b$cutoffs))==cut$cutoff_ts)
 if(length(b$sleeves)) {
  view<-n7_sleeve_tables(b,b$cutoffs,settings$model_id)
  t<-view$long |> select(issue,sleeve_id,ticket_col_idx,prob,payout_hat) |>
   mutate(ticket_id=paste(sleeve_id,ticket_col_idx,sep=':'),
    cell=paste(cut(prob,settings$p_breaks,right=FALSE,include.lowest=TRUE),
     cut(payout_hat,settings$r_breaks,right=FALSE),sep=' | ')) |>
   left_join(base |> select(ticket_id,base_copies),by='ticket_id',relationship='one-to-one') |>
   mutate(base_copies=replace_na(base_copies,0L))
  members<-bind_rows(lapply(b$sleeves,function(g)tibble(sleeve_id=g$id,fixture=as.character(unlist(g$fixture_indices)))))
  keys<-vapply(b$sleeves,function(g)paste(sort(as.integer(unlist(g$fixture_indices))),collapse=','),character(1));stopifnot(!anyDuplicated(keys))
 } else {
  t<-tibble(issue=character(),sleeve_id=integer(),ticket_col_idx=integer(),prob=double(),payout_hat=double(),ticket_id=character(),cell=character(),base_copies=integer())
  members<-tibble(sleeve_id=integer(),fixture=character())
 }
 old<-base
 stopifnot(setequal(t$ticket_id[t$base_copies==1L],old$ticket_id[old$base_copies==1L]))
 s<-signals
 stopifnot(all(s$cutoff_identity==cut$cutoff_identity))
 attr(s,'input_receipt')<-list(cutoff=cut,hash=digest::digest(s,algo='sha256'))
 selected<-list(BASE=t |> filter(base_copies>0) |> mutate(copies=base_copies,state='BASE',action='UNCHANGED'))
 for(mode in c('EXPAND','ROTATE')) {
  a<-joint_grid_rotate(t,members,s,cut,model_receipt_sha256,mode,FALSE,settings$n,settings$unit,settings$budget,settings$payout_floor,settings$fixture_cap,settings$max_overlap,settings$cut_fraction,settings$bad,settings$good,floor(settings$budget/settings$unit))
  matched<-joint_grid_rotate(t,members,s,cut,model_receipt_sha256,mode,TRUE,settings$n,settings$unit,settings$budget,settings$payout_floor,settings$fixture_cap,settings$max_overlap,settings$cut_fraction,settings$bad,settings$good,sum(a$copies))
  # Deterministic replay under row permutation and irrelevant post-cutoff labels.
  changed<-t[nrow(t):1,,drop=FALSE]
  if(!nrow(t))changed<-t
  changed$target_settlement<-rep(1e9,nrow(changed))
  replay<-joint_grid_rotate(changed,members,s,cut,model_receipt_sha256,mode,FALSE,settings$n,settings$unit,settings$budget,settings$payout_floor,settings$fixture_cap,settings$max_overlap,settings$cut_fraction,settings$bad,settings$good,floor(settings$budget/settings$unit))
  stopifnot(identical(a$copies,replay$copies[match(a$ticket_id,replay$ticket_id)]))
  native<-reticulate::import('src.temporal_learning.core',convert=FALSE)$Cutoff$decision_epoch(id,cut$cutoff_ts)
  oracle<-reticulate::import('src.joint_grid_rotation_replay',convert=TRUE)
  st<-s |> transmute(cell,state=if_else(supported & long_hit_signal!='UNKNOWN',if_else(return_ratio<settings$bad,'BAD',if_else(return_ratio>=settings$good,'GOOD','NEUTRAL')),'UNKNOWN'))
  for(prob_only in c(FALSE,TRUE)) {
   target<-if(prob_only)sum(a$copies) else floor(settings$budget/settings$unit)
   payload<-list(issue=id,cutoff_ts=cut$cutoff_ts,cutoff_identity=cut$cutoff_identity,tickets=t,members=members,signals=st,
    parameters=list(mode=mode,cut_fraction=settings$cut_fraction,unit_cny=settings$unit,fixture_cap_cny=settings$fixture_cap,
     payout_floor=settings$payout_floor,probability_only=prob_only,target_units=target,max_overlap=settings$max_overlap))
   independent<-oracle$replay_rotation_json(jsonlite::toJSON(payload,auto_unbox=TRUE,dataframe='rows',digits=NA),native)
   stopifnot(identical(as.integer(unlist(independent)),if(prob_only)matched$copies else a$copies))
  }
  selected[[mode]]<-t |> left_join(a,by='ticket_id',relationship='one-to-one') |> filter(copies>0 | base_copies>0)
  selected[[paste0(mode,'_PROB')]]<-t |> left_join(matched,by='ticket_id',relationship='one-to-one') |> filter(copies>0 | base_copies>0)
  diagnostics[[paste(id,mode)]]<-tibble(issue=id,policy=mode,candidate_groups=length(b$sleeves),candidates=nrow(t),
   target_stake=settings$unit*sum(a$copies),comparator_stake=settings$unit*sum(matched$copies),
   new_combinations=sum(a$copies>0 & t$base_copies==0),extra_copies=sum(pmax(a$copies-1L,0L)),removed=sum(a$copies==0 & t$base_copies==1L),
   new_groups=length(setdiff(t$sleeve_id[a$copies>0],t$sleeve_id[t$base_copies>0])))
 }
 list(plans=bind_rows(selected,.id='policy'),diagnostics=bind_rows(diagnostics))
}
