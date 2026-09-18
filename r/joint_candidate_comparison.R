# Fixed label-free candidate expansion. Keep the entire original pool and add
# up to additional_groups from the fresh Top2 universe. Anchor its diversified
# four groups, then alternate probability/estimated-gross ranking subject to
# pairwise overlap <= max_overlap among added groups. No labels/fitting/I/O.
# Native enumeration and chronology remain in the shared Python modules.
joint_candidate_expand <- function(bundle,fresh,cutoffs,python,additional_groups,max_overlap) {
 stopifnot(identical(bundle$cutoffs,cutoffs),identical(fresh$cutoffs,cutoffs),
   identical(fresh$seal,digest::digest(fresh[names(fresh)!='seal'],algo='sha256')),
   additional_groups>=4,additional_groups==floor(additional_groups),max_overlap>=0,max_overlap<=6,
   max_overlap==floor(max_overlap))
 n7_joint_validate(bundle$expanded_pool$fixtures,cutoffs,python)
 f<-dplyr::bind_rows(bundle$expanded_pool$fixtures)
 stopifnot(identical(f$slot,fresh$fixtures$slot),isTRUE(all.equal(f,fresh$fixtures,check.attributes=FALSE)))
 selected<-fresh$selected$TOP2_DIVERSE
 remaining<-setdiff(seq_along(fresh$groups),selected)
 while(length(selected)<additional_groups && length(remaining)) {
  ok<-vapply(remaining,function(j)all(vapply(selected,function(k)length(intersect(fresh$groups[[j]],fresh$groups[[k]]))<=max_overlap,logical(1))),logical(1))
  remaining<-remaining[ok];if(!length(remaining))break
  score<-if(length(selected)%%2==0)fresh$probability else fresh$expected_gross
  best<-remaining[order(-score[remaining],-fresh$probability[remaining],remaining)[1]]
  selected<-c(selected,best);remaining<-setdiff(remaining,best)
 }
 out<-bundle;known<-vapply(out$sleeves,function(g)paste(sort(as.integer(unlist(g$fixture_indices))+1L),collapse=','),character(1))
 mod<-reticulate::import('src.n7_sleeve_states');core<-reticulate::import('src.temporal_learning')
 next_id<-max(vapply(out$sleeves,function(g)as.integer(g$id),integer(1)))+1L
 for(j in selected) {
  ix<-fresh$groups[[j]];key<-paste(ix,collapse=',');if(key %in% known)next
  native<-lapply(cutoffs[as.character(f$slot[ix])],function(epoch)core$Cutoff$decision_epoch(bundle$issue,epoch))
  e<-mod$enumerate_sleeve(reticulate::r_to_py(as.data.frame(f[ix,])),cutoffs=native,unit_cny=fresh$parameters$unit_cny,payout_factor=fresh$parameters$payout_factor)
  # Record-list identity is canonical in the existing R bundle contract.
  e$fixtures<-out$expanded_pool$fixtures[ix]
  out$sleeves[[length(out$sleeves)+1L]]<-list(id=next_id,fixture_indices=as.list(ix-1L),origin='FRESH_DIVERSE_POOL',enumeration=e,options=list())
  next_id<-next_id+1L;known<-c(known,key)
 }
 out$source_bundle_seal<-bundle$seal
 out$expansion<-list(additional_groups=additional_groups,max_overlap=max_overlap,selected_fresh=selected,
   actual_added=length(out$sleeves)-length(bundle$sleeves),fresh_seal=fresh$seal)
 out$seal<-digest::digest(out[names(out)!='seal'],algo='sha256');out
}

