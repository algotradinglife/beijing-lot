(function() {
# 可变场数串场合同（issue #512 stage1）
#
# 覆盖范围：
#   · parlay_settings 接受 6/7/8 与任意整数 >=1，默认 7，无臆测上界
#   · 结构与票长度随 n_legs 变化；同一方案禁止混合场数
#   · 6/7/8 场端到端：构组 -> 结构 -> 枚举 -> 估值 -> 排名 -> 资金 -> 冻结
#   · 冻结的 n_legs/unit/payout 不被之后的 session 改动改写
#   · 结构不匹配（pattern 与组宽度不一致）显式报错
#   · 空表在 6/7/8 场下都返回 typed-empty
#   · 枚举只对真实数值/分配上限报错，不设任意 max

parlay_settings(reset = TRUE)
on.exit(parlay_settings(reset = TRUE), add = TRUE)

# 生成任意场数的合成一期，并给出已定价的 epoch。
leg_fixture <- function(n_legs, n_fixtures = n_legs, seed = 42L,
                        local_date = '2026-09-22') {
  kickoff_at <- match_kickoff_window(local_date, n_fixtures)
  issue <- make_example_issue('26097', kickoff_at, seed = seed)
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'),
                 issue_id = '26097')
  inputs <- read_match_inputs(example_match_source(issue), '26097')
  prepared <- prepare_engine(inputs, cutoff, list(members = c('c01', 'c02', 'c03'), missing = 'error'), list(companies = NULL, line = 'nearest_main',
                         watermark = 'decimal'))
  estimated <- estimate_engine(prepared, cutoff, -0.14, c(0.1, 16), 1e-10)
  # 公共计划入口消费的是绑定上下文的投影对象（cutoff + 选中场次 + 状态台账 + 赛前SP）。
  projection <- list(cutoff = cutoff, fixtures = prepared$fixtures,
                     probabilities = estimated$probabilities,
                     prematch_sp = prepared$prematch_sp,
                     match_status = prepared$match_status,
                     fit = estimated$fit, exclusions = estimated$exclusions)
  list(issue = issue, cutoff = cutoff, inputs = inputs, projected = projection,
       fixtures = prepared$fixtures, probabilities = estimated$probabilities,
       match_status = prepared$match_status)
}

# 一个 3/2/1 递减的 n 位结构，元素只取 1/2/3。
leg_pattern <- function(n_legs) {
  as.integer(pmax(1L, pmin(3L, seq(3L, 1L, length.out = n_legs))))
}

# Block 8 public path: one explicit strategy configuration for an arbitrary plan
# width. There is no fixed group count; the funded groups are derived from the
# budget and the reuse/overlap constraints. `wide` is the contract's 3333222-style
# depth profile (repeated/truncated to n_legs), `narrow` its 2222221 counterpart.
block8_leg_config <- function(n_legs, name = "legs") {
  wide <- as.integer(rep_len(c(3L, 3L, 3L, 3L, 2L, 2L, 2L), n_legs))
  narrow <- as.integer(rep_len(c(2L, 2L, 2L, 2L, 2L, 2L, 1L), n_legs))
  pattern <- function(values) {
    stats::setNames(list(values), paste0("p", paste(values, collapse = "")))
  }
  parlay_strategy_config(
    parlay_settings(), name = name,
    construction_policy = list(max_candidates = 2L, seed = 1L),
    patterns = c(pattern(wide), pattern(narrow)),
    objective = "probability", max_reuse = 1L, max_overlap = n_legs - 1L,
    spend_limit_cny = 16)
}

# --- 会话参数：可变宽度 -----------------------------------------------------

testthat::test_that('parlay_settings 默认 7，接受 6/8 与任意整数 >=1', {
  testthat::expect_identical(parlay_settings(reset = TRUE)$n_legs, 7L)
  for (width in c(1L, 6L, 7L, 8L, 15L)) {
    testthat::expect_identical(parlay_settings(n_legs = width)$n_legs,
                               as.integer(width))
  }
  # 非整数 / 0 / 负数被拒；没有臆测的任意上界。
  for (bad in list(0, -1, 2.5)) {
    testthat::expect_error(parlay_settings(n_legs = bad), 'n_legs')
  }
  testthat::expect_error(parlay_settings(n_legs = .Machine$integer.max + 1),
                         'n_legs')
  testthat::expect_error(parlay_settings(n_legs = 1e12), 'n_legs')
})

testthat::test_that('结构宽度来自 group_legs，与 session 当前值解耦', {
  legs <- tibble::tibble(group_id = rep('G', 8), fixture_id = paste0('F', 1:8),
                         leg_order = 1:8)
  parlay_settings(n_legs = 6L)
  # 即使 session 声称 6，结构宽度仍是表里真实的 8。
  testthat::expect_identical(parlay_structure_legs(legs), 8L)
})

# --- 6/7/8 场端到端 ---------------------------------------------------------

for (WIDTH in c(6L, 7L, 8L)) {
  local({
    width <- WIDTH
    testthat::test_that(sprintf('%d 场：构组/结构/枚举/估值/排名/资金/冻结端到端', width), {
      fx <- leg_fixture(width, n_fixtures = width * 2L)
      parlay_settings(reset = TRUE)
      parlay_settings(n_legs = width, unit_cny = 2, payout_factor = 0.65)

      groups <- parlay_construct_groups(fx$fixtures, fx$probabilities,
                                        fx$cutoff, width, 'fixture_round_robin',
                                        2L, seed = 1L,
                                        match_status = fx$match_status)
      # 每组恰好 width 条腿。
      per_group <- table(groups$group_legs$group_id)
      testthat::expect_true(all(per_group == width))
      testthat::expect_identical(parlay_structure_legs(groups$group_legs), width)

      pattern <- leg_pattern(width)
      structure <- parlay_apply_structure(groups$group_legs, fx$probabilities,
                                          fx$cutoff, pattern)
      testthat::expect_true(nrow(structure$supports) > 0L)

      tickets <- parlay_enumerate_tickets(groups$group_legs,
                                          fx$probabilities, fx$cutoff,
                                          structure$supports)
      # 每条票恰好 width 条腿——这是"结构长度匹配 n_legs"的核心断言。
      legs_per_ticket <- table(tickets$ticket_legs$ticket_id)
      testthat::expect_true(all(legs_per_ticket == width))

      valued <- parlay_value_tickets(tickets$tickets, tickets$ticket_legs,
                                     fx$issue$prematch_sp, fx$cutoff,
                                     sp_threshold = 10, sp_replacement = 4.5,
                                     unit_cny = 2, payout_factor = 0.65)
      ranked <- parlay_rank_tickets(valued, tickets$candidate_tickets, fx$cutoff)

      config <- block8_leg_config(width)
      result <- parlay_build_plan(fx$projected, config)
      testthat::expect_identical(result$plan$constants$n_legs, width)
      testthat::expect_identical(parlay_structure_legs(result$plan$group_legs), width)
      # 冻结计划里的票也恰好 width 条腿。
      frozen_legs <- table(result$plan$ticket_legs$ticket_id)
      testthat::expect_true(all(frozen_legs == width))
    })
  })
}

# --- 混合场数 / 结构不匹配 ---------------------------------------------------

testthat::test_that('结构 pattern 与组宽度不一致时显式报错', {
  fx <- leg_fixture(6L, n_fixtures = 6L)
  groups <- parlay_construct_groups(fx$fixtures, fx$probabilities,
                                    fx$cutoff, 6L, 'fixture_round_robin', 1L, seed = 1L,
                                    match_status = fx$match_status)
  # 用七位 pattern 套六场组：必须报错，而不是补齐或截断。
  testthat::expect_error(
    parlay_apply_structure(groups$group_legs, fx$probabilities, fx$cutoff,
                           rep(2L, 7L)),
    'pattern must be 6')
})

testthat::test_that('parlay_enumerate_tickets 拒绝与组宽度不符的 n_legs', {
  fx <- leg_fixture(6L, n_fixtures = 6L)
  groups <- parlay_construct_groups(fx$fixtures, fx$probabilities,
                                    fx$cutoff, 6L, 'fixture_round_robin', 1L, seed = 1L,
                                    match_status = fx$match_status)
  structure <- parlay_apply_structure(groups$group_legs, fx$probabilities,
                                      fx$cutoff, leg_pattern(6L))
  testthat::expect_error(
    parlay_enumerate_tickets(groups$group_legs, fx$probabilities, fx$cutoff,
                             structure$supports, n_legs = 7L),
    'does not match the group width')
  # 非整数 / 越界宽度被拒。
  testthat::expect_error(
    parlay_enumerate_tickets(groups$group_legs, fx$probabilities, fx$cutoff,
                             structure$supports, n_legs = 0L),
    'at least 1')
})

testthat::test_that('.BuildDecisionTables 拒绝与 n_legs 不符的 pattern', {
  fx <- leg_fixture(7L, n_fixtures = 7L)
  parlay_settings(reset = TRUE)
  parlay_settings(n_legs = 7L)
  testthat::expect_error(
    .BuildDecisionTables(fx$fixtures, fx$probabilities,
                          fx$issue$prematch_sp, fx$cutoff, fx$match_status,
                          patterns = list(rep(2L, 6L)), construction = 'fixture_round_robin',
                          max_candidates = 1L, seed = 1L,
                          constants = parlay_settings()),
    'every pattern must have 7 legs')
})

# --- 冻结不受 session 变化影响 -----------------------------------------------

testthat::test_that('冻结的 n_legs/unit/payout 不被之后的 session 改动改写', {
  width <- 6L
  fx <- leg_fixture(width, n_fixtures = width)
  parlay_settings(reset = TRUE)
  parlay_settings(n_legs = width, unit_cny = 2, payout_factor = 0.65)
  config <- block8_leg_config(width)
  result <- parlay_build_plan(fx$projected, config)
  frozen <- result$plan
  # 之后的 session 改动：宽度、单价、赔付因子全部改掉。
  parlay_settings(n_legs = 8L, unit_cny = 50, payout_factor = 0.1)
  testthat::expect_identical(frozen$constants$n_legs, width)
  testthat::expect_identical(frozen$constants$unit_cny, 2)
  testthat::expect_identical(frozen$constants$payout_factor, 0.65)
  # 结算读取冻结值，产生的 stake 必须是 2 而不是 50。
  settled <- parlay_settle_plan(frozen, match_typed_empty('settlements'),
                                as.POSIXct('2026-11-01 00:00:00', tz = 'UTC'))
  if (nrow(settled$ticket_returns)) {
    testthat::expect_true(all(settled$ticket_returns$stake_cny == 2))
  }
  parlay_settings(reset = TRUE)
})

# --- 空表 -------------------------------------------------------------------

testthat::test_that('6/7/8 场下空输入都返回 typed-empty，而不是报错', {
  for (width in c(6L, 7L, 8L)) {
    empty_groups <- match_typed_empty('group_legs')
    testthat::expect_identical(parlay_structure_legs(empty_groups), 0L)
    res <- parlay_enumerate_tickets(empty_groups, match_typed_empty('probabilities'),
                                    list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00',
                                                                 tz = 'UTC'),
                                         issue_id = '26097'),
                                    match_typed_empty('supports'), n_legs = width)
    testthat::expect_identical(nrow(res$tickets), 0L)
    testthat::expect_identical(names(res$tickets), match_table_schemas()$tickets$columns)
  }
})

