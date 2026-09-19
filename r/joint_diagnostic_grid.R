# Complete a descriptive probability x estimated-payout grid from verified
# joint_ticket_calibration() types. Explicit category order and display-support
# floors; these are not significance tests or future allocation gates. CNY money.
# Empty cells are NO_PURCHASE, not zero-return failures. No fitting or IO.
joint_diagnostic_grid <- function(types,probability_levels,payout_levels,
                                 minimum_issues,minimum_expected_hits) {
 keys<-c('policy','stage','band','payout_band')
 stopifnot(!anyDuplicated(types[keys]),!anyNA(types[keys]),
  !anyDuplicated(probability_levels),!anyDuplicated(payout_levels),
  all(types$band %in% probability_levels),all(types$payout_band %in% payout_levels),
  all(is.finite(as.matrix(types[c('tickets','issues','expected_hits','actual_hits','stake','gross')]))),
  all(types$tickets>0),all(types$issues>0),all(types$issues<=types$tickets),
  all(types$actual_hits>=0 & types$actual_hits<=types$tickets),
  all(types$expected_hits>=0 & types$expected_hits<=types$tickets),
  all(types$stake>0),all(types$gross>=0),
  length(minimum_issues)==1,is.finite(minimum_issues),minimum_issues>=1,
  length(minimum_expected_hits)==1,is.finite(minimum_expected_hits),minimum_expected_hits>0)
 out<-tidyr::crossing(policy=unique(types$policy),stage=unique(types$stage),
  band=probability_levels,payout_band=payout_levels) |>
  dplyr::left_join(types,by=keys,relationship='one-to-one') |>
  dplyr::mutate(empty=is.na(tickets)) |>
  dplyr::mutate(dplyr::across(c(tickets,issues,expected_hits,actual_hits,stake,gross),~tidyr::replace_na(.x,0))) |>
  dplyr::group_by(policy,stage) |>
  dplyr::mutate(stake_share=if(sum(stake)>0)stake/sum(stake) else NA_real_) |>
  dplyr::ungroup() |>
  dplyr::mutate(mean_probability=ifelse(tickets>0,expected_hits/tickets,NA_real_),
   hit_rate=ifelse(tickets>0,actual_hits/tickets,NA_real_),
   hit_ratio=ifelse(expected_hits>0,actual_hits/expected_hits,NA_real_),
   net=gross-stake,roi=ifelse(stake>0,net/stake,NA_real_),
   diagnosis=dplyr::case_when(empty~'NO_PURCHASE',
    issues<minimum_issues | expected_hits<minimum_expected_hits~'LOW_SUPPORT',
    hit_ratio<1~'HIT_SHORTFALL',roi<0~'PAYOUT_SHORTFALL',TRUE~'HIT_AND_RETURN_OK'),
   band=factor(band,levels=probability_levels),payout_band=factor(payout_band,levels=payout_levels))
 out
}
