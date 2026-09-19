# Pure descriptive projection of a saved goal-difference distribution.
# distribution: unique integer net, finite nonnegative probability summing to1.
# handicap: signed integer added to home score; tolerance: explicit tie tolerance.
# step is 1 or .5; metric is unconditional |W-L| or conditional |W-L|/(W+L).
# Conditional candidates with non-draw mass <= tolerance are unavailable.
# All support-covering lines at the requested step are examined. Integer nets
# permit exact CDF lookup at -line and -line-.25 (strict lower side).
# Ties are reported, and the
# representative minimizes abs(line), then signed line; actual line never breaks
# ties. No labels, fitting, price selection, I/O, or future admission is involved.
handicap_line_gap <- function(distribution,handicap,tolerance,step=1,metric='unconditional') {
 stopifnot(all(c('net','probability') %in% names(distribution)),nrow(distribution)>0,
  !anyNA(distribution),!anyDuplicated(distribution$net),all(is.finite(distribution$net)),all(distribution$net==round(distribution$net)),
  all(is.finite(distribution$probability)),all(distribution$probability>=0),abs(sum(distribution$probability)-1)<1e-8,
  length(handicap)==1,is.finite(handicap),handicap==round(handicap),length(tolerance)==1,is.finite(tolerance),tolerance>=0,
  length(step)==1,step %in% c(1,.5),length(metric)==1,metric %in% c('unconditional','conditional'))
 lines<-seq(-max(distribution$net)-1,-min(distribution$net)+1,by=step)
 d<-distribution[order(distribution$net),];cdf<-c(0,cumsum(d$probability))
 w<-sum(d$probability)-cdf[findInterval(-lines,d$net)+1L]
 l<-cdf[findInterval(-lines-.25,d$net)+1L]
 objective<-abs(w-l)
 if(metric=='conditional')objective<-ifelse(w+l>tolerance,objective/(w+l),Inf)
 stopifnot(any(is.finite(objective)))
 best<-lines[is.finite(objective)&objective<=min(objective)+tolerance]
 hstar<-best[order(abs(best),best)][1]
 qw<-sum(distribution$probability[distribution$net+handicap>0]);ql<-sum(distribution$probability[distribution$net+handicap<0]);qd<-sum(distribution$probability[distribution$net+handicap==0])
 tibble::tibble(optimal_line=hstar,optimal_min=min(best),optimal_max=max(best),ties=length(best),
  delta=handicap-hstar,imbalance=min(objective),q_W=qw,q_D=qd,q_L=ql,
  signal=if(length(best)>1)'AMBIGUOUS' else if(handicap>hstar)'W' else if(handicap<hstar)'L' else 'NONE')
}
