# Retrospective accounting, not selection/learning. rows: unique issue/policy,
# period integer chronology, stake/gross/net/hits; CNY money. initial is CNY.
# Returns chronological equity/drawdown and cohort summaries; zero-stake ROI NA.
# Missing, duplicate, inconsistent accounts fail. No I/O or state mutation.
joint_extension_diagnostics <- function(rows, old_periods, initial) {
 stopifnot(nrow(rows)>0,!anyDuplicated(rows[c('issue','policy')]),
  !anyNA(rows[c('issue','policy','period','stake','gross','net','hits')]),
  all(is.finite(as.matrix(rows[c('period','stake','gross','net','hits')]))),
  all(rows$stake>=0),all(rows$gross>=0),all(rows$hits>=0),
  all(abs(rows$net-rows$gross+rows$stake)<1e-7),old_periods>=1,initial>0)
 curves<-list();summary<-list()
 for(policy in unique(rows$policy)) {
  z<-rows[rows$policy==policy,];z<-z[order(z$period),]
  stopifnot(identical(as.integer(z$period),seq_len(nrow(z))))
  z$bankroll<-initial+cumsum(z$net);z$peak<-cummax(c(initial,z$bankroll))[-1]
  z$drawdown<-z$peak-z$bankroll;z$drawdown_pct<-z$drawdown/z$peak
  z$cohort<-ifelse(z$period<=old_periods,'OLD784','NEW50');curves[[policy]]<-z
  for(cohort in c('OLD784','NEW50','ALL834')) {
   q<-if(cohort=='ALL834')z else z[z$cohort==cohort,]
   if(!nrow(q))next
   eq<-initial+cumsum(q$net);dd<-cummax(c(initial,eq))[-1]-eq
   dry<-rle(q$hits==0);drymax<-max(c(0,dry$lengths[dry$values]))
   summary[[paste(policy,cohort)]]<-tibble::tibble(policy,cohort,issues=nrow(q),stake=sum(q$stake),
    gross=sum(q$gross),net=sum(q$net),roi=if(sum(q$stake)>0)sum(q$net)/sum(q$stake) else NA_real_,
    hit_issues=sum(q$hits>0),profit_issues=sum(q$net>0),local_max_drawdown=max(dd),
    full_curve_drawdown=max(q$drawdown),longest_no_hit=drymax,
    min_bankroll=min(c(initial,eq)),max_drawdown_pct=max(dd/cummax(c(initial,eq))[-1]))
  }
 }
 list(curves=dplyr::bind_rows(curves),summary=dplyr::bind_rows(summary))
}
