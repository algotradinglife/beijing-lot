test_that('scoring rejects a replaced settlement manifest before reading labels', {
  root <- Sys.getenv('BEIDAN_REPOSITORY_ROOT',unset=rprojroot::find_root(rprojroot::has_file('AGENTS.md')))
  source <- file.path(root,'results/margin-first-mapping-20261018')
  required <- c('inputs.rds','frozen-selections.rds','selection-manifest.json')
  expect_true(all(file.exists(file.path(source,required))))
  work <- tempfile('first-mapping-manifest-');dir.create(work)
  on.exit(unlink(work,recursive=TRUE),add=TRUE)
  out <- file.path(work,'results/margin-first-mapping-20261018');dir.create(out,recursive=TRUE)
  expect_true(all(file.copy(file.path(source,required),out)))
  expect_true(file.symlink(dirname(find.package('beidan')),file.path(out,'library')))
  dir.create(file.path(work,'results/full100-historical-rounds-20261018'),recursive=TRUE)
  writeLines('[{"label_snapshot":"forbidden-target-label.json"}]',
    file.path(work,'results/full100-historical-rounds-20261018/input-manifest.json'))
  script <- file.path(root,'r/margin_first_mapping_evaluate_20261018.R')
  expect_true(file.exists(script))
  output <- tempfile();on.exit(unlink(output),add=TRUE)
  status <- system2(file.path(R.home('bin'),'Rscript'),c(shQuote(script),shQuote(work)),
    stdout=output,stderr=output,env='R_PROFILE_USER=/dev/null')
  text <- paste(readLines(output,warn=FALSE),collapse='\n')
  expect_equal(status,1L)
  expect_match(text,'manifest_path')
  expect_false(grepl('cannot open|forbidden-target-label',text))
  expect_false(file.exists(file.path(out,'evaluation.json')))
})

test_that('QMD review gate rejects stale or incomplete reviewed source inventories', {
  root <- Sys.getenv('BEIDAN_REPOSITORY_ROOT',unset=rprojroot::find_root(rprojroot::has_file('AGENTS.md')))
  qmd <- file.path(root,'quarto/margin_first_mapping_20261018.qmd')
  script <- tempfile(fileext='.R');on.exit(unlink(script),add=TRUE)
  invisible(knitr::purl(qmd,output=script,quiet=TRUE))
  nodes <- as.list(parse(script))
  chosen <- vapply(nodes,function(node)grepl('final-review-receipt.json',paste(deparse(node),collapse='\n'),fixed=TRUE),logical(1))
  expect_equal(sum(chosen),1L)
  gate <- nodes[[which(chosen)]]
  paths <- c('packages/beidan/R/margin_first_mapping.R',
    'packages/beidan/tests/testthat/test-margin-first-mapping.R',
    'r/margin_first_mapping_inputs_20261018.R','r/margin_first_mapping_freeze_20261018.R',
    'r/margin_first_mapping_evaluate_20261018.R','r/margin_first_mapping_checks_20261019.R',
    'tests/testthat/test-margin-first-mapping-manifest.R','quarto/margin_first_mapping_20261018.qmd')
  files <- tibble::tibble(path=paths,sha256=vapply(file.path(root,paths),digest::digest,character(1),file=TRUE,algo='sha256'))
  out <- tempfile();dir.create(out);on.exit(unlink(out,recursive=TRUE),add=TRUE)
  for(mode in c('valid','stale','missing')) {
    reviewed <- files
    if(mode=='stale') reviewed$sha256[1] <- paste(rep('0',64),collapse='')
    if(mode=='missing') reviewed <- reviewed[-1,]
    receipt <- list(status='NO_BLOCKING_FINDINGS',exit_status=0L,files=reviewed,
      command='codex review',findings='none',resolution='none')
    jsonlite::write_json(receipt,file.path(out,'final-review-receipt.json'),dataframe='rows',auto_unbox=TRUE)
    env <- new.env(parent=globalenv());env$root <- root;env$out <- out
    env$as_tibble <- tibble::as_tibble;env$tibble <- tibble::tibble
    env$params <- list(require_acceptance=TRUE)
    # Match both receipts: current source validation must still catch stale hashes.
    env$acceptance <- list(files=jsonlite::fromJSON(file.path(out,'final-review-receipt.json'))$files,
      tests=tibble::tibble(failed=0L),checks=tibble::tibble(exit_status=0L))
    if(mode=='valid') expect_no_error(invisible(capture.output(eval(gate,envir=env))))
    else expect_error(eval(gate,envir=env),'is not TRUE')
  }
})
