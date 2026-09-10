# Deterministic integration fixture. New output directory, pending TRUE/FALSE.
args <- commandArgs(TRUE)
if(length(args)!=2L || dir.exists(args[1])) stop('New fixture directory and pending flag required')
source('r/fundamentals_n7_baseline.R');source('r/fundamentals_n7_twocover.R')
p <- args[1];dir.create(p,recursive=TRUE)
x <- tidyr::expand_grid(issue=c('100101','100102'),strategy=c('BASE','TOP2','TOP3'),funding='UNIT') |>
  dplyr::mutate(stake=ifelse(strategy=='BASE',512,ifelse(strategy=='TOP2',768,1024)),budget=stake,cash=0,
    gross=ifelse(strategy=='BASE',400,ifelse(strategy=='TOP2',800,1200)),net=gross-stake,roi=net/stake,hits=1,groups=2,top_group=1,top_probability=.4,
    ideal_gross=gross,status='COMPLETE',issue_anchor_ts='2010-01-01',model_any_hit=.4)

if(isTRUE(as.logical(args[2]))) {
  x$status[] <- 'PENDING_AUDIT_OR_WINNING_SP'
  for(k in c('gross','net','roi','hits','ideal_gross')) x[[k]][] <- NA_real_
}
extra <- c('r/fundamentals_n7_topstake.R','scripts/settle_fundamentals_n7_topstake.R')
jsonlite::write_json(list(source_hashes=stats::setNames(lapply(extra,digest::digest,file=TRUE,algo='sha256'),extra)),file.path(p,'inputs.json'),auto_unbox=TRUE);writeLines('[]',file.path(p,'plans.json'))
jsonlite::write_json(list(training_issues='100101',mode='SYNTHETIC_REPORT_FIXTURE'),file.path(p,'contract.json'),auto_unbox=TRUE)
a <- list(results=x,r_implementation=n7_baseline_r_receipt(getwd()),
    plans_sha256=digest::digest(file=file.path(p,'plans.json'),algo='sha256'),
    inputs_sha256=digest::digest(file=file.path(p,'inputs.json'),algo='sha256'),
    contract_sha256=digest::digest(file=file.path(p,'contract.json'),algo='sha256'))
paths <- c('r/fundamentals_n7_twocover.R','scripts/settle_fundamentals_n7_twocover.R')
a$report_implementation <- stats::setNames(lapply(paths,digest::digest,file=TRUE,algo='sha256'),paths)
jsonlite::write_json(a,file.path(p,'settlement.json'),auto_unbox=TRUE,dataframe='rows',na='null')
