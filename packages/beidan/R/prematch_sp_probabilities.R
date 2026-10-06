#' Convert observed prematch SP into normalized inverse-SP probabilities
#' @param prematch_sp Tibble keyed fixture_id/outcome, positive finite sp_raw,
#'   POSIXct quote_at strictly before explicit cutoff; complete W/D/L per fixture.
#' @param cutoff Explicit issue decision cutoff. Missing/invalid evidence fails.
#' @return Probability tibble keyed fixture_id/outcome, normalized to one. No IO,
#'   labels, fitting or clock. This is a market proxy, not calibrated probability.
#' @export
PrematchSPProbabilities <- function(prematch_sp,cutoff) {
 match_require_cutoff(cutoff)
 match_validate_table(prematch_sp,"prematch_sp",keys=c("fixture_id","outcome"))
 prematch_sp <- tibble::as_tibble(prematch_sp)
 if (!is.null(dim(prematch_sp$sp_raw)) || !is.null(attr(prematch_sp$sp_raw,"class"))) {
  stop("sp_raw must be a plain double column")
 }
 match_check_character_id(prematch_sp$fixture_id,"fixture_id")
 match_check_character_id(prematch_sp$source_url,"source_url")
 stopifnot(nrow(prematch_sp)>0,!anyNA(prematch_sp$sp_raw),
  all(is.finite(prematch_sp$sp_raw)),all(prematch_sp$sp_raw>0),
  !anyNA(prematch_sp$quote_at),all(is.finite(as.numeric(prematch_sp$quote_at))),
  all(prematch_sp$quote_at<cutoff$cutoff_utc))
 counts <- prematch_sp |> dplyr::count(fixture_id)
 stopifnot(all(counts$n==3L),all(prematch_sp$outcome %in% c("W","D","L")))
 out <- prematch_sp |> dplyr::group_by(fixture_id) |>
  dplyr::mutate(probability=(min(sp_raw)/sp_raw)/sum(min(sp_raw)/sp_raw)) |>
  dplyr::ungroup() |> dplyr::select(fixture_id,outcome,probability)
 match_validate_table(out,"probabilities")
 return(out)
}

