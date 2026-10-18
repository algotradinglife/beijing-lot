test_that("research command refuses invalid modes before touching frozen artifacts", {
  root <- Sys.getenv("BEIDAN_REPO_ROOT",unset=rprojroot::find_root(
    rprojroot::has_file("AGENTS.md")))
  script <- file.path(root,"r/margin_combination_study_20261018.R")
  output <- tempfile(fileext=".log")
  path <- file.path(root,"results/margin-combination-study-20261018-v2/frozen-study.rds")
  before <- if(file.exists(path))digest::digest(file=path,algo="sha256")else NA_character_
  code <- system2("/opt/R/4.6.1/bin/Rscript",shQuote(c(script,root,"invalid-mode")),
    stdout=output,stderr=output)
  expect_equal(code,1L)
  expect_match(paste(readLines(output),collapse="\n"),"args\\[2\\].*not TRUE")
  after <- if(file.exists(path))digest::digest(file=path,algo="sha256")else NA_character_
  expect_identical(after,before)
})

#' Find a named call in a parsed research command without executing its IO
#' @param x Parsed expression, call or list to inspect.
#' @param name Exact function symbol to locate.
#' @return List of matching calls, exercised by the contract regression below.
#' @noRd
StudyContractCalls <- function(x,name) {
  head <- if(is.call(x))x[[1]]else NULL
  matches <- identical(head,as.name(name)) ||
    (is.call(head)&&as.character(head[[1]])%in%c("::",":::")&&identical(head[[3]],as.name(name)))
  found <- if(is.call(x)&&matches)list(x)else list()
  if(is.recursive(x))for(child in as.list(x)) {
    if(!rlang::is_missing(child)&&!is.symbol(child))found <- c(found,StudyContractCalls(child,name))
  }
  found
}

test_that("actual study settlement expression enforces authoritative column order", {
  root <- Sys.getenv("BEIDAN_REPO_ROOT",unset=rprojroot::find_root(rprojroot::has_file("AGENTS.md")))
  calls <- StudyContractCalls(parse(file=file.path(root,"r/evaluate_margin_combination_20261018.R")),
    "parlay_settle_plan")
  expect_length(calls,1L)
  env <- new.env(parent=asNamespace("dplyr"))
  env$a <- tibble::tibble(issue_id="009",fixture_id="009:1",outcome="W",settled_sp=2,
    label_available_at=lubridate::ymd_hms("2026-10-10 00:00:00",tz="UTC"),source_url="fixture")
  settlements <- eval(calls[[1]][[3]],envir=env)
  expect_identical(names(settlements),c("issue_id","fixture_id","outcome","settled_sp",
    "label_available_at","status","source_url"))
  expect_silent(beidan:::match_validate_table(settlements,"settlements"))
})

test_that("actual scorer pairs only observed labels and preserves pending ticket status", {
  root <- Sys.getenv("BEIDAN_REPO_ROOT",unset=rprojroot::find_root(rprojroot::has_file("AGENTS.md")))
  program <- parse(file=file.path(root,"r/evaluate_margin_combination_20261018.R"))
  calls <- StudyContractCalls(program,"DcAccuracyDiagnostic")
  expect_length(calls,1L)
  env <- new.env(parent=asNamespace("dplyr"))
  env$q <- tibble::tibble(fixture_id=rep(c("A","B"),each=3),outcome=rep(c("W","D","L"),2),
    probability=rep(c(.5,.3,.2),2))
  env$a <- tibble::tibble(fixture_id="A",outcome="W")
  env$model <- "RAW"
  scores <- eval(calls[[1]],envir=env)$scores
  expect_identical(scores$fixture_id,"A")
  expect_identical(scores$model,"RAW")
  expect_identical(scores$top1,TRUE)
  env$a$fixture_id <- "C"
  expect_error(eval(calls[[1]],envir=env),"rows|row")
  rows <- Filter(function(x)"any_hit"%in%names(as.list(x)),StudyContractCalls(program,"tibble"))
  expect_length(rows,1L)
  env$gs <- tibble::tibble(hit=c(FALSE,FALSE),pending=c(TRUE,FALSE))
  expect_true(is.na(eval(rows[[1]][["any_hit"]],envir=env)))
  env$gs$hit[1] <- TRUE
  expect_true(eval(rows[[1]][["any_hit"]],envir=env))
  env$gs$hit[] <- FALSE;env$gs$pending[] <- FALSE
  expect_false(eval(rows[[1]][["any_hit"]],envir=env))
})

test_that("producer decision computation is identical to independently replayed source evidence", {
  root <- Sys.getenv("BEIDAN_REPO_ROOT",unset=rprojroot::find_root(rprojroot::has_file("AGENTS.md")))
  current <- StudyContractCalls(parse(file=file.path(root,"r/margin_combination_study_20261018.R")),"for")
  prior <- StudyContractCalls(parse(file=file.path(root,
    "results/margin-combination-study-20261018-v2/producer-source.R")),"for")
  current <- Filter(function(x)identical(x[[2]],as.name("i"))&&identical(x[[3]],quote(4:10)),current)
  prior <- Filter(function(x)identical(x[[2]],as.name("i"))&&identical(x[[3]],quote(4:10)),prior)
  expect_length(current,1L);expect_identical(current,prior)
})
