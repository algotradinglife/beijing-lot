# Target-label-free experiment: change native lambda only; source routing frozen.
args <- commandArgs(TRUE);root <- normalizePath(args[1],mustWork=TRUE)
replay <- length(args)>1L && args[2]=="replay"
suppressPackageStartupMessages(library(tidyverse))
library(beidan,lib.loc=file.path(root,"results/fm17-diagnostic-iterations-20261013/library"))
out <- file.path(root,"results/fm17-opponent-lambda-20261013")
runtime <- jsonlite::fromJSON(file.path(root,"config/fm17_opponent_lambda_runtime.json"))
input_path <- file.path(out,"inputs.json");metadata_path <- file.path(out,"metadata-v2/metadata.json")
inputs <- jsonlite::fromJSON(input_path,simplifyVector=FALSE)
metadata <- jsonlite::fromJSON(metadata_path,simplifyVector=FALSE)
exclusion_path <- file.path(out,"exclusion-rosters-v4/rosters.json")
exclusion <- jsonlite::fromJSON(exclusion_path,simplifyVector=FALSE)
stopifnot(exclusion$parser_sha256==digest::digest(file=file.path(root,"packages/beidan/inst/python/beidan_backend/opponent_roster.py"),algo="sha256"))
declared_issues <- unique(unlist(map(exclusion$packets,"declared_issues")))
exclusion_roster <- map_dfr(exclusion$packets,~bind_rows(.x$roster)) |> distinct(issue_id,provider_id)
required_exclusion_issues <- declared_issues[as.integer(declared_issues)>=26098L]
if(length(setdiff(required_exclusion_issues,exclusion_roster$issue_id))) stop("Published future issue roster coverage is incomplete")
stopifnot(metadata$input_sha256==digest::digest(file=input_path,algo="sha256"))
stopifnot(metadata$parser_sha256==digest::digest(file=file.path(root,"packages/beidan/inst/python/beidan_backend/opponent_history.py"),algo="sha256"),
  metadata$source_parser_sha256==digest::digest(file=file.path(root,"packages/beidan/inst/python/beidan_backend/fundamentals.py"),algo="sha256"))
fixtures <- bind_rows(inputs$fixtures)
history <- bind_rows(inputs$history)
meta_rows <- map_dfr(metadata$parsed,function(packet) {
  if(!length(packet$result$rows))return(tibble(fixture_id=character(),selected_source=character(),scope=character(),match_id=character(),
    metadata_date=character(),metadata_home_id=character(),metadata_away_id=character(),metadata_home_score=integer(),metadata_away_score=integer(),
    competition_id=character(),competition_name=character(),neutral_reported=logical()))
  bind_rows(packet$result$rows) |>
    mutate(competition_name=map_chr(packet$result$rows,~.x$competition_name %||% NA_character_)) |>
    transmute(fixture_id=packet$fixture_id,selected_source=packet$source,
    scope=recode(block,h_data="home_recent",a_data="away_recent",v_data="head_to_head"),match_id=history_id,
    metadata_date=event_date,metadata_home_id=home_id,metadata_away_id=away_id,
    metadata_home_score=home_score,metadata_away_score=away_score,competition_id,competition_name,neutral_reported)
})
stopifnot(!anyDuplicated(meta_rows[c("fixture_id","selected_source","scope","match_id")]))
enriched <- history |> left_join(meta_rows,by=c("fixture_id","selected_source","scope","match_id"),relationship="one-to-one") |>
  mutate(metadata_agrees=!is.na(competition_id)&event_date==metadata_date&home_id==metadata_home_id&away_id==metadata_away_id&
    home_score==metadata_home_score&away_score==metadata_away_score,
    row_key=paste(fixture_id,scope,match_id,sep=":"))
# Source selection is the existing factual ledger, never a target outcome choice.
target_meta <- map_dfr(metadata$parsed,function(p)tibble(fixture_id=p$fixture_id,source=p$source,
  competition_id=p$result$target_competition_id %||% NA_character_,
  competition_name=p$result$target_competition_name %||% NA_character_,
  neutral_reported=p$result$target_neutral_reported,
  metadata_state=p$result$target_competition_state)) |>
  arrange(fixture_id,source!="titan") |> group_by(fixture_id) |>
  filter(!is.na(competition_id)) |> slice_head(n=1) |> ungroup()
