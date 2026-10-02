#' Prepare an exact, read-only betting sheet from a computed plan
#' @param result Complete parlay_build_plan() result with reconciled ledgers.
#' @param schedule Schedule tibble with unique fixture_key, slot, home_name,
#'   away_name, handicap and POSIXct kickoff_at. Supply the snapshot used to build
#'   the plan; identifiers must cover every selected fixture.
#' @return List(groups, tickets, matches, ticket_legs) of tibbles. matches has one
#'   row per selected group/fixture/outcome with unconditional model probability
#'   and a selected flag for occurrence in at least one purchased ticket.
#'   ticket_legs contains only actual selected tickets, labelled slots and outcomes.
#'   Costs occur once per row in tickets/groups; neither long table is a stake ledger.
#' @details Does not rerank, expand a mask into additional bets, fit, fetch, save or
#'   settle. The per-match selection union is not permission to buy its Cartesian
#'   product; the exact tickets table is authoritative. Missing identities and
#'   inconsistent ledgers error. Requires at least one selected ticket.
#' @export
parlay_betting_sheet <- function(result, schedule) {
  parlay_check_saved_result(result)
  match_validate_table(result$probabilities,"probabilities",keys=c("fixture_id","outcome"))
  match_validate_table(result$plan$ticket_legs,"ticket_legs",keys=c("ticket_id","fixture_id"))
  summary <- parlay_plan_summary(result)
  if (!nrow(summary$tickets)) stop("betting sheet requires selected tickets")
  if (!tibble::is_tibble(schedule)) stop("schedule must be a tibble")
  required <- c("fixture_key", "slot", "home_name", "away_name", "handicap", "kickoff_at")
  if (!all(required %in% names(schedule))) stop("schedule lacks betting-sheet fields")
  checkmate::assert_character(schedule$fixture_key, any.missing=FALSE, unique=TRUE, min.chars=1)
  checkmate::assert_integer(schedule$slot, any.missing=FALSE, lower=1)
  checkmate::assert_character(schedule$home_name, any.missing=FALSE, min.chars=1)
  checkmate::assert_character(schedule$away_name, any.missing=FALSE, min.chars=1)
  checkmate::assert_integerish(schedule$handicap, any.missing=FALSE)
  checkmate::assert_posixct(schedule$kickoff_at, any.missing=FALSE)
  legs <- dplyr::semi_join(result$plan$group_legs, summary$groups, by="group_id")
  if (any(!legs$fixture_id %in% schedule$fixture_key)) stop("schedule missing selected fixture")
  catalog <- dplyr::transmute(schedule, fixture_id=fixture_key, slot, home_name,
    away_name, handicap, kickoff_at=lubridate::with_tz(kickoff_at,"Asia/Shanghai"))
  legs <- dplyr::left_join(legs, catalog, by="fixture_id", relationship="many-to-one") |>
    dplyr::left_join(dplyr::select(summary$groups,group_id,display_label),
      by="group_id",relationship="many-to-one")
  actual <- dplyr::inner_join(result$plan$ticket_legs,
    dplyr::select(summary$tickets,ticket_id,group_id), by="ticket_id",relationship="many-to-one")
  ticket_legs <- dplyr::left_join(actual,legs,by=c("group_id","fixture_id"),
    relationship="many-to-one")
  if (!setequal(ticket_legs$ticket_id, summary$tickets$ticket_id) ||
      anyNA(ticket_legs$slot) ||
      any(table(ticket_legs$ticket_id) != result$constants$n_legs)) {
    stop("selected ticket legs do not reconcile with groups")
  }
  selected <- dplyr::distinct(actual,group_id,fixture_id,outcome) |>
    dplyr::mutate(selected=TRUE)
  matches <- dplyr::inner_join(legs,result$probabilities,by="fixture_id",relationship="many-to-many") |>
    dplyr::left_join(selected,by=c("group_id","fixture_id","outcome"),relationship="one-to-one") |>
    dplyr::mutate(selected=tidyr::replace_na(selected,FALSE)) |>
    dplyr::arrange(display_label,leg_order,match(outcome,c("W","D","L")))
  if (nrow(matches) != nrow(legs)*3L || anyNA(matches$probability)) {
    stop("selected fixtures need three outcome probabilities")
  }
  return(list(groups=summary$groups,tickets=summary$tickets,matches=matches,
    ticket_legs=dplyr::arrange(ticket_legs,display_label,ticket_id,leg_order)))
}