# Hard Top2/compressed supports and nearby probability-ranked prefixes on one
# expanded pool. Explicit fixed settings, native cutoffs; no labels or fitting.
# Anchor score = (1-epsilon)*normalized(p^temperature within hard support)
#                + epsilon*p over all states. Original p still values tickets.
# Complete hard options remain feasible. A label-free model-world safeguard
# retains the hard portfolio if greedy anchored selection has lower any-hit.
joint_candidate_compare <- function(bundle,cutoffs,python,settings) {
 s<-settings;stopifnot(s$budget_cny==1024,s$unit_cny==2,s$payout_factor==.65,
   s$temperature>0,s$temperature<=1,s$outside_mix>=0,s$outside_mix<=.05,
   s$outside_ticket_fraction>=0,s$outside_ticket_fraction<=.05,s$marginal_tv_cap>=0,s$marginal_tv_cap<=.25)
 a<-n7_probability_allocate(bundle,cutoffs,s$model_id,python,s$target_coverage,s$group_cap_cny,s$minimum_sp,s$budget_cny,s$unit_cny,s$payout_factor,s$seed,s$worlds,s$max_actions)
 v<-a$surface;f<-dplyr::bind_rows(bundle$expanded_pool$fixtures)
 p<-as.matrix(f[paste0('p_',c('W','D','L'))])
 all_groups<-lapply(bundle$sleeves,function(g)as.integer(unlist(g$fixture_indices))+1L)
 eligible<-which(vapply(all_groups,function(ix)all(a$gate$fixtures$eligible[ix]),logical(1)))
 states<-as.matrix(expand.grid(rep(list(0:2),7)))[,7:1,drop=FALSE]
 ordering<-lapply(seq_len(nrow(f)),function(i)order(-p[i,],1:3)-1L)
 worlds<-n7_joint_worlds(list(fixtures=bundle$expanded_pool$fixtures,cutoffs=cutoffs),cutoffs,s$hard_seed,s$hard_worlds)
 evaluation_worlds<-n7_joint_worlds(list(fixtures=bundle$expanded_pool$fixtures,cutoffs=cutoffs),cutoffs,s$evaluation_seed,s$evaluation_worlds)
 picks<-list(JOINT_NATIVE=a$pool$options[a$fit$selected]);fallback<-list(JOINT_NATIVE=FALSE)
 for(compressed in 0:2) {
  hard<-list();anchor<-list();within<-list()
  for(j in eligible) {
   ix<-all_groups[[j]];sid<-as.character(bundle$sleeves[[j]]$id)
   singles<-head(order(-apply(p[ix,,drop=FALSE],1,max),f$slot[ix]),compressed)
   mask<-rep(TRUE,2187);target<-matrix(0,7,3)
   for(k in 1:7) {allowed<-head(ordering[[ix[k]]],if(k %in% singles)1 else 2);mask<-mask & states[,k] %in% allowed;target[k,allowed+1L]<-1/length(allowed)}
   size<-2^(7-compressed);stopifnot(sum(mask)==size)
   conditional<-v$prob_mat[sid,]^s$temperature*mask;conditional<-conditional/sum(conditional)
   score<-(1-s$outside_mix)*conditional+s$outside_mix*v$prob_mat[sid,]
   rank<-order(-score,-v$value_mat[sid,],1:2187)
   subsets<-c(list(which(mask)),lapply(c(size/4,size/2,size),function(n)head(rank,n)))
   keys<-vapply(subsets,function(z)paste(sort(z),collapse=','),FUN.VALUE=character(1));subsets<-subsets[!duplicated(keys)]
   for(k in seq_along(subsets)) {
    ids<-subsets[[k]];outside<-mean(!mask[ids]);tv<-max(vapply(1:7,function(leg)sum(abs(tabulate(states[ids,leg]+1L,nbins=3)/length(ids)-target[leg,]))/2,numeric(1)));if(outside>s$outside_ticket_fraction+1e-12 || tv>s$marginal_tv_cap+1e-12)next
    o<-list(sleeve_id=bundle$sleeves[[j]]$id,fixtures=ix,state_ids=ids,depth=length(ids),
       stake=s$unit_cny*length(ids),coverage=sum(v$prob_mat[sid,ids]),expected_gross=sum(v$value_mat[sid,ids]),
       state_payout=v$payout_hat_mat[sid,],state_probability=v$prob_mat[sid,],unit_copies=1,role='CORE',
       max_marginal_tv=tv,outside_fraction=outside,outside_state_ids=ids[!mask[ids]],compressed=compressed)
    anchor[[length(anchor)+1L]]<-o
    if(k==1)hard[[length(hard)+1L]]<-o
   }
   inside_rank<-which(mask)[order(-conditional[mask],-v$value_mat[sid,which(mask)],which(mask))]
   for(depth in c(size/4,size/2,size)) {
    ids<-head(inside_rank,depth);tv<-max(vapply(1:7,function(leg)sum(abs(tabulate(states[ids,leg]+1L,nbins=3)/length(ids)-target[leg,]))/2,numeric(1)));if(tv>s$marginal_tv_cap+1e-12)next;o<-hard[[length(hard)]];o$max_marginal_tv<-tv
    o$state_ids<-ids;o$depth<-depth;o$stake<-s$unit_cny*depth
    o$coverage<-sum(v$prob_mat[sid,ids]);o$expected_gross<-sum(v$value_mat[sid,ids])
    within[[length(within)+1L]]<-o
   }
  }
  fits<-list();candidate_pools<-list()
  for(kind in c('HARD','WITHIN','ANCHOR')) {
   opts<-switch(kind,HARD=hard,WITHIN=within,ANCHOR=anchor)
   pool<-list(issue=bundle$issue,cutoffs=cutoffs,fixtures=bundle$expanded_pool$fixtures,
      options=opts,mode='BREADTH',opening_options=seq_along(opts),opportunity_options=integer())
   scenarios<-n7_joint_returns(pool,worlds,cutoffs)
   fit<-n7_core_allocate(pool,scenarios,cutoffs,s$budget_cny,'any_hit',s$max_actions,'OPEN_FIRST')
   stopifnot(fit$stop_reason!='ACTION_LIMIT')
   fits[[kind]]<-fit;candidate_pools[[kind]]<-pool
  }
  hard_name<-paste0('HARD',compressed)
  picks[[hard_name]]<-hard[fits$HARD$selected];fallback[[hard_name]]<-FALSE
  for(kind in c('WITHIN','ANCHOR')) {
   keep_hard<-fits[[kind]]$metrics$any_hit+1e-12<fits$HARD$metrics$any_hit
   name<-paste0(kind,compressed);opts<-candidate_pools[[kind]]$options
   picks[[name]]<-if(keep_hard)picks[[hard_name]] else opts[fits[[kind]]$selected]
   fallback[[name]]<-keep_hard
  }
 }
 ticket_parts<-list();metrics<-list()
 for(policy in names(picks)) {
  for(o in picks[[policy]]) {
   sid<-as.character(o$sleeve_id);ids<-o$state_ids;outside_flag<-if(policy=="JOINT_NATIVE")rep(NA,length(ids)) else ids %in% o$outside_state_ids
   ticket_parts[[length(ticket_parts)+1L]]<-tibble::tibble(issue=bundle$issue,policy=policy,group_id=as.integer(sid),state_id=ids,probability=as.numeric(v$prob_mat[sid,ids]),estimated_payout=as.numeric(v$payout_hat_mat[sid,ids]),outside_support=outside_flag)
  }
  projected<-n7_joint_returns(list(cutoffs=cutoffs,fixtures=bundle$expanded_pool$fixtures,options=picks[[policy]]),evaluation_worlds,cutoffs)
  metrics[[policy]]<-tibble::tibble(policy=policy,model_any_hit=mean(rowSums(projected$hits)>0),
     model_expected_gross=sum(vapply(picks[[policy]],function(o)o$expected_gross,numeric(1))),
     hard_fallback=fallback[[policy]],max_marginal_tv=if(policy=='JOINT_NATIVE')NA_real_ else max(c(0,vapply(picks[[policy]],function(o)o$max_marginal_tv,numeric(1)))))
 }
 tickets<-dplyr::bind_rows(c(list(tibble::tibble(issue=character(),policy=character(),group_id=integer(),state_id=integer(),probability=double(),estimated_payout=double(),outside_support=logical())),ticket_parts))
 stopifnot(all(table(tickets$policy)*s$unit_cny<=s$budget_cny))
 groups<-dplyr::bind_rows(lapply(seq_along(all_groups),function(j)tibble::tibble(group_id=bundle$sleeves[[j]]$id,fixture_index=all_groups[[j]])))
 out<-list(issue=bundle$issue,cutoffs=cutoffs,fixtures=f,groups=groups,tickets=tickets,
   policies=names(picks),metrics=dplyr::bind_rows(metrics),settings=s,
   source_bundle_seal=bundle$seal,historical_admission=FALSE)
 c(out,list(seal=joint_candidate_seal(out)))
}

