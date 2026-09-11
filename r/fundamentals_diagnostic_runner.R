# Export a verified, settled N7 category packet to a NEW directory atomically.
# study: existing results.json/plans-frozen.json packet; archived_report must
# explicitly select portable archive verification. repository_root must be cwd.
# output: new absolute/relative directory under an existing parent. No overwrite.
# Writes four CSVs, diagnostics.json and receipt.json; no RDS/network/fitting.
# Failure removes only the private staging directory. Returns output path.
run_category_diagnostics <- function(study,output,archived_report,repository_root) {
 root<-normalizePath(repository_root,mustWork=TRUE)
 stopifnot(identical(root,normalizePath(getwd())),!file.exists(output),dir.exists(dirname(output)))
 input<-normalizePath(study,mustWork=TRUE)
 verified<-read_pure_baseline_report(input,archived_report)
 v<-verified$result
 if(!all(c('factors','features','legs','audit','rows') %in% names(v))) stop('Input must be a category diagnostic packet with factors/features/legs/audit/rows')
 if(anyDuplicated(v$rows$issue)) stop('Exactly one original control row per issue is required')
 z<-category_diagnostics(v$factors,v$features,v$legs,v$audit,dplyr::select(v$rows,issue,hits))
 stage<-tempfile('.diagnostics-',tmpdir=dirname(output))
 if(!dir.create(stage)) stop('Cannot create staging directory')
 on.exit(unlink(stage,recursive=TRUE),add=TRUE)
 stopifnot(file.copy(file.path(root,'quarto/92_diagnostic_runner.qmd'),file.path(stage,'report.qmd')))
 for(n in names(z)) readr::write_csv(z[[n]],file.path(stage,paste0(n,'.csv')))
 jsonlite::write_json(z,file.path(stage,'diagnostics.json'),dataframe='rows',auto_unbox=TRUE,na='null',digits=NA)
 sources<-file.path(input,c('results.json','plans-frozen.json',if(archived_report)'archive.json'))
 code<-file.path(root,c('r/fundamentals_diagnostic_runner.R','r/fundamentals_category_diagnostics.R',
  'r/fundamentals_missed_issues.R','r/fundamentals_pure_report.R','scripts/diagnose_fundamentals.R','quarto/92_diagnostic_runner.qmd'))
 hashes<-vapply(c(sources,code),digest::digest,character(1),file=TRUE,algo='sha256')
 outputs<-list.files(stage)
 receipt<-list(scope='POST_SETTLEMENT_DESCRIPTIVE_NO_ADMISSION',generated_at_utc=format(Sys.time(),tz='UTC',usetz=TRUE),
  archived_input=archived_report,source_seal=v$upstream_freeze_seal,
  issues=nrow(z$original_issues),missed_issues=sum(z$original_issues$whole_issue_missed),
  source_hashes=as.list(stats::setNames(hashes[seq_along(sources)],sources)),
  implementation_hashes=as.list(stats::setNames(hashes[length(sources)+seq_along(code)],code)),
  output_hashes=as.list(stats::setNames(vapply(file.path(stage,outputs),digest::digest,character(1),file=TRUE,algo='sha256'),outputs)),
  r_version=R.version.string,package_versions=as.list(vapply(c('dplyr','tidyr','readr','jsonlite','digest'),function(p)as.character(utils::packageVersion(p)),character(1))))
 jsonlite::write_json(receipt,file.path(stage,'receipt.json'),auto_unbox=TRUE,pretty=TRUE)
 if(file.exists(output) || !file.rename(stage,output)) stop('Cannot publish new output directory')
 normalizePath(output)
}

# Read exported tables after verifying their bytes and bound current R/QMD code.
# Does not require the original data directory: source hashes remain provenance.
# Returns report data and receipt; modified/missing outputs or code fail closed.
read_category_diagnostic_output <- function(output) {
 receipt<-jsonlite::read_json(file.path(output,'receipt.json'))
 stopifnot(receipt$scope=='POST_SETTLEMENT_DESCRIPTIVE_NO_ADMISSION')
 for(n in names(receipt$output_hashes)) stopifnot(identical(digest::digest(file=file.path(output,n),algo='sha256'),receipt$output_hashes[[n]]))
 code<-names(receipt$implementation_hashes)
 for(p in code) stopifnot(identical(digest::digest(file=p,algo='sha256'),receipt$implementation_hashes[[p]]))
 list(data=jsonlite::read_json(file.path(output,'diagnostics.json'),simplifyVector=TRUE),receipt=receipt)
}
