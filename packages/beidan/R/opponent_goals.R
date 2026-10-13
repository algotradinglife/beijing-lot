#' Fit an opponent-normalized Poisson attack and defence model
#' @param prepared Python object returned by prepare_opponent_goals(), including
#'   verified shared contexts, complete weight ledgers and their receipts.
#' @param fixture Named list with home_id, away_id, competition_id and explicit
#'   logical neutral_reported; IDs refer to the target fixture.
#' @param cutoff Explicit shared Cutoff object bound to the prepared contexts.
#' @param policy Named list with ridge (positive fixed glmnet lambda),
#'   minimum_target_matches (integer venue support floor), convergence_tolerance
#'   and maximum_iterations. No target labels or market values are accepted.
#' @param repository_root Explicit path containing the project Python backend.
#' @return List of one-row parameter and same-support raw-parameter tibbles,
#'   coefficient/support/observation tibbles, shared receipts and a fit receipt.
#' @details Research only. Uses glmnet Poisson ridge with an unpenalized intercept
#'   and home indicator; attack/defence features receive equal shrinkage toward
#'   zero. Competition is fixed by the source-reported target league. Sparse,
#'   disconnected target teams, wrong cutoffs or changed implementation fail.
#'   No fetching or writes. Non-neutrality is not independently verified.
FitOpponentGoals <- function(prepared, fixture, cutoff, policy, repository_root) {
  root <- normalizePath(repository_root,mustWork=TRUE)
  if (!inherits(prepared,"python.builtin.object") || !inherits(cutoff,"python.builtin.object") ||
      !is.list(fixture) || !is.logical(fixture$neutral_reported) ||
      length(fixture$neutral_reported)!=1L || is.na(fixture$neutral_reported)) stop("Explicit prepared context, cutoff and venue required")
  checkmate::assert_names(names(policy),identical.to=c("ridge","minimum_target_matches","convergence_tolerance","maximum_iterations"))
  checkmate::assert_number(policy$ridge,lower=.Machine$double.eps)
  checkmate::assert_int(policy$minimum_target_matches,lower=2L)
  checkmate::assert_number(policy$convergence_tolerance,lower=.Machine$double.eps)
  checkmate::assert_int(policy$maximum_iterations,lower=1L)
  reticulate::use_python(file.path(root,".venv/bin/python"),required=TRUE)
  backend <- reticulate::import("beidan_backend.opponent_goals",convert=FALSE)
  backend$verify_opponent_preparation(prepared,fixture,cutoff,root)
  observations <- dplyr::bind_rows(reticulate::py_to_r(prepared$observations))
  support <- dplyr::bind_rows(reticulate::py_to_r(prepared$support))
  if (!nrow(observations) || anyNA(observations) || anyDuplicated(observations$row_key) ||
      !all(observations$competition_id==fixture$competition_id) ||
      any(!is.finite(observations$weight)|observations$weight<=0)) stop("Opponent observations contract differs")
  home_venue <- if(fixture$neutral_reported) "neutral" else "home"
  away_venue <- if(fixture$neutral_reported) "neutral" else "away"
  home <- dplyr::filter(observations,team_id==fixture$home_id,venue==home_venue)
  away <- dplyr::filter(observations,team_id==fixture$away_id,venue==away_venue)
  if(min(nrow(home),nrow(away))<policy$minimum_target_matches) stop("Sparse target competition/venue support")
  teams <- sort(unique(c(observations$team_id,observations$opponent_id)))
  # Matrix sparse model columns use numeric team positions, preserving IDs.
  attack <- match(observations$team_id,teams)
  defence <- match(observations$opponent_id,teams)
  adjacency <- Matrix::sparseMatrix(i=attack,j=defence,x=1,dims=c(length(teams),length(teams)))
  # Mature igraph connectivity avoids estimating disconnected relative strengths.
  graph <- igraph::graph_from_adjacency_matrix(adjacency,mode="undirected",weighted=TRUE,diag=FALSE)
  components <- igraph::components(graph)$membership
  if(components[match(fixture$home_id,teams)]!=components[match(fixture$away_id,teams)]) stop("Disconnected target strength network")
  selected_component <- components[match(fixture$home_id,teams)]
  observations <- observations[components[attack]==selected_component,,drop=FALSE]
  teams <- sort(unique(c(observations$team_id,observations$opponent_id)))
  attack <- match(observations$team_id,teams); defence <- match(observations$opponent_id,teams)
  n <- nrow(observations); k <- length(teams)
  design <- Matrix::sparseMatrix(i=rep(seq_len(n),3),
    j=c(rep(1L,n),1L+attack,1L+k+defence),
    x=c(observations$home_indicator,rep(1,2*n)),dims=c(n,1L+2L*k))
  colnames(design) <- c("home_indicator",paste0("attack:",teams),paste0("defence:",teams))
  if(sum(observations$goals)==0) stop("Positive goal mass required")
  fit <- glmnet::glmnet(design,observations$goals,family="poisson",alpha=0,
    lambda=policy$ridge,weights=observations$weight,standardize=FALSE,
    intercept=TRUE,penalty.factor=c(0,rep(1,2*k)),
    control=list(thresh=policy$convergence_tolerance,maxit=policy$maximum_iterations))
  if(fit$jerr!=0L || length(fit$lambda)!=1L) stop("Poisson ridge did not converge")
  target <- Matrix::sparseMatrix(i=rep(1:2,3),
    j=c(c(1L,1L),1L+match(c(fixture$home_id,fixture$away_id),teams),
        1L+k+match(c(fixture$away_id,fixture$home_id),teams)),
    x=c(if(fixture$neutral_reported)c(.5,.5)else c(1,0),rep(1,4)),dims=c(2,1L+2L*k))
  predicted <- as.numeric(stats::predict(fit,newx=target,type="response",s=policy$ridge))
  if(any(!is.finite(predicted)|predicted<=0)) stop("Positive finite predicted goal means required")
  parameters <- tibble::tibble(lambda_home=predicted[1],lambda_away=predicted[2])
  raw <- tibble::tibble(lambda_home=(stats::weighted.mean(home$goals,home$weight)+stats::weighted.mean(away$against,away$weight))/2,
    lambda_away=(stats::weighted.mean(away$goals,away$weight)+stats::weighted.mean(home$against,home$weight))/2)
  if(any(unlist(raw)<=0)) stop("Positive same-support raw means required")
  coefficients <- tibble::tibble(term=rownames(stats::coef(fit,s=policy$ridge)),value=as.numeric(stats::coef(fit,s=policy$ridge)))
  receipts <- reticulate::py_to_r(prepared$receipts)
  admission <- reticulate::py_to_r(prepared$admission$receipt$payload)
  dependencies <- list(glmnet=as.character(utils::packageVersion("glmnet")),Matrix=as.character(utils::packageVersion("Matrix")),igraph=as.character(utils::packageVersion("igraph")))
  shared <- reticulate::import("beidan_backend.temporal_learning",convert=FALSE)
  cache_key <- reticulate::py_to_r(shared$temporal_cache_key(cutoff,
    c(admission$source_hashes,list(fit_policy=digest::digest(policy,algo="sha256"),
      dependencies=digest::digest(dependencies,algo="sha256"),groups=digest::digest(receipts,algo="sha256"))),
    admission$implementation_hashes,shared$AvailabilityPolicy$historical_proxy("DATE_PLUS_ONE_UTC_OPPONENT_NETWORK_DIAGNOSTIC"),
    "HISTORICAL_DIAGNOSTIC",shared$PartitionPolicy("FIXED_PRIOR_FIT",0L,0L,1L),
    shared$WeightingPolicy$expanding_equal(minimum_ess=1)))
  receipt <- list(model="OPPONENT_POISSON_RIDGE_RESEARCH_1",cutoff=reticulate::py_to_r(cutoff$identity),
    policy=policy,fixture=fixture,admission=admission,cache_key=cache_key,cache_reuse="NONE",
    group_receipts_sha256=digest::digest(receipts,algo="sha256"),
    observations_sha256=digest::digest(observations,algo="sha256"),
    R_code_sha256=digest::digest(file=file.path(root,"packages/beidan/R/opponent_goals.R"),algo="sha256"),
    dependencies=dependencies,
    parameters_sha256=digest::digest(parameters,algo="sha256"),coefficients_sha256=digest::digest(coefficients,algo="sha256"),
    target_label_optimization=FALSE,intended_use="HISTORICAL_DIAGNOSTIC",fitted_rows=n)
  list(parameters=parameters,same_support_raw=raw,coefficients=coefficients,
       support=support,observations=observations,receipts=receipts,
       ledgers=reticulate::py_to_r(prepared$ledgers),receipt=receipt)
}
