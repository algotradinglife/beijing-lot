# Thin label-free prepared input -> R baseline/features entry.
args <- commandArgs(TRUE)
if(length(args)!=2) stop('Supply study and output directory')
study <- args[1];out <- args[2]
if(dir.exists(out)) stop('Immutable new output required')
modules <- c('probability_exploration','fundamentals_home_away','goal_distribution_experiment',
 'fundamentals_score_diagnostic','fundamentals_score_shape','fundamentals_high_margin','fundamentals_three_issue_experts',
 'fundamentals_market_comparison','fundamentals_total_market','fundamentals_retraining','eight_issue_holdout','fundamentals_clean_validation')
for(m in modules) source(paste0('r/',m,'.R'))
prepared <- jsonlite::read_json(file.path(study,'prepared.json'))
for(path in names(prepared$receipt$files)) stopifnot(identical(digest::digest(file=path,algo='sha256'),prepared$receipt$files[[path]]))
dir.create(out,recursive=TRUE)
for(issue in prepared$receipt$contract$issues) {
 connection <- gzfile(file.path(study,'inputs',paste0(issue,'.json.gz')),'rt')
 input <- jsonlite::fromJSON(paste(readLines(connection,warn=FALSE),collapse=''),simplifyVector=FALSE);close(connection)
 result <- project_clean_validation_input(input,1e-10)
 jsonlite::write_json(result,file.path(out,paste0(issue,'.json')),auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null')
 cat('PROJECTED',issue,nrow(result$features),'\n');flush.console()
}
paths <- file.path(out,paste0(unlist(prepared$receipt$contract$issues),'.json'))
code <- c(paste0('r/',modules,'.R'),'scripts/project_clean_validation.R')
receipt <- list(prepared_sha256=digest::digest(file=file.path(study,'prepared.json'),algo='sha256'),
 files=as.list(stats::setNames(vapply(paths,digest::digest,character(1),file=TRUE,algo='sha256'),paths)),
 implementation=as.list(stats::setNames(vapply(code,digest::digest,character(1),file=TRUE,algo='sha256'),code)))
jsonlite::write_json(receipt,file.path(out,'receipt.json'),auto_unbox=TRUE,pretty=TRUE)
