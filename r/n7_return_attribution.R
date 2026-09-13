# Descriptive accounting of frozen funded prefixes; no selection or fitting.
# funded: unique issue/arm/seed/sleeve_id, depth, stake, expected_gross,
# coverage and explicit copies. evidence: unique issue/sleeve_id with actual_rank,
# estimated_actual_payout and actual_gross_cny (both include ticket factor once).
# All currency is CNY. Missing/invalid or unmatched evidence fails; empty inputs
# return typed empty tables. Returns sleeve bridges and issue aggregates; no IO.
n7_return_attribution <- function(funded,evidence,unit_cny) {
  stopifnot(identical(unit_cny,2) || identical(unit_cny,2L))
  keys <- c('issue','arm','seed','sleeve_id')
  fcols <- c(keys,'depth','stake','expected_gross','coverage','copies')
  ecols <- c('issue','sleeve_id','actual_rank','estimated_actual_payout','actual_gross_cny')
  stopifnot(all(fcols %in% names(funded)),all(ecols %in% names(evidence)),
    !anyNA(funded[fcols]),!anyNA(evidence[ecols]),
    !anyDuplicated(funded[keys]),!anyDuplicated(evidence[c('issue','sleeve_id')]),
    all(is.finite(as.matrix(funded[c('depth','stake','expected_gross','coverage','copies')]))),
    all(is.finite(as.matrix(evidence[c('actual_rank','estimated_actual_payout','actual_gross_cny')]))),
    all(funded$copies>=1 & funded$copies==floor(funded$copies)),
    all(funded$depth>=1 & funded$depth<=2187 & funded$depth==floor(funded$depth)),
    all(funded$stake==unit_cny*funded$depth*funded$copies),
    all(funded$expected_gross>=0),all(funded$coverage>=0 & funded$coverage<=1),
    all(evidence$actual_rank>=1 & evidence$actual_rank<=2187 & evidence$actual_rank==floor(evidence$actual_rank)),
    all(evidence$estimated_actual_payout>0),all(evidence$actual_gross_cny>=0))
  z <- dplyr::left_join(funded,evidence[ecols],by=c('issue','sleeve_id'),relationship='many-to-one')
  stopifnot(!anyNA(z[ecols]))
  z <- z |> dplyr::mutate(hit=actual_rank<=depth,
    model_net=expected_gross-stake,
    estimated_hit_gross=as.numeric(hit)*estimated_actual_payout*copies,
    actual_gross=as.numeric(hit)*actual_gross_cny*copies,
    outcome_residual=estimated_hit_gross-expected_gross,
    price_residual=actual_gross-estimated_hit_gross,
    actual_net=actual_gross-stake)
  stopifnot(all(abs(z$actual_net-z$model_net-z$outcome_residual-z$price_residual)<1e-7))
  periods <- z |> dplyr::group_by(issue,arm,seed) |> dplyr::summarise(
    stake=sum(stake),model_net=sum(model_net),
    estimated_hit_gross=sum(estimated_hit_gross),actual_gross=sum(actual_gross),
    outcome_residual=sum(outcome_residual),price_residual=sum(price_residual),
    actual_net=sum(actual_net),group_hits=sum(hit),expected_group_hits=sum(coverage),.groups='drop')
  list(groups=z,periods=periods)
}
