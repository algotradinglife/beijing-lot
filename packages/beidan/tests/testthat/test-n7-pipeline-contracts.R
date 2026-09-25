testthat::test_that('every declared table has a typed empty with matching schema', {
  for (table in names(n7_table_schemas())) {
    empty <- n7_typed_empty(table)
    schema <- n7_table_schemas()[[table]]
    testthat::expect_identical(names(empty), schema$columns)
    testthat::expect_equal(nrow(empty), 0L)
    testthat::expect_silent(n7_validate_table(empty, table))
  }
})

testthat::test_that('typed empty tables keep types so bind_rows is safe', {
  a <- n7_typed_empty('euro')
  b <- n7_typed_empty('euro')
  bound <- dplyr::bind_rows(a, b)
  testthat::expect_identical(names(bound), names(a))
  testthat::expect_type(bound$odds_home, 'double')
  testthat::expect_s3_class(bound$quote_at, 'POSIXct')
  testthat::expect_silent(n7_validate_table(bound, 'euro'))
})

testthat::test_that('a populated table binds onto a typed empty without type drift', {
  empty <- n7_typed_empty('probabilities')
  populated <- tibble::tibble(fixture_id = 'f1', outcome = 'W', probability = 0.5)
  bound <- dplyr::bind_rows(empty, populated)
  testthat::expect_equal(nrow(bound), 1L)
  testthat::expect_silent(n7_validate_table(bound, 'probabilities'))
})

testthat::test_that('unknown table names are rejected rather than guessed', {
  testthat::expect_error(n7_typed_empty('nope'), 'unknown table')
  testthat::expect_error(n7_validate_table(tibble::tibble(), 'nope'), 'unknown table')
})

testthat::test_that('column order and type are enforced, not silently repaired', {
  good <- n7_typed_empty('fixtures')
  reordered <- good[, rev(names(good))]
  testthat::expect_error(n7_validate_table(reordered, 'fixtures'), 'columns must be exactly')

  wrong_type <- good
  wrong_type$slot <- as.double(wrong_type$slot)
  testthat::expect_error(n7_validate_table(wrong_type, 'fixtures'), 'must be integer')

  extra <- good
  extra$surprise <- character(0)
  testthat::expect_error(n7_validate_table(extra, 'fixtures'), 'columns must be exactly')
})

testthat::test_that('a non-UTC POSIXct column is rejected at the boundary', {
  bad <- n7_typed_empty('euro')
  bad$quote_at <- as.POSIXct(character(0), tz = 'Asia/Shanghai')
  testthat::expect_error(n7_validate_table(bad, 'euro'), 'must carry tz UTC')
})

testthat::test_that('duplicate keys are rejected when keys are declared', {
  dup <- tibble::tibble(
    issue_id = c('26097', '26097'), fixture_id = c('f1', 'f1'), slot = c(1L, 1L),
    provider_id = 'synthetic', kickoff_at = as.POSIXct(c('2026-09-22 11:00:00', '2026-09-22 11:00:00'), tz = 'UTC'),
    handicap = c(0L, 0L), sale_state = 'open', source_url = 'synthetic://x')
  testthat::expect_silent(n7_validate_table(dup, 'fixtures'))
  testthat::expect_error(n7_validate_table(dup, 'fixtures', keys = c('issue_id', 'fixture_id')),
                         'duplicate key')
})

testthat::test_that('character ids reject NA, empty and padded values', {
  testthat::expect_silent(n7_check_character_id(c('26097', '00101'), 'ids'))
  testthat::expect_error(n7_check_character_id(c('26097', NA), 'ids'), 'must not be NA')
  testthat::expect_error(n7_check_character_id(c('26097', ''), 'ids'), 'must not be empty')
  testthat::expect_error(n7_check_character_id(c('26097', ' 26097'), 'ids'), 'must not be padded')
  testthat::expect_error(n7_check_character_id(26097, 'ids'), 'must be character')
})

testthat::test_that('slots must be positive whole numbers and come back integer', {
  testthat::expect_identical(n7_check_slot(c(1, 7)), c(1L, 7L))
  testthat::expect_error(n7_check_slot(c(0, 1)), 'positive whole')
  testthat::expect_error(n7_check_slot(c(1.5)), 'positive whole')
  testthat::expect_error(n7_check_slot(c(1, NA)), 'finite')
})

testthat::test_that('probability triples must be non-negative and sum to exactly 1', {
  testthat::expect_silent(n7_check_probability_sum(matrix(c(0.5, 0.3, 0.2), nrow = 1)))
  testthat::expect_silent(n7_check_probability_sum(matrix(c(1, 0, 0, 0, 1, 0), nrow = 2, byrow = TRUE)))
  testthat::expect_error(n7_check_probability_sum(matrix(c(0.5, 0.3, 0.1), nrow = 1)), 'sum to 1')
  testthat::expect_error(n7_check_probability_sum(matrix(c(0.5, 0.6, 0.2), nrow = 1)), 'sum to 1')
  testthat::expect_error(n7_check_probability_sum(matrix(c(-0.1, 0.6, 0.5), nrow = 1)), 'non-negative')
  testthat::expect_error(n7_check_probability_sum(matrix(c(NA, 0.5, 0.5), nrow = 1)), 'must be finite')
})

testthat::test_that('a cutoff is required and must be a UTC temporal_learning object', {
  good <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  testthat::expect_silent(n7_require_cutoff(good))
  testthat::expect_identical(n7_cutoff_utc(good), good$cutoff_utc)

  testthat::expect_error(n7_require_cutoff(NULL), 'explicit cutoff is required')
  testthat::expect_error(n7_require_cutoff('2026-09-22'), 'must be a temporal_learning object')
  testthat::expect_error(
    n7_require_cutoff(list(cutoff_utc = as.POSIXct('2026-09-22', tz = 'Asia/Shanghai'), issue_id = '26097')),
    'must be UTC')
  testthat::expect_error(
    n7_require_cutoff(list(cutoff_utc = as.POSIXct('2026-09-22', tz = 'UTC'))), 'missing issue_id')
  testthat::expect_error(
    n7_require_cutoff(list(cutoff_utc = c(as.POSIXct('2026-09-22', tz = 'UTC'),
                                           as.POSIXct('2026-09-23', tz = 'UTC')), issue_id = '26097')),
    'single instant')
})

testthat::test_that('a naive timestamp is rejected rather than assumed UTC', {
  naive <- tibble::tibble(
    fixture_id = 'f1', company_id = 'c01', quote_at = '2026-09-22T11:00:00',
    odds_home = 2, odds_draw = 3, odds_away = 4, source_url = 'synthetic://x')
  testthat::expect_error(n7_coerce_source_table(naive, 'euro'), 'explicit UTC offset')
})

testthat::test_that('an offset-bearing timestamp is accepted and normalised to UTC', {
  ok <- tibble::tibble(
    fixture_id = 'f1', company_id = 'c01', quote_at = '2026-09-22T11:00:00Z',
    odds_home = 2, odds_draw = 3, odds_away = 4, source_url = 'synthetic://x')
  out <- n7_coerce_source_table(ok, 'euro')
  testthat::expect_s3_class(out$quote_at, 'POSIXct')
  testthat::expect_identical(attr(out$quote_at, 'tzone'), 'UTC')
})

testthat::test_that('unexpected or missing csv columns are rejected', {
  missing_col <- tibble::tibble(fixture_id = 'f1', company_id = 'c01')
  testthat::expect_error(n7_coerce_source_table(missing_col, 'euro'), 'is missing columns')

  extra_col <- tibble::tibble(
    fixture_id = 'f1', company_id = 'c01', quote_at = '2026-09-22T11:00:00Z',
    odds_home = 2, odds_draw = 3, odds_away = 4, source_url = 'synthetic://x', extra = 1)
  testthat::expect_error(n7_coerce_source_table(extra_col, 'euro'), 'unexpected columns')
})

