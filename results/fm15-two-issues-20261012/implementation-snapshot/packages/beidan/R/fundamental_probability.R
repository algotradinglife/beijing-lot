# Internal artifact integrity and code identity. No source admission is duplicated.
.fundamental_code_hash <- function() {
  rlang::hash(list(bodies=lapply(list(fundamental_goal_baseline, apply_goal_adjustments,
    compare_fundamental_market, .fundamental_verify, .fundamental_finish,
    .fundamental_code_hash, dixon_coles_score_grid, dc_tau_multiplier,
    dc_validate_rho, market_score_projection, total_market_constraint,
    asian_total_probability, total_constrained_projection, match_require_cutoff), body),
    packages=lapply(c("tibble","dplyr","lubridate","checkmate","reticulate","rlang","stats","digest"),utils::packageVersion),
    R=getRversion()))
}

.fundamental_verify <- function(x) {
  if (!inherits(x, "fundamental_scenario")) stop("Explicit fundamental scenario required")
  seal <- x$seal; x$seal <- NULL
  if (!identical(seal, rlang::hash(x))) stop("Scenario integrity differs")
  match_require_cutoff(x$cutoff)
  if (!identical(x$receipt$implementation_hash, .fundamental_code_hash()))
    stop("Scenario implementation differs; rebuild required")
  if (!identical(x$cutoff$issue_id, x$fixture$issue_id) ||
      !identical(x$receipt$cutoff_hash, rlang::hash(x$cutoff)) ||
      as.numeric(lubridate::ymd_hms(x$receipt$source_context$cutoff_ts,tz="UTC"))!=as.numeric(x$cutoff$cutoff_utc) ||
      x$receipt$source_context$cutoff_identity!=paste0("DECISION_EPOCH_",x$cutoff$issue_id) ||
      !identical(x$receipt$fixture_hash,rlang::hash(x$fixture)) ||
      !identical(x$receipt$policy_hash,rlang::hash(x$policy))) stop("Cutoff binding differs")
  invisible(TRUE)
}

.fundamental_finish <- function(x) {
  p <- x$parameters
  dc <- dixon_coles_score_grid(p$lambda_home, p$lambda_away,
    x$fixture$handicap, x$policy$tail_tolerance, x$policy$rho)
  x$probabilities <- tibble::tibble(fixture_id=x$fixture$fixture_id,
    stage=p$stage, market="handicap", outcome=c("W","D","L"),
    probability=unname(dc$probability))
  ordinary <- dixon_coles_score_grid(p$lambda_home,p$lambda_away,0L,
    x$policy$tail_tolerance,x$policy$rho)
  x$ordinary <- tibble::tibble(outcome=c("W","D","L"),
    probability=unname(ordinary$probability))
  revision <- nrow(x$ledger)
  history <- dplyr::mutate(p,revision=revision)
  prob_history <- dplyr::mutate(x$probabilities,revision=revision)
  if(is.null(x$parameter_history)) {
    x$parameter_history <- history
    x$probability_history <- prob_history
  } else if(!revision %in% x$parameter_history$revision) {
    x$parameter_history <- dplyr::bind_rows(x$parameter_history,history)
    x$probability_history <- dplyr::bind_rows(x$probability_history,prob_history)
  }
  x$receipt$selected_parameters <- as.list(x$parameters[1,])
  x$receipt$cache_reuse <- "NONE"
  x$receipt$omitted_mass <- dc$omitted_mass
  x$receipt$implementation_hash <- .fundamental_code_hash()
  x$receipt$cutoff_hash <- rlang::hash(x$cutoff)
  x$seal <- NULL
  class(x) <- c("fundamental_scenario","list")
  x$seal <- rlang::hash(x)
  x
}

