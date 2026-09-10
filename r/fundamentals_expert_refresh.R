# Read completed historical labels through the authoritative read-only SQLite API.
# Returns one typed row per issue/slot/native ID; invalid scores/statuses remain
# explicit exclusions. No historical fitting, availability inference or writes.
query_expert_refresh_labels <- function(db_path,issues,query_fn=query_nowscore_settlement) {
  if(!is.character(issues) || !length(issues) || anyNA(issues) || anyDuplicated(issues) ||
     any(!grepl('^[0-9]+$',issues))) stop('Explicit unique issue strings required')
  queries <- lapply(issues,function(issue) query_fn(db_path,issue,play='spf'))
  rows <- dplyr::bind_rows(lapply(queries,`[[`,'settlement')) |>
    dplyr::select(issue,slot,native_match_id,status,score,source_sha256) |> dplyr::distinct()
  if(anyDuplicated(rows[c('issue','slot')])) stop('Conflicting fixture labels')
  parts <- stringr::str_match(rows$score,'^([0-9]+)[-:]([0-9]+)$')
  result <- rows |> dplyr::transmute(issue_code=issue,slot=as.integer(slot),
    provider_id=as.character(native_match_id),actual_home=as.integer(parts[,2]),
    actual_away=as.integer(parts[,3]),source_status=status,source_score=score,source_sha256,
    label_status=dplyr::case_when(is.na(native_match_id) | native_match_id=='' ~ 'MISSING_ID',
      is.na(parts[,1]) ~ 'NO_COMPLETED_SCORE',
      !is.na(status) & !status %in% c('','完场','已完场','完') ~ 'NON_COMPLETED_STATUS',
      TRUE ~ 'COMPLETED'))
  list(labels=tibble::as_tibble(result),findings=dplyr::bind_rows(lapply(queries,`[[`,'findings')),
       build_receipt=queries[[1]]$receipt)
}
