#' Reporting helpers for the #493 Nowscore 3in1 probe delivery.
#'
#' Pure, parameterised helpers used by quarto/493_n7_input_probe.qmd. Every
#' function takes explicit paths and returns a validated tibble; nothing here
#' reads global state or performs network I/O.

#' Locate the repository root by probing candidate directories for the artifact.
#'
#' @param candidates Character vector of directories to probe, in order.
#' @param relative Path of the probe artifact directory, relative to the root.
#' @return The normalised first matching root.
#' @export
n7_probe_find_root <- function(candidates = c(".", "..", "../.."),
                               relative = "results/data_collection/n7_493_3in1_probe_v1") {
  for (candidate in candidates) {
    if (dir.exists(file.path(candidate, relative))) {
      return(normalizePath(candidate, mustWork = TRUE))
    }
  }
  stop("probe artifact directory not found from any candidate root")
}

#' Read the request ledger into a tibble.
#'
#' The ledger carries a per-field provenance column; unrecorded fields are NA and
#' are never filled in with a plausible default.
#'
#' @param path Path to requests.jsonl.
#' @return A tibble with one row per ledger record.
#' @export
n7_probe_read_ledger <- function(path) {
  if (!file.exists(path)) stop("ledger not found: ", path)
  lines <- readLines(path, encoding = "UTF-8", warn = FALSE)
  lines <- lines[nzchar(trimws(lines))]
  if (!length(lines)) {
    return(tibble::tibble(
      label = character(), kind = character(), status = character(),
      status_provenance = character(), duration_ms = double(),
      duration_provenance = character(), hop = character(),
      hop_provenance = character(), ended_at = character(),
      ended_at_provenance = character()))
  }
  rows <- lapply(lines, function(line) {
    record <- jsonlite::fromJSON(line, simplifyVector = FALSE)
    pick <- function(key) if (is.null(record[[key]])) NA else record[[key]]
    tibble::tibble(
      label = as.character(pick("label")),
      kind = as.character(pick("kind")),
      status = as.character(pick("http_status")),
      status_provenance = as.character(pick("http_status_provenance")),
      duration_ms = as.double(pick("duration_ms")),
      duration_provenance = as.character(pick("duration_ms_provenance")),
      hop = as.character(pick("hop")),
      hop_provenance = as.character(pick("hop_provenance")),
      ended_at = as.character(pick("ended_at")),
      ended_at_provenance = as.character(pick("ended_at_provenance")))
  })
  do.call(rbind, rows)
}

#' Read the diagnostic table, asserting that the assumption columns are present.
#'
#' The timestamp columns must name their assumed timezone and year; a table
#' without them is rejected rather than silently rendered.
#'
#' @param path Path to diagnostics.csv.
#' @return A tibble.
#' @export
n7_probe_read_diagnostics <- function(path) {
  if (!file.exists(path)) stop("diagnostics not found: ", path)
  # check.names = FALSE preserves "UTC+8" instead of repairing it to "UTC.8".
  out <- tibble::as_tibble(utils::read.csv(
    path, stringsAsFactors = FALSE, fileEncoding = "UTF-8", check.names = FALSE))
  last <- grep("^last_before_epoch_ASSUMED_", names(out), value = TRUE)
  before <- grep("^rows_strictly_before_epoch_ASSUMED_", names(out), value = TRUE)
  if (!length(last) || !length(before)) {
    stop("diagnostic columns must name their assumed timezone and year")
  }
  if (!all(c("tz_status", "availability_evidence") %in% names(out))) {
    stop("diagnostics must carry tz_status and availability_evidence")
  }
  out
}

#' Compute SHA-256 hashes for implementation and test files.
#'
#' @param root Repository root.
#' @param files Workspace-relative paths.
#' @return A tibble of file and sha256, one row per file.
#' @export
n7_probe_read_impl_hashes <- function(root, files) {
  hashes <- vapply(files, function(relative) {
    path <- file.path(root, relative)
    if (!file.exists(path)) return(NA_character_)
    out <- system2("sha256sum", shQuote(path), stdout = TRUE, stderr = FALSE)
    strsplit(trimws(out), "[[:space:]]+")[[1]][1]
  }, character(1), USE.NAMES = FALSE)
  tibble::tibble(file = files, sha256 = hashes)
}

#' Read the artifact SHA256SUMS file into a tibble.
#'
#' @param path Path to SHA256SUMS.
#' @return A tibble of file and sha256.
#' @export
n7_probe_read_artifacts <- function(path) {
  if (!file.exists(path)) stop("SHA256SUMS not found: ", path)
  sums <- readLines(path, encoding = "UTF-8", warn = FALSE)
  sums <- sums[nzchar(trimws(sums))]
  parts <- strsplit(sums, "  ", fixed = TRUE)
  tibble::tibble(
    file = vapply(parts, function(x) x[2], character(1)),
    sha256 = vapply(parts, function(x) x[1], character(1)))
}

#' Verify every artifact listed in SHA256SUMS against its actual bytes.
#'
#' Displaying recorded digests does not prove the bytes match; this fails closed
#' on a missing file or a mismatch.
#'
#' @param root Repository root.
#' @param manifest Workspace-relative path to SHA256SUMS.
#' @return A tibble with file, recorded, actual and matches.
#' @export
n7_probe_validate_artifacts <- function(root, manifest) {
  # NB: do not name this local `recorded`; tibble()'s data mask shadows it.
  manifest_rows <- n7_probe_read_artifacts(file.path(root, manifest))
  base <- dirname(manifest)
  actual <- vapply(manifest_rows$file, function(relative) {
    path <- file.path(root, base, relative)
    if (!file.exists(path)) return(NA_character_)
    out <- system2("sha256sum", shQuote(path), stdout = TRUE, stderr = FALSE)
    strsplit(trimws(out), "[[:space:]]+")[[1]][1]
  }, character(1), USE.NAMES = FALSE)
  result <- tibble::tibble(
    file = manifest_rows$file,
    recorded = manifest_rows$sha256,
    actual = actual,
    matches = !is.na(actual) & manifest_rows$sha256 == actual)
  if (!all(result$matches)) {
    stop("artifact mismatch: ",
         paste(result$file[!result$matches], collapse = ", "))
  }
  result
}


#' Compare current implementation hashes against a frozen reviewed revision.
#'
#' @param root Repository root.
#' @param reviewed_path Path to the frozen reviewed-revision JSON.
#' @return A tibble with file, reviewed, current and matches.
#' @export
n7_probe_compare_reviewed <- function(root, reviewed_path) {
  if (!file.exists(reviewed_path)) stop("reviewed revision not found: ", reviewed_path)
  reviewed <- jsonlite::fromJSON(reviewed_path, simplifyVector = FALSE)
  # A single-key JSON object may simplify to an atomic vector; normalise it.
  recorded <- as.list(unlist(reviewed$files, use.names = TRUE))
  files <- names(recorded)
  if (!length(files)) stop("reviewed revision records no files")
  expected <- vapply(files, function(f) as.character(recorded[[f]]), character(1),
                     USE.NAMES = FALSE)
  # NB: do not name this local `current`; tibble()'s data mask shadows it.
  hashes <- n7_probe_read_impl_hashes(root, files)
  tibble::tibble(
    file = files,
    reviewed = expected,
    current = hashes$sha256,
    matches = expected == hashes$sha256)
}
