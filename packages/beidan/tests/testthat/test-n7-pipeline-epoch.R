# Shared harness (epoch_fixture, default_euro, default_totals) lives in
# helper-n7-fixtures.R so every N7 test file builds the same synthetic world.

testthat::test_that('HK water is converted explicitly and never guessed', {
  testthat::expect_equal(match_hk_to_decimal(0.9), 1.9)
  testthat::expect_equal(match_convert_water(0.9, 'hk', 'over'), 1.9)
  testthat::expect_equal(match_convert_water(1.9, 'decimal', 'over'), 1.9)
  testthat::expect_error(match_convert_water(0.9, 'euro', 'over'), "must be 'decimal' or 'hk'")
  testthat::expect_error(match_convert_water(0.9, c('hk', 'decimal'), 'over'), 'must be one string')
})

testthat::test_that('prepare_epoch selects only quotes strictly before the cutoff', {
  fx <- epoch_fixture()
  prepared <- prepare_engine(fx$inputs, fx$cutoff, default_euro(), default_totals())
  testthat::expect_true(all(prepared$euro_mean$fixture_id %in% prepared$fixtures$fixture_id))
  testthat::expect_equal(nrow(prepared$fixtures), 10L)
  testthat::expect_equal(nrow(prepared$exclusions), 0L)

  # A quote exactly at the cutoff is not admitted (as-of rule is strict).
  late <- fx$inputs
  late$euro$quote_at <- fx$cutoff$cutoff_utc
  prepared_late <- prepare_engine(late, fx$cutoff, default_euro(), default_totals())
  testthat::expect_equal(nrow(prepared_late$fixtures), 0L)
  testthat::expect_true(all(grepl('no euro quote before cutoff', prepared_late$exclusions$reason)))
})

testthat::test_that('a fixture missing a policy member fails rather than averaging the rest', {
  fx <- epoch_fixture()
  partial <- fx$inputs
  # Drop company c03 entirely: the member set is now incomplete.
  partial$euro <- partial$euro[partial$euro$company_id != 'c03', , drop = FALSE]
  testthat::expect_error(
    prepare_engine(partial, fx$cutoff, default_euro(), default_totals()),
    'missing euro members c03')
})

testthat::test_that('drop_member records the reduced member count instead of failing silently', {
  fx <- epoch_fixture()
  partial <- fx$inputs
  partial$euro <- partial$euro[partial$euro$company_id != 'c03', , drop = FALSE]
  prepared <- prepare_engine(partial, fx$cutoff, list(members = c('c01', 'c02', 'c03'), missing = 'drop_member'), default_totals())
  testthat::expect_equal(nrow(prepared$fixtures), 10L)
  testthat::expect_true(all(prepared$euro_mean$n_members == 2L))
})

testthat::test_that('conflicting euro values at one instant are an error, not a coin flip', {
  fx <- epoch_fixture()
  conflicted <- fx$inputs
  duplicate <- conflicted$euro[1, , drop = FALSE]
  duplicate$odds_home <- duplicate$odds_home + 0.5
  conflicted$euro <- dplyr::bind_rows(conflicted$euro, duplicate)
  testthat::expect_error(
    prepare_engine(conflicted, fx$cutoff, default_euro(), default_totals()),
    'conflicting')
})

testthat::test_that('fixtures outside the decision window are excluded with a reason', {
  fx <- epoch_fixture()
  shifted <- fx$inputs
  # Push every kickoff a week later, out of the D+1 window.
  shifted$fixtures$kickoff_at <- shifted$fixtures$kickoff_at + 7 * 86400
  # The ledger is keyed by (issue_id, fixture_id), not by kickoff, so the visible
  # scheduled report still covers these fixtures; only the window rejects them.
  prepared <- prepare_engine(shifted, fx$cutoff, default_euro(), default_totals())
  testthat::expect_equal(nrow(prepared$fixtures), 0L)
  testthat::expect_true(all(prepared$exclusions$reason == 'kickoff outside decision window'))
})

testthat::test_that('projection produces one valid triple per fitted fixture', {
  fx <- epoch_fixture()
  prepared <- prepare_engine(fx$inputs, fx$cutoff, default_euro(), default_totals())
  projected <- estimate_engine(prepared, fx$cutoff, rho = -0.14, total_bounds = c(0.1, 16), tail_tolerance = 1e-10)
  testthat::expect_equal(nrow(projected$fit), 10L)
  testthat::expect_equal(nrow(projected$probabilities), 30L)
  testthat::expect_equal(nrow(projected$exclusions), 0L)

  wide <- tidyr::pivot_wider(projected$probabilities, names_from = outcome,
                             values_from = probability)
  testthat::expect_silent(match_check_probability_sum(as.matrix(wide[, c('W', 'D', 'L')])))
  testthat::expect_true(all(projected$fit$rho == -0.14))
  testthat::expect_true(all(projected$fit$status == 'fitted'))
})

