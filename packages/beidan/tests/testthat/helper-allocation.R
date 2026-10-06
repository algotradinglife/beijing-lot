#' Frozen three-group allocation acceptance input
#' @param n_legs Positive explicit number of legs; one-leg case has hand values.
#' @return Receipt-bound selected evaluation, without target labels or IO.
#' @noRd
AllocationFixture <- function(n_legs=1L) {
  c <- list(issue_id="A",cutoff_utc=as.POSIXct("2026-10-04",tz="UTC"))
  m <- tibble::tibble(fixture_id=c("A:001","A:002","A:003"),
    win=c(.4,.37,.34),draw=c(.3,.33,.33),lose=c(.3,.3,.33))
  sp <- tidyr::crossing(fixture_id=m$fixture_id,outcome=c("W","D","L")) |>
    dplyr::mutate(quote_at=c$cutoff_utc-60,sp_raw=3,source_url="fixture://allocation")
  s <- parlay_constant_defaults();s$n_legs <- n_legs;s$issue_budget_cny <- 20
  p <- parlay_construct_role_groups(rank_outcome_selections(prepare_outcome_selections(m),c),
    s,rep(3L,n_legs),max_candidates=3L,prematch_sp=sp)
  return(parlay_select_groups(p,objective="coverage",budget_cny=20,group_budget_cny=2)$evaluation)
}
#' Explicit observations for the three-group fixture
#' @param e AllocationFixture evaluation.
#' @return Canonical post-cutoff results and actual prices; no IO.
#' @noRd
AllocationObservation <- function(e) {
  m <- tibble::tibble(issue_id="A",fixture_id=c("A:001","A:002","A:003"),outcome=c("D","D","L"),
    result_available_at=e$cutoff$cutoff_utc+60,source_url="fixture://results")
  a <- m |> dplyr::transmute(issue_id,fixture_id,outcome,settled_sp=5,
    label_available_at=result_available_at,status="settled",source_url)
  return(list(match_results=m,settlements=a,as_of=e$cutoff$cutoff_utc+120))
}
#' Canonical frozen catalog for allocation tests
#' @param e AllocationFixture evaluation.
#' @return Pre-cutoff fixtures tibble; synthetic, no network or IO.
#' @noRd
AllocationCatalog <- function(e) {
  c <- e$cutoff
  return(tibble::tibble(issue_id=c$issue_id,fixture_key=c("A:001","A:002","A:003"),
    slot=1:3,home_name=c("Home <A>","B","C"),away_name="Away & Co",
    handicap=0L,kickoff_at=c$cutoff_utc+3600,observed_at=c$cutoff_utc-60,source_url="fixture://catalog"))
}
#' Portable research-bundle fixture for the migrated template view
#' @return Explicit frozen bundle/prepared pair, without repository files or IO.
#' @noRd
ResearchSheetFixture <- function() {
  source <- AllocationFixture()
  selected <- parlay_select_groups(source$portfolio,objective="coverage",budget_cny=20,group_budget_cny=2)
  e <- selected$evaluation
  view <- BuildEvaluationBettingSheetView(e,AllocationCatalog(e))
  prefix <- FreezeResearchBudgetPrefixes(selected,c(0,2,4,6),1L,2)
  frozen <- list(decision_at=e$cutoff$cutoff_utc,groups=list(`3`=dplyr::select(view$groups,-theoretical)),
    tickets=list(`3`=view$tickets),ticket_legs=list(`3`=view$legs),
    prefixes=list(`3`=prefix$prefixes),frozen=list(`3`=prefix))
  prepared <- list(decision_at=e$cutoff$cutoff_utc,projected=list(prematch_sp=e$portfolio$prematch_sp))
  return(list(frozen=frozen,prepared=prepared,evaluation=e))
}