#' Construct a manual goal scenario from admitted venue summary snapshots
#'
#' @param context Opaque shared Python temporal_learning LearningContext. Its
#'   explicit decision cutoff, source/fixture/code bindings and availability
#'   are independently verified; date proxies authorize diagnostics only.
#' @param fixture One-row tibble with character fixture_id, issue_id, home,
#'   away and integer-valued handicap. IDs and leading zeros are preserved.
#' @param policy List with explicit rho, tail_tolerance, minimum_matches, lambda_digits.
#'   Minimum support applies to each venue summary. Rates use goals/match;
#'   lambdas are the cross mean of own scoring and opponent conceding rates.
#' @param repository_root Explicit repository with declared .venv/bin/python.
#' @return Sealed fundamental_scenario list: typed fixture, parameters,
#'   probabilities, ordinary probabilities, summaries, empty adjustment ledger,
#'   explicit cutoff and machine-readable shared-source/computation receipt.
#' @details No HTTP, writes, packages installed, parameter fitting or hidden
#'   weighting. Reticulate selects the explicit interpreter. Historical admission
#'   is owned by the shared context; insufficient, conflicting or zero support
#'   and nonpositive means fail. This is a manual-rate scenario, not calibrated xG.
#' @export
fundamental_goal_baseline <- function(context, fixture, policy, repository_root) {
  checkmate::assert_tibble(fixture, nrows=1L)
  checkmate::assert_names(names(fixture),must.include=c("fixture_id","issue_id","home","away","handicap"))
  fixture <- dplyr::select(fixture,fixture_id,issue_id,home,away,handicap)
  for (k in c("fixture_id","issue_id","home","away"))
    checkmate::assert_character(fixture[[k]],len=1L,any.missing=FALSE,min.chars=1L)
  checkmate::assert_integerish(fixture$handicap,len=1L,any.missing=FALSE)
  if (fixture$home==fixture$away) stop("Distinct target teams required")
  checkmate::assert_list(policy)
  checkmate::assert_count(policy$minimum_matches,positive=TRUE)
  checkmate::assert_count(policy$lambda_digits)
  if (policy$lambda_digits>10) stop("At most ten lambda digits supported")
  dc_validate_rho(policy$rho)
  checkmate::assert_number(policy$tail_tolerance,lower=0,upper=.01,finite=TRUE)
  reticulate::use_python(file.path(repository_root,".venv/bin/python"),required=TRUE)
  sys <- reticulate::import("sys",convert=FALSE)
  if (!identical(normalizePath(reticulate::py_to_r(sys$prefix)),normalizePath(file.path(repository_root,".venv")))) stop("Project Python environment required")
  invisible(sys$path$insert(0L,file.path(repository_root,"packages/beidan/inst/python")))
  backend <- reticulate::import("beidan_backend.fundamental_probability",convert=FALSE)
  if (!identical(digest::digest(file=reticulate::py_to_r(backend$`__file__`),algo="sha256"),
    digest::digest(file=file.path(repository_root,"packages/beidan/inst/python/beidan_backend/fundamental_probability.py"),
      algo="sha256"))) stop("Backend implementation differs")
  if (!inherits(context,"python.builtin.object")) stop("Opaque shared learning context required")
  native <- reticulate::py_to_r(backend$export_goal_baseline_context(context,
    as.list(fixture[1,]),repository_root))
  summaries <- dplyr::bind_rows(native$summaries) |>
    dplyr::mutate(dplyr::across(c(matches,goals_for,goals_against),as.integer))
  if (!tibble::is_tibble(summaries) || nrow(summaries)!=2L || anyNA(summaries) ||
      any(summaries$matches<policy$minimum_matches)) stop("Insufficient venue support")
  home <- dplyr::filter(summaries,team==fixture$home,venue=="home")
  away <- dplyr::filter(summaries,team==fixture$away,venue=="away")
  lambda <- c((home$goals_for/home$matches+away$goals_against/away$matches)/2,
              (away$goals_for/away$matches+home$goals_against/home$matches)/2)
  lambda <- round(lambda,policy$lambda_digits)
  if (any(!is.finite(lambda)) || any(lambda<=0)) stop("Positive goal means required")
  cutoff <- list(issue_id=native$issue_id,
    cutoff_utc=as.POSIXct(native$cutoff_epoch,origin="1970-01-01",tz="UTC"))
  .fundamental_finish(list(fixture=fixture,cutoff=cutoff,policy=policy,
    parameters=tibble::tibble(stage="data_baseline",lambda_home=lambda[1],lambda_away=lambda[2],rho=policy$rho),
    summaries=summaries,repository_root=repository_root,
    evidence=tibble::tibble(evidence_id=character(),fixture_id=character(),source_hash=character()),
    ledger=tibble::tibble(adjustment_id=character(),stage=character(),parameter=character(),
      delta_goals=double(),evidence_id=character(),reason=character()),
    receipt=list(model="MANUAL_VENUE_CROSS_MEAN_DC",source_context=native$receipt,
      fixture_hash=rlang::hash(fixture),policy_hash=rlang::hash(policy))))
}

