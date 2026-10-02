#' Replay one frozen probability snapshot with the current outcome rules
#' @param probabilities Long tibble: fixture_id, W/D/L outcome, probability.
#' @param cutoff Explicit original issue_id and cutoff_utc decision context.
#' @param settings Explicit package business constants.
#' @param pattern Target integer roles, all groups use the same target.
#' @param prematch_sp Raw pre-cutoff SP tibble; typed empty means unavailable.
#' @param group_budget_cny Per-group CNY cap, or NULL for full support.
#' @param reuse_policy Explicit final-admission maximum fixture reuse.
#' @param overlap_policy Explicit final-admission maximum shared fixtures.
#' @return Filter audit/receipt, selections, ranking, pool and evaluation list.
#'   No labels, learning, I/O or fetching. Missing SP keeps the fixture with an
#'   explicit flag; Top1 SP below 2 excludes it before classification/ranking.
#' Candidate generation has no artificial cap; baseline improvement is disabled.
ReplayRankedOutcomes <- function(probabilities, cutoff, settings, pattern,
                                prematch_sp, group_budget_cny,
                                reuse_policy, overlap_policy) {
  beidan::match_validate_table(probabilities, "probabilities")
  matches <- probabilities |>
    tidyr::pivot_wider(names_from=outcome, values_from=probability) |>
    dplyr::rename(win=W, draw=D, lose=L)
  filtered <- beidan::filter_outcome_matches(matches, prematch_sp, cutoff)
  admitted <- filtered$matches
  attr(admitted, "filter_receipt") <- filtered$receipt
  selections <- beidan::prepare_outcome_selections(admitted)
  ranked <- beidan::rank_outcome_selections(selections, cutoff, priority="coverage")
  pool <- beidan::parlay_construct_role_groups(ranked, settings, pattern,
    max_candidates=NULL, prematch_sp=prematch_sp)
  evaluation <- beidan::parlay_evaluate_portfolio(pool, budget_cny=NULL,
    group_budget_cny=group_budget_cny, reuse_policy=reuse_policy,
    overlap_policy=overlap_policy, improve=FALSE)
  return(list(filtered=filtered, selections=selections, ranked=ranked,
    pool=pool, evaluation=evaluation))
}

#' Diagnose frozen purchases using independently provided visible settlements
#' @param replay Output of ReplayRankedOutcomes, already frozen without labels.
#' @param settlements Valid settlement tibble, including actual SP and availability.
#' @param as_of Explicit UTC POSIXct settlement observation time.
#' @return Authoritative returns, misses, complementary protection and group legs.
#' Missing results remain pending. This diagnostic never reconstructs a decision.
DiagnoseRankedReplay <- function(replay, settlements, as_of) {
  returns <- beidan::parlay_settle_plan(replay$evaluation$plan, settlements, as_of)
  admitted <- dplyr::filter(replay$evaluation$group_selection, admitted)
  legs <- replay$evaluation$final$role_legs |>
    dplyr::semi_join(admitted, by=c("group_id","group_slot"))
  visible <- dplyr::filter(settlements,
    issue_id==replay$evaluation$cutoff$issue_id, label_available_at<=as_of)
  # Unique keys are enforced by the settlement API and the join cardinality.
  labelled <- legs |>
    dplyr::left_join(dplyr::select(visible,fixture_id,actual=outcome,status),
                    by="fixture_id",relationship="many-to-one") |>
    dplyr::mutate(covered=purrr::pmap_lgl(list(actual,status,allowed_outcomes),
      function(actual,status,allowed) {
        if(is.na(actual) || is.na(status) || status!="settled") NA else actual %in% allowed
      }))
  eligible <- replay$selections |>
    dplyr::count(fixture_id,name="directions") |>
    dplyr::filter(directions>1L)
  nominal <- legs |>
    dplyr::semi_join(eligible,by="fixture_id") |>
    dplyr::mutate(mask=purrr::map_chr(allowed_outcomes,
      ~paste(sort(.x),collapse="+"))) |>
    dplyr::group_by(fixture_id) |>
    dplyr::summarise(admitted_directions=dplyr::n_distinct(mask),.groups="drop")
  actual <- replay$evaluation$plan$ticket_legs |>
    dplyr::left_join(dplyr::select(replay$evaluation$purchases,ticket_id,group_id),
                    by="ticket_id",relationship="many-to-one") |>
    dplyr::semi_join(eligible,by="fixture_id") |>
    dplyr::group_by(fixture_id,group_id) |>
    dplyr::summarise(mask=paste(sort(unique(outcome)),collapse="+"),
      draw_bought=any(outcome=="D"),.groups="drop")
  protection <- actual |>
    dplyr::group_by(fixture_id) |>
    dplyr::summarise(purchased_groups=dplyr::n_distinct(group_id),
      purchased_directions=dplyr::n_distinct(mask),
      draw_protected=any(draw_bought),
      all_three_bought=all(c("W","D","L") %in%
        unlist(strsplit(mask,"+",fixed=TRUE))),.groups="drop")
  protection <- eligible |>
    dplyr::left_join(nominal,by="fixture_id",relationship="one-to-one") |>
    dplyr::left_join(protection,by="fixture_id",relationship="one-to-one") |>
    dplyr::mutate(admitted_directions=dplyr::coalesce(admitted_directions,0L),
      purchased_groups=dplyr::coalesce(purchased_groups,0L),
      purchased_directions=dplyr::coalesce(purchased_directions,0L),
      draw_protected=dplyr::coalesce(draw_protected,FALSE),
      all_three_bought=dplyr::coalesce(all_three_bought,FALSE),
      complementary_bought=admitted_directions>=2L & all_three_bought)
  return(list(returns=returns, group_legs=labelled,
       misses=dplyr::filter(labelled,!covered), protection=protection))
}

#' Verify original frozen decision and input identities before settlement refresh
#' @param decision_path Explicit existing frozen decision RDS path.
#' @param input_path Explicit original probability/SP input path.
#' @param receipt Original receipt with decision_hash and input_sha256 strings.
#' @return TRUE invisibly; missing receipts or altered bytes fail before diagnosis.
#' Reads bytes only, with no writes or decision reconstruction.
VerifyRankedReplayReceipt <- function(decision_path, input_path, receipt) {
  if (!is.list(receipt) || !is.character(receipt$decision_hash) ||
      length(receipt$decision_hash)!=1L || is.na(receipt$decision_hash) ||
      !is.character(receipt$input_sha256) || length(receipt$input_sha256)!=1L ||
      is.na(receipt$input_sha256)) stop("Missing original replay receipt")
  if (!identical(digest::digest(decision_path,file=TRUE,algo="sha256"),receipt$decision_hash) ||
      !identical(digest::digest(input_path,file=TRUE,algo="sha256"),receipt$input_sha256))
    stop("Frozen decision or original input hash mismatch")
  return(invisible(TRUE))
}
