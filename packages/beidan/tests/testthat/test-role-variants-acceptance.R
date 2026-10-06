# Controller-owned independent numerical regressions for #553.
# Synthetic declared probabilities and SP, no source labels or network.

test_that("raw SP and the one ticket payout factor reproduce hand-computed EV", {
  cutoff <- list(issue_id = "26098",
    cutoff_utc = as.POSIXct("2026-09-26 12:00:00", tz = "UTC"))
  matches <- tibble::tibble(fixture_id = c("T", "D"),
    win = c(.40, .50), draw = c(.30, .30), lose = c(.30, .20))
  sp <- tibble::tibble(fixture_id = rep(c("T", "D"), each = 3),
    outcome = rep(c("W", "D", "L"), 2), quote_at = rep(cutoff$cutoff_utc - 60, 6),
    sp_raw = c(12, 3, 3, 3, 3, 3), source_url = rep("synthetic://SP", 6))
  settings <- parlay_settings()
  settings$n_legs <- 2L
  settings$unit_cny <- 2
  settings$payout_factor <- .65
  ranked <- rank_outcome_selections(prepare_outcome_selections(matches), cutoff)
  pool <- parlay_construct_role_groups(ranked, settings, pattern = c(3L, 2L),
    max_candidates = 1L, prematch_sp = sp)
  full <- parlay_select_groups(pool, objective="coverage", budget_cny = NULL,
    group_budget_cny = NULL, reuse_policy = list(max_reuse = 4L),
    overlap_policy = list(max_overlap = 3L))$evaluation
  expect_identical(nrow(full$purchases), 6L)
  expect_equal(full$summary$spent_cny, 12)
  expect_equal(full$summary$actual_coverage, .8, tolerance = 1e-12)
  # .8 * (.4*12 + .3*3 + .3*3) * 3 * 2 * .65 = 20.592 gross,
  # 12 CNY stake yields 8.592 net. A per-leg .65 factor or SP replacement fails.
  expect_equal(full$summary$ev_net_cny, 8.592, tolerance = 1e-12)
  expect_equal(max(full$purchases$sp_product_est), 36)
  top <- parlay_select_groups(pool, objective="coverage", budget_cny = NULL,
    group_budget_cny = 4, reuse_policy = list(max_reuse = 4L),
    overlap_policy = list(max_overlap = 3L))$evaluation
  expect_equal(top$purchases$probability, c(.20, .15), tolerance = 1e-12)
  expect_equal(top$summary$actual_coverage, .35, tolerance = 1e-12)
  expect_equal(top$summary$ev_net_cny, 7.115, tolerance = 1e-12)
  expect_false(any(full$plan$ticket_legs$fixture_id == "D" &
    full$plan$ticket_legs$outcome == "L"))
  sp <- sp[!(sp$fixture_id == "D" & sp$outcome == "D"), ]
  missing <- parlay_construct_role_groups(ranked, settings, pattern = c(3L, 2L),
    max_candidates = 1L, prematch_sp = sp)
  missing <- parlay_select_groups(missing, objective="coverage", budget_cny = NULL,
    group_budget_cny = NULL, reuse_policy = list(max_reuse = 4L),
    overlap_policy = list(max_overlap = 3L))$evaluation
  expect_false(missing$summary$ev_available)
  expect_true(is.na(missing$summary$ev_net_cny))
  expect_equal(missing$summary$actual_coverage, .8, tolerance = 1e-12)
  changed <- pool
  changed$cutoff$cutoff_utc <- changed$cutoff$cutoff_utc + 60
  expect_error(parlay_select_groups(changed, objective="coverage", reuse_policy = list(max_reuse = 4L),
    overlap_policy = list(max_overlap = 3L))$evaluation, "cutoff")
})

test_that("exact union handles overlaps, duplicate and nested ticket events", {
  probabilities <- tibble::tibble(
    fixture_id=rep(c("A","B","C"),each=3),
    outcome=rep(c("W","D","L"),3),
    probability=c(.6,.2,.2,.5,.3,.2,.4,.3,.3))
  legs <- tibble::tibble(
    ticket_id=c("AB","AB","AC","AC"),
    fixture_id=c("A","B","A","C"), outcome=rep("W",4),leg_order=rep(1:2,2))
  expect_equal(beidan:::.parlay_ranked_union_coverage(c("AB","AC"),legs,probabilities),
               .6*(.5+.4-.5*.4), tolerance=1e-12)
  expect_equal(beidan:::.parlay_ranked_union_coverage(c("AB","AB"),legs,probabilities),
               .6*.5, tolerance=1e-12)
  duplicate <- dplyr::bind_rows(legs,dplyr::mutate(legs[legs$ticket_id=="AB",],ticket_id="copy"))
  expect_equal(beidan:::.parlay_ranked_union_coverage(c("AB","AC","copy"),duplicate,probabilities),
               .42, tolerance=1e-12)
  nested <- dplyr::bind_rows(legs,tibble::tibble(ticket_id="A",fixture_id="A",outcome="W",leg_order=1L))
  expect_equal(beidan:::.parlay_ranked_union_coverage(c("AB","AC","A"),nested,probabilities),
               .6, tolerance=1e-12)
})


