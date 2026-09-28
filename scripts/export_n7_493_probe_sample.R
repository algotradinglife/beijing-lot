#!/usr/bin/env Rscript
# Freeze the #493 Phase-1 probe sample: read-only export of the minimal field set
# the sample selection depends on, plus its content hashes.
#
# The sample is chosen for a RETROSPECTIVE probe only. The per-issue count of
# fixtures with a real kickoff is a SAMPLING device for this probe; it must never
# be reused as decision-time fixture admission.
#
# Usage:
#   Rscript scripts/export_n7_493_probe_sample.R [--out DIR]

suppressMessages({
  library(DBI)
  library(RSQLite)
  library(tibble)
  library(dplyr)
  library(jsonlite)
  library(digest)
})

args <- commandArgs(trailingOnly = TRUE)
out_dir <- if (length(args) >= 2L && args[1L] == "--out") args[2L] else
  "results/n7_493_probe_sample_v1"
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

live_db <- "data/beidan_live.db"
cutoff_db <- "data/derived/500_bjdc/500_bjdc.sqlite.bak"

# --- Read-only extraction of the minimal fields the selection depends on ------
live <- dbConnect(SQLite(), live_db, flags = RSQLite::SQLITE_RO)
matches <- dbGetQuery(live, paste(
  "SELECT issue, match_idx, match_id, kickoff_ts, handicap_line",
  "FROM matches"))
snapshots <- dbGetQuery(live, paste(
  "SELECT match_id, snapshot_ts, eu_h FROM snapshots WHERE eu_h IS NOT NULL"))
dbDisconnect(live)

cut <- dbConnect(SQLite(), cutoff_db, flags = RSQLite::SQLITE_RO)
nowscore <- dbGetQuery(cut, paste(
  "SELECT issue, match_idx, provider_match_id, schedule_date, kickoff_time",
  "FROM nowscore_bjdc_matches"))
dbDisconnect(cut)

# --- Join contract ------------------------------------------------------------
# (issue, match_idx) is the declared key on both sides. It is checked, not
# assumed: a duplicate would multiply rows and attach the wrong evidence.
stopifnot(!anyDuplicated(matches[c("issue", "match_idx")]))
stopifnot(!anyDuplicated(nowscore[c("issue", "match_idx")]))
stopifnot(!anyDuplicated(matches$match_id))

matches$kickoff_ts <- trimws(matches$kickoff_ts)
nowscore$provider_match_id <- trimws(nowscore$provider_match_id)
joined <- merge(nowscore, matches, by = c("issue", "match_idx"))
# The join must not multiply rows. nowscore does not necessarily cover every
# match_idx of an issue it appears in, so the check is on key uniqueness and on
# orphan counts rather than on a row-count equality with the wider side.
stopifnot(!anyDuplicated(joined[c("issue", "match_idx")]))
n_orphan_nowscore <- nrow(dplyr::anti_join(nowscore, matches, by = c("issue", "match_idx")))
n_orphan_matches <- nrow(dplyr::anti_join(
  matches, nowscore[nowscore$issue %in% matches$issue, ], by = c("issue", "match_idx")))

# A placeholder midnight kickoff is not a real kickoff.
joined <- joined[!grepl("T00:00:00$", joined$kickoff_ts), ]
joined$issue <- as.character(joined$issue)
joined$local_date <- substr(joined$kickoff_ts, 1L, 10L)

# --- Selection rule (frozen) --------------------------------------------------
# 1. per issue, count fixtures with a real kickoff (SAMPLING ONLY);
# 2. take the 3 issues with the most, ties by ascending issue;
# 3. within each, the earliest local kickoff date holding >= 8 fixtures;
# 4. the 8 lowest match_idx on that date; decision date D = that date - 1.
counts <- sort(table(joined$issue), decreasing = TRUE)
picked_issues <- names(counts)[order(-as.integer(counts), names(counts))][1:3]

primary <- do.call(rbind, lapply(picked_issues, function(is) {
  d <- joined[joined$issue == is, ]
  per_date <- table(d$local_date)
  ok <- names(per_date)[as.integer(per_date) >= 8L]
  if (!length(ok)) return(NULL)
  window_date <- sort(ok)[1L]
  w <- d[d$local_date == window_date, ]
  w <- w[order(w$match_idx), ][seq_len(8L), ]
  w$role <- "primary"
  w
}))
primary$decision_date_D <- as.character(as.Date(primary$local_date) - 1L)

