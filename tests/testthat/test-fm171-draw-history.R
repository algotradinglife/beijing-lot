testthat::test_that("prior-only draw corrections reconcile shrinkage, clocks and full score masses", {
 root <- rprojroot::find_root(rprojroot::has_file("AGENTS.md"));out <- file.path(root,"results/fm171-draw-calibration-20261017")
 m <- jsonlite::fromJSON(file.path(out,"manifest.json"));rp <- jsonlite::fromJSON(file.path(out,"replay.json"))
 testthat::expect_identical(rp$status,"FULL_IDENTICAL_REPLAY")
 testthat::expect_identical(digest::digest(file=file.path(out,"forecasts.rds"),algo="sha256"),m$sha256)
 testthat::expect_false(m$target_labels_admitted_to_fit);testthat::expect_true(m$retrospective_label_catalog_opened)
 testthat::expect_false(m$observed_availability_validated)
 x <- readRDS(file.path(out,"forecasts.rds"));source <- readRDS(file.path(root,"results/fm171-margin-shape-20261017/forecasts.rds"))
 y <- readr::read_csv(file.path(root,"results/fm17-three-issues-20261013/labels.csv"),show_col_types=FALSE)
 pd <- source$probabilities[source$probabilities$model=="FM171" & source$probabilities$outcome=="D",]
 testthat::expect_length(x$entries,323L)
 testthat::expect_equal(nrow(x$probabilities),323L*7L*3L)
 labels_source <- readRDS(file.path(root,"results/fundamental-issues-20261011/inputs/labels.rds"))
 observed_times <- vapply(labels_source,function(z)z$receipt$observed_at,character(1))
 source_counts <- source$features |> dplyr::filter(eligible,fixture_id %in% y$fixture_id) |> dplyr::count(issue_id)
 keys <- list()
 for(id in names(x$entries)) {
  e <- x$entries[[id]]
  nominated_issues <- if(e$cutoff$issue_id=="26098")character() else if(e$cutoff$issue_id=="26101")"26098" else c("26098","26101")
  observed_before <- lubridate::ymd_hms(observed_times[nominated_issues],tz="UTC")<e$cutoff$cutoff_utc
  expected_observed <- sum(source_counts$n[match(nominated_issues[observed_before],source_counts$issue_id)])
  testthat::expect_true(all(x$audit$observed_labels_admitted[x$audit$fixture_id==id]==expected_observed))
  original <- source$entries[[id]]$results$FM171$final$grid
  h <- source$features$handicap[match(id,source$features$fixture_id)]
  for(name in setdiff(names(e$results),"FM171")) {
   z <- e$results[[name]];grid <- z$final$grid
   testthat::expect_equal(sum(grid$probability),1,tolerance=1e-10)
   testthat::expect_true(all(grid$probability>=0))
   testthat::expect_identical(z$final$cutoff,e$cutoff)
   predicted <- x$probabilities[x$probabilities$fixture_id==id & x$probabilities$model==name,]
   margins <- grid$home_goals-grid$away_goals+h
   expected <- c(W=sum(grid$probability[margins>0]),D=sum(grid$probability[margins==0]),L=sum(grid$probability[margins<0]))
   testthat::expect_equal(predicted$probability,unname(expected[predicted$outcome]),tolerance=1e-10)
   testthat::expect_equal(expected[['D']],z$calibrated_draw,tolerance=1e-10)
   testthat::expect_equal(expected[['W']]/expected[['L']],sum(original$probability[margins>0])/sum(original$probability[margins<0]),tolerance=1e-10)
   # Conditional score probabilities are preserved separately inside draw/non-draw events.
   ratios <- grid$probability/original$probability
   testthat::expect_lt(max(ratios[margins==0])-min(ratios[margins==0]),1e-8)
   testthat::expect_lt(max(ratios[margins!=0])-min(ratios[margins!=0]),1e-8)
   if(z$state!="ESTIMATED") {
    testthat::expect_null(z$fit_receipt)
    testthat::expect_identical(z$final,source$entries[[id]]$results$FM171$final)
    next
   }
   r <- z$fit_receipt;p <- r$parameters;l <- z$fit_ledger
   testthat::expect_equal(p$empirical_mass+p$prior_mass,1,tolerance=1e-12)
   testthat::expect_equal(p$group_empirical_mass+p$group_prior_mass,1,tolerance=1e-12)
   testthat::expect_equal(sum(l$weight),p$global_n,tolerance=1e-10)
   testthat::expect_equal(sum(l$total_mass),1,tolerance=1e-10)
   testthat::expect_true(all(l$label_available_ts<e$cutoff$cutoff_utc))
   testthat::expect_false(e$cutoff$issue_id%in%l$issue_code)
   nominated <- if(e$cutoff$issue_id=="26101")"26098" else c("26098","26101")
   testthat::expect_true(all(l$issue_code%in%nominated))
   testthat::expect_lt(as.numeric(lubridate::ymd_hms(r$maximum_training_label_timestamp,tz="UTC")),as.numeric(e$cutoff$cutoff_utc))
   yy <- as.double(y$actual_outcome[match(l$fixture_id,y$fixture_id)]=="D")
   pp <- pd$probability[match(l$fixture_id,pd$fixture_id)]
   testthat::expect_false(anyNA(c(yy,pp)))
   mu <- stats::weighted.mean(pp,l$weight);observed <- stats::weighted.mean(yy,l$weight)
   shrunk <- (p$global_n*observed+p$pseudocount_matches*mu)/(p$global_n+p$pseudocount_matches)
   testthat::expect_equal(p$global_delta,stats::qlogis(shrunk)-stats::qlogis(mu),tolerance=1e-10)
   if(p$group_state=="GROUP_ESTIMATED") {
    features <- source$features[match(l$fixture_id,source$features$fixture_id),]
    matched <- if(p$model=="LINE")ifelse(features$handicap==0,"ZERO","NONZERO")==p$group_key else
     ifelse(features$interval80_positions<=4,"WIDTH4","WIDTH5PLUS")==p$group_key
    testthat::expect_equal(sum(matched),p$group_n)
    gm <- stats::weighted.mean(stats::plogis(stats::qlogis(pp[matched])+p$global_delta),l$weight[matched])
    go <- stats::weighted.mean(yy[matched],l$weight[matched])
    gs <- (sum(l$weight[matched])*go+p$pseudocount_matches*gm)/(sum(l$weight[matched])+p$pseudocount_matches)
    testthat::expect_equal(p$local_delta,stats::qlogis(gs)-stats::qlogis(gm),tolerance=1e-10)
   } else testthat::expect_equal(p$local_delta,0)
   testthat::expect_equal(z$calibrated_draw,stats::plogis(stats::qlogis(z$original_draw)+p$delta),tolerance=1e-10)
   keys[[paste(id,name)]] <- tibble::tibble(cutoff=as.numeric(e$cutoff$cutoff_utc),cache=r$cache_key)
  }
 }
 key <- dplyr::bind_rows(keys)
 testthat::expect_true(all(dplyr::count(dplyr::distinct(key,cutoff,cache),cache)$n==1L))
})

