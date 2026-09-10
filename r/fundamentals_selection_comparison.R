# Build disjoint seven-match groups from frozen diagnostic model factors.
# Explicit fixture cutoffs and business constants; no labels or refitting.
# Verifies the source implementation receipt, uses shared temporal objects and
# provenance, and freezes JSON before settlement. Returns plans/summary/receipt.
selection_comparison_plans <- function(source_path,cutoffs,python,project_root,output_path,
    n,groups,unit_cny,budget_cny,payout_factor,owner_exception,methods=c("ev","coverage"),group_policy="fixed") {
  if(length(c(n,groups,unit_cny,budget_cny,payout_factor))!=5L || anyNA(c(n,groups,unit_cny,budget_cny,payout_factor)) ||
     n!=7 || !groups %in% 1:6 || unit_cny!=2 || budget_cny!=256*groups+256 || payout_factor!=.65) stop('Explicit fixed business constants required')
  if(!length(methods) || anyDuplicated(methods) || !all(methods %in% c('ev','coverage'))) stop('Explicit valid methods required')
  if(length(group_policy)!=1L || is.na(group_policy) || !group_policy %in% c('fixed','cap')) stop('Explicit valid group policy required')
  prior <- jsonlite::read_json(source_path,simplifyVector=TRUE)
  if(!identical(prior$cutoffs,cutoffs) || owner_exception!='OWNER_AUTHORIZED_HISTORICAL_RETURNS' ||
     !identical(prior$owner_exception,owner_exception) || !identical(prior$historical_admission,FALSE)) stop('Explicit matching diagnostic cutoffs required')
  ev_settle_plans(list(plans=list(),implementation=prior$implementation),tibble::tibble(),python,project_root)
  fields <- c('issue','slot','provider_id','scenario','handicap','selected','protect_home','protect_away',
    'main_factor','protection_factor','p_W','p_D','p_L','q_W','q_D','q_L')
  factors <- dplyr::select(prior$factors,dplyr::all_of(fields))
  if(anyDuplicated(factors[c('issue','slot','scenario')]) || anyDuplicated(factors[c('issue','provider_id','scenario')])) stop('Duplicate candidate identities')
  for(prefix in c('p_','q_')) {
    z <- as.matrix(factors[paste0(prefix,c('W','D','L'))])
    if(any(!is.finite(z)) || any(z<0) || any(abs(rowSums(z)-1)>1e-8)) stop('Normalized candidate probabilities required')
  }
  goals <- unlist(factors[c('protect_home','protect_away')]);h <- factors$handicap
  if(any(!is.finite(c(goals,h))) || any(goals<0 | goals%%1!=0) || any(h%%1!=0)) stop('Integer handicap/protection scores required')
  factors$double_probability <- factors$market_double_probability <- NA_real_
  for(i in seq_len(nrow(factors))) {
    dirs <- strsplit(factors$selected[i],',',fixed=TRUE)[[1]]
    if(length(dirs)!=2 || anyDuplicated(dirs) || !all(dirs %in% c('W','D','L'))) stop('Two valid directions required')
    factors$double_probability[i] <- sum(unlist(factors[i,paste0('p_',dirs)]))
    factors$market_double_probability[i] <- sum(unlist(factors[i,paste0('q_',dirs)]))
  }
  module <- project_python_module('src.fundamentals_disjoint_portfolios',project_root,python,convert=FALSE)
  temporal <- project_python_module('src.temporal_learning',project_root,python,convert=FALSE)
  plans <- summaries <- solutions <- list()
  scopes <- dplyr::distinct(prior$summary,issue,scenario)
  for(i in seq_len(nrow(scopes))) {
    issue <- scopes$issue[i];model <- scopes$scenario[i]
    rows <- dplyr::filter(factors,.data$issue==.env$issue,scenario==model)
    actual_groups <- if(group_policy=='cap') min(groups,nrow(rows)%/%n) else groups
    actual_budget <- if(actual_groups==0) 0 else 256*actual_groups+256
    pycuts <- lapply(cutoffs[[issue]],function(stamp)temporal$Cutoff$decision_epoch(issue,stamp))
    inputs <- lapply(seq_len(nrow(rows)),function(j)as.list(rows[j,c('issue','slot','provider_id','main_factor','protection_factor','double_probability')]))
    for(method in methods) {
      key <- paste(issue,model,method,sep='/')
      if(!nrow(rows) || actual_groups==0) {
        summaries[[key]] <- tibble::tibble(issue=issue,model=model,selection=method,status=paste0('FEWER_THAN_',if(group_policy=='cap') n else n*groups,'_CANDIDATES'),candidates=nrow(rows),actual_groups=0L,planned_stake=0,expected_gross=NA_real_,mean_double_probability=NA_real_,model_any_win_probability=NA_real_,model_expected_winning_groups=NA_real_)
        next
      }
      sol <- reticulate::py_to_r(module$select_disjoint_portfolios(inputs,cutoffs=pycuts,method=method,n=as.integer(n),groups=as.integer(actual_groups),
        unit_cny=as.integer(unit_cny),budget_cny=as.integer(actual_budget),payout_factor=payout_factor,owner_exception=owner_exception))
      solutions[[key]] <- sol
      if(sol$status!='PLANNED') {
        summaries[[key]] <- tibble::tibble(issue=issue,model=model,selection=method,status=sol$status,candidates=nrow(rows),actual_groups=0L,planned_stake=0,expected_gross=NA_real_,mean_double_probability=NA_real_,model_any_win_probability=NA_real_,model_expected_winning_groups=NA_real_)
        next
      }
      selected <- dplyr::left_join(dplyr::select(dplyr::bind_rows(sol$selected),issue,slot,provider_id,group,protection_stake),rows,
        by=c('issue','slot','provider_id'),relationship='one-to-one')
      legs <- dplyr::select(selected,issue,slot,provider_id,handicap,selected,protect_home,protect_away,group,protection_stake)
      if(nrow(legs)!=n*actual_groups || anyDuplicated(legs$slot) || anyDuplicated(legs$provider_id) || sum(legs$protection_stake)!=256) stop('Disjoint allocation contract failed')
      plan <- list(legs=legs,n=n,groups=actual_groups,unit_cny=unit_cny,budget_cny=actual_budget,payout_factor=payout_factor,
        cutoffs=cutoffs[[issue]],owner_exception=owner_exception,historical_admission=FALSE)
      plan$seal <- digest::digest(plan,algo='sha256');plans[[key]] <- plan
      group_probabilities <- vapply(seq_len(actual_groups),function(g)prod(selected$double_probability[selected$group==g]),numeric(1))
      summaries[[key]] <- tibble::tibble(issue=issue,model=model,selection=method,status='PLANNED',candidates=nrow(rows),actual_groups=actual_groups,planned_stake=actual_budget,expected_gross=sol$expected_gross,
        mean_double_probability=mean(selected$double_probability),model_any_win_probability=1-prod(1-group_probabilities),model_expected_winning_groups=sum(group_probabilities))
    }
  }
  provenance <- project_python_module('src.temporal_learning.provenance',project_root,python,convert=FALSE)
  closure <- reticulate::py_to_r(provenance$implementation_closure(reticulate::import('pathlib',convert=FALSE)$Path(project_root),
    c('src.fundamentals_disjoint_portfolios','src.nowscore_settlement')))
  implementation <- list(python=closure,r=prior$implementation$r)
  file <- 'r/fundamentals_selection_comparison.R'
  implementation$r[[file]] <- digest::digest(file=file.path(project_root,file),algo='sha256')
  artifact <- list(group_policy=group_policy,group_limit=groups,maximum_budget_cny=budget_cny,plans=plans,summary=dplyr::bind_rows(summaries),solutions=solutions,implementation=implementation,
    cutoffs=cutoffs,source_sha256=digest::digest(file=source_path,algo='sha256'),
    owner_exception=owner_exception,historical_admission=FALSE)
  encoded <- as.character(jsonlite::toJSON(artifact,auto_unbox=TRUE,dataframe='rows',digits=15,na='null',null='null'))
  dir.create(dirname(output_path),recursive=TRUE,showWarnings=FALSE)
  if(file.exists(output_path)) {
    if(!identical(readChar(output_path,file.info(output_path)$size,useBytes=TRUE),encoded)) stop('Frozen selection comparison changed')
  } else writeChar(encoded,output_path,eos=NULL,useBytes=TRUE)
  c(artifact,list(prediction_sha256=digest::digest(file=output_path,algo='sha256')))
}

