# Rscript r/margin_combination_study_20261018.R ROOT freeze|replay|evaluate
# Research orchestration only. Shared package owns learning/selection/contracts.
args <- commandArgs(TRUE);stopifnot(length(args)==2L,args[2]%in%c('freeze','replay','evaluate'))
root <- normalizePath(args[1],mustWork=TRUE);setwd(root);mode <- args[2]
suppressPackageStartupMessages(library(tidyverse))
out <- file.path(root,'results/margin-combination-study-20261018-v2')
library(beidan,lib.loc=file.path(root,'results/margin-combination-study-20261018/library'))
sources <- c(parent='results/fm171-full100-rebase-20261018/frozen-latest-replay.rds',
  training='results/fm171-margin-shape-20261017/forecasts.rds',
  labels='results/fm17-three-issues-20261013/labels.csv',
  observed='results/fm171-draw-calibration-20261017/label-source-observations.csv',
  manifest='results/full100-historical-rounds-20261018/input-manifest.json',
  client='r/margin_combination_study_20261018.R',implementation='packages/beidan/R/margin_shape_research.R')
hashes <- map_chr(sources,~digest::digest(file=.x,algo='sha256'))
if(mode%in%c('freeze','replay')) {
 parent <- readRDS(sources[['parent']]);train <- readRDS(sources[['training']])
 tm <- jsonlite::fromJSON('results/fm171-margin-shape-20261017/manifest.json')
 stopifnot(hashes[['training']]==tm$sha256,parent$model_id=='FM-1.7.1',!parent$prospective_admission)
 labels <- read_csv(sources[['labels']],col_types=cols(.default=col_character()))
 observed <- read_csv(sources[['observed']],col_types=cols(.default=col_character()))
 training_prob <- train$probabilities |> filter(model=='SOURCE_FULL') |>
  select(fixture_id,outcome,probability) |> pivot_wider(names_from=outcome,values_from=probability)
 history <- train$features |> filter(eligible) |>
  select(fixture_id,issue_code=issue_id,data_available_ts=cutoff_utc,entropy,local_mass) |>
  inner_join(training_prob,by='fixture_id',relationship='one-to-one') |>
  inner_join(labels |> select(fixture_id,actual_outcome),by='fixture_id',relationship='one-to-one') |>
  left_join(observed |> rename(issue_code=issue_id,label_available_ts=observed_label_ts),
    by='issue_code',relationship='many-to-one') |> mutate(issue_year=2026L)
 stopifnot(nrow(history)==322L,!anyNA(history),!anyDuplicated(history$fixture_id))
 manifest <- jsonlite::fromJSON(sources[['manifest']]) |> as_tibble()
 all_rounds <- list()
 for(i in 4:10) {
  p <- parent$plans[[i]];row <- manifest[i,];cutoff <- p$cutoff
  forecast_path <- file.path('results',row$dataset,'frozen-probabilities.rds')
  original_path <- file.path('results',row$dataset,'plans.rds')
  stopifnot(digest::digest(file=forecast_path,algo='sha256')==row$frozen_probability_sha256,
    digest::digest(file=original_path,algo='sha256')==row$plans_sha256)
  original <- readRDS(original_path)$plans[[row$sheet_index]]
  forecast <- readRDS(forecast_path);features <- list();max_times <- list()
  for(id in unique(p$probabilities$fixture_id)) {
   e <- parent$grids[[paste(i,id,sep='|')]];grid <- as_tibble(e$grid)
   stopifnot(identical(e$cutoff,cutoff),abs(sum(grid$probability)-1)<1e-9)
   h <- unique(forecast$probabilities$handicap[forecast$probabilities$fixture_id==id])
   stopifnot(length(h)==1L,is.finite(h),h==as.integer(h))
   margins <- grid |> mutate(margin=home_goals-away_goals) |> group_by(margin) |>
    summarise(probability=sum(probability),.groups='drop')
   q <- p$probabilities |> filter(fixture_id==id) |> pivot_wider(names_from=outcome,values_from=probability)
   features[[id]] <- q |> mutate(entropy=-sum(margins$probability[margins$probability>0]*
     log(margins$probability[margins$probability>0])),
     local_mass=sum(margins$probability[abs(margins$margin+h)<=1]),
     mean_margin=sum(margins$margin*margins$probability),handicap=h)
   max_times[[id]] <- forecast$entries[[id]]$base$max_source_available_utc
  }
  f <- bind_rows(features);source_at <- do.call(max,max_times)
  stopifnot(source_at<cutoff$cutoff_utc,!cutoff$issue_id%in%history$issue_code)
  fd <- list(cutoff=cutoff,features=f,receipt=list(cutoff=cutoff,
    feature_hash=rlang::hash(f),max_source_available_utc=source_at))
  fits <- list();probs <- list(RAW=as_tibble(p$probabilities))
  for(model in c('GLOBAL','SHAPE')) {
   policy <- list(prior_issues=sort(unique(history$issue_code)),
     features=if(model=='GLOBAL')character()else c('entropy','local_mass'),
     minimum_ess=100,minimum_class_count=15L,epsilon=1e-8)
   fit <- beidan:::FitMarginShapeCalibration(history,cutoff,policy,as.list(hashes),root,file.path(root,'.venv/bin/python'))
   fits[[model]] <- fit
   probs[[model]] <- beidan:::PredictMarginShapeCalibration(fit,fd)
  }
  outputs <- list()
  for(model in names(probs)) {
   q <- probs[[model]];blocks <- list()
   for(g in 1:8) {
    fx <- sort(original$legs$fixture_id[original$legs$group_slot==g]);gid <- sprintf('g%02d',g)
    gl <- tibble(group_id=gid,fixture_id=fx,leg_order=1:7)
    supports <- q |> filter(fixture_id%in%fx) |> transmute(candidate_id=paste0(gid,'|7'),
      fixture_id,outcome,allowed=TRUE,preference=match(outcome,c('W','D','L')))
    space <- parlay_enumerate_tickets(gl,q,cutoff=cutoff,supports=supports,n_legs=7L)
    blocks[[g]] <- parlay_rank_tickets(space$tickets,space$candidate_tickets,cutoff=cutoff,
      ranking='probability_desc') |> as_tibble() |> select(group_id,ticket_id,probability,rank)
   }
   t <- bind_rows(blocks)
   if(model=='RAW')for(g in 1:8) {
    a <- t |> filter(group_id==sprintf('g%02d',g),rank>=30L,rank<=154L) |> arrange(ticket_id)
    b <- p$tickets |> filter(group==g) |> arrange(ticket_id)
    stopifnot(identical(a$ticket_id,b$ticket_id),max(abs(a$probability-b$probability))<1e-12)
   }
   d <- list(cutoff=cutoff,probabilities=q,candidates=t,source_bindings=c(as.list(hashes),list(
     forecast=row$frozen_probability_sha256,plans=row$plans_sha256,model=model)))
   at <- source_at
   if(model!='RAW')at <- max(at,lubridate::ymd_hms(fits[[model]]$receipt$maximum_source_time,tz='UTC'))
   d$source_receipt <- list(cutoff=cutoff,probability_hash=rlang::hash(q),candidate_hash=rlang::hash(t),
     max_source_available_utc=at,source_snapshots=as.list(hashes))
   d$input_hash <- rlang::hash(d)
   message('round ',i,' ',model,': ',nrow(f),' fixtures, full-space selection')
   outputs[[model]] <- list(decision=d,selection=beidan:::SelectJointOutcomeTickets(d,125L,30L,2,3^14))
  }
  all_rounds[[as.character(i)]] <- list(index=i,dataset=p$dataset,sheet=p$sheet,cutoff=cutoff,
    features=f,feature_decision=fd,fits=fits,outputs=outputs,label_manifest=row)
 }
 batch <- list(rounds=all_rounds,source_hashes=hashes,training_n=nrow(history),
   training_issues=sort(unique(history$issue_code)),mode='PRIOR_ISSUE_HISTORICAL_DIAGNOSTIC',
   prospective_admission=FALSE,target_labels_used_for_selection=FALSE)
 path <- file.path(out,'frozen-study.rds')
 if(mode=='replay') {
  ref <- readRDS(path)
  stopifnot(identical(batch,ref))
  jsonlite::write_json(list(status='FULL_IDENTICAL_REPLAY',sha256=digest::digest(file=path,algo='sha256')),
    file.path(out,'replay.json'),pretty=TRUE,auto_unbox=TRUE)
 }else {
  stopifnot(!file.exists(path));saveRDS(batch,path)
  jsonlite::write_json(list(sha256=digest::digest(file=path,algo='sha256'),sources=as.list(sources),
    source_hashes=as.list(hashes),training_n=nrow(history),training_issues=batch$training_issues,
    target_labels_opened=FALSE,prospective_admission=FALSE),file.path(out,'manifest.json'),pretty=TRUE,auto_unbox=TRUE)
 }
} else {
 x <- readRDS(file.path(out,'frozen-study.rds'))
 stopifnot(identical(x$source_hashes,hashes),!x$prospective_admission)
 replay <- jsonlite::fromJSON(file.path(out,'replay.json'))
 stopifnot(replay$status=='FULL_IDENTICAL_REPLAY',replay$sha256==digest::digest(file=file.path(out,'frozen-study.rds'),algo='sha256'))
 rows <- groups <- scores <- windows <- list();all_labels <- list()
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
   score <- beidan:::DcAccuracyDiagnostic(q |> mutate(model=model),a |>
     filter(fixture_id%in%q$fixture_id) |> transmute(fixture_id,actual_outcome=outcome))$scores
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
      any_hit=any(gs$hit),model_any_hit=union,model_expected_wins=sum(tickets$probability),
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
 summary <- results |> group_by(model,policy) |> summarise(rounds=n(),hit_rounds=sum(any_hit),
   hit_groups=sum(hit_groups),cost_cny=sum(cost_cny),model_any_hit=mean(model_any_hit),
   cash_complete_rounds=sum(monetary_complete),.groups='drop')
 tables <- list(rounds=results,summary=summary,groups=bind_rows(groups),windows=bind_rows(windows),
   scores=ss,unique_scores=unique_scores,metrics=metrics,issues=issues)
 for(name in names(tables))write_csv(tables[[name]],file.path(out,paste0(name,'.csv')))
 stopifnot(nrow(results)==84L,nrow(metrics)==3L,all(results$pending_groups==0L))
 jsonlite::write_json(list(frozen_sha256=replay$sha256,source_hashes=as.list(hashes),
   outputs=as.list(map_chr(names(tables),~digest::digest(file=file.path(out,paste0(.x,'.csv')),algo='sha256')) |>
     set_names(names(tables))),independent_kernel_union_agreement=TRUE),file.path(out,'evaluation.json'),pretty=TRUE,auto_unbox=TRUE)
 print(metrics,width=Inf);print(summary,width=Inf)
}
