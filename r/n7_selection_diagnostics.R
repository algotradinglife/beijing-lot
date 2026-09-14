# Descriptive overlap of frozen purchases, never used to choose tickets.
# rows: unique issue/arm/seed plans with groups and eval_union; funded: one row
# per selected sleeve with coverage. membership: issue/sleeve_id/fixture_id,
# fixture IDs unique within an issue; exactly seven distinct fixtures per group.
# Returns one row per plan: bought groups, fixture count, maximum fixture reuse,
# pairwise maximum/mean shared fixtures and summed coverage minus model union.
# Probabilities unitless; overlap counts are matches. Empty purchases return zero.
# Missing/duplicate keys, mismatched group counts and memberships fail. No IO.
n7_selection_overlap <- function(rows,funded,membership) {
  keys<-c('issue','arm','seed')
  stopifnot(all(c(keys,'groups','eval_union') %in% names(rows)),
    all(c(keys,'sleeve_id','coverage') %in% names(funded)),
    all(c('issue','sleeve_id','fixture_id') %in% names(membership)),
    !anyNA(rows[c(keys,'groups','eval_union')]),!anyNA(funded),!anyNA(membership),
    !anyDuplicated(rows[keys]),!anyDuplicated(funded[c(keys,'sleeve_id')]),
    !anyDuplicated(membership[c('issue','sleeve_id','fixture_id')]),
    all(funded$coverage>=0 & funded$coverage<=1),all(rows$eval_union>=0 & rows$eval_union<=1),
    all(rows$groups>=0 & rows$groups==floor(rows$groups)))
  stopifnot(nrow(dplyr::anti_join(funded,rows,by=keys))==0)
  counts<-membership |> dplyr::count(issue,sleeve_id)
  stopifnot(all(counts$n==7))
  answer<-vector('list',nrow(rows))
  for(i in seq_len(nrow(rows))) {
    row<-rows[i,]
    f<-funded |> dplyr::semi_join(row,by=keys)
    stopifnot(nrow(f)==row$groups)
    m<-membership |> dplyr::semi_join(f,by=c('issue','sleeve_id'))
    stopifnot(nrow(m)==7*nrow(f))
    reuse<-table(m$fixture_id)
    pair<-numeric()
    if(nrow(f)>1) {
      incidence<-table(m$sleeve_id,m$fixture_id)
      overlaps<-tcrossprod(incidence)
      pair<-overlaps[upper.tri(overlaps)]
    }
    answer[[i]]<-tibble::tibble(issue=row$issue,arm=row$arm,seed=row$seed,
      bought_groups=nrow(f),unique_fixtures=length(reuse),
      max_fixture_reuse=if(length(reuse))max(reuse) else 0,
      max_pair_overlap=if(length(pair))max(pair) else 0,
      mean_pair_overlap=if(length(pair))mean(pair) else 0,
      summed_coverage=sum(f$coverage),eval_union=row$eval_union,
      coverage_minus_union=sum(f$coverage)-row$eval_union)
  }
  dplyr::bind_rows(answer)
}
