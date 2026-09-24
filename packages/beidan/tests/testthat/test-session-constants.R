(function() {
# 会话常量读写契约：n7_pipeline_constants(...)
#
# 覆盖范围（逐条对应任务契约）：
#   · 零参调用 = 读取当前会话快照
#   · 命名局部更新 = 返回完整列表快照
#   · reset=TRUE 恢复默认；reset 与更新同时给出 -> 拒绝
#   · 默认值恰如合同冻结值
#   · 未知 / 未命名 / 重复字段，NULL/NA/NaN/Inf，非标量 / 类型错误，非逻辑 reset
#   · 完整候选先校验后更新内存 -> 每次失败都是原子的（状态不变）
#   · 取值约束：n_legs 固定 7（数值 7 归一化）、budget>=0、unit>0、factor(0,1]、
#     rho[-0.5,0.5]、SP 值 >0 且 replacement<=threshold
#   · 无文件 / options / 全局环境写入；新进程从默认值开始
#   · 快照互相独立
#   · 下游不因会话常量变更而改变行为（显式参数仍然说了算）

n7_pipeline_constants(reset = TRUE)
on.exit(n7_pipeline_constants(reset = TRUE), add = TRUE)

CONSTANT_NAMES <- c('n_legs', 'issue_budget_cny', 'unit_cny', 'payout_factor',
                    'rho', 'sp_threshold', 'sp_replacement')

# --- 读取 / 默认值 ----------------------------------------------------------

testthat::test_that('零参调用读取当前会话快照，且键集合与默认值恰如合同', {
  n7_pipeline_constants(reset = TRUE)
  constants <- n7_pipeline_constants()
  testthat::expect_type(constants, 'list')
  testthat::expect_identical(names(constants), CONSTANT_NAMES)
  testthat::expect_identical(constants$n_legs, 7L)
  testthat::expect_identical(constants$issue_budget_cny, 1024)
  testthat::expect_identical(constants$unit_cny, 2)
  testthat::expect_identical(constants$payout_factor, 0.65)
  testthat::expect_identical(constants$rho, -0.14)
  testthat::expect_identical(constants$sp_threshold, 10)
  testthat::expect_identical(constants$sp_replacement, 4.5)
})

testthat::test_that('零参调用的返回是当前会话值，而不总是默认值', {
  n7_pipeline_constants(rho = -0.22)
  testthat::expect_identical(n7_pipeline_constants()$rho, -0.22)
})

# --- 局部更新：返回完整快照 --------------------------------------------------

testthat::test_that('命名局部更新返回完整列表快照，且未提及的字段保持不变', {
  n7_pipeline_constants(reset = TRUE)
  updated <- n7_pipeline_constants(rho = -0.18, issue_budget_cny = 512)
  # 返回的必须是完整快照，而不是只含被更新字段的补丁。
  testthat::expect_identical(names(updated), CONSTANT_NAMES)
  testthat::expect_length(updated, 7L)
  testthat::expect_identical(updated$rho, -0.18)
  testthat::expect_identical(updated$issue_budget_cny, 512)
  testthat::expect_identical(updated$unit_cny, 2)
  testthat::expect_identical(updated$payout_factor, 0.65)
  testthat::expect_identical(updated$sp_threshold, 10)
  testthat::expect_identical(updated$sp_replacement, 4.5)
  # 更新内存后的会话状态与返回值一致。
  testthat::expect_identical(n7_pipeline_constants(), updated)
})

testthat::test_that('更新可以叠加，后续更新基于当前会话值', {
  n7_pipeline_constants(rho = -0.2)
  second <- n7_pipeline_constants(unit_cny = 5)
  testthat::expect_identical(second$rho, -0.2)
  testthat::expect_identical(second$unit_cny, 5)
})

testthat::test_that('n_legs 接受数值 7 并归一化为 integer 7L', {
  updated <- n7_pipeline_constants(n_legs = 7)
  testthat::expect_identical(updated$n_legs, 7L)
  testthat::expect_type(updated$n_legs, 'integer')
})

# --- reset ------------------------------------------------------------------

testthat::test_that('reset = TRUE 恢复冻结默认值', {
  n7_pipeline_constants(reset = TRUE)
  n7_pipeline_constants(rho = -0.4, unit_cny = 9, sp_threshold = 20,
                        sp_replacement = 3)
  restored <- n7_pipeline_constants(reset = TRUE)
  testthat::expect_identical(restored, n7_pipeline_constants())
  testthat::expect_identical(restored$rho, -0.14)
  testthat::expect_identical(restored$unit_cny, 2)
  testthat::expect_identical(restored$sp_threshold, 10)
  testthat::expect_identical(restored$sp_replacement, 4.5)
  testthat::expect_identical(restored$n_legs, 7L)
})

testthat::test_that('reset = TRUE 与更新同时给出必须被拒绝', {
  n7_pipeline_constants(rho = -0.2)
  before <- n7_pipeline_constants()
  testthat::expect_error(n7_pipeline_constants(reset = TRUE, rho = -0.1),
                         'cannot be combined with updates')
  # 被拒绝的调用不得改动状态。
  testthat::expect_identical(n7_pipeline_constants(), before)
})

testthat::test_that('reset 必须是非 NA 的逻辑标量', {
  testthat::expect_error(n7_pipeline_constants(reset = NA), 'reset')
  testthat::expect_error(n7_pipeline_constants(reset = 'yes'), 'reset')
  testthat::expect_error(n7_pipeline_constants(reset = 1), 'reset')
  testthat::expect_error(n7_pipeline_constants(reset = c(TRUE, FALSE)), 'reset')
  testthat::expect_error(n7_pipeline_constants(reset = NULL), 'reset')
})

# --- 字段名结构：未知 / 未命名 / 重复 / NULL --------------------------------

testthat::test_that('未知字段名被拒绝', {
  testthat::expect_error(n7_pipeline_constants(bogus = 1), 'bogus|subset')
  testthat::expect_error(n7_pipeline_constants(N7_LEGS = 7), 'N7_LEGS|subset')
})

testthat::test_that('未命名字段被拒绝', {
  testthat::expect_error(n7_pipeline_constants(5), 'named')
  testthat::expect_error(n7_pipeline_constants(rho = -0.2, 5), 'named')
})

testthat::test_that('重复字段名被拒绝，且不会静默保留最后一个', {
  before <- n7_pipeline_constants()
  testthat::expect_error(n7_pipeline_constants(rho = -0.18, rho = -0.2), 'duplicate')
  testthat::expect_error(
    n7_pipeline_constants(unit_cny = 3, unit_cny = 4, rho = -0.1), 'duplicate')
  testthat::expect_identical(n7_pipeline_constants(), before)
})

testthat::test_that('NULL 字段被拒绝', {
  testthat::expect_error(n7_pipeline_constants(rho = NULL), 'rho|sp_threshold')
  testthat::expect_error(n7_pipeline_constants(sp_threshold = NULL), 'rho|sp_threshold')
})

# --- 取值类型：NA / NaN / Inf / 非标量 / 错误类型 ---------------------------

testthat::test_that('每个常量都拒绝 NA / NaN / Inf', {
  for (field in CONSTANT_NAMES) {
    bad <- list(NA_real_, NaN, Inf, -Inf)
    for (value in bad) {
      args <- stats::setNames(list(value), field)
      testthat::expect_error(do.call(n7_pipeline_constants, args), NULL,
                             info = paste(field, '=', value))
    }
  }
})

testthat::test_that('每个常量都拒绝非标量', {
  for (field in CONSTANT_NAMES) {
    args <- stats::setNames(list(c(1, 2)), field)
    testthat::expect_error(do.call(n7_pipeline_constants, args), NULL,
                           info = paste(field, 'non-scalar'))
  }
})

testthat::test_that('每个常量都拒绝错误类型', {
  for (field in CONSTANT_NAMES) {
    for (value in list('x', TRUE, list(1), factor('a'), as.Date('2026-01-01'), matrix(7), structure(7, class = 'custom'))) {
      args <- stats::setNames(list(value), field)
      testthat::expect_error(do.call(n7_pipeline_constants, args), NULL,
                             info = paste(field, 'wrong type'))
    }
  }
})

# --- 取值约束 ---------------------------------------------------------------

testthat::test_that('n_legs 固定为 7，其它整数一律拒绝', {
  for (bad in list(6, 8, 0, -7, 7.5, 3)) {
    testthat::expect_error(n7_pipeline_constants(n_legs = bad), 'n_legs',
                           info = paste('n_legs =', bad))
  }
})

testthat::test_that('issue_budget_cny 允许 0，拒绝负值', {
  testthat::expect_identical(n7_pipeline_constants(issue_budget_cny = 0)$issue_budget_cny, 0)
  testthat::expect_error(n7_pipeline_constants(issue_budget_cny = -1), 'issue_budget_cny')
  testthat::expect_error(n7_pipeline_constants(issue_budget_cny = -0.01), 'issue_budget_cny')
})

testthat::test_that('unit_cny 必须严格为正', {
  testthat::expect_identical(n7_pipeline_constants(unit_cny = 0.5)$unit_cny, 0.5)
  testthat::expect_error(n7_pipeline_constants(unit_cny = 0), 'unit_cny must be positive')
  testthat::expect_error(n7_pipeline_constants(unit_cny = -2), 'unit_cny')
})

testthat::test_that('payout_factor 落在 (0, 1]：1 允许，0 与 >1 拒绝', {
  testthat::expect_identical(n7_pipeline_constants(payout_factor = 1)$payout_factor, 1)
  testthat::expect_identical(n7_pipeline_constants(payout_factor = 0.5)$payout_factor, 0.5)
  testthat::expect_error(n7_pipeline_constants(payout_factor = 0), 'payout_factor')
  testthat::expect_error(n7_pipeline_constants(payout_factor = 1.01), 'payout_factor')
  testthat::expect_error(n7_pipeline_constants(payout_factor = -0.5), 'payout_factor')
})

testthat::test_that('rho 遵循模型范围 [-0.5, 0.5]', {
  testthat::expect_identical(n7_pipeline_constants(rho = 0)$rho, 0)
  testthat::expect_identical(n7_pipeline_constants(rho = -0.5)$rho, -0.5)
  testthat::expect_identical(n7_pipeline_constants(rho = 0.5)$rho, 0.5)
  testthat::expect_error(n7_pipeline_constants(rho = -0.51), 'rho')
  testthat::expect_error(n7_pipeline_constants(rho = 0.51), 'rho')
  testthat::expect_error(n7_pipeline_constants(rho = -1.5), 'rho')
  testthat::expect_error(n7_pipeline_constants(rho = 2), 'rho')
})

testthat::test_that('SP 值必须为正，且 replacement 不得超过 threshold', {
  testthat::expect_identical(n7_pipeline_constants(sp_threshold = 12)$sp_threshold, 12)
  testthat::expect_identical(n7_pipeline_constants(sp_replacement = 3)$sp_replacement, 3)
  # 边界：replacement == threshold 允许。
  both <- n7_pipeline_constants(sp_threshold = 8, sp_replacement = 8)
  testthat::expect_identical(both$sp_threshold, 8)
  testthat::expect_identical(both$sp_replacement, 8)
  testthat::expect_error(n7_pipeline_constants(sp_threshold = 1, sp_replacement = 0.5), 'sp_threshold')
  testthat::expect_error(n7_pipeline_constants(sp_threshold = 0), 'sp_threshold')
  testthat::expect_error(n7_pipeline_constants(sp_threshold = -1), 'sp_threshold')
  testthat::expect_error(n7_pipeline_constants(sp_replacement = 0), 'sp_replacement')
  testthat::expect_error(n7_pipeline_constants(sp_replacement = -4.5), 'sp_replacement')
  # 单独抬高 replacement 越过当前 threshold 也必须失败：校验的是完整候选快照。
  testthat::expect_error(n7_pipeline_constants(sp_replacement = 11), 'must not exceed')
})

# --- 原子性 ----------------------------------------------------------------

testthat::test_that('每次失败都是原子的：状态与调用前完全相同', {
  n7_pipeline_constants(rho = -0.2, unit_cny = 3)
  before <- n7_pipeline_constants()
  failing <- list(
    quote(n7_pipeline_constants(rho = -0.12, unit_cny = 0)),
    quote(n7_pipeline_constants(issue_budget_cny = 999, n_legs = 8)),
    quote(n7_pipeline_constants(sp_threshold = 20, sp_replacement = 30)),
    quote(n7_pipeline_constants(rho = Inf, payout_factor = 0.9)),
    quote(n7_pipeline_constants(bogus = 1)),
    quote(n7_pipeline_constants(rho = -0.1, rho = -0.3)),
    quote(n7_pipeline_constants(NA)),
    quote(n7_pipeline_constants(reset = TRUE, rho = -0.1))
  )
  for (expr in failing) {
    testthat::expect_error(eval(expr))
    testthat::expect_identical(n7_pipeline_constants(), before,
                               info = deparse(expr))
  }
})

testthat::test_that('成功更新前不会留下部分写入的中间态', {
  n7_pipeline_constants(rho = -0.2)
  before <- n7_pipeline_constants()
  # 第二个字段非法：第一个字段绝不能已经被写进去。
  testthat::expect_error(n7_pipeline_constants(issue_budget_cny = 777, rho = 5))
  after <- n7_pipeline_constants()
  testthat::expect_identical(after$issue_budget_cny, before$issue_budget_cny)
  testthat::expect_identical(after$rho, before$rho)
  testthat::expect_identical(after, before)
})

# --- 快照独立 ---------------------------------------------------------------

testthat::test_that('返回的快照互相独立，修改返回值不影响会话状态', {
  n7_pipeline_constants(reset = TRUE)
  first <- n7_pipeline_constants()
  first$rho <- 99
  first$n_legs <- 3L
  second <- n7_pipeline_constants()
  testthat::expect_identical(second$rho, -0.14)
  testthat::expect_identical(second$n_legs, 7L)
  # 两个快照本身也不共享存储。
  third <- n7_pipeline_constants()
  third$unit_cny <- 123
  testthat::expect_false(identical(third, second))
  testthat::expect_identical(n7_pipeline_constants()$unit_cny, 2)
})

testthat::test_that('reset 返回的是新建的默认列表，而不是共享同一对象', {
  a <- n7_pipeline_constants(reset = TRUE)
  a$rho <- 88
  b <- n7_pipeline_constants(reset = TRUE)
  testthat::expect_identical(b$rho, -0.14)
})

# --- 无文件 / options / 全局环境副作用 --------------------------------------

testthat::test_that('读写会话常量不写文件、不碰 options、不写全局环境', {
  before_options <- options()
  before_globals <- ls(envir = globalenv())
  before_files <- list.files(tempdir(), all.files = TRUE)

  n7_pipeline_constants(rho = -0.2, unit_cny = 4)
  n7_pipeline_constants()
  n7_pipeline_constants(reset = TRUE)

  testthat::expect_identical(options(), before_options)
  testthat::expect_setequal(ls(envir = globalenv()), before_globals)
  testthat::expect_setequal(list.files(tempdir(), all.files = TRUE), before_files)
  # 全局环境里不得出现常量对象名。
  testthat::expect_false(exists('.n7_session_constants', envir = globalenv(),
                                inherits = FALSE))
})

# --- 新进程从默认值开始 -----------------------------------------------------

testthat::test_that('新 R 进程从冻结默认值开始（callr 可用时）', {
  testthat::skip_if_not_installed('callr')
  # test_file() 会把工作目录切到测试文件所在目录，所以不能用相对路径 'packages/beidan'。
  # pkgload::pkg_path() 在 load_all 下返回源码目录，且与工作目录无关。
  pkg_path <- pkgload::pkg_path()
  testthat::expect_true(dir.exists(pkg_path))
  lib_paths <- .libPaths()
  r_libs <- Sys.getenv('R_LIBS')
  # 当前进程改成非默认值，然后在新进程里只做零参读取。
  n7_pipeline_constants(rho = -0.31, issue_budget_cny = 77)
  result <- callr::r(
    function(pkg, r_libs, lib_paths) {
      if (nzchar(r_libs)) .libPaths(c(r_libs, lib_paths)) else .libPaths(lib_paths)
      pkgload::load_all(pkg, quiet = TRUE)
      n7_pipeline_constants()
    },
    args = list(pkg = pkg_path, r_libs = r_libs, lib_paths = lib_paths)
  )
  testthat::expect_identical(result$rho, -0.14)
  testthat::expect_identical(result$issue_budget_cny, 1024)
  testthat::expect_identical(result$n_legs, 7L)
  # 本进程的值不受子进程影响。
  testthat::expect_identical(n7_pipeline_constants()$rho, -0.31)
})

# --- 下游不变性 -------------------------------------------------------------

testthat::test_that('下游计算仍以显式传入的常量为准，不受会话状态影响', {
  n7_pipeline_constants(reset = TRUE)
  # 一笔票的估值必须只取决于 n7_value_tickets 收到的显式参数。
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'),
                 issue_id = '26097')
  tickets <- tibble::tibble(
    ticket_id = 'T1', group_id = 'G1',
    probability = 0.5, sp_product_est = 4, ev_net_est = 0)
  ticket_legs <- tibble::tibble(
    ticket_id = rep('T1', 7),
    fixture_id = paste0('F', 1:7),
    outcome = rep('W', 7))
  prematch_sp <- tibble::tibble(
    fixture_id = paste0('F', 1:7),
    outcome = rep('W', 7),
    quote_at = rep(as.POSIXct('2026-09-21 12:00:00', tz = 'UTC'), 7),
    sp_raw = rep(2, 7),
    source_url = rep('u', 7))

  baseline <- n7_value_tickets(tickets, ticket_legs, prematch_sp, cutoff,
                               sp_threshold = 10, sp_replacement = 4.5,
                               unit_cny = 2, payout_factor = 0.65)
  # 把会话常量改成完全不同的值：显式参数没有变，输出必须逐位相同。
  n7_pipeline_constants(reset = TRUE)
  n7_pipeline_constants(sp_threshold = 3, sp_replacement = 1, unit_cny = 50,
                        payout_factor = 0.1, rho = 0.5)
  repeated <- n7_value_tickets(tickets, ticket_legs, prematch_sp, cutoff,
                               sp_threshold = 10, sp_replacement = 4.5,
                               unit_cny = 2, payout_factor = 0.65)
  testthat::expect_identical(repeated, baseline)

  # 而显式换参数确实会改变结果，说明上面不是"什么都没算"。
  changed <- n7_value_tickets(tickets, ticket_legs, prematch_sp, cutoff,
                              sp_threshold = 10, sp_replacement = 4.5,
                              unit_cny = 2, payout_factor = 0.5)
  testthat::expect_false(identical(changed, baseline))
  n7_pipeline_constants(reset = TRUE)
})

testthat::test_that('结构层 n7_legs 与会话常量解耦', {
  testthat::expect_identical(n7_legs(), 7L)
  n7_pipeline_constants(rho = 0.3, sp_threshold = 5, sp_replacement = 1)
  testthat::expect_identical(n7_legs(), 7L)
  testthat::expect_identical(n7_legs(), N7_LEGS)
})

 testthat::test_that("重新加载包恢复默认值", {
  pkg_path <- pkgload::pkg_path()
  result <- callr::r(function(pkg, libs) {
    .libPaths(libs)
    pkgload::load_all(pkg, quiet = TRUE)
    n7_pipeline_constants(rho = -0.3)
    pkgload::load_all(pkg, quiet = TRUE)
    return(n7_pipeline_constants())
  }, args = list(pkg = pkg_path, libs = .libPaths()))
  testthat::expect_identical(result$rho, -0.14)
})

})()
