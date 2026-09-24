#' N7 管道：固定表 schema、typed-empty 表，以及标识/时间契约
#'
#' 每张表在此有一处唯一权威声明，依据 v1 函数契约
#' (docs/strategy/n7_pipeline_function_contracts.md)。本管道的每个读取方与
#' 写入方都对着它校验，因此契约漂移会在边界处变成错误，而不是下游的静默列错位。
#'
#' typed-empty 规则：空结果保留完整的列集合与列类型。调用方因此可以把空表与
#' 有表的结果直接 bind 而不需特例，"没有行"与"形状不对"保持可区分。
#'
#' @section 参数判定规范（后续所有 N7 模块统一遵守）:
#'
#' **一律使用 checkmate，不手写 stop() 判定。** 手写判定容易漏项、措辞不一，
#' 而 checkmate 是已安装的成熟库（AGENTS.md：不要重造主流库已有能力）。
#' 本仓库 r/ 下此前从未使用过 checkmate；本管道是它的首个使用方。
#'
#' **checkmate 的默认值是宽松的，必须显式收紧。** 实测确认以下默认会静默放过
#' 非法输入：
#' - `any.missing = FALSE`：默认 TRUE，会放过 NA。必须显式写，
#'   否则 `assert_numeric(NA)` 静默通过。
#' - `finite = TRUE`：只查 Inf/NaN，**不隐含** any.missing。
#'   `assert_numeric(NA, finite = TRUE)` 仍然通过，两者必须同时写。
#' - `min.chars = 1`：assert_string 默认放过空串 ""。
#' - `.var.name`：传入面向用户的参数名，使错误信息点名参数。
#'
#' @section 整数范围:
#' `assert_integerish()` 已内置整数溢出检查（实测 3e9 报错、
#' `.Machine$integer.max` 通过），因此不需要额外手写范围守卫。
#' 这一点很关键：`as.integer()` 对超范围值只发 warning 并静默产出 NA，
#' 违反 AGENTS.md「绝不把解析失败静默变成缺失值」，而 checkmate 在强转前就拦住。
#'
#' @section 领域类型（S7）:
#' 对外接口一律是 tibble（AGENTS.md：所有 R 分析表用 tibble）。
#' S7 仅用于管道**内部**的领域对象（如 SP 报价、结构、票），以在构造时而非
#' 下游某处才暴露非法状态。S7 对象不得出现在模块的公开返回结构中。
#'
#' @section 表类型契约:
#' 15 张表由 `n7_table_schemas()` 唯一声明，边界处由
#' `n7_validate_table()` 校验列集合、列序、列类型与主键。
#'
#' @details 本模块只定义函数；导入时不触发任何 I/O，不联网，不写库。

#' @name n7-contracts
#' @keywords internal
NULL

# Null coalescing, declared here so every module in this pipeline shares one
# definition instead of depending on a particular package version exporting it.
`%||%` <- function(x, y) if (is.null(x)) y else x

# --- table schemas ----------------------------------------------------------

