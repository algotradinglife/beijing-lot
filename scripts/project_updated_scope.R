# Fixed raw baseline and Euro+OU projection; reuse existing model functions.
args <- commandArgs(TRUE)
stopifnot(length(args)==1)
study <- args[1]
modules <- c('probability_exploration','fundamentals_home_away','goal_distribution_experiment',
 'fundamentals_score_diagnostic','fundamentals_score_shape','fundamentals_high_margin','fundamentals_three_issue_experts',
 'fundamentals_market_comparison','fundamentals_total_market','fundamentals_retraining','eight_issue_holdout','fundamentals_clean_validation','fundamentals_pure_baseline')
for(m in modules) source(paste0('r/',m,'.R'))
prepared <- jsonlite::read_json(file.path(study,'prepared.json'))
stopifnot(!file.exists(file.path(study,'factors.json')))
all <- list(); paths <- list(); dir.create(file.path(study,'projected'))
for(issue in prepared$receipt$contract$issues) {
 path <- file.path(study,'inputs',paste0(issue,'.json.gz'))
 stopifnot(identical(digest::digest(file=path,algo='sha256'),prepared$receipt$files[[path]]))
 con <- gzfile(path,'rt');input <- jsonlite::fromJSON(paste(readLines(con,warn=FALSE),collapse=''),simplifyVector=FALSE);close(con)
 x <- project_clean_validation_input(input,1e-10)
 if(nrow(x$control$fixtures)) all[[issue]] <- pure_baseline_factors(x$control,x$market,x$cutoffs)
 file <- file.path(study,'projected',paste0(issue,'.json'))
 jsonlite::write_json(x,file,auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null')
 paths[[file]] <- digest::digest(file=file,algo='sha256')
 cat('PROJECTED',issue,nrow(x$control$fixtures),'\n');flush.console()
}
code <- c(paste0('r/',modules,'.R'),'scripts/project_updated_scope.R')
jsonlite::write_json(list(rows=dplyr::bind_rows(all),cutoffs=prepared$receipt$cutoffs,issues=prepared$receipt$contract$issues,
 scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',historical_admission=FALSE,
 source_hashes=c(paths,prepared$receipt$files,prepared$receipt$source_hashes,
  stats::setNames(list(digest::digest(file=file.path(study,'prepared.json'),algo='sha256')),file.path(study,'prepared.json'))),
 implementation=as.list(stats::setNames(vapply(code,digest::digest,character(1),file=TRUE,algo='sha256'),code))),
 file.path(study,'factors.json'),auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null')
