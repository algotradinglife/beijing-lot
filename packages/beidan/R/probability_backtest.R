#' Validate named experiment axes
#' @param x A list, with nonempty unique character names when populated.
#' @param empty Whether a zero-length list is accepted.
#' @return Invisibly TRUE; malformed names fail. No IO or mutation.
#' @noRd
.ValidateBacktestAxis <- function(x, empty = FALSE) {
  checkmate::assert_list(x)
  if (!length(x)) {
    if (!empty) stop("experiment axis must not be empty")
    return(invisible(TRUE))
  }
  checkmate::assert_character(names(x),len=length(x),any.missing=FALSE,min.chars=1,unique=TRUE)
  return(invisible(TRUE))
}

#' Assemble explicit arguments for one raw-source decision
#' @param round List with inputs, cutoff, window_hours, market_policy.
#' @param strategy List with base and optional bd_weight, single_threshold,
#'   pattern and model_config. Missing optional values use fixed API defaults.
#' @param settings,group_budget_cny,max_candidates Explicit common business settings.
#' @return BuildProbabilityPlan argument list; rejects undeclared fields. No labels/IO.
#' @noRd
.BacktestArguments <- function(round, strategy, settings, group_budget_cny, max_candidates) {
  checkmate::assert_list(round,names="unique")
  checkmate::assert_names(names(round),must.include=c("inputs","cutoff","window_hours","market_policy"),
    subset.of=c("inputs","cutoff","window_hours","market_policy"))
  checkmate::assert_list(strategy,names="unique")
  checkmate::assert_names(names(strategy),must.include="base",
    subset.of=c("base","bd_weight","single_threshold","pattern","model_config"))
  return(c(list(inputs=round$inputs,cutoff=round$cutoff,settings=settings,
    group_budget_cny=group_budget_cny,window_hours=round$window_hours,
    market_policy=round$market_policy,max_candidates=max_candidates),strategy))
}

#' Freeze all fixed probability/structure alternatives before outcome evaluation
#' @param rounds Named list. Each round requires raw inputs, explicit cutoff,
#'   window_hours and market_policy (NULL for Beidan-only). Round IDs distinguish
#'   multiple decisions for the same issue. Empty rounds return an empty receipt-bound experiment.
#' @param strategies Nonempty named list of fixed user-supplied strategy lists:
#'   base, optional bd_weight, single_threshold, pattern and model_config.
#'   Defaults are BuildProbabilityPlan defaults; no historical parameter selection.
#' @param settings Explicit common parlay settings, including CNY budget, unit and factor.
#' @param group_budget_cny Explicit common CNY cap per group.
#' @param max_candidates Optional common candidate cap; NULL retains the full trajectory.
#' @return List of cases (round_id, strategy_id, arguments, decision), and receipt
#'   retaining raw inputs/parameters, cutoff ledger and transitive implementation.
#' @details Pure label-free construction; no fetching, persistence, clock, tuning
#'   or session changes. Call before opening target observations and persist the
#'   immutable result. Alternatives are separate hypothetical betting accounts.
#' @export
BuildProbabilityBacktest <- function(rounds, strategies, settings, group_budget_cny,
                                     max_candidates = NULL) {
  .ValidateBacktestAxis(rounds,TRUE); .ValidateBacktestAxis(strategies)
  parlay_validate_settings(settings)
  checkmate::assert_number(group_budget_cny,lower=0,finite=TRUE)
  if (is.object(group_budget_cny) || !is.null(dim(group_budget_cny))) stop("group cap must be plain numeric")
  if (!is.null(max_candidates)) checkmate::assert_count(max_candidates,positive=TRUE)
  for (strategy in strategies) {
    checkmate::assert_list(strategy,names="unique")
    checkmate::assert_names(names(strategy),must.include="base",
      subset.of=c("base","bd_weight","single_threshold","pattern","model_config"))
    checkmate::assert_choice(strategy$base,c("beidan","dc","mixed"))
    if (!is.null(strategy$single_threshold)) checkmate::assert_number(strategy$single_threshold,lower=1/3,upper=1,finite=TRUE)
    if (strategy$base=="mixed") checkmate::assert_number(strategy$bd_weight,lower=0,upper=1,finite=TRUE)
    else if (!is.null(strategy$bd_weight)) stop("bd_weight is only valid for mixed")
    for (field in c("single_threshold","bd_weight","pattern")) {
      if (!is.null(strategy[[field]]) && (is.object(strategy[[field]]) || !is.null(dim(strategy[[field]])))) stop("strategy numeric parameters must be plain values")
    }
    if (!is.null(strategy$pattern)) checkmate::assert_integerish(strategy$pattern,lower=1,upper=3,len=settings$n_legs,any.missing=FALSE)
  }
  cases <- list()
  for (round_id in names(rounds)) for (strategy_id in names(strategies)) {
    args <- .BacktestArguments(rounds[[round_id]],strategies[[strategy_id]],settings,group_budget_cny,max_candidates)
    cases[[length(cases)+1L]] <- list(round_id=round_id,strategy_id=strategy_id,
      arguments=args,decision=do.call(BuildProbabilityPlan,args))
  }
  out <- list(cases=cases)
  snapshot <- list(rounds=rounds,strategies=strategies,settings=settings,
    group_budget_cny=group_budget_cny,max_candidates=max_candidates)
  out$receipt <- list(input_snapshot=snapshot,input_hash=rlang::hash(snapshot),
    implementation_hash=.rank_outcome_code_hash(c("BuildProbabilityBacktest",".ValidateProbabilityBacktest")),
    output_hash=rlang::hash(out),cutoffs=lapply(rounds,`[[`,"cutoff"),
    historical_learning_inventory="NONE: fixed user alternatives, no target-label fitting, tuning or automatic winner selection")
  return(out)
}

