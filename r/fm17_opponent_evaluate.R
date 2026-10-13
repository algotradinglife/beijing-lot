# Descriptive paired evaluation, opened only after independent frozen replay.
root <- normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
suppressPackageStartupMessages(library(tidyverse))
library(beidan,lib.loc=file.path(root,"results/fm17-diagnostic-iterations-20261013/library"))
out <- file.path(root,"results/fm17-opponent-lambda-20261013")
manifest <- jsonlite::fromJSON(file.path(out,"manifest.json"))
replay <- jsonlite::fromJSON(file.path(out,"replay.json"))
forecast_path <- file.path(out,"forecasts.rds")
stopifnot(manifest$forecast_sha256==digest::digest(file=forecast_path,algo="sha256"),
  replay$status=="FULL_IDENTICAL_REPLAY",replay$sha256==manifest$forecast_sha256)
study <- readRDS(forecast_path)
parent_path <- file.path(root,"results/fm17-three-issues-20261013/forecasts.rds")
stopifnot(digest::digest(file=parent_path,algo="sha256")==study$bindings$parent_forecast_sha256)
parent <- readRDS(parent_path)
pm <- jsonlite::fromJSON(file.path(root,"results/fm17-three-issues-20261013/manifest.json"))
stage_path <- file.path(root,"results/fm16-three-issues-20261012/stage.rds")
stopifnot(digest::digest(file=stage_path,algo="sha256")==pm$source_hashes$parent_stage)
stage <- readRDS(stage_path)
roster <- map_dfr(stage$native,~as_tibble(.x$fixture)[,c("fixture_id","handicap","cutoff_utc")])
stopifnot(!anyDuplicated(roster$fixture_id))
label_path <- file.path(root,"results/fundamental-issues-20261011/inputs/labels.rds")
labels_source <- readRDS(label_path)
labels <- map_dfr(c("26098","26101","26102"),~labels_source[[.x]]$matches) |>
  transmute(fixture_id=paste0(issue_id,":",slot),status,score) |>
  filter(status=="完场",!is.na(score),str_detect(score,"^[0-9]+[-:][0-9]+$")) |>
  mutate(home_goals=as.integer(str_extract(score,"^[0-9]+")),away_goals=as.integer(str_extract(score,"[0-9]+$"))) |>
  inner_join(roster,by="fixture_id",relationship="one-to-one") |>
  transmute(fixture_id,score,actual_outcome=case_when(home_goals-away_goals+handicap>0~"W",home_goals-away_goals+handicap==0~"D",TRUE~"L"))
stopifnot(nrow(labels)==345L,!anyDuplicated(labels$fixture_id))
sp_path <- file.path(root,"results/fundamental-beidan-history-20261011/analysis-20261011T024028.510576Z/selected-sp.csv")
sp <- read_csv(sp_path,show_col_types=FALSE) |>
  inner_join(roster |> select(fixture_id,cutoff_utc),by="fixture_id",relationship="many-to-one")
stopifnot(nrow(problems(sp))==0,!anyDuplicated(sp[c("fixture_id","mode")]),
  all(sp$sp_w>0&sp$sp_d>0&sp$sp_l>0),all(sp$quote_at<sp$selection_cutoff),
  all(sp$selection_cutoff[sp$mode=="same_cutoff"]==sp$cutoff_utc[sp$mode=="same_cutoff"]))
bd <- sp |> transmute(fixture_id,mode,W=1/sp_w,D=1/sp_d,L=1/sp_l) |>
  mutate(mass=W+D+L,across(c(W,D,L),~.x/mass)) |> select(-mass) |>
  pivot_longer(c(W,D,L),names_to="outcome",values_to="probability") |>
  mutate(model=if_else(mode=="same_cutoff","BEIDAN_T24","BEIDAN_LATER"))
baseline <- parent$probabilities |> filter(model%in%c("FM-1.7.0","FM17-source-before-tail")) |>
  select(fixture_id,model,outcome,probability)
