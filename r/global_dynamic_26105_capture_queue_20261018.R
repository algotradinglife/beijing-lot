# Rscript r/global_dynamic_26105_capture_queue_20261018.R ROOT BASE_DIR EURO_DIR OUTPUT_CSV
args<-commandArgs(TRUE);stopifnot(length(args)==4L)
root<-normalizePath(args[1],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse))
s<-read_csv(file.path(args[2],'slots.csv'),col_types=cols(.default=col_character(),slot=col_integer()))
b<-read_csv(file.path(args[2],'base-resources.csv'),col_types=cols(.default=col_character())) |> mutate(kind='analysis')
e<-read_csv(file.path(args[3],'euro-resources.csv'),col_types=cols(.default=col_character())) |> mutate(kind='euro')
q<-bind_rows(b,e) |> filter(source=='titan',state=='CACHE_MISS') |> select(fixture_id,source,url,kind) |>
 left_join(s |> select(fixture_id,provider_id),by='fixture_id',relationship='many-to-one') |> arrange(fixture_id,kind)
stopifnot(nrow(q)==308L,n_distinct(q$fixture_id)==154L,!anyDuplicated(q$url),!anyNA(q))
if(file.exists(args[4])) {
 old<-read_csv(args[4],col_types=cols(.default=col_character()))
 stopifnot(identical(names(q),names(old)))
 for(name in names(q))stopifnot(identical(q[[name]],old[[name]]))
}else write_csv(q,args[4])
print(q |> count(kind))

paths<-c(file.path(args[2],c('slots.csv','base-resources.csv')),file.path(args[3],'euro-resources.csv'))
receipt<-list(output_sha256=digest::digest(file=args[4],algo='sha256'),source_client=list(path='r/global_dynamic_26105_capture_queue_20261018.R',sha256=digest::digest(file='r/global_dynamic_26105_capture_queue_20261018.R',algo='sha256')),input_files=tibble(path=paths,sha256=map_chr(paths,~digest::digest(file=.x,algo='sha256'))),rows=308L,fixtures=154L)
receipt_path<-paste0(args[4],'.json')
text<-jsonlite::toJSON(receipt,auto_unbox=TRUE,pretty=TRUE,dataframe='rows')
if(file.exists(receipt_path))stopifnot(identical(paste(readLines(receipt_path,warn=FALSE),collapse='\n'),as.character(text)))else writeLines(text,receipt_path)
