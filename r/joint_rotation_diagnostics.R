# Reconstruct allocation diagnostics from sealed ticket rows, not an auxiliary CSV.
# One issue; ledger may be empty. Counts are descriptive; no learning/selection.
# candidate_groups is the verified bundle's sleeve count; n_states explicit.
# Returns EXPAND/ROTATE funding and coverage counts, all typed for empty issues.
joint_rotation_diagnostics <- function(ledger,issue,candidate_groups,n_states,unit_cny) {
 stopifnot(all(c('issue','policy','ticket_id','sleeve_id','copies','base_copies') %in% names(ledger)),
  !anyNA(ledger),!anyDuplicated(ledger[c('policy','ticket_id')]),all(ledger$issue==issue),
  length(issue)==1,is.character(issue),nzchar(issue),all(ledger$copies %in% 0:2),all(ledger$base_copies %in% 0:1),
  candidate_groups>=0,candidate_groups==floor(candidate_groups),n_states>=1,n_states==floor(n_states),unit_cny>0)
 parts<-list()
 for(mode in c('EXPAND','ROTATE')) {
  x<-ledger[ledger$policy==mode,];y<-ledger[ledger$policy==paste0(mode,'_PROB'),]
  parts[[mode]]<-tibble::tibble(issue=issue,policy=mode,candidate_groups=candidate_groups,candidates=candidate_groups*n_states,
   target_stake=unit_cny*sum(x$copies),comparator_stake=unit_cny*sum(y$copies),new_combinations=sum(x$copies>0 & x$base_copies==0),
   extra_copies=sum(pmax(x$copies-1L,0L)),removed=sum(x$copies==0 & x$base_copies==1L),
   new_groups=length(setdiff(x$sleeve_id[x$copies>0],x$sleeve_id[x$base_copies>0])))
 }
 dplyr::bind_rows(parts)
}
