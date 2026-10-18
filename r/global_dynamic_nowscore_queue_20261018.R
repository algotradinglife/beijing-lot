# Rscript r/global_dynamic_nowscore_queue_20261018.R ROOT BASE_DIR EURO_DIR OUTPUT_CSV
# Bounded missing-only acquisition queue, never a learned match selection.
args<-commandArgs(TRUE);stopifnot(length(args)==4L)
root<-normalizePath(args[1],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse))
s<-read_csv(file.path(args[2],'slots.csv'),col_types=cols(.default=col_character(),slot=col_integer()))
b<-read_csv(file.path(args[2],'base-resources.csv'),col_types=cols(.default=col_character()))
e<-read_csv(file.path(args[3],'euro-resources.csv'),col_types=cols(.default=col_character()))
q<-bind_rows(b,e) |> filter(source=='nowscore',state=='CACHE_MISS') |>
 transmute(fixture_id,source,url,kind=case_when(str_detect(url,'/analysisJs/data')~'auxiliary',str_detect(url,'/analysis/')~'analysis',TRUE~'euro')) |>
 left_join(s |> select(fixture_id,provider_id),by='fixture_id',relationship='many-to-one') |> arrange(kind,fixture_id)
stopifnot(nrow(s)==365L,nrow(q)>0L,nrow(q)<=730L,!anyDuplicated(q$url),!anyNA(q),all(q$fixture_id%in%s$fixture_id))
if(file.exists(args[4])) {
 old<-read_csv(args[4],col_types=cols(.default=col_character()));stopifnot(identical(names(q),names(old)))
 for(name in names(q))stopifnot(identical(q[[name]],old[[name]]))
}else write_csv(q,args[4])
paths<-c(file.path(args[2],c('slots.csv','base-resources.csv')),file.path(args[3],'euro-resources.csv'))
receipt<-list(output_sha256=digest::digest(file=args[4],algo='sha256'),source_client=list(path='r/global_dynamic_nowscore_queue_20261018.R',sha256=digest::digest(file='r/global_dynamic_nowscore_queue_20261018.R',algo='sha256')),input_files=tibble(path=paths,sha256=map_chr(paths,~digest::digest(file=.x,algo='sha256'))),rows=nrow(q),fixtures=n_distinct(q$fixture_id))
p<-paste0(args[4],'.json');text<-jsonlite::toJSON(receipt,auto_unbox=TRUE,pretty=TRUE,dataframe='rows')
if(file.exists(p))stopifnot(identical(paste(readLines(p,warn=FALSE),collapse='\n'),as.character(text)))else writeLines(text,p)
print(q |> count(kind))
