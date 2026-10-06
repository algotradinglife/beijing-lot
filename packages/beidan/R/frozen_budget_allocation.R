#' Rank support with equal scoring weights on actual triple masks
#' @param space Enumerated group support with authoritative ticket probabilities.
#' @param block Validated role legs for this group.
#' @param probabilities Validated frozen fixture/outcome probability tibble.
#' @return Support with reordered ranks; probabilities and valuations unchanged.
#' @noRd
.UniformTripleRanking <- function(space, block, probabilities) {
  triples <- block$fixture_id[block$n_outcomes==3L]
  scores <- space$tickets$ticket_legs |>
    dplyr::left_join(dplyr::select(probabilities,fixture_id,outcome,probability),
      by=c("fixture_id","outcome"),relationship="many-to-one") |>
    dplyr::mutate(weight=dplyr::if_else(.data$fixture_id %in% triples,1/3,.data$probability)) |>
    dplyr::group_by(.data$ticket_id) |>
    dplyr::summarise(score=prod(.data$weight),.groups="drop")
  stopifnot(!anyNA(scores$score),setequal(scores$ticket_id,space$ranked$ticket_id))
  ranked <- space$ranked |> dplyr::left_join(scores,by="ticket_id",relationship="one-to-one") |>
    dplyr::arrange(dplyr::desc(.data$score),.data$ticket_id) |>
    dplyr::mutate(rank=as.integer(dplyr::row_number())) |> dplyr::select(-score)
  space$ranked <- ranked
  return(space)
}

#' Allocate unique tickets within a fixed set of admitted groups
#' @param pool Validated frozen pool.
#' @param group_ids Frozen admitted group identifiers.
#' @param budget_cny Finite nonnegative total CNY ceiling.
#' @param group_budget_cny Optional CNY ceiling per owner group.
#' @param method equal or probability; ties use group_id then ticket_id.
#' @param triple_ranking beidan retains source ranking; uniform scores actual
#'   triple legs equally without changing authoritative probability or valuation.
#' @return Authoritative funding ledger with typed empty tables. No labels or IO.
#' @noRd
.AllocateFrozenTickets <- function(pool, group_ids, budget_cny, group_budget_cny, method, triple_ranking="beidan") {
  prepared <- .PrepareRankedFunding(pool,group_budget_cny)
  nominal <- prepared$nominal |> dplyr::filter(.data$group_id %in% group_ids) |>
    dplyr::arrange(.data$group_id)
  spaces <- prepared$spaces[nominal$group_id]
  if(triple_ranking=="uniform") for(i in seq_len(nrow(nominal))) {
    block <- pool$legs |> dplyr::filter(.data$group_id==nominal$group_id[i])
    spaces[[i]] <- .UniformTripleRanking(spaces[[i]],block,pool$probabilities)
    nominal$nominal_coverage[i] <- sum(utils::head(spaces[[i]]$ranked$probability,nominal$group_units[i]))
  }
  count <- integer(nrow(nominal));cursor <- rep(1L,nrow(nominal));bought <- character()
  rows <- list();leg_rows <- list()
  units <- floor(budget_cny/pool$settings$unit_cny+1e-9)
  while(length(bought)<units && nrow(nominal)) {
    heads <- rep(NA_integer_,nrow(nominal))
    for(i in seq_len(nrow(nominal))) {
      ranked <- spaces[[i]]$ranked
      while(cursor[i]<=nrow(ranked) && ranked$ticket_id[cursor[i]] %in% bought) cursor[i] <- cursor[i]+1L
      if(count[i]<nominal$group_units[i] && cursor[i]<=nrow(ranked)) heads[i] <- cursor[i]
    }
    eligible <- which(!is.na(heads));if(!length(eligible)) break
    scores <- if(method=="equal") -count[eligible] else vapply(eligible,
      function(i) spaces[[i]]$ranked$probability[heads[i]],numeric(1))
    i <- eligible[order(-scores,nominal$group_id[eligible],method="radix")][1L]
    ticket <- spaces[[i]]$ranked[heads[i],]
    owned <- ticket |> dplyr::transmute(group_slot=nominal$group_slot[i],group_id=nominal$group_id[i],
      ticket_id,rank=as.integer(rank),probability,cost_cny=as.numeric(pool$settings$unit_cny),sp_product_est,ev_net_est)
    rows[[length(rows)+1L]] <- owned
    leg_rows[[length(leg_rows)+1L]] <- spaces[[i]]$tickets$ticket_legs |>
      dplyr::filter(.data$ticket_id==ticket$ticket_id)
    bought <- c(bought,ticket$ticket_id);count[i] <- count[i]+1L;cursor[i] <- cursor[i]+1L
  }
  purchases <- if(length(rows)) dplyr::bind_rows(rows) else .parlay_ranked_empty_purchases()
  legs <- if(length(leg_rows)) dplyr::bind_rows(leg_rows) else match_typed_empty("ticket_legs")
  selection <- nominal |> dplyr::mutate(admitted=count>0L,tickets=as.integer(count),
    spent_cny=as.numeric(count*pool$settings$unit_cny),actual_coverage=vapply(.data$group_id,
      function(id)sum(purchases$probability[purchases$group_id==id]),numeric(1)),
    reason=dplyr::if_else(.data$admitted,"admitted","no_purchase"))
  return(list(spaces=spaces,nominal=nominal,purchases=purchases,ticket_legs=legs,
    selection=selection,rejections=.parlay_ranked_empty_rejections(),bought=bought,
    spent=sum(purchases$cost_cny),selected_groups=nominal$group_id[count>0L]))
}

