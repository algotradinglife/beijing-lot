#' Rebuy fixed groups under explicitly diagnostic outcome masks
#' @param original One frozen output containing pool and evaluated, with bound cutoff.
#' @param mode 'sp_all' uses raw-SP ascending masks on every leg; 'sp_one_134'
#'   changes only fixture 26098:134 in the lexicographically first funded group.
#'   diversify_shared maximizes summed retained model mass over the at-most-nine
#'   mask pairs per shared fixture, requiring their union to cover W/D/L.
#' @return New evaluation-shaped diagnostic object, with final plan and a newly
#'   generated receipt. Original data are unchanged; no settlement input accepted.
#' @details Retains fixture sets, roles, probabilities and CNY256 per-group cap.
#'   SP modes require all three pre-cutoff quotes on changed legs. Uses authoritative
#'   enumeration, valuation, ranking and funding helpers, not the production
#'   Top-role policy validator. This is a retrospective experiment, not a policy.
#'   Invalid receipts, missing SP, empty funded plans or invalid mode fail.
#'   No network, files, fitting or hidden state; all amounts are CNY.
ParlayLossMaskExperiment <- function(original, mode) {
  checkmate::assert_choice(mode,c("sp_all","sp_one_134","diversify_shared"))
  cutoff <- original$evaluated$cutoff
  validated <- beidan:::.ParlayRiskPrepare(original$evaluated,cutoff)
  pool <- original$pool
  if (!identical(pool$cutoff,cutoff) ||
      !identical(rlang::hash(pool$probabilities),original$evaluated$receipt$probability_hash) ||
      !identical(rlang::hash(pool$prematch_sp),original$evaluated$receipt$prematch_sp_hash) ||
      !identical(pool$settings,validated$settings)) stop("pool source binding mismatch")
  final <- original$evaluated$final
  gl <- final$plan$group_legs
  ids <- sort(unique(final$plan$purchases$group_id))
  if (!length(ids)) stop("requires funded groups")
  pool$groups <- tibble::tibble(group_slot=as.integer(seq_along(ids)),
    group_id=ids,complete=TRUE)
  legs <- dplyr::filter(gl,.data$group_id %in% ids) |>
    dplyr::left_join(pool$groups,by="group_id",relationship="many-to-one") |>
    dplyr::transmute(group_slot=as.integer(.data$group_slot),group_id,fixture_id,
      role=as.integer(pool$pattern[.data$leg_order]),round=as.integer(.data$leg_order))
  supports <- final$plan$supports |>
    dplyr::filter(.data$allowed) |>
    dplyr::inner_join(dplyr::distinct(final$plan$purchases,candidate_id,group_id),
      by="candidate_id",relationship="many-to-one")
  quotes <- beidan:::match_latest_quote_before(validated$sp,cutoff$cutoff_utc,"sp_raw")
  legs$allowed_outcomes <- vector("list",nrow(legs))
  legs$retained_probability <- numeric(nrow(legs))
  for (i in seq_len(nrow(legs))) {
    leg <- legs[i,]
    allowed <- supports$outcome[supports$group_id==leg$group_id &
      supports$fixture_id==leg$fixture_id]
    if (length(allowed)!=leg$role) stop("frozen role support mismatch")
    changed <- mode=="sp_all" || (mode=="sp_one_134" &&
      leg$fixture_id=="26098:134" && leg$group_id==ids[1])
    if (changed) {
      q <- dplyr::filter(quotes,.data$fixture_id==leg$fixture_id)
      if (nrow(q)!=3L || anyNA(q$sp_raw) || !setequal(q$outcome,c("W","D","L")))
        stop("complete pre-cutoff SP required")
      allowed <- q$outcome[order(q$sp_raw,match(q$outcome,c("W","D","L")))][seq_len(leg$role)]
    }
    legs$allowed_outcomes[[i]] <- allowed
    legs$retained_probability[i] <- sum(pool$probabilities$probability[
      pool$probabilities$fixture_id==leg$fixture_id & pool$probabilities$outcome %in% allowed])
  }
  if (mode=="diversify_shared") {
    shared <- names(which(table(legs$fixture_id)>1L))
    for (fixture in shared) {
      index <- which(legs$fixture_id==fixture)
      if (length(index)!=2L) stop("diagnostic requires at most two shared uses")
      a <- utils::combn(c("W","D","L"),legs$role[index[1]],simplify=FALSE)
      b <- utils::combn(c("W","D","L"),legs$role[index[2]],simplify=FALSE)
      p <- pool$probabilities[pool$probabilities$fixture_id==fixture,]
      probability <- stats::setNames(p$probability,p$outcome)
      best <- -Inf
      masks <- NULL
      for (aa in a) for (bb in b) {
        if (length(union(aa,bb))!=3L) next
        score <- sum(probability[aa])+sum(probability[bb])
        if (score>best) { best <- score; masks <- list(aa,bb) }
      }
      if (is.null(masks)) stop("roles cannot diversify shared fixture")
      for (j in seq_along(index)) {
        legs$allowed_outcomes[[index[j]]] <- masks[[j]]
        legs$retained_probability[index[j]] <- sum(probability[masks[[j]]])
      }
    }
  }
  pool$role_legs <- legs
  constraints <- list(max_reuse=2L,max_overlap=2L)
  packages <- beidan:::.parlay_role_packages(pool,pool$probabilities,pool$prematch_sp,
    cutoff,256,"probability")
  selected <- beidan:::.parlay_role_select(packages$packages,packages$stack,
    pool$settings$unit_cny,NULL,constraints,packages$fixture_sets)
  result <- beidan:::.parlay_role_result(pool,selected$new_purchases,pool$prematch_sp,
    cutoff,"probability",NULL,constraints)
  result$provenance$mode <- "retrospective_custom_mask_diagnostic"
  result$provenance$source_hash <- rlang::hash(original)
  result$provenance$mask_mode <- mode
  receipt <- list(cutoff=cutoff,cutoff_hash=original$evaluated$receipt$cutoff_hash,
    probability_hash=rlang::hash(pool$probabilities),prematch_sp_hash=rlang::hash(pool$prematch_sp),
    source_hash=rlang::hash(original),experiment=mode,diagnostic_only=TRUE,
    portfolio_hash=rlang::hash(pool),implementation_hash=rlang::hash(list(
      body(ParlayLossMaskExperiment),beidan:::.ParlayRiskCodeHash())))
  evaluation <- list(final=result,cutoff=cutoff,receipt=receipt)
  beidan:::.ParlayRiskPrepare(evaluation,cutoff)
  return(evaluation)
}
