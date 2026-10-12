suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
root<-normalizePath('.');out<-file.path(root,'results/fm16-three-issues-20261012');s<-readRDS(file.path(out,'stage.rds'))
# Expert judgments fixed from evidence display, not outcome-ranked or tuned.
# Native confidence reflects shared missing opponent/cohort/lineup/stability evidence.
conflicts<-c('26098:2','26098:5','26098:138')
for(wd in list.files(out,pattern='^review-[0-9]+$',full.names=TRUE)) {
 inputs<-fromJSON(file.path(wd,'input.json'),simplifyVector=FALSE);rows<-list()
 for(p in inputs) {
  id<-p$fixture_id;pp<-s$packets[[id]];n<-pp$native_rates
  reliability<-paste0(pp$competition,': ',paste(n$role,': n=',n$matches,', recent=',n$recent_matches,', ESS=',round(n$ess,1),collapse='; '),'. Opponent-strength, roster/cohort continuity and window stability are unverified; no affirmative adequate-confidence evidence.')
  avail<-pp$market_available;books<-pp$euro_companies
  sufficient<-avail&&books>=3L
  consistent<-sufficient&&!id%in%conflicts
  if(!avail)market_reason<-paste('No validated joint reference:',pp$market_error)else {
   er<-max(abs(pp$market_ordinary$residual))*100;ar<-max(abs(pp$market_asian$residual))*100
   market_reason<-paste0(books,' Euro firms; AH ',paste(pp$asian$handicap,collapse=','),'; OU-based mean ',round(pp$market_parameters$total_mean,3),'; max Euro residual ',round(er,2),' pp, AH residual ',round(ar,2),' pp. ')
   market_reason<-paste0(market_reason,if(books==4L)'Complete specified basket; quotation evidence inspected for compatible direction/scale.'else if(books==3L)'Partial three-firm basket, diagnostic sufficiency accepted from cross-firm and AH/OU agreement; not complete.'else 'One/two-firm evidence is retained as insufficient in this conservative ROOT review, rather than declaring broad consensus.')
   if(id%in%conflicts)market_reason<-paste0(market_reason,' ROOT rejects cross-channel consistency: ',if(id=='26098:138')'AH away +0.5 strength exceeds near-balanced Euro view; residual compromise masks channel disagreement.'else 'Extreme favorite Euro probability is not reproduced by the OU-constrained score model; relevant uncertainty remains despite same favored direction.')
  }
  rows[[length(rows)+1L]]<-list(fixture_id=id,cutoff_utc=pp$cutoff_utc,confidence='uncertain',market_sufficient=sufficient,market_consistent=consistent,reason=paste(reliability,market_reason),counterevidence='ROOT retrospective expert judgment; systematic missing-variable uncertainty is a cohort-level limitation, not a calibrated confidence score. Partial coverage and old prior quotes can miss new information. No outcome-based threshold tuning.',evidence_ids=if(avail)c('native_rates','confidence_limitations','market_ordinary','market_asian')else c('native_rates','confidence_limitations'))
 }
 write_json(rows,file.path(wd,'reviews.json'),auto_unbox=TRUE,pretty=TRUE,digits=17)
 write_json(list(author='ROOT_CODEX',input_sha256=digest::digest(file=file.path(wd,'input.json'),algo='sha256'),review_sha256=digest::digest(file=file.path(wd,'reviews.json'),algo='sha256'),intended_use='POSTHOC_HISTORICAL_DIAGNOSTIC',target_labels_used_for_decisions=FALSE,root_prior_outcome_knowledge=TRUE,confidence_basis='shared missing opponent/cohort/lineup/stability evidence; not market disagreement',market_conflict_cases=conflicts),file.path(wd,'root-receipt.json'),auto_unbox=TRUE,pretty=TRUE)
}
