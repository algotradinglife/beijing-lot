#' Add fixed DC outcome protection while retaining the BD classification
#' @param bd,dc Named numeric W/D/L vectors (win/draw/lose), finite complete
#'   distributions summing to one; invalid vectors raise errors.
#' @param single_threshold Explicit fixed BD single-choice threshold.
#' @return Unique list of outcome vectors with original BD base_role attribute.
#'   For base1 disagreement protect DC Top1; base2 disagreement protect DC Top2;
#'   base3 unchanged. Agreement means equality of primary TopN sets (order-free).
#'   Stable W/D/L tie order. No labels, fitting, IO or mutable state.
DcProtectionChoices <- function(bd,dc,single_threshold) {
  for(p in list(bd,dc)) {
    stopifnot(is.numeric(p),length(p)==3L,identical(names(p),c("win","draw","lose")))
    classify_outcomes(p[[1]],p[[2]],p[[3]],single_threshold)
  }
  choices <- classify_outcomes(bd[[1]],bd[[2]],bd[[3]],single_threshold)
  role <- attr(choices,"base_role")
  codes <- c("win","draw","lose")
  if(role==3L)return(choices)
  bd_set <- codes[order(-bd,seq_along(bd))][seq_len(role)]
  dc_set <- codes[order(-dc,seq_along(dc))][seq_len(role)]
  if(setequal(bd_set,dc_set))return(choices)
  # Protect only the primary TopN set; keep every original BD candidate.
  out <- c(unname(choices),list(union(bd_set,dc_set)))
  # Same set in different order is one choice; retain first stable representation.
  keys <- vapply(out,function(choice)paste(sort(choice),collapse="|"),character(1))
  out <- out[!duplicated(keys)]
  attr(out,"base_role") <- role
  return(out)
}
