# Freeze one issue of a fixed predeclared factorial diagnostic. job: manifest row
# with issue/path/sha256/allocations; config: explicit business constants and grid.
# Reads a verified legacy probability bundle; does not access settlement. Writes
# a new gzipped JSON plan, refuses overwrite. Shared Cutoff boundary owns clocks.
# Returns output path. All generated plans retain historical_admission=FALSE.
joint_payout_freeze_issue <- function(job,config,python,output) {
 stopifnot(!file.exists(output),config$unit_cny==2,config$payout_factor==.65,
  config$budget_cny==1024,is.character(job$issue),length(job$issue)==1)
 reticulate::use_python(python,required=TRUE)
 reader<-reticulate::import('src.strategy_diagnostic_inputs',convert=TRUE)
 b<-jsonlite::fromJSON(reader$read_verified_bundle_json(job$path,job$sha256),simplifyVector=FALSE)
 stopifnot(identical(b$issue,job$issue))
 n7_joint_validate(b$expanded_pool$fixtures,b$cutoffs,python)
 a<-dplyr::bind_rows(job$allocations)
 if(!nrow(a))a<-tibble::tibble(sleeve_id=integer(),depth=integer())
 stopifnot(!anyDuplicated(a$sleeve_id),sum(a$depth)*config$unit_cny<=config$budget_cny)
 plans<-list();cutoffs<-b$cutoffs
 if(nrow(a)) {
  view<-n7_sleeve_tables(b,cutoffs,'frozen_joint_calibrated_market')
  worlds<-n7_joint_worlds(list(cutoffs=cutoffs,fixtures=b$expanded_pool$fixtures),cutoffs,
                         config$coverage_seed,config$coverage_worlds)
  selected_sleeves<-b$sleeves[vapply(b$sleeves,function(x)x$id %in% a$sleeve_id,logical(1))]
  world_states<-lapply(selected_sleeves,function(x)as.integer(worlds[,as.integer(unlist(x$fixture_indices))+1L,drop=FALSE] %*% (3^(6:0)))+1L)
  names(world_states)<-vapply(selected_sleeves,function(x)as.character(x$id),character(1))
 }
 specs<-list()
 for(floor in unlist(config$payout_floor_grid_cny))for(exposure in config$exposure_grid)
  specs[[paste0('P',floor,'_',exposure$name)]]<-list(floor=floor,exposure=exposure)
 for(share in unlist(config$supplement_shares))
  specs[[paste0('MIX',round(100*share))]]<-list(share=share)
 for(arm in names(specs)) {
  spec<-specs[[arm]];floor<-spec$floor;exposure<-spec$exposure
  if(nrow(a)) {
   if(!is.null(spec$share)) {
    z<-joint_payout_mix(b,view,a,cutoffs,python,config$budget_cny,config$unit_cny,
     config$main_floor_cny,config$supplement_floor_cny,spec$share)
    z$reason_counts<-c(MAIN=z$main_stake/config$unit_cny,SUPPLEMENT=z$supplement_stake/config$unit_cny)
   } else z<-joint_payout_exposure(b,view,a,cutoffs,python,config$budget_cny,config$unit_cny,
                          floor,exposure$fixture_cny,exposure$direction_cny)
   tickets<-z$tickets |> dplyr::select(sleeve_id,ticket_col_idx,prob,payout_hat,expected_gross_contribution,prob_rank)
   hit<-rep(FALSE,config$coverage_worlds)
   for(id in names(world_states))hit<-hit | world_states[[id]] %in% tickets$ticket_col_idx[as.character(tickets$sleeve_id)==id]
   if(arm=='P0_OPEN') {
    stopifnot(z$stake==sum(a$depth)*config$unit_cny)
    for(i in seq_len(nrow(a)))stopifnot(setequal(tickets$ticket_col_idx[tickets$sleeve_id==a$sleeve_id[i]],view$rank_idx[as.character(a$sleeve_id[i]),seq_len(a$depth[i])]))
   }
   plans[[arm]]<-list(tickets=tickets,groups=z$groups,stake=z$stake,cash=z$cash,
    union_coverage=mean(hit),union_mc_se=sqrt(mean(hit)*(1-mean(hit))/length(hit)),
    expected_gross=sum(tickets$expected_gross_contribution),
    max_fixture_exposure=max(z$fixture_exposure),max_direction_exposure=max(z$direction_exposure),
    reasons=as.list(z$reason_counts))
  } else plans[[arm]]<-list(tickets=list(),groups=list(),stake=0,cash=config$budget_cny,
    union_coverage=0,union_mc_se=0,expected_gross=0,max_fixture_exposure=0,max_direction_exposure=0,reasons=list())
 }
 result<-list(issue=b$issue,cutoffs=cutoffs,historical_admission=FALSE,
  evidence_class='EXPOSED_HISTORICAL_DIAGNOSTIC',partitions='NO_FIT_TUNE_CALIBRATION',
  source_sha256=job$sha256,allocations=a,plans=plans)
 con<-gzfile(output,'wb');on.exit(close(con),add=TRUE)
 writeBin(charToRaw(jsonlite::toJSON(result,auto_unbox=TRUE,digits=NA,null='null',dataframe='rows')),con)
 output
}