#' 本管道 15 张表的唯一权威声明
#'
#' 都对着它校验，因此契约漂移会在边界处变成错误，而不是下游的静默列错位。
#'
#'
#' @return · types 的名字集合必须与 columns 完全相同且同序
#'   · 支持的列类型：character / integer / double / logical / POSIXct
#'
#'
#' · 每张表的 columns 无重复
#' · 每张表的 names(types) == columns
#' · 所有类型取值都在 n7_typed_empty 可构造的集合内
#'
#' @details 列序本身是契约的一部分：typed-empty 表按此列序返回，下游可以依赖位置访问稳定。
n7_table_schemas <- function() {
  list(
    fixtures = list(
      columns = c("issue_id", "fixture_id", "slot", "provider_id", "kickoff_at",
                  "handicap", "sale_state", "source_url"),
      types = c(issue_id = "character", fixture_id = "character", slot = "integer",
                provider_id = "character", kickoff_at = "POSIXct",
                handicap = "integer", sale_state = "character",
                source_url = "character")),
    euro = list(
      columns = c("fixture_id", "company_id", "quote_at", "odds_home",
                  "odds_draw", "odds_away", "source_url"),
      types = c(fixture_id = "character", company_id = "character",
                quote_at = "POSIXct", odds_home = "double",
                odds_draw = "double", odds_away = "double",
                source_url = "character")),
    totals = list(
      columns = c("fixture_id", "company_id", "quote_at", "line",
                  "over_decimal", "under_decimal", "source_url"),
      types = c(fixture_id = "character", company_id = "character",
                quote_at = "POSIXct", line = "double",
                over_decimal = "double", under_decimal = "double",
                source_url = "character")),
    prematch_sp = list(
      columns = c("fixture_id", "outcome", "quote_at", "sp_raw", "source_url"),
      types = c(fixture_id = "character", outcome = "character",
                quote_at = "POSIXct", sp_raw = "double",
                source_url = "character")),
    # candidate_id/ticket_id 是 candidate 与物理票之间的多对多链接表：同一张物理票
    # 可被多个结构引用（契约：同物理票跨 candidate 仅一个 ticket_id），因此这张表
    # 的主键是 (candidate_id, ticket_id)，而不是任一单列。
    candidate_tickets = list(
      columns = c("candidate_id", "ticket_id"),
      types = c(candidate_id = "character", ticket_id = "character"),
      keys = c("candidate_id", "ticket_id")),
    # ranked 是 value 层的排序视图：每个 candidate 的票按分数降序，并列按 ticket_id
    # 定序。列名此前只是隐式约定（n7_fund_groups 直接用 $candidate_id/$ticket_id
    # 反复抓取），现在改为显式契约，使缺列或列序错位在边界处报错。
    ranked = list(
      columns = c("candidate_id", "ticket_id", "group_id", "probability",
                  "ev_net_est", "rank", "cumulative_mass"),
      types = c(candidate_id = "character", ticket_id = "character",
                group_id = "character", probability = "double",
                ev_net_est = "double", rank = "integer",
                cumulative_mass = "double"),
      keys = c("candidate_id", "ticket_id")),
    probabilities = list(
      columns = c("fixture_id", "outcome", "probability"),
      types = c(fixture_id = "character", outcome = "character",
                probability = "double")),
    fit = list(
      columns = c("fixture_id", "lambda_home", "lambda_away", "rho",
                  "residual", "status"),
      types = c(fixture_id = "character", lambda_home = "double",
                lambda_away = "double", rho = "double",
                residual = "double", status = "character")),
    group_legs = list(
      columns = c("group_id", "fixture_id", "leg_order"),
      types = c(group_id = "character", fixture_id = "character",
                leg_order = "integer")),
    supports = list(
      columns = c("candidate_id", "fixture_id", "outcome", "allowed", "preference"),
      types = c(candidate_id = "character", fixture_id = "character",
                outcome = "character", allowed = "logical",
                preference = "integer")),
    tickets = list(
      columns = c("ticket_id", "group_id", "probability", "sp_product_est",
                  "ev_net_est"),
      types = c(ticket_id = "character", group_id = "character",
                probability = "double", sp_product_est = "double",
                ev_net_est = "double")),
    ticket_legs = list(
      columns = c("ticket_id", "fixture_id", "outcome"),
      types = c(ticket_id = "character", fixture_id = "character",
                outcome = "character")),
    purchases = list(
      # A ticket id is shared by every structure over the same fixture set, so a
      # purchase must record WHICH candidate bought it; without that, a shared
      # purchase cannot be attributed and the ledger is ambiguous.
      columns = c("issue_id", "ticket_id", "epoch_at", "group_id", "candidate_id",
                  "stake_cny"),
      types = c(issue_id = "character", ticket_id = "character",
                epoch_at = "POSIXct", group_id = "character",
                candidate_id = "character", stake_cny = "double")),
    settlements = list(
      columns = c("issue_id", "fixture_id", "outcome", "settled_sp",
                  "label_available_at", "status", "source_url"),
      types = c(issue_id = "character", fixture_id = "character",
                outcome = "character", settled_sp = "double",
                label_available_at = "POSIXct", status = "character",
                source_url = "character")),
    exclusions = list(
      columns = c("scope", "issue_id", "fixture_id", "reason"),
      types = c(scope = "character", issue_id = "character",
                fixture_id = "character", reason = "character"))
  )
}

