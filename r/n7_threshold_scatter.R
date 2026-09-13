# Descriptive threshold-vs-realized rank table. Inputs are verified #425 rank
# rows, targets are fractions and unit is CNY2. No selection, fitting or writes.
# One row is one issue/sleeve/target; ticket counts include the winning prefix.
n7_threshold_points <- function(rows,targets,unit_cny) {
  stopifnot(unit_cny==2,length(targets)>0,!anyDuplicated(targets),
    all(is.finite(targets)),all(targets>0 & targets<=1),
    all(abs(targets*100-round(targets*100))<1e-8),
    !anyDuplicated(rows[c('issue','sleeve_id')]),
    all(is.finite(rows$actual_rank)),all(rows$actual_rank>=1 & rows$actual_rank<=2187),
    all(rows$actual_rank==floor(rows$actual_rank)))
  columns<-paste0('coverage_',round(targets*100),'_cost_cny')
  stopifnot(all(columns %in% names(rows)),all(is.finite(as.matrix(rows[columns]))),
    all(as.matrix(rows[columns])>0 & as.matrix(rows[columns])<=unit_cny*2187),
    all(as.matrix(rows[columns])%%unit_cny==0))
  ordered<-as.matrix(rows[columns[order(targets)]])
  if(ncol(ordered)>1)stopifnot(all(ordered[,-1,drop=FALSE]>=ordered[,-ncol(ordered),drop=FALSE]))
  dplyr::bind_rows(lapply(seq_along(targets),function(j) {
    tibble::tibble(issue=as.character(rows$issue),sleeve_id=as.character(rows$sleeve_id),
      origin=rows$origin,target=targets[j],theory_tickets=rows[[columns[j]]]/unit_cny,
      actual_tickets=rows$actual_rank) |>
      dplyr::mutate(covered=actual_tickets<=theory_tickets,
        actual_to_theory=actual_tickets/theory_tickets)
  }))
}

# Fixed descriptive cost bins, not learned routing boundaries. Fractions remain
# fractions. Counts are overlapping candidate groups, not independent trials.
n7_threshold_bins <- function(points,breaks,small_ticket_cap) {
  stopifnot(length(breaks)>1,all(diff(breaks)>0),small_ticket_cap>=1,
    !anyDuplicated(points[c('issue','sleeve_id','target')]),
    all(points$theory_tickets>min(breaks) & points$theory_tickets<=max(breaks)))
  points |> dplyr::mutate(theory_bin=cut(theory_tickets,breaks,include.lowest=TRUE,right=TRUE)) |>
    dplyr::group_by(target,theory_bin) |> dplyr::summarise(
      sleeves=dplyr::n(),issues=dplyr::n_distinct(issue),
      covered_rate=mean(actual_tickets<=theory_tickets),
      small_ticket_hit_rate=mean(actual_tickets<=small_ticket_cap),
      theory_median=median(theory_tickets),actual_median=median(actual_tickets),
      .groups='drop')
}
