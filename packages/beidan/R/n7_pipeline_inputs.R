#' N7 管道的输入适配层与 n7_read_inputs 入口
#'
#' 读取是显式的：调用方传入一个 source 描述符，指向内存中的夹具列表，或一个 CSV
#' 目录。这里不抓取、不爬、不写；需要网络访问的 source 一律拒绝。
#'
#' 返回的列表永不包含 settlements。决策侧输入不得看到赛果，这条契约由构造方式
#' 强制，而不是靠调用方记得别去看。
#'
#' @details 本模块只定义函数，导入时不触发任何 I/O。

#' 磁盘 CSV 适配层的列契约
#'
#' 与 tibble schema 保持一致；由下方读取器在边界处改名并改型。
#'
#' @return 具名 list，名字为表名，值为该表 CSV 必须携带且仅可携带的列名。
#' @details 只覆盖可在磁盘上出现的五张表：fixtures、euro、totals、prematch_sp、
#'   match_status。settlements 与其余派生表不在其中，因此磁盘源无法把赛果混进
#'   决策输入。
n7_source_csv_columns <- function() {
  list(
    fixtures = c("issue_id", "fixture_id", "slot", "provider_id", "kickoff_at",
                 "handicap", "sale_state", "source_url"),
    euro = c("fixture_id", "company_id", "quote_at", "odds_home", "odds_draw",
             "odds_away", "source_url"),
    totals = c("fixture_id", "company_id", "quote_at", "line", "over_decimal",
               "under_decimal", "source_url"),
    prematch_sp = c("fixture_id", "outcome", "quote_at", "sp_raw", "source_url"),
    match_status = c("issue_id", "fixture_id", "status", "status_at",
                     "available_at", "source_url")
  )
}

#' 解析 ISO-8601 UTC 时间戳列
#'
#' @param value  字符向量（ISO-8601 带显式 UTC 偏移的字符串），或 POSIXct 向量。
#'   允许零长度。字符形式：
#'   · 必须携带显式偏移（尾部 Z、+HH:MM 或 +HHMM）-> 裸时间戳报错
#'   · NA                -> stop()
#'   · 非字符非 POSIXct  -> stop()
#'   · 无法解析          -> stop()
#'   POSIXct 形式：非 UTC 时区的会先转换到 UTC 再返回。
#' @param what   长度 1 的非空字符标签，仅用于错误信息；同时校验它自己。
#' @return UTC 时区的 POSIXct 向量。
#' @details 裸时间戳被拒绝而不是假定为 UTC：在这里猜会静默平移 cutoff，从而错误地
#'   纳入或排除一笔报价。所有可接受的写法都被归一到 strptime 唯一认识的形式——
#'   尾部 Z 变 +0000，带冒号的偏移去掉冒号；否则 strptime 对 "+08:00" 返回 NA，
#'   而一个把墙钟部分当 UTC 的兜底会把每笔报价按其偏移量平移。
n7_parse_utc <- function(value, what) {
  if (!is.character(what) || length(what) != 1L || is.na(what) || !nzchar(what)) {
    stop("n7_parse_utc: what must be a single non-empty label")
  }
  if (inherits(value, "POSIXct")) {
    if (!identical(attr(value, "tzone"), "UTC")) {
      return(as.POSIXct(format(value, tz = "UTC", usetz = TRUE), tz = "UTC", format = "%Y-%m-%d %H:%M:%S"))
    }
    return(value)
  }
  if (!is.character(value)) stop("n7_parse_utc: ", what, " must be character or POSIXct")
  if (anyNA(value)) stop("n7_parse_utc: ", what, " must not be NA")
  if (any(!grepl("(Z|[+-][0-9]{2}:?[0-9]{2})$", value))) {
    stop("n7_parse_utc: ", what, " must carry an explicit UTC offset")
  }
  # Normalise every accepted spelling to the one form strptime understands:
  # a trailing Z becomes +0000 and a colon-bearing offset loses its colon. Without
  # this, strptime returns NA for "+08:00" and a fallback that formatted the
  # wall-clock part as UTC would shift every quote by its offset -- admitting
  # post-cutoff rows as if they were early.
  normalised <- sub("Z$", "+0000", value)
  normalised <- sub("([+-][0-9]{2}):([0-9]{2})$", "\\1\\2", normalised)
  parsed <- as.POSIXct(strptime(normalised, format = "%Y-%m-%dT%H:%M:%S%z", tz = "UTC"))
  if (anyNA(parsed) || !identical(attr(parsed, "tzone"), "UTC")) {
    attr(parsed, "tzone") <- "UTC"
  }
  if (anyNA(parsed)) stop("n7_parse_utc: ", what, " is not a parseable UTC instant")
  parsed
}