#' Validate a frozen experiment and each canonical decision
#' @param experiment Output of BuildProbabilityBacktest.
#' @return Invisibly TRUE; stale/tampered sources, parameters or decisions fail closed.
#' @details Reuses package projection/risk replay. Whole raw experiment is also
#'   independently rebuilt by the delivery verification entry point; no IO here.
#' @noRd
.ValidateProbabilityBacktest <- function(experiment) {
  r <- experiment$receipt
  if (!is.list(r) || is.null(r$input_snapshot)) stop("backtest receipt required")
  bare <- experiment;bare$receipt <- NULL
  if (!identical(r$input_hash,rlang::hash(r$input_snapshot)) ||
      !identical(r$output_hash,rlang::hash(bare)) ||
      !identical(r$implementation_hash,.rank_outcome_code_hash(c("BuildProbabilityBacktest",".ValidateProbabilityBacktest")))) stop("backtest source, output or implementation differs")
  s <- r$input_snapshot
  if (!identical(r$cutoffs,lapply(s$rounds,`[[`,"cutoff")) || length(experiment$cases)!=length(s$rounds)*length(s$strategies)) stop("backtest cutoff/case ledger differs")
  index <- 0L
  for (round_id in names(s$rounds)) for (strategy_id in names(s$strategies)) {
    index <- index+1L;case <- experiment$cases[[index]];d <- case$decision
    args <- .BacktestArguments(s$rounds[[round_id]],s$strategies[[strategy_id]],s$settings,s$group_budget_cny,s$max_candidates)
    if (!identical(case$round_id,round_id) || !identical(case$strategy_id,strategy_id) || !identical(args,case$arguments)) stop("backtest case identity or arguments differ")
    dr <- d$receipt;db <- d;db$receipt <- NULL
    if (!identical(dr$output_hash,rlang::hash(db)) ||
        !identical(dr$input_hash,rlang::hash(dr$input_snapshot)) ||
        !identical(dr$implementation_hash,.rank_outcome_code_hash("BuildProbabilityPlan")) ||
        !identical(dr$input_snapshot$inputs,args$inputs) ||
        !identical(.rank_outcome_cutoff_hash(d$cutoff),.rank_outcome_cutoff_hash(args$cutoff))) stop("case decision receipt differs")
    if (!identical(do.call(BuildProbabilityPlan,args),d)) stop("case raw-source decision replay differs")
  }
  return(invisible(TRUE))
}

