# Explicit immutable parent history and package-verified NAS provenance.
root <- normalizePath(commandArgs(TRUE)[1], mustWork=TRUE)
suppressPackageStartupMessages(library(tidyverse))
library(beidan,lib.loc=file.path(root,"results/fm17-diagnostic-iterations-20261013/library"))
out <- file.path(root,"results/fm17-opponent-lambda-20261013")
dir.create(out,recursive=TRUE,showWarnings=FALSE)
parent_path <- file.path(root,"results/fm17-three-issues-20261013/forecasts.rds")
stopifnot(digest::digest(file=parent_path,algo="sha256")=="e537428c0a43f966542c703d3edf6264722c95a7551dbabf7853aa909354e786")
parent <- readRDS(parent_path)
rosters <- readRDS(file.path(root,"results/fundamental-issues-20261011/inputs/rosters.rds"))
history <- provenance <- fixtures <- versions <- list()
for (issue in c("26098","26101","26102")) {
  path <- file.path(root,"results/fundamental-issues-20261011/run-20261011T011533.304058Z",paste0(issue,"-frozen.rds"))
  original <- readRDS(path)
  version <- original$source_version
  dataset <- paste0("source_issue_",issue)
  # Catalogue reader checks every Parquet hash; explicit versions, never current.
  nas_history <- read_dataset(dataset,"history",version=version)
  stopifnot(identical(nas_history,original$history))
  history[[issue]] <- nas_history |> mutate(issue_id=issue,event_date=as.character(event_date),.before=1)
  provenance[[issue]] <- read_dataset(dataset,"provenance",version=version) |>
    mutate(observed_at=format(observed_at,"%Y-%m-%dT%H:%M:%OS6Z",tz="UTC"))
  fixtures[[issue]] <- original$fixtures |>
    left_join(rosters[[issue]]$matches |> transmute(provider_id=native_id,league),
              by="provider_id",relationship="one-to-one") |>
    mutate(cutoff_utc=format(cutoff_utc,"%Y-%m-%dT%H:%M:%SZ",tz="UTC"),
           kickoff_utc=format(lubridate::ymd_hms(cutoff_utc,tz="UTC")+lubridate::hours(24),"%Y-%m-%dT%H:%M:%SZ",tz="UTC"))
  versions[[issue]] <- list(dataset=dataset,version=version,
    manifest=dataset_manifest(dataset,version=version),
    frozen_path=substring(path,nchar(root)+2L),frozen_sha256=digest::digest(file=path,algo="sha256"))
}
scope <- bind_rows(fixtures) |> mutate(native_selected=fixture_id %in% parent$audit$fixture_id[parent$audit$selected_source=="native"])
payload <- list(fixtures=scope,history=bind_rows(history),provenance=bind_rows(provenance),sources=versions,
  parent_forecast_sha256=digest::digest(file=parent_path,algo="sha256"),
  client_sha256=digest::digest(file=file.path(root,"r/fm17_opponent_inputs.R"),algo="sha256"))
destination <- file.path(out,"inputs.json")
body <- jsonlite::toJSON(payload,dataframe="rows",auto_unbox=TRUE,na="null",digits=NA,pretty=FALSE)
if(file.exists(destination))stopifnot(identical(readLines(destination,warn=FALSE),as.character(body))) else writeLines(body,destination)
write_csv(scope,file.path(out,"scope.csv"))
print(scope |> count(issue_id,native_selected))
