# Pure diagnostic drawdown duration from chronological period net returns.
# Time0 is a high-water mark; equality recovers it. Return maximum consecutive
# period-end observations strictly below a prior peak; unresolved runs count.
# Missing/nonfinite returns fail. Empty returns produce0.
n7_underwater_periods <- function(net) {
  if(any(!is.finite(net))) stop('Finite period returns required')
  equity <- c(0,cumsum(net))
  run <- rle((equity < cummax(equity))[-1])
  max(c(0L,run$lengths[run$values]))
}

# Reuse shared3-arm report and receipts; append underwater duration and the
# top group's stand-alone unit cash, computed by TOP2 minus BASE. Output tibbles
# use only common settled issues. No fit, model selection or writes.
n7_topstake_report <- function(study,project_root) {
  receipt <- jsonlite::read_json(file.path(study,'inputs.json'))
  for(f in c('r/fundamentals_n7_topstake.R','scripts/settle_fundamentals_n7_topstake.R')) stopifnot(identical(receipt$source_hashes[[f]],digest::digest(file=file.path(project_root,f),algo='sha256')))
  y <- n7_twocover_report(study,project_root)
  x <- y$per_issue |> dplyr::filter(issue %in% y$common_issues$issue[y$common_issues$ready])
  x <- dplyr::bind_rows(x,dplyr::mutate(x,partition='ALL')) |>
    dplyr::arrange(issue_anchor_ts,issue)
  water <- x |> dplyr::group_by(partition,strategy,funding) |>
    dplyr::summarise(longest_underwater_periods=n7_underwater_periods(net),.groups='drop')
  y$summary <- dplyr::left_join(y$summary,water,by=c('partition','strategy','funding'),relationship='one-to-one')
  base <- y$per_issue |> dplyr::filter(strategy=='BASE') |> dplyr::select(issue,status,top_group,top_probability,
    base_stake=stake,base_gross=gross,base_net=net,partition)
  top <- y$per_issue |> dplyr::filter(strategy=='TOP2') |> dplyr::select(issue,boost_status=status,boost_stake=stake,boost_gross=gross,boost_net=net)
  y$top_per_issue <- dplyr::left_join(base,top,by='issue',relationship='one-to-one') |>
    dplyr::mutate(status=ifelse(status %in% c('COMPLETE','NO_BET') & boost_status %in% c('COMPLETE','NO_BET'),status,'PENDING_AUDIT_OR_WINNING_SP'),stake=boost_stake-base_stake,gross=boost_gross-base_gross,net=boost_net-base_net,
      hit=ifelse(is.na(gross),NA_integer_,as.integer(gross>0)),roi=ifelse(stake>0,net/stake,NA_real_))
  z <- y$top_per_issue |> dplyr::filter(issue %in% y$common_issues$issue[y$common_issues$ready],stake>0)
  z <- dplyr::bind_rows(z,dplyr::mutate(z,partition='ALL'))
  y$top_summary <- z |> dplyr::group_by(partition) |> dplyr::summarise(issues=dplyr::n(),hits=sum(hit),
    hit_rate=mean(hit),mean_model_probability=mean(top_probability),stake=sum(stake),gross=sum(gross),
    net=sum(net),roi=net/stake,.groups='drop')
  y
}
