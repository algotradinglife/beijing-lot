#' N7 管道的确定性合成夹具（用于契约与端到端测试）
#'
#' 构造一个完整且自洽的赛前世界：fixtures、欧赔报价、大小球报价、赛前 SP。
#' 它是显式合成的，每条生成的行都带一个标明这一点的 source_url，因此夹具结果
#' 绝不会被误当成实测。确定性来自本地带种子的 RNG；不联网、不访问数据库。
#'
#' @details 本模块只定义函数，导入时不触发任何 I/O。

#' 生成行的 source_url 上携带的合成标记
#'
#' @param kind  长度 1 的非空字符，数据种类（fixture/euro/totals/sp）。
#' @param key   非空字符向量（可为长度 >1，键是向量化的），该行在其种类内的键。
#'   · 非字符 / 零长度 / 含 NA / 含空串 -> stop()
#' @return 字符向量，形如 synthetic://n7-pipeline/<kind>/<key>。
#' @details 前缀固定为 synthetic://，使任何下游都能一眼分辨合成数据与实测数据。
n7_fixture_source_url <- function(kind, key) {
  if (!is.character(kind) || length(kind) != 1L || is.na(kind) || !nzchar(kind)) {
    stop("n7_fixture_source_url: kind must be one non-empty label")
  }
  # Vectorised over key: see the note on the key check below.
  # key is vectorised: callers build it with sprintf() over a slot vector so the
  # whole column is produced in one tibble() expression. Require non-empty
  # strings, not a scalar.
  if (!is.character(key) || !length(key) || anyNA(key) || any(!nzchar(key))) {
    stop("n7_fixture_source_url: key must be non-empty label(s)")
  }
  paste0("synthetic://n7-pipeline/", kind, "/", key)
}

