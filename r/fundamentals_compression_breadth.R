# Post-settlement descriptive comparison; no model fitting, selection or I/O.
# One row per partition/issue/policy; baseline_policy exists exactly once for
# every issue in each partition. CNY amounts, probabilities in [0,1].
# Returns summaries and ordered capital paths. initial_capital_cny is explicit.
compression_breadth_summary <- function(results,baseline_policy,initial_capital_cny) {
 stopifnot(is.character(baseline_policy),length(baseline_policy)==1,
   is.numeric(initial_capital_cny),length(initial_capital_cny)==1,is.finite(initial_capital_cny),initial_capital_cny>0,
   nrow(results)>0,all(c('model_union','model_union_se','model_proxy_net','budget_cny','depth','rule','breadth','compression_seed','breadth_seed','unique_tickets','paid_ticket_units','repeat_units','miss_distance','fixture_hhi','outcome_hhi','max_pair_overlap','max_single_groups') %in% names(results)),
   !anyNA(results[c('model_union','budget_cny')]),all(results$model_union>=0 & results$model_union<=1),
   all(results$stake==results$budget_cny))
 totals <- integration_weight_summary(results)
 base <- results |> dplyr::filter(policy==baseline_policy) |>
   dplyr::select(partition,issue,base_stake=stake,base_net=net,base_union=model_union)
 x <- dplyr::left_join(results,base,by=c('partition','issue'),relationship='many-to-one')
 stopifnot(!anyNA(x$base_stake),all(x$stake==x$base_stake))
 x <- x |> dplyr::arrange(partition,policy,issue) |> dplyr::mutate(lift=net-base_net,union_lift=model_union-base_union)
 paths <- x |> dplyr::group_by(partition,policy) |>
   dplyr::mutate(capital_cny=initial_capital_cny+cumsum(net),peak_cny=cummax(pmax(initial_capital_cny,capital_cny)),drawdown_cny=peak_cny-capital_cny) |>
   dplyr::ungroup()
 groups <- split(paths,interaction(paths$partition,paths$policy,drop=TRUE));risk <- vector('list',length(groups));index <- 0L
 for(g in groups) {
   index <- index+1L;largest <- which.max(g$net);largest_lift <- which.max(g$lift);lossrun <- drawrun <- maxloss <- maxdrawrun <- 0L
   for(i in seq_len(nrow(g))) {
     lossrun <- if(g$net[i]<0) lossrun+1L else 0L;maxloss <- max(maxloss,lossrun)
     drawrun <- if(g$drawdown_cny[i]>0) drawrun+1L else 0L;maxdrawrun <- max(maxdrawrun,drawrun)
   }
   windows <- rep(NA_real_,3);names(windows) <- c('5','10','20')
   for(k in c(5L,10L,20L)) if(nrow(g)>=k) {
     cs <- c(0,cumsum(g$net));roll <- cs[(k+1L):length(cs)]-cs[seq_len(length(cs)-k)]
     windows[as.character(k)] <- max(0,-min(roll))
   }
   years <- substr(g$issue,1,2);year_net <- tapply(g$net,years,sum);largest_year <- names(year_net)[which.max(year_net)];year_keep <- years!=largest_year
   keep <- seq_len(nrow(g))!=largest;remaining <- sum(g$budget_cny[keep]);gross <- sum(g$gross)
   risk[[index]] <- tibble::tibble(partition=g$partition[1],policy=g$policy[1],depth=g$depth[1],rule=g$rule[1],breadth=g$breadth[1],compression_seed=g$compression_seed[1],breadth_seed=g$breadth_seed[1],
     model_proxy_net=sum(g$model_proxy_net),model_union=mean(g$model_union),union_lift=mean(g$union_lift),matched_lift=sum(g$lift),payout_issue_rate=mean(g$hits>0),profitable_issue_rate=mean(g$net>0),
     ex_largest_issue=g$issue[largest],ex_largest_net=sum(g$net[keep]),ex_largest_roi=if(remaining>0) sum(g$net[keep])/remaining else NA_real_,
     ex_largest_matched_lift=sum(g$lift[keep]),ex_largest_lift_issue=g$issue[largest_lift],ex_largest_lift=sum(g$lift[-largest_lift]),
     longest_losing_run=maxloss,max_drawdown_duration=maxdrawrun,unrecovered_at_end=tail(g$drawdown_cny,1)>0,
     worst_5_loss=windows['5'],worst_10_loss=windows['10'],worst_20_loss=windows['20'],
     payout_hhi=if(gross>0) sum((g$gross/gross)^2) else NA_real_,largest_payout_share=if(gross>0) max(g$gross)/gross else NA_real_,
     unique_tickets=sum(g$unique_tickets),paid_ticket_units=sum(g$paid_ticket_units),repeat_units=sum(g$repeat_units),
     mean_miss_distance=mean(g$miss_distance),mean_fixture_hhi=mean(g$fixture_hhi),mean_outcome_hhi=mean(g$outcome_hhi),max_pair_overlap=max(g$max_pair_overlap),max_single_groups=max(g$max_single_groups),
     ex_largest_year=paste0('20',largest_year),ex_largest_year_issues=sum(year_keep),ex_largest_year_net=if(any(year_keep)) sum(g$net[year_keep]) else NA_real_,
     ending_capital=tail(g$capital_cny,1),issue_years=dplyr::n_distinct(substr(g$issue,1,2)))
 }
 summary <- dplyr::left_join(totals,dplyr::bind_rows(risk),by=c('partition','policy'),relationship='one-to-one')
 list(summary=summary,paths=paths)
}

# Descriptive compression-leg strata. Repeated fixture holdings are dependent
# observations; report issue count explicitly and do not perform inference.
# breaks is a named list of fixed, strictly increasing numeric bin boundaries.
# Include -Inf/Inf for full coverage. Empty input returns a typed empty tibble.
compression_leg_strata <- function(legs,breaks) {
 required <- c('issue','slot','partition','policy','single','covered','retention','p2','gap','entropy','divergence','handicap','top1_direction')
 stopifnot(all(required %in% names(legs)),is.list(breaks),length(breaks)>0,
   all(names(breaks) %in% names(legs)),!anyNA(legs[required]))
 out <- list();index <- 0L;x <- legs |> dplyr::filter(single)
 for(variable in names(breaks)) {
   b <- breaks[[variable]];stopifnot(is.numeric(b),length(b)>=2,all(diff(b)>0))
   bin <- cut(x[[variable]],breaks=b,include.lowest=TRUE,right=FALSE);stopifnot(!anyNA(bin))
   index <- index+1L
   out[[index]] <- x |> dplyr::mutate(variable=variable,bin=as.character(bin)) |>
     dplyr::group_by(partition,policy,variable,bin) |>
     dplyr::summarise(holdings=dplyr::n(),issues=dplyr::n_distinct(issue),hit_rate=mean(covered),mean_retention=mean(retention),mean_discarded_mass=mean(p2),.groups='drop')
 }
 index <- index+1L
 out[[index]] <- x |> dplyr::mutate(variable='direction',bin=top1_direction) |>
   dplyr::group_by(partition,policy,variable,bin) |>
   dplyr::summarise(holdings=dplyr::n(),issues=dplyr::n_distinct(issue),hit_rate=mean(covered),mean_retention=mean(retention),mean_discarded_mass=mean(p2),.groups='drop')
 dplyr::bind_rows(out)
}