testthat::test_that('the over/under market actually moves the total-goals fit', {
  # This is the contract's key modelling requirement: if OU were decorative, the
  # total would not respond to it, and the model would silently be euro-only.
  fx <- epoch_fixture(n_fixtures = 6L)
  project_with <- function(scale) {
    prepared <- prepare_engine(fx$inputs, fx$cutoff, default_euro(), default_totals())
    prepared$totals_selected$over_decimal <- prepared$totals_selected$over_decimal * scale
    estimate_engine(prepared, fx$cutoff, rho = -0.14, total_bounds = c(0.1, 16), tail_tolerance = 1e-10)
  }
  base <- project_with(1)
  higher_total <- project_with(0.85)   # shorter over price => fewer goals expected
  total_base <- base$fit$lambda_home + base$fit$lambda_away
  total_shifted <- higher_total$fit$lambda_home + higher_total$fit$lambda_away
  testthat::expect_false(isTRUE(all.equal(total_base, total_shifted)))
})

testthat::test_that('rho is bound into the fit and never defaulted internally', {
  fx <- epoch_fixture(n_fixtures = 5L)
  prepared <- prepare_engine(fx$inputs, fx$cutoff, default_euro(), default_totals())
  other <- estimate_engine(prepared, fx$cutoff, rho = 0, total_bounds = c(0.1, 16), tail_tolerance = 1e-10)
  testthat::expect_true(all(other$fit$rho == 0))
  testthat::expect_error(
    estimate_engine(prepared, fx$cutoff, rho = 5, total_bounds = c(0.1, 16), tail_tolerance = 1e-10),
    'rho outside supported range')
})

testthat::test_that('a fixture with no over/under quote is excluded, never euro-priced', {
  fx <- epoch_fixture(n_fixtures = 5L)
  prepared <- prepare_engine(fx$inputs, fx$cutoff, default_euro(), default_totals())
  # Remove one fixture's totals entirely.
  target <- prepared$fixtures$fixture_id[1]
  prepared$totals_selected <- prepared$totals_selected[prepared$totals_selected$fixture_id != target, , drop = FALSE]
  projected <- estimate_engine(prepared, fx$cutoff, rho = -0.14, total_bounds = c(0.1, 16), tail_tolerance = 1e-10)
  testthat::expect_equal(nrow(projected$fit), 4L)
  testthat::expect_equal(nrow(projected$exclusions), 1L)
  testthat::expect_equal(projected$exclusions$fixture_id, target)
  testthat::expect_match(projected$exclusions$reason, 'no over/under quote')
  # The excluded fixture must not appear in probabilities.
  testthat::expect_false(target %in% projected$probabilities$fixture_id)
})

testthat::test_that('an empty epoch yields typed empty probabilities and fit', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  empty_inputs <- read_match_inputs(list(kind = 'frames',
                                      tables = list(match_status = match_typed_empty('match_status'))),
                                 '26097')
  prepared <- prepare_engine(empty_inputs, cutoff, default_euro(), default_totals())
  testthat::expect_equal(nrow(prepared$fixtures), 0L)
  projected <- estimate_engine(prepared, cutoff, rho = -0.14, total_bounds = c(0.1, 16), tail_tolerance = 1e-10)
  testthat::expect_equal(nrow(projected$probabilities), 0L)
  testthat::expect_equal(nrow(projected$fit), 0L)
  testthat::expect_silent(match_validate_table(projected$probabilities, 'probabilities'))
  testthat::expect_silent(match_validate_table(projected$fit, 'fit'))
})

testthat::test_that('total bounds and tail tolerance are validated', {
  fx <- epoch_fixture(n_fixtures = 4L)
  prepared <- prepare_engine(fx$inputs, fx$cutoff, default_euro(), default_totals())
  testthat::expect_error(
    estimate_engine(prepared, fx$cutoff, -0.14, c(1, 0), 1e-10), 'increasing positive')
  testthat::expect_error(
    estimate_engine(prepared, fx$cutoff, -0.14, c(0.1, 16), 1), 'strictly in')
})

