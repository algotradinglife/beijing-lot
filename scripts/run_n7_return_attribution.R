#!/usr/bin/env Rscript
# Descriptive replay of already frozen #439 plans. No new decisions or fitting.
args <- commandArgs(trailingOnly=TRUE);stopifnot(length(args)==1)
cfg <- jsonlite::fromJSON(args[1]);library(dplyr)
source('r/n7_sleeve_tables.R');source('r/n7_return_attribution.R');source('r/n7_fixture_price_diagnostic.R')
reticulate::use_python(cfg$python,required=TRUE)
bindings<-reticulate::import('src.n7_union_inputs',convert=TRUE)
input_binding<-bindings$bind_union_inputs(cfg$catalog,cfg$rank_dir,cfg$repository_root)
code<-c('r/n7_fixture_price_diagnostic.R','r/n7_return_attribution.R','r/n7_sleeve_tables.R','scripts/run_n7_return_attribution.R')
code_identity<-vapply(code,digest::digest,character(1),file=TRUE,algo='sha256')
stopifnot(!dir.exists(cfg$output_dir));dir.create(cfg$output_dir,recursive=TRUE)
catalog <- jsonlite::fromJSON(cfg$catalog)
rank_receipt <- jsonlite::fromJSON(file.path(cfg$rank_dir,'receipt.json'))
rank_path <- file.path(cfg$rank_dir,'ranks.csv')
stopifnot(digest::digest(file=rank_path,algo='sha256')==rank_receipt$outputs[['ranks.csv']])
ranks <- readr::read_csv(rank_path,show_col_types=FALSE,col_types=readr::cols(issue='c',sleeve_id='c'))
audit_rows<-list();audit_hashes<-list()
for(study in rank_receipt$sources$study) {
  ap<-file.path(study,'audit-snapshot.json');ep<-file.path(study,'evaluation-receipt.json')
  er<-jsonlite::fromJSON(ep)
  sf<-jsonlite::fromJSON(file.path(study,'plans-frozen.json'))
  source_hash<-rank_receipt$sources$freeze_sha256[rank_receipt$sources$study==study]
  stopifnot(length(source_hash)==1,er$freeze_sha256==source_hash,
    digest::digest(file=ap,algo='sha256')==er$audit_sha256)
  source_audit<-jsonlite::fromJSON(ap)$rows
  audit_rows[[study]]<-source_audit[as.character(source_audit$issue) %in% sf$receipt$issues,]
  audit_hashes[[ap]]<-er$audit_sha256
  audit_hashes[[ep]]<-digest::digest(file=ep,algo='sha256')
}
audits<-bind_rows(audit_rows)
evidence <- list();fixture_prices<-list()
for(i in seq_len(nrow(catalog$issues))) {
  item<-catalog$issues[i,]
  stopifnot(digest::digest(file=item$path,algo='sha256')==item$sha256)
  b<-jsonlite::fromJSON(gzfile(item$path),simplifyVector=FALSE)
  s<-n7_sleeve_tables(b,b$cutoffs,cfg$model_id)
  r<-ranks[ranks$issue==item$issue,]
  stopifnot(nrow(r)==nrow(s$rank_idx),!anyDuplicated(r$sleeve_id),
    setequal(r$sleeve_id,rownames(s$rank_idx)))
  row<-match(r$sleeve_id,rownames(s$rank_idx))
  col<-s$rank_idx[cbind(row,r$actual_rank)]
  stopifnot(all(col==r$actual_state_id+1),
    all(abs(s$prob_mat[cbind(row,col)]-r$actual_probability)<1e-10))
  r$estimated_actual_payout<-s$payout_hat_mat[cbind(row,col)]
  a<-audits |> filter(as.character(issue)==item$issue) |> mutate(issue=as.character(issue),provider_id=as.character(provider_id))
  f<-bind_rows(b$expanded_pool$fixtures) |> mutate(issue=as.character(issue),provider_id=as.character(provider_id))
  fp<-n7_fixture_price_diagnostic(f,a);fixture_prices[[i]]<-fp
  for(g in b$sleeves) {
    selected<-fp[as.integer(unlist(g$fixture_indices))+1L,]
    state<-sum((match(selected$actual_direction,c('W','D','L'))-1L)*3^(6:0))
    stopifnot(state==r$actual_state_id[r$sleeve_id==as.character(g$id)])
    actual<-1.3*prod(selected$spf_sp)
    stopifnot(abs(actual-r$actual_gross_cny[r$sleeve_id==as.character(g$id)])<1e-6)
  }
  evidence[[i]]<-r
  if(i%%20==0)message('attribution sources: ',i,'/',nrow(catalog$issues))
}
evidence<-bind_rows(evidence)
readr::write_csv(evidence,file.path(cfg$output_dir,'group-evidence.csv'))
readr::write_csv(bind_rows(fixture_prices),file.path(cfg$output_dir,'fixture-prices.csv'))
bridges<-list();periods<-list();stage_receipts<-list()
for(stage in cfg$stages) {
  freeze<-jsonlite::fromJSON(file.path(stage,'plans-frozen.json'))
  for(name in names(freeze$files))stopifnot(digest::digest(file=file.path(stage,name),algo='sha256')==freeze$files[[name]])
  receipt<-jsonlite::fromJSON(file.path(stage,'evaluation-receipt.json'))
  stopifnot(digest::digest(file=file.path(stage,'plans-frozen.json'),algo='sha256')==receipt$freeze_sha256,
    digest::digest(file=file.path(stage,'results.csv'),algo='sha256')==receipt$results_sha256,
    receipt$ranks_sha256==rank_receipt$outputs[['ranks.csv']])
  f<-readr::read_csv(file.path(stage,'funded.csv'),show_col_types=FALSE,col_types=readr::cols(.default='d',issue='c',arm='c',sleeve_id='c'))
  copies<-f$stake/(2*f$depth)
  if('copies' %in% names(f))stopifnot(all(f$copies==copies))
  f$copies<-copies
  z<-n7_return_attribution(f,evidence,2)
  results<-readr::read_csv(file.path(stage,'results.csv'),show_col_types=FALSE,col_types=readr::cols(issue='c'))
  reconciled<-results |> left_join(z$periods,by=c('issue','arm','seed'),suffix=c('','.bridge'),relationship='one-to-one')
  stopifnot(all(abs(results$net-coalesce(reconciled$actual_net,0))<1e-7),
    all(abs(results$expected_net-coalesce(reconciled$model_net,0))<1e-7))
  bridges[[stage]]<-mutate(z$groups,stage=basename(stage))
  reconciled<-reconciled |> mutate(across(c(model_net,outcome_residual,price_residual,actual_net,estimated_hit_gross,actual_gross,group_hits,expected_group_hits),~coalesce(.x,0)))
  periods[[stage]]<-mutate(reconciled,stage=basename(stage))
  stage_receipts[[stage]]<-receipt
}
readr::write_csv(bind_rows(bridges),file.path(cfg$output_dir,'bridges.csv'))
p<-bind_rows(periods);readr::write_csv(p,file.path(cfg$output_dir,'periods.csv'))
s<-p |> group_by(stage,arm,seed) |> summarise(stake=sum(stake),
  model_net=sum(coalesce(model_net,0)),outcome_residual=sum(coalesce(outcome_residual,0)),
  price_residual=sum(coalesce(price_residual,0)),net=sum(net),roi=net/stake,.groups='drop')
readr::write_csv(s,file.path(cfg$output_dir,'summary.csv'))
files<-c('fixture-prices.csv','group-evidence.csv','bridges.csv','periods.csv','summary.csv')
stopifnot(identical(code_identity,vapply(code,digest::digest,character(1),file=TRUE,algo='sha256')),
  bindings$verify_union_binding(input_binding,cfg$catalog,cfg$rank_dir,cfg$repository_root))
for(ap in names(audit_hashes))stopifnot(digest::digest(file=ap,algo='sha256')==audit_hashes[[ap]])
jsonlite::write_json(list(audit_hashes=audit_hashes,config=cfg,input_binding=input_binding,historical_admission=FALSE,kind='DESCRIPTIVE_FROZEN_PLAN_ATTRIBUTION',
  stages=stage_receipts,catalog_sha256=digest::digest(file=cfg$catalog,algo='sha256'),
  implementation=as.list(setNames(vapply(code,digest::digest,character(1),file=TRUE,algo='sha256'),code)),
  outputs=as.list(setNames(vapply(file.path(cfg$output_dir,files),digest::digest,character(1),file=TRUE,algo='sha256'),files))),
  file.path(cfg$output_dir,'receipt.json'),auto_unbox=TRUE,pretty=TRUE)
