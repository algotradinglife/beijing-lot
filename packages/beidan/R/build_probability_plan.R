#' Build a receipt-bound plan using one declared probability basis throughout
#'
#' @param inputs Raw match input list from [read_match_inputs()]. Beidan requires
#'   fixtures, prematch_sp and match_status; euro/totals are unused and optional.
#' @param cutoff Explicit issue decision context with character issue_id and UTC
#'   POSIXct cutoff_utc. Mismatched issue/source chronology fails closed.
#' @param settings Explicit validated [parlay_settings()] list, including n_legs,
#'   issue_budget_cny, unit_cny, payout_factor and SP valuation policy. Not mutated.
#' @param group_budget_cny Nonnegative finite plain scalar CNY cap per group;
#'   whole-ticket depth is limited by this cap divided by settings$unit_cny.
#' @param base Exact beidan (default), dc, or mixed source used in every stage.
#' @param bd_weight Explicit plain scalar in [0,1] required only for mixed.
#' @param market_policy Euro/totals policies required for DC/mixed; ignored for BD.
#' @param model_config Fixed DC settings; ignored for Beidan.
#' @param single_threshold Plain probability threshold in [1/3,1], default .45.
#' @param top1_sp_threshold Minimum Top1 raw decimal SP, default 2. Equality
#'   is admitted; independent of settings$sp_threshold valuation policy.
#' @param pattern NULL for the adaptive target, or explicit integer roles 1:3
#'   with length settings$n_legs. Both modes use cross-category allocation.
#' @param window_hours Elapsed-hour fixture decision window, default c(4,28).
#' @param max_candidates Optional finite candidate cap; NULL keeps the full
#'   deterministic construction trajectory, not exhaustive global enumeration.
#' @param objective Exact coverage or ev criterion; default coverage.
#' @param min_group_ev_cny Optional minimum group marginal EV in CNY.
#' @param reuse_policy Explicit group fixture-reuse policy.
#' @param overlap_policy Explicit group overlap policy.
#' @return List with cutoff, probability_base, epoch, projected, filtered, ranked,
#'   adapted, pool, canonical plan, selection tibble, BET/NO_BET status and receipt.
#'   Probability tables use fixture_id/outcome W/D/L and unitless doubles. All
#'   explicit parameters, raw inputs, code and output bind the deterministic
#'   receipt. Empty admitted pools return NO_BET and typed empty tables.
#' @details No labels, historical fitting/tuning, IO, clock inference or session
#'   settings changes. Existing preparation, projection, filtering, classifier,
#'   allocation and funding implementations are reused. Do not reuse a DC-filtered
#'   epoch for a Beidan decision; this entry starts from the raw source tables.
#' @export
BuildProbabilityPlan <- function(inputs, cutoff, settings, group_budget_cny,
    base = "beidan", bd_weight = NULL, market_policy = NULL,
    model_config = list(rho=-.14,total_bounds=c(.1,16),tail_tolerance=1e-10),
    single_threshold = .45, top1_sp_threshold = 2, pattern = NULL, window_hours = c(4,28),
    max_candidates = NULL, objective = "coverage", min_group_ev_cny = NULL,
    reuse_policy = list(max_reuse=NULL), overlap_policy = list(max_overlap=NULL)) {
  match_require_cutoff(cutoff)
  parlay_validate_settings(settings)
  checkmate::assert_choice(base,c("beidan","dc","mixed"))
  checkmate::assert_choice(objective,c("coverage","ev"))
  checkmate::assert_number(group_budget_cny,lower=0,finite=TRUE)
  checkmate::assert_number(single_threshold,lower=1/3,upper=1,finite=TRUE)
  if (is.object(group_budget_cny) || !is.null(dim(group_budget_cny)) ||
      is.object(single_threshold) || !is.null(dim(single_threshold))) {
    stop("budget and threshold must be plain numeric scalars")
  }
  epoch <- prepare_match_inputs(inputs,decision_at=cutoff$cutoff_utc,
    market_policy=market_policy,window_hours=window_hours,probability_base=base)
  if (!identical(.rank_outcome_cutoff_hash(epoch$cutoff),.rank_outcome_cutoff_hash(cutoff))) {
    stop("prepared input cutoff differs from requested issue/time")
  }
  cutoff <- epoch$cutoff
  projected <- SelectProbabilityBase(epoch,base,bd_weight,model_config)
  parlay_projection_context(projected)
  matches <- if (nrow(projected$probabilities)) {
    projected$probabilities |>
      tidyr::pivot_wider(names_from=outcome,values_from=probability) |>
      dplyr::rename(win=W,draw=D,lose=L)
  } else tibble::tibble(fixture_id=character(),win=double(),draw=double(),lose=double())
  filtered <- filter_outcome_matches(matches,projected$prematch_sp,cutoff,
    sp_threshold=top1_sp_threshold)
  attr(filtered$matches,"filter_receipt") <- filtered$receipt
  ranked <- rank_outcome_selections(prepare_outcome_selections(filtered$matches,
    single_threshold=single_threshold),cutoff,priority="coverage")
  requested_groups <- if (group_budget_cny > 0 && !is.null(settings$issue_budget_cny))
    max(1L, ceiling(settings$issue_budget_cny / group_budget_cny)) else 1L
  adapted <- AdaptOutcomeSelections(ranked,settings$n_legs,pattern=pattern,
    requested_groups=requested_groups,max_reuse=reuse_policy$max_reuse)
  pool <- parlay_construct_role_groups(adapted$ranked,settings,adapted$pattern,
    max_candidates=max_candidates,prematch_sp=projected$prematch_sp)
  plan <- parlay_select_groups(pool,objective=objective,
    budget_cny=settings$issue_budget_cny,group_budget_cny=group_budget_cny,
    min_group_ev_cny=min_group_ev_cny,reuse_policy=reuse_policy,overlap_policy=overlap_policy)
  out <- list(cutoff=cutoff,probability_base=base,epoch=epoch,projected=projected,
    filtered=filtered,ranked=ranked,adapted=adapted,pool=pool,plan=plan,
    status=if(nrow(plan$selection))"BET" else "NO_BET",
    selection=tibble::as_tibble(plan$selection))
  parameters <- list(settings=settings,group_budget_cny=group_budget_cny,
    base=base,bd_weight=bd_weight,market_policy=epoch$market_policy,
    model_config=projected$model_config,single_threshold=single_threshold,
    top1_sp_threshold=top1_sp_threshold,pattern=pattern,
    window_hours=window_hours,max_candidates=max_candidates,objective=objective,
    min_group_ev_cny=min_group_ev_cny,reuse_policy=reuse_policy,overlap_policy=overlap_policy)
  snapshot <- list(inputs=inputs,cutoff=cutoff,parameters=parameters)
  input_hash <- rlang::hash(snapshot)
  code_hash <- .rank_outcome_code_hash(roots="BuildProbabilityPlan")
  out$receipt <- list(cutoff=cutoff,cutoff_hash=.rank_outcome_cutoff_hash(cutoff),
    input_snapshot=snapshot,input_hash=input_hash,parameters=parameters,
    implementation_hash=code_hash,output_hash=rlang::hash(out),
    cache_key=rlang::hash(list(cutoff,input_hash,code_hash)),
    historical_learning_inventory="NONE: fixed current-market source and category rules; no historical fitting or tuning")
  return(out)
}
