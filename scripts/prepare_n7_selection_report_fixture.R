# Deterministic report integration fixture. Arguments: new output directory, pending TRUE/FALSE.
args <- commandArgs(TRUE)
if(length(args)!=2L || dir.exists(args[1])) stop('New fixture directory and pending flag required')
source('r/fundamentals_n7_baseline.R');source('r/fundamentals_n7_selection.R')
p <- args[1];dir.create(p,recursive=TRUE)
x <- tidyr::expand_grid(issue=c('100101','100102'),selector=c('COVERAGE','VALUE'),grouping=c('CONCENTRATED','SNAKE')) |>
  dplyr::mutate(stake=256,gross=300,net=44,roi=44/256,hits=1,groups=1,ideal_gross=300,status='COMPLETE',
                issue_anchor_ts='2010-01-01',expected_net=20,expected_roi=20/256,any_hit_probability=.2)
if(isTRUE(as.logical(args[2]))) {
  x$status[] <- 'PENDING_WINNING_SP'
  for(k in c('gross','net','roi','hits','ideal_gross')) x[[k]][] <- NA_real_
}
writeLines('{}',file.path(p,'inputs.json'));writeLines('[]',file.path(p,'plans.json'))
jsonlite::write_json(list(training_issues='100101',mode='SYNTHETIC_REPORT_FIXTURE'),file.path(p,'contract.json'),auto_unbox=TRUE)
a <- list(results=x,selection_r_implementation=n7_selection_r_receipt(getwd()),
          plans_sha256=digest::digest(file=file.path(p,'plans.json'),algo='sha256'),
          inputs_sha256=digest::digest(file=file.path(p,'inputs.json'),algo='sha256'),
          contract_sha256=digest::digest(file=file.path(p,'contract.json'),algo='sha256'))
jsonlite::write_json(a,file.path(p,'settlement.json'),auto_unbox=TRUE,dataframe='rows',na='null')