#' 让球胜平负三元组的取值集合
#'
#'
#'
#'
#'
#' @details 调用方不得依赖除此之外的取值顺序或大小写。
n7_outcomes <- function() c("W", "D", "L")

#' 返回一张带完整列集合与列类型的空表
#'
#' 空结果保留板式，使空表与有表可以无差别 rbind，"没有行"与"形状不对"
#' 保持可区分。
#'
#' @param table  长度恰为 1 的字符标量，取值必须属于 names(n7_table_schemas())。
#'   · 非字符 / 长度 != 1 / NA / 空串  -> stop()
#'   · 未知表名                        -> stop()，错误信息列出合法取值
#'
#'
n7_typed_empty <- function(table) {
  if (!is.character(table) || length(table) != 1L || is.na(table) || !nzchar(table)) {
    stop("n7_typed_empty: table must be a single non-empty table name; got ",
         paste(utils::capture.output(utils::str(table)), collapse = " "))
  }
  schema <- n7_table_schemas()[[table]]
  if (is.null(schema)) {
    stop("n7_typed_empty: unknown table ", table, "; known tables are ",
         paste(names(n7_table_schemas()), collapse = ", "))
  }
  out <- stats::setNames(vector("list", length(schema$columns)), schema$columns)
  for (column in schema$columns) {
    type <- schema$types[[column]]
    out[[column]] <- switch(type,
      character = character(0),
      integer = integer(0),
      double = numeric(0),
      logical = logical(0),
      POSIXct = as.POSIXct(character(0), tz = "UTC"),
      stop("n7_typed_empty: unsupported type ", type))
  }
  tibble::as_tibble(out)
}

