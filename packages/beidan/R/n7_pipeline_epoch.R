#' N7 管道的决策 epoch 准备与市场概率投影
#'
#' n7_prepare_epoch 把赛前的原始报价整理成每场一组被选中的报价。
#' n7_project_probabilities 通过既有的 DC + 普通欧赔 + 大小球主路径把它变成
#' 比分模型概率。两个函数都不拟合历史、不抓取、不读赛果。
#'
#' @details 本模块只定义函数，导入时不触发任何 I/O，也不访问数据库。

#' 香港盘净赔率 -> 十进制赔率
#'
#' @param water 数值向量，香港盘净赔率（>= 0）。允许零长度。
#'   · 非数值           -> stop()
#'   · 含 NA / 非有限   -> stop()
#'   · 负值             -> stop()
#' @return 数值向量，等于 1 + water。
#' @details 大小球市场在部分源上是香港盘水位、在另一些上是十进制赔率。契约要求
#'   调用方明说是哪一种，因为猜错会静默地把每个 lambda 重新缩放。香港盘 0 表示
#'   平赔，负的净赔率根本不是价格，接受它会静默把市场定错价。
n7_hk_to_decimal <- function(water) {
  if (!is.numeric(water)) stop("n7_hk_to_decimal: water must be numeric")
  if (anyNA(water) || any(!is.finite(water))) {
    stop("n7_hk_to_decimal: water must be finite and not NA")
  }
  # HK water is a net price: 0 means an even-money return, and a negative net price
  # is not a price at all. Accepting it would silently price the market wrong.
  if (any(water < 0)) {
    stop("n7_hk_to_decimal: HK water must be non-negative; got ",
         format(min(water), scientific = FALSE))
  }
  1 + water
}

#' 按调用方声明的约定把水位/赔率转成十进制
#'
#' @param value       数值向量。允许零长度。
#'   · 非数值                  -> stop()
#'   · 含 NA / 非有限          -> stop()（坏源不得变成静默的 NA 价格）
#'   · convention="decimal" 时出现 <= 0 -> stop()
#' @param convention  长度 1 的字符，取值 "decimal" 或 "hk"。其它值 -> stop()。
#' @param what        长度 1 的非空字符标签。
#' @return 数值向量。
n7_convert_water <- function(value, convention, what) {
  if (!is.character(what) || length(what) != 1L || is.na(what) || !nzchar(what)) {
    stop("n7_convert_water: what must be one non-empty label")
  }
  if (!is.character(convention) || length(convention) != 1L || is.na(convention)) {
    stop("n7_convert_water: ", what, " convention must be one string")
  }
  if (!is.numeric(value)) stop("n7_convert_water: ", what, " must be numeric")
  # NA and unparseable text must not become a silent NA price; converting a bad
  # feed into a missing value would hide the bad feed from the caller.
  if (anyNA(value) || any(!is.finite(as.double(value)))) {
    stop("n7_convert_water: ", what, " must be finite and not NA")
  }
  if (identical(convention, "decimal")) {
    if (any(value <= 0)) stop("n7_convert_water: ", what, " decimal odds must be positive")
    return(as.double(value))
  }
  if (identical(convention, "hk")) return(n7_hk_to_decimal(as.double(value)))
  stop("n7_convert_water: ", what, " convention must be 'decimal' or 'hk', got ", convention)
}

