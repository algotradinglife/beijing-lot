# Descriptive distribution geometry; no fitting, tuning, routing or I/O.
# fixtures: unique issue/slot/provider_id, actual_direction and p_W/D/L,q_W/D/L.
# members: unique issue/sleeve_id/slot, exactly n_legs per group. All fixtures
# and group members must match. n_legs and prefix_depth are explicit integers.
# Returns fixture metrics and exact independent-product group metrics for both
# frozen models. Natural-log entropy/surprise are in nats; probabilities [0,1].
# Zero probability has zero entropy contribution and infinite actual surprise.
# Ties use W,D,L for fixture ranks; group actual rank is an interval (relative
# tolerance 1e-10), so prefix_hit_low/high bound tie-breaking uncertainty.
strategy_distribution_shape <- function(fixtures,members,n_legs,prefix_depth) {
  keys<-c('issue','slot','provider_id')
  stopifnot(length(n_legs)==1L,is.finite(n_legs),n_legs>=1,n_legs<=7,n_legs==trunc(n_legs),
    length(prefix_depth)==1L,is.finite(prefix_depth),prefix_depth>=1,
    prefix_depth<=3^n_legs,prefix_depth==trunc(prefix_depth),
    all(c(keys,'actual_direction',paste0(rep(c('p','q'),each=3),'_',rep(c('W','D','L'),2))) %in% names(fixtures)),
    nrow(fixtures)>0,!anyNA(fixtures[keys]),is.character(fixtures$issue),is.character(fixtures$provider_id),
    !anyDuplicated(fixtures[c('issue','slot')]),all(fixtures$actual_direction %in% c('W','D','L')),
    all(c('issue','sleeve_id','slot') %in% names(members)),nrow(members)>0,
    !anyNA(members[c('issue','sleeve_id','slot')]),!anyDuplicated(members[c('issue','sleeve_id','slot')]))
  counts<-members |> dplyr::count(issue,sleeve_id)
  stopifnot(all(counts$n==n_legs),nrow(dplyr::anti_join(members,fixtures,by=c('issue','slot')))==0)
  ff<-list();gg<-list()
  for(model in c('p','q')) {
    mat<-as.matrix(fixtures[paste0(model,'_',c('W','D','L'))])
    stopifnot(all(is.finite(mat)),all(mat>=0),all(mat<=1),all(abs(rowSums(mat)-1)<1e-8))
    sorted<-t(apply(mat,1,sort,decreasing=TRUE))
    z<-fixtures[keys];z$model<-model
    z$top1<-sorted[,1];z$top2<-sorted[,2];z$top3<-sorted[,3]
    z$gap12<-z$top1-z$top2;z$gap23<-z$top2-z$top3
    z$entropy<- -rowSums(ifelse(mat>0,mat*log(mat),0))
    z$actual_probability<-mat[cbind(seq_len(nrow(mat)),match(fixtures$actual_direction,c('W','D','L')))]
    z$surprise<- -log(z$actual_probability)
    ranked<-t(apply(mat,1,order,decreasing=TRUE))
    z$actual_rank<-max.col(ranked==match(fixtures$actual_direction,c('W','D','L')),ties.method='first')
    z$entropy_residual<-z$surprise-z$entropy
    ff[[model]]<-z
    z$fixture_index<-seq_len(nrow(z))
    m<-members |> dplyr::left_join(z,by=c('issue','slot'),relationship='many-to-one')
    groups<-split(seq_len(nrow(m)),interaction(m$issue,m$sleeve_id,drop=TRUE))
    rows<-lapply(groups,function(idx) {
      a<-m[idx,];j<-a$fixture_index
      probs<-1
      for(i in j) probs<-as.vector(outer(probs,mat[i,],'*'))
      probs<-sort(probs,decreasing=TRUE)
      actual<-prod(a$actual_probability);tol<-actual*1e-10
      lo<-1L+sum(probs>actual+tol);hi<-sum(probs>=actual-tol)
      entropy<-sum(a$entropy);surprise<-sum(a$surprise)
      tibble::tibble(issue=a$issue[1],sleeve_id=a$sleeve_id[1],model=model,
        gap12=mean(a$gap12),entropy=entropy,effective_states=exp(entropy),
        actual_probability=actual,surprise=surprise,entropy_residual=surprise-entropy,
        actual_rank_low=lo,actual_rank_high=hi,expected_rank=sum(seq_along(probs)*probs),
        prefix_coverage=sum(head(probs,prefix_depth)),
        prefix_hit_low=hi<=prefix_depth,prefix_hit_high=lo<=prefix_depth,
        cumulative_mid=sum(probs[probs>actual+tol])+.5*sum(probs[abs(probs-actual)<=tol]),
        first=sum(a$actual_rank==1),second=sum(a$actual_rank==2),third=sum(a$actual_rank==3))
    })
    gg[[model]]<-dplyr::bind_rows(rows)
  }
  list(fixtures=dplyr::bind_rows(ff),groups=dplyr::bind_rows(gg))
}
