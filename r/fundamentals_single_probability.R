# Descriptive diagnostics of settled fixed groups; no fitting or routing.
# legs: one row per policy/issue/component/slot,7 rows and2 singles per group,
# normalized p/q WDL, support in310, observed actual_direction WDL.
# Explicit probability bin breaks cover[0,1]. Returns group metrics and tidy
# calibration bins. Joint products assume fixture independence. Group holdings
# overlap; counts are not independent matches. Missing/empty/invalid data fail.
# No I/O, cutoff selection, threshold tuning or source mutation.
single_probability_diagnostics <- function(legs,minimum_breaks,joint_breaks) {
 required<-c("issue","policy","component","slot","support","actual_direction",
             "p_W","p_D","p_L","q_W","q_D","q_L")
 stopifnot(all(required %in% names(legs)),nrow(legs)>0,
   !anyNA(legs[required]),!anyDuplicated(legs[c("issue","policy","component","slot")]),
   all(legs$actual_direction %in% c("W","D","L")),
   all(legs$support %in% c("3","1","0","31","30","10")))
 for (breaks in list(minimum_breaks,joint_breaks)) {
   stopifnot(is.numeric(breaks),length(breaks)>=2,all(is.finite(breaks)),
             breaks[1]==0,tail(breaks,1)==1,all(diff(breaks)>0))
 }
 for (prefix in c("p","q")) {
   mat<-as.matrix(legs[paste0(prefix,"_",c("W","D","L"))])
   stopifnot(all(is.finite(mat)),all(mat>=0 & mat<=1),all(abs(rowSums(mat)-1)<1e-10))
 }
 sizes<-legs |> dplyr::group_by(issue,policy,component) |>
   dplyr::summarise(n=dplyr::n(),singles=sum(nchar(support)==1),.groups="drop")
 stopifnot(all(sizes$n==7),all(sizes$singles==2))
 x<-legs |> dplyr::mutate(single=nchar(support)==1,
   actual_code=dplyr::recode(actual_direction,W="3",D="1",L="0"),
   hit=stringr::str_detect(support,actual_code),
   ps=dplyr::case_when(support=="3"~p_W,support=="1"~p_D,support=="0"~p_L),
   qs=dplyr::case_when(support=="3"~q_W,support=="1"~q_D,support=="0"~q_L),
   ms=(ps+qs)/2)
 groups<-x |> dplyr::group_by(issue,policy,component) |>
   dplyr::summarise(P_min=min(ps[single]),Q_min=min(qs[single]),MIX_min=min(ms[single]),
     P_joint=prod(ps[single]),Q_joint=prod(qs[single]),MIX_joint=prod(ms[single]),
     both_hit=all(hit[single]),group_hit=all(hit),.groups="drop")
 long<-groups |> tidyr::pivot_longer(cols=c(P_min,Q_min,MIX_min,P_joint,Q_joint,MIX_joint),
   names_to=c("basis","metric"),names_sep="_",values_to="probability")
 bins<-list()
 for (metric_name in c("min","joint")) {
   b<-if(metric_name=="min")minimum_breaks else joint_breaks
   z<-long |> dplyr::filter(metric==metric_name) |>
      dplyr::mutate(bin=cut(probability,b,include.lowest=TRUE,right=FALSE))
   stopifnot(!anyNA(z$bin))
   bins[[metric_name]]<-z |> dplyr::group_by(policy,basis,metric,bin) |>
      dplyr::summarise(groups=dplyr::n(),issues=dplyr::n_distinct(issue),
        mean_probability=mean(probability),both_hit_rate=mean(both_hit),
        group_hit_rate=mean(group_hit),.groups="drop") |>
      dplyr::mutate(bin=as.character(bin))
 }
 list(groups=groups,bins=dplyr::bind_rows(bins))
}