# Cross-validation fixtures: earliest 2 remaining fixtures whose euro snapshot is
# strictly before that fixture's own 20:00 epoch (12:00Z).
joined$epoch_utc <- paste0(as.character(as.Date(joined$local_date) - 1L), "T12:00:00Z")
joined$snapshot_utc <- sub("Z$", "", gsub(" ", "T", snapshots$snapshot_ts))[
  match(joined$match_id, snapshots$match_id)]
joined$snapshot_utc[is.na(match(joined$match_id, snapshots$match_id))] <- NA_character_
taken <- paste(primary$issue, primary$match_idx)
rest <- joined[!(paste(joined$issue, joined$match_idx) %in% taken) &
                 !is.na(joined$snapshot_utc) & joined$snapshot_utc < joined$epoch_utc, ]
rest <- rest[order(rest$issue, rest$match_idx), ]
rest <- rest[!duplicated(rest$match_id), ][seq_len(2L), ]
rest$role <- "cross_validation"
rest$decision_date_D <- as.character(as.Date(rest$local_date) - 1L)

fields <- c("issue", "match_idx", "match_id", "provider_match_id", "kickoff_ts",
            "local_date", "decision_date_D", "handicap_line", "role")
sample <- rbind(primary[, fields], rest[, fields])
sample <- sample[order(sample$role, sample$issue, sample$match_idx), ]
rownames(sample) <- NULL
stopifnot(nrow(sample) == 26L, !anyDuplicated(sample$match_id))

write.csv(sample, file.path(out_dir, "sample26.csv"), row.names = FALSE, quote = TRUE)
write.csv(sample[sample$role == "primary", ], file.path(out_dir, "sample_primary24.csv"),
          row.names = FALSE, quote = TRUE)

manifest <- list(
  purpose = "N7 #493 phase-1 input probe sample (retrospective diagnostic)",
  generated_at = format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"),
  read_only = TRUE,
  selection_rule = paste(
    "3 issues with the most real-kickoff fixtures (ties ascending issue);",
    "earliest local kickoff date with >= 8 fixtures; 8 lowest match_idx;",
    "plus the earliest 2 remaining fixtures with a euro snapshot strictly",
    "before their own 12:00Z epoch. Decision date D = local kickoff date - 1."),
  sampling_caveat = paste(
    "The per-issue real-kickoff count is a SAMPLING device for this",
    "retrospective probe only. It must not be reused as decision-time",
    "fixture admission."),
  join_keys = list(
    nowscore_to_matches = c("issue", "match_idx"),
    snapshots_to_matches = "match_id",
    cardinality = "1:1 on both keys (checked, not assumed)"),
  sources = lapply(c(live_db, cutoff_db), function(f) list(
    path = f,
    bytes = unname(file.size(f)),
    mtime_utc = format(file.mtime(f), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC"))),
  counts = list(
    nowscore_rows = nrow(nowscore),
    matches_rows = nrow(matches),
    joined_rows = nrow(joined),
    orphan_nowscore_keys = n_orphan_nowscore,
    uncovered_match_idx = n_orphan_matches,
    sample_primary = sum(sample$role == "primary"),
    sample_cross_validation = sum(sample$role == "cross_validation"),
    sample_total = nrow(sample)),
  hashes = list(
    sample26_csv = digest::digest(file.path(out_dir, "sample26.csv"),
                                  algo = "sha256", file = TRUE),
    sample_primary24_csv = digest::digest(file.path(out_dir, "sample_primary24.csv"),
                                          algo = "sha256", file = TRUE),
    sample26_canonical = digest::digest(
      paste(sample$issue, sample$match_idx, sample$match_id,
            sample$provider_match_id, sample$kickoff_ts, sep = "|"),
      algo = "sha256", serialize = FALSE)))
writeLines(jsonlite::toJSON(manifest, auto_unbox = TRUE, pretty = TRUE),
           file.path(out_dir, "sample_manifest.json"))

cat("sample rows:", nrow(sample), "\n")
cat("sample26 sha256:", manifest$hashes$sample26_csv, "\n")
cat("canonical sha256:", manifest$hashes$sample26_canonical, "\n")
print(sample[, c("role", "issue", "match_idx", "provider_match_id", "kickoff_ts")],
      row.names = FALSE)
