test_that("Poisson opponent model reproduces known home and away goal rates", {
  root <- Sys.getenv("FM17_OPPONENT_ROOT",unset="")
  if(!nzchar(root)) root <- normalizePath(file.path("..","..","..",".."),mustWork=TRUE)
  ns <- new.env(parent=asNamespace("beidan"))
  sys.source(file.path(root,"packages/beidan/R/opponent_goals.R"),ns)
  expect_identical(body(ns$FitOpponentGoals),body(getFromNamespace("FitOpponentGoals","beidan")))
  reticulate::use_python(file.path(root,".venv/bin/python"),required=TRUE)
  reticulate::import("sys",convert=FALSE)$path$insert(0L,file.path(root,"packages/beidan/inst/python"))
  backend <- reticulate::import("beidan_backend.opponent_goals",convert=FALSE)
  shared <- reticulate::import("beidan_backend.temporal_learning",convert=FALSE)
  fixture <- list(fixture_id="26102:6",issue_id="26102",provider_id="TARGET",
                  home_id="A",away_id="B",competition_id="35",neutral_reported=FALSE)
  history <- tibble::tibble(row_key=paste0("r",1:24),match_id=paste0("m",1:24),
    event_date=format(as.Date("2020-01-01")+0:23),home_id=rep(c("A","B"),12),
    away_id=rep(c("B","A"),12),home_score=2L,away_score=1L,
    score_scope="SOURCE_PUBLISHED_FULL_TIME",competition_id="35",neutral_reported=FALSE)
  rows <- jsonlite::fromJSON(jsonlite::toJSON(history,dataframe="rows",auto_unbox=TRUE),simplifyVector=FALSE)
  cutoff <- shared$Cutoff$decision_epoch("26102","2020-02-01T00:00:00Z")
  recent <- list(recent_n=8L,alpha=.5,minimum_recent_matches=12L,minimum_recent_ess=8)
  prepared <- backend$prepare_opponent_goals(rows,fixture,list("TARGET"),cutoff,list(source=strrep("a",64)),root,recent)
  policy <- list(ridge=.05,minimum_target_matches=12L,convergence_tolerance=1e-10,maximum_iterations=100000L)
  fit <- ns$FitOpponentGoals(prepared,fixture,cutoff,policy,root)
  expect_s3_class(fit$parameters,"tbl_df")
  expect_equal(fit$parameters$lambda_home,2,tolerance=1e-5)
  expect_equal(fit$parameters$lambda_away,1,tolerance=1e-5)
  expect_equal(fit$same_support_raw$lambda_home,2,tolerance=1e-12)
  expect_equal(fit$same_support_raw$lambda_away,1,tolerance=1e-12)
  expect_false(fit$receipt$target_label_optimization)
  expect_length(fit$ledgers,4)
  again <- ns$FitOpponentGoals(prepared,fixture,cutoff,policy,root)
  expect_identical(fit,again)
  expect_error(ns$FitOpponentGoals(prepared,fixture,shared$Cutoff$decision_epoch("26102","2020-02-02T00:00:00Z"),policy,root),"differs")
  expect_error(ns$FitOpponentGoals(prepared,fixture,NULL,policy,root),"Explicit")
  expect_error(ns$FitOpponentGoals(prepared,fixture,cutoff,modifyList(policy,list(minimum_target_matches=13L)),root),"Sparse")
  expect_error(ns$FitOpponentGoals(prepared,modifyList(fixture,list(away_id="C")),cutoff,policy,root),"differs")
  expect_error(ns$FitOpponentGoals(prepared,fixture,cutoff,modifyList(policy,list(ridge=0)),root))
  unrelated <- history |> dplyr::mutate(row_key=paste0("other-",row_key),match_id=paste0("other-",match_id),
    home_id=ifelse(home_id=="A","C","D"),away_id=ifelse(away_id=="A","C","D"),home_score=5L,away_score=4L)
  all_rows <- jsonlite::fromJSON(jsonlite::toJSON(dplyr::bind_rows(history,unrelated),dataframe="rows",auto_unbox=TRUE),simplifyVector=FALSE)
  extra <- backend$prepare_opponent_goals(all_rows,fixture,list("TARGET"),cutoff,list(source=strrep("a",64)),root,recent)
  extra_fit <- ns$FitOpponentGoals(extra,fixture,cutoff,policy,root)
  expect_equal(extra_fit$parameters,fit$parameters,tolerance=1e-12)
  expect_false(any(grepl(":[CD]$",extra_fit$coefficients$term)))
  # Run future mutation through native fit, FM17 tail selection and all ticket
  # projections; receipts must change, but probabilities/ranks must not.
  projection <- list();fit_keys <- character()
  for(variant in 1:2) {
    blocked <- history[1,,drop=FALSE] |> dplyr::mutate(row_key="future-roster",match_id="FUTURE_ROSTER",
      event_date=if(variant==1)"2019-01-01" else "2027-01-01",home_score=if(variant==1)0L else 99L)
    variant_rows <- jsonlite::fromJSON(jsonlite::toJSON(dplyr::bind_rows(history,blocked),dataframe="rows",auto_unbox=TRUE),simplifyVector=FALSE)
    variant_prepared <- backend$prepare_opponent_goals(variant_rows,fixture,list("TARGET","FUTURE_ROSTER"),cutoff,list(source=strrep("a",64)),root,recent)
    variant_fit <- ns$FitOpponentGoals(variant_prepared,fixture,cutoff,policy,root)
    expect_identical(variant_fit$parameters,fit$parameters)
    expect_identical(variant_fit$support,fit$support)
    fit_keys[variant] <- variant_fit$receipt$cache_key
    decision <- list(issue_id="26102",cutoff_utc=lubridate::ymd_hms("2020-02-01 00:00:00",tz="UTC"))
    score_fixture <- tibble::tibble(fixture_id="26102:6",issue_id="26102",home="A",away="B")
    base <- list(grid=beidan:::dixon_coles_score_grid(variant_fit$parameters$lambda_home,variant_fit$parameters$lambda_away,0L,1e-10,-.1)$grid |>
        dplyr::select(home_goals,away_goals,probability),cutoff=decision,model_id="SYNTHETIC_OPPONENT_TEST",
      source_hashes=list(fit=beidan:::.score_margin_hash(variant_fit)),
      max_source_available_utc=lubridate::ymd_hms(variant_fit$receipt$admission$maximum_source_time,tz="UTC"),intended_use="HISTORICAL_DIAGNOSTIC")
    review <- list(decision="apply",base_hash=beidan:::.score_margin_hash(base$grid),cutoff_utc="2020-02-01T00:00:00Z",
                   reason="Fixed test policy",counterevidence="Synthetic example only")
    core <- beidan::BuildFmTailJudgement(base,review,"test-evidence",decision,list(coverage=.9,coefficient=.3,tie_tolerance=1e-12))
    binding <- list(base_artifact=beidan:::.score_margin_hash(base),margin_judgement=beidan:::.score_margin_hash(core$judgement),
                    direction_implementation=beidan:::.score_margin_code(root))
    timestamp <- format(base$max_source_available_utc,"%Y-%m-%dT%H:%M:%SZ",tz="UTC")
    evidence <- list(list(evidence_id="test-evidence",fixture_id="26102:6",source_hash=strrep("a",64),row_key="test-evidence",
      issue_code="SYNTHETIC_FACT_PROXY",issue_year=2020L,label_available_ts=timestamp,data_available_ts=timestamp))
    adjustment <- reticulate::import("beidan_backend.fundamental_probability",convert=FALSE)
    context <- adjustment$build_adjustment_evidence_context(evidence,as.list(score_fixture),cutoff,binding,
      shared$AvailabilityPolicy$historical_proxy("SYNTHETIC_OPPONENT_TEST"),"HISTORICAL_DIAGNOSTIC",root)
    final <- beidan::adjust_score_margin_distribution(base,core$judgement,context,score_fixture,decision,root)
    projection[[variant]] <- lapply(c(-1L,0L,1L),function(handicap)beidan::project_score_outcomes(final,handicap,root))
  }
  expect_false(identical(fit_keys[1],fit_keys[2]))
  expect_identical(projection[[1]],projection[[2]])
})
