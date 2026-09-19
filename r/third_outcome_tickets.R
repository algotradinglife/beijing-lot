# Label-free fixed-group purchase preferences. No fitting, no I/O.
# fixtures/cutoffs/surface come from a verified frozen PROB replay; funded is
# unique sleeve_id/depth, one CNY2 copy, depth1..128. rules: id/kind/value.
# p remains the original probability; weight is a purchasing distribution only.
# Third mass released by discount/cap goes to ORIGINAL second; the original
# rank labels remain fixed even if the second becomes the largest weight.
# HARD restricts to original Top2 but preserves their original product ordering.
# Receipt binds inputs, exact cutoff map, parameters and this implementation.
third_outcome_ticket_plan <- function(fixtures,surface,funded,cutoffs,python,rules,
                                      unit_cny,payout_factor,budget_cny) {
 n7_joint_validate(fixtures,cutoffs,python)
 f<-dplyr::bind_rows(fixtures)
 stopifnot(unit_cny==2,payout_factor==.65,budget_cny>0,
  all(c('sleeve_id','depth') %in% names(funded)),!anyNA(funded),
  !anyDuplicated(funded$sleeve_id),all(funded$depth %in% 1:128),
  sum(funded$depth)*unit_cny<=budget_cny,
  all(c('id','kind','value') %in% names(rules)),nrow(rules)>0,!anyNA(rules),
  !anyDuplicated(rules$id),all(nzchar(rules$id)),
  all(rules$kind %in% c('discount','cap','hard')),all(is.finite(rules$value)),
  all(rules$value>=0 & rules$value<=1),all(rules$value[rules$kind=='hard']==0),
  !anyDuplicated(surface$summary$sleeve_id),
  all(as.character(funded$sleeve_id) %in% rownames(surface$prob_mat)))
 canonical<-as.matrix(expand.grid(rep(list(0:2),7)))[,7:1,drop=FALSE]
 options<-members<-list()
 for(j in seq_len(nrow(funded))) {
  sid<-as.character(funded$sleeve_id[j]);depth<-funded$depth[j]
  ss<-surface$summary[as.character(surface$summary$sleeve_id)==sid,]
  slots<-as.integer(strsplit(ss$fixture_slots,'|',fixed=TRUE)[[1]])
  stopifnot(length(slots)==7,!anyDuplicated(slots),all(slots %in% f$slot))
  gf<-f[match(slots,f$slot),];p<-as.matrix(gf[c('p_W','p_D','p_L')]);q<-as.matrix(gf[c('q_W','q_D','q_L')])
  orders<-t(apply(p,1,function(v)order(-v,1:3)))
  mass<-rep(1,2187);pay<-rep(unit_cny*payout_factor,2187);thirds<-integer(2187)
  for(k in 1:7) {
   mass<-mass*p[k,canonical[,k]+1];pay<-pay/q[k,canonical[,k]+1]
   thirds<-thirds+as.integer(canonical[,k]+1==orders[k,3])
  }
  mass<-as.numeric(mass);pay<-as.numeric(pay)
  stopifnot(max(abs(mass-surface$prob_mat[sid,]))<1e-12,
   max(abs(pay-surface$payout_hat_mat[sid,])/pay)<1e-12)
  base_order<-order(-mass,-mass*pay,1:2187)
  stopifnot(identical(as.integer(base_order),as.integer(surface$rank_idx[sid,])))
  members[[j]]<-tibble::tibble(issue=gf$issue,sleeve_id=sid,slot=gf$slot,
   provider_id=gf$provider_id,handicap=gf$handicap,third=c('W','D','L')[orders[,3]],
   p3=p[cbind(1:7,orders[,3])],p2=p[cbind(1:7,orders[,2])],depth=depth)
  for(i in seq_len(nrow(rules))) {
   rule<-rules[i,];w<-p
   if(rule$kind!='hard')for(k in 1:7) {
    old<-p[k,orders[k,3]]
    new<-if(rule$kind=='discount')old*rule$value else min(old,rule$value)
    w[k,orders[k,3]]<-new;w[k,orders[k,2]]<-p[k,orders[k,2]]+old-new
   }
   weight<-rep(1,2187)
   for(k in 1:7)weight<-weight*w[k,canonical[,k]+1]
   weight<-as.numeric(weight)
   stopifnot(abs(sum(weight)-1)<1e-10)
   order<-order(-weight,-mass*pay,1:2187)
   if(rule$kind=='hard')order<-order[thirds[order]==0]
   ids<-order[seq_len(depth)]
   options[[length(options)+1L]]<-list(sleeve_id=sid,rule=rule$id,depth=depth,
    state_ids=ids,purchase_order=order,probability=mass,selection_weight=weight,
    estimated_payout=pay,third_count=thirds,fixture_slots=slots,
    coverage=sum(mass[ids]),expected_gross=sum(mass[ids]*pay[ids]),
    top2_coverage=sum(mass[ids][thirds[ids]==0]),third_tickets=sum(thirds[ids]>0),
    base_state_ids=base_order[seq_len(depth)],stake=depth*unit_cny)
  }
 }
 receipt<-list(cutoffs=cutoffs,input_hash=digest::digest(list(fixtures,surface,funded),algo='sha256'),
  rules=rules,unit_cny=unit_cny,payout_factor=payout_factor,budget_cny=budget_cny,
  implementation=digest::digest(third_outcome_ticket_plan,algo='sha256'),historical_admission=FALSE)
 member_schema<-tibble::tibble(issue=character(),sleeve_id=character(),slot=integer(),
  provider_id=character(),handicap=double(),third=character(),p3=double(),p2=double(),depth=integer())
 result<-list(issue=f$issue[1],options=options,members=dplyr::bind_rows(member_schema,members),receipt=receipt)
 result$seal<-digest::digest(result,algo='sha256');result
}

