# Descriptive accounting only; never fits, selects or routes a strategy.
# rows: one issue/cell row with net (CNY); cells OO, ON, NO, NN encode
# probability calendar first, allocation calendar second (O=old, N=new).
# Returns per-issue net change and order-averaged probability/allocation effects.
# Explicit issue IDs; rejects missing/nonfinite/duplicate cells. No I/O.
n7_freeze_attribution <- function(rows, issues) {
 stopifnot(all(c('issue','cell','net') %in% names(rows)),is.character(issues),length(issues)>0,
  !anyNA(issues),!anyDuplicated(issues),!anyNA(rows[c('issue','cell','net')]),
  is.numeric(rows$net),all(is.finite(rows$net)),!anyDuplicated(rows[c('issue','cell')]),
  setequal(rows$issue,issues),setequal(rows$cell,c('OO','ON','NO','NN')),nrow(rows)==4*length(issues))
 wide<-tidyr::pivot_wider(rows[c('issue','cell','net')],names_from='cell',values_from='net')
 stopifnot(!anyNA(wide))
 wide<-wide[match(issues,wide$issue),]
 wide$probability_effect_cny<-((wide$NO-wide$OO)+(wide$NN-wide$ON))/2
 wide$allocation_effect_cny<-((wide$ON-wide$OO)+(wide$NN-wide$NO))/2
 wide$net_change_cny<-wide$NN-wide$OO
 stopifnot(max(abs(wide$probability_effect_cny+wide$allocation_effect_cny-wide$net_change_cny))<1e-6)
 wide
}
