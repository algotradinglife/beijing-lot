# Read accepted projected inputs; freeze pure p and unchanged market q.
args <- commandArgs(TRUE)
if(length(args)!=2) stop('Supply accepted expert study and new pure study')
study <- args[1];out <- args[2]
if(dir.exists(out)) stop('Immutable new study required')
source('r/fundamentals_pure_baseline.R')
receipt <- jsonlite::read_json(file.path(study,'projected/receipt.json'))
for(p in names(receipt$files)) stopifnot(identical(digest::digest(file=p,algo='sha256'),receipt$files[[p]]))
prepared <- jsonlite::read_json(file.path(study,'prepared.json'))
stopifnot(identical(receipt$prepared_sha256,digest::digest(file=file.path(study,'prepared.json'),algo='sha256')))
all <- list()
for(issue in prepared$receipt$contract$issues) {
 x <- jsonlite::read_json(file.path(study,'projected',paste0(issue,'.json')),simplifyVector=TRUE)
 all[[issue]] <- pure_baseline_factors(x$control,x$market,x$cutoffs)
 cat('PURE',issue,nrow(all[[issue]]),'\n');flush.console()
}
rows <- dplyr::bind_rows(all)
expert <- tibble::as_tibble(jsonlite::read_json(file.path(study,'factors.json'),simplifyVector=TRUE)$rows)
paired <- dplyr::full_join(rows,expert,by=c('issue','slot','provider_id'),suffix=c('_pure','_expert'),relationship='one-to-one')
stopifnot(nrow(paired)==nrow(rows),nrow(rows)==nrow(expert),!anyNA(paired))
for(d in c('W','D','L')) stopifnot(all(abs(paired[[paste0('q_',d,'_pure')]]-paired[[paste0('q_',d,'_expert')]])<1e-12))
code <- c('r/fundamentals_pure_baseline.R','scripts/prepare_pure_baseline.R')
files <- c(file.path(study,c('prepared.json','projected/receipt.json','factors.json')),names(receipt$files))
dir.create(out,recursive=TRUE)
jsonlite::write_json(list(rows=rows,cutoffs=prepared$receipt$cutoffs,
 scope='PURE_BASELINE_POST_EXPOSURE_PAIRED_DIAGNOSTIC',expert_source=study,
 source_hashes=as.list(stats::setNames(vapply(files,digest::digest,character(1),file=TRUE,algo='sha256'),files)),
 implementation=as.list(stats::setNames(vapply(code,digest::digest,character(1),file=TRUE,algo='sha256'),code))),
 file.path(out,'factors.json'),auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null',pretty=TRUE)
