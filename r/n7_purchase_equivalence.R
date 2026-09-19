# Compare two frozen allocator results on the same fixture universe/cutoffs.
# Inputs have pool$options, pool$fixtures, pool$cutoffs, fit$selected and worlds.
# All eligible options and ordered purchased options are compared. Descriptive
# rule names and scalar vector names are ignored; fixture indices, canonical
# state IDs, depth, stake, probability mass and expected gross are compared.
# No fitting, selection, labels, I/O or mutation. Returns named logical checks.
# Both empty selections are valid. Invalid selected indices/cutoffs fail.
n7_purchase_equivalence <- function(left,right,cutoffs) {
 stopifnot(is.list(cutoffs),length(cutoffs)>0,
  identical(left$pool$cutoffs,cutoffs),identical(right$pool$cutoffs,cutoffs))
 for(x in list(left,right)) {
  stopifnot(all(c('pool','fit','worlds') %in% names(x)),
   all(c('fixtures','options','cutoffs') %in% names(x$pool)),
   'selected' %in% names(x$fit),is.list(x$pool$fixtures),is.matrix(x$worlds),!anyNA(x$worlds))
  selected<-x$fit$selected
  stopifnot(is.list(x$pool$options),is.numeric(selected),!anyNA(selected),!anyDuplicated(selected),
   all(selected==floor(selected)),all(selected %in% seq_along(x$pool$options)))
 }
 fields<-c('sleeve_id','fixtures','state_ids','depth','stake','coverage','expected_gross')
 checks<-logical(2)
 for(i in seq_len(2)) {
  a<-if(i==1)left$pool$options else left$pool$options[left$fit$selected]
  b<-if(i==1)right$pool$options else right$pool$options[right$fit$selected]
  equal<-length(a)==length(b)
  if(equal)for(j in seq_along(a)) {
   stopifnot(all(fields %in% names(a[[j]])),all(fields %in% names(b[[j]])))
   for(opt in list(a[[j]],b[[j]])) {
    stopifnot(is.numeric(opt$state_ids),length(opt$state_ids)>0,
     !anyNA(opt$state_ids),!anyDuplicated(opt$state_ids),all(opt$state_ids %in% 1:2187),
     is.numeric(opt$fixtures),length(opt$fixtures)==7,!anyDuplicated(opt$fixtures),
     all(is.finite(opt$fixtures)),all(opt$fixtures>=1),all(opt$fixtures==floor(opt$fixtures)),
     length(opt$depth)==1,is.numeric(opt$depth),opt$depth==length(opt$state_ids),
     length(opt$stake)==1,is.numeric(opt$stake),is.finite(opt$stake),opt$stake==2*opt$depth,
     length(opt$sleeve_id)==1,!is.na(opt$sleeve_id),
     length(opt$coverage)==1,is.finite(opt$coverage),opt$coverage>=0,opt$coverage<=1,
     length(opt$expected_gross)==1,is.finite(opt$expected_gross),opt$expected_gross>=0)
   }
   for(field in fields) {
    av<-unname(a[[j]][[field]]);bv<-unname(b[[j]][[field]])
    stopifnot(!anyNA(av),!anyNA(bv))
    equal<-equal && isTRUE(all.equal(av,bv,tolerance=1e-12,check.attributes=FALSE))
   }
  }
  checks[i]<-equal
 }
 c(fixtures=identical(left$pool$fixtures,right$pool$fixtures),
   pool_options=checks[1],selected_tickets=checks[2],worlds=identical(left$worlds,right$worlds))
}
