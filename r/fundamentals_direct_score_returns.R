# Fixed historical diagnostic, no fitting: retain supplied frozen groups and
# doubles. Inputs are label-free legs and normalized final score grids, fixture
# cutoffs, CNY2 units and CNY256/issue. Returns sealed long-form singles ledger.
# Mixed arms each receive CNY128 via proportional largest remainder allocation;
# ties use slot then provider ID. No I/O; invalid/missing inputs stop.
direct_score_plan <- function(legs,scores,cutoffs,unit_cny,score_budget) {
  keys <- c('issue','slot','provider_id')
  legs <- dplyr::select(legs,dplyr::all_of(c(keys,'handicap','selected','group','protect_home','protect_away','protection_stake')))
  if(unit_cny!=2 || score_budget!=256 || !nrow(legs) || anyNA(legs) || anyDuplicated(legs[keys]) ||
     any(!is.finite(legs$protection_stake)) || any(legs$protection_stake<0 | legs$protection_stake%%unit_cny!=0)) stop('Invalid frozen legs/constants')
  if(any(!is.finite(legs$handicap)) || any(legs$handicap%%1!=0)) stop('Integer handicap required')
  out <- list()
  for(issue in unique(legs$issue)) {
    z <- dplyr::filter(legs,.data$issue==.env$issue) |> dplyr::arrange(slot,provider_id)
    if(any(!as.character(z$slot) %in% names(cutoffs[[issue]])) || anyNA(unlist(cutoffs[[issue]][as.character(z$slot)]))) stop('Missing fixture cutoff')
    if(sum(z$protection_stake)!=score_budget || any(table(z$group)!=7) || length(unique(z$group))>6 || anyDuplicated(z$slot) || anyDuplicated(z$provider_id)) stop('Invalid original budget/groups')
    z$direct_home <- z$direct_away <- z$direct_probability <- NA_real_
    for(i in seq_len(nrow(z))) {
      g <- scores[scores$issue==issue & scores$slot==z$slot[i] & scores$provider_id==z$provider_id[i],]
      if(!nrow(g) || anyNA(g[c('home_goals','away_goals','probability')]) ||
         any(!is.finite(as.matrix(g[c('home_goals','away_goals','probability')])) ) ||
         any(g$probability<0) || abs(sum(g$probability)-1)>1e-6 ||
         any(g$home_goals<0 | g$away_goals<0 | g$home_goals%%1!=0 | g$away_goals%%1!=0) || anyDuplicated(g[c('home_goals','away_goals')])) stop('Invalid final score grid')
      dirs <- strsplit(z$selected[i],',',fixed=TRUE)[[1]]
      net <- z$protect_home[i]-z$protect_away[i]+z$handicap[i]
      direction <- if(net>0) 'W' else if(net==0) 'D' else 'L'
      if(length(dirs)!=2 || anyDuplicated(dirs) || !all(dirs %in% c('W','D','L')) || direction %in% dirs ||
         any(c(z$protect_home[i],z$protect_away[i])<0) || any(c(z$protect_home[i],z$protect_away[i])%%1!=0)) stop('Invalid protection direction')
      g <- g[order(-g$probability,g$home_goals,g$away_goals),]
      z$direct_home[i] <- g$home_goals[1]; z$direct_away[i] <- g$away_goals[1];z$direct_probability[i] <- g$probability[1]
    }
    quota <- z$protection_stake/unit_cny/2
    units <- floor(quota);remaining <- score_budget/2/unit_cny-sum(units)
    if(remaining>0) { ix <- order(-(quota-units),z$slot,z$provider_id)[seq_len(remaining)];units[ix] <- units[ix]+1 }
    for(strategy in c('protection','direct','mixed')) for(arm in if(strategy=='mixed') c('protection','direct') else strategy) {
      a <- z;a$strategy <- strategy;a$arm <- arm
      a$score_home <- if(arm=='direct') z$direct_home else z$protect_home
      a$score_away <- if(arm=='direct') z$direct_away else z$protect_away
      a$stake <- if(strategy=='mixed') units*unit_cny else z$protection_stake
      out[[length(out)+1]] <- a
    }
  }
  artifact <- list(ledger=dplyr::bind_rows(out),cutoffs=cutoffs,unit_cny=unit_cny,score_budget=score_budget,historical_admission=FALSE)
  c(artifact,list(seal=digest::digest(artifact,algo='sha256')))
}

# Settle singles against audited winning BF options using the authoritative
# Python option mapper. Main returns are carried once from reconciled original
# totals. Same-option arms sum naturally; one 0.65 factor per singles stake.
# All money in CNY; no tax/cap/rounding. No writes; invalid audits fail closed.
settle_direct_scores <- function(plan,audit,totals,payout_factor,python,project_root) {
  if(payout_factor!=.65 || !identical(plan$seal,digest::digest(plan[setdiff(names(plan),'seal')],algo='sha256'))) stop('Plan seal/constants mismatch')
  keys <- c('issue','slot','provider_id')
  if(anyDuplicated(audit[keys]) || anyDuplicated(totals$issue)) stop('Duplicate settlement identity')
  s <- dplyr::left_join(plan$ledger,dplyr::select(audit,dplyr::all_of(keys),audit_handicap=handicap,bf_option,bf_sp,status),by=keys,relationship='many-to-one')
  if(anyNA(s[c('audit_handicap','bf_option','bf_sp','status')]) || any(s$audit_handicap!=s$handicap) || any(!is.finite(s$bf_sp) | s$bf_sp<=0) || any(!s$status %in% c('READY','spf:MISSING_WINNING_SP'))) stop('Complete BF audit required')
  module <- project_python_module('src.nowscore_settlement',project_root,python,convert=FALSE)
  s$option <- vapply(seq_len(nrow(s)),function(i)reticulate::py_to_r(module$expected_option(list(play='bf',score=paste(s$score_home[i],s$score_away[i],sep='-')))),character(1))
  s$hit <- s$option==s$bf_option;s$score_gross <- ifelse(s$hit,s$stake*payout_factor*s$bf_sp,0)
  rows <- s |> dplyr::group_by(issue,strategy) |> dplyr::summarise(score_stake=sum(stake),score_gross=sum(score_gross),.groups='drop') |>
    dplyr::left_join(dplyr::select(totals,issue,actual_groups,original_stake=stake,main_gross),by='issue',relationship='many-to-one')
  if(anyNA(rows) || any(!is.finite(rows$main_gross)) || any(rows$main_gross<0) || any(rows$score_stake!=plan$score_budget) || any(rows$original_stake!=rows$actual_groups*256+plan$score_budget)) stop('Settlement budget reconciliation failed')
  rows <- rows |> dplyr::mutate(stake=original_stake,gross=main_gross+score_gross,net=gross-stake,roi=net/stake,score_net=score_gross-score_stake)
  list(rows=rows,ledger=s,plan_seal=plan$seal)
}
