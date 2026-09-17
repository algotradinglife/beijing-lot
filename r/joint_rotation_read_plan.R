# Read a frozen sparse rotation ledger with a fixed schema, including empty CSVs.
# Same-byte SHA verification and parse failures use the shared IO boundary.
# No decisions, labels, fitting or writes. Returns a typed tibble.
joint_rotation_read_plan <- function(path,sha256) {
 x<-diagnostic_read_verified_csv(path,sha256,readr::cols(.default=readr::col_character(),
  sleeve_id=readr::col_integer(),ticket_col_idx=readr::col_integer(),prob=readr::col_double(),
  payout_hat=readr::col_double(),base_copies=readr::col_integer(),copies=readr::col_integer()))
 stopifnot(all(c('issue','policy','ticket_id','sleeve_id','ticket_col_idx','prob','payout_hat','cell','base_copies','copies','state','action') %in% names(x)),
  !anyNA(x),!anyDuplicated(x[c('issue','policy','ticket_id')]),all(x$base_copies %in% 0:1),all(x$copies %in% 0:2))
 x
}
