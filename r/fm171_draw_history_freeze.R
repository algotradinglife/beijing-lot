# Rscript r/fm171_draw_history_freeze.R ROOT OUTPUT [replay]
# Fixed, explicitly nominated issue research; temporal admission/weights/receipts are shared.
args <- commandArgs(TRUE);stopifnot(length(args)%in%c(2L,3L))
root <- normalizePath(args[1],mustWork=TRUE);out <- args[2];replay_mode <- length(args)==3L && args[3]=="replay"
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc=file.path(root,"r_lib"))
reticulate::use_python(file.path(root,".venv/bin/python"),required=TRUE)
invisible(beidan::python_backend(file.path(root,".venv/bin/python")))
shared <- reticulate::import("beidan_backend.temporal_learning",convert=FALSE)
core_module <- reticulate::import("beidan_backend.temporal_learning.core",convert=FALSE)
clock <- reticulate::import("beidan_backend.temporal_learning.diagnostic_labels",convert=FALSE)
model_receipts <- reticulate::import("beidan_backend.temporal_learning.issue_partitions",convert=FALSE)
adjustment <- reticulate::import("beidan_backend.fundamental_probability",convert=FALSE)
pandas <- reticulate::import("pandas",convert=FALSE);pathlib <- reticulate::import("pathlib",convert=FALSE)
policy_path <- file.path(root,"config/fm171_draw_history_study.json");policy <- jsonlite::fromJSON(policy_path,simplifyVector=FALSE)
stopifnot(!policy$versions_modified,identical(policy$models,list("GLOBAL","LINE","WIDTH")))
source_dir <- file.path(root,"results/fm171-margin-shape-20261017")
m <- jsonlite::fromJSON(file.path(source_dir,"manifest.json"));rp <- jsonlite::fromJSON(file.path(source_dir,"replay.json"))
source_path <- file.path(source_dir,"forecasts.rds")
stopifnot(rp$status=="FULL_IDENTICAL_REPLAY",rp$sha256==m$sha256,digest::digest(file=source_path,algo="sha256")==m$sha256)
x <- readRDS(source_path)
evaluation <- jsonlite::fromJSON(file.path(source_dir,"evaluation.json"))
label_path <- file.path(root,"results/fm17-three-issues-20261013/labels.csv")
stopifnot(digest::digest(file=label_path,algo="sha256")==evaluation$labels_sha256)
labels <- read_csv(label_path,col_types=cols(.default=col_character()))
# Retrospective label source is explicitly opened as a catalog; only nominated prior issues may enter any fit.
label_source_path <- file.path(root,"results/fundamental-issues-20261011/inputs/labels.rds")
parent_evaluation <- jsonlite::fromJSON(file.path(root,"results/fm17-three-issues-20261013/evaluation.json"))
stopifnot(digest::digest(file=label_source_path,algo="sha256")==parent_evaluation$label_sha256)
label_sources <- readRDS(label_source_path)
source_rows <- map_dfr(names(label_sources),~tibble(issue_code=.x,observed_label_ts=label_sources[[.x]]$receipt$observed_at))
features <- x$features |> filter(eligible) |> mutate(issue_id=as.character(issue_id),
 line_group=if_else(handicap==0,"ZERO","NONZERO"),width_group=if_else(interval80_positions<=4,"WIDTH4","WIDTH5PLUS"))
p0 <- x$probabilities |> filter(model=="FM171") |> select(fixture_id,outcome,probability)
history <- features |> inner_join(labels,by="fixture_id",relationship="one-to-one") |>
 left_join(p0 |> filter(outcome=="D") |> select(fixture_id,baseline_draw=probability),by="fixture_id",relationship="one-to-one") |>
 transmute(fixture_id,issue_code=issue_id,issue_year=2026L,data_available_ts=cutoff_utc,
  decision_ts=cutoff_utc,line_group,width_group,baseline_draw,draw_target=as.double(actual_outcome=="D")) |>
 left_join(source_rows,by="issue_code",relationship="many-to-one")
stopifnot(nrow(features)==323L,nrow(history)==322L,!anyNA(history),!anyDuplicated(history$fixture_id),
 all(history$baseline_draw>0 & history$baseline_draw<1))
# These are explicit source-snapshot nominations, not learned partitions or client-created clock filters.
issue_tables <- split(history,history$issue_code)
bindings <- list(forecast=digest::digest(file=source_path,algo="sha256"),
 labels=digest::digest(file=label_path,algo="sha256"),label_source=digest::digest(file=label_source_path,algo="sha256"),
 policy=digest::digest(file=policy_path,algo="sha256"),client=digest::digest(file=file.path(root,"r/fm171_draw_history_freeze.R"),algo="sha256"),
 direction_implementation=beidan:::.score_margin_code(root),
 R_runtime=digest::digest(list(R=as.character(getRversion()),packages=map_chr(c("stats","dplyr","tibble","reticulate"),~as.character(packageVersion(.x)))),algo="sha256"))
