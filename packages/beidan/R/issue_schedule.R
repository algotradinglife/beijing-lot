#' 整期赛程采集接口：抓取、解析、校验与落盘的显式边界
#'
#' Issue #514 的公开入口。`fetch_issue_schedule()` 返回**每期每场一行**的规范
#' tibble：身份、让球、开赛时刻、比赛状态、销售状态与原始显示文本分列存放。
#'
#' @details 本模块只做编排，不含任何业务解析规则。所有解析规则都在随包分发的
#'   Python 后端 `beidan_backend.issue_schedule` 中（唯一权威实现），R 侧负责：
#'   · 显式校验输入（期号、目录、超时、重试次数）
#'   · 通过已初始化的 Python 句柄调用后端
#'   · 把 Python 返回的行在 **R 边界** 转成带类型的 tibble
#'   · 导出 CSV（readr）与保留原始响应
#'
#'   导入本模块不触发任何 I/O，不联网，不写库。
#'
#' @name issue_schedule
NULL

#' 规范赛程表的列契约
#'
#' @return 字符向量，规范列的固定顺序。
#' @details 列序是契约的一部分：`fetch_issue_schedule()` 的返回、CSV 导出与
#'   Python 后端的 `canonical_columns()` 必须逐列一致。主键是
#'   `(issue_id, slot)`；`slot` 是那期内的场号。
#'
#'   时间列（`kickoff_at` / `sale_end_at` / `observed_at`）一律为北京时间 **Asia/Shanghai**
#'   POSIXct。`kickoff_hhmm` 与 `sale_end_raw` 保留来源的原始显示文本，
#'   与解析后的时刻分开存放：来源只给了 `HH:mm` 时 `kickoff_at` 为 `NA`，
#'   绝不借用期号日期补全。
#'
#'   比赛状态复用全包统一的 [match_status_levels()]；`unknown` 是合法取值，
#'   表示"来源没有给出可判定的证据"，而不是"没抓到"。
#' @export
issue_schedule_columns <- function() {
  c("issue_id", "slot", "fixture_key", "home_name", "away_name", "handicap",
    "kickoff_at", "kickoff_hhmm", "kickoff_group_date", "kickoff_date_source",
    "match_status", "match_status_raw", "sale_state", "sale_end_at",
    "sale_end_raw", "sale_end_date_source", "score", "provider_id",
    "provider_id_500", "provider_id_nowscore", "home_500", "away_500",
    "home_nowscore", "away_nowscore", "identity_method", "identity_note",
    "observed_at", "source_url_500", "source_url_nowscore",
    "raw_display_nowscore", "raw_display_500",
    "home_display_500", "home_title_500", "away_display_500", "away_title_500", "home_display_nowscore", "home_title_nowscore", "away_display_nowscore", "away_title_nowscore", "league_500", "league_nowscore")
}

#' 规范赛程表各列的类型契约
#'
#' @return 具名字符向量，名字为列名，值为
#'   `"character"` / `"integer"` / `"double"` / `"POSIXct"`。
#' @details 类型在 R 边界强制转换，不做静默的隐式解析：时间列必须已经是带
#'   Asia/Shanghai 时区的 POSIXct（后端 UTC 时刻由本模块显式转换），
#'   `slot` 必须是整数。
#' @export
issue_schedule_types <- function() {
  columns <- issue_schedule_columns()
  types <- stats::setNames(rep("character", length(columns)), columns)
  types[["slot"]] <- "integer"
  types[["handicap"]] <- "double"
  types[["kickoff_at"]] <- "POSIXct"
  types[["sale_end_at"]] <- "POSIXct"
  types[["observed_at"]] <- "POSIXct"
  return(types)
}

#' 一张类型化的空规范赛程表
#'
#' @return 0 行的规范 tibble，列序与类型与 [issue_schedule_columns()] 一致。
#' @details 空结果是合法结果（该期确实没有比赛），它必须与"抓取失败"区分开：
#'   失败会 `stop()`，而空表是正常返回。
#' @export
issue_schedule_empty <- function() {
  types <- issue_schedule_types()
  out <- stats::setNames(vector("list", length(types)), names(types))
  for (column in names(types)) {
    out[[column]] <- switch(types[[column]],
      character = character(0),
      integer = integer(0),
      double = numeric(0),
      POSIXct = lubridate::as_datetime(numeric(0), tz = "Asia/Shanghai"),
      stop("issue_schedule_empty: unsupported type ", types[[column]])
    )
  }
  return(tibble::as_tibble(out))
}