testthat::test_that('read_inputs returns typed empty tables for an empty source', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  result <- n7_read_inputs(n7_empty_frames(), '26097')
  testthat::expect_setequal(names(result), c('fixtures', 'euro', 'totals', 'prematch_sp', 'match_status'))
  for (table in names(result)) {
    testthat::expect_equal(nrow(result[[table]]), 0L)
    testthat::expect_silent(n7_validate_table(result[[table]], table))
  }
})

testthat::test_that('read_inputs never returns a settlement table', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  issue <- n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 8L), seed = 7L)
  result <- n7_read_inputs(n7_fixture_source(issue), '26097')
  testthat::expect_false('settlements' %in% names(result))
})

testthat::test_that('read_inputs filters to the requested issues only', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  a <- n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 8L), seed = 1L)
  b <- n7_make_fixture_issue('26098', n7_kickoff_window('2026-09-23', 8L), seed = 2L)
  source <- n7_fixture_source(a, b)
  result <- n7_read_inputs(source, '26097')
  testthat::expect_true(all(result$fixtures$issue_id == '26097'))
  testthat::expect_equal(nrow(result$fixtures), 8L)
  testthat::expect_equal(nrow(result$euro), 8L * 3L)
})

testthat::test_that('network-like sources are refused', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  testthat::expect_error(n7_read_inputs(list(kind = 'http', url = 'http://example.com'), '26097'),
                         'network sources are not permitted')
  testthat::expect_error(n7_read_inputs(list(kind = 'csv_dir', path = '/nonexistent-xyz'), '26097'),
                         'existing directory')
})

testthat::test_that('the synthetic fixture is internally consistent and deterministic', {
  a <- n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 8L), seed = 11L)
  b <- n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 8L), seed = 11L)
  testthat::expect_identical(a$fixtures, b$fixtures)
  testthat::expect_identical(a$truth, b$truth)

  # Truth triples are valid probabilities.
  testthat::expect_silent(n7_check_probability_sum(a$truth))

  # De-vigging the mean euro odds recovers the generating triple.
  mean_euro <- a$euro |>
    dplyr::group_by(fixture_id) |>
    dplyr::summarise(h = mean(odds_home), d = mean(odds_draw), aa = mean(odds_away), .groups = 'drop')
  inverse <- 1 / as.matrix(mean_euro[, c('h', 'd', 'aa')])
  recovered <- inverse / rowSums(inverse)
  testthat::expect_true(max(abs(recovered - a$truth)) < 0.02)

  # Every generated row declares itself synthetic.
  testthat::expect_true(all(grepl('^synthetic://', a$fixtures$source_url)))
  testthat::expect_true(all(grepl('^synthetic://', a$euro$source_url)))
})

# --- 逐函数边界测试（contracts）--------------------------------------------
# 每个函数按其 roxygen @param 契约逐条写用例：正常输入、边界、空/缺失、失败路径。
# 参数表里有多少行约束，这里就有多少个必须存在的测试。

testthat::test_that('n7_table_schemas 自身不变量：列无重复且 types 与 columns 对齐', {
  schemas <- n7_table_schemas()
  testthat::expect_type(schemas, 'list')
  testthat::expect_length(schemas, 16L)
  for (name in names(schemas)) {
    schema <- schemas[[name]]
    testthat::expect_true(length(schema$columns) > 0L)
    # 列名不得重复，否则 setNames/位置访问都会静默错位。
    testthat::expect_equal(anyDuplicated(schema$columns), 0L)
    # types 的名字集合必须与 columns 完全相同且同序。
    testthat::expect_identical(names(schema$types), schema$columns)
    # 每个类型都必须是 n7_typed_empty 能构造的类型。
    testthat::expect_true(all(schema$types %in% c('character','integer','double','logical','POSIXct')))
  }
})

testthat::test_that('n7_table_schemas 覆盖合同要求的全部表', {
  expected <- c('fixtures','euro','totals','prematch_sp','match_status',
                'candidate_tickets','ranked',
                'probabilities','fit','group_legs','supports','tickets','ticket_legs',
                'purchases','settlements','exclusions')
  testthat::expect_setequal(names(n7_table_schemas()), expected)
})

testthat::test_that('n7_outcomes 是固定顺序的 W/D/L', {
  testthat::expect_identical(n7_outcomes(), c('W','D','L'))
  testthat::expect_length(n7_outcomes(), 3L)
  testthat::expect_type(n7_outcomes(), 'character')
})

testthat::test_that('n7_typed_empty 拒绝非标量、NA、空串与未知表名', {
  testthat::expect_error(n7_typed_empty(c('tickets','purchases')), 'single non-empty')
  testthat::expect_error(n7_typed_empty(NA), 'single non-empty')
  testthat::expect_error(n7_typed_empty(1), 'single non-empty')
  testthat::expect_error(n7_typed_empty(''), 'single non-empty')
  testthat::expect_error(n7_typed_empty(character(0)), 'single non-empty')
  testthat::expect_error(n7_typed_empty('no_such_table'), 'unknown table')
})

testthat::test_that('n7_typed_empty 为每张表给出正确的列类型', {
  expected <- list(tickets = c(ticket_id = 'character', group_id = 'character',
                               probability = 'double', sp_product_est = 'double',
                               ev_net_est = 'double'))
  empty <- n7_typed_empty('tickets')
  testthat::expect_true(inherits(empty, 'tbl_df'))
  testthat::expect_identical(names(empty), names(expected$tickets))
  for (column in names(expected$tickets)) {
    # typeof(), not class(): class() reports doubles as "numeric", which would
    # make this assertion pass or fail for the wrong reason.
    testthat::expect_identical(typeof(empty[[column]]), expected$tickets[[column]])
  }
})

testthat::test_that('n7_typed_empty 的 POSIXct 列携带 UTC 时区', {
  for (table in c('fixtures','euro','totals','prematch_sp','purchases','settlements')) {
    empty <- n7_typed_empty(table)
    for (column in names(empty)) {
      if (inherits(empty[[column]], 'POSIXct')) {
        testthat::expect_identical(attr(empty[[column]], 'tzone'), 'UTC')
      }
    }
  }
})

testthat::test_that('n7_validate_table 拒绝非标量/未知表名', {
  data <- n7_typed_empty('tickets')
  testthat::expect_error(n7_validate_table(data, c('tickets','purchases')), 'single non-empty')
  testthat::expect_error(n7_validate_table(data, NA), 'single non-empty')
  testthat::expect_error(n7_validate_table(data, ''), 'single non-empty')
  testthat::expect_error(n7_validate_table(data, 'no_such_table'), 'unknown table')
})

testthat::test_that('n7_validate_table 拒绝非 data.frame', {
  testthat::expect_error(n7_validate_table(list(), 'tickets'), 'must be a data frame')
  testthat::expect_error(n7_validate_table(NULL, 'tickets'), 'must be a data frame')
  testthat::expect_error(n7_validate_table(1:3, 'tickets'), 'must be a data frame')
})

testthat::test_that('n7_validate_table 强制列集合、列序与列类型', {
  data <- n7_typed_empty('tickets')
  reordered <- data[, rev(names(data))]
  testthat::expect_error(n7_validate_table(reordered, 'tickets'), 'columns must be exactly')
  missing_column <- data[, setdiff(names(data), 'group_id')]
  testthat::expect_error(n7_validate_table(missing_column, 'tickets'), 'columns must be exactly')
  extra <- data; extra$extra_column <- character(0)
  testthat::expect_error(n7_validate_table(extra, 'tickets'), 'columns must be exactly')
  drift <- data; drift$probability <- integer(0)
  testthat::expect_error(n7_validate_table(drift, 'tickets'), 'must be double')
})

testthat::test_that('n7_validate_table 对零长度 POSIXct 也校验时区', {
  data <- n7_typed_empty('settlements')
  data$label_available_at <- as.POSIXct(character(0), tz = 'Asia/Shanghai')
  testthat::expect_error(n7_validate_table(data, 'settlements'), 'must carry tz UTC')
})

