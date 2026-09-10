# Deterministic integration fixture. New output directory, pending TRUE/FALSE.
args <- commandArgs(TRUE)
if(length(args)!=2L || dir.exists(args[1])) stop('New fixture directory and pending flag required')
source('r/fundamentals_n7_baseline.R');source('r/fundamentals_n67_overlay.R')
p <- args[1];dir.create(p,recursive=TRUE)
x <- tidyr::expand_grid(issue=c('100101','100102'),strategy=c('N7','N6','DIRECT','CROSS'),funding=c('UNIT','MATCHED')) |>
  dplyr::mutate(stake=ifelse(funding=='MATCHED',384,ifelse(strategy=='N7',256,ifelse(strategy=='N6',128,384))),
    budget=stake,cash=0,gross=stake+44,net=44,roi=44/stake,hits=1,groups=ifelse(strategy %in% c('N7','N6'),1,2),
    ideal_gross=gross,status='COMPLETE',n6_hits=ifelse(strategy=='N7',0,1),n7_hits=ifelse(strategy=='N7',1,0),
    issue_anchor_ts='2010-01-01',model_any_hit=.4,max_pair_overlap=ifelse(strategy=='DIRECT',6,1))
if(isTRUE(as.logical(args[2]))) {
  x$status[] <- 'PENDING_AUDIT_OR_WINNING_SP'
  for(k in c('gross','net','roi','hits','ideal_gross','n6_hits','n7_hits')) x[[k]][] <- NA_real_
}
writeLines('{}',file.path(p,'inputs.json'));writeLines('[]',file.path(p,'plans.json'))
jsonlite::write_json(list(training_issues='100101',mode='SYNTHETIC_REPORT_FIXTURE'),file.path(p,'contract.json'),auto_unbox=TRUE)
a <- list(results=x,overlay_r_implementation=n67_overlay_r_receipt(getwd()),
    plans_sha256=digest::digest(file=file.path(p,'plans.json'),algo='sha256'),
    inputs_sha256=digest::digest(file=file.path(p,'inputs.json'),algo='sha256'),
    contract_sha256=digest::digest(file=file.path(p,'contract.json'),algo='sha256'))
jsonlite::write_json(a,file.path(p,'settlement.json'),auto_unbox=TRUE,dataframe='rows',na='null')
