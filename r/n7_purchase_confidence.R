# Fixed probability-distinction limits, not fitted empirical confidence.
# Clear Top2 boundary permits high reuse; ambiguous p2/p3 permits only low reuse.
# For each direction, concentration allowance is high only if its probability
# exceeds every alternative by minimum_gap. Thus a high Top2 mass alone cannot
# grant high concentrated stake to the ambiguous second outcome.
# Requires exact validated pool/cutoffs; no fitting, labels or I/O.
n7_purchase_confidence_limits <- function(pool,cutoffs,unit_cny,minimum_gap,
                                          low_uses,high_uses,low_stake,high_stake) {
 stopifnot(length(minimum_gap)==1,is.finite(minimum_gap),minimum_gap>=0,minimum_gap<=1,
  length(low_uses)==1,length(high_uses)==1,length(low_stake)==1,length(high_stake)==1,
  low_uses<=high_uses,low_stake<=high_stake)
 limits<-n7_purchase_limits(pool,cutoffs,unit_cny,high_uses,high_stake)
 stopifnot(is.finite(low_uses),low_uses>=1,low_uses==floor(low_uses),
  is.finite(low_stake),low_stake>=0)
 n<-length(pool$fixtures)
 for(i in seq_len(n)) {
  f<-pool$fixtures[[i]];p<-unlist(f[c('p_W','p_D','p_L')],use.names=FALSE)
  stopifnot(length(p)==3,all(is.finite(p)),all(p>=0),abs(sum(p)-1)<1e-8)
  sorted<-sort(p,decreasing=TRUE)
  limits$upper[i]<-if(sorted[2]-sorted[3]>=minimum_gap)high_uses else low_uses
  for(k in 1:3)limits$upper[n+(i-1)*3+k]<-if(p[k]-max(p[-k])>=minimum_gap)high_stake else low_stake
 }
 limits$policy<-list(minimum_gap=minimum_gap,low_uses=low_uses,high_uses=high_uses,
  low_stake=low_stake,high_stake=high_stake)
 limits
}