testthat::test_that('the totals line policy selects the main line deterministically', {
  fx <- epoch_fixture(n_fixtures = 6L)
  prepared <- prepare_engine(fx$inputs, fx$cutoff, default_euro(), default_totals())
  # The generator emits 2.5 and 3.5 for every company; ties break to the lower.
  testthat::expect_true(all(prepared$totals_selected$line == 2.5))

  pinned <- prepare_engine(fx$inputs, fx$cutoff, default_euro(), list(companies = NULL, line = 3.5,
                                                  watermark = 'decimal'))
  testthat::expect_true(all(pinned$totals_selected$line == 3.5))
})

# --- 逐函数边界测试（epoch）-------------------------------------------------
# review 在此文件累计指出 14 处问题，是第二多的文件，因此边界必须钉死。

testthat::test_that('match_hk_to_decimal 把水位加 1 得到十进制赔率', {
  testthat::expect_identical(match_hk_to_decimal(0), 1)
  testthat::expect_identical(match_hk_to_decimal(1.5), 2.5)
  testthat::expect_identical(match_hk_to_decimal(c(0, 1, 2)), c(1, 2, 3))
  testthat::expect_identical(match_hk_to_decimal(numeric(0)), numeric(0))
})

testthat::test_that('match_hk_to_decimal 拒绝负水位、NA 与非数值', {
  # 负的净赔率根本不是价格，接受它会静默把市场定错价。
  testthat::expect_error(match_hk_to_decimal(-1), 'must be non-negative')
  testthat::expect_error(match_hk_to_decimal(c(1, -0.5)), 'must be non-negative')
  # NA 在 R 中是 logical，因此先被类型检查拦下；两者都必须报错。
  testthat::expect_error(match_hk_to_decimal(NA), 'must be numeric|finite and not NA')
  testthat::expect_error(match_hk_to_decimal(Inf), 'finite and not NA')
  testthat::expect_error(match_hk_to_decimal('abc'), 'must be numeric')
})

testthat::test_that('match_convert_water 按声明的约定转换', {
  testthat::expect_identical(match_convert_water(1.5, 'hk', 'over'), 2.5)
  testthat::expect_identical(match_convert_water(2.5, 'decimal', 'over'), 2.5)
  testthat::expect_identical(match_convert_water(c(1, 2), 'hk', 'over'), c(2, 3))
})

testthat::test_that('match_convert_water 拒绝未知约定与非法 what', {
  testthat::expect_error(match_convert_water(1, 'us', 'over'), 'must be .decimal. or .hk.')
  testthat::expect_error(match_convert_water(1, c('hk','decimal'), 'over'), 'must be one string')
  testthat::expect_error(match_convert_water(1, NA, 'over'), 'must be one string')
  testthat::expect_error(match_convert_water(1, 'hk', NA), 'one non-empty label')
  testthat::expect_error(match_convert_water(1, 'hk', ''), 'one non-empty label')
})

testthat::test_that('match_convert_water 让坏源报错而不是变成静默 NA 价格', {
  # 回归：此前 non-numeric 只 warning，NA 直接通过，两者都产出 NA 价格。
  testthat::expect_error(match_convert_water('abc', 'decimal', 'over'), 'must be numeric')
  testthat::expect_error(match_convert_water(NA, 'decimal', 'over'),
                         'must be numeric|finite and not NA')
  testthat::expect_error(match_convert_water(NA, 'hk', 'over'),
                         'must be numeric|finite and not NA')
  testthat::expect_error(match_convert_water(Inf, 'decimal', 'over'), 'finite and not NA')
  testthat::expect_error(match_convert_water(0, 'decimal', 'over'), 'must be positive')
  testthat::expect_error(match_convert_water(-1, 'decimal', 'over'), 'must be positive')
})

testthat::test_that('match_latest_quote_before 校验 cutoff_utc 与 value_columns', {
  quotes <- match_typed_empty('euro')
  instant <- as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')
  # 回归：非 POSIXct 的 cutoff 会静默匹配不到任何行，使缺报价看起来像市场安静。
  testthat::expect_error(match_latest_quote_before(quotes, '2026-09-22', 'odds_home'),
                         'must be POSIXct')
  testthat::expect_error(match_latest_quote_before(quotes, NULL, 'odds_home'), 'must be POSIXct')
  testthat::expect_error(match_latest_quote_before(quotes, NA, 'odds_home'), 'must be POSIXct')
  testthat::expect_error(
    match_latest_quote_before(quotes, c(instant, instant), 'odds_home'),
    'single non-NA instant')
  # 空 value_columns 会静默跳过全部冲突检查，必须显式报错。
  testthat::expect_error(match_latest_quote_before(quotes, instant, character(0)),
                         'non-empty column names')
  testthat::expect_error(match_latest_quote_before(quotes, instant, ''),
                         'non-empty column names')
  testthat::expect_error(match_latest_quote_before(quotes, instant, NA_character_),
                         'non-empty column names')
  testthat::expect_error(match_latest_quote_before(list(), instant, 'odds_home'),
                         'must be a data frame')
})

