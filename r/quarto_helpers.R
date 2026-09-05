library(DBI)
library(RSQLite)
library(dplyr)
library(jsonlite)

beijing_data_root <- function() {
  root <- Sys.getenv("BEIJING_LOT_DATA_ROOT")
  stopifnot(nzchar(root), dir.exists(root))
  normalizePath(root)
}

connect_titan <- function(root = beijing_data_root()) {
  DBI::dbConnect(RSQLite::SQLite(), file.path(root, "control", "titan", "control.sqlite"), flags = RSQLite::SQLITE_RO)
}

connect_discovery <- function(root = beijing_data_root()) {
  DBI::dbConnect(RSQLite::SQLite(), file.path(root, "control", "external_id_discovery", "discovery.sqlite"), flags = RSQLite::SQLITE_RO)
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
