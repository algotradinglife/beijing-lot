testthat::test_that("interactive QMD selects a fresh cutoff and explains zero admission", {
  lines <- readLines(testthat::test_path("..", "..", "quarto", "26098_walkthrough.qmd"), warn = FALSE)
  blocks <- list()
  for (label in c("prepare-decision", "probabilities", "plan")) {
    start <- which(lines == paste0("#| label: ", label)) + 1L
    end <- start + which(lines[start:length(lines)] == "```")[1L] - 2L
    blocks[[label]] <- parse(text = lines[start:end])
  }
  now <- lubridate::with_tz(Sys.time(), "Asia/Shanghai")
  fx <- beidan::make_example_issue("26098", rep(now + lubridate::dhours(6), 7), n_companies = 5L)
  inputs <- beidan::read_match_inputs(beidan::example_match_source(fx), "26098")
  inputs$euro$company_id <- unname(c(c01="281", c02="115", c03="82", c04="177", c05="432")[inputs$euro$company_id])
  inputs$match_status$status_at <- now - lubridate::dminutes(1)
  inputs$match_status$available_at <- now - lubridate::dminutes(1)
  env <- new.env(parent = globalenv())
  env$inputs <- inputs
  env$replay_decision_at <- NULL
  env$decision_at <- now - lubridate::dhours(5)
  env$model_config <- list(rho=-0.14,total_bounds=c(0.1,16),tail_tolerance=1e-10)
  invisible(capture.output(eval(blocks[["prepare-decision"]], env)))
  testthat::expect_gte(as.numeric(env$decision_at), as.numeric(now))
  testthat::expect_equal(nrow(env$epoch$fixtures), 7)
  invisible(capture.output(eval(blocks[["probabilities"]], env)))
  testthat::expect_equal(nrow(env$projected$probabilities), 21)
  env$settings <- beidan::parlay_settings(reset = TRUE)
  env$work_dir <- tempfile("walkthrough-plan-")
  env$issue_id <- "26098"
  invisible(capture.output(eval(blocks[["plan"]], env)))
  testthat::expect_equal(nrow(env$result$funded$purchases), 96L)
  testthat::expect_equal(sum(env$result$funded$purchases$stake_cny), 192)
  testthat::expect_equal(nrow(env$plan_summary$groups), 1L)
  testthat::expect_equal(nrow(env$plan_summary$tickets), 96L)
  testthat::expect_false("n_groups" %in% names(env$strategy_config))

  env$result <- list(stale = TRUE)
  env$inputs <- NULL
  invisible(capture.output(eval(blocks[["prepare-decision"]], env)))
  testthat::expect_null(env$projected)
  testthat::expect_null(env$result)
  output <- capture.output(eval(blocks[["probabilities"]], env))
  testthat::expect_true(any(grepl("尚未生成 epoch", output, fixed = TRUE)))
  env$inputs <- inputs
  env$inputs$match_status$available_at <- now + lubridate::dhours(1)
  invisible(capture.output(eval(blocks[["prepare-decision"]], env)))
  output <- capture.output(eval(blocks[["probabilities"]], env))
  testthat::expect_equal(nrow(env$epoch$fixtures), 0)
  testthat::expect_null(env$projected)
  testthat::expect_true(any(grepl("准入比赛为0", output, fixed=TRUE)))
  testthat::expect_true(any(grepl("no match status before cutoff", output, fixed=TRUE)))
})

 testthat::test_that("market block includes later slots and reports uncaptured fixtures", {
  lines <- readLines(testthat::test_path("..", "..", "quarto", "26098_walkthrough.qmd"), warn=FALSE)
  start <- which(lines == "#| label: market-source") + 1L
  end <- start + which(lines[start:length(lines)] == "```")[1L] - 2L
  block <- parse(text=lines[start:end])
  at <- lubridate::ymd_hms("2026-09-26 20:00:00",tz="Asia/Shanghai")
  s <- tibble::tibble(issue_id="26098", fixture_key=paste0("26098:",c(78,79,120,121)),
    slot=c(78L,79L,120L,121L), provider_id_nowscore=c("a","b","c","d"),
    home_nowscore="Home", away_nowscore="Away", kickoff_at=at+lubridate::dhours(c(3,4,27,28)),
    handicap=0L,sale_state="open",match_status="scheduled",observed_at=at-lubridate::dhours(1),
    source_url_nowscore="fixture://schedule")
  markets <- list(
    identities=dplyr::transmute(s[1,],fixture_id=fixture_key,provider_id_nowscore,
      home_nowscore,away_nowscore,kickoff_at),
    euro=beidan::match_typed_empty("euro"),totals=beidan::match_typed_empty("totals"),
    coverage=tibble::tibble(fixture_id="26098:78",status="ok"),
    companies=tibble::tibble(company_id=character()),
    captures=tibble::tibble(fixture_id=character(),market=character(),
      observed_at=at[0],source_url=character()))
  env <- new.env(parent=globalenv())
  env$schedule <- s; env$replay_decision_at <- at
  env$refresh_markets <- FALSE; env$market_slots <- 78L
  env$markets_file <- tempfile(fileext=".rds")
  on.exit(unlink(env$markets_file), add=TRUE)
  saveRDS(markets,env$markets_file)
  output <- capture.output(eval(block,env))
  testthat::expect_identical(env$market_schedule$slot,c(79L,120L))
  testthat::expect_identical(env$uncaptured$slot,c(79L,120L))
  testthat::expect_equal(nrow(env$inputs$fixtures),4L)
  testthat::expect_true(any(grepl("未采集盘口",output,fixed=TRUE)))
  # Historical replay must never silently initiate fresh requests.
  env$refresh_markets <- TRUE
  testthat::expect_error(invisible(capture.output(eval(block,env))),"历史回放")
})