#' Reconcile visible outcomes and actual settlements without pricing inference
#' @param observation List with canonical match_results, settlements, and UTC as_of.
#' @param cutoff Explicit target decision cutoff.
#' @return Visible reconciled results, visible actual settlements and counts.
#' @details Agreeing outcome observations reconcile to earliest availability,
#'   source URL breaks equal-time ties; conflicts/duplicates/missing chronology fail.
#'   Neutral ALL results are never invented W/D/L hits. No IO or mutation.
#' @noRd
.BacktestLabels <- function(observation, cutoff) {
  checkmate::assert_list(observation,names="unique")
  checkmate::assert_names(names(observation),permutation.of=c("match_results","settlements","as_of"))
  match_require_cutoff(cutoff)
  as_of <- observation$as_of
  if (!inherits(as_of,"POSIXct") || length(as_of)!=1L || !identical(attr(as_of,"tzone"),"UTC") || !is.finite(as.numeric(as_of)) || as_of<=cutoff$cutoff_utc) stop("as_of must be finite UTC after cutoff")
  m <- tibble::as_tibble(match_validate_table(observation$match_results,"match_results"))
  a <- tibble::as_tibble(match_validate_table(observation$settlements,"settlements"))
  for (x in list(m,a)) {
    time <- if("result_available_at" %in% names(x)) x$result_available_at else x$label_available_at
    if (any(x$issue_id!=cutoff$issue_id) || anyDuplicated(x$fixture_id) ||
        any(!is.finite(as.numeric(time))) || any(time<=cutoff$cutoff_utc)) stop("labels require unique target fixtures and finite availability after cutoff")
  }
  if (any(!is.na(a$settled_sp) & (!is.finite(a$settled_sp) | a$settled_sp<=0))) stop("actual SP must be positive finite or NA")
  future <- sum(m$result_available_at>as_of)+sum(a$label_available_at>as_of)
  m <- m |> dplyr::filter(.data$result_available_at<=as_of)
  a <- a |> dplyr::filter(.data$label_available_at<=as_of)
  derived <- a |> dplyr::filter(.data$status=="settled",.data$outcome %in% match_outcomes()) |>
    dplyr::transmute(issue_id,fixture_id,outcome,result_available_at=label_available_at,source_url)
  combined <- dplyr::bind_rows(m,derived)
  conflicts <- combined |> dplyr::group_by(.data$fixture_id) |>
    dplyr::summarise(n=dplyr::n_distinct(.data$outcome),.groups="drop")
  if (any(conflicts$n>1L)) stop("result and settlement outcomes conflict")
  if (any(combined$fixture_id %in% a$fixture_id[a$status=="all_options_one"])) stop("neutral fixture cannot have an ordinary result")
  duplicate_agreements <- nrow(combined)-dplyr::n_distinct(combined$fixture_id)
  combined <- combined |> dplyr::arrange(.data$result_available_at,.data$source_url) |>
    dplyr::distinct(.data$fixture_id,.keep_all=TRUE)
  combined$result_available_at <- lubridate::with_tz(combined$result_available_at,"UTC")
  return(list(results=combined,actual=a,as_of=as_of,excluded_future_rows=as.integer(future),
    reconciled_agreements=as.integer(duplicate_agreements)))
}

