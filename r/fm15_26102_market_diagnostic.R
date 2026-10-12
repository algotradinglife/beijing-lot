# Independent market-DC reference only: never adopted by the FM native model.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE);out<-file.path(root,'results/fm15-26102-20261012');impl<-file.path(out,'implementation')
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm15-version-20261012/library'))
reticulate::use_python(file.path(root,'.venv/bin/python'),required=TRUE);reticulate::import('sys',convert=FALSE)$path$insert(0L,file.path(impl,'packages/beidan/inst/python'))
shared<-reticulate::import('beidan_backend.temporal_learning',convert=FALSE);backend<-reticulate::import('beidan_backend.fundamental_probability',convert=FALSE)
nm<-fromJSON(file.path(out,'native-manifest.json'));mm<-fromJSON(file.path(out,'market-manifest.json'));native<-readRDS(file.path(out,nm$native_file));market<-readRDS(file.path(out,mm$stage_file))
stopifnot(beidan:::.score_margin_hash(native)==nm$object_hash,beidan:::.score_margin_hash(market)==mm$object_hash)
policy<-list(euro_weight=1,asian_weight=1,lambda_floor=.01,tail_tolerance=1e-10,max_quote_age_hours=48)
references<-ledger<-list()
for(id in names(native$entries)) {
  e<-native$entries[[id]];f<-e$fixture;p<-market$packets[[id]];q<-market$selected[[id]]
  result<-tryCatch({
    if(market$ledger$market_state[match(id,market$ledger$fixture_id)]!='COMPLETE'||is.null(p$total_constraint$lambda_total))stop('INCOMPLETE_OR_UNSUPPORTED_MARKET')
    fixture<-tibble(fixture_id=id,issue_id='26102',home=f$home,away=f$away);cutoff<-list(issue_id='26102',cutoff_utc=f$cutoff_utc)
    euro<-q$euro |> select(company_id,fixture_id,quote_at,odds_home,odds_draw,odds_away)
    asian<-q$asian |> select(company_id,fixture_id,quote_at,handicap,home_decimal,away_decimal)
    total_mean<-p$total_constraint$lambda_total
    bindings<-list(dc_market_input=beidan:::.score_margin_hash(list(euro=euro,asian=asian,total_mean=total_mean,rho=-.1,policy=policy,fixture=fixture,cutoff=cutoff)),direction_implementation=beidan:::.score_margin_code(impl),market_artifact=mm$object_hash,loaded_OU_implementation=market$loaded_OU_implementation,client=digest::digest(file=file.path(root,'r/fm15_26102_market_diagnostic.R'),algo='sha256'))
    rows<-list()
    for(kind in c('euro','asian','totals')) {
      qq<-if(kind=='euro')euro else if(kind=='asian')asian else q$totals
      for(j in seq_len(nrow(qq))) {
        qt<-format(qq$quote_at[j],'%Y-%m-%dT%H:%M:%SZ',tz='UTC');qid<-paste0(kind,'-',qq$company_id[j])
        rows[[length(rows)+1L]]<-list(evidence_id=qid,fixture_id=id,source_hash=beidan:::.score_margin_hash(qq[j,]),row_key=qid,issue_code='QUOTE_PROXY',issue_year=as.integer(substr(qt,1,4)),label_available_ts=qt,data_available_ts=qt)
      }
    }
    ctx<-backend$build_adjustment_evidence_context(rows,as.list(fixture),shared$Cutoff$decision_epoch('26102',p$cutoff_utc),bindings,shared$AvailabilityPolicy$historical_proxy('INDEPENDENT_MARKET_REFERENCE_DIAGNOSTIC_ONLY'),'HISTORICAL_DIAGNOSTIC',impl)
    model<-project_dc_market_handicap(euro,asian,total_mean,-.1,policy,ctx,fixture,cutoff,impl,'HISTORICAL_DIAGNOSTIC')
    list(model=model,evidence_rows=rows,bindings=bindings,fixture=fixture,cutoff=cutoff,total_mean=total_mean,error='')
  },error=function(e)list(error=conditionMessage(e)))
  if(nzchar(result$error))ledger[[id]]<-tibble(fixture_id=id,state='UNAVAILABLE',reason=result$error)else {
    references[[id]]<-result;ledger[[id]]<-tibble(fixture_id=id,state='DIAGNOSTIC_ONLY_NOT_ADOPTED',reason='')
  }
}
batch<-list(issue_id='26102',policy=policy,references=references,ledger=bind_rows(ledger),native_hash=nm$object_hash,market_hash=mm$object_hash)
id<-beidan:::.score_margin_hash(batch);path<-file.path(out,paste0('market-diagnostic-',substr(id,1,12),'.rds'))
if(file.exists(path))stopifnot(identical(readRDS(path),batch))else saveRDS(batch,path)
write_json(list(diagnostic_file=basename(path),object_hash=id,sha256=digest::digest(file=path,algo='sha256')),file.path(out,'market-diagnostic-manifest.json'),auto_unbox=TRUE,pretty=TRUE)
write_csv(batch$ledger,file.path(out,'market-diagnostic-ledger.csv'));print(count(batch$ledger,state))
