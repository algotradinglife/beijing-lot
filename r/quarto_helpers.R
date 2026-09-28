library(DBI)
library(RSQLite)
library(dplyr)
library(jsonlite)

beijing_data_root <- function() {
  root <- Sys.getenv("BEIJING_LOT_DATA_ROOT")
  stopifnot(nzchar(root), dir.exists(root))
  normalizePath(root)
}

# The clean Titan/settlement/discovery stores live under <data root>/clean_v1,
# per the BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 physical-isolation layout.
clean_root <- function(root = beijing_data_root()) {
  file.path(root, "clean_v1")
}

connect_titan <- function(root = beijing_data_root()) {
  DBI::dbConnect(RSQLite::SQLite(), file.path(clean_root(root), "control", "titan", "control.sqlite"), flags = RSQLite::SQLITE_RO)
}

connect_discovery <- function(root = beijing_data_root()) {
  DBI::dbConnect(RSQLite::SQLite(), file.path(clean_root(root), "control", "external_id_discovery", "discovery.sqlite"), flags = RSQLite::SQLITE_RO)
}

sql_table_count <- function(con, table) {
  DBI::dbGetQuery(con, paste0("SELECT COUNT(*) AS n FROM ", DBI::dbQuoteIdentifier(con, table)))$n[[1]]
}

parse_json_column <- function(x) {
  if (is.na(x) || !nzchar(x)) return(NULL)
  jsonlite::fromJSON(x, simplifyVector = FALSE)
}

snapshot_window_note <- function() {
  "Historical market timestamps are diagnostic proxies only; prospective use requires observed availability or a documented conservative safe boundary and the shared cutoff-learning contract."
}

read_settlement <- function(path) {
  stopifnot(file.exists(path))
  con <- DBI::dbConnect(RSQLite::SQLite(), path, flags = RSQLite::SQLITE_RO)
  on.exit(DBI::dbDisconnect(con), add = TRUE)
  tibble::as_tibble(DBI::dbReadTable(con, "settlement_merged"))
}

# SQL result -> caller-declared zero-row tibble schema; errors on names/type loss.
# Connections and optional SQL values are explicit; this helper does not close them.
query_tibble <- function(con, sql, prototype, params = NULL) {
  stopifnot(inherits(prototype, "tbl_df"), nrow(prototype) == 0L)
  result <- tibble::as_tibble(if (is.null(params)) DBI::dbGetQuery(con, sql)
                            else DBI::dbGetQuery(con, sql, params = params))
  if (!identical(names(result), names(prototype))) stop("query columns differ from declared prototype")
  if (nrow(result) == 0L) return(prototype)
  result <- purrr::imap(result, function(column, name) {
    if (is.logical(column) && all(is.na(column))) vctrs::vec_init(prototype[[name]], length(column))
    else column
  }) |> tibble::as_tibble()
  vctrs::vec_cast(result, prototype)
}

# One row per coverage summary, isolation reason, period, or failed issue.
# Count columns are integers; grouped empty results retain character/integer types.
discovery_summaries <- function(con) {
  list(
    coverage = query_tibble(con, "SELECT COUNT(DISTINCT issue_code) AS mapped_issues,
      COUNT(*) AS mapped_slots, COUNT(DISTINCT nowscore_provider_match_id) AS unique_titan_ids
      FROM issue_slot_nowscore_map",
      tibble::tibble(mapped_issues = integer(), mapped_slots = integer(), unique_titan_ids = integer())),
    isolated = query_tibble(con, "SELECT isolation_reason, COUNT(*) AS rows FROM conflict_isolated_slot
      GROUP BY isolation_reason ORDER BY rows DESC, isolation_reason",
      tibble::tibble(isolation_reason = character(), rows = integer())),
    periods = query_tibble(con, "SELECT CASE WHEN length(issue_code) = 6 THEN '2010-2019（6位）'
      ELSE '2020+（5位）' END AS period, COUNT(DISTINCT issue_code) AS issues, COUNT(*) AS slots
      FROM issue_slot_nowscore_map GROUP BY period ORDER BY period",
      tibble::tibble(period = character(), issues = integer(), slots = integer())),
    failures = query_tibble(con, "SELECT issue_code, COUNT(*) AS attempts FROM mapping_failure
      GROUP BY issue_code ORDER BY issue_code",
      tibble::tibble(issue_code = character(), attempts = integer()))
  )
}
