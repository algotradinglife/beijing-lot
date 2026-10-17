# Merge four independently recomputed replay receipts; no fitting or selection.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
library(beidan,lib.loc=file.path(root,'r_lib'))
out<-file.path(root,'results/fm171-26103-draw-20261017')
x<-readRDS(file.path(out,'native-forecasts.rds'));m<-jsonlite::fromJSON(file.path(out,'native-manifest.json'))
stopifnot(digest::digest(file=file.path(out,'native-forecasts.rds'),algo='sha256')==m$sha256)
rs<-lapply(seq_len(4),function(i)jsonlite::fromJSON(file.path(out,paste0('native-replay-',i,'of4.json'))))
ids<-unlist(lapply(rs,`[[`,'processed_fixture_ids'))
stopifnot(length(ids)==407,!anyDuplicated(ids),setequal(ids,x$audit$fixture_id),
 sum(vapply(rs,`[[`,numeric(1),'forecasts'))==length(x$entries))
for(r in rs)stopifnot(r$status=='FULL_IDENTICAL_REPLAY',r$sha256==m$sha256,r$bindings_sha256==beidan:::.score_margin_hash(x$bindings))
jsonlite::write_json(list(status='FULL_IDENTICAL_REPLAY',forecasts=length(x$entries),scope=407,sha256=m$sha256,
 method='Four disjoint fresh recomputations compared exact entries/audit/probabilities/bindings to frozen full batch; complete407-ID union verified',
 client_sha256=digest::digest(file=file.path(root,'r/fm171_26103_native_replay_accept.R'),algo='sha256')),
 file.path(out,'native-replay.json'),auto_unbox=TRUE,pretty=TRUE)
cat('Accepted407-ID complete independent replay, forecasts',length(x$entries),'\n')
