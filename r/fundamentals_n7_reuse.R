# R facade over the authoritative Python N7 bridge and support transforms.
# Source r/python_bridge.R first. Imports never fetch data or install packages.
# Runtime is explicit; every call checks interpreter and implementation identity.
.n7_reuse_runtime <- function(python,project_root) {
  names <- c(single='src.fundamentals_n7_single',bridge='src.fundamentals_compression_bridge',
    breadth='src.fundamentals_compression_breadth',support='src.fundamentals_repeated_support',
    settle='src.fundamentals_compression_variants',temporal='src.temporal_learning',core='src.temporal_learning.core',
    provenance='src.temporal_learning.provenance')
  out <- lapply(names,project_python_module,project_root=project_root,python=python,convert=FALSE)
  out$json <- reticulate::import('json',convert=FALSE)
  out$path <- reticulate::import('pathlib',convert=FALSE)$Path(normalizePath(project_root))
  out$r_hashes <- stats::setNames(lapply(c('r/python_bridge.R','r/fundamentals_n7_reuse.R'),
    function(p) digest::digest(file=file.path(project_root,p),algo='sha256')),c('r/python_bridge.R','r/fundamentals_n7_reuse.R'))
  out
}

# frame: one issue, unique integer slots, string issue/provider_id (leading zeros
# preserved), integer handicap, normalized p_W/D/L and q_W/D/L. Optional home/away
# names are retained in source identity. No labels or other columns allowed.
# cutoffs: named list of explicit UTC timestamps, one per slot; converted only by
# shared Cutoff.decision_epoch. Probabilities are caller-supplied, never fitted.
# q is comparable handicap market probability from pre-match Euro+OU mapping.
# Business constants/seeds are explicit. Returns an in-session prepared context
# with native Python objects, sealed references/designs and implementation receipt.
# Reuse this context for a parameter grid. Re-prepare in a new R session; do not
# persist Python pointers as RDS. No file writes, scraping, settlement or learning.
prepare_n7_reuse <- function(frame,cutoffs,python,project_root,n,budget_cny,unit_cny,payout_factor,
                             candidate_seed,pool_size,design_seed,design_draws) {
  required <- c('issue','slot','provider_id','handicap',paste0('p_',c('W','D','L')),paste0('q_',c('W','D','L')))
  stopifnot(is.data.frame(frame),nrow(frame)>=7L,all(required %in% names(frame)),
    all(names(frame) %in% c(required,'home','away')),!anyDuplicated(names(frame)),
    is.character(frame$issue),length(unique(frame$issue))==1L,is.character(frame$provider_id),
    !anyNA(frame),is.numeric(frame$slot),all(frame$slot%%1==0),!anyDuplicated(frame$slot),
    is.list(cutoffs),!is.null(names(cutoffs)),!anyDuplicated(names(cutoffs)),setequal(names(cutoffs),as.character(frame$slot)))
  constants <- c(n,budget_cny,unit_cny,payout_factor)
  stopifnot(all(lengths(list(n,budget_cny,unit_cny,payout_factor))==1L),
    all(vapply(list(n,budget_cny,unit_cny,payout_factor),is.numeric,logical(1))))
  stopifnot(length(constants)==4L,all(is.finite(constants)),n==7,budget_cny==1024,unit_cny==2,payout_factor==.65)
  seeds <- c(candidate_seed,pool_size,design_seed,design_draws)
  stopifnot(all(lengths(list(candidate_seed,pool_size,design_seed,design_draws))==1L),
    all(vapply(list(candidate_seed,pool_size,design_seed,design_draws),is.numeric,logical(1))))
  stopifnot(length(seeds)==4L,is.numeric(seeds),all(is.finite(seeds)),all(seeds%%1==0),
    candidate_seed>=0,design_seed>=0,pool_size>=128,design_draws>0,all(seeds<=.Machine$integer.max))
  rt <- .n7_reuse_runtime(python,project_root)
  cuts <- reticulate::dict(convert=FALSE)
  for(s in names(cutoffs)) {
    stopifnot(is.character(cutoffs[[s]]),length(cutoffs[[s]])==1L,!is.na(cutoffs[[s]]))
    cuts$`__setitem__`(s,rt$temporal$Cutoff$decision_epoch(frame$issue[1],cutoffs[[s]]))
  }
  frame <- as.data.frame(frame);frame$slot <- as.integer(frame$slot)
  pf <- reticulate::r_to_py(frame);refs <- reticulate::dict(convert=FALSE)
  for(d in 1:2) refs$`__setitem__`(d,rt$single$n7_single_plan(pf,cutoffs=cuts,budget_cny=as.integer(budget_cny),
    single_rule='MAX_SINGLE',single_count=d,max_uses=2L,unit_cny=as.integer(unit_cny),payout_factor=payout_factor,allocation_seed=0L))
  pool <- rt$breadth$breadth_candidates(pf,cutoffs=cuts,seed=as.integer(candidate_seed),pool_size=as.integer(pool_size))
  surfaces <- designs <- vector('list',2L)
  for(d in 1:2) {
    surfaces[[d]] <- rt$bridge$bridge_surface(pf,pool,refs,cutoffs=cuts,depth=d)
    designs[[d]] <- rt$breadth$breadth_scenarios(pf,surfaces[[d]],cutoffs=cuts,seed=as.integer(design_seed),draws=as.integer(design_draws))
  }
  implementation <- rt$provenance$implementation_closure(rt$path,
    as.list(c('src.fundamentals_n7_single','src.fundamentals_compression_bridge',
      'src.fundamentals_compression_breadth','src.fundamentals_repeated_support','src.fundamentals_compression_variants')),
    distributions=as.list(c('numpy','pandas','scipy')))
  prepared <- list(frame=pf,references=refs,surfaces=surfaces,designs=designs,cutoffs=cutoffs,issue=frame$issue[1],
    implementation=implementation,r_hashes=rt$r_hashes,parameters=list(n=as.integer(n),budget_cny=as.integer(budget_cny),
      unit_cny=as.integer(unit_cny),payout_factor=as.numeric(payout_factor),candidate_seed=as.integer(candidate_seed),pool_size=as.integer(pool_size),
      design_seed=as.integer(design_seed),design_draws=as.integer(design_draws)),scope='FIXED_RULE_DIAGNOSTIC_NO_FIT')
  binding <- prepared[c('cutoffs','issue','parameters','scope','r_hashes')]
  binding$implementation <- reticulate::py_to_r(implementation)
  prepared$metadata_seal <- reticulate::py_to_r(rt$core$stable_json_hash(reticulate::r_to_py(binding)))
  prepared
}