# --- 公共正常路径：上下文 / 篡改 / 多期 / 混合场数 / 空表 ---------------------

testthat::test_that('公共路径保留显式决策上下文，结算读取冻结常量', {
  width <- 6L
  fx <- leg_fixture(width, n_fixtures = width * 2L)
  parlay_settings(reset = TRUE)
  parlay_settings(n_legs = width, unit_cny = 2, payout_factor = 0.65)
  config <- block8_leg_config(width)
  result <- parlay_build_plan(fx$projected, config)
  # 上下文随输出返回：cutoff 与投影对象都在结果里，不需要调用方重新拼装。
  testthat::expect_identical(result$cutoff$issue_id, '26097')
  testthat::expect_identical(result$cutoff, fx$cutoff)
  testthat::expect_identical(result$constants, config$settings)
  testthat::expect_identical(result$plan$constants$n_legs, width)
  # history 是下一次调用必须交回的对象：purchases 与 fixture_sets 一起传递。
  testthat::expect_true(all(c('purchases', 'fixture_sets') %in% names(result$history)))
  # 诊断走公共入口，单价/派彩系数来自冻结常量，而不是调用方另传。
  depth <- parlay_diagnose_plan(result, match_typed_empty('settlements'),
                                as.POSIXct('2026-11-01 00:00:00', tz = 'UTC'))
  testthat::expect_s3_class(depth, 'tbl_df')
})