#' 取每个键在 cutoff 之前最后一条报价
#'
#' @param quotes         data.frame，必须含 quote_at（POSIXct）与 value_columns。
#'   · 非 data.frame -> stop()
#'   · 0 行          -> 原样返回
#' @param cutoff_utc     长度 1 的非 NA POSIXct。
#'   · 非 POSIXct -> stop()（否则与 POSIXct 比较时隐式强转并静默匹配不到任何行，
#'     使"缺报价"看起来像"市场很安静"）
#' @param value_columns  非空字符向量，参与冲突检查的列名。
#'   · 非字符 / 零长度 / 含 NA / 含空串 -> stop()
#' @return quotes 的子集，每个键只保留其最新时刻的那一行。
#' @details 同一时刻出现两个不同取值是真实的源冲突，按行序解决会让选择依赖于
#'   文件顺序，因此直接报错。冲突检查在去重之前进行——先去重恰好会丢掉这个守卫
#'   要抓的那一行。
n7_latest_quote_before <- function(quotes, cutoff_utc, value_columns) {
  # A non-POSIXct cutoff would be compared against POSIXct by implicit coercion and
  # silently match nothing, so a missing quote set would look like a quiet market.
  if (!inherits(cutoff_utc, "POSIXct")) {
    stop("n7_latest_quote_before: cutoff_utc must be POSIXct")
  }
  if (length(cutoff_utc) != 1L || is.na(cutoff_utc)) {
    stop("n7_latest_quote_before: cutoff_utc must be a single non-NA instant")
  }
  if (!is.character(value_columns) || !length(value_columns) || anyNA(value_columns) ||
      any(!nzchar(value_columns))) {
    stop("n7_latest_quote_before: value_columns must be non-empty column names")
  }
  if (!is.data.frame(quotes)) stop("n7_latest_quote_before: quotes must be a data frame")
  if (!nrow(quotes)) return(quotes)
  admitted <- quotes[quotes$quote_at < cutoff_utc, , drop = FALSE]
  if (!nrow(admitted)) return(quotes[0, , drop = FALSE])
  keys <- intersect(c("fixture_id", "company_id", "line", "outcome"), names(admitted))
  admitted <- admitted[order(admitted$quote_at), , drop = FALSE]

  # Conflict guard, applied BEFORE deduplication: two rows sharing a key and an
  # instant but disagreeing on a value are a genuine source conflict. Resolving
  # that by row order would make the selection depend on file order, so fail.
  key_id <- do.call(paste, c(unname(as.list(admitted[keys])), sep = "\r"))
  instant_id <- paste(key_id, format(admitted$quote_at, tz = "UTC", usetz = TRUE), sep = "\r")
  # NOTE: compare across ALL rows sharing an instant. Deduplicating first would
  # discard exactly the disagreeing row this guard exists to catch.
  for (column in value_columns) {
    conflict <- tapply(admitted[[column]], instant_id, function(v) length(unique(v)) > 1L)
    if (any(conflict)) {
      bad <- names(conflict)[which(conflict)[1]]
      stop("n7_latest_quote_before: conflicting ", column,
           " values at one instant for key ", bad)
    }
  }

  # Keep the latest instant per key; rows repeated at that instant agree, so
  # keeping the first is lossless.
  last_rows <- !duplicated(admitted[keys], fromLast = TRUE)
  selected <- admitted[last_rows, , drop = FALSE]
  selected
}

# Average euro odds across the policy's member companies, then de-vig.
#
# euro_policy$members lists the company_ids that participate, and
# euro_policy$missing says what to do when a member has no quote. Averaging only
# the companies that happen to be present would let the member set drift with
# coverage, which is exactly the defect the contract calls out, so the default is
# to fail and require an explicit rule.
#' 按 euro_policy 对成员公司的欧赔求均值并去水
#'
#' @param euro        tibble，euro 表（经 n7_validate_table 校验前的原始输入）。
#' @param cutoff_utc  长度 1 的非 NA POSIXct。
#' @param policy      list，必须含 members（唯一的公司 id 字符向量）。
#'   · 非 list                      -> stop()
#'   · members 非字符/零长度/有重复 -> stop()
#'   · missing 非 "error"/"drop_member" -> stop()
#' @param fixtures    tibble，至少含 fixture_id；决定输出行序。
#' @return tibble，每场一行：fixture_id, odds_home, odds_draw, odds_away, n_members。
#' @details euro_policy$members 列出参与的公司，euro_policy$missing 声明成员缺报价
#'   时的行为。完全没有报价算"cutoff 前没有报价"，不算成员集违规；只有成员集被
#'   部分覆盖才是需要由策略决定的那种缺陷。
n7_euro_mean <- function(euro, cutoff_utc, policy, fixtures) {
  if (!is.list(policy)) stop("n7_euro_mean: euro_policy must be a list")
  members <- policy$members
  missing_rule <- if (is.null(policy$missing)) "error" else policy$missing
  if (!is.character(members) || !length(members) || anyDuplicated(members)) {
    stop("n7_euro_mean: euro_policy$members must be unique company ids")
  }
  if (!missing_rule %in% c("error", "drop_member")) {
    stop("n7_euro_mean: euro_policy$missing must be 'error' or 'drop_member'")
  }
  selected <- n7_latest_quote_before(euro, cutoff_utc,
                                     c("odds_home", "odds_draw", "odds_away"))
  selected <- selected[selected$company_id %in% members, , drop = FALSE]
  fixture_ids <- fixtures$fixture_id
  result <- tibble::tibble(
    fixture_id = fixture_ids,
    odds_home = rep(NA_real_, length(fixture_ids)),
    odds_draw = rep(NA_real_, length(fixture_ids)),
    odds_away = rep(NA_real_, length(fixture_ids)),
    n_members = rep(0L, length(fixture_ids)))
  for (i in seq_along(fixture_ids)) {
    rows <- selected[selected$fixture_id == fixture_ids[i], , drop = FALSE]
    present <- sort(unique(rows$company_id))
    # No quotes at all is "no quote before cutoff", not a member-set violation.
    # Only a partially covered member set is the defect the policy must decide.
    if (!length(present)) next
    if (missing_rule == "error" && !setequal(present, members)) {
      stop("n7_euro_mean: fixture ", fixture_ids[i], " is missing euro members ",
           paste(setdiff(members, present), collapse = ", "))
    }
    if (!length(present)) next
    # Conflict guard: one value per member at the selected instant.
    for (company in present) {
      rows_c <- rows[rows$company_id == company, , drop = FALSE]
      if (nrow(rows_c) > 1L &&
          (length(unique(rows_c$odds_home)) > 1L || length(unique(rows_c$odds_draw)) > 1L ||
           length(unique(rows_c$odds_away)) > 1L)) {
        stop("n7_euro_mean: conflicting euro quotes for fixture ", fixture_ids[i],
             " company ", company)
      }
    }
    result$odds_home[i] <- mean(rows$odds_home)
    result$odds_draw[i] <- mean(rows$odds_draw)
    result$odds_away[i] <- mean(rows$odds_away)
    result$n_members[i] <- length(present)
  }
  result
}

