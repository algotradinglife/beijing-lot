#' N7 管道：内部领域类型（S7）
#'
#' 本文件定义管道**内部**使用的领域对象。它们只用于在构造时就把非法状态挡在门外，
#' 不构成对外接口：对所有调用方，输入仍是 tibble，输出仍是 tibble（AGENTS.md：
#' 所有 R 分析表必须用 tibble）。
#'
#' @details 为什么需要 S7：本管道的许多缺陷属于「非法状态在构造时就已存在，却直到
#'   下游某个函数才暴露」。实测例子：NA 的 score 静默产出 "NA" 组标识、非数值输入
#'   静默产出 NaN、超范围 as.integer() 静默产出 NA。参数判定（checkmate）能挡住
#'   传参错误，但挡不住**对象自身**在多次赋值后进入非法状态。S7 的 validator 在
#'   构造时与每次属性赋值时都会重跑，且赋值失败时原对象保持不变。
#'
#' S7 对象不得出现在模块的公开返回结构中；跨模块传递一律先转回 tibble。
#' 一条赛前 SP 报价
#'
#' @param fixture_id 长度 1 的非空字符串。
#' @param outcome    长度 1 的 "W"/"D"/"L"。
#' @param sp_raw     长度 1 的数值，必须 > 1（水位不能退化为 1 或更低）。
#' @param quote_at   长度 1 的 POSIXct，报价采集时点，不得为 NA。
#' @param source_url 长度 1 的非空字符串，报价来源。
#'
#' @return 一个 MatchSpQuote 对象。
#'
#' @details 校验在**构造时**与**每次属性赋值时**执行；校验失败时原对象保持不变。
#'   这样「一条 SP 报价」在整个生命周期内都不可能处于非法状态，下游函数因此不必
#'   重复判断 sp_raw 是否为正、outcome 是否为 W/D/L。
#'
#'   注意：时区不做强制。报价时点的**是否早于 cutoff** 由使用方按契约判断
#'   （见 match_latest_quote_before），本类型只保证它是个真实时刻。
#' @usage NULL
match_sp_quote_class <- S7::new_class(
  "MatchSpQuote",
  properties = list(
    fixture_id = S7::class_character,
    outcome    = S7::class_character,
    sp_raw     = S7::class_numeric,
    quote_at   = S7::class_POSIXct,
    source_url = S7::class_character
  ),
  validator = function(self) {
    problems <- character(0)
    if (length(self@fixture_id) != 1L || is.na(self@fixture_id) ||
        !nzchar(self@fixture_id)) {
      problems <- c(problems, "fixture_id must be one non-empty string")
    }
    if (length(self@outcome) != 1L || is.na(self@outcome) ||
        !self@outcome %in% match_outcomes()) {
      problems <- c(problems, "outcome must be one of W, D, L")
    }
    if (length(self@sp_raw) != 1L || is.na(self@sp_raw) ||
        !is.finite(self@sp_raw) || self@sp_raw <= 1) {
      problems <- c(problems, "sp_raw must be one finite number above 1")
    }
    if (length(self@quote_at) != 1L || is.na(self@quote_at)) {
      problems <- c(problems, "quote_at must be one non-missing instant")
    }
    if (length(self@source_url) != 1L || is.na(self@source_url) ||
        !nzchar(self@source_url)) {
      problems <- c(problems, "source_url must be one non-empty string")
    }
    if (length(problems)) problems else NULL
  }
)
#' 把 prematch_sp 表的一行转为 MatchSpQuote
#'
#' @param row 长度为 1 的 list 或一行 data.frame，须含 prematch_sp 的全部列：
#'   fixture_id, outcome, quote_at, sp_raw, source_url。
#'   · 缺列      -> stop()（列出缺失的列名）
#'   · 列值非法  -> 由 MatchSpQuote 的 validator 报错，错误信息说明违反哪条规则
#' @return 一个 MatchSpQuote 对象。
#' @details 这是 tibble 与领域类型之间的唯一入口。缺列必须显式报错：若用 $ 取值，
#'   缺列只会得到 NULL 并静默构造出一个字段为空的报价。
match_sp_quote_from_row <- function(row) {
  checkmate::assert_data_frame(row, max.rows = 1L, .var.name = "row")
  if (nrow(row) != 1L) {
    stop("match_sp_quote_from_row: row must hold exactly one row; got ", nrow(row))
  }
  required <- c("fixture_id", "outcome", "quote_at", "sp_raw", "source_url")
  missing <- setdiff(required, names(row))
  if (length(missing)) {
    stop("match_sp_quote_from_row: row is missing ", paste(missing, collapse = ", "))
  }
  match_sp_quote_class(
    fixture_id = as.character(row$fixture_id[[1L]]),
    outcome    = as.character(row$outcome[[1L]]),
    sp_raw     = as.numeric(row$sp_raw[[1L]]),
    quote_at   = row$quote_at[[1L]],
    source_url = as.character(row$source_url[[1L]])
  )
}

