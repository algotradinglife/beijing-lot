# mapping_engine.R — 北单历史期次 500→Nowscore 映射引擎（tidyverse + reticulate）
#
# 职责边界：
#   * 抓取（curl，UA 与 Python 采集器一致）+ 滚动限速（120/min）
#   * 解析 500 / Nowscore 页面 → tibble（rvest / stringr / 正则）
#   * 对齐（same-slot / exact-remap / ordered fallback / 翻译容差）
#   * void 行（provider<=0，取消/推迟/中断）识别与隔离
#   * 写库经 reticulate 调 Python 的 HistoricalIdMapStore —— 写库契约的
#     单一权威是 src/titan_clean/historical_id_map.py，R 侧不再有双份实现
#
library(tidyverse)
library(reticulate)
library(lubridate)
library(curl)
library(DBI)
library(RSQLite)
library(R6)

UA_DEFAULT <- "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
TRADE_URL_500 <- "https://trade.500.com/bjdc/?expect=%s"
NOWSCORE_URL <- "https://cp.nowscore.com/buy/DanChang.aspx?all=1&TypeID=5&issueNum=%s"
PARSER_VERSION <- "historical_id_map_v1"
RATE_LIMIT_PER_MINUTE <- 120L

# ---------------------------------------------------------------- 限速 ----

RateLimiter <- R6Class("RateLimiter", public = list(
  window_seconds = NULL, max_requests = NULL, timestamps = numeric(),
  clock = NULL, sleep = NULL,
  initialize = function(max_requests = 120L, window_seconds = 60,
                        clock = function() as.numeric(Sys.time()), sleep = Sys.sleep) {
    stopifnot(max_requests >= 1, window_seconds > 0)
    self$max_requests <- max_requests
    self$window_seconds <- window_seconds
    self$clock <- clock
    self$sleep <- sleep
  },
  acquire = function(n = 1L) {
    stopifnot(n >= 1, n <= self$max_requests, n == as.integer(n))
    repeat {
      now <- self$clock()
      self$timestamps <- self$timestamps[self$timestamps > now - self$window_seconds]
      if (length(self$timestamps) + n <= self$max_requests) break
      self$sleep(max(0.01, min(self$timestamps) + self$window_seconds - now))
    }
    self$timestamps <- c(self$timestamps, rep(now, n))
    invisible(NULL)
  }
))

# Return original bytes plus strictly decoded UTF-8 text; never drop bad bytes.
fetch_raw <- function(url, encoding, ua = UA_DEFAULT, timeout = 30L,
                      transport = curl::curl_fetch_memory, attempts = 3L,
                      rate_limiter = NULL, sleep = Sys.sleep) {
  stopifnot(length(url) == 1L, nzchar(url), timeout > 0, attempts >= 1L)
  h <- curl::new_handle(useragent = ua, accept_encoding = "identity", timeout = timeout)
  for (attempt in seq_len(attempts)) {
    if (!is.null(rate_limiter)) rate_limiter$acquire()
    response <- tryCatch(transport(url, handle = h), error = identity)
    transient <- inherits(response, "error") || response$status_code %in% c(429L, 500L, 502L, 503L, 504L)
    if (!transient || attempt == attempts) break
    sleep(min(2^(attempt - 1L), 8))
  }
  if (inherits(response, "error")) stop(response)
  if (response$status_code != 200L) stop(sprintf("HTTP %d for %s", response$status_code, url))
  list(payload = response$content, text = decode_source(response$content, encoding))
}

decode_source <- function(payload, encoding) {
  stopifnot(is.raw(payload), length(payload) > 0, length(encoding) == 1L)
  text <- iconv(rawToChar(payload), from = encoding, to = "UTF-8", sub = NA_character_)
  if (is.na(text)) stop("source decoding failed")
  sub("^\ufeff", "", text)
}

extract_first <- function(text, pattern) {
  hit <- regexec(pattern, text, perl = TRUE)
  m <- regmatches(text, hit)[[1]]
  if (length(m) < 2L) NA_character_ else m[[2]]
}

parse_js_datetime <- function(x, tz = "Asia/Shanghai") {
  pieces <- stringr::str_match(x, "new Date\\((\\d+),(\\d+),(\\d+),(\\d+),(\\d+),(\\d+)\\)")
  lubridate::make_datetime(as.integer(pieces[,2]), as.integer(pieces[,3]) + 1L,
                          as.integer(pieces[,4]), as.integer(pieces[,5]),
                          as.integer(pieces[,6]), as.integer(pieces[,7]), tz = tz)
}