reticulate::use_python(file.path(root,".venv/bin/python"),required=TRUE)
reticulate::import("sys",convert=FALSE)$path$insert(0L,file.path(root,"packages/beidan/inst/python"))
backend <- reticulate::import("beidan_backend.opponent_goals",convert=FALSE)
shared <- reticulate::import("beidan_backend.temporal_learning",convert=FALSE)
shared$verify_implementation_closure(reticulate::import("pathlib",convert=FALSE)$Path(root),exclusion$implementation)
adjustment <- reticulate::import("beidan_backend.fundamental_probability",convert=FALSE)
ns <- new.env(parent=asNamespace("beidan"));sys.source(file.path(root,"packages/beidan/R/opponent_goals.R"),ns)
parent_path <- file.path(root,"results/fm17-three-issues-20261013/forecasts.rds")
stopifnot(digest::digest(file=parent_path,algo="sha256")==inputs$parent_forecast_sha256)
parent <- readRDS(parent_path)
parent_cutoffs <- map_dfr(parent$entries,~tibble(fixture_id=.x$fixture$fixture_id,
  parent_cutoff=format(.x$cutoff$cutoff_utc,"%Y-%m-%dT%H:%M:%SZ",tz="UTC")))
bound_cutoffs <- fixtures |> inner_join(parent_cutoffs,by="fixture_id",relationship="one-to-one")
stopifnot(nrow(bound_cutoffs)==length(parent$entries),all(bound_cutoffs$cutoff_utc==bound_cutoffs$parent_cutoff))
bindings <- list(input_sha256=digest::digest(file=input_path,algo="sha256"),metadata_sha256=digest::digest(file=metadata_path,algo="sha256"),
  runtime_sha256=digest::digest(file=file.path(root,"config/fm17_opponent_lambda_runtime.json"),algo="sha256"),
  client_sha256=digest::digest(file=file.path(root,"r/fm17_opponent_freeze.R"),algo="sha256"),
  parent_forecast_sha256=inputs$parent_forecast_sha256)
