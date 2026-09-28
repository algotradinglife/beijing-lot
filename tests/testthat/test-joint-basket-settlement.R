source(testthat::test_path("..", "..", "r", "joint_basket_settlement.R"))
source(testthat::test_path("..", "..", "r", "nowscore_query.R"))

# --- helpers ---------------------------------------------------------------

# Minimal but schema-faithful settlement database: the authoritative reader
# requires a single build receipt plus observation/option_sp/finding.
# omit_sp_slots drops the option_sp row for those slots of the FIRST issue, which
# is how the real archive represents a fixture with no recorded result.
write_settlement_db <- function(path, n_slot = 8L, issues = c("100101", "100102"),
                                sp_w = 2.5, sp_d = 3.0, sp_l = 4.0,
                                correction = NULL, source_pure = TRUE,
                                omit_sp_slots = integer()) {
  con <- DBI::dbConnect(RSQLite::SQLite(), path)
  on.exit(DBI::dbDisconnect(con), add = TRUE)
  DBI::dbExecute(con, "CREATE TABLE receipt (payload_json TEXT)")
  DBI::dbExecute(con, "CREATE TABLE observation (observation_id INTEGER, issue TEXT,
    slot INTEGER, play TEXT, native_match_id TEXT, status TEXT, score TEXT,
    halftime_score TEXT, expected_option TEXT, source_sha256 TEXT, source_url TEXT,
    received_at TEXT, payload_json TEXT)")
  DBI::dbExecute(con, "CREATE TABLE option_sp (observation_id INTEGER, option TEXT,
    raw_sp TEXT, sp REAL, cell_id TEXT)")
  DBI::dbExecute(con, "CREATE TABLE finding (issue TEXT, slot INTEGER, play TEXT,
    code TEXT, detail TEXT, source_sha256 TEXT)")
  receipt <- jsonlite::toJSON(list(source = "nowscore", production_enabled = FALSE,
                                   source_pure = source_pure), auto_unbox = TRUE)
  DBI::dbExecute(con, "INSERT INTO receipt VALUES (?)", params = list(receipt))
  oid <- 0L
  for (ii in seq_along(issues)) {
    for (s in seq_len(n_slot)) {
      oid <- oid + 1L
      oc <- (s - 1L) %% 3L + 1L                      # deterministic realised direction
      opt <- c("胜", "平", "负")[oc]
      spv <- c(sp_w, sp_d, sp_l)[oc]
      payload <- jsonlite::toJSON(list(home = paste0("H", s), away = paste0("A", s),
                                       handicap_raw = "0", issue = issues[ii], slot = s),
                                  auto_unbox = TRUE)
      DBI::dbExecute(con, "INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        params = list(oid, issues[ii], s, "spf", as.character(300000L + oid), "完场",
                      "2-0", "1-0", opt, "sha", "url", "2026-01-01T00:00:00+00:00", payload))
      if (ii == 1L && s %in% omit_sp_slots) next
      DBI::dbExecute(con, "INSERT INTO option_sp VALUES (?,?,?,?,?)",
        params = list(oid, opt, as.character(spv), spv, paste0("archive_result_", oc)))
    }
  }
  if (!is.null(correction)) {
    # A corrected build stores the corrected SP in option_sp and keeps the
    # superseded value in the audit table.
    DBI::dbExecute(con, "UPDATE option_sp SET raw_sp = ?, sp = ? WHERE observation_id = ? AND option = ?",
      params = list(correction[[5]], correction[[6]], correction[[1]], correction[[2]]))
    DBI::dbExecute(con, "CREATE TABLE sp_correction (observation_id INTEGER, option TEXT,
      old_raw_sp TEXT, old_sp REAL, new_raw_sp TEXT, new_sp REAL, source TEXT,
      source_url TEXT, note TEXT)")
    DBI::dbExecute(con, "INSERT INTO sp_correction VALUES (?,?,?,?,?,?,?,?,?)", params = correction)
  }
  path
}

make_legs <- function(issue = "100101", baskets = 1:2, tickets = c(4L, 2L), n_slot = 8L) {
  ii <- match(issue, c("100101", "100102"))
  out <- list()
  for (b in baskets) {
    # 7 legs, cyclic slots; realised direction follows the same cycling as the DB
    slots <- ((b - 1L) * 7L + seq_len(7L) - 1L) %% n_slot + 1L
    out[[length(out) + 1L]] <- tibble::tibble(
      issue = issue, cohort = "ORIGINAL", basket = b, leg = seq_len(7L), slot = slots,
      provider_id = as.character(300000L + (ii - 1L) * n_slot + slots),
      outcome = (slots - 1L) %% 3L + 1L, tickets = tickets[b])
  }
  dplyr::bind_rows(out)
}

