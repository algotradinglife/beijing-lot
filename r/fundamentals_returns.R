# Query all five plays, then bind winning SPF/BF SP to accepted fixture identity
# and outcomes. Archive findings are preserved; absent prices are never zero.
# accepted: unique issue/slot/provider_id, actual_home/away, handicap, home/away.
# The authoritative score-option mapping is imported; no new mapping is defined.
# Read-only DB and Python imports; returns raw tibbles, findings and audit rows.
fundamentals_settlement_audit <- function(db_path,accepted,python,project_root) {
  keys <- c('issue','slot','provider_id')
  if(!nrow(accepted) || anyDuplicated(accepted[keys])) stop('Unique accepted fixtures required')
  module <- project_python_module('src.nowscore_settlement',project_root,python,convert=FALSE)
  queries <- lapply(sort(unique(accepted$issue)),function(issue)query_nowscore_settlement(db_path,issue))
  raw <- dplyr::bind_rows(lapply(queries,`[[`,'settlement'))
  findings <- dplyr::bind_rows(lapply(queries,`[[`,'findings'))
  audit <- list()
  for(i in seq_len(nrow(accepted))) {
    f <- accepted[i,];net <- f$actual_home-f$actual_away+f$handicap
    expected_spf <- if(net>0) '胜' else if(net==0) '平' else '负'
    expected_bf <- reticulate::py_to_r(module$expected_option(list(play='bf',score=paste(f$actual_home,f$actual_away,sep='-'))))
    row <- dplyr::select(f,dplyr::all_of(keys),home,away,handicap,actual_home,actual_away)
    row$actual_direction <- if(net>0) 'W' else if(net==0) 'D' else 'L'
    row$bf_option <- expected_bf;row$status <- 'READY';reason <- character()
    for(play in c('spf','bf')) {
      z <- dplyr::filter(raw,issue==f$issue,slot==f$slot,.data$play==.env$play)
      expected <- if(play=='spf') expected_spf else expected_bf
      winner <- dplyr::filter(z,option==expected)
      if(!nrow(z) || anyNA(z$native_match_id) || any(z$native_match_id!=f$provider_id) ||
         anyNA(z$score) || any(gsub(':','-',z$score,fixed=TRUE)!=paste(f$actual_home,f$actual_away,sep='-')))
        reason <- c(reason,paste0(play,':IDENTITY_OR_SCORE_MISMATCH'))
      if(nrow(winner)!=1 || !is.finite(winner$sp) || winner$sp<=0) reason <- c(reason,paste0(play,':MISSING_WINNING_SP'))
      row[[paste0(play,'_sp')]] <- if(nrow(winner)==1 && is.finite(winner$sp) && winner$sp>0) winner$sp else NA_real_
      row[[paste0(play,'_source_sha256')]] <- if(nrow(winner)==1) winner$source_sha256 else NA_character_
    }
    if(length(reason)) row$status <- paste(reason,collapse=';')
    audit[[i]] <- row
  }
  list(settlement=raw,findings=findings,fixtures=dplyr::bind_rows(audit),receipt=queries[[1]]$receipt)
}

# Freeze an already ranked seven-fixture portfolio. Ranking is upstream and must
# be label-free; final SP is deliberately not an argument. Explicit cutoffs and
# a diagnostic authorization are required. Returns stake ledger, no writes.
seven_double_plan <- function(ranked,cutoffs,n,unit_cny,budget_cny,main_multiples,
                              payout_factor,owner_exception) {
  if(!identical(owner_exception,'OWNER_AUTHORIZED_HISTORICAL_RETURNS') || is.null(cutoffs)) stop('Explicit diagnostic policy/cutoff required')
  if(n!=7 || unit_cny!=2 || budget_cny!=1024 || main_multiples<1 || main_multiples%%1!=0 || payout_factor!=.65) stop('Explicit fixed business constants required')
  if(nrow(ranked)!=n || length(unique(ranked$issue))!=1 || anyDuplicated(ranked$slot) || anyDuplicated(ranked$provider_id)) stop('Exactly seven unique ranked fixtures required')
  ranked <- dplyr::select(ranked,issue,slot,provider_id,handicap,selected,protect_home,protect_away)
  if(anyNA(ranked$handicap) || any(!is.finite(ranked$handicap)) || any(ranked$handicap%%1!=0)) stop('Integer handicap required')
  issue <- ranked$issue[1]
  if(any(!as.character(ranked$slot) %in% names(cutoffs[[issue]]))) stop('Missing fixture cutoffs')
  dirs <- strsplit(ranked$selected,',',fixed=TRUE)
  if(any(vapply(dirs,function(x)length(x)!=2 || anyDuplicated(x)>0 || !all(x %in% c('W','D','L')),logical(1)))) stop('Two distinct directions required')
  goals <- c(ranked$protect_home,ranked$protect_away)
  if(anyNA(goals) || any(!is.finite(goals)) || any(goals<0 | goals%%1!=0)) stop('Finite integer protection score required')
  main_stake <- 2^n*unit_cny*main_multiples
  remaining_units <- (budget_cny-main_stake)/unit_cny
  if(remaining_units<n || remaining_units%%1!=0) stop('Insufficient integer protection budget')
  ranked$protection_units <- rep(remaining_units%/%n,n)+as.integer(seq_len(n)<=remaining_units%%n)
  ranked$protection_stake <- ranked$protection_units*unit_cny
  artifact <- list(legs=ranked,cutoffs=cutoffs[[issue]],n=n,unit_cny=unit_cny,
    budget_cny=budget_cny,main_multiples=main_multiples,main_stake=main_stake,
    payout_factor=payout_factor,owner_exception=owner_exception,historical_admission=FALSE)
  c(artifact,list(seal=digest::digest(artifact,algo='sha256')))
}