testthat::test_that('n7_validate_table 的 keys 参数必须显式且合法', {
  data <- n7_typed_empty('tickets')
  # 空向量不是「不校验」的表达方式：要么显式给列名，要么写 NULL（用 schema 声明的键）。
  testthat::expect_error(n7_validate_table(data, 'tickets', keys = character(0)),
                         'must be NULL to use the schema')
  testthat::expect_error(n7_validate_table(data, 'tickets', keys = NA_character_), 'keys must be')
  testthat::expect_error(n7_validate_table(data, 'tickets', keys = ''), 'keys must be')
  testthat::expect_error(n7_validate_table(data, 'tickets', keys = 1), 'keys must be')
  testthat::expect_error(n7_validate_table(data, 'tickets', keys = 'no_such_column'),
                         'not in tickets')
  testthat::expect_silent(n7_validate_table(data, 'tickets', keys = NULL))
  testthat::expect_silent(n7_validate_table(data, 'tickets', keys = 'ticket_id'))
})

testthat::test_that('n7_validate_table 在空表上不检查重复键', {
  data <- n7_typed_empty('tickets')
  testthat::expect_silent(n7_validate_table(data, 'tickets', keys = 'ticket_id'))
})

testthat::test_that('n7_validate_table 返回原表以便管道内联', {
  data <- n7_typed_empty('tickets')
  result <- n7_validate_table(data, 'tickets')
  testthat::expect_identical(result, data)
})

testthat::test_that('n7_check_character_id 拒绝 NA、空串、带空白与非字符', {
  testthat::expect_silent(n7_check_character_id('26097', 'issue_id'))
  testthat::expect_silent(n7_check_character_id(character(0), 'issue_id'))
  testthat::expect_silent(n7_check_character_id(c('a','b'), 'issue_id'))
  testthat::expect_error(n7_check_character_id(26097, 'issue_id'), 'must be character')
  testthat::expect_error(n7_check_character_id(NA_character_, 'issue_id'), 'must not be NA')
  testthat::expect_error(n7_check_character_id('', 'issue_id'), 'must not be empty')
  testthat::expect_error(n7_check_character_id(' a', 'issue_id'), 'must not be padded')
  testthat::expect_error(n7_check_character_id('a ', 'issue_id'), 'must not be padded')
  testthat::expect_error(n7_check_character_id(c('a', NA), 'issue_id'), 'must not be NA')
})

testthat::test_that('n7_check_character_id 的 what 标签本身必须合法', {
  testthat::expect_error(n7_check_character_id('a', c('x','y')), 'single non-empty label')
  testthat::expect_error(n7_check_character_id('a', NA), 'single non-empty label')
  testthat::expect_error(n7_check_character_id('a', ''), 'single non-empty label')
  testthat::expect_error(n7_check_character_id('a', 1), 'single non-empty label')
})

testthat::test_that('n7_check_character_id 返回输入本身且不修改', {
  value <- c('26097', '26098')
  result <- n7_check_character_id(value, 'issue_id')
  testthat::expect_identical(result, value)
})

testthat::test_that('n7_check_slot 接受正整数并返回 integer', {
  testthat::expect_identical(n7_check_slot(1L), 1L)
  testthat::expect_identical(n7_check_slot(c(1, 7, 14)), c(1L, 7L, 14L))
  testthat::expect_type(n7_check_slot(3), 'integer')
  testthat::expect_identical(n7_check_slot(integer(0)), integer(0))
  testthat::expect_identical(n7_check_slot(.Machine$integer.max), .Machine$integer.max)
})

testthat::test_that('n7_check_slot 拒绝零、负数、小数、NA 与非数值', {
  testthat::expect_error(n7_check_slot(0), 'positive whole numbers')
  testthat::expect_error(n7_check_slot(-1), 'positive whole numbers')
  testthat::expect_error(n7_check_slot(1.5), 'positive whole numbers')
  testthat::expect_error(n7_check_slot(NA_real_), 'must be finite')
  testthat::expect_error(n7_check_slot(Inf), 'must be finite')
  testthat::expect_error(n7_check_slot('1'), 'must be numeric')
})

testthat::test_that('n7_check_slot 在超出 integer 范围时报错而非静默产出 NA', {
  testthat::expect_error(n7_check_slot(3e9), 'exceeds the integer range')
  testthat::expect_error(n7_check_slot(.Machine$integer.max + 1), 'exceeds the integer range')
  result <- tryCatch(n7_check_slot(3e9), error = function(e) 'errored', warning = function(w) 'warned')
  testthat::expect_identical(result, 'errored')
})

testthat::test_that('n7_check_slot 的 what 标签本身必须合法', {
  testthat::expect_error(n7_check_slot(1, what = c('a','b')), 'single non-empty label')
  testthat::expect_error(n7_check_slot(1, what = NA), 'single non-empty label')
  testthat::expect_error(n7_check_slot(1, what = ''), 'single non-empty label')
})

testthat::test_that('n7_check_probability_sum 接受合法三元组', {
  triples <- matrix(c(0.5, 0.3, 0.2, 0.34, 0.33, 0.33), nrow = 2, byrow = TRUE)
  testthat::expect_silent(n7_check_probability_sum(triples))
  # 0 行矩阵是合法的（没有三元组可校验）。
  testthat::expect_silent(n7_check_probability_sum(matrix(numeric(0), nrow = 0, ncol = 3)))
})

testthat::test_that('n7_check_probability_sum 接受 data.frame 但不接受非数值列', {
  good <- data.frame(W = 0.5, D = 0.3, L = 0.2)
  testthat::expect_silent(n7_check_probability_sum(good))
  # 回归：as.matrix() 会把字符列强转成字符矩阵，必须提前拦住。
  bad <- data.frame(W = '0.5', D = '0.3', L = '0.2', stringsAsFactors = FALSE)
  testthat::expect_error(n7_check_probability_sum(bad), 'only numeric columns')
  factored <- data.frame(W = factor('0.5'), D = 0.3, L = 0.2)
  testthat::expect_error(n7_check_probability_sum(factored), 'only numeric columns')
})

testthat::test_that('n7_check_probability_sum 拒绝行和不为 1 的三元组', {
  testthat::expect_error(n7_check_probability_sum(matrix(c(0.5, 0.3, 0.3), nrow = 1)),
                         'must sum to 1')
  testthat::expect_error(n7_check_probability_sum(matrix(c(0.5, 0.4, 0.4), nrow = 1)),
                         'must sum to 1')
  # 容差内的偏差必须放行。
  testthat::expect_silent(n7_check_probability_sum(matrix(c(1/3, 1/3, 1/3), nrow = 1)))
})

testthat::test_that('n7_check_probability_sum 拒绝负值、NA 与非有限', {
  testthat::expect_error(n7_check_probability_sum(matrix(c(-0.1, 0.6, 0.5), nrow = 1)),
                         'must be non-negative')
  testthat::expect_error(n7_check_probability_sum(matrix(c(NA, 0.5, 0.5), nrow = 1)),
                         'must be finite')
  testthat::expect_error(n7_check_probability_sum(matrix(c(Inf, 0, 0), nrow = 1)),
                         'must be finite')
})

testthat::test_that('n7_check_probability_sum 拒绝非矩阵/非数据框与非法 tolerance', {
  testthat::expect_error(n7_check_probability_sum(c(0.5, 0.3, 0.2)), 'matrix or data frame')
  testthat::expect_error(n7_check_probability_sum('abc'), 'matrix or data frame')
  testthat::expect_error(n7_check_probability_sum(NULL), 'matrix or data frame')
  triples <- matrix(c(0.5, 0.3, 0.2), nrow = 1)
  testthat::expect_error(n7_check_probability_sum(triples, tolerance = 0), 'positive finite')
  testthat::expect_error(n7_check_probability_sum(triples, tolerance = -1), 'positive finite')
  testthat::expect_error(n7_check_probability_sum(triples, tolerance = NA), 'positive finite')
  testthat::expect_error(n7_check_probability_sum(triples, tolerance = c(1e-9, 1e-8)), 'positive finite')
})

testthat::test_that('n7_check_probability_sum 的 what 标签本身必须合法', {
  triples <- matrix(c(0.5, 0.3, 0.2), nrow = 1)
  testthat::expect_error(n7_check_probability_sum(triples, what = c('a','b')), 'single non-empty label')
  testthat::expect_error(n7_check_probability_sum(triples, what = NA), 'single non-empty label')
  testthat::expect_error(n7_check_probability_sum(triples, what = ''), 'single non-empty label')
})

