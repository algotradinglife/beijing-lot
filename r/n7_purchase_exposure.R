# Exact ticket stake exposure for a frozen, validated N7 option pool.
# Rows are option x fixture x W/D/L. Monetary columns are CNY, not predicted
# losses: incompatible_stake is money ruled out if this fixture outcome occurs.
# A ticket is counted at each of its seven fixtures; do not sum across fixtures.
# pool is produced by the capital boundary; cutoffs must match exactly.
# No fitting, settlement, I/O, or probability changes.
n7_purchase_exposure <- function(pool, cutoffs, unit_cny) {
  stopifnot(identical(pool$cutoffs, cutoffs), length(cutoffs)>0,
    length(unit_cny)==1, is.finite(unit_cny), unit_cny>0)
  rows<-lapply(seq_along(pool$options), function(j) {
    o<-pool$options[[j]];ids<-o$state_ids;f<-o$fixtures
    stopifnot(length(f)==7, !anyDuplicated(f), all(f %in% seq_along(pool$fixtures)),
      length(ids)>0, !anyDuplicated(ids), all(ids %in% 1:2187),
      length(o$stake)==1,is.finite(o$stake),o$stake>0)
    copies<-o$stake/(length(ids)*unit_cny)
    stopifnot(copies>=1, abs(copies-round(copies))<1e-10)
    dplyr::bind_rows(lapply(seq_len(7), function(k) {
      states<-((ids-1L) %/% 3^(7-k)) %% 3L
      counts<-tabulate(states+1L,nbins=3L)
      tibble::tibble(option=j,sleeve_id=o$sleeve_id,fixture=f[k],
        outcome=c('W','D','L'),required_stake=counts*unit_cny*copies,
        incompatible_stake=o$stake-counts*unit_cny*copies,
        fixture_stake=o$stake)
    }))
  })
  schema<-tibble::tibble(option=integer(),sleeve_id=double(),fixture=integer(),
    outcome=character(),required_stake=double(),incompatible_stake=double(),fixture_stake=double())
  dplyr::bind_rows(schema,rows)
}

# Fixed, prediction-only limits for n7_core_allocate. Each selected sleeve counts
# once towards fixture use, regardless of depth. Outcome stake includes copies.
# Inf explicitly disables a family. Matrix columns bind the exact pool identity.
n7_purchase_limits <- function(pool,cutoffs,unit_cny,max_fixture_uses,max_direction_stake) {
  stopifnot(length(max_fixture_uses)==1,!is.na(max_fixture_uses),max_fixture_uses>=1,
    max_fixture_uses==floor(max_fixture_uses),length(max_direction_stake)==1,
    !is.na(max_direction_stake),max_direction_stake>=0)
  x<-n7_purchase_exposure(pool,cutoffs,unit_cny)
  nf<-length(pool$fixtures);no<-length(pool$options)
  a<-matrix(0,nrow=4*nf,ncol=no)
  if(nrow(x)) {
    a[cbind(x$fixture,x$option)]<-1
    a[cbind(nf+(x$fixture-1L)*3L+match(x$outcome,c('W','D','L')),x$option)]<-x$required_stake
  }
  list(matrix=a,upper=c(rep(max_fixture_uses,nf),rep(max_direction_stake,3*nf)),
    cutoffs=cutoffs,pool_hash=digest::digest(pool,algo='sha256'))
}
