# Replay the immutable historical run against its authenticated code snapshot.
# This evidence-only snapshot cannot serve new decisions or cutoffs.
root <- normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
out <- file.path(root,'results/fm15-two-issues-20261012')
snapshot <- normalizePath(file.path(out,'implementation-snapshot'),mustWork=TRUE)
# Explicit environment setup link to the declared project interpreter, no install.
venv_link <- file.path(snapshot,'.venv')
if(!file.exists(venv_link)) stopifnot(file.symlink(file.path(root,'.venv'),venv_link))
stopifnot(normalizePath(venv_link)==normalizePath(file.path(root,'.venv')))
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm15-version-20261012/library'))
inv <- fromJSON(file.path(out,'implementation-snapshot-inventory.json'))
stopifnot(all(map_chr(file.path(snapshot,inv$files$path),~digest::digest(file=.x,algo='sha256'))==inv$files$sha256))
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE)
reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(snapshot,'packages/beidan/inst/python'))
shared <- reticulate::import('beidan_backend.temporal_learning',convert=FALSE)
backend <- reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
s <- readRDS(file.path(out,'native-stage.rds'));m <- fromJSON(file.path(out,'manifest.json'))
bp <- file.path(out,m$batch_file);stopifnot(digest::digest(file=bp,algo='sha256')==m$sha256)
x <- readRDS(bp);stopifnot(beidan:::.score_margin_hash(x)==m$object_hash)
parents <- list()
for(issue in names(s$inputs)) {
  hashes <- s$inputs[[issue]]
  stopifnot(all(map_chr(file.path(root,names(hashes)),~digest::digest(file=.x,algo='sha256'))==unlist(hashes,use.names=FALSE)))
  parents[[issue]] <- readRDS(file.path(root,names(hashes)[endsWith(names(hashes),paste0(issue,'-frozen.rds'))]))
}
rows <- list()
for(id in names(s$entries)) {
  e <- s$entries[[id]];f <- e$fixture;p <- e$packet;parent <- parents[[f$issue_id]]
  h <- as_tibble(map(parent$history,identity)) |> filter(fixture_id==id) |> mutate(row_key=paste(scope,match_id,sep=':'),event_date=as.character(event_date))
  native <- beidan:::estimate_recent_venue_goals(h,f[c('fixture_id','issue_id','provider_id','home_id','away_id')],as.character(parent$fixtures$provider_id),shared$Cutoff$decision_epoch(f$issue_id,p$cutoff_utc),e$source_hashes,snapshot,s$policy)
  stopifnot(identical(native,e$native))
  z <- x$entries[[id]];cutoff <- z$base$cutoff
  judgement <- beidan:::build_fm15_tail_judgement(z$base,z$review,'admitted-native-history',cutoff,list(max_radius=2L,threshold=.1,coefficient=.3,tie_tolerance=1e-12))
  stopifnot(identical(judgement,z$policy))
  fixture <- tibble(fixture_id=f$fixture_id,issue_id=f$issue_id,home=f$home,away=f$away)
  ctx <- backend$build_adjustment_evidence_context(z$evidence_rows,as.list(fixture),shared$Cutoff$decision_epoch(f$issue_id,p$cutoff_utc),z$bindings,shared$AvailabilityPolicy$historical_proxy('NATIVE_HISTORY_ARTICLE_QUOTE_POSTHOC_DIAGNOSTIC'),'HISTORICAL_DIAGNOSTIC',snapshot)
  final <- adjust_score_margin_distribution(z$base,judgement$judgement,ctx,fixture,cutoff,snapshot)
  stopifnot(identical(final,z$final),identical(final,readRDS(file.path(root,z$score_path))))
  stopifnot(is.finite(f$handicap),f$handicap==round(f$handicap))
  projected <- project_score_outcomes(final,as.integer(f$handicap),snapshot)
  actual <- x$probabilities |> filter(fixture_id==id) |> select(names(projected))
  stopifnot(identical(projected,actual))
  rows[[id]] <- tibble(fixture_id=id,native_receipt_identical=TRUE,policy_identical=TRUE,final_receipt_identical=TRUE,projection_identical=TRUE)
  if(length(rows) %% 25L==0L) message('Independent replay ',length(rows))
}
ledger <- bind_rows(rows);stopifnot(nrow(ledger)==260L)
write_csv(ledger,file.path(out,'replay-ledger.csv'))
write_json(list(status='FULL_IDENTICAL_REPLAY',fixtures=nrow(ledger),forecast_sha256=m$sha256,snapshot_inventory_sha256=digest::digest(file=file.path(out,'implementation-snapshot-inventory.json'),algo='sha256'),replay_code_sha256=digest::digest(file=file.path(root,'r/fm15_two_issue_replay.R'),algo='sha256'),replayed_at_utc=format(Sys.time(),'%Y-%m-%dT%H:%M:%SZ',tz='UTC'),intended_use='POSTHOC_HISTORICAL_DIAGNOSTIC'),file.path(out,'replay-receipt.json'),auto_unbox=TRUE,pretty=TRUE)