testthat::test_that('n7_require_cutoff 拒绝 NULL、非 list 与缺字段', {
  testthat::expect_error(n7_require_cutoff(NULL), 'explicit cutoff is required')
  testthat::expect_error(n7_require_cutoff('2026-09-22'), 'must be a temporal_learning object')
  testthat::expect_error(n7_require_cutoff(1), 'must be a temporal_learning object')
  testthat::expect_error(
    n7_require_cutoff(list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'))),
    'missing issue_id')
  testthat::expect_error(n7_require_cutoff(list(issue_id = '26097')), 'missing cutoff_utc')
})

testthat::test_that('n7_require_cutoff 要求 cutoff_utc 是单个 UTC POSIXct', {
  naive <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00'), issue_id = '26097')
  testthat::expect_error(n7_require_cutoff(naive), 'must be POSIXct|must be UTC')
  wrong_zone <- list(cutoff_utc = as.POSIXct('2026-09-22 20:00:00', tz = 'Asia/Shanghai'),
                     issue_id = '26097')
  testthat::expect_error(n7_require_cutoff(wrong_zone), 'must be UTC')
  not_ct <- list(cutoff_utc = '2026-09-22T12:00:00Z', issue_id = '26097')
  testthat::expect_error(n7_require_cutoff(not_ct), 'must be POSIXct')
  two_instants <- list(
    cutoff_utc = as.POSIXct(c('2026-09-22 12:00:00', '2026-09-23 12:00:00'), tz = 'UTC'),
    issue_id = '26097')
  testthat::expect_error(n7_require_cutoff(two_instants), 'single instant')
})

testthat::test_that('n7_require_cutoff 要求 issue_id 恰好是一个合法标识符', {
  # 回归：此前多值 issue_id 会静默通过，使下游的 issue 过滤变得有歧义。
  two_issues <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'),
                     issue_id = c('26097', '26098'))
  testthat::expect_error(n7_require_cutoff(two_issues), 'exactly one issue')
  zero_issues <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'),
                      issue_id = character(0))
  testthat::expect_error(n7_require_cutoff(zero_issues), 'exactly one issue')
  bad_id <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = NA)
  testthat::expect_error(n7_require_cutoff(bad_id), 'must be character')
  empty_id <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '')
  testthat::expect_error(n7_require_cutoff(empty_id), 'must not be empty')
  numeric_id <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = 26097)
  testthat::expect_error(n7_require_cutoff(numeric_id), 'must be character')
})

testthat::test_that('n7_require_cutoff 接受合法 cutoff 且不改动它', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  before <- cutoff
  testthat::expect_silent(n7_require_cutoff(cutoff))
  testthat::expect_identical(cutoff, before)
})

testthat::test_that('n7_cutoff_utc 返回单个 UTC 时刻并继承全部校验', {
  cutoff <- list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'), issue_id = '26097')
  instant <- n7_cutoff_utc(cutoff)
  testthat::expect_s3_class(instant, 'POSIXct')
  testthat::expect_length(instant, 1L)
  testthat::expect_identical(attr(instant, 'tzone'), 'UTC')
  testthat::expect_identical(instant, cutoff$cutoff_utc)
  # 非法输入必须仍然报错，说明它确实先调用了 n7_require_cutoff。
  testthat::expect_error(n7_cutoff_utc(NULL), 'explicit cutoff is required')
  testthat::expect_error(n7_cutoff_utc(list(cutoff_utc = as.POSIXct('2026-09-22 12:00:00', tz = 'UTC'),
                                          issue_id = c('a','b'))), 'exactly one issue')
})

testthat::test_that('n7_pipeline_constants 的键集合与取值恰如合同冻结值', {
  # 本文件只保证默认值；会话读写契约在 test-session-constants.R 里逐条覆盖。
  constants <- n7_pipeline_constants(reset = TRUE)
  testthat::expect_type(constants, 'list')
  testthat::expect_setequal(
    names(constants),
    c('n_legs','issue_budget_cny','unit_cny','payout_factor','rho',
      'sp_threshold','sp_replacement'))
  testthat::expect_identical(constants$n_legs, 7L)
  testthat::expect_identical(constants$issue_budget_cny, 1024)
  testthat::expect_identical(constants$unit_cny, 2)
  testthat::expect_identical(constants$payout_factor, 0.65)
  testthat::expect_identical(constants$rho, -0.14)
  testthat::expect_identical(constants$sp_threshold, 10)
  testthat::expect_identical(constants$sp_replacement, 4.5)
})

testthat::test_that('n7_legs 是固定结构常量，不随会话常量漂移', {
  testthat::expect_identical(n7_legs(), 7L)
  testthat::expect_type(n7_legs(), 'integer')
  testthat::expect_identical(n7_legs(), N7_LEGS)
  # 结构层与会话可变层解耦：更新会话常量后，n7_legs() 必须纹丝不动。
  on.exit(n7_pipeline_constants(reset = TRUE), add = TRUE)
  n7_pipeline_constants(rho = -0.3, issue_budget_cny = 99)
  testthat::expect_identical(n7_legs(), 7L)
  testthat::expect_identical(n7_legs(), n7_pipeline_constants()$n_legs)
})


# --- 逐函数边界测试（inputs）-----------------------------------------------
# 每个函数按其 roxygen @param 契约逐条写用例：正常输入、边界、空/缺失、失败路径。

testthat::test_that('n7_source_csv_columns 只暴露磁盘上可出现的五张表', {
  columns <- n7_source_csv_columns()
  testthat::expect_type(columns, 'list')
  testthat::expect_setequal(names(columns),
                            c('fixtures','euro','totals','prematch_sp','match_status'))
  # settlements 绝不能在列契约里，否则磁盘源就能把赛果带进决策输入。
  testthat::expect_false('settlements' %in% names(columns))
  for (name in names(columns)) {
    testthat::expect_type(columns[[name]], 'character')
    testthat::expect_equal(anyDuplicated(columns[[name]]), 0L)
    # CSV 列必须与该表的 tibble schema 同集合（此处是同一份权威声明）。
    testthat::expect_setequal(columns[[name]], n7_table_schemas()[[name]]$columns)
  }
})

testthat::test_that('n7_parse_utc 接受 Z、+HH:MM 与 +HHMM 三种写法', {
  z <- n7_parse_utc('2026-09-23T10:00:00Z', 'kickoff_at')
  colon <- n7_parse_utc('2026-09-23T18:00:00+08:00', 'kickoff_at')
  nocolon <- n7_parse_utc('2026-09-23T18:00:00+0800', 'kickoff_at')
  testthat::expect_s3_class(z, 'POSIXct')
  testthat::expect_identical(attr(z, 'tzone'), 'UTC')
  # 三种写法指向同一时刻，归一化必须让它们完全相等。
  testthat::expect_identical(z, colon)
  testthat::expect_identical(z, nocolon)
  testthat::expect_identical(format(z, '%Y-%m-%d %H:%M:%S', tz = 'UTC'),
                             '2026-09-23 10:00:00')
})

testthat::test_that('n7_parse_utc 拒绝裸时间戳而非假定 UTC', {
  testthat::expect_error(n7_parse_utc('2026-09-23T10:00:00', 'kickoff_at'),
                         'must carry an explicit UTC offset')
  testthat::expect_error(n7_parse_utc('2026-09-23', 'kickoff_at'),
                         'must carry an explicit UTC offset')
  testthat::expect_error(n7_parse_utc('2026-09-23 10:00:00', 'kickoff_at'),
                         'must carry an explicit UTC offset')
})

