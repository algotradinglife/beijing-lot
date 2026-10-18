#' Publish source-bound competition and venue context
#'
#' Parse pinned analysis/auxiliary responses, reconcile source metadata and bind
#' historical context to a fixed base history. Never changes base data or forecasts.
#' Unknown venue markers remain missing logical values; all data remain historical
#' proxies. Catalog, schema and immutable Parquet versions are written on the NAS.
#'
#' @param issue Character issue ID.
#' @param base_version Fixed source_issue version label.
#' @param base_manifest_sha256 SHA256 of the fixed base manifest.
#' @param raw_evidence_relative Relative frozen raw archive directory.
#' @param raw_manifest_sha256 SHA256 of its asset manifest.
#' @param python Explicit project Python executable.
#' @param root Explicit existing NAS root.
#' @param hot_root Explicit existing short-lived root.
#' @return List containing status, dataset and immutable version. Same verified
#'   inputs/code are a no-op; invalid bytes/identities fail before publication.
#' @export
publish_fundamentals_context <- function(issue, base_version, base_manifest_sha256,
    raw_evidence_relative, raw_manifest_sha256, python, root, hot_root) {
  checkmate::assert_string(root, min.chars=1L)
  checkmate::assert_string(hot_root, min.chars=1L)
  checkmate::assert_directory_exists(root)
  checkmate::assert_directory_exists(hot_root)
  python_backend(python)
  backend <- reticulate::import("beidan_backend.fundamentals_context", convert=TRUE)
  backend$publish_fundamentals_context(issue=issue,base_version=base_version,
    base_manifest_sha256=base_manifest_sha256,raw_evidence_relative=raw_evidence_relative,
    raw_manifest_sha256=raw_manifest_sha256,base_reader=.context_base_rows_json,
    environ=list(BEIDAN_PARQUET_ROOT=normalizePath(root,mustWork=TRUE),
                 BEIDAN_HOT_ROOT=normalizePath(hot_root,mustWork=TRUE)))
}

# R is the authoritative analytical read boundary; dates cross JSON canonically.
.context_base_rows_json <- function(dataset, table, version, root) {
  if (identical(table,"match")) return(.cup_base_fixture_json(dataset,table,version,root))
  if (!identical(table,"history")) stop("unsupported context base table")
  x <- read_dataset(dataset,table,version=version,root=root)
  columns <- c("fixture_id","scope","match_id","event_date","home_id","away_id","selected_source")
  text <- setdiff(columns,"event_date")
  if (!all(columns%in%names(x)) || anyNA(x[columns]) ||
      !all(vapply(x[text],is.character,logical(1))) || !inherits(x$event_date,"Date") ||
      any(!nzchar(unlist(x[text],use.names=FALSE))) ||
      anyDuplicated(x[c("fixture_id","scope","match_id")]) ||
      !all(x$scope%in%c("home_recent","away_recent","head_to_head")) ||
      !all(x$selected_source%in%c("titan","nowscore"))) {
    stop("base context history contract failed")
  }
  x <- x[columns]
  x$event_date <- as.character(x$event_date)
  as.character(jsonlite::toJSON(x,dataframe="rows",auto_unbox=TRUE,na="null"))
}