#' 把一张 CSV 数据框强制转换为其声明的 tibble schema
#'
#' @param data   data.frame。列集合必须与 n7_source_csv_columns() 完全一致。
#'   · 缺失列            -> stop()
#'   · 多余列            -> stop()（不静默丢弃，避免调用方以为数据被采纳）
#' @param table  长度 1 的字符标量，属于 names(n7_source_csv_columns())。
#' @return tibble，列序与列类型等于 n7_table_schemas()[[table]]。
#' @details 列类型按 schema 逐列转换：character 原样、integer/double 走 as.numeric
#'   后再校验、POSIXct 走 n7_parse_utc。整数超出 integer 可表示范围时报错，而不是
#'   让 as.integer() 静默产出 NA——数据边界上的静默缺失值比报错危险得多。
#'   0 行输入直接返回该表的 typed-empty。
n7_coerce_source_table <- function(data, table) {
  expected <- n7_source_csv_columns()[[table]]
  if (!is.data.frame(data)) stop("n7_coerce_source_table: ", table, " must be a data frame")
  missing <- setdiff(expected, names(data))
  if (length(missing)) {
    stop("n7_coerce_source_table: ", table, " is missing columns ",
         paste(missing, collapse = ", "))
  }
  extra <- setdiff(names(data), expected)
  if (length(extra)) {
    stop("n7_coerce_source_table: ", table, " has unexpected columns ",
         paste(extra, collapse = ", "))
  }
  out <- data[expected]
  if (nrow(out) == 0) return(n7_typed_empty(table))
  schema <- n7_table_schemas()[[table]]
  for (column in expected) {
    type <- schema$types[[column]]
    value <- out[[column]]
    out[[column]] <- switch(type,
      character = {
        if (!is.character(value)) stop("n7_coerce_source_table: ", table, "$", column, " must be character")
        value
      },
      integer = {
        numeric_value <- suppressWarnings(as.numeric(value))
        if (anyNA(numeric_value)) stop("n7_coerce_source_table: ", table, "$", column, " must be integer")
        if (any(numeric_value != floor(numeric_value))) {
          stop("n7_coerce_source_table: ", table, "$", column, " must be whole numbers")
        }
        # Range check BEFORE coercion: as.integer() only warns past the range and
        # returns NA, which would store a silent missing value at a data boundary.
        # BOTH bounds are checked. Guarding only the upper bound let a large negative
        # value through to as.integer(), which warned and stored NA_integer_ -- the
        # exact silent-missing-value failure this guard exists to prevent.
        # -.Machine$integer.max, NOT -.Machine$integer.max - 1: R reserves
        # -2147483648 itself for NA_integer_. Accepting it stored a missing value
        # behind a legitimate-looking number, which is the failure this guards against.
        over <- numeric_value[!is.na(numeric_value) &
                                (numeric_value > .Machine$integer.max |
                                 numeric_value < -.Machine$integer.max)]
        if (length(over)) {
          stop("n7_coerce_source_table: ", table, "$", column,
               " exceeds the integer range: ",
               format(over[1], scientific = FALSE))
        }
        as.integer(numeric_value)
      },
      double = {
        numeric_value <- suppressWarnings(as.numeric(value))
        if (anyNA(numeric_value)) stop("n7_coerce_source_table: ", table, "$", column, " must be numeric")
        as.double(numeric_value)
      },
      POSIXct = n7_parse_utc(value, paste0(table, "$", column)),
      stop("n7_coerce_source_table: unsupported type ", type))
  }
  tibble::as_tibble(out)
}