# single_count: 1 or 2. U: positive integer fixture reuse cap. P: integer 0..6
# pair overlap cap. Fixed TOP2 ranking, preserved disjoint prefix, cash held.
# replace_singles: later single occurrences with original p1 <= single_ceiling
# choose original second direction, never toggle. double_rule: NONE/GAP/MARKET/
# EITHER; later doubles can choose Top1+Top3. Thresholds are probability units.
# cutoffs must exactly match preparation; no automatic latest/default cutoff.
# Returns a portable sealed bundle_json (BASE and SELECTED), legs/tickets tibbles,
# receipt with implementation/source/cutoff identities. No settlement or writes.
plan_n7_reuse <- function(prepared,cutoffs,single_count,U,P,python,project_root,
                          replace_singles=FALSE,single_ceiling=.75,double_rule='NONE',
                          max_gap=.05,minimum_tv=.15,minimum_market_tail_lead=.05) {
  stopifnot(length(single_count)==1L,is.numeric(single_count),!is.na(single_count),single_count %in% 1:2,
    length(U)==1L,is.numeric(U),is.finite(U),U>=1,U%%1==0,U<=.Machine$integer.max,
    length(P)==1L,is.numeric(P),is.finite(P),P %in% 0:6,identical(cutoffs,prepared$cutoffs),
    is.logical(replace_singles),length(replace_singles)==1L,!is.na(replace_singles),
    is.character(double_rule),length(double_rule)==1L,double_rule %in% c('NONE','GAP','MARKET','EITHER'))
  thresholds <- c(single_ceiling,max_gap,minimum_tv,minimum_market_tail_lead)
  stopifnot(all(lengths(list(single_ceiling,max_gap,minimum_tv,minimum_market_tail_lead))==1L),
    all(vapply(list(single_ceiling,max_gap,minimum_tv,minimum_market_tail_lead),is.numeric,logical(1))))
  stopifnot(length(thresholds)==4L,is.numeric(thresholds),all(is.finite(thresholds)),all(thresholds>=0 & thresholds<=1))
  rt <- .n7_reuse_runtime(python,project_root)
  stopifnot(identical(rt$r_hashes,prepared$r_hashes),identical(prepared$scope,'FIXED_RULE_DIAGNOSTIC_NO_FIT'))
  binding <- prepared[c('cutoffs','issue','parameters','scope','r_hashes')]
  binding$implementation <- reticulate::py_to_r(prepared$implementation)
  stopifnot(identical(prepared$metadata_seal,reticulate::py_to_r(rt$core$stable_json_hash(reticulate::r_to_py(binding)))))
  rt$provenance$verify_implementation_closure(rt$path,prepared$implementation)
  cuts <- reticulate::dict(convert=FALSE)
  for(s in names(cutoffs)) cuts$`__setitem__`(s,rt$temporal$Cutoff$decision_epoch(prepared$issue,cutoffs[[s]]))
  p <- prepared$parameters;d <- as.integer(single_count)
  base <- rt$bridge$bridge_plan(prepared$frame,prepared$surfaces[[d]],prepared$designs[[d]],
    prepared$references$`__getitem__`(d),cutoffs=cuts,preserve_prefix=TRUE,quality='TOP2',overlap='CAPPED',
    max_uses=as.integer(U),max_pair_overlap=as.integer(P),cash_policy='HOLD',
    budget_cny=as.integer(p$budget_cny),unit_cny=as.integer(p$unit_cny),payout_factor=p$payout_factor)
  selected <- if(!replace_singles && double_rule=='NONE') base else
    rt$support$replace_repeated_support(base,cutoffs=cuts,change_singles=replace_singles,double_rule=double_rule,
      single_ceiling=single_ceiling,max_gap=max_gap,minimum_tv=minimum_tv,minimum_market_tail_lead=minimum_market_tail_lead)
  rule_parameters <- list(single_count=d,U=as.integer(U),P=as.integer(P),replace_singles=replace_singles,single_ceiling=as.numeric(single_ceiling),
    double_rule=double_rule,max_gap=as.numeric(max_gap),minimum_tv=as.numeric(minimum_tv),minimum_market_tail_lead=as.numeric(minimum_market_tail_lead))
  rule_id <- reticulate::py_to_r(rt$core$stable_json_hash(reticulate::r_to_py(c(p,rule_parameters))))
  case <- paste0('C',d,'_U',U,'_P',P,'_',rule_id)
  bundle <- reticulate::dict(convert=FALSE)
  for(rule in c('BASE','SELECTED')) bundle$`__setitem__`(paste0(case,'_',rule),
    reticulate::dict(case=case,rule=rule,depth=d,quality='TOP2',overlap=paste0('U',U,'_P',P),
      plan=if(rule=='BASE') base else selected,evaluation=reticulate::dict(metrics=reticulate::dict()),convert=FALSE))
  payload <- reticulate::py_to_r(rt$json$dumps(bundle))
  native <- jsonlite::fromJSON(reticulate::py_to_r(rt$json$dumps(selected)),simplifyVector=TRUE)
  receipt <- list(scope=prepared$scope,cutoffs=cutoffs,input_sha256=native$input_sha256,plan_seal=native$seal,
    implementation=reticulate::py_to_r(prepared$implementation),r_hashes=rt$r_hashes,
    parameters=c(p,rule_parameters),
    bundle_sha256=digest::digest(payload,algo='sha256',serialize=FALSE))
  receipt$seal <- reticulate::py_to_r(rt$core$stable_json_hash(reticulate::r_to_py(receipt)))
  list(bundle_json=payload,legs=tibble::as_tibble(native$legs),tickets=tibble::as_tibble(native$tickets),
    summary=tibble::tibble(issue=prepared$issue,single_count=d,U=U,P=P,groups=native$groups,
      stake_cny=native$stake,cash_cny=native$cash_cny),receipt=receipt)
}