#' Evaluate frozen alternatives by round without selecting a strategy
#' @param experiment Frozen BuildProbabilityBacktest output, with embedded cutoffs.
#' @param observations Named list matching the round IDs exactly. Each entry has
#'   canonical match_results, actual settlements, explicit UTC as_of. Typed-empty
#'   results/settlements are valid; missing chronology and conflicting labels fail.
#' @return Receipt-bound list of round_summary, match_summary, fixture_results,
#'   ticket_returns, group_attributions and leg_attributions tibbles. Monetary
#'   amounts are CNY; hit rates are unitless fractions and NA for zero denominator.
#'   Round/strategy is the case key; scopes are projected, filtered and purchased.
#' @details Actual payout/net stay NA until every purchased ticket amount is known.
#'   known_actual_payout_cny is a partial cash tally, not a final return. Confirmed
#'   outcome losses have zero payout even if SP is missing. Frozen-SP outcome
#'   valuation is separate from model EV and actual money, with exactly one frozen
#'   ticket payout factor. Neutral/special results are not W/D/L prediction hits.
#'   No source fetching, historical learning, strategy routing, or decision mutation.
#' @export
SummarizeProbabilityBacktest <- function(experiment, observations) {
  .ValidateProbabilityBacktest(experiment);.ValidateBacktestAxis(observations,TRUE)
  s <- experiment$receipt$input_snapshot
  if (!setequal(names(observations),names(s$rounds))) stop("observation round IDs must match exactly")
  empty <- .BacktestEmptyTables()
  rounds <- list(empty$round_summary);fixtures <- list(empty$fixture_results)
  matches <- list(empty$match_summary);tickets <- list(empty$ticket_returns)
  groups <- list(empty$group_attributions);legs <- list(empty$leg_attributions)
  for (case in experiment$cases) {
    d <- case$decision;ev <- d$plan$evaluation
    labels <- .BacktestLabels(observations[[case$round_id]],d$cutoff)
    actual <- parlay_settle_plan(ev$plan,labels$actual,labels$as_of)
    proxy <- labels$results |> dplyr::inner_join(d$projected$prematch_sp |>
      dplyr::select(fixture_id,outcome,sp_raw),by=c("fixture_id","outcome"),relationship="one-to-one") |>
      dplyr::transmute(issue_id,fixture_id,outcome,settled_sp=sp_raw,
        label_available_at=result_available_at,status="settled",source_url)
    special <- labels$actual |> dplyr::filter(.data$status!="settled")
    proxy <- dplyr::bind_rows(proxy,special)
    priced <- parlay_settle_plan(ev$plan,proxy,labels$as_of)
    t <- actual$ticket_returns |> dplyr::rename(settlement_status=status,
      official_payout_cny=payout_cny,official_net_cny=net_cny) |>
      dplyr::left_join(priced$ticket_returns |> dplyr::select(ticket_id,
        outcome_status=status,frozen_sp_payout_cny=payout_cny),by="ticket_id",relationship="one-to-one") |>
      dplyr::mutate(actual_payout_cny=dplyr::case_when(
        .data$settlement_status=="WON" ~ .data$official_payout_cny,
        .data$settlement_status=="LOST" ~ 0,
        .data$settlement_status=="PENDING" & .data$outcome_status=="LOST" ~ 0,
        TRUE ~ NA_real_),
        frozen_sp_payout_cny=dplyr::if_else(.data$outcome_status %in% c("PENDING","SPECIAL"),NA_real_,.data$frozen_sp_payout_cny),
        actual_net_cny=.data$actual_payout_cny-.data$stake_cny,
        round_id=case$round_id,strategy_id=case$strategy_id,.before=1)
    diagnostic <- ParlayCoverageAttribution(ev,labels$results,labels$as_of)
    for (name in c("groups","legs")) diagnostic[[name]] <- diagnostic[[name]] |>
      dplyr::mutate(round_id=case$round_id,strategy_id=case$strategy_id,issue_id=d$cutoff$issue_id,.before=1)
    groups[[length(groups)+1L]] <- diagnostic$groups;legs[[length(legs)+1L]] <- diagnostic$legs
    p <- d$projected$probabilities |> dplyr::group_by(.data$fixture_id) |>
      dplyr::arrange(dplyr::desc(.data$probability),match(.data$outcome,match_outcomes()),.by_group=TRUE) |>
      dplyr::mutate(probability_rank=as.integer(dplyr::row_number())) |> dplyr::ungroup()
    f <- d$projected$fixtures |> dplyr::filter(.data$fixture_id %in% p$fixture_id) |> dplyr::select(fixture_id,handicap) |>
      dplyr::left_join(labels$results |> dplyr::select(fixture_id,actual_outcome=outcome),by="fixture_id",relationship="one-to-one") |>
      dplyr::left_join(p |> dplyr::select(fixture_id,actual_outcome=outcome,actual_rank=probability_rank),
        by=c("fixture_id","actual_outcome"),relationship="one-to-one") |>
      dplyr::mutate(filtered=.data$fixture_id %in% d$filtered$matches$fixture_id,
        purchased=.data$fixture_id %in% ev$plan$ticket_legs$fixture_id,
        neutral=.data$fixture_id %in% labels$actual$fixture_id[labels$actual$status=="all_options_one"],
        round_id=case$round_id,strategy_id=case$strategy_id,.before=1)
    for (scope in c("projected","filtered","purchased")) {
      block <- if(scope=="projected")f else f[f[[scope]],]
      resolved <- sum(!is.na(block$actual_rank));neutral <- sum(block$neutral)
      for (k in 1:3) matches[[length(matches)+1L]] <- tibble::tibble(
        round_id=case$round_id,strategy_id=case$strategy_id,scope=scope,top_n=as.integer(k),
        n_fixtures=nrow(block),n_resolved=as.integer(resolved),n_neutral=as.integer(neutral),
        n_pending=as.integer(nrow(block)-resolved-neutral),
        hits=as.integer(sum(block$actual_rank<=k,na.rm=TRUE)),
        hit_rate=if(resolved)sum(block$actual_rank<=k,na.rm=TRUE)/resolved else NA_real_)
    }
    stake <- sum(t$stake_cny);money_complete <- !anyNA(t$actual_payout_cny)
    proxy_complete <- !anyNA(t$frozen_sp_payout_cny)
    rounds[[length(rounds)+1L]] <- tibble::tibble(round_id=case$round_id,strategy_id=case$strategy_id,
      issue_id=d$cutoff$issue_id,cutoff_utc=d$cutoff$cutoff_utc,as_of=labels$as_of,
      base=d$probability_base,single_threshold=d$receipt$parameters$single_threshold,
      pattern=paste(d$adapted$pattern,collapse=""),
      n_admitted_fixtures=nrow(d$epoch$fixtures),n_projected_fixtures=dplyr::n_distinct(p$fixture_id),
      n_projection_exclusions=nrow(d$projected$fixtures)-dplyr::n_distinct(p$fixture_id),
      n_groups=nrow(d$selection),n_tickets=nrow(t),
      stake_cny=stake,n_winning_tickets=as.integer(sum(t$outcome_status=="WON")),
      n_pending_results=as.integer(sum(t$outcome_status=="PENDING")),
      n_pending_prices=as.integer(sum(t$outcome_status=="WON" & is.na(t$actual_payout_cny))),
      n_special=as.integer(sum(t$settlement_status=="SPECIAL")),
      n_resolved_tickets=as.integer(sum(t$outcome_status %in% c("WON","LOST"))),
      ticket_hit_rate=if(sum(t$outcome_status %in% c("WON","LOST")))sum(t$outcome_status=="WON")/sum(t$outcome_status %in% c("WON","LOST")) else NA_real_,
      known_actual_payout_cny=sum(t$actual_payout_cny,na.rm=TRUE),
      actual_payout_cny=if(money_complete)sum(t$actual_payout_cny) else NA_real_,
      actual_net_cny=if(money_complete)sum(t$actual_payout_cny)-stake else NA_real_,
      actual_roi=if(money_complete && stake>0)(sum(t$actual_payout_cny)-stake)/stake else NA_real_,
      frozen_sp_payout_cny=if(proxy_complete)sum(t$frozen_sp_payout_cny) else NA_real_,
      frozen_sp_net_cny=if(proxy_complete)sum(t$frozen_sp_payout_cny)-stake else NA_real_,
      model_ev_net_cny=if(anyNA(ev$purchases$ev_net_est))NA_real_ else sum(ev$purchases$ev_net_est),
      status=if(!nrow(t))"NO_BET" else if(sum(t$settlement_status=="SPECIAL"))"SPECIAL" else if(money_complete)"COMPLETE" else "PENDING",
      excluded_future_rows=labels$excluded_future_rows,reconciled_agreements=labels$reconciled_agreements,
      unused_result_rows=as.integer(sum(!labels$results$fixture_id %in% p$fixture_id)),
      unused_settlement_rows=as.integer(sum(!labels$actual$fixture_id %in% p$fixture_id)))
    fixtures[[length(fixtures)+1L]] <- f;tickets[[length(tickets)+1L]] <- t
  }
  # Typed prototypes also preserve schemas when there are no decision cases.
  out <- list(round_summary=dplyr::bind_rows(rounds),match_summary=dplyr::bind_rows(matches),
    fixture_results=dplyr::bind_rows(fixtures),ticket_returns=dplyr::bind_rows(tickets),
    group_attributions=dplyr::bind_rows(groups),leg_attributions=dplyr::bind_rows(legs))
  out$strategy_summary <- out$round_summary |> dplyr::group_by(.data$strategy_id) |>
    dplyr::summarise(n_rounds=dplyr::n(),n_bet_rounds=sum(.data$n_tickets>0),
      n_known_hit_rounds=sum(.data$n_winning_tickets>0),
      n_resolved_hit_rounds=sum(.data$n_tickets>0 & (.data$n_winning_tickets>0 | (.data$n_pending_results==0 & .data$n_special==0))),
      n_pending_rounds=sum(.data$status=="PENDING"),stake_cny=sum(.data$stake_cny),
      known_actual_payout_cny=sum(.data$known_actual_payout_cny),
      actual_payout_cny=sum(.data$actual_payout_cny),actual_net_cny=sum(.data$actual_net_cny),
      frozen_sp_net_cny=sum(.data$frozen_sp_net_cny),.groups="drop") |>
    dplyr::mutate(round_hit_rate=dplyr::if_else(.data$n_resolved_hit_rounds>0,.data$n_known_hit_rounds/.data$n_resolved_hit_rounds,NA_real_),
      actual_roi=dplyr::if_else(.data$stake_cny>0,.data$actual_net_cny/.data$stake_cny,NA_real_))
  out$receipt <- list(input_snapshot=list(experiment=experiment,observations=observations),
    input_hash=rlang::hash(list(experiment=experiment,observations=observations)),output_hash=rlang::hash(out),
    implementation_hash=.rank_outcome_code_hash(c("SummarizeProbabilityBacktest","SummarizeCoverageAttribution")),
    historical_learning_inventory="NONE: posthoc evaluation only; no strategy selection or learning")
  return(out)
}

