#' Freeze ordered whole-group prefixes of one authoritative selected test plan
#' @param selected Output of parlay_select_groups, with embedded cutoff
#'   and bound selection/evaluation receipts. Never reorder after settlement.
#' @param limits_cny Unique nonnegative finite numeric budget ceilings, CNY.
#' @param group_tickets Positive whole number of NEW physical tickets per group.
#' @param unit_cny Positive finite CNY stake per physical ticket.
#' @return List(selected, prefixes, receipt). prefixes is one tibble row per
#'   ceiling, containing ordered group_ids/ticket_ids list columns, whole-group
#'   spending and model union coverage. Empty prefixes retain list/type schemas.
#' @details Rejects changed selector bindings, fractional/short groups, duplicate
#'   physical tickets, mismatched cash and limits exceeding the frozen ceiling.
#'   No fitting, labels, selection, IO or mutable session state.
#' @export
FreezeResearchBudgetPrefixes <- function(selected, limits_cny, group_tickets, unit_cny) {
  .ParlayRiskPrepare(selected$evaluation,selected$evaluation$cutoff)
  if (!identical(selected$receipt$cutoff,selected$evaluation$cutoff) ||
      !identical(selected$receipt$selection_hash,rlang::hash(selected$selection)) ||
      !identical(selected$receipt$evaluation_receipt_hash,rlang::hash(selected$evaluation$receipt)))
    stop("Selector receipt binding mismatch")
  checkmate::assert_numeric(limits_cny,any.missing=FALSE,finite=TRUE,lower=0,unique=TRUE)
  checkmate::assert_integerish(group_tickets,len=1L,lower=1,any.missing=FALSE)
  checkmate::assert_number(unit_cny,finite=TRUE,lower=.Machine$double.eps)
  ceiling <- selected$receipt$budget_cny
  checkmate::assert_number(ceiling,finite=TRUE,lower=0)
  if(any(limits_cny>ceiling)) stop("Prefix limit exceeds frozen budget ceiling")
  groups <- selected$selection
  purchases <- selected$evaluation$purchases
  if(!identical(groups$order,seq_len(nrow(groups))) || anyDuplicated(groups$group_id) ||
      anyDuplicated(purchases$ticket_id)) stop("Invalid frozen group order or duplicate physical tickets")
  if(any(groups$new_ticket_count!=group_tickets) ||
      any(abs(groups$new_cost_cny-group_tickets*unit_cny)>1e-9) ||
      any(abs(purchases$cost_cny-unit_cny)>1e-9)) stop("Every group must buy its exact new-ticket quota")
  counts <- purchases |> dplyr::count(group_id,name="owned")
  reconciled <- groups |> dplyr::left_join(counts,by="group_id",relationship="one-to-one")
  if(anyNA(reconciled$owned) || any(reconciled$owned!=group_tickets) ||
      !setequal(purchases$group_id,groups$group_id) ||
      abs(sum(purchases$cost_cny)-sum(groups$new_cost_cny))>1e-9 ||
      sum(purchases$cost_cny)>ceiling+1e-9) stop("Physical group ledger mismatch")
  rows <- list()
  for(i in seq_along(limits_cny)) {
    count <- sum(groups$cumulative_cost_cny<=limits_cny[i]+1e-9)
    ids <- groups$group_id[seq_len(count)]
    owned <- purchases |> dplyr::filter(group_id %in% ids)
    rows[[i]] <- tibble::tibble(budget_cny=limits_cny[i],purchased_groups=as.integer(count),
      purchased_tickets=as.integer(nrow(owned)),stake_cny=sum(owned$cost_cny),
      model_coverage=if(count) groups$cumulative_coverage[count] else 0,
      group_ids=list(ids),ticket_ids=list(owned$ticket_id))
  }
  prefixes <- if(length(rows)) dplyr::bind_rows(rows) else tibble::tibble(
    budget_cny=double(),purchased_groups=integer(),purchased_tickets=integer(),
    stake_cny=double(),model_coverage=double(),group_ids=list(),ticket_ids=list())
  return(list(selected=selected,prefixes=prefixes,
    receipt=list(cutoff=selected$evaluation$cutoff,selected_hash=rlang::hash(selected),
      prefixes_hash=rlang::hash(prefixes),group_tickets=as.integer(group_tickets),unit_cny=unit_cny)))
}

