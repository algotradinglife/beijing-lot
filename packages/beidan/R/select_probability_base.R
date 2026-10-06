#' Select a fixed probability basis for a prepared decision epoch
#'
#' @param epoch Prepared input list from [prepare_match_inputs()], containing an
#'   explicit cutoff, decision_at, fixtures, match_status and prematch_sp. DC and
#'   mixed modes additionally require the existing selected DC market inputs.
#' @param base Exact scalar string: "beidan" (default), "dc", or "mixed".
#' @param bd_weight NULL except in mixed mode, where a finite scalar in [0,1]
#'   is required. Mixture is (1-bd_weight)*DC + bd_weight*Beidan.
#' @param model_config Fixed DC configuration passed to
#'   [estimate_match_probabilities()]; unused in pure Beidan mode.
#' @return Projection list with cutoff, fixtures, prematch_sp, match_status,
#'   probabilities (unique fixture_id/outcome W/D/L, normalized unitless double),
#'   fit, exclusions, model_config, market_policy and probability_base_receipt.
#'   Receipt binds the input snapshot, output, cutoff, basis, parameters and loaded
#'   transitive implementation. Empty fixture pools return typed empty tables.
#' @details Beidan uses normalized inverse raw SP without clipping. All selected
#'   fixtures require complete unique SP strictly before cutoff, scheduled status
#'   and future kickoff. Missing/malformed inputs and mixed fixture mismatches
#'   error; no implicit fallback or partial intersection. Beidan fit is typed empty
#'   and model_config is NULL. This fixed source selection performs no historical
#'   learning, weight tuning, label access, IO, caching or clock inference. The
#'   prepared epoch may already exclude fixtures under its upstream market policy;
#'   preparation must bind the same base; missing or altered preparation receipts
#'   fail closed. Rebuild from raw inputs when changing cutoff or probability base.
#' @export
SelectProbabilityBase <- function(epoch, base = "beidan", bd_weight = NULL,
    model_config = list(rho = -0.14, total_bounds = c(0.1, 16), tail_tolerance = 1e-10)) {
  checkmate::assert_string(base)
  if (!base %in% c("beidan", "dc", "mixed")) stop("base must be beidan, dc or mixed")
  if (base == "mixed") {
    if (!is.numeric(bd_weight) || !is.null(dim(bd_weight)) ||
        !is.null(attr(bd_weight,"class"))) stop("bd_weight must be a plain numeric scalar")
    checkmate::assert_number(bd_weight, lower = 0, upper = 1, finite = TRUE)
  } else if (!is.null(bd_weight)) stop("bd_weight is only valid for mixed mode")
  if (!is.list(epoch)) stop("epoch must be a prepared input list")
  match_require_cutoff(epoch$cutoff)
  cutoff <- epoch$cutoff
  .ValidatePreparedProbabilityInputs(epoch)
  if (!identical(epoch$probability_base,base)) stop("probability base differs from prepared epoch; rebuild inputs for requested base")
  checkmate::assert_posixct(epoch$decision_at, len = 1L, any.missing = FALSE)
  if (!is.finite(as.numeric(epoch$decision_at)) ||
      !identical(as.numeric(epoch$decision_at), as.numeric(cutoff$cutoff_utc))) {
    stop("decision_at must equal the embedded cutoff; rebuild the epoch")
  }
  fixtures <- tibble::as_tibble(match_validate_table(epoch$fixtures, "fixtures",
    keys = c("issue_id", "fixture_id")))
  if (any(fixtures$issue_id != cutoff$issue_id) || anyNA(fixtures$kickoff_at) ||
      any(!is.finite(as.numeric(fixtures$kickoff_at))) ||
      any(fixtures$kickoff_at <= cutoff$cutoff_utc)) stop("fixture issue or kickoff differs from cutoff")
  status <- match_select_status(fixtures, epoch$match_status, cutoff)
  if (nrow(status$exclusions)) stop("epoch fixtures must be visible as scheduled at cutoff")
  sp_all <- tibble::as_tibble(match_validate_table(epoch$prematch_sp, "prematch_sp"))
  sp <- sp_all |> dplyr::filter(.data$fixture_id %in% fixtures$fixture_id)
  bd <- if (nrow(fixtures)) PrematchSPProbabilities(sp, cutoff) else match_typed_empty("probabilities")
  if (!setequal(fixtures$fixture_id, bd$fixture_id)) stop("prematch SP must cover exactly the selected fixtures")
  if (base == "beidan") {
    out <- list(cutoff = cutoff, fixtures = fixtures, prematch_sp = sp,
      match_status = tibble::as_tibble(epoch$match_status), probabilities = bd,
      fit = match_typed_empty("fit"), exclusions = match_typed_empty("exclusions"),
      model_config = NULL, market_policy = epoch$market_policy)
  } else {
    out <- estimate_match_probabilities(epoch, model_config)
    out$fixtures <- tibble::as_tibble(out$fixtures)
    out$prematch_sp <- sp
    out$match_status <- tibble::as_tibble(out$match_status)
    out$probabilities <- tibble::as_tibble(out$probabilities)
    if (base == "mixed") {
      if (!setequal(out$probabilities$fixture_id, bd$fixture_id)) {
        stop("mixed mode requires complete DC and Beidan fixture alignment")
      }
      out$probabilities <- if (nrow(bd)) BlendMatchProbabilities(out$probabilities, bd, bd_weight) else bd
    }
  }
  out$probability_base <- base
  source_snapshot <- epoch
  source_hash <- rlang::hash(source_snapshot)
  code_hash <- .rank_outcome_code_hash(roots = c("SelectProbabilityBase", ".ValidateProbabilityBaseProjection"))
  admitted_times <- c(sp$quote_at, status$selected_status$status_at, status$selected_status$available_at)
  if (base != "beidan") admitted_times <- c(admitted_times, epoch$totals_selected$quote_at)
  if (base != "beidan" && !is.na(epoch$preparation_receipt$max_prior_eligible_euro_quote_at)) {
    admitted_times <- c(admitted_times,epoch$preparation_receipt$max_prior_eligible_euro_quote_at)
  }
  maximum <- if (length(admitted_times)) max(admitted_times) else as.POSIXct(NA_real_, origin = "1970-01-01", tz = "UTC")
  out$probability_base_receipt <- list(
    cutoff = cutoff, cutoff_hash = .rank_outcome_cutoff_hash(cutoff), base = base,
    bd_weight = bd_weight, model_config = out$model_config,
    input_snapshot = source_snapshot, input_hash = source_hash,
    implementation_hash = code_hash, output_hash = rlang::hash(out),
    maximum_admitted_quote_or_status_at = maximum,
    chronology_scope = "Maximum covers admitted SP, selected status event/availability, DC totals and prior eligible raw euro upper bound; preparation is independently replayed from raw inputs",
    ignored_sp_rows = as.integer(nrow(sp_all) - nrow(sp)),
    cache_key = rlang::hash(list(cutoff, source_hash, code_hash, base, bd_weight, out$model_config)),
    historical_learning_inventory = "NONE: fixed current-market inversion/DC projection and source mixture; no historical fitting or tuning")
  return(out)
}
