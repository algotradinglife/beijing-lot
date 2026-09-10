# Query only the explicitly nominated partition; test calls follow model freeze.
args <- commandArgs(TRUE)
if(length(args)!=4) stop('Supply contract, train/test, SQLite path, output JSON')
source('r/nowscore_query.R');source('r/fundamentals_expert_refresh.R')
contract <- jsonlite::read_json(args[1]);part <- args[2]
stopifnot(part %in% c('train','test'),!file.exists(args[4]))
if(part=='test') stopifnot(file.exists(file.path(dirname(args[1]),'models-frozen.json')))
issues <- unlist(contract[[paste0(part,'_issues')]])
sha <- digest::digest(file=args[3],algo='sha256')
x <- query_expert_refresh_labels(args[3],issues)
stopifnot(identical(sha,digest::digest(file=args[3],algo='sha256')))
x$receipt <- list(db_path=args[3],db_sha256=sha,partition=part,issues=issues,
  contract_sha256=digest::digest(file=args[1],algo='sha256'),
  query_api_sha256=digest::digest(file='r/nowscore_query.R',algo='sha256'))
jsonlite::write_json(x,args[4],auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null',pretty=TRUE)
cat('LABELS',part,nrow(x$labels),'COMPLETED',sum(x$labels$label_status=='COMPLETED'),'\n')