# Settle a sealed plan with audited winning prices. Missing/contradictory SP
# fails rather than dropping stakes. An explicitly audited missing SPF price is
# allowed only for an already losing ticket, where no SPF payout is due. All seven must hit MAIN for any parlay
# payout; score singles pay independently, not as a replacement parlay leg.
# Returns theoretical pre-tax CNY payouts under one ticket-level factor; no
# rounding/tax/cap policy or actual wager execution is implied.
settle_seven_double <- function(plan,audit,python,project_root) {
  if(!identical(plan$seal,digest::digest(plan[setdiff(names(plan),'seal')],algo='sha256'))) stop('Plan seal mismatch')
  keys <- c('issue','slot','provider_id');legs <- plan$legs
  if(anyDuplicated(audit[keys])) stop('Duplicate settlement identities')
  s <- dplyr::left_join(dplyr::select(legs,dplyr::all_of(keys)),audit,by=keys,relationship='one-to-one')
  if(anyNA(s$actual_direction) || any(!s$actual_direction %in% c('W','D','L'))) stop('Complete audited settlement required')
  main_hit <- vapply(seq_len(nrow(legs)),function(i)s$actual_direction[i] %in% strsplit(legs$selected[i],',',fixed=TRUE)[[1]],logical(1))
  unused_missing_sp <- s$status=='spf:MISSING_WINNING_SP' & !is.finite(s$spf_sp) & !all(main_hit)
  if(anyNA(s$status) || any(!(s$status=='READY' | unused_missing_sp)) ||
     any(!is.finite(s$bf_sp)) || any(s$bf_sp<=0) ||
     any((!is.finite(s$spf_sp) | s$spf_sp<=0) & !unused_missing_sp)) stop('Complete audited settlement required')
  if(anyNA(s$handicap) || any(s$handicap!=legs$handicap)) stop('Settlement handicap mismatch')
  module <- project_python_module('src.nowscore_settlement',project_root,python,convert=FALSE)
  protection <- vapply(seq_len(nrow(legs)),function(i)reticulate::py_to_r(module$expected_option(list(play='bf',score=paste(legs$protect_home[i],legs$protect_away[i],sep='-')))),character(1))
  main_hit <- vapply(seq_len(nrow(legs)),function(i)s$actual_direction[i] %in% strsplit(legs$selected[i],',',fixed=TRUE)[[1]],logical(1))
  bf_hit <- protection==s$bf_option
  main_gross <- if(all(main_hit)) plan$unit_cny*plan$main_multiples*plan$payout_factor*prod(s$spf_sp) else 0
  bf_gross <- ifelse(bf_hit,legs$protection_stake*plan$payout_factor*s$bf_sp,0)
  details <- dplyr::mutate(legs,spf_sp=s$spf_sp,bf_sp=s$bf_sp,actual_direction=s$actual_direction,
    main_hit=main_hit,settlement_status=s$status,unused_missing_sp=unused_missing_sp,protection_option=protection,protection_hit=bf_hit,protection_gross=bf_gross)
  gross <- main_gross+sum(bf_gross)
  list(legs=details,summary=tibble::tibble(issue=legs$issue[1],main_hits=sum(main_hit),
    parlay_hit=all(main_hit),protection_hits=sum(bf_hit),main_stake=plan$main_stake,
    protection_stake=sum(legs$protection_stake),stake=plan$budget_cny,
    main_gross=main_gross,protection_gross=sum(bf_gross),gross=gross,net=gross-plan$budget_cny,
    roi=(gross-plan$budget_cny)/plan$budget_cny),plan_seal=plan$seal)
}
