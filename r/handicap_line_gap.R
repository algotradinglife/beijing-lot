# Pure descriptive projection of a saved goal-difference distribution.
# distribution: unique integer net, finite nonnegative probability summing to1.
# handicap: signed integer added to home score; tolerance: explicit tie tolerance.
# All support-covering integer lines are examined. Ties are reported, and the
# representative minimizes abs(line), then signed line; actual line never breaks
# ties. No labels, fitting, price selection, I/O, or future admission is involved.
handicap_line_gap <- function(distribution,handicap,tolerance) {
 stopifnot(all(c('net','probability') %in% names(distribution)),nrow(distribution)>0,
  !anyNA(distribution),!anyDuplicated(distribution$net),all(is.finite(distribution$net)),all(distribution$net==round(distribution$net)),
  all(is.finite(distribution$probability)),all(distribution$probability>=0),abs(sum(distribution$probability)-1)<1e-8,
  length(handicap)==1,is.finite(handicap),handicap==round(handicap),length(tolerance)==1,is.finite(tolerance),tolerance>=0)
 lines<-seq(-max(distribution$net)-1,-min(distribution$net)+1)
 w<-vapply(lines,function(h)sum(distribution$probability[distribution$net+h>0]),numeric(1))
 l<-vapply(lines,function(h)sum(distribution$probability[distribution$net+h<0]),numeric(1))
 best<-lines[abs(w-l)<=min(abs(w-l))+tolerance]
 hstar<-best[order(abs(best),best)][1]
 qw<-sum(distribution$probability[distribution$net+handicap>0]);ql<-sum(distribution$probability[distribution$net+handicap<0]);qd<-sum(distribution$probability[distribution$net+handicap==0])
 tibble::tibble(optimal_line=hstar,optimal_min=min(best),optimal_max=max(best),ties=length(best),
  delta=handicap-hstar,imbalance=min(abs(w-l)),q_W=qw,q_D=qd,q_L=ql,
  signal=if(length(best)>1)'AMBIGUOUS' else if(handicap>hstar)'W' else if(handicap<hstar)'L' else 'NONE')
}