candidate <- study$probabilities |> select(fixture_id,model,outcome,probability)
estimated_ids <- names(study$entries)
stopifnot(length(estimated_ids)>0L,all(estimated_ids%in%parent$audit$fixture_id[parent$audit$selected_source=="native"]))
# Before-tail arithmetic reuses the package DC constructor on sealed goal means.
before <- map_dfr(estimated_ids,function(id) {
  entry <- study$entries[[id]];handicap <- roster$handicap[match(id,roster$fixture_id)]
  map_dfr(c("OPPONENT_NATIVE","SAME_SUPPORT_RAW"),function(model) {
    rates <- if(model=="OPPONENT_NATIVE")entry$fit$parameters else entry$fit$same_support_raw
    scenario <- beidan:::dixon_coles_score_grid(rates$lambda_home,rates$lambda_away,as.integer(handicap),1e-10,-.1)
    stopifnot(isTRUE(all.equal(scenario$grid$probability,entry$results[[model]]$base$grid$probability,tolerance=1e-12)))
    tibble(fixture_id=id,model=paste0(model,"_BEFORE_TAIL"),outcome=names(scenario$probability),probability=unname(scenario$probability))
  })
})
overlay <- map_dfr(c("OPPONENT_NATIVE","SAME_SUPPORT_RAW"),function(model) {
  bind_rows(candidate |> filter(.data$model==.env$model),
    baseline |> filter(model=="FM-1.7.0",!fixture_id%in%estimated_ids)) |>
    mutate(model=paste0("FM17_OVERLAY_",.env$model))
})
metrics <- scores <- calibration <- list()
for(cohort in c("ESTIMATED_PAIRED","FULL_FROZEN_ROUTING_OVERLAY")) {
  probabilities <- if(cohort=="ESTIMATED_PAIRED")bind_rows(candidate,before,baseline) |> filter(fixture_id%in%estimated_ids)
    else bind_rows(overlay,baseline)
  for(issue in c("26098","26101","26102","ALL"))for(mode in c("model_only","same_cutoff","near_sale")) {
    ids <- intersect(probabilities$fixture_id,labels$fixture_id)
    if(issue!="ALL")ids <- ids[startsWith(ids,paste0(issue,":"))]
    if(mode!="model_only")ids <- intersect(ids,bd$fixture_id[bd$mode==mode])
    if(!length(ids))next
    p <- probabilities |> filter(fixture_id%in%ids)
    if(mode!="model_only")p <- bind_rows(p,bd |> filter(.data$mode==.env$mode,fixture_id%in%ids) |> select(fixture_id,model,outcome,probability))
    d <- beidan:::DcAccuracyDiagnostic(p,labels |> filter(fixture_id%in%ids) |> select(fixture_id,actual_outcome))
    key <- paste(cohort,issue,mode)
    metrics[[key]] <- d$summary |> mutate(cohort=cohort,issue_id=issue,comparison=mode,.before=1)
    scores[[key]] <- d$scores |> mutate(cohort=cohort,issue_id=issue,comparison=mode,.before=1)
    calibration[[key]] <- d$calibration |> mutate(cohort=cohort,issue_id=issue,comparison=mode,.before=1)
  }
}
metrics <- bind_rows(metrics);scores <- bind_rows(scores);calibration <- bind_rows(calibration)
old_rates <- map_dfr(estimated_ids,function(id)tibble(fixture_id=id,
  old_lambda_home=stage$native[[id]]$native$parameters$lambda_home,
  old_lambda_away=stage$native[[id]]$native$parameters$lambda_away))
lambdas <- study$audit |> filter(state=="ESTIMATED") |> left_join(old_rates,by="fixture_id",relationship="one-to-one") |>
  mutate(old_difference=old_lambda_home-old_lambda_away,new_difference=lambda_home-lambda_away,
    same_support_difference=raw_same_support_home-raw_same_support_away,
    direction_changed=sign(old_difference)!=sign(new_difference),
    lambda_home_delta=lambda_home-old_lambda_home,lambda_away_delta=lambda_away-old_lambda_away)
margins <- map_dfr(estimated_ids,function(id) {
  entry <- study$entries[[id]]
  map_dfr(c("OPPONENT_NATIVE","SAME_SUPPORT_RAW","FM-1.7.0"),function(model) {
    result <- if(model=="FM-1.7.0")parent$entries[[id]]$results[[model]]else entry$results[[model]]
    map_dfr(c("base","final"),function(stage_name)result[[stage_name]]$grid |>
      mutate(margin=as.integer(home_goals-away_goals)) |> group_by(margin) |>
      summarise(probability=sum(probability),.groups="drop") |>
      mutate(fixture_id=id,model=model,stage=stage_name,core=margin%in%result$core$core_margins,.before=1))
  })
})
coefficients <- map_dfr(study$entries,~.x$fit$coefficients,.id="fixture_id")
observations <- map_dfr(study$entries,~.x$fit$observations,.id="fixture_id")
support <- map_dfr(study$entries,~.x$fit$support,.id="fixture_id")
tables <- list(metrics=metrics,scores=scores,calibration=calibration,lambdas=lambdas,margins=margins,
  coefficients=coefficients,observations=observations,support=support,labels=labels)
for(name in names(tables))write_csv(tables[[name]],file.path(out,paste0(name,".csv")))
receipt <- list(intended_use="POSTHOC_HISTORICAL_DIAGNOSTIC",candidate_forecast_sha256=manifest$forecast_sha256,
  source_hashes=list(labels=digest::digest(file=label_path,algo="sha256"),beidan=digest::digest(file=sp_path,algo="sha256"),
    parent_stage=digest::digest(file=stage_path,algo="sha256"),client=digest::digest(file=file.path(root,"r/fm17_opponent_evaluate.R"),algo="sha256")),
  outputs=set_names(map(paste0(names(tables),".csv"),~digest::digest(file=file.path(out,.x),algo="sha256")),names(tables)),
  estimated=length(estimated_ids),unestimated=sum(study$audit$state!="ESTIMATED"),full_settled=nrow(labels),
  overlay_definition="Candidate replaces only estimated native fixtures; all other frozen FM17 probabilities carried unchanged. Not a fully re-estimated issue.",
  causal_comparison="Fixed policy historical proxy diagnostic; known outcomes, not independent prospective evidence.")
jsonlite::write_json(receipt,file.path(out,"evaluation.json"),pretty=TRUE,auto_unbox=TRUE)
print(metrics |> filter(issue_id=="ALL",comparison%in%c("same_cutoff","near_sale")))
