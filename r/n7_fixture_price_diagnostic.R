# Descriptive realized-direction price comparison. fixtures/audit are tibbles,
# keyed by issue/slot/provider_id; probabilities fractions, SP dimensionless.
# Returns each frozen fixture once with estimate1/q and settlement/estimate ratio.
# Labels never enter selection. Missing, duplicate, identity or handicap conflict
# fails. No IO; missing provenance hash is invalid, not silently accepted.
n7_fixture_price_diagnostic <- function(fixtures,audit) {
  keys<-c('issue','slot','provider_id')
  stopifnot(all(c(keys,'handicap','p_W','p_D','p_L','q_W','q_D','q_L') %in% names(fixtures)),
    all(c(keys,'handicap','actual_direction','spf_sp','spf_source_sha256','status') %in% names(audit)),
    !anyDuplicated(fixtures[keys]),!anyDuplicated(audit[keys]))
  z<-dplyr::left_join(fixtures,audit,by=keys,suffix=c('','_audit'),relationship='one-to-one')
  stopifnot(!anyNA(z[c(keys,'handicap','handicap_audit','actual_direction','spf_sp','spf_source_sha256','status')]),
    all(z$handicap==z$handicap_audit),all(z$actual_direction %in% c('W','D','L')),
    all(is.finite(z$spf_sp) & z$spf_sp>0),all(nzchar(z$spf_source_sha256)),!any(grepl('spf:IDENTITY',z$status)))
  p<-as.matrix(z[c('p_W','p_D','p_L')]);q<-as.matrix(z[c('q_W','q_D','q_L')])
  stopifnot(all(is.finite(p)),all(p>=0),all(abs(rowSums(p)-1)<1e-8),
    all(is.finite(q)),all(q>0),all(abs(rowSums(q)-1)<1e-8))
  idx<-cbind(seq_len(nrow(z)),match(z$actual_direction,c('W','D','L')))
  z$actual_p<-p[idx];z$actual_q<-q[idx]
  z$estimated_sp<-1/z$actual_q;z$price_ratio<-z$spf_sp/z$estimated_sp
  z
}
