# Two-stage fixed-group ticket allocation. All money is CNY. supplement_share is
# a cap on original planned ticket count (not idle budget); integer tickets round
# down. Main tickets have payout >= main_floor; supplement tickets have payout in
# [supplement_floor, main_floor), and may only deepen groups opened by main.
# Both stages rank probability, expected contribution, then IDs. Group quotas
# remain fixed, no repeated ticket or multiplier, no transfer of unused reserve.
# Requires native shared cutoff validation via joint_payout_exposure. Pure,
# label-free; returns selected tickets, groups, exposures and component spending.
joint_payout_mix <- function(bundle,view,allocations,cutoffs,python,budget_cny,
                            unit_cny,main_floor,supplement_floor,supplement_share) {
 stopifnot(length(supplement_share)==1,is.finite(supplement_share),
  supplement_share>=0,supplement_share<1,length(supplement_floor)==1,
  is.finite(supplement_floor),supplement_floor>=0,
  length(main_floor)==1,is.finite(main_floor),main_floor>supplement_floor)
 # Validate shared inputs and obtain ordered eligible main candidates.
 base<-joint_payout_exposure(bundle,view,allocations,cutoffs,python,
  budget_cny,unit_cny,main_floor,budget_cny,budget_cny)
 total<-sum(allocations$depth)
 reserve<-floor(total*supplement_share+1e-10)
 main<-head(base$tickets,total-reserve)
 main$component<-rep('MAIN',nrow(main))
 ids<-as.character(allocations$sleeve_id)
 counts<-tabulate(match(as.character(main$sleeve_id),ids),nbins=length(ids))
 low<-view$long |>
  dplyr::filter(as.character(sleeve_id) %in% as.character(main$sleeve_id),
   payout_hat>=supplement_floor,payout_hat<main_floor) |>
  dplyr::arrange(dplyr::desc(prob),dplyr::desc(expected_gross_contribution),sleeve_id,ticket_col_idx)
 keep<-logical(nrow(low));used<-0L
 for(i in seq_len(nrow(low))) {
  if(used>=reserve)break
  j<-match(as.character(low$sleeve_id[i]),ids)
  if(counts[j]>=allocations$depth[j])next
  keep[i]<-TRUE;counts[j]<-counts[j]+1L;used<-used+1L
 }
 low<-low[keep,];low$component<-rep('SUPPLEMENT',nrow(low))
 tickets<-dplyr::bind_rows(main,low)
 groups<-tickets |> dplyr::group_by(issue,sleeve_id) |>
  dplyr::summarise(tickets=dplyr::n(),coverage=sum(prob),
   estimated_gross=sum(expected_gross_contribution),.groups='drop')
 fixture<-numeric(length(bundle$expanded_pool$fixtures));direction<-matrix(0,length(fixture),3)
 all_ids<-vapply(bundle$sleeves,function(x)as.character(x$id),character(1))
 for(id in unique(as.character(tickets$sleeve_id))) {
  t<-tickets[as.character(tickets$sleeve_id)==id,]
  ix<-as.integer(unlist(bundle$sleeves[[match(id,all_ids)]]$fixture_indices))+1L
  states<-outer(t$ticket_col_idx-1,3^(6:0),'%/%')%%3
  fixture[ix]<-fixture[ix]+nrow(t)*unit_cny
  for(j in seq_len(7))direction[ix[j],]<-direction[ix[j],]+unit_cny*tabulate(states[,j]+1L,nbins=3)
 }
 stopifnot(!anyDuplicated(tickets[c('sleeve_id','ticket_col_idx')]),
  all(counts<=allocations$depth),nrow(tickets)<=total,nrow(low)<=reserve)
 list(tickets=tickets,groups=groups,fixture_exposure=fixture,direction_exposure=direction,
  stake=nrow(tickets)*unit_cny,cash=budget_cny-nrow(tickets)*unit_cny,
  main_stake=nrow(main)*unit_cny,supplement_stake=nrow(low)*unit_cny,
  supplement_cap=reserve*unit_cny,cutoffs=cutoffs,historical_admission=FALSE)
}