#' Aggregate purchased-group coverage causes by round and fixture
#' @param backtest Receipt-bound SummarizeProbabilityBacktest output.
#' @return List of round_causes and fixture_causes tibbles and a bound receipt.
#'   Round grain is round/strategy/status; fixture grain is round/strategy/fixture.
#'   Counts refer to overlapping groups, not independent samples or causal losses.
#' @details Structural failures can have multiple offending fixtures; their counts
#'   must not be added as unique lost groups. Depth failures and COVERED_ELSEWHERE
#'   never blame an individually unadmitted fixture. Unknown outcomes remain unknown.
#'   No historical fitting, recommendation, ticket changes or IO.
#' @export
SummarizeCoverageAttribution <- function(backtest) {
  r <- backtest$receipt;bare <- backtest;bare$receipt <- NULL
  if (!is.list(r) || !identical(r$input_hash,rlang::hash(r$input_snapshot)) ||
      !identical(r$output_hash,rlang::hash(bare)) ||
      !identical(r$implementation_hash,.rank_outcome_code_hash(c("SummarizeProbabilityBacktest","SummarizeCoverageAttribution")))) stop("summary receipt differs")
  g <- backtest$group_attributions;l <- backtest$leg_attributions
  # Include no-bet cases as explicit NO_BET rows, without inventing purchased groups.
  round <- g |> dplyr::group_by(.data$round_id,.data$strategy_id,.data$issue_id,.data$status) |>
    dplyr::summarise(n_groups=dplyr::n(),purchased_tickets=sum(.data$purchased_tickets),.groups="drop")
  no_bet <- backtest$round_summary |> dplyr::filter(.data$n_groups==0L) |>
    dplyr::transmute(round_id,strategy_id,issue_id,status="NO_BET",n_groups=0L,purchased_tickets=0L)
  round <- dplyr::bind_rows(round,no_bet)
  fixture <- l |> dplyr::left_join(g |> dplyr::select(round_id,strategy_id,group_id,status),
    by=c("round_id","strategy_id","group_id"),relationship="many-to-one") |>
    dplyr::group_by(.data$round_id,.data$strategy_id,.data$issue_id,.data$fixture_id) |>
    dplyr::summarise(actual_outcome=dplyr::first(.data$actual_outcome),
      n_groups=dplyr::n_distinct(.data$group_id),n_unknown_groups=sum(is.na(.data$admitted)),
      structural_miss_groups=sum(!is.na(.data$admitted) & !.data$admitted),
      participating_depth_miss_groups=sum(.data$status=="DEPTH_MISS"),
      covered_elsewhere_groups=sum(.data$status=="COVERED_ELSEWHERE"),.groups="drop") |>
    dplyr::arrange(dplyr::desc(.data$structural_miss_groups),.data$round_id,.data$strategy_id,.data$fixture_id)
  repeated <- fixture |> dplyr::group_by(.data$strategy_id,.data$issue_id,.data$fixture_id) |>
    dplyr::summarise(n_rounds=dplyr::n_distinct(.data$round_id),
      n_groups=sum(.data$n_groups),rounds_with_structure_miss=sum(.data$structural_miss_groups>0),
      structural_miss_groups=sum(.data$structural_miss_groups),
      n_unknown_groups=sum(.data$n_unknown_groups),.groups="drop") |>
    dplyr::arrange(dplyr::desc(.data$structural_miss_groups),.data$strategy_id,.data$fixture_id)
  out <- list(round_causes=round,fixture_causes=fixture,repeated_fixtures=repeated)
  out$receipt <- list(input_hash=rlang::hash(backtest),output_hash=rlang::hash(out),
    implementation_hash=.rank_outcome_code_hash("SummarizeCoverageAttribution"),
    posthoc_diagnostic=TRUE)
  return(out)
}