#' 归一化赛果标签
#'
#' @param value  字符向量。允许零长度。
#'   · 非字符            -> stop()
#'   · 含 NA             -> stop()
#'   · 出现 W/D/L 之外的取值 -> stop()
#' @param what   长度 1 的非空字符标签。
#' @return 原样返回 value（取值已保证是 W/D/L 三者之一）。
#' @details 取值集合以 n7_outcomes() 为唯一权威，不在此重复声明，避免两处定义漂移。
#'   标签比较区分大小写：小写 "w" 不是合法赛果，不会被悄悄接受。
n7_normalise_outcome <- function(value, what = "outcome") {
  if (!is.character(what) || length(what) != 1L || is.na(what) || !nzchar(what)) {
    stop("n7_normalise_outcome: what must be a single non-empty label")
  }
  if (!is.character(value)) stop("n7_normalise_outcome: ", what, " must be character")
  if (anyNA(value)) stop("n7_normalise_outcome: ", what, " must not be NA")
  if (!all(value %in% n7_outcomes())) {
    stop("n7_normalise_outcome: ", what, " must be one of ",
         paste(n7_outcomes(), collapse = ", "))
  }
  value
}

# --- readers ----------------------------------------------------------------

#' 读取一个夹具 source 描述符
#'
#' @param source  list，必须含 kind。
#'   · 非 list                      -> stop()
#'   · 缺 kind                      -> stop()
#'   · kind == "frames"：必须含 list 型 tables；缺 match_status 表 -> stop()
#'   · kind == "csv_dir"：必须含 path，且指向已存在目录；缺 match_status.csv -> stop()
#'   · 其它 kind（含任何网络源）    -> stop()
#' @return 具名 list，五张表（fixtures/euro/totals/prematch_sp/match_status），均为
#'   已校验 tibble。
#' @details CSV 一律以 colClasses = "character" 读入：否则 read.csv 会在契约校验看到
#'   之前，把全数字的 issue_id 或带前导零的 id 变成数值。
#'
#'   match_status 是**必需的观测台账**：源没有提供它，是一个输入契约错误，必须报错，
#'   绝不回退成 typed-empty。把"源里没有这张表"读成"没有可见状态"会让一期比赛因为
#'   一个读取缺陷而被静默排除。其余表缺失时退化为 typed-empty（它们的缺失含义明确）。
n7_read_fixture_source <- function(source) {
  if (!is.list(source)) stop("n7_read_fixture_source: source must be a list")
  if (is.null(source$kind)) stop("n7_read_fixture_source: source$kind is required")
  if (identical(source$kind, "frames")) {
    tables <- source$tables
    if (!is.list(tables)) stop("n7_read_fixture_source: source$tables must be a list")
    if (is.null(tables[["match_status"]])) {
      stop("n7_read_fixture_source: source$tables has no match_status table; a missing ",
           "status ledger is an input-contract error and is never read as empty")
    }
    out <- list()
    for (table in names(n7_source_csv_columns())) {
      out[[table]] <- if (is.null(tables[[table]])) {
        n7_typed_empty(table)
      } else {
        n7_coerce_source_table(tables[[table]], table)
      }
    }
    return(out)
  }
  if (identical(source$kind, "csv_dir")) {
    directory <- source$path
    if (!is.character(directory) || length(directory) != 1L || !dir.exists(directory)) {
      stop("n7_read_fixture_source: source$path must be an existing directory")
    }
    status_file <- file.path(directory, "match_status.csv")
    if (!file.exists(status_file)) {
      stop("n7_read_fixture_source: ", status_file, " is missing; a missing status ",
           "ledger is an input-contract error and is never read as empty")
    }
    out <- list()
    for (table in names(n7_source_csv_columns())) {
      file <- file.path(directory, paste0(table, ".csv"))
      out[[table]] <- if (file.exists(file)) {
        # colClasses "character" keeps identifiers as text: read.csv would otherwise
        # turn an all-digit issue_id or a leading-zero id into a number before the
        # contract check ever sees it.
        raw <- utils::read.csv(file, stringsAsFactors = FALSE, colClasses = "character")
        n7_coerce_source_table(raw, table)
      } else {
        n7_typed_empty(table)
      }
    }
    return(out)
  }
  stop("n7_read_fixture_source: unsupported source$kind ", source$kind,
       "; network sources are not permitted by this contract")
}

