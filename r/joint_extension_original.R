# Build the unchanged JOINT original ticket set for one explicit fixture cutoff.
# bundle is a verified frozen candidate bundle; settings supplies coverage, cap,
# minimum_sp, budget/unit/factor, seed/worlds/max_actions and model identity.
# No labels or I/O. Returns canonical tickets, member identities and gate counts.
# Existing allocation/price/chronology implementations own all business rules.
joint_extension_original <- function(bundle,cutoff,settings,python) {
 b<-bundle;s<-settings;stopifnot(identical(cutoff,b$cutoffs))
 a<-n7_probability_allocate(b,cutoff,s$model_id,python,s$target_coverage,s$group_cap_cny,
  s$minimum_sp,s$budget_cny,s$unit_cny,s$payout_factor,s$seed,s$worlds,s$max_actions)
 v<-n7_sleeve_tables(b,cutoff,s$model_id)
 parts<-list()
 for(j in a$fit$selected) {
  o<-a$pool$options[[j]];sid<-as.character(o$sleeve_id);k<-v$rank_idx[sid,seq_len(o$depth)]
  t<-tibble::tibble(issue=b$issue,sleeve_id=as.integer(o$sleeve_id),ticket_col_idx=as.integer(k),
   ticket_id=paste(sid,k,sep=':'),prob=as.numeric(v$prob_mat[sid,k]),payout_hat=as.numeric(v$payout_hat_mat[sid,k]),prob_rank=seq_along(k))
  stopifnot(abs(sum(t$prob)-o$coverage)<1e-10,nrow(t)*s$unit_cny==o$stake)
  parts[[sid]]<-t
 }
 t<-dplyr::bind_rows(c(list(tibble::tibble(issue=character(),sleeve_id=integer(),ticket_col_idx=integer(),ticket_id=character(),prob=double(),payout_hat=double(),prob_rank=integer())),unname(parts)))
 stopifnot(!anyDuplicated(t$ticket_id),nrow(t)*s$unit_cny==a$fit$metrics$stake)
 members<-dplyr::bind_rows(lapply(b$sleeves,function(g)tibble::tibble(sleeve_id=g$id,fixture=as.character(unlist(g$fixture_indices)))))
 list(tickets=t,members=members,fixtures=dplyr::bind_rows(b$expanded_pool$fixtures),
  metrics=tibble::tibble(issue=b$issue,fixtures=nrow(a$gate$fixtures),eligible_fixtures=sum(a$gate$fixtures$eligible),
   candidate_groups=nrow(a$gate$groups),eligible_groups=sum(a$gate$groups$eligible),bought_groups=length(a$fit$selected),
   original_stake=nrow(t)*s$unit_cny,model_union=a$fit$metrics$any_hit))
}

# Independent relational replay of BASE: keep ceil(n/2) highest-probability
# tickets in BAD long-history cells, all others. Same explicit signal receipt.
# Returns copies aligned with tickets. No learning, labels or side effects.
joint_extension_base_replay <- function(tickets,signals,cutoff) {
 rec<-attr(signals,'signal_receipt');plain<-signals;attr(plain,'signal_receipt')<-NULL
 stopifnot(!is.null(rec),identical(rec$cutoff,cutoff),
  identical(rec$signal_hash,digest::digest(plain,algo='sha256')),
  cutoff$cutoff_kind=='DECISION_EPOCH',identical(cutoff$historical_admission,FALSE),
  !anyDuplicated(tickets$ticket_id),!anyDuplicated(signals$cell),
  !anyNA(tickets[c('ticket_id','cell','prob')]),all(is.finite(tickets$prob)))
 z<-tickets |> dplyr::mutate(input_order=dplyr::row_number()) |>
  dplyr::left_join(signals |> dplyr::select(cell,long_hit_signal),by='cell',relationship='many-to-one') |>
  dplyr::group_by(cell) |> dplyr::arrange(dplyr::desc(prob),ticket_id,.by_group=TRUE) |>
  dplyr::mutate(copies=as.integer(is.na(long_hit_signal)|long_hit_signal!='BAD'|dplyr::row_number()<=ceiling(dplyr::n()/2))) |>
  dplyr::ungroup() |> dplyr::arrange(input_order)
 z$copies
}
