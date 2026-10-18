# Rscript r/evaluate_margin_combination_20261018.R ROOT
# Read-only frozen forecasts; post-settlement scoring is a separate implementation.
args <- commandArgs(TRUE);stopifnot(length(args)==1L)
root <- normalizePath(args[1],mustWork=TRUE);setwd(root)
suppressPackageStartupMessages(library(tidyverse))
out <- file.path(root,'results/margin-combination-study-20261018-v2')
library(beidan,lib.loc=file.path(root,'results/margin-combination-study-20261018/library'))
producer <- jsonlite::fromJSON(file.path(out,'manifest.json'))
sources <- producer$sources
sources$client <- file.path(out,'producer-source.R')
hashes <- map_chr(sources,~digest::digest(file=.x,algo='sha256'))
 x <- readRDS(file.path(out,'frozen-study.rds'))
 stopifnot(identical(x$source_hashes,hashes),!x$prospective_admission)
 replay <- jsonlite::fromJSON(file.path(out,'replay.json'))
 stopifnot(replay$status=='FULL_IDENTICAL_REPLAY',replay$sha256==digest::digest(file=file.path(out,'frozen-study.rds'),algo='sha256'))
 rows <- groups <- scores <- windows <- missing_labels <- list()
 for(z in x$rounds) {
  row <- z$label_manifest;lp <- file.path(root,row$label_snapshot)
  stopifnot(digest::digest(file=lp,algo='sha256')==row$label_sha256)
  r <- if(row$label_kind=='json')jsonlite::fromJSON(lp)else readRDS(lp)$settlement
  a <- as_tibble(r$fixture_results) |> transmute(issue_id=as.character(issue_id),fixture_id,
    outcome,settled_sp=as.numeric(settled_sp),label_available_at=lubridate::ymd_hms(result_available_at,tz='UTC'),source_url)
  as_of <- lubridate::ymd_hms(r$as_of_utc,tz='UTC')
  stopifnot(!anyDuplicated(a$fixture_id),all(a$label_available_at>z$cutoff$cutoff_utc),
    all(a$label_available_at<=as_of))
  for(model in names(z$outputs)) {
   o <- z$outputs[[model]];q <- o$decision$probabilities;s <- o$selection
   missing_labels[[paste(z$index,model)]] <- q |> distinct(fixture_id) |>
     anti_join(a |> select(fixture_id),by='fixture_id') |>
     mutate(index=z$index,model,reason='Absent from immutable settlement snapshot')
   score <- beidan:::DcAccuracyDiagnostic(q |> semi_join(a,by='fixture_id') |> mutate(model=.env$model),
     a |> semi_join(q,by='fixture_id') |> transmute(fixture_id,actual_outcome=outcome))$scores
   scores[[paste(z$index,model)]] <- score |> mutate(index=z$index,cutoff_utc=z$cutoff$cutoff_utc,
     issue_id=z$cutoff$issue_id)
   for(policy in unique(s$purchases$policy)) {
    tickets <- s$purchases |> filter(.data$policy==.env$policy)
    tokens <- strsplit(tickets$ticket_id,'|',fixed=TRUE)
    legs <- tibble(ticket_id=rep(tickets$ticket_id,each=7L),fixture_id=sub(':[^:]+$','',unlist(tokens)),
      outcome=c('W','D','L')[as.integer(sub('.*:','',unlist(tokens)))]) |> distinct()
    check <- legs |> left_join(a |> select(fixture_id,actual=outcome),by='fixture_id',relationship='many-to-one') |>
      group_by(ticket_id) |> summarise(known=sum(!is.na(actual)),misses=sum(!is.na(actual)&outcome!=actual),.groups='drop')
    scored <- tickets |> left_join(check,by='ticket_id',relationship='many-to-one')
    gs <- scored |> group_by(group_id) |> summarise(hit=any(known==7L&misses==0L),
      pending=any(known<7L&misses==0L),.groups='drop')
    cash <- parlay_settle_plan(list(constants=list(unit_cny=2,payout_factor=.65,n_legs=7L),
      issue_id=z$cutoff$issue_id,funded=tickets |> select(ticket_id,group_id),ticket_legs=legs),
      a |> mutate(status='settled') |>
        select(issue_id,fixture_id,outcome,settled_sp,label_available_at,status,source_url),
      as_of=as_of)$ticket_returns
    complete <- all(!cash$status%in%c('PENDING','SPECIAL'))
    payout <- if(complete)sum(cash$payout_cny)else NA_real_
    trace <- s$trace |> filter(.data$policy==.env$policy)
    union <- beidan:::.parlay_ranked_union_coverage(tickets$ticket_id,legs,q)
    stopifnot(abs(union-tail(trace$cumulative_coverage,1))<1e-9,nrow(tickets)==1000L,nrow(gs)==8L)
    rows[[paste(z$index,model,policy)]] <- tibble(index=z$index,dataset=z$dataset,sheet=z$sheet,
      model,policy,cost_cny=2000,hit_groups=sum(gs$hit),pending_groups=sum(gs$pending),
      any_hit=if(any(gs$hit))TRUE else if(any(gs$pending))NA else FALSE,model_any_hit=union,model_expected_wins=sum(tickets$probability),
      payout_cny=payout,net_cny=payout-2000,monetary_complete=complete)
    groups[[paste(z$index,model,policy)]] <- gs |> mutate(index=z$index,model,policy)
    windows[[paste(z$index,model,policy)]] <- trace |> mutate(index=z$index,model)
   }
  }
 }
 results <- bind_rows(rows);ss <- bind_rows(scores)
 # Repeated fixture/cutoff contexts are not independent. Primary metrics use earliest cutoff per fixture.
 unique_scores <- ss |> arrange(cutoff_utc,index) |> distinct(fixture_id,model,.keep_all=TRUE)
 metrics <- unique_scores |> group_by(model) |> summarise(n=n(),hits1=sum(top1),hits2=sum(top2),
   top1=mean(top1),top2=mean(top2),brier=mean(brier),logloss=mean(logloss),.groups='drop')
 issues <- unique_scores |> group_by(issue_id,model) |> summarise(n=n(),hits1=sum(top1),hits2=sum(top2),
   brier=mean(brier),logloss=mean(logloss),.groups='drop')
 summary <- results |> group_by(model,policy) |> summarise(rounds=n(),hit_rounds=sum(any_hit%in%TRUE),pending_rounds=sum(is.na(any_hit)),
   hit_rounds_upper=sum(any_hit%in%TRUE)+sum(is.na(any_hit)),
   hit_groups=sum(hit_groups),pending_groups=sum(pending_groups),cost_cny=sum(cost_cny),model_any_hit=mean(model_any_hit),
   cash_complete_rounds=sum(monetary_complete),.groups='drop')
 tables <- list(rounds=results,summary=summary,groups=bind_rows(groups),windows=bind_rows(windows),
   scores=ss,unique_scores=unique_scores,metrics=metrics,issues=issues,missing_labels=bind_rows(missing_labels))
 for(name in names(tables))write_csv(tables[[name]],file.path(out,paste0(name,'.csv')))
 stopifnot(nrow(results)==84L,nrow(metrics)==3L,all(results$pending_groups>=0L))
 jsonlite::write_json(list(frozen_sha256=replay$sha256,source_hashes=as.list(hashes),
   evaluator_sha256=digest::digest(file='r/evaluate_margin_combination_20261018.R',algo='sha256'),
   outputs=as.list(map_chr(names(tables),~digest::digest(file=file.path(out,paste0(.x,'.csv')),algo='sha256')) |>
     set_names(names(tables))),independent_kernel_union_agreement=TRUE),file.path(out,'evaluation.json'),pretty=TRUE,auto_unbox=TRUE)
 print(metrics,width=Inf);print(summary,width=Inf)