# Select totals quotes under totals_policy: which companies, which line.
#' 按 totals_policy 选择大小球报价
#'
#' @param totals      tibble，totals 表。
#' @param cutoff_utc  长度 1 的非 NA POSIXct。
#' @param policy      list。
#'   · 非 list                          -> stop()
#'   · companies 非字符或有重复          -> stop()
#'   · watermark 缺省                    -> stop()
#'   · line 非 "nearest_main" 且非数值   -> stop()
#' @param fixtures    tibble，提供 fixture_id 与 handicap。
#' @return totals 表的子集（0 行时为该表的 typed-empty）。
#' @details line = "nearest_main" 时取跨公司出现最多的盘口，并列时取低盘；
#'   line 为数值时取该盘口。水位按 watermark 声明的约定转换。
n7_totals_selected <- function(totals, cutoff_utc, policy, fixtures) {
  if (!is.list(policy)) stop("n7_totals_selected: totals_policy must be a list")
  companies <- policy$companies
  if (!is.null(companies) && (!is.character(companies) || anyDuplicated(companies))) {
    stop("n7_totals_selected: totals_policy$companies must be unique company ids")
  }
  line_rule <- if (is.null(policy$line)) "nearest_main" else policy$line
  # Validate the line rule up front: inside the per-fixture loop it would only be
  # reached when at least one fixture survives, so an empty or fully-filtered input
  # would silently accept an invalid policy.
  if (!identical(line_rule, "nearest_main") &&
      !(is.numeric(line_rule) && length(line_rule) == 1L && !is.na(line_rule))) {
    stop("n7_totals_selected: totals_policy$line must be 'nearest_main' or a number")
  }
  watermark <- policy$watermark
  if (is.null(watermark)) stop("n7_totals_selected: totals_policy$watermark is required")
  if (!is.character(watermark) || length(watermark) != 1L || is.na(watermark) ||
      !watermark %in% c("decimal", "hk")) {
    stop("n7_totals_selected: totals_policy$watermark must be 'decimal' or 'hk'")
  }
  selected <- n7_latest_quote_before(totals, cutoff_utc,
                                     c("over_decimal", "under_decimal"))
  if (!is.null(companies)) {
    selected <- selected[selected$company_id %in% companies, , drop = FALSE]
  }
  result <- n7_typed_empty("totals")
  rows <- list()
  for (fixture_id in fixtures$fixture_id) {
    rows_f <- selected[selected$fixture_id == fixture_id, , drop = FALSE]
    if (!nrow(rows_f)) next
    if (identical(line_rule, "nearest_main")) {
      # The most common line across companies is the main line; ties break low.
      counts <- table(rows_f$line)
      best <- as.numeric(names(counts)[which.max(counts)])
      rows_f <- rows_f[rows_f$line == best, , drop = FALSE]
    } else if (is.numeric(line_rule)) {
      rows_f <- rows_f[rows_f$line == line_rule, , drop = FALSE]
      if (!nrow(rows_f)) next
    } else {
      stop("n7_totals_selected: totals_policy$line must be 'nearest_main' or a number")
    }
    rows_f$over_decimal <- n7_convert_water(rows_f$over_decimal, watermark, "over")
    rows_f$under_decimal <- n7_convert_water(rows_f$under_decimal, watermark, "under")
    rows[[length(rows) + 1L]] <- rows_f[, names(result), drop = FALSE]
  }
  if (length(rows)) result <- dplyr::bind_rows(rows)
  result
}