testthat::test_that("source nomination and shared time admission resist future or post-cutoff label mutation", {
 root <- rprojroot::find_root(rprojroot::has_file("AGENTS.md"))
 lines <- readLines(file.path(root,"r/fm171_draw_history_freeze.R"))
 guard <- parse(text=lines[grep('if\\(any\\(!source_history\\$issue_code',lines)])
 scope <- new.env(parent=baseenv());scope$nominated<-"26098"
 scope$source_history <- tibble::tibble(issue_code=c("26098","26101","26102"),label_available_ts="2000-01-01T00:00:00Z")
 testthat::expect_error(eval(guard,scope),"outside the nominated prior snapshots")
 scope$source_history <- tibble::tibble(issue_code="26098")
 testthat::expect_no_error(eval(guard,scope))
 beidan::python_backend(file.path(root,".venv/bin/python"))
 shared <- reticulate::import("beidan_backend.temporal_learning",convert=FALSE)
 core <- reticulate::import("beidan_backend.temporal_learning.core",convert=FALSE)
 pandas <- reticulate::import("pandas",convert=FALSE);pathlib <- reticulate::import("pathlib",convert=FALSE)
 cutoff <- shared$Cutoff$decision_epoch("26101","2026-09-28T06:00:00Z")
 hist <- tibble::tibble(fixture_id=paste0("probe",seq_len(62)),issue_code=c(rep("26098",61),"26101"),issue_year=2026L,
  label_available_ts=c(rep("2026-09-26T00:00:00Z",60),"2026-09-29T00:00:00Z","2000-01-01T00:00:00Z"),
  data_available_ts="2026-09-24T00:00:00Z",baseline_draw=.25,draw_target=rep(c(0,0,1),length.out=62))
 start <- grep('^     n <- sum\\(weights\\)',lines);end <- grep('^     global_delta <- qlogis',lines)
 testthat::expect_length(start,1L);testthat::expect_length(end,1L)
 actual_fit <- parse(text=lines[start:end])
 results <- receipts <- list()
 for(variant in 1:2) {
  h <- hist
  if(variant==2L)h$draw_target[61:62]<-1-h$draw_target[61:62]
  frame <- pandas$DataFrame(jsonlite::fromJSON(jsonlite::toJSON(h,dataframe="rows",auto_unbox=TRUE,digits=NA),simplifyVector=FALSE))
  ctx <- shared$prepare_learning_context(frame,cutoff,source_hashes=list(probe=reticulate::py_to_r(core$stable_frame_hash(frame))),
   repository_root=pathlib$Path(root),implementation_modules=list("beidan_backend.temporal_learning.core"),
   availability=shared$AvailabilityFilter(shared$AvailabilityPolicy$historical_proxy("ADVERSARIAL_TEST"),data_available_column="data_available_ts"),
   intended_use="HISTORICAL_DIAGNOSTIC",partition_policy=shared$PartitionPolicy("FIXED_PRIOR_FIT",0L,0L,1L),
   weighting_policy=shared$WeightingPolicy$expanding_equal(minimum_ess=50))
  env <- new.env(parent=asNamespace("stats"));env$policy<-list(pseudocount_matches=50)
  env$admitted <- dplyr::bind_rows(jsonlite::fromJSON(reticulate::py_to_r(ctx$partitions[["fit"]]$to_json(orient="records",date_format="iso",double_precision=15L)),simplifyVector=FALSE))
  env$weights<-as.numeric(reticulate::py_to_r(ctx$weights$to_numpy()))
  eval(actual_fit,env)
  results[[variant]]<-c(env$global_delta,stats::plogis(stats::qlogis(.26)+env$global_delta))
  receipts[[variant]]<-reticulate::py_to_r(ctx$receipt$payload)
 }
 testthat::expect_identical(results[[1]],results[[2]])
 testthat::expect_identical(receipts[[1]]$admitted_history_sha256,receipts[[2]]$admitted_history_sha256)
 testthat::expect_false(identical(receipts[[1]]$cache_key,receipts[[2]]$cache_key))
 testthat::expect_equal(receipts[[1]]$partition$fit_rows,60L)
 testthat::expect_equal(receipts[[1]]$target_rows_excluded,1L)
})

