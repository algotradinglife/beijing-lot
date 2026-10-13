test_that("NAS opponent research reproduces the frozen paired study", {
  root <- Sys.getenv("FM17_OPPONENT_ROOT",unset="")
  expect_true(nzchar(root))
  out <- file.path(root,"results/fm17-opponent-lambda-20261013")
  publication <- jsonlite::fromJSON(file.path(out,"publication.json"))
  study_manifest <- jsonlite::fromJSON(file.path(out,"manifest.json"))
  study <- readRDS(file.path(out,"forecasts.rds"))
  expect_identical(digest::digest(file=file.path(out,"forecasts.rds"),algo="sha256"),study_manifest$forecast_sha256)
  replay <- jsonlite::fromJSON(file.path(out,"replay.json"))
  expect_identical(replay$status,"FULL_IDENTICAL_REPLAY")
  expect_identical(replay$sha256,study_manifest$forecast_sha256)
  names <- c("audit","probabilities","metrics","lambdas","margins","coefficients","observations","support","snapshots")
  tables <- setNames(lapply(names,function(name)beidan::read_dataset(publication$dataset,name,version=publication$version)),names)
  for(name in names(tables)) {
    expect_s3_class(tables[[name]],"tbl_df")
    expect_identical(attr(tables[[name]],"dataset"),publication$dataset)
    expect_identical(attr(tables[[name]],"table"),name)
    expect_identical(attr(tables[[name]],"version"),publication$version)
  }
  expect_equal(nrow(tables$audit),117L)
  expect_equal(sum(tables$audit$state=="ESTIMATED"),94L)
  expect_equal(sum(tables$audit$state=="UNESTIMATED"),23L)
  # read_dataset adds storage provenance attributes, absent on the RDS input.
  expect_identical(names(tables$probabilities),names(study$probabilities))
  for(column in names(study$probabilities))expect_identical(tables$probabilities[[column]],study$probabilities[[column]])
  expect_true(inherits(tables$audit$cutoff_utc,"POSIXct"))
  expect_identical(attr(tables$audit$cutoff_utc,"tzone"),"UTC")
  expect_true(is.character(tables$observations$team_id))
  expect_true(is.character(tables$observations$opponent_id))
  expect_true(is.character(tables$observations$competition_id))
  expect_true(is.character(tables$observations$row_key))
  expect_true(is.integer(tables$metrics$n))
  expect_true(is.integer(tables$margins$margin))
  expect_false(anyDuplicated(tables$probabilities[c("fixture_id","model","outcome")])>0L)
  expect_true(all(tables$probabilities |> dplyr::summarise(mass=sum(probability),.by=c(fixture_id,model)) |> dplyr::pull(mass) |> (\(x)abs(x-1)<1e-12)()))
  expect_true(all(tables$lambdas$lambda_home>0&tables$lambdas$lambda_away>0))
  expect_setequal(tables$lambdas$fixture_id,names(study$entries))
  for(i in seq_len(nrow(tables$snapshots)))expect_identical(
    digest::digest(tables$snapshots$payload[i],algo="sha256",serialize=FALSE),tables$snapshots$sha256[i])
  saved_inputs <- jsonlite::fromJSON(tables$snapshots$payload[tables$snapshots$snapshot_id=="inputs"])
  expect_equal(nrow(saved_inputs$fixtures),347L)
  expect_setequal(unique(saved_inputs$fixtures$issue_id),c("26098","26101","26102"))
  parent <- readRDS(file.path(root,"results/fm17-three-issues-20261013/forecasts.rds"))
  labels <- readr::read_csv(file.path(out,"labels.csv"),show_col_types=FALSE)
  probabilities <- dplyr::bind_rows(study$probabilities |> dplyr::select(fixture_id,model,outcome,probability),
    parent$probabilities |> dplyr::filter(model=="FM-1.7.0",fixture_id%in%names(study$entries)) |>
      dplyr::select(fixture_id,model,outcome,probability))
  expected <- beidan:::DcAccuracyDiagnostic(probabilities,labels |> dplyr::filter(fixture_id%in%names(study$entries)) |>
    dplyr::select(fixture_id,actual_outcome))$summary
  actual <- tables$metrics |> dplyr::filter(cohort=="ESTIMATED_PAIRED",issue_id=="ALL",comparison=="model_only",model%in%expected$model) |>
    dplyr::select(dplyr::all_of(names(expected)))
  actual <- dplyr::arrange(actual,model);expected <- dplyr::arrange(expected,model)
  expect_identical(names(actual),names(expected))
  for(column in names(expected))expect_equal(actual[[column]],expected[[column]],tolerance=1e-12)
  cutoffs <- jsonlite::fromJSON(file.path(out,"publication-staging/receipt.json"),simplifyVector=FALSE)$cutoffs
  expect_setequal(names(cutoffs),tables$audit$fixture_id) # Named vectors must serialize as objects.
  current_metrics <- tables$metrics |> dplyr::filter(cohort=="FULL_FROZEN_ROUTING_OVERLAY",issue_id=="ALL",comparison=="near_sale")
  expect_true(all(current_metrics$n==345L))
  original <- current_metrics |> dplyr::filter(model=="FM-1.7.0")
  expect_equal(original$hits1,131L);expect_equal(original$hits2,250L)
  expect_equal(digest::digest(file=file.path(root,"results/fm17-three-issues-20261013/forecasts.rds"),algo="sha256"),
    "e537428c0a43f966542c703d3edf6264722c95a7551dbabf7853aa909354e786")
  # Exercise the staging entry point on an isolated copied study; a replaced
  # evaluation CSV must be refused before any staging or catalog write.
  isolated <- tempfile("opponent-publication-");dir.create(isolated)
  copied_out <- file.path(isolated,"results/fm17-opponent-lambda-20261013")
  dir.create(copied_out,recursive=TRUE)
  evaluation <- jsonlite::fromJSON(file.path(out,"evaluation.json"))
  copied_files <- c("manifest.json","replay.json","evaluation.json","forecasts.rds",paste0(names(evaluation$outputs),".csv"))
  expect_true(all(file.copy(file.path(out,copied_files),file.path(copied_out,copied_files))))
  cat("\n",file=file.path(copied_out,"metrics.csv"),append=TRUE)
  log <- file.path(isolated,"rejected.log")
  result <- system2("/opt/R/4.6.1/bin/Rscript",
    args=c(shQuote(file.path(root,"r/fm17_opponent_publish.R")),shQuote(isolated)),
    stdout=log,stderr=log,env=paste0("R_LIBS=",paste(.libPaths(),collapse=":")))
  expect_equal(result,1L)
  expect_match(paste(readLines(log,warn=FALSE),collapse="\n"),"Evaluation CSV hash differs: metrics",fixed=TRUE)
  expect_false(dir.exists(file.path(copied_out,"publication-staging")))
})
