# Saved raw responses -> typed diagnostic table plus input hashes; no network/writes.
mapping_report <- function(path_500, path_ns, issue) {
  stopifnot(file.exists(path_500), file.exists(path_ns))
  raw_500 <- readBin(path_500, "raw", n = file.info(path_500)$size)
  raw_ns <- readBin(path_ns, "raw", n = file.info(path_ns)$size)
  a <- parse_500(decode_source(raw_500, "GB18030"), issue)
  ns_text <- decode_source(raw_ns, "UTF-8")
  parsed <- parse_nowscore(ns_text, issue)
  b <- parsed$team_pairs %>% left_join(parsed$candidates, by = c("issue", "slot"), relationship = "one-to-one")
  status <- parse_nowscore_status(ns_text, issue)
  stopifnot(!anyDuplicated(a[c("issue", "slot")]), !anyDuplicated(b[c("issue", "slot")]),
            !anyDuplicated(status[c("issue", "slot")]))
  data <- full_join(a, b, by = c("issue", "slot"), relationship = "one-to-one") %>%
    left_join(status, by = c("issue", "slot"), relationship = "one-to-one") %>%
    mutate(status = normalize_status(status_raw),
           merge_status = case_when(is.na(fid_500) ~ "only_nowscore",
             is.na(home_ns) ~ "only_500",
             home_500 == home_ns & away_500 == away_ns ~ "exact_team",
             TRUE ~ "translation_or_alignment_review"),
           cutoff_gap_minutes = as.numeric(difftime(cutoff_500, cutoff_ns_html, units = "mins"))) %>%
    arrange(slot)
  inputs <- tibble::tibble(issue = issue, source = c("500", "nowscore"),
    path = c(path_500, path_ns), sha256 = c(digest::digest(raw_500, algo = "sha256", serialize = FALSE),
                                        digest::digest(raw_ns, algo = "sha256", serialize = FALSE)))
  list(data = data, inputs = inputs)
}
