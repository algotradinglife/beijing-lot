# Retrospective decomposition of an already settled group ledger; no selection,
# fitting, deployable gate, or new tickets. threshold bins top128_coverage only.
# groups: unique issue/sleeve_id with depth,copies,stake,coverage,actual_rank,
# actual_gross_cny,hit,gross,net,top128_coverage. plans: one row per issue with
# stake,gross,net,budget_cny. Explicit unit CNY and complete chronological issue
# list required. Returns components, full cash-inclusive ledgers and equity.
# MAIN and LOW are held subsets of the original tickets; SCALED_ALL is a
# fractional accounting benchmark with the MAIN issue stake, not legal tickets.
# No payout factor is reapplied; actual_gross_cny already includes it once.
n7_component_accounting <- function(groups,plans,issue_order,threshold,unit_cny,initial_capital_cny) {
  stopifnot(length(threshold)==1,is.finite(threshold),threshold>0,threshold<1,
    length(unit_cny)==1,is.finite(unit_cny),unit_cny>0,
    all(c('issue','sleeve_id','depth','copies','stake','coverage','actual_rank','actual_gross_cny','hit','gross','net','top128_coverage') %in% names(groups)),
    all(c('issue','stake','gross','net','budget_cny') %in% names(plans)),nrow(plans)>0,
    !anyDuplicated(groups[c('issue','sleeve_id')]),!anyDuplicated(plans$issue),
    setequal(plans$issue,issue_order),all(groups$issue %in% plans$issue),
    !anyNA(groups),!anyNA(plans[c('issue','stake','gross','net','budget_cny')]))
  for(n in c('depth','copies','stake','coverage','actual_rank','actual_gross_cny','gross','net','top128_coverage'))
    stopifnot(is.numeric(groups[[n]]),all(is.finite(groups[[n]])))
  stopifnot(all(groups$depth>=1 & groups$depth<=2187 & groups$depth==trunc(groups$depth)),
    all(groups$copies>=1 & groups$copies==trunc(groups$copies)),
    all(groups$actual_rank>=1 & groups$actual_rank<=2187 & groups$actual_rank==trunc(groups$actual_rank)),
    all(groups$actual_gross_cny>=0),all(groups$coverage>=0 & groups$coverage<=1),
    all(groups$top128_coverage>=0 & groups$top128_coverage<=1),
    all(abs(groups$stake-unit_cny*groups$depth*groups$copies)<1e-7),
    all(groups$hit==(groups$actual_rank<=groups$depth)),
    all(abs(groups$gross-groups$hit*groups$copies*groups$actual_gross_cny)<1e-6),
    all(abs(groups$net-groups$gross+groups$stake)<1e-6))
  components<-groups |> dplyr::mutate(component=ifelse(top128_coverage>threshold,'MAIN','LOW'))
  sums<-groups |> dplyr::group_by(issue) |> dplyr::summarise(gs=sum(stake),gg=sum(gross),gn=sum(net),.groups='drop')
  p<-plans |> dplyr::left_join(sums,by='issue',relationship='one-to-one') |>
    dplyr::mutate(dplyr::across(c(gs,gg,gn),~tidyr::replace_na(.x,0)))
  stopifnot(all(abs(p$stake-p$gs)<1e-6),all(abs(p$gross-p$gg)<1e-6),all(abs(p$net-p$gn)<1e-6))
  pieces<-list()
  for(kind in c('ALL','MAIN','LOW')) {
    g<-if(kind=='ALL') components else dplyr::filter(components,component==kind)
    z<-g |> dplyr::group_by(issue) |> dplyr::summarise(stake=sum(stake),gross=sum(gross),.groups='drop')
    pieces[[kind]]<-plans |> dplyr::select(issue,budget_cny) |>
      dplyr::left_join(z,by='issue',relationship='one-to-one') |>
      dplyr::mutate(dplyr::across(c(stake,gross),~tidyr::replace_na(.x,0)),policy=kind)
  }
  scaled<-pieces$ALL
  target<-pieces$MAIN$stake[match(scaled$issue,pieces$MAIN$issue)]
  ratio<-ifelse(scaled$stake>0,target/scaled$stake,0)
  scaled$stake<-target;scaled$gross<-scaled$gross*ratio;scaled$policy<-'SCALED_ALL'
  ledger<-dplyr::bind_rows(c(pieces,list(SCALED_ALL=scaled))) |>
    dplyr::mutate(model='frozen-market-diagnostic',net=gross-stake,cash_cny=budget_cny-stake,
      status=ifelse(stake==0,'NO_BET','COMPLETE'))
  curves<-strategy_equity_curves(ledger,issue_order,initial_capital_cny)
  list(components=components,ledger=ledger,curves=curves)
}