make_sp <- function(issues = c("100101", "100102"), n_slot = 8L) {
  out <- list()
  for (iss in issues) {
    s <- seq_len(n_slot)
    oc <- (s - 1L) %% 3L + 1L
    out[[length(out) + 1L]] <- tibble::tibble(
      issue = iss, slot = s,
      provider_id = as.character(300000L + (which(issues == iss) - 1L) * n_slot + s),
      option = c("胜", "平", "负")[oc], sp = c(2.5, 3.0, 4.0)[oc], sp_source = "nowscore")
  }
  dplyr::bind_rows(out)
}

# --- jb_official_sp --------------------------------------------------------

test_that("jb_official_sp reads one row per settled spf slot", {
  dir <- withr::local_tempdir()
  db <- write_settlement_db(file.path(dir, "s.sqlite"))
  sp <- jb_official_sp(db, c("100101", "100102"), progress_every = 0L)
  expect_named(sp, jb_sp_columns)
  expect_equal(nrow(sp), 16L)
  expect_true(all(sp$sp > 0))
  expect_true(all(sp$option %in% c("胜", "平", "负")))
  expect_equal(anyDuplicated(sp[c("issue", "slot")]), 0L)
})

test_that("jb_official_sp preserves a fixture with no recorded result as NA", {
  dir <- withr::local_tempdir()
  db <- write_settlement_db(file.path(dir, "s.sqlite"), omit_sp_slots = c(2L, 5L))
  sp <- jb_official_sp(db, "100101", progress_every = 0L)
  expect_equal(nrow(sp), 8L)                      # the row is kept, not dropped
  expect_true(all(is.na(sp$sp[sp$slot %in% c(2L, 5L)])))
  expect_true(all(is.na(sp$option[sp$slot %in% c(2L, 5L)])))
  expect_true(all(!is.na(sp$sp[!sp$slot %in% c(2L, 5L)])))
})

test_that("jb_official_sp applies the recorded SP correction", {
  dir <- withr::local_tempdir()
  db <- write_settlement_db(file.path(dir, "s.sqlite"),
    correction = list(1L, "胜", "2.5", 2.5, "9.9", 9.9, "manual", "src", "fix"))
  sp <- jb_official_sp(db, "100101", progress_every = 0L)
  expect_equal(sp$sp[sp$slot == 1L], 9.9)
  expect_equal(sp$sp_source[sp$slot == 1L], "manual")
})

test_that("jb_official_sp fails closed on a missing issue or bad arguments", {
  dir <- withr::local_tempdir()
  db <- write_settlement_db(file.path(dir, "s.sqlite"))
  expect_error(jb_official_sp(db, "999999", progress_every = 0L), "no spf settlement")
  expect_error(jb_official_sp(file.path(dir, "nope.sqlite"), "100101"), "existing SQLite file")
  expect_error(jb_official_sp(db, c("100101", "100101")), "unique")
})

# --- jb_attach_sp ----------------------------------------------------------

test_that("jb_attach_sp binds each leg to its official SP", {
  legs <- make_legs(); sp <- make_sp()
  out <- jb_attach_sp(legs, sp)
  expect_equal(nrow(out), nrow(legs))
  expect_true(all(is.finite(out$sp)))
  expect_true(all(out$sp_source == "nowscore"))
  # the recorded winning option must agree with the derived outcome
  expect_true(all(sp$option[match(paste(out$issue, out$slot), paste(sp$issue, sp$slot))] ==
                    jb_option_of_outcome[as.character(out$outcome)]))
})

test_that("jb_attach_sp keeps NA SP instead of failing the whole portfolio", {
  dir <- withr::local_tempdir()
  db <- write_settlement_db(file.path(dir, "s.sqlite"), omit_sp_slots = 1L)
  sp <- jb_official_sp(db, c("100101", "100102"), progress_every = 0L)
  out <- jb_attach_sp(make_legs(), sp)
  expect_equal(sum(is.na(out$sp)), 2L)   # slot 1 appears in both baskets
  expect_true(all(is.na(out$sp[out$slot == 1L])))
})

