#' Validate and independently replay a selected probability projection
#' @param projected Projection produced by [SelectProbabilityBase()].
#' @return Invisibly TRUE; missing, retimed, altered or stale evidence errors.
#' @details No IO or labels. Replays fixed current-market arithmetic with the
#'   receipt's input snapshot and parameters; does not infer a new decision time.
#' @noRd
.ValidateProbabilityBaseProjection <- function(projected) {
  receipt <- projected$probability_base_receipt
  if (!is.list(receipt) || is.null(receipt$input_snapshot)) stop("probability base receipt is required")
  match_require_cutoff(projected$cutoff)
  if (!identical(receipt$cutoff_hash, .rank_outcome_cutoff_hash(projected$cutoff)) ||
      !identical(receipt$cutoff, projected$cutoff) ||
      !identical(receipt$base, projected$probability_base) ||
      !identical(receipt$input_hash, rlang::hash(receipt$input_snapshot)) ||
      !identical(receipt$implementation_hash, .rank_outcome_code_hash(roots = c("SelectProbabilityBase", ".ValidateProbabilityBaseProjection")))) {
    stop("probability base receipt source, cutoff, parameters or implementation differs")
  }
  bare <- projected
  bare$probability_base_receipt <- NULL
  if (!identical(receipt$output_hash, rlang::hash(bare))) stop("probability base output differs from receipt")
  fresh <- SelectProbabilityBase(receipt$input_snapshot, receipt$base,
    receipt$bd_weight, receipt$model_config)
  if (!identical(fresh, projected)) stop("probability base replay differs")
  return(invisible(TRUE))
}
