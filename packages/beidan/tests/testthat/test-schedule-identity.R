identity_schedule_fixture <- function() {
  s <- tibble::as_tibble(lapply(issue_schedule_empty(), function(x) rep(x[NA_integer_], 2)))
  for (column in names(s)[vapply(s, is.character, logical(1))]) s[[column]] <- rep("", 2)
  s$issue_id <- c("26098", "26098"); s$slot <- c(77L, 33L)
  s$observed_at <- lubridate::ymd_hms(rep("2026-09-25 21:44:39", 2), tz = "Asia/Shanghai")
  s$home_500 <- c("赫尔辛基预备队", "都柏林大学")
  s$home_display_500 <- c("克鲁比04", "都柏林大学")
  s$home_title_500 <- s$home_500
  s$home_nowscore <- s$home_display_nowscore <- c("克鲁比", "都柏林")
  s$away_500 <- s$away_title_500 <- c("耶尔文佩", "布雷流浪者")
  s$away_display_500 <- c("查普斯", "布雷流浪者")
  s$away_nowscore <- s$away_display_nowscore <- c("耶尔文佩", "布雷流浪者")
  s$league_500 <- s$league_nowscore <- c("芬甲", "爱甲")
  s$provider_id_500 <- c("1370919", "1382740")
  s$provider_id_nowscore <- c("2921946", "2939061")
  s$source_url_500 <- rep("https://trade.500.com/bjdc/?expect=26098", 2)
  s$source_url_nowscore <- rep("https://cp.nowscore.com/buy/DanChang.aspx?all=1&issueNum=26098", 2)
  s
}

identity_fake_answers <- function(items) {
  tibble::tibble(item_id = items$item_id, choice = rep("same_team", nrow(items)),
    p_same = rep(0.9, nrow(items)), p_different = rep(0.04, nrow(items)),
    p_review = rep(0.06, nrow(items)), confidence = rep(0.85, nrow(items)),
    model = rep("test-judge", nrow(items)))
}

testthat::test_that("source aliases remain evidence and exact side bypasses judge", {
  s <- identity_schedule_fixture(); before <- s
  called <- character()
  judge <- function(items) {
    called <<- items$item_id
    identity_fake_answers(items)[rev(seq_len(nrow(items))), ]
  }
  out <- judge_schedule_identity(s, judge)
  testthat::expect_identical(s, before)
  testthat::expect_setequal(called, c("26098:77:home", "26098:33:home"))
  testthat::expect_identical(out$review_state, c("auto", "auto", "exact", "exact"))
  testthat::expect_true(all(c("克鲁比04", "赫尔辛基预备队") %in% out$aliases_500[[1]]))
  testthat::expect_true(all(c("查普斯", "耶尔文佩") %in% out$aliases_500[[3]]))
  testthat::expect_equal(out$margin[1], 0.84)
})

testthat::test_that("exact normalization retains sex age and squad distinctions", {
  exact <- beidan:::schedule_alias_exact
  testthat::expect_true(exact(c(" Club-A ", "另名"), "club a"))
  testthat::expect_false(exact("都柏林大学", "都柏林"))
  testthat::expect_false(exact("赫尔辛基预备队", "赫尔辛基"))
  testthat::expect_false(exact("上海女足", "上海男足"))
  testthat::expect_false(exact("England U21", "England U19"))
  testthat::expect_false(exact(c(NA_character_, " "), ""))
})

testthat::test_that("uncertainty, missing judge, credential and failures stay visible", {
  s <- identity_schedule_fixture()
  testthat::expect_identical(judge_schedule_identity(s)$review_state[1], "unavailable")
  testthat::expect_identical(judge_schedule_identity(s, function(x) {
    jev_schedule_judge(x, api_key = "")
  })$review_state[1], "unavailable")
  testthat::expect_identical(judge_schedule_identity(s, function(x) stop("network"))$review_state[1], "error")
  uncertain <- function(x) {
    a <- identity_fake_answers(x); a$p_same <- .5; a$p_different <- .1; a$p_review <- .4; a
  }
  testthat::expect_identical(judge_schedule_identity(s, uncertain)$review_state[1], "review")
  review <- function(x) {
    a <- identity_fake_answers(x); a$choice <- "manual_review"; a$p_same <- .04; a$p_review <- .92; a
  }
  testthat::expect_identical(judge_schedule_identity(s, review)$review_state[1], "review")
})

testthat::test_that("malformed response does not silently reassign identities", {
  s <- identity_schedule_fixture()
  mutations <- list(
    function(a) a[-1, ],
    function(a) a[c(1, 1), ],
    function(a) {a$item_id[1] <- "other"; a},
    function(a) {a$p_same[1] <- NA_real_; a},
    function(a) {a$p_same[1] <- .2; a},
    function(a) {a$choice[1] <- "different_team"; a},
    function(a) {a$model[1] <- ""; a})
  for (mutation in mutations) {
    out <- judge_schedule_identity(s, function(x) mutation(identity_fake_answers(x)))
    testthat::expect_identical(out$review_state[1], "error")
    testthat::expect_identical(out$method[3], "exact_alias")
  }
})

testthat::test_that("empty and invalid schedule contracts are enforced", {
  out <- judge_schedule_identity(issue_schedule_empty(), function(x) stop("must not call"))
  testthat::expect_s3_class(out, "tbl_df")
  testthat::expect_identical(nrow(out), 0L)
  testthat::expect_type(out$choice, "character")
  testthat::expect_type(out$p_same, "double")
  s <- identity_schedule_fixture()
  testthat::expect_error(schedule_identity_items(s[c(1,1), ]), "duplicate")
  testthat::expect_error(schedule_identity_items(s[, !names(s) %in% "home_title_500"]), "evidence")
  testthat::expect_error(judge_schedule_identity(s, auto_accept = NA_real_))
  testthat::expect_error(judge_schedule_identity(s, minimum_margin = 2))
  testthat::expect_error(judge_schedule_identity(s, judge = 1))
  testthat::expect_equal(nrow(jev_schedule_judge(schedule_identity_items(issue_schedule_empty()))), 0)
})

