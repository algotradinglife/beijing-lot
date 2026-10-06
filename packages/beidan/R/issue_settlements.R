#' 采集当前一期已经开奖的真实让球胜平负结算
#'
#' @param schedule tibble，至少含 issue_id、slot、fixture_key、provider_id_nowscore、handicap；
#'   同一期每场一行，fixture_key 为期号:场号。身份与让球必须和结算来源一致。
#' @param raw_dir 原始响应落盘目录，非空字符串。每次创建独立快照目录。
#' @param backend [python_backend()] 的显式 Python 句柄。
#' @param timeout 正有限秒数，默认25。
#' @param retries 非负整数，额外重试次数，默认2。
#' @param pages NULL 表示联网；离线回放用 list(body=原始raw字节,
#'   observed_at=带时区ISO8601原始采集时间)。不得把旧响应标为当前采集。
#' @return settlements 契约 tibble，包含 issue_id、fixture_id、outcome(W/D/L或ALL)、
#'   settled_sp、label_available_at(北京时间POSIXct)、status、source_url。
#'   普通未完场或未有唯一开奖SP不产生结算行；取消且停售、来源明确列出
#'   胜平负三个SP均为1时输出 status=all_options_one、outcome=ALL，
#'   不计预测命中。空结果保持列类型。
#'   match_results 属性为独立赛果 tibble：issue_id、fixture_id、outcome(W/D/L)、
#'   result_available_at(实际观测北京时间)、source_url；SP未发布也可有赛果。
#'   diagnostics 属性记录未接纳原因，receipt_path 属性记录原始证据回执位置。
#' @details 不推断开奖发布时间；label_available_at 为实际观测时刻。
#'   原始响应先持久化再解析。调用会联网及写文件，导入无副作用。
#'   不使用参考SP或人工SP调整值进行结算，不推定取消比赛退款。
#' @export
fetch_issue_settlements <- function(schedule, raw_dir, backend, timeout = 25,
                                    retries = 2L, pages = NULL) {
  if (!tibble::is_tibble(schedule)) stop("schedule must be a tibble")
  required <- c("issue_id", "slot", "fixture_key", "provider_id_nowscore", "handicap")
  checkmate::assert_subset(required, names(schedule))
  if (!nrow(schedule)) stop("schedule must contain at least one fixture")
  for (column in c("issue_id", "fixture_key", "provider_id_nowscore")) {
    checkmate::assert_character(schedule[[column]], any.missing = FALSE, min.chars = 1)
  }
  checkmate::assert_integerish(schedule$slot, lower = 1, any.missing = FALSE)
  checkmate::assert_numeric(schedule$handicap, any.missing = FALSE, finite = TRUE)
  checkmate::assert_string(raw_dir, min.chars = 1, na.ok = FALSE)
  checkmate::assert_number(timeout, lower = .Machine$double.eps, finite = TRUE)
  checkmate::assert_count(retries)
  if (!inherits(backend, "python_backend")) stop("backend must be a python_backend")
  if (!is.null(pages)) {
    checkmate::assert_names(names(pages), permutation.of = c("body", "observed_at"))
    if (!is.raw(pages$body)) stop("pages$body must be raw")
    checkmate::assert_string(pages$observed_at, min.chars = 1, na.ok = FALSE)
  }
  module <- reticulate::import_from_path("beidan_backend.settlement", path = backend$root,
                                          convert = FALSE)
  actual <- reticulate::py_to_r(module$`__file__`)
  expected <- file.path(backend$root, "beidan_backend", "settlement", "__init__.py")
  if (!identical(normalizePath(actual), normalizePath(expected))) {
    stop("settlement backend loaded from another location")
  }
  rows <- lapply(seq_len(nrow(schedule)), function(i) {
    row <- as.list(schedule[i, required]); row$slot <- as.integer(row$slot); row
  })
  result <- module$fetch_issue_settlements(rows, raw_dir, timeout = timeout,
    retries = as.integer(retries), pages = if (is.null(pages)) NULL else issue_schedule_pages_dict(pages))
  payload <- reticulate::py_to_r(result)
  out <- match_typed_empty("settlements")
  out$label_available_at <- lubridate::with_tz(out$label_available_at, "Asia/Shanghai")
  if (length(payload$settlements)) {
    out <- dplyr::bind_rows(payload$settlements)
    out$settled_sp <- as.double(out$settled_sp)
    out$label_available_at <- lubridate::with_tz(
      lubridate::ymd_hms(out$label_available_at, quiet = TRUE), "Asia/Shanghai")
    if (anyNA(out$label_available_at)) stop("invalid observed timestamp")
  }
  observed_results <- match_typed_empty("match_results")
  if (length(payload$match_results)) {
    observed_results <- dplyr::bind_rows(payload$match_results)
    observed_results$result_available_at <- lubridate::with_tz(
      lubridate::ymd_hms(observed_results$result_available_at, quiet = TRUE), "Asia/Shanghai")
    if (anyNA(observed_results$result_available_at)) stop("invalid result observed timestamp")
  }
  match_validate_table(observed_results,"match_results")
  attr(out, "match_results") <- observed_results
  attr(out, "diagnostics") <- if (length(payload$diagnostics)) dplyr::bind_rows(payload$diagnostics) else
    tibble::tibble(issue_id = character(), fixture_id = character(), reason = character())
  attr(out, "receipt_path") <- payload$receipt_path
  out
}
