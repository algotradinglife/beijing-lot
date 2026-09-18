# Validate paired prediction-only freezes for a common-input comparison.
# Different candidate groups are allowed; base fixtures, p/q and cutoffs are not.
# Caller verifies byte hashes and plan seals before this pure boundary check.
eight_strategy_validate_pair <- function(joint,top2) {
 stopifnot(identical(joint$issue,top2$issue),
  is.character(joint$source_sha256),length(joint$source_sha256)==1,
  grepl('^[0-9a-f]{64}$',joint$source_sha256),
  identical(joint$source_sha256,top2$source_sha256),
  setequal(names(joint$arms),c('JOINT','DEPTH_OPEN','U4','CONFIDENCE')),
  'TOP2_DIVERSE' %in% names(top2$fresh$selected),
  all(c('HARD1','HARD2','WITHIN0') %in% top2$expanded$policies),
  identical(joint$cutoffs,top2$fresh$cutoffs),
  identical(joint$cutoffs,top2$expanded$cutoffs))
 for(arm in joint$arms)stopifnot('options' %in% names(arm),is.list(arm$options))
 stopifnot(all(top2$expanded$tickets$policy %in% top2$expanded$policies))
 columns<-c('issue','slot','provider_id','handicap',paste0('p_',c('W','D','L')),paste0('q_',c('W','D','L')))
 base<-dplyr::bind_rows(joint$fixtures)
 for(other in list(top2$fresh$fixtures,top2$expanded$fixtures)) {
  stopifnot(setequal(names(base),columns),setequal(names(other),columns),
   !anyDuplicated(base[c('issue','slot')]),!anyDuplicated(other[c('issue','slot')]),
   isTRUE(all.equal(as.data.frame(base[order(base$slot),columns]),
    as.data.frame(other[order(other$slot),columns]),tolerance=0,check.attributes=FALSE)))
 }
 invisible(TRUE)
}

# Descriptive positive-profit removal and no-hit streaks for settled ledgers.
# No-bet/stop periods do not count as placed bets. Streak follows the ordered
# sequence of funded bets (cash gaps omitted), not calendar periods. No I/O.
eight_strategy_tail_diagnostics <- function(curves,remove_k) {
 required<-c('evaluation','accounting_basis','policy','period','stake','net','gross')
 stopifnot(all(required %in% names(curves)),length(remove_k)>0,
  all(is.finite(remove_k)),all(remove_k>=1 & remove_k==floor(remove_k)),
  !anyDuplicated(curves[c('evaluation','accounting_basis','policy','period')]),
  !anyNA(curves[required]),all(is.finite(curves$net)),all(curves$stake>=0),
  all(abs(curves$gross-curves$stake-curves$net)<1e-7))
 pieces<-curves |> dplyr::filter(period>0) |>
  dplyr::group_by(evaluation,accounting_basis,policy) |> dplyr::group_split()
 trims<-streaks<-list()
 for(x in pieces) {
  x<-x[order(x$period),];key<-x[1,c('evaluation','accounting_basis','policy')]
  bets<-x[x$stake>0,];run<-rle(bets$gross==0)
  streaks[[length(streaks)+1L]]<-dplyr::mutate(key,bet_issues=nrow(bets),
   longest_no_hit_bet_run=max(c(0L,run$lengths[run$values])))
  positive<-which(x$net>0);rank<-positive[order(-x$net[positive],x$period[positive])]
  for(k in remove_k) {
   drop<-head(rank,k);keep<-setdiff(seq_len(nrow(x)),drop)
   stake<-sum(x$stake[keep]);net<-sum(x$net[keep])
   trims[[length(trims)+1L]]<-dplyr::mutate(key,requested_remove=k,
    actual_removed=length(drop),remaining_issues=length(keep),stake_cny=stake,
    net_cny=net,roi_percent=if(stake>0)100*net/stake else NA_real_)
  }
 }
 list(trimmed=dplyr::bind_rows(trims),streaks=dplyr::bind_rows(streaks))
}

# Describe probability identity from verified source provenance and numeric
# columns, not an arbitrary strategy model label. Legacy bundles expose p/q
# without a calibrator version: report that limitation explicitly.
eight_strategy_probability_version <- function(fixtures,source_version,model_label) {
 stopifnot(all(c(paste0('p_',c('W','D','L')),paste0('q_',c('W','D','L'))) %in% names(fixtures)))
 if(identical(source_version,'ARCHIVED_RAW_MARKET')) {
  stopifnot(identical(model_label,'ARCHIVED_RAW_MARKET'))
  for(d in c('W','D','L'))stopifnot(identical(fixtures[[paste0('p_',d)]],fixtures[[paste0('q_',d)]]))
  return('ARCHIVED_RAW_MARKET')
 }
 stopifnot(is.null(source_version),identical(model_label,'frozen-market'))
 'ARCHIVED_P_COLUMN'
}

# Admit only READY audited labels for the frozen common fixture universe.
# Returns the authoritative settlement columns in fixture order. Missing,
# duplicate, contradictory or unresolved records fail; unrelated rows may
# remain in the source audit without becoming synthetic losses. No I/O.
eight_strategy_ready_labels <- function(fixtures,labels) {
 keys<-c('issue','slot','provider_id','handicap')
 stopifnot(all(c(keys,'status','actual_direction','spf_sp') %in% names(labels)),
  !anyDuplicated(fixtures[c('issue','slot')]),!anyDuplicated(labels[c('issue','slot')]))
 x<-dplyr::left_join(fixtures[keys],labels,by=keys,relationship='one-to-one')
 stopifnot(!anyNA(x$status),all(x$status=='READY'),!anyNA(x$actual_direction),
  all(x$actual_direction %in% c('W','D','L')),all(is.finite(x$spf_sp)),all(x$spf_sp>0))
 x[c(keys,'actual_direction','spf_sp')]
}

# Identify audited missing winning prices in a frozen fixture universe. Only
# explicit MISSING_WINNING_SP with a known outcome and truly absent SP is
# eligible for common-issue exclusion. Unknown identities or other failures
# remain fatal. Returns a typed anomaly table, including when empty; no I/O.
eight_strategy_unavailable_labels <- function(fixtures,labels) {
 keys<-c('issue','slot','provider_id','handicap')
 stopifnot(all(keys %in% names(fixtures)),
  all(c(keys,'status','actual_direction','spf_sp') %in% names(labels)),
  !anyDuplicated(fixtures[c('issue','slot')]),!anyDuplicated(labels[c('issue','slot')]))
 x<-dplyr::left_join(fixtures[keys],labels,by=keys,relationship='one-to-one')
 stopifnot(!anyNA(x$status),all(x$status %in% c('READY','spf:MISSING_WINNING_SP')),
  !anyNA(x$actual_direction),all(x$actual_direction %in% c('W','D','L')))
 missing<-x$status=='spf:MISSING_WINNING_SP'
 stopifnot(all(is.na(x$spf_sp[missing])),
  all(is.finite(x$spf_sp[!missing])),all(x$spf_sp[!missing]>0))
 x[missing,c(keys,'status','actual_direction','spf_sp')]
}