# Settle each of the disjoint groups independently using existing ticket
# settlement arithmetic and BF category mapping. Protection is allocated once
# across selected identities. Missing settlement or altered plans fail closed.
settle_selection_comparison <- function(predictions,audit,python,project_root) {
  ev_settle_plans(list(plans=list(),implementation=predictions$implementation),tibble::tibble(),python,project_root)
  details <- group_rows <- list()
  for(key in names(predictions$plans)) {
    plan <- predictions$plans[[key]]
    if(!identical(plan$seal,digest::digest(plan[setdiff(names(plan),'seal')],algo='sha256'))) stop('Plan seal mismatch')
    parts <- strsplit(key,'/',fixed=TRUE)[[1]]
    if(nrow(plan$legs)!=plan$n*plan$groups || anyDuplicated(plan$legs$slot) || anyDuplicated(plan$legs$provider_id) ||
      !identical(as.integer(table(plan$legs$group)),rep(7L,plan$groups)) || sum(plan$legs$protection_stake)!=256) stop('Disjoint allocation contract failed')
    for(g in seq_len(plan$groups)) {
      legs <- dplyr::filter(plan$legs,group==g)
      ticket <- list(legs=legs,unit_cny=plan$unit_cny,main_multiples=1,main_stake=256,
        budget_cny=256+sum(legs$protection_stake),payout_factor=plan$payout_factor)
      ticket$seal <- digest::digest(ticket,algo='sha256')
      settled <- settle_seven_double(ticket,audit,python,project_root)
      group_rows[[paste(key,g)]] <- dplyr::mutate(settled$summary,model=parts[2],selection=parts[3],group=g)
      details[[paste(key,g)]] <- dplyr::mutate(settled$legs,model=parts[2],selection=parts[3])
    }
  }
  groups <- dplyr::bind_rows(group_rows)
  summary <- if(nrow(groups)) groups |> dplyr::group_by(issue,model,selection) |>
    dplyr::summarise(main_hits=sum(main_hits),parlay_wins=sum(parlay_hit),protection_hits=sum(protection_hits),
      stake=sum(stake),main_gross=sum(main_gross),protection_gross=sum(protection_gross),gross=sum(gross),net=sum(net),roi=net/stake,.groups='drop') else
    tibble::tibble(issue=character(),model=character(),selection=character(),main_hits=integer(),parlay_wins=integer(),protection_hits=integer(),stake=double(),main_gross=double(),protection_gross=double(),gross=double(),net=double(),roi=double())
  unplanned <- predictions$summary |> dplyr::filter(status!='PLANNED') |> dplyr::select(issue,model,selection) |>
    dplyr::mutate(main_hits=0L,parlay_wins=0L,protection_hits=0L,stake=0,main_gross=0,protection_gross=0,gross=0,net=0,roi=NA_real_)
  summary <- dplyr::bind_rows(summary,unplanned)
  list(summary=summary,groups=groups,legs=dplyr::bind_rows(details),prediction_sha256=predictions$prediction_sha256)
}