#' 采集并解析一整期北单赛程
#'
#' @param issue_id 长度 1 的非空字符串期号。前导零保留；只允许数字。
#' @param raw_dir 长度 1 的非空字符串，原始响应与规范 CSV 的显式落盘目录。
#'   **必填**：没有默认值，因此调用方不可能误写进某个共享数据根。目录不存在
#'   时创建。
#' @param backend 由 [python_backend()] 返回的已初始化句柄。必填，避免隐藏的
#'   会话状态。句柄的 `$module` 是 `temporal_learning`，**不含** issue_schedule；
#'   本函数按显式路径 `backend$root` 单独导入并校验实际加载位置。
#' @param timeout 长度 1 的正数，单次 HTTP 请求超时秒数。
#' @param retries 长度 1 的非负整数，每个 URL 首次失败后的额外重试次数。
#' @param pages 可选具名 list，用于**离线回放**：`list("500" = raw,
#'   "nowscore" = raw)`，元素为原始响应字节（raw 向量）。给出时不发起任何网络
#'   请求。另须提供 `500_observed_at` / `nowscore_observed_at` 原始观测时间
#'   （带时区 ISO-8601 字符串），避免把旧快照标为新观测。
#' @return 列契约见 [issue_schedule_columns()] 的 tibble。附加属性：
#'   · `diagnostics`：跨源身份冲突等**显式诊断**（字符向量）
#'   · `identity_summary`：每种身份判定方法的计数
#'   · `written`：实际写入的文件路径（`raw_dir` 内，每次采集独立目录）
#'   · `source_urls`：本次采集使用的两个来源 URL
#' @details 抓取、解析、校验、落盘分离：解析规则全部在 Python 后端，落盘只写
#'   原始字节 + 解析行 JSON + 元数据回执，**不碰数据库，也不写 CSV**（CSV 是
#'   调用方的显式动作，直接用 `readr::write_csv()`）。原始响应在解析之前先落盘，
#'   且每次采集写入独立子目录，不会覆盖既有快照。
#'
#'   比赛状态只依据来源给出的证据判定：Nowscore 的 `完场` 才是 finished，
#'   `截止` 且无比分是 unknown，裸 `HH:mm` 是**销售显示**而不是比赛状态，
#'   `cansale = TRUE` 也**不会**把它升级为 scheduled。
#' @export
fetch_issue_schedule <- function(issue_id, raw_dir, backend, timeout = 25,
                                 retries = 2L, pages = NULL) {
  checkmate::assert_string(issue_id, na.ok = FALSE, min.chars = 1)
  if (!grepl("^[0-9]+$", issue_id)) {
    stop("fetch_issue_schedule: issue_id must be digits only (leading zeros ",
         "are preserved); got ", issue_id)
  }
  checkmate::assert_string(raw_dir, na.ok = FALSE, min.chars = 1)
  if (!inherits(backend, "python_backend")) stop("backend must be a python_backend")
  checkmate::assert_number(timeout, lower = .Machine$double.eps, finite = TRUE)
  checkmate::assert_count(retries, positive = FALSE)
  if (!is.null(pages)) {
    checkmate::assert_names(names(pages), type = "unique")
    if (any(!names(pages) %in% c("500", "nowscore", "500_observed_at",
          "nowscore_observed_at", "500_content_type", "nowscore_content_type"))) {
      stop("unknown offline pages field")
    }
    if (!is.list(pages) || is.null(pages[["500"]]) || is.null(pages[["nowscore"]])) {
      stop("pages must be a list with raw '500' and 'nowscore' byte vectors")
    }
    for (name in c("500", "nowscore")) {
      if (!is.raw(pages[[name]])) {
        stop("pages$", name, " must be a raw vector of response bytes")
      }
    }
  }

  module <- issue_schedule_module(backend)
  kwargs <- list(
    raw_dir = raw_dir,
    timeout = timeout,
    retries = as.integer(retries)
  )
  if (!is.null(pages)) {
    kwargs$pages <- issue_schedule_pages_dict(pages)
  }
  result <- do.call(module$fetch_issue_schedule, c(list(issue_id), kwargs))

  rows <- reticulate::py_to_r(result$rows)
  if (!length(rows)) return(issue_schedule_attach(issue_schedule_empty(), result))
  out <- issue_schedule_coerce(issue_schedule_rows_to_tibble(rows))
  return(issue_schedule_attach(out, result))
}

