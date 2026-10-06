#' Compute the actual combination's rank in each original group support
#' @param evaluation Receipt-bound frozen evaluation, with explicit embedded cutoff.
#' @param match_results Canonical chronology-bearing match_results tibble.
#' @param as_of Explicit UTC observation instant; required for nonempty results.
#' @return Tibble keyed by group_id with theoretical (double) and winner_depth
#'   (integer). Depth is zero for a known structural miss, NA while the actual
#'   combination remains unknown, otherwise its one-based frozen support rank,
#'   including combinations outside the purchased prefix. No IO or reranking.
#' @noRd
.BettingSheetCombinationDepth <- function(evaluation, match_results, as_of=NULL) {
  .parlay_ranked_validate_evaluation(evaluation)
  match_validate_table(match_results,"match_results")
  if(nrow(match_results)==0L) {
    return(evaluation$group_selection |> dplyr::filter(.data$tickets>0L) |>
      dplyr::transmute(group_id, theoretical=as.double(.data$legal_space),
        winner_depth=NA_integer_))
  }
  diagnosed <- ParlayCoverageAttribution(evaluation,match_results,as_of)$groups
  return(diagnosed |> dplyr::transmute(group_id,theoretical=legal_space,
    winner_depth=dplyr::if_else(structural_misses>0L,0L,winner_rank)))
}

#' Summarise the best single purchased ticket's match depth per group
#' @param legs Tibble with order, ticket_id, fixture_id, outcome; one row per
#'   purchased ticket leg, unique by ticket_id/fixture_id. All group tickets must
#'   have the same fixture set. Nonempty; malformed identities fail closed.
#' @param results Tibble keyed by fixture_id, actual_outcome (W/D/L). Only
#'   observed, chronology-validated final outcomes, not predictions. Empty is valid.
#' @return Tibble keyed by order: total, observed, best_hits and winning_tickets.
#'   winning_tickets is NA until all group fixtures have outcomes. viable_tickets
#'   counts purchased tickets with no confirmed losing leg. group_status is DEAD
#'   when none survive, HIT when a full purchased ticket matches, otherwise PENDING.
#'   These result states never imply financial settlement. No IO or fitting.
#' @export
BettingSheetDepth <- function(legs, results) {
  stopifnot(tibble::is_tibble(legs),tibble::is_tibble(results),nrow(legs)>0L,
    all(c("order","ticket_id","fixture_id","outcome") %in% names(legs)),
    all(c("fixture_id","actual_outcome") %in% names(results)),
    !anyNA(legs[c("order","ticket_id","fixture_id","outcome")]),
    !anyNA(results[c("fixture_id","actual_outcome")]),
    all(legs$outcome %in% c("W","D","L")),
    all(results$actual_outcome %in% c("W","D","L")),
    !anyDuplicated(results$fixture_id),
    !anyDuplicated(legs[c("ticket_id","fixture_id")]))
  ticket_sets <- legs |> dplyr::arrange(fixture_id) |>
    dplyr::group_by(order,ticket_id) |>
    dplyr::summarise(fixtures=list(fixture_id),.groups="drop")
  for(k in unique(legs$order)) {
    sets <- dplyr::filter(ticket_sets,order==k)$fixtures
    stopifnot(all(vapply(sets,identical,logical(1),sets[[1]])))
  }
  matched <- legs |> dplyr::left_join(results,by="fixture_id",relationship="many-to-one")
  counts <- matched |> dplyr::group_by(order,ticket_id) |>
    dplyr::summarise(total=dplyr::n(),observed=sum(!is.na(actual_outcome)),
      hits=sum(outcome==actual_outcome,na.rm=TRUE),.groups="drop")
  depth <- counts |> dplyr::group_by(order) |>
    dplyr::summarise(total=dplyr::first(total),observed=dplyr::first(observed),
      best_hits=max(hits),viable_tickets=as.integer(sum(hits==observed)),winning_tickets=if(dplyr::first(observed)==dplyr::first(total))
        as.integer(sum(hits==total)) else NA_integer_,.groups="drop") |>
    dplyr::mutate(group_status=dplyr::case_when(
      viable_tickets==0L ~ "DEAD",
      !is.na(winning_tickets) & winning_tickets>0L ~ "HIT",
      TRUE ~ "PENDING"))
  return(depth)
}

