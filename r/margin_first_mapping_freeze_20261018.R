# Label-free seven-round selection. Reusable ranking lives in installed beidan.
args <- commandArgs(TRUE);stopifnot(length(args)==1L)
root <- normalizePath(args[1],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse))
library(beidan,lib.loc=file.path(root,'results/margin-first-mapping-20261018/library'))
out <- file.path(root,'results/margin-first-mapping-20261018')
target <- file.path(out,'frozen-selections.rds');stopifnot(!file.exists(target))
manifest <- jsonlite::fromJSON(file.path(out,'input-manifest.json'))
input_path <- file.path(out,'inputs.rds')
stopifnot(digest::digest(file=input_path,algo='sha256')==manifest$input_sha256)
inputs <- readRDS(input_path);stopifnot(!inputs$target_labels_opened)
selections <- list();support <- list();receipts <- list()
for (key in names(inputs$rounds)) {
 r <- inputs$rounds[[key]]
 d <- list(cutoff=r$cutoff,margins=r$margins,legs=r$legs)
 d$receipt <- c(r$source_receipt,list(input_hash=rlang::hash(list(margins=d$margins,legs=d$legs))))
 for (depth in c(4,5,Inf)) {
  ranked <- beidan:::RankFirstMarginTickets(d,depth)
  tag <- if(is.finite(depth))as.character(depth)else'FULL'
  receipts[[paste(key,tag,sep='|')]] <- ranked$receipt
  support[[paste(key,tag,sep='|')]] <- ranked$tickets |> count(group_slot,name='supported_tickets') |>
    mutate(index=r$index,depth=tag)
  for (method in c('FIRST','SUM')) {
   t <- ranked$tickets
   if(method=='SUM') t <- t |> group_by(group_slot) |>
     arrange(desc(retained_ticket_mass),ticket_id,.by_group=TRUE) |>
     mutate(rank=row_number()) |> ungroup()
   for(start in c(1L,30L)) {
    counts <- t |> count(group_slot,name='available') |> mutate(window_complete=available>=start+124L)
    chosen <- t |> left_join(counts,by='group_slot',relationship='many-to-one') |>
      filter(window_complete,rank>=start,rank<=start+124L) |>
      mutate(index=r$index,depth=tag,method=method,window_start=start)
    selections[[paste(key,tag,method,start,sep='|')]] <- chosen
   }
  }
 }
}
result <- list(selections=bind_rows(selections),support=bind_rows(support),receipts=receipts,
 input_sha256=manifest$input_sha256,producer_sha256=digest::digest(file='r/margin_first_mapping_freeze_20261018.R',algo='sha256'),
 target_labels_opened=FALSE,prospective_admission=FALSE)
counts <- result$selections |> count(index,depth,method,window_start,group_slot)
stopifnot(all(counts$n==125L),!anyDuplicated(result$selections[c('index','depth','method','window_start','group_slot','ticket_id')]))
saveRDS(result,target)
write_csv(result$support,file.path(out,'support.csv'))
write_csv(counts,file.path(out,'selection-counts.csv'))
jsonlite::write_json(list(sha256=digest::digest(file=target,algo='sha256'),input_sha256=manifest$input_sha256,
 producer_sha256=result$producer_sha256,target_labels_opened=FALSE,selected_rows=nrow(result$selections)),
 file.path(out,'selection-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
print(result$support |> group_by(depth) |> summarise(groups=n(),min_space=min(supported_tickets),max_space=max(supported_tickets),.groups='drop'))
