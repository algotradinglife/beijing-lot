# Validate descriptive replay evidence before using equivalence claims.
# checks: one row per exact character issue; fields name required logical
# (nonmissing TRUE) verdict columns. Explicit issue set, including no-bet
# issues, prevents partial denominators. No I/O, fitting or selection.
n7_replay_checks <- function(checks, expected_issues, fields) {
 stopifnot(is.data.frame(checks),is.character(expected_issues),length(expected_issues)>0,
  !anyNA(expected_issues),all(nzchar(expected_issues)),!anyDuplicated(expected_issues),
  is.character(fields),length(fields)>0,!anyNA(fields),!anyDuplicated(fields),
  all(c('issue',fields) %in% names(checks)),is.character(checks$issue),
  !anyNA(checks$issue),!anyDuplicated(checks$issue),setequal(checks$issue,expected_issues))
 for(field in fields)stopifnot(is.logical(checks[[field]]),!anyNA(checks[[field]]),all(checks[[field]]))
 invisible(TRUE)
}
