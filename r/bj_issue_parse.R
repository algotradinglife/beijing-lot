# Parse a Nowscore BJ TypeID=5 (让球胜平负) issue page into a fixture tibble.
#
# The page lists one row per fixture. Cell layout (0-based) is fixed:
#   0 slot, 1 league, 2 kickoff, 3 status, 4 home, 5 handicap(+N only),
#   6 score, 7 away, 8 halftime, 9-11 odds, 12 sp anchor, 13-15 the three SPs.
# The handicap cell holds only a signed value such as '-1' or '+1'; a zero
# handicap renders as an empty cell (the same ambiguity as the archive pages).
# The three SP values are the 北单 pre-match SP for 让胜/让平/让负; any of them
# may be empty until the market posts it.

# Typed empty fixture tibble, used for every failure path.
bj_issue_empty <- function() {
  tibble::tibble(
    issue = character(), slot = integer(), league = character(),
    kickoff = character(), status = character(), home = character(),
    handicap = numeric(), score = character(), away = character(),
    ht = character(), sp_win = numeric(), sp_draw = numeric(), sp_lose = numeric())
}

# Parse raw HTML text for one issue. `html_text` must be a single string.
bj_issue_parse <- function(html_text, issue) {
  if (length(html_text) != 1L || !nzchar(html_text)) {
    stop('bj_issue_parse: html_text must be one non-empty string')
  }
  if (length(issue) != 1L || is.na(issue) || !nzchar(issue)) {
    stop('bj_issue_parse: issue must be one non-empty string')
  }
  doc <- rvest::read_html(html_text)
  rows <- rvest::html_elements(doc, 'tr[id]')
  out <- lapply(rows, function(tr) {
    cells <- rvest::html_elements(tr, 'td, th')
    if (length(cells) < 16L) return(NULL)
    txt <- stringr::str_squish(rvest::html_text2(cells))
    num <- function(x) suppressWarnings(as.numeric(x))
    tibble::tibble(
      issue    = as.character(issue),
      slot     = num(txt[1]),
      league   = txt[2],
      kickoff  = txt[3],
      status   = txt[4],
      home     = txt[5],
      handicap = num(stringr::str_remove(txt[6], '^\\+')),
      score    = txt[7],
      away     = txt[8],
      ht       = txt[9],
      sp_win   = num(txt[14]),
      sp_draw  = num(txt[15]),
      sp_lose  = num(txt[16]))
  })
  d <- dplyr::bind_rows(out)
  if (!nrow(d)) return(bj_issue_empty())
  d |> dplyr::filter(!is.na(.data$slot)) |>
    dplyr::arrange(.data$slot) |>
    dplyr::distinct(.data$slot, .keep_all = TRUE)
}

