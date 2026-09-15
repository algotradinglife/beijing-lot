# Independent official settlement and all-issue curve replay. No production helpers.
args<-commandArgs(TRUE);params<-jsonlite::fromJSON(args[1]);output<-args[2]
report<-params$output
rp<-jsonlite::fromJSON(file.path(report,'receipt.json'),simplifyVector=FALSE)
for(n in names(rp$files))stopifnot(digest::digest(file=file.path(report,n),algo='sha256')==rp$files[[n]])
stopifnot(digest::digest(file=params$labels,algo='sha256')==rp$labels_sha256)
labels<-read.csv(params$labels,colClasses=c(issue='character',provider_id='character'))
groups<-read.csv(file.path(report,'groups.csv'),colClasses=c(issue='character'))
periods<-read.csv(file.path(report,'rows.csv'),colClasses=c(issue='character'))
curves<-read.csv(file.path(report,'curves.csv'),colClasses=c(issue='character'))
stopifnot(all(c('issue','slot','provider_id','handicap','actual_direction','spf_sp') %in% names(labels)),
 all(c('issue','policy','net','gross','stake','hits','stage') %in% names(periods)),
 all(c('issue','policy','sleeve_id','hit','gross','stake') %in% names(groups)),
 all(c('policy','period','equity_cny','drawdown_cny') %in% names(curves)),
 all(is.finite(labels$slot)),all(labels$slot==floor(labels$slot)),
 !anyDuplicated(labels[c('issue','slot')]),
 !anyDuplicated(labels[c('issue','provider_id')]),
 all(is.finite(labels$handicap)),all(labels$actual_direction %in% c('W','D','L')),
 all(is.finite(labels$spf_sp)),all(labels$spf_sp>0),
 !anyDuplicated(periods[c('issue','policy')]),
 all(abs(periods$net-(periods$gross-periods$stake))<1e-6))
parent_hashes<-vapply(c(params$main,params$structure),function(root)
 digest::digest(file=file.path(root,'plans-receipt.json'),algo='sha256'),character(1))
stopifnot(identical(unname(parent_hashes),c(params$main_sha256,params$structure_sha256)),
 identical(unname(parent_hashes),unlist(rp$parent_hashes,use.names=FALSE)))
main_receipt<-jsonlite::fromJSON(file.path(params$main,'plans-receipt.json'),simplifyVector=FALSE)
structure_receipt<-jsonlite::fromJSON(file.path(params$structure,'plans-receipt.json'),simplifyVector=FALSE)
stopifnot(identical(main_receipt$scope,structure_receipt$scope),
 identical(main_receipt$scope,rp$scope),
 identical(structure_receipt$parent_receipt_sha256,unname(parent_hashes[1])))
checked<-0L
for(root in c(params$main,params$structure)) {
 r<-jsonlite::fromJSON(file.path(root,'plans-receipt.json'),simplifyVector=FALSE)
 for(id in unlist(r$scope)) {
  b<-r$bindings[[id]];path<-file.path(root,b$file)
  stopifnot(digest::digest(file=path,algo='sha256')==b$sha256)
  plan<-readRDS(path)
  for(arm in names(plan$arms)) {
   total<-0;stake<-0;hits<-0
   for(o in plan$arms[[arm]]$options) {
    f<-plan$fixtures[o$fixtures];keys<-vapply(f,function(x)as.character(x$provider_id),character(1))
    slots<-vapply(f,function(x)as.numeric(x$slot),numeric(1))
    stopifnot(all(is.finite(slots)),all(slots==floor(slots)))
    l<-labels[labels$issue==id,];l<-l[match(keys,l$provider_id),]
    stopifnot(!anyNA(l$actual_direction),identical(l$provider_id,keys),
     identical(as.integer(l$slot),vapply(f,function(x)as.integer(x$slot),integer(1))),
     all(l$handicap==vapply(f,function(x)as.numeric(x$handicap),numeric(1))))
    actual<-paste0(match(l$actual_direction,c('W','D','L'))-1L,collapse='')
    code<-vapply(o$state_ids,function(x)paste0(((x-1L)%/%3^(6:0))%%3,collapse=''),character(1))
    hit<-actual %in% code;gross<-if(hit)1.3*prod(l$spf_sp)*o$stake/(2*length(code)) else 0
    row<-groups[groups$issue==id & groups$policy==arm & groups$sleeve_id==o$sleeve_id,]
    stopifnot(nrow(row)==1,row$hit==hit,abs(row$gross-gross)<1e-6,row$stake==o$stake)
    total<-total+gross;stake<-stake+o$stake;hits<-hits+hit;checked<-checked+1L
   }
   row<-periods[periods$issue==id & periods$policy==arm,]
   stopifnot(nrow(row)==1,abs(row$gross-total)<1e-6,row$stake==stake,row$hits==hits)
  }
 }
}
for(policy in unique(periods$policy)) {
 x<-periods[periods$policy==policy,];x<-x[match(unlist(r$scope),x$issue),]
 expected<-100000+c(0,cumsum(x$gross-x$stake));dd<-cummax(expected)-expected
 c<-curves[curves$policy==policy,];c<-c[order(c$period),]
 stopifnot(nrow(c)==length(expected),max(abs(expected-c$equity_cny))<1e-5,max(abs(dd-c$drawdown_cny))<1e-5)
}
summary<-read.csv(file.path(report,'summary.csv'))
stopifnot(all(c('policy','evaluation','issues','stake_cny','net_cny','hit_issues',
 'max_drawdown_cny','max_drawdown_percent','roi_percent') %in% names(summary)))
for(i in seq_len(nrow(summary))) {
 s<-summary[i,];x<-periods[periods$policy==s$policy,]
 if(s$evaluation!='ALL')x<-x[x$stage==s$evaluation,]
 x<-x[order(match(x$issue,unlist(r$scope))),]
 net<-x$gross-x$stake
 eq<-100000+c(0,cumsum(net));dd<-cummax(eq)-eq
 stopifnot(nrow(x)==s$issues,abs(sum(x$stake)-s$stake_cny)<1e-6,
  abs(sum(net)-s$net_cny)<1e-6,sum(x$gross>0)==s$hit_issues,
  abs(max(dd)-s$max_drawdown_cny)<1e-5,
  abs(max(dd/cummax(eq))*100-s$max_drawdown_percent)<1e-8)
 if(sum(x$stake)>0)stopifnot(abs(100*sum(net)/sum(x$stake)-s$roi_percent)<1e-8)
 else stopifnot(is.na(s$roi_percent))
}
jsonlite::write_json(list(status='PASS',checked_groups=checked,policies=length(unique(periods$policy)),
 scope='official physical-ticket payout, period stake/gross/hits and full chronological equity/drawdown',
 parent_receipt_sha256=unname(parent_hashes),
 report_receipt_sha256=digest::digest(file=file.path(report,'receipt.json'),algo='sha256')),
 output,auto_unbox=TRUE,pretty=TRUE)
