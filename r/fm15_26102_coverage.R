# Correct fixed-basket completeness without changing any pre-label forecast.
# The original market clients/artifacts are inventoried execution evidence only.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE);out<-file.path(root,'results/fm15-26102-20261012')
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm15-version-20261012/library'))
mm<-fromJSON(file.path(out,'market-manifest.json'));md<-fromJSON(file.path(out,'market-diagnostic-manifest.json'));fm<-fromJSON(file.path(out,'manifest.json'))
market<-readRDS(file.path(out,mm$stage_file));diagnostic<-readRDS(file.path(out,md$diagnostic_file))
stopifnot(beidan:::.score_margin_hash(market)==mm$object_hash,beidan:::.score_margin_hash(diagnostic)==md$object_hash)
expected<-c('281','115','82','432');rows<-list()
for(id in names(market$selected)) {
  q<-market$selected[[id]];basket<-sort(q$euro$company_id)
  channels<-all(map_int(q,nrow)>0L);complete<-channels&&setequal(basket,expected)
  rows[[id]]<-tibble(fixture_id=id,market_state=if(complete)'COMPLETE'else'INCOMPLETE',channels_complete=channels,euro_company_count=length(basket),missing_euro_companies=paste(setdiff(expected,basket),collapse=','),reason=if(!setequal(basket,expected))'INCOMPLETE_FIXED_EURO_BASKET'else market$ledger$reason[match(id,market$ledger$fixture_id)])
}
coverage<-bind_rows(rows);eligible<-coverage$fixture_id[coverage$market_state=='COMPLETE']
stopifnot(nrow(coverage)==86L,sum(coverage$channels_complete)==71L,length(eligible)==43L)
references<-diagnostic$references[intersect(names(diagnostic$references),eligible)]
stopifnot(length(references)==43L)
inputs<-tibble(path=c(paste0('results/fm15-26102-20261012/',mm$stage_file),paste0('results/fm15-26102-20261012/',md$diagnostic_file),'results/fm15-26102-20261012/manifest.json','r/fm15_26102_coverage.R'),sha256=map_chr(file.path(root,c(paste0('results/fm15-26102-20261012/',mm$stage_file),paste0('results/fm15-26102-20261012/',md$diagnostic_file),'results/fm15-26102-20261012/manifest.json','r/fm15_26102_coverage.R')),~digest::digest(file=.x,algo='sha256')))
corrected<-list(coverage=coverage,market_references=references,expected_euro_companies=expected,forecast_sha256=fm$sha256,inputs=inputs,correction='POST_LABEL_COVERAGE_ONLY; NO_NEW_PROBABILITIES_OR_QUALITATIVE_JUDGEMENTS',retired_execution_clients=c('r/fm15_26102_market.R','r/fm15_26102_market_diagnostic.R'))
id<-beidan:::.score_margin_hash(corrected);p<-file.path(out,paste0('corrected-coverage-',substr(id,1,12),'.rds'))
if(file.exists(p))stopifnot(identical(readRDS(p),corrected))else saveRDS(corrected,p)
write_json(list(coverage_file=basename(p),object_hash=id,sha256=digest::digest(file=p,algo='sha256'),forecast_sha256=fm$sha256,probabilities_changed=FALSE,generated_at_utc=format(Sys.time(),'%Y-%m-%dT%H:%M:%SZ',tz='UTC')),file.path(out,'coverage-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
write_csv(coverage,file.path(out,'coverage-corrected.csv'));print(count(coverage,market_state,channels_complete))
