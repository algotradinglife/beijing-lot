# Rscript r/fm171_margin_shape_evaluate.R ROOT OUTPUT
# Descriptive scoring only, after immutable forecast and independent replay gates.
args <- commandArgs(TRUE);stopifnot(length(args)==2L)
root <- normalizePath(args[1],mustWork=TRUE);out <- args[2]
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc=file.path(root,"r_lib"))
manifest <- jsonlite::fromJSON(file.path(out,"manifest.json"));replay <- jsonlite::fromJSON(file.path(out,"replay.json"))
fp <- file.path(out,"forecasts.rds")
stopifnot(replay$status=="FULL_IDENTICAL_REPLAY",replay$forecasts==346L,replay$sha256==manifest$sha256,
 digest::digest(file=fp,algo="sha256")==manifest$sha256)
x <- readRDS(fp)
stopifnot(identical(x$bindings$client,digest::digest(file=file.path(root,"r/fm171_margin_shape_freeze.R"),algo="sha256")),
 identical(x$bindings$policy,digest::digest(file=file.path(root,"config/fm171_margin_shape_study.json"),algo="sha256")))
prior <- file.path(root,"results/fm-lambda-integration-20261017")
prior_eval <- jsonlite::fromJSON(file.path(prior,"evaluation.json"))
label_path <- file.path(root,"results/fm17-three-issues-20261013/labels.csv")
coverage_path <- file.path(root,"results/fm17-event-types-20261015/coverage.csv")
stopifnot(digest::digest(file=label_path,algo="sha256")==prior_eval$source_hashes$labels,
 digest::digest(file=coverage_path,algo="sha256")==prior_eval$source_hashes$coverage,
 digest::digest(file=file.path(prior,"scores.csv"),algo="sha256")==prior_eval$output_hashes$scores)
# Labels opened only after successful replay; known-outcome design remains diagnostic.
y <- read_csv(label_path,col_types=cols(.default=col_character()))
events <- read_csv(coverage_path,col_types=cols(.default=col_character())) |> select(fixture_id,event_type,league)
stopifnot(!anyDuplicated(y$fixture_id),nrow(y)==345L,!anyDuplicated(events$fixture_id))
f <- x$features |> inner_join(y,by="fixture_id",relationship="one-to-one") |>
 left_join(events,by="fixture_id",relationship="one-to-one")
stopifnot(nrow(f)==345L,!anyNA(f),sum(f$eligible)==322L)
p <- x$probabilities |> filter(fixture_id %in% y$fixture_id)
ranks <- p |> mutate(tie=match(outcome,c("W","D","L"))) |> arrange(model,fixture_id,desc(probability),tie) |>
 group_by(fixture_id,model) |> mutate(rank=row_number()) |> ungroup()
draw_ranks <- ranks |> filter(outcome=="D") |> select(fixture_id,model,draw_category_rank=rank)
f <- f |> left_join(draw_ranks |> filter(model=="FM171") |> select(-model),by="fixture_id",relationship="one-to-one") |>
 mutate(target_conflict=draw_top2 & draw_category_rank==3L,
  draw_group=case_when(target_conflict~"DRAW_BIN_TOP2_CATEGORY3",draw_top2~"DRAW_BIN_TOP2_ALREADY_INCLUDED",TRUE~"DRAW_BIN_OUTSIDE_TOP2"))
d <- beidan:::DcAccuracyDiagnostic(p,y |> select(fixture_id,actual_outcome))
scores <- d$scores |> left_join(f,by=c("fixture_id","actual_outcome"),relationship="many-to-one")
# Include unchanged alpha branch as a frozen comparator; no new alpha estimates or tuning.
al <- read_csv(file.path(prior,"scores.csv"),show_col_types=FALSE) |>
 filter(comparison=="near_sale",model %in% c("ALPHA+SAME_SUPPORT_RAW","BEIDAN_LATER")) |>
 select(model,fixture_id,actual_outcome,predicted_outcome,actual_rank,actual_probability,brier,logloss,top1,top2,top3) |>
 mutate(model=recode(model,`ALPHA+SAME_SUPPORT_RAW`="ALPHA_SAME_COMPETITION")) |>
 left_join(f,by=c("fixture_id","actual_outcome"),relationship="many-to-one")
