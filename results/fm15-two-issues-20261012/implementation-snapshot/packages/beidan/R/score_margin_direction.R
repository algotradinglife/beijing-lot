# Deterministic JSON identity, including typed tables and explicit cutoff objects.
.score_margin_hash <- function(x) {
  # JSON timestamp defaults round to milliseconds; preserve IEEE double identity
  # without readr spec/environment attributes or R serialization session state.
  encode <- function(z) {
    if(inherits(z,"POSIXct")) return(list(type="POSIXct",seconds=sprintf("%.17g",as.numeric(z)),timezone=attr(z,"tzone")))
    if(is.data.frame(z)) return(list(type="table",columns=lapply(z,encode),nrows=nrow(z)))
    if(is.list(z)) return(lapply(z,encode))
    if(is.double(z)) return(list(type="double",values=sprintf("%.17g",z),names=names(z)))
    if(is.integer(z)) return(list(type="integer",values=z,names=names(z)))
    z
  }
  digest::digest(jsonlite::toJSON(encode(x),auto_unbox=TRUE,
    null="null",na="string"),algo="sha256",serialize=FALSE)
}

# Bind this arithmetic and imported DC/cutoff primitives to shared source admission.
.score_margin_code <- function(repository_root) {
  .score_margin_hash(list(
    source=digest::digest(file=file.path(repository_root,"packages/beidan/R/score_margin_direction.R"),algo="sha256"),
    bodies=lapply(list(adjust_score_margin_distribution,project_dc_market_handicap,project_score_outcomes,.score_margin_hash,.score_margin_code,
      dixon_coles_score_grid,dc_tau_multiplier,dc_validate_rho,match_require_cutoff,match_check_character_id),
      function(f) paste(deparse(body(f)),collapse="\n")),
    versions=lapply(c("dplyr","tibble","checkmate","digest","jsonlite","reticulate","stats","utils","lubridate"),function(p) as.character(utils::packageVersion(p))),
    R=as.character(getRversion())))
}

