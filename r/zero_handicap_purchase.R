# Controlled diagnostic intervention. One row per fixture, W/D/L fractions.
# Euro rows must cover every zero-handicap fixture exactly. Nonzero fixtures
# remain byte-equivalent; p-only leaves q unchanged. No labels, fitting or I/O.
# Explicit cutoffs are checked by the shared native validator.
zero_purchase_fixtures <- function(fixtures, euro, cutoffs, python, arm) {
 stopifnot(arm %in% c('BASE','EURO_P','EURO_PQ'),
  setequal(names(fixtures),c('issue','slot','provider_id','handicap',paste0('p_',c('W','D','L')),paste0('q_',c('W','D','L')))),
  setequal(names(euro),c('issue','slot','provider_id','handicap','odds_W','odds_D','odds_L')),
  !anyDuplicated(euro[c('issue','slot','provider_id')]),all(euro$handicap==0))
 n7_joint_validate(fixtures,cutoffs,python)
 out<-fixtures;ix<-which(fixtures$handicap==0)
 key<-paste(fixtures$issue,fixtures$slot,fixtures$provider_id)
 j<-match(key[ix],paste(euro$issue,euro$slot,euro$provider_id))
 stopifnot(!anyNA(j))
 odds<-as.matrix(euro[j,paste0('odds_',c('W','D','L'))]);stopifnot(all(is.finite(odds)),all(odds>1))
 p<-1/odds;p<-p/rowSums(p)
 if(arm!='BASE')out[ix,paste0('p_',c('W','D','L'))]<-p
 if(arm=='EURO_PQ')out[ix,paste0('q_',c('W','D','L'))]<-p
 n7_joint_validate(out,cutoffs,python);out
}

# Revalue an immutable existing candidate universe; group membership and all
# canonical 2187 state IDs are preserved. Money in CNY. Requires exact fixture
# identities/order and explicit cutoffs. Returns a newly sealed diagnostic bundle.
zero_purchase_bundle <- function(bundle, fixtures, cutoffs, model_id, unit_cny, payout_factor) {
 stopifnot(identical(bundle$cutoffs,cutoffs),unit_cny==2,payout_factor==.65,
  identical(dplyr::bind_rows(bundle$expanded_pool$fixtures)[c('issue','slot','provider_id','handicap')],
   fixtures[c('issue','slot','provider_id','handicap')]))
 prediction<-fixtures[c('issue','slot','provider_id',paste0('p_',c('W','D','L')))];names(prediction)[4:6]<-paste0('new_',c('W','D','L'))
 out<-n7_probability_bundle(bundle,prediction,cutoffs,model_id)
 for(i in seq_len(nrow(fixtures)))for(d in c('W','D','L'))out$expanded_pool$fixtures[[i]][[paste0('q_',d)]]<-fixtures[[paste0('q_',d)]][i]
 for(i in seq_along(out$sleeves)) {
  g<-out$sleeves[[i]];e<-g$enumeration
  e$fixtures<-out$expanded_pool$fixtures[as.integer(unlist(g$fixture_indices))+1L]
  states<-matrix(as.integer(unlist(e$states)),2187,byrow=TRUE);pay<-rep(unit_cny*payout_factor,2187)
  for(k in 1:7)pay<-pay/unlist(e$fixtures[[k]][paste0('q_',c('W','D','L'))],use.names=FALSE)[states[,k]+1L]
  e$estimated_payout<-as.list(pay);e$expected_contribution<-as.list(pay*unlist(e$probability))
  e$seal<-digest::digest(e[names(e)!='seal'],algo='sha256');g$enumeration<-e;out$sleeves[[i]]<-g
 }
 out$seal<-digest::digest(out[names(out)!='seal'],algo='sha256');out
}

