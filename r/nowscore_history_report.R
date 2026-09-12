# Read an immutable raw audit database using aggregate SQL and bounded details.
# detail_limit is a positive integer number of findings, not option cells.
# Returns typed summaries, sample findings with full option vectors, and receipt.
# No corrections, network or writes. Duplicate observation keys/count drift fail.
read_nowscore_history_report <- function(path, detail_limit) {
  stopifnot(is.character(path), length(path) == 1L, !is.na(path), file.exists(path),
            is.numeric(detail_limit), length(detail_limit) == 1L,
            is.finite(detail_limit), detail_limit >= 1,
            detail_limit <= .Machine$integer.max, detail_limit == floor(detail_limit))
  con <- DBI::dbConnect(RSQLite::SQLite(), path, flags = RSQLite::SQLITE_RO)
  on.exit(DBI::dbDisconnect(con), add = TRUE)
  receipts <- DBI::dbReadTable(con, "receipt")
  stopifnot(nrow(receipts) == 1L)
  receipt <- jsonlite::fromJSON(receipts$payload_json[[1L]], simplifyVector = FALSE)
  stopifnot(identical(receipt$source, "nowscore"),
            identical(receipt$production_enabled, FALSE))
  if (identical(receipt$source_pure, FALSE) || !is.null(receipt$correction_batch_id) ||
      DBI::dbExistsTable(con, "sp_correction_batch"))
    stop("Raw-history report rejects corrected databases; use query_nowscore_settlement")
  duplicates <- DBI::dbGetQuery(con, paste(
    "SELECT issue, slot, play FROM observation GROUP BY issue, slot, play",
    "HAVING COUNT(*) > 1 LIMIT 1"))
  stopifnot(nrow(duplicates) == 0L)
  counts <- DBI::dbGetQuery(con, paste(
    "SELECT (SELECT COUNT(*) FROM capture) AS pages,",
    "(SELECT COUNT(*) FROM observation) AS observations,",
    "(SELECT COUNT(*) FROM option_sp) AS options,",
    "(SELECT COUNT(*) FROM finding) AS findings,",
    "(SELECT COUNT(*) FROM (SELECT DISTINCT issue, slot FROM observation)) AS matches"))
  stopifnot(counts$pages == receipt$capture_count,
            counts$observations == receipt$observations,
            counts$options == receipt$options, counts$matches == receipt$matches)
  statuses <- tibble::as_tibble(DBI::dbGetQuery(con, paste(
    "SELECT play, status, COUNT(*) AS observations FROM observation",
    "GROUP BY play, status ORDER BY play, status")))
  findings <- tibble::as_tibble(DBI::dbGetQuery(con, paste(
    "SELECT code, COUNT(*) AS findings FROM finding GROUP BY code",
    "ORDER BY findings DESC, code")))
  quarantined_pages <- tibble::as_tibble(DBI::dbGetQuery(con, paste(
    "SELECT f.issue, f.play, f.source_sha256, c.source_url, c.received_at,",
    "COUNT(*) AS conflict_findings FROM finding f JOIN capture c",
    "ON f.issue=c.issue AND f.source_sha256=c.sha256",
    "WHERE f.code='source_roster_conflict'",
    "GROUP BY f.issue, f.play, f.source_sha256, c.source_url, c.received_at",
    "ORDER BY f.issue, f.play, f.source_sha256")))
  years <- tibble::as_tibble(DBI::dbGetQuery(con, paste(
    "SELECT 2000 + CAST(substr(issue, 1, 2) AS INTEGER) AS year,",
    "COUNT(DISTINCT issue) AS issues, COUNT(*) AS pages FROM capture GROUP BY year ORDER BY year")))
  selection <- paste(
    "WITH selected AS (SELECT rowid AS finding_id, * FROM finding",
    "ORDER BY issue, slot, play, code, source_sha256, rowid LIMIT ?)")
  details <- tibble::as_tibble(DBI::dbGetQuery(con, paste(selection,
    "SELECT f.*, o.observation_id, o.status, o.score, o.halftime_score,",
    "o.expected_option, COALESCE(o.source_url,c.source_url) AS source_url,",
    "COALESCE(o.received_at,c.received_at) AS received_at FROM selected f LEFT JOIN observation o",
    "ON f.issue=o.issue AND f.slot=o.slot AND f.play=o.play AND f.source_sha256=o.source_sha256",
    "LEFT JOIN capture c ON f.issue=c.issue AND f.source_sha256=c.sha256",
    "ORDER BY f.issue, f.slot, f.play, f.code, f.source_sha256, f.finding_id"), params = list(as.integer(detail_limit))))
  options <- tibble::as_tibble(DBI::dbGetQuery(con, paste(selection,
    ", chosen AS (SELECT DISTINCT o.observation_id FROM selected f JOIN observation o",
    "ON f.issue=o.issue AND f.slot=o.slot AND f.play=o.play AND f.source_sha256=o.source_sha256)",
    "SELECT p.* FROM chosen c JOIN option_sp p ON p.observation_id=c.observation_id",
    "ORDER BY p.observation_id, p.option"),
    params = list(as.integer(detail_limit))))
  stopifnot(nrow(details) <= detail_limit,
            !anyDuplicated(details$finding_id), is.character(details$issue))
  vectors <- options |>
    dplyr::group_by(observation_id) |>
    dplyr::summarise(option_vector = paste0(option, "=",
      ifelse(is.na(raw_sp) | raw_sp == "", "∅", raw_sp), collapse = "；"), .groups = "drop")
  details <- dplyr::left_join(details, vectors, by = "observation_id", relationship = "many-to-one")
  list(receipt = receipt, counts = tibble::as_tibble(counts), years = years,
       statuses = statuses, findings = findings, quarantined_pages = quarantined_pages,
       details = details,
       detail_limit = as.integer(detail_limit), details_shown = nrow(details),
       details_omitted = counts$findings - nrow(details))
}