testthat::test_that('match_latest_quote_before 只保留严格早于 cutoff 的最新一行的', {
  cutoff <- as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')
  quotes <- tibble::tibble(
    fixture_id = 'f1', company_id = 'c1',
    quote_at = as.POSIXct(c('2026-09-22 08:00:00', '2026-09-22 10:00:00',
                            '2026-09-22 14:00:00'), tz = 'UTC'),
    odds_home = c(2.0, 2.1, 9.9), odds_draw = 3.0, odds_away = 4.0,
    source_url = 'u')
  selected <- match_latest_quote_before(quotes, cutoff, c('odds_home'))
  testthat::expect_equal(nrow(selected), 1L)
  # 选中 10:00 那行；14:00 在 cutoff 之后，绝不能被 admitted。
  testthat::expect_identical(selected$odds_home, 2.1)
})

testthat::test_that('match_latest_quote_before 在 cutoff 早于全部报价时返回 0 行', {
  cutoff <- as.POSIXct('2026-09-22 00:00:00', tz = 'UTC')
  quotes <- tibble::tibble(
    fixture_id = 'f1', company_id = 'c1',
    quote_at = as.POSIXct('2026-09-22 08:00:00', tz = 'UTC'),
    odds_home = 2.0, odds_draw = 3.0, odds_away = 4.0, source_url = 'u')
  selected <- match_latest_quote_before(quotes, cutoff, c('odds_home'))
  testthat::expect_equal(nrow(selected), 0L)
})

testthat::test_that('match_latest_quote_before 在同一时刻取值冲突时报错', {
  cutoff <- as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')
  instant <- as.POSIXct('2026-09-22 10:00:00', tz = 'UTC')
  conflicting <- tibble::tibble(
    fixture_id = 'f1', company_id = 'c1', quote_at = rep(instant, 2L),
    odds_home = c(2.0, 2.5), odds_draw = 3.0, odds_away = 4.0, source_url = 'u')
  # 同一时刻两个不同取值是真实的源冲突，按行序解决会让结果依赖文件顺序。
  testthat::expect_error(match_latest_quote_before(conflicting, cutoff, c('odds_home')),
                         'conflicting odds_home values at one instant')
  # 同一时刻取值一致的行不是冲突，可以正常去重。
  agreeing <- conflicting; agreeing$odds_home <- c(2.0, 2.0)
  selected <- match_latest_quote_before(agreeing, cutoff, c('odds_home'))
  testthat::expect_equal(nrow(selected), 1L)
})

testthat::test_that('match_latest_quote_before 只对实际选中的最新时刻检查冲突', {
  # 真实Titan分钟级旧报价可有并列冲突，不影响最新无歧义报价。
  cutoff <- as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')
  early <- as.POSIXct('2026-09-22 08:00:00', tz = 'UTC')
  late <- as.POSIXct('2026-09-22 10:00:00', tz = 'UTC')
  quotes <- tibble::tibble(
    fixture_id = 'f1', company_id = 'c1', quote_at = c(early, early, late),
    odds_home = c(2.0, 2.7, 2.1), odds_draw = 3.0, odds_away = 4.0, source_url = 'u')
  selected <- match_latest_quote_before(quotes, cutoff, c('odds_home'))
  testthat::expect_equal(nrow(selected), 1L)
  testthat::expect_equal(selected$odds_home, quotes$odds_home[3L])
})

testthat::test_that('match_latest_quote_before 按 fixture 与 company 各自独立选行', {
  cutoff <- as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')
  quotes <- tibble::tibble(
    fixture_id = c('f1','f1','f2'), company_id = c('c1','c1','c1'),
    quote_at = as.POSIXct(c('2026-09-22 08:00:00','2026-09-22 09:00:00',
                            '2026-09-22 09:30:00'), tz = 'UTC'),
    odds_home = c(2.0, 2.1, 3.0), odds_draw = 3.0, odds_away = 4.0, source_url = 'u')
  selected <- match_latest_quote_before(quotes, cutoff, c('odds_home'))
  testthat::expect_equal(nrow(selected), 2L)
  testthat::expect_identical(selected$odds_home[selected$fixture_id == 'f1'], 2.1)
  testthat::expect_identical(selected$odds_home[selected$fixture_id == 'f2'], 3.0)
})

