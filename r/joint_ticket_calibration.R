# Descriptive calibration of already purchased tickets, not a decision interface.
# x: one issue/policy/sleeve_id/ticket_col_idx row, probability in [0,1], hit
# boolean, gross/stake CNY, stage. Breaks explicit. Overlapping tickets are not
# independent; no binomial intervals or significance claims are returned.
joint_ticket_calibration <- function(x,breaks) {
 stopifnot(!anyDuplicated(x[c('issue','policy','sleeve_id','ticket_col_idx')]),
  all(is.finite(x$prob)),all(x$prob>=0 & x$prob<=1),
  all(x$hit %in% c(TRUE,FALSE)),!anyNA(x$hit),
  all(is.finite(x$gross)),all(x$gross>=0),all(x$stake>0),
  length(breaks)>=2,all(diff(breaks)>0),breaks[1]==0,tail(breaks,1)==1)
 x$band<-cut(x$prob,breaks,include.lowest=TRUE,right=FALSE)
 x$payout_band<-cut(x$payout_hat,c(0,128,256,512,1024,Inf),right=FALSE)
 z<-dplyr::bind_rows(x,dplyr::mutate(x,stage='ALL'))
 bins<-z |> dplyr::group_by(policy,stage,band) |>
  dplyr::summarise(tickets=dplyr::n(),issues=dplyr::n_distinct(issue),
   expected_hits=sum(prob),actual_hits=sum(hit),mean_probability=mean(prob),
   hit_rate=mean(hit),stake=sum(stake),gross=sum(gross),.groups='drop') |>
  dplyr::mutate(hit_ratio=actual_hits/expected_hits,net=gross-stake,roi=net/stake)
 types<-z |> dplyr::group_by(policy,stage,band,payout_band) |>
  dplyr::summarise(tickets=dplyr::n(),issues=dplyr::n_distinct(issue),
   expected_hits=sum(prob),actual_hits=sum(hit),stake=sum(stake),gross=sum(gross),.groups='drop') |>
  dplyr::mutate(hit_ratio=actual_hits/expected_hits,net=gross-stake,roi=net/stake)
 list(bins=bins,types=types)
}
