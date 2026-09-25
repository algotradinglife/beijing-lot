#' N7 管道的比赛状态（match_status）选择器
#'
#' 比赛可见性是**输入的观测事实**，不是从赛果倒推出来的属性。本模块提供唯一的
#' 共享选择器 n7_select_match_status()：在 cutoff 之前的那一刻，每一场复合比赛身份
#' 最新可见的状态报告决定它是否可投注。
#'
#' @details 本模块只定义函数，导入时不触发任何 I/O，不联网，不写库，也不做任何
#'   拟合或学习：可见性是一条 as-of 规则，不是需要从历史中学习的参数。

#' 比赛状态报告的取值集合
#'
#' @return 长度为 7 的字符向量：scheduled/live/finished/postponed/cancelled/
#'   abandoned/unknown。
#' @details 唯一权威声明。unknown 是**合法取值**（源确实报告了"未知"），但不是
#'   可投注状态：把它删掉会让"源说未知"与"源没有报告"混为一谈。
n7_match_statuses <- function() {
  c("scheduled", "live", "finished", "postponed", "cancelled", "abandoned", "unknown")
}

#' 校验 match_status 历史台账
#'
#' @param match_status data.frame，比赛状态报告台账，列集合必须为
#'   issue_id, fixture_id, status, status_at, available_at, source_url。
#'   · 缺列 / 多列        -> stop()
#'   · 含 NA 或空串的标识  -> stop()
#'   · status 不在 n7_match_statuses() -> stop()
#'   · 时间戳非 POSIXct/NA/非有限 -> stop()
#'   · status_at > available_at -> stop()（状态事件不可能晚于它的观测时刻）
#'   · 复合键 (issue_id, fixture_id, available_at) 重复 -> stop()
#' @param fixtures data.frame 或 NULL。给出时校验台账的键都能在 fixtures 中找到；
#'   台账可以携带该期但已被切掉的比赛（下游切片），但不得指向不存在的比赛。
#' @return 归一化为 tibble 的台账，列序与类型已确定（UTC POSIXct）。
#' @details 校验对**权威 schema**（n7_table_schemas()$match_status）执行，键是
#'   **有类型的** issue_id/fixture_id/available_at，不是格式化后的时间戳字符串：
#'   两个不同的 instant 若格式化到同一秒就会被误判为重复键，而数值/因子型 id 也
#'   绝不会被强转成字符来"修复"。时间戳的时区不从别处搬运：n7_validate_table()
#'   已经要求 tzone == "UTC"，本函数不再补写属性。
#'
#'   缺失的台账由调用方在边界处报错；本函数只校验"给了什么"。空台账是合法
#'   输入（零行），它表示"没有任何可见报告"，从而排除全部比赛，而不是回退到
#'   sale_state 之类的旧逻辑。
n7_validate_match_status <- function(match_status, fixtures = NULL) {
  n7_validate_table(match_status, "match_status")
  out <- tibble::as_tibble(match_status)
  n7_check_character_id(out$issue_id, "match_status$issue_id")
  n7_check_character_id(out$fixture_id, "match_status$fixture_id")
  if (anyNA(out$status)) {
    stop("n7_validate_match_status: match_status$status must not be NA")
  }
  if (any(!out$status %in% n7_match_statuses())) {
    bad <- unique(out$status[!out$status %in% n7_match_statuses()])
    stop("n7_validate_match_status: unknown match status token(s) ",
         paste(bad, collapse = ", "), "; allowed statuses are ",
         paste(n7_match_statuses(), collapse = ", "))
  }
  if (anyNA(out$source_url) || any(!nzchar(out$source_url))) {
    stop("n7_validate_match_status: match_status$source_url must be non-empty")
  }
  # Both instants are checked as instants, not as numbers: a non-POSIXct column
  # compared against the cutoff would coerce and silently match nothing, which
  # would look like "no report" and exclude a fixture the source did report on.
  for (column in c("status_at", "available_at")) {
    value <- out[[column]]
    if (length(value) && anyNA(value)) {
      stop("n7_validate_match_status: match_status$", column, " must not be NA")
    }
    if (length(value) && any(!is.finite(as.numeric(value)))) {
      stop("n7_validate_match_status: match_status$", column, " must be finite")
    }
  }
  if (nrow(out) && any(out$status_at > out$available_at)) {
    stop("n7_validate_match_status: a status event time after its availability ",
         "instant is impossible; the report cannot be observed before it happens")
  }
  # The declared composite key is enforced on TYPED columns. Formatting the instant
  # to a string would collapse two distinct observations into one and would also
  # hide a duplicate that differs only in sub-second precision.
  if (nrow(out) && anyDuplicated(out[c("issue_id", "fixture_id", "available_at")])) {
    stop("n7_validate_match_status: duplicate key (issue_id, fixture_id, ",
         "available_at); one observed report per match and availability instant")
  }
  if (!is.null(fixtures)) {
    if (!is.data.frame(fixtures)) {
      stop("n7_validate_match_status: fixtures must be a data frame")
    }
    unknown <- dplyr::anti_join(out, fixtures, by = c("issue_id", "fixture_id"))
    if (nrow(unknown)) {
      pairs <- unique(paste(unknown$issue_id, unknown$fixture_id, sep = "/"))
      stop("n7_validate_match_status: match_status references match(es) that are ",
           "not in fixtures: ", paste(pairs, collapse = ", "))
    }
  }
  out
}

