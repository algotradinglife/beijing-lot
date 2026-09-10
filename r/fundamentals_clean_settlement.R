# Bind SPF-only R query rows to post-freeze roster outcomes. One row per fixture;
# unresolved identity/outcome/handicap stays pending, missing SP stays NA. No BF
# requirement, SQL, fitting or writes. A blank DB handicap can only be
# paired with an explicit zero from the independently parsed same-match roster;
# this is recorded as roster evidence, never converted to a DB value. Returns native audit fields for the
# authoritative N7 settlement interface; amounts are never calculated here.
clean_validation_spf_audit <- function(settlement, fixtures) {
  keys <- c('issue','slot','provider_id')
  if (!nrow(fixtures) || anyDuplicated(fixtures[keys])) stop('Unique fixtures required')
  if (nrow(settlement) && (any(settlement$play!='spf') || anyDuplicated(settlement[c('issue','slot','option')])))
    stop('Unique SPF query rows required')
  rows <- list()
  for (i in seq_len(nrow(fixtures))) {
    f <- fixtures[i,]
    z <- dplyr::filter(settlement,issue==f$issue,slot==f$slot)
    row <- dplyr::select(f,dplyr::all_of(keys),handicap,home,away,actual_home,actual_away)
    row$actual_direction <- NA_character_;row$spf_sp <- NA_real_;row$spf_source_sha256 <- NA_character_
    row$status <- 'spf:IDENTITY_OR_SCORE_MISMATCH';row$handicap_evidence <- 'UNVERIFIED'
    scores <- c(f$actual_home,f$actual_away)
    if (f$result_state=='完场' && !anyNA(scores) && all(is.finite(scores)) && all(scores>=0 & scores%%1==0)) {
      net <- f$actual_home-f$actual_away+f$handicap
      row$actual_direction <- if(net>0) 'W' else if(net==0) 'D' else 'L'
      numeric_handicap <- nrow(z)>0 && !anyNA(z$handicap_raw) && all(grepl('^[+-]?[0-9]+$',z$handicap_raw))
      roster_zero <- nrow(z)>0 && f$handicap==0 && !anyNA(z$handicap_raw) && all(z$handicap_raw=='')
      handicap_valid <- (numeric_handicap && all(as.numeric(z$handicap_raw)==f$handicap)) || roster_zero
      valid <- handicap_valid && !anyNA(z$native_match_id) && all(z$native_match_id==f$provider_id) &&
        !anyNA(z$score) && all(gsub(':','-',z$score,fixed=TRUE)==paste(f$actual_home,f$actual_away,sep='-')) &&
        TRUE
      if (valid) {
        row$handicap_evidence <- if(roster_zero) 'EXPLICIT_ROSTER_ZERO_DB_FIELD_BLANK' else 'ROSTER_DB_NUMERIC_AGREEMENT'
        option <- c(W='胜',D='平',L='负')[[row$actual_direction]]
        winner <- dplyr::filter(z,.data$option==.env$option)
        row$status <- 'spf:MISSING_WINNING_SP'
        if (nrow(winner)==1 && is.finite(winner$sp) && winner$sp>0) {
          row$status <- 'READY';row$spf_sp <- winner$sp;row$spf_source_sha256 <- winner$source_sha256
        }
      }
    }
    rows[[i]] <- row
  }
  dplyr::bind_rows(rows)
}
