# Bind a descriptive report's verified inputs, implementation and numeric/figure
# outputs. inputs is named list(path,sha256), code is relative path -> SHA256.
# No learning or decision outputs. Refuses overwrite or drift during rendering.
joint_rotation_report_receipt <- function(out,repository_root,inputs,code,generated_at) {
 stopifnot(dir.exists(out),!file.exists(file.path(out,'report-receipt.json')),length(inputs)>0,length(code)>0)
 for(x in inputs)stopifnot(digest::digest(file=x$path,algo='sha256')==x$sha256)
 for(name in names(code))stopifnot(digest::digest(file=file.path(repository_root,name),algo='sha256')==code[[name]])
 files<-c('refined-bridge.csv','comparison-summary.csv','novelty.csv','full-curves.png','attribution.png','tail-curves.png')
 stopifnot(all(file.exists(file.path(out,files))))
 hashes<-setNames(as.list(vapply(file.path(out,files),digest::digest,character(1),file=TRUE,algo='sha256')),files)
 path<-file.path(out,'report-receipt.json')
 jsonlite::write_json(list(status='REPORT_COMPLETE',historical_admission=FALSE,generated_at=generated_at,
  inputs=inputs,code=code,files=hashes),path,auto_unbox=TRUE,pretty=TRUE)
 path
}
