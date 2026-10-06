#' Blend two complete match probability distributions with a fixed weight
#' @param dc,bd Probability tibbles keyed fixture_id/outcome, complete W/D/L,
#'   finite probabilities in 0--1 summing to one. Same fixture universe.
#' @param bd_weight Explicit finite numeric scalar in 0--1, chosen by the caller.
#' @return Probability tibble with (1-bd_weight)*dc + bd_weight*bd, in dc row order.
#' @details Pure arithmetic, no labels, fitting, selection, chronology or I/O.
#'   Empty, duplicate, incomplete, invalid or mismatched inputs fail. Caller binds
#'   prematch sources and cutoff separately; this function never learns weights.
BlendMatchProbabilities <- function(dc, bd, bd_weight) {
  checkmate::assert_number(bd_weight,lower=0,upper=1,finite=TRUE)
  for (p in list(dc,bd)) {
    checkmate::assert_tibble(p,min.rows=1L)
    match_validate_table(p,"probabilities",keys=c("fixture_id","outcome"))
    groups <- p |> dplyr::group_by(fixture_id) |>
      dplyr::summarise(n=dplyr::n(),mass=sum(probability),.groups="drop")
    if (anyNA(p) || !is.character(p$fixture_id) || any(!nzchar(p$fixture_id)) ||
        any(!p$outcome %in% c("W","D","L")) || any(!is.finite(p$probability)) ||
        any(groups$n!=3L) || any(abs(groups$mass-1)>1e-8)) stop("Invalid complete probability triples")
  }
  if (!setequal(dc$fixture_id,bd$fixture_id)) stop("Mismatched fixture universe")
  out <- dc |> dplyr::select(fixture_id,outcome,dc=probability) |>
    dplyr::left_join(bd |> dplyr::select(fixture_id,outcome,bd=probability),
      by=c("fixture_id","outcome"),relationship="one-to-one") |>
    dplyr::transmute(fixture_id,outcome,probability=(1-bd_weight)*dc+bd_weight*bd)
  return(out)
}
