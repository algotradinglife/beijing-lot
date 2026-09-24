# --- S7 领域类型（n7_pipeline_types.R）--------------------------------------
# 这些类型是管道内部对象：对外接口仍是 tibble，跨模块传递必须先转回 tibble。

sp_row <- function(...) {
  base <- list(fixture_id = 'f1', outcome = 'W',
               quote_at = as.POSIXct('2026-09-22 08:00:00', tz = 'UTC'),
               sp_raw = 3.04, source_url = 'synthetic://x')
  tibble::as_tibble(utils::modifyList(base, list(...)))
}

testthat::test_that('N7SpQuote 在构造时校验每一条契约', {
  make <- function(...) {
    base <- list(fixture_id = 'f1', outcome = 'W', sp_raw = 3.04,
                 quote_at = as.POSIXct('2026-09-22 08:00:00', tz = 'UTC'),
                 source_url = 'synthetic://x')
    do.call(n7_sp_quote_class, utils::modifyList(base, list(...)))
  }
  testthat::expect_true(S7::S7_inherits(make(), n7_sp_quote_class))
  testthat::expect_error(make(fixture_id = NA_character_), 'fixture_id')
  testthat::expect_error(make(fixture_id = ''), 'fixture_id')
  testthat::expect_error(make(fixture_id = c('a', 'b')), 'fixture_id')
  testthat::expect_error(make(outcome = 'X'), 'W, D, L')
  testthat::expect_error(make(outcome = NA_character_), 'W, D, L')
  testthat::expect_error(make(outcome = c('W', 'D')), 'W, D, L')
  # 水位等于 1 已退化，不是有效赔率。
  testthat::expect_error(make(sp_raw = 1), 'above 1')
  testthat::expect_error(make(sp_raw = 0.5), 'above 1')
  testthat::expect_error(make(sp_raw = NA_real_), 'sp_raw')
  testthat::expect_error(make(sp_raw = Inf), 'sp_raw')
  testthat::expect_error(make(sp_raw = c(3, 4)), 'sp_raw')
  testthat::expect_error(make(quote_at = as.POSIXct(NA)), 'quote_at')
  testthat::expect_error(make(quote_at = '2026-09-22'), 'quote_at')
  testthat::expect_error(make(source_url = ''), 'source_url')
  testthat::expect_error(make(source_url = NA_character_), 'source_url')
})

testthat::test_that('N7SpQuote 的非法赋值被拒绝且原对象不变', {
  quote <- n7_sp_quote_from_row(sp_row())
  testthat::expect_error(quote@sp_raw <- -1, 'above 1')
  # 关键性质：校验失败时对象未被破坏，不会留下半个非法状态。
  testthat::expect_equal(quote@sp_raw, 3.04)
  quote@sp_raw <- 5
  testthat::expect_equal(quote@sp_raw, 5)
  testthat::expect_error(quote@outcome <- 'X', 'W, D, L')
  testthat::expect_equal(quote@outcome, 'W')
})

testthat::test_that('n7_sp_quote_from_row 要求恰好一行与全部列', {
  # 缺列必须报错：若用 $ 取值，缺列只得到 NULL 并静默构造空字段报价。
  testthat::expect_error(n7_sp_quote_from_row(sp_row()[names(sp_row()) != 'sp_raw']),
                         'missing sp_raw')
  testthat::expect_error(n7_sp_quote_from_row(n7_typed_empty('prematch_sp')),
                         'exactly one row')
  # 两行先被 checkmate 的 max.rows 拦住，零行才走到本函数自己的措辞。
  two <- rbind(sp_row(), sp_row())
  testthat::expect_error(n7_sp_quote_from_row(two), 'at most 1 rows|exactly one row')
  testthat::expect_error(n7_sp_quote_from_row(list()), 'row')
  # 列值非法由 validator 报出，错误信息说明违反哪条规则。
  testthat::expect_error(n7_sp_quote_from_row(sp_row(sp_raw = -1)), 'above 1')
  testthat::expect_error(n7_sp_quote_from_row(sp_row(outcome = 'Z')), 'W, D, L')
})

