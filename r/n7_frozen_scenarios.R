# Decode an explicit, already hash-verified #453 snapshot into shared R capital
# contracts. x uses jsonlite simplifyVector=FALSE. No IO/fitting; exact cutoff
# equality and matrix dimensions/values are checked. Empty option matrices retain
# their row count. Returns pool/train/evaluation; never opens settlement labels.
n7_frozen_scenarios <- function(x,cutoffs) {
  stopifnot(length(cutoffs)>0,identical(x$cutoffs,cutoffs))
  pool<-list(options=x$options,cutoffs=cutoffs,mode='BREADTH',
    opening_options=as.integer(unlist(x$opening_options)),
    opportunity_options=as.integer(unlist(x$opportunity_options)))
  for(j in seq_along(pool$options)) {
    pool$options[[j]]$fixtures<-as.integer(unlist(pool$options[[j]]$fixtures))
    pool$options[[j]]$state_ids<-as.integer(unlist(pool$options[[j]]$state_ids))
    pool$options[[j]]$state_payout<-as.numeric(unlist(pool$options[[j]]$state_payout))
  }
  out<-list(pool=pool)
  for(lane in c('train','evaluation')) {
    raw<-x[[lane]];stopifnot(identical(raw$cutoffs,cutoffs))
    sc<-list(cutoffs=cutoffs)
    for(field in c('hits','gross')) {
      stopifnot(length(raw[[field]])>0,
        all(lengths(raw[[field]])==length(pool$options)))
      sc[[field]]<-matrix(as.numeric(unlist(raw[[field]])),nrow=length(raw[[field]]),
        ncol=length(pool$options),byrow=TRUE)
    }
    n7_capital_evaluate(pool,integer(),sc,cutoffs,0)
    out[[lane]]<-sc
  }
  out
}
