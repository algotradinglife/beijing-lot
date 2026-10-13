# Typed local staging for the single catalog/version publisher; no model fitting.
root <- normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
suppressPackageStartupMessages(library(tidyverse))
out <- file.path(root,"results/fm17-opponent-lambda-20261013")
manifest <- jsonlite::fromJSON(file.path(out,"manifest.json"))
replay <- jsonlite::fromJSON(file.path(out,"replay.json"))
evaluation <- jsonlite::fromJSON(file.path(out,"evaluation.json"))
stopifnot(replay$status=="FULL_IDENTICAL_REPLAY",replay$sha256==manifest$forecast_sha256,
  digest::digest(file=file.path(out,"forecasts.rds"),algo="sha256")==manifest$forecast_sha256,
  evaluation$candidate_forecast_sha256==manifest$forecast_sha256)
for(name in names(evaluation$outputs)) {
  if(digest::digest(file=file.path(out,paste0(name,".csv")),algo="sha256")!=evaluation$outputs[[name]])
    stop("Evaluation CSV hash differs: ",name)
}
study <- readRDS(file.path(out,"forecasts.rds"))
scope <- read_csv(file.path(out,"scope.csv"),col_types=cols(.default=col_character(),native_selected=col_logical(),handicap=col_double()),show_col_types=FALSE)
audit <- study$audit |> left_join(scope |> transmute(fixture_id,cutoff_utc=lubridate::ymd_hms(cutoff_utc,tz="UTC")),
  by="fixture_id",relationship="one-to-one")
tables <- list(audit=audit,probabilities=study$probabilities)
for(name in c("metrics","lambdas","margins","coefficients","observations","support")) {
  file <- file.path(out,paste0(name,".csv"))
  header <- names(read_csv(file,n_max=0,col_types=cols(.default=col_character()),show_col_types=FALSE))
  identifiers <- intersect(c("fixture_id","issue_id","team_id","opponent_id","competition_id","row_key"),header)
  specification <- do.call(cols,c(list(.default=col_guess()),set_names(rep(list(col_character()),length(identifiers)),identifiers)))
  tables[[name]] <- read_csv(file,col_types=specification,show_col_types=FALSE)
  for(column in intersect(c("n","hits1","hits2","matches","margin"),names(tables[[name]]))) {
    checkmate::assert_integerish(tables[[name]][[column]],lower=if(column=="margin")-2147483647 else 0,upper=2147483647,any.missing=FALSE)
    tables[[name]][[column]] <- as.integer(tables[[name]][[column]])
  }
  stopifnot(nrow(problems(tables[[name]]))==0L)
}
snapshot_paths <- c(inputs=file.path(out,"inputs.json"),metadata=file.path(out,"metadata-v2/metadata.json"),
  identity_rosters=file.path(out,"exclusion-rosters-v4/rosters.json"),labels=file.path(out,"labels.csv"),
  beidan_sp=file.path(root,"results/fundamental-beidan-history-20261011/analysis-20261011T024028.510576Z/selected-sp.csv"))
expected_snapshot_hashes <- c(inputs=study$bindings$input_sha256,metadata=study$bindings$metadata_sha256,
  identity_rosters=study$bindings$exclusion_rosters_sha256,labels=evaluation$outputs$labels,
  beidan_sp=evaluation$source_hashes$beidan)
for(name in names(snapshot_paths))if(digest::digest(file=snapshot_paths[[name]],algo="sha256")!=expected_snapshot_hashes[[name]])
  stop("Frozen replay snapshot hash differs: ",name)
tables$snapshots <- tibble(snapshot_id=names(snapshot_paths),
  payload=map_chr(snapshot_paths,~readChar(.x,nchars=file.info(.x)$size,useBytes=TRUE)),
  sha256=map_chr(snapshot_paths,~digest::digest(file=.x,algo="sha256")))
stopifnot(all(map2_lgl(tables$snapshots$payload,tables$snapshots$sha256,
  ~digest::digest(.x,algo="sha256",serialize=FALSE)==.y)))
fits <- map(study$entries,function(entry) {
  fit <- entry$fit
  # Keep the original admission hash exported by the shared group contexts.
  admission_hashes <- unique(map_chr(fit$receipts,~.x$source_hashes$admission))
  stopifnot(length(admission_hashes)==1L)
  fit$receipt$admission_binding <- admission_hashes
  # Tuple-like implementation roots must remain JSON arrays at length one.
  fit$receipt$admission$implementation$root_modules <- I(unlist(fit$receipt$admission$implementation$root_modules))
  for(i in seq_along(fit$receipts))fit$receipts[[i]]$implementation$root_modules <- I(unlist(fit$receipts[[i]]$implementation$root_modules))
  fit[c("receipt","receipts","ledgers")]
})
receipt <- list(intended_use="POSTHOC_HISTORICAL_DIAGNOSTIC",formal_FM_unchanged=TRUE,
  input_hashes=c(study$bindings,list(forecasts=manifest$forecast_sha256,
    evaluation=digest::digest(file=file.path(out,"evaluation.json"),algo="sha256"))),
  implementation_hashes=list(publish_R=digest::digest(file=file.path(root,"r/fm17_opponent_publish.R"),algo="sha256"),
    publish_Python=digest::digest(file=file.path(root,"packages/beidan/inst/python/beidan_backend/opponent_publication.py"),algo="sha256"),
    serialized_validator=digest::digest(file=file.path(root,"packages/beidan/inst/python/beidan_backend/temporal_learning/serialized_opponent_fit.py"),algo="sha256")),
  independent_replay=replay,fits=fits,
  cutoffs=as.list(set_names(format(audit$cutoff_utc,"%Y-%m-%dT%H:%M:%SZ",tz="UTC"),audit$fixture_id)),
  study_id="OPPONENT_POISSON_RIDGE_RESEARCH_1",evaluation=evaluation)
staging <- file.path(out,"publication-staging");dir.create(staging,showWarnings=FALSE)
for(name in names(tables))arrow::write_parquet(tables[[name]],file.path(staging,paste0(name,".parquet")))
jsonlite::write_json(receipt,file.path(staging,"receipt.json"),auto_unbox=TRUE,pretty=FALSE,digits=NA,null="null")
jsonlite::write_json(list(tables=set_names(map(paste0(names(tables),".parquet"),~digest::digest(file=file.path(staging,.x),algo="sha256")),names(tables)),
  receipt_sha256=digest::digest(file=file.path(staging,"receipt.json"),algo="sha256")),file.path(staging,"manifest.json"),auto_unbox=TRUE,pretty=TRUE)