#' Project DC goal means from same-cutoff Euro and Asian-handicap pricing
#' @param euro Tibble company_id, fixture_id, quote_at (POSIXct), odds_home,
#'   odds_draw, odds_away in decimal odds. Latest strictly prior quote per company.
#' @param asian Tibble company_id, fixture_id, quote_at, handicap (signed home
#'   quarter-goal line), home_decimal, away_decimal. Latest prior quote per company.
#' @param total_mean Explicit positive total goal mean from same-cutoff OU inversion.
#' @param rho Explicit fixed feasible DC dependence parameter.
#' @param policy List euro_weight, asian_weight (positive), lambda_floor (>0),
#'   tail_tolerance, max_quote_age_hours. Not learned from the target.
#' @param context Shared evidence context binding dc_market_input to
#'   .score_margin_hash(list(euro=euro,asian=asian,total_mean=total_mean,rho=rho,
#'   policy=policy,fixture=fixture,cutoff=cutoff)) and direction_implementation to
#'   .score_margin_code(repository_root). Each selected quote is admitted as a
#'   quote evidence row, ID euro-COMPANY or asian-COMPANY, source_hash equal to
#'   .score_margin_hash(selected canonical row). No outcome-label training.
#' @param fixture One-row typed fixture as in adjust_score_margin_distribution.
#' @param cutoff Explicit UTC decision cutoff.
#' @param repository_root Explicit repository and project Python.
#' @param intended_use HISTORICAL_DIAGNOSTIC or PROSPECTIVE_DECISION.
#' @return Parameters, selected quotes, market and model comparisons, normalized
#'   score grid and cutoff-bound receipt. Pure market inversion, no fetching/writes.
#' @details Fixed total mean and rho leave one free goal-share parameter. Minimize
#'   weighted channel mean squared residual: ordinary 1X2 and Asian settled-stake
#'   win share. Normalize reciprocal decimal prices per company. Quarter lines
#'   split half stakes; pushes excluded from the win/loss share. This share is
#'   not unconditional handicap win probability. Unsupported/stale inputs,
#'   unbound quotes, infeasible DC domains and boundary solutions fail closed.
#' @export
project_dc_market_handicap <- function(euro,asian,total_mean,rho,policy,context,fixture,cutoff,repository_root,intended_use) {
  match_require_cutoff(cutoff)
  checkmate::assert_tibble(fixture,nrows=1L)
  checkmate::assert_names(names(fixture),identical.to=c("fixture_id","issue_id","home","away"))
  for(k in c("fixture_id","issue_id","home","away")) checkmate::assert_character(fixture[[k]],len=1L,any.missing=FALSE,min.chars=1L)
  if(fixture$issue_id!=cutoff$issue_id || !startsWith(fixture$fixture_id,paste0(fixture$issue_id,":")) || fixture$home==fixture$away) stop("Fixture cutoff differs")
  checkmate::assert_number(total_mean,lower=0,finite=TRUE)
  dc_validate_rho(rho)
  for(k in c("euro_weight","asian_weight","lambda_floor","tail_tolerance","max_quote_age_hours")) checkmate::assert_number(policy[[k]],lower=0,finite=TRUE)
  if(policy$euro_weight==0 || policy$asian_weight==0 || policy$lambda_floor==0 || policy$lambda_floor*2>=total_mean || policy$tail_tolerance> .01) stop("Positive channel weights and feasible lambda bounds required")
  checkmate::assert_choice(intended_use,c("HISTORICAL_DIAGNOSTIC","PROSPECTIVE_DECISION"))
  input_hash <- .score_margin_hash(list(euro=euro,asian=asian,total_mean=total_mean,rho=rho,policy=policy,fixture=fixture,cutoff=cutoff))
  selected <- list();counts <- list()
  for(kind in c("euro","asian")) {
    q <- if(kind=="euro") euro else asian
    required <- c("company_id","fixture_id","quote_at",if(kind=="euro") c("odds_home","odds_draw","odds_away") else c("handicap","home_decimal","away_decimal"))
    checkmate::assert_tibble(q);checkmate::assert_names(names(q),identical.to=required)
    for(k in c("company_id","fixture_id")) checkmate::assert_character(q[[k]],any.missing=FALSE,min.chars=1L)
    if(!inherits(q$quote_at,"POSIXct") || anyNA(q$quote_at) || any(!is.finite(as.numeric(q$quote_at))) || any(q$fixture_id!=fixture$fixture_id)) stop("Typed quote chronology and matching fixture required")
    counts[[kind]] <- list(input=nrow(q),future_or_cutoff=sum(q$quote_at>=cutoff$cutoff_utc))
    q <- dplyr::filter(q,quote_at<cutoff$cutoff_utc)
    if(anyDuplicated(q[c("company_id","quote_at")])) stop("Duplicate quote identity")
    for(k in setdiff(required,c("company_id","fixture_id","quote_at"))) checkmate::assert_numeric(q[[k]],finite=TRUE,any.missing=FALSE)
    price_cols <- if(kind=="euro") c("odds_home","odds_draw","odds_away") else c("home_decimal","away_decimal")
    if(any(as.matrix(q[price_cols])<=1)) stop("Decimal prices must exceed one")
    if(kind=="asian" && any(q$handicap*4!=round(q$handicap*4))) stop("Quarter-goal Asian lines required")
    q <- q |> dplyr::arrange(company_id,dplyr::desc(quote_at)) |> dplyr::group_by(company_id) |> dplyr::slice_head(n=1L) |> dplyr::ungroup()
    if(!nrow(q) || any(as.numeric(difftime(cutoff$cutoff_utc,q$quote_at,units="hours"))>policy$max_quote_age_hours)) stop("Missing or stale market channel")
    selected[[kind]] <- q;counts[[kind]]$selected <- nrow(q)
  }
  reticulate::use_python(file.path(repository_root,".venv/bin/python"),required=TRUE)
  sys <- reticulate::import("sys",convert=FALSE)
  if(!identical(normalizePath(reticulate::py_to_r(sys$prefix)),normalizePath(file.path(repository_root,".venv")))) stop("Project Python required")
  sys$path$insert(0L,file.path(repository_root,"packages/beidan/inst/python"))
  backend <- reticulate::import("beidan_backend.fundamental_probability",convert=FALSE)
  if(!inherits(context,"python.builtin.object")) stop("Shared market evidence context required")
  native <- reticulate::py_to_r(backend$export_adjustment_evidence_context(context,as.list(fixture),as.numeric(cutoff$cutoff_utc),intended_use,repository_root))
  if(!identical(native$receipt$source_hashes$dc_market_input,input_hash) || !identical(native$receipt$source_hashes$direction_implementation,.score_margin_code(repository_root))) stop("Market input/code binding differs")
  admitted <- dplyr::bind_rows(native$evidence)
  for(kind in names(selected)) for(i in seq_len(nrow(selected[[kind]]))) {
    row <- selected[[kind]][i,];id <- paste0(kind,"-",row$company_id)
    bound <- dplyr::filter(admitted,evidence_id==id)
    if(nrow(bound)!=1 || bound$source_hash!=.score_margin_hash(row)) stop("Selected quote evidence unavailable or hash differs")
  }
  inv <- 1/as.matrix(selected$euro[c("odds_home","odds_draw","odds_away")])
  euro_target <- unname(colMeans(inv/rowSums(inv)))
  ah <- selected$asian |> dplyr::mutate(target_share=away_decimal/(home_decimal+away_decimal))
  # Mature stats optimization; local domain callback contains no chronology.
  evaluate <- function(lambda_home) {
    dc <- dixon_coles_score_grid(lambda_home,total_mean-lambda_home,0L,policy$tail_tolerance,rho)
    g <- dc$grid; margin <- g$home_goals-g$away_goals
    shares <- numeric(nrow(ah));win <- numeric(nrow(ah));loss <- numeric(nrow(ah))
    for(i in seq_len(nrow(ah))) {
      legs <- c(floor(ah$handicap[i]*2),ceiling(ah$handicap[i]*2))/2
      win[i] <- mean(vapply(legs,function(h) sum(g$probability[margin+h>0]),numeric(1)))
      loss[i] <- mean(vapply(legs,function(h) sum(g$probability[margin+h<0]),numeric(1)))
      if(win[i]+loss[i]<=0) stop("No settled Asian stake support")
      shares[i] <- win[i]/(win[i]+loss[i])
    }
    euro_error <- mean((unname(dc$probability)-euro_target)^2)
    asian_error <- mean((shares-ah$target_share)^2)
    list(dc=dc,shares=shares,win=win,loss=loss,euro_error=euro_error,asian_error=asian_error,
      objective=policy$euro_weight*euro_error+policy$asian_weight*asian_error)
  }
  # Fail before optimizer on infeasible DC domains, rather than hiding errors.
  lo <- policy$lambda_floor;hi <- total_mean-policy$lambda_floor
  for(lh in c(lo,(lo+hi)/2,hi)) evaluate(lh)
  fitted <- stats::optimize(function(lh) evaluate(lh)$objective,c(lo,hi),tol=1e-8)
  if(min(fitted$minimum-lo,hi-fitted$minimum)<1e-6) stop("Market solution at lambda boundary")
  result <- evaluate(fitted$minimum)
  ordinary <- tibble::tibble(outcome=c("W","D","L"),market=euro_target,model=unname(result$dc$probability)) |> dplyr::mutate(residual=model-market)
  ah <- ah |> dplyr::mutate(model_share=result$shares,win_mass=result$win,loss_mass=result$loss,fair_home_decimal=1+loss_mass/win_mass,residual=model_share-target_share)
  parameters <- tibble::tibble(lambda_home=fitted$minimum,lambda_away=total_mean-fitted$minimum,rho=rho,total_mean=total_mean,lambda_difference=2*fitted$minimum-total_mean)
  grid <- tibble::as_tibble(result$dc$grid) |> dplyr::select(home_goals,away_goals,probability)
  receipt <- list(model_id="DC_FIXED_TOTAL_EURO_ASIAN_PROJECTION",cutoff=list(issue_id=cutoff$issue_id,cutoff_utc=format(cutoff$cutoff_utc,"%Y-%m-%dT%H:%M:%OS6Z",tz="UTC")),fixture=as.list(fixture),policy=policy,selected_parameters=parameters,
    input_hash=input_hash,implementation_hash=.score_margin_code(repository_root),source_context=native$receipt,exclusions=counts,
    channel_errors=list(euro=result$euro_error,asian=result$asian_error,objective=result$objective),
    omitted_mass=result$dc$omitted_mass,output_hash=.score_margin_hash(list(parameters=parameters,grid=grid,ordinary=ordinary,asian=ah)),
    cache_reuse="NONE",cache_key=.score_margin_hash(list(cutoff=cutoff,input_hash=input_hash,code=.score_margin_code(repository_root))))
  list(parameters=parameters,grid=grid,ordinary=ordinary,asian=ah,euro=selected$euro,receipt=receipt)
}

