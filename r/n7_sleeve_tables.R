# Descriptive views of an already frozen #424 candidate bundle, not a learning
# or decision function. bundle is a JSON list parsed with simplifyVector=FALSE;
# cutoff_receipt is its exact named slot->UTC timestamp map, model_id an explicit
# frozen identifier. Admission remains false. No fetching, fitting or I/O.
# Returns dense matrices (rows=sleeves, columns=canonical state codes), 1-based
# rank_idx, sleeve summary, all 1..2187 depth points and identity-preserving long
# audit rows. Probabilities are fractions, entropy nats, payout/value CNY.
# Missing/invalid identity, mass, prices, cutoffs or selected state IDs stop.
n7_sleeve_tables <- function(bundle,cutoff_receipt,model_id) {
 stopifnot(is.list(bundle),is.list(cutoff_receipt),length(cutoff_receipt)>0,
  identical(bundle$cutoffs,cutoff_receipt),identical(bundle$historical_admission,FALSE),
  is.character(model_id),length(model_id)==1,!is.na(model_id),nzchar(model_id),
  length(bundle$sleeves)>0)
 count<-length(bundle$sleeves)
 canonical<-as.matrix(expand.grid(rep(list(0:2),7)))[,7:1,drop=FALSE]
 codes<-apply(canonical,1,paste0,collapse='')
 official<-apply(matrix(c('3','1','0')[canonical+1],nrow=2187),1,paste0,collapse='')
 prob_mat<-payout_hat_mat<-value_mat<-matrix(NA_real_,nrow=count,ncol=2187,dimnames=list(NULL,codes))
 rank_idx<-matrix(NA_integer_,nrow=count,ncol=2187)
 summaries<-depths<-audits<-vector('list',count)
 ids<-integer(count)
 for(j in seq_len(count)) {
  g<-bundle$sleeves[[j]];e<-g$enumeration;ids[j]<-g$id
  state<-matrix(as.integer(unlist(e$states)),nrow=2187,byrow=TRUE)
  indices<-as.integer(unlist(g$fixture_indices))+1L
  stopifnot(length(indices)==7,all(indices>=1 & indices<=length(bundle$expanded_pool$fixtures)),
   identical(e$fixtures,bundle$expanded_pool$fixtures[indices]))
  p<-as.numeric(unlist(e$probability));pay<-as.numeric(unlist(e$estimated_payout));value<-as.numeric(unlist(e$expected_contribution))
  slots<-vapply(e$fixtures,function(x)as.character(x$slot),character(1))
  expected<-cutoff_receipt[slots]
  stopifnot(identical(unname(state),unname(canonical)),length(unique(slots))==7,
   identical(e$cutoffs[sort(names(e$cutoffs))],expected[sort(names(expected))]),identical(e$historical_admission,FALSE),
   all(lengths(list(p,pay,value))==2187),all(is.finite(p)),all(p>=0),abs(sum(p)-1)<=1e-8,
   all(is.finite(pay)),all(pay>0),all(is.finite(value)),
   isTRUE(all.equal(value,p*pay,tolerance=1e-12)))
  source_mass<-rep(1,2187);source_payout<-rep(1.3,2187)
  for(k in seq_len(7)) {
   fixture<-e$fixtures[[k]];pp<-c(fixture$p_W,fixture$p_D,fixture$p_L);qq<-c(fixture$q_W,fixture$q_D,fixture$q_L)
   stopifnot(length(pp)==3,length(qq)==3,all(is.finite(c(pp,qq))),all(pp>=0),all(qq>0),
    abs(sum(pp)-1)<=1e-8,abs(sum(qq)-1)<=1e-8)
   source_mass<-source_mass*pp[canonical[,k]+1L];source_payout<-source_payout/qq[canonical[,k]+1L]
  }
  stopifnot(isTRUE(all.equal(p,source_mass,tolerance=1e-12)),isTRUE(all.equal(pay,source_payout,tolerance=1e-12)))
  rank<-order(-p,-value,seq_len(2187));cumulative<-cumsum(p[rank])
  stopifnot(all(diff(cumulative)>=0),abs(tail(cumulative,1)-1)<=1e-8)
  prob_mat[j,]<-p;payout_hat_mat[j,]<-pay;value_mat[j,]<-value;rank_idx[j,]<-rank
  depth<-tibble::tibble(issue=bundle$issue,sleeve_id=g$id,depth=seq_len(2187),
   ticket_col_idx=rank,ticket_code=codes[rank],coverage=cumulative)
  membership<-rep('',2187)
  for(name in names(g$options)) {
   selection<-g$options[[name]];selected<-as.integer(unlist(selection$state_ids))+1L
   stopifnot(all(selected>=1 & selected<=2187),!anyDuplicated(selected),
    (selection$status=='COMPLETE' && length(selected)==64) || (selection$status!='COMPLETE' && length(selected)==0))
   membership[selected]<-ifelse(nzchar(membership[selected]),paste0(membership[selected],'|',name),name)
  }
  prob_rank<-integer(2187);prob_rank[rank]<-seq_len(2187)
  cum_prob<-numeric(2187);cum_prob[rank]<-cumulative
  summary<-tibble::tibble(issue=bundle$issue,sleeve_id=g$id,origin=g$origin,
   fixture_slots=paste(slots,collapse='|'),
   fixture_ids=paste(vapply(e$fixtures,function(x)as.character(x$provider_id),character(1)),collapse='|'),
   model_id=model_id,top1_state_prob=max(p),entropy=-sum(p[p>0]*log(p[p>0])),
   mean_fixture_top1=mean(vapply(e$fixtures,function(x)max(c(x$p_W,x$p_D,x$p_L)),numeric(1))),
   mean_fixture_top2=mean(vapply(e$fixtures,function(x)sum(sort(c(x$p_W,x$p_D,x$p_L),decreasing=TRUE)[1:2]),numeric(1))),
   state_hhi=sum(p^2),top64_expected_gross=sum(value[rank[1:64]]),
   top64_expected_roi=sum(value[rank[1:64]])/128-1,
   source_grade='EXPOSED_HISTORICAL_DIAGNOSTIC',price_grade=e$price_lane,
   historical_admission=FALSE,bundle_seal=bundle$seal,enumeration_seal=e$seal,
   cutoff_receipt=as.character(jsonlite::toJSON(e$cutoffs,auto_unbox=TRUE)))
  for(m in c(16,32,64,128,256,512,2187))summary[[paste0('coverage_',m)]]<-cumulative[m]
  summaries[[j]]<-summary;depths[[j]]<-depth
  audits[[j]]<-tibble::tibble(issue=bundle$issue,sleeve_id=g$id,ticket_code=codes,
   official_outcomes=official,ticket_col_idx=seq_len(2187),prob=p,prob_rank=prob_rank,cum_prob=cum_prob,
   payout_hat=pay,expected_gross_contribution=value,selected_rules=membership)
 }
 stopifnot(!anyDuplicated(ids))
 rownames(prob_mat)<-rownames(payout_hat_mat)<-rownames(value_mat)<-rownames(rank_idx)<-as.character(ids)
 list(prob_mat=prob_mat,payout_hat_mat=payout_hat_mat,value_mat=value_mat,rank_idx=rank_idx,
  summary=dplyr::bind_rows(summaries),depth=dplyr::bind_rows(depths),long=dplyr::bind_rows(audits))
}