#' Compare budget allocation without changing admitted masks or fixture groups
#' @param evaluation Frozen evaluation from parlay_select_groups(), with embedded
#'   cutoff and source receipts. Reallocation of an already allocated result errors.
#' @param budget_cny Explicit finite nonnegative CNY ceiling.
#' @param method equal (balanced ticket counts) or probability (highest next-ticket
#'   frozen joint probability). Stable ties use group_id. Default equal.
#' @param group_budget_cny Optional finite nonnegative CNY owner-group ceiling;
#'   NULL allows the full legal support. Cash below one unit remains unspent.
#' @param triple_ranking beidan (original probabilities) or uniform (1/3 scoring
#'   weights for actual triple legs only). Ticket probabilities/EV stay original.
#'   Equal scores use canonical ticket_id and can concentrate triple outcomes.
#' @return Standard frozen evaluation with allocation tibble and replay-bound
#'   receipt. Allocation has one row per original admitted group, including zero
#'   purchases, legal_space, tickets, spent_cny, actual_coverage and pattern.
#' @details The universe is the source evaluation's admitted groups, not all
#'   candidates. Each physical ticket is paid once and owned by its first buyer;
#'   duplicates are skipped and depth refilled. Equal visits groups with the
#'   smallest owned count; probability visits the highest available next ticket.
#'   Neither maximizes exact union hit probability across overlapping fixtures.
#'   Fixed policies, no historical fitting, labels, IO, clock or mutable globals.
#' @export
AllocateParlayBudget <- function(evaluation,budget_cny,method="equal",group_budget_cny=NULL,triple_ranking="beidan") {
  pool <- .parlay_ranked_validate_evaluation(evaluation)
  if(!identical(evaluation$receipt$producer,"parlay_select_groups")) stop("allocation needs original selected evaluation")
  checkmate::assert_choice(method,c("equal","probability"))
  checkmate::assert_choice(triple_ranking,c("beidan","uniform"))
  budget_cny <- .parlay_role_validate_budget(budget_cny,"budget_cny")
  if(is.null(budget_cny)) stop("allocation requires finite budget_cny")
  group_budget_cny <- .parlay_role_validate_budget(group_budget_cny,"group_budget_cny")
  if(budget_cny/pool$settings$unit_cny>.Machine$integer.max) stop("allocation ticket count exceeds integer range")
  group_ids <- sort(unique(evaluation$purchases$group_id),method="radix")
  fund <- .AllocateFrozenTickets(pool,group_ids,budget_cny,group_budget_cny,method,triple_ranking)
  out <- .FinalizeRankedEvaluation(evaluation$portfolio,pool,fund,budget_cny,group_budget_cny,
    evaluation$receipt$reuse_policy,evaluation$receipt$overlap_policy,
    producer="AllocateParlayBudget",objective="coverage",order_rule=method,
    dynamic_resort=TRUE,selection_policy=list(method=method,triple_ranking=triple_ranking,group_ids=group_ids,
      source_evaluation=evaluation,source_hash=rlang::hash(evaluation)))
  out$allocation <- out$group_selection
  return(out)
}

