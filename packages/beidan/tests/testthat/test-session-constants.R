(function() {
# 会话常量读写契约：parlay_settings(...)
#
# 覆盖范围（逐条对应任务契约）：
#   · 零参调用 = 读取当前会话快照
#   · 命名局部更新 = 返回完整列表快照
#   · reset=TRUE 不接受命名更新；reset 单独给出 -> 恢复默认
#   · 默认值恰如合同冻结值
#   · 未知 / 未命名 / 重复字段，NULL/NA/NaN/Inf，非标量 / 类型错误，非逻辑 reset
#   · 完整候选先校验后更新内存 -> 每次失败都是原子的（状态不变）
#   · 取值约束：n_legs 整数 >=1（默认 7，数值归一化为 integer）、budget>=0、
#     unit>0、factor(0,1]、SP 值 >0 且 replacement<=threshold
#   · 无文件 / options / 全局环境写入；新进程从默认值开始
#   · 快照互相独立
#   · 下游不因会话常量变更而改变行为（显式参数仍然说了算）

parlay_settings(reset = TRUE)
on.exit(parlay_settings(reset = TRUE), add = TRUE)

CONSTANT_NAMES <- c('n_legs', 'issue_budget_cny', 'unit_cny', 'payout_factor',
                    'sp_threshold', 'sp_replacement')

# --- 读取 / 默认值 ----------------------------------------------------------

testthat::test_that('零参调用读取当前会话快照，且键集合与默认值恰如合同', {
  parlay_settings(reset = TRUE)
  constants <- parlay_settings()
  testthat::expect_type(constants, 'list')
  testthat::expect_identical(names(constants), CONSTANT_NAMES)
  testthat::expect_identical(constants$n_legs, 7L)
  testthat::expect_identical(constants$issue_budget_cny, 1024)
  testthat::expect_identical(constants$unit_cny, 2)
  testthat::expect_identical(constants$payout_factor, 0.65)
  testthat::expect_identical(constants$sp_threshold, 10)
  testthat::expect_identical(constants$sp_replacement, 4.5)
})

testthat::test_that('零参调用的返回是当前会话值，而不总是默认值', {
  parlay_settings(sp_threshold = 22)
  testthat::expect_identical(parlay_settings()$sp_threshold, 22)
})

# --- 局部更新：返回完整快照 --------------------------------------------------

testthat::test_that('命名局部更新返回完整列表快照，且未提及的字段保持不变', {
  parlay_settings(reset = TRUE)
  updated <- parlay_settings(sp_threshold = 18, issue_budget_cny = 512)
  # 返回的必须是完整快照，而不是只含被更新字段的补丁。
  testthat::expect_identical(names(updated), CONSTANT_NAMES)
  testthat::expect_length(updated, 6L)
  testthat::expect_identical(updated$sp_threshold, 18)
  testthat::expect_identical(updated$issue_budget_cny, 512)
  testthat::expect_identical(updated$unit_cny, 2)
  testthat::expect_identical(updated$payout_factor, 0.65)
  testthat::expect_identical(updated$sp_replacement, 4.5)
  # 更新内存后的会话状态与返回值一致。
  testthat::expect_identical(parlay_settings(), updated)
})

testthat::test_that('更新可以叠加，后续更新基于当前会话值', {
  parlay_settings(sp_threshold = 20)
  second <- parlay_settings(unit_cny = 5)
  testthat::expect_identical(second$sp_threshold, 20)
  testthat::expect_identical(second$unit_cny, 5)
})

testthat::test_that('n_legs 接受 6/7/8 等整数 >=1 并归一化为 integer', {
  for (width in c(1L, 6L, 7L, 8L, 12L)) {
    updated <- parlay_settings(n_legs = width)
    testthat::expect_identical(updated$n_legs, as.integer(width))
    testthat::expect_type(updated$n_legs, 'integer')
  }
})

# --- reset ------------------------------------------------------------------

testthat::test_that('reset = TRUE 恢复冻结默认值', {
  parlay_settings(reset = TRUE)
  parlay_settings(n_legs = 8L, unit_cny = 9, sp_threshold = 20,
                        sp_replacement = 3)
  restored <- parlay_settings(reset = TRUE)
  testthat::expect_identical(restored, parlay_settings())
  testthat::expect_identical(restored$n_legs, 7L)
  testthat::expect_identical(restored$unit_cny, 2)
  testthat::expect_identical(restored$sp_threshold, 10)
  testthat::expect_identical(restored$sp_replacement, 4.5)
  testthat::expect_identical(restored$n_legs, 7L)
})

testthat::test_that('reset = TRUE cannot be combined with updates', {
  parlay_settings(n_legs = 8L, sp_threshold = 12)
  before <- parlay_settings()
  testthat::expect_error(parlay_settings(reset = TRUE, sp_threshold = 11, n_legs = 6L), 'combined')
  testthat::expect_identical(parlay_settings(), before)
  testthat::expect_error(parlay_settings(reset = TRUE, sp_threshold = 0), 'combined')
  testthat::expect_identical(parlay_settings(), before)
})

testthat::test_that('reset 必须是非 NA 的逻辑标量', {
  testthat::expect_error(parlay_settings(reset = NA), 'reset')
  testthat::expect_error(parlay_settings(reset = 'yes'), 'reset')
  testthat::expect_error(parlay_settings(reset = 1), 'reset')
  testthat::expect_error(parlay_settings(reset = c(TRUE, FALSE)), 'reset')
  testthat::expect_error(parlay_settings(reset = NULL), 'reset')
})

# --- 字段名结构：未知 / 未命名 / 重复 / NULL --------------------------------

testthat::test_that('未知字段名被拒绝', {
  testthat::expect_error(parlay_settings(bogus = 1), 'bogus|subset')
  # rho 不属于会话参数：单场 rho 是 model_config 的一部分，不是会话快照字段。
  testthat::expect_error(parlay_settings(rho = -0.14), 'rho|subset')
})

testthat::test_that('未命名字段被拒绝', {
  testthat::expect_error(parlay_settings(5), 'named')
  testthat::expect_error(parlay_settings(sp_threshold = 12, 5), 'named')
})

testthat::test_that('重复字段名被拒绝，且不会静默保留最后一个', {
  before <- parlay_settings()
  testthat::expect_error(parlay_settings(sp_threshold = 18, sp_threshold = 20), 'duplicate')
  testthat::expect_error(
    parlay_settings(unit_cny = 3, unit_cny = 4, sp_threshold = 11), 'duplicate')
  testthat::expect_identical(parlay_settings(), before)
})

testthat::test_that('NULL 字段被拒绝', {
  testthat::expect_error(parlay_settings(n_legs = NULL), 'n_legs|sp_threshold')
  testthat::expect_error(parlay_settings(sp_threshold = NULL), 'n_legs|sp_threshold')
})

# --- 取值类型：NA / NaN / Inf / 非标量 / 错误类型 ---------------------------

testthat::test_that('每个常量都拒绝 NA / NaN / Inf', {
  for (field in CONSTANT_NAMES) {
    bad <- list(NA_real_, NaN, Inf, -Inf)
    for (value in bad) {
      args <- stats::setNames(list(value), field)
      testthat::expect_error(do.call(parlay_settings, args), NULL,
                             info = paste(field, '=', value))
    }
  }
})

testthat::test_that('每个常量都拒绝非标量', {
  for (field in CONSTANT_NAMES) {
    args <- stats::setNames(list(c(1, 2)), field)
    testthat::expect_error(do.call(parlay_settings, args), NULL,
                           info = paste(field, 'non-scalar'))
  }
})

testthat::test_that('每个常量都拒绝错误类型', {
  for (field in CONSTANT_NAMES) {
    for (value in list('x', TRUE, list(1), factor('a'), as.Date('2026-01-01'), matrix(7), structure(7, class = 'custom'))) {
      args <- stats::setNames(list(value), field)
      testthat::expect_error(do.call(parlay_settings, args), NULL,
                             info = paste(field, 'wrong type'))
    }
  }
})

# --- 取值约束 ---------------------------------------------------------------

testthat::test_that('n_legs 接受 6/7/8 及任意整数 >=1，拒绝 0/负数/非整数', {
  # 6 与 8 此前被拒（固定七场），现在按可变场数合同合法接受。
  for (good in list(6, 7, 8, 1, 3, 12)) {
    testthat::expect_identical(parlay_settings(n_legs = good)$n_legs,
                               as.integer(good), info = paste('n_legs =', good))
  }
  for (bad in list(0, -7, 7.5, 0.5)) {
    testthat::expect_error(parlay_settings(n_legs = bad), 'n_legs',
                           info = paste('n_legs =', bad))
  }
  # 无臆测上界：真实限制只是整数表示范围。
  testthat::expect_error(parlay_settings(n_legs = .Machine$integer.max + 1),
                         'n_legs')
})

testthat::test_that('issue_budget_cny 允许 0，拒绝负值', {
  testthat::expect_identical(parlay_settings(issue_budget_cny = 0)$issue_budget_cny, 0)
  testthat::expect_error(parlay_settings(issue_budget_cny = -1), 'issue_budget_cny')
  testthat::expect_error(parlay_settings(issue_budget_cny = -0.01), 'issue_budget_cny')
})

testthat::test_that('unit_cny 必须严格为正', {
  testthat::expect_identical(parlay_settings(unit_cny = 0.5)$unit_cny, 0.5)
  testthat::expect_error(parlay_settings(unit_cny = 0), 'unit_cny must be positive')
  testthat::expect_error(parlay_settings(unit_cny = -2), 'unit_cny')
})

testthat::test_that('payout_factor 落在 (0, 1]：1 允许，0 与 >1 拒绝', {
  testthat::expect_identical(parlay_settings(payout_factor = 1)$payout_factor, 1)
  testthat::expect_identical(parlay_settings(payout_factor = 0.5)$payout_factor, 0.5)
  testthat::expect_error(parlay_settings(payout_factor = 0), 'payout_factor')
  testthat::expect_error(parlay_settings(payout_factor = 1.01), 'payout_factor')
  testthat::expect_error(parlay_settings(payout_factor = -0.5), 'payout_factor')
})

testthat::test_that('rho 已移出会话参数块，成为显式 model 参数（stage2）', {
  # rho 不再是 session 常量键；它的取值范围仍由 dc_validate_rho 在显式传参处校验。
  testthat::expect_false('rho' %in% names(parlay_settings()))
  testthat::expect_error(parlay_settings(rho = -0.14), 'rho|subset')
  testthat::expect_silent(dc_validate_rho(-0.14))
  testthat::expect_error(dc_validate_rho(-0.51), 'rho')
})

testthat::test_that('SP 值必须为正，且 replacement 不得超过 threshold', {
  testthat::expect_identical(parlay_settings(sp_threshold = 12)$sp_threshold, 12)
  testthat::expect_identical(parlay_settings(sp_replacement = 3)$sp_replacement, 3)
  # 边界：replacement == threshold 允许。
  both <- parlay_settings(sp_threshold = 8, sp_replacement = 8)
  testthat::expect_identical(both$sp_threshold, 8)
  testthat::expect_identical(both$sp_replacement, 8)
  testthat::expect_error(parlay_settings(sp_threshold = 1, sp_replacement = 0.5), 'sp_threshold')
  testthat::expect_error(parlay_settings(sp_threshold = 0), 'sp_threshold')
  testthat::expect_error(parlay_settings(sp_threshold = -1), 'sp_threshold')
  testthat::expect_error(parlay_settings(sp_replacement = 0), 'sp_replacement')
  testthat::expect_error(parlay_settings(sp_replacement = -4.5), 'sp_replacement')
  # 单独抬高 replacement 越过当前 threshold 也必须失败：校验的是完整候选快照。
  testthat::expect_error(parlay_settings(sp_replacement = 11), 'must not exceed')
})

# --- 原子性 ----------------------------------------------------------------

testthat::test_that('每次失败都是原子的：状态与调用前完全相同', {
  parlay_settings(sp_threshold = 20, unit_cny = 3)
  before <- parlay_settings()
  failing <- list(
    quote(parlay_settings(sp_threshold = 12, unit_cny = 0)),
    quote(parlay_settings(issue_budget_cny = 999, n_legs = 0)),
    quote(parlay_settings(sp_threshold = 20, sp_replacement = 30)),
    quote(parlay_settings(sp_threshold = Inf, payout_factor = 0.9)),
    quote(parlay_settings(bogus = 1)),
    quote(parlay_settings(sp_threshold = 11, sp_threshold = 13)),
    quote(parlay_settings(NA)),
    quote(parlay_settings(reset = TRUE, sp_threshold = 0))
  )
  for (expr in failing) {
    testthat::expect_error(eval(expr))
    testthat::expect_identical(parlay_settings(), before,
                               info = deparse(expr))
  }
})

testthat::test_that('成功更新前不会留下部分写入的中间态', {
  parlay_settings(sp_threshold = 20)
  before <- parlay_settings()
  # 第二个字段非法：第一个字段绝不能已经被写进去。
  testthat::expect_error(parlay_settings(issue_budget_cny = 777, sp_threshold = 0))
  after <- parlay_settings()
  testthat::expect_identical(after$issue_budget_cny, before$issue_budget_cny)
  testthat::expect_identical(after$sp_threshold, before$sp_threshold)
  testthat::expect_identical(after, before)
})

# --- 快照独立 ---------------------------------------------------------------

testthat::test_that('返回的快照互相独立，修改返回值不影响会话状态', {
  parlay_settings(reset = TRUE)
  first <- parlay_settings()
  first$sp_threshold <- 99
  first$n_legs <- 3L
  second <- parlay_settings()
  testthat::expect_identical(second$sp_threshold, 10)
  testthat::expect_identical(second$n_legs, 7L)
  # 两个快照本身也不共享存储。
  third <- parlay_settings()
  third$unit_cny <- 123
  testthat::expect_false(identical(third, second))
  testthat::expect_identical(parlay_settings()$unit_cny, 2)
})

testthat::test_that('reset 返回的是新建的默认列表，而不是共享同一对象', {
  a <- parlay_settings(reset = TRUE)
  a$sp_threshold <- 88
  b <- parlay_settings(reset = TRUE)
  testthat::expect_identical(b$sp_threshold, 10)
})

# --- 无文件 / options / 全局环境副作用 --------------------------------------

testthat::test_that('读写会话常量不写文件、不碰 options、不写全局环境', {
  before_options <- options()
  before_globals <- ls(envir = globalenv())
  before_files <- list.files(tempdir(), all.files = TRUE)

  parlay_settings(sp_threshold = 12, unit_cny = 4)
  parlay_settings()
  parlay_settings(reset = TRUE)

  testthat::expect_identical(options(), before_options)
  testthat::expect_setequal(ls(envir = globalenv()), before_globals)
  testthat::expect_setequal(list.files(tempdir(), all.files = TRUE), before_files)
  # 全局环境里不得出现常量对象名。
  testthat::expect_false(exists('.parlay_session_settings', envir = globalenv(),
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
  parlay_settings(sp_threshold = 31, issue_budget_cny = 77)
  result <- callr::r(
    function(pkg, r_libs, lib_paths) {
      if (nzchar(r_libs)) .libPaths(c(r_libs, lib_paths)) else .libPaths(lib_paths)
      pkgload::load_all(pkg, quiet = TRUE)
      parlay_settings()
    },
    args = list(pkg = pkg_path, r_libs = r_libs, lib_paths = lib_paths)
  )
  testthat::expect_identical(result$sp_threshold, 10)
  testthat::expect_identical(result$issue_budget_cny, 1024)
  testthat::expect_identical(result$n_legs, 7L)
  # 本进程的值不受子进程影响。
  testthat::expect_identical(parlay_settings()$sp_threshold, 31)
})

# --- 下游不变性 -------------------------------------------------------------

testthat::test_that('下游计算仍以显式传入的常量为准，不受会话状态影响', {
  parlay_settings(reset = TRUE)
  # 一笔票的估值必须只取决于 parlay_value_tickets 收到的显式参数。
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

  physical_id <- parlay_physical_ticket_key(ticket_legs$fixture_id, rep(1L, 7L))
  tickets$ticket_id <- physical_id
  ticket_legs$ticket_id <- physical_id

  baseline <- parlay_value_tickets(tickets, ticket_legs, prematch_sp, cutoff,
                               sp_threshold = 10, sp_replacement = 4.5,
                               unit_cny = 2, payout_factor = 0.65)
  # 把会话常量改成完全不同的值：显式参数没有变，输出必须逐位相同。
  parlay_settings(reset = TRUE)
  parlay_settings(sp_threshold = 3, sp_replacement = 1, unit_cny = 50,
                        payout_factor = 0.1)
  repeated <- parlay_value_tickets(tickets, ticket_legs, prematch_sp, cutoff,
                               sp_threshold = 10, sp_replacement = 4.5,
                               unit_cny = 2, payout_factor = 0.65)
  testthat::expect_identical(repeated, baseline)

  # 而显式换参数确实会改变结果，说明上面不是"什么都没算"。
  changed <- parlay_value_tickets(tickets, ticket_legs, prematch_sp, cutoff,
                              sp_threshold = 10, sp_replacement = 4.5,
                              unit_cny = 2, payout_factor = 0.5)
  testthat::expect_false(identical(changed, baseline))
  parlay_settings(reset = TRUE)
})

testthat::test_that('冻结方案读取自身常量，会话改动不改写已冻结方案', {
  # 冻结层的 n_legs/unit/payout 来自方案本身；会话常量改动只影响下一次构建。
  parlay_settings(n_legs = 7L, unit_cny = 2, payout_factor = 0.65)
  frozen <- list(
    issue_id = '26097',
    constants = list(n_legs = 7L, unit_cny = 2, payout_factor = 0.65,
                     issue_budget_cny = 1024, sp_threshold = 10,
                     sp_replacement = 4.5),
    funded = match_typed_empty('purchases'),
    ticket_legs = match_typed_empty('ticket_legs'))
  parlay_settings(n_legs = 8L, unit_cny = 50, payout_factor = 0.1)
  settled <- parlay_settle_plan(frozen, match_typed_empty('settlements'),
                                as.POSIXct('2026-09-25 00:00:00', tz = 'UTC'))
  # 空计划返回空结果，但读取的仍是冻结值（8 场/50/0.1 的会话值未被使用）。
  testthat::expect_equal(nrow(settled$issue_returns), 0L)
  testthat::expect_identical(frozen$constants$n_legs, 7L)
  testthat::expect_identical(frozen$constants$unit_cny, 2)
  testthat::expect_identical(frozen$constants$payout_factor, 0.65)
  parlay_settings(reset = TRUE)
})

 testthat::test_that("重新加载包恢复默认值", {
  pkg_path <- pkgload::pkg_path()
  result <- callr::r(function(pkg, libs) {
    .libPaths(libs)
    pkgload::load_all(pkg, quiet = TRUE)
    parlay_settings(sp_threshold = 30)
    pkgload::load_all(pkg, quiet = TRUE)
    return(parlay_settings())
  }, args = list(pkg = pkg_path, libs = .libPaths()))
  testthat::expect_identical(result$sp_threshold, 10)
})

})()
