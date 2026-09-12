# Project a frozen draw-foundation prediction onto its original market score grid.
# grid: home_goals, away_goals, probability; prediction: one-row q/new WDL,
# cutoff_ts and version; handicap integer; cutoff explicit UTC string.
# Returns coherent grid and WDL. Pure, no fitting/I/O; mismatched inputs stop.
foundation_score_grid <- function(grid, handicap, prediction, cutoff) {
  stopifnot(nrow(prediction)==1L,identical(as.character(prediction$cutoff_ts),cutoff),
    identical(as.character(prediction$version),'market-strength-draw-1.0.0-diagnostic'))
  delta<-grid$home_goals-grid$away_goals+handicap
  observed<-c(sum(grid$probability[delta>0]),sum(grid$probability[delta==0]),sum(grid$probability[delta<0]))
  expected<-as.numeric(prediction[1,c('q_W','q_D','q_L')])
  stopifnot(all(is.finite(expected)),all(abs(observed-expected)<1e-8))
  result<-project_signal_rate_grid(grid,handicap,prediction$new_D,NA_real_,0,cutoff)
  stopifnot(all(abs(unname(result$probabilities[c('W','D','L')])-
    as.numeric(prediction[1,c('new_W','new_D','new_L')]))<1e-8))
  result
}
