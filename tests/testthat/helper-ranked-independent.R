# Shared fixture preparation only; all numerical oracles stay in independent tests.
IndependentRankedPool <- function(p, cutoff, settings, pattern, max_candidates=1L, sp=NULL) {
  matches <- if (!nrow(p)) tibble::tibble(fixture_id=character(),win=double(),draw=double(),lose=double()) else tidyr::pivot_wider(p,names_from=outcome,values_from=probability) |>
    dplyr::rename(win=W,draw=D,lose=L)
  ranked <- beidan::rank_outcome_selections(beidan::prepare_outcome_selections(matches),cutoff)
  if (is.null(sp)) sp <- beidan:::match_typed_empty("prematch_sp")
  beidan::parlay_construct_role_groups(ranked,settings,pattern,max_candidates=max_candidates,prematch_sp=sp)
}
IndependentEvaluate <- function(pool, ...) beidan::parlay_evaluate_portfolio(pool,
  reuse_policy=list(max_reuse=4L),overlap_policy=list(max_overlap=3L),improve=FALSE,...)