stopifnot(nrow(al)==690L)
scores <- bind_rows(scores,al)
ref <- scores |> filter(model=="FM171") |> select(fixture_id,ref_top1=top1,ref_top2=top2,ref_brier=brier,ref_logloss=logloss)
scores <- scores |> left_join(ref,by="fixture_id",relationship="many-to-one") |>
 mutate(saved_top1=top1 & !ref_top1,lost_top1=!top1 & ref_top1,saved_top2=top2 & !ref_top2,lost_top2=!top2 & ref_top2,
  brier_delta=brier-ref_brier,logloss_delta=logloss-ref_logloss)
metrics <- list()
for(cohort in c("ELIGIBLE_322","ALL_MIXED_345")) {
 s <- scores |> filter(cohort=="ALL_MIXED_345" | eligible)
 for(dimension in c("all","issue_id","event_type","shape","line_locality","draw_group","selected_source")) {
  g <- s |> mutate(stratum=if(dimension=="all")"ALL" else as.character(.data[[dimension]])) |>
   group_by(model,stratum) |> summarise(n=n(),hits1=sum(top1),hits2=sum(top2),top1=mean(top1),top2=mean(top2),
    brier=mean(brier),logloss=mean(logloss),saved_top1=sum(saved_top1),lost_top1=sum(lost_top1),
    saved_top2=sum(saved_top2),lost_top2=sum(lost_top2),brier_delta=mean(brier_delta),logloss_delta=mean(logloss_delta),.groups="drop") |>
   mutate(cohort=cohort,dimension=dimension,.before=1)
  metrics[[paste(cohort,dimension)]] <- g
 }
}
metrics <- bind_rows(metrics)
# Joint shape/locality cells, fixed bins; report sparse support rather than pool/select favorable cells.
shape_cells <- scores |> filter(eligible) |> group_by(model,shape,line_locality,draw_group) |>
 summarise(n=n(),hits1=sum(top1),hits2=sum(top2),saved_top2=sum(saved_top2),lost_top2=sum(lost_top2),
  brier=mean(brier),logloss=mean(logloss),.groups="drop")
# Per-class core/tail contribution from the selected source, independent of observed result.
contributions <- list()
for(id in names(x$entries)) {
 e <- x$entries[[id]];f0 <- e$feature;core <- e$results$FM171$core$core_margins
 m <- e$base$grid |> mutate(margin=home_goals-away_goals,
  outcome=case_when(margin>f0$draw_margin~"W",margin==f0$draw_margin~"D",TRUE~"L"),core=margin %in% core) |>
  group_by(outcome,core) |> summarise(mass=sum(probability),.groups="drop") |>
  mutate(fixture_id=id,.before=1)
 contributions[[id]] <- m
}
contributions <- bind_rows(contributions)
cases <- scores |> filter(target_conflict) |> arrange(fixture_id,model) |>
 select(fixture_id,issue_id,home,away,league,eligible,handicap,model,actual_outcome,predicted_outcome,
 actual_rank,top1,top2,saved_top2,lost_top2,draw_probability,draw_margin_rank,draw_category_rank,
 mode,mean_margin,interval80_positions,local_mass,shape,line_locality,raw_w,raw_d,raw_l)
shape_summary <- f |> group_by(eligible,draw_group,shape,line_locality) |>
 summarise(n=n(),actual_draws=sum(actual_outcome=="D"),mean_draw_probability=mean(draw_probability),
  mean_positions=mean(interval80_positions),mean_local_mass=mean(local_mass),.groups="drop")
tables <- list(metrics=metrics,scores=scores,shape_cells=shape_cells,cases=cases,features_labeled=f,
 contributions=contributions,shape_summary=shape_summary,draw_ranks=draw_ranks)
for(name in names(tables))write_csv(tables[[name]],file.path(out,paste0(name,".csv")))
jsonlite::write_json(list(mode="POSTHOC_FIXED_POLICY_DIAGNOSTIC",forecast_sha256=manifest$sha256,
 client_sha256=digest::digest(file=file.path(root,"r/fm171_margin_shape_evaluate.R"),algo="sha256"),
 labels_sha256=digest::digest(file=label_path,algo="sha256"),
 output_hashes=as.list(set_names(map_chr(names(tables),~digest::digest(file=file.path(out,paste0(.x,".csv")),algo="sha256")),names(tables))),
 selected_policy=NULL,versions_modified=FALSE,primary_n=322L,secondary_n=345L,
 interpretation="All preset candidates and sparse cells reported. No fitted thresholds, production promotion or independent prospective validation."),
 file.path(out,"evaluation.json"),pretty=TRUE,auto_unbox=TRUE)
print(metrics |> filter(dimension=="all"))
