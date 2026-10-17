# Rscript r/fm171_margin_shape_freeze.R ROOT OUTPUT [replay]
# Fixed-policy study orchestration; all cutoff/reweighting logic stays in beidan/shared backend.
args <- commandArgs(TRUE);stopifnot(length(args)%in%c(2L,3L))
root <- normalizePath(args[1],mustWork=TRUE);out <- args[2]
replay_mode <- length(args)==3L && args[3]=="replay"
suppressPackageStartupMessages(library(tidyverse))
library(beidan,lib.loc=file.path(root,"r_lib"))
reticulate::use_python(file.path(root,".venv/bin/python"),required=TRUE)
backend <- beidan::python_backend(file.path(root,".venv/bin/python"))
shared <- reticulate::import("beidan_backend.temporal_learning",convert=FALSE)
adjustment <- reticulate::import("beidan_backend.fundamental_probability",convert=FALSE)
policy_path <- file.path(root,"config/fm171_margin_shape_study.json")
policy <- jsonlite::fromJSON(policy_path)
stopifnot(!policy$parameters_selected_from_target_labels,!policy$versions_modified)
policies <- as_tibble(policy$candidate_policies)
stopifnot(identical(policies$model,c("SOURCE_FULL","FM171","CORE80_C03","CORE90_C01")))
source_dir <- file.path(root,"results/fm-lambda-integration-20261017")
manifest <- jsonlite::fromJSON(file.path(source_dir,"manifest.json"))
replay <- jsonlite::fromJSON(file.path(source_dir,"replay.json"))
source_path <- file.path(source_dir,"forecasts.rds")
stopifnot(replay$status=="FULL_IDENTICAL_REPLAY",replay$sha256==manifest$forecast_sha256,
 digest::digest(file=source_path,algo="sha256")==manifest$forecast_sha256)
x <- readRDS(source_path)
parent_path <- file.path(root,"results/fm17-three-issues-20261013/forecasts.rds")
stopifnot(digest::digest(file=parent_path,algo="sha256")==manifest$bindings$parent_forecast_sha256)
parent <- readRDS(parent_path)
roster_path <- file.path(root,"results/fm18-three-issues-20261017/forecasts.rds")
stopifnot(digest::digest(file=roster_path,algo="sha256")==manifest$bindings$old_alpha_sha256)
roster <- readRDS(roster_path)$audit |> select(fixture_id,handicap)
bindings <- list(source=digest::digest(file=source_path,algo="sha256"),
 parent=digest::digest(file=parent_path,algo="sha256"),roster=digest::digest(file=roster_path,algo="sha256"),
 policy=digest::digest(file=policy_path,algo="sha256"),
 client=digest::digest(file=file.path(root,"r/fm171_margin_shape_freeze.R"),algo="sha256"),
 direction_implementation=beidan:::.score_margin_code(root),
 tail_function=digest::digest(body(BuildFmTailJudgement),algo="sha256"))
