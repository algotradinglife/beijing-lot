# Combine immutable old/new predictions, then settle every funded prefix at
# current audited SP. No new allocation, selection, fitting or source mutation.
args<-commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1)
cfg<-jsonlite::fromJSON(args[1]);library(dplyr)
source('r/n7_quality_settlement.R')
reticulate::use_python(cfg$python,required=TRUE)
bindings<-reticulate::import('src.n7_union_inputs',convert=TRUE)
study<-cfg$study;output<-file.path(study,'evaluation')
stopifnot(!dir.exists(output))
template<-jsonlite::fromJSON(cfg$allocation_template)
ids<-template$policies$id
predictions<-list();funded<-list();old_results<-list();sources<-list()
for(old in cfg$old_plan_dirs) {
 fp<-file.path(old,'plans-frozen.json');freeze<-jsonlite::fromJSON(fp,simplifyVector=FALSE)
 stopifnot(bindings$verify_union_binding(freeze$input_binding,cfg$old_catalog,
  cfg$old_ranks,cfg$repository_root))
 for(n in c('predictions.csv','funded.csv'))stopifnot(digest::digest(file=file.path(old,n),algo='sha256')==freeze$files[[n]])
 x<-readr::read_csv(file.path(old,'predictions.csv'),col_types=readr::cols(issue='c'),show_col_types=FALSE)
 wanted<-paste0('T250_',ids,'_B')
 keep<-Reduce(`|`,lapply(wanted,startsWith,x=x$arm))
 if(grepl('exchange',basename(old)))keep<-keep & grepl('EXCHANGE',x$arm)
 x<-x[keep,] |> mutate(cohort='原200期')
 g<-readr::read_csv(file.path(old,'funded.csv'),col_types=readr::cols(issue='c',sleeve_id='c'),show_col_types=FALSE) |> semi_join(x,by=c('issue','arm','seed'))
 predictions[[length(predictions)+1L]]<-x;funded[[length(funded)+1L]]<-g
 old_results[[length(old_results)+1L]]<-readr::read_csv(file.path(old,'results.csv'),col_types=readr::cols(issue='c'),show_col_types=FALSE) |> semi_join(x,by=c('issue','arm','seed'))
 sources[[fp]]<-digest::digest(file=fp,algo='sha256')
 for(n in c('predictions.csv','funded.csv','results.csv'))sources[[file.path(old,n)]]<-digest::digest(file=file.path(old,n),algo='sha256')
}
master<-jsonlite::fromJSON(file.path(study,'all-plans-frozen.json'))
for(p in names(master$files))stopifnot(digest::digest(file=p,algo='sha256')==master$files[[p]])
for(p in names(master$files)[basename(names(master$files))=='plans-frozen.json']) {
 freeze<-jsonlite::fromJSON(p);folder<-dirname(p)
 for(n in c('predictions.csv','funded.csv'))stopifnot(digest::digest(file=file.path(folder,n),algo='sha256')==freeze$files[[n]])
 predictions[[length(predictions)+1L]]<-readr::read_csv(file.path(folder,'predictions.csv'),col_types=readr::cols(issue='c'),show_col_types=FALSE)
 funded[[length(funded)+1L]]<-readr::read_csv(file.path(folder,'funded.csv'),col_types=readr::cols(issue='c',sleeve_id='c'),show_col_types=FALSE)
 sources[[p]]<-master$files[[p]]
}
x<-bind_rows(predictions);g<-bind_rows(funded)
mapping<-c('SP130_BREADTH_OPEN_FIRST_coverage_sum'='SUM','SP130_BREADTH_OPEN_FIRST_any_hit'='JOINT',
 'SP130_BREADTH_OPEN_FIRST_expected_net'='EV','SP130_DEPTH_OPEN_FIRST_any_hit'='DEPTH',
 'SP130_EXCHANGE11'='EXCHANGE11','SP130_EXCHANGE12'='EXCHANGE12','SP100_BREADTH_OPEN_FIRST_any_hit'='NO_FILTER')
x$variant<-unname(mapping[sub('_B[0-9]+$','',sub('^T250_','',x$arm))])
stopifnot(!anyNA(x$variant),!anyDuplicated(x[c('issue','arm','seed')]),
 nrow(x)==cfg$expected_issues*7*9,length(unique(x$issue))==cfg$expected_issues)
rank_dir<-cfg$output_dir;rr<-jsonlite::fromJSON(file.path(rank_dir,'receipt.json'))
rp<-file.path(rank_dir,'ranks.csv');stopifnot(digest::digest(file=rp,algo='sha256')==rr$files[['ranks.csv']])
ranks<-readr::read_csv(rp,col_types=readr::cols(issue='c',sleeve_id='c'),show_col_types=FALSE)
unresolved<-anti_join(g,ranks,by=c('issue','sleeve_id'))
if(nrow(unresolved))stop('Funded groups lack audited settlement: ',paste(unique(unresolved$issue),collapse=','))
settled<-n7_quality_settlement(x,g,ranks)
dir.create(output)
readr::write_csv(x,file.path(output,'predictions.csv'));readr::write_csv(g,file.path(output,'funded.csv'))
readr::write_csv(settled$rows,file.path(output,'results.csv'));readr::write_csv(settled$groups,file.path(output,'settled-groups.csv'))
old<-bind_rows(old_results) |> select(issue,arm,seed,old_gross=gross,old_net=net)
changes<-settled$rows |> inner_join(old,by=c('issue','arm','seed'),relationship='one-to-one') |>
 mutate(gross_change=gross-old_gross,net_change=net-old_net)
readr::write_csv(changes,file.path(output,'old-settlement-revisions.csv'))
files<-c('predictions.csv','funded.csv','results.csv','settled-groups.csv','old-settlement-revisions.csv')
sources[[rp]]<-rr$files[['ranks.csv']]
sources[[file.path(rank_dir,'receipt.json')]]<-digest::digest(file=file.path(rank_dir,'receipt.json'),algo='sha256')
jsonlite::write_json(list(status='PASS',config=cfg,source_hashes=sources,plans=nrow(x),issues=cfg$expected_issues,
 files=as.list(setNames(vapply(file.path(output,files),digest::digest,character(1),algo='sha256',file=TRUE),files)),
 implementation=as.list(setNames(vapply(c('r/n7_quality_settlement.R','scripts/combine_n7_expanded_results.R'),
 digest::digest,character(1),algo='sha256',file=TRUE),c('r/n7_quality_settlement.R','scripts/combine_n7_expanded_results.R'))),
 historical_admission=FALSE),file.path(output,'receipt.json'),auto_unbox=TRUE,pretty=TRUE)
message('Settled full expanded grid: ',nrow(x),' plans')