# Independently recompute published metrics from frozen ticket IDs and original
# probabilities; no selection or settlement. Recreates shared worlds with the
# explicit diagnostic seed. Returns TRUE, fails on altered/null/missing metrics.
joint_payout_verify_metrics <- function(bundle,plan,config,python) {
 n7_joint_validate(bundle$expanded_pool$fixtures,bundle$cutoffs,python)
 stopifnot(identical(plan$cutoffs,bundle$cutoffs),identical(plan$issue,bundle$issue))
 if(length(bundle$sleeves))view<-n7_sleeve_tables(bundle,bundle$cutoffs,'frozen_joint_calibrated_market')
 worlds<-n7_joint_worlds(list(cutoffs=bundle$cutoffs,fixtures=bundle$expanded_pool$fixtures),bundle$cutoffs,
  config$coverage_seed,config$coverage_worlds)
 sid<-vapply(bundle$sleeves,function(g)as.character(g$id),character(1))
 for(arm in names(plan$plans)) {
  z<-plan$plans[[arm]];tickets<-dplyr::bind_rows(z$tickets)
  exposure<-numeric(length(bundle$expanded_pool$fixtures));direction<-matrix(0,length(exposure),3)
  hit<-rep(FALSE,config$coverage_worlds);expected<-0
  if(nrow(tickets)) {
   for(id in unique(tickets$sleeve_id)) {
    ix<-as.integer(unlist(bundle$sleeves[[match(as.character(id),sid)]]$fixture_indices))+1L
    t<-tickets[tickets$sleeve_id==id,];k<-t$ticket_col_idx
    stopifnot(!anyDuplicated(k),all(k %in% 1:2187),
     isTRUE(all.equal(t$prob,unname(view$prob_mat[as.character(id),k]),tolerance=1e-12)),
     isTRUE(all.equal(t$payout_hat,unname(view$payout_hat_mat[as.character(id),k]),tolerance=1e-12)),
     isTRUE(all.equal(t$expected_gross_contribution,unname(view$value_mat[as.character(id),k]),tolerance=1e-12)))
    states<-outer(k-1,3^(6:0),'%/%')%%3
    exposure[ix]<-exposure[ix]+config$unit_cny*nrow(t)
    for(j in seq_len(7))direction[ix[j],]<-direction[ix[j],]+config$unit_cny*tabulate(states[,j]+1L,nbins=3)
    hit<-hit | (as.integer(worlds[,ix,drop=FALSE] %*% (3^(6:0)))+1L) %in% k
    expected<-expected+sum(t$expected_gross_contribution)
   }
  }
  stopifnot(isTRUE(all.equal(z$union_coverage,mean(hit),tolerance=1e-12)),
   isTRUE(all.equal(z$union_mc_se,sqrt(mean(hit)*(1-mean(hit))/length(hit)),tolerance=1e-12)),
   isTRUE(all.equal(z$expected_gross,expected,tolerance=1e-12)),
   isTRUE(all.equal(z$max_fixture_exposure,max(exposure),tolerance=1e-12)),
   isTRUE(all.equal(z$max_direction_exposure,max(direction),tolerance=1e-12)))
  g<-dplyr::bind_rows(z$groups)
  if(nrow(tickets)) {
   expected_groups<-tickets |> dplyr::group_by(sleeve_id) |>
    dplyr::summarise(tickets=dplyr::n(),coverage=sum(prob),estimated_gross=sum(expected_gross_contribution),.groups='drop')
   stopifnot(nrow(g)==nrow(expected_groups),setequal(g$sleeve_id,expected_groups$sleeve_id))
   g<-g[match(expected_groups$sleeve_id,g$sleeve_id),]
   for(n in c('tickets','coverage','estimated_gross'))stopifnot(isTRUE(all.equal(g[[n]],expected_groups[[n]],tolerance=1e-12)))
  } else stopifnot(nrow(g)==0)
 }
 TRUE
}
