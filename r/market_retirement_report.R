# Summarize an existing retirement result and journal, without filesystem writes.
# Inputs: decoded JSON lists. Counts are files, hashes are SHA256 hex strings.
# This validates ledger agreement, not current file absence or database contents.
market_retirement_table <- function(result, journal) {
  if (!is.list(result) || !is.list(journal)) stop("retirement documents must be lists")
  hash <- result[["plan_sha256", exact = TRUE]]
  if (!is.character(hash) || length(hash) != 1L || is.na(hash) ||
      !grepl("^[0-9a-f]{64}$", hash) || !identical(hash, journal[["plan_sha256", exact = TRUE]])) {
    stop("retirement plan hashes differ or are invalid")
  }
  entries <- journal[["entries", exact = TRUE]]
  count <- result[["removed_files", exact = TRUE]]
  if (!identical(result[["state", exact = TRUE]], "RAW_RETIREMENT_COMPLETE") ||
      !is.numeric(count) || length(count) != 1L || is.na(count) ||
      !is.finite(count) || count < 0 || count != floor(count) ||
      !is.list(entries) || length(entries) != count) stop("incomplete retirement result")
  if (length(entries) > 0L && (is.null(names(entries)) || anyNA(names(entries)) ||
      any(!nzchar(names(entries))) || anyDuplicated(names(entries)) ||
      !all(vapply(entries, identical, logical(1), "REMOVED")))) {
    stop("incomplete retirement journal")
  }
  tibble::tibble(state = result[["state", exact = TRUE]], removed_files = as.double(count), plan_sha256 = hash)
}
