testthat::test_that("integrated native lambdas preserve routing and paired scoring contracts", {
  root <- rprojroot::find_root(rprojroot::has_file("AGENTS.md"))
  folder <- file.path(root,"results/fm-lambda-integration-20261017")
  manifest <- jsonlite::fromJSON(file.path(folder,"manifest.json"))
  replay <- jsonlite::fromJSON(file.path(folder,"replay.json"))
  testthat::expect_identical(replay$status,"FULL_IDENTICAL_REPLAY")
  testthat::expect_equal(replay$forecasts,346L)
  testthat::expect_identical(digest::digest(file=file.path(folder,"forecasts.rds"),algo="sha256"),manifest$forecast_sha256)
  x <- readRDS(file.path(folder,"forecasts.rds"))
  parent <- readRDS(file.path(root,"results/fm17-three-issues-20261013/forecasts.rds"))
  alpha <- readRDS(file.path(root,"results/fm18-three-issues-20261017/forecasts.rds"))
  testthat::expect_setequal(names(x$entries),names(parent$entries))
  testthat::expect_equal(nrow(x$probabilities),346L*4L*3L)
  testthat::expect_false(anyDuplicated(x$probabilities[c("fixture_id","model","outcome")])>0L)
  for(id in names(x$entries)) {
    e <- x$entries[[id]]
    testthat::expect_identical(e$cutoff,parent$entries[[id]]$cutoff)
    testthat::expect_identical(e$selected_source,parent$entries[[id]]$parent_selection$selected_source)
    testthat::expect_identical(e$changed_native,!is.null(e$fit)&&e$selected_source=="native")
    if(!is.null(e$fit)) {
      testthat::expect_equal(e$fit$receipt$policy$ridge,.05)
      testthat::expect_identical(e$fit$receipt$target_label_optimization,FALSE)
      testthat::expect_equal(as.POSIXct(e$fit$receipt$admission$cutoff_ts,format="%Y-%m-%dT%H:%M:%S",tz="UTC"),
        e$cutoff$cutoff_utc)
      testthat::expect_identical(digest::digest(e$fit$parameters,algo="sha256"),e$fit$receipt$parameters_sha256)
    }
    for(model in c("OPPONENT_NATIVE","SAME_SUPPORT_RAW")) {
      fm <- e$results[[paste0("FM17+",model)]]
      al <- e$results[[paste0("ALPHA+",model)]]
      testthat::expect_equal(sum(fm$grid$probability),1,tolerance=1e-9)
      testthat::expect_equal(sum(al$grid$probability),1,tolerance=1e-9)
      testthat::expect_true(all(fm$grid$probability>=0)&all(al$grid$probability>=0))
      if(!e$changed_native) {
        testthat::expect_identical(fm,parent$entries[[id]]$results[["FM-1.7.0"]]$final)
        testthat::expect_identical(al,alpha$entries[[id]])
      } else {
        testthat::expect_identical(al$receipt$tail_compression,FALSE)
        # Preserve W/L ratio from the new BEFORE-tail grid, without tail compression.
        original <- al$receipt$original_probabilities
        adjusted <- al$receipt$adjusted_probabilities
        testthat::expect_equal(original$W/original$L,adjusted$W/adjusted$L,tolerance=1e-10)
        testthat::expect_true(e$fit$receipt$admission$maximum_source_time <
          format(e$cutoff$cutoff_utc,"%Y-%m-%dT%H:%M:%S",tz="UTC"))
        testthat::expect_true(all(e$fit$observations$competition_id==e$fit$receipt$fixture$competition_id))
      }
    }
  }
  temp <- tempfile("fm-integrated-evaluation-"); dir.create(temp)
  for(name in c("forecasts.rds","manifest.json","replay.json")) {
    testthat::expect_true(file.copy(file.path(folder,name),file.path(temp,name)))
  }
  log <- tempfile()
  status <- system2("/opt/R/4.6.1/bin/Rscript",shQuote(c(file.path(root,"r/fm_lambda_integration_evaluate.R"),root,temp)),env=paste0("R_LIBS=",shQuote(paste(.libPaths(),collapse=":"))),stdout=log,stderr=log)
  testthat::expect_equal(status,0L,info=paste(readLines(log),collapse="\n"))
  m <- readr::read_csv(file.path(temp,"metrics.csv"),show_col_types=FALSE)
  all <- dplyr::filter(m,dimension=="all")
  testthat::expect_true(all(all$n[all$comparison=="near_sale"]==345L))
  testthat::expect_true(all(all$n[all$comparison=="same_cutoff"]==214L))
  testthat::expect_equal(nrow(all),16L)
  for(comparison in c("same_cutoff","near_sale"))for(model in unique(all$model[all$comparison==comparison])) {
    group <- dplyr::filter(m,.data$comparison==.env$comparison,.data$model==.env$model,dimension=="event_type")
    whole <- dplyr::filter(all,.data$comparison==.env$comparison,.data$model==.env$model)
    testthat::expect_equal(sum(group$n),whole$n)
    testthat::expect_equal(sum(group$hits1),whole$hits1)
    testthat::expect_equal(sum(group$hits2),whole$hits2)
    testthat::expect_equal(weighted.mean(group$brier,group$n),whole$brier,tolerance=1e-12)
  }
  changed <- readr::read_csv(file.path(temp,"changes.csv"),show_col_types=FALSE)
  testthat::expect_true(all(changed$brier_delta[!changed$changed_native]==0))
  for(candidate in unique(changed$model)) {
    rows <- dplyr::filter(changed,model==candidate)
    new <- dplyr::filter(all,comparison=="near_sale",model==candidate)
    old <- dplyr::filter(all,comparison=="near_sale",model==rows$reference[1])
    testthat::expect_equal(new$hits1-old$hits1,sum(rows$saved_top1)-sum(rows$lost_top1))
    testthat::expect_equal(new$hits2-old$hits2,sum(rows$saved_top2)-sum(rows$lost_top2))
  }
  prior <- readBin(file.path(temp,"metrics.csv"),"raw",file.info(file.path(temp,"metrics.csv"))$size)
  bad <- x; bad$probabilities$probability[1] <- .999
  saveRDS(bad,file.path(temp,"forecasts.rds"))
  status <- system2("/opt/R/4.6.1/bin/Rscript",shQuote(c(file.path(root,"r/fm_lambda_integration_evaluate.R"),root,temp)),env=paste0("R_LIBS=",shQuote(paste(.libPaths(),collapse=":"))),stdout=log,stderr=log)
  testthat::expect_true(status!=0L)
  testthat::expect_identical(readBin(file.path(temp,"metrics.csv"),"raw",length(prior)),prior)
})

