#!/usr/bin/env Rscript
# Thin offline entry point: config contains explicit frozen studies and output.
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==1)
config <- jsonlite::fromJSON(args[1])
library(dplyr)
source('r/n7_rank_diagnostic.R')
source('r/n7_rank_return.R')
reticulate::use_python(config$python,required=TRUE)
reader <- reticulate::import('src.n7_rank_diagnostic',convert=TRUE)
stopifnot(!dir.exists(config$output_dir))
dir.create(config$output_dir,recursive=TRUE)
parts <- list(); prefixes <- list(); bindings <- list(); k <- 0L
for (j in seq_len(nrow(config$studies))) {
  study <- config$studies$path[j]
  frozen <- jsonlite::fromJSON(file.path(study,'plans-frozen.json'))
  bindings[[j]] <- list(study=study,seal=frozen$seal,
    freeze_sha256=digest::digest(file=file.path(study,'plans-frozen.json'),algo='sha256'),
    evaluation_sha256=digest::digest(file=file.path(study,'evaluation-receipt.json'),algo='sha256'))
  for (issue in frozen$receipt$issues) {
    x <- jsonlite::fromJSON(reader$load_rank_issue(study,issue))
    r <- n7_rank_diagnostic(x,2,.65,c(.15,.2,.25,.5))
    z <- n7_rank_return_prefixes(x$curves,r,config$depths,2)
    r$cohort <- z$cohort <- config$studies$cohort[j]
    k <- k+1L; parts[[k]] <- r; prefixes[[k]] <- z
    if (k %% 10 == 0) message('Completed ',k,' issues')
  }
}
ranks <- bind_rows(parts); prefixes <- bind_rows(prefixes)
stopifnot(n_distinct(ranks$issue)==config$expected_issues,
  nrow(ranks)==config$expected_issues*24,
  !anyDuplicated(ranks[c('issue','sleeve_id')]))
summary <- n7_rank_return_summary(prefixes)
readr::write_csv(ranks,file.path(config$output_dir,'ranks.csv'))
readr::write_csv(prefixes,file.path(config$output_dir,'prefixes.csv'))
readr::write_csv(summary,file.path(config$output_dir,'summary.csv'))
files <- c('ranks.csv','prefixes.csv','summary.csv')
hashes <- setNames(vapply(file.path(config$output_dir,files),digest::digest,
  character(1),algo='sha256',file=TRUE),files)
code <- c('r/n7_rank_diagnostic.R','r/n7_rank_return.R','src/n7_rank_diagnostic.py',
  'scripts/diagnose_n7_rank_return.R')
jsonlite::write_json(list(evidence_class='POST_SETTLEMENT_DIAGNOSTIC',
  historical_admission=FALSE,issues=k,candidates=nrow(ranks),unit_cny=2,payout_factor=.65,
  sources=bindings,config=config,outputs=as.list(hashes),
  implementation=as.list(setNames(vapply(code,digest::digest,character(1),
    algo='sha256',file=TRUE),code))),file.path(config$output_dir,'receipt.json'),
  auto_unbox=TRUE,pretty=TRUE)
