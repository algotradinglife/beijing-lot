# Frozen live-data delivery checks; execution requires the declared #543 artifact.
artifact_path <- Sys.getenv('BEIDAN_543_ARTIFACT',
  unset=file.path(rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION')),
    'inputs/26098_walkthrough/three_plans_20260928/plans.rds'))
a543 <- if (file.exists(artifact_path)) readRDS(artifact_path) else NULL

testthat::test_that('543 input chronology and 2-26h window are frozen correctly', {
  testthat::skip_if(is.null(a543),'Requires declared frozen #543 delivery artifact')
  testthat::expect_identical(names(a543$outputs),c('3333222','3322221','3222221'))
  cutoff <- a543$epoch$cutoff$cutoff_utc
  testthat::expect_equal(as.numeric(a543$epoch$window$start_utc-cutoff,units='hours'),2)
  testthat::expect_equal(as.numeric(a543$epoch$window$end_utc-cutoff,units='hours'),26)
  testthat::expect_true(all(a543$epoch$fixtures$kickoff_at>=cutoff+7200))
  testthat::expect_true(all(a543$epoch$fixtures$kickoff_at<cutoff+26*3600))
  testthat::expect_true(all(a543$bundle$markets$captures$observed_at<cutoff))
  testthat::expect_true(all(a543$epoch$prematch_sp$quote_at<cutoff))
  testthat::expect_null(a543$bundle$budget_cny)
})

testthat::test_that('543 exact tickets reconcile costs, masks and independent probabilities', {
  testthat::skip_if(is.null(a543),'Requires declared frozen #543 delivery artifact')
  for (pattern in names(a543$outputs)) {
    output <- a543$outputs[[pattern]]
    result <- output$evaluated$final
    sheet <- output$sheet
    regenerated <- beidan::parlay_betting_sheet(result,a543$bundle$capture_selection$schedule)
    testthat::expect_equal(nrow(regenerated$tickets),nrow(sheet$tickets))
    testthat::expect_gt(nrow(sheet$groups),0L)
    testthat::expect_lte(nrow(sheet$groups),2L)
    testthat::expect_true(all(sheet$matches$kickoff_at>=a543$epoch$window$start_utc))
    testthat::expect_true(all(sheet$matches$kickoff_at<a543$epoch$window$end_utc))
    support <- prod(as.integer(strsplit(pattern,'')[[1]]))
    count <- min(128,support)
    testthat::expect_true(all(sheet$groups$funded_tickets==count))
    testthat::expect_true(all(sheet$groups$cost_cny==2*count))
    testthat::expect_true(all(sheet$tickets$cost_cny==2))
    testthat::expect_equal(sum(sheet$groups$cost_cny),sum(sheet$tickets$cost_cny))
    testthat::expect_true(all(diff(sheet$groups$coverage_probability)<=0))
    testthat::expect_true(isTRUE(result$provenance$budget_unlimited))
    testthat::expect_false(anyDuplicated(sheet$tickets$ticket_id)>0)
    legs <- dplyr::distinct(sheet$ticket_legs,group_id,fixture_id)
    reuse <- dplyr::count(legs,fixture_id)
    testthat::expect_true(all(reuse$n<=2))
    ids <- unique(legs$group_id)
    for (g1 in ids) for (g2 in setdiff(ids,g1)) {
      testthat::expect_lte(length(intersect(legs$fixture_id[legs$group_id==g1],
        legs$fixture_id[legs$group_id==g2])),2)
    }
    for (id in ids) {
      purchased <- sheet$ticket_legs[sheet$ticket_legs$group_id==id,]
      probs <- dplyr::left_join(dplyr::select(purchased,ticket_id,fixture_id,outcome),
        result$probabilities,by=c('fixture_id','outcome'),relationship='many-to-one') |>
        dplyr::summarise(p=prod(probability),n=dplyr::n(),.by=ticket_id)
      testthat::expect_true(all(probs$n==7L))
      testthat::expect_equal(sum(probs$p),sheet$groups$coverage_probability[sheet$groups$group_id==id],tolerance=1e-12)
      # Independently enumerate the selected group's legal mask and verify TopN.
      cid <- sheet$groups$candidate_id[sheet$groups$group_id==id]
      mask <- result$frontier$supports |>
        dplyr::filter(candidate_id==cid,allowed) |>
        dplyr::left_join(result$probabilities,by=c('fixture_id','outcome'),relationship='many-to-one')
      masses <- split(mask$probability,mask$fixture_id)
      full <- expand.grid(masses,KEEP.OUT.ATTRS=FALSE)
      legal <- sort(apply(full,1,prod),decreasing=TRUE)
      testthat::expect_length(legal,support)
      testthat::expect_equal(sort(probs$p,decreasing=TRUE),head(legal,count),tolerance=1e-12)
    }
  }
})

testthat::test_that('543 replay rejects changed implementations and inputs', {
  root <- rprojroot::find_root(rprojroot::has_file('packages/beidan/DESCRIPTION'))
  receipt_path <- file.path(root,'docs/reviews/543-three-structure-plans.json')
  testthat::skip_if_not(file.exists(receipt_path),'Requires #543 source receipt')
  withr::local_dir(root)
  receipt <- jsonlite::read_json(receipt_path,simplifyVector=TRUE)
  script <- file.path(root,'r/replay_three_structure_plans.R')
  input <- file.path(root,receipt$input_path)
  output <- tempfile(fileext='.rds')
  runner <- function(receipt_file,input_file) {
    suppressWarnings(system2(file.path(R.home('bin'),'Rscript'),
      shQuote(c(script,'verify',receipt_file,input_file,output)),stdout=TRUE,stderr=TRUE))
  }
  valid <- runner(receipt_path,input)
  testthat::expect_null(attr(valid,'status'))
  testthat::expect_true(any(grepl('verified',valid)))
  bad <- receipt
  bad$code_hashes[[1]] <- paste(rep('0',64),collapse='')
  bad_receipt <- tempfile(fileext='.json')
  jsonlite::write_json(bad,bad_receipt,auto_unbox=TRUE)
  changed_code <- runner(bad_receipt,input)
  testthat::expect_identical(attr(changed_code,'status'),1L)
  testthat::expect_true(any(grepl('implementation mismatch',changed_code)))
  bad_input <- tempfile(fileext='.rds')
  saveRDS(list(changed=TRUE),bad_input)
  changed_input <- runner(receipt_path,bad_input)
  testthat::expect_identical(attr(changed_input,'status'),1L)
  testthat::expect_true(any(grepl('input mismatch',changed_input)))
  testthat::expect_false(file.exists(output))
})
