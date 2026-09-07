# Synthetic audit database shared by offline query tests and the delivery QMD.
# path must not exist. Creates only that temporary SQLite file; never fetches.
# Identifiers, missing values, malformed SP and quarantine are deliberate.
nowscore_query_fixture <- function(path) {
  stopifnot(is.character(path), length(path) == 1L, !is.na(path),
            nzchar(path), !file.exists(path))
  con <- DBI::dbConnect(RSQLite::SQLite(), path)
  on.exit(DBI::dbDisconnect(con), add = TRUE)
  DBI::dbWriteTable(con, "receipt", data.frame(payload_json =
    '{"source":"nowscore","production_enabled":false}'))
  DBI::dbWriteTable(con, "observation", data.frame(
    observation_id = 1:3, issue = rep("00123", 3), slot = c(1L, 1L, 2L),
    play = c("bf", "spf", "bf"), native_match_id = rep("00042", 3),
    status = c("取消", "取消", "完场"), score = c("-", "-", "0-0"),
    halftime_score = c("-", "-", "0-0"), expected_option = c(NA, NA, "0:0"),
    source_url = "https://example.invalid", source_sha256 = "hash",
    received_at = "2026-09-07T00:00:00+00:00",
    payload_json = '{"home":"主队","away":"客队","handicap_raw":"0"}'))
  DBI::dbWriteTable(con, "option_sp", data.frame(
    observation_id = c(1L, 1L, 1L, 2L), option = c("0:0", "1:0", "2:0", "胜"),
    raw_sp = c("1.00", "", "bad", "0.00"), sp = c(1, NA, NA, 0)))
  DBI::dbWriteTable(con, "finding", data.frame(issue = "00123", slot = c(1L, 3L),
    play = "bf", code = c("invalid_sp", "source_roster_conflict"),
    detail = c("invalid", "quarantined"), source_sha256 = "hash"))
}