#' 构造后端 `pages=` 参数（真正的字符串键 Python 字典）
#'
#' @param pages 具名 list，元素为原始响应字节。
#' @return 一个 Python dict，键为字符串 `"500"` / `"nowscore"`。
#' @details `reticulate::dict("500" = ...)` 会把 `"500"` 当作整数键，后端按
#'   `pages["500"]` 取值就会 `KeyError`。这里先建空 dict，再用
#'   `__setitem__` 写入 Python 字符串键，确保键类型与后端一致。
#' @keywords internal
issue_schedule_pages_dict <- function(pages) {
  builtins <- reticulate::import_builtins(convert = FALSE)
  result <- builtins$dict()
  for (name in names(pages)) {
    result$`__setitem__`(name, pages[[name]])
  }
  return(result)
}

#' 显式导入并校验随包的 issue_schedule 后端模块
#'
#' @param backend 由 [python_backend()] 返回的已初始化句柄。
#' @return 从 `backend$root` 加载的 `beidan_backend.issue_schedule` 模块句柄。
#' @details `backend$module` 是 `beidan_backend.temporal_learning`，**没有**
#'   `issue_schedule` 属性。这里按显式包路径重新导入，并核对 `__file__` 确实
#'   落在该 `root` 下，避免误用别的检出或别的包位置。
#' @keywords internal
issue_schedule_module <- function(backend) {
  if (!inherits(backend, "python_backend")) stop("backend must be a python_backend")
  root <- backend$root
  if (!is.character(root) || length(root) != 1L || !nzchar(root)) {
    stop("backend$root must be a non-empty package python path")
  }
  module <- reticulate::import_from_path(
    "beidan_backend.issue_schedule", path = root, convert = FALSE
  )
  actual <- reticulate::py_to_r(module$`__file__`)
  expected <- file.path(root, "beidan_backend", "issue_schedule", "__init__.py")
  if (!identical(normalizePath(actual, mustWork = TRUE),
                 normalizePath(expected, mustWork = TRUE))) {
    stop("issue_schedule backend was loaded from another location: ", actual)
  }
  return(module)
}

#' 把 Python 行（list of named list）转成等长 tibble
#'
#' @param rows `py_to_r()` 之后的 list；每个元素是一行的具名 list，缺失字段为
#'   `NULL`，时间字段已由 reticulate 转成 POSIXct。
#' @return data.frame，列集合为各行的并集，列序按首次出现。
#' @details 真实后端行含 `None` 字段，且行间字段可能不齐。这里逐列构造**向量**：
#'   缺失或长度为 0 的值统一填 `NA`，所以一列全为 `None` 时仍然保留该列、
#'   保留类型与行数。直接把 `list` 交给 `as.data.frame()` 会生成
#'   `kickoff_at.NA` 这类坏列名并丢掉全 NA 列，因此不用那条路径。
#' @keywords internal
issue_schedule_rows_to_tibble <- function(rows) {
  if (!is.list(rows) || !length(rows)) {
    stop("issue_schedule_rows_to_tibble: rows must be a non-empty list")
  }
  if (!all(vapply(rows, is.list, logical(1)))) {
    stop("issue_schedule_rows_to_tibble: every row must be a named list")
  }
  columns <- unique(unlist(lapply(rows, names), use.names = FALSE))
  if (!length(columns)) {
    stop("issue_schedule_rows_to_tibble: rows carry no column names")
  }
  out <- stats::setNames(vector("list", length(columns)), columns)
  for (column in columns) {
    values <- lapply(rows, function(row) {
      value <- row[[column]]
      if (is.null(value)) return(NA)
      if (!is.atomic(value) || !is.null(dim(value)) || length(value) != 1L) stop("Python row fields must be scalars: ", column)
      return(value)
    })
    out[[column]] <- issue_schedule_column_vector(values, column)
  }
  return(tibble::as_tibble(out))
}

