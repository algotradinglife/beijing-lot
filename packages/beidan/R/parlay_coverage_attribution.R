#' Attribute outcome misses to retained masks or purchased depth
#'
#' Outcomes-only diagnosis, independent of settlement SP. The existing
#' parlay_diagnose_settlement consumes monetary settlements, which cannot supply
#' unpublished-SP match results. This function reuses frozen evaluation validation,
#' physical ticket identity and the authoritative group-space enumeration/ranking.
#'
#' @param evaluation Frozen portfolio evaluation with embedded cutoff.
#' @param match_results Canonical match_results tibble, one final outcome per
#'   fixture, with issue_id, fixture_id, outcome, result_available_at, source_url.
#' @param as_of Explicit finite UTC POSIXct scalar observation time after cutoff.
#' @return List of tibbles `legs` (selected masks and visible outcomes) and `groups`
#'   (one row per purchased group, legal_space, purchased_tickets, structural_misses,
#'   unknown_legs, winner_rank, purchased_winner, winner_owned_elsewhere, status),
#'   and bound diagnostic `receipt`. Status is STRUCTURE_MISS, HIT, DEPTH_MISS or
#'   PENDING (or COVERED_ELSEWHERE for a winner owned by another group). With unknown outcomes, depth_blocked indicates no purchased ticket
#'   can match even the known results, but final structural status stays unresolved.
#'   Winner rank follows the frozen selection policy, including uniform triples.
#'   Winner rank is an after-result diagnostic, not a recommended purchase depth.
#'   Unselected groups are excluded; empty purchases return typed empty tables.
#' @details Labels visible by as_of only; unknown labels are not losses. Source
#'   hashes, cutoff and maximum admitted result time are bound. No selection,
#'   learning, payout, IO or mutation of the evaluation or labels.
#' @export
ParlayCoverageAttribution <- function(evaluation, match_results, as_of) {
  prepared <- .ParlayRiskPrepare(evaluation, evaluation$cutoff)
  cutoff <- evaluation$cutoff
  match_validate_table(match_results, "match_results")
  if (!inherits(as_of,"POSIXct") || length(as_of)!=1L ||
      !is.finite(as.numeric(as_of)) || !identical(attr(as_of,"tzone"),"UTC") ||
      as_of <= cutoff$cutoff_utc) stop("as_of must be a UTC instant after cutoff")
  if (any(!is.finite(as.numeric(match_results$result_available_at)))) {
    stop("result availability must be finite")
  }
  if (any(match_results$issue_id != cutoff$issue_id)) stop("result issue differs from cutoff")
  if (anyDuplicated(match_results$fixture_id)) stop("result fixtures must be unique")
  visible <- match_results |> dplyr::filter(.data$result_available_at <= as_of)
  if (any(visible$result_available_at <= cutoff$cutoff_utc)) {
    stop("target results must become available after cutoff")
  }
  actual <- stats::setNames(visible$outcome, visible$fixture_id)
  owned <- prepared$purchases
  legs <- tibble::as_tibble(evaluation$portfolio$role_legs) |>
    dplyr::filter(.data$group_id %in% owned$group_id)
  legs$actual_outcome <- unname(actual[legs$fixture_id])
  legs$admitted <- vapply(seq_len(nrow(legs)),function(i) {
    if (is.na(legs$actual_outcome[[i]])) return(NA)
    return(legs$actual_outcome[[i]] %in% legs$allowed_outcomes[[i]])
  },logical(1))
  rows <- list()
  for (id in unique(owned$group_id)) {
    block <- legs[legs$group_id==id,]
    bought <- owned[owned$group_id==id,]
    misses <- as.integer(sum(!is.na(block$admitted) & !block$admitted))
    unknown <- as.integer(sum(is.na(block$admitted)))
    rank <- NA_integer_;won <- FALSE;elsewhere <- FALSE
    if (misses==0L && unknown==0L) {
      key <- parlay_physical_ticket_key(block$fixture_id,
        as.integer(match(block$actual_outcome,match_outcomes())))
      space <- .parlay_ranked_group_space(id,block,prepared$probabilities,
        prepared$sp,cutoff,prepared$settings,prepared$settings$n_legs)
      if(identical(evaluation$receipt$producer,"AllocateParlayBudget") &&
          identical(evaluation$receipt$selection_policy$triple_ranking,"uniform")) {
        space <- .UniformTripleRanking(space,block,prepared$probabilities)
      }
      rank <- space$ranked$rank[match(key,space$ranked$ticket_id)]
      if (length(rank)!=1L || is.na(rank)) stop("admitted winner missing from legal space")
      won <- key %in% bought$ticket_id
      elsewhere <- !won && key %in% owned$ticket_id
    }
    ticket_legs <- prepared$legs |>
      dplyr::filter(.data$ticket_id %in% bought$ticket_id)
    ticket_legs$actual <- unname(actual[ticket_legs$fixture_id])
    viability <- ticket_legs |> dplyr::group_by(.data$ticket_id) |>
      dplyr::summarise(wrong=any(!is.na(.data$actual) & .data$outcome!=.data$actual),.groups="drop")
    blocked <- all(viability$wrong)
    status <- if (misses>0L) "STRUCTURE_MISS" else if (unknown>0L) "PENDING" else
      if (won) "HIT" else if (elsewhere) "COVERED_ELSEWHERE" else "DEPTH_MISS"
    rows[[length(rows)+1L]] <- tibble::tibble(group_id=id,
      group_slot=as.integer(block$group_slot[[1]]),
      legal_space=as.double(prod(block$n_outcomes)),purchased_tickets=nrow(bought),
      structural_misses=misses,unknown_legs=unknown,winner_rank=as.integer(rank),
      purchased_winner=won,winner_owned_elsewhere=elsewhere,depth_blocked=blocked,status=status)
  }
  groups <- if(length(rows)) dplyr::bind_rows(rows) else tibble::tibble(
    group_id=character(),group_slot=integer(),legal_space=double(),purchased_tickets=integer(),
    structural_misses=integer(),unknown_legs=integer(),winner_rank=integer(),
    purchased_winner=logical(),winner_owned_elsewhere=logical(),depth_blocked=logical(),status=character())
  return(list(legs=legs,groups=groups,receipt=list(cutoff=cutoff,
    cutoff_hash=.rank_outcome_cutoff_hash(cutoff),as_of=as_of,
    input_hash=rlang::hash(list(evaluation,match_results,as_of)),
    code_hash=.rank_outcome_code_hash("ParlayCoverageAttribution"),
    excluded_future_labels=nrow(match_results)-nrow(visible),
    max_result_available_at=if(nrow(visible))max(visible$result_available_at) else as.POSIXct(NA_real_,origin="1970-01-01",tz="UTC"),
    posthoc_diagnostic=TRUE)))
}
