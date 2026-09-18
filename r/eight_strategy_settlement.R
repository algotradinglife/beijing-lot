# Attach explicit finality evidence to archived fixture labels, without writes.
# Official kaijiang SPF pages are settlement publications: a blank status there
# may authorize completed-score verification. A contradictory non-final status
# never does. Scores, identity, handicap and winning SP are checked separately
# by clean_validation_spf_audit. Missing evidence returns 未核实, not a loss.
eight_strategy_completion_evidence <- function(fixtures,settlement) {
 stopifnot(all(c('issue','slot','provider_id') %in% names(fixtures)),
  all(c('issue','slot','native_match_id','status','source_url') %in% names(settlement)),
  !anyDuplicated(fixtures[c('issue','slot')]))
 fixtures$result_state<-'未核实';fixtures$completion_evidence<-'UNVERIFIED'
 for(i in seq_len(nrow(fixtures))) {
  f<-fixtures[i,];z<-settlement[settlement$issue==f$issue & settlement$slot==f$slot,]
  if(!nrow(z)||anyNA(z$native_match_id)||!all(z$native_match_id==f$provider_id))next
  status<-ifelse(is.na(z$status),'',z$status)
  if(any(!status %in% c('','完场')))next
  explicit<-all(status=='完场')
  official<-!anyNA(z$source_url)&&all(z$source_url==paste0(
   'https://cp.nowscore.com/beijingdanchang/rangqiushengpingfu/kaijiang_dc_5_',f$issue,'.html'))
  if(explicit||official) {
   fixtures$result_state[i]<-'完场'
   fixtures$completion_evidence[i]<-if(explicit)'EXPLICIT_DB_COMPLETED' else 'OFFICIAL_KAIJIANG_PUBLICATION'
  }
 }
 fixtures
}
