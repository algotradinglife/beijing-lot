# Read and validate an explicit Nowscore issue-inventory plan without writes.
# Returns plan metadata, tidy candidate rows and tidy batch rows. Issue values
# remain character strings so leading zeroes are never lost.
read_nowscore_inventory_plan <- function(path) {
  stopifnot(is.character(path), length(path) == 1L, !is.na(path), file.exists(path))
  plan <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  stopifnot(identical(plan$schema, "nowscore_issue_inventory_plan_v1"),
            identical(plan$source, "nowscore"),
            identical(plan$historical_coverage_claimed, FALSE),
            identical(plan$production_enabled, FALSE))

  issues <- unlist(plan$candidates, use.names = FALSE)
  stopifnot(is.character(issues), length(issues) > 0L,
            length(issues) == plan$candidate_count,
            !anyDuplicated(issues), all(grepl("^[0-9]{5,6}$", issues)))
  candidate_json <- jsonlite::toJSON(as.list(issues), auto_unbox = TRUE, digits = NA)
  candidate_sha256 <- digest::digest(candidate_json, algo = "sha256", serialize = FALSE)
  if (!identical(candidate_sha256, plan$candidates_sha256)) {
    stop("candidate SHA256 does not match plan contents")
  }
  contract <- plan$candidate_contract
  stopifnot(is.list(contract), is.list(contract$legacy), is.list(contract$modern))
  legacy <- contract$legacy
  modern <- contract$modern
  bounds <- list(legacy$start_year, legacy$end_year, legacy$max_monthly_serial,
                 modern$start_year, modern$end_year, modern$max_serial)
  stopifnot(all(vapply(bounds, function(value) {
    is.integer(value) && length(value) == 1L && !is.na(value)
  }, logical(1))))
  stopifnot(legacy$start_year >= 2000L, legacy$end_year < 2020L,
            legacy$end_year >= legacy$start_year,
            legacy$max_monthly_serial >= 1L, legacy$max_monthly_serial <= 99L,
            modern$start_year >= 2020L, modern$end_year <= 2099L,
            modern$end_year >= modern$start_year,
            modern$max_serial >= 1L, modern$max_serial <= 999L)
  expected_legacy <- unlist(lapply(seq.int(legacy$start_year, legacy$end_year), function(year) {
    unlist(lapply(seq_len(12L), function(month) {
      sprintf("%02d%02d%02d", year %% 100L, month,
              seq_len(legacy$max_monthly_serial))
    }), use.names = FALSE)
  }), use.names = FALSE)
  expected_modern <- unlist(lapply(seq.int(modern$start_year, modern$end_year), function(year) {
    sprintf("%02d%03d", year %% 100L, seq_len(modern$max_serial))
  }), use.names = FALSE)
  if (!identical(issues, c(expected_legacy, expected_modern))) {
    stop("candidates do not match candidate contract")
  }
  candidates <- tibble::tibble(
    candidate_index = seq_along(issues) - 1L,
    issue = issues,
    issue_year = 2000L + as.integer(substr(issues, 1L, 2L)),
    encoding = ifelse(nchar(issues) == 6L, "YYMMNN", "YYNNN")
  )

  batches <- dplyr::bind_rows(lapply(plan$batches, function(batch) {
    tibble::tibble(
      batch_id = batch$batch_id,
      start_index = batch$start_index,
      end_index_exclusive = batch$end_index_exclusive,
      candidate_count = batch$candidate_count,
      first_issue = batch$first_issue,
      last_issue = batch$last_issue
    )
  }))
  expected_batch_ids <- sprintf("batch-%04d", seq_len(nrow(batches)))
  stopifnot(nrow(batches) == plan$batch_count,
            identical(batches$batch_id, expected_batch_ids),
            identical(batches$start_index, c(0L, head(batches$end_index_exclusive, -1L))),
            tail(batches$end_index_exclusive, 1L) == nrow(candidates),
            all(batches$candidate_count == batches$end_index_exclusive - batches$start_index),
            all(batches$first_issue == candidates$issue[batches$start_index + 1L]),
            all(batches$last_issue == candidates$issue[batches$end_index_exclusive]))

  list(plan = plan, candidates = candidates, batches = batches)
}

# Read one sealed discovery result bound to an explicit plan and file SHA256.
# Returns the original receipt, one row per candidate with observed classification,
# yearly counts (including zero-discovery years), and modern internal gap IDs.
# An empty source page does not prove the lottery issue never existed. This is
# read-only reporting validation, not a replacement for Python raw-batch replay.
read_nowscore_inventory_result <- function(path, plan_path, expected_sha256) {
  stopifnot(is.character(path), length(path) == 1L, !is.na(path), file.exists(path),
            is.character(expected_sha256), length(expected_sha256) == 1L,
            !is.na(expected_sha256), grepl("^[0-9a-f]{64}$", expected_sha256))
  if (!identical(digest::digest(file = path, algo = "sha256"), expected_sha256)) {
    stop("inventory file SHA256 mismatch")
  }
  planned <- read_nowscore_inventory_plan(plan_path)
  result <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  plan_text <- paste(readLines(plan_path, warn = FALSE, encoding = "UTF-8"), collapse = "\n")
  stopifnot(identical(result$schema, "nowscore_issue_inventory_v1"),
            identical(result$source, "nowscore"),
            identical(result$candidate_coverage_complete, TRUE),
            identical(result$production_enabled, FALSE),
            identical(result$plan_sha256, digest::digest(plan_text, algo = "sha256", serialize = FALSE)))
  present <- unlist(result$issues, use.names = FALSE)
  empty <- unlist(result$source_empty_candidates, use.names = FALSE)
  if (is.null(present)) present <- character()
  if (is.null(empty)) empty <- character()
  stopifnot(is.character(present), is.character(empty),
            !anyNA(c(present, empty)), !anyDuplicated(c(present, empty)),
            setequal(c(present, empty), planned$candidates$issue),
            length(present) == result$issue_count, length(empty) == result$source_empty_count,
            length(c(present, empty)) == result$candidate_count,
            length(present) * 5L == result$five_play_pages_to_capture,
            setequal(names(result$batch_manifests), planned$batches$batch_id))
  hashes <- vapply(result$batch_manifests, function(x) x$sha256, character(1))
  stopifnot(all(grepl("^[0-9a-f]{64}$", hashes)))
  candidates <- planned$candidates |>
    dplyr::mutate(classification = ifelse(issue %in% present, "present", "source_empty"))
  years <- candidates |>
    dplyr::group_by(issue_year, encoding) |>
    dplyr::summarise(candidates = dplyr::n(),
                     discovered = sum(classification == "present"),
                     source_empty = sum(classification == "source_empty"), .groups = "drop")
  declared <- unlist(result$issues_by_year)
  observed <- table(as.character(candidates$issue_year[candidates$classification == "present"]))
  stopifnot(setequal(names(declared), names(observed)),
            identical(as.integer(declared[names(observed)]), as.integer(observed)))
  gaps <- unlist(result$modern_internal_gaps, use.names = FALSE)
  if (is.null(gaps)) gaps <- character()
  stopifnot(is.character(gaps), !anyNA(gaps), !anyDuplicated(gaps),
            all(grepl("^[0-9]{5}$", gaps)), all(gaps %in% empty))
  gaps <- tibble::tibble(issue = gaps, issue_year = 2000L + as.integer(substr(gaps, 1L, 2L)))
  list(receipt = result, file_sha256 = expected_sha256, candidates = candidates,
       years = years, gaps = gaps)
}
