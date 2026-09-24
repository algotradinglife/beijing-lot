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
#' n_fixtures 场比赛被放在同一个本地日历日上，开赛时间错开。每场获得一个让球数、
#' 一个真实底层 W/D/L 三元组、一组欧赔报价、若干盘口的大小球报价，以及一个赛前 SP
#' 三元组。概率先生成、赔率由概率导出，因此夹具自洽。
#'
#' @details 自洽的准确含义：赔率按 margin 加水位，故隐含概率之和精确等于 margin；
#'   对欧赔去水得到的是每家公司各自的 noisy 三元组（以 truth 为中心），而**不是**
#'   truth 本身。truth 是底层参数，赔率是围绕它的抽样。因此不要断言"去水还原 truth"。
#'
#' @param issue_id     长度 1 的合法字符标识符（经 n7_check_character_id）。
#'   · 长度 != 1 -> stop()（本生成器只命名一期）
#' @param local_date   长度 1 的 YYYY-MM-DD 字符串，且必须是真实存在的日历日期。
#'   · 非字符 / 长度 != 1 / NA / 非补零写法（如 2026-9-2）-> stop()
#'   · 不存在的日期（如 2026-02-30）                      -> stop()
#' @param n_fixtures   长度 1 的正整数。<= 0、小数、NA、非有限 -> stop()
#' @param n_companies  长度 1 的正整数。<= 0、小数           -> stop()
#' @param seed         长度 1 的有限数值。
#' @param tz           长度 1 的非空时区名，必须存在于 OlsonNames() 中。
#'   · 未知时区 -> stop()（否则 as.POSIXct 会静默退回 UTC，使每个开赛时刻偏移）
#' @param kickoff_hour 长度 1 的整数，取值 0..23。
#'   · 越界 -> stop()（否则日期运算会静默回绕，产出没人要求的时间轴）
#' @param margin       长度 1 的正有限数值，用于给赔率加水位。
#'   · <= 0 会产出 Inf 赔率，NA 会产出 NA 赔率，两者都静默 -> stop()
#'
#' @return list(fixtures, euro, totals, prematch_sp, truth)，前四张为 tibble，
#'   truth 为 n_fixtures x 3 的数值矩阵（行名 fixture_id，列名 W/D/L）。
#' @details 开赛时间落在 D+1（决策窗口内）：local_date 是决策日 D，20:00 Asia/Shanghai
#'   的 epoch 能看到它们，而报价被放在 D 的上午，因此严格早于 cutoff。
n7_make_fixture_issue <- function(issue_id, local_date, n_fixtures = 10L,
                                  n_companies = 3L, seed = 1L, tz = "Asia/Shanghai",
                                  kickoff_hour = 19L,
                                  margin = 1.06) {
  n7_check_character_id(issue_id, "issue_id")
  # Exactly one issue: this generator names one issue, and a longer id would reach
  # tibble() and die there with a column-size error that names neither the argument
  # nor the cause.
  if (length(issue_id) != 1L) {
    stop("n7_make_fixture_issue: issue_id must name exactly one issue; got ",
         length(issue_id))
  }
  # Zero-padded ISO date only: "2026-9-2" would parse, but it makes the generated
  # calendar date look like something the caller did not ask for.
  if (!is.character(local_date) || length(local_date) != 1L || is.na(local_date) ||
      !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", local_date)) {
    stop("n7_make_fixture_issue: local_date must be one YYYY-MM-DD string")
  }
  # A non-existent calendar date is a caller error, not an invitation to roll over.
  if (is.na(as.Date(local_date, format = "%Y-%m-%d"))) {
    stop("n7_make_fixture_issue: local_date is not a real calendar date: ", local_date)
  }
  if (!is.numeric(n_fixtures) || length(n_fixtures) != 1L || is.na(n_fixtures) ||
      !is.finite(n_fixtures) || n_fixtures != floor(n_fixtures) || n_fixtures < 1) {
    stop("n7_make_fixture_issue: n_fixtures must be one positive whole number")
  }
  slot_values <- n7_check_slot(seq_len(as.integer(n_fixtures)), "n_fixtures")
  if (!is.numeric(n_companies) || length(n_companies) != 1L || is.na(n_companies) ||
      !is.finite(n_companies) || n_companies != floor(n_companies) || n_companies < 1) {
    stop("n7_make_fixture_issue: n_companies must be one positive whole number")
  }
  # kickoff_hour indexes a local calendar hour: a value outside 0..23 would be
  # silently wrapped by the date arithmetic, producing a timeline nobody asked for.
  if (!is.numeric(kickoff_hour) || length(kickoff_hour) != 1L || is.na(kickoff_hour) ||
      !is.finite(kickoff_hour) || kickoff_hour != floor(kickoff_hour) ||
      kickoff_hour < 0 || kickoff_hour > 23) {
    stop("n7_make_fixture_issue: kickoff_hour must be one whole hour in 0..23")
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
  # An unknown timezone must be refused: as.POSIXct would silently fall back to UTC
  # and shift every kickoff by the intended offset.
  if (!is.character(tz) || length(tz) != 1L || is.na(tz) || !nzchar(tz)) {
    stop("n7_make_fixture_issue: tz must be one non-empty timezone name")
  }
  if (!tz %in% OlsonNames()) {
    stop("n7_make_fixture_issue: tz is not a known timezone: ", tz)
  }
  set.seed(seed)

  # local_date is the DECISION day D. Kickoffs land on D+1 (the decision window),
  # so the 20:00 Asia/Shanghai epoch on D sees them, and quotes are placed a few
  # hours before kickoff, i.e. after that epoch and before the first kickoff.
  # 30-minute stagger keeps kickoffs inside the D+1 natural day for issues up to
  # 48 fixtures, so a full 4-group slate fits in one decision window.
  kickoff_local <- as.POSIXct(paste(local_date, sprintf("%02d:00:00", kickoff_hour)),
                              tz = tz) + 86400 + (slot_values - 1L) * 900
  kickoff_utc <- as.POSIXct(format(kickoff_local, tz = "UTC", usetz = TRUE), tz = "UTC")
  # Quotes are placed on the decision day D, a few hours before the 20:00
  # Asia/Shanghai epoch, so they are strictly pre-cutoff and the as-of rule has
  # something to select from. They are deliberately NOT tied to kickoff: a quote
  # taken after the decision is not an input to that decision.
  # Quotes are spread across the pre-cutoff morning but capped so that even a large
  # slate stays strictly before the 20:00 Asia/Shanghai epoch. Tying the offset to
  # the slot index would push late slots past the cutoff and silently drop them.
  spread_minutes <- if (length(slot_values) > 1L) {
    min(8, floor(540 / (length(slot_values) - 1L)))
  } else 0
  quote_local <- as.POSIXct(paste(local_date, "08:00:00"), tz = tz) +
    (slot_values - 1L) * spread_minutes * 60
  quote_at <- as.POSIXct(format(quote_local, tz = "UTC", usetz = TRUE), tz = "UTC")

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

  company_ids <- sprintf("c%02d", seq_len(n_companies))
  euro_rows <- list()
  for (i in seq_len(nrow(fixtures))) {
    for (company in company_ids) {
      # Per-company noise makes the mean non-trivial; margin overrounds it.
      noisy <- truth[i, ] * exp(stats::runif(3L, -0.03, 0.03))
      noisy <- noisy / sum(noisy)
      euro_rows[[length(euro_rows) + 1L]] <- tibble::tibble(
        fixture_id = fixtures$fixture_id[i],
        company_id = company,
        quote_at = quote_at[i],
        odds_home = 1 / (noisy[1] * margin),
        odds_draw = 1 / (noisy[2] * margin),
        odds_away = 1 / (noisy[3] * margin),
        source_url = n7_fixture_source_url("euro", paste0(fixtures$fixture_id[i], "_", company)))
    }
  }
  euro <- dplyr::bind_rows(euro_rows)

  # Totals at several lines, each a valid two-way de-vigged pair.
  lines <- c(2.5, 3.5)
  totals_rows <- list()
  for (i in seq_len(nrow(fixtures))) {
    for (company in company_ids) {
      for (line in lines) {
        over <- stats::plogis(2.4 - 0.55 * line + stats::runif(1L, -0.15, 0.15))
        totals_rows[[length(totals_rows) + 1L]] <- tibble::tibble(
          fixture_id = fixtures$fixture_id[i],
          company_id = company,
          quote_at = quote_at[i],
          line = as.double(line),
          over_decimal = 1 / (over * margin),
          under_decimal = 1 / ((1 - over) * margin),
          source_url = n7_fixture_source_url(
            "totals", paste0(fixtures$fixture_id[i], "_", company, "_", line)))
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

  list(fixtures = fixtures, euro = euro, totals = totals, prematch_sp = prematch_sp,
       truth = truth)
}

#' 把一个或多个已生成的期包装成 read_inputs 的 source
#'
#' @param ...  一个或多个由 n7_make_fixture_issue 返回的 list，每个必须含
#'   fixtures/euro/totals/prematch_sp 四张表。
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
    missing <- setdiff(c("fixtures", "euro", "totals", "prematch_sp"), names(issue))
    if (length(missing)) {
      stop("n7_fixture_source: argument ", i, " is missing ", paste(missing, collapse = ", "))
    }
  }
  list(kind = "frames",
       tables = list(
         fixtures = dplyr::bind_rows(lapply(issues, function(x) x$fixtures)),
         euro = dplyr::bind_rows(lapply(issues, function(x) x$euro)),
         totals = dplyr::bind_rows(lapply(issues, function(x) x$totals)),
         prematch_sp = dplyr::bind_rows(lapply(issues, function(x) x$prematch_sp))))
}