testthat::test_that('match_validate_rho 委托给既有实现对非法 rho 报错', {
  testthat::expect_silent(match_validate_rho(-0.14))
  testthat::expect_error(match_validate_rho(NA))
  testthat::expect_error(match_validate_rho(1))
  testthat::expect_error(match_validate_rho(c(1, 2)))
})

testthat::test_that('match_euro_mean 校验 policy 的形状', {
  cutoff <- as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')
  fixtures <- match_typed_empty('fixtures')
  testthat::expect_error(match_euro_mean(match_typed_empty('euro'), cutoff, 'x', fixtures),
                         'euro_policy must be a list')
  testthat::expect_error(
    match_euro_mean(match_typed_empty('euro'), cutoff, list(), fixtures),
    'members must be unique company ids')
  testthat::expect_error(
    match_euro_mean(match_typed_empty('euro'), cutoff, list(members = c('c1','c1')), fixtures),
    'members must be unique company ids')
  testthat::expect_error(
    match_euro_mean(match_typed_empty('euro'), cutoff,
                  list(members = 'c1', missing = 'ignore'), fixtures),
    "missing must be 'error' or 'drop_member'")
})

testthat::test_that('match_euro_mean 对成员公司求均值并报告覆盖数', {
  cutoff <- as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')
  fixtures <- tibble::tibble(
    issue_id = '26097', fixture_id = 'f1', slot = 1L, provider_id = 'p',
    kickoff_at = as.POSIXct('2026-09-23 02:00:00', tz = 'UTC'), handicap = 0L,
    sale_state = 'open', source_url = 'synthetic://x')
  euro <- tibble::tibble(
    fixture_id = 'f1', company_id = c('c1','c2'),
    quote_at = as.POSIXct('2026-09-22 08:00:00', tz = 'UTC'),
    odds_home = c(2.0, 4.0), odds_draw = c(3.0, 3.0), odds_away = c(4.0, 2.0),
    source_url = 'synthetic://x')
  result <- match_euro_mean(euro, cutoff, list(members = c('c1','c2'), missing = 'error'),
                         fixtures)
  testthat::expect_equal(nrow(result), 1L)
  testthat::expect_identical(result$odds_home, 3.0)
  testthat::expect_identical(result$odds_draw, 3.0)
  testthat::expect_identical(result$odds_away, 3.0)
  testthat::expect_identical(result$n_members, 2L)
})

testthat::test_that('match_euro_mean 的 missing 策略决定成员缺报价时是否报错', {
  cutoff <- as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')
  fixtures <- tibble::tibble(
    issue_id = '26097', fixture_id = 'f1', slot = 1L, provider_id = 'p',
    kickoff_at = as.POSIXct('2026-09-23 02:00:00', tz = 'UTC'), handicap = 0L,
    sale_state = 'open', source_url = 'synthetic://x')
  # 只有 c1 有报价，成员集 {c1, c2} 被部分覆盖。
  euro <- tibble::tibble(
    fixture_id = 'f1', company_id = 'c1',
    quote_at = as.POSIXct('2026-09-22 08:00:00', tz = 'UTC'),
    odds_home = 2.0, odds_draw = 3.0, odds_away = 4.0, source_url = 'synthetic://x')
  testthat::expect_error(
    match_euro_mean(euro, cutoff, list(members = c('c1','c2'), missing = 'error'), fixtures),
    'is missing euro members c2')
  dropped <- match_euro_mean(euro, cutoff,
                          list(members = c('c1','c2'), missing = 'drop_member'), fixtures)
  testthat::expect_identical(dropped$odds_home, 2.0)
  testthat::expect_identical(dropped$n_members, 1L)
})

testthat::test_that('match_euro_mean 对完全没有报价的比赛不报成员集违规', {
  # 完全没报价算 cutoff 前没有报价，只有部分覆盖才是策略要决定的缺陷。
  cutoff <- as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')
  fixtures <- tibble::tibble(
    issue_id = '26097', fixture_id = 'f1', slot = 1L, provider_id = 'p',
    kickoff_at = as.POSIXct('2026-09-23 02:00:00', tz = 'UTC'), handicap = 0L,
    sale_state = 'open', source_url = 'synthetic://x')
  result <- match_euro_mean(match_typed_empty('euro'), cutoff,
                         list(members = c('c1','c2'), missing = 'error'), fixtures)
  testthat::expect_equal(nrow(result), 1L)
  testthat::expect_true(is.na(result$odds_home))
  testthat::expect_identical(result$n_members, 0L)
})

