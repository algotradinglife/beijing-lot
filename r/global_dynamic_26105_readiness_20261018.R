# Rscript r/global_dynamic_26105_readiness_20261018.R ROOT OUTPUT ROSTER_METADATA RAW_PACKET_INDEX
# Offline-import original roster bytes, then cache-only census. No HTTP, forecasts, scores or NAS publication.
args<-commandArgs(TRUE);stopifnot(length(args)==4L)
root<-normalizePath(args[1],mustWork=TRUE);setwd(root);out<-args[2]
stopifnot(!dir.exists(out));dir.create(out,recursive=TRUE)
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc='results/margin-combination-study-20261018/library')
invisible(python_backend(file.path(root,'.venv/bin/python')))
registry<-reticulate::import('beidan_backend.catalog.registry',convert=FALSE)
known<-names(reticulate::py_to_r(registry$catalog_entries()))
source<-reticulate::import('beidan_backend.unified_sources',convert=FALSE)
collector<-reticulate::import('beidan_backend.source_issue_update',convert=FALSE)
client<-source$SourceClient()
metadata_path<-normalizePath(args[3],mustWork=TRUE)
metadata<-jsonlite::fromJSON(metadata_path)
raw_path<-sub('.source.json','.nowscore.raw.html',metadata_path,fixed=TRUE)
stopifnot(metadata$issue_id=='26105',metadata$row_counts$nowscore==365L,
 digest::digest(file=raw_path,algo='sha256')==metadata$raw_sha256$nowscore)
extractor<-reticulate::import('beidan_backend.source_extraction',convert=FALSE)
cache_backend<-reticulate::import('beidan_backend.extraction_cache',convert=FALSE)
contract<-reticulate::import('beidan_backend.issue_schedule.contract',convert=FALSE)
stopifnot(reticulate::py_to_r(cache_backend$canonical_url(metadata$urls$nowscore))==
 reticulate::py_to_r(cache_backend$canonical_url(contract$nowscore_url('26105'))))
body<-reticulate::import('pathlib',convert=FALSE)$Path(raw_path)$read_bytes()
imported<-extractor$extract_nowscore_issue('26105',client$cache_path,max_age=0L,min_interval=5L,
 offline=list(body=body,observed_at=metadata$observed_at$nowscore,content_type=metadata$content_type$nowscore))
