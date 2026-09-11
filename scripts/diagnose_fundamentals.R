#!/usr/bin/env Rscript
args<-commandArgs(TRUE)
usage<-'Usage: Rscript scripts/diagnose_fundamentals.R STUDY NEW_OUTPUT [--archived] [--no-render]\nDefault: validate packet, export CSV/JSON receipts and render report.html.\nInput must contain category packet factors/features/legs/audit/rows.\n--archived accepts only a restored, verified archived packet; not future admission.\nSet QUARTO_PATH if quarto is not on PATH. Output parent must already exist.\n'
if('--help' %in% args) {cat(usage);quit(status=0)}
archived<-'--archived' %in% args;render<-!'--no-render' %in% args
args<-args[!args %in% c('--archived','--no-render')]
if(length(args)!=2 || any(grepl('^--',args))) stop(usage)
study<-normalizePath(args[1],mustWork=TRUE)
out<-if(grepl('^/',args[2]))args[2] else file.path(getwd(),args[2])
filearg<-commandArgs(FALSE);filearg<-sub('^--file=','',filearg[grepl('^--file=',filearg)])
root<-dirname(dirname(normalizePath(filearg,mustWork=TRUE)))
quarto<-Sys.getenv('QUARTO_PATH',unset=Sys.which('quarto'))
if(render && (!nzchar(quarto) || !file.exists(quarto))) stop('Quarto not found: set QUARTO_PATH or use --no-render')
setwd(root)
source('r/fundamentals_pure_report.R');source('r/fundamentals_missed_issues.R')
source('r/fundamentals_category_diagnostics.R');source('r/fundamentals_diagnostic_runner.R')
output<-run_category_diagnostics(study,out,archived,root)
if(render) {
 setwd(output)
 status<-system2(quarto,c('render',shQuote(file.path(output,'report.qmd')),
  '--execute-dir',shQuote(root),'--execute','--no-cache','--output','report.html',
  '-P',shQuote(paste0('diagnostics:',output))))
 if(status!=0 || !file.exists(file.path(output,'report.html'))) stop('Tables exported, but report rendering failed; output is retained for inspection')
}
receipt<-jsonlite::read_json(file.path(output,'receipt.json'))
cat(sprintf('Completed: %s issues, %s missed issues\nOutput: %s\n',receipt$issues,receipt$missed_issues,output))