#' Settle frozen research funding prefixes without reselection or reordering
#' @param frozen Output of FreezeResearchBudgetPrefixes, unmodified.
#' @param settlements Valid settlement tibble; actual Beijing outcomes/SP and
#'   label_available_at are admitted only by the authoritative settlement API.
#' @param as_of Explicit one-instant UTC POSIXct observation time.
#' @return List(summary, settled, receipt). summary is one tibble row per ceiling,
#'   with stake/payout/final net in CNY, won groups/tickets and pending counts.
#'   Final hit_groups/hit_rate/net/ROI are NA until all tickets are final; zero
#'   purchased groups have NA hit rate/ROI. No labels change any owned ticket.
#' @details Altered prefix/selector/cutoff bindings fail closed; no fitting,
#'   selection, IO or mutation. The ticket-level 0.65 is applied only by beidan.
#' @export
SettleResearchBudgetPrefixes <- function(frozen, settlements, as_of) {
  checkmate::assert_posixct(as_of,len=1L,any.missing=FALSE)
  if(!identical(attr(as_of,"tzone"),"UTC")) stop("as_of must be UTC")
  if(!identical(frozen$receipt$selected_hash,rlang::hash(frozen$selected)) ||
      !identical(frozen$receipt$prefixes_hash,rlang::hash(frozen$prefixes)) ||
      !identical(frozen$receipt$cutoff,frozen$selected$evaluation$cutoff))
    stop("Frozen research prefix binding mismatch")
  settled <- parlay_settle_plan(frozen$selected$evaluation$plan,settlements,as_of)
  rows <- list()
  for(i in seq_len(nrow(frozen$prefixes))) {
    prefix <- frozen$prefixes[i,]
    returns <- settled$ticket_returns |>
      dplyr::filter(ticket_id %in% prefix$ticket_ids[[1]])
    won_groups <- dplyr::n_distinct(returns$group_id[returns$status=="WON"])
    pending <- sum(returns$status=="PENDING")
    special <- sum(!returns$status %in% c("WON","LOST","PENDING"))
    final <- pending+special==0L
    payout <- sum(returns$payout_cny,na.rm=TRUE)
    net <- if(final) payout-prefix$stake_cny else NA_real_
    rows[[i]] <- tibble::tibble(budget_cny=prefix$budget_cny,
      purchased_groups=prefix$purchased_groups,purchased_tickets=prefix$purchased_tickets,
      stake_cny=prefix$stake_cny,model_coverage=prefix$model_coverage,
      won_tickets=sum(returns$status=="WON"),won_groups=as.integer(won_groups),
      pending_tickets=as.integer(pending),special_tickets=as.integer(special),
      hit_groups=if(final) as.integer(won_groups) else NA_integer_,
      hit_rate=if(final && prefix$purchased_groups>0) won_groups/prefix$purchased_groups else NA_real_,
      payout_cny=payout,final_net_cny=net,
      roi=if(prefix$stake_cny>0) net/prefix$stake_cny else NA_real_)
  }
  summary <- if(length(rows)) dplyr::bind_rows(rows) else tibble::tibble(
    budget_cny=double(),purchased_groups=integer(),purchased_tickets=integer(),
    stake_cny=double(),model_coverage=double(),won_tickets=integer(),won_groups=integer(),
    pending_tickets=integer(),special_tickets=integer(),hit_groups=integer(),hit_rate=double(),
    payout_cny=double(),final_net_cny=double(),roi=double())
  return(list(summary=summary,settled=settled,receipt=list(frozen_hash=rlang::hash(frozen),
    settlement_hash=rlang::hash(settlements),as_of=as_of)))
}
