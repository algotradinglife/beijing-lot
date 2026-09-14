#!/usr/bin/env Rscript
# Prediction-only residual-cash experiment; settlement is a separate phase.
args<-commandArgs(TRUE);stopifnot(length(args)==1)
cfg<-jsonlite::fromJSON(args[1]);stopifnot(!dir.exists(cfg$output_dir))
reticulate::use_python(cfg$python,required=TRUE)
sources<-c('r/n7_sleeve_tables.R','r/n7_joint_sleeves.R','r/n7_capital_depth.R',
 'r/n7_capital_portfolio.R','r/n7_residual_refill.R','r/n7_residual_plans.R')
for(p in sources)source(p)
code<-c(sources,'scripts/run_n7_residual_refill.R')
hashes<-vapply(code,digest::digest,character(1),file=TRUE,algo='sha256')
original<-jsonlite::fromJSON(file.path(cfg$control_dir,'plans-frozen.json'))
refill<-jsonlite::fromJSON(file.path(cfg$refill_dir,'prediction-freeze.json'),simplifyVector=FALSE)
inputs<-c(file.path(cfg$control_dir,c('plans-frozen.json','funded.csv','predictions.csv')),
 file.path(cfg$refill_dir,'prediction-freeze.json'))
input_hashes<-vapply(inputs,digest::digest,character(1),file=TRUE,algo='sha256')
for(name in names(original$files))stopifnot(digest::digest(file=file.path(cfg$control_dir,name),algo='sha256')==original$files[[name]])
for(name in names(refill$files))stopifnot(digest::digest(file=file.path(cfg$refill_dir,name),algo='sha256')==refill$files[[name]])
bindings<-reticulate::import('src.n7_union_inputs',convert=TRUE)
stopifnot(bindings$verify_union_binding(refill$input_binding,cfg$catalog,cfg$rank_dir,cfg$repository_root))
temporal<-reticulate::import('src.temporal_learning',convert=TRUE)
pathlib<-reticulate::import('pathlib',convert=FALSE)
closure<-temporal$implementation_closure(pathlib$Path(cfg$repository_root),
 c('src.fundamentals_n7_baseline','src.temporal_learning'),distributions=c('numpy','pandas'))
funded<-readr::read_csv(file.path(cfg$control_dir,'funded.csv'),
 col_types=readr::cols(issue='c',sleeve_id='c'),show_col_types=FALSE)
dir.create(cfg$output_dir,recursive=TRUE)
rows<-actions<-metadata<-list()
for(issue in cfg$issues)for(seed in cfg$seeds) {
 key<-paste(issue,seed,sep='-')
 bundle_path<-file.path(cfg$refill_dir,paste0(key,'-bundle.json'))
 ledger_path<-file.path(cfg$refill_dir,paste0(key,'-candidates.json'))
 raw<-paste(readLines(bundle_path,warn=FALSE),collapse='\n')
 ledger<-jsonlite::fromJSON(ledger_path,simplifyVector=FALSE)
 cutoffs<-jsonlite::fromJSON(raw,simplifyVector=FALSE)$cutoffs
 result<-n7_residual_plans(raw,ledger,funded,cutoffs,cfg,seed)
 jsonlite::write_json(result$plans,file.path(cfg$output_dir,paste0(key,'-plans.json')),
   auto_unbox=TRUE,digits=NA,null='null')
 rows[[key]]<-result$rows;actions[[key]]<-result$actions
 metadata[[key]]<-list(cutoffs=cutoffs,bundle=bundle_path,candidates=ledger_path)
 message(key,': ',length(result$plans),' residual plans frozen')
}
readr::write_csv(dplyr::bind_rows(rows),file.path(cfg$output_dir,'predictions.csv'))
readr::write_csv(dplyr::bind_rows(actions),file.path(cfg$output_dir,'actions.csv'))
stopifnot(identical(hashes,vapply(code,digest::digest,character(1),file=TRUE,algo='sha256')))
temporal$verify_implementation_closure(pathlib$Path(cfg$repository_root),closure)
files<-list.files(cfg$output_dir,full.names=TRUE)
stopifnot(identical(input_hashes,vapply(inputs,digest::digest,character(1),file=TRUE,algo='sha256')))
for(name in names(refill$files))stopifnot(digest::digest(file=file.path(cfg$refill_dir,name),algo='sha256')==refill$files[[name]])
jsonlite::write_json(list(config=cfg,metadata=metadata,input_binding=refill$input_binding,
 python_implementation=closure,implementation=as.list(hashes),historical_admission=FALSE,labels_loaded=FALSE,
 input_hashes=as.list(setNames(input_hashes,inputs)),
 files=as.list(setNames(vapply(files,digest::digest,character(1),file=TRUE,algo='sha256'),basename(files)))),
 file.path(cfg$output_dir,'prediction-freeze.json'),auto_unbox=TRUE,digits=NA,pretty=TRUE)