#' 把一列 `NA`/标量混合的 list 折叠成类型稳定的向量
#'
#' @param values 长度等于行数的 list，元素为标量或 `NA`。
#' @param what 列名标签，仅用于错误信息。
#' @return 向量：全是 `NA` 时为 `NA` 逻辑向量，否则保持首个非缺失元素的类型
#'   （POSIXct 走 `do.call(c, ...)` 以保留时区）。
#' @keywords internal
issue_schedule_column_vector <- function(values, what) {
  present <- vapply(values, function(value) !is.null(value) && length(value) == 1L &&
                      !(length(value) == 1L && is.atomic(value) && is.na(value)), logical(1))
  if (!any(present)) return(rep(NA, length(values)))
  template <- values[[which(present)[1L]]]
  valid <- vapply(values[present], function(value) {
    if (inherits(template, "POSIXct")) return(inherits(value, "POSIXct"))
    if (is.character(template)) return(is.character(value))
    return(is.numeric(value) && !is.object(value))
  }, logical(1))
  if (!all(valid)) stop("inconsistent Python column types: ", what)
  if (inherits(template, "POSIXct")) {
    return(do.call(c, lapply(values, function(value) {
      if (is.null(value) || !length(value) || (is.atomic(value) && all(is.na(value)))) {
        return(lubridate::as_datetime(NA_real_, tz = "Asia/Shanghai"))
      }
      value
    })))
  }
  out <- rep(NA, length(values))
  out[present] <- unlist(values[present], use.names = FALSE)
  return(out)
}

#' 校准 Python 返回的行为规范 tibble
#'
#' @param data data.frame，列集合必须与 [issue_schedule_columns()] 完全一致。
#' @return 规范 tibble。
#' @details 缺列 / 多列一律 `stop()`：不静默丢列，也不让调用方以为数据被采纳。
#'   时间列按 ISO-8601 解析为北京时间 Asia/Shanghai；`NA` 原样保留。
#' @keywords internal
issue_schedule_coerce <- function(data) {
  expected <- issue_schedule_columns()
  if (!is.data.frame(data)) stop("issue_schedule_coerce: data must be a data frame")
  missing <- setdiff(expected, names(data))
  if (length(missing)) {
    stop("issue_schedule_coerce: missing columns ", paste(missing, collapse = ", "))
  }
  extra <- setdiff(names(data), expected)
  if (length(extra)) {
    stop("issue_schedule_coerce: unexpected columns ", paste(extra, collapse = ", "))
  }
  types <- issue_schedule_types()
  out <- data[expected]
  for (column in expected) {
    value <- out[[column]]
    out[[column]] <- switch(types[[column]],
      character = issue_schedule_character(value, column),
      integer = issue_schedule_integer(value, column),
      double = issue_schedule_double(value, column),
      POSIXct = issue_schedule_timestamp(value, column),
      stop("issue_schedule_coerce: unsupported type for ", column)
    )
  }
  return(tibble::as_tibble(out))
}

#' 把一列强制为 character，拒绝丢失精度或伪造缺失
#'
#' @param value 任意向量；`NULL` 视为整列缺失。
#' @param what 列名标签，仅用于错误信息。
#' @return character 向量。
#' @details 数值（尤其整数标识）转 character 会把 `00123` 变成 `123`，因此除非
#'   整列都是 `NA`，否则只接受 character 输入。空串保留为空串而不是 `NA`。
#' @keywords internal
issue_schedule_character <- function(value, what) {
  if (is.null(value)) return(NA_character_)
  if (is.character(value)) return(value)
  if (all(is.na(value))) return(rep(NA_character_, length(value)))
  stop("issue_schedule_coerce: ", what,
       " must be character; converting would corrupt identifiers")
}

