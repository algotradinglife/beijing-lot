# Read and validate one completed retrospective selection study for reporting.
# study_dir: explicit directory; expected_plans: positive integer plan count.
# Returns freeze/config and SHA256 identities of the prediction plan and results.
# Reads JSON/CSV bytes only; no writes, labels used for selection, or fitting.
# Missing files, stale checks, mutated outputs, count mismatch or label-reading
# allocation replay fail. Hashes identify bytes, not independent review quality.
n7_selection_report_inputs <- function(study_dir,expected_plans) {
  stopifnot(length(study_dir)==1,is.character(study_dir),dir.exists(study_dir),
    length(expected_plans)==1,is.finite(expected_plans),expected_plans>=1,
    expected_plans==floor(expected_plans))
  freeze_path<-file.path(study_dir,'plans-frozen.json')
  frozen<-jsonlite::fromJSON(freeze_path)
  freeze_hash<-digest::digest(file=freeze_path,algo='sha256')
  stopifnot(all(c('predictions.csv','funded.csv','actions.csv') %in% names(frozen$files)))
  for(n in names(frozen$files))stopifnot(digest::digest(file=file.path(study_dir,n),algo='sha256')==frozen$files[[n]])
  results_hash<-digest::digest(file=file.path(study_dir,'results.csv'),algo='sha256')
  for(n in c('allocation-replay.json','independent-check.json','evaluation-receipt.json')) {
    receipt<-jsonlite::fromJSON(file.path(study_dir,n))
    stopifnot(identical(receipt$status,'PASS'),identical(receipt$freeze_sha256,freeze_hash),
      length(receipt$plans)==1,receipt$plans==expected_plans)
    if(n=='allocation-replay.json')stopifnot(identical(receipt$labels_loaded,FALSE))
    else stopifnot(identical(receipt$results_sha256,results_hash))
  }
  list(frozen=frozen,freeze_sha256=freeze_hash,results_sha256=results_hash)
}