parse_cutoff <- function(x) lubridate::ymd_hm(x, tz = "Asia/Shanghai", quiet = TRUE)
parse_schedule_date <- function(x) lubridate::ymd(x, quiet = TRUE)

# ---------------------------------------------------------------- 解析 500 ----

parse_500 <- function(html, issue) {
  doc <- rvest::read_html(html, encoding = "UTF-8")
  nodes <- rvest::html_elements(doc, "tr.vs_lines")
  value_attr <- rvest::html_attr(nodes, "value")
  fid <- suppressWarnings(as.integer(rvest::html_attr(nodes, "fid")))

  tibble(value_attr = value_attr, fid_500 = fid) %>%
    filter(!is.na(fid_500), fid_500 > 0L, !is.na(value_attr)) %>%
    rowwise() %>%
    transmute(
      issue = issue,
      slot = suppressWarnings(as.integer(extract_first(value_attr, "index:'(\\d+)'"))),
      fid_500,
      league_500 = extract_first(value_attr, "leagueName:'([^']*)'"),
      home_500 = extract_first(value_attr, "homeTeam:'([^']*)'"),
      away_500 = extract_first(value_attr, "guestTeam:'([^']*)'"),
      cutoff_500 = parse_cutoff(extract_first(value_attr, "endTime:'([^']*)'")),
      schedule_date_500 = parse_schedule_date(extract_first(value_attr, "scheduleDate:'([^']*)'")),
      handicap_500 = suppressWarnings(as.numeric(extract_first(value_attr, "rangqiuNum:'(-?\\d+)'")))
    ) %>%
    ungroup()
}

# ---------------------------------------------------------------- 解析 Nowscore ----

parse_nowscore <- function(html, issue) {
  declared <- rvest::html_attr(rvest::html_element(rvest::read_html(html), "input#issueNum"), "value")
  if (is.na(declared) || declared != issue) stop("Nowscore payload-declared issue differs from requested issue")
  assigns <- regmatches(html, gregexpr("M\\[(\\d+)\\]\\[(\\d+)\\]\\s*=\\s*([^;]*);", html, perl = TRUE))[[1]]
  if (length(assigns) == 0L) stop("Nowscore complete membership matrix is absent")
  matched <- stringr::str_match(assigns, "M\\[(\\d+)\\]\\[(\\d+)\\]\\s*=\\s*([^;]*);")
  long <- tibble(
    row_id = as.integer(matched[, 2]),
    field = as.integer(matched[, 3]),
    value = trimws(matched[, 4])
  )
  if (anyDuplicated(long[c("row_id", "field")])) stop("duplicate Nowscore matrix field")
  wide <- long %>% pivot_wider(names_from = field, values_from = value)
  required <- c("0", "3", "16", "17", "20")
  missing <- setdiff(required, names(wide))
  if (length(missing) > 0L) stop(glue("Nowscore matrix missing fields: {paste(missing, collapse=',')}"))

  slot_col <- as.integer(wide[["16"]])
  provider_col <- wide[["0"]]
  provider_num <- suppressWarnings(as.numeric(gsub('^"|"$', "", provider_col)))
  valid <- !is.na(provider_num) & provider_num >= 1 & !is.na(slot_col) & slot_col >= 1
  void_slots <- slot_col[!is.na(slot_col) & !is.na(provider_num) & provider_num < 1] %>% unique() %>% sort()

  candidates <- tibble(
    issue = issue, slot = slot_col[valid],
    provider_id = sprintf("%.0f", provider_num[valid])
  )
  team_pairs <- tibble(
    issue = issue, slot = slot_col[!is.na(slot_col)],
    home_ns = strip_quotes(wide[["17"]][!is.na(slot_col)]),
    away_ns = strip_quotes(wide[["20"]][!is.na(slot_col)]),
    deadline_ns = parse_js_datetime(wide[["3"]][!is.na(slot_col)])
  )
  list(candidates = candidates, void_slots = void_slots, team_pairs = team_pairs)
}

strip_quotes <- function(x) gsub('^"|"$', "", x)

# ---------------------------------------------------------------- 解析 Nowscore 状态 ----

