test_that("ou_devig 归一化香港盘赔率", {
  p <- ou_devig(0.90, 0.82)
  expect_equal(sum(p), 1)
  expect_lt(p[["over"]], p[["under"]])          # 大赔更高 -> 大更不可能
  # 1/1.90 = 0.526316, 1/1.82 = 0.549451, 和 1.075767
  expect_equal(unname(p[["over"]]), 0.526316 / 1.075767, tolerance = 1e-6)
  expect_equal(unname(p[["under"]]), 0.549451 / 1.075767, tolerance = 1e-6)
  expect_error(ou_devig(0, 0.9), "必须为正")
  expect_error(ou_devig("a", 0.9), "必须是数值")
})

test_that("ou_p_over 在三种盘口上都随 lambda 单调递增", {
  grid <- seq(0.5, 6, by = 0.25)
  for (ln in c(2, 2.5, 2.75, 3, 3.25, 3.5)) {
    v <- vapply(grid, function(l) ou_p_over(l, ln), numeric(1))
    expect_true(all(diff(v) > 0), info = sprintf("line=%s", ln))
    expect_true(all(v > 0 & v < 1), info = sprintf("line=%s", ln))
  }
})

test_that("整数盘的走盘修正把概率推向 1（相对忽略走盘）", {
  lambda <- 2.5
  raw_gt <- stats::ppois(3, lambda, lower.tail = FALSE)
  expect_gt(ou_p_over(lambda, 3), raw_gt)
  expect_equal(ou_p_over(lambda, 3), raw_gt / (1 - stats::dpois(3, lambda)))
})

test_that("半球盘等于未修正的 P(T > n)", {
  expect_equal(ou_p_over(2.7, 2.5), stats::ppois(2, 2.7, lower.tail = FALSE))
  expect_equal(ou_p_over(2.7, 3.5), stats::ppois(3, 2.7, lower.tail = FALSE))
})

test_that("四分之一盘是相邻两盘口的平均", {
  expect_equal(ou_p_over(2.6, 2.75),
               0.5 * ou_p_over(2.6, 2.5) + 0.5 * ou_p_over(2.6, 3))
  expect_equal(ou_p_over(2.6, 3.25),
               0.5 * ou_p_over(2.6, 3) + 0.5 * ou_p_over(2.6, 3.5))
})

test_that("ou_p_over 拒绝非法输入", {
  expect_error(ou_p_over(0, 2.5), "正数")
  expect_error(ou_p_over(c(1, 2), 2.5), "单个正数")
  expect_error(ou_p_over(2.5, 2.6), "0.25 的整数倍")
  expect_error(ou_p_over(2.5, -1), "不能为负")
})

test_that("ou_implied_total 与 ou_p_over 互为逆运算", {
  for (ln in c(2, 2.5, 2.75, 3.5)) {
    for (lam in c(1.2, 2.8, 4.5)) {
      p <- ou_p_over(lam, ln)
      over_hk <- 1 / p - 1
      under_hk <- 1 / (1 - p) - 1
      expect_equal(ou_implied_total(over_hk, under_hk, ln), lam, tolerance = 1e-6)
    }
  }
})

test_that("ou_implied_total 在区间未变号时报错", {
  expect_error(ou_implied_total(0.9, 0.9, 3, range = c(0.05, 0.1)), "未变号")
  expect_error(ou_implied_total(0.9, 0.9, 3, range = c(15, 0.05)), "递增")
})

test_that("ou_implied_total 的已知解", {
  # 公平 2.5 球盘（港赔相等）在 lambda 满足 P(T>2)=0.5
  lam <- ou_implied_total(0.9, 0.9, 2.5)
  expect_equal(stats::ppois(2, lam, lower.tail = FALSE), 0.5, tolerance = 1e-8)
  expect_gt(lam, 2.5)
})

test_that("ou_consensus_total 汇总多公司并给出离散度", {
  r <- ou_consensus_total(c(0.90, 0.98, 0.84), c(0.82, 0.89, 0.96), c(3, 3, 2.75))
  expect_equal(r$n, 3L)
  expect_true(r$total > 0 && r$total < 10)
  expect_gte(r$spread, 0)
  expect_length(r$values, 3L)
  expect_error(ou_consensus_total(numeric(0), numeric(0), numeric(0)), "至少需要一条")
  expect_error(ou_consensus_total(c(0.9, 0.9), c(0.8), c(3, 3)), "长度必须一致")
})

test_that("ou_consensus_total 跳过不可解的报价", {
  r <- ou_consensus_total(c(0.90, 0.90), c(0.82, 0.82), c(3, 3))
  expect_equal(r$n, 2L)
})