#' Diagnose structure versus purchased depth on frozen tickets
#' @param evaluation Frozen selected or allocated evaluation with embedded cutoff.
#' @param match_results Canonical final W/D/L results with availability times.
#' @param as_of Explicit UTC observation time after cutoff.
#' @return List(groups,legs,receipt). groups includes coverage status, legal-space
#'   size, winner_rank, owned_tickets, best_hits, observed, viable_tickets and
#'   unbought_tickets_before_winner. The latter is hindsight, not a depth rule.
#'   Zero-purchase groups are NO_PURCHASE, not losses; unknown results stay pending.
#' @details Reuses ParlayCoverageAttribution and BettingSheetDepth. Additional
#'   tickets count excludes all globally owned physical tickets, including those
#'   owned elsewhere. No payouts, learning, selection, IO or label mutation.
#' @export
DiagnoseParlayDepth <- function(evaluation,match_results,as_of) {
  coverage <- ParlayCoverageAttribution(evaluation,match_results,as_of)
  pool <- .parlay_ranked_validate_evaluation(evaluation)
  groups <- coverage$groups
  leg <- evaluation$plan$ticket_legs |>
    dplyr::left_join(dplyr::select(evaluation$purchases,ticket_id,group_id),
      by="ticket_id",relationship="many-to-one") |>
    dplyr::left_join(dplyr::select(evaluation$group_selection,group_id,order=group_slot),
      by="group_id",relationship="many-to-one")
  visible <- match_results |> dplyr::filter(.data$result_available_at<=as_of) |>
    dplyr::transmute(fixture_id,actual_outcome=outcome)
  depth <- if(nrow(leg)) BettingSheetDepth(leg,visible) else tibble::tibble(
    order=integer(),total=integer(),observed=integer(),best_hits=integer(),
    viable_tickets=integer(),winning_tickets=integer(),group_status=character())
  groups <- groups |> dplyr::left_join(depth,by=c("group_slot"="order"),relationship="one-to-one")
  groups$unbought_tickets_before_winner <- vapply(seq_len(nrow(groups)),function(i) {
    if(is.na(groups$winner_rank[i])) return(NA_integer_)
    if(groups$status[i] %in% c("HIT","COVERED_ELSEWHERE")) return(0L)
    id <- groups$group_id[i]
    block <- pool$legs[pool$legs$group_id==id,]
    ranked <- .parlay_ranked_group_space(id,block,pool$probabilities,pool$prematch_sp,
      pool$cutoff,pool$settings,pool$n_legs)$ranked
    return(as.integer(sum(ranked$rank<=groups$winner_rank[i] & !ranked$ticket_id %in% evaluation$purchases$ticket_id)))
  },integer(1))
  zero <- evaluation$group_selection |> dplyr::filter(.data$tickets==0L) |>
    dplyr::transmute(group_id,group_slot,legal_space=as.double(legal_space),purchased_tickets=0L,
      status="NO_PURCHASE",unbought_tickets_before_winner=NA_integer_)
  groups <- dplyr::bind_rows(groups,zero) |> dplyr::arrange(.data$group_slot)
  return(list(groups=groups,legs=coverage$legs,receipt=list(cutoff=evaluation$cutoff,
    input_hash=rlang::hash(list(evaluation,match_results,as_of)),
    code_hash=.rank_outcome_code_hash("DiagnoseParlayDepth"),posthoc_diagnostic=TRUE)))
}