# Post-freeze settlement. labels is unique issue/slot/provider_id with handicap,
# actual_direction and positive official spf_sp. No label-driven plan changes.
# Returns one funded-group/rule row; actual third states forbidden by HARD have
# NA rank. Official payout factor applied exactly once here to product SP.
third_outcome_ticket_settle <- function(plan,labels) {
 stopifnot(identical(plan$seal,digest::digest(plan[names(plan)!='seal'],algo='sha256')),
  all(c('issue','slot','provider_id','handicap','actual_direction','spf_sp') %in% names(labels)),
  !anyNA(labels),!anyDuplicated(labels[c('issue','slot','provider_id')]),
  !anyDuplicated(labels[c('issue','slot')]),
  all(labels$actual_direction %in% c('W','D','L')),all(is.finite(labels$spf_sp)),all(labels$spf_sp>0))
 rows<-list()
 for(opt in plan$options) {
  m<-plan$members[plan$members$sleeve_id==opt$sleeve_id,]
  l<-labels[labels$issue==plan$issue,];l<-l[match(m$slot,l$slot),]
  stopifnot(nrow(l)==7,!anyNA(l),identical(l$provider_id,m$provider_id),all(l$handicap==m$handicap))
  state<-1+sum((match(l$actual_direction,c('W','D','L'))-1)*3^(6:0))
  rank<-match(state,opt$purchase_order);hit<-state %in% opt$state_ids;base_hit<-state %in% opt$base_state_ids
  gross<-plan$receipt$unit_cny*plan$receipt$payout_factor*prod(l$spf_sp)
  rows[[length(rows)+1L]]<-tibble::tibble(issue=plan$issue,sleeve_id=opt$sleeve_id,rule=opt$rule,
   depth=opt$depth,stake=opt$stake,coverage=opt$coverage,top2_coverage=opt$top2_coverage,
   expected_gross=opt$expected_gross,third_tickets=opt$third_tickets,
   actual_rank=rank,actual_thirds=opt$third_count[state],actual_probability=opt$probability[state],
   actual_gross=gross,estimated_actual_gross=opt$estimated_payout[state],
   hit=hit,base_hit=base_hit,gross=ifelse(hit,gross,0),base_gross=ifelse(base_hit,gross,0),
   rescued=hit & !base_hit,lost=!hit & base_hit,
   actual_cumulative=if(is.na(rank))NA_real_ else sum(opt$probability[opt$purchase_order[seq_len(rank)]]))
 }
 schema<-tibble::tibble(issue=character(),sleeve_id=character(),rule=character(),depth=integer(),
  stake=double(),coverage=double(),top2_coverage=double(),expected_gross=double(),third_tickets=integer(),
  actual_rank=integer(),actual_thirds=integer(),actual_probability=double(),actual_gross=double(),
  estimated_actual_gross=double(),hit=logical(),base_hit=logical(),gross=double(),base_gross=double(),
  rescued=logical(),lost=logical(),actual_cumulative=double())
 dplyr::bind_rows(schema,rows)
}
