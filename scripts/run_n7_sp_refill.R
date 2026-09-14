#!/usr/bin/env Rscript
# Prediction-only refill stage. Settlement is a separate consumer of this freeze.
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==1)
cfg <- jsonlite::fromJSON(args[[1]])
stopifnot(!dir.exists(cfg$output_dir),length(cfg$issues)>0,
  !anyDuplicated(cfg$issues),!anyDuplicated(cfg$seeds))
reticulate::use_python(cfg$python,required=TRUE)
sources <- c('r/n7_sleeve_tables.R','r/n7_joint_sleeves.R','r/n7_capital_depth.R',
  'r/n7_capital_portfolio.R','r/n7_core_opportunity.R','r/n7_sweet_union.R',
  'r/n7_funding_modes.R','r/n7_sp_filter.R','r/n7_sp_refill.R',
  'r/n7_sp_refill_prepare.R','r/n7_sp_refill_plans.R')
for(p in sources)source(p)
code <- c(sources,'scripts/run_n7_sp_refill.R','src/n7_sp_refill.py')
identities <- vapply(code,digest::digest,character(1),algo='sha256',file=TRUE)
bindings <- reticulate::import('src.n7_union_inputs',convert=TRUE)
binding <- bindings$bind_union_inputs(cfg$catalog,cfg$rank_dir,cfg$repository_root)
temporal<-reticulate::import('src.temporal_learning',convert=TRUE)
pathlib<-reticulate::import('pathlib',convert=FALSE)
closure<-temporal$implementation_closure(pathlib$Path(cfg$repository_root),
  c('src.n7_sp_refill','src.n7_sleeve_states','src.fundamentals_n7_baseline'),
  distributions=c('numpy','pandas'))
catalog <- jsonlite::fromJSON(cfg$catalog)$issues
stopifnot(all(cfg$issues %in% catalog$issue),!anyDuplicated(catalog$issue))
dir.create(cfg$output_dir,recursive=TRUE)
rows<-funded<-actions<-manifests<-list()
for(issue in cfg$issues) {
  item<-catalog[catalog$issue==issue,,drop=FALSE]
  stopifnot(digest::digest(file=item$path,algo='sha256')==item$sha256)
  con<-gzfile(item$path,'rt');text<-paste(readLines(con,warn=FALSE),collapse='\n');close(con)
  cutoffs<-jsonlite::fromJSON(text,simplifyVector=FALSE)$cutoffs
  for(seed in cfg$seeds) {
    prepared<-n7_sp_refill_prepare(text,cutoffs,cfg$python,cfg$model_id,
      cfg$minimum_sp,cfg$candidate_count,seed,cfg$maximum_attempts,cfg$depths,
      cfg$depth_reference_targets,cfg$target,cfg$cap_cny,cfg$unit_cny,cfg$payout_factor,cfg$n)
    result<-n7_sp_refill_plans(prepared,cutoffs,cfg,seed)
    key<-paste(issue,seed,sep='-')
    jsonlite::write_json(result$plans,file.path(cfg$output_dir,paste0(key,'-plans.json')),
      auto_unbox=TRUE,digits=NA,null='null')
    jsonlite::write_json(prepared$refill,file.path(cfg$output_dir,paste0(key,'-candidates.json')),
      auto_unbox=TRUE,digits=NA,null='null')
    writeLines(prepared$bundle_json,file.path(cfg$output_dir,paste0(key,'-bundle.json')))
    rows[[key]]<-dplyr::mutate(result$rows,cohort=item$cohort)
    funded[[key]]<-result$funded;actions[[key]]<-result$actions
    manifests[[key]]<-list(source_sha256=item$sha256,cutoffs=cutoffs,unchanged=prepared$unchanged)
    message(key,': ',prepared$refill$actual,' candidates; ',length(result$plans),' plans')
  }
}
readr::write_csv(dplyr::bind_rows(rows),file.path(cfg$output_dir,'predictions.csv'))
readr::write_csv(dplyr::bind_rows(funded),file.path(cfg$output_dir,'funded.csv'))
readr::write_csv(dplyr::bind_rows(actions),file.path(cfg$output_dir,'actions.csv'))
stopifnot(identical(identities,vapply(code,digest::digest,character(1),algo='sha256',file=TRUE)),
  bindings$verify_union_binding(binding,cfg$catalog,cfg$rank_dir,cfg$repository_root))
temporal$verify_implementation_closure(pathlib$Path(cfg$repository_root),closure)
files<-list.files(cfg$output_dir,full.names=TRUE)
jsonlite::write_json(list(config=cfg,input_binding=binding,python_implementation=closure,metadata=manifests,
  implementation=as.list(identities),historical_admission=FALSE,labels_loaded=FALSE,
  files=as.list(setNames(vapply(files,digest::digest,character(1),algo='sha256',file=TRUE),basename(files)))),
  file.path(cfg$output_dir,'prediction-freeze.json'),auto_unbox=TRUE,digits=NA,pretty=TRUE)