#' 读取某期决策侧的输入表
#'
#' @param source    夹具 source 描述符，语义同 n7_read_fixture_source。
#' @param issue_ids 字符向量，要保留的期号；经 n7_check_character_id 校验
#'   （非字符/含 NA/空串/带空白 -> stop()）。零长度表示不保留任何行。
#' @return list(fixtures, euro, totals, prematch_sp, match_status)，均为已校验 tibble。
#'   返回结构中不含 settlements。
#' @details 读取是**整期**的：没有任何 cutoff 参数，也不按时间过滤，因此一期内
#'   每一天的比赛都被完整保留。哪一天属于哪个决策窗口、哪条报告在 cutoff 当时可见，
#'   一律归 n7_prepare_epoch 与 n7_select_match_status 决定 —— 在这里先按时间裁剪
#'   会丢掉后续"事后取消"的观测，从而无法证明未来报告不能改写过去的决策。
#'
#'   source 表**不被修改**：过滤只产出新的子集，调用方传进来的 data.frame 保持原样。
#'
#'   match_status 的关系键在过滤**之前**、对着**原始的完整** fixtures 校验：一条
#'   指向根本不存在的比赛的台账行，无论它属于哪一期，都必须在输入边界报错，而不是
#'   在过滤后因为"没匹配上"被静默丢弃。过滤之后只按 (issue_id, fixture_id) 复合键
#'   保留属于被请求期的行。因此台账里"本期但被裁掉"的比赛仍被视为已知比赛。
#'
#'   缺失 match_status **表**是输入契约错误（frames 源的 tables 里没有该键、CSV 目录里
#'   没有该文件），必须报错；**不允许**回退成 typed-empty。typed-empty 只能由调用方
#'   显式提供一个零行的 match_status 表来表达"确实没有任何可见报告"。
n7_read_inputs <- function(source, issue_ids) {
  n7_check_character_id(issue_ids, "issue_ids")
  inputs <- n7_read_fixture_source(source)
  fixtures <- inputs$fixtures
  if (!"match_status" %in% names(inputs)) {
    stop("n7_read_inputs: source provides no match_status table; a missing status ",
         "ledger is an input-contract error, not an empty one")
  }
  raw_status <- n7_validate_match_status(inputs$match_status, fixtures = fixtures)
  if (nrow(fixtures)) {
    fixtures <- fixtures[fixtures$issue_id %in% issue_ids, , drop = FALSE]
  }
  fixture_ids <- fixtures$fixture_id
  keep <- function(data) {
    if (!nrow(data) || !length(fixture_ids)) return(data[0, , drop = FALSE])
    data[data$fixture_id %in% fixture_ids, , drop = FALSE]
  }
  # Composite-key filter on typed columns: a same-numbered fixture in another issue
  # is a different match and must not ride along with this issue's fixtures.
  match_status <- if (nrow(raw_status)) {
    raw_status[raw_status$issue_id %in% issue_ids, , drop = FALSE]
  } else {
    raw_status
  }
  result <- list(
    fixtures = n7_validate_table(fixtures, "fixtures", keys = c("issue_id", "fixture_id")),
    euro = n7_validate_table(keep(inputs$euro), "euro"),
    totals = n7_validate_table(keep(inputs$totals), "totals"),
    prematch_sp = n7_validate_table(keep(inputs$prematch_sp), "prematch_sp"),
    match_status = n7_validate_match_status(match_status, fixtures = fixtures))
  if ("settlements" %in% names(result)) {
    stop("n7_read_inputs: decision inputs must not carry settlements")
  }
  result
}