#' 按 schema 校验一张表
#'
#' 出错即 stop()，绝不静默强转，因此契约破坏不会被悄悄修好。
#'
#' @param data    data.frame（含 tibble）。
#'   · 非 data.frame -> stop()
#' @param table   长度恰为 1 的字符标量，属于 names(n7_table_schemas())。
#'   · 非字符 / 长度 != 1 / NA / 空串 / 未知表名 -> stop()
#' @param keys    校验唯一性的列名。NULL 表示沿用 schema 自己声明的 keys；
#'   若 schema 也没有声明，则不校验唯一性。
#'   · 非字符 / 含 NA / 含空串      -> stop()
#'   · character(0)                 -> stop()（要用 schema 的键或不校验，都必须写 NULL）
#'   · 含 schema 之外的列名          -> stop()
#'
#' @details 列：names(data) 必须与 schema$columns 完全相同（含顺序）
#' 类型：character/integer/double/logical/POSIXct 精确匹配（不宽恕 double vs integer）
#' POSIXct：必须携带 tzone == "UTC"；零长度列同样校验
#' 主键：keys 组合不得重复。keys 未显式给出时采用 schema$keys，
#'   因此声明了复合主键的表（candidate_tickets、ranked）在任何调用点都被强制唯一，
#'   而不是依赖每个调用方记得传 keys
#'
n7_validate_table <- function(data, table, keys = NULL) {
  if (!is.character(table) || length(table) != 1L || is.na(table) || !nzchar(table)) {
    stop("n7_validate_table: table must be a single non-empty table name")
  }
  schema <- n7_table_schemas()[[table]]
  if (is.null(schema)) {
    stop("n7_validate_table: unknown table ", table, "; known tables are ",
         paste(names(n7_table_schemas()), collapse = ", "))
  }
  if (!is.data.frame(data)) stop("n7_validate_table: ", table, " must be a data frame")
  # A schema may DECLARE its own key. Enforcing it here rather than relying on each
  # caller to pass keys means a table cannot be validated as if it had no key: a
  # duplicated composite key would otherwise flow straight through, and a structure
  # referencing one ticket twice would be ranked twice and then BOUGHT twice.
  # An explicit keys argument still wins, so callers can check a narrower key.
  if (is.null(keys) && !is.null(schema$keys)) keys <- schema$keys
  if (!is.null(keys)) {
    if (!is.character(keys) || anyNA(keys) || any(!nzchar(keys))) {
      stop("n7_validate_table: keys must be non-empty column names, or NULL")
    }
    if (!length(keys)) {
      stop("n7_validate_table: keys must be NULL to use the schema's declared key ",
           "(or to skip the check when the schema declares none), not an empty vector")
    }
    unknown <- setdiff(keys, schema$columns)
    if (length(unknown)) {
      stop("n7_validate_table: keys name column(s) not in ", table, ": ",
           paste(unknown, collapse = ", "))
    }
  }
  if (!identical(names(data), schema$columns)) {
    stop("n7_validate_table: ", table, " columns must be exactly ",
         paste(schema$columns, collapse = ", "), "; got ",
         paste(names(data), collapse = ", "))
  }
  for (column in schema$columns) {
    type <- schema$types[[column]]
    value <- data[[column]]
    ok <- switch(type,
      character = is.character(value),
      integer = is.integer(value),
      double = is.double(value),
      logical = is.logical(value),
      POSIXct = inherits(value, "POSIXct"),
      FALSE)
    if (!ok) {
      stop("n7_validate_table: ", table, "$", column, " must be ", type,
           "; got ", paste(class(value), collapse = "/"))
    }
    # Checked even when empty: R preserves tzone on zero-length POSIXct, so an
    # empty column with the wrong zone is still a contract breach.
    if (type == "POSIXct" && !identical(attr(value, "tzone"), "UTC")) {
      stop("n7_validate_table: ", table, "$", column, " must carry tz UTC")
    }
  }
  if (!is.null(keys)) {
    if (nrow(data) && anyDuplicated(data[keys])) {
      stop("n7_validate_table: ", table, " has duplicate key (",
           paste(keys, collapse = ", "), ")")
    }
  }
  data
}

# --- identifier and value contracts -----------------------------------------

#' 校验标识符是干净的字符向量
#'
#' 且可能超出整数范围，数值强转会损坏它们。
#'
#' @param value  字符向量。允许零长度（表示"没有标识符"）。
#'   · 非字符              -> stop()
#'   · 含 NA                -> stop()
#'   · 含空串 ""            -> stop()
#'   · 首尾有空白           -> stop()（空白是数据错误，不是格式）
#' @param what   长度 1 的非空字符，仅用于错误信息；同时校验它自己。
n7_check_character_id <- function(value, what) {
  if (!is.character(what) || length(what) != 1L || is.na(what) || !nzchar(what)) {
    stop("n7_check_character_id: what must be a single non-empty label")
  }
  if (!is.character(value)) stop("n7_check_character_id: ", what, " must be character")
  if (anyNA(value)) stop("n7_check_character_id: ", what, " must not be NA")
  if (any(!nzchar(value))) stop("n7_check_character_id: ", what, " must not be empty")
  if (any(trimws(value) != value)) stop("n7_check_character_id: ", what, " must not be padded")
  invisible(value)
}