#' 准备一个决策 epoch 的输入
#'
#' @param inputs         list，含 fixtures/euro/totals/prematch_sp/match_status 五张表
#'   （通常来自 n7_read_inputs）。每张表经 n7_validate_table 校验。
#'   match_status 是**必填**台账：缺失即输入契约错误（stop()），不得回退到任何
#'   其它可见性来源；typed-empty 台账合法，它表示没有可见状态、因而排除全部比赛。
#' @param cutoff         temporal_learning 对象，经 n7_require_cutoff 校验。
#' @param tz             决策日边界时区，必须等于 N7_DECISION_TZ。
#'   · 其它取值 -> stop()（本管道的决策日边界是固定的）
#' @param euro_policy    欧赔策略，语义见 n7_euro_mean。
#' @param totals_policy  大小球策略，语义见 n7_totals_selected。
#'
#' @return list(fixtures, euro_mean, totals_selected, sp_selected, match_status,
#'   status_selected, exclusions)，每项为 tibble。
#'   · match_status     输入台账的原样保留，供下游（投影）重新校验
#'   · status_selected  被采纳的那条 scheduled 报告，每场一行
#' @details 决策 epoch 是本地日 D 的 20:00 Asia/Shanghai，窗口是整个 D+1。
#'   只有当开赛落在该窗口内、cutoff 之前存在可用欧赔报价、**且 cutoff 当时可见的
#'   最新状态是 scheduled** 时，比赛才会被保留。被剔除的比赛连同原因记入
#'   exclusions 表，因此剔除是可审计的而不是静默的。
#'
#'   期号绑定：一个 epoch 就是一期。携带其它 issue_id 的比赛会被拒绝，
#'   否则它会在错误的决策日下被定价、分组、买入。
#'
#'   可见性判断全部委托给唯一的共享选择器 n7_select_match_status()：本函数不自己
#'   比较 status、也不读 fixtures$sale_state。sale_state 是售卖通道状态，与比赛
#'   是否发生是两件事，用前者替代后者会在比赛被取消时仍然开卖。
n7_prepare_epoch <- function(inputs, cutoff, tz = N7_DECISION_TZ,
                             euro_policy, totals_policy) {
  n7_require_cutoff(cutoff)
  if (!identical(tz, N7_DECISION_TZ)) {
    stop("n7_prepare_epoch: this pipeline's decision day boundary is ", N7_DECISION_TZ)
  }
  cutoff_utc <- n7_cutoff_utc(cutoff)
  fixtures_all <- n7_validate_table(inputs$fixtures, "fixtures",
                                    keys = c("issue_id", "fixture_id"))
  euro <- n7_validate_table(inputs$euro, "euro")
  totals <- n7_validate_table(inputs$totals, "totals")
  sp <- n7_validate_table(inputs$prematch_sp, "prematch_sp")
  # Missing is an input-contract error; an empty ledger is a legitimate observation
  # of "nothing was visible" and must not be confused with the former.
  if (is.null(inputs$match_status)) {
    stop("n7_prepare_epoch: inputs$match_status is required; a missing status ledger ",
         "is an input-contract error, not an empty one")
  }
  match_status <- n7_validate_match_status(inputs$match_status, fixtures = fixtures_all)

  exclusions <- list()
  note <- function(fixture_id, reason) {
    exclusions[[length(exclusions) + 1L]] <<- tibble::tibble(
      scope = "epoch", issue_id = cutoff$issue_id,
      fixture_id = as.character(fixture_id), reason = reason)
  }

  # Issue binding: one epoch is one issue. A fixture carrying a different issue_id
  # would otherwise be priced, grouped and bought under the wrong decision day.
  stray <- setdiff(unique(fixtures_all$issue_id), cutoff$issue_id)
  if (length(stray)) {
    stop("n7_prepare_epoch: fixtures carry issue_id ",
         paste(stray, collapse = ", "), " but the cutoff is bound to '",
         cutoff$issue_id, "'")
  }

  # Window filter. n7_decision_window owns the day-boundary rule and speaks
  # ISO-8601 UTC strings, so convert at the boundary rather than duplicating it.
  window <- n7_decision_window(n7_utc_iso(as.numeric(cutoff_utc), "cutoff"), tz)
  window_start <- n7_parse_utc(window$start_utc, "window$start_utc")
  window_end <- n7_parse_utc(window$end_utc, "window$end_utc")
  in_window <- fixtures_all$kickoff_at >= window_start & fixtures_all$kickoff_at < window_end
  fixtures <- fixtures_all[in_window, , drop = FALSE]
  for (fixture_id in fixtures_all$fixture_id[!in_window]) {
    note(fixture_id, "kickoff outside decision window")
  }

  # Visibility: the ONE shared selector decides which fixtures had a visible
  # scheduled status at the cutoff.
  #
  # The window filter runs FIRST, so `fixtures` here is already a slice. Relation
  # keys were validated at the raw input boundary (n7_read_inputs) against the FULL
  # fixture frame, and that validation is repeated above by
  # n7_validate_match_status(inputs$match_status, fixtures = fixtures_all). The
  # selector itself therefore never re-derives a relation from the slice: a ledger
  # row for a fixture this epoch dropped is simply ignored, not reported as unknown.
  status <- n7_select_match_status(fixtures, match_status, cutoff)
  if (nrow(status$exclusions)) {
    for (i in seq_len(nrow(status$exclusions))) {
      exclusions[[length(exclusions) + 1L]] <- tibble::tibble(
        scope = "epoch", issue_id = status$exclusions$issue_id[i],
        fixture_id = status$exclusions$fixture_id[i],
        reason = status$exclusions$reason[i])
    }
  }
  fixtures <- status$fixtures

  euro_mean <- n7_euro_mean(euro, cutoff_utc, euro_policy, fixtures)
  usable <- !is.na(euro_mean$odds_home)
  for (fixture_id in euro_mean$fixture_id[!usable]) {
    note(fixture_id, "no euro quote before cutoff")
  }
  fixtures <- fixtures[usable, , drop = FALSE]
  euro_mean <- euro_mean[usable, , drop = FALSE]

  selected_totals <- n7_totals_selected(totals, cutoff_utc, totals_policy, fixtures)
  selected_sp <- n7_latest_quote_before(sp, cutoff_utc, c("sp_raw"))

  list(fixtures = fixtures, euro_mean = euro_mean,
       totals_selected = selected_totals, sp_selected = selected_sp,
       match_status = match_status, status_selected = status$selected_status,
       exclusions = if (length(exclusions)) dplyr::bind_rows(exclusions) else n7_typed_empty("exclusions"))
}

