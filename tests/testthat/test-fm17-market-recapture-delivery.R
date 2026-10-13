root<-normalizePath(Sys.getenv('FM17_MARKET_ROOT',getwd()))
out<-file.path(root,'results/fm17-market-recapture-20261013')

test_that('published tables are typed, hashed and reconcile exact cutoff scope',{
 p<-jsonlite::fromJSON(file.path(out,'publication.json'))
 expect_identical(p$publication$version,'20261013-v4');expect_identical(p$idempotent_republish$status,'unchanged')
 expect_false(p$receipt$historical_admitted)
 expect_equal(length(p$receipt$admission_receipts),117L)
 for(id in names(p$receipt$admission_receipts)) {
  r<-p$receipt$admission_receipts[[id]]
  expect_equal(lubridate::ymd_hms(r$cutoff$cutoff_utc,tz='UTC'),lubridate::ymd_hms(p$receipt$cutoffs[[id]],tz='UTC'))
  if(!is.null(r$shared$implementation$files)) {
   expect_true(all(unlist(r$shared$implementation$files)==unlist(p$receipt$admission_implementation_hashes[names(r$shared$implementation$files)])))
   expect_lt(as.numeric(lubridate::ymd_hms(r$shared$maximum_source_time,tz='UTC')),as.numeric(lubridate::ymd_hms(r$cutoff$cutoff_utc,tz='UTC')))
  }
 }
 expected<-readRDS(file.path(out,'final-audit.rds'))
 tables<-list()
 for(k in c('history','latest','coverage','provenance')) {
  tables[[k]]<-beidan::read_dataset(p$publication$dataset,k,version=p$publication$version,root=p$publication$root)
  expect_s3_class(tables[[k]],'tbl_df')
  if(k!='provenance') {
   expect_equal(nrow(tables[[k]]),nrow(expected[[k]]))
   expect_identical(names(tables[[k]]),names(expected[[k]]))
   for(col in names(expected[[k]]))expect_equal(tables[[k]][[col]],expected[[k]][[col]])
  }
 }
 h<-tables$history;l<-tables$latest;c<-tables$coverage;v<-tables$provenance
 expect_equal(nrow(c),351L);expect_equal(nrow(v),371L)
 expect_equal(length(unique(c$fixture_id)),117L)
 expect_false(anyDuplicated(c[c('fixture_id','market')])>0)
 expect_false(anyDuplicated(l[c('fixture_id','market','company_id')])>0)
 expect_false(anyDuplicated(v[c('fixture_id','market','source_url')])>0)
 expect_true(all(is.finite(l$age_hours)&l$age_hours>=0))
 expect_true(all(l$qualified==(l$fresh&l$supported&l$identity_status %in% c('EXACT','EXACT_IDS'))))
 expect_true(all(l$fresh==(l$age_hours<=48)))
 q<-h |> dplyr::left_join(dplyr::distinct(c,fixture_id,cutoff_utc),by='fixture_id',relationship='many-to-one')
 expect_true(all(q$quote_at[q$prior]<q$cutoff_utc[q$prior]))
 counts<-h |> dplyr::group_by(fixture_id,market) |> dplyr::summarise(n=sum(prior),.groups='drop')
 z<-c |> dplyr::left_join(counts,by=c('fixture_id','market'),relationship='one-to-one')
 expect_equal(z$prior_rows,tidyr::replace_na(z$n,0L))
 expect_true(all(v$availability=='HISTORICAL_QUOTE_PROXY'))
 expect_true(all(v$collected_at>v$cutoff_utc))
 expect_true(all(!is.na(v$request_error)))
 # Missing raw response is allowed only for an explicitly recorded request failure.
 expect_true(all(!is.na(v$response_sha256)|nzchar(v$request_error)))
})

test_that('coverage and whole-capture source choice match declared evidence',{
 a<-readRDS(file.path(out,'selected-audit.rds'));b<-readRDS(file.path(out,'final-audit.rds'))
 e<-jsonlite::fromJSON(file.path(out,'augmentation.json'))
 expect_equal(digest::digest(file=file.path(out,'final-audit.rds'),algo='sha256'),e$final_sha256)
 fa<-a$coverage |> dplyr::group_by(fixture_id) |> dplyr::summarise(full=all(qualified_companies>0),prior=all(prior_rows>0),.groups='drop')
 fb<-b$coverage |> dplyr::group_by(fixture_id) |> dplyr::summarise(full=all(qualified_companies>0),prior=all(prior_rows>0),.groups='drop')
 expect_equal(sum(fa$full),41L);expect_equal(sum(fb$full),43L);expect_equal(sum(fb$prior),109L)
 extra<-b$latest |> dplyr::filter(company_id=='3',market!='euro')
 expect_equal(nrow(extra),4L);expect_true(all(extra$qualified))
 expect_setequal(unique(extra$fixture_id),c('26101:10','26102:20'))
 choice<-readr::read_csv(file.path(out,'source-choice.csv'),show_col_types=FALSE)
 expect_equal(sum(choice$selected=='recaptured'),2L)
 expect_true(all(choice$selected[choice$conflict]=='offline'))
 expect_equal(sum(choice$reason=='NEW_CAPTURE_LESS_COMPLETE_KEEP_PRIOR'),3L)
 r<-jsonlite::fromJSON(file.path(out,'capture-completion.json'))
 expect_equal(r$fixtures,77L);expect_equal(r$market_keys,231L)
 expect_equal(digest::digest(file=file.path(out,'request-ledger.csv'),algo='sha256'),r$ledger_sha256)
 ledger<-readr::read_csv(file.path(out,'request-ledger.csv'),show_col_types=FALSE)
 expect_equal(nrow(ledger),231L);expect_false(anyDuplicated(ledger[c('fixture_id','market')])>0)
 quarantined<-b$coverage |> dplyr::filter(identity_status=='NAME_OR_CLOCK_CONFLICT')
 expect_setequal(quarantined$fixture_id,'26101:48');expect_true(all(quarantined$qualified_companies==0L))
 expect_equal(digest::digest(file=file.path(root,'results/fm17-three-issues-20261013/forecasts.rds'),algo='sha256'),'e537428c0a43f966542c703d3edf6264722c95a7551dbabf7853aa909354e786')
 # Primary publication remains independently readable after later augmentation.
 old<-beidan::read_dataset('fm17_replayed_markets','coverage',version='20261013-v1',root=Sys.getenv('BEIDAN_PARQUET_ROOT'))
 expect_equal(old$qualified_companies,a$coverage$qualified_companies)
})

test_that('QMD summary reports eight incomplete fixtures without sequential masking',{
 q<-readLines(file.path(root,'quarto/fm17_market_recapture_20261013.qmd'))
 line<-q[grepl('caption=.*同截止覆盖',q)]
 expression<-sub('^knitr::kable\\((.*),caption=.*$','\\1',line)
 a<-readRDS(file.path(out,'final-audit.rds'))
 env<-new.env(parent=globalenv())
 env$fixture_coverage<-a$coverage |> dplyr::group_by(fixture_id) |> dplyr::summarise(prior_all=all(prior_rows>0),qualified_all=all(qualified_companies>0),.groups='drop')
 s<-eval(parse(text=expression),env)
 expect_equal(s$fixtures,117L)
 expect_equal(s$prior_histories_complete,109L)
 expect_equal(s$qualified_quote_complete,43L)
 expect_equal(s$incomplete_prior,8L)
})
