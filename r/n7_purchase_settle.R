# Post-freeze settlement of explicit canonical ticket selections. The plan seal
# binds issue, fixture identity, options, cutoffs and all purchase parameters.
# labels: unique issue/slot/provider_id, handicap, W/D/L actual_direction, spf_sp.
# Returns group rows; official SP is used only here. One ticket factor per payout.
n7_purchase_settle <- function(plan,labels,unit_cny,payout_factor) {
 stopifnot(identical(plan$seal,digest::digest(plan[names(plan)!='seal'],algo='sha256')),
  is.numeric(unit_cny),length(unit_cny)==1L,is.finite(unit_cny),unit_cny==2,
  is.numeric(payout_factor),length(payout_factor)==1L,is.finite(payout_factor),payout_factor==.65,
  all(c('issue','slot','provider_id','handicap','actual_direction','spf_sp') %in% names(labels)),
  !anyDuplicated(labels[c('issue','slot')]),!anyNA(labels),
  all(labels$actual_direction %in% c('W','D','L')),all(is.finite(labels$spf_sp)),all(labels$spf_sp>0))
 rows<-list()
 for(arm in names(plan$arms))for(o in plan$arms[[arm]]$options) {
  f<-dplyr::bind_rows(plan$fixtures[o$fixtures])
  l<-labels[labels$issue==plan$issue,];l<-l[match(f$slot,l$slot),]
  stopifnot(nrow(f)==7,!anyNA(l),identical(l$provider_id,f$provider_id),all(l$handicap==f$handicap))
  actual<-1+sum((match(l$actual_direction,c('W','D','L'))-1)*3^(6:0))
  hit<-actual %in% o$state_ids;copies<-o$stake/(unit_cny*length(o$state_ids))
  stopifnot(copies>=1,copies==floor(copies))
  rows[[length(rows)+1L]]<-tibble::tibble(issue=plan$issue,policy=arm,sleeve_id=o$sleeve_id,
   stake=o$stake,depth=length(o$state_ids),coverage=o$coverage,expected_gross=o$expected_gross,
   hit=hit,gross=if(hit)unit_cny*payout_factor*prod(l$spf_sp)*copies else 0)
 }
 dplyr::bind_rows(tibble::tibble(issue=character(),policy=character(),sleeve_id=double(),
  stake=double(),depth=integer(),coverage=double(),expected_gross=double(),hit=logical(),gross=double()),rows)
}