# Explicit accepted settlement audit: unique issue/slot/provider_id, READY status,
# handicap, actual_direction W/D/L, positive final spf_sp. Reads portable bundle,
# checks receipt and delegates payouts/paired changes to authoritative settlement.
# Returns two tidy rows (BASE/SELECTED), CNY amounts and probability-unit ROI.
# This is evaluation only; audit is never passed to preparation/selection.
settle_n7_reuse <- function(plan,audit,python,project_root) {
  stopifnot(identical(digest::digest(plan$bundle_json,algo='sha256',serialize=FALSE),plan$receipt$bundle_sha256))
  rt <- .n7_reuse_runtime(python,project_root)
  receipt <- plan$receipt;seal <- receipt$seal;receipt$seal <- NULL
  stopifnot(identical(seal,reticulate::py_to_r(rt$core$stable_json_hash(reticulate::r_to_py(receipt)))))
  stopifnot(identical(plan$receipt$r_hashes,rt$r_hashes))
  rt$provenance$verify_implementation_closure(rt$path,reticulate::r_to_py(plan$receipt$implementation))
  result <- rt$settle$settle_compression_variants(rt$json$loads(plan$bundle_json),reticulate::r_to_py(as.data.frame(audit)))
  rows <- jsonlite::fromJSON(reticulate::py_to_r(rt$json$dumps(result)),simplifyVector=TRUE) |> tibble::as_tibble()
  for(k in c('single_count','U','P','replace_singles','single_ceiling','double_rule','max_gap','minimum_tv','minimum_market_tail_lead'))
    rows[[k]] <- plan$receipt$parameters[[k]]
  rows
}
