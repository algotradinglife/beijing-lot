# Query one Nowscore issue without exposing SQL to analysis callers.
# path: existing SQLite database; issue: digit string (leading zeros preserved).
# slot: optional positive integer; play: optional spf/jq/ds/bf/bq code.
# Returns settlement (one row per observation/option, or an NA option if absent),
# findings (one row per audit finding), and the original parsed build receipt.
# SP is a dimensionless source multiplier, NOT a ticket payout. raw_sp retains
# empty/invalid text; sp uses NA for missing values. expected_option is derived,
# not an official winner. received_at remains the original ISO-8601 evidence.
# No matches returns typed empty tibbles; quarantine may have findings only.
# Invalid arguments, receipts, schemas or duplicate keys raise errors.
# Opens read-only, uses a consistent read transaction, and always disconnects.
# Does not fetch, correct data, infer availability or perform historical fitting.
query_nowscore_settlement <- function(path, issue, slot = NULL, play = NULL) {
  if (!is.character(path) || length(path) != 1L || is.na(path) ||
      !file.exists(path) || dir.exists(path)) stop("path must be an existing SQLite file")
  if (!is.character(issue) || length(issue) != 1L || is.na(issue) ||
      !grepl("^[0-9]+$", issue)) stop("issue must be a digit string; preserve leading zeros")
  if (!is.null(slot) && (!is.numeric(slot) || length(slot) != 1L ||
      !is.finite(slot) || slot < 1 || slot > .Machine$integer.max ||
      slot != floor(slot))) stop("slot must be a positive integer or NULL")
  if (!is.null(play) && (!is.character(play) || length(play) != 1L ||
      is.na(play) || !play %in% c("spf", "jq", "ds", "bf", "bq"))) {
    stop("play must be spf, jq, ds, bf, bq or NULL")
  }
  con <- DBI::dbConnect(RSQLite::SQLite(), path, flags = RSQLite::SQLITE_RO)
  on.exit(DBI::dbDisconnect(con), add = TRUE)
  DBI::dbBegin(con)
  receipts <- DBI::dbReadTable(con, "receipt")
  if (nrow(receipts) != 1L) stop("Expected exactly one build receipt")
  receipt <- jsonlite::fromJSON(receipts$payload_json[[1L]], simplifyVector = FALSE)
  if (!identical(receipt$source, "nowscore") ||
      !identical(receipt$production_enabled, FALSE)) stop("Expected a Nowscore audit build")
  where <- "issue = ?"
  params <- list(issue)
  if (!is.null(slot)) {
    where <- paste(where, "AND slot = ?")
    params <- c(params, list(as.integer(slot)))
  }
  if (!is.null(play)) {
    where <- paste(where, "AND play = ?")
    params <- c(params, list(play))
  }
  selected <- paste("WITH selected AS (SELECT * FROM observation WHERE", where, ")")
  duplicates <- DBI::dbGetQuery(con, paste(selected,
    "SELECT issue, slot, play FROM selected GROUP BY issue, slot, play",
    "HAVING COUNT(*) > 1 LIMIT 1"), params = params)
  if (nrow(duplicates)) stop("Duplicate observation keys in selection")
  settlement <- tibble::as_tibble(DBI::dbGetQuery(con, paste(selected,
    "SELECT o.observation_id, o.issue, o.slot, o.play, o.native_match_id,",
    "json_extract(o.payload_json, '$.home') AS home,",
    "json_extract(o.payload_json, '$.away') AS away,",
    "json_extract(o.payload_json, '$.handicap_raw') AS handicap_raw,",
    "o.status, o.score, o.halftime_score, o.expected_option,",
    "p.option, p.raw_sp, p.sp, o.source_url, o.source_sha256, o.received_at",
    "FROM selected o LEFT JOIN option_sp p USING (observation_id)",
    "ORDER BY o.slot, o.play, p.option"), params = params))
  if (anyDuplicated(settlement[c("observation_id", "option")])) {
    stop("Duplicate option keys in selection")
  }
  findings <- tibble::as_tibble(DBI::dbGetQuery(con, paste(
    "SELECT issue, slot, play, code, detail, source_sha256 FROM finding WHERE",
    where, "ORDER BY slot, play, code, source_sha256, detail"), params = params))
  DBI::dbCommit(con)
  list(settlement = settlement, findings = findings, receipt = receipt)
}
