testthat::test_that("FM171 fixed shape study preserves score mapping and symmetric width contracts", {
 root <- rprojroot::find_root(rprojroot::has_file("AGENTS.md"))
 out <- file.path(root,"results/fm171-margin-shape-20261017")
 manifest <- jsonlite::fromJSON(file.path(out,"manifest.json"))
 replay <- jsonlite::fromJSON(file.path(out,"replay.json"))
 testthat::expect_identical(replay$status,"FULL_IDENTICAL_REPLAY")
 testthat::expect_equal(replay$forecasts,346L)
 testthat::expect_identical(digest::digest(file=file.path(out,"forecasts.rds"),algo="sha256"),manifest$sha256)
 x <- readRDS(file.path(out,"forecasts.rds"))
 testthat::expect_equal(sum(x$features$eligible),323L)
 testthat::expect_equal(nrow(x$probabilities),346L*4L*3L)
 testthat::expect_false(anyDuplicated(x$probabilities[c("fixture_id","model","outcome")])>0)
 testthat::expect_false(manifest$target_labels_opened)
 for(id in names(x$entries)) {
  e <- x$entries[[id]];f <- e$feature
  testthat::expect_identical(e$base$cutoff,e$cutoff)
  testthat::expect_lt(as.numeric(e$base$max_source_available_utc),as.numeric(e$cutoff$cutoff_utc))
  m <- dplyr::summarise(dplyr::group_by(dplyr::mutate(e$base$grid,margin=home_goals-away_goals),margin),p=sum(probability),.groups="drop")
  testthat::expect_equal(f$draw_probability,sum(m$p[m$margin==f$draw_margin]),tolerance=1e-12)
  testthat::expect_equal(f$draw_margin_rank,1L+sum(m$p>f$draw_probability+1e-12))
  testthat::expect_equal(f$local_mass,sum(m$p[abs(m$margin-f$draw_margin)<=1]),tolerance=1e-12)
  testthat::expect_equal(sum(c(f$raw_w,f$raw_d,f$raw_l)),1,tolerance=1e-10)
  testthat::expect_equal(f$interval80_positions,f$interval80_hi-f$interval80_lo+1)
  testthat::expect_gte(f$interval80_mass,.8-1e-12)
  # No shorter contiguous interval reaches 80%, including outside the selected mode.
  width <- f$interval80_positions-1L
  if(width>0L)for(lo in m$margin) testthat::expect_lt(sum(m$p[m$margin>=lo & m$margin<lo+width]),.8+1e-12)
  for(name in names(e$results)) {
   z <- e$results[[name]];grid <- z$final$grid
   testthat::expect_equal(sum(grid$probability),1,tolerance=1e-10)
   testthat::expect_true(all(grid$probability>=0))
   testthat::expect_identical(z$final$cutoff,e$cutoff)
   q <- x$probabilities[x$probabilities$fixture_id==id & x$probabilities$model==name,]
   expected <- c(W=sum(grid$probability[grid$home_goals-grid$away_goals>f$draw_margin]),
    D=sum(grid$probability[grid$home_goals-grid$away_goals==f$draw_margin]),
    L=sum(grid$probability[grid$home_goals-grid$away_goals<f$draw_margin]))
   testthat::expect_equal(q$probability,unname(expected[q$outcome]),tolerance=1e-10)
   if(name=="SOURCE_FULL" || e$review$decision=="retain")testthat::expect_equal(grid$probability,e$base$grid$probability,tolerance=1e-10)
   # Uniform margin reweighting preserves relative probabilities of scores within each margin.
   original <- e$base$grid;ratio <- grid$probability/original$probability
   for(margin in unique(original$home_goals-original$away_goals)) {
    r <- ratio[original$home_goals-original$away_goals==margin & original$probability>0]
    if(length(r)>1)testthat::expect_lt(max(r)-min(r),1e-8)
   }
  }
 }
})

testthat::test_that("shape scoring replays independently, reconciles changes and rejects corrupt forecasts", {
 root <- rprojroot::find_root(rprojroot::has_file("AGENTS.md"))
 folder <- file.path(root,"results/fm171-margin-shape-20261017")
 evaluation <- jsonlite::fromJSON(file.path(folder,"evaluation.json"))
 temp <- tempfile("shape-evaluation-");dir.create(temp)
 for(name in c("forecasts.rds","manifest.json","replay.json"))testthat::expect_true(file.copy(file.path(folder,name),file.path(temp,name)))
 log <- tempfile();status <- system2("/opt/R/4.6.1/bin/Rscript",shQuote(c(file.path(root,"r/fm171_margin_shape_evaluate.R"),root,temp)),
  env=paste0("R_LIBS=",shQuote(paste(.libPaths(),collapse=":"))),stdout=log,stderr=log)
 testthat::expect_equal(status,0L,info=paste(readLines(log),collapse="\n"))
 for(name in names(evaluation$output_hashes))testthat::expect_identical(
  digest::digest(file=file.path(temp,paste0(name,".csv")),algo="sha256"),evaluation$output_hashes[[name]])
 m <- readr::read_csv(file.path(temp,"metrics.csv"),show_col_types=FALSE)
 for(cohort in unique(m$cohort)) {
  all <- dplyr::filter(m,.data$cohort==.env$cohort,dimension=="all")
  testthat::expect_true(all(all$n==if(cohort=="ELIGIBLE_322")322 else 345))
  ref <- all[all$model=="FM171",]
  testthat::expect_equal(all$hits1-ref$hits1,all$saved_top1-all$lost_top1)
  testthat::expect_equal(all$hits2-ref$hits2,all$saved_top2-all$lost_top2)
  for(model in all$model) {
   rows <- dplyr::filter(m,.data$cohort==.env$cohort,.data$model==.env$model,dimension=="shape")
   whole <- all[all$model==model,]
   testthat::expect_equal(sum(rows$n),whole$n)
   testthat::expect_equal(sum(rows$hits2),whole$hits2)
   testthat::expect_equal(weighted.mean(rows$brier,rows$n),whole$brier,tolerance=1e-12)
  }
 }
 x <- readRDS(file.path(temp,"forecasts.rds"));x$features$local_mass[1]<-.99;saveRDS(x,file.path(temp,"forecasts.rds"))
 status <- system2("/opt/R/4.6.1/bin/Rscript",shQuote(c(file.path(root,"r/fm171_margin_shape_evaluate.R"),root,temp)),
  env=paste0("R_LIBS=",shQuote(paste(.libPaths(),collapse=":"))),stdout=log,stderr=log)
 testthat::expect_true(status!=0L)
})

testthat::test_that("shape projections reject cutoff and distribution mutations", {
 root <- rprojroot::find_root(rprojroot::has_file("AGENTS.md"))
 x <- readRDS(file.path(root,"results/fm171-margin-shape-20261017/forecasts.rds"))
 e <- x$entries[[1]];final <- e$results$FM171$final;h <- e$feature$handicap
 original <- beidan::project_score_outcomes(final,h,root)
 final$cutoff$cutoff_utc <- final$cutoff$cutoff_utc+1
 testthat::expect_error(beidan::project_score_outcomes(final,h,root))
 final <- e$results$FM171$final;final$grid$probability[1]<-.999
 testthat::expect_error(beidan::project_score_outcomes(final,h,root))
 testthat::expect_identical(original,beidan::project_score_outcomes(e$results$FM171$final,h,root))
})
