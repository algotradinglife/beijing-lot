#' Publish verified cup group standings
#'
#' Keep cup group tables separate from league standings. The publisher validates
#' the exact fixture set and native team/provider IDs against a fixed base
#' version read through [read_dataset()]. It preserves source observations,
#' per-cell conflicts, empty/missing distinctions and historical-proxy status.
#' It never changes the base dataset or frozen predictions.
#'
#' @param parsed_sources List returned by the bundled Python
#'   `cup_standings.parse_cup_standings` for both sources of every base fixture.
#' @param issue Character issue ID, preserving leading zeroes.
#' @param base_version Immutable source_issue version label.
#' @param base_manifest_sha256 SHA256 of the immutable base manifest.
#' @param raw_evidence_relative Relative path under root to the frozen raw archive.
#' @param raw_manifest_sha256 SHA256 of the archive's asset manifest.
#' @param python Explicit project Python executable.
#' @param root Explicit existing NAS Parquet root.
#' @param hot_root Explicit existing short-lived working root.
#' @return A list containing publication status, dataset and version.
#' @details Writes an immutable dataset version and catalog/schema metadata via
#'   the authoritative backend. Identical inputs are a no-op. Integrity errors
#'   stop publication; catalog failures restore the prior pointer. Source cells
#'   that disagree remain null in the effective table, with both values retained.
#' @export
publish_cup_standings <- function(parsed_sources, issue, base_version,
                                  base_manifest_sha256, raw_evidence_relative,
                                  raw_manifest_sha256, python, root, hot_root) {
  checkmate::assert_list(parsed_sources)
  checkmate::assert_string(root, min.chars=1L)
  checkmate::assert_string(hot_root, min.chars=1L)
  checkmate::assert_directory_exists(root)
  checkmate::assert_directory_exists(hot_root)
  # Reticulate simplifies a Python list of strings to an R vector. Preserve
  # array semantics when sending group membership back across the boundary.
  for (i in seq_along(parsed_sources)) {
    if (!is.null(parsed_sources[[i]]$groups)) {
      parsed_sources[[i]]$groups <- as.list(parsed_sources[[i]]$groups)
    }
  }
  python_backend(python)
  backend <- reticulate::import("beidan_backend.cup_standings", convert=TRUE)
  backend$publish_cup_standings(parsed_sources, issue=issue, base_version=base_version,
    base_manifest_sha256=base_manifest_sha256, raw_evidence_relative=raw_evidence_relative,
    raw_manifest_sha256=raw_manifest_sha256, base_reader=.cup_base_fixture_json,
    environ=list(BEIDAN_PARQUET_ROOT=normalizePath(root,mustWork=TRUE),
                 BEIDAN_HOT_ROOT=normalizePath(hot_root,mustWork=TRUE)))
}

.cup_base_fixture_json <- function(dataset, table, version, root) {
  x <- read_dataset(dataset, table, version=version, root=root)
  columns <- c("fixture_id","provider_id","home_id","away_id")
  if (!all(columns %in% names(x)) || anyNA(x[columns]) ||
      anyDuplicated(x$fixture_id) || !all(vapply(x[columns],is.character,logical(1)))) {
    stop("base fixture/native identity contract failed")
  }
  as.character(jsonlite::toJSON(x[columns], dataframe="rows", auto_unbox=TRUE, na="null"))
}
