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
  s$league_500 <- c("芬甲", "爱甲")
  s$league_nowscore <- c("芬甲", "爱超")
  s$provider_id_500 <- c("1370919", "1382740")
  s$provider_id_nowscore <- c("2921946", "2939061")
  s$kickoff_at <- lubridate::ymd_hms(c("2026-09-25 20:00:00", "2026-09-25 22:30:00"), tz = "Asia/Shanghai")
  s$kickoff_hhmm <- c("20:00", "22:30")
  s$kickoff_date_source <- rep("js-kickoff-date", 2)
  s$sale_end_raw_500 <- c("2026-09-25 19:50", "2026-09-25 22:20")
  s$sale_end_raw_nowscore <- c("2026-09-25 19:55", "2026-09-25 22:25")
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
  testthat::expect_true(all(c("克鲁比04", "赫尔辛基预备队") %in% receipt$request$state$items[[1]]$side_aliases_500))
  testthat::expect_true("耶尔文佩" %in% receipt$request$state$items[[1]]$opponent_aliases_500)
  testthat::expect_true(receipt$request$state$items[[1]]$opponent_exact_alias$value)
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

testthat::test_that("obsolete saved receipt is rejected instead of replayed as fresh", {
  fixture <- testthat::test_path("fixtures", "schedule_identity")
  receipt <- readRDS(file.path(fixture, "jev_receipt.rds"))
  httr2::local_mocked_responses(function(req) stop("replay must not use network"))
  # The saved real receipt predates the opposite-side/kickoff/sale evidence
  # contract. Its request must not be replayed as a fresh inference. NOTE: the
  # saved schedule.rds also predates the two source sale-end raw columns, so the
  # current fixture supplies the current-schema schedule; control regenerates the
  # real RDS from saved raw bytes and runs one new inference.
  testthat::expect_true(all(c("opponent_aliases_500", "kickoff_at_nowscore",
    "sale_end_raw_500") %in% names(receipt$request$state$items[[1]])) == FALSE)
  s <- identity_schedule_fixture()
  a <- replay_schedule_identity(s, receipt)
  testthat::expect_true(any(a$review_state == "error"))
  testthat::expect_true(all(!is.na(a$choice)))
  testthat::expect_identical(attr(a, "evidence_hash"), rlang::hash(schedule_identity_items(s)))
  bad <- receipt
  bad$response$answers[[1]]$probabilities$same_team <- -1
  testthat::expect_true(any(replay_schedule_identity(s, bad)$review_state == "error"))
})

testthat::test_that("opposite-side aliases and exact support come from both sources", {
  s <- identity_schedule_fixture()
  items <- schedule_identity_items(s)
  slot77_home <- items[items$slot == 77L & items$side == "home", ]
  testthat::expect_true("耶尔文佩" %in% slot77_home$opponent_aliases_500[[1]])
  testthat::expect_true("耶尔文佩" %in% slot77_home$opponent_aliases_nowscore[[1]])
  testthat::expect_true(slot77_home$opponent_exact_alias)
  slot33_home <- items[items$slot == 33L & items$side == "home", ]
  testthat::expect_true("布雷流浪者" %in% slot33_home$opponent_aliases_500[[1]])
  testthat::expect_true("布雷流浪者" %in% slot33_home$opponent_aliases_nowscore[[1]])
  testthat::expect_true(slot33_home$opponent_exact_alias)
  # Judged side's own exact support is independent of the opponent's.
  testthat::expect_true(slot77_home$opponent_exact_alias)
  testthat::expect_false(schedule_alias_exact(slot77_home$aliases_500[[1]], slot77_home$aliases_nowscore[[1]]))
})

testthat::test_that("changed opponent name flips exact support and binds hashes", {
  s <- identity_schedule_fixture()
  a <- judge_schedule_identity(s)
  request_a <- beidan:::jev_schedule_request(schedule_identity_items(s), "m")
  s$away_nowscore[1] <- s$away_display_nowscore[1] <- s$away_title_nowscore[1] <- "另一个队"
  items <- schedule_identity_items(s)
  testthat::expect_false(items$opponent_exact_alias[items$slot == 77L & items$side == "home"])
  testthat::expect_false(identical(attr(a, "evidence_hash"), rlang::hash(items)))
  testthat::expect_false(identical(request_a, beidan:::jev_schedule_request(items, "m")))
})

