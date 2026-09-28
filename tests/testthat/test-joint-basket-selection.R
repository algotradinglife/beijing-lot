# Tests for the selection walk-forward module.

source(testthat::test_path('../../r/joint_basket_allocation.R'))
source(testthat::test_path('../../r/joint_basket_walk_forward.R'))
source(testthat::test_path('../../r/joint_basket_selection.R'))

# Two issues, three baskets each. mass orders baskets within an issue.
fixture <- function() {
  tibble::tibble(
    issue = c(rep('1001', 3), rep('1002', 3)),
    group = rep(1:3, 2),
    mass  = c(0.5, 0.3, 0.2, 0.4, 0.35, 0.25),
    tickets0  = c(10, 5, 1, 10, 5, 1),
    unit_gross = c(2, 5, 20, 3, 4, 10),
    hit   = c(TRUE, FALSE, TRUE, FALSE, TRUE, FALSE)
  )
}

test_that('jb_select_top_k keeps the highest-mass baskets per issue', {
  s <- jb_select_top_k(fixture(), 1, 'mass')
  expect_equal(nrow(s), 2)
  expect_setequal(s$group, c(1L, 1L))
  s2 <- jb_select_top_k(fixture(), 2, 'mass')
  expect_equal(nrow(s2), 4)
  expect_setequal(s2$group, c(1L, 2L, 1L, 2L))
})

test_that('jb_select_top_k clamps k above the per-issue basket count', {
  s <- jb_select_top_k(fixture(), 99, 'mass')
  expect_equal(nrow(s), 6)
})

test_that('jb_select_top_k accepts Inf as play-every-basket', {
  s <- jb_select_top_k(fixture(), Inf, 'mass')
  expect_equal(nrow(s), 6)
})

test_that('jb_select_top_k rejects invalid arguments', {
  expect_error(jb_select_top_k(fixture(), 0, 'mass'), 'k must be >= 1')
  expect_error(jb_select_top_k(fixture(), NA_real_, 'mass'), 'k must be >= 1')
  expect_error(jb_select_top_k(fixture(), 1, 'nope'), 'missing columns')
  bad <- fixture(); bad$mass[1] <- NA
  expect_error(jb_select_top_k(bad, 1, 'mass'), 'non-missing')
})

test_that('jb_select_return drops stake and payout of unselected baskets', {
  # k=1 keeps group 1 of each issue. Only issue 1001 hits (1002 g1 does not),
  # so the payout is 1001 alone while the stake covers both selected baskets.
  r <- jb_select_return(fixture(), 1, 'mass', 2)
  stake  <- (10 + 10) * 2
  payout <- 10 * 2 * 2
  expect_equal(r, payout/stake - 1)
})

test_that('dropping a basket removes both its stake and its payout', {
  d <- fixture()
  # k=2 keeps groups 1 and 2 of each issue; issue 1002 group 2 hits.
  r <- jb_select_return(d, 2, 'mass', 2)
  sel <- jb_select_top_k(d, 2, 'mass')
  stake  <- sum(sel$tickets0) * 2
  payout <- sum(ifelse(sel$hit, sel$tickets0 * 2 * sel$unit_gross, 0))
  expect_equal(r, payout/stake - 1)
  # the k=3 portfolio must include everything k=2 did
  expect_true(all(jb_select_top_k(d, 2, 'mass')$group %in% jb_select_top_k(d, 3, 'mass')$group))
})

test_that('jb_select_return with a huge k equals the full portfolio', {
  d <- fixture()
  full <- jb_alloc_realised(d$tickets0, d$unit_gross, d$hit, 2)
  expect_equal(jb_select_return(d, Inf, 'mass', 2), full)
})

test_that('jb_select_return validates its columns', {
  bad <- fixture(); bad$unit_gross <- NULL
  expect_error(jb_select_return(bad, 1, 'mass'), 'missing columns')
})

test_that('jb_walk_forward_select scores folds strictly out of sample', {
  d <- fixture()
  wf <- jb_walk_forward_select(d, c(1, 2), 'mass', n_folds = 2L, unit_cny = 2)
  expect_equal(nrow(wf), 1)
  expect_equal(wf$n_past_issues, 1)
  expect_equal(wf$n_oos_issues, 1)
  expect_true(wf$k %in% c(1, 2))
})

test_that('jb_walk_forward_select pools stake and payout across folds', {
  d <- fixture()
  wf <- jb_walk_forward_select(d, c(1), 'mass', n_folds = 2L, unit_cny = 2)
  # only k=1 is offered, so the chosen rule is deterministic
  expect_equal(wf$k, 1)
  expect_true(is.finite(attr(wf, 'pooled_return')))
  expect_true(is.finite(attr(wf, 'pooled_baseline')))
})

test_that('jb_walk_forward_select rejects a single fold', {
  expect_error(jb_walk_forward_select(fixture(), c(1), 'mass', n_folds = 1L), 'n_folds must be >= 2')
})

test_that('ranking never reads settlement', {
  # Flipping hit must not change WHICH baskets are selected or their order:
  # selection depends on mass alone.
  d <- fixture()
  flipped <- d; flipped$hit <- !flipped$hit
  a <- jb_select_top_k(d, 1, 'mass')
  b <- jb_select_top_k(flipped, 1, 'mass')
  expect_equal(a$issue, b$issue)
  expect_equal(a$group, b$group)
  expect_equal(a$mass, b$mass)
})

test_that('the walk-forward uses PAST outcomes to choose k, never the fold', {
  # Choosing k legitimately consumes the past window's realised returns. What
  # must hold is that the fold's own settlement cannot influence the choice:
  # flipping only the FINAL fold's outcomes must leave the chosen k unchanged.
  d <- fixture()
  fl <- d; fl$hit[fl$issue == '1002'] <- !fl$hit[fl$issue == '1002']
  w1 <- jb_walk_forward_select(d,  c(1, 2), 'mass', n_folds = 2L, unit_cny = 2)
  w2 <- jb_walk_forward_select(fl, c(1, 2), 'mass', n_folds = 2L, unit_cny = 2)
  expect_equal(w1$k, w2$k)
  # but the reported out-of-sample return DOES move, because the fold settled
  # differently - which is exactly the point of scoring the fold.
  expect_false(isTRUE(all.equal(w1$oos_return, w2$oos_return)))
})
