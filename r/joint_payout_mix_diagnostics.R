# Paired issue diagnostics relative to uniform floor256. Input: complete settled
# rows (issue/policy/stake/gross/net/hits) and unique issue/stage map. Monetary
# units CNY. No decision or fitting, no IO. Outputs stage-level exact accounting
# and rescued/lost hit issues, plus issue-level paired differences.
joint_payout_mix_diagnostics <- function(rows,map,reference_policy) {
 required<-c('issue','policy','stake','gross','net','hits')
 stopifnot(all(required %in% names(rows)),all(c('issue','stage') %in% names(map)),
  !anyDuplicated(rows[c('issue','policy')]),!anyDuplicated(map$issue),
  length(reference_policy)==1,reference_policy %in% rows$policy,
  all(is.finite(as.matrix(rows[c('stake','gross','net','hits')]))),
  all(rows$stake>=0),all(rows$gross>=0),all(rows$hits>=0),
  all(abs(rows$gross-rows$stake-rows$net)<1e-7),!anyNA(map$stage))
 ref<-rows[rows$policy==reference_policy,required]
 stopifnot(setequal(ref$issue,map$issue))
 for(p in unique(rows$policy))stopifnot(setequal(rows$issue[rows$policy==p],ref$issue))
 names(ref)[-(1:2)]<-paste0('reference_',names(ref)[-(1:2)])
 paired<-rows |> dplyr::left_join(dplyr::select(ref,-policy),by='issue',relationship='many-to-one') |>
  dplyr::left_join(dplyr::select(map,issue,stage),by='issue',relationship='many-to-one') |>
  dplyr::mutate(delta_stake=stake-reference_stake,delta_gross=gross-reference_gross,
   delta_net=net-reference_net,rescued=hits>0 & reference_hits==0,
   lost=hits==0 & reference_hits>0,improved=delta_net>1e-7,worse=delta_net< -1e-7)
 summary<-dplyr::bind_rows(paired,dplyr::mutate(paired,stage='ALL')) |>
  dplyr::group_by(policy,stage) |>
  dplyr::summarise(issues=dplyr::n(),delta_stake=sum(delta_stake),
   delta_gross=sum(delta_gross),delta_net=sum(delta_net),rescued=sum(rescued),
   lost=sum(lost),improved=sum(improved),worse=sum(worse),
   unchanged=issues-improved-worse,.groups='drop')
 stopifnot(all(abs(summary$delta_net-summary$delta_gross+summary$delta_stake)<1e-6))
 list(paired=paired,summary=summary)
}
