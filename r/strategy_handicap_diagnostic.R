# Descriptive class diagnostics, never fitting or selection. frame follows
# strategy_probability_diagnostics; strata must include the signed handicap.
# Positive handicap adds goals to the home score. outcomes declares tie order.
# Returns cells (stratum/model/outcome), paired fixture scores and calibration.
# Rates are fractions; absent selections/actual outcomes have NA conditional
# rates. Empty, inconsistent probabilities/identities/strata fail via the shared
# validator. No I/O or side effects. Source strategy_diagnostic_probabilities.R.
strategy_handicap_diagnostic <- function(frame, strata, outcomes, breaks) {
  stopifnot('handicap' %in% strata, is.numeric(frame$handicap),
    all(is.finite(frame$handicap)), all(frame$handicap == trunc(frame$handicap)))
  checked <- strategy_probability_diagnostics(frame, strata, outcomes, breaks)
  z <- frame |>
    dplyr::mutate(class_order=match(outcome,outcomes), hit=outcome==actual_outcome) |>
    dplyr::group_by(issue,slot,provider_id,model) |>
    dplyr::arrange(dplyr::desc(probability),class_order,.by_group=TRUE) |>
    dplyr::mutate(rank=dplyr::row_number()) |> dplyr::ungroup()
  cells <- z |> dplyr::group_by(dplyr::across(dplyr::all_of(c(strata,'model','outcome')))) |>
    dplyr::summarise(fixtures=dplyr::n(),issues=dplyr::n_distinct(issue),
      expected=sum(probability),actual=sum(hit),predicted=mean(probability),
      observed=mean(hit),gap=mean(hit-probability),brier=mean((probability-hit)^2),
      top1_selected=sum(rank==1),top1_hits=sum(hit & rank==1),
      top2_selected=sum(rank<=2),top2_hits=sum(hit & rank<=2),
      top2_misses=sum(hit & rank==3),.groups='drop') |>
    dplyr::mutate(top1_precision=top1_hits/dplyr::na_if(top1_selected,0L),
      top1_recall=top1_hits/dplyr::na_if(actual,0L),
      top2_recall=top2_hits/dplyr::na_if(actual,0L))
  list(cells=cells,scores=checked$scores,summary=checked$summary,
    calibration=checked$calibration)
}