roster<-client$issue('26105',max_age=0L,cache_only=TRUE)
stopifnot(reticulate::py_to_r(imported$receipt$capture_id)==reticulate::py_to_r(roster$receipt$capture_id))
r<-reticulate::py_to_r(roster);stopifnot(r$receipt$network_attempts==0L)
fixtures<-bind_rows(r$data)
stopifnot(nrow(fixtures)==365L,!anyDuplicated(fixtures$slot),all(fixtures$issue_id=='26105'))
index_path<-normalizePath(args[4],mustWork=TRUE)
packets<-jsonlite::fromJSON(index_path)
stopifnot(is.data.frame(packets),all(packets$kind%in%c('facts','markets')),!anyDuplicated(packets$packet_path))
imports<-list();packet_hashes<-list()
for(i in seq_len(nrow(packets))) {
 packet_path<-packets$packet_path[i];z<-jsonlite::fromJSON(packet_path,simplifyVector=FALSE)
 packet_hashes[[packet_path]]<-digest::digest(file=packet_path,algo='sha256')
 if(packets$kind[i]=='facts') {
  stopifnot(z$fixture_key%in%paste0('26105:',fixtures$slot))
  caps<-list(list(fixture_id=z$fixture_key,source='titan',url=z$source_url,
    raw_path=z$raw_path,sha256=z$sha256,observed_at=z$observed_at))
 }else {
  stopifnot(z$fixture$fixture_id%in%paste0('26105:',fixtures$slot))
  caps<-z$captures
 }
 for(cap in caps) {
  id<-if(packets$kind[i]=='facts')z$fixture_key else z$fixture$fixture_id
  if(is.null(cap$raw_path)||!file.exists(cap$raw_path)) {
   imports[[length(imports)+1L]]<-tibble(packet_path,fixture_id=id,state='RAW_NOT_RETAINED',url=cap$url %||% NA_character_,raw_path=cap$raw_path %||% NA_character_,sha256=cap$sha256 %||% NA_character_,observed_at=cap$observed_at %||% NA_character_,capture_id=NA_integer_)
   next
  }
  stopifnot(digest::digest(file=cap$raw_path,algo='sha256')==cap$sha256)
  raw<-reticulate::import('pathlib',convert=FALSE)$Path(cap$raw_path)$read_bytes()
  imported_cap<-client$cache$extract('titan',cap$url,source$document_bytes,max_age=0L,min_interval=5L,
   offline=list(body=raw,observed_at=cap$observed_at,content_type=cap$content_type))
  cr<-reticulate::py_to_r(imported_cap$receipt)
  stopifnot(cr$network_attempts==0L,cr$sha256==cap$sha256)
  imports[[length(imports)+1L]]<-tibble(packet_path,fixture_id=id,state='IMPORTED_OR_REUSED_VERIFIED_RAW',url=cap$url,raw_path=cap$raw_path,sha256=cap$sha256,observed_at=cap$observed_at,capture_id=as.integer(cr$capture_id))
 }
}
import_ledger<-bind_rows(imports);stopifnot(is_tibble(import_ledger),nrow(import_ledger)>0L)
write_csv(import_ledger,file.path(out,'raw-reuse-ledger.csv'))
result<-collector$collect_issue(client,'26105',max_age=0L,cache_only=TRUE)
collector$validate_tables(result)
receipt<-reticulate::py_to_r(result$receipt);stopifnot(receipt$network_attempts==0L,receipt$expected_slots==365L)
status<-bind_rows(reticulate::py_to_r(result$tables[['status']]))
resources<-bind_rows(reticulate::py_to_r(result$tables[['resources']]))
stopifnot(is_tibble(status),is_tibble(resources),nrow(status)==365L,!anyDuplicated(status$fixture_id),all(status$issue=='26105'))
# Do not use target scores/status to select or fit; this inventory concerns source availability only.
slots<-fixtures |> transmute(fixture_id=paste0('26105:',slot),slot=as.integer(slot),provider_id=native_id)
stopifnot(setequal(slots$fixture_id,status$fixture_id),!anyNA(slots),!anyDuplicated(slots$provider_id))
files<-c('results/fm171-upcoming-20261018/frozen-probabilities.rds','results/fm171-check-20261019/frozen-probabilities.rds')
old_hashes<-map_chr(files,~digest::digest(file=.x,algo='sha256'))
coverage<-list()
for(p in files) {
 x<-readRDS(p)
 stopifnot(x$cutoff$issue_id=='26105',x$model_id=='FM-1.7.1')
 for(id in names(x$entries)) {
  e<-x$entries[[id]]
  stopifnot(id%in%slots$fixture_id,is_tibble(e$base$grid),abs(sum(e$base$grid$probability)-1)<1e-8)
  coverage[[paste(p,id)]]<-tibble(snapshot=p,fixture_id=id,cutoff_utc=x$cutoff$cutoff_utc,full100_source_available=TRUE)
 }
}
coverage<-bind_rows(coverage)
stopifnot(identical(old_hashes,map_chr(files,~digest::digest(file=.x,algo='sha256'))))
write_csv(slots,file.path(out,'slots.csv'));write_csv(status,file.path(out,'base-status.csv'))
write_csv(resources,file.path(out,'base-resources.csv'));write_csv(coverage,file.path(out,'existing-fm171.csv'))
# Retain source roster separately; labels present in original bytes are not evaluated here.
jsonlite::write_json(r,file.path(out,'frozen-roster.json'),auto_unbox=TRUE,pretty=TRUE,digits=NA)
outputs<-c('slots.csv','base-status.csv','base-resources.csv','existing-fm171.csv','frozen-roster.json','raw-reuse-ledger.csv')
manifest<-list(scope=365L,issue_id='26105',network_attempts=0L,target_labels_evaluated=FALSE,
 all_matches_finished=FALSE,all_finished_evidence='USER_CONFIRMED_UNFINISHED_NO_NEW_FINISH_CHECK',
 dataset_registration=tibble(issue_id=rep(c('26105','26106'),each=2),kind=rep(c('fundamentals','euro'),2)) |>
  mutate(dataset=paste0(if_else(kind=='fundamentals','source_issue_','source_euro_issue_'),issue_id),registered=dataset%in%known),
 reused_forecasts=tibble(path=files,sha256=unname(old_hashes)),
 collection_receipt=receipt,roster_receipt=r$receipt,
 metadata_input=list(path=metadata_path,sha256=digest::digest(file=metadata_path,algo='sha256'),raw_path=raw_path,raw_sha256=metadata$raw_sha256$nowscore,original_observed_at=metadata$observed_at$nowscore),
 raw_packet_inputs=list(path=index_path,sha256=digest::digest(file=index_path,algo='sha256'),packet_sha256=packet_hashes),
 client_sha256=digest::digest(file='r/global_dynamic_26105_readiness_20261018.R',algo='sha256'),
 files=as.list(map_chr(outputs,~digest::digest(file=file.path(out,.x),algo='sha256'))) |> set_names(outputs),
 generated_at_utc=format(Sys.time(),'%Y-%m-%dT%H:%M:%SZ',tz='UTC'))
jsonlite::write_json(manifest,file.path(out,'manifest.json'),auto_unbox=TRUE,pretty=TRUE,digits=NA)
print(status |> count(state),n=Inf);print(resources |> count(source,state),n=Inf)
print(tibble(frozen_snapshots=length(files),frozen_rows=nrow(coverage),unique_frozen_fixtures=n_distinct(coverage$fixture_id),whole_issue=365L))