#' 构造一期的合成夹具
#'
#' kickoff_at 的每个元素生成一场比赛，因此一期可以跨多个比赛日。每场获得一个让球数、
#' 一个真实底层 W/D/L 三元组、一组欧赔报价、若干盘口的大小球报价，以及一个赛前 SP
#' 三元组。概率先生成、赔率由概率导出，因此夹具自洽。
#'
#' @details 自洽的准确含义：赔率按 margin 加水位，故隐含概率之和精确等于 margin；
#'   对欧赔去水得到的是每家公司各自的 noisy 三元组（以 truth 为中心），而**不是**
#'   truth 本身。truth 是底层参数，赔率是围绕它的抽样。因此不要断言"去水还原 truth"。
#'
#' @param issue_id     长度 1 的合法字符标识符（经 n7_check_character_id）。
#'   · 长度 != 1 -> stop()（本生成器只命名一期）
#' @param kickoff_at   非空、有限、非 NA 的 UTC POSIXct 向量。每个元素一场比赛。
#'   · 非 POSIXct / 零长度 / 含 NA / 非有限 -> stop()
#'   · 非 UTC 时区的 POSIXct 会被显式转换到 UTC 后再使用。
#' @param n_companies  长度 1 的正整数。<= 0、小数           -> stop()
#' @param seed         长度 1 的有限数值。
#' @param margin       长度 1 的正有限数值，用于给赔率加水位。
#'   · <= 0 会产出 Inf 赔率，NA 会产出 NA 赔率，两者都静默 -> stop()
#' @param match_status 长度 1 的字符，本期的比赛状态报告取值：scheduled（默认）
#'   或任意 n7_match_statuses() 中的非 scheduled 取值。
#'   · 非法取值 -> stop()
#'
#' @return list(fixtures, euro, totals, prematch_sp, match_status, truth)，前五张为
#'   tibble，truth 为 length(kickoff_at) x 3 的数值矩阵（行名 fixture_id，列名 W/D/L）。
#' @details 生成器**不推断决策 epoch**：kickoff_at 就是调用方声明的开赛时刻。
#'   报价与初始状态报告都取每场 kickoff_at - 36 小时，再叠加已声明的小幅公司错开，
#'   与任何 cutoff 无关 —— 因此跨日的整期读取能保留全部比赛日，而哪一天属于哪个
#'   决策窗口由 n7_prepare_epoch 独占决定。
#'
#'   match_status 是**显式合成**的观测台账：每场一条报告，status_at 等于 available_at
#'   （合成源同时报告事件与观测），绝不从任何真实赛果或最终记录推导 —— 否则测试会
#'   依赖"已知结果"而不是"当时看到了什么"。需要"事后观测"的测试自行 bind_rows 追加，
#'   从而显式表达"这条报告在 cutoff 之后才出现"。
n7_make_fixture_issue <- function(issue_id, kickoff_at, n_companies = 3L,
                                  seed = 1L, margin = 1.06,
                                  match_status = "scheduled") {
  n7_check_character_id(issue_id, "issue_id")
  # Exactly one issue: this generator names one issue, and a longer id would reach
  # tibble() and die there with a column-size error that names neither the argument
  # nor the cause.
  if (length(issue_id) != 1L) {
    stop("n7_make_fixture_issue: issue_id must name exactly one issue; got ",
         length(issue_id))
  }
  # kickoff_at is the explicit kickoff schedule. The fixture COUNT is derived from
  # it, not from a separate n_fixtures argument that could disagree with the vector.
  if (!inherits(kickoff_at, "POSIXct")) {
    stop("n7_make_fixture_issue: kickoff_at must be a POSIXct vector")
  }
  if (!length(kickoff_at)) {
    stop("n7_make_fixture_issue: kickoff_at must not be empty; it names the fixtures")
  }
  if (anyNA(kickoff_at)) {
    stop("n7_make_fixture_issue: kickoff_at must not be NA")
  }
  if (any(!is.finite(as.numeric(kickoff_at)))) {
    stop("n7_make_fixture_issue: kickoff_at must be finite")
  }
  # A non-UTC vector is converted explicitly rather than relabelled: the instant is
  # preserved, only the zone attribute changes, and the contract requires UTC.
  kickoff_utc <- lubridate::with_tz(kickoff_at, "UTC")
  if (!is.numeric(n_companies) || length(n_companies) != 1L || is.na(n_companies) ||
      !is.finite(n_companies) || n_companies != floor(n_companies) || n_companies < 1) {
    stop("n7_make_fixture_issue: n_companies must be one positive whole number")
  }
  # margin overrounds the odds, so it must be strictly positive and finite;
  # margin = 0 yields Inf odds and margin = NA yields NA odds, both silently.
  if (!is.numeric(margin) || length(margin) != 1L || is.na(margin) ||
      !is.finite(margin) || margin <= 0) {
    stop("n7_make_fixture_issue: margin must be one positive finite number")
  }
  if (!is.numeric(seed) || length(seed) != 1L || is.na(seed) || !is.finite(seed)) {
    stop("n7_make_fixture_issue: seed must be one finite number")
  }
  if (!is.character(match_status) || length(match_status) != 1L ||
      is.na(match_status) || !match_status %in% n7_match_statuses()) {
    stop("n7_make_fixture_issue: match_status must be one of ",
         paste(n7_match_statuses(), collapse = ", "))
  }
  set.seed(seed)

  slot_values <- n7_check_slot(seq_along(kickoff_utc), "kickoff_at")
  company_ids <- sprintf("c%02d", seq_len(n_companies))

  fixtures <- tibble::tibble(
    issue_id = rep(issue_id, length(slot_values)),
    fixture_id = sprintf("%s_%03d", issue_id, slot_values),
    slot = slot_values,
    provider_id = rep("synthetic", length(slot_values)),
    kickoff_at = kickoff_utc,
    handicap = as.integer(sample(c(-1L, 0L, 0L, 0L, 1L), length(slot_values), replace = TRUE)),
    sale_state = rep("open", length(slot_values)),
    source_url = n7_fixture_source_url("fixture", sprintf("%s_%03d", issue_id, slot_values)))

  # A mild home edge plus per-fixture noise. Dirichlet keeps triples valid.
  truth <- matrix(NA_real_, nrow = length(slot_values), ncol = 3L)
  for (i in seq_along(slot_values)) {
    base <- c(0.42, 0.30, 0.28) + stats::runif(3L, -0.06, 0.06)
    base <- pmax(base, 0.02)
    truth[i, ] <- base / sum(base)
  }
  colnames(truth) <- n7_outcomes()
  rownames(truth) <- fixtures$fixture_id

  # Quotes and the initial synthetic status report are observed before each kickoff.
  # The -36h anchor is declared here and is deliberately NOT coupled to any cutoff:
  # generation must not guess a decision epoch, and a quote placed relative to the
  # cutoff would move whenever the caller changed the decision day.
  quote_at <- kickoff_utc - 36 * 3600
  # A small per-company offset keeps the synthetic feed from looking like one
  # simultaneous snapshot, while staying inside the declared -36h anchor.
  company_offset <- seq(0, 120, length.out = length(company_ids))
  status_at <- quote_at

  euro_rows <- list()
  for (i in seq_len(nrow(fixtures))) {
    for (company_index in seq_along(company_ids)) {
      # Per-company noise makes the mean non-trivial; margin overrounds it.
      noisy <- truth[i, ] * exp(stats::runif(3L, -0.03, 0.03))
      noisy <- noisy / sum(noisy)
      euro_rows[[length(euro_rows) + 1L]] <- tibble::tibble(
        fixture_id = fixtures$fixture_id[i],
        company_id = company_ids[company_index],
        quote_at = quote_at[i] + company_offset[company_index],
        odds_home = 1 / (noisy[1] * margin),
        odds_draw = 1 / (noisy[2] * margin),
        odds_away = 1 / (noisy[3] * margin),
        source_url = n7_fixture_source_url(
          "euro", paste0(fixtures$fixture_id[i], "_", company_ids[company_index])))
    }
  }
  euro <- dplyr::bind_rows(euro_rows)

  # Totals at several lines, each a valid two-way de-vigged pair.
  lines <- c(2.5, 3.5)
  totals_rows <- list()
  for (i in seq_len(nrow(fixtures))) {
    for (company_index in seq_along(company_ids)) {
      for (line in lines) {
        over <- stats::plogis(2.4 - 0.55 * line + stats::runif(1L, -0.15, 0.15))
        totals_rows[[length(totals_rows) + 1L]] <- tibble::tibble(
          fixture_id = fixtures$fixture_id[i],
          company_id = company_ids[company_index],
          quote_at = quote_at[i] + company_offset[company_index],
          line = as.double(line),
          over_decimal = 1 / (over * margin),
          under_decimal = 1 / ((1 - over) * margin),
          source_url = n7_fixture_source_url(
            "totals",
            paste0(fixtures$fixture_id[i], "_", company_ids[company_index], "_", line)))
      }
    }
  }
  totals <- dplyr::bind_rows(totals_rows)

  # Pre-match SP: the same triple priced at a slightly different margin, which is
  # what makes SP valuation differ from probability without inventing drift.
  sp_rows <- list()
  for (i in seq_len(nrow(fixtures))) {
    for (outcome in n7_outcomes()) {
      sp_rows[[length(sp_rows) + 1L]] <- tibble::tibble(
        fixture_id = fixtures$fixture_id[i],
        outcome = outcome,
        quote_at = quote_at[i],
        sp_raw = 1 / (truth[i, outcome] * 0.92),
        source_url = n7_fixture_source_url("sp", paste0(fixtures$fixture_id[i], "_", outcome)))
    }
  }
  prematch_sp <- dplyr::bind_rows(sp_rows)

  # A synthetic OBSERVATION, not a derived fact: one report per fixture, taken 36
  # hours before kickoff. status_at equals available_at because the synthetic source
  # reports the event and its observation at the same instant; nothing here is
  # inferred from a real-world final record.
  match_status_table <- tibble::tibble(
    issue_id = rep(issue_id, length(slot_values)),
    fixture_id = fixtures$fixture_id,
    status = rep(match_status, length(slot_values)),
    status_at = status_at,
    available_at = status_at,
    source_url = n7_fixture_source_url("match_status", fixtures$fixture_id))

  list(fixtures = fixtures, euro = euro, totals = totals, prematch_sp = prematch_sp,
       match_status = match_status_table, truth = truth)
}