# n7_project_probabilities(epoch_inputs, cutoff, rho, total_bounds, tail_tolerance)
#   -> list(probabilities, fit, exclusions)
#
# Reuses the existing DC + ordinary euro + over/under main path
# (project_n7_market_inputs -> total_market_constraint -> total_constrained_projection).
# rho is supplied by the caller; -0.14 is the frozen project value but the function
# never defaults to it. A fixture whose over/under cannot be fitted is excluded with
# a reason rather than being silently priced from euro alone, because euro-only
# pricing is a different (and weaker) model that the contract forbids substituting.
#' 通过 DC + 欧赔 + 大小球主路径投影概率
#'
#' @param epoch_inputs  n7_prepare_epoch 的返回值。
#' @param cutoff        temporal_learning 对象。用于校验期号与 as-of 时刻。
#' @param rho           低比分相关参数，经 n7_validate_rho 校验。
#' @param total_bounds  长度 2 的数值向量，总进球的下界与上界。
#' @param tail_tolerance 数值，尾概率容差。
#'
#' @return list(probabilities, fit)，均为已校验 tibble。
#'   probabilities 每场 3 行（W/D/L），fit 每场 1 行。
#' @details 只有开赛落在决策窗口内、且报价严格早于 cutoff 的比赛才参与投影；
#'   每场比赛的 issue_id 必须与 cutoff 绑定的期号一致。投影失败的比赛连同原因
#'   记入 fit 表，而不是被静默跳过。
#'
#'   投影边界再次用 epoch_inputs$match_status 保留的历史台账校验可见性：直接调用
#'   本函数（绕过 n7_prepare_epoch）时，任何在**本** cutoff 当时不可见或非
#'   scheduled 的比赛都必须报错，而不是被照常定价——那会让调用方拿别的时刻的
#'   选择结果给现在定价。
#'
#'   瑞典盘三项为决策三元组；普通 W/D/L 仅作为诊断信息挂在 fit 表上，
#'   绝不作为投注赛果使用。
n7_project_probabilities <- function(epoch_inputs, cutoff, rho, total_bounds,
                                     tail_tolerance) {
  n7_require_cutoff(cutoff)
  n7_validate_rho(rho)
  if (length(total_bounds) != 2L || any(!is.finite(total_bounds)) ||
      total_bounds[1] <= 0 || total_bounds[2] <= total_bounds[1]) {
    stop("n7_project_probabilities: total_bounds must be an increasing positive pair")
  }
  if (length(tail_tolerance) != 1L || !is.finite(tail_tolerance) ||
      tail_tolerance <= 0 || tail_tolerance >= 1) {
    stop("n7_project_probabilities: tail_tolerance must lie strictly in (0,1)")
  }
  fixtures <- epoch_inputs$fixtures
  euro_mean <- epoch_inputs$euro_mean
  totals <- epoch_inputs$totals_selected

  # Re-validate chronology at the projection boundary. prepare_epoch already
  # filtered, but this function is public and can be handed an epoch directly, so
  # every quote it consumes is checked against the cutoff again. Failing open would
  # let a post-cutoff price price a pre-cutoff decision.
  cutoff_bound <- n7_cutoff_utc(cutoff)
  # euro_mean is an aggregate per fixture, so its own chronolgy is checked at
  # selection time in n7_prepare_epoch; the selected quotes and totals carry their
  # instants and are checked here.
  if (nrow(totals) && any(totals$quote_at >= cutoff_bound)) {
    stop("n7_project_probabilities: over/under quotes at or after the cutoff are not admissible")
  }
  if (nrow(fixtures) && any(fixtures$kickoff_at <= cutoff_bound)) {
    stop("n7_project_probabilities: fixtures already kicked off at the cutoff are not admissible")
  }
  # A direct projection call must be as bound to its issue as a prepared epoch is.
  # Another issue's fixtures cannot be priced against this issue's cutoff.
  if (nrow(fixtures) && "issue_id" %in% names(fixtures)) {
    stray <- setdiff(unique(as.character(fixtures$issue_id)),
                     as.character(cutoff$issue_id))
    if (length(stray)) {
      stop("n7_project_probabilities: fixtures belong to issue(s) ",
           paste(stray, collapse = ", "), ", not ", cutoff$issue_id)
    }
  }
  # Re-validate the fixtures against the RETAINED status history. Handing the same
  # fixtures a second, later cutoff would otherwise let a fixture whose visible
  # status was `cancelled` be projected anyway: the selection happened in
  # prepare_epoch against a different instant, and this function is public.
  # The ledger is schema-validated first; the relation to fixtures is intentionally
  # NOT re-derived here: prepare_epoch sliced fixtures before selecting, so `fixtures`
  # is a subset of the frame the ledger was validated against at the input boundary.
  # Joining the full ledger's keys against this slice would manufacture a false
  # "unknown match" for every fixture the epoch legitimately dropped.
  if (nrow(fixtures)) {
    if (is.null(epoch_inputs$match_status)) {
      stop("n7_project_probabilities: epoch_inputs$match_status is required to ",
           "revalidate fixture visibility at this cutoff")
    }
    revalidated <- n7_select_match_status(
      fixtures, n7_validate_match_status(epoch_inputs$match_status), cutoff)
    if (nrow(revalidated$exclusions)) {
      stop("n7_project_probabilities: fixture(s) are not visible as scheduled at ",
           "this cutoff: ",
           paste(paste0(revalidated$exclusions$fixture_id, " (",
                        revalidated$exclusions$reason, ")"), collapse = "; "))
    }
  }

  probabilities <- list()
  fits <- list()
  exclusions <- list()
  note <- function(fixture_id, reason) {
    exclusions[[length(exclusions) + 1L]] <<- tibble::tibble(
      scope = "projection", issue_id = cutoff$issue_id,
      fixture_id = as.character(fixture_id), reason = reason)
  }

  if (!nrow(fixtures)) {
    return(list(probabilities = n7_typed_empty("probabilities"),
                fit = n7_typed_empty("fit"),
                exclusions = n7_typed_empty("exclusions")))
  }

  for (i in seq_len(nrow(fixtures))) {
    fixture_id <- fixtures$fixture_id[i]
    row <- euro_mean[euro_mean$fixture_id == fixture_id, , drop = FALSE]
    quotes <- totals[totals$fixture_id == fixture_id, , drop = FALSE]
    if (!nrow(quotes)) {
      note(fixture_id, "no over/under quote before cutoff")
      next
    }
    inverse <- 1 / as.numeric(row[1, c("odds_home", "odds_draw", "odds_away")])
    target <- inverse / sum(inverse)
    constraint <- tryCatch(
      total_market_constraint(
        # total_market_constraint inverts HK water as 1/(1+water). The selected
        # columns are already decimal, so hand it the HK equivalent, not the
        # decimal price: passing decimal here adds one a second time.
        data.frame(company = quotes$company_id, line = quotes$line,
                   over_hk = quotes$over_decimal - 1,
                   under_hk = quotes$under_decimal - 1,
                   stringsAsFactors = FALSE),
        total_bounds),
      error = function(e) e)
    if (inherits(constraint, "error")) {
      note(fixture_id, paste0("over/under fit failed: ", conditionMessage(constraint)))
      next
    }
    projection <- tryCatch(
      total_constrained_projection(constraint$lambda_total, target,
                                   fixtures$handicap[i], tail_tolerance, rho),
      error = function(e) e)
    if (inherits(projection, "error")) {
      note(fixture_id, paste0("projection failed: ", conditionMessage(projection)))
      next
    }
    fields <- projection$fields
    # The handicap triple is the decision triple; ordinary W/D/L is carried on the
    # fit table for diagnostics only and must never be used as a bet outcome.
    triple <- c(W = fields$W, D = fields$D, L = fields$L)
    if (any(!is.finite(triple)) || abs(sum(triple) - 1) > 1e-6) {
      note(fixture_id, "projected triple is not a valid probability")
      next
    }
    for (outcome in n7_outcomes()) {
      probabilities[[length(probabilities) + 1L]] <- tibble::tibble(
        fixture_id = fixture_id, outcome = outcome, probability = unname(triple[outcome]))
    }
    fits[[length(fits) + 1L]] <- tibble::tibble(
      fixture_id = fixture_id,
      lambda_home = fields$lambda_home,
      lambda_away = fields$lambda_away,
      rho = fields$low_score_dependence_rho,
      residual = fields$market_residual,
      status = "fitted")
  }
  list(
    probabilities = if (length(probabilities)) {
      n7_validate_table(dplyr::bind_rows(probabilities), "probabilities",
                        keys = c("fixture_id", "outcome"))
    } else n7_typed_empty("probabilities"),
    fit = if (length(fits)) {
      n7_validate_table(dplyr::bind_rows(fits), "fit", keys = "fixture_id")
    } else n7_typed_empty("fit"),
    exclusions = if (length(exclusions)) {
      dplyr::bind_rows(exclusions)
    } else n7_typed_empty("exclusions"))
}

# Dixon-Coles rho guard. Re-declared here only if the grid module is not loaded,
# so this file stays usable on its own in tests.
if (!exists("dc_validate_rho", mode = "function")) {
  dc_validate_rho <- function(rho) {
    if (length(rho) != 1L || !is.numeric(rho) || is.na(rho) || !is.finite(rho)) {
      stop("Invalid rho")
    }
    if (rho <= -1 || rho >= 1) stop("Invalid rho")
    invisible(rho)
  }
}
#' 校验 Dixon-Coles 的低比分相关参数 rho
#'
#' @param rho 长度 1 的有限数值，必须落在 dc_validate_rho 接受的范围内。
#' @return rho 本身（经底层校验后返回）。
#' @details 委托给既有实现，不在此重复声明合法区间，避免两处定义漂移。
n7_validate_rho <- function(rho) dc_validate_rho(rho)