testthat::test_that('投影必须在两个边界都绑定同一 cutoff，拒绝错配上下文', {
  width <- 7L
  fx <- leg_fixture(width, n_fixtures = width * 2L)
  parlay_settings(reset = TRUE)
  config <- block8_leg_config(width)
  # 非投影对象、缺字段、cutoff 与 fixtures 不同期，都必须显式报错。
  testthat::expect_error(parlay_build_plan(list(), config), 'projected')
  broken <- fx$projected
  broken$cutoff <- NULL
  testthat::expect_error(parlay_build_plan(broken, config), 'cutoff')
  wrong_issue <- fx$projected
  wrong_issue$cutoff <- list(cutoff_utc = fx$cutoff$cutoff_utc, issue_id = '99001')
  testthat::expect_error(parlay_build_plan(wrong_issue, config), 'issue')
})

testthat::test_that('策略配置拒绝未知字段与缺字段，不做静默回退', {
  fx <- leg_fixture(7L, n_fixtures = 14L)
  parlay_settings(reset = TRUE)
  config <- block8_leg_config(7L)
  # 拼错的预算字段不能被忽略——否则真实上限会退回默认值。
  typo <- utils::modifyList(config, list(budgt_cny = 160))
  typo$budget_cny <- NULL
  testthat::expect_error(parlay_build_plan(fx$projected, typo), 'unknown field')
  incomplete <- config
  incomplete$max_reuse <- NULL
  testthat::expect_error(parlay_build_plan(fx$projected, incomplete), 'missing')
  bad_pattern <- config
  bad_pattern$patterns <- list(c(rep(2L, 6L), 1L))
  testthat::expect_error(parlay_build_plan(fx$projected, bad_pattern), 'pattern')
})

