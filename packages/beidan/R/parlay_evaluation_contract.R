#' Validate a current ranked evaluation before downstream analysis
#' @param evaluation Result of parlay_evaluate_portfolio().
#' @return Validated normalized source pool; no IO or mutation.
#' @details Source, code, cutoff, purchased ledger and frozen-plan bindings fail closed.
#' @noRd
.parlay_ranked_validate_evaluation <- function(evaluation) {
  checkmate::assert_list(evaluation)
  pool <- .parlay_ranked_validate_pool(evaluation$portfolio)
  receipt <- evaluation$receipt
  if (!identical(evaluation$cutoff, pool$cutoff) ||
      !identical(receipt$cutoff, pool$cutoff) ||
      !identical(receipt$cutoff_hash, pool$cutoff_hash)) stop("evaluation cutoff binding mismatch")
  producer <- receipt$producer
  if (!is.character(producer) || length(producer) != 1L || is.na(producer) ||
      !producer %in% c("parlay_evaluate_portfolio", "parlay_select_groups")) {
    stop("evaluation producer binding missing or invalid")
  }
  expected <- list(portfolio_hash=rlang::hash(evaluation$portfolio),
    probability_hash=rlang::hash(pool$probabilities), prematch_sp_hash=rlang::hash(pool$prematch_sp),
    settings_hash=rlang::hash(pool$settings), final_purchase_hash=rlang::hash(evaluation$purchases),
    final_role_legs_hash=rlang::hash(evaluation$final$role_legs), plan_hash=rlang::hash(evaluation$plan),
    code_hash=.rank_outcome_code_hash(roots=c("parlay_construct_role_groups",producer)))
  for (field in names(expected)) {
    if (!identical(receipt[[field]], expected[[field]])) stop("evaluation binding mismatch: ",field)
  }
  if (!identical(evaluation$plan$constants, pool$settings)) stop("evaluation frozen settings mismatch")
  ledger <- evaluation$purchases
  frozen <- evaluation$plan$purchases
  funded <- evaluation$plan$funded
  checkmate::assert_tibble(funded)
  if (!all(c("ticket_id","group_id","stake_cny") %in% names(funded)) ||
      anyDuplicated(funded$ticket_id) ||
      !identical(dplyr::arrange(dplyr::select(funded,ticket_id,group_id,stake_cny),ticket_id),
        dplyr::arrange(tibble::tibble(ticket_id=ledger$ticket_id,
          group_id=ledger$group_id,stake_cny=ledger$cost_cny),ticket_id))) {
    stop("evaluation settlement funding ledger mismatch")
  }
  if (!identical(as.character(ledger$ticket_id),as.character(frozen$ticket_id)) ||
      !identical(as.character(ledger$group_id),as.character(frozen$group_id)) ||
      !identical(as.numeric(ledger$cost_cny),as.numeric(frozen$stake_cny)) ||
      anyDuplicated(ledger$ticket_id) || anyNA(ledger$cost_cny) ||
      any(ledger$cost_cny!=pool$settings$unit_cny)) stop("evaluation physical purchase ledger mismatch")
  if (!identical(evaluation$plan$epoch_utc,pool$cutoff$cutoff_utc)) stop("evaluation frozen cutoff mismatch")
  issue <- as.character(pool$cutoff$issue_id)
  if (!identical(evaluation$plan$issue_id,issue) ||
      !identical(receipt$issue_id,issue) ||
      !identical(frozen$issue_id,rep(issue,nrow(frozen))) ||
      !identical(frozen$epoch_at,rep(pool$cutoff$cutoff_utc,nrow(frozen)))) {
    stop("evaluation frozen issue/cutoff ledger mismatch")
  }
  final_legs <- evaluation$final$role_legs
  for (group in unique(final_legs$group_id)) {
    block <- final_legs[final_legs$group_id==group,,drop=FALSE]
    if (nrow(block)!=pool$settings$n_legs || anyDuplicated(block$fixture_id)) stop("evaluation invalid final group legs")
    .parlay_ranked_validate_masks(block,pool$ranked_selections,pool$probabilities,group)
  }
  for (group in unique(ledger$group_id)) {
    block <- final_legs[final_legs$group_id==group,,drop=FALSE]
    frozen_legs <- evaluation$plan$group_legs[evaluation$plan$group_legs$group_id==group,,drop=FALSE]
    if (!setequal(block$fixture_id,frozen_legs$fixture_id)) stop("evaluation frozen group fixtures mismatch")
    for (ticket in ledger$ticket_id[ledger$group_id==group]) {
      legs <- evaluation$plan$ticket_legs[evaluation$plan$ticket_legs$ticket_id==ticket,,drop=FALSE]
      if (nrow(legs)!=pool$settings$n_legs || anyDuplicated(legs$fixture_id) ||
          !setequal(legs$fixture_id,block$fixture_id)) stop("evaluation frozen physical legs mismatch")
      if (!identical(ticket,parlay_physical_ticket_key(legs$fixture_id,
          match(legs$outcome,match_outcomes())))) stop("evaluation physical ticket identity mismatch")
      for (i in seq_len(nrow(legs))) {
        mask <- block$allowed_outcomes[[match(legs$fixture_id[i],block$fixture_id)]]
        if (!legs$outcome[i] %in% mask) stop("evaluation frozen ticket lies outside final mask")
      }
    }
  }
  p <- pool$probabilities; sp <- pool$prematch_sp; settings <- pool$settings
  legs <- evaluation$plan$ticket_legs
  tickets <- dplyr::select(ledger,ticket_id,group_id,probability,sp_product_est,ev_net_est)
  # Revalue from bound source probabilities and pre-cutoff raw SP. Receipt hashes
  # alone cannot justify manually rebound stale values.
  expected_probability <- vapply(tickets$ticket_id, function(id) {
    block <- legs[legs$ticket_id==id,,drop=FALSE]
    if (nrow(block)!=settings$n_legs || anyDuplicated(block$fixture_id)) stop("invalid physical ticket legs")
    index <- match(paste(block$fixture_id,block$outcome),paste(p$fixture_id,p$outcome))
    if (anyNA(index)) stop("physical ticket absent from probabilities")
    prod(p$probability[index])
  }, numeric(1))
  if (!isTRUE(all.equal(tickets$probability,unname(expected_probability),tolerance=1e-12))) stop("evaluation purchased probability mismatch")
  revalued <- parlay_value_tickets(tickets,legs,sp,pool$cutoff,
    .Machine$double.xmax,1,settings$unit_cny,settings$payout_factor)
  for (field in c("sp_product_est","ev_net_est")) {
    if (!isTRUE(all.equal(tickets[[field]],revalued[[field]],tolerance=1e-12))) stop("evaluation purchased valuation mismatch: ",field)
  }
  pool
}