testthat::test_that('match_totals_selected 校验 policy 的形状', {
  cutoff <- as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')
  fixtures <- match_typed_empty('fixtures')
  totals <- match_typed_empty('totals')
  testthat::expect_error(match_totals_selected(totals, cutoff, 'x', fixtures),
                         'totals_policy must be a list')
  # companies = NULL 表示不限制公司，这是合法的，不得报错。
  testthat::expect_silent(
    match_totals_selected(totals, cutoff, list(watermark = 'decimal'), fixtures))
  testthat::expect_error(
    match_totals_selected(totals, cutoff,
                        list(companies = c('c1','c1'), watermark = 'decimal'), fixtures),
    'must be unique company ids')
  testthat::expect_error(
    match_totals_selected(totals, cutoff, list(companies = 1, watermark = 'decimal'), fixtures),
    'must be unique company ids')
  # watermark 必须显式且取值受限：缺失或拼错都不得静默按十进制处理。
  testthat::expect_error(match_totals_selected(totals, cutoff, list(companies = 'c1'), fixtures),
                         'watermark is required')
  testthat::expect_error(
    match_totals_selected(totals, cutoff, list(watermark = 'bogus'), fixtures),
    "must be 'decimal' or 'hk'")
  testthat::expect_error(match_totals_selected(totals, cutoff, list(), fixtures),
                         'watermark is required')
  # line 规则必须在进入逐场循环之前校验：此前空输入会静默接受非法规则。
  testthat::expect_error(
    match_totals_selected(totals, cutoff,
                        list(watermark = 'decimal', line = 'bogus'), fixtures),
    'must be .nearest_main. or a number')
})

testthat::test_that('match_totals_selected 取跨公司出现最多的盘口，并列取低', {
  cutoff <- as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')
  fixtures <- tibble::tibble(
    issue_id = '26097', fixture_id = 'f1', slot = 1L, provider_id = 'p',
    kickoff_at = as.POSIXct('2026-09-23 02:00:00', tz = 'UTC'), handicap = 0L,
    sale_state = 'open', source_url = 'synthetic://x')
  instant <- as.POSIXct('2026-09-22 08:00:00', tz = 'UTC')
  totals <- tibble::tibble(
    fixture_id = 'f1', company_id = c('c1','c2','c3'), quote_at = instant,
    line = c(2.5, 2.5, 3.5), over_decimal = c(1.9, 1.95, 2.4),
    under_decimal = c(1.9, 1.95, 1.6), source_url = 'synthetic://x')
  result <- match_totals_selected(totals, cutoff, list(watermark = 'decimal'), fixtures)
  # 2.5 出现两次，3.5 一次，故主盘是 2.5。
  testthat::expect_true(all(result$line == 2.5))
  testthat::expect_equal(nrow(result), 2L)
})

testthat::test_that('match_totals_selected 支持显式数值盘口与 hk 水位转换', {
  cutoff <- as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')
  fixtures <- tibble::tibble(
    issue_id = '26097', fixture_id = 'f1', slot = 1L, provider_id = 'p',
    kickoff_at = as.POSIXct('2026-09-23 02:00:00', tz = 'UTC'), handicap = 0L,
    sale_state = 'open', source_url = 'synthetic://x')
  instant <- as.POSIXct('2026-09-22 08:00:00', tz = 'UTC')
  totals <- tibble::tibble(
    fixture_id = 'f1', company_id = 'c1', quote_at = instant, line = 3.5,
    over_decimal = 1.9, under_decimal = 1.9, source_url = 'synthetic://x')
  numeric_line <- match_totals_selected(totals, cutoff,
                                     list(watermark = 'decimal', line = 3.5), fixtures)
  testthat::expect_equal(nrow(numeric_line), 1L)
  testthat::expect_identical(numeric_line$over_decimal, 1.9)
  # hk 约定下 1.9 是水位，应转成 2.9 的十进制赔率。
  hk <- match_totals_selected(totals, cutoff, list(watermark = 'hk'), fixtures)
  testthat::expect_identical(hk$over_decimal, 2.9)
  testthat::expect_identical(hk$under_decimal, 2.9)
  # 该盘口不存在时返回 0 行，而不是报错。
  absent <- match_totals_selected(totals, cutoff,
                               list(watermark = 'decimal', line = 9.5), fixtures)
  testthat::expect_equal(nrow(absent), 0L)
})