#' Typed zero-case schemas for the descriptive evaluator
#' @return List of six zero-row tibbles, matching normal output keys/types/units.
#' @details Reuses authoritative role-leg schema; no synthetic production data or IO.
#' @noRd
.BacktestEmptyTables <- function() {
  utc <- as.POSIXct(numeric(),origin="1970-01-01",tz="UTC")
  l <- .parlay_role_typed_empty("legs")
  l$actual_outcome <- character();l$admitted <- logical()
  l <- l |> dplyr::mutate(round_id=character(),strategy_id=character(),issue_id=character(),.before=1)
  return(list(round_summary=tibble::tibble(round_id=character(),strategy_id=character(),
    issue_id=character(),cutoff_utc=utc,as_of=utc,base=character(),single_threshold=double(),
    pattern=character(),n_admitted_fixtures=integer(),n_projected_fixtures=integer(),n_projection_exclusions=integer(),n_groups=integer(),n_tickets=integer(),stake_cny=double(),
    n_winning_tickets=integer(),n_pending_results=integer(),n_pending_prices=integer(),
    n_special=integer(),n_resolved_tickets=integer(),ticket_hit_rate=double(),
    known_actual_payout_cny=double(),actual_payout_cny=double(),actual_net_cny=double(),
    actual_roi=double(),frozen_sp_payout_cny=double(),frozen_sp_net_cny=double(),
    model_ev_net_cny=double(),status=character(),excluded_future_rows=integer(),reconciled_agreements=integer(),unused_result_rows=integer(),unused_settlement_rows=integer()),
    match_summary=tibble::tibble(round_id=character(),strategy_id=character(),scope=character(),
      top_n=integer(),n_fixtures=integer(),n_resolved=integer(),n_neutral=integer(),n_pending=integer(),hits=integer(),hit_rate=double()),
    fixture_results=tibble::tibble(round_id=character(),strategy_id=character(),fixture_id=character(),
      handicap=integer(),actual_outcome=character(),actual_rank=integer(),filtered=logical(),purchased=logical(),neutral=logical()),
    ticket_returns=tibble::tibble(round_id=character(),strategy_id=character(),ticket_id=character(),
      group_id=character(),settlement_status=character(),stake_cny=double(),official_payout_cny=double(),
      official_net_cny=double(),outcome_status=character(),frozen_sp_payout_cny=double(),actual_payout_cny=double(),actual_net_cny=double()),
    group_attributions=tibble::tibble(round_id=character(),strategy_id=character(),issue_id=character(),group_id=character(),
      group_slot=integer(),legal_space=double(),purchased_tickets=integer(),structural_misses=integer(),unknown_legs=integer(),winner_rank=integer(),
      purchased_winner=logical(),winner_owned_elsewhere=logical(),depth_blocked=logical(),status=character()),
    leg_attributions=l))
}