#' Adjust a score distribution using independent net-goal judgments
#'
#' @param base List with normalized tibble grid (home_goals, away_goals,
#'   probability), cutoff (issue_id, cutoff_utc in UTC), model_id, source_hashes,
#'   max_source_available_utc (POSIXct), and intended_use (HISTORICAL_DIAGNOSTIC
#'   or PROSPECTIVE_DECISION). The grid and provenance are bound by shared context.
#' @param judgement List with bins tibble: bin_id, min_margin, max_margin,
#'   target_mass, evidence_id, reason. Inclusive integer endpoints, with -Inf/Inf
#'   allowed for tails. Bins cover all integers without gaps/overlaps. Also
#'   model_id and a disclosed rationale. Northsingle roles are forbidden inputs;
#'   masses are explicit expert net-goal judgments independent of ticket lines.
#' @param context Opaque, independently verified temporal_learning evidence
#'   context. source_hashes must include base_artifact=.score_margin_hash(base),
#'   margin_judgement=.score_margin_hash(judgement), and
#'   direction_implementation=.score_margin_code(repository_root).
#' @param fixture One-row tibble with character fixture_id, issue_id, home, away
#'   only. Northsingle handicap is deliberately absent from calibration inputs.
#' @param cutoff Explicit issue_id/cutoff_utc; must match base and shared context.
#' @param repository_root Explicit repository with .venv/bin/python.
#' @return List with final score/margin/bin tibbles and JSON-safe
#'   receipt: cutoff, input and code identities, shared evidence receipt, no-cache
#'   identity and observable gates. Project betting outcomes separately after
#'   freezing this grid. Final grid is expert-reweighted, not a DC
#'   family; within-bin conditional score proportions are retained.
#' @details No fetching, writes, learning or betting-line/rank constraints. Invalid
#'   chronology, absent evidence, unsupported positive bins and non-normalized
#'   grids or masses fail closed. Betting roles cannot govern calibration.
#'   Targets reflect human confidence; this function does not establish its truth.
#' @export
adjust_score_margin_distribution <- function(base, judgement, context, fixture, cutoff, repository_root) {
  if("roles" %in% names(judgement)) stop("Betting roles cannot govern score calibration")
  checkmate::assert_names(names(judgement),identical.to=c("model_id","rationale","bins"))
  if(any(c("handicap","roles","beidan_handicap") %in% names(base))) stop("Ticket line cannot govern score calibration")
  match_require_cutoff(cutoff);match_require_cutoff(base$cutoff)
  if(!identical(cutoff,base$cutoff)) stop("Base cutoff differs; rebuild required")
  checkmate::assert_tibble(fixture,nrows=1L)
  checkmate::assert_names(names(fixture),identical.to=c("fixture_id","issue_id","home","away"))
  for(k in c("fixture_id","issue_id","home","away")) checkmate::assert_character(fixture[[k]],len=1L,any.missing=FALSE,min.chars=1L)
  if(fixture$issue_id!=cutoff$issue_id || !startsWith(fixture$fixture_id,paste0(fixture$issue_id,":")) || fixture$home==fixture$away) stop("Fixture/cutoff binding differs")
  checkmate::assert_character(base$model_id,len=1L,any.missing=FALSE,min.chars=1L)
  checkmate::assert_list(base$source_hashes,min.len=1L,names="unique")
  checkmate::assert_character(unlist(base$source_hashes,use.names=FALSE),any.missing=FALSE,min.chars=1L)
  if(!inherits(base$max_source_available_utc,"POSIXct") || length(base$max_source_available_utc)!=1L || anyNA(base$max_source_available_utc) || !is.finite(as.numeric(base$max_source_available_utc)) || base$max_source_available_utc>=cutoff$cutoff_utc) stop("Base source chronology required before cutoff")
  checkmate::assert_choice(base$intended_use,c("HISTORICAL_DIAGNOSTIC","PROSPECTIVE_DECISION"))
  grid <- base$grid;checkmate::assert_tibble(grid,min.rows=1L)
  checkmate::assert_names(names(grid),identical.to=c("home_goals","away_goals","probability"))
  for(k in c("home_goals","away_goals")) checkmate::assert_integerish(grid[[k]],lower=0,any.missing=FALSE)
  checkmate::assert_numeric(grid$probability,lower=0,upper=1,finite=TRUE,any.missing=FALSE)
  if(anyDuplicated(grid[c("home_goals","away_goals")]) || abs(sum(grid$probability)-1)>1e-12) stop("Unique normalized score grid required")
  checkmate::assert_character(judgement$model_id,len=1L,any.missing=FALSE,min.chars=1L)
  checkmate::assert_character(judgement$rationale,len=1L,any.missing=FALSE,min.chars=1L)
  bins <- judgement$bins;checkmate::assert_tibble(bins,min.rows=1L)
  checkmate::assert_names(names(bins),identical.to=c("bin_id","min_margin","max_margin","target_mass","evidence_id","reason"))
  for(k in c("bin_id","evidence_id","reason")) checkmate::assert_character(bins[[k]],any.missing=FALSE,min.chars=1L)
  for(k in c("min_margin","max_margin")) checkmate::assert_numeric(bins[[k]],any.missing=FALSE)
  checkmate::assert_numeric(bins$target_mass,lower=0,upper=1,finite=TRUE,any.missing=FALSE)
  bins <- dplyr::arrange(bins,min_margin)
  ends <- c(bins$min_margin,bins$max_margin)
  if(anyDuplicated(bins$bin_id) || any(ends[is.finite(ends)]!=round(ends[is.finite(ends)])) ||
     any(bins$min_margin>bins$max_margin) || bins$min_margin[1]!= -Inf || tail(bins$max_margin,1)!=Inf ||
     (nrow(bins)>1 && any(bins$min_margin[-1]!=head(bins$max_margin,-1)+1)) ||
     abs(sum(bins$target_mass)-1)>1e-12) stop("Bins require complete integer partition and normalized masses")
  reticulate::use_python(file.path(repository_root,".venv/bin/python"),required=TRUE)
  sys <- reticulate::import("sys",convert=FALSE)
  if(!identical(normalizePath(reticulate::py_to_r(sys$prefix)),normalizePath(file.path(repository_root,".venv")))) stop("Project Python required")
  sys$path$insert(0L,file.path(repository_root,"packages/beidan/inst/python"))
  backend <- reticulate::import("beidan_backend.fundamental_probability",convert=FALSE)
  if(!inherits(context,"python.builtin.object")) stop("Opaque shared evidence context required")
  native <- reticulate::py_to_r(backend$export_adjustment_evidence_context(context,as.list(fixture),as.numeric(cutoff$cutoff_utc),base$intended_use,repository_root))
  hashes <- list(base_artifact=.score_margin_hash(base),margin_judgement=.score_margin_hash(judgement),direction_implementation=.score_margin_code(repository_root))
  if(!identical(native$receipt$source_hashes[names(hashes)],hashes)) stop("Score inputs or implementation binding differs; rebuild context")
  evidence <- dplyr::bind_rows(native$evidence)
  if(!all(bins$evidence_id %in% evidence$evidence_id)) stop("Bin evidence unavailable before cutoff")
  grid <- dplyr::mutate(grid,margin=home_goals-away_goals,base_probability=probability)
  grid$bin_id <- NA_character_
  for(i in seq_len(nrow(bins))) grid$bin_id[grid$margin>=bins$min_margin[i] & grid$margin<=bins$max_margin[i]] <- bins$bin_id[i]
  if(anyNA(grid$bin_id)) stop("Score outside bins")
  masses <- grid |> dplyr::group_by(bin_id) |> dplyr::summarise(base_mass=sum(base_probability),.groups="drop")
  ledger <- bins |> dplyr::left_join(masses,by="bin_id",relationship="one-to-one") |>
    dplyr::mutate(base_mass=dplyr::coalesce(base_mass,0))
  if(any(ledger$base_mass==0 & ledger$target_mass>0)) stop("Positive target bin has no score support")
  ledger$multiplier <- 0
  supported <- ledger$base_mass>0
  ledger$multiplier[supported] <- ledger$target_mass[supported]/ledger$base_mass[supported]
  grid <- grid |> dplyr::left_join(dplyr::select(ledger,bin_id,multiplier),by="bin_id",relationship="many-to-one") |>
    dplyr::mutate(probability=base_probability*multiplier)
  marg <- grid |> dplyr::group_by(margin) |> dplyr::summarise(base_probability=sum(base_probability),probability=sum(probability),.groups="drop")
  receipt <- list(model_id=judgement$model_id,distribution_family="EXPERT_REWEIGHTED_SCORE_GRID",
    cutoff=list(issue_id=cutoff$issue_id,cutoff_utc=format(cutoff$cutoff_utc,"%Y-%m-%dT%H:%M:%OS6Z",tz="UTC")),
    fixture=as.list(fixture),input_hashes=hashes,base_model=base$model_id,
    base_source_hashes=base$source_hashes,max_base_source_available_utc=format(base$max_source_available_utc,"%Y-%m-%dT%H:%M:%OS6Z",tz="UTC"),
    source_context=native$receipt,selected_bins=ledger,rationale=judgement$rationale,
    cache_reuse="NONE",cache_key=.score_margin_hash(list(cutoff=cutoff,fixture=fixture,hashes=hashes)),
    output_hash=.score_margin_hash(list(grid=grid,margins=marg)),
    gates=list(normalized=abs(sum(grid$probability)-1)<1e-12,nonnegative=all(grid$probability>=0)))
  result <- list(grid=grid,margins=marg,ledger=ledger,evidence=evidence,receipt=receipt,cutoff=cutoff)
  class(result) <- c("score_margin_scenario","list")
  result$seal <- .score_margin_hash(result)
  result
}