#' 把一个或多个已生成的期包装成 read_inputs 的 source
#'
#' @param ...  一个或多个由 n7_make_fixture_issue 返回的 list，每个必须含
#'   fixtures/euro/totals/prematch_sp/match_status 五张表。
#'   · 无参数                      -> stop()
#'   · 任一参数非 list             -> stop()，并点名第几个参数
#'   · 任一参数缺表                 -> stop()，并点名缺了哪些
#' @return 可直接传给 n7_read_inputs 的 source list（kind = "frames"）。
#' @details 各期的同名表被纵向 bind_rows 合并；期号由 fixtures$issue_id 携带，
#'   因此多期 source 仍由 n7_read_inputs 的 issue_ids 参数筛选。
n7_fixture_source <- function(...) {
  issues <- list(...)
  if (!length(issues)) stop("n7_fixture_source: at least one issue is required")
  for (i in seq_along(issues)) {
    issue <- issues[[i]]
    if (!is.list(issue)) {
      stop("n7_fixture_source: argument ", i, " must be a generated issue list")
    }
    missing <- setdiff(c("fixtures", "euro", "totals", "prematch_sp", "match_status"),
                       names(issue))
    if (length(missing)) {
      stop("n7_fixture_source: argument ", i, " is missing ", paste(missing, collapse = ", "))
    }
  }
  list(kind = "frames",
       tables = list(
         fixtures = dplyr::bind_rows(lapply(issues, function(x) x$fixtures)),
         euro = dplyr::bind_rows(lapply(issues, function(x) x$euro)),
         totals = dplyr::bind_rows(lapply(issues, function(x) x$totals)),
         prematch_sp = dplyr::bind_rows(lapply(issues, function(x) x$prematch_sp)),
         match_status = dplyr::bind_rows(lapply(issues, function(x) x$match_status))))
}