testthat::test_that('n7_sp_quotes_to_tibble 空输入返回 typed-empty 表', {
  empty <- n7_sp_quotes_to_tibble(list())
  testthat::expect_equal(nrow(empty), 0L)
  # 必须与契约的 typed-empty 完全一致，否则 bind_rows 会列序错位。
  testthat::expect_identical(empty, n7_typed_empty('prematch_sp'))
})

testthat::test_that('n7_sp_quotes_to_tibble 拒绝非 N7SpQuote 元素并点名下标', {
  quote <- n7_sp_quote_from_row(sp_row())
  testthat::expect_error(n7_sp_quotes_to_tibble(list(1)), 'element 1')
  testthat::expect_error(n7_sp_quotes_to_tibble(list(quote, 42)), 'element 2')
  testthat::expect_error(n7_sp_quotes_to_tibble('not a list'), 'quotes')
})

testthat::test_that('tibble 与 N7SpQuote 的往返是无损的', {
  table <- tibble::tibble(
    fixture_id = c('f1', 'f2'),
    outcome    = c('W', 'L'),
    quote_at   = as.POSIXct(c('2026-09-22 08:00:00', '2026-09-22 08:05:00'), tz = 'UTC'),
    sp_raw     = c(3.04, 1.78),
    source_url = c('u1', 'u2'))
  quotes <- lapply(seq_len(nrow(table)), function(i) {
    n7_sp_quote_from_row(table[i, , drop = FALSE])
  })
  back <- n7_sp_quotes_to_tibble(quotes)
  # 无损往返是这套类型的核心保证：列序、类型、时区都必须一致。
  testthat::expect_identical(back, table)
  testthat::expect_identical(attr(back$quote_at, 'tzone'), 'UTC')
  # 往返结果必须能被契约校验接受，否则它在管道里是不可用的。
  testthat::expect_silent(n7_validate_table(back, 'prematch_sp'))
})

# --- S7 表级类型（N7DomainTable）--------------------------------------------
# 逐行类型挡「一条记录非法」；表级类型挡「一张表与它自己的契约不符」。
# value 层多数缺陷属于后者，因此列序错位必须在这里被拦住。

testthat::test_that('N7DomainTable 校验已声明域的列集合与列序', {
  empty <- n7_typed_empty('prematch_sp')
  testthat::expect_true(S7::S7_inherits(
    n7_domain_table(empty, 'prematch_sp'), n7_domain_table_class))
  # 列序错位是最危险的静默错误：值会被赋到错误的列上。
  reordered <- empty[, c('outcome', 'fixture_id', 'quote_at', 'sp_raw', 'source_url')]
  testthat::expect_error(n7_domain_table(reordered, 'prematch_sp'), 'must have columns')
  testthat::expect_error(n7_domain_table(empty[, 1:4], 'prematch_sp'), 'must have columns')
  extended <- cbind(empty, extra = character(0))
  testthat::expect_error(n7_domain_table(extended, 'prematch_sp'), 'must have columns')
})

testthat::test_that('N7DomainTable 对已声明与未声明的域区别对待', {
  # ranked / candidate_tickets 原为值层内部表、无 schema 声明，属契约缺口；
  # 现已声明，因此它们的列集合与列序同样受本类型管辖。
  testthat::expect_true(S7::S7_inherits(
    n7_domain_table(n7_typed_empty('ranked'), 'ranked'), n7_domain_table_class))
  testthat::expect_true(S7::S7_inherits(
    n7_domain_table(n7_typed_empty('candidate_tickets'), 'candidate_tickets'),
    n7_domain_table_class))
  # 已声明的域必须列序正确，否则报错。
  testthat::expect_error(
    n7_domain_table(tibble::tibble(a = 1), 'ranked'), 'must have columns')
  testthat::expect_error(
    n7_domain_table(tibble::tibble(ticket_id = character(0),
                                   candidate_id = character(0)),
                    'candidate_tickets'), 'must have columns')
  # 真正未声明的域才只要求是 data.frame。
  testthat::expect_true(S7::S7_inherits(
    n7_domain_table(tibble::tibble(a = 1), 'not_a_declared_domain'),
    n7_domain_table_class))
})

