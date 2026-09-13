# Descriptive post-settlement diagnostics; no learning or selection.
# curves: frozen complete probability prefixes; ranks: n7_rank_diagnostic output.
# depths: distinct integer ticket counts 1..2187; unit_cny must be 2.
# Returns one row per candidate/depth. Frozen expected_gross and actual_gross_cny
# already include the single ticket-level 0.65 factor: do not multiply again.
# Missing/duplicate keys or invalid amounts fail; no IO or side effects.
n7_rank_return_prefixes <- function(curves, ranks, depths, unit_cny) {
  stopifnot(unit_cny == 2, nrow(ranks)>0, length(depths)>0,
    all(is.finite(depths)), all(depths==floor(depths)),
    all(depths>=1 & depths<=2187), !anyDuplicated(depths),
    !anyDuplicated(ranks[c('issue','sleeve_id')]),
    dplyr::n_distinct(ranks$issue)==1,
    all(is.finite(ranks$actual_gross_cny)), all(ranks$actual_gross_cny>=0),
    all(ranks$actual_rank %in% 1:2187))
  curves$sleeve_id <- as.character(curves$sleeve_id)
  ranks$sleeve_id <- as.character(ranks$sleeve_id)
  stopifnot(!anyDuplicated(curves[c('sleeve_id','depth')]))
  z <- curves |> dplyr::filter(depth %in% depths) |>
    dplyr::select(sleeve_id,depth,stake,coverage,expected_gross) |>
    dplyr::left_join(ranks |> dplyr::select(issue,sleeve_id,actual_rank,actual_gross_cny),
      by='sleeve_id',relationship='many-to-one')
  stopifnot(nrow(z)==nrow(ranks)*length(depths), !anyNA(z),
    setequal(z$sleeve_id,ranks$sleeve_id),
    all(z$stake==unit_cny*z$depth), all(is.finite(z$expected_gross)),
    all(z$expected_gross>=0), all(z$coverage>=0 & z$coverage<=1+1e-8))
  z |> dplyr::mutate(hit=actual_rank<=depth,
    realized_gross=ifelse(hit,actual_gross_cny,0),
    expected_net=expected_gross-stake, realized_net=realized_gross-stake)
}

# Equal-candidate fixed-depth diagnostics, not a 1024-CNY portfolio simulation.
# Input has cohort, issue, sleeve_id, depth, stake, coverage and both gross fields.
# Returns pooled capital-weighted ROI and group hit fraction per cohort/depth.
# Overlapping candidates are not independent observations; no CIs are inferred.
n7_rank_return_summary <- function(prefixes) {
  stopifnot(nrow(prefixes)>0,
    !anyDuplicated(prefixes[c('cohort','issue','sleeve_id','depth')]),
    !anyNA(prefixes),all(prefixes$stake>0))
  prefixes |> dplyr::group_by(cohort,depth) |> dplyr::summarise(
    groups=dplyr::n(),issues=dplyr::n_distinct(issue),
    expected_hit=mean(coverage),actual_hit=mean(hit),stake=sum(stake),
    expected_gross=sum(expected_gross),actual_gross=sum(realized_gross),
    expected_roi=expected_gross/stake-1,actual_roi=actual_gross/stake-1,
    .groups='drop')
}