testthat::test_that('n7_parse_utc 拒绝 NA、非字符非 POSIXct 与不可解析值', {
  testthat::expect_error(n7_parse_utc(NA_character_, 'kickoff_at'), 'must not be NA')
  testthat::expect_error(n7_parse_utc(c('2026-09-23T10:00:00Z', NA), 'kickoff_at'),
                         'must not be NA')
  testthat::expect_error(n7_parse_utc(20260923, 'kickoff_at'), 'must be character or POSIXct')
  testthat::expect_error(n7_parse_utc(list(1), 'kickoff_at'), 'must be character or POSIXct')
  # 带偏移但不是合法时间，必须报解析失败而不是静默 NA。
  testthat::expect_error(n7_parse_utc('2026-13-45T99:99:99Z', 'kickoff_at'),
                         'not a parseable UTC instant')
})

testthat::test_that('n7_parse_utc 处理零长度与 POSIXct 输入', {
  testthat::expect_length(n7_parse_utc(character(0), 'kickoff_at'), 0L)
  utc <- as.POSIXct('2026-09-23 10:00:00', tz = 'UTC')
  testthat::expect_identical(n7_parse_utc(utc, 'kickoff_at'), utc)
  # 非 UTC 的 POSIXct 必须被转换到同一时刻，而不是当作墙钟时间。
  shanghai <- as.POSIXct('2026-09-23 18:00:00', tz = 'Asia/Shanghai')
  converted <- n7_parse_utc(shanghai, 'kickoff_at')
  testthat::expect_identical(attr(converted, 'tzone'), 'UTC')
  testthat::expect_identical(as.numeric(converted), as.numeric(shanghai))
})

testthat::test_that('n7_parse_utc 的 what 标签本身必须合法', {
  testthat::expect_error(n7_parse_utc('2026-09-23T10:00:00Z', NA), 'single non-empty label')
  testthat::expect_error(n7_parse_utc('2026-09-23T10:00:00Z', ''), 'single non-empty label')
  testthat::expect_error(n7_parse_utc('2026-09-23T10:00:00Z', c('a','b')), 'single non-empty label')
})

testthat::test_that('n7_coerce_source_table 强制列集合完全一致', {
  good <- data.frame(issue_id = '26097', fixture_id = 'f1', slot = '5',
                     provider_id = 'p', kickoff_at = '2026-09-23T10:00:00Z',
                     handicap = '0', sale_state = 's', source_url = 'u',
                     stringsAsFactors = FALSE)
  testthat::expect_s3_class(n7_coerce_source_table(good, 'fixtures'), 'tbl_df')
  missing <- good[, setdiff(names(good), 'slot')]
  testthat::expect_error(n7_coerce_source_table(missing, 'fixtures'), 'is missing columns')
  extra <- good; extra$surprise <- 'x'
  testthat::expect_error(n7_coerce_source_table(extra, 'fixtures'), 'unexpected columns')
  testthat::expect_error(n7_coerce_source_table(list(), 'fixtures'), 'must be a data frame')
})

testthat::test_that('n7_coerce_source_table 按 schema 转换列类型', {
  good <- data.frame(issue_id = '26097', fixture_id = 'f1', slot = '5',
                     provider_id = 'p', kickoff_at = '2026-09-23T10:00:00Z',
                     handicap = '0', sale_state = 's', source_url = 'u',
                     stringsAsFactors = FALSE)
  out <- n7_coerce_source_table(good, 'fixtures')
  testthat::expect_identical(names(out), n7_table_schemas()$fixtures$columns)
  testthat::expect_identical(typeof(out$slot), 'integer')
  testthat::expect_identical(typeof(out$handicap), 'integer')
  testthat::expect_identical(typeof(out$issue_id), 'character')
  testthat::expect_s3_class(out$kickoff_at, 'POSIXct')
  testthat::expect_identical(attr(out$kickoff_at, 'tzone'), 'UTC')
  # 结果必须能通过 schema 校验，否则转换就没完成。
  testthat::expect_silent(n7_validate_table(out, 'fixtures'))
})

testthat::test_that('n7_coerce_source_table 拒绝非整数与非数值内容', {
  base <- data.frame(issue_id = '26097', fixture_id = 'f1', slot = '5',
                     provider_id = 'p', kickoff_at = '2026-09-23T10:00:00Z',
                     handicap = '0', sale_state = 's', source_url = 'u',
                     stringsAsFactors = FALSE)
  fractional <- base; fractional$slot <- '5.5'
  testthat::expect_error(n7_coerce_source_table(fractional, 'fixtures'), 'must be whole numbers')
  nonnumeric <- base; nonnumeric$slot <- 'abc'
  testthat::expect_error(n7_coerce_source_table(nonnumeric, 'fixtures'), 'must be integer')
  bad_time <- base; bad_time$kickoff_at <- '2026-09-23 10:00:00'
  testthat::expect_error(n7_coerce_source_table(bad_time, 'fixtures'),
                         'must carry an explicit UTC offset')
})

testthat::test_that('n7_coerce_source_table 在整数超范围时报错而非静默产出 NA', {
  # 回归：此前 as.integer() 只发 warning 并在数据边界存入 NA。
  base <- data.frame(issue_id = '26097', fixture_id = 'f1', slot = '3000000000',
                     provider_id = 'p', kickoff_at = '2026-09-23T10:00:00Z',
                     handicap = '0', sale_state = 's', source_url = 'u',
                     stringsAsFactors = FALSE)
  testthat::expect_error(n7_coerce_source_table(base, 'fixtures'),
                         'exceeds the integer range')
  result <- tryCatch(n7_coerce_source_table(base, 'fixtures'),
                     error = function(e) 'errored', warning = function(w) 'warned')
  testthat::expect_identical(result, 'errored')
})

testthat::test_that('n7_coerce_source_table 对 0 行返回 typed-empty', {
  empty <- data.frame(issue_id = character(0), fixture_id = character(0),
                      slot = character(0), provider_id = character(0),
                      kickoff_at = character(0), handicap = character(0),
                      sale_state = character(0), source_url = character(0),
                      stringsAsFactors = FALSE)
  out <- n7_coerce_source_table(empty, 'fixtures')
  testthat::expect_equal(nrow(out), 0L)
  testthat::expect_identical(names(out), n7_table_schemas()$fixtures$columns)
  testthat::expect_identical(typeof(out$slot), 'integer')
})

testthat::test_that('n7_normalise_outcome 接受 W/D/L 并原样返回', {
  testthat::expect_identical(n7_normalise_outcome(c('W','D','L')), c('W','D','L'))
  testthat::expect_identical(n7_normalise_outcome('W'), 'W')
  testthat::expect_identical(n7_normalise_outcome(character(0)), character(0))
})

testthat::test_that('n7_normalise_outcome 拒绝小写、其它取值与非字符', {
  # 标签比较区分大小写：小写不是合法赛果，不得被悄悄接受。
  testthat::expect_error(n7_normalise_outcome(c('w','d','l')), 'must be one of W, D, L')
  testthat::expect_error(n7_normalise_outcome('X'), 'must be one of W, D, L')
  testthat::expect_error(n7_normalise_outcome('WIN'), 'must be one of W, D, L')
  testthat::expect_error(n7_normalise_outcome(1), 'must be character')
  testthat::expect_error(n7_normalise_outcome(c('W', NA)), 'must not be NA')
  testthat::expect_error(n7_normalise_outcome(NA_character_), 'must not be NA')
})

testthat::test_that('n7_normalise_outcome 的 what 标签本身必须合法', {
  testthat::expect_error(n7_normalise_outcome('W', what = NA), 'single non-empty label')
  testthat::expect_error(n7_normalise_outcome('W', what = ''), 'single non-empty label')
  testthat::expect_error(n7_normalise_outcome('W', what = c('a','b')), 'single non-empty label')
})

testthat::test_that('n7_read_fixture_source 拒绝非 list、缺 kind 与未知 kind', {
  testthat::expect_error(n7_read_fixture_source(NULL), 'source must be a list')
  testthat::expect_error(n7_read_fixture_source('x'), 'source must be a list')
  # fixed = TRUE: the message contains $, a regex metacharacter.
  testthat::expect_error(n7_read_fixture_source(list()), 'source$kind is required',
                         fixed = TRUE)
  testthat::expect_error(n7_read_fixture_source(list(kind = NA)), 'unsupported source$kind',
                         fixed = TRUE)
  testthat::expect_error(n7_read_fixture_source(list(kind = 'no_such_kind')),
                         'unsupported source$kind', fixed = TRUE)
})

