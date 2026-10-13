# Descriptive error/counterexample inventory, not a prediction router or fitted rule.
root<-normalizePath(commandArgs(TRUE)[1],mustWork=TRUE)
suppressPackageStartupMessages(library(tidyverse));library(jsonlite)
library(beidan,lib.loc=file.path(root,'results/fm17-release-20261013/library'))
out<-file.path(root,'results/fm17-diagnostic-iterations-20261013');dir.create(out,recursive=TRUE,showWarnings=FALSE)
src<-file.path(root,'results/fm17-three-issues-20261013');ev<-fromJSON(file.path(src,'evaluation.json'));m<-fromJSON(file.path(src,'manifest.json'))
paths<-c('results/fm17-three-issues-20261013/forecasts.rds','results/fm17-three-issues-20261013/changes.csv','results/fm17-three-issues-20261013/labels.csv','results/fm17-three-issues-20261013/scores.csv','results/fm16-three-issues-20261012/stage.rds','results/fm16-three-issues-20261012/forecasts.rds')
expected<-c(m$forecast_sha256,ev$changes_sha256,ev$labels_csv_sha256,ev$scores_sha256,m$source_hashes$parent_stage,m$source_hashes$parent_forecast)
stopifnot(all(map_chr(file.path(root,paths),~digest::digest(file=.x,algo='sha256'))==expected))
x<-readRDS(file.path(root,paths[1]));s<-readRDS(file.path(root,paths[5]));old<-readRDS(file.path(root,paths[6]))
changes<-read_csv(file.path(root,paths[2]),show_col_types=FALSE)
labels<-read_csv(file.path(root,paths[3]),col_types=cols(fixture_id=col_character(),score=col_character(),actual_outcome=col_character())) |>
 mutate(actual_margin=as.integer(str_extract(score,'^[0-9]+'))-as.integer(str_extract(score,'[0-9]+$')))
features<-ordinary<-margins<-parameters<-list()
for(id in labels$fixture_id) {
 z<-x$entries[[id]];p<-s$packets[[id]];f<-s$native[[id]]$fixture
 r<-z$results[['FM-1.7.0']];raw<-z$results[['FM17-source-before-tail']]
 actual<-labels$actual_margin[match(id,labels$fixture_id)]
 ps<-x$probabilities |> filter(fixture_id==id,model=='FM-1.7.0') |> arrange(rank)
 g<-r$final$margins;before<-raw$final$margins
 hw<-sum(g$probability[g$margin>0]);aw<-sum(g$probability[g$margin<0]);dr<-sum(g$probability[g$margin==0])
 q<-p$euro;market_home<-market_draw<-market_away<-NA_real_
 if(!is.null(q)&&nrow(q)>0L) {
  inv<-1/as.matrix(q[c('odds_home','odds_draw','odds_away')]);v<-colMeans(inv/rowSums(inv))
  market_home<-unname(v[1]);market_draw<-unname(v[2]);market_away<-unname(v[3])
 }
 lh<-if(z$parent_selection$selected_source=='market')p$market_parameters$lambda_home else p$native_parameters$lambda_home
 la<-if(z$parent_selection$selected_source=='market')p$market_parameters$lambda_away else p$native_parameters$lambda_away
 features[[id]]<-tibble(fixture_id=id,competition=p$competition,handicap=as.integer(f$handicap),actual_margin=actual,actual_in_core=actual%in%r$core$core_margins,ordinary_home=hw,ordinary_draw=dr,ordinary_away=aw,direction_reversed=(actual>0&&aw>hw+1e-12)||(actual<0&&hw>aw+1e-12),mean_margin_before=sum(before$margin*before$probability),mean_margin_after=sum(g$margin*g$probability),lambda_home=lh,lambda_away=la,native_lambda_home=p$native_parameters$lambda_home,native_lambda_away=p$native_parameters$lambda_away,top1_probability=ps$probability[1],top12_gap=ps$probability[1]-ps$probability[2],top23_gap=ps$probability[2]-ps$probability[3],market_available=p$market_available,euro_companies=p$euro_companies,asian_rows=if(is.null(p$asian))0L else nrow(p$asian),total_rows=if(is.null(p$totals))0L else nrow(p$totals),market_error=p$market_error,euro_home=market_home,euro_draw=market_draw,euro_away=market_away)
 margins[[id]]<-g |> mutate(fixture_id=id,stage='FM17',actual=margin==.env$actual,.before=1)
 margins[[paste0(id,'-raw')]]<-before |> mutate(fixture_id=id,stage='source-before-tail',actual=margin==.env$actual,.before=1)
 parameters[[id]]<-p$native_rates |> mutate(fixture_id=id,.before=1)
}
a<-changes |> left_join(bind_rows(features),by='fixture_id',relationship='one-to-one') |>
 mutate(bd_top1_fm_top1_loss=`top1_北单-后期SP`&!`top1_FM-1.7.0`,bd_top1_fm_top2_loss=`top1_北单-后期SP`&!`top2_FM-1.7.0`,raw_top1_tail_loss=`top1_FM17-source-before-tail`&!`top1_FM-1.7.0`,raw_top2_tail_loss=`top2_FM17-source-before-tail`&!`top2_FM-1.7.0`,fm16_top1_loss=`top1_FM-1.6.0`&!`top1_FM-1.7.0`,fm16_top2_loss=`top2_FM-1.6.0`&!`top2_FM-1.7.0`,delta_ll_bd=`logloss_FM-1.7.0`-`logloss_北单-后期SP`,delta_ll_tail=`logloss_FM-1.7.0`-`logloss_FM17-source-before-tail`,p_actual=exp(-`logloss_FM-1.7.0`),p_actual_raw=exp(-`logloss_FM17-source-before-tail`),p_actual_bd=exp(-`logloss_北单-后期SP`),competition_type=case_when(str_detect(competition,'U[0-9]|青年|亚运|奥运')~'age_group',str_detect(competition,'友谊|国际|世预|欧国|亚洲杯|欧洲杯|美洲杯')~'national_or_international',str_detect(competition,'杯')~'cup',TRUE~'other_league_or_unknown'))