test_that("actual_pattern reports selected outcome counts and single cannot fall back", {
  cutoff <- list(issue_id = "26098",
    cutoff_utc = as.POSIXct("2026-09-26 12:00:00", tz = "UTC"))
  settings <- parlay_settings()
  settings$n_legs <- 7L
  matches <- tibble::tibble(fixture_id = sprintf("F%02d",1:7),
    win = c(rep(.4,3),rep(.5,3),.55),
    draw = c(rep(.3,6),.23),lose = c(rep(.3,3),rep(.2,3),.22))
  ranked <- rank_outcome_selections(prepare_outcome_selections(matches),cutoff)
  pool <- parlay_construct_role_groups(ranked,settings,
    pattern=c(3L,3L,3L,2L,2L,2L,1L),max_candidates=1L)
  expect_identical(pool$role_legs$base_role,c(3L,3L,3L,2L,2L,2L,1L))
  expect_identical(pool$role_legs$n_outcomes,c(3L,3L,3L,2L,2L,2L,2L))
  expect_identical(pool$group_patterns$actual_pattern[[1L]],
    c(3L,3L,3L,2L,2L,2L,2L))
  expect_equal(prod(pool$group_patterns$actual_pattern[[1L]]),432)
  settings$n_legs <- 2L
  no_single <- tibble::tibble(fixture_id=c("T","D"),
    win=c(.4,.5),draw=c(.3,.3),lose=c(.3,.2))
  ranked <- rank_outcome_selections(prepare_outcome_selections(no_single),cutoff)
  pool <- parlay_construct_role_groups(ranked,settings,
    pattern=c(3L,1L),max_candidates=1L)
  expect_identical(nrow(pool$groups),0L)
})