testthat::test_that('N7DomainTable 拒绝非 data.frame 与非法 domain', {
  empty <- n7_typed_empty('prematch_sp')
  testthat::expect_error(n7_domain_table(list(), 'prematch_sp'), 'data.frame')
  testthat::expect_error(n7_domain_table(NULL, 'prematch_sp'), 'data.frame')
  testthat::expect_error(n7_domain_table(1:3, 'prematch_sp'), 'data.frame')
  testthat::expect_error(n7_domain_table(empty, NA_character_), 'domain')
  testthat::expect_error(n7_domain_table(empty, ''), 'domain')
  testthat::expect_error(n7_domain_table(empty, c('a', 'b')), 'domain')
  testthat::expect_error(n7_domain_table(empty, 1), 'domain')
})

testthat::test_that('N7DomainTable 的列序违规赋值被拒绝且原对象不变', {
  object <- n7_domain_table(n7_typed_empty('prematch_sp'), 'prematch_sp')
  testthat::expect_error(object@table <- tibble::tibble(a = 1), 'must have columns')
  testthat::expect_equal(ncol(object@table), 5L)
})

testthat::test_that('n7_domain_table_data 只接受 N7DomainTable 并原样返回', {
  table <- tibble::tibble(
    fixture_id = c('f1', 'f2'),
    outcome    = c('W', 'L'),
    quote_at   = as.POSIXct(c('2026-09-22 08:00:00', '2026-09-22 08:05:00'), tz = 'UTC'),
    sp_raw     = c(3.04, 1.78),
    source_url = c('u1', 'u2'))
  object <- n7_domain_table(table, 'prematch_sp')
  testthat::expect_identical(n7_domain_table_data(object), table)
  testthat::expect_identical(attr(n7_domain_table_data(object)$quote_at, 'tzone'), 'UTC')
  # 出口必须返回 tibble，否则违反 AGENTS.md 的表契约。
  testthat::expect_s3_class(n7_domain_table_data(object), 'tbl_df')
  testthat::expect_error(n7_domain_table_data(table), 'N7DomainTable')
  testthat::expect_error(n7_domain_table_data(NULL), 'N7DomainTable')
})

testthat::test_that('N7DomainTable 与 dplyr 互操作，且重装箱后仍受校验', {
  table <- tibble::tibble(
    fixture_id = c('f1', 'f2', 'f1'),
    outcome    = c('W', 'L', 'D'),
    quote_at   = as.POSIXct(c('2026-09-22 08:00:00', '2026-09-22 08:05:00',
                              '2026-09-22 08:10:00'), tz = 'UTC'),
    sp_raw     = c(3.04, 1.78, 3.17),
    source_url = c('u1', 'u2', 'u3'))
  inner <- n7_domain_table_data(n7_domain_table(table, 'prematch_sp'))
  # dplyr 必须能在内层表上原样工作，否则这套类型会让代码更啰嗦而不是更安全。
  testthat::expect_equal(nrow(dplyr::filter(inner, sp_raw > 2)), 2L)
  testthat::expect_equal(dplyr::arrange(inner, dplyr::desc(sp_raw))$sp_raw[1], 3.17)
  testthat::expect_equal(nrow(dplyr::mutate(inner, ev = sp_raw * 0.65)), 3L)
  testthat::expect_equal(nrow(dplyr::slice(inner, 1L)), 1L)
  # 经 dplyr 处理后重新装箱仍然合法。
  filtered <- dplyr::filter(inner, sp_raw > 2)
  testthat::expect_equal(nrow(n7_domain_table(filtered, 'prematch_sp')@table), 2L)
  # 但 select() 造成的列序错位必须在重装箱时被抓到。
  reordered <- dplyr::select(inner, outcome, fixture_id, quote_at, sp_raw, source_url)
  testthat::expect_error(n7_domain_table(reordered, 'prematch_sp'), 'must have columns')
})


testthat::test_that('S7 domain helpers stay outside the public package API', {
  exports <- getNamespaceExports('beidan')
  testthat::expect_false(any(c('n7_sp_quote_class', 'n7_domain_table_class',
    'n7_sp_quote_from_row', 'n7_sp_quotes_to_tibble', 'n7_domain_table',
    'n7_domain_table_data') %in% exports))
})