# Native diversified Top2 re-selection on an EXISTING candidate list only.
# Same exact union increment, expected-gross tie-break and SP gate as native
# top2_fresh_groups. Candidate generation is deliberately frozen, not rerun.
# Return a plan compatible with top2_fresh_settle; no settlement access.
zero_purchase_top2 <- function(fresh, fixtures, cutoffs, python) {
 stopifnot(identical(fresh$cutoffs,cutoffs),identical(fresh$seal,digest::digest(fresh[names(fresh)!='seal'],algo='sha256')),
  identical(fresh$fixtures[c('issue','slot','provider_id','handicap')],fixtures[c('issue','slot','provider_id','handicap')]))
 n7_joint_validate(fixtures,cutoffs,python);s<-fresh$parameters
 p<-as.matrix(fixtures[paste0('p_',c('W','D','L'))]);q<-as.matrix(fixtures[paste0('q_',c('W','D','L'))])
 options<-t(apply(p,1,function(z)order(-z,seq_along(z))[1:2]))
 coords<-cbind(rep(seq_len(nrow(p)),each=2),as.vector(t(options)))
 mass<-rowSums(matrix(p[coords],ncol=2,byrow=TRUE));factor<-rowSums(matrix((p/q)[coords],ncol=2,byrow=TRUE))
 eligible<-which(1/q[cbind(seq_len(nrow(p)),options[,1])]>=s$minimum_sp)
 groups<-fresh$groups;ok<-vapply(groups,function(g)all(g %in% eligible),logical(1))
 prob<-vapply(groups,function(g)prod(mass[g]),numeric(1));ev<-vapply(groups,function(g)s$unit_cny*s$payout_factor*prod(factor[g]),numeric(1))
 ids<-integer();coverage<-numeric()
 for(k in seq_len(min(sum(ok),floor(s$budget_cny/(s$unit_cny*2^s$n))))) {
  inc<-top2_group_increment(groups,groups[ids],mass);score<-inc;score[!ok]<- -Inf;score[ids]<- -Inf
  chosen<-order(-score,-ev,seq_along(groups))[1L];ids<-c(ids,chosen);coverage<-c(coverage,sum(tail(coverage,1),inc[chosen]))
 }
 out<-fresh;out$fixtures<-fixtures;out$options<-options;out$mass<-mass;out$eligible<-eligible
 out$probability<-prob;out$expected_gross<-ev;out$selected<-list(TOP2_DIVERSE=ids);out$union_probability<-list(TOP2_DIVERSE=coverage)
 out$seal<-digest::digest(out[names(out)!='seal'],algo='sha256');out
}

# Convert native selected options or a full Top2 plan to the existing sealed
# ticket settlement contract. Both use canonical W/D/L base-3 state IDs.
# No outcomes or I/O; callers freeze this result before opening label files.
zero_purchase_tickets <- function(fixtures, groups, picks, cutoffs, settings, policy) {
 stopifnot(length(cutoffs)>0,all(as.character(fixtures$slot) %in% names(cutoffs)),settings$unit_cny==2,settings$payout_factor==.65)
 parts<-lapply(picks,function(o)tibble::tibble(issue=fixtures$issue[1],policy=policy,group_id=as.integer(o$sleeve_id),
  state_id=as.integer(o$state_ids),probability=as.numeric(o$state_probability[o$state_ids]),estimated_payout=as.numeric(o$state_payout[o$state_ids]),outside_support=NA))
 tickets<-dplyr::bind_rows(c(list(tibble::tibble(issue=character(),policy=character(),group_id=integer(),state_id=integer(),probability=double(),estimated_payout=double(),outside_support=logical())),parts))
 stopifnot(nrow(tickets)*settings$unit_cny<=settings$budget_cny,!anyDuplicated(tickets[c('group_id','state_id')]))
 out<-list(issue=fixtures$issue[1],fixtures=fixtures,groups=groups,tickets=tickets,policies=policy,cutoffs=cutoffs,settings=settings,historical_admission=FALSE)
 out$seal<-joint_candidate_seal(out);out
}

# Validate a parallel freeze receipt against its aggregate experiment contract.
# No I/O or learning. Parent identity is required, not just a matching scope:
# the Top2 parent supplies the fixed candidate universe. Returns TRUE or errors.
zero_purchase_chunk <- function(part, config, code, closure_sha256) {
 stopifnot(part$status=='FROZEN_NOT_SETTLED',identical(part$code,code),
  identical(part$closure$closure_sha256,closure_sha256),
  identical(part$config$scope_sha256,config$scope_sha256),
  identical(part$config$euro_manifest_sha256,config$euro_manifest_sha256))
 for(k in c('top2','joint','reference'))for(field in c('path','sha256'))
  stopifnot(identical(part$config[[k]][[field]],config[[k]][[field]]))
 if(!is.null(part$config$inputs)||!is.null(config$inputs))stopifnot(identical(part$config$inputs,config$inputs))
 expected<-jsonlite::fromJSON(jsonlite::toJSON(config$settings,auto_unbox=TRUE,digits=NA),simplifyVector=FALSE)
 stopifnot(identical(part$config$settings,expected));TRUE
}