#' Prepare audited betting-sheet display data without changing purchases
#' @param frozen Audited frozen research plan bundle; pattern tables and bound
#'   frozen selector/prefix receipt. Nonempty ordered groups and unique tickets.
#' @param prepared Audited prematch input bundle with projected prematch_sp tibble
#'   keyed by fixture_id/outcome, numeric sp_raw and POSIXct quote_at strictly
#'   before decision_at. Missing SP rows/NA show as missing; bad values fail.
#' @param pattern Character bundle key; never shown as a suggested structure.
#' @param settlements NULL or a canonical settlements tibble; validated by beidan.
#'   Its optional match_results attribute is a canonical independent final-score
#'   tibble; SP may remain unpublished. Only monetary columns use settlements.
#' @param as_of Explicit UTC POSIXct observation time, required with settlements.
#' @return List(groups,tickets,legs,prefixes,options,depth,returns,budget_results).
#'   depth includes theoretical support size and winner_depth: one-based actual
#'   combination rank, zero for structural exclusion, NA while unknown.
#'   Each table is a tibble. returns/budget_results are NULL without settlement;
#'   actual_outcome and settled_sp in options are NA for unobserved results.
#'   Monetary amounts are CNY. No IO, selection, fitting or current-clock inference.
#' @details Delegates payouts exclusively to SettleResearchBudgetPrefixes and
#'   parlay_settle_plan. Contradictory keys/counts, chronology and receipts fail.
#' @export
BuildBettingSheetView <- function(frozen, prepared, pattern, settlements=NULL, as_of=NULL) {
  stopifnot(is.character(pattern),length(pattern)==1L,pattern %in% names(frozen$groups),
    identical(frozen$decision_at,prepared$decision_at))
  groups <- frozen$groups[[pattern]] |> dplyr::arrange(order)
  tickets <- frozen$tickets[[pattern]] |> dplyr::arrange(order,rank)
  legs <- frozen$ticket_legs[[pattern]]
  prefixes <- frozen$prefixes[[pattern]]
  stopifnot(tibble::is_tibble(groups),tibble::is_tibble(tickets),
    tibble::is_tibble(legs),tibble::is_tibble(prefixes),nrow(groups)>0L,
    identical(groups$order,seq_len(nrow(groups))),!anyDuplicated(groups$group_id),
    nrow(tickets)>0L,!anyDuplicated(tickets$ticket_id),
    !anyNA(tickets$cost_cny),all(is.finite(tickets$cost_cny)),all(tickets$cost_cny>0),
    setequal(tickets$order,groups$order),setequal(legs$ticket_id,tickets$ticket_id))
  owned <- tickets |> dplyr::count(order,wt=cost_cny,name="cost")
  counts <- tickets |> dplyr::count(order,name="count")
  stopifnot(identical(as.integer(counts$count),as.integer(groups$new_ticket_count)),
    isTRUE(all.equal(owned$cost,groups$new_cost_cny)),
    isTRUE(all.equal(cumsum(owned$cost),groups$cumulative_cost_cny)))
  ledger <- legs |> dplyr::distinct(ticket_id,order,group_id)
  stopifnot(nrow(ledger)==nrow(tickets),
    nrow(dplyr::anti_join(ledger,tickets,by=c("ticket_id","order","group_id")))==0L)
  authority <- frozen$frozen[[pattern]]$selected$evaluation
  stopifnot(nrow(dplyr::anti_join(legs,authority$plan$ticket_legs,
    by=c("ticket_id","fixture_id","outcome")))==0L,
    nrow(dplyr::anti_join(tickets,authority$purchases,
      by=c("ticket_id","group_id","rank","cost_cny")))==0L)
  sp <- prepared$projected$prematch_sp
  stopifnot(tibble::is_tibble(sp),!anyDuplicated(sp[c("fixture_id","outcome")]),
    !anyNA(sp[c("fixture_id","outcome","quote_at")]),
    inherits(sp$quote_at,"POSIXct"),all(sp$quote_at<frozen$decision_at),
    all(sp$outcome %in% c("W","D","L")),is.numeric(sp$sp_raw),
    !any(is.nan(sp$sp_raw)),
    all(is.na(sp$sp_raw) | (is.finite(sp$sp_raw) & sp$sp_raw>0)))
  # Count original allowed outcomes, not the post-selection option union.
  original <- frozen$frozen[[pattern]]$selected$evaluation$portfolio$group_patterns
  shape <- original |> dplyr::transmute(group_id,
    original_pattern=vapply(actual_pattern,paste,character(1),collapse=""),
    theoretical=vapply(actual_pattern,prod,numeric(1)))
  groups <- groups |> dplyr::left_join(shape,by="group_id",relationship="one-to-one")
  stopifnot(!anyNA(groups$theoretical),all(groups$actual_pattern==groups$original_pattern))
  results <- tibble::tibble(fixture_id=character(),actual_outcome=character(),settled_sp=double())
  returns <- NULL
  budget_results <- NULL
  if (!is.null(settlements)) {
    match_validate_table(settlements,"settlements")
    checkmate::assert_posixct(as_of,len=1L,any.missing=FALSE)
    stopifnot(identical(attr(as_of,"tzone"),"UTC"))
    evaluated <- SettleResearchBudgetPrefixes(frozen$frozen[[pattern]],settlements,as_of)
    returns <- evaluated$settled$ticket_returns
    budget_results <- evaluated$summary
    results <- settlements |> dplyr::filter(issue_id==authority$plan$issue_id,label_available_at<=as_of,status=="settled") |>
      dplyr::transmute(fixture_id,actual_outcome=outcome,settled_sp)
    stopifnot(!anyDuplicated(results$fixture_id),
      setequal(returns$ticket_id,tickets$ticket_id))
  }
  observed <- if(is.null(settlements)) NULL else attr(settlements,"match_results")
  if(!is.null(observed)) {
    match_validate_table(observed,"match_results")
    stopifnot(!anyNA(observed),all(observed$outcome %in% c("W","D","L")))
    observed <- observed |> dplyr::filter(issue_id==authority$plan$issue_id,result_available_at<=as_of) |>
      dplyr::transmute(fixture_id,actual_outcome=outcome)
    stopifnot(!anyDuplicated(observed$fixture_id))
    common <- dplyr::inner_join(observed,results,by="fixture_id",suffix=c("_score","_sp"),relationship="one-to-one")
    stopifnot(all(common$actual_outcome_score==common$actual_outcome_sp))
    # Financial settlement also confirms a result; union preserves that evidence.
    results <- dplyr::bind_rows(results,dplyr::anti_join(observed,results,by="fixture_id") |>
      dplyr::mutate(settled_sp=NA_real_))
  }
  catalog <- legs |> dplyr::distinct(order,fixture_id,slot,home_name,away_name,handicap,kickoff_beijing)
  stopifnot(!anyDuplicated(catalog[c("order","fixture_id")]))
  chosen <- legs |> dplyr::distinct(order,fixture_id,outcome) |> dplyr::mutate(selected=TRUE)
  options <- tidyr::crossing(catalog,outcome=c("W","D","L")) |>
    dplyr::left_join(sp |> dplyr::select(fixture_id,outcome,sp_raw),
      by=c("fixture_id","outcome"),relationship="many-to-one") |>
    dplyr::left_join(chosen,by=c("order","fixture_id","outcome"),relationship="one-to-one") |>
    dplyr::left_join(results,by="fixture_id",relationship="many-to-one") |>
    dplyr::mutate(selected=tidyr::replace_na(selected,FALSE),
      result=tidyr::replace_na(outcome==actual_outcome,FALSE))
  canonical_results <- match_typed_empty("match_results")
  if(!is.null(settlements)) {
    canonical_results <- settlements |>
      dplyr::filter(issue_id==authority$cutoff$issue_id,status=="settled",label_available_at<=as_of) |>
      dplyr::transmute(issue_id,fixture_id,outcome,result_available_at=label_available_at,source_url)
    score_results <- attr(settlements,"match_results")
    if(!is.null(score_results)) {
      score_results <- score_results |> dplyr::filter(issue_id==authority$cutoff$issue_id,result_available_at<=as_of)
      canonical_results <- dplyr::bind_rows(score_results,
        dplyr::anti_join(canonical_results,score_results,by="fixture_id"))
    }
  }
  combination_depth <- .BettingSheetCombinationDepth(authority,canonical_results,as_of)
  depth <- BettingSheetDepth(legs,dplyr::select(results,fixture_id,actual_outcome)) |>
    dplyr::left_join(dplyr::select(groups,order,group_id),by="order",relationship="one-to-one") |>
    dplyr::left_join(combination_depth,by="group_id",relationship="one-to-one")
  out <- list(groups=groups,tickets=tickets,legs=legs,prefixes=prefixes,
    options=options,depth=depth,returns=returns,budget_results=budget_results)
  out$receipt <- list(cutoff=authority$cutoff,input_hash=rlang::hash(list(frozen,prepared,pattern,settlements,as_of)),
    output_hash=rlang::hash(out),code_hash=.rank_outcome_code_hash("BuildBettingSheetView"))
  return(out)
}