dir.create(out,recursive=TRUE,showWarnings=FALSE)
entries <- features <- projections <- margins <- list()
for(id in names(x$entries)) {
 e <- parent$entries[[id]];z <- x$entries[[id]];h <- roster$handicap[match(id,roster$fixture_id)]
 stopifnot(identical(e$cutoff,z$cutoff),length(h)==1L,!is.na(h))
 beidan:::match_require_cutoff(z$cutoff)
 cutoff <- shared$Cutoff$decision_epoch(z$cutoff$issue_id,format(z$cutoff$cutoff_utc,"%Y-%m-%dT%H:%M:%SZ",tz="UTC"))
 base <- e$results[["FM-1.7.0"]]$base
 rows <- e$evidence_rows
 if(z$changed_native) {
  stopifnot(!is.null(z$fit),z$selected_source=="native",
   identical(z$fit$receipt$R_code_sha256,manifest$bindings$R_fit_sha256),
   identical(digest::digest(file=file.path(root,"packages/beidan/R/opponent_goals.R"),algo="sha256"),manifest$bindings$R_fit_sha256))
  lambda <- z$fit$same_support_raw
  base$grid <- beidan:::dixon_coles_score_grid(lambda$lambda_home,lambda$lambda_away,0L,1e-10,-.1)$grid |>
   as_tibble() |> select(home_goals,away_goals,probability)
  base$model_id <- "FM171_SAME_COMPETITION_SOURCE"
  base$source_hashes <- c(bindings,list(fit=beidan:::.score_margin_hash(z$fit)))
  base$max_source_available_utc <- lubridate::ymd_hms(z$fit$receipt$admission$maximum_source_time,tz="UTC")
  ts <- format(base$max_source_available_utc,"%Y-%m-%dT%H:%M:%SZ",tz="UTC")
  rows <- list(list(evidence_id="same-competition-fit",fixture_id=id,source_hash=beidan:::.score_margin_hash(z$fit),
   row_key="same-competition-fit",issue_code="NATIVE_HISTORY_PROXY",issue_year=as.integer(substr(ts,1,4)),
   label_available_ts=ts,data_available_ts=ts))
 }
 stopifnot(identical(base$cutoff,z$cutoff),base$max_source_available_utc<z$cutoff$cutoff_utc)
 # Shape measurements use only the selected source grid and actual handicap, never target labels.
 m <- base$grid |> mutate(margin=home_goals-away_goals) |> group_by(margin) |>
  summarise(probability=sum(probability),.groups="drop") |> arrange(margin) |> mutate(cumulative=cumsum(probability))
 dd <- -as.integer(h);dp <- sum(m$probability[m$margin==dd]);mu <- sum(m$margin*m$probability)
 intervals <- tidyr::crossing(lo=m$margin,hi=m$margin) |> filter(hi>=lo) |>
  mutate(mass=m$cumulative[match(hi,m$margin)]-c(0,head(m$cumulative,-1))[match(lo,m$margin)],
   positions=hi-lo+1L) |> filter(mass>=policy$shape_policy$interval_mass-policy$tie_tolerance) |>
  arrange(positions,desc(mass),abs((lo+hi)/2-mu),lo)
 stopifnot(nrow(intervals)>0L)
 short <- intervals[1,]
 ranked <- m |> arrange(desc(probability),margin)
 dr <- 1L+sum(m$probability>dp+policy$tie_tolerance)
 w <- sum(m$probability[m$margin>dd]);l <- sum(m$probability[m$margin<dd])
 local <- sum(m$probability[abs(m$margin-dd)<=policy$shape_policy$local_radius])
 original_review <- e$results[["FM-1.7.0"]]$review
 review <- list(decision=original_review$decision,base_hash=beidan:::.score_margin_hash(base$grid),
  cutoff_utc=format(z$cutoff$cutoff_utc,"%Y-%m-%dT%H:%M:%SZ",tz="UTC"),
  reason="Fixed distribution-shape sensitivity; inherited apply/retain review",counterevidence="Known outcomes; no fitted thresholds or new source decisions")
 results <- list()
 for(k in seq_len(nrow(policies))) {
  p <- policies[k,];name <- p$model
  core <- BuildFmTailJudgement(base,review,rows[[1]]$evidence_id,z$cutoff,
   list(coverage=p$coverage,coefficient=p$coefficient,tie_tolerance=policy$tie_tolerance))
  binding <- c(bindings,list(base_artifact=beidan:::.score_margin_hash(base),
   margin_judgement=beidan:::.score_margin_hash(core$judgement),tail_binding=core$binding_hash,
   shape_inputs=beidan:::.score_margin_hash(list(handicap=h,policy=policy$shape_policy,cutoff=z$cutoff)),
   policy_variant=name))
  ctx <- adjustment$build_adjustment_evidence_context(rows,as.list(e$fixture),cutoff,binding,
   shared$AvailabilityPolicy$historical_proxy("FM171_MARGIN_SHAPE_DIAGNOSTIC"),"HISTORICAL_DIAGNOSTIC",root)
  final <- adjust_score_margin_distribution(base,core$judgement,ctx,e$fixture,z$cutoff,root)
  q <- project_score_outcomes(final,as.integer(h),root)
  if(name=="FM171") {
   ref <- x$probabilities |> filter(fixture_id==id,model=="FM17+SAME_SUPPORT_RAW")
   stopifnot(max(abs(q$probability[match(ref$outcome,q$outcome)]-ref$probability))<1e-10)
  }
  if(name=="SOURCE_FULL")stopifnot(max(abs(final$grid$probability-base$grid$probability))<1e-10)
  results[[name]] <- list(final=final,core=core)
  projections[[paste(id,name)]] <- q |> mutate(fixture_id=id,model=name,.before=1) |> select(fixture_id,model,outcome,probability)
  margins[[paste(id,name)]] <- final$grid |> mutate(margin=home_goals-away_goals) |> group_by(margin) |>
   summarise(probability=sum(probability),.groups="drop") |> mutate(fixture_id=id,model=name,.before=1)
 }
 f <- tibble(fixture_id=id,issue_id=z$fixture$issue_id,home=z$fixture$home,away=z$fixture$away,
  cutoff_utc=review$cutoff_utc,handicap=as.integer(h),draw_margin=dd,selected_source=z$selected_source,
  native_changed=z$changed_native,eligible=z$changed_native||z$selected_source!="native",
  review_decision=review$decision,draw_margin_rank=dr,draw_top2=dr<=2L,draw_probability=dp,
  mode=ranked$margin[1],mode_probability=ranked$probability[1],mode_gap=ranked$probability[1]-dp,
  mean_margin=mu,sd_margin=sqrt(sum((m$margin-mu)^2*m$probability)),
  entropy=-sum(m$probability[m$probability>0]*log(m$probability[m$probability>0])),
  interval80_lo=short$lo,interval80_hi=short$hi,interval80_positions=short$positions,interval80_mass=short$mass,
  line_in_interval80=dd>=short$lo && dd<=short$hi,local_mass=local,
  shape=case_when(short$positions<=policy$shape_policy$narrow_max_integer_positions~"NARROW",
   short$positions<=policy$shape_policy$medium_max_integer_positions~"MEDIUM",TRUE~"BROAD"),
  line_locality=case_when(local>=policy$shape_policy$local_mass_high~"HIGH",local>=policy$shape_policy$local_mass_low~"MEDIUM",TRUE~"LOW"),
  raw_w=w,raw_d=dp,raw_l=l)
 features[[id]] <- f
 entries[[id]] <- list(fixture=e$fixture,cutoff=z$cutoff,base=base,evidence_rows=rows,
  review=review,feature=f,results=results)
 if(length(entries)%%50L==0L)message("Frozen ",length(entries))
}
batch <- list(entries=entries,features=bind_rows(features),probabilities=bind_rows(projections),margins=bind_rows(margins),
 bindings=bindings,policy=policy)
path <- file.path(out,"forecasts.rds")
if(replay_mode) {
 stopifnot(identical(batch,readRDS(path)))
 jsonlite::write_json(list(status="FULL_IDENTICAL_REPLAY",forecasts=length(entries),
  sha256=digest::digest(file=path,algo="sha256")),file.path(out,"replay.json"),pretty=TRUE,auto_unbox=TRUE)
} else {
 if(file.exists(path))stopifnot(identical(batch,readRDS(path)))else saveRDS(batch,path)
 write_csv(batch$features,file.path(out,"features.csv"));write_csv(batch$probabilities,file.path(out,"probabilities.csv"))
 write_csv(batch$margins,file.path(out,"margins.csv"))
 jsonlite::write_json(list(sha256=digest::digest(file=path,algo="sha256"),bindings=bindings,
  forecasts=length(entries),eligible=sum(batch$features$eligible),target_labels_opened=FALSE,
  mode=policy$mode,versions_modified=FALSE),file.path(out,"manifest.json"),pretty=TRUE,auto_unbox=TRUE)
}
