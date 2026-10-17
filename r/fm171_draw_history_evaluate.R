# Rscript r/fm171_draw_history_evaluate.R ROOT OUTPUT
# Paired descriptive evaluation after full independent forecast replay.
args <- commandArgs(TRUE);stopifnot(length(args)==2L)
root <- normalizePath(args[1],mustWork=TRUE);out <- args[2]
suppressPackageStartupMessages(library(tidyverse));library(beidan,lib.loc=file.path(root,"r_lib"))
m <- jsonlite::fromJSON(file.path(out,"manifest.json"));rp <- jsonlite::fromJSON(file.path(out,"replay.json"))
stopifnot(rp$status=="FULL_IDENTICAL_REPLAY",rp$sha256==m$sha256,rp$forecasts==323L,
 digest::digest(file=file.path(out,"forecasts.rds"),algo="sha256")==m$sha256)
x <- readRDS(file.path(out,"forecasts.rds"))
stopifnot(digest::digest(file=file.path(root,"r/fm171_draw_history_freeze.R"),algo="sha256")==x$bindings$client,
 digest::digest(file=file.path(root,"config/fm171_draw_history_study.json"),algo="sha256")==x$bindings$policy)
label_path <- file.path(root,"results/fm17-three-issues-20261013/labels.csv")
stopifnot(digest::digest(file=label_path,algo="sha256")==x$bindings$labels)
y <- read_csv(label_path,col_types=cols(.default=col_character())) |> filter(fixture_id%in%names(x$entries)) |>
 select(fixture_id,actual_outcome)
stopifnot(nrow(y)==322L,!anyDuplicated(y$fixture_id))
source_dir <- file.path(root,"results/fm171-margin-shape-20261017")
previous <- jsonlite::fromJSON(file.path(source_dir,"evaluation.json"))
stopifnot(digest::digest(file=file.path(source_dir,"features_labeled.csv"),algo="sha256")==previous$output_hashes$features_labeled)
f <- read_csv(file.path(source_dir,"features_labeled.csv"),show_col_types=FALSE) |> filter(eligible) |>
 mutate(issue_id=as.character(issue_id)) |> select(fixture_id,issue_id,home,away,event_type,handicap,shape,line_locality,draw_group,interval80_positions)
audit <- x$audit
status <- audit |> filter(model=="GLOBAL_D48") |> select(fixture_id,primary_estimated=state) |>
 mutate(primary_estimated=primary_estimated=="ESTIMATED")
p <- x$probabilities |> filter(fixture_id%in%y$fixture_id)
d <- beidan:::DcAccuracyDiagnostic(p,y)
scores <- d$scores |> left_join(f,by="fixture_id",relationship="many-to-one") |>
 left_join(status,by="fixture_id",relationship="many-to-one") |>
 left_join(p |> filter(outcome=="D") |> select(fixture_id,model,draw_probability=probability),by=c("fixture_id","model"),relationship="one-to-one") |>
 mutate(draw_actual=as.double(actual_outcome=="D"),draw_brier=(draw_probability-draw_actual)^2,
  draw_logloss=-draw_actual*log(draw_probability)-(1-draw_actual)*log1p(-draw_probability))
ref <- scores |> filter(model=="FM171") |> select(fixture_id,ref_top1=top1,ref_top2=top2,ref_brier=brier,ref_logloss=logloss)
scores <- scores |> left_join(ref,by="fixture_id",relationship="many-to-one") |>
 mutate(saved_top1=top1 & !ref_top1,lost_top1=!top1 & ref_top1,saved_top2=top2 & !ref_top2,lost_top2=!top2 & ref_top2,
  brier_delta=brier-ref_brier,logloss_delta=logloss-ref_logloss)
metrics <- list()
for(cohort in c("ALL_322","PRIMARY_ESTIMATED")) {
 s <- scores |> filter(cohort=="ALL_322" | primary_estimated)
 for(dimension in c("all","issue_id","event_type","draw_group","handicap_zero","width")) {
  s1 <- s |> mutate(stratum=if(dimension=="all")"ALL" else if(dimension=="handicap_zero")if_else(handicap==0,"ZERO","NONZERO") else
   if(dimension=="width")as.character(interval80_positions) else as.character(.data[[dimension]]))
  metrics[[paste(cohort,dimension)]] <- s1 |> group_by(model,stratum) |>
   summarise(n=n(),hits1=sum(top1),hits2=sum(top2),top1=mean(top1),top2=mean(top2),brier=mean(brier),logloss=mean(logloss),
    actual_draws=sum(draw_actual),mean_draw_probability=mean(draw_probability),actual_draw_rate=mean(draw_actual),
    draw_brier=mean(draw_brier),draw_logloss=mean(draw_logloss),
    saved_top1=sum(saved_top1),lost_top1=sum(lost_top1),saved_top2=sum(saved_top2),lost_top2=sum(lost_top2),.groups="drop") |>
   mutate(cohort=cohort,dimension=dimension,.before=1)
 }
}
metrics <- bind_rows(metrics)
calibration <- scores |> mutate(bin=cut(draw_probability,breaks=c(0,.2,.25,.3,.35,.4,.5,1),include.lowest=TRUE,right=FALSE)) |>
 group_by(model,primary_estimated,bin) |> summarise(n=n(),predicted=mean(draw_probability),observed=mean(draw_actual),.groups="drop")
changes <- scores |> filter(model!="FM171",saved_top2|lost_top2) |>
 select(fixture_id,issue_id,home,away,model,handicap,actual_outcome,draw_probability,saved_top2,lost_top2,draw_group)
support <- audit |> group_by(issue_id,model,state,group_state) |> summarise(n=n(),minimum_training=min(training_n),
 maximum_training=max(training_n),minimum_group_ess=min(group_ess),maximum_group_ess=max(group_ess),
 targets_with_observed_prior_labels=sum(observed_labels_admitted>0),.groups="drop")
clocks <- audit |> filter(model=="GLOBAL_D48") |> group_by(issue_id) |>
 summarise(forecasts=n(),estimated=sum(state=="ESTIMATED"),
  with_any_observed_label_history=sum(observed_labels_admitted>0),maximum_observed_labels=max(observed_labels_admitted),
  first_cutoff=min(cutoff_utc),last_cutoff=max(cutoff_utc),.groups="drop")
tables <- list(metrics=metrics,scores=scores,calibration=calibration,changes=changes,support=support,clocks=clocks)
for(name in names(tables))write_csv(tables[[name]],file.path(out,paste0(name,".csv")))
jsonlite::write_json(list(mode="POSTHOC_PRIOR_ISSUE_CALIBRATION_DIAGNOSTIC",forecast_sha256=m$sha256,
 evaluator_sha256=digest::digest(file=file.path(root,"r/fm171_draw_history_evaluate.R"),algo="sha256"),
 output_hashes=as.list(set_names(map_chr(names(tables),~digest::digest(file=file.path(out,paste0(.x,".csv")),algo="sha256")),names(tables))),
 primary_n=n_distinct(scores$fixture_id[scores$primary_estimated]),all_n=322L,
 observed_availability_validated=FALSE,versions_modified=FALSE,selected_model=NULL,
 interpretation="Only nominated prior issues and shared admitted proxy label times; all preset models/clocks reported, no tuning. First issue has no fitted correction; observed label coverage separate, predictor availability remains retrospective proxy."),
 file.path(out,"evaluation.json"),pretty=TRUE,auto_unbox=TRUE)
print(metrics |> filter(dimension=="all") |> select(cohort,model,n,hits1,hits2,brier,logloss,draw_brier,mean_draw_probability,actual_draw_rate),n=20,width=180)