testthat::test_that("draw-history scoring is reproducible and frozen inputs cannot be silently changed", {
 root<-rprojroot::find_root(rprojroot::has_file("AGENTS.md"));out<-file.path(root,"results/fm171-draw-calibration-20261017")
 ev<-jsonlite::fromJSON(file.path(out,"evaluation.json"));temp<-tempfile("draw-replay-");dir.create(temp)
 for(name in c("forecasts.rds","manifest.json","replay.json"))testthat::expect_true(file.copy(file.path(out,name),file.path(temp,name)))
 log<-tempfile();status<-system2("/opt/R/4.6.1/bin/Rscript",shQuote(c(file.path(root,"r/fm171_draw_history_evaluate.R"),root,temp)),
  env=c(paste0("R_LIBS=",shQuote(paste(.libPaths(),collapse=":"))),"TZ=UTC"),stdout=log,stderr=log)
 testthat::expect_equal(status,0L,info=paste(readLines(log),collapse="\n"))
 for(name in names(ev$output_hashes))testthat::expect_identical(digest::digest(file=file.path(temp,paste0(name,".csv")),algo="sha256"),ev$output_hashes[[name]])
 m<-readr::read_csv(file.path(temp,"metrics.csv"),show_col_types=FALSE)
 for(cohort in unique(m$cohort)) {
  a<-dplyr::filter(m,.data$cohort==.env$cohort,dimension=="all");r<-a[a$model=="FM171",]
  testthat::expect_equal(a$hits2-r$hits2,a$saved_top2-a$lost_top2)
  for(model in a$model) {
   g<-dplyr::filter(m,.data$cohort==.env$cohort,.data$model==.env$model,dimension=="issue_id")
   w<-a[a$model==model,]
   testthat::expect_equal(sum(g$n),w$n)
   testthat::expect_equal(sum(g$hits2),w$hits2)
   testthat::expect_equal(stats::weighted.mean(g$brier,g$n),w$brier,tolerance=1e-12)
  }
 }
 x<-readRDS(file.path(temp,"forecasts.rds"));x$probabilities$probability[1]<-.999;saveRDS(x,file.path(temp,"forecasts.rds"))
 status<-system2("/opt/R/4.6.1/bin/Rscript",shQuote(c(file.path(root,"r/fm171_draw_history_evaluate.R"),root,temp)),
  env=c(paste0("R_LIBS=",shQuote(paste(.libPaths(),collapse=":"))),"TZ=UTC"),stdout=log,stderr=log)
 testthat::expect_true(status!=0L)
})