testthat::test_that('n7_read_fixture_source 拒绝一切网络源', {
  testthat::expect_error(n7_read_fixture_source(list(kind = 'http', path = 'http://x')),
                         'network sources are not permitted')
  testthat::expect_error(n7_read_fixture_source(list(kind = 'url', path = 'https://x')),
                         'network sources are not permitted')
})

testthat::test_that('n7_read_fixture_source 的 frames 分支要求 tables 是 list', {
  testthat::expect_error(n7_read_fixture_source(list(kind = 'frames')),
                         'source$tables must be a list', fixed = TRUE)
  testthat::expect_error(n7_read_fixture_source(list(kind = 'frames', tables = 1)),
                         'source$tables must be a list', fixed = TRUE)
  # 显式空状态台账合法；缺失台账另有拒绝测试。
  out <- n7_read_fixture_source(n7_empty_frames())
  testthat::expect_setequal(names(out), names(n7_source_csv_columns()))
  for (name in names(out)) {
    testthat::expect_equal(nrow(out[[name]]), 0L)
    testthat::expect_silent(n7_validate_table(out[[name]], name))
  }
})

testthat::test_that('n7_read_fixture_source 的 csv_dir 分支要求目录存在', {
  testthat::expect_error(n7_read_fixture_source(list(kind = 'csv_dir')),
                         'must be an existing directory')
  testthat::expect_error(n7_read_fixture_source(list(kind = 'csv_dir', path = '/no/such/dir')),
                         'must be an existing directory')
  testthat::expect_error(n7_read_fixture_source(list(kind = 'csv_dir', path = c('a','b'))),
                         'must be an existing directory')
})

testthat::test_that('n7_read_inputs 校验 issue_ids 且不再接受 cutoff', {
  source <- n7_empty_frames()
  testthat::expect_error(n7_read_inputs(source, 26097), 'must be character')
  testthat::expect_error(n7_read_inputs(source, NA_character_), 'must not be NA')
  testthat::expect_error(n7_read_inputs(source, ''), 'must not be empty')
  testthat::expect_error(n7_read_inputs(source, ' 26097'), 'must not be padded')
  # 读取是整期的：接口不再有 cutoff 形参，多余的实参一律报错而不是被忽略。
  testthat::expect_error(n7_read_inputs(source, '26097', list(issue_id = '26097')),
                         'unused argument')
})

testthat::test_that('n7_read_inputs 在 frames 源缺少 match_status 表时报错', {
  # 缺表是输入契约错误：把"源里没有这张表"读成"没有可见状态"会让一期比赛
  # 因为一个读取缺陷而被静默排除，因此绝不回退成 typed-empty。
  source <- list(kind = 'frames', tables = list())
  testthat::expect_error(n7_read_inputs(source, '26097'),
                         'has no match_status table')
  # 显式给一张零行表则合法，表达"确实没有任何可见报告"。
  explicit <- list(kind = 'frames',
                   tables = list(match_status = n7_typed_empty('match_status')))
  testthat::expect_silent(n7_read_inputs(explicit, '26097'))
})

testthat::test_that('n7_read_inputs 返回五张表且永不含 settlements', {
  result <- n7_read_inputs(n7_empty_frames(), '26097')
  testthat::expect_setequal(names(result),
                            c('fixtures','euro','totals','prematch_sp','match_status'))
  testthat::expect_false('settlements' %in% names(result))
  for (name in names(result)) {
    testthat::expect_s3_class(result[[name]], 'tbl_df')
  }
})

testthat::test_that('n7_read_inputs 按 issue_ids 过滤 fixtures 并按 fixture 过滤依赖表', {
  fixtures <- data.frame(
    issue_id = c('26097','26097','26098'),
    fixture_id = c('f1','f2','f3'), slot = c('1','2','3'), provider_id = 'p',
    kickoff_at = '2026-09-23T10:00:00Z', handicap = '0', sale_state = 's',
    source_url = 'u', stringsAsFactors = FALSE)
  euro <- data.frame(
    fixture_id = c('f1','f2','f3'), company_id = 'c1',
    quote_at = '2026-09-23T09:00:00Z', odds_home = '2.0', odds_draw = '3.0',
    odds_away = '4.0', source_url = 'u', stringsAsFactors = FALSE)
  ledger <- data.frame(
    issue_id = c('26097','26098'), fixture_id = c('f1','f3'), status = 'scheduled',
    status_at = '2026-09-22T08:00:00Z', available_at = '2026-09-22T08:00:00Z',
    source_url = 'u', stringsAsFactors = FALSE)
  source <- list(kind = 'frames',
                 tables = list(fixtures = fixtures, euro = euro, match_status = ledger))
  result <- n7_read_inputs(source, '26097')
  # 只保留属于被请求期号的 fixtures。
  testthat::expect_setequal(result$fixtures$fixture_id, c('f1','f2'))
  testthat::expect_true(all(result$fixtures$issue_id == '26097'))
  # 依赖表按保留下来的 fixture_id 过滤，f3 必须被剔除。
  testthat::expect_setequal(result$euro$fixture_id, c('f1','f2'))
  # 台账按复合键 (issue_id, fixture_id) 过滤：26098 的行不随 fixture_id 撞号进来。
  testthat::expect_setequal(result$match_status$issue_id, '26097')
})

testthat::test_that('n7_read_inputs 在过滤之前、对着完整 fixtures 校验台账关系键', {
  # 一条指向根本不存在的比赛的台账行，无论它属于哪一期，都必须在输入边界报错，
  # 而不是在过滤后因为"没匹配上"被静默丢弃。
  fixtures <- data.frame(
    issue_id = '26097', fixture_id = 'f1', slot = '1', provider_id = 'p',
    kickoff_at = '2026-09-23T10:00:00Z', handicap = '0', sale_state = 's',
    source_url = 'u', stringsAsFactors = FALSE)
  ledger <- data.frame(
    issue_id = '26098', fixture_id = 'ghost', status = 'scheduled',
    status_at = '2026-09-22T08:00:00Z', available_at = '2026-09-22T08:00:00Z',
    source_url = 'u', stringsAsFactors = FALSE)
  source <- list(kind = 'frames',
                 tables = list(fixtures = fixtures, match_status = ledger))
  testthat::expect_error(n7_read_inputs(source, '26097'),
                         'not in fixtures')
})

testthat::test_that('n7_read_inputs 在期号无匹配时返回全部 typed-empty', {
  fixtures <- data.frame(
    issue_id = '26097', fixture_id = 'f1', slot = '1', provider_id = 'p',
    kickoff_at = '2026-09-23T10:00:00Z', handicap = '0', sale_state = 's',
    source_url = 'u', stringsAsFactors = FALSE)
  euro <- data.frame(
    fixture_id = 'f1', company_id = 'c1', quote_at = '2026-09-23T09:00:00Z',
    odds_home = '2.0', odds_draw = '3.0', odds_away = '4.0', source_url = 'u',
    stringsAsFactors = FALSE)
  ledger <- data.frame(
    issue_id = '26097', fixture_id = 'f1', status = 'scheduled',
    status_at = '2026-09-22T08:00:00Z', available_at = '2026-09-22T08:00:00Z',
    source_url = 'u', stringsAsFactors = FALSE)
  source <- list(kind = 'frames',
                 tables = list(fixtures = fixtures, euro = euro, match_status = ledger))
  result <- n7_read_inputs(source, '26098')
  for (name in names(result)) {
    testthat::expect_equal(nrow(result[[name]]), 0L)
    # 空结果仍必须带完整列集合，否则下游无法无差别 rbind。
    testthat::expect_identical(names(result[[name]]), n7_table_schemas()[[name]]$columns)
  }
})

testthat::test_that('n7_read_inputs 对 fixtures 强制 (issue_id, fixture_id) 唯一键', {
  duplicated_rows <- data.frame(
    issue_id = '26097', fixture_id = c('f1','f1'), slot = c('1','2'), provider_id = 'p',
    kickoff_at = '2026-09-23T10:00:00Z', handicap = '0', sale_state = 's',
    source_url = 'u', stringsAsFactors = FALSE)
  source <- list(kind = 'frames',
                 tables = list(fixtures = duplicated_rows,
                               match_status = n7_typed_empty('match_status')))
  testthat::expect_error(n7_read_inputs(source, '26097'), 'duplicate key')
})