testthat::test_that('公共入口从输入推导期号并归一化决策时点为 UTC', {
  fx <- epoch_fixture(n_fixtures = 4L)
  policy <- list(euro = default_euro(), totals = default_totals())
  # 带显式时区的决策时点：任何时区都接受，内部归一化为同一瞬时的 UTC。
  decision_at <- lubridate::with_tz(fx$cutoff$cutoff_utc, 'Asia/Shanghai')
  epoch <- prepare_match_inputs(fx$inputs, decision_at, policy)
  testthat::expect_identical(epoch$cutoff$issue_id, '26097')
  testthat::expect_identical(epoch$cutoff$cutoff_utc, fx$cutoff$cutoff_utc)
  testthat::expect_identical(epoch$decision_at, fx$cutoff$cutoff_utc)
  # 选中 SP 暴露为 prematch_sp，而不是 sp_selected/sp。
  testthat::expect_true('prematch_sp' %in% names(epoch))
  testthat::expect_false('sp_selected' %in% names(epoch))
  testthat::expect_false('sp' %in% names(epoch))
  testthat::expect_identical(epoch$market_policy, policy)
  # 缺时区、非法时点、缺市场策略字段、未知字段都必须报错。
  testthat::expect_error(prepare_match_inputs(fx$inputs, NA, policy), 'decision_at')
  testthat::expect_error(prepare_match_inputs(fx$inputs, fx$cutoff$cutoff_utc, list()), 'market_policy')
  testthat::expect_error(
    prepare_match_inputs(fx$inputs, decision_at, list(euro = default_euro())),
    'market_policy')
  testthat::expect_error(
    prepare_match_inputs(fx$inputs, decision_at,
                         list(euro = default_euro(), totals = default_totals(),
                              extra = list())),
    'unknown market_policy')
})

testthat::test_that('公共入口拒绝零期号与多期号输入', {
  policy <- list(euro = default_euro(), totals = default_totals())
  empty <- list(fixtures = match_typed_empty('fixtures'), euro = match_typed_empty('euro'),
                totals = match_typed_empty('totals'), prematch_sp = match_typed_empty('prematch_sp'),
                match_status = match_typed_empty('match_status'))
  decision_at <- as.POSIXct('2026-09-22 12:00:00', tz = 'UTC')
  # 没有比赛就没有期号：先让用户选定读入的期号。
  testthat::expect_error(prepare_match_inputs(empty, decision_at, policy), 'no issue')
  # 多期输入必须拒绝，而不是替用户挑一期。
  first <- epoch_fixture(n_fixtures = 2L)
  second <- make_example_issue('26098', match_kickoff_window('2026-09-22', 2L), seed = 43L)
  multiple <- read_match_inputs(example_match_source(first$issue, second),
                                c('26097', '26098'))
  testthat::expect_error(prepare_match_inputs(multiple, decision_at, policy),
                         'issues')
})

testthat::test_that('prepare_match_inputs 拒绝携带其它期号的比赛', {
  # 回归：期号错配的比赛会在错误的决策日下被定价、分组、买入。
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  stray <- tibble::tibble(
    issue_id = '26098', fixture_id = 'f1', slot = 1L, provider_id = 'p',
    kickoff_at = as.POSIXct('2026-09-23 02:00:00', tz = 'UTC'), handicap = 0L,
    sale_state = 'open', source_url = 'synthetic://x')
  instant <- as.POSIXct('2026-09-22 08:00:00', tz = 'UTC')
  stray_ledger <- tibble::tibble(
    issue_id = '26098', fixture_id = 'f1', status = 'scheduled',
    status_at = instant, available_at = instant, source_url = 'synthetic://x')
  inputs <- list(fixtures = stray, euro = match_typed_empty('euro'),
                 totals = match_typed_empty('totals'), prematch_sp = match_typed_empty('prematch_sp'),
                 match_status = stray_ledger)
  testthat::expect_error(
    prepare_engine(inputs, cutoff, list(members = 'c1'),
                   list(watermark = 'decimal')),
    'but the cutoff is bound to')
})

