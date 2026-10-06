#' Independently verify prepared inputs and their probability basis
#' @param epoch Receipt-bound output from [prepare_match_inputs()].
#' @return Invisibly TRUE; missing/tampered/stale provenance fails closed.
#' @details Reuses the authoritative preparation on its retained raw inputs;
#'   never infers chronology or reconstructs fixtures from derived probabilities.
#'   No labels, IO or mutation. Change cutoff by rebuilding from raw inputs.
#' @noRd
.ValidatePreparedProbabilityInputs <- function(epoch) {
  receipt <- epoch$preparation_receipt
  if (!is.list(receipt) || is.null(receipt$input_snapshot)) stop("epoch preparation receipt is required")
  match_require_cutoff(epoch$cutoff)
  if (!identical(receipt$cutoff,epoch$cutoff) ||
      !identical(receipt$cutoff_hash,.rank_outcome_cutoff_hash(epoch$cutoff)) ||
      !identical(receipt$probability_base,epoch$probability_base) ||
      !identical(receipt$input_hash,rlang::hash(receipt$input_snapshot)) ||
      !identical(receipt$implementation_hash,.rank_outcome_code_hash(
        roots=c("prepare_match_inputs",".ValidatePreparedProbabilityInputs")))) {
    stop("epoch preparation receipt basis, cutoff, source or implementation differs")
  }
  bare <- epoch; bare$preparation_receipt <- NULL
  if (!identical(receipt$output_hash,rlang::hash(bare))) stop("epoch prepared output differs from receipt")
  source <- receipt$input_snapshot
  fresh <- do.call(prepare_match_inputs,c(list(inputs=source$inputs),source$parameters))
  if (!identical(fresh,epoch)) stop("epoch preparation replay differs")
  return(invisible(TRUE))
}
