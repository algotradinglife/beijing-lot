#' Replace probabilities only for fixtures with zero signed handicap
#' @param probabilities Complete probability tibble keyed fixture_id/outcome W/D/L.
#' @param euro_probabilities Complete normalized euro probability tibble on the
#'   same universe; prematch source admission belongs to the supplied snapshot.
#' @param fixtures Tibble with unique fixture_id and finite numeric handicap.
#' @return Complete probability tibble in input order; zero-handicap rows use
#'   euro probabilities, all other rows remain identical. No IO, labels, fitting,
#'   cutoff changes or deployment. Invalid/mismatched/empty inputs fail.
ReplaceZeroHandicapProbability <- function(probabilities,euro_probabilities,fixtures) {
  # Reuse the authoritative complete-triple and matched-universe contract.
  BlendMatchProbabilities(probabilities,euro_probabilities,0)
  checkmate::assert_tibble(fixtures,min.rows=1L)
  stopifnot(all(c("fixture_id","handicap") %in% names(fixtures)),
    is.character(fixtures$fixture_id),!anyNA(fixtures$fixture_id),
    !anyDuplicated(fixtures$fixture_id),all(nzchar(fixtures$fixture_id)),
    is.numeric(fixtures$handicap),all(is.finite(fixtures$handicap)),
    nrow(probabilities)>0,nrow(euro_probabilities)>0,
    setequal(probabilities$fixture_id,fixtures$fixture_id),
    setequal(euro_probabilities$fixture_id,fixtures$fixture_id))
  out <- probabilities |> dplyr::left_join(
    euro_probabilities |> dplyr::select(fixture_id,outcome,euro=probability),
    by=c("fixture_id","outcome"),relationship="one-to-one") |>
    dplyr::left_join(dplyr::select(fixtures,fixture_id,handicap),by="fixture_id",relationship="many-to-one") |>
    dplyr::mutate(probability=dplyr::if_else(handicap==0,euro,probability)) |>
    dplyr::select(dplyr::all_of(names(probabilities)))
  match_validate_table(out,"probabilities")
  return(out)
}
