# Replay the combined account against independently verified parent ledgers.
# Usage: Rscript --vanilla scripts/check_eight_strategy_combined.R REPORT_DIR
suppressPackageStartupMessages({library(jsonlite);library(digest);library(dplyr);library(readr)})
args<-commandArgs(TRUE);stopifnot(length(args)==1)
directory<-args[1];receipt<-fromJSON(file.path(directory,'receipt.json'));cfg<-receipt$config
checker_file<-file.path(cfg$repository_root,'scripts/check_eight_strategy_combined.R')
checker_sha256<-digest(file=checker_file,algo='sha256')
stopifnot(digest(file=cfg$source_scope$path,algo='sha256')==cfg$source_scope$sha256)
source_scope<-fromJSON(cfg$source_scope$path)
stopifnot(setequal(source_scope$prepared_issues,cfg$expected_issues))
for(n in names(receipt$files))stopifnot(digest(file=file.path(directory,n),algo='sha256')==receipt$files[[n]])
parents<-input_counts<-unavailable<-requested<-parent_groups<-list();joint_bindings<-character()
for(i in seq_len(nrow(cfg$reports))) {
 e<-cfg$reports[i,]
 stopifnot(digest(file=e$receipt,algo='sha256')==e$sha256,
  digest(file=e$proof,algo='sha256')==e$proof_sha256)
 r<-fromJSON(e$receipt);p<-fromJSON(e$proof)
 stopifnot(p$status=='PASS',p$report_receipt_sha256==e$sha256,p$issues==length(r$issues))
 joint_bindings[r$config$joint$receipt]<-r$config$joint$sha256
 requested[[i]]<-r$requested_issues
 path<-file.path(dirname(e$receipt),'unavailable-issues.csv')
 stopifnot(digest(file=path,algo='sha256')==r$files[['unavailable-issues.csv']])
 unavailable[[i]]<-read_csv(path,col_types=cols(issue='c',provider_id='c',slot='d',handicap='d',status='c',actual_direction='c',spf_sp='d'),show_col_types=FALSE) |> mutate(phase=e$phase)
 path<-file.path(dirname(e$receipt),'rows.csv')
 stopifnot(digest(file=path,algo='sha256')==r$files[['rows.csv']])
 parents[[i]]<-read_csv(path,col_types=cols(issue='c'),show_col_types=FALSE) |>
  mutate(stage=e$phase,model='RECORDED_MARKET_VERSIONS')
 path<-file.path(dirname(e$receipt),'groups.csv')
 stopifnot(digest(file=path,algo='sha256')==r$files[['groups.csv']])
 parent_groups[[i]]<-read_csv(path,col_types=cols(issue='c'),show_col_types=FALSE) |> mutate(phase=e$phase)
 path<-file.path(dirname(e$receipt),'input-counts.csv')
 stopifnot(digest(file=path,algo='sha256')==r$files[['input-counts.csv']])
 input_counts[[i]]<-read_csv(path,col_types=cols(issue='c'),show_col_types=FALSE) |> mutate(phase=e$phase)
}
expected_groups<-bind_rows(parent_groups)
reported_groups<-read_csv(file.path(directory,'groups.csv'),col_types=cols(issue='c'),show_col_types=FALSE)
stopifnot(!anyDuplicated(reported_groups[c('issue','policy','sleeve_id')]),
 isTRUE(all.equal(as.data.frame(arrange(expected_groups,issue,policy,sleeve_id)),
 as.data.frame(arrange(reported_groups,issue,policy,sleeve_id)),check.attributes=FALSE,tolerance=1e-12)))
expected<-bind_rows(parents)
actual<-read_csv(file.path(directory,'rows.csv'),col_types=cols(issue='c'),show_col_types=FALSE)
stopifnot(!anyDuplicated(expected[c('issue','policy')]),
 identical(as.data.frame(arrange(expected,issue,policy)),as.data.frame(arrange(actual,issue,policy))),
 setequal(actual$issue,receipt$issues))
requested<-unlist(requested,use.names=FALSE);unavailable<-bind_rows(unavailable)
stopifnot(!anyDuplicated(requested),setequal(requested,cfg$expected_issues),
 identical(sort(requested),receipt$requested_issues),!any(unavailable$issue %in% actual$issue),
 setequal(c(unique(actual$issue),unique(unavailable$issue)),requested))
reported_unavailable<-read_csv(file.path(directory,'unavailable-issues.csv'),
 col_types=cols(issue='c',provider_id='c',slot='d',handicap='d',status='c',actual_direction='c',spf_sp='d'),show_col_types=FALSE)
stopifnot(isTRUE(all.equal(as.data.frame(arrange(unavailable,issue,slot)),
 as.data.frame(arrange(reported_unavailable,issue,slot)),check.attributes=FALSE,tolerance=0)))