#' Execute explicit human goal-mean adjustments without choosing their effects
#' @param parameters Sealed fundamental_scenario returned by the baseline or this
#'   function; its cutoff is embedded and integrity is checked before use.
#' @param adjustments Tibble with adjustment_id, stage, parameter, delta_goals,
#'   evidence_id, reason; one row per evidence/parameter adjustment. Stages are
#'   qualitative then market_review. Typed empty input is a no-op. IDs cannot
#'   repeat across calls. parameter is lambda_home or lambda_away, never rho.
#' @param policy List with explicit max_absolute_delta, a nonnegative bound on
#'   each adjustment in goals/match. It is a disclosed manual bound, not learned.
#' @return A newly sealed scenario with accumulated ledger and recomputed DC.
#' @details Pure arithmetic, no fitting or I/O. Missing reasons/evidence IDs,
#'   invalid values, backward stages or nonpositive resulting lambdas fail.
#'   Evidence IDs refer to the caller's source-bound evidence table; this function
#'   does not establish the factual validity of narrative effects.
#' @export
apply_goal_adjustments <- function(parameters, adjustments, policy) {
  .fundamental_verify(parameters)
  checkmate::assert_tibble(adjustments)
  required <- c("adjustment_id","stage","parameter","delta_goals","evidence_id","reason")
  checkmate::assert_names(names(adjustments),must.include=required)
  adjustments <- dplyr::select(adjustments,dplyr::all_of(required))
  for (k in setdiff(required,"delta_goals"))
    checkmate::assert_character(adjustments[[k]],any.missing=FALSE,min.chars=1L)
  checkmate::assert_numeric(adjustments$delta_goals,any.missing=FALSE,finite=TRUE)
  checkmate::assert_number(policy$max_absolute_delta,lower=0,finite=TRUE)
  if (any(abs(adjustments$delta_goals)>policy$max_absolute_delta)) stop("Adjustment exceeds explicit bound")
  if (!nrow(adjustments)) return(parameters)
  backend <- reticulate::import("beidan_backend.fundamental_probability",convert=FALSE)
  if(!inherits(policy$evidence_context,"python.builtin.object")) stop("Shared evidence context required")
  native <- reticulate::py_to_r(backend$export_adjustment_evidence_context(
    policy$evidence_context,as.list(parameters$fixture),as.numeric(parameters$cutoff$cutoff_utc),
    parameters$receipt$source_context$availability$intended_use,parameters$repository_root))
  evidence <- dplyr::bind_rows(native$evidence)
  if(any(!adjustments$evidence_id %in% evidence$evidence_id)) stop("Evidence unavailable before cutoff")
  known <- intersect(evidence$evidence_id,parameters$evidence$evidence_id)
  if(length(known) && !identical(
      dplyr::arrange(dplyr::filter(evidence,evidence_id %in% known),evidence_id),
      dplyr::arrange(dplyr::filter(parameters$evidence,evidence_id %in% known),evidence_id)))
    stop("Earlier evidence binding changed; rebuild required")
  if(length(unique(adjustments$stage))!=1L) stop("One stage per call required")
  if (anyDuplicated(c(parameters$ledger$adjustment_id,adjustments$adjustment_id)))
    stop("Duplicate adjustment identity")
  ranks <- match(adjustments$stage,c("qualitative","market_review"))
  old <- match(parameters$parameters$stage,c("data_baseline","qualitative","market_review"))-1L
  if (anyNA(ranks) || any(diff(c(old,ranks))<0)) stop("Invalid or backward adjustment stage")
  if (any(!adjustments$parameter %in% c("lambda_home","lambda_away"))) stop("Invalid adjusted parameter")
  x <- parameters
  for (i in seq_len(nrow(adjustments))) {
    k <- adjustments$parameter[i]
    x$parameters[[k]] <- x$parameters[[k]]+adjustments$delta_goals[i]
    if (x$parameters[[k]]<=0) stop("Adjustment produces nonpositive lambda")
  }
  x$parameters$stage <- tail(adjustments$stage,1)
  x$ledger <- dplyr::bind_rows(x$ledger,adjustments)
  x$receipt$parent_seal <- parameters$seal
  used <- dplyr::filter(evidence,evidence_id %in% adjustments$evidence_id)
  x$evidence <- dplyr::bind_rows(parameters$evidence,
    dplyr::anti_join(used,parameters$evidence,by="evidence_id"))
  x$receipt$adjustment_policies <- c(parameters$receipt$adjustment_policies,
    list(list(first_row=nrow(parameters$ledger)+1L,last_row=nrow(x$ledger),
      max_absolute_delta=policy$max_absolute_delta,evidence_context=native$receipt,
      evidence=used)))
  .fundamental_finish(x)
}