bindings$exclusion_rosters_sha256 <- digest::digest(file=exclusion_path,algo="sha256")
write_csv(exclusion_roster,file.path(out,"exclusion-native-identities.csv"))
entries <- probabilities <- audit <- list()
existing <- if(replay)readRDS(file.path(out,"forecasts.rds"))else NULL
for(id in fixtures$fixture_id[fixtures$native_selected]) {
  f <- fixtures |> filter(fixture_id==id)
  tm <- target_meta |> filter(fixture_id==id)
  row <- tibble(fixture_id=id,issue_id=f$issue_id,home=f$home,away=f$away,league=f$league,
                state="",reason="",metadata_supported=NA_integer_,metadata_missing=NA_integer_)
  if(nrow(tm)!=1L) {
    row$state <- "NO_BOUND_COMPETITION";row$reason <- "Source title/history cannot bind target competition"
    audit[[id]] <- row;next
  }
  h <- enriched |> filter(issue_id==f$issue_id)
  row$metadata_supported <- sum(h$metadata_agrees)
  row$metadata_missing <- sum(!h$metadata_agrees)
  h <- h |> filter(metadata_agrees) |> select(row_key,match_id,event_date,home_id,away_id,
    home_score,away_score,score_scope,competition_id,neutral_reported)
  fixture <- as.list(f[1,c("fixture_id","issue_id","provider_id","home_id","away_id")])
  fixture$competition_id <- tm$competition_id;fixture$neutral_reported <- tm$neutral_reported
  cutoff <- shared$Cutoff$decision_epoch(f$issue_id,f$cutoff_utc)
  # Exact target and future roster identities excluded even if source dates lie.
  excluded <- exclusion_roster$provider_id[as.integer(exclusion_roster$issue_id)>=as.integer(f$issue_id)]
  stopifnot(all(fixtures$provider_id[fixtures$issue_id==f$issue_id] %in% excluded))
  domain <- jsonlite::fromJSON(jsonlite::toJSON(h,dataframe="rows",auto_unbox=TRUE,na="null",digits=NA),simplifyVector=FALSE)
  native <- tryCatch({
    prepared <- backend$prepare_opponent_goals(domain,fixture,as.list(unique(excluded)),cutoff,bindings,root,runtime$native_policy)
    ns$FitOpponentGoals(prepared,fixture,cutoff,runtime$fit_policy,root)
  },error=function(error)error)
  if(inherits(native,"error")) {
    row$state <- "UNESTIMATED";row$reason <- conditionMessage(native)
    audit[[id]] <- row;next
  }
  row$state <- "ESTIMATED";row$reason <- "Fixed ridge .05, target-competition-only; no target-label fitting"
  e <- parent$entries[[id]];results <- list()
  for(model in c("OPPONENT_NATIVE","SAME_SUPPORT_RAW")) {
    lambdas <- if(model=="OPPONENT_NATIVE")native$parameters else native$same_support_raw
    base <- e$results[["FM-1.7.0"]]$base
    base$grid <- beidan:::dixon_coles_score_grid(lambdas$lambda_home,lambdas$lambda_away,0L,1e-10,-.1)$grid |>
      as_tibble() |> select(home_goals,away_goals,probability)
    base$model_id <- model
    base$source_hashes <- c(bindings,list(fit=beidan:::.score_margin_hash(native)))
    base$max_source_available_utc <- lubridate::ymd_hms(native$receipt$admission$maximum_source_time,tz="UTC")
    eid <- paste0("opponent-",model)
    ts <- format(base$max_source_available_utc,"%Y-%m-%dT%H:%M:%SZ",tz="UTC")
    rows <- list(list(evidence_id=eid,fixture_id=id,source_hash=beidan:::.score_margin_hash(native),row_key=eid,
      issue_code="OPPONENT_FACT_PROXY",issue_year=as.integer(substr(ts,1,4)),label_available_ts=ts,data_available_ts=ts))
    review <- list(decision=e$results[["FM-1.7.0"]]$review$decision,base_hash=beidan:::.score_margin_hash(base$grid),
      cutoff_utc=f$cutoff_utc,reason="FM17 existing apply/retain judgement held fixed",counterevidence="No fresh qualitative or routing decision; opponent prototype diagnostic only")
    core <- BuildFmTailJudgement(base,review,eid,e$cutoff,list(coverage=.9,coefficient=.3,tie_tolerance=1e-12))
    binding <- c(bindings,list(base_artifact=beidan:::.score_margin_hash(base),margin_judgement=beidan:::.score_margin_hash(core$judgement),
      direction_implementation=beidan:::.score_margin_code(root),fit_receipt=beidan:::.score_margin_hash(native$receipt),
      ledgers=beidan:::.score_margin_hash(native$ledgers),tail_binding=core$binding_hash))
    ctx <- adjustment$build_adjustment_evidence_context(rows,as.list(e$fixture),cutoff,binding,
      shared$AvailabilityPolicy$historical_proxy("FM17_OPPONENT_LAMBDA_DIAGNOSTIC"),"HISTORICAL_DIAGNOSTIC",root)
    final <- adjust_score_margin_distribution(base,core$judgement,ctx,e$fixture,e$cutoff,root)
    results[[model]] <- list(base=base,review=review,core=core,final=final)
    probabilities[[paste(id,model)]] <- project_score_outcomes(final,as.integer(f$handicap),root) |>
      mutate(fixture_id=id,model=model,.before=1)
  }
  entry <- list(fixture=fixture,cutoff=e$cutoff,fit=native,results=results)
  if(replay)stopifnot(identical(entry,existing$entries[[id]]))
  entries[[id]] <- entry
  audit[[id]] <- row |> mutate(competition_id=tm$competition_id,competition_name=tm$competition_name,
    neutral_reported=fixture$neutral_reported,lambda_home=native$parameters$lambda_home,
    lambda_away=native$parameters$lambda_away,raw_same_support_home=native$same_support_raw$lambda_home,
    raw_same_support_away=native$same_support_raw$lambda_away,fit_rows=native$receipt$fitted_rows)
  if(length(entries)%%10L==0L)message("Estimated ",length(entries)," / ",length(audit)," processed")
}
batch <- list(entries=entries,probabilities=bind_rows(probabilities),audit=bind_rows(audit),bindings=bindings)
path <- file.path(out,"forecasts.rds")
if(replay) {
  stopifnot(identical(batch,existing))
  jsonlite::write_json(list(status="FULL_IDENTICAL_REPLAY",forecasts=length(entries),sha256=digest::digest(file=path,algo="sha256")),file.path(out,"replay.json"),pretty=TRUE,auto_unbox=TRUE)
} else {
  if(file.exists(path))stopifnot(identical(batch,readRDS(path)))else saveRDS(batch,path)
  write_csv(batch$audit,file.path(out,"audit.csv"));write_csv(batch$probabilities,file.path(out,"probabilities.csv"))
  write_csv(enriched |> count(issue_id,metadata_agrees),file.path(out,"metadata-coverage.csv"))
  write_csv(bind_rows(metadata$ledger),file.path(out,"source-replay-ledger.csv"))
  jsonlite::write_json(list(forecast_sha256=digest::digest(file=path,algo="sha256"),bindings=bindings,
    estimated=length(entries),native_scope=sum(fixtures$native_selected),target_labels_opened=FALSE,
    formal_FM_unchanged=TRUE),file.path(out,"manifest.json"),pretty=TRUE,auto_unbox=TRUE)
}
print(batch$audit |> count(issue_id,state))
