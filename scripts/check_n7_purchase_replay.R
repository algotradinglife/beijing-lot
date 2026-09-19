# Independent mathematical/accounting replay; no production purchase/settlement functions.
suppressPackageStartupMessages({library(dplyr);library(jsonlite)})
args<-commandArgs(TRUE);root<-args[1];expected<-args[2];destination<-args[3]
rp<-file.path(root,'plans-receipt.json');stopifnot(digest::digest(file=rp,algo='sha256')==expected)
r<-fromJSON(rp,simplifyVector=FALSE)
checked<-0L;ticket_count<-0L
for(id in unlist(r$scope)) {
 b<-r$bindings[[id]];path<-file.path(root,b$file)
 stopifnot(digest::digest(file=path,algo='sha256')==b$sha256)
 plan<-readRDS(path);stopifnot(identical(plan$seal,digest::digest(plan[names(plan)!='seal'],algo='sha256')))
 for(name in names(plan$arms)) {
  arm<-plan$arms[[name]];pool<-arm$pool;opts<-pool$options
  stopifnot(identical(arm$options,opts[arm$fit$selected]),
   identical(plan$fixtures,pool$fixtures))
  nf<-length(pool$fixtures);no<-length(opts)
  outcomes<-withr::with_seed(plan$seed,vapply(pool$fixtures,function(f) {
   u<-runif(plan$worlds);as.integer((u>=f$p_W)+(u>=f$p_W+f$p_D))
  },integer(plan$worlds)))
  events<-matrix(FALSE,plan$worlds,no);uses<-matrix(0,nf,no);money<-matrix(0,nf*3,no)
  costs<-values<-sids<-numeric(no)
  for(j in seq_along(opts)) {
   a<-opts[[j]];stopifnot(length(a$fixtures)==7,length(a$state_ids)==a$depth,!anyDuplicated(a$state_ids))
   # Rebuild all canonical states from fixture probabilities, independently
   # of saved ranking/probability vectors and production purchase functions.
   full_prob<-rep(1,2187);full_pay<-rep(1.3,2187)
   third_count<-penalty_count<-integer(2187)
   pp<-pool$purchase_parameters
   for(k in 1:7) {
    f<-pool$fixtures[[a$fixtures[k]]];fp<-c(f$p_W,f$p_D,f$p_L)
    direction<-((0:2186) %/% 3^(7-k))%%3+1L
    ranks<-order(-fp,1:3);third<-direction==ranks[3]
    full_prob<-full_prob*fp[direction]
    full_pay<-full_pay/c(f$q_W,f$q_D,f$q_L)[direction]
    third_count<-third_count+third
    penalty_count<-penalty_count+third*(fp[ranks[2]]-fp[ranks[3]]>=pp$gap_threshold)
   }
   rank_score<-full_prob
   if(pp$policy=='GAP')rank_score<-rank_score*pp$third_penalty^penalty_count
   ranked<-order(-rank_score,-full_prob*full_pay,1:2187)
   if(pp$policy=='HARD')ranked<-ranked[third_count[ranked]==0]
   stopifnot(identical(as.integer(a$state_ids),as.integer(head(ranked,a$depth))))
   codes<-a$state_ids-1L;prob<-rep(1,length(codes));pay<-rep(1.3,length(codes))
   for(k in 1:7) {
    f<-pool$fixtures[[a$fixtures[k]]];d<-(codes %/% 3^(7-k))%%3+1L
    prob<-prob*c(f$p_W,f$p_D,f$p_L)[d];pay<-pay/c(f$q_W,f$q_D,f$q_L)[d]
    money[(a$fixtures[k]-1L)*3+1:3,j]<-tabulate(d,3)*2
   }
   stopifnot(abs(sum(prob)-a$coverage)<1e-10,abs(sum(prob*pay)-a$expected_gross)<1e-7,a$stake==2*length(codes))
   uses[a$fixtures,j]<-1
   realized<-as.integer(outcomes[,a$fixtures,drop=FALSE] %*% 3^(6:0))+1L
   events[,j]<-realized %in% a$state_ids
   costs[j]<-a$stake;values[j]<-a$expected_gross;sids[j]<-a$sleeve_id
  }
  policy<-plan$policies[plan$policies$id==name,]
  upper_use<-rep(Inf,nf);upper_money<-rep(Inf,nf*3)
  if('u' %in% names(policy)) {upper_use[]<-policy$u;upper_money[]<-policy$money}
  if('confidence' %in% names(policy) && policy$confidence)for(k in 1:nf) {
   f<-pool$fixtures[[k]];p<-c(f$p_W,f$p_D,f$p_L);sorted<-sort(p,decreasing=TRUE)
   upper_use[k]<-if(sorted[2]-sorted[3]>=.05)policy$high_uses else policy$low_uses
   for(d in 1:3)upper_money[(k-1)*3+d]<-if(p[d]-max(p[-d])>=.05)policy$high_stake else policy$low_stake
  }
  selected<-integer();ordering<-if('ordering' %in% names(policy))policy$ordering else 'OPEN_FIRST'
  for(step in 1:1024) {
   spent<-sum(costs[selected]);open<-pool$opening_options[!sids[pool$opening_options] %in% sids[selected]]
   open<-open[costs[open]<=1024-spent]
   legal<-vapply(seq_along(opts),function(j) {
    proposal<-c(selected[sids[selected]!=sids[j]],j)
    all(rowSums(uses[,proposal,drop=FALSE])<=upper_use) && all(rowSums(money[,proposal,drop=FALSE])<=upper_money+1e-8)
   },logical(1))
   open<-open[legal[open]]
   if(length(open) && (ordering=='OPEN_FIRST' || pool$mode=='BREADTH'))candidate<-open else {
    if(pool$mode=='BREADTH')break
    candidate<-which(sids %in% sids[selected] & !seq_along(opts) %in% selected & legal)
    candidate<-candidate[vapply(candidate,function(j) {
     old<-selected[sids[selected]==sids[j]]
     length(old)==1 && costs[j]>costs[old] && costs[j]-costs[old]<=1024-spent
    },logical(1))]
    if(ordering=='COMPETE')candidate<-c(open,candidate)
   }
   if(!length(candidate))break
   current<-rowSums(events[,selected,drop=FALSE])>0
   scores<-lapply(candidate,function(j) {
    old<-selected[sids[selected]==sids[j]];proposal<-c(setdiff(selected,old),j)
    cost<-costs[j]-sum(costs[old]);gain<-mean(rowSums(events[,proposal,drop=FALSE])>0)-mean(current)
    c(j=j,rate=gain/cost,value=(values[j]-sum(values[old])-cost)/cost,gain=gain)
   })
   scores<-do.call(rbind,scores)
   winner<-order(-scores[,'rate'],-scores[,'value'],-scores[,'gain'],sids[scores[,'j']],scores[,'j'])[1]
   j<-as.integer(scores[winner,'j']);selected<-c(selected[sids[selected]!=sids[j]],j)
  }
  stopifnot(identical(as.integer(selected),as.integer(arm$fit$selected)),sum(costs[selected])<=1024)
  checked<-checked+1L;ticket_count<-ticket_count+sum(vapply(opts[selected],function(x)length(x$state_ids),integer(1)))
 }
 writeLines(paste(id,checked),paste0(destination,'.progress'))
}
write_json(list(status='PASS',receipt_sha256=expected,issues=length(r$scope),allocations=checked,purchased_tickets= ticket_count,
 scope='independent canonical probability/value, fixture/direction exposure and greedy selection replay; labels not opened'),destination,auto_unbox=TRUE,pretty=TRUE)