test_that("jb_attach_sp fails closed on an unjoinable or disagreeing leg", {
  legs <- make_legs(); sp <- make_sp()
  expect_error(jb_attach_sp(legs, sp[sp$slot != 1L, ]), "no settlement row at all")
  bad <- sp; bad$provider_id[1] <- "999"
  expect_error(jb_attach_sp(legs, bad), "provider identity disagrees")
  wrong <- sp; wrong$option[1] <- "负"
  expect_error(jb_attach_sp(legs, wrong), "outcome/SP option disagreement")
  expect_error(jb_attach_sp(legs, rbind(sp, sp[1, ])), "duplicated issue/slot")
  noout <- legs; noout$outcome[1] <- 9L
  expect_error(jb_attach_sp(noout, sp), "outcome outside 1..3")
  expect_error(jb_attach_sp(legs[0, ], sp), "no legs")
})

# --- jb_priceable_baskets --------------------------------------------------

test_that("jb_priceable_baskets marks every fully priced basket", {
  legs <- jb_attach_sp(make_legs(), make_sp())
  per <- jb_priceable_baskets(legs)
  expect_equal(nrow(per), 2L)
  expect_true(all(per$priceable))
  expect_equal(per$n_priced, c(7L, 7L))
})

test_that("jb_priceable_baskets excludes a basket with one unpriced leg", {
  dir <- withr::local_tempdir()
  db <- write_settlement_db(file.path(dir, "s.sqlite"), omit_sp_slots = 1L)
  sp <- jb_official_sp(db, c("100101", "100102"), progress_every = 0L)
  per <- jb_priceable_baskets(jb_attach_sp(make_legs(), sp))
  expect_false(any(per$priceable))          # slot 1 sits in both baskets
  expect_equal(per$n_priced, c(6L, 6L))
})

test_that("jb_priceable_baskets fails closed on a malformed basket", {
  legs <- jb_attach_sp(make_legs(), make_sp())
  expect_error(jb_priceable_baskets(legs[legs$leg != 7L, ]), "exactly 7 legs")
  expect_error(jb_priceable_baskets(legs[0, ]), "no legs")
  expect_error(jb_priceable_baskets(dplyr::select(legs, -sp)), "must include issue, basket, sp")
})

# --- jb_basket_gross -------------------------------------------------------

test_that("jb_basket_gross applies unit * factor * prod(SP) once", {
  legs <- jb_attach_sp(make_legs(), make_sp())
  g <- jb_basket_gross(legs)
  expect_equal(nrow(g), 2L)
  manual <- legs |> dplyr::filter(.data$basket == 1L)
  expect_equal(g$gross_if_hit[g$basket == 1L], 2 * 0.65 * prod(manual$sp))
  expect_equal(g$break_even_depth[g$basket == 1L], floor(g$gross_if_hit[g$basket == 1L] / 2))
  expect_equal(g$tickets, c(4L, 2L))
})

test_that("jb_basket_gross saturates break-even at the 2187-tuple bound", {
  # Force a payout far above 2187 * unit so the clamp is the binding term.
  legs <- jb_attach_sp(make_legs(), make_sp())
  big <- legs
  big$sp <- big$sp * 100
  g <- jb_basket_gross(big)
  expect_true(all(g$gross_if_hit / 2 > 2187))
  expect_true(all(g$break_even_depth == 2187L))
  # below the bound it is the plain floor
  small <- legs
  small$sp <- 1.01
  gs <- jb_basket_gross(small)
  expect_equal(gs$break_even_depth, floor(gs$gross_if_hit / 2))
})

test_that("jb_basket_gross fails closed on business constants and shapes", {
  legs <- jb_attach_sp(make_legs(), make_sp())
  expect_error(jb_basket_gross(legs, unit_cny = 1), "unit_cny must be 2")
  expect_error(jb_basket_gross(legs, payout_factor = 0.5), "payout_factor must be 0.65")
  expect_error(jb_basket_gross(legs[legs$leg != 7L, ]), "exactly 7 distinct legs")
  dup <- rbind(legs, legs[legs$leg == 1L, ])
  expect_error(jb_basket_gross(dup), "exactly 7 distinct legs")
  bad <- legs; bad$sp[1] <- 0
  expect_error(jb_basket_gross(bad), "SP must be finite and positive")
  nap <- legs; nap$sp[1] <- NA_real_
  expect_error(jb_basket_gross(nap), "unpriceable basket passed")
  twotix <- legs; twotix$tickets[twotix$basket == 1L & twotix$leg == 1L] <- 9L
  expect_error(jb_basket_gross(twotix), "tickets must be constant")
  expect_error(jb_basket_gross(legs[0, ]), "no legs")
})

