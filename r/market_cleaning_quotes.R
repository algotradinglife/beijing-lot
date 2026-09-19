# Read hash-bound examples from an offline market audit.
# One row is an issue/slot/market, quotes is the selected-company list-column.
# expected_sha256 binds summary.json; sample_size is a positive integer.
# No collection or writes. Missing/corrupt evidence raises an error.
read_market_quote_examples <- function(study, expected_sha256, sample_size = 6L) {
  stopifnot(length(sample_size) == 1L, !is.na(sample_size),
            sample_size > 0L, sample_size == as.integer(sample_size))
  path <- file.path(study, "summary.json")
  if (!identical(digest::digest(file = path, algo = "sha256"), expected_sha256))
    stop("Summary hash mismatch")
  summary <- jsonlite::read_json(path)
  result <- tibble::tibble(issue = character(), slot = integer(),
    provider_id = character(), market = character(), source = character(),
    quotes = list())
  for (issue in summary$issues) {
    name <- paste0(issue$issue, ".json")
    path <- file.path(study, name)
    if (!identical(digest::digest(file = path, algo = "sha256"), summary$output_hashes[[name]]))
      stop("Issue output hash mismatch")
    rows <- jsonlite::read_json(path)
    for (row in rows) {
      if (!identical(row$issue, issue$issue)) stop("Issue identity mismatch")
      if (!identical(row$status, "QUOTES_PRIOR_DIAGNOSTIC")) next
      result <- dplyr::bind_rows(result, tibble::tibble(
        issue = row$issue, slot = as.integer(row$slot), provider_id = row$provider_id,
        market = row$market, source = "Titan", quotes = list(row$rows)))
      if (nrow(result) >= sample_size) return(result)
    }
  }
  result
}
