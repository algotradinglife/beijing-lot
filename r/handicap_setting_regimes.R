# Descriptive setting/composition diagnostic; no fitting or decision rules.
# frame: unique issue/slot/provider_id with year, signed integer handicap,
# average decimal odds_W/D/L, nullable mapped lambda_home/away and READY labels.
# breaks and complete_years are declared before inspection, minimum_support is
# a descriptive common-cell reporting floor, never a betting admission gate.
# Returns yearly/cell tables, explicit overlap coverage and an order-dependent
# decomposition of zero-handicap share. No I/O; missing means form UNKNOWN.
handicap_setting_regimes <- function(frame,strength_breaks,total_breaks,complete_years,minimum_support,condition_on_total=TRUE) {
  keys<-c('issue','slot','provider_id')
  stopifnot(nrow(frame)>0,all(c(keys,'year','handicap',paste0('odds_',c('W','D','L')),'lambda_home','lambda_away') %in% names(frame)),
    !anyDuplicated(frame[keys]),!anyNA(frame[c(keys,'year','handicap')]),all(is.finite(frame$handicap)),all(frame$handicap==round(frame$handicap)),
    length(complete_years)>=2,!anyDuplicated(complete_years),all(complete_years %in% frame$year),
    minimum_support>=1,length(minimum_support)==1,is.logical(condition_on_total),length(condition_on_total)==1,!is.na(condition_on_total),
    all(diff(strength_breaks)>0),head(strength_breaks,1)==-1,tail(strength_breaks,1)==1,
    all(diff(total_breaks)>0),head(total_breaks,1)==0,is.infinite(tail(total_breaks,1)))
  odds<-as.matrix(frame[paste0('odds_',c('W','D','L'))]);stopifnot(all(is.finite(odds)),all(odds>1))
  means<-as.matrix(frame[c('lambda_home','lambda_away')]);stopifnot(all(is.na(means)|is.finite(means)&means>0))
  euro<-1/odds;euro<-euro/rowSums(euro)
  x<-frame |> dplyr::mutate(euro_W=euro[,1],euro_D=euro[,2],euro_L=euro[,3],
    strength=euro_W-euro_L,total=lambda_home+lambda_away,
    strength_bin=as.character(cut(strength,strength_breaks,include.lowest=TRUE)),
    total_bin=dplyr::if_else(is.na(total),'UNKNOWN',as.character(cut(total,total_breaks,include.lowest=TRUE))),
    cell=if(condition_on_total)paste(strength_bin,total_bin,sep=' / ') else strength_bin,zero=as.numeric(handicap==0))
  annual<-x |> dplyr::group_by(year) |> dplyr::summarise(fixtures=dplyr::n(),issues=dplyr::n_distinct(issue),
    zero_share=mean(zero),home_gives=mean(handicap<0),away_gives=mean(handicap>0),
    mean_handicap=mean(handicap),mean_euro_gap=mean(strength),mapped_total_known=sum(!is.na(total)),.groups='drop')
  cells<-x |> dplyr::mutate(total_bin=if(condition_on_total)total_bin else 'NOT_CONDITIONED') |> dplyr::group_by(year,cell,strength_bin,total_bin) |> dplyr::summarise(n=dplyr::n(),issues=dplyr::n_distinct(issue),
    zero_share=mean(zero),mean_handicap=mean(handicap),.groups='drop')
  eligible<-cells |> dplyr::filter(year %in% complete_years,total_bin!='UNKNOWN') |> dplyr::group_by(cell) |>
    dplyr::summarise(years=dplyr::n_distinct(year),minimum=min(n),.groups='drop') |>
    dplyr::filter(years==length(complete_years),minimum>=minimum_support)
  common<-x |> dplyr::filter(year %in% complete_years,cell %in% eligible$cell)
  coverage<-annual |> dplyr::filter(year %in% complete_years) |>
    dplyr::left_join(common |> dplyr::count(year,name='common_n'),by='year',relationship='one-to-one') |>
    dplyr::mutate(common_n=dplyr::coalesce(common_n,0L),common_share=common_n/fixtures)
  # Empty common support is explicit, not an imputed zero effect.
  standardized<-tibble::tibble(year=character(),standard_zero=double(),common_cells=integer())
  decomposition<-tibble::tibble(reference=character(),target=character(),reference_mean=double(),target_mean=double(),composition=double(),within=double(),change=double())
  if(nrow(common)>0){
    weights<-common |> dplyr::count(cell,name='pooled_n') |> dplyr::mutate(weight=pooled_n/sum(pooled_n))
    standardized<-cells |> dplyr::filter(year %in% complete_years,cell %in% eligible$cell) |>
      dplyr::left_join(weights,by='cell',relationship='many-to-one') |> dplyr::group_by(year) |>
      dplyr::summarise(standard_zero=sum(weight*zero_share),common_cells=dplyr::n(),.groups='drop')
    d<-common |> dplyr::transmute(segment=year,stratum=cell,value=zero)
    decomposition<-dplyr::bind_rows(lapply(complete_years[-1],function(y)
      strategy_composition_diagnostics(d,complete_years[1],y)$summary))
  }
  list(fixtures=x,annual=annual,cells=cells,coverage=coverage,standardized=standardized,decomposition=decomposition)
}