test_that("selection freezes original candidate legs without post-selection changes", {
  cutoff <- list(issue_id="26098",
    cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  matches <- tibble::tibble(fixture_id=c("T1","T2","D1","D2"),
    win=c(.40,.35,.50,.49),draw=c(.30,.33,.35,.31),lose=c(.30,.32,.15,.20))
  settings <- parlay_settings()
  settings$n_legs <- 2L
  pool <- parlay_construct_role_groups(
    rank_outcome_selections(prepare_outcome_selections(matches),cutoff),
    settings,pattern=c(3L,2L),max_candidates=1L)
  selected <- parlay_select_groups(pool, objective="coverage", group_budget_cny=2,
    reuse_policy=list(max_reuse=4L),overlap_policy=list(max_overlap=3L))
  evaluation <- selected$evaluation
  expect_identical(evaluation$final$role_legs,pool$role_legs)
  expect_false(evaluation$diagnostics$improvement_enabled)
  expect_equal(evaluation$summary$spent_cny,2)
  expect_identical(nrow(evaluation$purchases),1L)
  block <- pool$role_legs
  probabilities <- tidyr::pivot_wider(pool$probabilities,
    names_from=outcome,values_from=probability)
  top_mass <- prod(vapply(seq_len(nrow(block)),function(i) {
    row <- probabilities[probabilities$fixture_id==block$fixture_id[i],]
    max(as.numeric(row[block$allowed_outcomes[[i]]]))
  },numeric(1)))
  expect_equal(evaluation$summary$actual_coverage,top_mass,tolerance=1e-12)
})


test_that("permuting leg order does not emit duplicate physical groups", {
  cutoff <- list(issue_id="26098",
    cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  matches <- tibble::tibble(fixture_id=c("A","B"),
    win=.5,draw=.3,lose=.2)
  settings <- parlay_settings()
  settings$n_legs <- 2L
  ranked <- rank_outcome_selections(prepare_outcome_selections(matches),cutoff)
  pool <- parlay_construct_role_groups(ranked,settings,
    pattern=c(2L,2L),max_candidates=NULL)
  expect_identical(nrow(pool$groups),1L)
  expect_identical(pool$generation_status$stop_reason,"state_repeated")
  expect_setequal(pool$role_legs$fixture_id,c("A","B"))
  expect_true("duplicate_candidate_package" %in% pool$shortages$reason)
  prefix <- parlay_construct_role_groups(ranked,settings,
    pattern=c(2L,2L),max_candidates=1L)
  expect_identical(prefix$role_legs,pool$role_legs)
  evaluation <- parlay_select_groups(pool, objective="coverage",budget_cny=NULL,
    group_budget_cny=NULL,reuse_policy=list(max_reuse=4L),
    overlap_policy=list(max_overlap=3L))$evaluation
  expect_identical(nrow(evaluation$purchases),4L)
  expect_equal(evaluation$summary$spent_cny,8)
  expect_equal(evaluation$summary$actual_coverage,.64,tolerance=1e-12)
})


test_that("dimensioned and classed numeric controls are not valid planning vectors", {
  cutoff <- list(issue_id="26098",
    cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  ranked <- rank_outcome_selections(prepare_outcome_selections(
    tibble::tibble(fixture_id="A",win=.50,draw=.30,lose=.20)),cutoff)
  settings <- parlay_settings()
  settings$n_legs <- 1L
  for (bad in list(matrix(2,1,1),structure(2,class="custom_control"))) {
    expect_error(parlay_construct_role_groups(ranked,settings,pattern=bad),"pattern")
    expect_error(parlay_construct_role_groups(ranked,settings,pattern=2L,
      max_candidates=bad),"max_candidates")
  }
  pool <- parlay_construct_role_groups(ranked,settings,pattern=2L,max_candidates=1L)
  for (bad in list(matrix(1,1,1),structure(1,class="custom_control"))) {
    expect_error(parlay_select_groups(pool, objective="coverage",reuse_policy=list(max_reuse=bad),
      overlap_policy=list(max_overlap=1L))$evaluation,"whole number")
    expect_error(parlay_select_groups(pool, objective="coverage",reuse_policy=list(max_reuse=4L),
      overlap_policy=list(max_overlap=bad))$evaluation,"whole number")
  }
})


test_that("purchase refuses missing or stale construction identity", {
  cutoff <- list(issue_id="26098",
    cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  settings <- parlay_settings()
  settings$n_legs <- 1L
  ranked <- rank_outcome_selections(prepare_outcome_selections(
    tibble::tibble(fixture_id="A",win=.50,draw=.30,lose=.20)),cutoff)
  pool <- parlay_construct_role_groups(ranked,settings,pattern=2L,max_candidates=1L)
  evaluate <- function(value) parlay_select_groups(value, objective="coverage",
    reuse_policy=list(max_reuse=4L),overlap_policy=list(max_overlap=3L))$evaluation
  missing <- pool
  missing$construction_code_hash <- NULL
  expect_error(evaluate(missing),"construction implementation binding")
  stale <- pool
  stale$construction_code_hash <- "00000000000000000000000000000000"
  expect_error(evaluate(stale),"construction implementation binding")
  missing <- pool
  missing$ranked_selections_hash <- NULL
  expect_error(evaluate(missing),"ranked_selections.*hash")
  testthat::local_mocked_bindings(.parlay_ranked_candidate_signature=function(block) {
    stop("changed constructor helper")
  },.package="beidan")
  expect_error(evaluate(pool),"construction implementation binding")
})


test_that("accepted probability-sum tolerance survives construction and purchase", {
  cutoff <- list(issue_id="26098",
    cutoff_utc=as.POSIXct("2026-09-26 12:00:00",tz="UTC"))
  matches <- tibble::tibble(fixture_id="T",
    win=.4,draw=.3,lose=.3000000005)
  settings <- parlay_settings()
  settings$n_legs <- 1L
  pool <- parlay_construct_role_groups(
    rank_outcome_selections(prepare_outcome_selections(matches),cutoff),
    settings,pattern=3L,max_candidates=1L)
  expect_equal(pool$role_legs$retained_probability,1.0000000005,tolerance=1e-12)
  result <- parlay_select_groups(pool, objective="coverage",budget_cny=NULL,group_budget_cny=NULL,
    reuse_policy=list(max_reuse=4L),overlap_policy=list(max_overlap=3L))$evaluation
  expect_identical(nrow(result$purchases),3L)
  expect_equal(result$summary$spent_cny,6)
  expect_equal(result$summary$actual_coverage,1.0000000005,tolerance=1e-12)
  expect_equal(sort(result$purchases$probability),
    c(.3,.3000000005,.4),tolerance=1e-12)
  expect_equal(pool$probabilities$probability[pool$probabilities$outcome=="L"],
    .3000000005,tolerance=0)
})