testthat::test_that("kickoff origin and per-source sale cutoffs are preserved without agreement claims", {
  items <- schedule_identity_items(identity_schedule_fixture())
  request <- beidan:::jev_schedule_request(items, "m")
  evidence <- request$state$items[["26098:77:home"]]
  testthat::expect_identical(evidence$kickoff_at_nowscore, "2026-09-25T20:00:00+0800")
  testthat::expect_identical(evidence$kickoff_hhmm, "20:00")
  testthat::expect_identical(evidence$kickoff_date_source, "js-kickoff-date")
  testthat::expect_match(evidence$kickoff_at_nowscore_explanation, "NOT cross-source agreement")
  testthat::expect_match(evidence$sale_cutoff_note, "DIFFERENT")
  testthat::expect_identical(evidence$sale_end_raw_500, "2026-09-25 19:50")
  testthat::expect_identical(evidence$sale_end_raw_nowscore, "2026-09-25 19:55")
  testthat::expect_false(identical(evidence$sale_end_raw_500, evidence$sale_end_raw_nowscore))
  testthat::expect_false(any(grepl("agreement", tolower(evidence$kickoff_at_nowscore_explanation)) &&
    !grepl("NOT cross-source agreement", evidence$kickoff_at_nowscore_explanation)))
  testthat::expect_false(grepl("kickoff", evidence$sale_cutoff_note, ignore.case = TRUE) &&
    grepl("estimate", evidence$sale_cutoff_note) && !grepl("neither is a kickoff estimate", evidence$sale_cutoff_note))
})

testthat::test_that("missing evidence is explicit and invalid datetime types fail", {
  s <- identity_schedule_fixture()
  s$kickoff_at[1] <- lubridate::as_datetime(NA_real_, tz = "Asia/Shanghai")
  s$kickoff_hhmm[1] <- NA_character_
  s$kickoff_date_source[1] <- "absent"
  s$sale_end_raw_500[1] <- NA_character_
  items <- schedule_identity_items(s)
  testthat::expect_true(is.na(items$kickoff_at[1]))
  request <- beidan:::jev_schedule_request(items, "m")
  evidence <- request$state$items[["26098:77:home"]]
  testthat::expect_true(is.null(evidence$kickoff_at_nowscore) || is.na(evidence$kickoff_at_nowscore))
  testthat::expect_true(is.null(evidence$sale_end_raw_500) || is.na(evidence$sale_end_raw_500))
  testthat::expect_error(schedule_identity_items(s[s$slot == 1L, !names(s) %in% "kickoff_at"]), "evidence")
  testthat::expect_error(
    schedule_identity_items(within(s, kickoff_at <- rep(NA, nrow(s)))), "kickoff_at must be POSIXct")
  testthat::expect_error(beidan:::jev_schedule_request(items[0, ], "m"), "must not be empty")
  testthat::expect_error(beidan:::schedule_identity_iso(as.Date("2026-09-25")), "must be POSIXct")
})

testthat::test_that("opponent exact support keeps women age and reserve distinctions", {
  exact <- beidan:::schedule_alias_exact
  testthat::expect_false(exact("上海女足", "上海男足"))
  testthat::expect_false(exact("England U21", "England U19"))
  testthat::expect_false(exact("赫尔辛基预备队", "赫尔辛基"))
  testthat::expect_false(exact("耶尔文佩", "耶尔文佩女足"))
  s <- identity_schedule_fixture()
  s$away_nowscore[1] <- s$away_display_nowscore[1] <- s$away_title_nowscore[1] <- "耶尔文佩女足"
  items <- schedule_identity_items(s)
  testthat::expect_false(items$opponent_exact_alias[items$slot == 77L & items$side == "home"])
  testthat::expect_true(all(items$league_exact[items$slot == 77L]))
  testthat::expect_false(any(items$league_exact[items$slot == 33L]))
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

testthat::test_that("context response replays through production without network", {
  fixture <- testthat::test_path("fixtures", "schedule_identity")
  schedule <- readRDS(file.path(fixture, "schedule.rds"))
  receipt <- readRDS(file.path(fixture, "jev_context_receipt.rds"))
  httr2::local_mocked_responses(function(req) stop("replay must not contact network"))
  result <- replay_schedule_identity(schedule, receipt)
  testthat::expect_equal(nrow(result), 292L)
  testthat::expect_false(any(result$review_state %in% c("error", "unavailable")))
  testthat::expect_true(result$opponent_exact_alias[result$slot == 77L & result$side == "home"])
  testthat::expect_identical(attr(result, "judge_receipt"), receipt)
  schedule$away_title_500[schedule$slot == 77L] <- "altered opponent evidence"
  testthat::expect_true(any(replay_schedule_identity(schedule, receipt)$review_state == "error"))
})

testthat::test_that("context serialization helpers bind the implementation receipt", {
  s <- identity_schedule_fixture()
  before <- judge_schedule_identity(s)
  original <- beidan:::schedule_identity_iso
  testthat::local_mocked_bindings(schedule_identity_iso = function(value) original(value), .package = "beidan")
  after <- judge_schedule_identity(s)
  testthat::expect_false(identical(attr(before,"implementation_hash"),attr(after,"implementation_hash")))
})