#' Compare a fundamental scenario with same-cutoff market quotes
#' @param fundamental Sealed scenario with embedded cutoff.
#' @param market Tibble of raw ordinary decimal 1X2 quotes: company_id,
#'   fixture_id, quote_at (POSIXct), odds_home, odds_draw, odds_away. Multiple
#'   times per company are allowed; duplicate company/time pairs are errors.
#' @param totals Tibble of decimal total quotes: company_id, fixture_id,
#'   quote_at, line, over_decimal, under_decimal. Typed empty input is allowed.
#' @param decision Explicit list issue_id, cutoff_utc, max_quote_age_hours,
#'   total_bounds. Cutoff must match the scenario; stale quotes are retained and
#'   flagged against the disclosed age limit. Future quotes are inventoried.
#' @return List of selected quote tibbles, comparison tibble in ordinary W/D/L,
#'   total inversion and fixed-rho market projection (NULL if no totals), and
#'   receipt binding cutoff, source tables, age policy, exclusions and code.
#' @details Pure arithmetic, no fetching, learned blending or automatic lambda
#'   changes. Empty markets return typed empty comparison. Totals currently
#'   require half-goal lines >=2.5: DC corrections cancel on these sides.
#'   Other lines fail rather than silently applying Poisson to DC settlement.
#' @export
compare_fundamental_market <- function(fundamental, market, totals, decision) {
  .fundamental_verify(fundamental)
  match_require_cutoff(decision)
  if (!identical(decision$issue_id,fundamental$cutoff$issue_id) ||
      as.numeric(decision$cutoff_utc)!=as.numeric(fundamental$cutoff$cutoff_utc)) stop("Decision cutoff mismatch")
  checkmate::assert_number(decision$max_quote_age_hours,lower=0,finite=TRUE)
  selected <- list(); counts <- list()
  for (kind in c("market","totals")) {
    q <- if (kind=="market") market else totals
    checkmate::assert_tibble(q)
    required <- c("company_id","fixture_id","quote_at",if(kind=="market")
      c("odds_home","odds_draw","odds_away") else c("line","over_decimal","under_decimal"))
    checkmate::assert_names(names(q),must.include=required)
    q <- dplyr::select(q,dplyr::all_of(required))
    for (k in c("company_id","fixture_id")) checkmate::assert_character(q[[k]],any.missing=FALSE,min.chars=1L)
    if (!inherits(q$quote_at,"POSIXct") || anyNA(q$quote_at) || any(!is.finite(as.numeric(q$quote_at)))) stop("Typed quote times required")
    if (any(q$fixture_id!=fundamental$fixture$fixture_id)) stop("Market fixture mismatch")
    input_n <- nrow(q)
    future_n <- sum(q$quote_at>=decision$cutoff_utc)
    q <- dplyr::filter(q,quote_at<decision$cutoff_utc)
    if (anyDuplicated(q[c("company_id","quote_at")])) stop("Conflicting company/time quotes")
    for (k in setdiff(required,c("company_id","fixture_id","quote_at")))
      checkmate::assert_numeric(q[[k]],any.missing=FALSE,finite=TRUE)
    prices <- if(kind=="market") c("odds_home","odds_draw","odds_away") else c("over_decimal","under_decimal")
    if (any(as.matrix(q[prices])<=1)) stop("Decimal odds must exceed one")
    if(kind=="totals" && any(q$line<2.5 | q$line*2!=round(q$line*2) | q$line==round(q$line)))
      stop("DC total comparison requires half-goal lines >=2.5")
    prior <- q |> dplyr::filter(quote_at<decision$cutoff_utc) |>
      dplyr::arrange(company_id,dplyr::desc(quote_at)) |>
      dplyr::group_by(company_id) |> dplyr::slice_head(n=1) |> dplyr::ungroup() |>
      dplyr::mutate(age_hours=as.numeric(difftime(decision$cutoff_utc,quote_at,units="hours")),
        stale=age_hours>decision$max_quote_age_hours)
    selected[[kind]] <- prior
    counts[[kind]] <- list(input=input_n,future_or_cutoff=future_n,
      superseded=sum(q$quote_at<decision$cutoff_utc)-nrow(prior),selected=nrow(prior),stale=sum(prior$stale))
  }
  comparison <- tibble::tibble(outcome=character(),fundamental=double(),market=double(),difference=double())
  m <- selected$market
  if(nrow(m)) {
    inv <- 1/as.matrix(m[c("odds_home","odds_draw","odds_away")])
    p <- colMeans(inv/rowSums(inv))
    comparison <- fundamental$ordinary |> dplyr::transmute(outcome,fundamental=probability,
      market=unname(p),difference=fundamental-market)
  }
  t <- selected$totals; total <- NULL; projection <- NULL
  if(nrow(t)) {
    total <- total_market_constraint(t |> dplyr::mutate(company=company_id,
      over_hk=over_decimal-1,under_hk=under_decimal-1),decision$total_bounds)
    if(nrow(comparison)) projection <- total_constrained_projection(total$lambda_total,
      comparison$market,0L,fundamental$policy$tail_tolerance,fundamental$policy$rho)
  }
  list(market=m,totals=t,comparison=comparison,total=total,projection=projection,
    receipt=list(cutoff=fundamental$cutoff,fundamental_seal=fundamental$seal,
      market_hash=rlang::hash(market),totals_hash=rlang::hash(totals),decision_hash=rlang::hash(decision),
      exclusions=counts,implementation_hash=.fundamental_code_hash()))
}
