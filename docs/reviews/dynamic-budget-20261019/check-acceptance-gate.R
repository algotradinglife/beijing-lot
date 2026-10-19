# Exercise the actual QMD gate after genuine full-suite acceptance, never a fake pass.
suppressPackageStartupMessages(library(tidyverse))
library(testthat)
root<-normalizePath('.',mustWork=TRUE)
script<-tempfile(fileext='.R')
invisible(knitr::purl('quarto/dynamic_budget_20261019.qmd',output=script,quiet=TRUE))
nodes<-as.list(parse(script))
# deparse adds spaces around '<-'; locate the unique outer conditional by its parameter.
selected<-vapply(nodes,function(node)grepl('params$require_acceptance',paste(deparse(node),collapse=''),fixed=TRUE),logical(1))
stopifnot(sum(selected)==1)
gate<-nodes[[which(selected)]]
a<-jsonlite::fromJSON('results/dynamic-budget-20261019/acceptance.json')
work<-tempfile('budget-gate-');dir.create(work)
for(mode in c('valid','stale','missing')) {
 copy<-a
 if(mode=='stale')copy$source_files$sha256[1]<-paste(rep('0',64),collapse='')
 if(mode=='missing')copy$source_files<-copy$source_files[-1,]
 jsonlite::write_json(copy,file.path(work,'acceptance.json'),dataframe='rows',auto_unbox=TRUE,pretty=TRUE)
 env<-new.env(parent=globalenv());env$params<-list(require_acceptance=TRUE);env$out<-work;env$root<-root
 if(mode=='valid')expect_no_error(invisible(capture.output(eval(gate,envir=env))))
 else expect_error(eval(gate,envir=env),'is not TRUE')
}
unlink(c(script,work),recursive=TRUE)
cat('PASS: real QMD acceptance gate, valid source accepted; stale hash and missing source rejected.\n')
