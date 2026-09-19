source('scripts/check_worst_line_groups.R')
stopifnot(nrow(x)==23*11,!anyDuplicated(x[c('issue','policy')]),all(abs(x$net-x$gross+x$stake)<1e-7))
parent<-jsonlite::fromJSON(cfg$regroup$path);old<-read.csv(file.path(dirname(cfg$regroup$path),'periods.csv'),colClasses=c(issue='character'))
z<-x[x$policy %in% unique(old$policy),names(old)]
stopifnot(isTRUE(all.equal(z[order(z$issue,z$policy),],old[order(old$issue,old$policy),],check.attributes=FALSE)))
count<-0L
for(id in names(freeze$bindings)){
 ref<-freeze$bindings[[id]];stopifnot(digest::digest(file=ref$context,algo='sha256')==ref$context_sha256,digest::digest(file=ref$parent_context,algo='sha256')==ref$parent_context_sha256)
 contexts<-readRDS(ref$context);prior<-readRDS(ref$parent_context)
 for(kind in c('OLD','EXP')){
  b<-if(kind=='OLD')prior$original else prior$expanded;a<-contexts[[paste0(kind,'_OPEN_DROP')]]
  f<-a$plan$fixtures;p<-as.matrix(f[c('p_W','p_D','p_L')]);q<-as.matrix(f[c('q_W','q_D','q_L')]);rank<-apply(p,1,function(v)order(-v,1:3));third<-rank[3,]
  qualified<-1/q[cbind(seq_len(nrow(q)),rank[1,])]>=cfg$settings$minimum_sp
  expected_ids<-vapply(b$sleeves,function(g)if(all(qualified[as.integer(unlist(g$fixture_indices))+1L]))g$id else NA_real_,numeric(1));expected_ids<-expected_ids[!is.na(expected_ids)]
  stopifnot(setequal(vapply(a$pool$options,function(o)o$sleeve_id,numeric(1)),expected_ids))
  for(o in a$pool$options){
   g<-b$sleeves[[which(vapply(b$sleeves,function(g)g$id,numeric(1))==o$sleeve_id)]];e<-g$enumeration
   pp<-as.numeric(unlist(e$probability));vv<-as.numeric(unlist(e$expected_contribution));order0<-order(-pp,-vv,1:2187)
   desired<-which(cumsum(pp[order0])>=cfg$settings$target_coverage)[1];depth<-min(desired,cfg$settings$group_cap_cny/2)
   states<-matrix(as.integer(unlist(e$states)),2187,byrow=TRUE)+1L;mask<-rep(TRUE,2187)
   for(k in 1:7)mask<-mask & states[,k]!=third[o$fixtures[k]]
   allowed<-which(mask);ids<-head(allowed[order(-pp[allowed],allowed)],depth)
   stopifnot(o$depth==depth,o$stake==2*depth,identical(as.integer(o$state_ids),as.integer(ids)),abs(o$coverage-sum(pp[ids]))<1e-10)
   old_opts<-prior$pools[[kind]]$options;oi<-which(vapply(old_opts,function(v)v$sleeve_id==o$sleeve_id,logical(1)))
   if(length(oi))stopifnot(identical(old_opts[[oi]]$state_ids,o$state_ids),old_opts[[oi]]$stake==o$stake)
   count<-count+1L
  }
 }
}
cat('PASS:',count,'open-admission group options; existing admitted supports/costs unchanged; all parent period rows preserved\n')
reticulate::use_python(cfg$python,required=TRUE)
prov<-reticulate::import('src.temporal_learning.provenance')
closure<-prov$implementation_closure(reticulate::import('pathlib')$Path(cfg$repository_root),list('src.strategy_diagnostic_inputs','src.n7_sleeve_states','src.temporal_learning'),distributions=list('numpy','pandas'))
stopifnot(identical(closure$closure_sha256,freeze$closure$closure_sha256),identical(closure$closure_sha256,parent$closure$closure_sha256))
cat('PASS: current and parent transitive Python closures match the run\n')
