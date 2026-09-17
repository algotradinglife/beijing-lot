source(file.path('..','..','r','joint_rotation_receipt.R'))
test_that('publication binds plans, outputs and source identity and refuses overwrite', {
 out<-tempfile();dir.create(out);dir.create(file.path(out,'plans'));root<-tempfile();dir.create(root)
 writeLines('source',file.path(root,'code.R'));audit<-tempfile();writeLines('labels',audit)
 writeLines('ticket',file.path(out,'plans','001.csv'))
 pr<-list(historical_admission=FALSE,audit_sha256=digest::digest(file=audit,algo='sha256'),
  code=list('code.R'=digest::digest(file=file.path(root,'code.R'),algo='sha256')),
  plan_hashes=list('001'=digest::digest(file=file.path(out,'plans','001.csv'),algo='sha256')),parameters=list(budget=1024),implementation=list(identity='test'))
 jsonlite::write_json(pr,file.path(out,'plans-receipt.json'),auto_unbox=TRUE)
 for(n in c('rows','curves','summary','bridge','concentration','verified-allocation-diagnostics'))writeLines('a,b',file.path(out,paste0(n,'.csv')))
 bad<-tempfile();writeLines('wrong',bad)
 expect_error(joint_rotation_receipt(out,root,bad,'2026-09-17T00:00:00Z',pr$code))
 result<-joint_rotation_receipt(out,root,audit,'2026-09-17T00:00:00Z',pr$code)
 r<-jsonlite::fromJSON(result);expect_equal(r$status,'ANALYSIS_COMPLETE');expect_length(r$files,6)
 expect_equal(r$files[['rows.csv']],digest::digest(file=file.path(out,'rows.csv'),algo='sha256'))
 expect_error(joint_rotation_receipt(out,root,audit,'2026-09-17T00:00:00Z',pr$code))
})