#' 把一列强制为 integer，拒绝小数与不可解析值
#'
#' @param value 任意向量；`NULL` 视为整列缺失。
#' @param what 列名标签，仅用于错误信息。
#' @return integer 向量。
#' @details `as.integer()` 会静默截断 `1.5`，所以先按数值解析并核对是否整数。
#'   `NA` 保留为 `NA`；非空且不可解析或带小数的值 `stop()`。
#' @keywords internal
issue_schedule_integer <- function(value, what) {
  if (is.null(value)) return(NA_integer_)
  numeric_value <- suppressWarnings(as.numeric(value))
  bad <- is.na(numeric_value) & !is.na(value)
  if (any(bad)) {
    stop("issue_schedule_coerce: ", what, " has non-numeric value(s): ",
         paste(utils::head(as.character(value[bad]), 3L), collapse = ", "))
  }
  if (any(is.nan(numeric_value)) ||
      any(!is.na(numeric_value) & (!is.finite(numeric_value) |
          abs(numeric_value) > .Machine$integer.max))) stop("integer out of range: ", what)
  present <- !is.na(numeric_value)
  if (any(present & numeric_value != trunc(numeric_value))) {
    stop("issue_schedule_coerce: ", what, " must be a whole number; fractional ",
         "values such as ", numeric_value[present & numeric_value != trunc(numeric_value)][1L],
         " are not silently truncated")
  }
  return(as.integer(numeric_value))
}

#' 把一列强制为 double，拒绝不可解析值
#'
#' @param value 任意向量；`NULL` 视为整列缺失。
#' @param what 列名标签，仅用于错误信息。
#' @return double 向量。
#' @details 非空且不可解析的值 `stop()`，不静默 NA。
#' @keywords internal
issue_schedule_double <- function(value, what) {
  if (is.null(value)) return(NA_real_)
  numeric_value <- suppressWarnings(as.numeric(value))
  bad <- is.na(numeric_value) & !is.na(value)
  if (any(bad)) {
    stop("issue_schedule_coerce: ", what, " has non-numeric value(s): ",
         paste(utils::head(as.character(value[bad]), 3L), collapse = ", "))
  }
  if (any(is.nan(numeric_value)) ||
      any(!is.na(numeric_value) & !is.finite(numeric_value))) stop("nonfinite number: ", what)
  return(as.numeric(numeric_value))
}

#' 把 ISO-8601 字符串列解析为北京时间 POSIXct
#'
#' @param value 字符向量（UTC 或带偏移的 ISO-8601），允许 NA。
#' @param what 长度 1 的列名标签，仅用于错误信息。
#' @return Asia/Shanghai POSIXct 向量。
#' @details `NA` 与空串均为 `NA`（来源确实没有给出时刻）。可解析但带非 UTC
#'   偏移的字符串按同一时刻换算到 Asia/Shanghai；不可解析的非空值 `stop()`——把解析失败
#'   变成静默缺失值会伪造"来源没给时间"的假象。
#' @keywords internal
issue_schedule_timestamp <- function(value, what) {
  if (inherits(value, "POSIXct")) return(lubridate::with_tz(value, "Asia/Shanghai"))
  value <- as.character(value)
  out <- lubridate::as_datetime(rep(NA_real_, length(value)), tz = "UTC")
  present <- !is.na(value) & nzchar(value)
  if (any(present)) {
    parsed <- lubridate::ymd_hms(value[present], tz = "UTC", quiet = TRUE)
    if (anyNA(parsed)) {
      stop("issue_schedule_timestamp: ", what,
           " has values that are not parseable ISO-8601 instants: ",
           paste(utils::head(value[present][is.na(parsed)], 3L), collapse = ", "))
    }
    out[present] <- parsed
  }
  attr(out, "tzone") <- "Asia/Shanghai"
  return(out)
}

#' 给规范表附加本次采集的来源与诊断属性
#'
#' @param table 规范 tibble。
#' @param result 后端返回的结果对象。
#' @return 附加了 `diagnostics` / `identity_summary` / `written` /
#'   `source_urls` 属性的 tibble。
#' @keywords internal
issue_schedule_attach <- function(table, result) {
  attr(table, "diagnostics") <- reticulate::py_to_r(result$diagnostics)
  attr(table, "identity_summary") <- reticulate::py_to_r(result$identity_summary)
  attr(table, "written") <- reticulate::py_to_r(result$written)
  attr(table, "source_urls") <- reticulate::py_to_r(result$urls)
  attr(table, "observed_at") <- reticulate::py_to_r(result$observed_at)
  return(table)
}