#' Settle comparable frozen allocation alternatives and diagnose depth
#' @param alternatives Named nonempty list of AllocateParlayBudget evaluations.
#'   They must share source evaluation, cutoff, total budget and per-group cap.
#' @param observation Explicit match_results, settlements and UTC as_of list,
#'   with independent outcome evidence permitted before official SP publication.
#' @return List(summary,groups,ticket_returns,receipt), all tabular outputs tibbles.
#'   Actual final payout/net remain NA while winning prices or results are pending;
#'   confirmed losses pay zero. Frozen SP is a separate valuation, not actual cash.
#'   Summary is one row per alternative; group diagnostics retain alternative IDs.
#' @details Authoritative settlement engine applies the payout factor once. No
#'   historical tuning, retrospective policy selection, IO or decision mutation.
#' @export
SummarizeBudgetAllocations <- function(alternatives,observation) {
  .ValidateBacktestAxis(alternatives)
  reference <- alternatives[[1]]$receipt
  rows <- list();tickets <- list();groups <- list()
  for(id in names(alternatives)) {
    ev <- alternatives[[id]];pool <- .parlay_ranked_validate_evaluation(ev)
    if(!identical(ev$receipt$producer,"AllocateParlayBudget") ||
       !identical(ev$receipt$selection_policy$source_hash,reference$selection_policy$source_hash) ||
       !identical(ev$cutoff,reference$cutoff) || !identical(ev$receipt$budget_cny,reference$budget_cny) ||
       !identical(ev$receipt$group_budget_cny,reference$group_budget_cny)) stop("alternatives need same frozen source and budgets")
    labels <- .BacktestLabels(observation,ev$cutoff)
    proxy <- labels$results |> dplyr::left_join(pool$prematch_sp |> dplyr::select(fixture_id,outcome,sp_raw),
      by=c("fixture_id","outcome"),relationship="one-to-one") |>
      dplyr::transmute(issue_id,fixture_id,outcome,settled_sp=sp_raw,label_available_at=result_available_at,status="settled",source_url)
    proxy <- dplyr::bind_rows(proxy,labels$actual |> dplyr::filter(.data$status!="settled"))
    outcome_only <- labels$results |>
      dplyr::transmute(issue_id,fixture_id,outcome,settled_sp=1,
        label_available_at=result_available_at,status="settled",source_url)
    outcome_only <- dplyr::bind_rows(outcome_only,labels$actual |> dplyr::filter(.data$status!="settled"))
    resolved <- parlay_settle_plan(ev$plan,outcome_only,labels$as_of)$ticket_returns
    actual <- parlay_settle_plan(ev$plan,labels$actual,labels$as_of)$ticket_returns
    priced <- parlay_settle_plan(ev$plan,proxy,labels$as_of)$ticket_returns
    t <- actual |> dplyr::rename(official_status=status,actual_payout_cny=payout_cny,actual_net_cny=net_cny) |>
      dplyr::left_join(priced |> dplyr::select(ticket_id,frozen_status=status,
        frozen_sp_payout_cny=payout_cny),by="ticket_id",relationship="one-to-one") |>
      dplyr::left_join(resolved |> dplyr::select(ticket_id,outcome_status=status),
        by="ticket_id",relationship="one-to-one") |>
      dplyr::mutate(actual_payout_cny=dplyr::case_when(
        .data$official_status=="WON" ~ .data$actual_payout_cny,
        .data$official_status=="LOST" ~ 0,
        .data$official_status=="PENDING" & .data$outcome_status=="LOST" ~ 0,
        TRUE ~ NA_real_),
        frozen_sp_payout_cny=dplyr::if_else(.data$frozen_status %in% c("PENDING","SPECIAL"),NA_real_,.data$frozen_sp_payout_cny),
        actual_net_cny=.data$actual_payout_cny-.data$stake_cny,alternative_id=id,.before=1)
    diagnostic <- DiagnoseParlayDepth(ev,labels$results,labels$as_of)$groups |>
      dplyr::mutate(alternative_id=id,.before=1)
    stake <- sum(t$stake_cny);complete <- !anyNA(t$actual_payout_cny)
    rows[[length(rows)+1L]] <- tibble::tibble(alternative_id=id,method=ev$receipt$selection_policy$method,
      eligible_groups=nrow(ev$allocation),purchased_groups=dplyr::n_distinct(t$group_id),
      n_tickets=nrow(t),stake_cny=stake,unspent_cny=ev$receipt$budget_cny-stake,
      winning_tickets=sum(t$outcome_status=="WON"),pending_results=sum(t$outcome_status=="PENDING"),
      pending_prices=sum(t$outcome_status=="WON" & is.na(t$actual_payout_cny)),
      actual_payout_cny=if(complete)sum(t$actual_payout_cny) else NA_real_,
      actual_net_cny=if(complete)sum(t$actual_payout_cny)-stake else NA_real_,
      actual_roi=if(complete && stake>0)(sum(t$actual_payout_cny)-stake)/stake else NA_real_,
      frozen_sp_net_cny=sum(t$frozen_sp_payout_cny)-stake,
      model_union_coverage=ev$summary$actual_coverage,model_ev_net_cny=ev$summary$ev_net_cny,
      status=if(!nrow(t))"NO_BET" else if(any(t$official_status=="SPECIAL"))"SPECIAL" else if(complete)"COMPLETE" else "PENDING")
    tickets[[length(tickets)+1L]] <- t;groups[[length(groups)+1L]] <- diagnostic
  }
  out <- list(summary=dplyr::bind_rows(rows),groups=dplyr::bind_rows(groups),ticket_returns=dplyr::bind_rows(tickets))
  out$receipt <- list(cutoff=reference$cutoff,input_snapshot=list(alternatives=alternatives,observation=observation),
    input_hash=rlang::hash(list(alternatives,observation)),output_hash=rlang::hash(out),
    code_hash=.rank_outcome_code_hash("SummarizeBudgetAllocations"),posthoc_diagnostic=TRUE)
  return(out)
}
