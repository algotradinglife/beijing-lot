# Validate a manually declared fixed diagnostic scope before sorting. No fitting,
# selection by outcomes, I/O or chronology inference. cfg is parsed JSON; digest
# is the actual catalog SHA-256. Return distinct sorted character issue IDs.
# Missing/null/malformed scope, digest or experiment constants fail closed.
n7_purchase_scope <- function(cfg,catalog_sha256) {
 stopifnot(is.list(cfg),all(c('issues','excluded_drawdown_issues','catalog_sha256') %in% names(cfg)))
 for(value in list(cfg$catalog_sha256,catalog_sha256))stopifnot(
  is.character(value),length(value)==1,!is.na(value),grepl('^[0-9a-f]{64}$',value))
 stopifnot(identical(cfg$catalog_sha256,catalog_sha256),
  is.character(cfg$issues),length(cfg$issues)>0,
  length(cfg$excluded_drawdown_issues)==0 || is.character(cfg$excluded_drawdown_issues))
 ids<-c(cfg$issues,as.character(cfg$excluded_drawdown_issues))
 stopifnot(!anyNA(ids),all(grepl('^[0-9]+$',ids)),!anyDuplicated(ids))
 expected<-list(target_coverage=.25,group_cap_cny=256,minimum_sp=1.3,
  budget_cny=1024,unit_cny=2,payout_factor=.65,seed=42501,worlds=256)
 for(name in names(expected)) {
  value<-cfg[[name]]
  stopifnot(is.numeric(value),length(value)==1,!is.na(value),is.finite(value),value==expected[[name]])
 }
 sort(ids)
}
