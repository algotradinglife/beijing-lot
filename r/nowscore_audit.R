# Read one explicitly supplied Nowscore audit snapshot, with no writes/network.
# Returns typed database tables and JSON receipts. Missing schema, duplicate
# observation keys, wrong source, or an absent file raises an error.
read_nowscore_audit <- function(path) {
  stopifnot(is.character(path), length(path) == 1L, !is.na(path), file.exists(path))
  con <- DBI::dbConnect(RSQLite::SQLite(), path, flags = RSQLite::SQLITE_RO)
  on.exit(DBI::dbDisconnect(con), add = TRUE)
  receipt <- jsonlite::fromJSON(DBI::dbReadTable(con, "receipt")$payload_json[[1]])
  stopifnot(identical(receipt$source, "nowscore"), identical(receipt$production_enabled, FALSE))
  observations <- tibble::as_tibble(DBI::dbReadTable(con, "observation"))
  stopifnot(!anyDuplicated(observations$observation_id),
            !anyDuplicated(observations[c("issue", "slot", "play")]), is.character(observations$issue))
  list(receipt = receipt, observations = observations,
       options = tibble::as_tibble(DBI::dbReadTable(con, "option_sp")),
       findings = tibble::as_tibble(DBI::dbReadTable(con, "finding")),
       derivations = tibble::as_tibble(DBI::dbReadTable(con, "bf_derivation")),
       derivation_receipt = jsonlite::fromJSON(DBI::dbReadTable(con, "derivation_receipt")$payload_json[[1]]),
       effective_findings = tibble::as_tibble(DBI::dbReadTable(con, "effective_finding")),
       effective_options = tibble::as_tibble(DBI::dbReadTable(con, "effective_option_sp")),
       manual_all_one = tibble::as_tibble(DBI::dbReadTable(con, "manual_all_one")),
       special_notices = tibble::as_tibble(DBI::dbReadTable(con, "special_settlement_notice")),
       manual_receipt = jsonlite::fromJSON(DBI::dbReadTable(con, "manual_all_one_receipt")$payload_json[[1]]))
}