stopifnot(nrow(a)==345L,!anyDuplicated(a$fixture_id),all(is.finite(a$lambda_home)&is.finite(a$lambda_away)))
summary<-a |> group_by(issue_id,selected_source) |> summarise(n=n(),bd1_fm1_loss=sum(bd_top1_fm_top1_loss),bd1_fm2_loss=sum(bd_top1_fm_top2_loss),raw1_tail_loss=sum(raw_top1_tail_loss),raw2_tail_loss=sum(raw_top2_tail_loss),reversed_direction=sum(direction_reversed),actual_outside_core=sum(!actual_in_core),mean_delta_ll_bd=mean(delta_ll_bd),mean_delta_ll_tail=mean(delta_ll_tail),.groups='drop')
# Explicit outcome-selected diagnostic strata; no selected row governs prediction.
shortlist<-bind_rows(a |> filter(bd_top1_fm_top2_loss) |> mutate(stratum='BD_TOP1_FM_TOP2_MISS'),a |> filter(raw_top2_tail_loss) |> arrange(desc(delta_ll_tail)) |> slice_head(n=4) |> mutate(stratum='RAW_TOP2_TAIL_MISS'),a |> filter(fm16_top1_loss) |> mutate(stratum='FM16_TOP1_FM17_MISS'),a |> filter(!`top1_FM-1.7.0`,top1_probability>=.6) |> arrange(desc(top1_probability)) |> slice_head(n=3) |> mutate(stratum='CONFIDENT_MISS'),a |> filter(`top1_FM-1.7.0`,!`top1_北单-后期SP`) |> arrange(delta_ll_bd) |> slice_head(n=3) |> mutate(stratum='SUCCESS_COUNTEREXAMPLE'))
ids<-unique(shortlist$fixture_id)
write_csv(a,file.path(out,'round1-fixtures.csv'));write_csv(summary,file.path(out,'round1-summary.csv'));write_csv(shortlist,file.path(out,'round1-shortlist.csv'));write_csv(bind_rows(margins),file.path(out,'round1-margins.csv'));write_csv(bind_rows(parameters),file.path(out,'round1-native-rates.csv'))
saveRDS(list(cases=a |> filter(fixture_id%in%ids),packets=s$packets[ids],native=s$native[ids],fm17=x$entries[ids],fm16=old$entries[ids]),file.path(out,'round1-cases.rds'))
write_json(list(round=1,intended_use='OUTCOME_SELECTED_POSTHOC_DIAGNOSTIC',prediction_updates=FALSE,case_count=length(ids),case_ids=ids,selection_policy='All BD-top1/FM-top2 misses; top4 raw-top2 losses by deltaLL; all FM16-top1 losses; top3 >=.6 confident misses; top3 successful counterexamples. No rule training.',inputs=tibble(path=paths,sha256=expected),client_sha256=digest::digest(file=file.path(root,'r/fm17_diagnostic_round1.R'),algo='sha256'),outputs=tibble(path=c('round1-fixtures.csv','round1-summary.csv','round1-shortlist.csv','round1-margins.csv','round1-native-rates.csv','round1-cases.rds'),sha256=map_chr(file.path(out,c('round1-fixtures.csv','round1-summary.csv','round1-shortlist.csv','round1-margins.csv','round1-native-rates.csv','round1-cases.rds')),~digest::digest(file=.x,algo='sha256')))),file.path(out,'round1-receipt.json'),auto_unbox=TRUE,pretty=TRUE)
print(summary,width=Inf)
print(shortlist |> select(fixture_id,home,away,competition,selected_source,stratum,delta_ll_bd,delta_ll_tail,actual_in_core,direction_reversed),n=30,width=Inf)