# --- jb_issue_returns ------------------------------------------------------

test_that("jb_issue_returns pays only hitting baskets and nets the stake", {
  legs <- jb_attach_sp(make_legs(), make_sp())
  g <- jb_basket_gross(legs)
  baskets <- tibble::tibble(issue = "100101", cohort = "ORIGINAL", basket = 1:2,
                            tickets = c(4L, 2L), rank_full = c(2L, 900L), hit = c(TRUE, FALSE))
  r <- jb_issue_returns(baskets, g)
  expect_equal(nrow(r), 1L)
  expect_equal(r$stake, 12)
  expect_equal(r$gross, g$gross_if_hit[g$basket == 1L])
  expect_equal(r$net, r$gross - 12)
  expect_equal(r$roi, r$net / 12)
  expect_equal(r$hits, 1L)
})

test_that("jb_issue_returns fails closed on inconsistent or missing input", {
  legs <- jb_attach_sp(make_legs(), make_sp())
  g <- jb_basket_gross(legs)
  ok <- tibble::tibble(issue = "100101", cohort = "ORIGINAL", basket = 1:2,
                       tickets = c(4L, 2L), rank_full = c(2L, 900L), hit = c(TRUE, FALSE))
  bad <- ok; bad$hit[2] <- TRUE
  expect_error(jb_issue_returns(bad, g), "hit disagrees with the bought-rank definition")
  expect_error(jb_issue_returns(ok[0, ], g), "no baskets")
  expect_error(jb_issue_returns(rbind(ok, ok[1, ]), g), "duplicated issue/basket")
  expect_error(jb_issue_returns(ok, g[g$basket == 1L, ]), "no payout")
  expect_error(jb_issue_returns(ok, g, unit_cny = 5), "unit_cny must be 2")
})

# --- bootstrap and summary -------------------------------------------------

test_that("jb_bootstrap_roi is deterministic for a seed and restores the RNG", {
  r <- tibble::tibble(issue = paste0("i", 1:40), stake = rep(100, 40),
                      net = rep(c(50, -30), 20))
  set.seed(123); before <- .Random.seed
  a <- jb_bootstrap_roi(r, n_boot = 200L, seed = 7L)
  expect_identical(.Random.seed, before)
  b <- jb_bootstrap_roi(r, n_boot = 200L, seed = 7L)
  expect_identical(a, b)
  expect_length(a, 3L)
  expect_true(a[1] <= a[2] && a[2] <= a[3])
  cc <- jb_bootstrap_roi(r, n_boot = 200L, seed = 8L)
  expect_false(identical(a, cc))
  expect_error(jb_bootstrap_roi(r[0, ]), "no returns")
})

test_that("jb_return_summary pools stake and reports every cohort", {
  r <- tibble::tibble(issue = c("a", "b", "c"), cohort = c("ORIGINAL", "ORIGINAL", "ADDITIONAL"),
                      baskets = 1L, tickets = c(4L, 2L, 10L),
                      stake = c(8, 4, 20), hits = c(1L, 0L, 1L),
                      gross = c(100, 0, 0), net = c(92, -4, -20), roi = c(11.5, -1, -1))
  s <- jb_return_summary(r, n_boot = 50L, seed = 3L)
  expect_equal(s$scope, c("ALL", "ORIGINAL", "ADDITIONAL"))
  expect_equal(s$issues, c(3L, 2L, 1L))
  expect_equal(s$roi[1], sum(r$net) / sum(r$stake))
  expect_equal(s$stake[2], 12)
  expect_equal(s$hit_rate[2], 0.5)
})

test_that("jb_return_summary tolerates an empty cohort", {
  r <- tibble::tibble(issue = "a", cohort = "ORIGINAL", baskets = 1L, tickets = 4L,
                      stake = 8, hits = 0L, gross = 0, net = -8, roi = -1)
  s <- jb_return_summary(r, n_boot = 20L, seed = 1L)
  expect_equal(s$issues, c(1L, 1L, 0L))
  expect_true(is.na(s$roi[3]))
})

# --- jb_equity_curve / jb_drawdown -----------------------------------------

