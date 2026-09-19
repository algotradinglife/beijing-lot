# Filter frozen JOINT options by the number of strong line-gap fixtures.
# evidence is prediction-only issue/slot/provider_id/degree/signal, one row per
# pool fixture. Explicit cutoff identity must match both pool and scenarios.
# No probabilities, option states, payout, fixtures, worlds or labels change.
# Empty admissible pools retain cash via the native allocator. No learning/I/O.
line_gap_pool <- function(pool,scenarios,evidence,cutoffs,minimum_degree,minimum_count) {
 stopifnot(identical(pool$cutoffs,cutoffs),identical(scenarios$cutoffs,cutoffs),
  setequal(names(evidence),c('issue','slot','provider_id','degree','signal')),
  !anyNA(evidence),!anyDuplicated(evidence[c('issue','slot','provider_id')]),
  all(evidence$signal %in% c('W','L','NONE','AMBIGUOUS')),all(is.finite(evidence$degree)),all(evidence$degree>=0),
  length(minimum_degree)==1,is.finite(minimum_degree),minimum_degree>=0,
  length(minimum_count)==1,minimum_count %in% 0:7,
  is.matrix(scenarios$hits),identical(dim(scenarios$hits),dim(scenarios$gross)),ncol(scenarios$hits)==length(pool$options))
 f<-dplyr::bind_rows(pool$fixtures);keys<-c('issue','slot','provider_id')
 stopifnot(nrow(evidence)==nrow(f),!anyDuplicated(f[keys]))
 j<-match(paste(f$issue,f$slot,f$provider_id),paste(evidence$issue,evidence$slot,evidence$provider_id));stopifnot(!anyNA(j))
 strong<-evidence$degree[j]>=minimum_degree & evidence$signal[j] %in% c('W','L')
 count<-vapply(pool$options,function(o){stopifnot(all(o$fixtures %in% seq_len(nrow(f))),!anyDuplicated(o$fixtures));sum(strong[o$fixtures])},integer(1))
 keep<-which(count>=minimum_count);p<-pool;p$options<-pool$options[keep]
 p$opening_options<-match(intersect(pool$opening_options,keep),keep)
 p$opportunity_options<-match(intersect(pool$opportunity_options,keep),keep)
 s<-scenarios;s$hits<-scenarios$hits[,keep,drop=FALSE];s$gross<-scenarios$gross[,keep,drop=FALSE]
 list(pool=p,scenarios=s,audit=tibble::tibble(option=seq_along(pool$options),strong_count=count,admitted=count>=minimum_count),strong_fixtures=sum(strong))
}
