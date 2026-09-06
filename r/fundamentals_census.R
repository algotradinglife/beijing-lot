# Diagnostic census reporting only. No learned features, fits or database writes.

# Read immutable Python output tables, preserving identifiers and missing values.
# input_dir: existing directory with receipt.json and hashed CSV files.
# Returns named data frames and receipt; stops on tampering or key mismatch.
read_fundamentals_census <- function(input_dir) {
  receipt <- jsonlite::read_json(file.path(input_dir, "receipt.json"), simplifyVector = TRUE)
  if (!identical(receipt$schema, "bj407_diagnostic_census_v1") ||
      !identical(receipt$historical_learning, "NONE")) stop("Unsupported census contract")
  required <- paste0(c("panel", "denominator", "responses", "identity", "fields", "history", "findings"), ".csv")
  if (!all(required %in% names(receipt$output_hashes))) stop("Missing required output hashes")
  for (name in names(receipt$output_hashes)) {
    actual <- digest::digest(file = file.path(input_dir, name), algo = "sha256", serialize = FALSE)
    if (!identical(actual, receipt$output_hashes[[name]])) stop("Census output hash mismatch: ", name)
  }
  tables <- list()
  for (name in c("panel", "denominator", "responses", "identity", "fields", "history", "findings")) {
    tables[[name]] <- readr::read_csv(file.path(input_dir, paste0(name, ".csv")),
      col_types = readr::cols(.default = readr::col_character()), na = "", show_col_types = FALSE)
    if (nrow(readr::problems(tables[[name]]))) stop("CSV parsing failure: ", name)
  }
  for (name in names(tables)) {
    table <- tables[[name]]
    integer_columns <- c("slot", "byte_count", "record_count", "ordinal", "home_score", "away_score",
                         "halftime_home_score", "halftime_away_score")
    if (name == "responses") integer_columns <- c(integer_columns, "status", "auxiliary_status")
    for (column in intersect(integer_columns, names(table))) {
      values <- suppressWarnings(readr::parse_integer(table[[column]]))
      if (nrow(readr::problems(values))) stop("Integer parsing failure: ", name, ".", column)
      table[[column]] <- values
    }
    for (column in intersect(c("kickoff_utc", "received_at_utc", "auxiliary_received_at_utc", "sampled_at_utc", "roster_received_at_utc"), names(table))) {
      values <- suppressWarnings(readr::parse_datetime(table[[column]], locale = readr::locale(tz = "UTC")))
      if (nrow(readr::problems(values))) stop("Datetime parsing failure: ", name, ".", column)
      table[[column]] <- values
    }
    tables[[name]] <- table
  }
  panel <- tables$panel
  if (nrow(panel) != receipt$panel_rows || anyDuplicated(panel[c("issue", "slot")]) ||
      anyDuplicated(panel$provider_id)) stop("Invalid panel identity")
  for (name in c("responses", "identity", "fields", "history", "findings")) {
    unmatched <- dplyr::anti_join(tables[[name]], panel, by = c("issue", "slot", "provider_id"))
    if (nrow(unmatched)) stop("Unmatched panel key: ", name)
  }
  if (anyDuplicated(tables$responses[c("issue", "slot", "source")]) ||
      nrow(tables$responses) != 2L * nrow(panel)) stop("Invalid response cardinality")
  tables$receipt <- receipt
  tables
}

# Return field coverage with all attempted source documents as denominator.
# Missing/failed parsers remain in the denominator; a zero count is not agreement.
summarize_fundamentals_coverage <- function(census) {
  denominator <- dplyr::count(census$responses, source, period, name = "documents")
  observed <- dplyr::count(census$fields, source, period, field, field_state, name = "observations")
  result <- dplyr::left_join(observed, denominator, by = c("source", "period"), relationship = "many-to-one")
  if (anyNA(result$documents)) stop("Missing coverage denominator")
  dplyr::mutate(result, fraction = observations / documents)
}

# Return one acquisition summary row per source/state combination, including errors.
summarize_fundamentals_access <- function(census) {
  dplyr::count(census$responses, source, capture_state, parse_state, evidence_class, name = "documents")
}

# Read versioned manual diagnostic reviews and verify the referenced raw bytes.
# audit_dir contains independent-cases.v1.json and relative official receipt files.
# This validates provenance and review completeness, not the truth of the review.
read_fundamentals_review <- function(audit_dir) {
  path <- file.path(audit_dir, "independent-cases.v1.json")
  records <- jsonlite::read_json(path, simplifyVector = FALSE)
  result <- list(tibble::tibble(issue = character(), slot = integer(), provider_id = character(),
                                disposition = character(), rationale = character()))
  for (record in records) {
    valid_revision <- length(record$revision) == 1L && is.numeric(record$revision) &&
      !is.na(record$revision) && is.finite(record$revision) && record$revision >= 1 &&
      record$revision == floor(record$revision) && record$revision <= .Machine$integer.max
    if (!identical(record$schema, "bj407_independent_audit_v1") ||
        !valid_revision || !nzchar(record$reviewer) || !nzchar(record$rationale) ||
        isTRUE(record$model_admission) || isTRUE(record$settlement_mutation)) stop("Invalid diagnostic review")
    if (!length(record$independent_evidence)) stop("Missing independent evidence")
    for (evidence in record$independent_evidence) {
      receipt <- jsonlite::read_json(file.path(audit_dir, evidence$file))
      bytes <- jsonlite::base64_dec(receipt$body_base64)
      actual <- digest::digest(bytes, algo = "sha256", serialize = FALSE)
      if (!identical(actual, evidence$sha256) || !identical(receipt$url, evidence$url) ||
          receipt$status != 200L) stop("Independent evidence receipt mismatch")
    }
    result[[length(result) + 1L]] <- tibble::tibble(issue = record$issue,
      slot = record$slot, provider_id = record$provider_id,
      disposition = record$disposition, rationale = record$rationale)
  }
  dplyr::bind_rows(result)
}
