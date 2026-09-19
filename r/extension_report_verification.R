# Verify an independently produced replay receipt before report publication.
# receipt is parsed JSON, hashes are SHA256 strings, issues positive integer.
# Returns TRUE or stops; missing fields must fail, never pass as logical(0).
# No I/O, fitting, decisions or side effects.
extension_report_verification <- function(receipt, source_sha256, checker_sha256, issues) {
 stopifnot(is.list(receipt),length(source_sha256)==1L,length(checker_sha256)==1L,
  !is.na(source_sha256),!is.na(checker_sha256),grepl('^[0-9a-f]{64}$',source_sha256),
  grepl('^[0-9a-f]{64}$',checker_sha256),length(issues)==1L,is.finite(issues),issues>=1,issues==floor(issues),
  identical(receipt$status,'PASS'),identical(receipt$source_receipt_sha256,source_sha256),
  identical(receipt$implementation_sha256,checker_sha256),identical(receipt$independent_official_settlement,TRUE))
 expected<-c(issues=issues,policy_rows=issues*6,future_history_invariance=issues,base_replays=issues,selective_replays=issues*5)
 for(n in names(expected))stopifnot(is.numeric(receipt[[n]]),length(receipt[[n]])==1L,
  !is.na(receipt[[n]]),is.finite(receipt[[n]]),identical(as.numeric(receipt[[n]]),unname(as.numeric(expected[n]))))
 TRUE
}
