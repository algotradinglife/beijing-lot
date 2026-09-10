# Read a pure/expert report with authenticated payload and canonical receipt.
# study: directory containing results.json and plans-frozen.json. archived_report
# validates portable archive hashes instead of external runtime/source files.
# Returns result and receipt lists. Read-only; missing/changed bindings fail.
read_pure_baseline_report <- function(study,archived_report) {
 stopifnot(is.logical(archived_report),length(archived_report)==1,!is.na(archived_report))
 frozen <- jsonlite::read_json(file.path(study,'plans-frozen.json'))
 stopifnot(is.character(frozen$canonical_json),length(frozen$canonical_json)==1,
  identical(digest::digest(frozen$canonical_json,algo='sha256',serialize=FALSE),frozen$seal))
 # The exact canonical bytes are authoritative; do not trust a detached ID.
 receipt <- jsonlite::parse_json(frozen$canonical_json)
 if(!identical(digest::digest(file=file.path(study,'results.json'),algo='sha256'),receipt$result_sha256))
  stop('Packaged result hash mismatch')
 result <- jsonlite::read_json(file.path(study,'results.json'),simplifyVector=TRUE)
 stopifnot(identical(result$upstream_freeze_seal,receipt$plan_freeze_seal),
  receipt$scope=='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC')
 bindings <- c(receipt$source_hashes,receipt$implementation$files,receipt$report_files)
 if(archived_report) {
  archive <- jsonlite::read_json(file.path(study,'archive.json'))
  stopifnot(archive$mode=='ARCHIVED_RENDER_ONLY_NOT_MODEL_REPLAY')
  bindings <- archive$hashes
 }
 for(path in names(bindings)) stopifnot(identical(digest::digest(file=path,algo='sha256'),bindings[[path]]))
 list(result=result,receipt=receipt)
}