testthat::test_that('同一期多次决策共享账本与复用/重叠上限', {
  width <- 7L
  fx <- leg_fixture(width, n_fixtures = width * 4L)
  parlay_settings(reset = TRUE)
  config <- block8_leg_config(width)
  first <- parlay_build_plan(fx$projected, config)
  # 第二次决策拿回第一次的 history：已买过的物理票不得重复扣款。
  testthat::expect_error(parlay_build_plan(fx$projected, config,
    prior_purchases = first$history), 'strictly before')
  later_epoch <- prepare_match_inputs(fx$inputs, fx$cutoff$cutoff_utc + lubridate::hours(1),
    list(euro = list(members = c('c01', 'c02', 'c03'), missing = 'error'),
         totals = list(companies = NULL, line = 'nearest_main', watermark = 'decimal')))
  second <- parlay_build_plan(estimate_match_probabilities(later_epoch), config,
                              prior_purchases = first$history)
  testthat::expect_equal(anyDuplicated(c(first$funded$purchases$ticket_id,
                                         second$funded$purchases$ticket_id)), 0L)
  # 整期额度是绝对上限：两次决策合计不得超过 issue_budget_cny。
  testthat::expect_lte(sum(first$funded$purchases$stake_cny) +
                         sum(second$funded$purchases$stake_cny),
                       config$settings$issue_budget_cny)
  # 同一期多决策必须走公共回放；跨期序列被明确拒绝。
  second_projection <- fx$projected
  second_projection$cutoff <- list(cutoff_utc = fx$cutoff$cutoff_utc + 3600,
                                   issue_id = '26097')
  replayed <- parlay_replay_issue(list(fx$projected, second_projection), config,
                                  match_typed_empty('settlements'),
                                  as.POSIXct('2026-11-01 00:00:00', tz = 'UTC'))
  testthat::expect_equal(replayed$metrics$n_epochs, 2L)
  testthat::expect_equal(anyDuplicated(replayed$purchases$ticket_id), 0L)
  other <- second_projection
  other$cutoff <- list(cutoff_utc = fx$cutoff$cutoff_utc, issue_id = '26098')
  other$fixtures$issue_id[] <- '26098'
  other$match_status$issue_id[] <- '26098'
  testthat::expect_error(
    parlay_replay_issue(list(fx$projected, other), config,
                        match_typed_empty('settlements'),
                        as.POSIXct('2026-11-01 00:00:00', tz = 'UTC')),
    'one issue')
})

testthat::test_that('投影后的未来状态变更不能改写既有决策', {
  width <- 7L
  fx <- leg_fixture(width, n_fixtures = width * 2L)
  parlay_settings(reset = TRUE)
  config <- block8_leg_config(width)
  baseline <- parlay_build_plan(fx$projected, config)
  # 一个在 cutoff 之后才可见的取消状态：不得进入本决策。
  later <- fx$match_status[1L, ]
  later$status <- 'cancelled'
  later$status_at <- fx$cutoff$cutoff_utc + lubridate::hours(1)
  later$available_at <- later$status_at
  tampered <- fx$projected
  tampered$match_status <- dplyr::bind_rows(fx$match_status, later)
  changed <- parlay_build_plan(tampered, config)
  testthat::expect_identical(changed$plan$purchases, baseline$plan$purchases)
})

testthat::test_that('空投影返回 typed-empty 计划而不是报错', {
  empty_projection <- list(
    cutoff = list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'),
                  issue_id = '26097'),
    fixtures = match_typed_empty('fixtures'),
    probabilities = match_typed_empty('probabilities'),
    prematch_sp = match_typed_empty('prematch_sp'),
    match_status = match_typed_empty('match_status'))
  parlay_settings(reset = TRUE)
  config <- block8_leg_config(7L)
  result <- parlay_build_plan(empty_projection, config)
  testthat::expect_identical(nrow(result$funded$purchases), 0L)
  testthat::expect_identical(names(result$funded$purchases),
                             match_table_schemas()$purchases$columns)
  testthat::expect_identical(nrow(result$plan$purchases), 0L)
  depth <- parlay_diagnose_plan(result, match_typed_empty('settlements'),
                                as.POSIXct('2026-11-01 00:00:00', tz = 'UTC'))
  testthat::expect_identical(nrow(depth), 0L)
})

})()
