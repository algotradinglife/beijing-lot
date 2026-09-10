# Read-only authoritative R/SQLite query after Python seals all plans and labels.
args <- commandArgs(TRUE)
if(length(args)!=2) stop('Supply study and SQLite path')
study <- args[1];db <- args[2]
source('r/nowscore_query.R');source('r/fundamentals_clean_settlement.R')
out <- file.path(study,'settlement-audit.json')
if(file.exists(out)) stop('Immutable audit already exists')
stopifnot(file.exists(file.path(study,'plans-frozen.json')))
labels <- jsonlite::read_json(file.path(study,'labels.json'),simplifyVector=TRUE)
db_before <- digest::digest(file=db,algo='sha256')
queries <- lapply(sort(unique(labels$issue)),function(issue) query_nowscore_settlement(db,issue,play='spf'))
settlement <- dplyr::bind_rows(lapply(queries,`[[`,'settlement'))
audit <- clean_validation_spf_audit(settlement,tibble::as_tibble(labels))
stopifnot(identical(db_before,digest::digest(file=db,algo='sha256')))
code <- c('r/nowscore_query.R','r/fundamentals_clean_settlement.R','scripts/query_clean_validation.R')
jsonlite::write_json(list(rows=audit,query_rows=settlement,findings=dplyr::bind_rows(lapply(queries,`[[`,'findings')),
 receipt=list(db_path=db,db_sha256=db_before,build_receipt=queries[[1]]$receipt,plans_sha256=digest::digest(file=file.path(study,'plans-frozen.json'),algo='sha256'),
 labels_sha256=digest::digest(file=file.path(study,'labels.json'),algo='sha256'),
 implementation=as.list(stats::setNames(vapply(code,digest::digest,character(1),file=TRUE,algo='sha256'),code)))),
 out,auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null')
cat('AUDITED',nrow(audit),'\n')
