# Fixed-grid, post-settlement descriptive summaries. No learning or routing.
# points: exact frozen coverage prefixes joined to outcomes; CNY money units.
# issue_order: complete explicit chronology, block_size: fixed diagnostic span.
# Returns grid, chronological blocks and whole-issue extreme-removal tables.
n7_sweet_diagnostics <- function(points,caps_cny,issue_order,block_size) {
  stopifnot(nrow(points)>0,!anyDuplicated(points[c('issue','sleeve_id','target')]),
    !anyDuplicated(issue_order),setequal(points$issue,issue_order),
    length(caps_cny)>0,all(is.finite(caps_cny)),all(caps_cny>0),!anyDuplicated(caps_cny),
    block_size>=1,block_size==floor(block_size),!anyNA(points))
  rows <- dplyr::bind_rows(lapply(caps_cny,function(cap)
    points |> dplyr::filter(stake<=cap) |>
      dplyr::mutate(cap_cny=cap,target_pct=round(100*target,6))))
  described <- n7_coverage_summary(rows)
  issues <- described$issues
  blocks <- rows |> dplyr::mutate(block=(match(issue,issue_order)-1L)%/%block_size+1L) |>
    dplyr::group_by(target_pct,cap_cny,block) |> dplyr::summarise(
      groups=dplyr::n(),issues=dplyr::n_distinct(issue),stake=sum(stake),net=sum(net),
      hit_rate=mean(hit),coverage=mean(coverage),roi=net/stake,.groups='drop')
  ordered <- issues |> dplyr::group_by(cohort,target_pct,cap_cny) |>
    dplyr::arrange(dplyr::desc(net),issue,.by_group=TRUE) |>
    dplyr::mutate(rank=dplyr::row_number()) |> dplyr::ungroup()
  trimmed <- dplyr::bind_rows(lapply(c(0,1,3,5),function(drop)
    ordered |> dplyr::filter(rank>drop) |>
      dplyr::group_by(cohort,target_pct,cap_cny) |> dplyr::summarise(
        drop_issues=drop,issues=dplyr::n(),stake=sum(stake),net=sum(net),roi=net/stake,.groups='drop')))
  list(grid=described$summary,issues=issues,blocks=blocks,trimmed=trimmed,rows=rows)
}

# Descriptive overlap of selected sleeve IDs, keyed to frozen issue metadata.
# Missing fixture sets fail. No effective-independent-sample-size claim is made.
# Returns count of distinct fixtures, mean pairwise shared fixtures (NA <2 groups),
# and largest fraction of groups that contain one fixture (0 for no groups).
n7_sweet_overlap <- function(ids,fixture_sets) {
  stopifnot(!anyDuplicated(ids),all(ids %in% names(fixture_sets)))
  sets <- fixture_sets[ids]
  stopifnot(all(lengths(sets)==7),all(vapply(sets,anyDuplicated,integer(1))==0))
  all <- unlist(sets)
  shared <- numeric()
  if(length(sets)>1)for(i in seq_len(length(sets)-1))for(j in (i+1):length(sets))
    shared <- c(shared,length(intersect(sets[[i]],sets[[j]])))
  tibble::tibble(groups=length(ids),fixtures=length(unique(all)),
    mean_pair_overlap=if(length(shared))mean(shared) else NA_real_,
    max_fixture_group_share=if(length(ids))max(table(all))/length(ids) else 0)
}