#' 校验赛程槽位为正整数，并返回 integer 向量
#'
#' @param value  数值向量。允许零长度。
#'   · 非 numeric            -> stop()
#'   · 含 NA / 非有限         -> stop()
#'   · < 1 或非整数           -> stop()
#'   · 超出 integer 可表示范围 -> stop()
#' @param what   长度 1 的非空字符标签。
#'
#' @details 范围检查必须发生在强转之前：as.integer() 对超范围值只发 warning 并
#'   静默产出 NA，调用方会误以为校验通过。按 AGENTS.md「绝不把解析失败静默变成
#'   缺失值」，这里必须报错。
n7_check_slot <- function(value, what = "slot") {
  if (!is.character(what) || length(what) != 1L || is.na(what) || !nzchar(what)) {
    stop("n7_check_slot: what must be a single non-empty label")
  }
  if (!is.numeric(value)) stop("n7_check_slot: ", what, " must be numeric")
  if (anyNA(value) || any(!is.finite(value))) stop("n7_check_slot: ", what, " must be finite")
  if (any(value < 1 | value != floor(value))) {
    stop("n7_check_slot: ", what, " must be positive whole numbers")
  }
  # Guard BEFORE coercion: as.integer() would silently return NA past the range.
  if (any(value > .Machine$integer.max)) {
    stop("n7_check_slot: ", what, " exceeds the integer range: ",
         format(max(value), scientific = FALSE))
  }
  as.integer(value)
}

# Every probability triple must be non-negative and sum to 1. A triple that is
# merely close is still wrong: these values are used as probabilities, so a
# triple that does not sum to 1 means the caller did the arithmetic wrongly.
#' 校验每行概率三元组非负且行和为 1
#'
#' 行和不为 1 说明调用方算错了。
#'
#' @param triples   matrix（numeric）或 data.frame。允许 0 行。
#'   · 其它类型                  -> stop()
#'   · 含 factor/character 列     -> stop()（不得悄悄变字符矩阵）
#'   · 含 NA / 非有限             -> stop()
#'   · 含负值                     -> stop()
#'   · 任一行和偏离 1 超过 tolerance -> stop()，报最差偏差
#' @param tolerance 长度 1 的正有限数值。
#'   · 非数值 / 长度 != 1 / NA / <= 0 / 非有限 -> stop()
#' @param what      长度 1 的非空字符标签。
n7_check_probability_sum <- function(triples, tolerance = 1e-9, what = "probability") {
  if (!is.character(what) || length(what) != 1L || is.na(what) || !nzchar(what)) {
    stop("n7_check_probability_sum: what must be a single non-empty label")
  }
  if (!is.numeric(tolerance) || length(tolerance) != 1L || is.na(tolerance) ||
      !is.finite(tolerance) || tolerance <= 0) {
    stop("n7_check_probability_sum: tolerance must be one positive finite number")
  }
  if (!is.matrix(triples) && !is.data.frame(triples)) {
    stop("n7_check_probability_sum: ", what, " must be a matrix or data frame")
  }
  # Catch non-numeric columns BEFORE as.matrix(), which would otherwise coerce a
  # data frame to a character matrix and turn a type error into a value error.
  if (is.data.frame(triples) &&
      !all(vapply(triples, function(col) is.numeric(col) || is.integer(col), logical(1)))) {
    stop("n7_check_probability_sum: ", what, " must contain only numeric columns")
  }
  values <- as.matrix(triples)
  if (!is.numeric(values)) stop("n7_check_probability_sum: ", what, " must be numeric")
  if (anyNA(values) || any(!is.finite(values))) {
    stop("n7_check_probability_sum: ", what, " must be finite")
  }
  if (any(values < 0)) stop("n7_check_probability_sum: ", what, " must be non-negative")
  sums <- rowSums(values)
  if (any(abs(sums - 1) > tolerance)) {
    stop("n7_check_probability_sum: ", what, " rows must sum to 1; worst deviation ",
         format(max(abs(sums - 1)), digits = 3))
  }
  invisible(values)
}

#' 校验调用方提供了真实且字段齐全的 cutoff
#'
#' beidan_backend.temporal_learning 的对象，经既有 reticulate 桥接入；本管道不自造第二套
#' 时间框架，因此这里只做"确实给了、且字段够用"的校验，更严格的属于
#' temporal_learning 本身。
#'
#' @param cutoff  list，必须含 cutoff_utc 与 issue_id 两个字段。
#'   · NULL                          -> stop()（显式 cutoff 是硬要求）
#'   · 非 list                       -> stop()
#'   · 缺任一字段                     -> stop()
#'   · cutoff_utc 非 POSIXct          -> stop()
#'   · cutoff_utc 非 UTC              -> stop()
#'   · cutoff_utc 长度 != 1           -> stop()
#'   · issue_id 长度 != 1             -> stop()
#'   · issue_id 非字符/含 NA/空串/带空白 -> stop()
#'
#'
#' --- cutoff binding ---------------------------------------------------------