#' 把 MatchSpQuote 列表转回 tibble
#'
#' @param quotes MatchSpQuote 对象的 list（可为空 list）。
#'   · 含非 MatchSpQuote 元素 -> stop()（点名第几个元素）
#' @return tibble，列与类型与 prematch_sp 契约表完全一致；空输入返回 typed-empty 表。
#' @details 这是领域类型回到对外接口的唯一出口。领域类型**绝不**直接返回给调用方：
#'   AGENTS.md 要求所有 R 分析表是 tibble。
match_sp_quotes_to_tibble <- function(quotes) {
  checkmate::assert_list(quotes, .var.name = "quotes")
  if (!length(quotes)) return(match_typed_empty("prematch_sp"))
  bad <- which(!vapply(quotes, S7::S7_inherits, logical(1),
                       class = match_sp_quote_class))
  if (length(bad)) {
    stop("match_sp_quotes_to_tibble: element ", bad[[1L]], " is not an MatchSpQuote")
  }
  tibble::tibble(
    fixture_id = vapply(quotes, function(q) q@fixture_id, character(1)),
    outcome    = vapply(quotes, function(q) q@outcome, character(1)),
    quote_at   = as.POSIXct(vapply(quotes, function(q) as.numeric(q@quote_at),
                                   numeric(1)), origin = "1970-01-01", tz = "UTC"),
    sp_raw     = vapply(quotes, function(q) q@sp_raw, numeric(1)),
    source_url = vapply(quotes, function(q) q@source_url, character(1))
  )
}
#' 一张已验证列契约的域内表
#'
#' @param table tibble（必须是 data.frame）。
#' @param domain 长度 1 的非空字符串，表的域名（对应 match_table_schemas() 的名字），
#'   或 "ranked"/"candidate_tickets" 这类值层内部表。
#'
#' @return 一个 MatchDomainTable 对象。
#'
#' @details 这是 S7 表级类型的通用底座。它保证：
#'   - `table` 确实是 data.frame，且非 NULL；
#'   - 列集合与列序与声明一致（对已声明 schema 的表）；
#'   - 空表仍是完整的 typed-empty（列集合不因零行而丢失）。
#'
#'   与逐行类型（MatchSpQuote）的分工：逐行类型挡的是「一条记录非法」，本类型挡的是
#'   「一张表与它自己的契约不符」。value 层的多数缺陷属于后者。
#'
#'   \strong{不做}的事：本类型不校验跨表关系（如 ranked$ticket_id 是否都在
#'   tickets 表里）。跨表关系由使用方按契约判断，因为只有使用方知道两张表的角色。
#' @usage NULL
match_domain_table_class <- S7::new_class(
  "MatchDomainTable",
  properties = list(
    table  = S7::class_data.frame,
    domain = S7::class_character
  ),
  validator = function(self) {
    problems <- character(0)
    if (length(self@domain) != 1L || is.na(self@domain) || !nzchar(self@domain)) {
      problems <- c(problems, "domain must be one non-empty string")
    }
    if (length(problems)) return(problems)
    schema <- match_table_schemas()[[self@domain]]
    if (!is.null(schema)) {
      if (!identical(names(self@table), schema$columns)) {
        problems <- c(problems, sprintf(
          "table for domain '%s' must have columns (%s); got (%s)",
          self@domain, paste(schema$columns, collapse = ", "),
          paste(names(self@table), collapse = ", ")))
      }
    }
    if (length(problems)) problems else NULL
  }
)

#' 构造一张域内表
#'
#' @param table  tibble。
#' @param domain 长度 1 的非空字符串，域名。
#' @return 一个 MatchDomainTable 对象。
#' @details 这是 tibble 进入域内表类型的唯一入口。对已在 match_table_schemas() 中
#'   声明的域名，列集合与列序会在构造时校验；对值层内部表（ranked 等），只校验
#'   它确实是 data.frame。
match_domain_table <- function(table, domain) {
  checkmate::assert_data_frame(table, .var.name = "table")
  checkmate::assert_string(domain, min.chars = 1L, .var.name = "domain")
  match_domain_table_class(table = tibble::as_tibble(table), domain = domain)
}

#' 把域内表转回 tibble
#'
#' @param object 一个 MatchDomainTable 对象。
#' @return 内层 tibble。
#' @details 这是域内表回到对外接口的唯一出口。AGENTS.md 要求所有 R 分析表是
#'   tibble，因此域内表**绝不**直接返回给调用方：返回前一律先转回 tibble。
match_domain_table_data <- function(object) {
  if (!S7::S7_inherits(object, match_domain_table_class)) {
    stop("match_domain_table_data: object must be an MatchDomainTable")
  }
  object@table
}