#' 选择每场比赛在 cutoff 之前最新的可见状态
#'
#' 这是决策侧关于比赛可见性的**唯一**实现：所有从 fixtures 出发的决策都必须经过它。
#'
#' @param fixtures tibble，fixtures 表；每行一场比赛，强制 (issue_id, fixture_id)
#'   唯一键。空表合法。
#' @param match_status tibble，n7_validate_match_status() 接受的台账。**必填**：
#'   NULL -> stop()（缺失台账是输入契约错误，不是"没有可见状态"，不得回退）。
#' @param cutoff temporal_learning 对象，经 n7_require_cutoff 校验。
#' @return list(fixtures, selected_status, exclusions)，均为 tibble：
#'   · fixtures        被 admitted 的比赛（原样列集合，零行时为 typed-empty）
#'   · selected_status 每场一行：issue_id, fixture_id, status, status_at,
#'                     available_at, source_url（被采纳的那条报告）
#'   · exclusions      每场被排除的比赛及其稳定原因
#' @details 规则严格按契约：
#'   1. 只有 available_at **严格早于** cutoff 的报告可见；
#'   2. 可见报告里再要求 status_at 也严格早于 cutoff（"源说这件事在 cutoff 之后
#'      才发生"不是 cutoff 当时可知的事实）；
#'   3. 每场取其可见报告中 available_at 最新的一条（同一时刻不可能有两条：见
#'      n7_validate_match_status 的重复键检查）；
#'   4. 只有 scheduled 被采纳，其余（live/finished/postponed/cancelled/abandoned/
#'      unknown）一律排除，原因是稳定的 'match status: <status>'；
#'   5. 没有可见报告时原因是 'no match status before cutoff'。
#'   finished 不等于已结算/已派彩：本函数从不读取赛果或派彩表。
#'
#'   关系键在**原始输入边界**上、对着**完整** fixtures 校验：调用方必须传完整帧
#'   （见 n7_read_inputs 与 n7_prepare_epoch）。本函数**不**用切片后的 fixtures
#'   去校验台账，因此"本期但被裁掉"的比赛不会被误报为未知比赛；同时，正因为
#'   关系校验已经由完整帧完成并保留在输入里，本函数也**不**再对切片做任何关系
#'   检查 —— 它只按复合键 (issue_id, fixture_id) 把与 fixtures 无关的台账行忽略。
n7_select_match_status <- function(fixtures, match_status, cutoff) {
  n7_require_cutoff(cutoff)
  if (is.null(match_status)) {
    stop("n7_select_match_status: match_status is required; a missing ledger is an ",
         "input-contract error, not an empty one")
  }
  n7_validate_table(fixtures, "fixtures", keys = c("issue_id", "fixture_id"))
  if (any(fixtures$issue_id != cutoff$issue_id)) {
    stop("n7_select_match_status: fixtures belong to issue(s) other than the cutoff issue")
  }
  ledger <- n7_validate_match_status(match_status)
  cutoff_utc <- n7_cutoff_utc(cutoff)
  exclusions <- list()
  note <- function(issue_id, fixture_id, reason) {
    exclusions[[length(exclusions) + 1L]] <<- tibble::tibble(
      scope = "match_status", issue_id = as.character(issue_id),
      fixture_id = as.character(fixture_id), reason = reason)
  }
  empty_selected <- tibble::tibble(
    issue_id = character(0), fixture_id = character(0), status = character(0),
    status_at = as.POSIXct(character(0), tz = "UTC"),
    available_at = as.POSIXct(character(0), tz = "UTC"),
    source_url = character(0))
  if (!nrow(fixtures)) {
    return(list(fixtures = n7_typed_empty("fixtures"), selected_status = empty_selected,
                exclusions = n7_typed_empty("exclusions")))
  }
  # Visible = strictly before the cutoff on BOTH instants. A report whose event time
  # is still in the future was not knowable at the cutoff, however early it arrived.
  visible <- ledger[ledger$available_at < cutoff_utc & ledger$status_at < cutoff_utc, ,
                    drop = FALSE]
  # Latest report per composite match identity. The typed key guarantees at most one
  # row per (issue_id, fixture_id, available_at), so "latest" is unambiguous.
  fixtures$..n7_order <- seq_len(nrow(fixtures))
  latest <- dplyr::inner_join(
    fixtures[, c("issue_id", "fixture_id", "..n7_order")], visible,
    by = c("issue_id", "fixture_id"), relationship = "many-to-many")
  if (nrow(latest)) {
    latest <- latest[order(latest$issue_id, latest$fixture_id, latest$available_at), ,
                     drop = FALSE]
    latest <- latest[!duplicated(latest[c("issue_id", "fixture_id")], fromLast = TRUE), ,
                     drop = FALSE]
    latest <- latest[order(latest$..n7_order), , drop = FALSE]
  }
  selected_status <- if (nrow(latest)) {
    latest[, c("issue_id", "fixture_id", "status", "status_at", "available_at",
               "source_url"), drop = FALSE]
  } else {
    empty_selected
  }
  # The decision itself is a left join so a fixture with no visible report is still
  # accounted for, with a stable reason.
  verdict <- dplyr::left_join(fixtures[, c("issue_id", "fixture_id", "..n7_order")],
                             latest[, c("issue_id", "fixture_id", "status"), drop = FALSE],
                             by = c("issue_id", "fixture_id"))
  verdict <- verdict[order(verdict$..n7_order), , drop = FALSE]
  admitted <- !is.na(verdict$status) & verdict$status == "scheduled"
  for (i in seq_len(nrow(verdict))) {
    if (admitted[i]) next
    reason <- if (is.na(verdict$status[i])) {
      "no match status before cutoff"
    } else {
      paste0("match status: ", verdict$status[i])
    }
    note(verdict$issue_id[i], verdict$fixture_id[i], reason)
  }
  list(
    fixtures = fixtures[admitted, , drop = FALSE][, setdiff(names(fixtures), "..n7_order")],
    selected_status = selected_status,
    exclusions = if (length(exclusions)) dplyr::bind_rows(exclusions) else n7_typed_empty("exclusions"))
}