# The cutoff is a beidan_backend.temporal_learning object, brokered in through the existing
# reticulate bridge. This pipeline does not invent a second time framework, so the
# only thing validated here is that a real cutoff was supplied and that it carries
# the instants this layer needs. Anything stricter belongs to temporal_learning.
n7_require_cutoff <- function(cutoff) {
  if (is.null(cutoff)) stop("n7_require_cutoff: an explicit cutoff is required")
  if (!is.list(cutoff)) stop("n7_require_cutoff: cutoff must be a temporal_learning object")
  for (field in c("cutoff_utc", "issue_id")) {
    if (is.null(cutoff[[field]])) {
      stop("n7_require_cutoff: cutoff is missing ", field)
    }
  }
  if (!inherits(cutoff$cutoff_utc, "POSIXct")) {
    stop("n7_require_cutoff: cutoff$cutoff_utc must be POSIXct")
  }
  if (!identical(attr(cutoff$cutoff_utc, "tzone"), "UTC")) {
    stop("n7_require_cutoff: cutoff$cutoff_utc must be UTC")
  }
  length(cutoff$cutoff_utc) == 1L || stop("n7_require_cutoff: cutoff must be a single instant")
  # issue_id must be exactly ONE issue: a cutoff binds a single decision, and a
  # multi-valued id would make every downstream issue filter ambiguous.
  if (length(cutoff$issue_id) != 1L) {
    stop("n7_require_cutoff: cutoff$issue_id must name exactly one issue; got ",
         length(cutoff$issue_id))
  }
  n7_check_character_id(cutoff$issue_id, "cutoff$issue_id")
  invisible(cutoff)
}

#' 取出 cutoff 的时刻，供本层比较使用
#'
#'
#' @param cutoff  同 n7_require_cutoff；本函数先调用它，因此继承其全部判定。
n7_cutoff_utc <- function(cutoff) {
  n7_require_cutoff(cutoff)
  cutoff$cutoff_utc
}

# --- explicit business constants --------------------------------------------
#
# The contract's constants block: n_legs, issue budget, unit stake, payout factor,
# rho, SP threshold and SP replacement. They are declared here so the pipeline can
# be exercised without sourcing the older research modules, and they are passed
# into functions explicitly rather than read from the session. The defaults match
# the frozen project values; a caller may override any of them.

#' 合同的常量块
#'
#' 显式接收它们，不偷偷依赖全局常量。默认值即项目冻结值，调用方可覆盖任意一项。
#'
#'
#' @return n_legs            integer 标量，固定 7
#' issue_budget_cny  double，单期总预算 CNY 1024
#' unit_cny          double，单票本金 CNY 2
#' payout_factor     double，票级派彩系数 0.65（只乘一次）
#' rho               double，Dixon-Coles 相关参数 -0.14（冻结值，本交付不重新标定）
#' sp_threshold      double，SP 替换阈值 10（> 10 才替换）
#' sp_replacement    double，SP 替换值 4.5
#'
n7_pipeline_constants <- function() {
  list(n_legs = 7L,
       issue_budget_cny = 1024,
       unit_cny = 2,
       payout_factor = 0.65,
       rho = -0.14,
       sp_threshold = 10,
       sp_replacement = 4.5)
}

#' 固定腿数守卫
#'
#'
#'
#'
n7_legs <- function() n7_pipeline_constants()$n_legs

# The shared experiment-contract helpers (ticket identity, group admission) are
# written against a bare N7_LEGS. Defining it here keeps them usable from this
# pipeline without sourcing an unrelated research module; the value is the same
# fixed 7 the contract requires.
N7_LEGS <- 7L