parse_nowscore_status <- function(html, issue) {
  trs <- regmatches(html, gregexpr(
    "(?s)<tr id=\"row_\\d+\"[^>]*matchid=\"\\d+\"[^>]*>.*?</tr>", html, perl = TRUE
  ))[[1]]
  if (length(trs) == 0L) {
    return(tibble(issue = character(), slot = integer(), status_raw = character(), cutoff_ns_html = as.POSIXct(character())))
  }
  slot_m <- stringr::str_match(trs, 'matchid="(\\d+)"')
  td_m <- stringr::str_match(trs, '<td[^>]*title="截止时间：([^"]*)"[^>]*>(.*?)</td>')
  tibble(
    issue = issue,
    slot = as.integer(slot_m[, 2]),
    status_raw = stringr::str_trim(stringr::str_remove_all(td_m[, 3], "<[^>]+>")),
    cutoff_ns_html = parse_cutoff(td_m[, 2])
  ) %>%
    filter(!is.na(slot))
}

normalize_status <- function(x) {
  case_when(
    x %in% c("完场", "完赛") ~ "finished",
    x %in% c("取消", "腰斩") ~ "cancelled",
    x == "推迟" ~ "postponed",
    x %in% c("中断", "待定") ~ "suspended",
    x == "上" ~ "first_half",
    x == "下" ~ "second_half",
    x == "中场" ~ "halftime",
    x == "截止" ~ "closed",
    grepl("^\\d{2}:\\d{2}$", x) ~ "not_started",
    TRUE ~ NA_character_
  )
}

# ---------------------------------------------------------------- 对齐 ----

# Same-slot translation tolerance is diagnostic identity matching, not availability.
resolve_alignment <- function(dt_500, team_pairs, issue) {
  stopifnot(nrow(dt_500) > 0, nrow(team_pairs) > 0,
            !anyNA(dt_500$slot), !anyNA(team_pairs$slot),
            !anyDuplicated(dt_500$slot), !anyDuplicated(team_pairs$slot))
  target <- integer(nrow(dt_500))
  for (i in seq_len(nrow(dt_500))) {
    slot <- dt_500$slot[i]
    exact <- team_pairs$slot[which(team_pairs$home_ns == dt_500$home_500[i] &
                                  team_pairs$away_ns == dt_500$away_500[i])]
    if (slot %in% exact) target[i] <- slot
    else if (length(exact) == 1L) target[i] <- exact
    else if (length(exact) == 0L && slot %in% team_pairs$slot) target[i] <- slot
    else stop(sprintf("ambiguous or missing team match: issue %s slot %s", issue, slot))
  }
  if (anyDuplicated(target)) stop("alignment targets collide")
  setNames(target, as.character(dt_500$slot))
}

# Preserve integer/string types when passing rows through reticulate.
df_to_tuples <- function(df) {
  lapply(seq_len(nrow(df)), function(i) unname(as.list(df[i, , drop = FALSE])))
}

# Explicit capture identity/time make retries reproducible; writes use Python only.
run_issue_mapping <- function(issue, data_root, capture_key, received_at_utc,
                              project_root, python, rate_limiter = RateLimiter$new(),
                              resolve_conflict = list(), raw_500 = NULL,
                              raw_ns = NULL, rebuild = FALSE) {
  url_500 <- sprintf(TRADE_URL_500, issue)
  url_ns <- sprintf(NOWSCORE_URL, issue)
  if (is.null(raw_500)) raw_500 <- fetch_raw(url_500, "GB18030", rate_limiter = rate_limiter)$payload
  if (is.null(raw_ns)) raw_ns <- fetch_raw(url_ns, "UTF-8", rate_limiter = rate_limiter)$payload
  dt_500 <- parse_500(decode_source(raw_500, "GB18030"), issue)
  ns <- parse_nowscore(decode_source(raw_ns, "UTF-8"), issue)
  slot_map <- resolve_alignment(dt_500, ns$team_pairs, issue)
  module <- project_python_module("src.titan_clean.historical_id_map", project_root, python)
  store <- module$HistoricalIdMapStore$open(normalizePath(data_root, mustWork = TRUE))
  on.exit(store$close(), add = TRUE)
  result <- store$record_capture(
    issue_code = issue, capture_key = capture_key, received_at_utc = received_at_utc,
    source_url_500 = url_500, source_url_nowscore = url_ns,
    raw_500 = raw_500, raw_nowscore = raw_ns,
    rows_500 = df_to_tuples(dplyr::select(dt_500, slot, fid_500)),
    slot_pairs = df_to_tuples(tibble(slot = as.integer(names(slot_map)), target = unname(slot_map))),
    resolution_pairs = lapply(resolve_conflict, function(x) list(as.character(x$provider), as.integer(x$slot))),
    rebuild = rebuild
  )
  result$void_slots <- ns$void_slots
  result
}
