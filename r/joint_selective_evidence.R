# Bind verified membership to the exact input bundle that generated original
# tickets. source is issue/sha256 from the hashed original freeze; job is the
# membership manifest entry; projection is read from those verified bytes.
# Returns a tidy member table. Identity mismatch fails, including empty issues.
joint_selective_members <- function(source,job,projection) {
 stopifnot(identical(source$issue,job$issue),identical(source$sha256,job$sha256),
  identical(projection$issue,source$issue),is.character(source$sha256),nchar(source$sha256)==64)
 members<-dplyr::bind_rows(lapply(projection$sleeves,function(g)tibble::tibble(sleeve_id=g$id,fixture=as.character(unlist(g$fixture_indices)))))
 stopifnot(!anyNA(members),!anyDuplicated(members))
 members
}

# Descriptive incremental sensitivity; no decisions, fitting or I/O.
# x: one row per issue/policy, finite extra_stake >=0 and extra_net in CNY.
# Reports actual marginal ROI (NA with zero spend), period sign counts and
# removing positive top 1/3 incremental net contributions, retaining other rows.
joint_selective_concentration <- function(x) {
 stopifnot(all(c('issue','policy','extra_stake','extra_net') %in% names(x)),!anyNA(x),
  !anyDuplicated(x[c('issue','policy')]),all(is.finite(x$extra_stake)),all(x$extra_stake>=0),all(is.finite(x$extra_net)))
 x |> dplyr::group_by(policy) |> dplyr::arrange(dplyr::desc(extra_net),.by_group=TRUE) |>
  dplyr::summarise(total_extra_stake=sum(extra_stake),total_extra_net=sum(extra_net),
   without_top1=sum(extra_net)-sum(head(pmax(extra_net,0),1)),
   without_top3=sum(extra_net)-sum(head(pmax(extra_net,0),3)),
   positive_issues=sum(extra_net>1e-7),negative_issues=sum(extra_net< -1e-7),.groups='drop') |>
  dplyr::mutate(marginal_roi=dplyr::if_else(total_extra_stake>0,total_extra_net/total_extra_stake,NA_real_))
}