testthat::test_that('prepare_match_inputs 只保留开赛落在 D+1 窗口内的比赛', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  # 决策窗口是 D+1 整天：2026-09-22 16:00Z .. 2026-09-23 16:00Z。
  inside <- as.POSIXct('2026-09-23 02:00:00', tz = 'UTC')
  before <- as.POSIXct('2026-09-22 10:00:00', tz = 'UTC')
  after <- as.POSIXct('2026-09-23 20:00:00', tz = 'UTC')
  fixtures <- tibble::tibble(
    issue_id = '26097', fixture_id = c('f_in','f_before','f_after'),
    slot = 1:3, provider_id = 'p', kickoff_at = c(inside, before, after),
    handicap = 0L, sale_state = 'open', source_url = 'synthetic://x')
  instant <- as.POSIXct('2026-09-22 08:00:00', tz = 'UTC')
  euro <- tibble::tibble(
    fixture_id = c('f_in','f_before','f_after'), company_id = 'c1', quote_at = instant,
    odds_home = 2.0, odds_draw = 3.0, odds_away = 4.0, source_url = 'synthetic://x')
  ledger <- tibble::tibble(
    issue_id = '26097', fixture_id = c('f_in','f_before','f_after'), status = 'scheduled',
    status_at = instant, available_at = instant, source_url = 'synthetic://x')
  inputs <- list(fixtures = fixtures, euro = euro, totals = match_typed_empty('totals'),
                 prematch_sp = match_typed_empty('prematch_sp'), match_status = ledger)
  epoch <- prepare_engine(inputs, cutoff, list(members = 'c1'),
                          list(watermark = 'decimal'))
  testthat::expect_identical(epoch$fixtures$fixture_id, 'f_in')
  # 被剔除的比赛必须连同原因进入 exclusions，剔除是可审计的。
  testthat::expect_true(all(c('f_before','f_after') %in% epoch$exclusions$fixture_id))
  testthat::expect_true(all(epoch$exclusions$scope == 'epoch'))
})

testthat::test_that('prepare_engine 的空输入返回带完整列的空表', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  inputs <- list(fixtures = match_typed_empty('fixtures'), euro = match_typed_empty('euro'),
                 totals = match_typed_empty('totals'), prematch_sp = match_typed_empty('prematch_sp'),
                 match_status = match_typed_empty('match_status'))
  epoch <- prepare_engine(inputs, cutoff, list(members = 'c1'),
                          list(watermark = 'decimal'))
  testthat::expect_setequal(names(epoch),
                            c('fixtures','euro_mean','totals_selected','prematch_sp',
                              'match_status','status_selected','exclusions'))
  testthat::expect_equal(nrow(epoch$fixtures), 0L)
  testthat::expect_equal(nrow(epoch$exclusions), 0L)
})

testthat::test_that('公共投影对象携带 epoch、cutoff、模型参数与概率', {
  fx <- epoch_fixture(n_fixtures = 5L)
  decision_at <- fx$cutoff$cutoff_utc
  epoch <- prepare_match_inputs(fx$inputs, decision_at,
                                list(euro = default_euro(), totals = default_totals()))
  model_config <- list(rho = -0.14, total_bounds = c(0.1, 16), tail_tolerance = 1e-10)
  projected <- estimate_match_probabilities(epoch, model_config)
  # 投影自带绑定上下文：cutoff/fixtures/prematch_sp/match_status 与概率一起返回。
  testthat::expect_identical(projected$cutoff, epoch$cutoff)
  testthat::expect_identical(projected$fixtures, epoch$fixtures)
  testthat::expect_identical(projected$prematch_sp, epoch$prematch_sp)
  testthat::expect_identical(projected$model_config, model_config)
  testthat::expect_equal(nrow(projected$probabilities), 5L * 3L)
  # 模型参数显式：缺字段、未知字段、非法取值都在这里失败。
  testthat::expect_error(estimate_match_probabilities(epoch, list(rho = -0.14)), 'model_config')
  testthat::expect_error(
    estimate_match_probabilities(epoch, list(rho = -0.14, total_bounds = c(0.1, 16),
                                             tail_tolerance = 1e-10, extra = 1)),
    'unknown model_config')
  testthat::expect_error(estimate_match_probabilities(list(), model_config), 'epoch')
})

testthat::test_that('合约束值 rho 不在会话参数里，而是 model_config 的一部分', {
  # rho 属于单场模型参数；会话快照不含它，因此冻结值必须显式传入 model_config。
  testthat::expect_false('rho' %in% names(parlay_settings()))
  testthat::expect_silent(match_validate_rho(-0.14))
})

testthat::test_that("euro policy excludes unrelated companies and fixtures before conflicts", {
  fx <- epoch_fixture()
  euro <- fx$inputs$euro
  baseline <- match_euro_mean(euro, fx$cutoff$cutoff_utc, default_euro(), fx$inputs$fixtures)
  extra <- euro[rep(1L, 2L), ]
  extra$company_id <- "not-a-member"
  extra$odds_home <- c(2, 3)
  actual <- match_euro_mean(dplyr::bind_rows(euro, extra), fx$cutoff$cutoff_utc,
                            default_euro(), fx$inputs$fixtures)
  testthat::expect_equal(actual, baseline)
})