#' Project a frozen score grid onto an actual integer handicap
#' @param distribution Frozen score_margin_scenario from the adjustment function,
#'   including its explicit embedded cutoff, source/code receipt and integrity
#'   seal. No rows or probabilities are modified; bare grids are not admitted.
#' @param handicap Explicit signed integer home handicap, including zero.
#' @return Tibble outcome W/D/L, handicap, probability, rank and tied_rank.
#'   Rank is descending probability; equal probabilities within 1e-12 keep
#'   shared ranks. Ties must not be presented as a unique Top1 or Top2.
#' @param repository_root Explicit repository for source/code identity checking.
#' @details Arithmetic after distribution freeze, no tuning, cutoff
#'   selection, writes or receipt rewrite; changing ticket line only changes
#'   aggregation and rankings. Does not supply constraints to calibration.
#' @export
project_score_outcomes <- function(distribution,handicap,repository_root) {
  if(!inherits(distribution,"score_margin_scenario")) stop("Frozen cutoff-bound score distribution required")
  saved <- distribution$seal;unsigned <- distribution;unsigned$seal <- NULL
  if(!identical(saved,.score_margin_hash(unsigned))) stop("Frozen distribution integrity differs")
  match_require_cutoff(distribution$cutoff)
  receipt <- distribution$receipt;cutoff <- distribution$cutoff
  if(!identical(receipt$input_hashes$direction_implementation,.score_margin_code(repository_root))) stop("Score implementation differs; rebuild required")
  expected_ts <- format(cutoff$cutoff_utc,"%Y-%m-%dT%H:%M:%OS6Z",tz="UTC")
  source_ts <- suppressWarnings(lubridate::ymd_hms(receipt$source_context$cutoff_ts,tz="UTC"))
  if(!identical(receipt$cutoff$issue_id,cutoff$issue_id) || !identical(receipt$cutoff$cutoff_utc,expected_ts) ||
    length(source_ts)!=1L || anyNA(source_ts) || as.numeric(source_ts)!=as.numeric(cutoff$cutoff_utc) ||
    !identical(receipt$source_context$cutoff_identity,paste0("DECISION_EPOCH_",cutoff$issue_id)) ||
    !identical(receipt$fixture$issue_id,cutoff$issue_id)) stop("Score cutoff binding differs")
  grid <- distribution$grid
  checkmate::assert_tibble(grid,min.rows=1L)
  checkmate::assert_names(names(grid),must.include=c("home_goals","away_goals","probability"))
  for(k in c("home_goals","away_goals")) checkmate::assert_integerish(grid[[k]],lower=0,any.missing=FALSE)
  checkmate::assert_numeric(grid$probability,lower=0,upper=1,finite=TRUE,any.missing=FALSE)
  checkmate::assert_integerish(handicap,len=1L,any.missing=FALSE)
  if(anyDuplicated(grid[c("home_goals","away_goals")]) || abs(sum(grid$probability)-1)>1e-12) stop("Unique normalized score grid required")
  grouped <- grid |> dplyr::mutate(outcome=dplyr::case_when(home_goals-away_goals+handicap>0~"W",home_goals-away_goals+handicap==0~"D",TRUE~"L")) |>
    dplyr::group_by(outcome) |> dplyr::summarise(probability=sum(probability),.groups="drop")
  result <- tibble::tibble(outcome=c("W","D","L"),handicap=as.integer(handicap)) |>
    dplyr::left_join(grouped,by="outcome",relationship="one-to-one") |> dplyr::mutate(probability=dplyr::coalesce(probability,0))
  result$rank <- vapply(result$probability,function(p) 1L+sum(result$probability>p+1e-12),integer(1))
  result$tied_rank <- duplicated(result$rank) | duplicated(result$rank,fromLast=TRUE)
  dplyr::arrange(result,rank,outcome)
}