reported_counts<-read_csv(file.path(directory,'input-counts.csv'),col_types=cols(issue='c'),show_col_types=FALSE)
expected_counts<-bind_rows(input_counts)
stopifnot(!anyDuplicated(reported_counts$issue),setequal(reported_counts$issue,receipt$issues),
 identical(as.data.frame(arrange(reported_counts,issue)),as.data.frame(arrange(expected_counts,issue))))
policies<-c('JOINT','DEPTH_OPEN','U4','CONFIDENCE','TOP2_DIVERSE','HARD1','HARD2','WITHIN0')
stopifnot(setequal(actual$policy,policies),nrow(actual)==length(receipt$issues)*8L)
helper<-file.path(cfg$repository_root,'r/n7_purchase_cohort_audit.R')
helper_sha256<-digest(file=helper,algo='sha256');source(helper)
for(kind in c('summary.csv','block-summary.csv')) {
 summary<-read_csv(file.path(directory,kind),col_types=cols(funding_stop_issue='c'),show_col_types=FALSE)
 required_scopes<-c('ALL',if(kind=='summary.csv')unique(actual$stage) else
  unique(sprintf('BLOCK_%02d',(seq_along(receipt$issues)-1L)%/%100L+1L)))
 stopifnot(setequal(summary$evaluation,required_scopes))
 for(evaluation in unique(summary$evaluation)) {
  ids<-if(evaluation=='ALL')receipt$issues else if(kind=='summary.csv')
   receipt$issues[receipt$issues %in% actual$issue[actual$stage==evaluation]] else receipt$issues[
    sprintf('BLOCK_%02d',(seq_along(receipt$issues)-1L)%/%100L+1L)==evaluation]
  stopifnot(length(ids)>0)
  observed<-summary[summary$evaluation==evaluation,];observed$evaluation<-'ALL'
  duplicate<-observed;duplicate$evaluation<-'ADDITIONAL'
  n7_purchase_cohort_audit(actual[actual$issue %in% ids,],bind_rows(observed,duplicate),
   ids,character(),policies,1024,100000)
 }
}
detail_helper<-file.path(cfg$repository_root,'r/eight_strategy_detail_audit.R')
detail_sha256<-digest(file=detail_helper,algo='sha256');source(detail_helper)
scopes<-list(ALL=receipt$issues)
for(s in unique(actual$stage))scopes[[s]]<-receipt$issues[receipt$issues %in% actual$issue[actual$stage==s]]
tables<-setNames(lapply(c('curves','trimmed','streaks','complementarity','paired'),
 function(n)read_csv(file.path(directory,paste0(n,'.csv')),
  col_types=if(n=='curves')cols(issue='c',funding_stop_issue='c') else cols(),show_col_types=FALSE)),
 c('curves','trimmed','streaks','complementarity','paired'))
eight_strategy_detail_audit(actual,scopes,tables,100000,'JOINT')
stopifnot(is.list(cfg$legacy))
for(n in c('receipt','results','payout_proof','selection_proof','joint_replication')) {
 e<-cfg$legacy[[n]];stopifnot(digest(file=e$path,algo='sha256')==e$sha256)
}
replication<-fromJSON(cfg$legacy$joint_replication$path)
stopifnot(replication$status=='PASS',length(replication$inputs)>0)
for(path in names(replication$inputs))stopifnot(digest(file=path,algo='sha256')==replication$inputs[[path]])
shared<-intersect(names(joint_bindings),names(replication$inputs))
stopifnot(length(shared)>0,all(joint_bindings[shared]==unlist(replication$inputs[shared])))
old<-fromJSON(cfg$legacy$results$path)
old_payout<-fromJSON(cfg$legacy$payout_proof$path)
old_selection<-fromJSON(cfg$legacy$selection_proof$path)
stopifnot(old_payout$status=='PASS',old_selection$status=='PASS',
 old_payout$results_sha256==cfg$legacy$results$sha256,
 old_selection$frozen_sha256==old_payout$frozen_sha256)
legacy<-read_csv(file.path(directory,'legacy-summary.csv'),col_types=cols(funding_stop_issue='c'),show_col_types=FALSE)
stopifnot(setequal(legacy$evaluation,'ALL'))
duplicate<-legacy;duplicate$evaluation<-'ADDITIONAL'
invisible(n7_purchase_cohort_audit(old$rows,bind_rows(legacy,duplicate),old$issue_order,
 character(),unique(old$rows$policy),1024,100000))
stopifnot(digest(file=checker_file,algo='sha256')==checker_sha256,
 digest(file=helper,algo='sha256')==helper_sha256,
 digest(file=detail_helper,algo='sha256')==detail_sha256)
cat(toJSON(list(status='PASS',issues=length(receipt$issues),
 checker_sha256=checker_sha256,
 report_receipt_sha256=digest(file=file.path(directory,'receipt.json'),algo='sha256'),
 accounting_helper_sha256=helper_sha256,
 detail_helper_sha256=detail_sha256,
 scope='Exact parent period ledgers and independent continuous, phase and block funding accounts'),auto_unbox=TRUE),'\n')