testthat::test_that("integration aborts critical native errors and admits only stated insufficiency", {
  root <- rprojroot::find_root(rprojroot::has_file("AGENTS.md"))
  expressions <- as.list(parse(file.path(root,"r/fm_lambda_integration_freeze.R")))
  loops <- Filter(function(x)is.call(x)&&identical(x[[1]],as.name("for")),expressions)
  main <- Filter(function(x)identical(x[[2]],as.name("id")),loops)[[1]]
  guards <- Filter(function(x)any(grepl("Critical native estimation failure",deparse(x),fixed=TRUE)),as.list(main[[4]])[-1])
  testthat::expect_length(guards,1L)
  scope <- new.env(parent=baseenv()); scope$need_native_fit <- TRUE
  scope$native <- simpleError("Implementation binding differs")
  testthat::expect_error(eval(guards[[1]],scope),"Critical native estimation failure")
  scope$native <- simpleError("Cutoff differs; rebuild required")
  testthat::expect_error(eval(guards[[1]],scope),"Critical native estimation failure")
  scope$native <- simpleError("Sparse target competition/venue support")
  testthat::expect_no_error(eval(guards[[1]],scope))
  scope$native <- simpleError("Disconnected target strength network")
  testthat::expect_no_error(eval(guards[[1]],scope))
})