test_that("jb_equity_curve floors the peak at zero and tracks underwater", {
  r <- tibble::tibble(issue = as.character(1:6), stake = rep(10, 6),
                      net = c(100, -50, -100, 200, -300, 50))
  c6 <- jb_equity_curve(r)
  expect_equal(c6$equity, c(100, 50, -50, 150, -150, -100))
  expect_equal(c6$peak, c(100, 100, 100, 150, 150, 150))
  expect_equal(c6$underwater, c(0, -50, -150, 0, -300, -250))
  down <- tibble::tibble(issue = as.character(1:3), stake = rep(10, 3), net = rep(-10, 3))
  expect_equal(jb_equity_curve(down)$peak, rep(0, 3))
})

test_that("jb_drawdown identifies the peak, trough and underwater run", {
  r <- tibble::tibble(issue = as.character(1:6), stake = rep(10, 6),
                      net = c(100, -50, -100, 200, -300, 50))
  d <- jb_drawdown(r)
  expect_equal(d$issues, 6L)
  expect_equal(d$net, -100)
  expect_equal(d$roi, -100 / 60)
  expect_equal(d$peak_cny, 150)          # reached at issue 4
  expect_equal(d$peak_issue, "4")
  expect_equal(d$trough_cny, -150)       # deepest at issue 5
  expect_equal(d$trough_issue, "5")
  expect_equal(d$max_drawdown_cny, -300)
  expect_equal(d$peak_to_trough_issues, 1L)
  expect_equal(d$longest_underwater_run, 2L)
  expect_equal(d$terminal_cny, -100)
  expect_equal(d$gap_to_peak_cny, -250)
  expect_equal(d$max_drawdown_share_of_deployed, -300 / 50)
  expect_equal(d$issues_underwater_share, 4 / 6)
})

test_that("jb_drawdown handles monotone series and the pre-betting peak", {
  up <- tibble::tibble(issue = as.character(1:5), stake = rep(10, 5), net = rep(10, 5))
  d <- jb_drawdown(up)
  expect_equal(d$max_drawdown_cny, 0)
  expect_equal(d$longest_underwater_run, 0L)
  expect_equal(d$gap_to_peak_cny, 0)
  expect_equal(d$peak_issue, "5")
  down <- tibble::tibble(issue = as.character(1:5), stake = rep(10, 5), net = rep(-10, 5))
  e <- jb_drawdown(down)
  expect_equal(e$max_drawdown_cny, -50)
  expect_equal(e$peak_cny, 0)                    # never rose: peak is "before betting"
  expect_true(is.na(e$peak_issue))
  expect_equal(e$peak_to_trough_issues, 5L)      # measured from the start
  expect_equal(e$terminal_cny, -50)
  expect_equal(e$longest_underwater_run, 5L)
  expect_equal(e$issues_underwater_share, 1)
})

test_that("jb_drawdown orders by issue and uses calendar days when given", {
  r <- tibble::tibble(issue = c("3", "1", "2"), stake = rep(10, 3), net = c(-30, 100, -50))
  d <- jb_drawdown(r)
  expect_equal(d$net, 20)
  expect_equal(d$peak_issue, "1")
  expect_equal(d$trough_issue, "3")
  rd <- tibble::tibble(issue = c("100708", "100709", "100710"), stake = rep(256, 3),
                       net = c(500, -1000, -200),
                       date = as.Date(c("2010-07-08", "2010-07-09", "2010-07-10")))
  dd <- jb_drawdown(rd)
  expect_equal(dd$peak_to_trough_days, 2L)       # 07-08 peak -> 07-10 trough
  expect_equal(dd$peak_to_trough_issues, 2L)
  expect_true(is.na(jb_drawdown(dplyr::select(rd, -date))$peak_to_trough_days))
})

test_that("jb_equity_curve and jb_drawdown fail closed on malformed input", {
  r <- tibble::tibble(issue = as.character(1:3), stake = rep(10, 3), net = c(1, -2, 3))
  for (f in list(jb_equity_curve, jb_drawdown)) {
    expect_error(f(r[0, ]), "no returns")
    expect_error(f(dplyr::select(r, -net)), "must include issue, net, stake")
    expect_error(f(rbind(r, r[1, ])), "one row per issue")
    bad <- r; bad$net[1] <- NA_real_
    expect_error(f(bad), "must be complete")
    bad2 <- r; bad2$stake[1] <- 0
    expect_error(f(bad2), "stake must be positive")
    bad3 <- r; bad3$net[1] <- Inf
    expect_error(f(bad3), "must be finite")
    bad4 <- r; bad4$date <- as.Date(c("2010-01-01", NA, "2010-01-03"))
    expect_error(f(bad4), "date must be complete")
  }
})
