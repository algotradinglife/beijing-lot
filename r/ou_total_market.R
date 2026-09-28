#' 大小球（总进球）盘口 -> 期望总进球
#'
#' 数据来自 `src/nowscore_danchang_odds.py` 抓取的 nowscore 北单挂盘页市场，
#' 公司为澳M（companyid 1）与皇G（companyid 3）。赔率是香港盘（净赔率）。
#'
#' 术语
#' ----
#' * `line`：盘口，如 2.5、3、2.75。整数盘有走盘（push，退还本金），
#'   半球盘没有，四分之一盘是相邻两个盘口各半注。
#' * 本模块只做「盘口 -> 期望总进球」的反解，不做让球线映射（那是
#'   `r/joint_basket_dc_fit.R` 的职责）。
#'
#' 模型假设：总进球数 T ~ Poisson(lambda)。这是大小球盘口的通行反解方式，
#' 只需要一个自由度，因此用单一盘口即可反解；多公司多盘口时取各公司
#' 反解值的均值，并用离散度做一致性检查。

#' 香港盘净赔率 -> 去水后的隐含概率
#'
#' @param over_hk,under_hk 香港盘净赔率（> 0）。
#' @return 长度 2 的数值向量 `c(over = , under = )`，和为 1。
#' @export
ou_devig <- function(over_hk, under_hk) {
  if (!is.numeric(over_hk) || !is.numeric(under_hk)) stop("赔率必须是数值")
  if (any(over_hk <= 0) || any(under_hk <= 0)) stop("香港赔率必须为正")
  over <- 1 / (1 + over_hk)
  under <- 1 / (1 + under_hk)
  total <- over + under
  c(over = over / total, under = under / total)
}

#' Poisson 总进球在给定盘口下的「大」概率
#'
#' 整数盘按走盘退还本金处理，即 code{P(T > n) / (1 - P(T = n))}；
#' 半球盘为 code{P(T > n)}；四分之一盘取相邻两盘口各半。
#'
#' @param lambda 期望总进球（> 0）。
#' @param line 盘口，必须是 0.25 的整数倍。
#' @return 标量概率，取值 (0, 1)。
#' @export
ou_p_over <- function(lambda, line) {
  if (!is.numeric(lambda) || length(lambda) != 1L || !is.finite(lambda) || lambda <= 0) {
    stop("lambda 必须是单个正数")
  }
  if (!is.numeric(line) || length(line) != 1L || !is.finite(line)) stop("line 必须是单个数值")
  if (abs(line * 4 - round(line * 4)) > 1e-9) stop("line 必须是 0.25 的整数倍")
  if (line < 0) stop("line 不能为负")

  p_gt <- function(x) stats::ppois(x, lambda, lower.tail = FALSE)
  p_eq <- function(x) stats::dpois(x, lambda)
  # 整数盘：走盘退还本金
  p_int <- function(n) {
    push <- p_eq(n)
    if (push >= 1) return(0.5)
    p_gt(n) / (1 - push)
  }

  n <- floor(line + 1e-9)
  frac <- line - n
  if (frac < 1e-9) return(p_int(n))
  if (abs(frac - 0.5) < 1e-9) return(p_gt(n))
  if (abs(frac - 0.25) < 1e-9) return(0.5 * p_int(n) + 0.5 * p_gt(n))
  0.5 * p_gt(n) + 0.5 * p_int(n + 1L)
}

#' 由单一大小球盘口反解期望总进球
#'
#' @param over_hk,under_hk 香港盘净赔率。
#' @param line 盘口。
#' @param range 搜索区间，长度 2、正、递增。
#' @return 标量 lambda；区间端点未变号时抛出错误。
#' @export
ou_implied_total <- function(over_hk, under_hk, line, range = c(0.05, 15)) {
  if (length(range) != 2L || any(range <= 0) || range[1] >= range[2]) {
    stop("range 必须是两个正数且递增")
  }
  p <- ou_devig(over_hk, under_hk)[["over"]]
  f <- function(lambda) ou_p_over(lambda, line) - p
  lo <- f(range[1]); hi <- f(range[2])
  if (is.na(lo) || is.na(hi)) stop("目标函数在区间端点取到 NA")
  if (lo * hi > 0) stop(sprintf("区间 [%.3f, %.3f] 未变号 (f=%+.5f, %+.5f)", range[1], range[2], lo, hi))
  stats::uniroot(f, range, tol = 1e-8)$root
}

#' 多公司/多盘口的一致性汇总
#'
#' @param over_hk,under_hk,line 等长数值向量（同一场比赛的若干条大小球报价）。
#' @return 具名列表：code{total} 各条反解值的均值，code{n} 条数，
#'   code{spread} 极差，code{values} 各条反解值。
#' @export
ou_consensus_total <- function(over_hk, under_hk, line, range = c(0.05, 15)) {
  n <- length(over_hk)
  if (n == 0L) stop("至少需要一条报价")
  if (length(under_hk) != n || length(line) != n) stop("三个向量的长度必须一致")
  values <- vapply(seq_len(n), function(i) {
    tryCatch(ou_implied_total(over_hk[i], under_hk[i], line[i], range),
             error = function(e) NA_real_)
  }, numeric(1))
  ok <- is.finite(values)
  if (!any(ok)) stop("没有任何一条报价可反解")
  list(total = mean(values[ok]), n = sum(ok), spread = diff(range(values[ok])),
       values = values[ok])
}