# Reusable six-arm controlled issue replay. Reuse native JOINT and Top2
# algorithms, candidate memberships, explicit cutoff and settings. euro is the
# complete zero-line quote subset; fresh_control and joint_control are frozen
# original plans. BASE must reproduce both. No labels, learning, or I/O.
zero_purchase_compare <- function(bundle, fresh_control, joint_control, euro,
                                  cutoffs, python, settings) {
 stopifnot(identical(bundle$cutoffs,cutoffs))
 b<-bundle;s<-settings;f<-dplyr::bind_rows(b$expanded_pool$fixtures);ef<-euro;id<-b$issue
 states<-as.matrix(expand.grid(rep(list(0:2),7)))[,7:1,drop=FALSE]
 frozen<-list();audit<-list()
 for(arm in c('BASE','EURO_P','EURO_PQ')) {
  ff<-zero_purchase_fixtures(f,dplyr::select(ef,issue,slot,provider_id,handicap,odds_W,odds_D,odds_L),b$cutoffs,python,arm)
  bb<-if(arm=='BASE')b else zero_purchase_bundle(b,ff,b$cutoffs,arm,s$unit_cny,s$payout_factor)
  a<-n7_probability_allocate(bb,b$cutoffs,arm,python,s$target_coverage,s$group_cap_cny,s$minimum_sp,s$budget_cny,s$unit_cny,s$payout_factor,s$seed,s$worlds,s$max_actions)
  picks<-a$pool$options[a$fit$selected]
  if(arm=='BASE') {
   ref<-joint_control
   stopifnot(identical(lapply(picks,function(o)list(o$sleeve_id,o$state_ids)),lapply(ref,function(o)list(o$sleeve_id,o$state_ids))))
  }
  groups<-dplyr::bind_rows(lapply(bb$sleeves,function(g)tibble::tibble(group_id=as.integer(g$id),fixture_index=as.integer(unlist(g$fixture_indices))+1L)))
  frozen[[paste0('JOINT_',arm)]]<-zero_purchase_tickets(ff,groups,picks,b$cutoffs,s,paste0('JOINT_',arm))
  fresh<-zero_purchase_top2(fresh_control,ff,b$cutoffs,python)
  if(arm=='BASE')stopifnot(identical(fresh$options,fresh_control$options),identical(fresh$selected$TOP2_DIVERSE,fresh_control$selected$TOP2_DIVERSE))
  p<-as.matrix(ff[paste0('p_',c('W','D','L'))]);q<-as.matrix(ff[paste0('q_',c('W','D','L'))]);picks<-list()
  for(j in fresh$selected$TOP2_DIVERSE) {
   ix<-fresh$groups[[j]];mask<-rep(TRUE,2187);prob<-rep(1,2187);pay<-rep(s$unit_cny*s$payout_factor,2187)
   for(k in 1:7){mask<-mask & (states[,k]+1L) %in% fresh$options[ix[k],];prob<-prob*p[ix[k],states[,k]+1L];pay<-pay/q[ix[k],states[,k]+1L]}
   stopifnot(sum(mask)==128);picks[[length(picks)+1L]]<-list(sleeve_id=j,state_ids=which(mask),state_probability=prob,state_payout=pay)
  }
  groups<-dplyr::bind_rows(lapply(seq_along(fresh$groups),function(j)tibble::tibble(group_id=as.integer(j),fixture_index=fresh$groups[[j]])))
  frozen[[paste0('TOP2_',arm)]]<-zero_purchase_tickets(ff,groups,picks,b$cutoffs,s,paste0('TOP2_',arm))
  audit[[arm]]<-tibble::tibble(issue=id,arm=arm,fixtures=nrow(ff),zero=sum(ff$handicap==0),eligible=sum(a$gate$fixtures$eligible),joint_candidates=nrow(a$gate$groups),joint_legal=sum(a$gate$groups$eligible),top2_candidates=length(fresh$groups),top2_selected=length(fresh$selected$TOP2_DIVERSE),joint_groups=length(a$fit$selected))
 }
 list(plans=frozen,admission=dplyr::bind_rows(audit))
}