horizon <- shared$Cutoff$decision_epoch("DIAGNOSTIC_CLOCK_HORIZON",policy$clock_horizon)
# Clock construction is shared and source-row invariant: compute once, never per target.
history_by_delay <- list()
for(delay in as.numeric(unlist(policy$diagnostic_label_delays_hours))) {
 h <- history
 h$label_available_ts <- map_chr(h$decision_ts,~reticulate::py_to_r(clock$diagnostic_label_clock(.x,cutoff=horizon,delay_hours=delay)))
 history_by_delay[[as.character(delay)]] <- split(h,h$issue_code)
}
entries <- audit <- probabilities <- list()
for(id in features$fixture_id) {
 e <- x$entries[[id]];f <- features |> filter(fixture_id==id)
 plan <- keep(policy$issue_plan,~.x$target_issue==f$issue_id)[[1]]
 nominated <- as.character(unlist(plan$prior_issues))
 stopifnot(!f$issue_id%in%nominated,all(nominated %in% names(issue_tables)))
 source_history <- if(length(nominated))bind_rows(issue_tables[nominated])else history[0,]
 # Nomination guard fails closed even if a counterfeit target/future source has an early label clock.
 if(any(!source_history$issue_code %in% nominated))stop("Historical source issue is outside the nominated prior snapshots")
 cutoff <- shared$Cutoff$decision_epoch(e$cutoff$issue_id,f$cutoff_utc)
 results <- list(FM171=e$results$FM171$final)
 original <- p0 |> filter(fixture_id==id)
 probabilities[[paste(id,"FM171")]] <- original |> mutate(model="FM171",.before=1)
 for(delay in as.numeric(unlist(policy$diagnostic_label_delays_hours))) {
  h <- if(length(nominated))bind_rows(history_by_delay[[as.character(delay)]][nominated])else source_history
  state <- "NO_PRIOR_SAME_VERSION_HISTORY";reason <- "First nominated issue; no prior FM171 forecasts"
  ctx <- NULL;admitted <- h;weights <- numeric();receipt <- NULL;global_delta <- 0
  admission_ledger <- tibble(fixture_id=character(),weight=double())
  if(nrow(h)) {
   frame <- pandas$DataFrame(jsonlite::fromJSON(jsonlite::toJSON(h,dataframe="rows",auto_unbox=TRUE,digits=NA),simplifyVector=FALSE))
   sources <- c(bindings,list(nominated=beidan:::.score_margin_hash(nominated),history_frame=reticulate::py_to_r(core_module$stable_frame_hash(frame)),
    delay=beidan:::.score_margin_hash(delay)))
   ctx <- tryCatch(shared$prepare_learning_context(frame,cutoff,source_hashes=sources,repository_root=pathlib$Path(root),
    implementation_modules=list("beidan_backend.temporal_learning.issue_partitions","beidan_backend.temporal_learning.diagnostic_labels"),
    implementation_distributions=list("numpy","pandas"),
    availability=shared$AvailabilityFilter(shared$AvailabilityPolicy$historical_proxy("FM171_DECISION_PLUS_DELAY_NOT_OBSERVED"),data_available_column="data_available_ts"),
    intended_use="HISTORICAL_DIAGNOSTIC",partition_policy=shared$PartitionPolicy("FIXED_PRIOR_FIT",0L,0L,1L),
    weighting_policy=shared$WeightingPolicy$expanding_equal(minimum_ess=policy$minimum_global_ess)),error=function(error)error)
   if(inherits(ctx,"error")) {
    if(!grepl("cutoff admits no prior observations|effective sample size",conditionMessage(ctx)))stop(ctx)
    state <- "INSUFFICIENT_PRIOR_HISTORY";reason <- conditionMessage(ctx);ctx <- NULL
   } else {
    admitted <- bind_rows(jsonlite::fromJSON(reticulate::py_to_r(ctx$partitions[["fit"]]$to_json(orient="records",date_format="iso",double_precision=15L)),simplifyVector=FALSE)) |>
     mutate(across(c(data_available_ts,label_available_ts),~lubridate::ymd_hms(.x,tz="UTC")))
    weights <- as.numeric(reticulate::py_to_r(ctx$weights$to_numpy()))
    admission_ledger <- bind_rows(jsonlite::fromJSON(reticulate::py_to_r(ctx$weight_ledger$to_json(orient="records",date_format="iso",double_precision=15L)),simplifyVector=FALSE)) |>
     mutate(across(any_of(c("label_available_ts","data_available_ts","cutoff_ts")),~lubridate::ymd_hms(.x,tz="UTC")))
    admission_ledger$fixture_id <- admitted$fixture_id
    receipt <- reticulate::py_to_r(ctx$receipt$payload)
    stopifnot(nrow(admitted)==length(weights),!anyDuplicated(admitted$fixture_id),all(admitted$issue_code%in%nominated),
     all(abs(weights-1)<1e-12),lubridate::ymd_hms(receipt$maximum_source_time,tz="UTC")<lubridate::ymd_hms(f$cutoff_utc,tz="UTC"),
     lubridate::ymd_hms(receipt$maximum_training_label_timestamp,tz="UTC")<lubridate::ymd_hms(f$cutoff_utc,tz="UTC"))
    if(min(sum(admitted$draw_target==1),sum(admitted$draw_target==0))<policy$minimum_global_class_count) {
     state <- "INSUFFICIENT_PRIOR_CLASSES";reason <- "Fewer than fixed minimum observations in one outcome class"
    } else {
     state <- "ESTIMATED";reason <- "Only shared-admitted nominated prior FM171 outcomes"
     n <- sum(weights);mu <- weighted.mean(admitted$baseline_draw,weights);observed <- weighted.mean(admitted$draw_target,weights)
     shrunk <- (n*observed+policy$pseudocount_matches*mu)/(n+policy$pseudocount_matches)
     global_delta <- qlogis(shrunk)-qlogis(mu)
    }
   }
  }
  for(model in as.character(unlist(policy$models))) {
   name <- paste0(model,"_D",delay);delta <- global_delta;group_n <- 0L;group_ess <- 0;local_delta <- 0;group_state <- "GLOBAL_ONLY"
   group_key <- if(model=="LINE")f$line_group else if(model=="WIDTH")f$width_group else "ALL"
   fit_receipt <- NULL;fit_ledger <- tibble(fixture_id=character(),weight=double())
   if(state=="ESTIMATED") {
    if(model!="GLOBAL") {
     column <- if(model=="LINE")"line_group" else "width_group"
     in_group <- admitted[[column]]==group_key
     group_n <- sum(in_group)
     if(group_n>0)group_ess <- reticulate::py_to_r(core_module$effective_sample_size(reticulate::np_array(weights[in_group],dtype="float64")))
     if(group_ess>=policy$minimum_group_ess-1e-10) {
      w <- weights[in_group];ng <- sum(w)
      adjusted_mu <- weighted.mean(plogis(qlogis(admitted$baseline_draw[in_group])+global_delta),w)
      observed_g <- weighted.mean(admitted$draw_target[in_group],w)
      shrunk_g <- (ng*observed_g+policy$pseudocount_matches*adjusted_mu)/(ng+policy$pseudocount_matches)
      local_delta <- qlogis(shrunk_g)-qlogis(adjusted_mu);delta <- global_delta+local_delta;group_state <- "GROUP_ESTIMATED"
     } else group_state <- "SPARSE_GROUP_SHRUNK_TO_GLOBAL"
    }
    params <- list(model=model,group_key=group_key,global_delta=global_delta,local_delta=local_delta,
     delta=delta,pseudocount_matches=policy$pseudocount_matches,global_n=n,global_mean_prediction=mu,global_observed_rate=observed,
     global_shrunk_rate=shrunk,group_n=group_n,group_ess=group_ess,group_state=group_state,delay_hours=delay,
     empirical_mass=n/(n+policy$pseudocount_matches),prior_mass=policy$pseudocount_matches/(n+policy$pseudocount_matches),
     group_empirical_mass=if(group_state=="GROUP_ESTIMATED")group_n/(group_n+policy$pseudocount_matches)else 0,
     group_prior_mass=if(group_state=="GROUP_ESTIMATED")policy$pseudocount_matches/(group_n+policy$pseudocount_matches)else 1)
    fit_receipt <- reticulate::py_to_r(model_receipts$bind_model_receipt(ctx,cutoff,
     model_identity=paste0("FM171_DRAW_HISTORY_",model),model_parameters=params))
    fit_receipt$R_bindings <- bindings;fit_receipt$parameters <- params
    fit_ledger <- admission_ledger
    p_draw <- original$probability[original$outcome=="D"];q <- plogis(qlogis(p_draw)+delta)
    target <- original |> mutate(probability=if_else(outcome=="D",q,(1-q)*probability/(1-p_draw)))
    base <- list(grid=e$results$FM171$final$grid |> select(home_goals,away_goals,probability),cutoff=e$cutoff,
     model_id="FROZEN_FM171_PLUS_HISTORICAL_DRAW",source_hashes=c(bindings,list(fit=beidan:::.score_margin_hash(fit_receipt))),
     max_source_available_utc=max(e$base$max_source_available_utc,lubridate::ymd_hms(receipt$maximum_source_time,tz="UTC")),intended_use="HISTORICAL_DIAGNOSTIC")
    dd <- -as.integer(f$handicap);eid <- "prior-draw-calibration"
    judgement <- list(model_id=name,rationale="Prior-only shrinkage of draw-event log odds; no desired rank constraint",
     bins=tibble(bin_id=c("lower","draw","upper"),min_margin=c(-Inf,dd,dd+1),max_margin=c(dd-1,dd,Inf),
      target_mass=target$probability[match(c("L","D","W"),target$outcome)],evidence_id=eid,reason="Fixed prior-only empirical-rate calibration"))
    source_time <- format(base$max_source_available_utc,"%Y-%m-%dT%H:%M:%SZ",tz="UTC")
    rows <- list(list(evidence_id=eid,fixture_id=id,source_hash=beidan:::.score_margin_hash(fit_receipt),row_key=eid,
     issue_code="PRIOR_CALIBRATION_EVIDENCE",issue_year=2026L,label_available_ts=source_time,data_available_ts=source_time))
    binding <- c(bindings,list(base_artifact=beidan:::.score_margin_hash(base),margin_judgement=beidan:::.score_margin_hash(judgement),
     fitted_model=beidan:::.score_margin_hash(fit_receipt),event_definition=beidan:::.score_margin_hash(list(handicap=f$handicap,cutoff=e$cutoff))))
    score_ctx <- adjustment$build_adjustment_evidence_context(rows,as.list(e$fixture),cutoff,binding,
     shared$AvailabilityPolicy$historical_proxy("FM171_EMPIRICAL_DRAW_DIAGNOSTIC_ONLY"),"HISTORICAL_DIAGNOSTIC",root)
    final <- adjust_score_margin_distribution(base,judgement,score_ctx,e$fixture,e$cutoff,root)
    projected <- project_score_outcomes(final,as.integer(f$handicap),root) |> select(outcome,probability)
    stopifnot(max(abs(projected$probability[match(target$outcome,projected$outcome)]-target$probability))<1e-10)
   } else {
    final <- e$results$FM171$final;projected <- original |> select(outcome,probability)
    p_draw <- original$probability[original$outcome=="D"];q <- p_draw
   }
   results[[name]] <- list(final=final,fit_receipt=fit_receipt,fit_ledger=fit_ledger,state=state,
    delta=delta,original_draw=p_draw,calibrated_draw=q,group_state=group_state)
   probabilities[[paste(id,name)]] <- projected |> mutate(fixture_id=id,model=name,.before=1)
   audit[[paste(id,name)]] <- tibble(fixture_id=id,issue_id=f$issue_id,model=name,delay_hours=delay,
    cutoff_utc=f$cutoff_utc,handicap=f$handicap,group_key=group_key,state=state,reason=reason,
    training_n=if(state=="ESTIMATED")n else 0,group_n=group_n,group_ess=group_ess,group_state=group_state,
    global_delta=global_delta,local_delta=local_delta,delta=delta,original_draw=p_draw,calibrated_draw=q,
    nominated_prior_issues=paste(nominated,collapse="|"),maximum_label_time=if(is.null(receipt))NA_character_ else receipt$maximum_training_label_timestamp,
    observed_labels_admitted=sum(source_history$observed_label_ts<f$cutoff_utc))
  }
 }
 entries[[id]] <- list(fixture=e$fixture,cutoff=e$cutoff,results=results)
 if(length(entries)%%50L==0L)message("Processed ",length(entries))
}
batch <- list(entries=entries,probabilities=bind_rows(probabilities),audit=bind_rows(audit),bindings=bindings,policy=policy)
dir.create(out,recursive=TRUE,showWarnings=FALSE);path <- file.path(out,"forecasts.rds")
if(replay_mode) {
 stopifnot(identical(batch,readRDS(path)))
 jsonlite::write_json(list(status="FULL_IDENTICAL_REPLAY",forecasts=length(entries),sha256=digest::digest(file=path,algo="sha256")),
  file.path(out,"replay.json"),pretty=TRUE,auto_unbox=TRUE)
} else {
 if(file.exists(path))stopifnot(identical(batch,readRDS(path)))else saveRDS(batch,path)
 write_csv(batch$audit,file.path(out,"audit.csv"));write_csv(batch$probabilities,file.path(out,"probabilities.csv"))
 jsonlite::write_json(list(sha256=digest::digest(file=path,algo="sha256"),bindings=bindings,forecasts=length(entries),
  retrospective_label_catalog_opened=TRUE,target_labels_admitted_to_fit=FALSE,observed_availability_validated=FALSE,
  versions_modified=FALSE,root_prior_outcome_knowledge=TRUE),file.path(out,"manifest.json"),pretty=TRUE,auto_unbox=TRUE)
}
