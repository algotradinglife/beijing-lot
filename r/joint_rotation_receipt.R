# Publish an immutable analysis receipt after a successful frozen-plan evaluation.
# out holds plans-receipt.json and numeric CSVs. expected_code/source identities
# are already declared in the freeze; validate every plan and current R code.
# No modeling or acceptance policy: status ANALYSIS_COMPLETE awaits external review.
# Returns receipt path. Refuses missing/modified inputs and existing publication.
joint_rotation_receipt <- function(out,repository_root,audit_path,generated_at,evaluation_code) {
 stopifnot(dir.exists(out),dir.exists(repository_root),file.exists(audit_path),
  length(generated_at)==1,is.character(generated_at),nzchar(generated_at),
  !file.exists(file.path(out,'analysis-receipt.json')))
 raw<-readBin(file.path(out,'plans-receipt.json'),'raw',n=file.info(file.path(out,'plans-receipt.json'))$size)
 pr<-jsonlite::fromJSON(rawToChar(raw),simplifyVector=FALSE)
 stopifnot(identical(pr$historical_admission,FALSE),
  digest::digest(file=audit_path,algo='sha256')==pr$audit_sha256)
 for(name in names(pr$code))stopifnot(digest::digest(file=file.path(repository_root,name),algo='sha256')==pr$code[[name]])
 for(name in names(evaluation_code))stopifnot(digest::digest(file=file.path(repository_root,name),algo='sha256')==evaluation_code[[name]])
 for(id in names(pr$plan_hashes))stopifnot(digest::digest(file=file.path(out,'plans',paste0(id,'.csv')),algo='sha256')==pr$plan_hashes[[id]])
 required<-c('rows.csv','curves.csv','summary.csv','bridge.csv','concentration.csv','verified-allocation-diagnostics.csv')
 stopifnot(all(file.exists(file.path(out,required))))
 files<-setNames(as.list(vapply(file.path(out,required),digest::digest,character(1),file=TRUE,algo='sha256')),required)
 path<-file.path(out,'analysis-receipt.json')
 jsonlite::write_json(list(status='ANALYSIS_COMPLETE',historical_admission=FALSE,generated_at=generated_at,
  plan_receipt_sha256=digest::digest(raw,serialize=FALSE,algo='sha256'),audit_sha256=pr$audit_sha256,
  implementation=pr$implementation,parameters=pr$parameters,code=pr$code,evaluation_code=evaluation_code,files=files),path,auto_unbox=TRUE,pretty=TRUE)
 path
}
