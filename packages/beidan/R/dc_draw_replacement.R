#' Replace the DC handicap draw mass while retaining its win/loss ratio
#' @param dc,bd Complete probability tibbles, keyed by fixture_id/outcome (W/D/L),
#'   probabilities in 0--1 summing to one. bd is an already normalized prematch
#'   inverse-SP proxy; the caller binds both inputs to their frozen cutoff.
#' @return Probability tibble with D=bd_D and W/L=(1-bd_D)*dc_W/L/(dc_W+dc_L).
#' @details Pure fixed arithmetic, no labels, fitting, selection, I/O or caches.
#'   Empty, invalid, incomplete or mismatched inputs fail. If DC has zero W+L
#'   and bd_D<1, its W:L ratio is undefined and the function fails; bd_D=1
#'   yields W=L=0. This descriptive transformation is not a fitted score model.
ReplaceDcDrawProbability <- function(dc, bd) {
  for (p in list(dc, bd)) {
    checkmate::assert_tibble(p, min.rows = 1L)
    match_validate_table(p, "probabilities", keys = c("fixture_id", "outcome"))
    if (!is.character(p$fixture_id) || anyNA(p) ||
        any(!nzchar(p$fixture_id)) || any(!is.finite(p$probability)) ||
        any(!p$outcome %in% c("W", "D", "L"))) stop("Invalid probability input")
    groups <- p |> dplyr::group_by(fixture_id) |>
      dplyr::summarise(n = dplyr::n(), mass = sum(probability), .groups = "drop")
    if (any(groups$n != 3L) || any(abs(groups$mass - 1) > 1e-8)) {
      stop("Incomplete probability triples")
    }
  }
  if (!setequal(dc$fixture_id, bd$fixture_id)) stop("Mismatched fixture universe")
  masses <- dc |> dplyr::filter(outcome != "D") |>
    dplyr::group_by(fixture_id) |> dplyr::summarise(non_draw = sum(probability), .groups = "drop") |>
    dplyr::inner_join(bd |> dplyr::filter(outcome == "D") |>
      dplyr::select(fixture_id, bd_draw = probability), by = "fixture_id", relationship = "one-to-one")
  if (any(masses$non_draw == 0 & masses$bd_draw < 1)) stop("Undefined DC win/loss ratio")
  out <- dc |> dplyr::select(fixture_id, outcome, probability) |>
    dplyr::left_join(masses, by = "fixture_id", relationship = "many-to-one")
  nondraw <- out$outcome != "D"
  usable <- nondraw & out$non_draw > 0
  out$probability[out$outcome == "D"] <- out$bd_draw[out$outcome == "D"]
  out$probability[usable] <- (1-out$bd_draw[usable]) * out$probability[usable] / out$non_draw[usable]
  out$probability[nondraw & out$non_draw == 0] <- 0
  return(out |> dplyr::select(fixture_id, outcome, probability))
}