testthat::test_that("real HTTP adapter batches and validates typed Jev response", {
  items <- schedule_identity_items(identity_schedule_fixture())[1, ]
  called <- 0L
  httr2::local_mocked_responses(function(req) {
    called <<- called + 1L
    testthat::expect_identical(req$url, "https://api.typesafe.ai/v1/systemone")
    httr2::response(status_code = 200, headers = list(`content-type` = "application/json"),
      body = charToRaw('{"model":"jev-test","answers":{"26098:77:home":{"type":"choice","choice":"same_team","probabilities":{"same_team":0.9,"different_team":0.04,"manual_review":0.06},"confidence":0.85}}}'))
  })
  out <- jev_schedule_judge(items, api_key = "fake-key")
  testthat::expect_identical(called, 1L)
  testthat::expect_identical(out$model, "jev-test")
  receipt <- attr(out, "judge_receipt")
  testthat::expect_false(grepl("fake-key", paste(capture.output(str(receipt)), collapse = "")))
  testthat::expect_true(all(c("克鲁比04", "赫尔辛基预备队") %in% receipt$request$state$items[[1]]$aliases_500))
  testthat::expect_error(jev_schedule_judge(items, api_key = "x", timeout = 0))
})

testthat::test_that("missing source names are not sent to a semantic judge", {
  s <- identity_schedule_fixture()[1, ]
  s$home_nowscore <- s$home_display_nowscore <- s$home_title_nowscore <- ""
  out <- judge_schedule_identity(s, function(x) stop("must not call"))
  testthat::expect_identical(out$review_state, c("unavailable", "exact"))
})

testthat::test_that("HTTP failures and malformed service bodies remain errors", {
  items <- schedule_identity_items(identity_schedule_fixture())[1, ]
  httr2::local_mocked_responses(function(req) {
    httr2::response(status_code = 503, headers = list(`content-type` = "application/json"), body = charToRaw('{}'))
  })
  testthat::expect_error(jev_schedule_judge(items, api_key = "fake"), class = "httr2_http_503")
  testthat::expect_error(jev_schedule_judge(items[, "item_id", drop=FALSE], api_key = "fake"))
})

testthat::test_that("receipts bind input evidence and decision thresholds", {
  s <- identity_schedule_fixture()
  a <- judge_schedule_identity(s)
  b <- judge_schedule_identity(s, auto_accept = .95)
  testthat::expect_identical(attr(a, "evidence_hash"), rlang::hash(schedule_identity_items(s)))
  testthat::expect_identical(attr(a, "implementation_hash"), attr(b, "implementation_hash"))
  testthat::expect_identical(attr(b, "identity_policy")$auto_accept, .95)
  s$home_title_500[1] <- "changed"
  testthat::expect_false(identical(attr(a, "evidence_hash"), attr(judge_schedule_identity(s), "evidence_hash")))
  testthat::expect_identical(attr(attr(a, "generated_at"), "tzone"), "Asia/Shanghai")
})

testthat::test_that("real saved response replays current policy without network", {
  fixture <- testthat::test_path("fixtures", "schedule_identity")
  s <- readRDS(file.path(fixture, "schedule.rds"))
  receipt <- readRDS(file.path(fixture, "jev_receipt.rds"))
  httr2::local_mocked_responses(function(req) stop("replay must not use network"))
  a <- replay_schedule_identity(s, receipt)
  testthat::expect_equal(sum(a$review_state == "auto"), 21)
  testthat::expect_equal(sum(a$review_state == "review"), 5)
  testthat::expect_identical(a$review_state[a$slot==77L & a$side=="home"], "review")
  testthat::expect_identical(a$review_state[a$slot==33L & a$side=="home"], "review")
  testthat::expect_identical(attr(a,"judge_receipt"), receipt)
  testthat::expect_identical(attr(a,"evidence_hash"), rlang::hash(schedule_identity_items(s)))
  b <- replay_schedule_identity(s, receipt, auto_accept = 1, minimum_margin = 1)
  testthat::expect_true(sum(b$review_state == "auto") < sum(a$review_state == "auto"))
  s$home_title_500[s$slot==77L] <- "different evidence"
  testthat::expect_true(any(replay_schedule_identity(s, receipt)$review_state == "error"))
  bad <- receipt
  bad$response$answers[[1]]$probabilities$same_team <- -1
  testthat::expect_true(any(replay_schedule_identity(readRDS(file.path(fixture,"schedule.rds")),bad)$review_state == "error"))
})

testthat::test_that("implementation receipts bind response helpers and adapters", {
  s <- identity_schedule_fixture()
  first <- judge_schedule_identity(s, identity_fake_answers)
  adapter <- function(items) identity_fake_answers(items)
  second <- judge_schedule_identity(s, adapter)
  testthat::expect_false(identical(attr(first,"implementation_hash"), attr(second,"implementation_hash")))
  original <- beidan:::jev_schedule_answers
  testthat::local_mocked_bindings(jev_schedule_answers = function(response, items) original(response, items),
                                .package = "beidan")
  third <- judge_schedule_identity(s, identity_fake_answers)
  testthat::expect_false(identical(attr(first,"implementation_hash"), attr(third,"implementation_hash")))
})