# --- 逐函数边界测试（fixture）----------------------------------------------
# 夹具是所有下游测试的基准：夹具错了会污染每一个断言，因此这里必须详尽。

testthat::test_that('n7_fixture_source_url 产出带 synthetic:// 前缀的标记', {
  url <- n7_fixture_source_url('fixture', '26097_001')
  testthat::expect_type(url, 'character')
  testthat::expect_length(url, 1L)
  testthat::expect_identical(url, 'synthetic://n7-pipeline/fixture/26097_001')
  # 前缀固定：下游靠它一眼分辨合成与实测。
  testthat::expect_match(url, '^synthetic://', fixed = FALSE)
})

testthat::test_that('n7_fixture_source_url 对 key 向量化', {
  urls <- n7_fixture_source_url('euro', c('a', 'b', 'c'))
  testthat::expect_length(urls, 3L)
  testthat::expect_identical(urls[1], 'synthetic://n7-pipeline/euro/a')
  testthat::expect_identical(urls[3], 'synthetic://n7-pipeline/euro/c')
})

testthat::test_that('n7_fixture_source_url 拒绝非法 kind 与 key', {
  testthat::expect_error(n7_fixture_source_url(NA, 'k'), 'kind must be one non-empty label')
  testthat::expect_error(n7_fixture_source_url('', 'k'), 'kind must be one non-empty label')
  testthat::expect_error(n7_fixture_source_url(c('a','b'), 'k'), 'kind must be one non-empty label')
  testthat::expect_error(n7_fixture_source_url('fixture', NA), 'key must be non-empty')
  testthat::expect_error(n7_fixture_source_url('fixture', ''), 'key must be non-empty')
  testthat::expect_error(n7_fixture_source_url('fixture', character(0)), 'key must be non-empty')
  testthat::expect_error(n7_fixture_source_url('fixture', 1), 'key must be non-empty')
  testthat::expect_error(n7_fixture_source_url('fixture', c('a', NA)), 'key must be non-empty')
})

testthat::test_that('n7_make_fixture_issue 产出自洽的五张表与 truth 矩阵', {
  issue <- n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 5L),
                                 n_companies = 2L)
  testthat::expect_setequal(names(issue),
                            c('fixtures','euro','totals','prematch_sp','match_status','truth'))
  testthat::expect_equal(nrow(issue$match_status), 5L)
  testthat::expect_equal(nrow(issue$fixtures), 5L)
  testthat::expect_equal(nrow(issue$euro), 5L * 2L)
  testthat::expect_equal(nrow(issue$totals), 5L * 2L * 2L)
  testthat::expect_equal(nrow(issue$prematch_sp), 5L * 3L)
  testthat::expect_equal(dim(issue$truth), c(5L, 3L))
  testthat::expect_identical(colnames(issue$truth), n7_outcomes())
  testthat::expect_identical(rownames(issue$truth), issue$fixtures$fixture_id)
  # 四张表都必须通过各自的 schema 校验。
  for (name in c('fixtures','euro','totals','prematch_sp')) {
    testthat::expect_silent(n7_validate_table(issue[[name]], name))
  }
})

testthat::test_that('n7_make_fixture_issue 的概率三元组和为 1 且赔率自洽', {
  issue <- n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 4L),
                                 n_companies = 3L, margin = 1.06)
  testthat::expect_equal(unname(rowSums(issue$truth)), rep(1, 4L), tolerance = 1e-12)
  testthat::expect_silent(n7_check_probability_sum(issue$truth))
  # 赔率按 margin 加水位，因此隐含概率之和必须精确等于 margin。这是真正
  # 可从赔率还原的不变量。
  euro <- issue$euro[issue$euro$company_id == 'c01', ]
  euro <- euro[match(issue$fixtures$fixture_id, euro$fixture_id), ]
  implied <- 1 / cbind(euro$odds_home, euro$odds_draw, euro$odds_away)
  testthat::expect_equal(unname(rowSums(implied)), rep(1.06, 4L), tolerance = 1e-12)
  # 去水还原的是每家公司各自的 noisy 三元组，不是 truth：赔率由 noisy 定价，
  # truth 只是它的中心。此处只断言去水结果是一个合法概率三元组。
  devigged <- implied / rowSums(implied)
  testthat::expect_silent(n7_check_probability_sum(devigged))
  testthat::expect_equal(unname(rowSums(devigged)), rep(1, 4L), tolerance = 1e-12)
  # truth 与去水结果应当接近（同一中心），但不得被断言为相等。
  testthat::expect_lt(max(abs(devigged - unname(issue$truth))), 0.05)
})

testthat::test_that('n7_make_fixture_issue 是确定性的：同 seed 同结果', {
  a <- n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 4L), seed = 7L)
  b <- n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 4L), seed = 7L)
  testthat::expect_identical(a$truth, b$truth)
  testthat::expect_identical(a$fixtures, b$fixtures)
  # 不同 seed 必须产出不同结果，否则 seed 参数形同虚设。
  c <- n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 4L), seed = 8L)
  testthat::expect_false(identical(a$truth, c$truth))
})

testthat::test_that('n7_make_fixture_issue 校验 kickoff_at 是显式的 UTC POSIXct 向量', {
  # 接口精化：开赛时刻由调用方显式给出，生成器不再推断决策 epoch。
  testthat::expect_error(n7_make_fixture_issue('26097', '2026-09-23'), 'must be a POSIXct')
  testthat::expect_error(n7_make_fixture_issue('26097', as.Date('2026-09-23')),
                         'must be a POSIXct')
  testthat::expect_error(n7_make_fixture_issue('26097', as.POSIXct(character(0), tz = 'UTC')),
                         'must not be empty')
  testthat::expect_error(
    n7_make_fixture_issue('26097', as.POSIXct(c('2026-09-23 04:00:00', NA), tz = 'UTC')),
    'must not be NA')
  testthat::expect_error(n7_make_fixture_issue('26097', as.POSIXct(Inf, origin = '1970-01-01', tz = 'UTC')),
                         'must be finite')
  # 多场比赛可以同时开赛；身份由独立的比赛 ID 区分。
  repeated <- as.POSIXct(rep('2026-09-23 04:00:00', 2L), tz = 'UTC')
  testthat::expect_identical(n7_make_fixture_issue('26097', repeated)$fixtures$kickoff_at, repeated)
})

testthat::test_that('n7_make_fixture_issue 从非空 kickoff_at 向量推断比赛数', {
  # 场次数由向量长度决定，不存在一个会与向量打架的 n_fixtures 形参。
  two_days <- as.POSIXct(c('2026-09-23 04:00:00', '2026-09-24 04:00:00'), tz = 'UTC')
  issue <- n7_make_fixture_issue('26097', two_days)
  testthat::expect_equal(nrow(issue$fixtures), 2L)
  testthat::expect_equal(dim(issue$truth), c(2L, 3L))
  testthat::expect_equal(nrow(issue$match_status), 2L)
  testthat::expect_identical(issue$fixtures$kickoff_at, two_days)
  # 非 UTC 的 POSIXct 保留瞬时、只改时区属性。
  shanghai <- as.POSIXct(two_days, tz = 'Asia/Shanghai')
  converted <- n7_make_fixture_issue('26097', shanghai)
  testthat::expect_identical(as.numeric(converted$fixtures$kickoff_at), as.numeric(two_days))
  testthat::expect_identical(attr(converted$fixtures$kickoff_at, 'tzone'), 'UTC')
})

testthat::test_that('n7_make_fixture_issue 校验 issue_id', {
  kicks <- n7_kickoff_window('2026-09-22', 2L)
  testthat::expect_error(n7_make_fixture_issue(26097, kicks), 'must be character')
  testthat::expect_error(n7_make_fixture_issue(NA_character_, kicks), 'must not be NA')
  testthat::expect_error(n7_make_fixture_issue('', kicks), 'must not be empty')
  # 长度 != 1 必须在此处报错，而不是崩在 tibble() 的列长检查里。
  testthat::expect_error(n7_make_fixture_issue(c('a','b'), kicks),
                         'must name exactly one issue')
})