# Settle frozen exact-state tickets with audited official SPF labels. Identity
# and handicap must match every fixture; .65 applied once per winning CNY2.
# Returns typed period rows including cash-only cases, and ticket/group evidence.
joint_candidate_settle <- function(plan,labels) {
 stopifnot(identical(plan$seal,joint_candidate_seal(plan[names(plan)!='seal'])),
   !anyDuplicated(labels[c('issue','slot','provider_id')]))
 x<-dplyr::left_join(plan$fixtures,labels,by=c('issue','slot','provider_id','handicap'),relationship='one-to-one')
 stopifnot(!anyNA(x$actual_direction),all(x$actual_direction %in% c('W','D','L')),all(is.finite(x$spf_sp)),all(x$spf_sp>0))
 labels_group<-plan$groups |> dplyr::group_by(group_id) |> dplyr::summarise(
   actual_state=1+sum((match(x$actual_direction[fixture_index],c('W','D','L'))-1)*3^(6:0)),
   payout=plan$settings$unit_cny*plan$settings$payout_factor*prod(x$spf_sp[fixture_index]),.groups='drop')
 ticket_input<-tibble::as_tibble(plan$tickets)
 if(!nrow(ticket_input))ticket_input<-tibble::tibble(issue=character(),policy=character(),group_id=integer(),state_id=integer(),probability=double(),estimated_payout=double(),outside_support=logical())
 tickets<-ticket_input |> dplyr::left_join(labels_group,by='group_id',relationship='many-to-one') |>
   dplyr::mutate(hit=state_id==actual_state,gross=dplyr::if_else(hit,payout,0))
 rows<-tickets |> dplyr::group_by(policy) |> dplyr::summarise(stake=dplyr::n()*plan$settings$unit_cny,
   gross=sum(gross),hits=sum(hit),bought_groups=dplyr::n_distinct(group_id),.groups='drop')
 rows<-tibble::tibble(policy=plan$policies) |>
   dplyr::left_join(rows,by='policy',relationship='one-to-one') |> dplyr::mutate(dplyr::across(c(stake,gross,hits,bought_groups),~tidyr::replace_na(.x,0)),issue=plan$issue,net=gross-stake)
 list(rows=rows,tickets=tickets)
}

# Canonical JSON bytes for the persistent, reloadable plan boundary; no I/O.
# Field order is retained by jsonlite save/load. JSON nulls represent NA.
joint_candidate_seal <- function(payload) {
 digest::digest(as.character(jsonlite::toJSON(payload,auto_unbox=TRUE,digits=NA,null='null',na='null')),algo='sha256',serialize=FALSE)
}