testthat::test_that('n7_make_fixture_issue 校验 n_companies', {
  kicks <- n7_kickoff_window('2026-09-22', 2L)
  testthat::expect_error(n7_make_fixture_issue('26097', kicks, n_companies = 0L),
                         'positive whole number')
  testthat::expect_error(n7_make_fixture_issue('26097', kicks, n_companies = 2.5),
                         'positive whole number')
  testthat::expect_error(n7_make_fixture_issue('26097', kicks, n_companies = NA),
                         'positive whole number')
  # n_fixtures 已从接口移除：多余的具名实参必须报错，而不是被静默忽略。
  testthat::expect_error(n7_make_fixture_issue('26097', kicks, n_fixtures = 4L),
                         'unused argument')
})

testthat::test_that('n7_make_fixture_issue 不再接受 local_date/kickoff_hour/tz', {
  # 接口精化的另一半：决策 epoch 不属于生成器，这些形参必须彻底消失，不留兼容层。
  kicks <- n7_kickoff_window('2026-09-22', 2L)
  for (argument in c('local_date', 'kickoff_hour', 'tz')) {
    testthat::expect_error(do.call(n7_make_fixture_issue,
                                   stats::setNames(list('26097', kicks, 'x'), c('issue_id', 'kickoff_at', argument))),
                           'unused argument')
  }
})

testthat::test_that('n7_make_fixture_issue 校验 margin 为正有限值', {
  kicks <- n7_kickoff_window('2026-09-22', 2L)
  testthat::expect_error(n7_make_fixture_issue('26097', kicks, margin = 0),
                         'positive finite number')
  testthat::expect_error(n7_make_fixture_issue('26097', kicks, margin = -1),
                         'positive finite number')
  testthat::expect_error(n7_make_fixture_issue('26097', kicks, margin = NA),
                         'positive finite number')
  testthat::expect_error(n7_make_fixture_issue('26097', kicks, margin = Inf),
                         'positive finite number')
  testthat::expect_silent(n7_make_fixture_issue('26097', kicks, margin = 1.06))
})

testthat::test_that('n7_make_fixture_issue 的合成状态报告是一条显式观测', {
  kicks <- n7_kickoff_window('2026-09-22', 3L)
  issue <- n7_make_fixture_issue('26097', kicks, match_status = 'scheduled')
  testthat::expect_true(all(issue$match_status$status == 'scheduled'))
  # status_at == available_at：合成源同时报告事件与观测。
  testthat::expect_identical(issue$match_status$status_at, issue$match_status$available_at)
  # 时间与 cutoff 解耦，锚在各自的 kickoff_at - 36h 上。
  testthat::expect_identical(issue$match_status$available_at, kicks - 36 * 3600)
  # 非 scheduled 取值也合法，用于构造"决策当时已知已取消"的场景。
  cancelled <- n7_make_fixture_issue('26097', kicks, match_status = 'cancelled')
  testthat::expect_true(all(cancelled$match_status$status == 'cancelled'))
  testthat::expect_error(n7_make_fixture_issue('26097', kicks, match_status = 'nope'),
                         'must be one of')
})

testthat::test_that('n7_make_fixture_issue 校验 seed', {
  testthat::expect_error(n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 3L), seed = NA), 'finite number')
  testthat::expect_error(n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 3L), seed = Inf), 'finite number')
  testthat::expect_error(n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 3L), seed = c(1,2)), 'finite number')
})

testthat::test_that('n7_make_fixture_issue 把报价与状态锚在各自的 kickoff_at - 36h', {
  kicks <- n7_kickoff_window('2026-09-22', 3L)
  issue <- n7_make_fixture_issue('26097', kicks)
  # 报价与任何 cutoff 无关：它只相对本场开赛。公司错开是已声明的小幅偏移。
  matched_kickoff <- issue$fixtures$kickoff_at[match(issue$euro$fixture_id, issue$fixtures$fixture_id)]
  testthat::expect_true(all(issue$euro$quote_at >= matched_kickoff - 36 * 3600))
  testthat::expect_true(all(issue$euro$quote_at <= matched_kickoff - 36 * 3600 + 120))
  testthat::expect_true(all(issue$prematch_sp$quote_at == rep(kicks, each = 3L) - 36 * 3600))
  # 报价必须严格早于开赛，否则它就不是赛前信息。
  testthat::expect_true(all(issue$euro$quote_at < matched_kickoff))
})

testthat::test_that('n7_make_fixture_issue 保留跨日的同一期赛程', {
  # 多日赛程不再是生成器拼出来的：调用方给出两天，两天的比赛都留在同一期里。
  two_days <- as.POSIXct(c('2026-09-23 04:00:00', '2026-09-24 04:00:00'), tz = 'UTC')
  issue <- n7_make_fixture_issue('26097', two_days)
  days <- format(issue$fixtures$kickoff_at, '%Y-%m-%d', tz = 'UTC')
  testthat::expect_identical(unique(days), c('2026-09-23', '2026-09-24'))
  # 大期程也不得让尾部报价越过任何已声明的锚点。
  many <- n7_kickoff_window('2026-09-22', 56L, step_seconds = 0)
  big <- n7_make_fixture_issue('26097', many)
  testthat::expect_true(all(big$euro$quote_at <= many[1] - 36 * 3600 + 120))
})

testthat::test_that('n7_make_fixture_issue 的每行都带 synthetic source_url', {
  issue <- n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 3L))
  for (name in c('fixtures','euro','totals','prematch_sp')) {
    urls <- issue[[name]]$source_url
    testthat::expect_true(all(grepl('^synthetic://n7-pipeline/', urls)))
    testthat::expect_false(anyNA(urls))
  }
})

testthat::test_that('n7_make_fixture_issue 的 fixture_id 与 slot 一致且唯一', {
  issue <- n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 6L))
  testthat::expect_identical(issue$fixtures$fixture_id,
                             sprintf('26097_%03d', 1:6))
  testthat::expect_identical(issue$fixtures$slot, 1:6)
  testthat::expect_equal(anyDuplicated(issue$fixtures$fixture_id), 0L)
  testthat::expect_true(all(issue$fixtures$issue_id == '26097'))
})

testthat::test_that('n7_fixture_source 要求至少一个期', {
  testthat::expect_error(n7_fixture_source(), 'at least one issue is required')
})

testthat::test_that('n7_fixture_source 拒绝非期 list 与缺表的期', {
  issue <- n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 2L))
  testthat::expect_error(n7_fixture_source(list(a = 1)), 'is missing')
  testthat::expect_error(n7_fixture_source('x'), 'must be a generated issue list')
  incomplete <- issue; incomplete$euro <- NULL
  testthat::expect_error(n7_fixture_source(incomplete), 'is missing euro')
  # 第二个参数出错时错误信息必须点名是第几个。
  testthat::expect_error(n7_fixture_source(issue, list(a = 1)), 'argument 2')
})

testthat::test_that('n7_fixture_source 包装单期与多期', {
  one <- n7_make_fixture_issue('26097', n7_kickoff_window('2026-09-22', 3L), seed = 1L)
  source <- n7_fixture_source(one)
  testthat::expect_identical(source$kind, 'frames')
  testthat::expect_setequal(names(source$tables),
                            c('fixtures','euro','totals','prematch_sp','match_status'))
  testthat::expect_equal(nrow(source$tables$fixtures), 3L)
  # 多期：同名表纵向合并，期号由 issue_id 携带。
  two <- n7_make_fixture_issue('26098', n7_kickoff_window('2026-09-22', 4L), seed = 2L)
  source2 <- n7_fixture_source(one, two)
  testthat::expect_equal(nrow(source2$tables$fixtures), 7L)
  testthat::expect_setequal(unique(source2$tables$fixtures$issue_id),
                            c('26097','26098'))
})
